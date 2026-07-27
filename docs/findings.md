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
- **Local policy:** the country roster and large character/Companion box sizes
  are compatibility fixtures, not recovered production-service values.

## Account and mutation behavior

- **Confirmed by implementation and real-HTTP regression tests:** signup/login
  binds a source host to an account; rotated tokens follow that owner, and an
  unidentified host cannot inherit the active account.
- **Confirmed by restart tests:** accepted mutations and body-scoped replay
  responses persist atomically. A repeated request ID with a different body is
  evaluated as that distinct body.
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

- Original-client acceptance beyond Chapter 2-1 is not certified.
- Chapter 2-2 through Chapter 42, bundled Hunting availability, and other
  declared catalogs are local preservation policy unless a narrower finding
  explicitly says otherwise.
- Historical schedules, reward odds, social/multiplayer systems, and commerce
  remain unsupported or unknown.
