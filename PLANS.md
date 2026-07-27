# Execution Plans

## 2026-07-27 Metal and Special Quest selector ownership

Status: completed 2026-07-27.

Objective: keep all supported Chapter 3000 Metal rows in the Metal Zone
selector and prevent Arena -> Special Quests from inheriting the client's
built-in Metal fallback list.

Evidence boundary:

- The original client displays only Chapter 3000 sections 11--17 plus Dragon
  Road and Machine Road in Metal Zone.
- Arena -> Special Quests displays all Chapter 3000 Metal rows.
- Static client analysis confirms that Metal mode reads
  `metalHuntingList`, while normal Special mode reads `specialQuestList` and
  falls back to a fixed 50-entry client list when the server list is empty.
- That fixed list contains Chapter 3000 sections 1--7 and 11--17. The current
  broad `sp_ch_3000` login flag therefore opens every one of those fallback
  rows.

Required proof:

1. Metal Zone advertises both recovered Chapter 3000 ranges, 1--7 and 11--17,
   plus Dragon Road and Machine Road at the existing progress gates.
2. Every advertised Metal row receives its exact `sp_ch_<chapter>-<section>`
   flag; no broad Chapter 3000 flag is emitted.
3. The server always sends a nonempty, server-owned `specialQuestList`, using
   only validated local event-catalog stages when configured and a known,
   closed client entry when none are configured, so the 50-entry fallback
   cannot take ownership.
4. Every advertised row remains startable through the same bounded catalog.
5. Focused catalog and real-HTTP regressions, warning-strict full tests,
   clean-candidate release gates, deployment, and original-client selector
   confirmation pass before publication.

Result:

- The bundled Metal selector now advertises the regular sections 1--7 and All
  Hail the King sections 11--17, plus Dragon Road and Machine Road, at their
  existing local-policy progress gates.
- Login derives exact section flags for every advertised Metal row and no
  longer emits the broad `sp_ch_3000` flag.
- Status always supplies an explicit nonempty `specialQuestList`. A configured
  user-local event catalog owns that list; otherwise a recovered but closed
  client entry suppresses the built-in 50-entry fallback without exposing an
  unsupported quest.
- 61 focused catalog/runtime/HTTP tests and the full 436-test warning-strict
  suite passed; compilation and diff checks passed.
- The deployed service restarted through its configured recovery path and
  returned the expected lists and exact flags over real HTTP. After a full
  client relaunch, the tester confirmed that Metal Zone showed the regular row
  and Arena -> Special Quests no longer inherited the Metal rows.

## 2026-07-27 Metal Ticket clear reconciliation

Status: completed 2026-07-27.

Objective: settle the captured original-client Metal Zone 1 clear without
restoring the Item 50 ticket that the server already consumed at entry.

Evidence boundary:

- The private live capture reports Chapter 3000 section 11, 208066 EXP, one
  Companion 128 drop, no monsters/items/coins/summons, and a full roster.
- Every declared reward and wallet check passes. The sole mismatch is Item 50:
  durable state has 3 after entry while the clear repeats the client's
  pre-entry count of 4.

Required proof:

1. A ticket-backed Metal start records its entry choice durably.
2. Its clear may repeat exactly one already-consumed ticket while every other
   item slot and declared reward remains exact; settlement preserves the
   server's lower ticket count.
3. Stamina-fallback Metal and all non-Metal Hunting clears cannot use that
   reconciliation.
4. The captured retry shape settles after restart, replays without a second
   grant, and a different body cannot receive that cached success.
5. Focused HTTP regressions and the warning-strict release gates pass before
   deployment.

Result:

- A ticket-backed start now persists whether Item 50 or stamina paid for the
  entry. Stamina fallback and ordinary Hunting remain exact.
- Metal clear reconciliation permits only the one pre-entry ticket repeated by
  the final client. The durable, already-consumed balance remains authoritative;
  every other item slot and bounded reward must still match.
- A pre-fix active battle can use the same non-minting reconciliation once,
  allowing an interrupted live result to recover after the service upgrade.
- The exact captured clear settled on a temporary copy of the live save,
  replayed after reload, retained 3 tickets, and granted Companion 128 once.
- 48 focused Hunting/catalog/state tests and the full 436-test warning-strict
  suite passed; compilation and diff checks passed.
- After deployment, the original client retried the paused result successfully.
  The live server recorded HTTP 200, returned the account to free roam, retained
  3 tickets, and persisted exactly one additional Companion 128.

## 2026-07-27 resumed-account Huntland and Tavern compatibility

Status: completed 2026-07-27.

Objective: make the already-supported Hunting, Metal, and permanent Pact
policies visible and usable after a private-save migration without weakening
host ownership, replay, or durable-state boundaries.

Required proof:

1. A pre-login status request with a rotated token resolves a single migrated
   account or an already-owned client host, but not an unrelated host.
2. Every advertised Metal selector row has the matching client event flag.
3. Original-client packed floating-point roster records survive an ordinary or
   Fate Pact mutation without being replaced by the public test schema.
4. The captured permanent Fate form (`luckType=true`) applies level-plus-Luck
   duplicate behavior, charges once, and replays after restart.
5. Real HTTP regressions and the warning-strict release gates pass.

Result:

- Hunting and Metal selector availability is derived from the resumed
  account's progress before login; the original client displayed both lists.
- Metal rows receive only the event flags derived from the stages already
  advertised by the Hunting catalog.
- Permanent coin/Energy Fate requests use the corresponding
  Fellowship/Truth local-policy pools. New units begin with zero Luck;
  duplicates gain one local-policy level and 5.0 Luck without changing Skill
  Boost.
- Pact mutation now preserves original-client packed level/EXP values and
  full roster records. Same-body retries replay the committed result across a
  service restart.
- The resumed original client completed a Pact summon after deployment; the
  live event log records the repaired `/gd/do_slot` request as HTTP 200.
- The live server's four user-derived Pact banners return HTTP 200. No
  copyrighted image is included in the repository.
- The Hunting selector still has a client-side flashing/loading symptom. Live
  server diagnostics recorded no banner/resource request or 404 during the
  symptom, so no speculative server response was added.
- The warning-strict release suite passed 434 tests in 88.764 seconds;
  compilation and diff checks passed.

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
