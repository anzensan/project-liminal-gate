# Maintenance review — August 2026

Findings from a four-track review (server core, data/catalog modules,
setup/tooling, test suite) aimed at refactoring and cleanup without behavior
change. Baseline at review time: **983 tests, OK (5 skipped), ~160 s** via
`.venv/bin/python -m unittest discover -s tests`.

Line numbers were verified at review time and will drift; treat them as
starting points, not anchors.

## 1. Defects and near-defects found by inspection

These are worth fixing regardless of any refactoring.

- [x] **`_maxima` has drifted between generator and catalog.**
  `story_outcome_catalog.py:217` rejects leading-zero and non-positive IDs;
  the copy in `story_outcome_generator.py:707` does not, and the gap is only
  caught by the round-trip load at the end of `main` — *after* the file is
  written. Adopt the stricter rule in the generator so refusal happens
  pre-write.
- [x] **`native_encounter_importer` silently overwrites its output.**
  `scenario_encounter_importer` has a `--force` guard; the native importer's
  `main` (~`:502`) clobbers an existing file without one. Add `--force` for
  parity.
- [x] **`event_catalog_generator` docstring promises validation it skips.**
  It claims output "is validated by `load_event_catalog`" but never calls it
  (unlike `story_outcome_generator.py:794`, which round-trips its output).
  Add the one-line round-trip.
- [x] **`on_device_setup.py:492` hard-codes `"android-35"`** instead of using
  `tool_install.ANDROID_PLATFORM_API` (also consulted by `doctor.py`). Drift
  bug waiting for the next platform bump.
- [x] **`LOOPBACK_HOST`/`LOOPBACK_PORT` duplicated** in `on_device_setup.py:39`
  and `android_entrypoint.py:31` — the packaged APK breaks if they disagree
  and nothing enforces agreement. Single-source or add an equality test.
- [x] **`MUTATION_RESULT_STATUSES` gap is a runtime `KeyError`.** A result
  string returned by a state method but absent from the table crashes inside
  `_write_mutation_result` (`bootstrap_server.py:~3937`) instead of producing
  a response. Add a test asserting every dispatchable result string is in the
  table (or a defensive 500 with logging).
- [x] **`_bound_locked` hardcodes the four replay buckets**
  (`bootstrap_server.py:~3116`). Adding a fifth bucket silently makes it
  unbounded. Derive the list from one registry shared with the mutation
  helpers.
- [x] **`save_validation.FLOAT_FIELDS` (`:43`) is dead** while
  `_validate_floats` re-lists the same six names inline in three places —
  the constant and the code can drift apart unnoticed. Wire the constant in
  (behavior-preserving today) or delete it.
- [x] **`tests/test_on_device_state.py:178-182` hides coverage**: five
  inherited tests are replaced by `unittest.skip(...)(lambda: None)`; a new
  parent test would not be suppressed or reported. Replace with explicit
  per-method skips.
- [x] **`input_importer.py:35` defines `class ImportError(ValueError)`**,
  shadowing the builtin and forcing an alias at the `tester_setup` import
  site. Rename (e.g. `InputImportError`).

Possibly intentional (confirm before touching): `luck_data.py:62-64`
`LUCKY_*` constants and `event_flag_data.py:173` `KNOWN_EVENT_FLAGS` have zero
references — they read as recovered-but-unwired preservation data.

## 2. Quick wins — mechanical, low risk

- [x] **One `sha256_file`.** 12 near-identical definitions
  (`file_digests.py:27` is the natural home): `apk_patcher`, `input_importer`,
  `battledata_importer`, `character_catalog_importer`,
  `event_character_catalog`, `native_encounter_importer`, `on_device_apk`,
  `on_device_setup`, `setup_rehearsal`, plus private `_sha256_file` copies in
  `daily_quest_importer` and `resource_catalog`. Same semantics everywhere;
  fully mechanical.
- [x] **Shared inventory constants.** `BUNDLED_ITEM_SLOTS = 181` appears in
  11 modules (+ `save_validation.ITEM_SLOTS`), `BUNDLED_MAX_STACK = 999` in
  4 (+ `save_validation.MAX_ITEM_STACK`). Define once, re-export under the
  existing names so no test changes.
- [x] **Name the reviewed-profile string once.** `"terra-battle-android-5.5.7-170"`
  exists under three constant names and as bare literals inside validators at
  `story_outcome_catalog.py:126` and `story_progression_catalog.py:95` — the
  two spots most likely to drift if the pin ever changes. Same for
  `"assets/bin/Data/data.unity3d"` (three names) and the metadata member path.
- [x] **One atomic-write helper.** The temp-file + `os.replace` block is
  copied ~16×. Extract with an `indent` parameter preserving each site's
  current value — **do not unify indent**: generated-file bytes are hashed
  into provenance chains, so indent changes are behavioral (see §5).
  Note: all copies inherit `NamedTemporaryFile`'s 0600 mode on published
  files; a shared helper makes that fixable in one place if desired.
- [ ] **Shared `_read_json(path, what)`** — verbatim copies in
  `event_catalog_generator.py:55` / `story_outcome_generator.py:252`, variants
  in `setup_rehearsal.py:411` / `tester_setup.py:1282`.
- [x] **Collapse the triplicated row-emission block** in
  `event_catalog_generator.build_catalog` (archive/tower/eidolon,
  `:106/:138/:178`) — contained in one function, well tested.

## 3. Test-suite consolidation (the "ballooning" fix)

The suite is healthy where it counts — no real network, no ordering
dependencies, minimal mocking, per-test tempdirs. The bloat is 97 files with
**zero shared infrastructure**: no conftest/support module at all.

- [x] **Tier 1: create `tests/support.py`** with a server-lifecycle context
  manager plus `post`/`get`/`request` helpers, shared
  `PUBLIC_ROOT`/profile-loader constants, a `write_catalog(dir, name, doc)`
  helper, and an account-document builder with keyword overrides. Replaces:
  26 nested `start()` defs, 34 `post()` defs, 11 `request()` defs, 8
  `start_server/stop_server/restart` quartets, 111 shutdown triads, 49
  profile-path literals, 100 `write_text(json.dumps(...))` idioms, and 30
  hand-rolled account seeds. **~1,300–1,400 lines (~7% of the suite) with no
  assertion changes.** The account builder also removes a real schema-drift
  hazard (30 independent update sites today).
- [ ] **Tier 2: wall-clock.** ~140 real socket binds + thread spawns per run
  (`test_bootstrap_server`, `test_world_map_special` (20 binds),
  `test_hunting_runtime` (23) are the worst). Move read-mostly classes to
  `setUpClass`-scoped servers; keep per-test servers where tests `restart()`
  or exercise single-writer locking.
- [ ] **Tier 2: table-drive the copy-paste families** with `subTest`:
  the 12-file catalog-loader rejection template (~58 `assertRaises` methods),
  `test_world_map_special.py:216-296` claim-validation sextet,
  `test_trailing_last_update.py:40-72` (7 tests → 1 table).
- [ ] **Tier 3 (design first, higher risk):** the 12-file endpoint-family
  cluster (`test_add_job`, `test_companion_*`, `test_rebirth`, …) each
  re-tests the dispatch layer's replay/collision/restart triple through its
  own socket server — a shared assertion routine could halve those files,
  but each embeds endpoint-specific expectations; consolidate only with a
  genuinely expressive expectation model or coverage will silently thin.
  Also: `test_bootstrap_server.py:601` is one 557-line test method covering
  the whole declared account flow — splitting it converts one all-or-nothing
  failure into ~10 diagnosable ones.
- [ ] **Coverage gaps to close while consolidating** (modules no test imports
  by name): `companion_progression_data` (518 lines),
  `statusup_character_data` (366), `job_unlock_data` (308),
  `trading_post_data` (188), `companion_evolution_data` (173),
  `server_constants` (144), `setup_progress` (114), `companion_master_data`
  (102), `rebirth_recipe_data` (89), `data_manifest` (72).
- [ ] Optional: group `tests/` into subpackages (`catalog/`, `server/`,
  `setup/`) — zero code risk, touches CI paths, large discoverability win
  given 23 files target `bootstrap_server` under feature names.

## 4. Structural refactors (larger, do after §2–3)

### bootstrap_server.py decomposition, in dependency-safe order

1. [x] **Extract request parsers** (`_parse_*` block, ~740 lines, 37 pure
   functions) → `bootstrap_parsers.py`. Highest value, lowest risk.
2. [x] **Extract wire encoding** (`_render`, `_signed_json`,
   `_endpoint_refusal_envelope`, last-update helpers) → `bootstrap_wire.py`.
3. [x] **Extract profile schema/loading** (`ProfileError`, dataclasses,
   validators, `load_profile`) → `bootstrap_profile.py`, re-exporting
   `ProfileError`/`PROFILE_SCHEMA_VERSION` from `bootstrap_server` for the
   four existing external import sites.
4. [ ] **Replay-mutation helper.** The 26-site identical mutation prologue
   (lock → account lookup → replay-cache check) and 28-site epilogue (cache
   store → `_persist_locked`) are a textbook decorator/context manager;
   250–350 lines of boilerplate, and it makes the bucket registry explicit
   (fixes the `_bound_locked` item in §1).
5. [ ] **Route dispatch table.** Collapse `_select_mutation`'s 17-entry
   lambda table and derive `MUTATION_ROUTE_NAMES`/`RESOLVED_MUTATION_KINDS`
   from one `(route, kind, method, catalog)` registry instead of three
   hand-maintained constants.
6. [ ] Later, if ever: persistence/messages/settlement extraction and any
   `BootstrapState`/`BootstrapHandler` split — see constraints in §5; the
   state class must keep a single lock owner and the account-dict schema is
   load-bearing for existing saves.

### Setup half

- [ ] **Split `tester_setup.py` (1,814 lines) along its existing seams**, all
  already consumed as a library by other modules: adb/device orchestration
  (`:165-341`), host toolchain discovery (`:364-501`), keystore management
  (`:504-600`), Il2CppDumper integration (`:626-1147`, 522 lines — larger
  than most whole modules), catalog derivation (`:1175-1283`), preflight
  (`:1470-1622`). Keep re-exports so `doctor`/`on_device_*`/`setup_rehearsal`
  import sites don't all move at once.
- [x] **De-fork `resolve_resource_root`**: `server_setup.py:64` is a verbatim
  copy of `tester_setup.py:343` differing only in exception class; every
  other module already imports the `tester_setup` one.
- [x] **De-fork Gradle extraction**: `on_device_setup.ensure_gradle:110-155`
  re-implements `tool_install.extract`'s unsafe-path/exec-bit/long-path
  handling, minus the Windows long-path support — which is why the manual
  chmod repairs exist. Route through `tool_install`.
- [x] **Unify the three preflight frameworks** (`tester_setup`,
  `on_device_setup`, `doctor` each clone Check/probe/report; only one wraps
  long failure text).
- [ ] **Shared adb runner**: six raw `subprocess.run((adb, ...))` sites in
  `tester_setup` each hand-roll returncode/stderr handling;
  `on_device_setup._adb_shell` shows the wrapper works.
- [x] **Retire vestigial surface**: `choose_local_server_options(ask=…)` and
  the `LocalServerOptions` constant booleans removed 2026-08-04 with owner
  approval (see the execution record below); `prepare_local_tester
  (event_catalog=…)` kept (harmless guard); `tool_install._safe_tar_members`
  kept deliberately — it is live on interpreters older than 3.11.4, which
  Debian 12 ships.
- [x] **Fix the layering inversion**: `tester_setup.py:81` imports
  `DEFAULT_OUTCOME_CATALOG` from `server_setup` (client-build depending on
  server launcher for a filename); move such path constants
  (`bootstrap-state.json`, `resources.json`, `public_data`, ports…) to one
  constants module — five different default ports currently live in five
  files.

### Deliberately deferred

- **The ~15-clone catalog-loader template** (`load_x_catalog` five-step
  ritual): highest duplication volume, but the exact error strings are
  asserted by 12 test files and the strict shape checks are a deliberate
  anti-drift device. Consolidate last, if at all, with per-caller nouns
  preserving every message.
- **Splitting `BootstrapState`/`BootstrapHandler`** — see §5.

## 5. Constraints that make "don't break anything" concrete

- **`tests/test_launch_config.py` reads `bootstrap_server.py` source text**
  and slices it at `def load_launch_config(` / `def main(` — those functions
  must stay in that file, in that order, `main` last. It is also the drift
  guard comparing server flags across `tester_setup`/`server_setup`/on-device.
- **Monkeypatch targets pin module paths**: `...bootstrap_server.time.time`
  (`test_login_bonuses.py:90`, `test_daily_quests.py:425,604`) and
  `...bootstrap_server.random.SystemRandom.randrange`
  (`test_bootstrap_server.py:496,517,685`). Anything calling
  `time.time()`/`SystemRandom` (login, daily quests, gacha helpers) stays in
  `bootstrap_server` or the patches move with it.
- **Private names are public API**: `account_state.py:32` and
  `android_entrypoint.py:20` import `_lock_exclusive`/`_fsync_directory`/
  `ACCOUNT_STATE_BACKUP_COUNT`; six test modules import `_`-named helpers
  (`_clear_state_matches`, `_settlement_matches`, `_parse_generic_story_clear`,
  `_preserved_progress`, …).
- **Output bytes are provenance**: generated catalogs' SHA-256 feeds
  derivation-source records (`story_outcome_generator._native_source` etc.).
  Changing indent (currently an unexplained 1-vs-2 split across writers) or
  key order changes hashes.
- **Save-format compatibility**: the account document's ~30 string keys are
  scattered as literals across 2,400 lines with no schema object;
  `_migrate_replay_keys` is the only existing migration precedent. Backups
  cover corruption, not schema drift.
- **Threading**: every `BootstrapState` mutation must hold `self.lock` for
  its whole body; a split that breaks the discipline corrupts data silently
  (advisory file lock means overwrite, not error).
- **Untested danger zones — don't refactor without adding tests first**:
  `on_device_setup.py` (0.20 test ratio; `resolve_gradle_java_home` has
  zero tests), `on_device_apk.py` internals (hand-written ZIP central
  directory + binary-XML parsing, 27 private functions), `tool_install.py`
  (no dedicated test file; `install_command_line_tools`, `_restore_zip_modes`
  untested), the Windows `msvcrt` locking branch (`pragma: no cover`), and
  the whole on-device path is outside `setup_rehearsal`'s coverage.

## 6. Execution record (2026-08-03)

The checked items above were executed in one maintenance pass; the suite was
green (unittest discover) after every commit. Items examined and deliberately
**not** executed, with the reasoning:

- **`_safe_tar_members`.** Kept permanently: the tarfile `filter="data"`
  parameter is absent from 3.11.0–3.11.3, and Debian 12 pins Python 3.11.2,
  so the fallback is live for stock Debian testers. The review's
  "effectively unreachable" assessment was wrong.
- **`choose_local_server_options(ask=…)` and the `LocalServerOptions`
  booleans** were initially deferred as documented author decisions, then
  executed on 2026-08-04 with owner approval: the `ask` compatibility
  argument is removed (its no-prompt guarantee is now asserted by patching
  `builtins.input` in tests), and all three launchers derive their policy
  sets from `server_config.STANDARD_POLICY_FLAGS` — turning the drift class
  the launch-config test was built to catch into something that cannot be
  expressed. The structural test now derives the policy universe from
  `ServerConfig`'s boolean fields, so a new server policy must be made
  standard, deliberately off, or exempted with a reason.
- **Shared adb runner.** On inspection the six call sites share only the
  `(adb, "-s", device, …)` prefix; their error handling is deliberately
  different per command (probe vs check=True vs pattern-match-and-retry).
  A wrapper would add indirection without removing real duplication.
- **Catalog-loader template and its rejection-test table-driving; the
  `test_world_map_special` claim table.** The exact error strings and the
  individually named tests function as the project's spec language; the
  strict repeated shape is a deliberate anti-drift device. Consolidation
  would save lines and lose failure granularity/spec value.
- **`_read_json` consolidation.** The four variants differ in error class and
  message per module; a parameterized-exception helper is not clearly better
  than four honest five-liners.
- **`setUpClass`-scoped servers.** Blocked on a real design gap: every
  runtime test seeds accounts into a durable `BootstrapState`, so a shared
  server shares save state across tests. A safe conversion needs a per-test
  state reset (plausibly via `replace_document`) — new server surface, not a
  test cleanup. Designed follow-up.
- **Tier-3 endpoint-family merge and the 557-line flow-test split.** Both
  risk silently thinning coverage without an expectation model that does not
  exist yet; deferred by their own risk notes.
- **New tests for the ten untested data modules.** Deferred per standing
  instruction not to add unrequested test scripts; the list in §3 stands as
  the follow-up inventory.
- **`sha256_file` in `on_device_apk.py` and `resource_catalog.py`.** Kept:
  the former is deliberately decoupled from the package (duck-typed assembly
  module), the latter wraps its own stream-hasher that also serves zip
  members.
- **doctor's preflight variant.** Its survey/report operates on a different
  vocabulary (`ToolStatus`) with install semantics; only the
  tester/on-device pair were true clones and those now share one reporter.

Still open from §4: the replay-mutation helper (26+28 boilerplate sites) and
the route dispatch registry. Both modify `BootstrapState` mutation bodies —
the highest-consequence code in the repo — and deserve their own reviewed
pass now that the parser/wire/profile seams are out.

## 7. Suggested sequencing

1. §1 defect fixes (each small, each testable) — then full suite + preflight.
2. §3 Tier 1 test support module — biggest single cleanup, zero behavior risk,
   and it makes every later change cheaper to verify.
3. §2 quick wins (shared hashing/constants/atomic-write), one commit each.
4. §3 Tier 2 (server scope + table-driving).
5. §4 structural extractions, one seam per commit, suite green between each;
   run `setup_rehearsal` after anything touching the derivation pipeline.
