from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
import unittest

from liminal_gate.release_audit import audit_release_repository


class ReleaseAuditTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_requires_independent_repository_but_allows_a_reviewed_remote(self) -> None:
        findings = audit_release_repository(self.root)
        self.assertIn(("repository", "not an independent Git repository"), [(f.subject, f.reason) for f in findings])
        self._git("init", "-b", "main")
        self._git("config", "user.name", "Release Test")
        self._git("config", "user.email", "release-test@example.invalid")
        (self.root / "README.md").write_text("public source\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "initial public source")
        self.assertEqual([], audit_release_repository(self.root))
        self._git("remote", "add", "origin", "https://example.invalid/public.git")
        self.assertEqual([], audit_release_repository(self.root))

    def test_rejects_dirty_worktree_and_prohibited_historical_paths(self) -> None:
        self._git("init", "-b", "main")
        self._git("config", "user.name", "Release Test")
        self._git("config", "user.email", "release-test@example.invalid")
        (self.root / "build").mkdir()
        prohibited = self.root / "build" / "client.apk"
        prohibited.write_bytes(b"private")
        self._git("add", "-f", "build/client.apk")
        self._git("commit", "-m", "unsafe history")
        prohibited.unlink()
        (self.root / "README.md").write_text("public source\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-m", "remove unsafe file")
        (self.root / "dirty.txt").write_text("not committed\n", encoding="utf-8")

        values = {
            (finding.subject, finding.reason)
            for finding in audit_release_repository(self.root)
        }

        self.assertIn(
            ("worktree", "repository has uncommitted or untracked files"), values
        )
        self.assertIn(
            (
                "build/client.apk",
                "prohibited file type: .apk appears in Git history",
            ),
            values,
        )

    def _git(self, *arguments: str) -> None:
        subprocess.run(("git", "-C", str(self.root), *arguments), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
