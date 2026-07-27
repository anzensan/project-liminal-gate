# Execution Plans

## 2026-07-27 persistent Linux systemd service

Status: completed 2026-07-27.

Objective: run the dedicated server-only path continuously as an unprivileged
system service, restart it after any unexpected exit, and start it automatically
during normal host boot.

Required proof:

1. The versioned unit runs `liminal_gate.server_setup` as the invoking
   unprivileged user, not the Android tester path and not root.
2. Only the checkout's `user-data` directory is writable under the unit's
   filesystem protections.
3. `systemd-analyze verify` and focused unit tests pass.
4. The installed service is both `active` and `enabled` for
   `multi-user.target`.
5. Killing the main process causes systemd to start a different PID
   automatically.
6. The recovered service returns the operator page and an exact
   hash-validated resource over both LAN and Tailscale paths.

Result:

- The generic template and one-line installer render the unit for the invoking
  checkout, user, group, and selected port.
- The first live installer attempt stopped before sudo because its temporary
  filename lacked a `.service` suffix. The installer now creates a valid unit
  filename; its focused regression and the corrected live run pass.
- A later portability pass caught a host systemd version rejecting quoted
  `WorkingDirectory` paths. The final installer rejects ambiguous checkout
  paths before sudo and renders compatible unquoted paths; live verification
  and installation pass.
- The public README, plan, and status describe the workflow without retaining
  the validation host's name, user, checkout path, or addresses.
- The installed unit was verified as `active`, `enabled`, and linked from
  `multi-user.target.wants`.
- A forced main-process failure caused systemd to record a restart and restore
  the listener under a different PID without intervention.
- After the final installer-driven restart, the service ran as the invoking
  unprivileged user with only the setup parent and bootstrap child in its
  cgroup. Systemd's security review reported exposure level `4.2 OK`.
- LAN and private-overlay requests both returned HTTP 200 and served the same
  hash-validated resource.
- The final combined warning-strict release suite passed 429 tests; compilation,
  diff checks, and clean-candidate publication audits also passed.
- No host reboot was performed. Boot behavior is proven to the systemd
  configuration boundary by the enabled unit state and exact
  `multi-user.target` symlink; an actual future boot remains the first
  end-to-end boot observation.

## 2026-07-27 dedicated server-only onboarding

Status: completed 2026-07-27.

Objective: provide one command that prepares and runs the standard compatibility
server on a separate machine without touching APK, Android SDK, ADB, Java,
signing, emulator, or device-discovery paths.

Writable scope:

- A dedicated server-only launcher and focused tests.
- The public command entry point and concise LAN deployment documentation.
- Status documentation after live dedicated-host validation.

Required proof:

1. Resource-root validation selects the final `data_u2017/android` directory.
2. Setup builds the hash-validated resource manifest and keeps durable account
   state beneath the selected data directory.
3. The launched bootstrap command enables every standard bundled policy and
   contains no Android preparation arguments.
4. Focused tests pass.
5. The command prepares a complete user-supplied resource set, starts the real
   server on a free LAN port, serves a live HTTP request, and leaves no process
   behind after the validation run.

Result:

- `python3 -m liminal_gate.server_setup` prepares and runs the standard server
  without an APK or Android tooling.
- 56 focused setup, resource, and client-setup regressions passed with
  `ResourceWarning` promoted to error; compilation and diff checks passed.
- A complete 11,806-file resource set produced 23,594 explicit resource
  mappings during live validation.
- One real process served the news route and an exact hash-validated resource
  over both LAN and private-overlay paths, then stopped cleanly with no listener
  or child process intended to remain.
- An approved subnet route let one client keep the LAN origin at home and reach
  that same origin through Tailscale while away; no dual-origin APK patch was
  required.

## 2026-07-27 full-review follow-up remediation

Status: completed 2026-07-27.

Objective: fix all seven findings from the 2026-07-27 full public-release
codebase review without expanding the supported protocol boundary.

Writable scope:

- `liminal_gate/` launcher, configuration, recovery, account-state, request
  parsing, and outcome-catalog code.
- Focused regression tests and public release documentation.

Forbidden scope:

- `input/`, APKs, original resources, raw captures, local `user-data/`, and
  private reference evidence.
- New gameplay behavior or historical-service claims.

Required proof:

1. A documented TOML-only launch works, while mixed TOML/flag launch remains
   rejected and every configuration boolean is type-safe.
2. Repeated account safety copies cannot overwrite one another, including
   same-second operations, and recovery offers a played account when the active
   account is a fresh reinstall.
3. Generated story-outcome catalogs reject cross-APK inputs and retain the
   source hashes and native-calibration status used to derive them.
4. Optional trailing `lastUpdate` fields are accepted only with the exact
   observed value `1`.
5. Parity and checkpoint documentation matches the implemented outcome
   ceilings and current validation boundary.
6. Focused regressions, the warning-strict full suite, compilation, diff
   checks, and clean-candidate preflight/history audit pass.

Result:

- All six proof items passed.
- 75 focused launcher, configuration, account, parser, and provenance tests
  passed with `ResourceWarning` promoted to error.
- The warning-strict full suite passed 417 tests in 86.348 seconds.
- Compilation and diff checks passed.
- A clean source candidate passed release preflight and repository-history
  audit.
- This work did not run a new canonical original-client path; the certified
  boundary remains Chapter 2-1.

## Public-release review remediation

Status: completed 2026-07-26.

Objective: fix every issue in the 2026-07-26 full codebase review without
regressing the current client-compatible path.

Required proof:

1. Unknown LAN hosts cannot inherit or mutate the active account, while normal
   signup/login, rotated-token, household, and legacy-save flows still work.
2. Mutation bodies are bounded and incomplete bodies fail explicitly.
3. Save editing clears every durable mutation replay cache when requested and
   validates all party/token shapes the server assumes.
4. Event logs exclude account identifiers and documentation lists their exact
   retained diagnostics.
5. Release gates inspect `build/`, `dist/`, dirty state, and prohibited paths in
   all Git history.
6. The browser editor never inserts user-supplied save values as unescaped
   HTML.
7. Compatibility, distribution, release, checkpoint, and endpoint documents
   agree with current implementation.
8. CI and the full local suite pass with `ResourceWarning` promoted to error.
9. The final diff contains no original material, generated user data, or
   unrelated changes.

Forbidden scope:

- APKs, original resources, raw captures, private account state, and
  `user-data/`.
- New protocol behavior not established by existing evidence.

Result:

- All nine proof items passed.
- The strict full suite passed 287 tests on Python 3.14.6.
- Compile, documentation-link, source preflight, current-history path, and
  clean-candidate repository audit checks passed.
- Ignored local `user-data/` and `build/` contents were neither modified nor
  copied into the clean candidate.
