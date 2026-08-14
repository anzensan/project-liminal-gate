# Public Technical Findings

This file records only findings safe for the source-only public repository.
Private inputs, captures, account state, and original assets remain excluded.

## Puppet Show strict-audit aggregate

- **Reported runtime evidence:** a tester received 74 items from one
  otherwise-stock Puppet Show battle. No raw capture accompanied the report.
- **Disproved policy:** the former aggregate of 60 was a conservative project
  choice, not a recovered client or retired-service maximum.
- **Correction boundary:** the shared default is now the observed 74. The
  setting applies only with `--outcome-strict`; an over-ceiling report refuses
  the entire clear without mutation rather than discarding excess chests.
  Normal preservation play does not apply catalog reward maxima.
- **Transport proof:** a focused real-HTTP regression rejects 75 without
  mutation, settles 74 exactly once, and replays the response after restart.
  The true retail maximum remains unknown.

## Optional-stage refresh after chapter transitions

- **Reported symptom:** newly eligible Metal, Huntland, and Arena solo stages
  remained absent until the client process restarted; ordinary story stages
  continued to appear.
- **Confirmed implementation mismatch:** the server projected selector lists
  from account progress only in `get_server_status.constants`, and projected
  the exact `sp_ch_*` gates only in login `eventFlags`. Those are separate
  pieces of client state, so refreshing one route could not repair the stale
  half owned by the other.
- **Confirmed ARM64 client contract:** the status callback calls
  `EventManager.SetFlags` at `0xFB5568` and tail-calls
  `UserData.SetServerConstants` at `0xFB5644`; the login callback calls those
  same setters at `0xFB7998` and `0xFB7B28`. Both response shapes therefore
  already have a recovered consumer for both objects; no new wire field was
  invented.
- **Correction boundary:** status and login now each send lists and flags from
  the same progress snapshot. Locked rows remain unadvertised, and a direct
  start remains independently progress-gated. Real-HTTP regression covers the
  locked state, a login-only refresh after progress changes, status agreement,
  and restart persistence. Original-client retest without relaunch is pending.

## Battle-clear Luck preservation

- **Confirmed final-client wire behavior:** the preserved Chapter 3-2 clear
  body (SHA-256
  `dc3017906db7da31a0979a239048050cc0238006db53f387045abba25752e5a5`)
  omits optional `luck` members from `chrdata` after start returned a nonzero
  `luckUpTable`. Omission is valid and means the server remains authoritative
  for the durable field; it is not a request to reset every character.
- **Confirmed regression:** the shared clear merge retained monotonic job
  progression and Skill Boost but copied an omitted or stale-zero Luck field
  from the client row. Because ordinary story, Archive, Hunting, Daily, Metal,
  Special, and World Map Special clears share that merge, the loss was not
  confined to one quest family.
- **Correction boundary:** clear now keeps the greater durable/reported Luck
  before applying the cached server-authored gain. The clear response, replay
  payload, and durable save therefore agree. This prevents future loss but
  cannot reconstruct values already overwritten without a backup.

## Which roster members the client serializes

- **Confirmed ARM64 client contract:** `Character.ToHashTable` (`0xD0A318`)
  builds its Hashtable from exactly eight keys — `id`, `jobID`, `flags`,
  `jobLevels`, `jobSlots`, `skillBoost`, `buddy`, `date` — read from the string
  literals its own call sites load. `Character.LoadFromJson` (`0xD07C5C`) reads
  those eight and two more, calling `set_luck` and reading `plusCount`. The
  earlier finding that a clear omits `luck` is therefore not a property of the
  clear: the client has no code path that transmits `luck` or `plusCount` on
  any route, so the server owns both outright.
- **Confirmed client-side application:** `UITeamStateItem.UpdateForResult` and
  `UIBattleResultTeam.ShowMsg` both call `Character.set_luck`, so the result
  screen applies `luckUpTable` to the client's own objects. That value is
  in-memory only and is replaced by the server's on the next userdata read —
  which is why a gain the server failed to commit reads to a player as Luck
  that appeared and then vanished, rather than as Luck that never arrived.
- **Consequence for Skill Boost:** because `skillBoost` *is* serialized, a
  client that raises it locally reports the raised figure, and a server-side
  grant added after the clear merge is paid twice. See the Joker duplicate
  entry in the changelog.
- **Consequence for roster writes:** the free-roam roster write took every
  submitted member wholesale, so a stale client could walk `skillBoost` and
  `jobLevels` backwards through an ordinary equip or party save. `luck` and
  `plusCount` were never exposed to that, but only because the client does not
  send them. Both halves now run through the same monotonic merge.

## Daily item and monster drop rotation

- **Confirmed final-client mechanism:** `DailyQuestManager.GetDailyBonusType`
  reads the boolean event flag `enableDailyBonus`, rejects Chapter 1 and values
  above 99, and deterministically selects no bonus, item x2, or monster-recruit
  x2 from the local calendar day of a server-corrected instant. Item and monster
  rolls read that result in fresh and resumed battles. Companion and Battle
  Summon rolls do not. The 15-day formula and write/read paths agree in both
  final-client ABIs.
- **Independent community corroboration:** the live
  [Terra Battle Stats schedule source](https://tbs.desile.fr/scripts/services/daily-bonus.js)
  anchors its displayed cycle to 2015-02-07. That date is day 37 from the
  client's 2015-01-01 epoch and resolves to the same first item-bonus chapter
  group, so all fifteen published slots align with the client formula.
- **Preservation policy:** Issue 35 prompted guided core story to keep the
  boolean gate enabled. The server does not compute or settle the bonus; it lets
  the client select and display its recovered schedule. Continuous enablement
  does not claim that the retired service used one unbounded event window.
  Physical-client badge and eligible-drop confirmation remain pending.

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
- **Physical-client correction from Issue 33:** the final client rendered the
  Chapter 7 milestone row and localized text, but its reward area was empty and
  opening it did not clear the unread badge. The earlier HTTP-only read proof
  was therefore insufficient. Guided core story now treats direct, exactly-once
  inventory settlement as explicit compatibility policy. An existing unread
  milestone record is settled and marked read; an already-read or deleted
  record is never granted again. The generic local inbox remains available for
  operator messages and login rewards, whose client acceptance is separate.

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
- **Tester-reported retail behavior:** the scripted Chapter 1-2 recruit is not
  one character but the generic that completes the Circle of Carnage against
  the starter — an Archer for Bahl, a Warrior for Grace. Two testers report the
  rule independently, and the client itself animates recruiting the Archer on a
  Bahl run, which is the client deciding the completion locally rather than
  reading it from the response. This is operator- and tester-supplied
  historical evidence; the public repository holds no retail capture of a Bahl
  Chapter 1-2 clear.
- **Confirmed executable behavior:** every first-Pact outcome declares the
  recruit beside its starter, and both commit together when the outcome is
  selected. Later tutorial templates resolve the recruit from that durable
  state, so the grant and every following party projection name the same
  character the client displayed. Forced real-HTTP tests cover both sides
  through the Chapter 1-2 clear, restart, exact retry, and the party write the
  client sends back.
- **Compatibility boundary:** later tutorial templates resolve their starter
  slot from durable state, while a legacy state with no starter field resolves
  to Grace because the earlier server could produce no other result. A save
  with no recruit field resolves to the Warrior for the same reason: every such
  account was granted that character whichever starter it holds, so it is what
  the client's own roster already contains. A clean original-client Bahl run
  through the tutorial remains pending; the earlier server granted the Warrior
  on the Bahl path, and the mismatch it produced is what the tester report
  above identified. In particular, the later Chapter 1-2 callback currently
  applies the captured starter packed level/EXP projection with the durable
  starter ID; Bahl-specific packed progression has not been independently
  captured.

## Quest settlement compatibility

- **Confirmed by Pixel 7 Pro final-client/server evidence:** the Issue 20
  Crystal Road attachment (SHA-256
  `b3139d63dd54a8ae6d6c067c7f15a62c8014ad301f61a33f98332b53a5acb99d`)
  contains 25 HTTP 409 `invalid_local_hunting_result` records for Chapter
  3004-1. All report 280 Coins; 21 report 5,400 EXP and four report 5,625 EXP.
  This proves the bundled zero-Coin/zero-EXP placeholders were incomplete, not
  compatibility limits. It does not establish the historical maxima or reward
  distribution.
- **Local preservation-policy correction:** Hunting, Metal, default Special,
  and Daily Quest clears now trust a structurally valid result for the exact
  active battle by default. Stage identity, wallet arithmetic, item/ticket
  projection, Companion-box integrity, body-scoped replay, and durable commit
  remain mandatory. Catalog maxima are enforced only with `--outcome-strict`.
  Companion ids still require catalog level data because the server must author
  a response row absent from the clear request. A real-HTTP regression settles
  the observed Crystal Road 280-Coin/5,625-EXP shape and proves restart replay
  does not credit it twice; physical-client retest remains pending.

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
  Chapter 3003-1 (*Money Money Time*) through the Hunting transaction. Its
  permanent availability is not recovered service behavior; the Issue 25
  final-client 1,800-Coin result remains strict-audit evidence, not a recovered
  historical distribution or a default acceptance ceiling. Arena VS remains
  unsupported.
- **Confirmed final-client static contract:** `ChapterInterface::.cctor` and
  its predicates identify Chapters 9010--9013 as Tower of Temptation and
  9100--9102 as Donation. `ServerConstants.towerQuestList` and
  `UISpecialSelect.Mode.TowerQuest` establish the dedicated selector. Direct
  ARM64 callers of the Tower predicate are selector/title presentation, while
  completed `ChapterBase` stages call ordinary `AppServerUtil.ClearQuest`.
  Matching BattleData contains three one-battle, 15-stamina, zero-entry-Coin
  stages in each Tower chapter. The claim that Donation "has separate
  aggregate-state UI and remains disabled" is **withdrawn**; see the 2026-08-07
  entry below. The chapter *range* is as stated, but its content is Melting Pot
  and the aggregate-state UI is dead code in the final build.
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
  zero entry Coins. Chapters 9100--9102 carry fifteen sections each, 45 in
  total; they were recorded here as "the 45 Donation sections" on the strength
  of the chapter range alone, and that reading is **withdrawn** -- their
  BattleData titles name them Melting Pot, see the 2026-08-07 entry below. This
  confirms local section economics, not service-authored clear rewards.
- **Confirmed by supplied final-APK analysis:** BattleData identifies Chapter
  3004-1 as *Crystal Road* (`クリスタルロード`): three battles and seven stamina.
  `UISpecialSelect` mode 7 reads `huntingHuntingList`, while the generic
  non-1000-series gate requires `sp_ch_3004-1`. **Local policy:** its bounded
  catalog records up to two Items from material IDs 1--17 and the
  Ticket/power-up IDs 50 and 53--56 for optional strict auditing. The reference
  table's historical odds are not implemented or claimed. A later Pixel 7 Pro
  clear confirms entry and reports 280 Coins plus 5,400/5,625 EXP; client
  acceptance after the relaxed settlement-policy change remains pending.
- **Confirmed by static client analysis, live transport, and original-client
  observation:** Strikes Back reads `descentHuntingList`. One row per unlocked
  Chapter 8000--8007 or 8012--8017 family opens that family's card. Spinetrich
  Kino and Kraken Kino rendered for the current progress, and Chapter 8000-1
  reached `start_quest` and loaded its battle resources. The reading that a
  *tier-1* row plus a chapter flag is the right shape for that card is
  **withdrawn**: it renders, but as a single stage rather than a card, which
  is why only tier 1 was ever reachable. See the 2026-08-08 entry below.
- **Confirmed by ARM64 disassembly (issue 20), original-client observation
  pending:** the final client validates a selector row *twice*, under two
  different rules, and the mismatch is what made the Hunting Zone selector
  flash around Attack of the Coin Creeps. `UISpecialSelect.IsQuestOpen`
  (ARM64 RVA `0xF84D84`) exempts Chapters 1000--1099 from the per-row
  `sp_ch_<chapter>-<section>` gate: `0xF84EB0` computes `chapter - 1000`,
  compares it against `0x63`, and returns true without consulting a flag.
  That bypass covers only list *construction* --
  `UISpecialSelect.<GetList>c__Iterator0.MoveNext` is its sole caller in the
  class (`0xF897FC`, `0xF89898`, `0xF898D4`). The per-frame revalidation in
  `UISpecialSelect.UpdateItems` (`0xF856C8`) instead calls `CheckQuestFlag`
  directly at `0xF85A44`, with no range exemption. A row that fails it is
  appended to a local removal list (`0xF85AE4`), removed from `openList` and
  `itemList`, and -- when that list is nonempty (`0xF85B00`) --
  `StartCoroutine(Refresh())` runs at `0xF85BF4`, rebuilding the row so the
  next frame repeats. That loop is the flashing selector and its permanent
  loading circle.
- **Confirmed implementation cause and fix:** `client_event_flags` withheld
  `sp_ch_` flags for exactly Chapters 1000--1099, citing the `IsQuestOpen`
  bypass, so tier-1 Hunting rows 1001--1004 were advertised unflagged while
  Metal Zone (3000), the Roads (1200/1201), Crystal Road (3004-1), and Strikes
  Back (8000--8017) were flagged and stayed stable -- exactly the reported
  boundary. Every advertised row now carries its own exact section flag.
  Nothing about this is visible as an HTTP error, because the loop is entirely
  client-local; the reporter's event log correctly showed no selector-time
  endpoint failure.
- **Confirmed follow-on cause:** after the selector stabilized, the Chapter
  1003 card remained blank. The final APK's embedded `AssetVersions` TextAsset
  contains 306 `SpecialBanner` rows and jumps from complete `sp1001` and
  `sp1002` families to `sp1004`; neither the catalog nor the retained Android,
  iOS, or Mac archives contains an `sp1003` family. `UISpecialItem.Init` still
  receives `hasBanner=true` and starts `loadImage` without changing its stored
  chapter/section fields, so this is an image-catalog gap rather than a quest
  identity or server-list failure.
- **Implemented local presentation policy:** the source-hash-guarded APK plan
  copies the retained `sp3003-1` 610x140/version-110 catalog record to logical
  names `sp1003-1`, `sp1003-2`, and `sp1003-3`. The resource manifest serves an
  exact operator-owned `sp1003` file if one exists; otherwise setup derives
  three ENCA bundles from retained `sp3003-1` Coin Creeps-family art, renaming
  each Unity texture, container path, and bundle identity to the matching
  `sp1003` name. The public-data transport serves those derivations at both the
  plain and client-MD5 URLs. It does not rename Chapter 1003, change click
  routing, or modify battle/settlement state. A real rebuilt final APK
  round-tripped all three catalog records; all three derived bundles
  round-tripped through ENCA and Unity parsing, and real HTTP returned the exact
  172,451-byte section-1 derivation.
- **Confirmed defect in that first derivation (2026-08-06):** the three derived
  bundles rendered blank or not depending on what the client had loaded just
  before, which two testers reported as cards vanishing after an unrelated
  Hunting run and reappearing later. Renaming the texture, container path, and
  bundle identity leaves a fourth name untouched: the serialized file inside
  the bundle, which all three inherited from `sp3003-1`
  (`CAB-14adb4c29162ab0d738835335430ce7e`). Unity keys a loaded bundle by that
  internal file and refuses to load one another loaded bundle already
  provides, so overlapping loads returned null and the card drew empty.
  Decoding 1,200 retained bundles found 1,274 distinct internal names and no
  duplicate at all, so uniqueness is an archive invariant only the derivation
  broke. `AssetManager` reads the texture and calls `delayedUnloadAssetBundle`,
  which is why the collision is a timing race rather than a permanent blank.
  Each derived bundle now carries its own internal name.
- **Confirmed client image caching (2026-08-06):** both
  `LoadAssetFromCacheOrDownload` call sites inside `AssetManager.LoadImageAsset`
  pass `useCacheFolder = 1`, and `GetCacheFolder` resolves to
  `Application.temporaryCachePath`; `GetPersistantDataFolder` resolves to
  `GameManager.storagePath` and holds unrelated client files. A downloaded
  image is stored as `<asset>_<ver>.bin` and reused without asking the server
  again, and `deleteOldVersion` removes only the other versions of the same
  asset. The version comes solely from the client's own `AssetVersions`
  TextAsset — no route sends one — so corrected bytes at an unchanged URL
  reach an existing install only when that catalog version changes. The three
  `sp1003` aliases therefore carry version 111 instead of the copied 110.
- **Remaining evidence boundary:** the fallback is retained client artwork for
  the related Coin Creeps special quest, not a claim that it is the lost retail
  Attack of Coin Creeps banner. The rebuilt card still needs physical-client
  visual confirmation. Only ARM64 was disassembled for the earlier flashing
  diagnosis; the matching ARMv7 addresses are not yet confirmed. The removal
  branch at `0xF85A70` also
  requires a global byte to be zero, and that field is unidentified -- the
  observed flash implies its value rather than proving it.
- **Local policy:** the country roster and large character/Companion box sizes
  are compatibility fixtures, not recovered production-service values.
- **Local policy with confirmed client meter semantics:** a successful
  chapter-boundary clear in either ordinary core-story catalog writes
  `refillStartTime: 0.0`, the client's full-meter representation. The rule is
  replay- and restart-safe and excludes intermediate story stages, Hunting,
  events, and World Map Special; it is not a claim about historical rewards.
- **Local policy over confirmed client meter semantics:** every quest
  settlement reports the post-clear `refillStartTime`, which capture does not
  show the retired service sending. The field defaults to zero and zero is the
  client's assertion of a meter refilled at the epoch, so a settlement that
  says nothing about the meter is read as one that says the meter is full — a
  bar restored to maximum over stamina the entry had just spent, persisting
  until the next start callback restated it. The server holds the only correct
  value and the client cannot derive it, so this states it rather than leaving
  the bar wrong. Chapter 1's tutorial clears stay on their captured shape:
  those stages charge no stamina, so a full bar there is accurate.

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
- **Confirmed statically and by real-HTTP replay/restart regression; a
  one-result-only reading of it was refuted by original-client reports:**
  `NormalItem=20` is the Item 81 Fellowship Ticket payment form. It reuses the
  Fellowship pool for ordinary Skill Boost draws and the Fellowship-side Fate
  Luck policy when `luckType=true`, spends no Coins or Energy, and returns the
  post-spend `itemList`. Coin Fellowship draws are refused while a ticket
  remains because no mixed ticket/coin batch is recovered. Campaign/event
  selectors remain outside this boundary. The form is **not** limited to one
  result: the single capture behind that earlier reading was a one-ticket
  press, and `UIBarSlot.OnClickNormalBulk`/`OnClickNormalBulk2` reach the same
  `SlotKind.NormalItem` through the ten-pull control, with `InitChrMenu`
  sizing the batch from the held Item 81 count (`numNormalSlot`, capped at
  ten). Testers reported Network Error on every multi-ticket press, which is
  what a `count>1` refusal looks like from the client's side.
- **Confirmed statically; original-client acceptance reported:** the Companion
  page posts four payment variants to `do_buddy_slot`, not two.
  `UIBarSlot.OnClickBuddyNormal`/`OnClickBuddyNormalBulk` read
  `NormalSlotItemId` (Item 81) and post `SlotKind.Normal` (0) or
  `NormalItem` (20); `OnClickBuddyRare`/`OnClickBuddyRareBulk` read
  `BuddySlotItemId` (Item 112) and post `Rare` (1) or `BuddyItem` (21). The
  two pools are the `SlotKind` members of BuddyDatabase: 81 records at
  `Normal` for the Coin pull, 114 at `Rare` for the Energy pull, disjoint. A
  server accepting only the rare pair answered every Fellowship Ticket press
  on the Companion page with an unsigned 501, which the client shows as
  Network Error -- the reported symptom, and unlike the character page it had
  no working single-press path to fall back on.
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
  reward table was recovered, and issue 46 observed that the client reports a
  won battle's own experience, Coins, and drops, so clear settles those from the
  client's report against a server-projected inventory rather than requiring the
  zero-base result it originally accepted. The reading that Chapters 8008--8011
  and 8018 must stay unavailable because their progression and reward contracts
  are unrecovered is **withdrawn**: they are Battle Champs and 8-Bit Rush, the
  contract that differs is their `dropBuddies` manifest, and it is in the
  tester's own BattleData. See the 2026-08-10 entry below.

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

## 2026-08-04: Luck had preservation but no growth outside the story

- **Confirmed defect, from two operator reports.** One reporter kept 10% Luck
  on a character across Metal Zone runs; another watched every character show
  1.8 during the Lucky Orbling quest and hold nothing in the party menu
  afterwards. Together they separate the two halves: the roster merge preserves
  the stat correctly, and no Hunting-family stage could raise it.
- **Mechanism.** `luckUpTable` is authored at `start_quest` and applied at
  `clear_quest`, and only the generic story handler did either. The Hunting
  start -- which serves Hunting Zones, Metal Zone, the Roads and every Daily
  Quest -- and the Chapter 1100 start both returned `success` and
  `refillStartTime` alone, so `active_luck_up` was never set and their clears
  had nothing to apply. The exclusion was structural, not a rule: Metal Zone
  zones 2--7 cost 8 to 20 stamina, the Roads 15, Coin Creeps 10 to 20, and
  Chapter 1100 25, all of which `LUCK_GAIN_MIN_STAMINA` already qualifies.
- **Why the client cannot supply it.** The pincer that raises Luck on a flagged
  chapter happens inside the client's own battle, and the confirmed final client
  omits the optional `luck` member from a valid clear, so the gain never reaches
  the server. `_preserved_progress` takes the greater of durable and reported,
  meaning a reported 1.8 *would* have stuck; the value simply never arrives.
  A server-authored source delivered through `luckUpTable` is therefore the only
  channel available, and it is the one the client already renders.
- **Correction boundary.** The confirmed ≥8 stamina rule is unchanged and still
  reads the stage's declared cost rather than what the meter was charged, so it
  never depended on `--enable-stamina`. The Lucky-enemy source the five
  `allowLucky` chapters carry is separate from it by necessity, since three of
  those five cost less than eight stamina or nothing at all. How many Lucky
  enemies one battle offers is invented and labeled as such; the gain and the
  pincer chance are the community record's.

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

## 2026-08-02: the Puzzle Quests' Companion drop, and a bound that wedges an account

- **Confirmed, from the client's own data:** Chapters 6011-1 and 6011-2 are the
  only two of the fourteen Daily Quests whose `BattleData` section carries a
  non-empty `dropBuddies`. Each holds exactly one packed code — 68353 and 35841
  — which decode under the project's existing `code >> 8` Companion /
  `code & 0xFF` count packing to Companion 267 at one copy and Companion 140 at
  one copy. Both IDs are present in the recovered Companion master data. The
  community record agrees independently, naming them Glassy Minion Λ and Golden
  Minion Λ, each behind a 60% Ancient Key roll. The other twelve declare an
  empty manifest.
- **Confirmed defect:** the bundled Daily Quest policy declared no
  `companion_maxima` for any stage, so a Puzzle Quest clear reporting the drop
  the client's own data allows was refused with `409
  invalid_local_hunting_result`. Reported as issue 29 from a physical Pixel 7
  Pro: eleven identical refusals for chapter 6011 section 1 with `coins: 0,
  exp: 0`.
- **The severity is the wedge, not the lost drop.** A refused settlement never
  releases `active_hunt`, so the account stays `hunting_active` across a
  force-close and every unrelated stage start is then refused with
  `tutorial_state_conflict`. That is what a tester reports as a corrupted
  installation. The same shape produced issue 25. **A bound in a
  client-settled family is only ever safely too generous, never too tight**, and
  the bundled Daily Quest ceilings are now written with that asymmetry stated.
- **Confirmed, same defect class, found while fixing it:** all fourteen stages
  carried `max_exp = 0`, which refuses the ordinary battle EXP a Daily Quest
  pays; Metal Runner Rampage pays nothing else and its recovered spawns reach
  306,000 alone. Both Puzzle Quests bounded only their first reward tier, not
  the Tears, Particles and Ores their later tiers pay, and their item totals
  were roughly a third of the wave capacity behind them. Rarity Rumble's Ore
  identities (26-29) and Tearjerker Time's Tears and attribute rings were
  unbounded. Every one of these would have refused an honest clear and wedged
  the account the same way; all are now declared.
- **Confirmed diagnostic gap:** the refusal event recorded chapter, section,
  coins and EXP and nothing else, so eleven logged refusals could not name the
  channel at fault and the cause had to be recovered from the APK instead. The
  settlement diagnostic now also records how many Companions, battle-recruited
  monsters, Summons, and item stacks a result claimed — counts only, no
  identity and no body string, which is the same boundary the rest of the event
  log keeps.
- **Validation:** all 889 Python tests passed with `ResourceWarning` promoted to
  an error, including a real-HTTP regression that starts 6011-1, settles a
  reported Companion 267, and asserts the box holds one copy at level 1 and the
  account returns to `free_roam`.

## 2026-08-06: the Android 16 crash is Unity's own bind, not Play Billing

- **Confirmed defect, from a physical Galaxy S26 on Android 16.** The client
  crashed on launch with `NoSuchMethodError` on
  `ServiceConnection.onServiceConnected(ComponentName, IBinder, IBinderSession)`
  while carrying all eighteen `--disable-google-services` dex edits. The flag
  was verified applied, so the crash had to come from a bind the dex does not
  own.
- **Where it comes from.** `libunity.so` binds Play Services from native code to
  read the advertising ID and carries its own copy of everything it needs, none
  of it in `classes.dex`: the action
  `com.google.android.gms.ads.identifier.service.START` (once per ABI, at
  `0xAD2760` in `lib/arm64-v8a` and `0xBAFFC3` in `lib/armeabi-v7a`), the package
  name, the AIDL descriptor
  `com.google.android.gms.ads.identifier.internal.IAdvertisingIdService`, and the
  messages `Failed to obtain GoogleAdsId from GooglePlayService` and `Cannot bind
  to GooglePlayService.`. Beside them sits the JNI method table Unity builds its
  connection proxy from, declaring exactly one connect method:
  `onServiceConnected (Landroid/content/ComponentName;Landroid/os/IBinder;)V`.
- **Why only that one bind fails, Confirmed structurally.** Unity creates the
  connection as a `java.lang.reflect.Proxy` through `bitter.jnibridge`, and a
  Proxy hands every interface method to its `InvocationHandler` including
  `default` ones. An ordinary Java class inherits Android 16's new overload and
  is unaffected. Parsing the client dex's `class_def` interface lists finds
  twelve classes implementing `ServiceConnection` --
  `com.unity.purchasing.googleplay.BillingServiceManager$1`,
  `com.google.android.gms.common.internal.BaseGmsClient$zze`, the support-library
  and downloader ones -- and every one is a real class. None of them can raise
  this error.
- **Retraction.** The Galaxy S24 FE log put `UnityIAP: Billing service
  connected.` immediately before the fatal, and this project read Play Billing
  as the crashing bind; `PLAY_BILLING_BIND_ACTIONS` was added on that basis and
  the claim was repeated in `COMPATIBILITY_SCOPE.md` and the troubleshooting
  guide. It is withdrawn on the structural argument above: billing's connection
  is `BillingServiceManager$1`, an ordinary class, so it never could have thrown
  this. The line ordering was coincidence. The S26 log shows the same shape --
  `com.android.vending` unfrozen 20ms after `IAB helper created.` and a fatal
  50ms later -- and it is the same coincidence, because that build's billing
  action was already inert.
- **Correction.** The flag now also rewrites the action's first byte inside both
  `libunity.so` members. An ELF `.rodata` string has no ordering to preserve, so
  unlike the dex any byte would do; the head is taken because a C toolchain may
  tail-merge string literals, meaning a shorter string can be a pointer into
  this one's suffix, while a head is never shared. In the reviewed build the
  adjacent `com.google.android.gms` is a separate NUL-terminated string rather
  than a merged suffix, so nothing is shared either way. Offsets are read from
  each member under its own digest guard rather than recorded, and a member
  carrying the action twice is refused.
- **Cost.** Unity cannot read the advertising ID. That is analytics for a
  service retired years ago, and Unity already handles the bind failing --
  `Cannot bind to GooglePlayService.` is its own message for this path.
- **Also corrected: how to tell whether a build carries the flag.** On the
  separate-server route `/healthz` cannot answer it, and
  `user-data/local-server-plan.json` must not be used either -- it is rewritten
  by every setup run, so it describes the last build rather than the installed
  one. The installed APK is the only authority; see the troubleshooting guide.
- **Confirmed on hardware.** A Samsung Galaxy Tab A9+ (SM-X210) on Android 16,
  API 36, runs a *separate-server* build carrying all three edits -- the dex
  actions and both `libunity.so` members, verified by reading the APK the device
  is actually running -- through launch and real gameplay. That is the route
  with no host guard, so nothing masks the result, and it is the configuration
  the Galaxy S26 crashed in. It also retires the standing risk in editing
  Unity's binary at all: the patched `libunity.so` loads and the player runs
  normally.
- **What it does not establish.** No unpatched control was taken on this tablet,
  so the crash is proven on Android 16 by the S26 and the fix is proven on
  Android 16 by the tablet, on two different devices rather than one. An
  on-device combined APK cannot supply the control either, because its host
  guard catches the callback whatever caused the bind. The dex half stays, at no
  cost, rather than being removed on the strength of reasoning alone.

## 2026-08-06: Orbling Cavern and Cryptid Forest were gated behind a prefix scan

- **Confirmed defect, from repeated tester reports.** Neither area ever appeared
  on the world map. Both are complete content in the reviewed client, and the
  cause was entirely on the server side: it sent no event flag under either
  prefix the two map points scan, so neither point was ever constructed and
  nothing anywhere reported it.
- **Identity, Confirmed.** `ChapterInterface::.cctor` (ARM64 `0xD0741C`) sets
  `OrblingCavernChapter` 7000 / `OrblingCavernEndChapter` 7009 and
  `EidolonForestChapter` 7010 / `EidolonForestEndChapter` 7019. Chapter 7010 is
  Cryptid Forest; `EidolonForest` is the internal name, and the same naming trap
  is what once paid it a Lucky Orbling's Luck. Only 7000 and 7010 carry sections.
- **The gate, Confirmed.** `UIMap::InitPoints0` (`0xE6BB0C`) builds each point
  behind `EventManager.IsEnabledAny("sp_ch_700")` and `("sp_ch_701")`, a *prefix*
  scan over the `eventFlags` object login and status send: any key starting with
  the prefix and holding true passes. A second gate follows, the `openChapter`
  argument, which is 6 for Orbling Cavern and 5 for Cryptid Forest -- the same
  argument slot in which the neighbouring `CH35_SP_BOSS` point passes 35, which
  is what identifies it as a story chapter.
- **The selectors are client-owned, which is unlike every other area here.**
  `UIMapPoint::OnClickBtn` (`0xE75014`) opens `UISpecialSelect` mode 1 or 2, and
  `SetMode` (`0xF84588`) reads a hardcoded list for each: `.cctor` (`0xF8768C`)
  sets `orblingCavernQuestList` to `["7000-1", "7000-2"]` and
  `eidolonForestQuestList` to `["7010-1", "7010-2"]`. Neither mode consults a
  served list the way mode 0 consults `specialQuestList`, and no JSON key of
  either name exists in the client's string-literal table. The server can open
  the door and nothing else, so all four stages are `hidden`.
- **`battleCnt` 0 does not mean a placeholder, and reading it that way would
  have written Orbling Cavern off.** Its two sections declare zero battles, the
  signature this project once read as a stage with no battle program. Twenty-six
  of the 174 chapters declare all-zero `battleCnt`, and they include 2007, 2008
  and 2014 -- three implemented Archive events -- plus 6010 Lucky Orbling and
  6011 Yamamoto, all confirmed playable on hardware. What actually distinguishes
  a placeholder is whether the binary carries a `ChapterNNNN` class: 6006 has
  none, and 6007, 6010, 6011, 7000 and 7010 all do.
- **What each area is, Confirmed from the operator's own BattleData.** Both cost
  one stamina and zero Coins. Orbling Cavern's sections are titled
  `バルちゃん・Ο` and `グレース・Ο` and declare `dropBuddies` 75265 and 75777,
  decoding to Companion 294 and Companion 296 at one apiece -- Bahl OIII and
  Grace OIII, both carrying a master-data value of 1 against the 7,500 to 50,000
  their neighbours carry. Cryptid Forest's are `キリン・ビリ` and
  `キリン・ファンネ`, three battles each, empty manifests, `allowLucky` 1.
- **Cryptid Forest is the Dracorin job-material farm, and two independent
  recoveries say so.** `Chapter7010`'s constructor sets `JobItemDropRatio` 75,
  `luckyAddRate` 30, `luckyAddRateSpecial` 50 and `KirinChrID` 188;
  `Init_KR_KIRIN` (`0x1433628`) hands the engine items 150 and 151 at that ratio
  and `Init_KR_KIRIN2` (`0x1434160`) hands it 152 and 153. From the other
  direction, `JOB_UNLOCK_ROWS` -- read out of ChrDatabase long before any of
  this -- prices character 188's first job at items 150 and 151 and its second
  at 152 and 153, and character 188 is Dracorin. Section 1 farms the first job's
  materials and section 2 the second's.
- **The constructor also corroborates the 2026-08-05 Cryptid Forest finding
  from inside the binary.** `luckyAddRate` 30 is the record's 30% chance of a
  second Lucky Runner and `luckyAddRateSpecial` 50 is its Dracorin Λ *Cryptid
  Ruler* variant. Both are client-side, which is why the record's rates are
  observable and this server rolls neither.
- **Card art was never the problem.** All four `SpecialBanner` records --
  `sp7000-1`, `sp7000-2`, `sp7010-1`, `sp7010-2` -- are in the final 306-row
  catalog, and all four bundles are present in a retained resource tree. There
  is no repeat of the `sp1003` blank-card case here.
- **Correction.** `--cavern-forest` now sends the four per-section flags once an
  account has reached each area's chapter, and the four stages settle through
  the Hunting transaction. Per-section flags rather than chapter-level ones do
  both jobs at once: each answers its own card's `CheckQuestFlag` directly, and
  each also carries the prefix its map point scans.
- **Confirmed on hardware.** An operator reached both map points, opened both
  two-card selectors, cleared Orbling Cavern and received its Companion, and
  cleared Cryptid Forest with its job materials and Luck settling. The recovered
  identities, the two prefixes, the `openChapter` thresholds, the hardcoded
  selector lists, and the `dropBuddies` decode are therefore all confirmed by
  the original client rather than by derivation alone. It also settles the
  `battleCnt` question outright: Orbling Cavern declares zero battles and is
  playable, so that field does not mark a placeholder.

## 2026-08-05: Chapter 7010 is Cryptid Forest, and its Lucky enemy is a Runner

- **Confirmed defect, from the community record.** The `allowLucky` source paid
  every one of the five flagged chapters the Lucky *Orbling*'s +0.3 at the
  record's 50% pincer chance. Chapter 7010 is a Lucky *Runner* zone, so it has
  been granting three times the documented Luck, from the wrong enemy, on a
  coin flip where the record states a guarantee.
- **How the naming hid it.** 7010 is `ChapterInterface.EidolonForestChapter` in
  the client, and this repository recorded it under that internal name. The
  player-facing name is Cryptid Forest — 幻獣の森, the same 幻獣 the game
  translates as Eidolon elsewhere — and the record files the stage's enemies
  under the English name. Searching for "Eidolon Forest" finds nothing; the
  species was never checked. The `LUCKY_ENEMIES_PER_BATTLE` comment asserted
  that "the record names the Orbling on the flagged chapters it identifies",
  which was true of the four chapters anyone had looked at.
- **What the record states for Cryptid Forest**, enemy by enemy, and it is the
  only flagged chapter documented at this resolution: one Lucky Runner always
  spawns in a random battle; a second spawns with a 30% chance; pincering one
  *in any direction* grants 0.1 Luck to every party member. A 50% variant
  applies when the party carries Dracorin Λ's *Cryptid Ruler* skill, and
  resuming the quest after terminating the app suppresses the spawn — neither
  is implemented, because this server models neither party skills nor client
  lifecycle, and guessing at either would replace a stated rate with an
  invented one.
- **Scope of the correction.** 7010 alone. The other four keep the Orbling
  policy, and `roll_lucky_enemy_gain` keeps their draw sequence byte for byte:
  the chapter is not seed material and the Runner branch returns before the
  Orbling loop, so no chapter this finding does not name re-rolls. The invented
  `LUCKY_ENEMIES_PER_BATTLE` count is now scoped to the chapters where the
  record is actually silent.
- **Corollary, structural.** Callers passed `allow_lucky=stage.chapter in
  ALLOW_LUCKY_CHAPTERS` — a policy decision duplicated at each of the two call
  sites, which is what let the membership test and the species come apart.
  `roll_luck_up_table` now takes `lucky_chapter` and owns both.
- **Also recorded, not implemented.** Version 4.6.0 (2017-02-23) states that
  the Lucky Orbling became outflankable from four sides and that flanking order
  does not matter, which bears on the invented 0.5 the Orbling chapters still
  use. It is a dated primary source about a mechanic this server approximates;
  acting on it needs its own derivation.

## 2026-08-06: the Fellowship pool was flat, and one of its IDs named nobody

The bundled Fellowship roster was a single sorted tuple with no availability
data, so every member was drawable from the first pull. The community wiki's
"Availability by Chapter" table (operator-approved, `Pact of Fellowship`, in
the sense of `external-quest-reference-ledger.md`) describes the pool as
cumulative instead: completing a chapter adds that chapter's characters and
keeps every earlier one. Roughly half the roster was therefore reachable
earlier than the record says it should be — 54 of 103 members open at
Chapter 1, the remaining 49 spread across 21 later gates through Chapter 38.

- **Applied as bounded policy.** Each member now carries the earliest chapter
  that can draw it, and the draw route filters on `chapter_for_progress` of the
  account's own `progressCode` — the same `_chapterNo` low bits that already
  gate achievement claims and stage entry, not a new progress notion. Same
  evidence class as the rates alongside it: community record for a retired
  service, no APK table to cross-validate, because the server owned pool
  selection entirely. Truth carries no comparable availability record, so its
  pool stays whole rather than borrowing Fellowship's curve, and a
  user-supplied schema version 1 catalog has no availability data to honour, so
  an operator's pool is still served whole — the same restraint the Fate/Luck
  refusal in the draw route already applies.

- **Corrected: character ID 122 was not a character.** The roster carried 122,
  which names nothing in the decoded name table and appears in no character
  catalog; 126 (Megacell, Chapter 15, class B) was absent. The surrounding run
  is 123/124/128 against a wiki cluster of Regenercell, Mechavirus 3721,
  Megacell, Wastecell, so this reads as a transcription slip of 126 to 122.
  Megacell was unobtainable from Fellowship, and roughly one pull in 103 minted
  a `chrdata` row for a character the client has no master data for.

- **What found it, and what now enforces it.** A count check passes on the
  broken table — 103 against 103. The error surfaced only by resolving the
  wiki's *names* to IDs through the operator's decoded name table and then
  cross-checking each matched ID's recovered `rarity` against the wiki's class
  column, under the D/C/B/A/S/SS/Z = 2--8 banding this bundle already
  documents. All 103 agree on class, which is what makes the roster itself
  corroborated rather than merely transcribed. `validate_bundled_pools` now
  refuses to start a Pact-enabled server when any bundled pool member does not
  resolve in the operator's own character catalog. It is deliberately not part
  of `build_bundled_pact_policy`, which stays tolerant of a partial mapping:
  an unclassifiable member is a documented gap in *weighting* policy, whereas
  an unresolvable one is an inconsistency between two documents describing the
  same client, and this project fails those visibly.

- **Not addressed.** Whether Truth has its own availability curve is unread;
  its pool resolves completely (122 of 122) against the operator's catalog, so
  only membership timing is open. The wiki's own caveat — that Pact
  availability is not the same as where a monster can be recruited in game —
  means this table bounds the Pact and nothing else.

## 2026-08-07: the Companion rare pool drew uniformly, inverting its own rates

- **Reported empirically, then confirmed statically.** A tester reported 12
  Companion Ticket pulls returning 5 Z, 4 S, 2 A, 1 B, and a second reported
  five Z in one ten-pull against a single low-class result. Both are ordinary
  outcomes of the pool as it was served and near-impossible under the rates the
  service displayed: the observed 12 are about 54,000 times more likely under
  uniform selection than under the displayed table, and five Z in twelve has
  probability 3.6e-2 uniform against 1.6e-5 displayed.

- **Cause.** `build_bundled_companion_draw_policy` gave every rare-slot member
  weight 1, so `_draw_companion_id` selected uniformly across pool
  *membership* rather than across rarity *class*. The rare pool is lopsided the
  opposite way from its rates — 50 of its 114 members are S and only 2 are B —
  so uniform selection returned Z at 16.7% against a displayed 3%, and B at
  1.8% against a displayed 49%, inverting the two commonest outcomes. The
  Companion Ticket was incidental: kinds 1 and 21 resolve to the same pool
  through `draws_for_kind`, so the ticket changes who pays and never selection.

- **Why it was uniform, and what changed.** The pool's per-class counts were
  already documented, but the bundle stored no map from ID to class, and
  applying the displayed table without one was not possible. `BuddyData.rarity`
  carries it, on the same master object the bundled membership, base Coin
  values, progression values, and evolution recipes already come from, so
  bundling it is the evidence class this project already ships rather than a
  new one. The 114 IDs are now grouped by that recovered field, and each
  class's displayed share is split evenly across its own members.

- **What corroborates the map.** The recovered `rarity` field groups the pool
  as 19 Z, 13 SS, 50 S, 30 A, 2 B, which is exactly the split the community
  record states, and the normal pool as 41 C and 40 D, also exactly. Grouping
  the roster by class rather than listing it flat makes that agreement
  structural: a transcription error in either document now shows up as a group
  of the wrong size, and a test asserts the five counts.

- **Not addressed.** The displayed table also carried a per-Companion rate,
  which does not survive in the record, so an even split within a class remains
  local policy — the same caveat the Pact of Truth shares carry.

- **Does not apply here, unlike the character Pact.** The Pact of Truth shares
  carry a second caveat, that the pool shrank as characters hit 100% Skill
  Boost and left it, redistributing their share. That one is implemented, in
  the Pact draw route: selection runs over an `eligible` list filtered on the
  account's own `skillBoost` against `max_skill_boost` — or `luck` against
  `max_luck` for Fate — and an exhausted pool answers `errorCode` 3. It has no
  Companion counterpart because Companions have no Skill Boost to cap. Their
  owned record is `bid`/`lv`/`date`/`iid`/`exp`/`flag`/`chrID`, and they are
  instanced rather than unique per master: a draw mints a new `iid` and an
  account may hold a thousand, so no per-master state exists that could max out
  and leave the pool. Companion strengthening is levels and EXP through the
  same-Companion and ByeBye multipliers, a different mechanic entirely.

- **Also not addressed.** The normal pool stays uniform
  deliberately: no displayed-rate record was found for it, and its two classes
  are near-evenly sized, so a uniform draw is already close to whatever the
  service did.

## 2026-08-07: the Power-Up Item slot was gated on a constant nobody sent

**Reported symptom.** The pre-battle screen showed no Power-Up Item field
above Start Battle, on an account holding Disarmers, with no sign the feature
was progress-locked.

- **Confirmed by ARM64 disassembly of the reviewed client.** The field is
  gated on exactly one server constant and nothing the account owns.
  `UITeamPopup.<Setup>c__Iterator2.MoveNext` calls
  `UITeamPopup.IsHelpItemEnabled` (RVA `0xD65A08`) and caches the answer into
  the popup's own `helpItemEnabled` field (offset `0x180`), which drives
  `helpItemRoot`. The predicate is three terms: false if
  `GameManager.GetCurrentChapter().InWMSpecial()`, false if
  `UserData.helpItemEnabled` (static, offset `0x1F0`) is zero, otherwise
  `!TutorialManager.InTutorial()`. That static is fed from the status route's
  `constants` block, which had never carried a `helpItemEnabled` key — so it
  stayed false for every account regardless of inventory or progress.
- **Confirmed by the same disassembly — the wire form the flag makes
  reachable.** `AppServerUtil.<StartQuest>c__Iterator20.MoveNext` (`0xFC4D24`)
  builds the start body in insertion order `stamina`, `coins`, optional
  `itemID`/`itemCount`, optional `helpItemID`, `chapter`, `section`, then the
  multiplayer and weekly-challenge fields. `helpItemID` is emitted **only when
  it is at least 1** (`cmp w8, #1; b.lt`), which is why every start seen
  before this change parsed: with the field hidden the value was always zero.
  Enabling the flag without extending the parsers would therefore have refused
  the battle whenever a power-up was chosen. Field names were recovered by
  resolving the GOT slots behind each `Dictionary.set_Item` key against
  `script.json`'s `ScriptString` table.
- **Confirmed by the client's own master data — the acceptance set.**
  `UIHelpItemSelect.MakeList` walks the account's held items, calls
  `ItemSet.GetItem`, and keeps only rows whose `ItemData.kind` (offset `0x14`)
  is `ItemKind.HelpItem` (1). Reading `ItemSet.itemSet` out of the reviewed
  `data.unity3d` gives exactly eight such rows; item IDs are one-based, so the
  set is 53 Time Extension, 54 Disarmer, 55 EXP Boost, 56 Coin Boost, 166
  Reinforcement Alika, 167 Reinforcement Gugba, 172 Reinforcement Bajanna, and
  180 Reinforcement Zeera. The community record's "Power-up items" category
  lists the same eight and adds that only one may be used at a time, which is
  what the single `helpItemID` field already implies. The seven
  `ItemKind.UsableItem` rows are the same seven the record calls candy items.
- **Confirmed — the spend belongs to the server.** `UITeamPopup.SetHelpItem`
  (`0xD69B58`) only paints the slot: labels, sprite, scale, and a confirmation
  dialog. It never touches a held count. The start response's `itemList` is
  fed to `UserData.LoadItemlistFromJson`, and every field in that callback is
  guarded by a `ContainsKey` check, so an absent `itemList` is safely ignored
  and a present one replaces the client's whole inventory. The debit is
  therefore committed at start and reported back, and the following clear
  submits the count the server produced. No stale-count reconciliation is
  needed, unlike the Metal Ticket, whose slot the client does repeat stale.

**Local policy.** All eight IDs are accepted. An ID outside the set is a
wire-form refusal (`unsupported_start_quest` / `unsupported_hunting_start`)
because `UIHelpItemSelect` cannot offer one; an ID the account does not hold is
the soft `cmdError` 2 shape, so a client that asks for something it was not
offering sees its own refusal rather than a Network Error. A power-up named on
a World-0 map special is refused, matching the client's `InWMSpecial` term.
What the items *do* is entirely client-side; the server authors no effect.

**Related gap, not closed here.** Candy items (161, 162, 163, 168, 175, 176,
177) and the four Reinforcements have no local source. Story stages cannot
drop them — the 780 recovered `item_maxima` rows top out at item 165 — and
neither can Huntland, Daily Quests, or the Trading Post. Their historical
sources were Tower of Temptation milestone rewards, Melting Pot Lizardfolk,
and Ultimate Five Luck chests. Tower's 12 stages carry no reward channel at
all in the generated event catalog, consistent with those rewards being
condition-counted and service-authored rather than client-side drop programs;
they are recoverable only as bounded local policy from the community record,
the way the Trading Post already is. The server has always supported *spending*
candy through `use_statusup_item`.

## 2026-08-07: Chapters 9100--9102 are Melting Pot, and their candy is recovered

Two earlier readings are corrected here. The chapter *range* was right; what
sits in it, and what that costs, were not.

- **Confirmed by BattleData titles.** Chapters 9100, 9101, and 9102 are
  `[るつぼの都] トカゲ`, `ケモノ`, and `ヒト` -- Melting Pot: Lizardfolk,
  Beastfolk, and Human -- fifteen sections each. Section economics match the
  community record quest for quest: five battles per section, 5 stamina rising
  to 15, assumed levels 15/15/25/25/35 and upward. `parentQuest` chains each
  section to its predecessor, which is the record's "unlocked in order". They
  were previously recorded as "the 45 Donation sections" from the chapter range
  alone; the count was right and the identification was not.
- **Confirmed by ARM64 disassembly -- the Donation blocker is dead code.**
  `ChapterInterface..cctor` does assign the range: `TowerOfTemptationChapter`
  9010 / `TowerOfTemptationEndChapter` 9099, `DonationQuestChapter` 9100 /
  `DonationQuestEndChapter` 9199, and `NumOfDonationQuestSections` 15 -- the
  client hard-codes the section count these chapters have, so no server list
  needs to supply it. But the two consumers cited as the reason Donation "could
  not be recreated by a generic quest list" do nothing in the final build:
  `UISpecialItem.DispDonationQuest` (`0xF833F0`) is a single `ret`, and
  `EventManager.GetDonationQuestAmount` (`0xD9749C`) and
  `ChapterInterface.InDonationQuest` (`0xD06518`) have **no callers at all**.
  `GetDonationQuestAmount` also returns 0 when `GetQuestParam` finds nothing,
  so a server that authors no donation state cannot fault it.
- **Confirmed -- what `IsDonationQuest` still does.** Four call sites, all
  selector presentation: `UISpecialSelect.GetSectionCount` (returns the
  hard-coded 15), `UISpecialSelect.InitItems`, `UISpecialSelect2.HasBanner`,
  and `UISpecialSelect2.<GetList>`, where it sets a flag that makes the list
  fetch `get_special_event_param` before rendering. That route already exists
  in the bootstrap profile and answers from a canned signed response.
- **Confirmed -- the candy drops are recovered, not service-authored.** An
  earlier reading of this project's own evidence concluded candy was authored
  by the retired service, because none of the 1,930 enemies carrying
  `EnemyParams.items` names a candy ID. That is true and misleading: Melting
  Pot attaches its drops *per spawn*, in the chapter program, through
  `ChapterBase.SetDropItem(Entity, int itemIdx, int dropRatio, int[] itemList)`
  at managed vtable slot 109. The immediates are literal:
  - `Chapter910x.Init_DROPPOD` -- the record's "Candy Pot" -- builds
    `new int[3] {175, 176, 177}` and calls `SetDropItem(e, 0, 100, ...)`: one
    of Level, Skill, or Luck **Candybox**, at a 100 drop ratio. The record says
    "Candy Pot drops one of the following" and lists exactly those three.
  - Six boss spawns per race (`Init_SP9100_2_YAPKAR`, `_3_SHBER`, `_5_AMISAN`,
    `_6_RAPROW`, `_8_RZONAND`, `_9_MACURI`, and the 9101/9102 equivalents)
    build `new int[3] {161, 162, 163}` and call `SetDropItem(e, 1, 3, ...)`:
    one of Level, Skill, or Luck **Candy**, at a 3 drop ratio.

  Sixty-six such sites exist across the three chapters. This is the same class
  of evidence the story chapters' drop ceilings rest on, read from the same
  `Init_*` spawn methods `native_encounter_importer` already disassembles --
  it is simply attached at the spawn rather than on the shared enemy master.

**Local policy.** The three chapters are generated and advertised as ordinary
local events under `projected_rewards`, the same settlement Counter Descent
uses and for a weaker reason than Melting Pot can offer: Counter Descent has no
recovered reward basis at all, while these two rates and six item identities
*are* recovered. Bounding the stages by them would need the importer to record
`SetDropItem` operands alongside spawn identity, which it does not yet do; the
rates are written down here so that work has a source when it happens.

**Still not recovered.** `Chapter910x` carries `enablePot`, `potRatio`,
`donationOptionLists`, and `winRatioLists`. Whatever community-aggregate
mechanic those served is not reconstructed, and nothing here claims it was.
What is asserted is narrower: the fifteen sections per race, their economics,
and their per-spawn drops are all in the client, and none of the three dead
Donation consumers can refuse them.

## 2026-08-07: two client gates the server had never fed

Both were reported together by a tester holding a Luck Candybox from Melting
Pot's Candy Pot, and they turned out to be the same shape as the Power-Up Item
slot above: a client feature gated on a server field this project had never
sent, failing as a flat refusal rather than an error.

### The candy items could not be used on any character

**Reported symptom.** "Luck Candybox says I can't use it on any characters."
The item is held, the item-use screen opens, and the character list is empty.

- **Confirmed by ARM64 disassembly -- the filter is one lookup.**
  `UIChrSelectWindow.GetFilteredList` (`0xEF4BEC`) keeps a character in mode 7
  (`ItemUseChrSelect`) only when `CalcMaxUseNum` (`0xEF82BC`) returns at least
  one. That method's first act is
  `UserData.statusUpItems.Contains(itemID.ToString())`, and a miss returns zero
  before any character state is read. Every held character therefore fails,
  which is exactly "no characters", with no dialog to explain it.
- **Confirmed -- the table is the server's, not the client's.**
  `UserData.statusUpItems` is a static `JsonData` filled by
  `UserData.SetServerConstants` (`0x19D2A74`) from the status route's
  `constants` block, key `statusUpItems`, and set to an *empty* `JsonData` when
  the key is absent (`0x19D4474`). The block this server sends had never
  carried the key. The seven item effects themselves were already recovered and
  already applied by `use_statusup_item`; only the client's own gate was
  missing, so the server would have settled a use the client refused to offer.
- **Confirmed -- the row shape, positionally.** `CalcMaxUseNum` reads
  `statusUpItems[id]` as an array: `[0]` job levels against `ServerConstants.levelCap`,
  `[1]` displayed Skill Boost percent against `Character.get_skillBoostRatio`
  and 100, `[2]` displayed Luck percent against `Character.get_luckMax`/10 and
  `get_luckRate`, `[3]` the designated species, compared against
  `Character.GetJobParam(-1)` and skipped when below 1. All four are required
  here: `IsStatusUpItemsDesignatedSpeciesImplemented` (`0x19D7348`) is true
  whenever both advertised client versions exceed 4.99, and the status route
  advertises 5.57, so a three-value row is read as species 1000 and matches
  nobody. The values are read through LitJson's `int` accessor, which raises on
  a JSON double.
- **Local policy.** The key is sent only while a status-up policy is loaded, so
  the client offers exactly the items `use_statusup_item` would settle rather
  than a row the route answers with a 501. The projection is derived from that
  same policy, so one table drives the client's gate and the server's effect.

### No chained event section could ever open

**Reported symptom.** "Despite clearing the first stage, the second stage
didn't open up" -- Melting Pot Lizardfolk stayed one section long.

- **Confirmed by ARM64 disassembly.** `UISpecialSelect.IsQuestOpen`
  (`0xF84D84`) resolves `BattleData.Chapter.GetSection` for the id it is asked
  about and, when that section's `parentQuest` is not empty, returns false
  unless `UserData.GetQuestClearDate(parentQuest)` (`0x19D8ADC`) is nonzero. It
  is called from `UISpecialSelect.<GetList>` and `UISpecialSelect2.<GetList>`,
  so a section that fails is not greyed out -- it is never listed.
- **Confirmed by BattleData.** Read through the same type trees
  `battledata_importer` uses, Melting Pot's sections chain
  `9100-1 <- 9100-2 <- ... <- 9100-15`, and identically for 9101 and 9102.
  Tower's 9000/9003 sections chain the same way. Section 1 of each carries an
  empty `parentQuest`, which is why the first section, and only the first, was
  ever reachable.
- **Confirmed -- the map is server state.** `UserData.questClearDate` is filled
  by `AppServerUtil.LoadUserdataFromJson` (`0xDB6010`) from `userdata`'s
  `questClearDate` object, and refreshed by the clear callback
  (`AppServerUtil.<ClearQuest>`, `0xDC0FE0`) from the same key in the clear
  response. This server had never written either, and nothing else in the save
  recorded which stages had been cleared.
- **Confirmed -- the value must be a decimal.** `GetQuestClearDate` reads the
  entry with LitJson's `double` accessor (`0xFF4F84`), which throws
  `InvalidCastException` on `JsonType.Int` rather than converting it. An
  integer stamp would fault inside the client's response parsing, the same trap
  `jobLevels` carries. `save_validation` now checks the map for it.
- **Local policy.** Every stage clear the server settles -- generic story and
  event (`clear_quest`), Hunting, and the Chapter-1100 Roads, which all reach
  the client through that one route -- stamps `"<chapter>-<section>"` with the
  settlement instant and restates the whole map in its response. Nothing
  reconstructs clears that predate this: an account that cleared a section
  before the change re-stamps it by clearing it again. The tutorial
  transitions, which are profile-canned rather than identity-settled, are left
  alone; the ordinary story is gated by `progressCode`, not by this map.

## 2026-08-08: two settled mutations answered without `success` and hung the client

**Reported symptom.** A Luck Candybox could finally be used, and confirming it
left the client on the "Connecting" overlay forever. Restarting showed the use
had been applied in full -- the item spent, the Luck gained -- so the request
had been settled and answered before the client stopped.

- **Confirmed by ARM64 disassembly -- `success` is the one unguarded read in
  the transport.** `AppServerUtil.<callAPI>c__Iterator4D.MoveNext` parses the
  body and immediately casts `json["success"]` to bool at `0xDBE174`, with no
  `Contains` ahead of it. Every field after it is guarded: `lastupdate`
  (`0xDBE4B0`), `cmdError` (`0xDBE5B0`), and each key the endpoint callbacks
  read. LitJson's string indexer raises `KeyNotFoundException` on a miss, and
  the bool cast (`0xFF4EEC`) raises `InvalidCastException` on anything that is
  not `JsonType.Boolean`, so the key is required and no default exists.
- **Confirmed -- why it presents as a soft lock rather than an error.** The
  throw happens inside the transport coroutine, after the mutation has been
  settled, persisted, and answered. The endpoint callback never runs, so
  nothing takes down the `UILoading.ForceShow` overlay the screen raised before
  the request (`UIChrSelectWindow.<ShowItemUseDialog>`, `0xEAE638`), and the
  retry/error dialogs live on paths that were never reached. This is the
  freeze half of the pair recorded for refusals: an unsigned refusal reads as
  Network Error, a thrown parse reads as a hang.
- **Confirmed -- the scope was exactly two routes.** `use_statusup_item` and
  `achived` were the only signed bodies this server ever emitted without a
  `success` key; every other route either sets it or carries an `errorCode`
  that `_endpoint_refusal_envelope` already rewrote into
  `{"success": true, "cmdError": n}`. Neither had been exercised by a real
  client: the candy route was unreachable until `statusUpItems` was sent the
  day before, and no tester had claimed an achievement.
- **Confirmed -- nothing else in the flow disagrees.** The rest of the
  status-up response was already the shape the client reads:
  `<UseStatusUpItem>` `<>m__0` (`0xFC8058`) takes `chrdata`, `itemList`, and
  `resultValues`, each `Contains`-guarded; `UIUseItemResultWindow.<ShowMsg>`
  (`0x10ECA08`) walks `addedLevels` as `((IDictionary)levels).Keys` and casts
  each value with the *int* accessor, which is what an object of
  `"<jobIndex>": <int>` provides; `addedSkillBoost` and `addedLuck` are read
  the same way. `Character.LoadFromJson` (`0xD07C5C`) reads `id`, `jobID`,
  `skillBoost`, `flags`, `buddy`, `luck`, and `plusCount` as ints, `date` and
  `jobSlots` as doubles, and tests `IsInt` per `jobLevels` entry before
  choosing an accessor.

**Local policy.** The key is stamped in the wire layer rather than at each
route, so a route cannot reintroduce the hang by forgetting it. A payload that
carries no verdict of its own is answered with the one it was returned under;
an explicit `false` is left untouched, and an endpoint refusal code still
rides `cmdError` exactly as before.

## 2026-08-08: the two Roads declare a species lock, and nothing asserted it

Reported alongside the Captive Golem class band, as a suspected second case of
the same defect. It is one, but it is a different field and a different code,
so the class fix did not touch it.

- **Confirmed by BattleData -- the Roads are the only species-locked sections
  in the game.** `BattleData.Section.species` is 128 on 1200-1 and 256 on
  1201-1 and zero on all 783 other sections, read through the same type trees
  `battledata_importer` uses. The value is a bit per `Species` enum member:
  128 is `1 << Dragon` (7), 256 is `1 << Machine` (8), which is what the
  sections' own titles say -- `ドラゴンロード` and `メカロード`. Their
  `classMin`/`classMax` are both zero, so the recovered class band does not
  reach them and never would have.
- **Confirmed -- neither limit can be produced by the client.**
  `AppServerUtil.StartQuestErrorCode` carries `ClassLimit` (4) and
  `SpeciesLimit` (6) as siblings, but the only local start gate,
  `AppServerUtil.IsEnableToStartQuestLocal` (`0xDB0984`), calls
  `BattleData.Section.get_stamina`, `EventManager.GetBoolean`,
  `UserData.get_coins`, `UserData.GetItemCount` and
  `MultiplayUserData.GetVsStaminaAndFillSec` -- it walks no party and reads
  neither field, so it can raise neither code. Both limits were the retired
  service's to assert, and this server asserted neither.
- **Confirmed -- the species map needs no new input.** Each character's
  `Species` is already recovered per character in
  `statusup_character_data.STATUSUP_CHARACTER_ROWS`, taken from its base job
  row, which is the same reading the status-up species gate uses. 346 rows,
  including 24 Dragons and 23 Machines.

**Local policy.** The masks are recovered into `SECTION_SPECIES_LIMITS` and
applied by stage identity when a catalog is built, so the bundled policy and an
operator's own hunting catalog both carry the limit without restating it. A
start whose party breaks the lock is refused before anything is charged, under
the client's own `SpeciesLimit` code in the soft shape the Daily Quest rotation
uses, so it reaches the player as the game's dialog rather than a Network
Error. A character the recovered table cannot describe is not refused: this
restores a declared limit, it does not invent one for state it cannot read.

**Worth stating plainly, because it is a visible change.** Dragon Road was
being used as a general-purpose EXP route for any party. That was possible only
because the limit went unasserted; the game declares otherwise. Nothing about
either Road's rewards, stamina, or unlock changed.

## 2026-08-08: Strikes Back cards never expanded, so only tier 1 was reachable

**Reported symptom.** "Are the Strikes Back higher level stages active? I have
all of the stage 1s unlocked, but I assume the higher stages unlock later."
They were not gated on later progress. They were unreachable.

- **Confirmed by ARM64 disassembly -- the client folds on the shape of the id
  alone.** `UISpecialSelect.IsFolded` (`0xF821DC`) is exactly
  `!id.Contains("-")`; the `"-"` literal resolves through the GOT relocation at
  `0x2AD43D8`. `UISpecialItem.OnClickedBtn` branches on it at `0xF81DD4`: a
  folded id builds a tier sub-list from
  `GetSectionTitlesIfSpecialFoldedQuest` or, failing that,
  `GetSectionCount` and `Concat(chapter, "-", i)`; an unfolded id calls
  `UISpecialSelect.StartSpecial` on that one stage. This server advertised
  `8000-1`, which carries a section, so every Strikes Back card was an
  ordinary single-stage row. Tapping it started tier 1. Tiers 2 and up were
  never drawn, and no amount of story progress would have drawn them.
- **Confirmed -- the list builder has the matching branch.**
  `UISpecialSelect.<GetList>c__Iterator0.MoveNext` calls `IsFolded` at
  `0xF897C8` and, for a folded row, admits the card when `IsQuestOpen(chapter)`
  holds or, failing that, when any `IsQuestOpen("<chapter>-<i>")` for `i` in
  `1..GetSectionCount` does (`0xF89818`--`0xF898B4`). A section-less id is
  therefore safe: `IsQuestOpen` (`0xF84D84`) splits on `"-"` and tests
  `parts.Length >= 2` at `0xF84FD0` before it reads a section at all.
- **Confirmed -- the tiers inside the card are gated individually, and the
  chapter key answers for all of them.** `IsQuestOpen` builds its key as
  `Concat("sp_ch_", id)` (`0xF84F04`) for whatever id it is handed, and the
  expanded sub-list runs through
  `UISpecialSelect2.<GetList>c__Iterator0.MoveNext` (`IsQuestOpen` at
  `0xD5422C`) with `UISpecialSelect2.UpdateItems` revalidating by
  `CheckQuestFlag` every frame (`0xF8AD8C`). `CheckQuestFlag` (`0xF85108`) is
  `GetBoolean(key)` or, failing that, `GetBoolean(key.Substring(0,
  key.LastIndexOf("-")))` -- the chapter fallback `event_flag_data` already
  documents. So the chapter key alone would have kept the tiers on screen; it
  was never the missing half. `sp_ch_8001-2`, `-3`, and `-4` are in the
  community flag table, so the retired service named sections individually
  anyway, and the next entry is why that matters.
- **Confirmed -- the client's tier count is hard-coded and wrong for half the
  families, and the chapter fallback is what makes that dangerous.**
  `UISpecialSelect.GetSectionCount` (`0xF82328`) parses the chapter and, for
  `ChapterInterface.IsCounterDescentQuest`, returns
  `NumOfCounterDescentQuestSections`, which its `.cctor` sets to 5 at
  `0xD07608` across the whole 8000--8999 range (`0xD07588`, `0xD07598`).
  Chapters 8012--8017 have three sections in BattleData, so their cards expand
  to `-4` and `-5`, which no section backs. `IsQuestOpen` does not drop those
  on its own: a null `BattleData.Chapter.GetSection` skips the parent test and
  tail-calls `CheckQuestFlag` at `0xF85040`, so a chapter key would answer true
  and offer a tier with no stamina, no battles, and a `start_quest` this server
  refuses. Withholding the chapter key is the only thing that removes them.
- **Confirmed by BattleData -- no clear-order chain is involved.** Read through
  the same type trees `battledata_importer` uses, every section of Chapters
  8000--8018 carries an empty `parentQuest`, unlike Tower 9000--9003 and
  Melting Pot 9100--9102, which chain. The `questClearDate` gate that hid
  Melting Pot's later sections does not reach Strikes Back.

**Local policy.** `descentHuntingList` now advertises the bare chapter, and
login flags one `sp_ch_<chapter>-<section>` per section the catalog declares
and no chapter key -- the only family here flagged that way, and deliberately
so. The card still lists, because `<GetList>` and `UpdateItems` both admit a
folded row on any open tier, and the two phantom rows on a three-tier family
fail the gate that a chapter key would have passed for them.

`IsEnableToStartQuestLocal` (`0xDB0984`) is unaffected: its one
`EventManager.GetBoolean` reads `multiplay_stamina_zero` (`0xDB0A0C`) and no
`sp_ch_` key, so withholding the chapter flag reaches presentation only.

No unlock schedule changed -- the families still open on their existing Chapter
5--18 gates, and all of their tiers were already accepted by `start_quest`.

## 2026-08-09: the side worlds were open and unreachable, and three contracts settle it

**Reported symptom.** Entering an Ultimate Five quest refuses and the client
shows its transport dialog. The stages had been served since 2026-08-02 behind
`--secondary-worlds`, so the report read like a stage-catalog gap. It was not.
The menu that reaches them could never have appeared, and had it appeared, every
clear behind it would have been refused.

The three questions this project had left open -- and had declined to guess at,
in the note beside `maxChapter` in `server_constants.py` -- are all answered
below from the reviewed 5.5.7-170 `libil2cpp.so`. None of them needed a client
on an emulator; all three are readable in the handlers themselves.

- **Confirmed -- the menu predicate reads a userdata key the server never
  sent.** `UIMap.IsWorld1ChangeEnable` (`0xE67EB8`) is
  `IsMatsunoQuestEnabled() && UserData.instance.IsSectionUnlocked(26, 1) &&
  EventManager.GetBoolean("sp_matsuno")`, and `IsWorld2ChangeEnable`
  (`0xE67FA8`) is the same shape with `IsFiveEmperorsQuestEnabled()`,
  `IsSectionUnlocked(20, 1)`, and `"sp_five_emperors"`. Both thresholds are
  literal `mov w1` immediates, so the two unlock gates are recovered rather than
  the community claim they were labeled as. `IsSectionUnlocked` (`0x19D7684`)
  resolves the chapter to a world through
  `ChapterInterface.GetWorldNoByChapter` and compares against
  `GetWorldChapterNo` / `GetWorldSectionNo`, which read `worldProgressCode`
  (field `0x98`) and nothing else. `InitData` allocates that array zeroed, so
  with the key unsent both predicates were false for every account and the flags
  alone opened nothing.
- **Confirmed -- `worldProgressCode` is an object keyed by world index, not the
  array its `int[]` declaration implies.**
  `AppServerUtil.LoadUserdataFromJson` (`0xDB6010`) tests the key, then walks
  the value's `Keys`, calls `System.Int32.Parse` on each key
  (`0xDB6604`), reads the element with the *string* `get_Item`, and stores it at
  the parsed index after a length check (`0xDB6658`). LitJson's `Keys` throws on
  a JSON array, which is the boot hang another reimplementation reported and
  which this project could not previously reproduce in either direction.
- **Confirmed -- the value packing is the client's own, and it is the story
  packing.** `UserData.SetWorldNewChapter` (`0x19D8680`) writes
  `(section & 0x3F) | (chapter << 6) | 0x3000000` and `GetWorldChapterNo` /
  `GetWorldSectionNo` read the halves back with `(v >> 6) & 0x3FF` and
  `v & 0x3F`. Bits 24 and 25 are `newStage` and `showProgress`, exactly as in
  `progressCode`. `InitData` seeds world 1 at 100-1 and world 2 at 110-1.
- **Confirmed -- `worldMaxChapter` is an int array indexed by world, in internal
  chapter numbers.** `UserData.SetServerConstants` (`0x19D5EF4`) reads it with
  the integer `get_Item` over `0..Count` into a `List<int>` and calls
  `ToArray`, so this one *is* a JSON array. `get_worldChapterNo` (`0x19D7938`)
  clamps the world's chapter against `worldMaxChapter[worldNo]`, which settles
  the other open question: internal chapter numbers, not per-world display
  indices. Index 0 is never read -- both consumers, `get_worldChapterNo` and
  `NeedShowProgress` (`0x19D8EB0`), branch away when `worldNo` is zero.
  `SetServerConstants` then force-writes index 2 to `114` unless
  `EventManager.GetBoolean("sp_five_emperors2")` holds (`0x19D6080`--`0x19D6140`),
  which is what the second Five Emperors flag actually buys: the five hard
  descents, 115--119.
- **Confirmed -- `WORLD_NUM` is not a server constant.** It reads like one:
  `public static int WORLD_NUM` sits at `0x200` beside `worldMaxChapter` at
  `0x1F8`. But the build carries no `WORLD_NUM` string literal at all, and
  `UserData..cctor` assigns the literal `3` at `0x19DE500`. There was never
  anything to send.
- **Confirmed -- the world cursor is `worldMapNo`, and moving it is a write the
  server was refusing.** `UIMap.SetWorld` (`0xE65890`) compares
  `UserData.instance.worldNo` against the requested world and, when they differ,
  writes it (`0xE65984`) and calls `SetDirty(8)`.
  `LoadUserdataFromJson` stores the parsed `worldMapNo` into that same field
  `0x80` (`0xDB6314`), and `SerializeJsonUserData` (`0xDB54D8`) writes it back
  out. So a swap posts the three-field `progressCode` / `worldMapNo` /
  `lastUpdate` write with a new world, and every clear afterwards carries it.
  This server compared that value against a stored zero in four places and wrote
  it in none, so the swap was refused and then so was everything after it.
- **Withdrawn -- "the client never sends its world progress back."** A
  whole-`.text` scan for the `worldProgressCode` literal does find exactly one
  site, `LoadUserdataFromJson`, and that reading was wrong: the value comes back
  under a different name. See the correction below, which is what made both maps
  unusable after the menu opened.

**Correction: `progressCode` is two fields wearing one name.**

Reported after the menu fix shipped: the Ultimate Five row appears and opening
it answers a Network Error. The tester's save named the half that was still
broken -- `worldMapNo` was still `0`, so the swap had never been accepted --
while the server refused nothing when driven with the body this project
*believed* the client sent.

`AppServerUtil.SerializeJsonUserData` (`0xDB4674`) does not send
`UserData.progressCode` for `UserDataKind.Progress`. At `0xDB47C4` it sends
`UserData.GetWorldProgressCode()` (`0x19D9394`), which reads `worldNo` at
`+0x80` and branches:

- **`worldNo == 0`** rebuilds the story code from `chapterNo` (`+0x88`),
  `sectionNo` (`+0x8C`) and the two banner bytes at `+0x90`, which is the value
  this server always expected.
- **`worldNo != 0`** returns `worldProgressCode[worldNo]` after a bounds check
  against the same three-element array.

So the field carries the *world's* cursor on the swap that arrives at a map, on
every Progress flush after it, and on the clear each side-world battle posts.
Three separate comparisons against the stored story code -- the cursor write,
the reveal fallthrough, and the Hunting clear -- were therefore guaranteed to
fail for any player who left world 0. The menu opened onto a refusal, and had
the swap succeeded, every battle behind it would have been refused too.

- **Confirmed -- `ChapterInterface.GetWorldNoByChapter` (`0xD062E4`) has no
  world 2.** It is four instructions, `(unsigned)(ch - 100) < 10`, so chapters
  100--109 answer 1 and everything else answers 0 -- including 110--119, which
  `InitData` itself seeds as world 2. The Five Emperors shipped behind a later
  version gate (5.19 against Matsuno's 4.89) and this function was never
  extended. Its five callers are all cosmetic for this purpose: a shader pick,
  a level label, `UISectionSelect.CheckWorldChange` (which tests only for world
  1), and `IsSectionUnlocked` / `IsSectionCleared`, neither of which the map
  points or the stage-entry path consult. Nothing server-side may copy the gap,
  because `world_for_chapter` decides which world a clear advances.
- **Confirmed -- the two menu predicates are version gates on served
  constants.** `IsMatsunoQuestEnabled` (`0x19D69A8`) and
  `IsFiveEmperorsQuestEnabled` (`0x19D6A58`) each require *both*
  `UserData.currentVersioniOS` (`+0x0`) and `currentVersionAndroid` (`+0x4`) to
  exceed a rodata float: `4.89` at `0x21DAB40` and `5.19` at `0x21DAB44`. Those
  two statics are the `currentVersion_iOS` / `currentVersion_Android` keys this
  server sends, so `FINAL_CLIENT_VERSION` is load-bearing for both maps --
  5.57 clears both, and any value below 5.19 would make both rows vanish with
  no other symptom.
- **Confirmed -- static methods in this build take their first declared
  argument in `w1`.** `x0` is passed zero and the `MethodInfo*` goes in `x2`.
  Read off the `GetWorldNoByChapter` call site inside `IsSectionUnlocked`
  (`0x19D76E4`) and confirmed against `IsExpQuest`. Reading `w0` as the first
  argument inverts every one of these predicates.

**What changed.** `worldMaxChapter` is served with the worlds; `worldProgressCode`
is projected onto every userdata read, with world 0 derived from `progressCode`
and worlds 1 and 2 held in a new `world_progress` account key behind an explicit
migration; the three-field write is accepted when it moves only the cursor; and a
secondary-world clear advances that world's cursor and nothing else.

Three of those needed a second pass, and the review that found them is worth
recording with them. The three-field form carries a *third* thing besides the
swap and the map reveal -- the tutorial's own final map write -- and a dispatch
rule that separated only the first two swallowed it, leaving every account
stranded at `chapter1_5_cleared` on any server carrying this flag, which is every
guided one. All three are told apart by what each changes: the swap changes the
world, the reveal and the tutorial write change `progressCode`. The cursor write
also gates on the tutorial rather than on idleness, because a force-close leaves
a battle phase open and every later start renews it, so a `free_roam` gate
answered Network Error until the player happened to finish a battle. And a clear
past a world's frontier now settles without moving the cursor, rather than
advancing it to the cleared section's successor and silently retiring everything
in between. The main
story's `progressCode` is untouched by all of it, which is why the per-world
stamina-cap inflation another reimplementation recorded cannot arise here.

**Still unvalidated.** Nothing above has been played. The contracts are read from
the client's own handlers rather than from a capture, and the thirty stages have
never run against this server.

## Tower of Temptation sits in the client's Raid quest chapter range

**Reported symptom.** "Tower of Temptation quests are locked now. Says I don't
meet the requirements to play them," from two testers. Jade Dragon and the rest
of Arena were fine when checked.

- **Reproduced on the reviewed client, and the server never hears about it.**
  Arena -> Tower of Temptation -> any of the four cards raises
  "You don't meet the requirements to unlock this quest. Check the event notice
  for details." The event log records the banner fetches for the list and then
  nothing: the refusal happens on the device, before any start request. In the
  same session Eidolon quests, standing Special Quests, and the archive folded
  cards all opened their team popup normally, which is what rules out the
  Special category and leaves the chapter numbers.
- **Confirmed -- the chapter ranges are literals in `ChapterInterface..cctor`
  (`0xD0741C`).** `CounterDescentQuestChapter` 8000--8999,
  **`RaidQuestChapter` 9000--9009**, `TowerOfTemptationChapter` 9010--9099,
  `DonationQuestChapter` 9100--9199. This server serves Tower of Temptation from
  9000--9003, so its cards are Raid quests to the client no matter what
  `towerQuestList` calls them. The range decides the start path; the family does
  not.
- **Confirmed -- the raid gate and what an unsent key decodes to.**
  `UISpecialSelect2.StartSpecial` (`0xF82590`) calls
  `ChapterInterface.IsRaidQuest` (`0xD0602C`, a bounds test against those two
  statics) and then `EventManager.GetRaidQuestStatus` (`0xD96EC0`), which is
  `GetQuestParam(id)["status"]` over the `eventQuestParams` object
  `AppServerUtil.<Login>` installs via `EventManager.SetQuestParams`
  (`0xFB79B0` names the key). `GetQuestParam` returns null when the object is
  absent, and the status accessor answers `UISpecialItem.RaidStatus.Lock` (1) on
  null. `Lock` (1) and `Completed` (4) are the two values the start path
  refuses; `Subjugating` (2) and `Overkilling` (3) pass.
  `UISpecialItem.OnClickedBtn` (`0xF81D2C`) asks `IsFolded` about the *chapter*
  rather than the row, so a `9000-1` row reaches this same path -- serving the
  family folded moves the refusal one level in rather than avoiding it, which a
  live test confirmed.
- **Confirmed -- the field types are strict, as everywhere else here.** `status`
  is read with LitJson's `int` accessor and `remainHp` (`0xD96F50`) with the
  `double` one, which throws on `JsonType.Int` rather than converting -- the
  same trap `jobLevels` and `questClearDate` carry.
- **Local policy.** `status` is sent as `Subjugating` and `remainHp` as a full
  `1.0`. Neither is recovered: what the retired service put here was live
  state. `Subjugating` is chosen because it is the plainer of the two values
  that pass, and a full bar is the honest reading for a boss nobody has fought
  on this server.
- **Deliberately unsent: `overkillEndDate`.** `UISpecialSelect2.UpdateItems`
  (`0xF8AE00`) draws the raid countdown and HP bar only once that date is
  present. Withholding it keeps the cards rendering as ordinary quest cards
  instead of dressing them in an availability window this project never
  recovered, and a live test confirms the cards are unchanged.

**What changed.** The login reply carries `eventQuestParams` for every advertised
stage whose chapter falls in 9000--9009, derived from the event catalog so a
later family added in that range cannot miss it.

**Validated against the reviewed client.** Tower of Temptation Alika now opens
its team popup at 15 stamina, difficulty 35, one battle. The clear was not
played.

## 2026-08-10: two menus the server never filled, and five families named after the wrong table

**Reported symptom.** Issue 62 recorded the final 5.5.7 menu tree as it stood at
shutdown, and it did not match what this server draws in two ways: the Third
Descents, the Dragon King and the Royal Rings were listed under Arena -> Descent
Quests rather than beside the Special Quests, and Arena -> Special Quests held a
Battle Champs family and an 8-Bit Rush card this archive did not serve at all.

- **Confirmed by the client's own selector enum.** `UISpecialSelect.Mode`
  declares ten modes, and `DescentQuest` (3) is not `DescentHunting` (8). Mode 8
  is Huntland -> Strikes Back, which this server already fed. Mode 3 reads
  `ServerConstants.descentQuestList`, a field at static offset `0x198` beside the
  six lists already served, whose string literal is present in the metadata --
  so `SetServerConstants` reads it, and this server had simply never sent it.
- **Confirmed: the move is presentation only.** `ChapterInterface` declares no
  Descent range. The ranges it does declare -- Counter Descent 8000--8999, Raid
  9000--9009, Tower 9010--9099, Donation 9100--9199 -- are what pick a start
  path, and no 2000-series chapter is in any of them. Which menu draws a row is
  decided by the list it is advertised on and by nothing else, so the seven rows
  keep their folded or per-section identity, their flags, and their settlement.
- **Measured, and the reason this is not cosmetic.** At full progress
  `specialQuestList` was 32 rows against a client that hangs above 30, so two
  were already being withheld by the cap. Moving the seven Descent rows to their
  own list leaves 25 and withholds nothing.
- **Confirmed by banner artwork: 8008--8011 are Battle Champs and 8018 is
  8-Bit Rush.** Both were excluded from this archive under the names their
  BattleData titles carry -- `リトルノア：ケツァルコアトル` and `ヒメラッシュ`,
  read here as Little Noah and Hime Rush. Those are the Japanese internal names.
  The English client drew its own banners over them, and decrypting the retained
  ENCA bundles gives TEMPEST I/II (8008), DIRE FANG I/II (8009), VOID VENOM I/II
  (8010), BRUSHFYR I/II (8011) and `8-Bit Rush` (8018-1) -- which are the
  shutdown menu's Strike of the Stormy Serpent, Fearsome Fiends!, The Creature
  From the Void, The Dragon Awakens, and 8-Bit Rush. A family named off its
  BattleData title alone can be named after the wrong game entirely.
- **Confirmed: the contract that differed is `dropBuddies`, and it is recovered.**
  The five were held back because "their distinct progression/reward contracts
  are unrecovered." The distinction is that every Strikes Back section declares
  an empty `dropBuddies` while these are the only members of 8000--8018 whose
  manifest names anything. Decoded with the same packed rule the story outcomes
  and the Chapter-1100 manifests use (`code >> 8` is the Companion, the low byte
  its cap): 8008-2 Samatha and Maverick, 8009-2 Yukken and Maverick, 8010-2
  Yukken and Spike, 8011-2 Samatha and Spike, 8018-1 Holy Breath, Axion Breath
  and The Ancient Key, one copy each. Tier I of all four families declares none.
- **Confirmed section economics.** 8008--8011 carry two sections of three
  battles at 5 and 15 stamina; 8018 one section of six battles at 15. Every one
  declares an empty `parentQuest`, so none is chained.
- **Also settled by the same sweep, so it is not looked for again.** Chapter
  2005 already serves Mobius Final Fantasy, Recode and Strike as three unfolded
  cards -- `sp2005-1`, `-2` and `-3` are three distinct banners, which is what
  the menu's three Mobius entries are. Chapters 1300--1302 are escort quests
  (`パルパル護衛`, `復讐護衛`, `お兄チャン護衛`), one battle at 10 stamina each,
  and carry no `sp` banner at all, so they never had a selector card. Chapters
  4000--4011 and 5000--5007 carry `mp`-prefixed banners: they are the retired
  Co-op and VS content and stay outside solo parity.

**Local policy.** Each Battle Champs family is advertised as one folded card
rather than two section rows. Both are drawable -- the retained bundles include
a folded `sp8008` and both section banners -- and folding is what holds
`specialQuestList` at exactly the 30 rows the client can render with these five
added. The tiers a fold would otherwise offer past the two that exist stay shut
by the mechanism the three-tier Strikes Back families already rely on: per
section flags and no chapter flag. 8-Bit Rush has one section and no folded
banner, so it is advertised as `8018-1`. The Chapter 19--23 unlock cadence
continues the same permanent local gate the fourteen Strikes Back families
carry, and is not a recovered schedule.

**What changed.** `descentQuestList` is served and carries the seven Descent
rows; Battle Champs and 8-Bit Rush are served on `specialQuestList` through a
bundled policy beside the Counter Descent one, under the same `--hunting`
switch, so neither deployment can advertise a menu the other does not. A clear
of any of the five is refused unless the Companions it reports are the ones its
own section declares, at that section's cap; a section declaring none accepts
none. Sections whose manifest was never read stay unconstrained, which is every
other event stage.

**Not validated against the reviewed client.** Both menus are covered by
real-HTTP tests only. What is still open is what the shutdown record shows and
this server does not: display *order* within Arena -> Special Quests, which
remains chapter-ordered here and was not in the final client.

## 2026-08-10: the Daily Quest Energy reward had a label and nothing behind it

**Reported symptom.** A tester cleared Sweet Temptation and the result screen
showed an Energy reward with no amount beside it. No Energy arrived, and no
item did either.

- **Confirmed by the client's own constants.** `DailyQuestManager` declares
  `EnergyGetChapter = 6006` and `EnergyItemId = 80` as literals, and Item 80
  resolves to *Energy* through the operator's own names catalog. Chapter 6006
  is the Daily Quest the client itself designates as the Energy source, which
  `daily_quest_data` already recorded and already bounded at one per clear.
- **Confirmed: the client mints nothing.** `ServerConstants` carries
  `EnergyBonusByDailyQuest` at static offset `0x4C`, beside
  `ChapterClearEnergyBonus`, and this server has always advertised it as 1.
  Both are display values whose balance the server's own response was expected
  to supply -- `archive_economy` states exactly that in its module docstring.
  It then excluded Daily Quests from `ENERGY_BEARING_KINDS` regardless, so the
  client drew the reward and no wallet moved.
- **Confirmed against the live save.** The reporting account showed `energy` 0,
  `freeEnergy` 4, and item slot 80 at zero. The drop landed in neither wallet
  nor inventory: the client treats Item 80 as currency and never writes it to
  `itemList`, and the server was never going to mint it.
- **The stated reason for the exclusion does not hold for this family.** The
  rule exists because Hunting, Metal Zone, the special quest and the Roads
  repeat without bound, and a stage that both repeats forever and mints Energy
  makes every Energy price a matter of how long a run is repeated. A Daily
  Quest is entered at most once per UTC day, and only from the two quests the
  day's rotation names. Sweet Temptation appears four times in the recovered
  41-day rotation. The bound is the calendar, not the stage.

**Local policy.** Every Daily Quest pays on an accepted clear, not only the
chapter the client designates -- deliberately wider than the client's own rule,
at the operator's decision. The amount is `DAILY_QUEST_FREE_ENERGY`, which is
the same number `EnergyBonusByDailyQuest` advertises: one constant, so the
screen and the wallet cannot disagree. It is minted into `freeEnergy` under the
existing `maxFreeEnergy` ceiling, never into the paid families, so a local grant
can never be read as a purchase.

**What changed.** `award_daily_quest_energy` grants on the Daily Quest clear
path, keyed by quest identity and UTC day rather than by request identity, so a
clear replayed under a fresh request id cannot pay twice. The wallet projection
is resynchronised after the grant: the nested `valuables` copy the client reads
its balance from is built earlier in the same settlement, and left alone it
reports the pre-reward balance on the screen announcing the reward. Nothing is
reconstructed for clears settled before this.

**Not validated against the reviewed client.** Covered by real-HTTP tests only:
the grant, the balance in all three places, and the day gate refusing a second
entry. What the result screen draws once an amount is actually behind it has not
been seen on hardware.

## 2026-08-12: Lucia II and III use the item-bearing quest-start form

**Reported symptom.** Lucia the Explorer II returned Network Error when a
tester attempted to enter it. The initial report proposed that its required
entry item was the difference from the first tier.

- **Confirmed by reviewed BattleData.** Chapter 2006-2 is 35 stamina with
  `itemID=110`, `itemCount=1`; Item 110 is Key of Hearts. Chapter 2006-3 is 40
  stamina with `itemID=111`, `itemCount=1`; Item 111 is Key of Diamonds.
  Sections 1 and 4 have a zero item pair. Across all reviewed BattleData, the
  only other positive pairs are the existing Chapter-3000 Metal Ticket rows.
- **Confirmed by client control flow.** ARM64
  `AppServerUtil.<StartQuest>c__Iterator20.MoveNext` begins the item branch at
  `0xFC4F78`: it loads `BattleData.Section.itemID` from offset `0x34`, requires
  it to be positive, then loads `itemCount` from offset `0x38` and requires that
  to be positive. It serializes both before continuing to chapter and section.
  No chapter or selector test appears on that branch, so treating the longer
  form as Metal-only was incorrect.
- **Confirmed server mismatch.** `battledata_importer` projected stamina,
  Coins, and battle count but dropped `itemID`/`itemCount`; consequently the
  generated 2006-2/3 event rows declared no key, routing parsed only the shorter
  form, and the real client body reached `unsupported_start_quest`.

**What changed.** The local BattleData projection and event catalog retain a
complete nonnegative entry-item pair. Archive routing accepts the shared
ordered form only when it exactly matches the selected stage, and accepted
entry debits the key with stamina in the same persisted transaction. The
response carries the post-spend `itemList`; duplicate and fresh-ID re-entry do
not charge again, an interrupted client may repeat only the pre-entry key slot
at clear, and exact clear replay survives restart. A missing key returns the
client's own `StartQuestErrorCode.NotEnoughItems` code.

**Not yet validated on hardware.** Focused real-HTTP tests establish the
generated contract, one-time spend, body-scoped refusal, lost-response
re-entry, clear reconciliation, and restart replay. The reporting client has
not yet retried Lucia II against this build.
