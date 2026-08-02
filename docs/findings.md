# Public Technical Findings

This file records only findings safe for the source-only public repository.
Private inputs, captures, account state, and original assets remain excluded.

## Chapter ticket presents

- **Confirmed local gap and retail-backed correction:** the retained Chapter
  8-9 account had read Chapter 5 Item 50 x2 and Chapter 6 Item 112 x3 messages,
  but no Chapter 7 message and zero of both ticket balances. Retail
  documentation records Metal Ticket x2 after Chapters 5 and 7 and Companion
  Ticket x3/x3/x4 after Chapters 6, 8, and 10. The guided core-story path now
  creates each eligible inbox message once, backfills a missed milestone on
  login, and retains a separate issued sentinel after inbox deletion. Exact
  client item IDs and limits are Confirmed; milestone quantities are
  community-documented historical behavior. Sources checked 2026-07-31:
  [Metal Ticket](https://terrabattle.fandom.com/wiki/Metal_Ticket) and
  [Companion Ticket](https://terrabattle.fandom.com/wiki/Companion_Ticket).

## First tutorial Pact outcome

- **Confirmed transport and existing client boundary:** the surviving client
  sends the exact ordered `kind=10&count=1&luckType=false&campaignChrID=0&`
  `eventFlag=0&lastUpdate=1` form after initial userdata. The Grace result shape
  and continuation are client-confirmed.
- **Maintainer-supplied retail behavior:** the first pull was an equal Bahl or
  Grace choice. The operator's private derived name catalog identifies Bahl as
  character 1 and Grace as character 3; no private catalog is committed. The
  public repository does not yet contain independent raw retail responses for
  both outcomes.
- **Confirmed executable behavior:** the bundled profile declares two positive
  weight-1 outcomes. The handler selects only after phase validation, then
  atomically persists the starter, roster/team delta, canonical response, and
  body-scoped replay entry. Forced real-HTTP tests cover both sides; Bahl
  survives restart, replays byte-for-byte without rerolling, continues to the
  A'misandra result with team `[1, 25]`, and settles the following tutorial save
  without minting or referencing Grace. Thirty-two focused tests and the full
  641-test warning-strict suite passed.
- **Compatibility boundary:** later tutorial templates resolve their starter
  slot from durable state, while a legacy state with no starter field resolves
  to Grace because the earlier server could produce no other result. A clean
  original-client Bahl run through the tutorial remains pending. In particular,
  the later Chapter 1-2 callback currently applies the captured starter packed
  level/EXP projection with the durable starter ID; Bahl-specific packed
  progression has not been independently captured.

## Quest settlement compatibility

- **Confirmed by exact final-client Chapter 2004-1 transport:** Jade Dragon's
  result reports variable battle Coins independently of the generated event
  catalog's fixed clear increment. The preserved 17,795-byte form has SHA-256
  `1d58ffb61f94ccbc1acd10620616b0d6aec8acbc5dc697888bd84b32ba421b3f`,
  reports 819 battle Coins and 6,851 EXP, and uses `itmp0=-1`. After a clean
  login, the client submitted a wallet of 11,824, exactly the durable 11,005
  plus those 819 Coins; the earlier 12,124 wallet was stale and remained
  correctly refused.
- **Confirmed client acceptance and durable behavior:** after deployment, the
  maintainer retried the retained result. The bounded settlement returned HTTP
  200, the client exited the result screen, and no further network error was
  shown. The save returned to `free_roam` with no active quest, 11,824 Coins,
  27 free Energy, 78 characters including one Jade Dragon (673), and the
  submitted items. Its
  SHA-256 remained byte-identical across a service restart. A real-HTTP
  regression covers stale-wallet and below-`-1` sentinel refusal, successful
  settlement, immediate replay, and restart replay.
- **Remaining evidence boundary:** Chapter 2004-1 proves one final-client event
  result shape, not the retired service's fixed rewards, random drops, or
  schedules. The generated fixed clear-Coin increment remains zero because no
  such increment is present in BattleData; other Archive families still need
  their own client result observations.
- **Confirmed by Issue 25 final-client/server evidence:** a Pixel 7 Pro running
  the final client reported 1,800 Coins after Chapter 3003-1. The
  privacy-filtered attachment has SHA-256
  `c8f338759172437f93cedf89623550354c2919ad6ca2db0f5373cb3d3689518d`;
  its 53 rejoined JSON records contain 34 HTTP 409
  `invalid_local_hunting_result` responses for that exact result and 19 later
  HTTP 409 `tutorial_state_conflict` responses, all in `hunting_active`.
- **Confirmed implementation cause and recovery:** the bundled local ceiling
  was 1,500, so the clear was rejected without mutation and the active
  operation correctly survived restart. That durability made every unrelated
  stage start fail until the original result could settle. The bounded policy
  now accepts the observed 1,800 and refuses 1,801. A real-HTTP regression
  restarts before refusal and recovery, then proves exact replay and another
  restart grant Coins only once and leave the account in `free_roam`.
- **Remaining evidence boundary:** this establishes one client-produced result,
  not the retired service's full reward distribution or validation rule. The
  external 1,200--1,500 table is incomplete for this final-client path, and the
  permanent Chapter 3 availability remains local policy. Reporter acceptance
  of the fixed reward-screen retry is pending.

## Clean onboarding and generated-data boundary

- **Confirmed by a clean public-source run:** a first-time data directory can
  start with only the operator's final 5.5.7-170 APK, matching Android resource
  tree, and documented external tools. Guided setup freshly generated 48
  `DummyDll` assemblies, `dump.cs`, the character/native/scenario/story
  catalogs, 23,594 resource mappings, local Pact banners, a signing key, and
  the patched APK. It did not consume earlier generated output or account
  state.
- **Confirmed by generated provenance and package checks:** the character,
  native encounter, scenario encounter, and story-outcome catalogs all named
  and hashed the selected APK and their required derived inputs. The output APK
  passed zip-alignment and v1/v2/v3 signature verification, and its installed
  bytes matched the generated file.
- **Confirmed by original-client transport and restart:** a fresh install
  performed signup, login, and userdata, loaded resources, visibly entered the
  Recruit tutorial, and committed its first Pact mutation. After the server was
  stopped and relaunched through `liminal_gate.server_setup`, the client loaded
  the same privacy-hashed account and persisted tutorial state. The capture
  contains 548 requests, all HTTP 200.
- **Confirmed onboarding defect and fix:** file existence did not prove that a
  framework-dependent Il2CppDumper apphost could locate its .NET runtime.
  `--check` now executes the dumper without inputs and requires its usage
  output. A failed apphost points the operator at `Il2CppDumper.dll`, which
  setup runs through `dotnet`.
- **Confirmed onboarding defect and fix:** guided setup judged the Il2CppDumper
  run by its exit code, which a successful run cannot be relied on to set.
  Il2CppDumper v6.7.46 (tag `v6.7.46`, commit `8a521b9c`) ends `Program.Main`
  with a `Console.ReadKey` guarded only by the `RequireAnyKey` its shipped
  `config.json` sets true, and that call sits outside the `try` wrapping the
  dump; .NET raises `InvalidOperationException: Cannot read keys ...` whenever
  standard input is not a console, which it is not while `run_with_heartbeat`
  captures the child (`stdin=DEVNULL`, piped output). A Windows tester therefore
  saw `complete guided setup needs Il2CppDumper to produce a DummyDll directory
  and dump.cs` after a run that had produced both. Redirecting real bytes to
  stdin does not help — the call wants a console handle. Setup now decides on
  the artifacts (`DummyDll/*.dll` and `dump.cs`), reports a non-zero exit that
  produced them rather than failing on it, keeps every run in
  `user-data/il2cpp/il2cppdumper-last-run.log`, and demotes the refused keypress
  below any other fault line when the artifacts really are absent.
- **Environment boundary:** two emulator graphics configurations served the
  same successful transport but rendered black with framebuffer `0x506`
  errors. The already documented software ANGLE launch path rendered the title
  and tutorial. A responsive server alone therefore does not certify client
  presentation.
- **Strongly inferred from original-client failure evidence and confirmed by
  real-HTTP restart regression:** after Chapter 1-1, a relaunched final 5.5.7
  client enters `Tutorial03_start` and posts the established tutorial
  party-save field structure before its next Pact. The server had no structural
  acknowledgment in `chapter1_1_cleared` and returned HTTP 409
  `tutorial_state_conflict`. That phase now acknowledges the write without
  applying its roster arrays or moving forward; restart replay is stable and
  the following `kind=12` Pact remains required. The reporter's event log
  exposed field names and `lastUpdate=1`, not the other body values, and a
  post-fix original-client retest is still pending.

## Client compatibility constants

- **Confirmed root cause from the Issue 15 device log and matching official
  Unity symbols:** the Pixel 7 Pro run loads the final client's ARM64 Unity
  2017.4.37f1 player, logs
  `Using memoryadresses from more that 16GB of memory`, and terminates with
  signal 11 before server transport. The failing
  `UnityDefaultAllocator<LowLevelAllocator>::AllocationPage` stores only five
  distinct high 32-bit address-region keys. Reaching a sixth region logs the
  message; bypassing that branch would index outside the five-entry table.
- **Strongly inferred fix with ARM64 runtime validation:** the same exact
  player contains `DynamicHeapAllocator<LowLevelAllocator>` and constructs a
  176-byte instance for its fallback allocator. Each default allocator already
  reserves 192 bytes. The hash- and source-byte-guarded plan now replaces only
  the default constructor with that existing layout and vtable. A signed build
  remained live through Unity title startup and real HTTP on ARM64-only Android
  12 with 11,940 MB reported RAM and Android 14; the Android 12 process reached
  a 66,027,632 kB virtual-memory peak without the old message or signal 11.
  The 12 GB AVD also ran the unpatched control, however, so it did not reproduce
  the reporter's device-specific allocation pattern. Pixel 7 Pro acceptance
  remains pending.
- **Confirmed compatibility correction:** Pixel 7 and Pixel 7 Pro support only
  64-bit apps. The earlier suggestion to drop `arm64-v8a` cannot produce a
  runnable package for that reporter. Their later plan-generation error was
  separate: `--source-apk` named the `local-input` directory rather than the
  APK, and reinstalling Python extras did not update the Git checkout.
  Upstream source trail:
  [Android's 64-bit-only Pixel 7 announcement](https://android-developers.googleblog.com/2022/10/64-bit-only-devices.html),
  [Unity issue 1284525](https://issuetracker.unity3d.com/issues/android-il2cpp-empty-project-crashes-on-launch-with-using-memoryadresses-from-more-than-16gb-of-memory-messages),
  and the
  [Unity 2018.4.30f1 fix note](https://unity.com/releases/editor/whats-new/2018.4.30f1).
- **Confirmed by final-version service notes and final-client static
  analysis:** Version 5.5.0 discontinued Co-op/VS, in-battle Eidolon use, and
  Tavern Eidolon enhancement. The final 5.5.7 client still carries
  `eidolonQuestList`, the Mode 4 selector, Chapters 4100--4111, and a distinct
  result path for Summon collectibles because the former Co-op Eidolon quests
  became single-player quests. Owned Eidolons remain viewable under Options.
  The relevant solo boundary is therefore quest visibility, start/clear, and
  durable collectible acquisition—not a charging gauge or battle summon
  system. That server boundary is now implemented; original-client acceptance
  remains pending.
  Public source trail: the archived community
  [Eidolons status](https://terrabattle.fandom.com/wiki/Eidolons) records the
  final behavior and collection location; the contemporary
  [5.5.0 announcement report](https://www.siliconera.com/terra-battles-ver-5-5-0-update-is-the-final-major-update-to-the-game/)
  records that the Co-op Eidolon quests became single-player quests. The
  selector, chapter, and result-path details come from the supplied final APK,
  not those public summaries.
- **Static archival compatibility, not final-version UI acceptance:** the
  recovered `summon_skill_unlock` route and all 44 material-cost rows remain
  useful for documenting the client binary. Version 5.5.0 retired the
  enhancement surface, so the bundled route is not required for ordinary
  final-version solo play, is no longer enabled by either supported default
  launcher, and is not claimed to be reachable through its UI. The explicit
  archival option remains available.
- **Confirmed by launcher and archival-route regressions:** guided and
  server-only default command lines omit `--summon-skills`, while the explicit
  bundled policy still loads and its mutation remains replay- and restart-safe
  over the real HTTP route.
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
- **Confirmed by dual-ABI selector analysis:** `UISpecialSelect.SetMode(0)`
  first reads `ServerConstants.specialQuestList` (static offset `0x190` on
  ARM64 and `0x114` on ARMv7), checks that it is nonempty, and only then falls
  back to the embedded 50-entry array. The server list therefore owns normal
  Special presentation when supplied. The curated generator preserves the
  final list's distinction between folded chapter cards and explicit section
  cards instead of assuming every start/clear identity is its own card.
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
  Its permanent availability is not recovered service behavior; the 1,800
  Coin ceiling is bounded by the Issue 25 final-client result, not a recovered
  historical distribution. Arena VS remains unsupported.
- **Confirmed final-client static contract:** `ChapterInterface::.cctor` and
  its predicates identify Chapters 9010--9013 as Tower of Temptation and
  9100--9102 as Donation. `ServerConstants.towerQuestList` and
  `UISpecialSelect.Mode.TowerQuest` establish the dedicated selector. Direct
  ARM64 callers of the Tower predicate are selector/title presentation, while
  completed `ChapterBase` stages call ordinary `AppServerUtil.ClearQuest`.
  Matching BattleData contains three one-battle, 15-stamina, zero-entry-Coin
  stages in each Tower chapter. Donation has separate aggregate-state UI and
  remains disabled.
- **Explicit solo-adapter policy with real-HTTP restart proof:** guided setup
  advertises all 12 BattleData-backed stages in Chapters 9010--9013 through
  `towerQuestList` after Chapter 3, supplies their chapter flags, and settles
  them through the normal durable event transaction without advancing story
  progress. This does not recreate the historical shared HP, staged
  achievements, or reward state. Permanent availability and zero fixed clear
  Coins are preservation policy. The maintainer opened the corrected Tower
  selector on the physical final client and its first entry loaded the battle
  after a retry. This is operator-observed navigation/entry acceptance without
  a preserved transport trace; clear and result-screen return remain pending.
  Arena VS remains disabled throughout.
- **Confirmed final-client Eidolon result contract with bounded local
  settlement:** `ClearQuest` serializes the existing `summonList` before the
  result UI runs; `battle_result.summons` carries the dropped IDs; and the
  clear callback does not read a returned Summon list. `ShowSummonGet` then
  calls `UserData.AddSummon`, which constructs `SummonInfo(id, 1, 0)`, so the
  durable raw value for a new collectible is exactly `1`. The runtime can
  therefore validate an explicit reviewed stage ceiling and commits accepted
  acquisition before acknowledgment; it refuses unlisted, duplicate, or
  already-owned reports without mutation, and exact replay survives restart.
  The original 28-row generated projection was nevertheless wrong. Sixteen
  tier-I/tier-II rows have zero battles and no final-client banner. The twelve
  nonzero-battle identities exactly match the Android `SpecialBanner` catalog:
  4100-3, 4101-3, 4102-3, 4103-1, 4104-3, 4105-3, 4106-1, 4107-3, 4108-3,
  4109-3, 4110-1, and 4111-1. Those are now the only generated selector rows.
  Older Co-op enemy records contain 50 percent Eidolon drops, but the playable
  solo programs use different enemy records; generated acquisition ceilings
  remain empty until a solo result capture establishes their mapping.
- **Confirmed by final-client static identities, resources, and
  generated-catalog validation:** guided setup derives 42 curated Archive
  Special Quest stages across Chapters 2000--2011 and 2014--2018 from the
  matching local BattleData and character catalog. Compiled chapter programs,
  backgrounds, and required explicit banners exist for each selected row.
  Test Chapter 2012, bannerless Chapter 2013, and empty 2015-4--6 placeholders
  are excluded. The selector merges these rows with Chapter 3003-1; bundled
  Chapters 8000--8007 and 8012--8017 remain authoritative on
  `descentHuntingList`.
  **Local policy:** the permanent story gates, zero fixed
  clear-Coin increment, and first-section associated-character grants are not
  recovered schedules, probabilities, or complete reward tables. Variable
  battle Coins are reconciled from the client result. Jade Dragon 2004-1 clear
  is client-confirmed; the other Archive families remain unverified.
- **Confirmed local master-data projection:**
  `user-data/derived/battledata-stages.json`, SHA-256
  `be6fee15b28fd192d12c2ee5c8ac4cce30f25addda3135f77deec3dc65596767`,
  was produced by `battledata_importer` for final Android 5.5.7-170 APK
  SHA-256 `f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15`.
  `jq` grouped the recovered rows by chapter: 2000/2001/2002 each have four
  sections at 15/25/40/40 stamina, 2004 has one at 15, 2006 has four at
  30/35/40/40, every Chapter 8000--8007 family has five at
  5/10/15/15/15, and every Chapter 8012--8017 family has three at 5/10/15.
  Chapters 9010--9013 each contain three one-battle, 15-stamina sections and
  zero entry Coins. Chapters 9100--9102 instead contain the 45 Donation
  sections and are not generated. This
  confirms local section economics, not service-authored clear rewards.
- **Confirmed by supplied final-APK analysis:** BattleData identifies Chapter
  3004-1 as *Crystal Road* (`クリスタルロード`): three battles and seven stamina.
  `UISpecialSelect` mode 7 reads `huntingHuntingList`, while the generic
  non-1000-series gate requires `sp_ch_3004-1`. **Local policy:** its bounded
  transaction accepts up to two Items from material IDs 1--17 and the
  Ticket/power-up IDs 50 and 53--56. The reference table's historical odds are
  not implemented or claimed; original-client acceptance is still unverified.
- **Confirmed by static client analysis, live transport, and original-client
  observation:** Strikes Back reads `descentHuntingList`. One folded tier-1 row
  per unlocked Chapter 8000--8007 or 8012--8017 family plus its matching
  chapter flag opens that family's card. Spinetrich Kino and Kraken Kino
  rendered for the current progress, and Chapter 8000-1 reached `start_quest`
  and loaded its battle resources.
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
- **Confirmed statically and by real-HTTP replay/restart regression; original
  client acceptance pending:** `NormalItem=20` is the exact one-draw Item 81
  Fellowship Ticket payment form. It reuses the Fellowship pool for ordinary
  Skill Boost draws and the Fellowship-side Fate Luck policy when
  `luckType=true`, spends no Coins or Energy, and returns the post-spend
  `itemList`. Coin Fellowship draws are refused while a ticket remains because
  no mixed ticket/coin batch is recovered. Campaign/event selectors remain
  outside this boundary.
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
- **Confirmed by final 5.5.7 ARM64 `Buddy.CanEquip` control flow at
  `0xD01AE0`--`0xD01BB4`:** a nonzero `exclusiveChrID` accepts either the
  direct target character or its nonzero `ancestorChrID`; a nonzero
  `exclusiveSpeciesID` must match the active job's `Species`. The method does
  not read `RequiredLevel`; that field gates the effects of an already equipped
  Companion, so turning it into an equip refusal would invent behavior.
  The final master projection contains 346 characters, 1,111 jobs, and 497
  Companions; all 65 nonzero ancestors and all 132 character restrictions
  resolve, and the two species-restricted Companions use a species present in
  the job masters.
- **Strongly inferred from dual-ABI serializer/equip paths and proven by
  real-HTTP replay/restart regression:** the combined
  `chrdata`, `buddyInfo`, `lastUpdate` form is one atomic Companion equip
  mutation. The public server now requires owned, one-to-one bidirectional
  `character.buddy`/`companion.chrID` links and refuses one-sided retargets
  without changing either array. Newly equipped or retargeted links also
  require the APK-hashed generated catalog and obey the recovered direct
  character, ancestor-family, and active-job species rules. Direct, ancestor,
  species-matched, unrestricted level-one, rejection, missing-catalog, exact
  replay, and restart cases pass over the real HTTP route.
- **Operator-observed, trace certification pending:** the maintainer played
  through Chapter 8-4 on a physical device without a client-visible failure.
  The preserved trace-based canonical checkpoint remains Chapter 2-1.

## Configuration and derived-data boundaries

- **Confirmed by setup/preflight regressions:** guided setup resolves one
  complete explicit or generated `(DummyDll, dump.cs)` pair through the same
  path in `--check` and the real build. Generated output beneath `--data-dir`
  remains reusable without the dumper executable; an incomplete pair fails
  before the resource inventory. Port range, requested-device readiness, and
  physical-device host routing are likewise checked before the build. Advanced
  local events are enabled only by explicit `--event-catalog`, not a normal
  first-run prompt. This is setup behavior, not recovered service behavior.
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
  Chapters 8000--8007 unlock permanently after local Chapter 5--12 gates and
  their five tiers cost 5/10/15/15/15 stamina. Chapters 8012--8017 unlock
  after local Chapter 13--18 gates and their three tiers cost 5/10/15. No
  recovered base reward is granted, so clear accepts only a zero-base result
  and unchanged server-owned state. Chapters 8008--8011 and 8018 remain
  unavailable because their distinct progression/reward contracts are not
  recovered.

## Public-release boundary

- **Confirmed by the 2026-07-30 Issue 25 run:** 35 focused Hunting
  catalog/real-HTTP tests passed. The warning-strict full suite passed 619
  tests in 118.143 seconds; compilation, profile JSON, endpoint YAML, and diff
  checks passed. An exact clean source candidate passed both publication gates.
  The new test reproduces rejected settlement, restart persistence, accepted
  recovery, exact replay, and one durable Coin grant. Reporter client
  acceptance remains pending.
- **Confirmed by the 2026-07-28 clean-onboarding run:** the focused preflight
  suite passed 19 tests and the warning-strict full suite passed 585 tests in
  112.308 seconds. The clean client/bootstrap/restart evidence above does not
  expand the canonical gameplay boundary beyond Chapter 2-1.
- **Confirmed by the 2026-07-28 refactoring run:** the warning-strict baseline
  passed 578 tests and the behavior-preserving result passed 581 tests in
  112.991 seconds. Focused real-HTTP tests covered mutation routing, collision,
  retry, restart, persistence, GET/resource serving, and refusal diagnostics.
  This establishes behavioral regression coverage for the structural changes;
  it does not expand the original-client certification boundary. An exact
  clean source candidate also passed material preflight and the independent
  repository-history audit.
- **Confirmed by the 2026-07-27 follow-up run:** 417 tests passed with
  `ResourceWarning` promoted to error, including the generated-outcome
  real-HTTP settlement path and account-state reload checks.
- **Confirmed by release tests:** preflight scans generated-output directories
  rather than hiding them, while the repository audit rejects dirty state and
  prohibited path names anywhere in Git history.
- **Confirmed by the 2026-07-26 remediation run:** 287 tests passed with
  `ResourceWarning` promoted to error; a clean temporary source candidate
  passed preflight and repository-history audit.

## 2026-08-01 external-reference sweep

All entries below are operator-approved community/reference material in the
sense of `external-quest-reference-ledger.md`: they tighten or corroborate
bounded local policy and never promote a row to recovered. Wiki pages were
read as raw wikitext through the site's MediaWiki API on 2026-08-01.

- **Corroborated exactly, no change:** Pact of Truth class shares (4/10/15/71),
  duplicate gains (+6/12.0%, +5/10.0%, +1/5.0%), the Pact of Fate +5.0 Luck
  duplicate increment, and the 100.0/80.0/70.0 Luck-cap banding that matches
  the recovered `Character.get_luckMax` split. Provenance is now dated: the
  in-game rate display began 2018-02-28 per the archived official news post
  (Wayback 20180228133231, terra-battle.com post-156). Fellowship selection
  stays uniform; the only surviving empirical record is a 2015 forum sample
  (Wayback 20150424040406, thread 5198) that predates the final pool.
- **Recorded, not yet appliable:** the Companions of Truth displayed base
  rates (Z 3%, SS 8%, S 10%, A 30%, B 49%). The public bundle stores the
  114-member Rare pool without per-ID rarity, so the bundled draw stays
  uniform; an operator-supplied weighted catalog is the sanctioned path.
- **Applied as bounded policy — Chapter 1100:** the community record (Mutoh Λ
  and Shin'en Λ quest pages) documents one exclusive Companion roll per
  battle, and its per-battle candidate lists match the recovered `dropBuddies`
  manifests exactly (three on battle 4, two on battles 2-3, one on battle 1,
  none on battle 5). The settlement now accepts at most one reported manifest
  Companion per clear, minted at level 1. The record's roll weights, item
  drops, story-progress/UTC-hour difficulty schedule, and the battle-4
  character recruit remain unimplemented; a clear claiming any of those is
  still refused.
- **Applied as bounded policy — the two Roads (1200-1/1201-1), channel by
  channel against the recovered flags.** Empty `dropBuddies` rules out
  Companion drops, which stays refused on the game's own authority. The Luck
  chest was refused on `allowLucky` 0; that reading is **withdrawn**, see the
  2026-08-02 entry below. `doNotDropExchangeItem` 1 governs, by
  its own name, exchange items — whether it suppresses every item drop is an
  interpretation, not a recovered declaration — so Machine Road accepts the
  contemporaneously documented Star drops (recovered items 118-121) under a
  generous ceiling: inert if the client never rolls an item there, and it
  stops a won battle being refused if it does. None of the three flags
  addresses battle-recruited monsters, so Dragon Road accepts at most one
  reported Steel Dragon recruit per clear (character 1090, resolved from the
  operator's own decoded name catalog); a duplicate recruit changes nothing
  because no duplicate rule survives. The Messages-borne Mech Skill Drop has
  no recovered identity or transport and stays out. A real-client Road run's
  refused-write shapes would settle the item-flag semantics empirically.
- **Applied as bounded policy — Daily Quests:** Crystal Roundelay's documented
  guaranteed power-up now bounds the four recovered power-up IDs (53-56), and
  Rarity Rumble's documented 10% Fellowship Ticket bounds Item 81. Its
  guaranteed Ore stays unbounded: Ore identities remain unresolved. The
  record also gives the final rotation as a 41-day cycle of two quests per
  day; the client schedules that itself from its own `questOrder`, so the
  server's once-per-UTC-day rule is unchanged.
- **Applied with dated evidence — Trading Post phase:** the rotation page's own
  edit history (revisions 83575-83859) was built live, one table per Friday,
  2018-10-12 through "Rotation finished" on 2018-11-30, and the archived
  5.5.0 news post dates the first table's launch week. The bundled cycle is
  now anchored to Friday 2018-10-05 00:00 UTC, so week indices reproduce the
  historically dated weeks. The fixed cycle existed only from 5.5.0 onward;
  continuity to end of service rests on two years of edit silence, not a
  capture.
- **Corroborated:** chapter ticket milestones (2/3/2/3/4 across Chapters 5-10,
  introduced by v4.0.0 per the archived official news) with no documented
  milestones past Chapter 10; Weekly Challenge was removed in v5.5.0, so the
  final-client all-zero shell is the correct shape; The Hunt For Joker's 100%
  Joker Λ grant with +10% Skill Boost and +10 Luck duplicates.
- **Recorded for future boundaries:** the wiki's 62-achievement reward table
  (Chronicle rows pay 1 Energy + 1 Metal Ticket, matching the recovered
  present list; the Eidolon/Hunting/VS sets were removed in v5.5.0); Descent
  quest ownership-gated drop chains (for example Bahamut Descended 20%,
  Ultra 100%-then-materials); Tower of Temptation's shared-HP/Final Blow
  reward structure; Battle Champs (Little Noah) Nia recruit rates. No public
  source documents the Donation event, Hime Rush, or fixed clear-Coin values
  for the 2000-series archive chapters (tbs.desile.fr covers story chapters
  1-38 only).

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

## 2026-08-02: `allowLucky` does not gate the Luck Treasure Chest

- **Withdrawn:** three places in this repository refused a stage's Luck chest
  because its `BattleData` section sets `allowLucky` to 0. That inference does
  not hold and the refusals it supported have been re-derived.
- **Disproof, from data already on disk.** All forty-two story chapters set
  `allowLucky` 0. Mistwalker's own Ver 4.2.0 announcement states that a Luck
  Treasure Chest's "spawn rate and contents depend on your team's average Luck
  value" and lists only *some* quests as excluded, and the community record
  documents chest contents for twelve story chapters by name -- every one of
  which is `allowLucky` 0 in the operator's own data. A flag that is 0 on
  content that demonstrably produces chests cannot be the chest's gate.
- **What it tracks instead, Strongly inferred.** Exactly five chapters set it
  to 1: 2006 Lucia, 3003 Money Money Time, 3004 Crystal Road, 6010 Lucky
  Orbling, and 7010 Eidolon Forest. The community record independently places
  the Luck-granting "Lucky" enemies -- Lucky Orbling and Lucky Runner, which
  raise party Luck when pincered -- in the Lucky Orbling daily quest and in
  Lucia the Explorer IV. The flag therefore reads as "Lucky-type enemies may
  spawn here", which is a Luck *source*, not a Luck *reward*. Two details keep
  this short of Confirmed: the record also names Coin Creeps Lv. 35 as an
  Orbling stage and that chapter does not set the flag, and Crystal Road sets
  it while appearing on the record's own no-chest list.
- **The chest curve is not in the client.** `Character.get_luckRate` (ARM64
  `0xD08B74`) loads the float at `0x2056F48`, which is `0.1`, and multiplies:
  it converts stored tenths to displayed Luck and nothing more. The client
  carries the stat, the per-class caps, the Companion modifiers and the display
  maths, and no chest table or spawn rule at all. The retired service owned
  that decision, which is consistent with `luckResult` arriving on
  `start_quest` rather than being computed at clear.
- **Consequence.** Dragon Road's chest refusal survives on other evidence: the
  community record's explicit no-chest list names it, alongside Crystal Road,
  Hunting Zones, Metal Zones, Orbling Cavern and The Hunt For Joker. Machine
  Road and Chapter 1100 are not on that list, so their chests are now
  *undetermined* rather than declared absent, and stay refused as labeled local
  policy rather than on the game's authority.

## 2026-08-02: one-process Android host and packaged server transport

- **Confirmed, static/build:** the reviewed 5.5.7-170 Android package names
  `com.unity3d.player.UnityPlayerActivity` as its launcher, carries one client
  DEX, targets API 28, declares minimum API 16, and contains both ARM64 and
  ARMv7 Unity/IL2CPP libraries. The activity name is 38 bytes, exactly matching
  `org.liminalgate.android.HostedActivity`; the private assembler therefore
  makes a bounded binary-string replacement and changes the typed minimum SDK
  from 16 to 24 without rebuilding the original resource table.
- **Confirmed, build:** the Android host builds with Gradle 8.11.1, AGP 8.9.2,
  Chaquopy 17.0.0, and Python 3.11. Its payload contains three host DEX files
  and Python native/runtime members for both `arm64-v8a` and `armeabi-v7a`.
  The combined structural artifact preserved the client package/version/target,
  exposed the replacement launcher, retained both ABIs, aligned successfully,
  and verified with APK signature schemes v2 and v3.
- **Confirmed, full-resource ARM64 emulator transport:** the one-command build
  inventoried all 11,806 resource files (940,138,388 bytes) and produced a
  locally signed 1.0-GiB final APK (1,064,591,384 bytes) with SHA-256
  `aeba11eade3b507d62403ee806b3e7390bb3a2abced03a0219e3ec4633685ef0`
  and payload-bound build ID
  `53d043cbb585337d19a749ef1a1735b31c5499bbe00c1376123d9600900fff93`.
  Its signer certificate SHA-256 is
  `01625a63bced5d45c7fb545d2bf2ef8d7660669e8db7a34a9638adf9e5d6e09f`.
  Every new/changed local ZIP header agrees with its central-directory flags,
  compression, and timestamp; all packaged resources are stored.
- **Confirmed, preceding full-payload ARM64 transport:** an emulator-only copy
  of the preceding full-resource payload was signed with the already-installed
  validation key; the installed APK SHA-256 is
  `23f6fc9f913c92ad3457352fd9014c294fffdee44c1e1fab178bdd81bca7faae`.
  On API 34, that reviewed client started Chaquopy in the app process, returned
  build ID `0f075b3c3a9cce9427d14bea17f5967b9a07e6c304f663e276e76bcaf4d9f211`
  from real `127.0.0.1:8002/healthz`, and only then initialized Unity
  2017.4.37f1. The server returned a 129,018-byte packaged BG member whose
  SHA-256 exactly matched the manifest. After force-stop, a new process
  returned the same health identity. The exact component launcher returned
  Android `Status: ok`; this replaced a one-event `monkey` launch which could
  exit without starting the activity. This proves the full packaging,
  readiness, direct resource transport, deterministic launcher, and relaunch
  design on ARM64. The source-exact final payload could not replace it because
  emulator-5580 had only 1.2 GiB free, so final-artifact device acceptance and
  any physical playthrough remain unverified.
- **Confirmed, regression:** schema-v1 filesystem catalogs still hash and serve
  explicit local files. Schema-v2 validates stored APK-member metadata and
  streams resources without extracting them. Small runtime/catalog members are
  size/digest checked before atomic extraction; seed state uses create-if-absent
  and a retry does not replace an existing save.
- **Confirmed, installer:** ADB incremental mode falsely reported success for
  the 1-GiB update while leaving no installed package. The on-device installer
  now requires `--no-incremental`; streamed installation then installed and
  launched the same full artifact, with focused regression coverage.
- **Unverified:** a full-resource physical-device playthrough, an ARMv7 runtime
  launch, and Chapter 2-1 mutation/restart certification from the combined APK.
  None may be inferred from build, signing, health, or Unity-start evidence.
- **Validation:** all 875 Python tests passed in 142.654 seconds with
  `ResourceWarning` promoted to an error. The three Android JVM tests passed
  under pinned Gradle 8.11.1 and Java 21. A clean committed source candidate
  passed release material preflight and independent-history audit.
