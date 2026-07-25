"""Inspect, snapshot, restore, and re-point a local account save.

The server retains the last committed states beside the save, but retaining
them is only half of a recovery story: this is the half a player actually uses.
Every command here refuses to touch a save a server still holds, and every
destructive one preserves the current file first.

`adopt` exists because an account is keyed by the client's device UUID. Clearing
the app's data or reinstalling gives the client a new UUID, so its login no
longer matches and it signs up into a new, empty account while the real save
sits in the same file, complete and unreachable. Re-pointing it is a local
bookkeeping change, not a protocol one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from liminal_gate.bootstrap_server import ACCOUNT_STATE_BACKUP_COUNT, _lock_exclusive


class AccountStateError(ValueError):
    """A local account save could not be read or safely changed."""


def read_document(path: Path) -> tuple[bytes, dict[str, Any]]:
    """Read one save and check only the structure these commands rely on."""
    data = path.read_bytes()
    try:
        document = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AccountStateError(f"invalid JSON in {path}: {error}") from error
    if (
        type(document) is not dict
        or type(document.get("accounts")) is not dict
        or type(document.get("tokens")) is not dict
        or (document.get("active_account_id") is not None and document["active_account_id"] not in document["accounts"])
    ):
        raise AccountStateError(f"invalid account-state root in {path}")
    return data, document


def summarize_account(account_id: str, account: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    userdata = account.get("userdata") if isinstance(account.get("userdata"), dict) else {}
    roster = userdata.get("chrdata")
    return {
        "accountId": account_id,
        "active": account_id == document.get("active_account_id"),
        "username": account.get("username"),
        "phase": account.get("tutorial_phase"),
        "progressCode": userdata.get("progressCode"),
        "coins": userdata.get("coins"),
        "characters": len(roster) if isinstance(roster, list) else None,
        "boundTokens": sum(1 for value in document["tokens"].values() if value == account_id),
        # A never-played account is the one `adopt` may safely replace.
        "played": account.get("tutorial_phase", "initial") != "initial" or bool(account.get("tutorial_requests")),
    }


def summarize(path: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path.resolve()), "exists": path.exists()}
    if not path.exists():
        return result
    try:
        data, document = read_document(path)
        result.update({
            "valid": True,
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "activeAccountId": document.get("active_account_id"),
            "accounts": [
                summarize_account(account_id, account, document)
                for account_id, account in sorted(document["accounts"].items())
            ],
        })
    except (OSError, AccountStateError, KeyError, TypeError) as error:
        result.update({"valid": False, "error": str(error)})
    return result


def candidates(state: Path) -> list[Path]:
    return [state] + [
        state.with_name(f"{state.name}.bak.{index}")
        for index in range(1, ACCOUNT_STATE_BACKUP_COUNT + 1)
    ]


def timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def acquire_lock(state: Path):
    """Refuse to change a save a running server still owns."""
    state.parent.mkdir(parents=True, exist_ok=True)
    stream = state.with_name(f".{state.name}.lock").open("a+b")
    try:
        _lock_exclusive(stream)
    except OSError as error:
        stream.close()
        raise AccountStateError(
            "account state is in use; stop the local server before changing it"
        ) from error
    return stream


def write_document(state: Path, data: bytes) -> None:
    """Publish a save the same way the server does, so a crash cannot tear it."""
    temporary = state.with_name(f".{state.name}.write.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, state)
        directory = os.open(state.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temporary.unlink(missing_ok=True)


def preserve(state: Path, label: str) -> Path | None:
    if not state.exists():
        return None
    preserved = state.with_name(f"{state.name}.{label}.{timestamp()}.json")
    shutil.copyfile(state, preserved)
    with preserved.open("rb") as stream:
        os.fsync(stream.fileno())
    return preserved


def snapshot(state: Path, destination: Path | None) -> dict[str, Any]:
    data, _ = read_document(state)
    target = destination or state.with_name(f"{state.name}.snapshot.{timestamp()}.json")
    if target.exists():
        raise AccountStateError(f"snapshot target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"status": "snapshot_created", "source": str(state), **summarize(target)}


def restore(state: Path, source: Path, confirmed: bool) -> dict[str, Any]:
    if not confirmed:
        raise AccountStateError("restore requires --yes")
    source_data, _ = read_document(source)
    lock = acquire_lock(state)
    try:
        preserved = preserve(state, "pre-restore")
        write_document(state, source_data)
    finally:
        lock.close()
    return {
        "status": "restored",
        "source": str(source.resolve()),
        "preservedPrimary": None if preserved is None else str(preserved.resolve()),
        **summarize(state),
    }


def adopt(state: Path, source_id: str, target_id: str, confirmed: bool, force: bool) -> dict[str, Any]:
    """Re-point a save at the UUID a reinstalled client now sends."""
    if not confirmed:
        raise AccountStateError("adopt requires --yes")
    if source_id == target_id:
        raise AccountStateError("--from and --to are the same account")
    lock = acquire_lock(state)
    try:
        _, document = read_document(state)
        accounts = document["accounts"]
        if source_id not in accounts:
            raise AccountStateError(f"no account {source_id} in {state}; run `inspect` to list them")
        replaced = accounts.get(target_id)
        if replaced is not None and summarize_account(target_id, replaced, document)["played"] and not force:
            raise AccountStateError(
                f"account {target_id} has its own progress; pass --force to discard it"
            )
        preserved = preserve(state, "pre-adopt")
        accounts[target_id] = accounts.pop(source_id)
        # A token still naming the old account would route to a save that no
        # longer exists.  The replaced account's tokens move too: the client
        # that owns them is the one now holding the adopted save.
        document["tokens"] = {
            token: target_id if account_id in (source_id, target_id) else account_id
            for token, account_id in document["tokens"].items()
        }
        if document.get("active_account_id") in (source_id, target_id, None):
            document["active_account_id"] = target_id
        hosts = document.get("client_hosts")
        if isinstance(hosts, dict):
            document["client_hosts"] = {
                host: target_id if account_id in (source_id, target_id) else account_id
                for host, account_id in hosts.items()
            }
        encoded = (json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        write_document(state, encoded)
    finally:
        lock.close()
    return {
        "status": "adopted",
        "from": source_id,
        "to": target_id,
        "discardedAccount": None if replaced is None else target_id,
        "preservedPrimary": None if preserved is None else str(preserved.resolve()),
        **summarize(state),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="liminal_gate.account_state", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    inspect_parser = subparsers.add_parser("inspect", help="show the save and every retained state")
    inspect_parser.add_argument("state", type=Path)
    snapshot_parser = subparsers.add_parser("snapshot", help="copy the save to a named file")
    snapshot_parser.add_argument("state", type=Path)
    snapshot_parser.add_argument("--output", type=Path)
    restore_parser = subparsers.add_parser("restore", help="replace the save with a retained state")
    restore_parser.add_argument("state", type=Path)
    restore_parser.add_argument("source", type=Path)
    restore_parser.add_argument("--yes", action="store_true")
    adopt_parser = subparsers.add_parser("adopt", help="re-point a save at a reinstalled client's UUID")
    adopt_parser.add_argument("state", type=Path)
    adopt_parser.add_argument("--from", dest="source_id", required=True)
    adopt_parser.add_argument("--to", dest="target_id", required=True)
    adopt_parser.add_argument("--yes", action="store_true")
    adopt_parser.add_argument("--force", action="store_true", help="discard progress already on --to")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "inspect":
            result: Any = [summarize(path) for path in candidates(args.state)]
        elif args.command == "snapshot":
            result = snapshot(args.state, args.output)
        elif args.command == "restore":
            result = restore(args.state, args.source, args.yes)
        else:
            result = adopt(args.state, args.source_id, args.target_id, args.yes, args.force)
    except (OSError, AccountStateError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
