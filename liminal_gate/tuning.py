"""Operator-tunable rates, gates, and multipliers for a local installation.

Every value here is one this project already had to choose rather than recover,
or one whose enforcement an operator may legitimately want to decline.  They
were previously module constants, which meant changing any of them was a source
edit -- fine for the person who wrote them, useless to someone running a
release.  This module keeps the constants as the defaults and adds one strict
document that can restate them at launch, so the same number is reachable both
ways: edit `DEFAULT_TUNING` for a build, pass `--tuning` for a run.

What belongs here is bounded by one rule.  A **recovered** value -- one read out
of the client, master data, or a capture -- is not tunable, because changing it
would make the server disagree with the client that shipped it.  A **local
policy** value is, because this project chose it and says so.  The Pact rates
below are policy from a secondary source; the Pact costs are recovered and are
carried here only so a house-rules installation can restate them deliberately,
which is why they are the only recovered numbers this document accepts.

The two gates are a third case: both limits are recovered, and enforcing them is
correct.  They are switchable because enforcement is nonetheless a choice an
operator can make about their own archive -- Dragon Road spent a long time
serving as this game's general-purpose EXP route on servers that never asserted
its species lock, and an operator restoring that deliberately is doing something
different from one who never knew the limit existed.  Both default to enforced.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import struct
import tomllib


class TuningError(ValueError):
    """A user-local tuning document is invalid."""


#: The conventional filename inside a launcher's data directory, matching
#: `DEFAULT_OUTCOME_CATALOG` and `DEFAULT_COMPANION_EQUIPMENT_CATALOG`.  Setup
#: writes the template below there, so an operator edits a file that is already
#: in front of them rather than learning a schema from documentation first.
DEFAULT_TUNING_DOCUMENT = "tuning.toml"

#: What setup writes when no tuning document exists yet.
#:
#: Every override is commented out, and that is the whole design: a commented
#: line shows the bundled default *and keeps tracking it*, so a later release
#: that corrects one of these numbers reaches an install that never touched it.
#: Writing the values out live would freeze them at install time and quietly
#: turn "the default" into "the default on the day you set this up" -- which is
#: how this project's one corrected Pact rate and one corrected roster ID would
#: have failed to reach anybody.
#:
#: `test_tuning` uncomments this mechanically and asserts the result loads to
#: exactly `DEFAULT_TUNING`, so the template cannot drift from the code.
DEFAULT_TUNING_TEMPLATE = '''# Operator tuning for Project Liminal Gate.
#
# Every override below is commented out. A commented line is not "unset" --
# it shows the bundled default and keeps following it, so a later release that
# corrects one of these numbers reaches you. Uncomment a line to take it over,
# and it stays where you put it from then on.
#
# What lives here is the half of what this server sends that had to be chosen
# rather than recovered from your client. Item and monster drop rates are not
# here and cannot be: the client rolls those from its own tables and never asks
# the server about them.
#
# Full reference: docs/advanced-configuration.md

schema_version = 1
provenance = "user-supplied"

[pact]
# How often a pull arrives decorated as a "+" Pact, as a percent of pulls. The
# one number here no source states -- both records say only "sometimes". Zero
# turns the "+" Pact off entirely.
# plus_chance_percent = 22
# Published gain ranges: 1 to 5 extra levels, and 0.5% to 3.0% Skill Boost (or
# Luck on a Fate-type pull), in the client's tenths of one percent.
# plus_levels = [1, 5]
# plus_tenths = [5, 30]
# Recovered costs. The Energy price is also what the client displays, so
# changing it changes the shown price and the charged price together.
# coin_cost = 3000
# energy_cost = 5
# fate_duplicate_luck = 50
# Pact of Truth class shares, in parts per million of one pull. Name all four
# classes; they must total exactly 1000000.
# truth_class_share_ppm = { z = 40000, ss = 100000, s = 150000, a_and_below = 710000 }
# What a duplicate grants, per class: [levels, skill-boost tenths].
# duplicate_gains = { z = [6, 120], ss_s = [5, 100], a_and_below = [1, 50] }

[companion]
# The Rare Companion pool's displayed class rates: Z 3%, SS 8%, S 10%, A 30%,
# B 49%. Same totalling rule as the Pact shares.
# rare_class_share_ppm = { z = 30000, ss = 80000, s = 100000, a = 300000, b = 490000 }
# The Normal Companion pool's class rates. No record of these survives, so
# unlike the line above they are a chosen policy, picked so that the Coin pool
# never beats the Energy pool for a class the two share.
# normal_class_share_ppm = { a = 80000, b = 120000, c = 300000, d = 500000 }
# The random strengthen EXP bonus, as [percent, weight] pairs. No production
# odds for it survive, so these weights are a chosen policy.
# strengthen_bonus_weights = [[0, 85], [25, 8], [50, 5], [100, 2]]

[hunting]
# The chapter each Hunting tier and each Metal Zone becomes permanently
# available after. The retired rotations were never captured, so this schedule
# is local policy. Give either ladder whole; neither may decrease.
# tier_unlock_chapters = [3, 9, 18]
# metal_unlock_chapters = [3, 8, 12, 17, 21, 26, 30]
# Puppet Show's per-clear item aggregate for optional --outcome-strict audits.
# Its board refills with no cumulative spawn counter, so no exact cap exists to
# recover. The bundled 74 is the highest stock-client result reported so far;
# exceeding it refuses the clear in strict mode rather than discarding items.
# puppet_show_item_aggregate = 74

[gates]
# Dragon Road and Machine Road admitting only Dragons and Machines, and
# Captive Golem's four sections admitting only their declared class band. Both
# limits are recovered and both are asserted by this server, because the client
# never walks the party. Enforcing them is still your call.
# species_limits = true
# class_bands = true

[exp]
# Extra battle EXP credited on top of what the client awards, as a percent.
# The client computes its own EXP, so this credits a further share on the
# server's roster rather than changing the result screen. It needs
# --clear-state-catalog for the level curve, and it switches off that catalog's
# experience audit. Read the EXP section of docs/advanced-configuration.md
# before raising this.
# multiplier_percent = 100

[client]
# The one setting here that is not sent by the server. It is applied by
# patching your own APK when you build it, so it takes effect on the next
# *rebuild* rather than the next restart, and a running server is unaffected.
# Seconds to drag a unit before the turn resolves. The client ships 4.0.
# Whole, half and quarter seconds all work; 1.0 to 30.0.
# drag_time_seconds = 4.0
'''


def write_default_tuning(path: Path) -> bool:
    """Write the commented template, and report whether it was written.

    Never overwrites: an operator's edits are the whole point of the file, and
    a setup rerun is the moment they would be lost.  A missing document is
    equivalent to an untouched one, so nothing is repaired or migrated here.
    """
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(DEFAULT_TUNING_TEMPLATE, encoding="utf-8")
    return True


#: The class keys the Pact tables are keyed on.  These are the bands
#: :mod:`liminal_gate.pact_draw_catalog` derives from the recovered ``rarity``
#: field, not free-form names, so a document naming anything else is refused
#: rather than silently ignored.
DUPLICATE_CLASSES = ("z", "ss_s", "a_and_below")
TRUTH_CLASSES = ("z", "ss", "s", "a_and_below")

#: The Rare Companion pool's own classes, which are the displayed ones rather
#: than the Pact's bands: the record gives this pool a per-class rate for each.
RARE_CLASSES = ("z", "ss", "s", "a", "b")
NORMAL_CLASSES = ("a", "b", "c", "d")

#: Hunting has three tiers and Metal Zone seven zones. Both counts are the
#: client's, so a document restating either must restate all of it.
HUNTING_TIERS = 3
METAL_ZONES = 7

#: Class shares are parts per million of one pull and must total exactly this,
#: whether they are the Pact of Truth's or the Rare Companion pool's.
TRUTH_SHARE_TOTAL_PPM = 1_000_000


@dataclass(frozen=True)
class PactTuning:
    """Rates and costs for the bundled Fellowship/Truth Pact policy.

    ``truth_class_share_ppm`` and ``duplicate_gains`` are local policy from the
    community record of the retired service; the client holds no rate table to
    contradict them.  ``coin_cost`` and ``energy_cost`` are recovered, and the
    Energy cost is also sent to the client as ``RareSlotEnergy``, so changing it
    changes the price the player is shown as well as the price charged.
    """

    coin_cost: int
    energy_cost: int
    fate_duplicate_luck: int
    #: The "+" Pact frequency, as a percent of pulls.  The one number in the
    #: bundle no source states -- both records say only "sometimes".
    plus_chance_percent: int
    #: Published: 1 to 5 additional levels, inclusive.
    plus_levels: tuple[int, int]
    #: Published: 0.5 to 3.0, in the client's tenths of one percent.
    plus_tenths: tuple[int, int]
    #: ``class -> ppm share of one Pact of Truth pull``.
    truth_class_share_ppm: dict[str, int]
    #: ``class -> (levels, skill-boost tenths)`` a duplicate grants.
    duplicate_gains: dict[str, tuple[int, int]]


@dataclass(frozen=True)
class GateTuning:
    """Whether the two recovered party limits are asserted.

    Neither can come from the client: it owns ``StartQuestErrorCode.ClassLimit``
    and ``SpeciesLimit`` but its only local start gate walks no party, so both
    were always the server's to assert or decline.
    """

    #: Dragon Road and Machine Road admitting only Dragons and Machines.
    species_limits: bool = True
    #: Captive Golem's four sections admitting only their declared class band.
    class_bands: bool = True


@dataclass(frozen=True)
class ExpTuning:
    """How much battle EXP a clear credits, as a percent of the client's own.

    The client computes battle EXP from its own tables and reports the roster it
    derived; this server validates that roster rather than authoring it.  A
    multiplier therefore cannot change what the client *awards* -- it credits an
    additional share on top, on the server's authoritative roster, which the
    client reads back on its next roster fetch.

    Raising it needs a level curve to turn the extra experience back into a
    level, and the only source of one is an operator's own clear-state catalog.
    A launch asking for a multiplier without that catalog is refused rather than
    quietly serving 100.
    """

    multiplier_percent: int = 100


@dataclass(frozen=True)
class CompanionTuning:
    """Selection odds for the two Companion policies that had to choose them.

    ``rare_class_share_ppm`` is the same evidence class as the Pact of Truth
    shares: the rates the service displayed in-game from 2018-02-28, as the
    community record transcribes them, with no APK table to cross-validate.
    Weighting matters more here than it looks, because the pool is lopsided the
    opposite way from the rates -- B is its commonest class by share but only
    its second-largest by count, so a uniform draw inverts the two commonest
    outcomes.

    ``normal_class_share_ppm`` has no record behind it at all; the rate
    announcement and the Companions of Truth page cover the Rare pool only.
    It is a chosen policy, and the thing it is chosen to satisfy is a property
    of the two pools rather than a claim about retired odds: A and B are the
    same Companions in both, so the Coin pool must not be a better source of
    them than the Energy pool. Uniform selection failed that -- it put a given
    A at 0.690% on Coins against 0.536% on Energy -- which is why this table
    exists. See :mod:`liminal_gate.companion_draw_catalog` for the derivation.

    ``strengthen_bonus_weights`` are weaker still: no production odds for the
    random EXP bonus survive and the client's own calculation does not contain
    them, so the bundled weights are a named local policy that keeps all three
    documented outcomes reachable while leaving no bonus the common result.
    """

    #: ``class -> ppm share of one Rare Companion pull``.
    rare_class_share_ppm: dict[str, int]
    #: ``class -> ppm share of one Normal Companion pull``.
    normal_class_share_ppm: dict[str, int]
    #: ``(bonus percent, weight)`` pairs for the strengthen EXP bonus.
    strengthen_bonus_weights: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class HuntingTuning:
    """Availability and the one ceiling Hunting could not recover.

    Both are preservation policy and say so in their own code. The retired
    rotations were never captured, so each tier and Metal zone simply becomes
    permanent once the story has passed the chapter recorded here -- a schedule
    this project chose, not one it found. Puppet Show's real-time board refills
    without any cumulative spawn counter, so no exact finite cap exists to
    recover and its aggregate is conservative anti-inflation policy.

    Stage identities, entry stamina, and every other item ceiling stay
    recovered and are not reachable from here.
    """

    #: The chapter each Hunting tier becomes permanently available after.
    tier_unlock_chapters: tuple[int, ...]
    #: The same, per Metal Zone.
    metal_unlock_chapters: tuple[int, ...]
    #: Puppet Show's per-clear item aggregate, and its per-item ceiling with it.
    puppet_show_item_aggregate: int


@dataclass(frozen=True)
class ClientTuning:
    """The one knob here that is not a server policy at all.

    Everything else in this document is something the server *sends*. This is
    applied by patching the operator's own APK at build time, because the value
    lives nowhere else: `BattleManager.DraggableTime` is a private static float
    set once in the class constructor, with no config key, no master-data entry
    and no field the server could answer with. Nothing at runtime can reach it.

    It is here anyway because an operator tuning their installation should find
    every knob in one place. What differs is the lifecycle: a change takes
    effect on the next *rebuild*, not the next restart, and a server already
    running is unaffected by it.

    The value is limited to what a single instruction can carry, on both ABIs
    the package ships. See `liminal_gate.legacy_client_apk_plan`.
    """

    #: Seconds a player may drag a unit before the turn resolves. Stock is 4.0.
    drag_time_seconds: float = 4.0


@dataclass(frozen=True)
class Tuning:
    pact: PactTuning
    companion: CompanionTuning
    hunting: HuntingTuning
    gates: GateTuning = GateTuning()
    exp: ExpTuning = ExpTuning()
    client: ClientTuning = ClientTuning()


#: The bundled defaults.  Editing these is the build-time path, and every value
#: is the one this project shipped before the document existed, so a server
#: launched with no ``--tuning`` behaves exactly as it did.
DEFAULT_TUNING = Tuning(
    pact=PactTuning(
        coin_cost=3000,
        energy_cost=5,
        fate_duplicate_luck=50,
        plus_chance_percent=22,
        plus_levels=(1, 5),
        plus_tenths=(5, 30),
        truth_class_share_ppm={"z": 40_000, "ss": 100_000, "s": 150_000, "a_and_below": 710_000},
        duplicate_gains={"z": (6, 120), "ss_s": (5, 100), "a_and_below": (1, 50)},
    ),
    companion=CompanionTuning(
        rare_class_share_ppm={"z": 30_000, "ss": 80_000, "s": 100_000, "a": 300_000, "b": 490_000},
        normal_class_share_ppm={"a": 80_000, "b": 120_000, "c": 300_000, "d": 500_000},
        strengthen_bonus_weights=((0, 85), (25, 8), (50, 5), (100, 2)),
    ),
    hunting=HuntingTuning(
        tier_unlock_chapters=(3, 9, 18),
        metal_unlock_chapters=(3, 8, 12, 17, 21, 26, 30),
        puppet_show_item_aggregate=74,
    ),
)

_SECTIONS = {"pact", "companion", "hunting", "gates", "exp", "client"}
_REQUIRED = {"schema_version", "provenance"}


def load_tuning(path: Path) -> Tuning:
    """Load a strict operator tuning document, defaulting anything it omits.

    Unlike the catalogs, a partial document is meaningful here: an operator who
    only wants to turn off a species lock should not have to restate every Pact
    rate to do it.  Each section and each key inside it is optional, and what is
    absent keeps its bundled default.  What is *present* is validated exactly --
    an unknown key is refused rather than ignored, because a misspelled rate
    that silently keeps its default is the failure this project's strict parsing
    policy exists to prevent.
    """
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise TuningError("could not read tuning TOML") from error
    if not isinstance(document, dict) or not _REQUIRED <= set(document) or set(document) - (_REQUIRED | _SECTIONS):
        raise TuningError("tuning document has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise TuningError("tuning document requires schema version 1 and user-supplied provenance")
    return Tuning(
        pact=_pact(document.get("pact", {})),
        companion=_companion(document.get("companion", {})),
        hunting=_hunting(document.get("hunting", {})),
        gates=_gates(document.get("gates", {})),
        exp=_exp(document.get("exp", {})),
        client=_client(document.get("client", {})),
    )


def _section(value: object, permitted: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) - permitted:
        raise TuningError(f"[{name}] has an invalid schema")
    return value


def _positive(value: object, name: str) -> int:
    if type(value) is not int or value <= 0:
        raise TuningError(f"{name} must be a positive integer")
    return value


def _percent(value: object, name: str, ceiling: int) -> int:
    if type(value) is not int or not 0 <= value <= ceiling:
        raise TuningError(f"{name} must be an integer from 0 through {ceiling}")
    return value


def _range(value: object, name: str) -> tuple[int, int]:
    if (
        not isinstance(value, list)
        or len(value) != 2
        or any(type(item) is not int for item in value)
        or value[0] < 1
        or value[1] < value[0]
    ):
        raise TuningError(f"{name} must be two ascending positive integers")
    return (value[0], value[1])


def _pact(value: object) -> PactTuning:
    keys = {
        "coin_cost", "energy_cost", "fate_duplicate_luck", "plus_chance_percent",
        "plus_levels", "plus_tenths", "truth_class_share_ppm", "duplicate_gains",
    }
    document = _section(value, keys, "pact")
    default = DEFAULT_TUNING.pact
    fields: dict[str, object] = {}
    for name in ("coin_cost", "energy_cost", "fate_duplicate_luck"):
        if name in document:
            fields[name] = _positive(document[name], name)
    if "plus_chance_percent" in document:
        # Zero is meaningful and supported: it turns the "+" Pact off, which is
        # the only setting here whose behaviour predates the feature.
        fields["plus_chance_percent"] = _percent(document["plus_chance_percent"], "plus_chance_percent", 100)
    for name in ("plus_levels", "plus_tenths"):
        if name in document:
            fields[name] = _range(document[name], name)
    if "truth_class_share_ppm" in document:
        fields["truth_class_share_ppm"] = _shares(document["truth_class_share_ppm"])
    if "duplicate_gains" in document:
        fields["duplicate_gains"] = _duplicate_gains(document["duplicate_gains"])
    return replace(default, **fields)


def _shares(value: object, classes: tuple[str, ...] = TRUTH_CLASSES, name: str = "truth_class_share_ppm") -> dict[str, int]:
    """A complete class table that adds up.

    Partial is refused for the reason the unlock ladders give, and the total is
    checked because a table that does not add up is a transcription error
    rather than a preference -- the shares are read as parts of one pull.
    """
    if not isinstance(value, dict) or set(value) != set(classes):
        listed = ", ".join(classes)
        raise TuningError(f"{name} must name exactly these classes: {listed}")
    shares = {entry: _positive(value[entry], f"{name}.{entry}") for entry in classes}
    if sum(shares.values()) != TRUTH_SHARE_TOTAL_PPM:
        raise TuningError(f"{name} must total exactly {TRUTH_SHARE_TOTAL_PPM} parts per million")
    return shares


def _duplicate_gains(value: object) -> dict[str, tuple[int, int]]:
    if not isinstance(value, dict) or set(value) != set(DUPLICATE_CLASSES):
        listed = ", ".join(DUPLICATE_CLASSES)
        raise TuningError(f"duplicate_gains must name exactly these classes: {listed}")
    gains: dict[str, tuple[int, int]] = {}
    for name in DUPLICATE_CLASSES:
        entry = value[name]
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or any(type(item) is not int or item < 1 for item in entry)
        ):
            raise TuningError(f"duplicate_gains.{name} must be a positive level gain and skill-boost gain")
        gains[name] = (entry[0], entry[1])
    return gains


def _companion(value: object) -> CompanionTuning:
    document = _section(value, {"rare_class_share_ppm", "normal_class_share_ppm", "strengthen_bonus_weights"}, "companion")
    fields: dict[str, object] = {}
    if "rare_class_share_ppm" in document:
        fields["rare_class_share_ppm"] = _shares(
            document["rare_class_share_ppm"], RARE_CLASSES, "rare_class_share_ppm",
        )
    if "normal_class_share_ppm" in document:
        fields["normal_class_share_ppm"] = _shares(
            document["normal_class_share_ppm"], NORMAL_CLASSES, "normal_class_share_ppm",
        )
    if "strengthen_bonus_weights" in document:
        fields["strengthen_bonus_weights"] = _bonus_weights(document["strengthen_bonus_weights"])
    return replace(DEFAULT_TUNING.companion, **fields)


def _bonus_weights(value: object) -> tuple[tuple[int, int], ...]:
    """Validate ``(bonus percent, weight)`` pairs for the strengthen bonus.

    A zero-weight outcome is refused rather than accepted as a way of removing
    one: drop the pair instead, so the table reads as what it selects from.
    """
    if not isinstance(value, list) or not value:
        raise TuningError("strengthen_bonus_weights must be a nonempty array of [percent, weight] pairs")
    weights: list[tuple[int, int]] = []
    for entry in value:
        if (
            not isinstance(entry, list)
            or len(entry) != 2
            or any(type(item) is not int for item in entry)
            or entry[0] < 0
            or entry[1] < 1
        ):
            raise TuningError(
                "each strengthen_bonus_weights entry must be a nonnegative percent and a positive "
                "weight; to remove an outcome delete its pair rather than weighting it 0, so the "
                "table reads as what it selects from"
            )
        weights.append((entry[0], entry[1]))
    if len({percent for percent, _ in weights}) != len(weights):
        raise TuningError("strengthen_bonus_weights must not repeat a bonus percent")
    return tuple(weights)


def _hunting(value: object) -> HuntingTuning:
    keys = {"tier_unlock_chapters", "metal_unlock_chapters", "puppet_show_item_aggregate"}
    document = _section(value, keys, "hunting")
    fields: dict[str, object] = {}
    for name, count in (("tier_unlock_chapters", HUNTING_TIERS), ("metal_unlock_chapters", METAL_ZONES)):
        if name in document:
            fields[name] = _unlock_chapters(document[name], name, count)
    if "puppet_show_item_aggregate" in document:
        fields["puppet_show_item_aggregate"] = _positive(
            document["puppet_show_item_aggregate"], "puppet_show_item_aggregate",
        )
    return replace(DEFAULT_TUNING.hunting, **fields)


def _unlock_chapters(value: object, name: str, count: int) -> tuple[int, ...]:
    """A full ladder, ascending.

    Partial is refused because the tiers are one schedule rather than several
    independent numbers: restating the third without the first would leave a
    ladder whose rungs an operator never looked at between two they chose.
    Equal neighbours are allowed -- opening two tiers at once is a coherent
    thing to want -- but a later tier opening earlier than an earlier one is
    not, since the client offers them in this order.
    """
    if (
        not isinstance(value, list)
        or len(value) != count
        or any(type(item) is not int or item < 0 for item in value)
    ):
        raise TuningError(f"{name} must be {count} nonnegative integers")
    if any(later < earlier for earlier, later in zip(value, value[1:])):
        raise TuningError(f"{name} must not decrease")
    return tuple(value)


def _gates(value: object) -> GateTuning:
    document = _section(value, {"species_limits", "class_bands"}, "gates")
    fields: dict[str, object] = {}
    for name in ("species_limits", "class_bands"):
        if name in document:
            if type(document[name]) is not bool:
                raise TuningError(f"{name} must be a boolean")
            fields[name] = document[name]
    return replace(GateTuning(), **fields)


def _exp(value: object) -> ExpTuning:
    document = _section(value, {"multiplier_percent"}, "exp")
    if "multiplier_percent" not in document:
        return ExpTuning()
    # The ceiling is a guard against a typo turning a clear into an overflowing
    # roster, not a judgement about how generous an archive should be.
    multiplier = document["multiplier_percent"]
    if type(multiplier) is not int or not 100 <= multiplier <= 10_000:
        raise TuningError("multiplier_percent must be an integer from 100 through 10000")
    return ExpTuning(multiplier_percent=multiplier)


#: The drag-time patch rewrites one instruction per ABI, and each carries the
#: float's high 16 bits only -- an AArch64 `MOVZ` with a 16-bit shift, and an
#: ARM `MOVT` beside a `MOVW #0`. A value whose low 16 bits are not zero would
#: need a second instruction and a longer patch, so it is refused rather than
#: silently rounded. Every whole and half second qualifies, and so does every
#: 1/32 in the range this accepts.
def _encodable_drag_time(seconds: float) -> bool:
    return struct.unpack("<I", struct.pack("<f", seconds))[0] & 0xFFFF == 0


def _client(value: object) -> ClientTuning:
    document = _section(value, {"drag_time_seconds"}, "client")
    if "drag_time_seconds" not in document:
        return ClientTuning()
    seconds = document["drag_time_seconds"]
    if type(seconds) not in (int, float) or type(seconds) is bool or not 1.0 <= float(seconds) <= 30.0:
        raise TuningError("drag_time_seconds must be a number from 1.0 through 30.0")
    if not _encodable_drag_time(float(seconds)):
        raise TuningError(
            f"drag_time_seconds {seconds} cannot be patched in one instruction; use a value whose "
            "float32 low half is zero -- every whole and half second qualifies, as does every 0.25"
        )
    return ClientTuning(drag_time_seconds=float(seconds))
