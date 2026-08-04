"""Move the self-hosted APK's save on and off the device.

The packaged Android build keeps its save in app-private storage, where none of
the workstation commands in `liminal_gate.account_state` can reach it: the app is
not debuggable, so `run-as` is unavailable, and `adb backup` stopped carrying app
data for release packages after Android 11.  The embedded server is already
listening on device loopback, so these commands drive its operator save routes
over an `adb forward` instead.

Export first, then treat everything else as reversible.  `export` is the only
command here that cannot lose anything.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time
from typing import Any
import urllib.error
import urllib.request

from liminal_gate import tester_setup
from liminal_gate.account_state import AccountStateError, read_document
from liminal_gate.on_device_setup import (
    DEFAULT_APK, DEFAULT_DATA, DEFAULT_HOST_SOURCE, DEFAULT_RESOURCES, LOOPBACK_PORT,
    OnDeviceSetupError, launch_apk, prepare_on_device_apk, validate_device,
)
from liminal_gate.save_validation import validate_document

STATE_ROUTE = "/local/state"
HEALTH_ROUTE = "/healthz"
BACKUP_DIRECTORY = "on-device-state"
# The app takes a moment to bind loopback after a launch, and the whole point of
# an import is that it happens around a restart.
READY_TIMEOUT_SECONDS = 60.0
READY_POLL_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 30.0


class OnDeviceStateError(RuntimeError):
    """The on-device save could not be read, replaced, or verified."""


class StateRouteUnavailable(OnDeviceStateError):
    """The installed build has no save-transfer route.

    Every build made before that route existed is in this state, including the
    one an operator must replace in order to get a build that has it.  `update`
    therefore has to be able to proceed past this, which is why it is a distinct
    type rather than a message.
    """


def _request(port: int, route: str, payload: bytes | None = None) -> dict[str, Any]:
    url = f"http://127.0.0.1:{port}{route}"
    request = urllib.request.Request(url, data=payload, method="POST" if payload is not None else "GET")
    if payload is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            body = response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", "replace").strip()
        if route == STATE_ROUTE and error.code in {404, 501}:
            raise StateRouteUnavailable(
                "the installed build has no save-transfer route, so its save cannot be reached. "
                "Builds made before this route existed are in that state."
            ) from error
        raise OnDeviceStateError(f"the app refused {route}: HTTP {error.code} {detail}") from error
    except (urllib.error.URLError, OSError) as error:
        raise OnDeviceStateError(
            f"could not reach the embedded server on {route}; open the app and wait for the game to appear ({error})"
        ) from error
    try:
        document = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OnDeviceStateError(f"the app answered {route} with data that is not JSON") from error
    if not isinstance(document, dict):
        raise OnDeviceStateError(f"the app answered {route} with an unexpected document")
    return document


def wait_for_health(port: int, timeout: float = READY_TIMEOUT_SECONDS) -> str:
    """Block until the embedded server answers, returning its build ID.

    Every command here confirms the health route first: a forward that reaches
    *something* is not evidence that it reached this app, and reading or
    replacing a save on the strength of an unidentified listener is exactly the
    mistake worth spending one request to avoid.
    """
    deadline = time.monotonic() + timeout
    last: OnDeviceStateError | None = None
    while True:
        try:
            document = _request(port, HEALTH_ROUTE)
        except OnDeviceStateError as error:
            last = error
            if time.monotonic() >= deadline:
                raise OnDeviceStateError(
                    f"the embedded server did not answer within {timeout:.0f}s. Open the app on the "
                    f"device and wait for the game to appear, then rerun. ({last})"
                ) from last
            time.sleep(READY_POLL_SECONDS)
            continue
        if document.get("service") != "project-liminal-gate" or document.get("status") != "ok":
            raise OnDeviceStateError(f"{HEALTH_ROUTE} answered, but not as this project's server: {document}")
        build_id = document.get("build_id")
        if not isinstance(build_id, str) or not build_id:
            raise OnDeviceStateError(f"{HEALTH_ROUTE} did not report a build ID")
        return build_id


def fetch_state(port: int) -> dict[str, Any]:
    document = _request(port, STATE_ROUTE)
    if not isinstance(document.get("accounts"), dict):
        raise OnDeviceStateError(
            f"the app answered {STATE_ROUTE} without a save. This build predates on-device save "
            f"transfer; rebuild and reinstall it before exporting."
        )
    return document


def push_state(port: int, document: dict[str, Any]) -> str | None:
    payload = (json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    result = _request(port, STATE_ROUTE, payload)
    if result.get("status") != "imported":
        raise OnDeviceStateError(f"the app did not confirm the import: {result}")
    active = result.get("active_account_id")
    return active if isinstance(active, str) else None


def describe(document: dict[str, Any]) -> str:
    accounts = document.get("accounts", {})
    active = document.get("active_account_id")
    return f"{len(accounts)} account(s), active {active or 'none'}"


def default_backup_path(data_directory: Path, build_id: str) -> Path:
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    return data_directory / BACKUP_DIRECTORY / f"{stamp}-{build_id[:12]}.json"


def write_backup(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, separators=(",", ":"), sort_keys=True) + "\n", encoding="utf-8")


def export_state(adb: str, device: str, data_directory: Path, output: Path | None) -> Path:
    with tester_setup.adb_forward(adb, device, LOOPBACK_PORT) as port:
        build_id = wait_for_health(port)
        document = fetch_state(port)
    destination = output if output is not None else default_backup_path(data_directory, build_id)
    write_backup(destination, document)
    print(f"Exported the on-device save: {destination}")
    print(f"  build {build_id}")
    print(f"  {describe(document)}")
    findings = [finding for finding in validate_document(document) if finding.severity == "error"]
    if findings:
        # Worth saying, never worth refusing: this is the copy that exists, and
        # a flawed backup still beats no backup.
        print(f"  note: {len(findings)} validation error(s) in the exported save; `account_state validate` lists them")
    return destination


def import_state(
    adb: str, device: str, source: Path, confirmed: bool, force: bool,
) -> int:
    if not confirmed:
        raise OnDeviceStateError("import requires --yes")
    _, edited = read_document(source)
    errors = [finding.as_dict() for finding in validate_document(edited) if finding.severity == "error"]
    if errors and not force:
        raise OnDeviceStateError(
            f"{source} breaks {len(errors)} invariant(s) and was not imported; run "
            f"`python3 -m liminal_gate.account_state validate {source}` to see them, or pass --force"
        )
    with tester_setup.adb_forward(adb, device, LOOPBACK_PORT) as port:
        wait_for_health(port)
        current = fetch_state(port)
        # An import missing an account the device holds is far more likely to be
        # the wrong file than an intended deletion. Same reasoning, and the same
        # escape hatch, as `account_state apply`.
        lost = sorted(set(current.get("accounts", {})) - set(edited["accounts"]))
        if lost and not force:
            raise OnDeviceStateError(
                f"{source} is missing account(s) {', '.join(lost)} that the device holds; "
                f"pass --force if that is intended"
            )
        print(f"Replacing the on-device save ({describe(current)}) with {source} ({describe(edited)}).")
        active = push_state(port, edited)
        print(f"Imported. The device kept its previous save beside the new one as state.json.bak.1.")
        # The running client is mid-session against the save that just went
        # away, so the restart is part of the import rather than advice after it.
        tester_setup.force_stop(adb, device)
        launch_apk(adb, device)
        wait_for_health(port)
        verified = fetch_state(port)
    if verified.get("active_account_id") != active:
        raise OnDeviceStateError(
            f"the app restarted on account {verified.get('active_account_id')}, not the imported "
            f"{active}. The previous save is still on the device as state.json.bak.1."
        )
    print(f"Verified after relaunch: {describe(verified)}")
    return 0


def _recovery_steps(backup: Path, device: str) -> str:
    return (
        f"\nThe installed app is signed with a different local key, so Android refused the update.\n"
        f"Your save is exported to {backup} and the install was left untouched.\n"
        f"\nTo continue, accepting that step 1 clears the app's data:\n"
        f"  1. python3 -m liminal_gate.on_device_setup --device {device} --replace-existing\n"
        f"  2. open the app, let it reach the title screen so it signs up, then close it\n"
        f"  3. python3 -m liminal_gate.on_device_state export --device {device} --output new-install.json\n"
        f"  4. read the new account id from new-install.json, then re-point your save at it:\n"
        f"     python3 -m liminal_gate.account_state adopt {backup} \\\n"
        f"       --from <your-account-id> --to <the-new-account-id> --yes\n"
        f"  5. python3 -m liminal_gate.on_device_state import --device {device} {backup} --yes\n"
        f"\nStep 4 matters: the client generates a new UUID when its data is cleared, and the\n"
        f"restored save has to name that UUID or the app opens as a new player.\n"
    )


def update(args: argparse.Namespace) -> int:
    adb = tester_setup.resolve_adb(args.adb)
    device = tester_setup.select_device(adb, args.device)
    validate_device(adb, device)
    backup: Path | None = None
    if tester_setup.package_installed(adb, device):
        launch_apk(adb, device)
        try:
            backup = export_state(adb, device, args.data_dir, None)
        except StateRouteUnavailable as error:
            # The first update onto a build that predates the route necessarily
            # lands here, and refusing outright would leave no way to ever
            # install a build that can be backed up. An in-place update over a
            # matching signature preserves app data on its own; the backup is
            # insurance against the paths that do not.
            if not args.allow_missing_backup:
                raise OnDeviceStateError(
                    f"{error} This update would proceed without a backup. An in-place update keeps "
                    f"the save on its own, and the build it installs can be exported afterwards, so "
                    f"rerun with --allow-missing-backup to accept that this one update is unprotected."
                ) from error
            print("Warning: the installed build cannot be exported, so this update has no backup.")
    else:
        print(f"{tester_setup.PACKAGE_NAME} is not installed on {device}; installing without a backup.")
    signed = prepare_on_device_apk(
        args.apk, args.resource_root, args.data_dir, args.host_source,
        args.build_tools, args.seed_state, args.dummy_dll_dir,
        args.disable_google_services,
    )
    print(f"Prepared private on-device APK: {signed}")
    try:
        tester_setup.install_apk(adb, device, signed, replace_existing=False, no_incremental=True)
    except tester_setup.TesterSetupError as error:
        if backup is None:
            raise
        print(_recovery_steps(backup, device))
        raise OnDeviceStateError(str(error)) from error
    launch_apk(adb, device)
    with tester_setup.adb_forward(adb, device, LOOPBACK_PORT) as port:
        wait_for_health(port)
        current = fetch_state(port)
    print(f"Installed and launched on {device}. The save survived the update: {describe(current)}")
    if backup is not None:
        before, _ = read_document(backup)
        expected = json.loads(before)
        missing = sorted(set(expected.get("accounts", {})) - set(current.get("accounts", {})))
        if missing:
            raise OnDeviceStateError(
                f"the updated install is missing account(s) {', '.join(missing)} that {backup} holds. "
                f"Import that file to restore them: python3 -m liminal_gate.on_device_state import "
                f"--device {device} {backup} --yes"
            )
        print(f"  backup retained: {backup}")
    return 0


def _add_connection_options(parser: argparse.ArgumentParser, *, defaults: bool) -> None:
    """Declare the options that name the device, on the parser and each command.

    They are accepted on both sides of the subcommand because every documented
    invocation writes them after it -- `export --device SERIAL` -- and argparse
    otherwise refuses that form with `unrecognized arguments`, which reads as a
    broken checkout rather than as a word order.  The per-command copies
    suppress their defaults so that omitting one there leaves whatever the
    parser before the subcommand parsed, instead of overwriting it with None.
    """
    def default(value: object) -> object:
        return value if defaults else argparse.SUPPRESS

    parser.add_argument("--adb", default=default("adb"))
    parser.add_argument(
        "--device", default=default(None),
        help="adb serial; required only when multiple devices are ready",
    )
    parser.add_argument("--data-dir", type=Path, default=default(DEFAULT_DATA))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="liminal_gate.on_device_state", description=__doc__)
    _add_connection_options(parser, defaults=True)
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="copy the on-device save to this computer")
    export_parser.add_argument("--output", type=Path, help="where to write it; defaults under the data directory")
    import_parser = subparsers.add_parser("import", help="replace the on-device save with a local file")
    import_parser.add_argument("source", type=Path)
    import_parser.add_argument("--yes", action="store_true")
    import_parser.add_argument("--force", action="store_true", help="import despite validation errors or a missing account")
    update_parser = subparsers.add_parser("update", help="back the save up, then rebuild and reinstall over it")
    update_parser.add_argument("--apk", type=Path, default=DEFAULT_APK)
    update_parser.add_argument("--resource-root", type=Path, default=DEFAULT_RESOURCES)
    update_parser.add_argument("--host-source", type=Path, default=DEFAULT_HOST_SOURCE)
    update_parser.add_argument("--build-tools", type=Path)
    update_parser.add_argument("--dummy-dll-dir", type=Path, default=tester_setup.DEFAULT_DUMMY_DLL)
    update_parser.add_argument("--seed-state", action="store_true", help="include the optional first-install-only seed state")
    update_parser.add_argument(
        "--allow-missing-backup", action="store_true",
        help="update even though the installed build predates the save-transfer route and cannot be exported",
    )
    update_parser.add_argument(
        "--disable-google-services", action="store_true",
        help="rebuild with the client's Google Play Services bind actions made unresolvable",
    )
    for command in (export_parser, import_parser, update_parser):
        _add_connection_options(command, defaults=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "update":
            return update(args)
        adb = tester_setup.resolve_adb(args.adb)
        device = tester_setup.select_device(adb, args.device)
        if args.command == "export":
            export_state(adb, device, args.data_dir, args.output)
            return 0
        return import_state(adb, device, args.source, args.yes, args.force)
    except (OnDeviceStateError, OnDeviceSetupError, AccountStateError, tester_setup.TesterSetupError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"on-device state: {error}") from error


if __name__ == "__main__":
    raise SystemExit(main())
