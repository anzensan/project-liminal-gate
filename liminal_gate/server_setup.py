"""Prepare and run only the compatibility server, without Android tooling."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

from liminal_gate.resource_catalog import ResourceCatalogError
from liminal_gate.resource_catalog_builder import build_resource_manifest, write_resource_manifest


class ServerSetupError(RuntimeError):
    """The server-only environment is incomplete or unsafe to launch."""


DEFAULT_RESOURCES = Path("local-input/resources/data_u2017/android")
DEFAULT_DATA = Path("user-data")
DEFAULT_PROFILE = Path("profiles/legacy-client-bootstrap.json")
REQUIRED_RESOURCE_CATEGORIES = (
    "BG",
    "BGM",
    "Banner",
    "BuddyImages",
    "BuddyThumbs",
    "Illust",
    "Pieces",
    "SE",
    "Scenario",
)
STANDARD_POLICY_FLAGS = (
    "--core-story",
    "--pacts",
    "--hunting",
    "--jobs",
    "--rebirth",
    "--status-items",
    "--companion-draw",
    "--companion-sale",
    "--companion-strengthen",
    "--companion-evolution",
    "--trading-post",
    "--drop-eligibility",
    "--achievements",
    "--summon-skills",
)


def resolve_resource_root(requested: Path) -> Path:
    """Find and validate the final data_u2017/android resource directory."""
    candidates = (
        requested,
        requested / "android",
        requested / "data_u2017" / "android",
        requested / "gdresources" / "data_u2017" / "android",
    )
    for candidate in candidates:
        if candidate.is_dir() and all(
            (candidate / category).is_dir() for category in REQUIRED_RESOURCE_CATEGORIES
        ):
            resolved = candidate.resolve()
            if resolved != requested.resolve():
                print(f"Using detected Android resource root: {resolved}")
            return resolved
    expected = "data_u2017/android containing " + ", ".join(REQUIRED_RESOURCE_CATEGORIES)
    if not requested.exists():
        raise ServerSetupError(f"resource path does not exist: {requested}; expected {expected}")
    missing = [
        category
        for category in REQUIRED_RESOURCE_CATEGORIES
        if not (requested / category).is_dir()
    ]
    raise ServerSetupError(
        "resource path is not the final Android resource folder; "
        f"expected {expected} (missing here: {', '.join(missing)})"
    )


def prepare_server(resource_root: Path, data_directory: Path) -> tuple[Path, Path, int]:
    """Build the hash-validated resource manifest needed by the server."""
    resolved_resources = resolve_resource_root(resource_root)
    resolved_data = data_directory.resolve()
    resolved_data.mkdir(parents=True, exist_ok=True)
    manifest = build_resource_manifest(resolved_resources)
    manifest_path = resolved_data / "resources.json"
    write_resource_manifest(manifest_path, manifest)
    return resolved_resources, resolved_data, len(manifest["resources"])


def server_arguments(
    resource_root: Path,
    data_directory: Path,
    host: str,
    port: int,
    profile: Path = DEFAULT_PROFILE,
) -> list[str]:
    """Build the standard server command without any client preparation."""
    return [
        sys.executable,
        "-m",
        "liminal_gate.bootstrap_server",
        "--profile",
        str(profile.resolve()),
        "--state-file",
        str(data_directory / "bootstrap-state.json"),
        "--host",
        host,
        "--port",
        str(port),
        "--event-log",
        str(data_directory / "events.jsonl"),
        "--resource-root",
        str(resource_root),
        "--resource-manifest",
        str(data_directory / "resources.json"),
        "--public-data-root",
        str(data_directory / "public_data"),
        *STANDARD_POLICY_FLAGS,
    ]


def run_server(arguments: Sequence[str]) -> None:
    """Run the compatibility server in the foreground and stop it cleanly."""
    process = subprocess.Popen(arguments, start_new_session=(os.name == "posix"))
    try:
        return_code = process.wait()
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        print("\nServer stopped.")
        return
    if return_code:
        raise subprocess.CalledProcessError(return_code, arguments)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resource-root", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="validate and hash resources without starting the server",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if not args.host or any(character.isspace() for character in args.host):
            raise ServerSetupError("--host must be a non-empty address with no spaces")
        if not 1 <= args.port <= 65535:
            raise ServerSetupError("--port must be an integer from 1 through 65535")
        resource_root, data_directory, resource_count = prepare_server(
            args.resource_root, args.data_dir
        )
        print(f"Prepared server resource manifest: {resource_count} mapped entries")
        print(f"Durable account state: {data_directory / 'bootstrap-state.json'}")
        if args.prepare_only:
            return 0
        print(
            f"Starting server on http://{args.host}:{args.port}; "
            "press Control-C to stop it."
        )
        run_server(
            server_arguments(
                resource_root,
                data_directory,
                args.host,
                args.port,
            )
        )
    except (OSError, ResourceCatalogError, ServerSetupError, subprocess.CalledProcessError) as error:
        raise SystemExit(f"server setup failed: {error}") from error
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
