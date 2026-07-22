"""Audit that a proposed source release has its own clean Git boundary."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess

from liminal_gate.release_preflight import inspect_release_tree


@dataclass(frozen=True)
class ReleaseAuditFinding:
    subject: str
    reason: str


def audit_release_repository(root: Path) -> list[ReleaseAuditFinding]:
    """Check material preflight plus the minimum independent-Git requirement."""
    root = root.resolve()
    findings = [ReleaseAuditFinding(str(finding.path), finding.reason) for finding in inspect_release_tree(root)]
    top_level = _git(root, "rev-parse", "--show-toplevel")
    if top_level is None:
        return findings + [ReleaseAuditFinding("repository", "not an independent Git repository")]
    if Path(top_level).resolve() != root:
        findings.append(ReleaseAuditFinding("repository", "Git top-level is outside the proposed release root"))
        return findings
    if _git(root, "rev-parse", "--verify", "HEAD") is None:
        findings.append(ReleaseAuditFinding("history", "repository has no initial public-only commit"))
    return findings


def _git(root: Path, *arguments: str) -> str | None:
    completed = subprocess.run(
        ("git", "-C", str(root), *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("."))
    root = parser.parse_args().root.resolve()
    findings = audit_release_repository(root)
    if findings:
        for finding in findings:
            print(f"FAIL {finding.subject}: {finding.reason}")
        return 1
    print(f"PASS {root}: independent public-release repository passes boundary audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
