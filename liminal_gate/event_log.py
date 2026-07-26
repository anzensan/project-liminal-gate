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
        if name in {"progressCode", "worldMapNo", "lastUpdate", "chapter", "section"}
    }
    if safe_values:
        details["request_values"] = safe_values
    raw = dict(fields)
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
        if settlement:
            details["reported_battle_result"] = settlement
    return details


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
