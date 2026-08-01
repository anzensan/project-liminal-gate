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

`link` is the two-device version of the same bookkeeping: instead of moving the
save onto a new UUID, it records the second device's UUID as an alias of an
existing account, so both devices sign in to one save. The wire protocol has no
account system at all — the silently stored device UUID is the only credential —
so this operator command is where "log in to my account from another device"
lives. `unlink` detaches the device again.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from liminal_gate.bootstrap_server import ACCOUNT_STATE_BACKUP_COUNT, _lock_exclusive
from liminal_gate.save_validation import validate_document


class AccountStateError(ValueError):
    """A local account save could not be read or safely changed."""


REPLAY_CACHE_FIELDS = (
    "tutorial_requests",
    "achievement_requests",
    "message_requests",
    "exchange_requests",
)


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
    aliases = document.get("account_aliases")
    hosts = document.get("client_hosts")
    return {
        "accountId": account_id,
        "active": account_id == document.get("active_account_id"),
        "username": account.get("username"),
        "phase": account.get("tutorial_phase"),
        "progressCode": userdata.get("progressCode"),
        "coins": userdata.get("coins"),
        "characters": len(roster) if isinstance(roster, list) else None,
        "boundTokens": sum(1 for value in document["tokens"].values() if value == account_id),
        # Which network address the account last identified itself from — the
        # discriminator that tells two otherwise-identical fresh signups apart.
        "clientHosts": sorted(
            host for host, owner in hosts.items() if owner == account_id
        ) if isinstance(hosts, dict) else [],
        "linkedDevices": sorted(
            device for device, owner in aliases.items() if owner == account_id
        ) if isinstance(aliases, dict) else [],
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
    basename = f"{state.name}.{label}.{timestamp()}.json"
    suffix = 0
    while True:
        preserved = state.with_name(basename if suffix == 0 else f"{basename}.{suffix}")
        try:
            with state.open("rb") as source, preserved.open("xb") as destination:
                while chunk := source.read(1024 * 1024):
                    destination.write(chunk)
                destination.flush()
                os.fsync(destination.fileno())
            directory = os.open(state.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            return preserved
        except FileExistsError:
            suffix += 1
        except BaseException:
            preserved.unlink(missing_ok=True)
            raise


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
        aliases = document.get("account_aliases")
        if isinstance(aliases, dict):
            # The moved save keeps its linked devices, and a target UUID that
            # was itself a linked device now names a real account instead — a
            # UUID may never be both, or the server refuses to load the save.
            aliases.pop(target_id, None)
            document["account_aliases"] = {
                device: target_id if account_id == source_id else account_id
                for device, account_id in aliases.items()
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


def link(state: Path, device_id: str, target_id: str, confirmed: bool, force: bool) -> dict[str, Any]:
    """Give a second device's UUID the save its owner already plays.

    The linked device has usually signed up already, into a fresh empty
    account: that throwaway is absorbed here, with the same played-progress
    guard `adopt` uses. Linking a UUID the server has never seen is also fine —
    the device's first signup then lands straight on the shared save.
    """
    if not confirmed:
        raise AccountStateError("link requires --yes")
    if device_id == target_id:
        raise AccountStateError("--device and --to are the same id; nothing to link")
    lock = acquire_lock(state)
    try:
        _, document = read_document(state)
        accounts = document["accounts"]
        aliases = document.get("account_aliases") if isinstance(document.get("account_aliases"), dict) else {}
        if target_id not in accounts:
            if target_id in aliases:
                raise AccountStateError(
                    f"{target_id} is itself a linked device of {aliases[target_id]}; link --to {aliases[target_id]} instead"
                )
            raise AccountStateError(f"no account {target_id} in {state}; run `inspect` to list them")
        absorbed = accounts.get(device_id)
        if absorbed is not None and summarize_account(device_id, absorbed, document)["played"] and not force:
            raise AccountStateError(
                f"account {device_id} has its own progress; pass --force to discard it, "
                f"or `adopt` it if it is the save you meant to keep"
            )
        preserved = preserve(state, "pre-link")
        accounts.pop(device_id, None)
        # Devices linked to the absorbed throwaway follow it to the shared
        # save, or their aliases would name an account that no longer exists.
        aliases = {
            device: target_id if account_id == device_id else account_id
            for device, account_id in aliases.items()
        }
        aliases[device_id] = target_id
        document["account_aliases"] = aliases
        # The linked device's client is the one holding these bindings, and it
        # is now playing the shared save.
        document["tokens"] = {
            token: target_id if account_id == device_id else account_id
            for token, account_id in document["tokens"].items()
        }
        if document.get("active_account_id") == device_id:
            document["active_account_id"] = target_id
        hosts = document.get("client_hosts")
        if isinstance(hosts, dict):
            document["client_hosts"] = {
                host: target_id if account_id == device_id else account_id
                for host, account_id in hosts.items()
            }
        encoded = (json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        write_document(state, encoded)
    finally:
        lock.close()
    return {
        "status": "linked",
        "device": device_id,
        "account": target_id,
        "discardedAccount": None if absorbed is None else device_id,
        "preservedPrimary": None if preserved is None else str(preserved.resolve()),
        **summarize(state),
    }


def unlink(state: Path, device_id: str, confirmed: bool) -> dict[str, Any]:
    """Detach a linked device so its UUID no longer opens the shared save.

    The device itself keeps sending the unlinked UUID, so its next login is
    refused until it clears the app's data (a fresh signup under a new UUID)
    or is linked or adopted again.
    """
    if not confirmed:
        raise AccountStateError("unlink requires --yes")
    lock = acquire_lock(state)
    try:
        _, document = read_document(state)
        aliases = document.get("account_aliases")
        if not isinstance(aliases, dict) or device_id not in aliases:
            raise AccountStateError(f"{device_id} is not a linked device; run `inspect` to list them")
        preserved = preserve(state, "pre-unlink")
        detached_from = aliases.pop(device_id)
        encoded = (json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        write_document(state, encoded)
    finally:
        lock.close()
    return {
        "status": "unlinked",
        "device": device_id,
        "account": detached_from,
        "preservedPrimary": None if preserved is None else str(preserved.resolve()),
        **summarize(state),
    }


def switch(state: Path, account_id: str, confirmed: bool) -> dict[str, Any]:
    """Put the client on a chosen save by swapping it with the active one.

    `adopt` moves a save onto another UUID and discards whatever was there,
    which is right for recovering from a reinstall and wrong for browsing.
    Choosing a save should be reversible, so this exchanges the two accounts
    instead: the chosen save takes the UUID the client currently sends, and the
    save being left takes the chosen account's old UUID. Nothing is destroyed,
    and switching back is the same command with the other ID.
    """
    if not confirmed:
        raise AccountStateError("switch requires --yes")
    lock = acquire_lock(state)
    try:
        _, document = read_document(state)
        accounts = document["accounts"]
        active_id = document.get("active_account_id")
        if account_id not in accounts:
            raise AccountStateError(f"no account {account_id} in {state}; run `inspect` to list them")
        if active_id is None:
            raise AccountStateError("no active account to switch away from; use `adopt` instead")
        if account_id == active_id:
            raise AccountStateError(f"account {account_id} is already the active one")
        preserved = preserve(state, "pre-switch")
        accounts[account_id], accounts[active_id] = accounts[active_id], accounts[account_id]
        # Tokens and hosts keep naming the UUID the client sends, which is
        # exactly what should now resolve to the chosen save. Nothing moves.
        encoded = (json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        write_document(state, encoded)
    finally:
        lock.close()
    return {
        "status": "switched",
        "nowActive": active_id,
        "swappedWith": account_id,
        "preservedPrimary": None if preserved is None else str(preserved.resolve()),
        **summarize(state),
    }


def validate(path: Path) -> dict[str, Any]:
    """Report every invariant an edited save breaks, without changing it."""
    _, document = read_document(path)
    findings = validate_document(document)
    errors = [finding for finding in findings if finding.severity == "error"]
    return {
        "status": "invalid" if errors else "valid",
        "path": str(path.resolve()),
        "errors": len(errors),
        "warnings": len(findings) - len(errors),
        "findings": [finding.as_dict() for finding in findings],
    }


def apply_edited(state: Path, source: Path, confirmed: bool, force: bool, clear_replay_cache: bool) -> dict[str, Any]:
    """Replace a save with an edited copy, but only one that still holds up.

    The edited file is validated before anything is touched, because the whole
    point of editing through a tool is that a broken save never reaches the
    client, where the symptom appears far from the cause.
    """
    if not confirmed:
        raise AccountStateError("apply requires --yes")
    source_data, edited = read_document(source)
    findings = validate_document(edited)
    errors = [finding.as_dict() for finding in findings if finding.severity == "error"]
    if errors and not force:
        raise AccountStateError(
            f"the edited save breaks {len(errors)} invariant(s) and was not applied; "
            f"run `validate {source}` to see them, or pass --force to apply it anyway"
        )
    lock = acquire_lock(state)
    try:
        _, current = read_document(state)
        # An edited file that has lost an account is far more likely to be the
        # wrong file than an intended deletion.
        lost = sorted(set(current["accounts"]) - set(edited["accounts"]))
        if lost and not force:
            raise AccountStateError(
                f"the edited save is missing account(s) {', '.join(lost)} that the current save has; "
                f"pass --force if that is intended"
            )
        if clear_replay_cache:
            for account in edited["accounts"].values():
                if isinstance(account, dict):
                    for field in REPLAY_CACHE_FIELDS:
                        account[field] = {}
        preserved = preserve(state, "pre-apply")
        encoded = (
            source_data if not clear_replay_cache
            else (json.dumps(edited, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        )
        write_document(state, encoded)
    finally:
        lock.close()
    return {
        "status": "applied",
        "source": str(source.resolve()),
        "appliedWithErrors": len(errors) if errors else 0,
        "clearedReplayCache": clear_replay_cache,
        "preservedPrimary": None if preserved is None else str(preserved.resolve()),
        "warnings": [finding.as_dict() for finding in findings if finding.severity == "warning"],
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
    link_parser = subparsers.add_parser("link", help="let a second device play an existing account")
    link_parser.add_argument("state", type=Path)
    link_parser.add_argument("--device", required=True, dest="device_id", help="the second device's UUID")
    link_parser.add_argument("--to", required=True, dest="target_id", help="the account both devices will play")
    link_parser.add_argument("--yes", action="store_true")
    link_parser.add_argument("--force", action="store_true", help="discard progress already on --device")
    unlink_parser = subparsers.add_parser("unlink", help="detach a linked device from its shared account")
    unlink_parser.add_argument("state", type=Path)
    unlink_parser.add_argument("--device", required=True, dest="device_id", help="the linked device's UUID")
    unlink_parser.add_argument("--yes", action="store_true")
    switch_parser = subparsers.add_parser("switch", help="put the client on a different saved account")
    switch_parser.add_argument("state", type=Path)
    switch_parser.add_argument("--account", required=True, dest="account_id", help="the account to play")
    switch_parser.add_argument("--yes", action="store_true")
    validate_parser = subparsers.add_parser("validate", help="check an edited save without changing anything")
    validate_parser.add_argument("state", type=Path)
    apply_parser = subparsers.add_parser("apply", help="replace the save with a validated edited copy")
    apply_parser.add_argument("state", type=Path)
    apply_parser.add_argument("source", type=Path, help="the edited save, as exported by the editor")
    apply_parser.add_argument("--yes", action="store_true")
    apply_parser.add_argument("--force", action="store_true", help="apply despite validation errors or a missing account")
    apply_parser.add_argument(
        "--clear-replay-cache", action="store_true",
        help="drop all cached mutation responses so a replayed request cannot return pre-edit values",
    )
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
        elif args.command == "link":
            result = link(args.state, args.device_id, args.target_id, args.yes, args.force)
        elif args.command == "unlink":
            result = unlink(args.state, args.device_id, args.yes)
        elif args.command == "switch":
            result = switch(args.state, args.account_id, args.yes)
        elif args.command == "validate":
            result = validate(args.state)
        elif args.command == "apply":
            result = apply_edited(args.state, args.source, args.yes, args.force, args.clear_replay_cache)
        else:
            result = adopt(args.state, args.source_id, args.target_id, args.yes, args.force)
    except (OSError, AccountStateError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if isinstance(result, dict) and result.get("status") == "invalid" else 0


if __name__ == "__main__":
    raise SystemExit(main())
