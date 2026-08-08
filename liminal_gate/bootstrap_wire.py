"""Wire-encoding helpers shared by the bootstrap transport.

The response side renders the one-time token and account id into profile
templates, hoists an endpoint's refusal code onto the field the client reads,
and signs the JSON body the way the final client verifies it. The request
side holds the small form-shape checks strict ordered-field parsers share.
Everything here is imported back into ``bootstrap_server``; this module must
never import the server.
"""

from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

from liminal_gate.bootstrap_profile import SigningProfile


def _render(value: Any, token: str, account_id: str | None = None) -> Any:
    if isinstance(value, str):
        rendered = value.replace("{otk}", token)
        return rendered if account_id is None else rendered.replace("{uuid}", account_id)
    if isinstance(value, list):
        return [_render(item, token, account_id) for item in value]
    if isinstance(value, dict):
        return {key: _render(item, token, account_id) for key, item in value.items()}
    return copy.deepcopy(value)


def _endpoint_refusal_envelope(payload: dict[str, Any]) -> dict[str, Any]:
    """Carry an endpoint's own refusal code on the field the client reads.

    `errorCode` is the *transport* namespace — `AppServerUtil.ErrorCode` is
    1, 90 and 100-115 — and the client only reads it when `success` is false,
    a path that shows the common error dialog and never invokes the endpoint's
    callback. An endpoint's own code rides `cmdError` on an accepted success,
    which the client defaults to zero and passes as that callback's first
    argument. Both are confirmed in `reports/response_verifier.md`.

    Emitting a route code as `errorCode` therefore never reaches the screen
    that asked: refusing a Trading Post trade with `NotEnoughItems` (3) showed
    a bare "ErrorCode : 3" server error instead of the counter's own message,
    because 3 is not a transport code. This server never emits a transport
    error in a signed body, so any refusal code in one belongs on `cmdError`.

    `success` itself is not optional, and its absence does not read as false.
    `AppServerUtil.<callAPI>` (ARM64 `0xDBE174`) casts `json["success"]`
    straight to bool with no `Contains` guard ahead of it -- unlike
    `lastupdate`, `cmdError`, and every field the endpoint callbacks read,
    which are all guarded. A body without the key therefore raises inside the
    transport coroutine, which is a soft lock rather than an error: the request
    has already been settled and answered, the callback never runs, and the
    "Connecting" overlay it raised is never taken down. So a payload that
    carries no verdict of its own is stamped with the one it was returned
    under. Adding the key here rather than at each route means a route cannot
    reintroduce the hang by forgetting it; an explicit `False` is left alone.
    """
    code = payload.get("errorCode")
    if payload.get("success") is True or type(code) is not int:
        return payload if "success" in payload else {"success": True, **payload}
    rest = {key: value for key, value in payload.items() if key not in {"success", "errorCode"}}
    return {"success": True, "cmdError": code, **rest}


def _signed_json(token: str, payload: dict[str, Any], signing: SigningProfile) -> bytes:
    placeholder = "0" * (signing.digest_end - signing.digest_start)
    unsigned_payload = {**payload, "digest": placeholder}
    text = json.dumps(unsigned_payload, ensure_ascii=True) + "\n"
    marker = '"digest": "'
    digest_offset = text.index(marker) + len(marker)
    unsigned = text[:digest_offset] + text[digest_offset + len(placeholder):]
    digest = hashlib.md5((token + unsigned + signing.salt).encode("utf-8")).hexdigest().upper()
    selected = digest[signing.digest_start:signing.digest_end]
    return (text[:digest_offset] + selected + text[digest_offset + len(placeholder):]).encode("utf-8")


def _json_fields_match(values: dict[str, str], expected_kinds: dict[str, str]) -> bool:
    for name, expected_kind in expected_kinds.items():
        try:
            value = json.loads(values[name])
        except (KeyError, json.JSONDecodeError):
            return False
        if expected_kind == "object" and not isinstance(value, dict):
            return False
        if expected_kind == "array" and not isinstance(value, list):
            return False
    return True


def _drop_trailing_last_update(pairs: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """Drop a single trailing ``lastUpdate`` pair from a mutation POST body.

    The final client's shared mutation POST helper appends ``&lastUpdate=1``, so
    strict ordered-field parsers must tolerate it before their exact-tuple
    check. Only a trailing occurrence is removed, which preserves each form's
    positional fields; bodies without it are unaffected.

    Routes whose form requires ``lastUpdate`` as a named field parse it
    directly and must not use this helper.
    """
    return pairs[:-1] if pairs and pairs[-1] == ("lastUpdate", "1") else pairs


def _valid_last_update(value: str) -> bool:
    try:
        return int(value) >= 0
    except ValueError:
        return False
