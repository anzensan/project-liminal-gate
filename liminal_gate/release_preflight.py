"""Reject source-release trees that contain prohibited local material."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path


PROHIBITED_DIRECTORIES = frozenset({"input", "work", "extracted", "state", "user-data"})
PROHIBITED_SUFFIXES = frozenset({
    ".apk", ".apkm", ".apks", ".bin", ".bundle", ".ipa", ".mp3", ".ogg",
    ".png", ".unity3d", ".wav", ".webp", ".zip", ".7z",
})
IGNORED_DIRECTORIES = frozenset({".git", "__pycache__", "build", "dist"})


@dataclass(frozen=True)
class PreflightFinding:
    path: Path
    reason: str


def inspect_release_tree(root: Path) -> list[PreflightFinding]:
    """Return prohibited material found below a proposed source-release root."""
    findings: list[PreflightFinding] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRECTORIES for part in relative.parts):
            continue
        forbidden_directory = next(
            (part for part in relative.parts if part in PROHIBITED_DIRECTORIES), None
        )
        if forbidden_directory is not None:
            findings.append(PreflightFinding(relative, f"prohibited directory: {forbidden_directory}"))
            continue
        if path.is_file() and path.suffix.lower() in PROHIBITED_SUFFIXES:
            findings.append(PreflightFinding(relative, f"prohibited file type: {path.suffix.lower()}"))
    return findings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("."))
    return parser.parse_args()


def main() -> int:
    root = parse_args().root.resolve()
    findings = inspect_release_tree(root)
    if findings:
        for finding in findings:
            print(f"FAIL {finding.path}: {finding.reason}")
        return 1
    print(f"PASS {root}: no prohibited local material found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
