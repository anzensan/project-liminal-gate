"""Request-body parsers for the bootstrap mutation and write routes.

Each parser is a pure ``bytes -> parsed | None`` check of one final-client
form: the exact ordered field tuple, then the value constraints that form
declares, with ``None`` for anything else. The block-local helpers they share
(identity projection, roster and Companion decoding, the equipment coherence
checks) live here with them so the forms cannot drift apart. Everything is
imported back into ``bootstrap_server``; this module must never import the
server, and nothing here may read the clock or draw randomness.
"""

from __future__ import annotations

import copy
import json
import math
from typing import Any
from urllib.parse import parse_qsl, urlencode

from liminal_gate.bootstrap_wire import _drop_trailing_last_update, _json_fields_match, _valid_last_update
from liminal_gate.companion_equipment_catalog import CompanionEquipmentCatalog


# Metal Zone starts carry the ticket the client would spend instead of stamina,
# so their form has two fields the ordinary story start does not.
_TICKET_START_FIELDS = ("stamina", "coins", "itemID", "itemCount", "chapter", "section", "lastUpdate")


def _parse_hunting_start(body: bytes) -> dict[str, int] | None:
    """Parse a Huntland start in either the ordinary or ticket-aware form.

    Kept separate from `_parse_generic_story_start` on purpose: accepting the
    longer form there would let an ordinary story stage be started with entry
    fields no story stage declares.
    """
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) == _TICKET_START_FIELDS:
            values = {name: int(value) for name, value in pairs}
            if any(value < 0 for value in values.values()) or values["chapter"] < 2 or values["section"] < 1:
                return None
            # Which form arrived is itself part of the contract: a stage without
            # a ticket alternative is never entered through this form.
            return values | {"ticket_form": 1}
    except (UnicodeDecodeError, ValueError):
        return None
    ordinary = _parse_generic_story_start(body)
    return None if ordinary is None else ordinary | {"itemID": 0, "itemCount": 0, "ticket_form": 0}


def _identity_chapter(identity: tuple[int, int] | None) -> int | None:
    """The chapter of a parsed identity, used to route a whole chapter's stages."""
    return None if identity is None else identity[0]


def _started_hunting_identity(body: bytes) -> tuple[int, int] | None:
    """The chapter/section a Huntland start names, if it is well formed."""
    values = _parse_hunting_start(body)
    return None if values is None else (values["chapter"], values["section"])


def _profile_clear_matches(body: bytes, transitions: tuple[dict[str, Any], ...]) -> bool:
    try:
        fields = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return False
    values = dict(fields)
    return any(
        tuple(name for name, _ in fields) == tuple(item["field_names"])
        and all(values.get(name) == value for name, value in item["fixed_fields"].items())
        and _json_fields_match(values, item["json_fields"])
        for item in transitions
    )


def _parse_generic_story_start(body: bytes) -> dict[str, int] | None:
    fields = ("stamina", "coins", "chapter", "section", "lastUpdate")
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != fields:
            return None
        values = {name: int(value) for name, value in pairs}
    except (UnicodeDecodeError, ValueError):
        return None
    if any(value < 0 for value in values.values()) or values["chapter"] < 2 or values["section"] < 1:
        return None
    return values


def _parse_generic_story_clear(body: bytes) -> dict[str, Any] | None:
    fields = ("progressCode", "worldMapNo", "valuables", "chrdata", "itemList", "summonList", "battle_result", "itmp0", "itmp1", "lastUpdate")
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != fields:
            return None
        raw = dict(pairs)
        result = {
            "progressCode": int(raw["progressCode"]), "worldMapNo": int(raw["worldMapNo"]),
            "valuables": json.loads(raw["valuables"]), "chrdata": json.loads(raw["chrdata"]),
            "itemList": json.loads(raw["itemList"]), "summonList": json.loads(raw["summonList"]),
            "battle_result": json.loads(raw["battle_result"]), "itmp0": int(raw["itmp0"]),
            "itmp1": int(raw["itmp1"]), "lastUpdate": int(raw["lastUpdate"]),
        }
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if (
        any(
            type(result[name]) is not int or result[name] < 0
            for name in ("progressCode", "worldMapNo", "itmp1", "lastUpdate")
        )
        or type(result["itmp0"]) is not int
        or result["itmp0"] < -1
    ):
        return None
    valuable_fields = {"energyAppStore", "energy", "energyAndApp", "freeEnergy", "energyGooglePlay", "coins"}
    if type(result["valuables"]) is not dict or set(result["valuables"]) != valuable_fields or any(type(value) is not int or value < 0 for value in result["valuables"].values()):
        return None
    if type(result["chrdata"]) is not list or not result["chrdata"] or any(not _valid_generic_character_record(row) for row in result["chrdata"]) or len({row["id"] for row in result["chrdata"]}) != len(result["chrdata"]):
        return None
    if type(result["itemList"]) is not list or any(type(value) is not int or value < 0 for value in result["itemList"]) or type(result["summonList"]) is not list or any(type(value) is not int or value < 0 for value in result["summonList"]):
        return None
    battle = result["battle_result"]
    battle_fields = {"coins", "buddies", "items", "exp", "section", "monsters", "summons", "luckynum", "chapter", "unableluckdrop", "boostup"}
    if not isinstance(battle, dict) or set(battle) - {"counters"} != battle_fields or any(type(battle.get(name)) is not int or battle[name] < 0 for name in ("coins", "exp", "section", "luckynum", "chapter")) or battle["chapter"] < 2 or battle["section"] < 1 or type(battle["unableluckdrop"]) is not bool:
        return None
    if "counters" in battle and type(battle["counters"]) is not str:
        return None
    if any(type(battle[name]) is not list or any(type(value) is not int or value < 0 for value in battle[name]) for name in ("buddies", "monsters", "summons")):
        return None
    if type(battle["items"]) is not dict or any(not isinstance(item_id, str) or not item_id.isdecimal() or int(item_id) <= 0 or type(count) is not int or count < 1 for item_id, count in battle["items"].items()):
        return None
    if type(battle["boostup"]) is not list or len(battle["boostup"]) != 6 or any(type(value) is not int or value < 0 for value in battle["boostup"]):
        return None
    return result


def _parse_story_progression_reveal(body: bytes) -> dict[str, int] | None:
    """Parse the reviewed ordered post-chapter userdata map write."""
    fields = ("progressCode", "worldMapNo", "lastUpdate")
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != fields:
            return None
        values = {name: int(value) for name, value in pairs}
    except (UnicodeDecodeError, ValueError):
        return None
    return values if all(value >= 0 for value in values.values()) else None


def _valid_generic_character_record(row: object) -> bool:
    fields = {"id", "buddy", "date", "jobSlots", "jobLevels", "jobID", "flags", "skillBoost"}
    if not isinstance(row, dict) or set(row) not in (fields, fields | {"luck"}):
        return False
    if any(type(row[name]) is not int or row[name] < 0 for name in ("id", "buddy", "jobID", "flags", "skillBoost")) or ("luck" in row and (type(row["luck"]) is not int or not 0 <= row["luck"] <= 1000)):
        return False
    if type(row["date"]) not in {int, float} or not math.isfinite(row["date"]) or row["date"] < 0:
        return False
    return all(isinstance(row[name], list) and len(row[name]) == 3 and all(type(value) in {int, float} and math.isfinite(value) and value >= 0 and int(value) == value and (name != "jobSlots" or value <= 0xFFFFFFFF) for value in row[name]) for name in ("jobSlots", "jobLevels"))


def _parse_continue(body: bytes) -> int | None:
    """Parse the final-client Continue form, allowing a trailing lastUpdate."""
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    pairs = _drop_trailing_last_update(pairs)
    if tuple(name for name, _ in pairs) != ("cost",):
        return None
    try:
        return int(pairs[0][1])
    except ValueError:
        return None


def _parse_change_uname(body: bytes) -> str | None:
    try:
        pairs = tuple(parse_qsl(body.decode("utf-8"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    pairs = _drop_trailing_last_update(pairs)
    if tuple(name for name, _ in pairs) != ("name",):
        return None
    name = pairs[0][1]
    return name if 1 <= len(name) <= 13 else None


def _parse_refill_stamina(body: bytes) -> int | None:
    try:
        pairs = _drop_trailing_last_update(tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True)))
        return int(pairs[0][1]) if tuple(name for name, _ in pairs) == ("cost",) else None
    except (UnicodeDecodeError, ValueError, IndexError):
        return None


def _parse_statusup_item(body: bytes) -> tuple[int, int, int] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    pairs = _drop_trailing_last_update(pairs)
    if tuple(name for name, _ in pairs) != ("targetChrID", "useItemID", "useAmount"):
        return None
    values = tuple(value for _, value in pairs)
    if any(not value.isdecimal() or int(value) <= 0 for value in values):
        return None
    return tuple(int(value) for value in values)  # type: ignore[return-value]


def _parse_add_job(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    names = tuple(name for name, _ in pairs)
    if names not in (("targetID",), ("targetID", "isTutorial"), ("targetID", "lastUpdate"), ("targetID", "isTutorial", "lastUpdate")):
        return None
    target = pairs[0][1]
    if not target.isdecimal() or int(target) <= 0:
        return None
    if len(pairs) >= 2 and names[1] == "isTutorial" and pairs[1][1] != "True":
        return None
    if names[-1] == "lastUpdate" and pairs[-1][1] != "1":
        return None
    return int(target)


def _parse_rebirth(body: bytes) -> tuple[int, bool] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    pairs = _drop_trailing_last_update(pairs)
    if tuple(name for name, _ in pairs) != ("rebirthID", "useJoker") or not pairs[0][1].isdecimal() or int(pairs[0][1]) <= 0 or pairs[1][1] not in {"False", "True"}:
        return None
    return int(pairs[0][1]), pairs[1][1] == "True"


def _parse_summon_skill_unlock(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    pairs = _drop_trailing_last_update(pairs)
    if tuple(name for name, _ in pairs) != ("targetID",):
        return None
    target_id = pairs[0][1]
    if not target_id.isdecimal() or not 1 <= int(target_id) <= 16:
        return None
    return int(target_id)


def _parse_achievement_claim(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("id", "lastUpdate") or pairs[1][1] != "1":
        return None
    return int(pairs[0][1]) if pairs[0][1].isdecimal() and int(pairs[0][1]) > 0 else None


def _parse_sell_companions(body: bytes, *, multiple: bool) -> list[int] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    field = "sellList" if multiple else "inventoryID"
    if tuple(name for name, _ in pairs) != (field,):
        return None
    value = pairs[0][1].strip()
    if multiple and value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    values = value.split(",") if multiple else [value]
    if not values:
        return None
    try:
        ids = [int(item.strip()) for item in values]
    except ValueError:
        return None
    return ids if all(value > 0 for value in ids) and len(ids) == len(set(ids)) else None


def _companion_info(owned: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    records: dict[int, dict[str, Any]] = {}
    for companion in owned:
        current = records.get(companion["bid"])
        if current is None or (companion["lv"], companion["iid"]) > (current["lv"], current["iid"]):
            records[companion["bid"]] = copy.deepcopy(companion)
    return {"list": copy.deepcopy(owned), "record": [records[companion_id] for companion_id in sorted(records)]}


def _parse_companion_strengthen(body: bytes) -> tuple[int, list[int]] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if len(pairs) == 3 and pairs[-1] == ("lastUpdate", "1"):
        pairs = pairs[:-1]
    if tuple(name for name, _ in pairs) != ("baseID", "matList"):
        return None
    try:
        base_id = int(pairs[0][1])
    except ValueError:
        return None
    value = pairs[1][1].strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    try:
        materials = [int(item.strip()) for item in value.split(",")]
    except ValueError:
        return None
    if base_id <= 0 or not 1 <= len(materials) <= 4 or base_id in materials or any(item <= 0 for item in materials) or len(materials) != len(set(materials)):
        return None
    return base_id, materials


def _parse_companion_evolve(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if len(pairs) == 2 and pairs[-1] == ("lastUpdate", "1"):
        pairs = pairs[:-1]
    if tuple(name for name, _ in pairs) != ("baseID",):
        return None
    value = pairs[0][1]
    return int(value) if value.isdecimal() and int(value) > 0 else None


def _parse_companion_draw(body: bytes) -> tuple[int, int] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("kind", "count", "campaignID", "eventFlag", "lastUpdate"):
        return None
    try:
        values = {name: int(value) for name, value in pairs}
    except ValueError:
        return None
    if values["kind"] not in {1, 21} or not 1 <= values["count"] <= 100 or values["campaignID"] != 0 or values["eventFlag"] != 0 or values["lastUpdate"] < 0:
        return None
    return values["kind"], values["count"]


def _parse_ordinary_pact_draw(body: bytes) -> tuple[int, int, bool] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("kind", "count", "luckType", "campaignChrID", "eventFlag", "lastUpdate"):
        return None
    values = dict(pairs)
    if values["kind"] not in {"0", "1", "20"} or values["luckType"] not in {"false", "true"} or values["campaignChrID"] != "0" or values["eventFlag"] != "0" or not values["count"].isdecimal() or not values["lastUpdate"].isdecimal():
        return None
    kind, count = int(values["kind"]), int(values["count"])
    if kind == 20:
        return (
            (kind, count, values["luckType"] == "true")
            if count == 1 and values["lastUpdate"] == "1"
            else None
        )
    # The client emits an affordable remainder when its ten-pull control has
    # less than a full batch available (for example, count=6 with 20 Energy).
    # Button labels are not the wire contract; retain the strict envelope but
    # accept every client-visible batch from one through ten.
    if not 1 <= count <= 10:
        return None
    return kind, count, values["luckType"] == "true"


def _parse_companion_userdata_write(body: bytes) -> list[dict[str, Any]] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != ("buddyInfo", "lastUpdate") or int(pairs[1][1]) < 0:
            return None
        companions = json.loads(pairs[0][1])
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    fields = {"bid", "lv", "date", "iid", "exp", "flag", "chrID"}
    if not isinstance(companions, list) or not companions:
        return None
    if any(not isinstance(companion, dict) or set(companion) != fields or type(companion["bid"]) is not int or companion["bid"] <= 0 or type(companion["lv"]) is not int or companion["lv"] < 1 or type(companion["date"]) not in {int, float} or companion["date"] < 0 or any(type(companion[name]) is not int or companion[name] < 0 for name in ("iid", "exp", "flag", "chrID")) or companion["iid"] <= 0 for companion in companions):
        return None
    ids = [companion["iid"] for companion in companions]
    return companions if len(ids) == len(set(ids)) else None


def _project_companion_delta(
    userdata: dict[str, Any],
    submitted: list[dict[str, Any]],
    *,
    allow_equipment: bool = False,
) -> list[dict[str, Any]] | None:
    """Return a client-authored Companion delta projected over owned records.

    Shared so the standalone Companion write and the equip forms, which carry
    the same delta alongside a roster or party change, cannot drift apart.
    """
    buddy_info = userdata.get("buddyInfo")
    owned = buddy_info.get("list") if isinstance(buddy_info, dict) else None
    if not isinstance(owned, list):
        return None
    current = {companion.get("iid"): companion for companion in owned if isinstance(companion, dict) and type(companion.get("iid")) is int}
    if len(current) != len(owned) or not submitted or any(
        companion["iid"] not in current
        or any(companion[name] != current[companion["iid"]].get(name) for name in ("bid", "lv", "date", "iid", "exp"))
        or (
            not allow_equipment
            and companion["chrID"] != current[companion["iid"]].get("chrID")
        )
        or companion["flag"] & ~0x3
        or (current[companion["iid"]].get("flag", 0) & 1 and not companion["flag"] & 1)
        for companion in submitted
    ):
        return None
    candidates = copy.deepcopy(owned)
    updates = {companion["iid"]: companion for companion in submitted}
    for index, companion in enumerate(candidates):
        if companion["iid"] in updates:
            candidates[index] = copy.deepcopy(updates[companion["iid"]])
    return candidates


def _apply_companion_delta(userdata: dict[str, Any], submitted: list[dict[str, Any]]) -> bool:
    """Apply a validated standalone Companion preference delta in place."""
    candidates = _project_companion_delta(userdata, submitted)
    if candidates is None:
        return False
    userdata["buddyInfo"] = _companion_info(candidates)
    return True


def _valid_companion_equipment(
    characters: list[dict[str, Any]],
    companions: list[dict[str, Any]],
    previous_companions: list[dict[str, Any]],
    catalog: CompanionEquipmentCatalog | None,
) -> bool:
    """Require coherent links and master authorization for every new target."""
    by_character: dict[int, dict[str, Any]] = {}
    for character in characters:
        character_id = character.get("id") if isinstance(character, dict) else None
        buddy = character.get("buddy", 0) if isinstance(character, dict) else None
        if (
            type(character_id) is not int
            or character_id <= 0
            or character_id in by_character
            or type(buddy) is not int
            or buddy < 0
        ):
            return False
        by_character[character_id] = character
    by_inventory: dict[int, dict[str, Any]] = {}
    for companion in companions:
        inventory_id = companion.get("iid") if isinstance(companion, dict) else None
        if (
            type(inventory_id) is not int
            or inventory_id <= 0
            or inventory_id in by_inventory
        ):
            return False
        by_inventory[inventory_id] = companion
    previous_links = {
        companion.get("iid"): companion.get("chrID")
        for companion in previous_companions
        if (
            isinstance(companion, dict)
            and type(companion.get("iid")) is int
            and type(companion.get("chrID")) is int
        )
    }
    if len(previous_links) != len(previous_companions):
        return False
    equipped = [
        character.get("buddy", 0)
        for character in characters
        if character.get("buddy", 0)
    ]
    if len(equipped) != len(set(equipped)):
        return False
    for character_id, character in by_character.items():
        buddy = character.get("buddy", 0)
        if buddy and (
            buddy not in by_inventory
            or by_inventory[buddy].get("chrID") != character_id
        ):
            return False
    if not all(
        type(companion.get("chrID")) is int
        and companion["chrID"] >= 0
        and (
            companion["chrID"] == 0
            or (
                companion["chrID"] in by_character
                and by_character[companion["chrID"]].get("buddy", 0)
                == companion["iid"]
            )
        )
        for companion in companions
    ):
        return False
    return all(
        companion["chrID"] == 0
        or companion["chrID"] == previous_links.get(companion["iid"])
        or _companion_target_allowed(
            by_character[companion["chrID"]],
            companion,
            catalog,
        )
        for companion in companions
    )


def _companion_target_allowed(
    character: dict[str, Any],
    companion: dict[str, Any],
    catalog: CompanionEquipmentCatalog | None,
) -> bool:
    """Mirror ``Buddy.CanEquip`` character-family and species checks.

    ``RequiredLevel`` is intentionally absent: the final client uses it to
    activate an equipped Companion's effects, not to prohibit selection.
    """
    if catalog is None:
        return False
    character_id = character.get("id")
    companion_id = companion.get("bid")
    job_index = character.get("jobID")
    if (
        type(character_id) is not int
        or type(companion_id) is not int
        or type(job_index) is not int
    ):
        return False
    character_master = catalog.characters.get(character_id)
    companion_master = catalog.companions.get(companion_id)
    if (
        character_master is None
        or companion_master is None
        or not 0 <= job_index < len(character_master.job_species)
    ):
        return False
    family_id = character_master.ancestor_character_id or character_id
    if (
        companion_master.exclusive_character_id
        and companion_master.exclusive_character_id
        not in {character_id, family_id}
    ):
        return False
    return (
        companion_master.exclusive_species_id == 0
        or companion_master.exclusive_species_id
        == character_master.job_species[job_index]
    )


def _parse_party_companion_userdata_write(
    body: bytes,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]] | None:
    """Parse a party change that also carries a Companion delta.

    The equip/party screen posts this when swapping a character *and* touching
    Companion state in one action. It is the party form with `buddyInfo`
    inserted after `chrdata`, so neither the party parser nor the equip parser
    above matches it on its own.
    """
    fields = (
        "chrdata", "buddyInfo", "teamMembers", "teamMembers_VS", "teamBuddies_VS",
        "teamNo", "teamNo_VS", "summonId", "lastUpdate",
    )
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != fields:
        return None
    values = dict(pairs)
    characters = _decoded_roster(values["chrdata"])
    companions = _decoded_companions(values["buddyInfo"])
    if characters is None or companions is None or not _valid_last_update(values["lastUpdate"]):
        return None
    # Reuse the party form's own validation by handing it the same body with
    # the Companion delta removed, so the two paths cannot drift apart.
    without_companions = urlencode([(name, value) for name, value in pairs if name != "buddyInfo"])
    party = _parse_free_roam_party_userdata_write(without_companions.encode("ascii"))
    if party is None:
        return None
    return party[0], party[1], companions


def _parse_companion_equip_userdata_write(
    body: bytes,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
    """Parse the equip screen's dual-dirty roster + Companion write.

    Moving a Companion from one character to another dirties both halves at
    once, so the client posts `chrdata` and `buddyInfo` together. Neither the
    roster form (no `buddyInfo`) nor the Companion form (no `chrdata`) accepts
    that, so it was refused and the player saw a network error.
    """
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("chrdata", "buddyInfo", "lastUpdate"):
        return None
    characters = _decoded_roster(pairs[0][1])
    companions = _decoded_companions(pairs[1][1])
    if characters is None or companions is None or not _valid_last_update(pairs[2][1]):
        return None
    return characters, companions


def _decoded_roster(value: str) -> list[dict[str, Any]] | None:
    """Decode and validate a `chrdata` payload shared by several write forms."""
    try:
        characters = json.loads(value)
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(characters, list) or not all(
        isinstance(character, dict) and type(character.get("id")) is int and character["id"] > 0
        for character in characters
    ):
        return None
    ids = [character["id"] for character in characters]
    return characters if len(ids) == len(set(ids)) else None


def _decoded_companions(value: str) -> list[dict[str, Any]] | None:
    """Decode and validate a `buddyInfo` payload shared by several write forms."""
    try:
        companions = json.loads(value)
    except (ValueError, json.JSONDecodeError):
        return None
    fields = {"bid", "lv", "date", "iid", "exp", "flag", "chrID"}
    if not isinstance(companions, list) or not companions:
        return None
    if any(
        not isinstance(companion, dict) or set(companion) != fields
        or type(companion["bid"]) is not int or companion["bid"] <= 0
        or type(companion["lv"]) is not int or companion["lv"] < 1
        or type(companion["date"]) not in {int, float} or companion["date"] < 0
        or any(type(companion[name]) is not int or companion[name] < 0 for name in ("iid", "exp", "flag", "chrID"))
        or companion["iid"] <= 0
        for companion in companions
    ):
        return None
    ids = [companion["iid"] for companion in companions]
    return companions if len(ids) == len(set(ids)) else None


def _parse_free_roam_character_userdata_write(body: bytes) -> list[dict[str, Any]] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != ("chrdata", "lastUpdate") or int(pairs[1][1]) < 0:
            return None
        characters = json.loads(pairs[0][1])
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(characters, list) or not all(
        isinstance(character, dict) and type(character.get("id")) is int and character["id"] > 0
        for character in characters
    ):
        return None
    ids = [character["id"] for character in characters]
    return characters if len(ids) == len(set(ids)) else None


def _parse_free_roam_party_userdata_write(
    body: bytes,
) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
    fields = (
        "chrdata", "teamMembers", "teamMembers_VS", "teamBuddies_VS",
        "teamNo", "teamNo_VS", "summonId", "lastUpdate",
    )
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != fields or int(pairs[-1][1]) < 0:
            return None
        values = dict(pairs)
        characters = json.loads(values["chrdata"])
        team_members = json.loads(values["teamMembers"])
        versus_members = json.loads(values["teamMembers_VS"])
        versus_buddies = json.loads(values["teamBuddies_VS"])
        team_no, versus_team_no, summon_id = (int(values[name]) for name in ("teamNo", "teamNo_VS", "summonId"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if (
        not isinstance(characters, list)
        or not all(isinstance(character, dict) and type(character.get("id")) is int and character["id"] > 0 for character in characters)
        or not all(isinstance(values, list) and all(type(value) is int and value >= 0 for value in values) for values in (team_members, versus_members, versus_buddies))
        or team_no < 0 or versus_team_no < 0 or summon_id < 0
    ):
        return None
    ids = [character["id"] for character in characters]
    # The client may send only the row it changed alongside a complete party
    # layout.  Membership is checked against the durable roster atomically in
    # ``update_character_userdata``; requiring it here would reject that valid
    # delta before it can be merged.
    if len(ids) != len(set(ids)):
        return None
    return characters, {
        "teamMembers": team_members,
        "teamMembers_VS": versus_members,
        "teamBuddies_VS": versus_buddies,
        "teamNo": team_no,
        "teamNo_VS": versus_team_no,
        "summonId": summon_id,
    }


def _parse_free_roam_party_layout_userdata_write(body: bytes) -> dict[str, Any] | None:
    """Accept the client's later party-only save without replacing its roster."""
    fields = (
        "teamMembers", "teamMembers_VS", "teamBuddies_VS",
        "teamNo", "teamNo_VS", "summonId", "lastUpdate",
    )
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != fields or int(pairs[-1][1]) < 0:
            return None
        values = dict(pairs)
        team_members = json.loads(values["teamMembers"])
        versus_members = json.loads(values["teamMembers_VS"])
        versus_buddies = json.loads(values["teamBuddies_VS"])
        team_no, versus_team_no, summon_id = (int(values[name]) for name in ("teamNo", "teamNo_VS", "summonId"))
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if (
        not all(isinstance(rows, list) and all(type(value) is int and value >= 0 for value in rows) for rows in (team_members, versus_members, versus_buddies))
        or team_no < 0 or versus_team_no < 0 or summon_id < 0
    ):
        return None
    return {
        "teamMembers": team_members,
        "teamMembers_VS": versus_members,
        "teamBuddies_VS": versus_buddies,
        "teamNo": team_no,
        "teamNo_VS": versus_team_no,
        "summonId": summon_id,
    }
