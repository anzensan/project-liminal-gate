"""User-local ordinary Pact pool, rates, and duplicate policy."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import tomllib


class PactDrawCatalogError(ValueError):
    """A user-local ordinary-Pact catalog is invalid."""


@dataclass(frozen=True)
class PactDraw:
    character_id: int
    weight: int
    duplicate_level_added: int
    duplicate_skill_boost: int


@dataclass(frozen=True)
class PactDrawCatalog:
    coin_cost: int
    new_level: int
    max_level: int
    max_skill_boost: int
    draws: tuple[PactDraw, ...]

    def draws_for_kind(self, kind: int) -> tuple[PactDraw, ...]:
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
    fellowship_draws: tuple[PactDraw, ...]
    truth_draws: tuple[PactDraw, ...]

    def draws_for_kind(self, kind: int) -> tuple[PactDraw, ...]:
        return self.fellowship_draws if kind == 0 else self.truth_draws if kind == 1 else ()

    def cost_for_kind(self, kind: int) -> tuple[str, int] | None:
        return ("coins", self.coin_cost) if kind == 0 else ("energy", self.energy_cost) if kind == 1 else None


_FELLOWSHIP_IDS = (
    9, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 79, 80, 81, 84, 85, 86, 88, 91, 94, 98, 99, 100, 107, 110, 114, 115, 122, 123, 124, 128, 143, 145, 146, 149, 150, 163, 164, 165, 166, 175, 176, 188, 199, 200, 201, 202, 203, 204, 205, 210, 211, 212, 215, 216, 220, 221, 228, 237, 238, 239, 264, 285, 286, 287, 292, 299, 307, 308, 312, 313, 314, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 399, 402, 403, 620, 648, 678, 679, 703, 711, 938, 999, 1007, 1224, 1225, 1226, 1227,
)
_TRUTH_IDS = (
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 74, 81, 399, 402, 403, 540, 546, 547, 557, 564, 582, 588, 620, 828, 829, 830, 831, 832, 833, 834, 835, 836, 894, 915, 917, 971, 1005, 1006, 1019, 1020, 1021, 1022, 1023, 1024, 1084, 1096, 1097, 1098, 1099, 1100, 1103, 1156, 1157, 1159, 1200, 1201, 1202, 1243, 1244, 1245, 1257, 1258, 1259, 1260, 1261, 1262, 1263, 1264, 1265, 1266,
)


def build_bundled_pact_policy() -> BundledPactPolicy:
    """Return the guided-path local Fellowship/Truth Pact policy."""
    draw = lambda character_id: PactDraw(character_id, 1, 1, 10)
    return BundledPactPolicy(
        coin_cost=3000,
        energy_cost=5,
        new_level=10,
        max_level=90,
        max_skill_boost=1000,
        fellowship_draws=tuple(draw(character_id) for character_id in _FELLOWSHIP_IDS),
        truth_draws=tuple(draw(character_id) for character_id in _TRUTH_IDS),
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
