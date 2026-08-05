"""Audit that a proposed source release has its own clean Git boundary."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import subprocess

from liminal_gate.release_preflight import inspect_release_tree, prohibited_reason


@dataclass(frozen=True)
class ReleaseAuditFinding:
    subject: str
    reason: str


def audit_release_repository(
    root: Path, include_ignored: bool = False
) -> list[ReleaseAuditFinding]:
    """Check material preflight plus the minimum independent-Git requirement.

    Ignored, untracked material is left out of the on-disk sweep: this audit is
    about what a clone of the release carries, and Git omits exactly those
    paths from every clone.  Sweeping them anyway buried the findings that
    matter under thousands of lines about a working checkout's own local
    inputs.  Pass ``include_ignored`` to sweep the whole tree regardless, for a
    release handed over as a directory rather than as a clone.

    This narrows only the disk sweep.  A prohibited path that is *tracked* is
    still reported however `.gitignore` reads -- Git does not apply ignore
    rules to tracked files, so the query below cannot return one -- and the
    separate history scan below still refuses one that any reachable commit
    carries.  `release_preflight` remains the unconditional filesystem gate.
    """
    root = root.resolve()
    skip = None if include_ignored else _ignored_matcher(root)
    findings = [ReleaseAuditFinding(str(finding.path), finding.reason) for finding in inspect_release_tree(root, skip)]
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


def _ignored_matcher(root: Path) -> Callable[[Path], bool] | None:
    """Match the paths Git ignores, so the disk sweep can pass over them.

    `--others` restricts the listing to untracked paths, which is what makes
    this safe to skip: Git does not apply ignore rules to a tracked file, so a
    prohibited path that is committed can never appear here.  `--directory`
    collapses a wholly ignored directory to a single entry, so a local input
    tree costs one prefix rather than one entry per file.  A root that is not
    a repository yields no matcher at all and is swept in full.
    """
    listing = _git(
        root, "ls-files", "--others", "--ignored", "--exclude-standard", "--directory"
    )
    if listing is None:
        return None
    files: set[PurePosixPath] = set()
    directories: list[PurePosixPath] = []
    for line in listing.splitlines():
        if not line:
            continue
        if line.endswith("/"):
            directories.append(PurePosixPath(line.rstrip("/")))
        else:
            files.add(PurePosixPath(line))

    def ignored(relative: Path) -> bool:
        candidate = PurePosixPath(relative.as_posix())
        if candidate in files:
            return True
        return any(
            candidate == directory or directory in candidate.parents
            for directory in directories
        )

    return ignored


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
    parser.add_argument(
        "--include-ignored",
        action="store_true",
        help=(
            "sweep ignored, untracked material too, for a release handed over "
            "as a directory rather than as a clone"
        ),
    )
    arguments = parser.parse_args()
    root = arguments.root.resolve()
    findings = audit_release_repository(root, arguments.include_ignored)
    if findings:
        for finding in findings:
            print(f"FAIL {finding.subject}: {finding.reason}")
        return 1
    print(f"PASS {root}: independent public-release repository passes boundary audit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
