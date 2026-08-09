"""Privacy-bounded local HTTP diagnostics for compatibility failures."""

from __future__ import annotations

import hashlib
from http import HTTPStatus
import json
from pathlib import Path
from threading import Lock
import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit


def safe_form_diagnostics(body: bytes) -> dict[str, Any]:
    """Return a small view of a form without account or structured state."""
    try:
        fields = tuple(
            parse_qsl(
                body.decode("ascii"),
                keep_blank_values=True,
                strict_parsing=True,
            )
        )
    except (UnicodeDecodeError, ValueError):
        return {
            "request_body_sha256": hashlib.sha256(body).hexdigest(),
            "request_body_size": len(body),
        }
    details: dict[str, Any] = {"request_fields": [name for name, _ in fields]}
    safe_values = {
        name: value
        for name, value in fields
        # The entry costs a start declares are stage economics, not account
        # state: they are what the catalog is compared against, and a refused
        # start is unreadable without them. Two reports of a 501 on
        # `start_quest` could not be told apart -- an unknown stage from a cost
        # that disagreed with the catalog -- because these five were withheld.
        if name in {
            "progressCode", "worldMapNo", "lastUpdate", "chapter", "section",
            "stamina", "coins", "itemID", "itemCount", "helpItemID",
        }
    }
    if safe_values:
        details["request_values"] = safe_values
    raw = dict(fields)
    if "idlist" in raw:
        # The mail routes carry a JSON array of catalog message IDs. The IDs
        # themselves stay out of the log; whether it parsed and how many it
        # named is what separates a malformed form from an unknown message.
        try:
            identifiers = json.loads(raw["idlist"])
        except json.JSONDecodeError:
            details["idlist_shape"] = "not JSON"
        else:
            details["idlist_shape"] = (
                f"{len(identifiers)} entries, "
                + ", ".join(sorted({type(value).__name__ for value in identifiers}) or ["empty"])
                if isinstance(identifiers, list)
                else f"not an array: {type(identifiers).__name__}"
            )
    try:
        valuables = json.loads(raw["valuables"]) if "valuables" in raw else None
        battle = json.loads(raw["battle_result"]) if "battle_result" in raw else None
    except json.JSONDecodeError:
        valuables = battle = None
    if isinstance(valuables, dict) and type(valuables.get("coins")) is int:
        details["reported_wallet_coins"] = valuables["coins"]
    if isinstance(battle, dict):
        settlement = {
            name: battle[name]
            for name in ("chapter", "section", "coins", "exp")
            if type(battle.get(name)) is int
        }
        # Coins and EXP alone cannot say why a bounded settlement was refused.
        # A Puzzle Quest clear reporting a Companion was refused eleven times
        # over with `coins: 0, exp: 0` in the log, and nothing in it named the
        # channel at fault -- see `docs/findings.md`. These are counts, not
        # contents: how many Companions, recruits, Summons, and item stacks a
        # result claimed, which is enough to point at the channel without
        # putting a single identity or body string in the log.
        for name in ("buddies", "monsters", "summons"):
            if isinstance(battle.get(name), list):
                settlement[f"reported_{name}"] = len(battle[name])
        if isinstance(battle.get("items"), dict):
            counts = [count for count in battle["items"].values() if type(count) is int]
            settlement["reported_item_stacks"] = len(battle["items"])
            settlement["reported_items_total"] = sum(counts)
        if settlement:
            details["reported_battle_result"] = settlement
    return details


# Form fields whose value is a JSON document rather than a scalar. A write is
# refused on the *shape* of one of these, so that is what a diagnostic needs.
_JSON_FORM_FIELDS = (
    "chrdata", "buddyInfo", "teamMembers", "party", "itemList", "summonList",
    "valuables", "battle_result",
)
# The only key names a diagnostic may repeat. A body must never introduce a
# new string into the log, so a name is echoed when this server already models
# it and is counted otherwise. These are the keys the write validators, the
# stored projection, and the settlement parsers name for themselves.
_KNOWN_KEYS = frozenset({
    # The Companion row and the stored `buddyInfo` projection around it.
    "bid", "lv", "date", "iid", "exp", "flag", "chrID", "list", "record",
    # Roster and party. Every member `_valid_generic_character_record` names,
    # because that validator gates the clear parser: a row it will not read
    # refuses every clear the account attempts afterwards, and the refusal is
    # unreadable unless the log can say *which* member was unfamiliar. A
    # recoded row carrying `plusCount` did exactly that and logged only
    # "6 unrecognized keys", naming none of them.
    "id", "teamMembers", "jobLevels", "job", "equip",
    "buddy", "jobSlots", "jobID", "flags", "skillBoost", "luck", "plusCount",
    # Wallet projections.
    "coins", "energy", "freeEnergy", "energyAppStore", "energyAndApp",
    "energyGooglePlay", "bonusStamina", "refillStartTime",
    # Battle settlement.
    "chapter", "section", "items", "buddies", "summons", "monsters",
})


def _key_view(names: Any) -> dict[str, Any]:
    """Split key names into the ones this server models and a count of the rest."""
    known = sorted(name for name in names if name in _KNOWN_KEYS)
    view: dict[str, Any] = {"keys": known}
    unrecognized = len(names) - len(known)
    if unrecognized:
        view["unrecognized_keys"] = unrecognized
    return view


def _json_shape(value: Any) -> dict[str, Any]:
    """Describe a decoded JSON value by structure and type, never by content."""
    if isinstance(value, list):
        shape: dict[str, Any] = {"type": "list", "entries": len(value)}
        rows = [row for row in value if isinstance(row, dict)]
        if rows:
            shape["key_sets"] = len({tuple(sorted(row)) for row in rows})
            types: dict[str, list[str]] = {}
            for row in rows:
                for key, item in row.items():
                    name = type(item).__name__
                    if name not in types.setdefault(key, []):
                        types[key].append(name)
            view = _key_view(types)
            shape["entry_types"] = {key: sorted(types[key]) for key in view["keys"]}
            if "unrecognized_keys" in view:
                shape["unrecognized_entry_keys"] = view["unrecognized_keys"]
        elif value:
            shape["entry_types"] = sorted({type(row).__name__ for row in value})
        return shape
    if isinstance(value, dict):
        return {"type": "object", **_key_view(value)}
    return {"type": type(value).__name__}


def refused_write_shapes(body: bytes) -> dict[str, Any]:
    """Structure of a refused write's JSON fields: types and key names only.

    A refusal to parse otherwise records just the field list, which is
    identical to the accepted form — the difference that caused it lives in
    the shape, and bodies are never logged. Six live equip writes were refused
    on a field tuple that succeeded minutes later, and nothing in the log could
    say which half or which key was at fault.

    No value ever appears here, and no string from the body does either: only
    JSON types, entry counts, how many distinct key sets a list holds, and key
    names this server already models. An unmodelled key is counted, not named.
    """
    try:
        fields = dict(
            parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True)
        )
    except (UnicodeDecodeError, ValueError):
        return {}
    shapes: dict[str, Any] = {}
    for name in _JSON_FORM_FIELDS:
        if name not in fields:
            continue
        try:
            shapes[name] = _json_shape(json.loads(fields[name]))
        except (ValueError, json.JSONDecodeError):
            shapes[name] = {"type": "invalid_json"}
    return shapes


class EventRecorder:
    """Append route diagnostics without retaining account identities or bodies."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.lock = Lock()

    def record(
        self,
        method: str,
        target: str,
        status: HTTPStatus,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.path is None:
            return
        event = {
            "method": method,
            "path": urlsplit(target).path,
            "status": status.value,
            "timestamp_utc": int(time.time()),
        }
        if details:
            event.update(details)
        encoded = json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()
