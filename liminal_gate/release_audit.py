"""Audit that a proposed source release has its own clean Git boundary."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import subprocess

from liminal_gate.release_preflight import inspect_release_tree, prohibited_reason


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
    status = _git(root, "status", "--porcelain", "--untracked-files=all")
    if status:
        findings.append(ReleaseAuditFinding("worktree", "repository has uncommitted or untracked files"))
    objects = _git(root, "rev-list", "--objects", "--all")
    if objects is None:
        findings.append(ReleaseAuditFinding("history", "could not inspect repository object paths"))
        return findings
    unsafe_history: set[tuple[str, str]] = set()
    for line in objects.splitlines():
        _, separator, raw_path = line.partition(" ")
        if not separator or not raw_path:
            continue
        path = Path(raw_path)
        reason = prohibited_reason(path)
        if reason is not None:
            unsafe_history.add((raw_path, reason))
    findings.extend(
        ReleaseAuditFinding(path, f"{reason} appears in Git history")
        for path, reason in sorted(unsafe_history)
    )
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
