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

    def _git(self, *arguments: str) -> None:
        subprocess.run(("git", "-C", str(self.root), *arguments), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
