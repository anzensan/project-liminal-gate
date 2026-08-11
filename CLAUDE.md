# Project Liminal Gate — agent notes

Read `OVERVIEW.md` first: it maps the package tiers, `bootstrap_server.py`
internals, the setup/tooling half, conventions, and refactoring gotchas.

## Commands

```sh
.venv/bin/python -m unittest discover -s tests   # test suite (unittest, NOT pytest; ~21s)
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
- **The two deployments must always stay at feature parity.** The dedicated
  server and the all-in-one on-device package are the same server, and a change
  that reaches one must reach the other. They diverge silently because their
  inputs differ: the dedicated route takes operator flags and paths, while the
  on-device route bakes its configuration into `write_server_runtime` and its
  catalogs into the APK. A policy added to one launcher and not the other, or a
  catalog regenerated for one, is a bug that only some testers can see. Say
  which deployment every change needs — server restart, APK rebuild, or both.
- No TODO/FIXME markers; explain rationale in prose comments instead.
- Version pins in `tool_install.py` are load-bearing; read adjacent comments
  before bumping.

Maintenance backlog from the 2026-08 review: `docs/maintenance-review-2026-08.md`.
