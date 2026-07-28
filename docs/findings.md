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
- **Confirmed by static client analysis and original-client observation:**
  normal Special mode falls back to a fixed 50-entry client list when
  `specialQuestList` is empty. That list contains all Chapter 3000 Metal rows,
  so the former broad `sp_ch_3000` flag exposed them in Arena -> Special
  Quests. The server now supplies an explicit Special list and exact Metal
  section flags; the relaunched client showed the regular Metal row in Metal
  Zone and no Metal rows in Special Quests.
- **Confirmed by original-client observation and real-HTTP regressions:** the
  final client requests status before login with a rotated token. A single
  unclaimed migrated account can supply selector progress until login binds
  the client host; afterward, unrelated hosts receive no account-derived
  selector availability.
- **Confirmed by static client analysis and original-client observation:**
  advertised Metal rows also require matching `sp_ch_<chapter>-<section>`
  login flags.
  The server derives those flags from the same advertised rows; Hunting and
  Metal lists then rendered in the final client.
- **Confirmed by static client analysis:** Arena -> Special Quests reads the
  server `specialQuestList` and exact `sp_ch_<chapter>-<section>` flags.
  **Local policy:** after Chapter 3, the bundled server advertises recovered
  Chapter 3003-1 (*Money Money Time*) through the bounded Hunting transaction.
  Its permanent availability and 1,500 Coin ceiling are not recovered service
  behavior; Tower and Arena VS remain unsupported.
- **Confirmed by supplied final-APK analysis:** BattleData identifies Chapter
  3004-1 as *Crystal Road* (`クリスタルロード`): three battles and seven stamina.
  `UISpecialSelect` mode 7 reads `huntingHuntingList`, while the generic
  non-1000-series gate requires `sp_ch_3004-1`. **Local policy:** its bounded
  transaction accepts up to two Items from material IDs 1--17 and the
  Ticket/power-up IDs 50 and 53--56. The reference table's historical odds are
  not implemented or claimed; original-client acceptance is still unverified.
- **Confirmed by static client analysis, live transport, and original-client
  observation:** Strikes Back reads `descentHuntingList`. One folded tier-1 row
  per unlocked Chapter 8000--8007 family plus its matching chapter flag opens
  that family's five-tier card. Spinetrich Kino and Kraken Kino rendered for
  the current progress, and Chapter 8000-1 reached `start_quest` and loaded its
  battle resources.
- **Local policy:** the country roster and large character/Companion box sizes
  are compatibility fixtures, not recovered production-service values.
- **Local policy with confirmed client meter semantics:** a successful
  chapter-boundary clear in either ordinary core-story catalog writes
  `refillStartTime: 0.0`, the client's full-meter representation. The rule is
  replay- and restart-safe and excludes intermediate story stages, Hunting,
  events, and World Map Special; it is not a claim about historical rewards.

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
- **Confirmed by original-client transport observation and live acceptance:**
  a ticket-backed Metal Zone clear repeats the pre-entry Item 50 count even
  though the server has already committed that ticket at `start_quest`. The
  server records whether the ticket paid for entry, permits only that one stale
  slot at `clear_quest`, and keeps the lower durable count. The captured
  Companion 128 result then settled live with HTTP 200 without restoring the
  ticket.
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
- **Local policy with recovered static costs:** packaged Counter Descent
  Chapters 8000--8007 unlock permanently after local Chapter 5--12 gates.
  Their five tiers cost 5/10/15/15/15 stamina. No recovered base reward is
  granted, so clear accepts only a zero-base result and unchanged
  server-owned state.

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
- Strikes Back selector and Chapter 8000-1 fight entry are accepted by the
  original client. Its battle-clear callback and return to free roam remain
  unobserved; only the bounded real-HTTP regression has exercised that clear.
- The retired Tavern “Watch Video” controls are created by client UI and rely
  on the unavailable ad SDK. Removing them is an APK-patch boundary, not a
  server catalog flag.
- Original-client acceptance beyond Chapter 2-1 is not certified.
- Chapter 2-2 through Chapter 42, bundled Hunting availability, and other
  declared catalogs are local preservation policy unless a narrower finding
  explicitly says otherwise.
- Historical schedules, reward odds, social/multiplayer systems, and commerce
  remain unsupported or unknown.
