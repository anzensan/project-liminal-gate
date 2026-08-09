# Project Liminal Gate — agent notes

Read `OVERVIEW.md` first: it maps the package tiers, `bootstrap_server.py`
internals, the setup/tooling half, conventions, and refactoring gotchas.

## Commands

```sh
.venv/bin/python -m unittest discover -s tests   # test suite (unittest, NOT pytest; ~160s)
python3 -m liminal_gate.release_preflight        # before publishing changes
python3 -m liminal_gate.release_audit
```

## Hard rules

- Strict parsing is policy: unknown wire/document shapes must fail visibly,
  never be silently accepted. Tests assert exact error-message strings.
- Never make a new branch without checking with the user first.
- Generated catalog bytes are hashed into provenance chains — do not change
  output formatting (indent, key order) casually.
- The account state document is an implicit schema; renaming keys breaks
  existing user saves. Migrations must be explicit (see `_migrate_replay_keys`).
- `tests/test_launch_config.py` reads `bootstrap_server.py` source text and
  cross-checks server flags across three modules — check it after touching
  `load_launch_config`, `main`, `server_arguments`, or policy flags.
- No TODO/FIXME markers; explain rationale in prose comments instead.
- Version pins in `tool_install.py` are load-bearing; read adjacent comments
  before bumping.

Maintenance backlog from the 2026-08 review: `docs/maintenance-review-2026-08.md`.
