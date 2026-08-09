"""Prepare and run only the compatibility server, without Android tooling.

No SDK, no adb, no Java, no signing key, and no connected device: this host
never prepares a client. It does derive its own generated catalogs from the
operator's APK when one is beside the resource tree, so a dedicated server is
one command rather than one command plus a list of files to copy from the
machine that builds the APK. That copy was the step operators skipped, and the
game it produced was quietly reduced rather than visibly broken.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
from typing import Sequence

from liminal_gate import tester_setup
from liminal_gate.character_catalog_importer import (
    CharacterCatalogImportError,
    build_character_catalog,
    load_master_trees,
    sha256_file,
    write_character_catalog,
)
from liminal_gate.companion_equipment_catalog import (
    DEFAULT_COMPANION_EQUIPMENT_CATALOG,
    CompanionEquipmentCatalogError,
    build_companion_equipment_catalog,
    write_companion_equipment_catalog,
)
from liminal_gate.coin_creeps_banner import CoinCreepsBannerError, prepare_coin_creeps_banners
from liminal_gate.pact_banner_importer import PactBannerImportError, prepare_pact_banners
from liminal_gate.event_catalog import DEFAULT_EVENT_CATALOG
from liminal_gate.resource_catalog import ResourceCatalogError
from liminal_gate.resource_catalog_builder import build_resource_manifest, report_resource_inventory, write_resource_manifest
from liminal_gate.luck_pool_catalog import DEFAULT_LUCK_POOL_CATALOG
from liminal_gate.server_config import STANDARD_POLICY_FLAGS
from liminal_gate.story_outcome_catalog import DEFAULT_OUTCOME_CATALOG
from liminal_gate.tuning import DEFAULT_TUNING_DOCUMENT, write_default_tuning
from liminal_gate.tester_setup import DEFAULT_APK, REQUIRED_RESOURCE_CATEGORIES


class ServerSetupError(RuntimeError):
    """The server-only environment is incomplete or unsafe to launch."""


@dataclass(frozen=True)
class Shortfall:
    """One thing this host is serving without, and what it costs a player."""

    title: str
    symptom: str
    reason: str
    fix: str


class StartupReport:
    """Collect every shortfall so startup ends with all of them in one place.

    Each of these was already reported at the moment it happened, which is the
    wrong moment to read it: derivation, banner preparation, and the catalog
    resolvers are minutes and hundreds of lines apart, and an operator watching
    a first start -- or scrolling back through `journalctl` after a player
    reports something -- sees the end. A host that is serving a reduced game
    should say so last, in one block, naming what a player will actually hit
    rather than which file is absent.
    """

    #: Wide enough for the longest line the block below renders, and fixed so
    #: the frame does not change width between hosts.
    WIDTH = 74

    def __init__(self) -> None:
        self.shortfalls: list[Shortfall] = []
        #: Why derivation did not leave this host with its catalogs, recorded
        #: separately because it is a cause rather than a shortfall: a host
        #: whose catalogs were copied in by hand has this set and is missing
        #: nothing, and one that is missing three catalogs has one cause, not
        #: three. The resolvers below report what is actually absent and quote
        #: this as the reason.
        self.derivation_reason: str | None = None

    def note(self, title: str, symptom: str, reason: str, fix: str) -> None:
        self.shortfalls.append(Shortfall(title, symptom, reason, fix))

    def why_missing(self, default: str) -> str:
        return self.derivation_reason or default

    def _wrapped(self, label: str, value: str) -> list[str]:
        """Wrap one labelled line, hanging the continuation under its value.

        Long words are never split. Every value here can contain a path, and a
        path broken across two lines -- on one of its own hyphens, at that --
        cannot be copied back out of a terminal or a `journalctl` page. An
        overrun line is the smaller cost.
        """
        return textwrap.wrap(
            f"{label}{value}",
            width=self.WIDTH,
            subsequent_indent=" " * len(label),
            break_long_words=False,
            break_on_hyphens=False,
        ) or [label]

    def render(self) -> str:
        """Return the closing block: a clear all-good line, or every shortfall.

        Shortfalls are grouped by cause. One absent APK costs three catalogs,
        and printing its reason and its correction under each of them buries
        the single thing to do under three copies of itself.
        """
        rule = "=" * self.WIDTH
        if not self.shortfalls:
            return (
                f"{rule}\n"
                "OK  Serving the complete local game: every generated catalog "
                "is present.\n"
                f"{rule}"
            )
        counted = (
            "1 problem" if len(self.shortfalls) == 1
            else f"{len(self.shortfalls)} problems"
        )
        lines = [
            rule,
            f"!!  This host is serving a REDUCED game -- {counted} found at startup",
            rule,
        ]
        causes: dict[tuple[str, str], list[Shortfall]] = {}
        for shortfall in self.shortfalls:
            causes.setdefault((shortfall.reason, shortfall.fix), []).append(shortfall)
        numbered = 0
        for (reason, fix), group in causes.items():
            for shortfall in group:
                numbered += 1
                lines.extend(self._wrapped(f"[{numbered}] ", shortfall.title))
                lines.extend(self._wrapped("     A player sees: ", shortfall.symptom))
            lines.extend(self._wrapped("     Why: ", reason))
            lines.extend(self._wrapped("     Fix: ", fix))
            lines.append("")
        lines.append("Everything else still works. See docs/dedicated-server.md")
        lines.append(rule)
        return "\n".join(lines)


DEFAULT_RESOURCES = Path("local-input/resources/data_u2017/android")
DEFAULT_DATA = Path("user-data")
DEFAULT_PROFILE = Path("profiles/legacy-client-bootstrap.json")

#: The character catalog is named directly rather than through a constant of
#: its own because three other modules already spell it this way; the remaining
#: three carry the names their own catalog modules publish.
DEFAULT_CHARACTER_CATALOG = "character-catalog.json"

#: Every catalog this host can derive from the operator's own APK. These used
#: to be generated on the APK workstation and copied here by hand, which is a
#: step that silently degrades the game when it is skipped: a host missing
#: `companion-equipment.json` refuses every new Companion equip, and the player
#: sees a Network Error rather than a missing file. A host holding the APK can
#: produce all four itself, so it does.
DERIVED_CATALOGS = (
    DEFAULT_CHARACTER_CATALOG,
    DEFAULT_COMPANION_EQUIPMENT_CATALOG,
    DEFAULT_OUTCOME_CATALOG,
    DEFAULT_EVENT_CATALOG,
)

#: The single correction for every derived catalog: this host derives them all
#: in one pass, so naming a per-catalog remedy would imply four separate
#: repairs where there is one.
DERIVATION_FIX = (
    "put your APK beside the resource tree and restart; if a tool is missing, "
    "python3 -m liminal_gate.doctor --install-missing"
)


def resolve_resource_root(requested: Path) -> Path:
    """Find and validate the final data_u2017/android resource directory.

    One probe serves both deployment layouts: this delegates to the guided
    setup's resolver so the two paths can never disagree about what a valid
    resource root is, and only the error type is this launcher's own.
    """
    try:
        return tester_setup.resolve_resource_root(requested)
    except tester_setup.TesterSetupError as error:
        raise ServerSetupError(str(error)) from error


def prepare_coin_creeps_cards(
    apk: Path,
    resource_root: Path,
    data_directory: Path,
    report: StartupReport | None = None,
) -> None:
    """Derive the Attack of Coin Creeps card bundles, or say what is missing.

    The client asks for `sp1003-1` and `sp1003-2` for this family whatever
    chapter the server advertises it under, and the final archive retained
    neither: they are derived from the retained `sp3003-1` art instead, under
    the internal names the client looks up. Without them every request 404s and
    the client retries in a tight loop, which a player sees as the Hunting
    cards flashing rather than as a missing image.

    Guided setup has always derived them. This launcher had not, so a dedicated
    server served a Hunting screen it could never draw -- the same shape of gap
    as a policy no launcher passes. It is best effort rather than fatal: an
    operator running a server-only host may reasonably have no APK and no
    master-import extra, and neither is worth refusing to start over. What is
    not acceptable is failing silently, so every reason names itself and says
    what a player will see.
    """
    try:
        prepare_coin_creeps_banners(apk, resource_root, data_directory / "public_data")
    except (CoinCreepsBannerError, OSError, ValueError) as error:
        print(
            f"Attack of Coin Creeps cards not derived: {error}\n"
            "  Those cards will flash in the Hunting selector until this is resolved. "
            'Install the extra with: pip install ".[master-import]"'
        )
        if report is not None:
            report.note(
                "Attack of Coin Creeps card artwork is missing",
                "those cards flash in the Hunting selector",
                str(error),
                'pip install ".[master-import]"',
            )
    # The Pact banners are the same shape of artifact from the same inputs, and
    # were one-sided for the same reason. Their absence is milder -- the Pact
    # screens miss artwork rather than looping a request -- so it is reported
    # and not treated as a failure, exactly as guided setup already treats it.
    try:
        prepare_pact_banners(apk, resource_root, data_directory / "public_data")
    except (PactBannerImportError, OSError, ValueError) as error:
        print(f"Pact banner preparation skipped: {error}")
        if report is not None:
            report.note(
                "Pact banner artwork is missing",
                "the Pact screens draw without their banner images",
                str(error),
                'pip install ".[master-import]"',
            )


def catalogs_match_apk(data_directory: Path, apk_sha256: str) -> bool:
    """Report whether every derived catalog already came from this APK.

    Deriving disassembles every chapter program, which costs minutes, so a
    restart must not repeat work an earlier run already published -- an
    always-on host restarts for reasons that have nothing to do with its APK.
    Each catalog records the APK it was derived from, so the question is
    answered from the files themselves rather than from a marker this launcher
    would have to keep in step with them.
    """
    documents: dict[str, object] = {}
    for name in DERIVED_CATALOGS:
        path = data_directory / name
        if not path.is_file():
            return False
        try:
            documents[name] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            # An unreadable catalog is not a current one, and deriving over it
            # is the repair. Refusing to start would strand a host whose only
            # fault is a file truncated by a full disk.
            return False
    for name in (
        DEFAULT_CHARACTER_CATALOG,
        DEFAULT_COMPANION_EQUIPMENT_CATALOG,
        DEFAULT_OUTCOME_CATALOG,
    ):
        document = documents[name]
        source = document.get("source") if isinstance(document, dict) else None
        if not isinstance(source, dict) or source.get("apk_sha256") != apk_sha256:
            return False
    # The event catalog names no APK of its own: it is a join of battle data
    # against the character catalog, and records that catalog's digest instead.
    # Checking it against the character catalog on disk keeps the pair honest
    # even when only one of the two was replaced by hand.
    event_catalog = documents[DEFAULT_EVENT_CATALOG]
    return isinstance(event_catalog, dict) and event_catalog.get(
        "character_catalog_sha256"
    ) == sha256_file(data_directory / DEFAULT_CHARACTER_CATALOG)


def derive_local_catalogs(
    apk: Path,
    data_directory: Path,
    force: bool = False,
    report: StartupReport | None = None,
) -> None:
    """Derive this host's four APK-backed catalogs, or say what is missing.

    A dedicated host used to receive these from the setup workstation by hand.
    That copy is the step operators skip, and skipping it is invisible: the
    server starts, serves the story, and then refuses an ordinary Companion
    equip with a 501 the client shows as a Network Error. Since every one of
    them is derived from the operator's own APK, a host holding that APK needs
    no copy at all.

    Best effort, for the reason `prepare_coin_creeps_cards` gives: an operator
    may deliberately run a host with no APK and hand-placed catalogs, or with
    no derivation toolchain at all, and neither is worth refusing to start
    over. What is not acceptable is failing silently, so a shortfall names
    itself, says what a player loses, and says how to resolve it.
    """
    apk_sha256 = sha256_file(apk)
    # The digest answers "same APK", which is the question a restart asks. It
    # cannot answer "same generator": a release that corrects a derivation
    # leaves the APK untouched, so those catalogs still look current and an
    # operator following its changelog entry needs a way to say so.
    if not force and catalogs_match_apk(data_directory, apk_sha256):
        print(f"Generated catalogs: current for {apk}")
        return
    try:
        tester_setup.check_derivation_prerequisites(None, data_directory)
        reusable = tester_setup.reusable_il2cpp_dump(None, data_directory)
        if reusable is None:
            dummy_dll_dir, dump_cs = tester_setup.ensure_il2cpp_dump(apk, data_directory)
        else:
            dummy_dll_dir, dump_cs = reusable
            print(f"Reusing the local IL2CPP dump in {dummy_dll_dir.parent}.")
        trees = load_master_trees(
            apk, dummy_dll_dir, ("ChrDatabase", "ItemSet", "BuddyDatabase"),
        )
        write_character_catalog(
            data_directory / DEFAULT_CHARACTER_CATALOG,
            build_character_catalog(trees["ChrDatabase"], apk_sha256),
        )
        write_companion_equipment_catalog(
            data_directory / DEFAULT_COMPANION_EQUIPMENT_CATALOG,
            build_companion_equipment_catalog(
                trees["ChrDatabase"], trees["BuddyDatabase"], apk_sha256,
            ),
        )
        # Not consumed by the server, and derived here anyway: it is the
        # readable-name table the save editor and the account tools expect
        # beside a save, and this host is now the machine that has one.
        tester_setup.write_local_names(data_directory / "names.json", apk, trees)
        # Writes the story-outcome catalog and, from the same battle data, the
        # archive event catalog -- two of the four in one pass.
        tester_setup.derive_story_outcome_catalog(
            apk, dummy_dll_dir, data_directory, dump_cs,
        )
    except (
        tester_setup.TesterSetupError,
        CharacterCatalogImportError,
        CompanionEquipmentCatalogError,
        OSError,
        ValueError,
    ) as error:
        print(
            f"Generated catalogs not derived: {error}\n"
            "  This host serves without them: equipping a Companion is refused, "
            "story Companion drops are discarded, and the archive Special "
            "Quests, Tower, and Eidolon quests stay absent.\n"
            "  Install what is missing with: "
            "python3 -m liminal_gate.doctor --install-missing"
        )
        if report is not None:
            report.derivation_reason = f"could not derive it here: {error}"


def prepare_server(
    resource_root: Path,
    data_directory: Path,
    apk: Path | None = None,
    derive_catalogs: bool = True,
    rederive_catalogs: bool = False,
    report: StartupReport | None = None,
) -> tuple[Path, Path, int]:
    """Build the hash-validated resource manifest needed by the server."""
    resolved_resources = resolve_resource_root(resource_root)
    resolved_data = data_directory.resolve()
    resolved_data.mkdir(parents=True, exist_ok=True)
    if apk is not None and apk.is_file():
        if derive_catalogs:
            derive_local_catalogs(
                apk, resolved_data, force=rederive_catalogs, report=report,
            )
        prepare_coin_creeps_cards(apk, resolved_resources, resolved_data, report)
    elif apk is not None:
        print(
            f"Attack of Coin Creeps cards not derived: no APK at {apk}\n"
            "  Those cards will flash in the Hunting selector until this is resolved."
        )
        if derive_catalogs:
            print(
                f"Generated catalogs not derived: no APK at {apk}\n"
                "  A host with your own APK beside its resource tree derives "
                "them itself; without one they have to be generated with "
                "liminal_gate.tester_setup and copied into this data directory."
            )
        if report is not None and derive_catalogs:
            report.derivation_reason = (
                f"there is no APK at {apk} to derive it from"
            )
    if report is not None and not derive_catalogs:
        report.derivation_reason = (
            "--no-derive-catalogs was passed, so this host derived nothing"
        )
    # The tuning document is written here rather than documented into
    # existence: it is a short list of knobs with known defaults, so an
    # operator should find it already in front of them. Every override in it is
    # commented out, so a fresh install is byte-for-byte the bundled policy.
    if write_default_tuning(resolved_data / DEFAULT_TUNING_DOCUMENT):
        print(f"Wrote {resolved_data / DEFAULT_TUNING_DOCUMENT} -- rates, gates, and EXP, all commented out.")
    manifest = build_resource_manifest(resolved_resources)
    manifest_path = resolved_data / "resources.json"
    # Reported before the write, so the comparison is against the previous
    # build rather than against the manifest this one just published.
    report_resource_inventory(manifest, manifest_path)
    write_resource_manifest(manifest_path, manifest)
    return resolved_resources, resolved_data, len(manifest["resources"])


def resolve_story_outcome_catalog(requested: Path | None, data_directory: Path) -> Path | None:
    """Choose the story-outcome catalog to run with, if there is one.

    An explicit path must exist -- silently ignoring a mistyped one would look
    exactly like the failure it is meant to fix, a server that quietly drops
    every Companion.  With no explicit path the conventional name in the data
    directory is used when present, and its absence is not an error.
    """
    if requested is not None:
        resolved = requested.resolve()
        if not resolved.is_file():
            raise ServerSetupError(f"story-outcome catalog does not exist: {requested}")
        return resolved
    candidate = (data_directory / DEFAULT_OUTCOME_CATALOG).resolve()
    return candidate if candidate.is_file() else None


def resolve_companion_equipment_catalog(
    requested: Path | None, data_directory: Path,
) -> Path | None:
    """Choose the generated Companion equipment catalog, if deployed."""
    if requested is not None:
        resolved = requested.resolve()
        if not resolved.is_file():
            raise ServerSetupError(
                f"Companion equipment catalog does not exist: {requested}"
            )
        return resolved
    candidate = (
        data_directory / DEFAULT_COMPANION_EQUIPMENT_CATALOG
    ).resolve()
    return candidate if candidate.is_file() else None


def resolve_luck_pool_catalog(
    requested: Path | None, data_directory: Path,
) -> Path | None:
    """Choose an operator's own Luck chest pools, if there are any.

    Never bundled and never implied: the community record documents thirty
    story stages and this file is how an operator goes past that deliberately.
    An explicit path that does not exist is an error rather than a silent
    fallback, for the reason every other resolver here gives -- ignoring a
    mistyped path looks exactly like the failure it would cause.
    """
    candidate = (
        requested.resolve()
        if requested is not None
        else (data_directory / DEFAULT_LUCK_POOL_CATALOG).resolve()
    )
    if requested is not None and not candidate.is_file():
        raise ServerSetupError(f"Luck pool catalog does not exist: {requested}")
    return candidate if candidate.is_file() else None


def resolve_event_catalog(
    requested: Path | None, data_directory: Path,
) -> Path | None:
    """Choose a generated archive/Tower catalog and require its hash authority."""
    candidate = (
        requested.resolve()
        if requested is not None
        else (data_directory / DEFAULT_EVENT_CATALOG).resolve()
    )
    if requested is not None and not candidate.is_file():
        raise ServerSetupError(f"event catalog does not exist: {requested}")
    if not candidate.is_file():
        return None
    character_catalog = (data_directory / "character-catalog.json").resolve()
    if not character_catalog.is_file():
        raise ServerSetupError(
            f"event catalog {candidate} requires its matching local character "
            f"catalog at {character_catalog}"
        )
    return candidate


def server_arguments(
    resource_root: Path,
    data_directory: Path,
    host: str,
    port: int,
    profile: Path = DEFAULT_PROFILE,
    story_outcome_catalog: Path | None = None,
    companion_equipment_catalog: Path | None = None,
    event_catalog: Path | None = None,
    luck_pool_catalog: Path | None = None,
    interpolated_luck_pools: bool = True,
    enable_stamina: bool = False,
    tuning: Path | None = None,
) -> list[str]:
    """Build the standard server command without any client preparation."""
    # No `--outcome-strict` here: the catalog's job in the guided setup is to let
    # story Companion drops settle, and bounding the reported items and monsters
    # on top of that can only refuse clears, never enable one.
    luck_pool_flags = (
        [] if luck_pool_catalog is None else ["--luck-pool-catalog", str(luck_pool_catalog)]
    )
    if not interpolated_luck_pools:
        luck_pool_flags = luck_pool_flags + ["--no-interpolated-luck-pools"]
    outcome_flags = (
        [] if story_outcome_catalog is None else ["--story-outcome-catalog", str(story_outcome_catalog)]
    )
    equipment_flags = (
        []
        if companion_equipment_catalog is None
        else [
            "--companion-equipment-catalog",
            str(companion_equipment_catalog),
        ]
    )
    # The one optional document nothing generates, so the conventional path is
    # passed only when it exists: naming a missing file is an error, and every
    # host that never wrote one would hit it. An explicit path is passed as
    # given, and fails visibly if it is wrong.
    selected_tuning = tuning if tuning is not None else data_directory / DEFAULT_TUNING_DOCUMENT
    tuning_flags = (
        ["--tuning", str(selected_tuning.resolve())]
        if tuning is not None or selected_tuning.exists()
        else []
    )
    event_flags = (
        []
        if event_catalog is None
        else [
            "--event-catalog",
            str(event_catalog),
            "--character-catalog",
            str((data_directory / "character-catalog.json").resolve()),
        ]
    )
    return [
        sys.executable,
        "-m",
        "liminal_gate.bootstrap_server",
        "--profile",
        str(profile.resolve()),
        "--state-file",
        str(data_directory / "bootstrap-state.json"),
        "--host",
        host,
        "--port",
        str(port),
        "--event-log",
        str(data_directory / "events.jsonl"),
        "--resource-root",
        str(resource_root),
        "--resource-manifest",
        str(data_directory / "resources.json"),
        "--public-data-root",
        str(data_directory / "public_data"),
        *STANDARD_POLICY_FLAGS,
        # Outside the standard set on purpose: the meter is off unless this
        # host's operator asked for it, so the flag is emitted only when asked.
        *(["--enable-stamina"] if enable_stamina else []),
        *outcome_flags,
        *luck_pool_flags,
        *equipment_flags,
        *event_flags,
        *tuning_flags,
    ]


def run_server(arguments: Sequence[str]) -> None:
    """Run the compatibility server in the foreground and stop it cleanly."""
    process = subprocess.Popen(arguments, start_new_session=(os.name == "posix"))
    try:
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print("\nServer stopped.")
        return
    if return_code:
        raise subprocess.CalledProcessError(return_code, arguments)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-root", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument(
        "--apk",
        type=Path,
        default=DEFAULT_APK,
        help=(
            "your own APK, read only. This host derives its generated catalogs "
            "and both banner families from it, so nothing has to be copied here "
            "from the machine that prepares the client"
        ),
    )
    parser.add_argument(
        "--no-derive-catalogs",
        action="store_true",
        help=(
            "never derive the generated catalogs on this host; use whatever "
            f"copies of {', '.join(DERIVED_CATALOGS)} the data directory "
            "already holds"
        ),
    )
    parser.add_argument(
        "--rederive-catalogs",
        action="store_true",
        help=(
            "derive the generated catalogs again even though they already match "
            "this APK, for a release whose changelog says it corrects one of the "
            "derivations rather than the server"
        ),
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument(
        "--story-outcome-catalog",
        type=Path,
        help=(
            "story-outcome catalog enabling story Companion drops; defaults to "
            f"{DEFAULT_OUTCOME_CATALOG} in the data directory when that file exists"
        ),
    )
    parser.add_argument(
        "--companion-equipment-catalog",
        type=Path,
        help=(
            "generated Companion character/species restrictions; defaults to "
            f"{DEFAULT_COMPANION_EQUIPMENT_CATALOG} in the data directory when present"
        ),
    )
    parser.add_argument(
        "--no-interpolated-luck-pools",
        action="store_true",
        help=(
            "roll chests only for the thirty story stages the community record "
            "documents, instead of also donating a nearby documented chapter's "
            "pools to the rest"
        ),
    )
    parser.add_argument(
        "--luck-pool-catalog",
        type=Path,
        help=(
            "operator-supplied Luck Treasure Chest pools for stages the "
            "community record does not document; defaults to "
            f"{DEFAULT_LUCK_POOL_CATALOG} in the data directory when present"
        ),
    )
    parser.add_argument(
        "--event-catalog",
        type=Path,
        help=(
            "reviewed archive-event catalog; defaults to "
            f"{DEFAULT_EVENT_CATALOG} in the data directory when present"
        ),
    )
    parser.add_argument(
        "--enable-stamina",
        action="store_true",
        help=(
            "charge the client's own stamina meter for quest entry; without it "
            "the meter stays pinned full and entry is never gated by a timer"
        ),
    )
    parser.add_argument(
        "--tuning",
        type=Path,
        help=(
            "operator tuning document for Pact and Companion rates, Hunting "
            "availability, the two party gates, and the EXP multiplier; "
            f"defaults to {DEFAULT_TUNING_DOCUMENT} in the data directory when "
            "that file exists"
        ),
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="validate and hash resources without starting the server",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not args.host or any(character.isspace() for character in args.host):
            raise ServerSetupError("--host must be a non-empty address with no spaces")
        if not 1 <= args.port <= 65535:
            raise ServerSetupError("--port must be an integer from 1 through 65535")
        report = StartupReport()
        resource_root, data_directory, resource_count = prepare_server(
            args.resource_root,
            args.data_dir,
            args.apk,
            derive_catalogs=not args.no_derive_catalogs,
            rederive_catalogs=args.rederive_catalogs,
            report=report,
        )
        print(f"Prepared server resource manifest: {resource_count} mapped entries")
        print(f"Durable account state: {data_directory / 'bootstrap-state.json'}")
        outcome_catalog = resolve_story_outcome_catalog(
            args.story_outcome_catalog, data_directory
        )
        if outcome_catalog is None:
            print(
                "Story Companion drops: OFF (no story-outcome catalog; the client "
                "rolls them and the server discards them)\n"
                f"  This host derives {DEFAULT_OUTCOME_CATALOG} from your own APK; "
                "the reason it has not is reported above. See docs/dedicated-server.md"
            )
            report.note(
                f"{DEFAULT_OUTCOME_CATALOG} is missing",
                "every Companion a story clear rolls is silently discarded",
                report.why_missing(f"it is not in {data_directory}"),
                DERIVATION_FIX,
            )
        else:
            print(f"Story Companion drops: ON from {outcome_catalog}")
        equipment_catalog = resolve_companion_equipment_catalog(
            args.companion_equipment_catalog, data_directory,
        )
        if equipment_catalog is None:
            print(
                "Companion master restrictions: OFF (new equip targets are "
                f"refused without {DEFAULT_COMPANION_EQUIPMENT_CATALOG}, which a "
                "player sees as a Network Error)\n"
                "  This host derives it from your own APK; the reason it has not "
                "is reported above. See docs/dedicated-server.md"
            )
            report.note(
                f"{DEFAULT_COMPANION_EQUIPMENT_CATALOG} is missing",
                "equipping any Companion to any character fails with a Network "
                "Error the player has to force-close the game to escape",
                report.why_missing(f"it is not in {data_directory}"),
                DERIVATION_FIX,
            )
        else:
            print(f"Companion master restrictions: ON from {equipment_catalog}")
        event_catalog = resolve_event_catalog(
            args.event_catalog, data_directory,
        )
        if event_catalog is None:
            print(
                "Archive Special Quests, Tower, and Eidolon quests: OFF "
                "(no generated event catalog; "
                "bundled Strikes Back remains enabled)\n"
                f"  This host derives {DEFAULT_EVENT_CATALOG} and "
                f"{DEFAULT_CHARACTER_CATALOG} from your own APK; the reason it has "
                "not is reported above. See docs/dedicated-server.md"
            )
            report.note(
                f"{DEFAULT_EVENT_CATALOG} is missing",
                "the Archive Special Quests, Tower, and solo Eidolon quests are "
                "absent from the game",
                report.why_missing(f"it is not in {data_directory}"),
                DERIVATION_FIX,
            )
        else:
            print(
                "Archive Special Quests, Tower, and Eidolon quests: "
                f"ON from {event_catalog}"
            )
        luck_pool_catalog = resolve_luck_pool_catalog(
            args.luck_pool_catalog, data_directory,
        )
        if args.no_interpolated_luck_pools and luck_pool_catalog is None:
            print(
                "Luck Treasure Chests: the thirty story stages the community "
                "record documents; every other stage rolls six empty slots"
            )
        elif luck_pool_catalog is None:
            # Said plainly on every start. The thirty documented stages are the
            # record's; the rest are this project's arrangement of it, and a
            # running server should not let the two look alike.
            print(
                "Luck Treasure Chests: thirty story stages from the community "
                "record, and the rest donated from the nearest documented "
                "chapter (--no-interpolated-luck-pools to disable)"
            )
        else:
            # Named deliberately. These pools are the operator's own, not
            # anything this project recovered, and a running server should say
            # so rather than let invented contents look sourced.
            print(f"Luck Treasure Chests: operator pools from {luck_pool_catalog}")
        print(
            "Stamina meter: ON (quest entry charges it)"
            if args.enable_stamina
            else "Stamina meter: OFF (pinned full; pass --enable-stamina to charge it)"
        )
        # Standard, not an opt-in: `STANDARD_POLICY_FLAGS` carries it, so
        # saying anything conditional here would misreport what was launched.
        print("Inbox presents: recovered client shape (text and rewards render)")
        # Last, deliberately. The per-item reports above are spread across
        # minutes of derivation and hundreds of lines, and this is the point an
        # operator is actually looking at: the end of a foreground start, and
        # the end of what `journalctl -u project-liminal-gate` shows first.
        print(report.render())
        if args.prepare_only:
            return 0
        print(
            f"Starting server on http://{args.host}:{args.port}; "
            "press Control-C to stop it."
        )
        run_server(
            server_arguments(
                resource_root,
                data_directory,
                args.host,
                args.port,
                story_outcome_catalog=outcome_catalog,
                companion_equipment_catalog=equipment_catalog,
                event_catalog=event_catalog,
                luck_pool_catalog=luck_pool_catalog,
                interpolated_luck_pools=not args.no_interpolated_luck_pools,
                enable_stamina=args.enable_stamina,
                tuning=args.tuning,
            )
        )
    except (OSError, ResourceCatalogError, ServerSetupError, subprocess.CalledProcessError) as error:
        # Framed like the closing block above, and for the same reason: under
        # systemd this line is followed within seconds by the whole start
        # sequence again, and an unframed sentence is easy to lose in the
        # repetition.
        rule = "=" * StartupReport.WIDTH
        raise SystemExit(
            f"\n{rule}\n"
            f"!!  SERVER SETUP FAILED -- nothing is serving\n"
            f"{rule}\n"
            f"{error}\n"
            f"{rule}"
        ) from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
