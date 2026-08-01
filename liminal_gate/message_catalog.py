"""Strict user-local inbox messages and bounded read rewards."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
import tomllib


class MessageCatalogError(ValueError):
    """A user-local message catalog is invalid."""


@dataclass(frozen=True)
class LocalMessage:
    message_id: str
    date: float
    days_last: int
    texts: dict[str, str]
    coins: int
    free_energy: int
    items: dict[int, int]


@dataclass(frozen=True)
class MessageCatalog:
    item_slots: int
    max_free_energy: int
    max_coins: int
    max_stack: int
    messages: tuple[LocalMessage, ...]


# Retail first-clear chapter presents. These are progress-gated inbox messages,
# not unconditional startup gifts: the next unlocked chapter must be strictly
# greater than the completed chapter. Item IDs are decoded by the final client
# as Metal Ticket (50) and Companion Ticket (112).
CHAPTER_MILESTONES: tuple[tuple[int, int, int, str], ...] = (
    (5, 50, 2, "Metal Ticket"),
    (6, 112, 3, "Companion Ticket"),
    (7, 50, 2, "Metal Ticket"),
    (8, 112, 3, "Companion Ticket"),
    (10, 112, 4, "Companion Ticket"),
)
BUNDLED_ITEM_SLOTS = 181
BUNDLED_MAX_FREE_ENERGY = 9_999
BUNDLED_MAX_COINS = 99_999_999
BUNDLED_MAX_STACK = 999


def load_message_catalog(path: Path) -> MessageCatalog:
    try:
        document = tomllib.loads(path.read_text(encoding="utf-8")) if path.suffix.lower() == ".toml" else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        raise MessageCatalogError("could not read message catalog JSON or TOML") from error
    required = {"schema_version", "provenance", "item_slots", "max_free_energy", "max_coins", "max_stack", "messages"}
    if not isinstance(document, dict) or set(document) != required:
        raise MessageCatalogError("message catalog has an invalid schema")
    if document["schema_version"] != 1 or document["provenance"] != "user-supplied":
        raise MessageCatalogError("message catalog requires schema version 1 and user-supplied provenance")
    limits = ("item_slots", "max_free_energy", "max_coins", "max_stack")
    if any(type(document[key]) is not int or document[key] < 1 for key in limits):
        raise MessageCatalogError("message catalog limits must be positive integers")
    raw = document["messages"]
    if not isinstance(raw, list):
        raise MessageCatalogError("messages must be an array")
    messages = tuple(_message(value, document["item_slots"]) for value in raw)
    ids = [message.message_id for message in messages]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise MessageCatalogError("messages must be ordered and unique by id")
    return MessageCatalog(*(document[key] for key in limits), messages)


def _message(value: object, item_slots: int) -> LocalMessage:
    required = {"id", "date", "days_last", "messages", "coins", "free_energy", "items"}
    if not isinstance(value, dict) or set(value) != required:
        raise MessageCatalogError("each message has an invalid schema")
    if not isinstance(value["id"], str) or not value["id"] or type(value["date"]) not in {int, float} or not math.isfinite(value["date"]) or value["date"] < 0:
        raise MessageCatalogError("message id/date values are outside range")
    if type(value["days_last"]) is not int or value["days_last"] < 0 or type(value["coins"]) is not int or value["coins"] < 0 or type(value["free_energy"]) is not int or value["free_energy"] < 0:
        raise MessageCatalogError("message numeric values are outside range")
    texts = value["messages"]
    if not isinstance(texts, dict) or set(texts) != {"default", "ja", "en"} or not all(isinstance(text, str) for text in texts.values()):
        raise MessageCatalogError("message texts require default, ja, and en strings")
    items = value["items"]
    if not isinstance(items, dict):
        raise MessageCatalogError("message items must be an object")
    parsed: dict[int, int] = {}
    for raw_id, amount in items.items():
        if not isinstance(raw_id, str) or not raw_id.isdecimal() or raw_id != str(int(raw_id)) or not 1 <= int(raw_id) <= item_slots or type(amount) is not int or amount < 1:
            raise MessageCatalogError("message items require in-range decimal IDs and positive amounts")
        parsed[int(raw_id)] = amount
    return LocalMessage(value["id"], float(value["date"]), value["days_last"], dict(texts), value["coins"], value["free_energy"], parsed)


def build_bundled_chapter_message_policy() -> MessageCatalog:
    """Return reward limits for the progress-gated retail chapter presents.

    The messages themselves are created only when an account has completed the
    relevant chapter. Keeping this catalog empty prevents a new Chapter 1
    account from seeing later presents while still giving the existing inbox
    settlement path its recovered client limits.
    """
    return MessageCatalog(
        BUNDLED_ITEM_SLOTS,
        BUNDLED_MAX_FREE_ENERGY,
        BUNDLED_MAX_COINS,
        BUNDLED_MAX_STACK,
        (),
    )


def eligible_chapter_messages(progress_code: int, issued_at: float) -> tuple[LocalMessage, ...]:
    """Build every retail chapter present earned by ``progress_code``."""
    if type(progress_code) is not int or progress_code < 0:
        return ()
    unlocked_chapter = (progress_code & 0xFFFF) >> 6
    messages: list[LocalMessage] = []
    for chapter, item_id, count, item_name in CHAPTER_MILESTONES:
        if unlocked_chapter <= chapter:
            continue
        title = "Chapter milestone reward"
        messages.append(LocalMessage(
            message_id=f"chapter:{chapter}:item:{item_id}",
            date=issued_at,
            days_last=36_500,
            texts={
                "default": f"{title}.\nReward: {item_name} x{count}",
                "ja": title,
                "en": title,
            },
            coins=0,
            free_energy=0,
            items={item_id: count},
        ))
    return tuple(messages)
