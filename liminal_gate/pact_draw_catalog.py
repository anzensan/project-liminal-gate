"""User-local ordinary Pact pool, rates, and duplicate policy."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


class PactDrawCatalogError(ValueError):
    """A user-local ordinary-Pact catalog is invalid."""


# The final client's ``rarity`` field carries the seven displayed classes as
# values 2--8: D, C, B, A, S, SS, Z.  The banding below is *not* read off a
# class-name string, which the master data does not store; it is corroborated
# by recovered client behaviour.  ``Character.get_luckMax`` derives its cap
# from the same field, and across the user's own catalog the non-Lambda caps
# fall exactly on these three groups: 700 for rarities 2--5, 800 for 6--7, and
# 1000 for 8.  Two independent client-side rules therefore split the classes
# in the same places these gains do.
_RARITY_Z = 8
_RARITY_SS_S = (6, 7)

# Duplicate gains by class.  These are **local preservation policy from a
# secondary source**, not recovered service values, and they cannot be made
# recovered ones: the final client never computed them.  It renders whatever
# the server sent, through
# ``UIPactResult.PrepareShow(int _chrId, JsonData _addedLevels,
# int _addedSkillBoost, int _addedLuck)``, so no table exists inside the APK
# to cross-validate against.  The community record for the retired service is
# consistent across both Pact pages, and it is a better archive default than
# the flat +1 level / +1.0% this bundle previously applied to every class.
# Skill boost is the client's tenths-of-one-percent wire unit, so 120 is 12.0%.
_DUPLICATE_GAINS_BY_CLASS = {
    "z": (6, 120),
    "ss_s": (5, 100),
    "a_and_below": (1, 50),
}

# Pact of Truth class shares, in parts per million of one pull.  Same evidence
# status as the duplicate gains above: community record, no APK table, since
# the retired server owned selection entirely.  The client's only rate-related
# symbol is ``RareSlotEnergy``, the cost this bundle already sends.  The
# record's provenance is now dated: Mistwalker began displaying recruitment
# rates in-game on 2018-02-28 (archived official news, "Display of
# Character/Companion recruitment rates", 2018-02-23; Wayback capture
# 20180228133231 of terra-battle.com/en/news/2018/02/post-156.html), and the
# community wiki's Pact of Truth page transcribes the displayed split as
# exactly these 4/10/15/71 shares.  Two things the display had that this table
# does not: per-character rates, and a pool that shrank as characters hit 100%
# Skill Boost and left it, redistributing their share.  Within a class the
# share is split evenly, which is what the source describes for A/B and the
# only defensible reading for the rest.  Fellowship keeps uniform selection
# because no comparable record of its rates was found -- the only surviving
# empirical data, a 2015 forum sample of ~1,200 pulls (Wayback capture
# 20150424040406 of terrabattleforum.com thread 5198), predates the final
# pool, though its uniform spread across the six adventurers supports uniform
# selection within a class.  Inventing a class table from a 2015 sample would
# be worse than an honest uniform one.
_TRUTH_CLASS_SHARE_PPM = {
    "z": 40_000,
    "ss": 100_000,
    "s": 150_000,
    "a_and_below": 710_000,
}
_WEIGHT_SCALE = 1_000_000

# The "+" Pact.  A pull sometimes arrives decorated, granting the recruit extra
# levels and extra Skill Boost -- or extra Luck, on a Fate-type pull, which
# grants Luck where the others grant Skill Boost.  The client renders it from
# fields the server fills: `levelAdded2`, `boostUp2` and `luckup2` on the pull
# result, read by `AppServerUtil.<DoSlot>c__IteratorB`.  Version 2.6.0 added it.
#
# The two gain ranges are the published ones, documented identically in the
# English and Japanese record: 1 to 5 levels, and 0.5% to 3.0% Skill Boost, in
# the client's tenths.  The Fate-side Luck gain is documented on the same scale.
#
# **The frequency is local policy.**  It is the one number no source states --
# both records say only "sometimes" -- because the retired service owned the
# roll and the client holds no table for it.  Twenty-two percent is adopted
# from operator-side observation and sits inside the only field estimate on
# record, a tester's "2-3 times on a 10-pull".  It is a chosen number, on the
# same footing as the Companion-strengthen EXP-bonus weights: honest to
# change, and named here rather than buried in the draw.
#
# The *shape* of the roll inside those ranges is a second, smaller choice.  No
# source describes it and the client cannot: it renders the numbers the server
# sends and nothing in that path bounds them.  Uniform is the assumption with
# the fewest parts, and it is the only other thing here that was chosen rather
# than read.
PLUS_PACT_CHANCE_PERCENT = 22
#: Published: 1 to 5 additional levels.
PLUS_PACT_LEVELS = (1, 5)
#: Published: 0.5 to 3.0, in the client's tenths -- Skill Boost on a Truth or
#: Fellowship pull, Luck on a Fate-type one.
PLUS_PACT_TENTHS = (5, 30)


def _duplicate_class(rarity: int) -> str:
    if rarity == _RARITY_Z:
        return "z"
    return "ss_s" if rarity in _RARITY_SS_S else "a_and_below"


def _truth_rate_class(rarity: int) -> str:
    if rarity == _RARITY_Z:
        return "z"
    if rarity == 7:
        return "ss"
    return "s" if rarity == 6 else "a_and_below"


def load_character_rarity(path: Path) -> dict[int, int]:
    """Return ``{character_id: rarity}`` from the user's own character catalog.

    The catalog is derived from the operator's matching APK by
    :mod:`liminal_gate.character_catalog_importer`, so this reads recovered
    master data rather than anything bundled here.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PactDrawCatalogError("could not read the local character catalog JSON") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1 or document.get("provenance") != "user-derived" or not isinstance(document.get("characters"), list):
        raise PactDrawCatalogError("local character catalog has an invalid schema or provenance")
    rarities: dict[int, int] = {}
    for record in document["characters"]:
        if not isinstance(record, dict) or type(record.get("character_id")) is not int or type(record.get("rarity")) is not int:
            raise PactDrawCatalogError("each character record requires integer character_id and rarity")
        if record["character_id"] <= 0 or not 2 <= record["rarity"] <= 8:
            raise PactDrawCatalogError("character IDs must be positive and rarity must be 2 through 8")
        rarities[record["character_id"]] = record["rarity"]
    if not rarities:
        raise PactDrawCatalogError("local character catalog contains no characters")
    return rarities


@dataclass(frozen=True)
class PactDraw:
    character_id: int
    weight: int
    duplicate_level_added: int
    duplicate_skill_boost: int
    # The earliest chapter that can draw this member.  Chapter 1 means "from
    # the first pull", which is the only claim a source without an
    # availability table supports, so it is also the default.
    required_chapter: int = 1


@dataclass(frozen=True)
class PactDrawCatalog:
    coin_cost: int
    new_level: int
    max_level: int
    max_skill_boost: int
    draws: tuple[PactDraw, ...]

    def draws_for_kind(self, kind: int, chapter: int | None = None) -> tuple[PactDraw, ...]:
        # A user-supplied schema version 1 catalog carries no availability
        # data, so the operator's pool is served whole.  Gating it on a curve
        # this bundle invented would be the same overreach the Fate/Luck
        # refusal in the draw route already avoids.
        return self.draws if kind == 0 else ()

    def cost_for_kind(self, kind: int) -> tuple[str, int] | None:
        return ("coins", self.coin_cost) if kind == 0 else None


@dataclass(frozen=True)
class BundledPactPolicy:
    """Local normal-Pact policy used by the guided tester path.

    The client contract distinguishes Fellowship (coin) and Truth (Energy)
    pulls. Pool membership is bounded; uniform selection and duplicate gains
    are local policy rather than a claim about retired-service odds.
    """

    coin_cost: int
    energy_cost: int
    new_level: int
    max_level: int
    max_skill_boost: int
    max_luck: int
    fate_duplicate_luck: int
    fellowship_draws: tuple[PactDraw, ...]
    truth_draws: tuple[PactDraw, ...]

    def draws_for_kind(self, kind: int, chapter: int | None = None) -> tuple[PactDraw, ...]:
        if kind != 0:
            # No comparable availability record was found for Truth, so its
            # pool stays whole rather than borrowing Fellowship's curve.
            return self.truth_draws if kind == 1 else ()
        if chapter is None:
            return self.fellowship_draws
        return tuple(draw for draw in self.fellowship_draws if draw.required_chapter <= chapter)

    def cost_for_kind(self, kind: int) -> tuple[str, int] | None:
        return ("coins", self.coin_cost) if kind == 0 else ("energy", self.energy_cost) if kind == 1 else None


# Fellowship membership keyed by the chapter that unlocks it.  The community
# wiki's "Availability by Chapter" table describes the pool as cumulative:
# completing a chapter adds that chapter's characters and keeps every earlier
# one, so a member's key here is the *earliest* chapter that can draw it.  This
# is the same evidence class as the rates below -- community record for a
# retired service, with no APK table to cross-validate, because the server
# owned pool selection entirely.  What can be cross-validated is the roster:
# every ID resolves through the operator's decoded name table, and all 103
# agree with the recovered ``rarity`` field under the class banding documented
# at the top of this module.  That two-way agreement is what caught the one
# transcription error this table previously carried, an ID 122 that names no
# character in the final client, in place of 126 (Megacell, chapter 15).
_FELLOWSHIP_UNLOCKS = {
    1: (9, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 79, 80, 81, 84, 85, 88, 91, 98, 107, 188, 199, 200, 201, 202, 203, 204, 205, 210, 211, 212, 220, 228, 308, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 399, 402, 403, 620, 999, 1007),
    4: (175, 176),
    7: (94, 99, 221),
    9: (86,),
    10: (100, 110, 114, 115, 215, 216),
    13: (123, 124, 128),
    15: (126,),
    16: (312, 313),
    20: (143, 145, 149, 150, 285, 286, 287, 307, 314),
    21: (146, 237, 299),
    22: (239,),
    23: (238,),
    25: (292, 337),
    28: (163, 164, 165, 166, 264),
    31: (648,),
    32: (678, 679),
    33: (703,),
    34: (711,),
    35: (1224,),
    36: (1226,),
    37: (938,),
    38: (1225, 1227),
}
_FELLOWSHIP_CHAPTER = {
    character_id: chapter
    for chapter, character_ids in _FELLOWSHIP_UNLOCKS.items()
    for character_id in character_ids
}
_FELLOWSHIP_IDS = tuple(sorted(_FELLOWSHIP_CHAPTER))
_TRUTH_IDS = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 74, 81, 399, 402, 403, 540, 546, 547, 557, 564, 582, 588, 620, 828, 829, 830, 831, 832, 833, 834, 835, 836, 894, 915, 917, 971, 1005, 1006, 1019, 1020, 1021, 1022, 1023, 1024, 1084, 1096, 1097, 1098, 1099, 1100, 1103, 1156, 1157, 1159, 1200, 1201, 1202, 1243, 1244, 1245, 1257, 1258, 1259, 1260, 1261, 1262, 1263, 1264, 1265, 1266,
)


def _class_weights(character_ids: tuple[int, ...], rarities: Mapping[int, int]) -> dict[int, int]:
    """Split each class's share evenly across its own members.

    A pool member missing from the local catalog cannot be classified, so it
    keeps the mean weight of the pool rather than being dropped or silently
    treated as the commonest class.
    """
    members: dict[str, list[int]] = {}
    for character_id in character_ids:
        rarity = rarities.get(character_id)
        if rarity is not None:
            members.setdefault(_truth_rate_class(rarity), []).append(character_id)
    weights: dict[int, int] = {}
    for name, ids in members.items():
        share = _TRUTH_CLASS_SHARE_PPM[name] * _WEIGHT_SCALE // len(ids)
        for character_id in ids:
            weights[character_id] = max(share, 1)
    unclassified = [character_id for character_id in character_ids if character_id not in weights]
    if unclassified:
        mean = sum(weights.values()) // len(weights) if weights else 1
        for character_id in unclassified:
            weights[character_id] = max(mean, 1)
    return weights


def validate_bundled_pools(character_rarity: Mapping[int, int]) -> None:
    """Fail visibly when a bundled pool names a character the APK does not.

    Both pools are fixed rosters of the final client, so every member must
    resolve in master data derived from the operator's own matching APK.  One
    that does not means either this bundle's transcription is wrong or the
    catalog does not match the client -- and drawing it would mint a
    ``chrdata`` row for a character the client has no data for.

    This is deliberately separate from :func:`build_bundled_pact_policy`,
    which stays tolerant of a partial mapping: weighting and duplicate gains
    degrade to a documented default for an unclassifiable member, whereas an
    unresolvable member is not a gap in policy but an inconsistency between
    two documents that describe the same client.
    """
    unknown = tuple(
        character_id
        for character_id in _FELLOWSHIP_IDS + _TRUTH_IDS
        if character_id not in character_rarity
    )
    if unknown:
        listed = ", ".join(str(character_id) for character_id in unknown)
        raise PactDrawCatalogError(f"bundled Pact pools name characters absent from the local character catalog: {listed}")


def build_bundled_pact_policy(character_rarity: Mapping[int, int] | None = None) -> BundledPactPolicy:
    """Return the guided-path local Fellowship/Truth Pact policy.

    Without ``character_rarity`` every entry keeps a uniform weight and the
    same flat duplicate gain, which is what this bundle can justify with no
    master data in hand.  Given the operator's own catalog, duplicate gains
    follow the recovered rarity bands and Truth selection follows the
    documented class shares; both are labeled local policy above.
    """
    if character_rarity is None:
        fellowship_draws = tuple(
            PactDraw(character_id, 1, 1, 10, _FELLOWSHIP_CHAPTER[character_id])
            for character_id in _FELLOWSHIP_IDS
        )
        truth_draws = tuple(PactDraw(character_id, 1, 1, 10) for character_id in _TRUTH_IDS)
        return _pact_policy(fellowship_draws, truth_draws)

    def duplicate(character_id: int) -> tuple[int, int]:
        rarity = character_rarity.get(character_id)
        # An unclassifiable member keeps the conservative lowest-class gain.
        return _DUPLICATE_GAINS_BY_CLASS["a_and_below" if rarity is None else _duplicate_class(rarity)]

    truth_weights = _class_weights(_TRUTH_IDS, character_rarity)
    fellowship_draws = tuple(
        PactDraw(character_id, 1, *duplicate(character_id), required_chapter=_FELLOWSHIP_CHAPTER[character_id])
        for character_id in _FELLOWSHIP_IDS
    )
    truth_draws = tuple(PactDraw(character_id, truth_weights[character_id], *duplicate(character_id)) for character_id in _TRUTH_IDS)
    return _pact_policy(fellowship_draws, truth_draws)


def _pact_policy(fellowship_draws: tuple[PactDraw, ...], truth_draws: tuple[PactDraw, ...]) -> BundledPactPolicy:
    return BundledPactPolicy(
        coin_cost=3000,
        # The service charged 5 Energy for a single Truth pull.  An earlier
        # local observation of 3 came from the client's own embedded fallback:
        # the server had not yet sent `RareSlotEnergy`, so the client displayed
        # a default rather than the real cost.  It is sent now, from this value,
        # so the displayed cost and the charged cost are the same number.
        energy_cost=5,
        new_level=10,
        max_level=90,
        max_skill_boost=1000,
        # Luck uses the client's tenths-of-one-percent wire unit.  The
        # community record documents the retired caps as 100.0 for Λ and Z,
        # 80.0 for SS/S, and 70.0 for A and below -- the same three-way split
        # the recovered ``Character.get_luckMax`` banding enforces on the
        # client itself.  The server-side policy keeps the absolute 100.0
        # ceiling because the client's own recovered cap already clamps each
        # character to its band; the record also ties the +5.0 duplicate
        # increment specifically to the Pact of Fate.
        max_luck=1000,
        fate_duplicate_luck=50,
        fellowship_draws=fellowship_draws,
        truth_draws=truth_draws,
    )


def load_pact_draw_catalog(path: Path) -> PactDrawCatalog:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise PactDrawCatalogError("could not read ordinary-Pact catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "coin_cost", "new_level", "max_level", "max_skill_boost", "draws"}
    if not isinstance(document, dict) or set(document) != required:
        raise PactDrawCatalogError("ordinary-Pact catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise PactDrawCatalogError("ordinary-Pact catalog requires schema version 1 and user-supplied provenance")
    numeric = ("coin_cost", "new_level", "max_level", "max_skill_boost")
    if any(type(document[name]) is not int for name in numeric) or document["coin_cost"] <= 0 or document["new_level"] < 1 or document["max_level"] < document["new_level"] or document["max_skill_boost"] < 1:
        raise PactDrawCatalogError("ordinary-Pact numeric values are outside range")
    if not isinstance(document["draws"], list) or not document["draws"]:
        raise PactDrawCatalogError("draws must be a nonempty array")
    draws = tuple(_draw(value) for value in document["draws"])
    ids = [draw.character_id for draw in draws]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise PactDrawCatalogError("draws must be ordered and unique by character_id")
    return PactDrawCatalog(*(document[name] for name in numeric), draws)


def _draw(value: object) -> PactDraw:
    fields = {"character_id", "weight", "duplicate_level_added", "duplicate_skill_boost"}
    if not isinstance(value, dict) or set(value) != fields or any(type(value[name]) is not int for name in fields) or any(value[name] <= 0 for name in fields):
        raise PactDrawCatalogError("each draw requires positive character_id, weight, and duplicate gains")
    return PactDraw(value["character_id"], value["weight"], value["duplicate_level_added"], value["duplicate_skill_boost"])
