"""Build a local bootstrap profile from a user-owned transport capture."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from liminal_gate.bootstrap_server import PROFILE_SCHEMA_VERSION, ProfileError
from liminal_gate.input_importer import write_import_manifest


REQUIRED_ROLES = frozenset({"time", "status", "signup", "login", "userdata"})


def import_profile(
    capture: Path,
    output_directory: Path,
    routes: dict[str, str],
    response_salt: str,
    digest_start: int,
    digest_end: int,
) -> Path:
    """Generate a user-local compatibility profile without retaining captures."""
    if set(routes) != REQUIRED_ROLES or not all(path.startswith("/") for path in routes.values()):
        raise ProfileError("route mapping must define every bootstrap role with absolute paths")
    if len(set(routes.values())) != len(routes):
        raise ProfileError("bootstrap routes must be unique")
    records = _read_capture(capture)
    by_path: dict[str, dict[str, Any]] = {}
    for record in records:
        path = record.get("path")
        if isinstance(path, str) and path not in by_path:
            by_path[path] = record
    missing = sorted(path for path in routes.values() if path not in by_path)
    if missing:
        raise ProfileError(f"capture is missing bootstrap routes: {missing}")
    payloads = {role: _response_json(by_path[path]) for role, path in routes.items()}
    token = _extract_signup_token(by_path[routes["signup"]], payloads["signup"])
    account_binding = _derive_account_binding(
        by_path[routes["signup"]], payloads["signup"], by_path[routes["login"]]
    )
    responses = {
        "signup": _replace_token(_remove_digest(payloads["signup"]), token),
        "login": _replace_token(_remove_digest(payloads["login"]), token),
        "status": _replace_token(_remove_digest(payloads["status"]), token),
    }
    userdata_seed = _replace_token(_remove_digest(payloads["userdata"]), token)
    if not isinstance(userdata_seed, dict):
        raise ProfileError("captured userdata response must be an object")
    userdata_seed.pop("success", None)
    profile = {
        "schema_version": PROFILE_SCHEMA_VERSION,
        "routes": routes,
        "response_signing": {
            "algorithm": "md5-uppercase-slice",
            "salt": response_salt,
            "digest_start": digest_start,
            "digest_end": digest_end,
        },
        "account_binding": account_binding,
        "responses": responses,
        "userdata_seed": userdata_seed,
    }
    _validate_profile_shape(profile)
    return _write_profile(output_directory, profile)


def _read_capture(path: Path) -> list[dict[str, Any]]:
    try:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError("could not read JSONL capture") from error
    if not rows or not all(isinstance(row, dict) for row in rows):
        raise ProfileError("capture must contain JSON object records")
    return rows


def _response_json(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("response_status") != 200:
        raise ProfileError("captured bootstrap response must have status 200")
    body = record.get("response_body_utf8")
    if not isinstance(body, str):
        raise ProfileError("capture record is missing response_body_utf8")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise ProfileError("captured response body must be JSON") from error
    if not isinstance(payload, dict):
        raise ProfileError("captured response must be a JSON object")
    return payload


def _derive_account_binding(
    signup_record: dict[str, Any], signup_payload: dict[str, Any], login_record: dict[str, Any]
) -> dict[str, str]:
    for response_field, value in signup_payload.items():
        if not isinstance(value, str) or not value:
            continue
        query_name = _query_name_for_value(login_record, value)
        if query_name is not None:
            return {"signup_response_field": response_field, "login_query_field": query_name}
    raise ProfileError("could not derive account binding from signup and login capture")


def _query_name_for_value(record: dict[str, Any], expected: str) -> str | None:
    query = record.get("query")
    if not isinstance(query, list):
        return None
    for pair in query:
        if isinstance(pair, dict) and isinstance(pair.get("name"), str) and pair.get("value") == expected:
            return pair["name"]
    return None


def _extract_signup_token(record: dict[str, Any], payload: dict[str, Any]) -> str:
    query = record.get("query")
    if isinstance(query, list):
        for pair in query:
            if isinstance(pair, dict) and pair.get("name") == "otk" and isinstance(pair.get("value"), str) and pair["value"]:
                return pair["value"]
    token = payload.get("otk")
    if isinstance(token, str) and token:
        return token
    raise ProfileError("captured signup request or response must contain a nonempty otk")


def _remove_digest(payload: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(payload)
    value.pop("digest", None)
    return value


def _replace_token(value: Any, token: str) -> Any:
    if isinstance(value, str):
        return value.replace(token, "{otk}")
    if isinstance(value, list):
        return [_replace_token(item, token) for item in value]
    if isinstance(value, dict):
        return {key: _replace_token(item, token) for key, item in value.items()}
    return copy.deepcopy(value)


def _validate_profile_shape(profile: dict[str, Any]) -> None:
    signing = profile["response_signing"]
    if not isinstance(signing["salt"], str) or not signing["salt"]:
        raise ProfileError("response salt must be nonempty")
    if type(signing["digest_start"]) is not int or type(signing["digest_end"]) is not int:
        raise ProfileError("digest bounds must be integers")
    if not 0 <= signing["digest_start"] < signing["digest_end"] <= 32:
        raise ProfileError("digest bounds must fall inside an MD5 digest")


def _write_profile(output_directory: Path, profile: dict[str, Any]) -> Path:
    output_directory.mkdir(parents=True, exist_ok=True)
    output = output_directory / "liminal-gate-bootstrap-profile.json"
    # Reuse the atomic local manifest writer, then move its result to the
    # profile filename so a partial profile is never observable.
    temporary = write_import_manifest(output_directory, profile)
    temporary.replace(output)
    return output


def parse_route(value: str) -> tuple[str, str]:
    role, separator, path = value.partition("=")
    if separator != "=" or role not in REQUIRED_ROLES or not path.startswith("/"):
        raise argparse.ArgumentTypeError("routes use role=/absolute/path")
    return role, path


def parse_digest_range(value: str) -> tuple[int, int]:
    start, separator, end = value.partition(":")
    try:
        parsed = int(start), int(end)
    except ValueError as error:
        raise argparse.ArgumentTypeError("digest range uses start:end") from error
    if separator != ":":
        raise argparse.ArgumentTypeError("digest range uses start:end")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--route", action="append", required=True, type=parse_route)
    parser.add_argument("--response-salt", required=True)
    parser.add_argument("--digest-range", default="16:32", type=parse_digest_range)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    routes = dict(args.route)
    try:
        output = import_profile(
            args.capture,
            args.output_dir,
            routes,
            args.response_salt,
            *args.digest_range,
        )
    except (OSError, ProfileError) as error:
        raise SystemExit(f"bootstrap profile import failed: {error}") from error
    print(f"wrote local bootstrap profile: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
