"""Check a hand-edited save against the invariants the client and server assume.

A save is not plain data, and the ways it goes wrong are quiet ones: the client
fails while parsing an otherwise successful response, or a later write is
refused, long after the edit that caused it.  This module is the single
authority on what a well-formed save looks like, so an editing tool never has to
carry its own copy of these rules.

Three of the traps are worth naming here, because none is visible in the JSON:

- `jobLevels` is packed, not a level.  The low twelve bits are the job level and
  the remaining bits carry its progression, so writing a plain `90` sets level 90
  and destroys everything above it.
- The client reads those values with LitJson's *double* accessor.  A value that
  round-trips through a permissive editor as the integer `10` rather than `10.0`
  makes the client fail parsing a response the server considered successful.
  This is why the server re-coerces them on every read.
- `tutorial_requests` caches whole response payloads against their request id.
  Editing a value the cache already answered with does not change what a replay
  of that request returns.

Everything here is read-only: nothing in this module writes a save.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


#: The low bits of a packed `jobLevels` entry hold the job level itself.
JOB_LEVEL_MASK = 0xFFF
#: `ServerConstants.levelCap`, the highest level the client will show.
LEVEL_CAP = 90
#: The client's own inventory shape, shared with the Hunting catalogs.
ITEM_SLOTS = 181
MAX_ITEM_STACK = 999
#: `ServerConstants.maxCoins` and `maxEnergy`.
MAX_COINS = 99999999
MAX_ENERGY = 9999
#: Values the client reads as LitJson doubles.  An integer here is a parse
#: failure on the client, not a rounding difference.
FLOAT_FIELDS = ("jobLevels", "jobSlots", "date", "lastupdate", "refillStartTime", "metalZoneUnlockTime")
WALLET_FIELDS = ("coins", "energy", "freeEnergy", "energyAppStore", "energyGooglePlay", "energyAndApp")


@dataclass(frozen=True)
class Finding:
    """One problem with a save, located precisely enough to act on."""

    account: str
    field: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {"account": self.account, "field": self.field, "message": self.message, "severity": self.severity}


def decode_job_level(value: float | int) -> tuple[int, int]:
    """Split a packed `jobLevels` entry into its level and its progression."""
    packed = int(value)
    if packed < 0:
        raise ValueError("a packed job level cannot be negative")
    return packed & JOB_LEVEL_MASK, packed >> 12


def encode_job_level(level: int, progression: int) -> float:
    """Repack a level and its progression, as a float the client can read."""
    if not 0 <= level <= JOB_LEVEL_MASK or progression < 0:
        raise ValueError(f"level must be 0 to {JOB_LEVEL_MASK} and progression cannot be negative")
    return float((progression << 12) | level)


def validate_document(document: object) -> list[Finding]:
    """Return every problem found in a whole save, most structural first."""
    if not isinstance(document, dict) or not isinstance(document.get("accounts"), dict):
        return [Finding("", "accounts", "the save has no accounts object")]
    findings: list[Finding] = []
    for account_id, account in sorted(document["accounts"].items()):
        findings.extend(_validate_account(str(account_id), account))
    tokens = document.get("tokens")
    if not isinstance(tokens, dict):
        findings.append(Finding("", "tokens", "the save has no token-binding object"))
    else:
        for token, owner in sorted(tokens.items(), key=lambda item: str(item[0])):
            if not isinstance(token, str) or not isinstance(owner, str):
                findings.append(Finding("", "tokens", "every token binding must map one string to an account id"))
                continue
            if owner not in document["accounts"]:
                findings.append(Finding("", f"tokens.{token}", f"token points at unknown account {owner!r}"))
    active = document.get("active_account_id")
    if active is not None and active not in document["accounts"]:
        findings.append(Finding("", "active_account_id", f"active account {active!r} does not exist"))
    aliases = document.get("account_aliases")
    if aliases is not None:
        if not isinstance(aliases, dict):
            findings.append(Finding("", "account_aliases", "the linked-device map must be an object"))
        else:
            for device, owner in sorted(aliases.items(), key=lambda item: str(item[0])):
                if not isinstance(device, str) or not isinstance(owner, str):
                    findings.append(Finding("", "account_aliases", "every linked device must map one string UUID to an account id"))
                    continue
                if owner not in document["accounts"]:
                    findings.append(Finding("", f"account_aliases.{device}", f"linked device points at unknown account {owner!r}"))
                if device in document["accounts"]:
                    findings.append(Finding("", f"account_aliases.{device}", "a device UUID cannot name both an account and a link; the server refuses such a save"))
    return findings


def _validate_account(account_id: str, account: object) -> list[Finding]:
    if not isinstance(account, dict) or not isinstance(account.get("userdata"), dict):
        return [Finding(account_id, "userdata", "the account has no userdata object")]
    userdata = account["userdata"]
    findings = [
        *_validate_roster(account_id, userdata),
        *_validate_items(account_id, userdata),
        *_validate_wallet(account_id, userdata),
        *_validate_companions(account_id, userdata),
        *_validate_floats(account_id, userdata),
    ]
    if account.get("tutorial_requests"):
        findings.append(Finding(
            account_id, "tutorial_requests",
            f"{len(account['tutorial_requests'])} cached response payloads remain; a replayed request "
            f"returns what it returned before this edit, not the edited values",
            "warning",
        ))
    return findings


def _validate_roster(account_id: str, userdata: dict[str, Any]) -> list[Finding]:
    rows = userdata.get("chrdata")
    if not isinstance(rows, list):
        return [Finding(account_id, "chrdata", "the roster is missing or is not a list")]
    findings: list[Finding] = []
    seen: set[int] = set()
    for index, row in enumerate(rows):
        where = f"chrdata[{index}]"
        if not isinstance(row, dict) or type(row.get("id")) is not int or row["id"] <= 0:
            findings.append(Finding(account_id, where, "each character needs a positive integer id"))
            continue
        if row["id"] in seen:
            findings.append(Finding(account_id, where, f"character id {row['id']} appears more than once"))
        seen.add(row["id"])
        levels = row.get("jobLevels")
        if not isinstance(levels, list) or not levels:
            findings.append(Finding(account_id, f"{where}.jobLevels", "jobLevels must be a non-empty list"))
            continue
        for slot, value in enumerate(levels):
            if type(value) not in (int, float) or value < 0:
                findings.append(Finding(account_id, f"{where}.jobLevels[{slot}]", "a packed job level must be a non-negative number"))
                continue
            level, _ = decode_job_level(value)
            if level > LEVEL_CAP:
                findings.append(Finding(
                    account_id, f"{where}.jobLevels[{slot}]",
                    f"decodes to level {level}, above the client's cap of {LEVEL_CAP}; "
                    f"a plain level written straight into this field is the usual cause",
                ))
    findings.extend(_validate_party(account_id, userdata, seen))
    return findings


def _validate_party(account_id: str, userdata: dict[str, Any], roster: set[int]) -> list[Finding]:
    findings: list[Finding] = []
    for name in ("teamMembers", "teamMembers_VS", "teamBuddies_VS"):
        members = userdata.get(name)
        if members is None:
            continue
        if not isinstance(members, list):
            findings.append(Finding(account_id, name, "a party must be a list"))
            continue
        invalid = [
            index for index, member in enumerate(members)
            if type(member) is not int or member < 0
        ]
        if invalid:
            findings.append(Finding(
                account_id, name,
                "every party slot must be a non-negative integer "
                f"(invalid indexes: {', '.join(str(index) for index in invalid)})",
            ))
            continue
        # Zero is an empty slot; anything else must be a character the account
        # owns, or the client's next party save is refused.
        missing = sorted({member for member in members if member and member not in roster})
        if name in {"teamMembers", "teamMembers_VS"} and missing:
            findings.append(Finding(
                account_id, name,
                f"party names {', '.join(str(value) for value in missing)}, which the roster does not contain",
            ))
    for name in ("teamNo", "teamNo_VS", "summonId"):
        value = userdata.get(name)
        if value is not None and (type(value) is not int or value < 0):
            findings.append(Finding(account_id, name, "must be a non-negative integer"))
    return findings


def _validate_items(account_id: str, userdata: dict[str, Any]) -> list[Finding]:
    items = userdata.get("itemList")
    if not isinstance(items, list):
        return [Finding(account_id, "itemList", "the inventory is missing or is not a list")]
    findings: list[Finding] = []
    if len(items) != ITEM_SLOTS:
        findings.append(Finding(
            account_id, "itemList",
            f"the inventory has {len(items)} slots; the client's shape is exactly {ITEM_SLOTS}",
        ))
    for index, value in enumerate(items):
        if type(value) is not int or not 0 <= value <= MAX_ITEM_STACK:
            findings.append(Finding(
                account_id, f"itemList[{index}]",
                f"each slot holds a whole number from 0 to {MAX_ITEM_STACK}",
            ))
    return findings


def _validate_wallet(account_id: str, userdata: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for name, maximum in (("coins", MAX_COINS), ("energy", MAX_ENERGY), ("freeEnergy", MAX_ENERGY)):
        value = userdata.get(name)
        if value is None:
            continue
        if type(value) is not int or not 0 <= value <= maximum:
            findings.append(Finding(account_id, name, f"{name} must be a whole number from 0 to {maximum}"))
    projection = userdata.get("valuables")
    if projection is None:
        return findings
    if not isinstance(projection, dict):
        return [*findings, Finding(account_id, "valuables", "the wallet projection must be an object")]
    # The client reads the nested projection while the server mutates the flat
    # fields, so a disagreement shows the player one balance and spends another.
    for name in WALLET_FIELDS:
        if name in userdata and name in projection and userdata[name] != projection[name]:
            findings.append(Finding(
                account_id, f"valuables.{name}",
                f"reads {projection[name]} while {name} reads {userdata[name]}; these must agree",
            ))
    return findings


def _validate_companions(account_id: str, userdata: dict[str, Any]) -> list[Finding]:
    info = userdata.get("buddyInfo")
    if info is None:
        return []
    owned = info.get("list") if isinstance(info, dict) else None
    if not isinstance(owned, list):
        return [Finding(account_id, "buddyInfo.list", "the Companion box must be a list")]
    findings: list[Finding] = []
    inventory_ids: set[int] = set()
    for index, row in enumerate(owned):
        where = f"buddyInfo.list[{index}]"
        if not isinstance(row, dict) or type(row.get("iid")) is not int or row["iid"] <= 0:
            findings.append(Finding(account_id, where, "each Companion needs a positive integer iid"))
            continue
        if row["iid"] in inventory_ids:
            findings.append(Finding(account_id, where, f"inventory id {row['iid']} appears more than once"))
        inventory_ids.add(row["iid"])
    next_id = userdata.get("nextCompanionInventoryId")
    if next_id is not None and (type(next_id) is not int or next_id <= max(inventory_ids, default=0)):
        findings.append(Finding(
            account_id, "nextCompanionInventoryId",
            f"must be greater than every id in the box (highest is {max(inventory_ids, default=0)}), "
            f"or the next Companion granted reuses an id",
        ))
    return findings


def _validate_floats(account_id: str, userdata: dict[str, Any]) -> list[Finding]:
    """Catch the integers that make the client fail parsing a good response."""
    findings: list[Finding] = []

    def check(value: object, where: str) -> None:
        if type(value) is int:
            findings.append(Finding(
                account_id, where,
                f"is the whole number {value}; the client reads this field as a decimal, so it must be "
                f"written {value}.0",
            ))

    for name in ("lastupdate", "refillStartTime", "metalZoneUnlockTime"):
        if name in userdata:
            check(userdata[name], name)
    rows = userdata.get("chrdata")
    for index, row in enumerate(rows if isinstance(rows, list) else []):
        if not isinstance(row, dict):
            continue
        for name in ("jobLevels", "jobSlots"):
            values = row.get(name)
            for slot, value in enumerate(values if isinstance(values, list) else []):
                check(value, f"chrdata[{index}].{name}[{slot}]")
        if "date" in row:
            check(row["date"], f"chrdata[{index}].date")
    return findings
