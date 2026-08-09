"""Prepare and run only the compatibility server, without Android tooling."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

from liminal_gate import tester_setup
from liminal_gate.companion_equipment_catalog import (
    DEFAULT_COMPANION_EQUIPMENT_CATALOG,
)
from liminal_gate.event_catalog import DEFAULT_EVENT_CATALOG
from liminal_gate.resource_catalog import ResourceCatalogError
from liminal_gate.resource_catalog_builder import build_resource_manifest, report_resource_inventory, write_resource_manifest
from liminal_gate.luck_pool_catalog import DEFAULT_LUCK_POOL_CATALOG
from liminal_gate.server_config import STANDARD_POLICY_FLAGS
from liminal_gate.story_outcome_catalog import DEFAULT_OUTCOME_CATALOG
from liminal_gate.tuning import DEFAULT_TUNING_DOCUMENT
from liminal_gate.tester_setup import REQUIRED_RESOURCE_CATEGORIES


class ServerSetupError(RuntimeError):
    """The server-only environment is incomplete or unsafe to launch."""


DEFAULT_RESOURCES = Path("local-input/resources/data_u2017/android")
DEFAULT_DATA = Path("user-data")
DEFAULT_PROFILE = Path("profiles/legacy-client-bootstrap.json")


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


def prepare_server(resource_root: Path, data_directory: Path) -> tuple[Path, Path, int]:
    """Build the hash-validated resource manifest needed by the server."""
    resolved_resources = resolve_resource_root(resource_root)
    resolved_data = data_directory.resolve()
    resolved_data.mkdir(parents=True, exist_ok=True)
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
        resource_root, data_directory, resource_count = prepare_server(
            args.resource_root, args.data_dir
        )
        print(f"Prepared server resource manifest: {resource_count} mapped entries")
        print(f"Durable account state: {data_directory / 'bootstrap-state.json'}")
        outcome_catalog = resolve_story_outcome_catalog(
            args.story_outcome_catalog, data_directory
        )
        if outcome_catalog is None:
            print(
                "Story Companion drops: OFF (no story-outcome catalog; the client "
                "rolls them and the server discards them)"
            )
        else:
            print(f"Story Companion drops: ON from {outcome_catalog}")
        equipment_catalog = resolve_companion_equipment_catalog(
            args.companion_equipment_catalog, data_directory,
        )
        if equipment_catalog is None:
            print(
                "Companion master restrictions: OFF (new equip targets are "
                f"refused without {DEFAULT_COMPANION_EQUIPMENT_CATALOG})"
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
                "bundled Strikes Back remains enabled)"
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
        raise SystemExit(f"server setup failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
