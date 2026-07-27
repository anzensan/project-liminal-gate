# Public Technical Findings

This file records only findings safe for the source-only public repository.
Private inputs, captures, account state, and original assets remain excluded.

## Client compatibility constants

- **Confirmed by static client analysis:** the final-major UI gate requires
  both platform versions to exceed 4.99. Evidence and ARM64 ranges are recorded
  in `liminal_gate/server_constants.py`.
- **Confirmed by static client analysis:** Hunting selectors read
  `metalHuntingList` and `huntingHuntingList`; the server derives both lists
  from the enabled catalog and account progress.
- **Confirmed by original-client observation and real-HTTP regressions:** the
  final client requests status before login with a rotated token. A single
  unclaimed migrated account can supply selector progress until login binds
  the client host; afterward, unrelated hosts receive no account-derived
  selector availability.
- **Confirmed by static client analysis and original-client observation:**
  advertised Metal rows also require matching `sp_ch_<chapter>` login flags.
  The server derives those flags from the same advertised rows; Hunting and
  Metal lists then rendered in the final client.
- **Local policy:** the country roster and large character/Companion box sizes
  are compatibility fixtures, not recovered production-service values.

## Account and mutation behavior

- **Confirmed by implementation and real-HTTP regression tests:** signup/login
  binds a source host to an account; rotated tokens follow that owner, and an
  unidentified host cannot inherit the active account.
- **Confirmed by restart tests:** accepted mutations and body-scoped replay
  responses persist atomically. A repeated request ID with a different body is
  evaluated as that distinct body.
- **Confirmed by a prior exact request capture and real-HTTP restart
  regression:** permanent Pact of Fate reuses the ordinary coin/Energy kinds
  with `luckType=true`. The bundled archive policy uses the corresponding
  Fellowship/Truth pool and level-plus-Luck duplicates. Its Luck increment and
  ceiling are explicit local policy, not recovered production odds.
- **Confirmed by a migrated-state transport regression:** original-client
  `chrdata` stores packed level/EXP values as integral JSON doubles. Pact draws
  now preserve those packed values and full roster records while returning the
  plain level expected by the draw callback. A resumed original client then
  completed a live Pact summon and the server recorded HTTP 200.
- **Confirmed by boundary tests:** request bodies larger than 4 MiB, negative
  lengths, and incomplete bodies fail before mutation.
- **Confirmed by deterministic collision and reload tests:** account restore,
  adoption, switching, and edited-save application create a durable safety copy
  before mutation. Same-second copies use exclusive creation and distinct
  suffixes, so no earlier copy is overwritten.
- **Confirmed by guided-setup regression:** a fresh active account no longer
  hides an older played account; the reversible switch preserves the displaced
  fresh save.

## Configuration and derived-data boundaries

- **Confirmed by parsed-launcher and TOML tests:** `--config` works by itself,
  remains mutually exclusive with individual flags, and every bundled-policy
  option requires a TOML boolean rather than accepting a truthy string, number,
  or array.
- **Confirmed by parser regressions:** routes using the final client's shared
  optional mutation trailer accept only the observed `lastUpdate=1`; other
  values remain visible to the exact form parser and are rejected.
- **Confirmed by provenance regressions:** story-outcome generation requires
  the native encounter map and character catalog to name the selected APK.
  Output retains the APK and derived-file hashes, native library and `dump.cs`
  hashes, optional baseline hash, tool identity, and verified/unverified
  calibration label.

## Public-release boundary

- **Confirmed by the 2026-07-27 follow-up run:** 417 tests passed with
  `ResourceWarning` promoted to error, including the generated-outcome
  real-HTTP settlement path and account-state reload checks.
- **Confirmed by release tests:** preflight scans generated-output directories
  rather than hiding them, while the repository audit rejects dirty state and
  prohibited path names anywhere in Git history.
- **Confirmed by the 2026-07-26 remediation run:** 287 tests passed with
  `ResourceWarning` promoted to error; a clean temporary source candidate
  passed preflight and repository-history audit.

## Unresolved

- Hunting rows render, but the selector can flash while showing a loading
  indicator. Live event diagnostics contained no corresponding resource
  request or 404, so the remaining boundary is client-side runtime evidence.
- The retired Tavern “Watch Video” controls are created by client UI and rely
  on the unavailable ad SDK. Removing them is an APK-patch boundary, not a
  server catalog flag.
- Original-client acceptance beyond Chapter 2-1 is not certified.
- Chapter 2-2 through Chapter 42, bundled Hunting availability, and other
  declared catalogs are local preservation policy unless a narrower finding
  explicitly says otherwise.
- Historical schedules, reward odds, social/multiplayer systems, and commerce
  remain unsupported or unknown.
