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

## Public-release boundary

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
