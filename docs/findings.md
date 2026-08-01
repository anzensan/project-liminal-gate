# Public Technical Findings

This file records only findings safe for the source-only public repository.
Private inputs, captures, account state, and original assets remain excluded.

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
  durable raw value for a new collectible is exactly `1`. Mapping the final
  chapter programs through EnemyData's ordinal table yields eight allowed
  first-tier pairs: 4100-1 -> 4, 4101-1 -> 9, 4102-1 -> 3, 4104-1 -> 8,
  4105-1 -> 10, 4107-1 -> 6, 4108-1 -> 5, and 4109-1 -> 7. Each matching enemy
  row carries a 50 percent ratio; the client rolls it, not the server. The
  server accepts an empty result or one allowed, unowned ID, commits it before
  acknowledgment, and refuses unlisted, duplicate, or already-owned reports
  without mutation. Exact replay survives restart. Chapters 4100--4111 and
  their 28 BattleData rows are exposed through `eidolonQuestList` after the
  Chapter 3 local gate. Original-client acceptance remains pending.
- **Confirmed by final-client static identities and generated-catalog
  validation:** guided setup derives Archive Special Quest Chapters 2000,
  2001, 2002, 2004, and 2006 from the matching local BattleData and character
  catalog. The selector merges these rows with Chapter 3003-1; bundled
  Chapters 8000--8007 and 8012--8017 remain authoritative on
  `descentHuntingList`.
  **Local policy:** the permanent Chapter 2/4/10/13/20 gates, zero fixed
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
