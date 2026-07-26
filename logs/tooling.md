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
