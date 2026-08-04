# Codebase Overview

Orientation for contributors and coding agents. The README covers the tester
path; this file covers how the source is organized, how the pieces relate, and
the conventions the code follows. It describes structure, which changes slowly;
verify line-level detail against the code itself.

## What this is

A source-only local compatibility server for a retired mobile game client
(Android 5.5.7-170). One flat Python package, `liminal_gate/` (~84 modules,
stdlib-only at runtime; UnityPy is an optional extra for master-data import),
plus an Android host app under `android-host/`. Testers supply their own APK
and resources; importers derive local catalogs from them; the server replays
the confirmed protocol against durable per-account state.

## Directory map

| Path | Contents |
|---|---|
| `liminal_gate/` | The entire Python package, flat — no subpackages |
| `tests/` | `unittest` suite (97 files; feature-named, not module-named) |
| `docs/` | Tester and developer documentation (see index below) |
| `profiles/` | Bundled bootstrap profile JSON used by tests and the guided path |
| `protocol/` | Preserved wire-shape reference material |
| `android-host/` | Gradle project for the on-device (single-APK) deployment |
| `deploy/`, `scripts/` | systemd unit template and install script |
| `tools/` | `save-editor.html`, a standalone local save editor |
| `user-data/` | Untracked tester artifacts (downloads, catalogs, saves, keys) |

## The four data tiers

The package splits into tiers that flow strictly one direction:

1. **Frozen data tables — `*_data.py`.** Python literals transcribed from the
   reviewed client (e.g. `companion_master_data.py`, `job_unlock_data.py`,
   `trading_post_data.py`). Mostly pure tuples with zero functions; a few
   (`luck_data.py`, `daily_quest_data.py`, `event_flag_data.py`,
   `secondary_world_data.py`) also carry small policy functions.
2. **Catalog validators — `*_catalog.py`.** Each owns an error class, frozen
   dataclasses, a strict `load_<x>_catalog(path)` JSON/TOML validator, and
   usually a `build_bundled_<x>_policy()` that lifts the Tier-1 rows into the
   dataclass shape. The pairing is 1:1 (`job_catalog` ← `job_unlock_data`,
   `exchange_catalog` ← `trading_post_data`, and so on).
3. **Importers/generators — `*_importer.py`, `*_generator.py`.** Read the
   tester's own APK/resources and emit Tier-2-shaped JSON under recorded
   provenance. Foundations: `character_catalog_importer` and
   `battledata_importer` (UnityPy type-tree readers). Chapters 8–42 battle
   programs come from `native_encounter_importer` (ARM64/objdump); chapters
   2–7 from `scenario_encounter_importer` (MoonSharp decode). Both feed
   `story_outcome_generator`. `event_catalog_generator` joins battledata,
   the character catalog, and `event_manifest_data`.
4. **Runtime consumers.** `bootstrap_server.py` loads ~30 Tier-2 catalogs;
   `server.py` is the generic empty foundation server; `account_state.py`,
   `save_validation.py`, `on_device_state.py` handle save inspection and
   transfer.

## bootstrap_server.py (the 6,000-line core)

Three classes plus ~150 module-level helper functions:

- **`BootstrapState`** — the durable save plus all game logic: account
  binding, tutorial state machine, inbox/messages, exchange, companions,
  pact draws, battle start/clear settlement for hunting / world-map special /
  generic story, and atomic JSON persistence with rotated backups. Every
  mutation runs under `self.lock`, checks the per-account replay cache
  (keyed by requestID + body SHA-256), and ends with `_persist_locked()`.
  Methods named `*_locked` assume the lock is held.
- **`BootstrapHandler`** — routing. `do_GET` handles signup/time/status/
  login/userdata reads; `do_POST` runs the mutation pipeline
  (`_select_mutation` → `_resolve_mutation` → `_write_mutation_result`).
- **`BootstrapServer(ThreadingHTTPServer)`** — holds the loaded catalogs.

Free-function regions, in file order: profile schema and `load_profile`;
persistence primitives (`_lock_exclusive`, `_fsync_directory`,
`_parse_state_document`); battle/wallet/daily helpers; request-body parsers
(`_parse_*`, all pure `bytes -> parsed | None`); domain projection helpers
(messages, exchange, settlement validation); wire encoding (`_render`,
`_signed_json`); CLI (`parse_args`, `load_launch_config`, `build_server`,
`main`).

A route must be registered in four places that are not automatically
cross-checked: `MUTATION_ROUTE_NAMES`, the `_select_mutation` dispatch table,
`RESOLVED_MUTATION_KINDS` (if eagerly resolved), and every result string it
can return in `MUTATION_RESULT_STATUSES`. A result string missing from the
last one raises `KeyError` inside the request handler at runtime.

## The setup / device-tooling half

`tester_setup.py` is the hub (guided setup pipeline) and also a de-facto
library: `doctor.py`, `on_device_setup.py`, `on_device_state.py`, and
`setup_rehearsal.py` all import its adb wrappers, toolchain discovery,
keystore management, and resolver functions. Other members:

- `doctor.py` — environment survey; `--install-missing` drives `tool_install.py`
  (vendor downloads: JDK, Android SDK tools, NDK objdump, Il2CppDumper).
- `toolchain.py` — records/reapplies resolved tool locations
  (`user-data/toolchain.json`). Stdlib-only leaf, as is `setup_progress.py`.
- `apk_patcher.py`, `apk_signer.py`, `legacy_client_apk_plan.py`,
  `il2cpp_plan_generator.py` — hash-guarded APK plan generation/apply/sign.
- `on_device_setup.py` → `on_device_apk.py` — single-APK build: runs the
  tester pipeline, then Gradle over `android-host/`, then reassembles the
  APK (hand-written ZIP central-directory and Android binary-XML code lives
  in `on_device_apk.py`).
- `setup_rehearsal.py` — re-runs the real setup as a subprocess on a staged
  copy and compares outputs against a trusted run. It rehearses the
  separate-server path only, not the on-device path.
- `server_setup.py` — one-command server launch; also the systemd ExecStart.
- `release_preflight.py`, `release_audit.py` — public-source-boundary checks.

## Running tests and checks

```sh
.venv/bin/python -m unittest discover -s tests        # NOT pytest; ~160s, ~985 tests
python3 -m liminal_gate.release_preflight             # prohibited-material check
python3 -m liminal_gate.release_audit                 # releasability check
```

The unit suite fakes the IL2CPP dump, master-data import, catalog
derivations, and signing. After changing any of those, run
`setup_rehearsal` against real inputs (see `docs/setup-rehearsal.md`).
CI (`.github/workflows/ci.yml`) runs compileall + the suite + both release
checks on Python 3.11 and 3.13; nothing in CI runs Gradle.

## Conventions and invariants

- **Strict parsing; unknown behavior fails visibly.** Validators check exact
  key sets (`set(document) != required`) and exact error strings are asserted
  in tests — error messages are an operator-facing surface, not incidental.
- **Generated/loaded catalogs** carry `schema_version: 1` and
  `provenance: "user-supplied"`; file hashes participate in provenance
  chains, so byte-level output changes (even whitespace/indent) are
  behavioral changes.
- **Durability**: writes go through temp-file + `os.replace`; account state
  additionally fsyncs, takes an advisory file lock, and rotates `.bak.1–5`.
  The account document is an implicit dict schema (~30 string keys) with no
  dataclass — renaming a key invalidates existing saves.
- **Error classes**: data/catalog modules derive from `ValueError`;
  setup orchestrators derive from `RuntimeError`.
- **No TODO/FIXME markers anywhere.** Rationale lives in prose comments;
  deliberate policy decisions are documented where they are made.
- Version pins in `tool_install.py` are often load-bearing (Il2CppDumper
  v6.7.46 exit behavior, .NET roll-forward). Read the adjacent comment
  before bumping any pin.

## Gotchas when refactoring

- `tests/test_launch_config.py` **reads the source text** of
  `bootstrap_server.py` and regexes `args.*` usage out of
  `load_launch_config`/`main` — those two functions must stay in that file,
  in that order. It also cross-checks `tester_setup.server_arguments`
  against `server_setup` and the on-device runtime so policy flags cannot
  drift.
- Tests monkeypatch module attributes `liminal_gate.bootstrap_server.time`
  and `...bootstrap_server.random...` — functions calling `time.time()` or
  `random.SystemRandom()` cannot move out of that module without retargeting
  the patches.
- Underscore-prefixed names are not private in practice: `account_state.py`
  and `android_entrypoint.py` import `_lock_exclusive`/`_fsync_directory`
  from `bootstrap_server`, and several tests import `_`-named helpers.
- Test files are named by feature, not by module — ~23 different test files
  exercise `bootstrap_server.py`. Grep for the route or function name rather
  than guessing the test file.
- `BootstrapServer` is a `ThreadingHTTPServer`; correctness of every
  mutation depends on holding `BootstrapState.lock` for the whole body.

## Documentation index

Root: `README.md` (tester path) · `PROJECT_STATUS.md` (current phase and
issue log) · `PLANS.md` (design plans) · `PARITY_ROADMAP.md` ·
`COMPATIBILITY_SCOPE.md` · `RELEASE_SCOPE.md` · `DISTRIBUTION_ARCHITECTURE.md`
· `CHANGELOG.md` · `CONTRIBUTING.md` · `PUBLICATION_CHECKLIST.md`.

`docs/`: `developer-reference.md` (tools and modes beyond the tester path) ·
`reconstruction-architecture.md` (the pipeline in seven sentences) ·
`scope-and-status.md` · `server-protocol.md` · `advanced-configuration.md` ·
`setup-rehearsal.md` · `on-device-setup.md` · `saves.md` ·
`troubleshooting.md` · `findings.md` (reverse-engineering findings) — plus
setup guides (`install-tools.md`, `emulator.md`, `device-setup.md`,
`setup-manual.md`, `dedicated-server.md`).
