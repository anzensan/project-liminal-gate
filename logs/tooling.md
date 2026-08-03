# Tooling Log

## 2026-07-26 public-release remediation

- Host: Darwin 25.5.0 arm64
- Python: 3.14.6
- Git: 2.39.5 (Apple Git-154)
- Compile: `python3 -m compileall -q liminal_gate tests`
- Strict tests:
  `PYTHONWARNINGS='error::ResourceWarning' python3 -m unittest discover -s tests -v`
- Release checks: `python3 -m liminal_gate.release_preflight` and
  `python3 -m liminal_gate.release_audit`
- Result: 287 tests passed; clean temporary source candidate passed both
  release checks.

CI separately targets Python 3.11 and 3.13 on Ubuntu.

## 2026-08-02 doctor-managed AArch64 disassembler

- Host: Darwin arm64
- Pinned package: Android NDK r27d, `ndk;27.3.13750724`
- Package availability check: the installed Google `sdkmanager --list` reported
  `ndk;27.3.13750724` as available.
- Focused warning-strict tests:
  `PYTHONWARNINGS='error::ResourceWarning' python3 -m unittest -v tests.test_doctor tests.test_toolchain tests.test_setup_story_drops tests.test_tester_preflight`
- Complete warning-strict tests:
  `PYTHONWARNINGS='error::ResourceWarning' python3 -m unittest discover -s tests -v`
- Result: 113 focused tests and all 897 tests passed. A POSIX NDK-layout fixture
  executed the same `--version` AArch64 probe used by guided setup. The current
  host's existing Apple `objdump` also passed the live survey. Compilation and
  diff hygiene passed; a clean committed candidate passed both
  `liminal_gate.release_preflight` and the independent
  `liminal_gate.release_audit`.
- Deliberate boundary: no real NDK package was installed during validation.
  The doctor refuses to accept Google's Android SDK licence without the
  tester's explicit confirmation; package retrieval and repository verification
  remain delegated to Google's `sdkmanager`.
