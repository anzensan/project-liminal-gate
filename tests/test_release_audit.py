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

    def _public_repository(self) -> None:
        self._git("init", "-b", "main")
        self._git("config", "user.name", "Release Test")
        self._git("config", "user.email", "release-test@example.invalid")
        (self.root / "README.md").write_text("public source\n", encoding="utf-8")
        self._git("add", "README.md")
        self._git("commit", "-m", "initial public source")

    def test_ignored_local_material_is_not_swept(self) -> None:
        """A clone cannot carry an ignored file, so the audit does not read one.

        A working checkout keeps its local inputs beside the source, and
        sweeping them buried the boundary findings this audit exists to report
        under thousands of lines about material no release was ever going to
        carry.
        """
        self._public_repository()
        (self.root / ".gitignore").write_text("local-input/\nuser-data/\n", encoding="utf-8")
        self._git("add", ".gitignore")
        self._git("commit", "-m", "ignore local inputs")
        (self.root / "local-input").mkdir()
        (self.root / "local-input" / "client.apk").write_bytes(b"private")
        (self.root / "user-data").mkdir()
        (self.root / "user-data" / "state.json").write_text("{}", encoding="utf-8")

        self.assertEqual([], audit_release_repository(self.root))

    def test_ignoring_does_not_excuse_tracked_or_committed_material(self) -> None:
        """Ignore rules must not become a way to smuggle a file into a release.

        Git does not apply ignore rules to a file it already tracks, so a
        committed `.apk` stays visible however `.gitignore` reads -- on disk
        while it is tracked, and in history once it is deleted.
        """
        self._public_repository()
        (self.root / ".gitignore").write_text("build/\n", encoding="utf-8")
        (self.root / "build").mkdir()
        (self.root / "build" / "client.apk").write_bytes(b"private")
        self._git("add", "-f", "build/client.apk")
        self._git("add", ".gitignore")
        self._git("commit", "-m", "tracked despite the ignore rule")

        values = {
            (finding.subject, finding.reason)
            for finding in audit_release_repository(self.root)
        }

        # On disk, because the ignore rule does not reach a tracked file.
        self.assertIn(("build/client.apk", "prohibited file type: .apk"), values)
        # And in history, which no ignore rule has ever governed.
        self.assertIn(
            ("build/client.apk", "prohibited file type: .apk appears in Git history"),
            values,
        )

    def test_include_ignored_restores_the_whole_disk_sweep(self) -> None:
        """A release handed over as a directory carries whatever is on disk."""
        self._public_repository()
        (self.root / ".gitignore").write_text("local-input/\n", encoding="utf-8")
        self._git("add", ".gitignore")
        self._git("commit", "-m", "ignore local inputs")
        (self.root / "local-input").mkdir()
        (self.root / "local-input" / "client.apk").write_bytes(b"private")

        self.assertEqual([], audit_release_repository(self.root))
        values = {
            (finding.subject, finding.reason)
            for finding in audit_release_repository(self.root, include_ignored=True)
        }
        self.assertIn(
            ("local-input/client.apk", "prohibited file type: .apk"), values
        )

    def test_a_root_that_is_no_repository_is_still_swept_in_full(self) -> None:
        """Nothing is proven ignored without a repository to ask."""
        (self.root / "client.apk").write_bytes(b"private")

        values = {
            (finding.subject, finding.reason)
            for finding in audit_release_repository(self.root)
        }

        self.assertIn(("client.apk", "prohibited file type: .apk"), values)
        self.assertIn(("repository", "not an independent Git repository"), values)

    def _git(self, *arguments: str) -> None:
        subprocess.run(("git", "-C", str(self.root), *arguments), check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
