# Execution Plans

## 2026-08-01 Repeatable setup rehearsal

Status: completed 2026-08-01.

Objective: make it cheap to prove that a change did not break guided setup.
Until now the only proof was the manual clean-onboarding rehearsal recorded on
2026-07-28: reset a checkout by hand, run setup, read the output. That is slow
enough to happen rarely and is judged by eye, so a catalog that quietly lost
half its rows looks exactly like one that did not.

Execution boundaries:

1. Rehearse the real pipeline, not a fake of it. The unit suite replaces the
   IL2CPP dump, the master-data import, the catalog derivations, the APK patch,
   and the signing; the rehearsal must run all of them.
2. Require no emulator, phone, or tablet. Device certification stays a separate,
   manual concern.
3. Treat the operator's APK and resource tree as immutable inputs, and keep
   every derived hash out of the repository: the comparison baseline lives
   beside the save under `user-data/`, which is ignored.
4. Report a regression as a named changed field rather than as output an
   operator has to notice. Ignore only what legitimately differs between two
   correct runs.
5. Cover the harness's own decision logic with ordinary unit tests, so the thing
   that judges setup is itself judged.

Result:

- `liminal_gate/setup_rehearsal.py` stages a clean source copy (the working tree
  including uncommitted files by default, or a Git worktree at a revision),
  builds an isolated environment, runs the prerequisite check, runs guided setup
  with `--prepare-only`, then serves the generated catalogs to a scripted client
  over real HTTP: time, status, signup, login, userdata, the tutorial Pact, and
  one hash-checked resource; then a full server stop and restart, requiring the
  same account, the surviving starter, and a replayed rather than rerolled Pact.
- Each run writes `summary.json`, `summary.txt`, and stage logs under
  `build/rehearsal/`, and compares every field against
  `user-data/rehearsal-baseline.json` except timestamps, run directory, commit,
  interpreter version, and the signed APK, whose hash comes from a keystore each
  run creates fresh. A baseline recorded from a different APK is refused rather
  than reported field by field.
- The build port is fixed at 8697 because it is compiled into the patched APK; a
  borrowed port would change that file's hash and report a regression where
  nothing had changed. The smoke server borrows a free port, which nothing bakes
  in.
- 31 focused tests cover source staging, generation facts, baseline comparison,
  transport summarizing, the onboarding assertions, and run-directory handling.
- Validated against the real inputs: two consecutive independent runs compared
  identical in every field, a run with a changed build port reported exactly the
  build port and the patched APK it changes and exited 1, and the freshly
  extracted `dump.cs`, native/scenario encounter maps, character catalog, and
  resource manifest reproduced the 2026-07-28 clean-onboarding hashes byte for
  byte, at 23,594 resource mappings, 780 story rules, and 48 DummyDll
  assemblies. A run takes about 50 seconds. Warning-strict full suite: 725
  tests.
- **The first complete run found a real defect.** `--daily-quests`, added on
  2026-07-31, was defined by the parser and read by `main`, but never carried by
  `ServerConfig`, and `load_launch_config` returns a `ServerConfig`
  unconditionally. Every command-line launch — including the one guided setup
  performs — died with `AttributeError: 'ServerConfig' object has no attribute
  'daily_quests'` before serving a request. The whole 722-test suite passed
  throughout, because every other test constructs `BootstrapServer` directly.
- Fixed by carrying `daily_quests` through `ServerConfig`, its TOML loader, and
  `load_launch_config`. Added a structural regression test asserting that every
  launch option `main` reads is a field the configuration carries — the same
  guard that already existed one level earlier, between the parser and the
  launcher, which is why the gap fell between them.

## 2026-07-31 Pact pool cap and Daily Quests

Objective: implement the two items the secondary-source audit listed as
unmodeled. One was already implemented and needed only coverage; the other is
blocked on unrecovered data and is **not** being implemented.

### Removal from the pool at 100% Skill Boost — already implemented

The audit was wrong to list this as missing. `bootstrap_server` already filters
every draw against the catalog cap, on `skillBoost` for an ordinary pull and on
`luck` for the Fate variant, and refuses the whole Pact when nothing in the pool
remains eligible. Both of the recorded service rules were therefore already
honored: a character at 100% stops being offered, and an account holding the
entire pool at 100% can no longer pull.

What was missing was a test. Added one covering both halves: with one member of
a two-entry pool capped, three consecutive draws all select the other member;
with the pool wholly capped the Pact answers `success:true, cmdError:3` and the
coin balance is untouched. Note the wire shape — the refusal is a *successful*
call carrying a command error, not an HTTP failure, matching the documented
`cmdError` convention. The exhausted case needs its own server and state file,
because one account per state file owns the host claim.

### Daily Quests — blocked, not implemented

The client schedules these itself. `DailyQuestManager` computes up to three
quests a day from `DailyQuestData.questOrder` and its own UTC/local clock,
`ChapterInterface.DailyQuestChapter` is a client static rather than a served
constant, and playability is decided from `lastDailyQuestPlayTime`,
`lastDailyQuestPlayTime1` and `lastDailyQuestPlayTime2`, three save fields this
server does not currently persist. `enableDailyQuest` is a known client flag and
`AppServerUtil.DeleteDailyQuestPlayTime` is the reset call. So the server side
is small: three longs, a flag, one endpoint, and entry/clear for the daily
chapters.

The content is the blocker. In the daily chapter block 6000--6012 the operator's
own BattleData gives **exactly one** row a battle program, 6007 with three
battles. Every other row including 6006, which the client names
`DailyQuestManager.EnergyGetChapter`, is a zero-battle placeholder with no
stamina and no coins. `BoostUpChapter` 6077 is absent from BattleData entirely.
The recovered constants `EnergyItemId = 80`, `BoostUpCount = 20` and the two
drop-up ratios of 2 therefore attach to stages that either cannot be played or
do not exist.

Implementing now would mean inventing the daily rotation, the reward settlement
and most of the stage set. That is the same reasoning that excluded the sixteen
empty Eidolon tier placeholders and all 45 Donation stages, and it applies here
with less recovered material than either.

Unblock condition: recover `DailyQuestData.questOrder` from the operator's own
Unity assets. **Done, see below.** The rotation is recovered; the reward
question is not, so Daily Quests stay absent rather than invented and the
Huntland menu is still short one category.

### The rotation is recovered

`liminal_gate/daily_quest_importer.py` reads `DailyQuestData` out of
`assets/bin/Data/data.unity3d` in the operator's own APK. The asset is not in
the downloaded resource pack at all — that tree carries only the nine media
categories — so it had to come from the APK's own Unity data.

An IL2CPP build strips field names, so there is no type tree to read the
`MonoBehaviour` with. It does not need one. `DailyQuestData` declares exactly
one field, so the payload after the standard 28-byte header is a single
length-prefixed string array, and a parse that consumes the object *exactly*
is self-validating. The importer requires that, and additionally refuses a
rotation naming a chapter outside the 6000-block, disagreeing instances, and a
catalog without an APK digest.

Result on the reviewed 5.5.7-170 client: a 41-entry rotation across 14 stages,
Chapters 6000--6012 plus section 2 of 6011, consuming 528 of 528 bytes. That
stage set matches the 6000-block rows in a real BattleData tree exactly in both
directions, no extras on either side. Two independent assets, one a Unity
scene object and the other the master battle tree, agree on the same fourteen
stages. Nine focused tests cover the parser and the catalog's refusals using
synthetic objects, so none of them needs an APK.

The day-to-index rule was deliberately not reproduced and does not need to be.
The client owns it, computes today's three entries itself, and the server only
ever needs to know which stages are legitimate Daily Quests.

### The stage identities are settled, and the category is implemented

The chapter-to-quest mapping was resolved by matching all fourteen APK banner
textures pixel-wise against the community record's own banner images. The result
is a clean bijection: every wiki banner matched a distinct stage, eleven of them
at a distance under 1.1 where the nearest rival sat near 50, the Hunt For Joker
at 7.1 against a nearest rival of 64, and the two Yamamoto banners at 27-28
against rivals near 58. No assignment is ambiguous.

Three assignments had been predicted independently before the match and are
confirmed by it: 6006-1 is Sweet Temptation, because the client's own
`EnergyGetChapter` is 6006 and Sweet Temptation is the one-Energy quest; 6011-1
and 6011-2 are the two Yamamoto variants, because 6011 is the only two-section
chapter and the record lists exactly two; and 6010-1 is Lucky Orbling, forced by
the rotation's frequency classes once 6006 is fixed. The frequency argument is
itself independent evidence: every quest name appears in the wiki's 41-day
schedule exactly twice as often as its stage appears in `questOrder`, so both
records partition into identical classes.

| Stage | Quest | Stage | Quest |
| --- | --- | --- | --- |
| 6000-1 | Metal Runner Rampage | 6007-1 | Tropical Haze |
| 6001-1 | Puppet Pandemonium | 6008-1 | Tearjerker Time |
| 6002-1 | Crystal Roundelay | 6009-1 | Hidden Stars |
| 6003-1 | Hedgehog Hullabaloo | 6010-1 | Lucky Orbling |
| 6004-1 | Particle Hoarder Horde? | 6011-1 | Yamamoto's Puzzle Quest |
| 6005-1 | Rarity Rumble | 6011-2 | Yamamoto's Puzzle Quest II |
| 6006-1 | Sweet Temptation | 6012-1 | The Hunt For Joker |

`bootstrap_server --daily-quests` implements the category. The stages reuse the
Hunting bounded-settlement path with the `hidden` selector, since the client
lists Daily Quests itself and never asks the server which exist. Entry is free,
matching all fourteen zero-stamina BattleData rows. The server sends
`enableDailyQuest` plus a per-stage `sp_ch_` flag.

Reward ceilings are local policy from a secondary source and cannot become
recovered values: the retired server owned Daily Quest rewards and the client
only rendered them. Item identities were resolved to IDs through the operator's
own master data, which cross-checks: `Energy` resolves to 80, exactly the
client's `EnergyItemId`, and the tickets to the 50 and 81 already used here.

### What is still missing

Both of the gaps this entry originally recorded are now closed.

**The Hunt For Joker grants Joker Λ.** Character 1018 is neither an item nor a
Companion, so `HuntingStage` gained a `character_grants` channel and the clear
path applies it after the roster merge, where `_preserved_roster` already
guarantees a server-side grant survives a stale client. A first clear adds the
row; a later one raises Skill Boost by 10.0% and Luck by 10.0, capped at the
client's 100.0 ceiling. The identity came from the operator's own master data;
the two duplicate increments are secondary-source policy like the ceilings.

**The once-a-day limit is enforced server-side.** Each stage carries
`once_per_utc_day`, the clear stamps the account's UTC day, and a second start
that day is refused. The refusal deliberately uses the client's soft
`success:false, errorCode` shape rather than an error, so a player who tries
anyway sees an ordinary refusal instead of a Network Error. The caveat is that
this reuses the insufficient-resource code, so the client's wording may not name
the real reason. Sending the real `lastDailyQuestPlayTime` fields would let the
client grey the entry out properly, but their wire format is not recovered --
`IsDailyQuestPlayable` compares quest strings rather than a plain timestamp --
and guessing it is not worth a desynced save.

Still unresolved, though it blocks nothing: the client's day-to-index rule. The
`DailyQuestManager` region contains no modulo or array indexing, so the schedule
is computed elsewhere. It was never needed -- the client owns the schedule and
the server only needs to know which stages are legitimate.

## 2026-07-31 secondary-source audit of the bundled local policies

Objective: check every value this project labels local policy against the
community record, correct what was demonstrably wrong, and record what remains
unmodeled. Done for the Pact tables and documentation; the items under
"Unresolved" below are open.

Corroborated exactly, and therefore no longer merely asserted: Metal Zone
stamina 5/8/10/13/15/18/20; the Metal Zone 6 and 7 story gates at Chapters 26
and 30 (the widely cited 27 and 34 are the pre-4.6.0 schedule and are wrong for
5.5.7); Metal Minion maxima 1/2/3-and-up with Λ absent below Zone 3 and capped
at two above it; Coin Creeps 10/15/20; Pudding, Tin and Puppet 5/8/10; Crystal
Road 7; Pact of Truth 5 Energy and 50 for ten; Pact of Fellowship 3,000 Coins;
new characters at level 10; Fate reusing the Truth pool with Luck substituted
for Skill Boost; and the fourteen Strikes Back identities in the order this
bundle already declares them.

Corrected: Pact duplicate gains were a flat +1 level and +1.0% Skill Boost for
every class, which matched no source. They are now banded by class, keyed on the
operator's own catalog `rarity`. Pact of Truth selection was uniform and is now
weighted 4/10/15/71 across Z, SS, S and A-plus-B. Neither can be promoted to a
recovered value: `UIPactResult.PrepareShow(chrId, addedLevels, addedSkillBoost,
addedLuck)` shows the client rendering server-computed gains, and the only
rate-adjacent client symbol is `RareSlotEnergy`. Documentation claiming eight
Strikes Back families gated at Chapters 5 through 12 was wrong in both numbers;
`event_manifest_data.py` carries fourteen at Chapters 5 through 18.

Unresolved:

1. Huntland composition. The community record says 5.5.0 left Metal Zones
   reachable only as their All Hail the King versions, seven rows plus the two
   Roads; this bundle advertises all fourteen sections. A tester previously
   confirmed a regular row on the real client, so operator evidence and the
   record disagree and a device check should settle it before either is
   trusted.
2. All Hail the King guarantees the King floor where a regular run has a 5%
   chance of it, and the King is worth 4x a standard enemy at Zone 1 rising to
   14x at Zone 6. Both variants currently share one `max_exp` ceiling. The
   ceilings are loose enough that no legitimate clear should be refused, so this
   is a fidelity gap rather than a live defect.
3. A full base-EXP-per-difficulty table, per-enemy multipliers and the party EXP
   split are documented and would bound a Metal clear far more tightly than the
   present single ceiling.
4. Unmodeled and documented: "+" Pacts granting +1-5 levels and +0.5-3.0% Skill
   Boost; permanent removal from the pool at 100% Skill Boost; per-character
   chapter gating inside both pools; and Daily Quests, a fourth Huntland
   category this project neither implements nor mentions.
5. Still unsourced, so their local-policy labels stand unchanged: the Chapter
   3/9/18 Hunting tiers, the Metal Zone 1-5 gates, the Chapter 3003-1 Coin
   ceiling, and the Descent permanence gates. The Descents are explained rather
   than merely missing, since they ran as timed Arena rotations and have no
   permanent schedule to recover.

Evidence status: the community wiki is a secondary source. Everything above is
Strongly inferred at best, except where it independently agrees with data
already recovered from the APK. The class banding is the one place where it
does: `Character.get_luckMax` derives its cap from the same `rarity` field, and
across a real catalog the non-Lambda caps fall on exactly the three groups the
duplicate table uses, 700 for rarities 2-5, 800 for 6-7 and 1000 for 8.

## 2026-07-31 restore chapter milestone tickets

Objective: restore the retail Chapter 5/7 Metal Ticket and Chapter 6/8/10
Companion Ticket presents as durable, replay-safe inbox rewards, including a
safe retroactive grant for accounts already past a milestone.

Evidence boundary:

- The retained account at Chapter 8-9 contains read Chapter 5 Item 50 x2 and
  Chapter 6 Item 112 x3 messages, but no Chapter 7 message and zero of both
  ticket balances.
- The documented retail milestones are Metal Ticket x2 after Chapters 5 and 7,
  and Companion Ticket x3/x3/x4 after Chapters 6, 8, and 10 respectively.
- The server already has an exact inbox read/delete transport. The missing
  boundary is progress-gated message issuance and durable issued-state, not a
  new direct inventory mutation.

Required proof:

1. Issue only milestones strictly below the currently unlocked story chapter.
2. Record issued message IDs separately from the inbox so deleting a claimed
   message cannot recreate or duplicate its reward.
3. Backfill existing eligible accounts at login, persist before responding,
   and prove read retry, deletion, restart, and the Chapter 8 boundary over the
   real HTTP path.
4. Run focused and full validation, publish, deploy, and verify the live
   account receives only its missing Chapter 7 present.

Current result:

- Chapter 8-9 login creates Chapters 5, 6, and 7 but not Chapter 8; the exact
  Chapter 7 read credits two Item 50, an identical replay credits nothing, and
  deletion plus restart does not recreate the message. Entering Chapter 9 then
  creates Chapter 8 Item 112 x3.
- A migration run against a copy of the live save adopted its existing read
  Chapter 5/6 messages, added only the missing Chapter 7 message, and left the
  zero ticket balances unchanged until read.
- Twenty-one focused tests and all 656 repository tests pass warning-strict;
  compilation and diff checks pass. Both clean-candidate publication gates
  pass. Commit `d976bd5` is pushed and deployed on the Beelink under systemd
  PID 264479. Live login at progress 8-10 adopted the read Chapter 5/6 messages,
  created exactly one unread Chapter 7 Item 50 x2 message, and left Item 50 and
  Item 112 at zero until the player reads it. Original-client inbox/read
  acceptance remains pending.

## 2026-07-31 correct the solo Eidolon selector catalog

Objective: replace the over-broad 28-row Eidolon selector with the twelve
final-client solo quests that have both an actual battle and a matching banner,
without restoring Co-op, VS, in-battle summoning, or unproven reward behavior.

Evidence boundary:

- The maintainer's physical client rendered all 28 raw rows but roughly half
  had no banner. The APK-matched BattleData explains the split exactly: sixteen
  tier-I/tier-II rows have `battleCnt=0`, while twelve rows have battles.
- The final Android `SpecialBanner` catalog and retained Android resources have
  exactly the same twelve identities: 4100-3, 4101-3, 4102-3, 4103-1, 4104-3,
  4105-3, 4106-1, 4107-3, 4108-3, 4109-3, 4110-1, and 4111-1.
- Version 5.5.0 removed multiplayer and Eidolon battle use but added Eidolon
  Single Quests. The quests remain valid solo content; the sixteen empty raw
  rows are not independent selector cards.
- Older Co-op enemy records retain 50 percent Eidolon drops, but the playable
  solo programs use different enemy records. Moving those ceilings to the
  banner-backed rows would be an unsupported reward claim.

Required proof:

1. Generate exactly the twelve banner-backed, nonzero-battle identities and
   fail clearly if a supplied BattleData projection has a different shape.
2. Keep the generic, replay-safe Summon settlement available for an explicitly
   reviewed override, but generate no Eidolon acquisition ceiling yet.
3. Run focused and full release validation, publish, regenerate on the Beelink,
   and verify the live Chapter 8 selector and multiplayer-disabled response.
4. Reopen the selector on the physical client and confirm every remaining card
   has its intended banner before attempting one clear/result capture.

Current result:

- Local generation produces 124 stages across 47 families: 42 curated Archive,
  58 Counter Descent, 12 Tower, and 12 banner-backed solo Eidolon stages. The
  generated Eidolon rows have no fabricated collectible ceiling.
- Forty focused generator/catalog/runtime tests and all 654 repository tests
  pass warning-strict. Compilation, JSON/YAML parsing, and diff checks pass.
  The retained inputs generate SHA-256
  `1b99bc264ac6dbba4f81f4d89105e54e804b9f12cdaa4078d516886b3044ceeb`.
  Both publication gates pass from a clean candidate. Commit, deployment, and
  physical-client confirmation remain pending.

## 2026-07-31 complete the curated solo Event Archive

Objective: expose every release-facing, packaged solo Chapter 2000--2018 event
through the final client's server-owned Special Quest list while retaining the
existing Strikes Back, Tower, and solo Eidolon boundaries and keeping Arena VS
and multiplayer disabled.

Evidence boundary:

- Dual-ABI `UISpecialSelect.SetMode(0)` reads a nonempty server
  `specialQuestList` and falls back to the embedded 50-entry array only when the
  server list is null or empty. The server can therefore publish later packaged
  rows without a client patch.
- APK-matched BattleData contains 49 sections in Chapters 2000--2018, and the
  final binary contains native `Chapter2000` through `Chapter2018` programs.
- Chapter 2012 is explicitly test content, Chapter 2013 lacks a released
  selector banner, and 2015-4--6 are empty zero-battle placeholders. The other
  42 sections form the curated release-facing archive.
- Every selected chapter background and required explicit section banner is
  present in the operator's Android resource archive. Historical calendars and
  complete reward tables remain unrecovered.

Required proof:

1. Generate the 42 curated Archive stages with folded or explicit presentation
   IDs matching the final selector, and reject impossible selector/flag pairs.
2. Preserve local-policy progress gates and first-section character grants;
   derive entry economics only from matching user-local BattleData.
3. Prove generated-catalog shape, progress projection, folded non-first-section
   entry, clear, replay, restart, and multiplayer-disabled behavior over real
   HTTP.
4. Run the warning-strict full suite, compilation, structured-file checks, and
   clean-candidate publication gates.
5. Regenerate and deploy the catalog, then obtain physical-client Archive,
   Strikes Back, Tower-clear, and Eidolon acceptance without claiming recovered
   live schedules or multiplayer behavior.

Current result:

- At this checkpoint the retained inputs generated 140 stages across 47 families:
  42 curated Archive stages, 58 Counter Descent stages, 12 Tower stages, and
  28 raw Eidolon rows. The later Eidolon correction above retracts that selector
  shape and reduces it to the twelve battle/banner-backed rows. The Archive uses 26 folded/explicit selector cards and
  excludes Chapters 2012/2013 plus empty 2015-4--6.
- Focused warning-strict catalog, transport, and setup validation passed all
  139 tests. The complete warning-strict suite passed all 653 tests in 128.357
  seconds; compilation, profile JSON, endpoint YAML, and diff checks passed.
- Commit `5302fb0` is pushed and deployed to the Beelink. The regenerated live
  catalog has SHA-256
  `364048ce39141cad2712aba16561864bad9ad75a612c18c2f6c79bb2f753a863`.
  The Chapter 8 account receives Archive cards `2000`, `2004-1`, and `3003-1`,
  three unlocked Strikes Back cards, all 12 Tower rows, and the then-incorrect
  28-row Eidolon list. Live status/news return HTTP 200, multiplayer remains exactly disabled,
  and the save hash is unchanged across restart. The physical-client acceptance
  items in `docs/solo-event-completion-audit.md` remain separate completion
  boundaries. The maintainer has now opened the single Bahamut `2000` card in
  the final client and observed all four sections, confirming folded Archive
  presentation. Bahamut entry/clear and the injected explicit-card check remain.

## 2026-07-31 correct Tower identity and complete the solo adapter

Objective: expose the actual final-client Tower chapters through a bounded solo
adapter, remove the accidentally exposed Donation chapters, and retain the
converted solo Eidolon lifecycle without enabling Arena VS, Co-op, rankings,
or retired Eidolon battle/enhancement UI.

Evidence boundary:

- `ChapterInterface::.cctor` and its predicates identify 9010--9013 as Tower
  of Temptation and 9100--9102 as Donation. The earlier public mapping of the
  45 Donation sections to Tower was wrong and must not remain deployed.
- Final-client static output contains `towerQuestList`, `eidolonQuestList`,
  selector modes 5 and 4, Tower Chapters 9010--9013, and Eidolon Chapters
  4100--4111. APK-matched BattleData contains 12 Tower stages and 28 Eidolon
  stages with their entry economics.
- Tower predicate call sites are confined to selector/title presentation;
  completed `ChapterBase` stages call ordinary `AppServerUtil.ClearQuest`.
  The original shared HP, staged achievement, and reward state is unavailable,
  so this is explicitly a solo adapter rather than historical emulation.
- `ClearQuest` serializes the pre-result `summonList` and reports drops in
  `battle_result.summons`; its callback does not consume a returned Summon
  list. `ShowSummonGet` calls `UserData.AddSummon`, whose
  `SummonInfo(id, 1, 0)` constructor establishes raw value `1`.
- Mapping the compiled chapter enemy enums through EnemyData's ordinal table
  identified eight first-tier acquisition ceilings in the disabled raw rows.
  The later selector audit above shows those ceilings cannot be moved onto the
  banner-backed solo rows without new result evidence.
- Permanent Chapter 3 availability and zero fixed clear-Coin increments are
  local archive policy. Historical rotations and complete reward tables were
  not recovered. Original-client acceptance remains separate from static and
  local transport proof.

Required proof:

1. Generate every BattleData-backed Tower and Eidolon stage and project them
   through their dedicated status lists and exact login flags; generate no
   Donation row.
2. Accept only no Eidolon drop or one stage-allowed, previously unowned ID;
   durably store raw value `1` without returning an invented response field.
3. Refuse unlisted, duplicate, already-owned, or malformed reports without
   mutation; prove accepted clear, exact replay, and restart behavior over the
   real HTTP path.
4. Keep `multiplay_enable` false, regenerate and deploy the catalog to the
   Beelink, and request original-client Tower/Eidolon acceptance.

Current result:

- Manifest, classifier, runtime tests, and documentation now use the four
  actual Tower chapters and explicitly exclude all three Donation chapters.
- Focused validation passes, and all 648 warning-strict repository tests pass
  in 127.822 seconds. Corrective commit `99a6143` is pushed and deployed. The
  regenerated Beelink catalog has 115 rows: the exact 12 Tower identities, no
  Donation identity, and the then-incorrect 28 Eidolon identities. The later
  correction above replaces them with twelve battle/banner-backed identities. The service is healthy,
  Arena VS remains disabled, and the save hash is unchanged. The maintainer
  opened Tower on the physical final client and the corrected first entry
  loaded its battle after a retry, confirming navigation and entry. Tower
  clear/result return and all Eidolon original-client acceptance remain in
  progress.

## 2026-07-31 late non-collaboration Counter Descent expansion

Objective: complete the ordinary solo Strikes Back tranche that shares the
recovered Counter Descent contract without enabling collaboration-specific
progression, unrecovered reward systems, or Arena VS.

Evidence boundary:

- The final client's fixed Arena catalog identifies Chapters 8012--8017 as six
  non-collaboration Counter Descent families.
- The APK-matched BattleData projection records three sections per family,
  exact stamina costs of 5/10/15, and zero entry Coins.
- Permanent Chapter 13--18 availability and zero-base settlement are local
  preservation policy. No historical schedule or base reward was recovered.
- Little Noah Chapters 8008--8011 and Hime Rush 8018 use distinct unrecovered
  progression/reward contracts and remain deliberately unavailable.

Required proof:

1. Add only Chapters 8012--8017 to the bundled solo Counter Descent policy and
   retain the existing five-tier economics for Chapters 8000--8007.
2. Fold each unlocked family to one `descentHuntingList` row and emit only its
   matching flag.
3. Refuse 8008--8011 and 8018, exercise exact entry for 8017-3, restart before
   clear, and prove durable settlement plus exact replay after another restart.
4. Keep all multiplayer Arena routes disabled and update the public capability
   boundary without claiming original-client acceptance.

Outcome:

- The bundled policy contains fourteen families and 58 stages: forty five-tier
  stages across 8000--8007 and eighteen three-tier stages across 8012--8017.
- Generated matching rows retain the bundled `descent_hunting` selector and
  zero-base contract; collaboration/special chapters remain excluded.
- Focused catalog/generator/runtime tests cover selector ordering, stamina,
  exclusions, restart settlement, and replay. Original-client acceptance is
  still required before describing Chapters 8012--8017 as client-certified.

## 2026-07-31 Jade Dragon original-client settlement recovery

Objective: accept the exact final-client Chapter 2004-1 result without relaxing
the event transaction beyond fields observed on the wire, and prove that the
settlement is replay- and restart-safe.

Evidence boundary:

- The first result retry was preserved privately as an exact 17,795-byte form,
  SHA-256 `1d58ffb61f94ccbc1acd10620616b0d6aec8acbc5dc697888bd84b32ba421b3f`.
  It reported 819 battle Coins, 6,851 EXP, and the observed `itmp0=-1`
  sentinel. Its 12,124-Coin wallet was stale relative to the durable save.
- After a clean client login, the same result reported 11,824 wallet Coins,
  exactly the durable 11,005 plus the reported 819 battle Coins. This ruled out
  the tentative 300-Coin fixed-increment hypothesis.
- BattleData establishes the stage identity and entry economics, but does not
  establish a service-authored fixed clear increment. The generated catalog
  therefore keeps that increment at zero.

Required proof:

1. Accept the observed `itmp0=-1` sentinel while continuing to refuse values
   below `-1` and every other malformed clear field.
2. Reconcile an event wallet as durable Coins plus the catalog's fixed clear
   increment plus client-reported battle Coins; retain Counter Descent's
   separate zero-base restriction.
3. Exercise Chapter 2004-1 over real HTTP, including stale-wallet refusal,
   successful settlement, exact replay, durable rewards, and replay after a
   full server restart.
4. Deploy the bounded fix, obtain original-client result-screen acceptance,
   and verify that the resulting save remains byte-identical across a service
   restart.
5. Update public protocol/status documentation and pass focused, full-suite,
   compilation, structured-file, diff, and clean-candidate release checks.

Outcome:

- After deployment, the maintainer retried the retained Jade Dragon result.
  The original client received HTTP 200 from `POST /gd/clear_quest`, exited the
  result screen, and did not show another network error.
- The durable account returned to `free_roam` with no active quest, 11,824
  Coins, 27 free Energy, 78 characters including one Jade Dragon (673), and
  the submitted item counts. A service restart changed the PID while preserving
  the save byte-for-byte.
- Exact replay/restart behavior is covered by the focused real-HTTP regression.
  Other Archive families and Strikes Back still require their own client clear
  observations; this one result does not establish retired reward schedules.
- Thirty-six focused event tests and all 642 warning-strict repository tests
  passed. Compilation, profile JSON, endpoint YAML, and diff checks passed.

## 2026-07-31 retail first-Pact Bahl or Grace outcome

Objective: make the mandatory `kind=10` tutorial Pact choose Bahl or Grace at
equal weight while keeping the selected starter durable through the remaining
tutorial, exact retry, and restart paths.

Evidence boundary:

- The final-client request form, response field types, and accepted Grace path
  are already captured and client-confirmed.
- The maintainer identifies the retail first-Pact rule as a 50/50 Bahl-or-Grace
  choice. This is operator-supplied historical evidence; the public repository
  does not contain an independent retail response capture for both branches.
- User-local derived names identify Bahl as character 1 and Grace as character
  3. No original or derived private input will be committed.
- The existing profile embeds Grace in later tutorial party projections, so a
  first-response-only edit would create an invalid Bahl continuation.

Required proof:

1. Declare two equal-weight, strictly validated first-Pact outcomes with the
   existing response shape and persist the selected starter in account state.
2. Resolve later tutorial response, party, and transition templates from that
   durable starter while preserving legacy Grace saves that lack the new field.
3. Exercise Bahl and Grace over real HTTP; prove the random branch is selected
   once, exact retry is byte-stable without another roll, and restart retains
   both the response and starter identity.
4. Prove Bahl continues through the second tutorial Pact and first tutorial
   userdata settlement without introducing an unowned Grace party member.
5. Update the compatibility contract, endpoint matrix, checkpoint, status, and
   findings; run focused tests, the warning-strict full suite, compilation,
   structured-file checks, and diff review.

Original-client completion remains separate: a clean final client must visibly
receive both outcomes across controlled fresh accounts, continue through the
tutorial on Bahl, and retain the selected starter after a full service/client
restart.

Outcome:

- The bundled profile now declares Bahl (character 1) and Grace (character 3)
  as two positive weight-1 outcomes for the exact first `kind=10` form.
- The selected starter, roster/team projection, canonical response, and replay
  entry commit together. An exact retry does not select again and returns the
  same signed bytes after a full server restart.
- Later tutorial response and party templates resolve from the durable starter.
  A forced Bahl real-HTTP path continued through A'misandra and the following
  tutorial userdata settlement without introducing Grace. A forced Grace run
  completed the existing scripted path through Chapter 2-1, and an older
  Grace-only state with no starter field continued successfully.
- Thirty-two focused bootstrap/profile tests passed. The warning-strict full
  suite passed all 641 tests in 122.438 seconds. Compilation, profile JSON,
  endpoint YAML, and diff checks passed.
- No APK was built or installed. Original-client Bahl acceptance and its later
  packed level/EXP projection remain the next evidence boundary.

## RETRACTED 2026-07-31 — 2026-07-30 Tower 9100-1 vertical slice

This plan used an incorrect chapter mapping. Chapters 9100--9102 are Donation,
not Tower; the deployed rows were removed by the corrective plan above. The
text is retained only as an audit record and is not a current capability claim.

Objective: make the first recovered Tower of Temptation floor visible and
settleable through the final client's solo Tower selector without enabling
Arena VS or claiming the retired Tower schedule and rewards.

Evidence boundary:

- Final-client static output contains `ServerConstants.towerQuestList`,
  `UISpecialSelect.Mode.TowerQuest`, and the
  `ChapterInterface.TowerOfTemptationChapter` range check. The derived
  `dump.cs` has SHA-256
  `093b32f0015b1498be710fef7c857634ee1350b2ed065c55ae12b02bcb062a34`.
- BattleData derived from final Android APK SHA-256
  `f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15`
  records Chapter 9100 Section 1 as a five-battle, five-stamina, zero-Coin
  stage. The derived projection has SHA-256
  `be6fee15b28fd192d12c2ee5c8ac4cce30f25addda3135f77deec3dc65596767`.
- The selector, Tower-specific range, Chapter 9100 program, and 15-section
  structure strongly support the 9100 mapping, but no original-client Tower
  navigation or clear has been captured.
- Permanent availability after Chapter 3 and zero clear Coins are explicit
  local preservation policy. No Tower item, Companion, character, ranking, or
  historical schedule is invented.

Required proof:

1. Generate only Chapter 9100-1 as the bounded first Tower work packet from
   the tester's matching BattleData; leave the other 44 recovered 9100--9102
   floors unavailable.
2. Project `towerQuestList` and its exact `sp_ch_9100` login flag only after
   the local Chapter 3 gate, without changing `multiplay_enable` or any Arena
   VS route.
3. Prove exact entry economics, locked/unknown-stage refusal, one-active-quest
   behavior, body-scoped retries, rejected clear stability, successful clear,
   replay, and restart over real HTTP.
4. Update the endpoint matrix, checkpoint, status, findings, and setup
   documentation; run focused tests, the warning-strict full suite,
   compilation, structured-file checks, and diff review.

Original-client completion remains separate: the final client must visibly
open Tower, enter 9100-1, clear it, return to free roam, and retain the result
after server/client restart before this slice is described as client-certified.

Outcome:

- Guided setup now derives only 9100-1 from matching user-local BattleData and
  projects it through `towerQuestList` after the Chapter 3 local gate.
- The exact five-stamina, zero-Coin start enters the shared event transaction;
  clear preserves story progress, returns to `free_roam`, and replays across
  restart. Unknown Tower floors remain explicitly unsupported.
- Focused real-HTTP tests cover hidden/locked refusal, selector and login flag,
  exact entry, body-scoped same-ID/different-body refusal, retry without a
  second debit, rejected clear, successful clear, and restart replay. The same
  test confirms `multiplay_enable` remains false.
- The warning-strict full suite passed all 638 tests in 120.460 seconds.
  Compilation, profile JSON, endpoint YAML, and diff checks passed.
- No APK was built or installed. Original-client Tower navigation and clear
  remain the next evidence boundary.

## 2026-07-30 guided Archive Special Quests and Strikes Back

Objective: make the five recovered Archive Special Quest families and the
eight bundled Strikes Back families reachable through the standard guided
setup without an expert-supplied event catalog.

Evidence boundary:

- The final client supplies exact selector flags and chapters for Bahamut
  Descent (2000), Leviathan Descent (2001), Odin Descent (2002), Jade Dragon
  Hunt (2004), Lucia (2006), and Strikes Back Chapters 8000--8007.
- The tester's own BattleData supplies section identities and entry economics.
  The tester's own character catalog bounds the four recovered character
  associations.
- Permanent availability, the Chapter 2/4/10/13/20 archive unlock cadence,
  zero clear Coins, and granting an associated character on the first event
  section are local archive policy. They are not claimed as recovered service
  schedules, probabilities, or complete historical reward tables.
- Bundled Strikes Back remains authoritative for Chapters 8000--8007: five
  tiers, recovered stamina costs, progress gates, and zero-base settlement.
  Selector navigation and Chapter 8000-1 entry are original-client confirmed;
  its clear callback is not.

Required proof:

1. Generate and validate the default archive catalog during guided setup from
   the same user-local BattleData and character inputs already required for
   the complete game path.
2. Carry the labeled archive unlock cadence into the generated catalog and
   keep older explicit catalogs loadable.
3. Start the guided server with that generated catalog automatically while
   preserving an explicit `--event-catalog` override.
4. Prove Archive and Strikes Back selector projection, start, bounded clear,
   exact replay, body-scoped same-ID/different-body handling, and restart
   persistence over real HTTP.
5. Update the endpoint matrix, checkpoint, status, and operator documentation;
   run focused tests, the warning-strict full suite, compilation, structured
   file checks, and diff review.

Physical-device completion remains a separate boundary: Bahamut 2000-1 and
Strikes Back 8000-1 must each visibly clear and return to free roam in the
final client before either path is described as client-certified.

Outcome:

- Guided setup atomically writes `user-data/event-catalog.json` from the
  already loaded local BattleData and matching character catalog. The standard
  launcher passes it automatically; server-only setup discovers it only with
  the matching `character-catalog.json`. An explicit event catalog remains an
  override.
- The generated archive cadence is enforced while older explicit catalogs
  without `unlock_after_chapter` remain loadable. Archive rows merge with
  Chapter 3003-1 instead of hiding it. Bundled Counter Descent remains the
  first owner of every Chapter 8000--8007 section.
- The existing user-derived BattleData projection, SHA-256
  `be6fee15b28fd192d12c2ee5c8ac4cce30f25addda3135f77deec3dc65596767`,
  contains all five Archive chapters and all eight five-section Strikes Back
  chapters with the expected entry economics.
- The warning-strict full suite passed all 635 tests in 118.402 seconds.
  Compilation, profile JSON, endpoint YAML, and diff checks passed.
- No APK was built or installed and no physical-client run was performed.
  Bahamut 2000-1 and Strikes Back 8000-1 clear/result callbacks remain the next
  client-visible evidence boundary.

## 2026-07-30 guided-setup usability remediation

Objective: make `tester_setup --check` predict the exact guided setup path and
keep the normal first-run interaction limited to choices a new tester can
meaningfully make.

Evidence boundary:

- A supplied `DummyDll` directory without sibling `dump.cs` was reported as
  ready, although the mandatory story-outcome derivation rejects it.
- A complete generated `user-data/il2cpp/{DummyDll,dump.cs}` pair was ignored
  by preflight and by the early prerequisite gate, needlessly requiring
  Il2CppDumper again.
- A ready physical-device serial paired with the emulator-only `10.0.2.2`
  address passed preflight, then the real setup rejected it.
- `--check --port 70000` reached `socket.bind` and raised an uncaught
  `OverflowError`.
- Every normal interactive run asked about an advanced local event catalog
  even when no `--event-catalog` was supplied.

Plan:

1. Resolve explicit and generated IL2CPP artifact pairs through one shared
   helper used by preflight and the real build.
2. Validate the same port, device-host, requested-device, and physical-device
   routing conditions in preflight that the real setup enforces.
3. Enable advanced events only through the explicit CLI option.
4. Add focused regressions, update the operator documentation, then run the
   warning-strict focused/full suites, compilation, structured-file checks,
   and diff review.

This changes setup diagnostics and selection only. It does not change server
wire behavior, account state, replay semantics, or the canonical client
boundary.

Outcome:

- Preflight and the real build now resolve the same complete explicit or
  generated `(DummyDll, dump.cs)` pair. Generated output beneath the selected
  `--data-dir` is reusable without Il2CppDumper, while an incomplete supplied
  pair fails before hashing.
- Port range, device-host syntax, requested-device readiness, and the
  physical-device/emulator-host mismatch are reported by `--check`; an absent
  unselected device remains a warning for `--prepare-only`.
- The standard TTY path no longer asks about advanced events. Supplying
  `--event-catalog` enables the existing reviewed event path directly.
- The focused warning-strict setup suite passed 123 tests. The complete
  warning-strict suite passed all 625 tests in 118.332 seconds; compilation and
  diff checks passed.
- No APK was built or installed on a physical device in this pass. The changed
  behavior is command-line/preflight confirmed and covered with platform-neutral
  fixtures; Windows and physical-device operator confirmation remain pending.

## 2026-07-30 GitHub Issue 25 Chapter 3003-1 settlement deadlock

Status: implementation and release validation completed 2026-07-30; reporter
retest pending.

Objective: let the final Android client settle its observed 1,800-Coin
Chapter 3003-1 result and leave the durable `hunting_active` phase, so later
story and Hunting stages can start normally.

Evidence boundary:

- The Issue 25 attachment has SHA-256
  `c8f338759172437f93cedf89623550354c2919ad6ca2db0f5373cb3d3689518d`.
  Rejoining PowerShell-wrapped records yields 53 server events: 34 HTTP 409
  `invalid_local_hunting_result` responses for Chapter 3003-1 with exactly
  1,800 Coins and 19 later HTTP 409 `tutorial_state_conflict` responses. Every
  record names the durable phase `hunting_active`.
- The bundled local policy capped Chapter 3003-1 at 1,500 Coins. The rejected
  clear intentionally did not mutate or settle the active operation, so the
  durable phase survived both client and server restart and blocked every
  unrelated stage start.
- This final-client result confirms that 1,800 must be accepted for
  compatibility. It does not recover the retired service's complete reward
  distribution or validation rule.

Required proof:

1. Raise only the bundled Chapter 3003-1 Coin ceiling to the observed 1,800.
2. Reproduce the active settlement over real HTTP, restart before clear,
   refuse 1,801 without mutation, restart again, then accept 1,800.
3. Verify exact replay and another restart do not grant the Coins twice and
   leave the account in `free_roam`.
4. Run focused Hunting tests, the warning-strict full suite, compilation,
   JSON/YAML and diff checks, and clean-candidate publication gates.
5. Commit and push the bounded fix, then ask the Issue 25 reporter to update
   and let the existing reward-screen retry complete.

Result:

- The bundled Chapter 3003-1 ceiling is now 1,800 Coins. No other stage,
  reward channel, start cost, or mutation path changed.
- Thirty-five focused Hunting catalog/real-HTTP tests passed. The regression
  restarts with the operation active, refuses 1,801 without mutation, restarts
  again, settles the captured 1,800, replays the response, and verifies after
  another restart that Coins were granted once and the phase is `free_roam`.
- The warning-strict full suite passed all 619 tests in 118.143 seconds.
  Compilation, profile JSON, endpoint YAML, and diff checks passed. An exact
  clean source candidate passed the prohibited-material preflight and
  independent-history audit.
- Original-client acceptance remains with the reporter; the issue stays open
  until the existing reward-screen retry completes on the updated server.

## 2026-07-29 GitHub Issue 15 Android 11+ ARM64 allocator crash

Status: implementation and release validation completed 2026-07-29; original
Pixel 7 Pro acceptance pending.

Objective: prevent the final Android client's Unity 2017 ARM64 player from
crashing at the title screen when Android's Scudo allocator returns addresses
outside the five regions tracked by `UnityDefaultAllocator`.

Evidence boundary:

- The reporter's attached Pixel 7 Pro log reaches Unity 2017.4.37f1 ARM64
  IL2CPP, logs `Using memoryadresses from more that 16GB of memory`, and then
  terminates with signal 11 before the client reaches the server.
- Pixel 7 and Pixel 7 Pro are 64-bit-app-only devices. Removing
  `arm64-v8a` cannot run on the reported device, regardless of the separate
  path error in the reporter's attempted manual command.
- Unity issue 1284525 identifies this allocator/Scudo crash and fixed it in
  2018.4.30f1 by switching the internal Unity allocator to
  `DynamicHeapAllocator`; Unity 2017 did not receive that upstream fix.
- Matching official 2017.4.37f1 symbols identify the failing
  `UnityDefaultAllocator<LowLevelAllocator>::AllocationPage` implementation.
  The shipped player also contains and constructs
  `DynamicHeapAllocator<LowLevelAllocator>` elsewhere: its 176-byte object fits
  in each existing 192-byte default-allocator slot.

Required proof:

1. Gate any native change on the exact final-client APK member hash, Unity
   build marker, patch offset, and expected bytes.
2. Replace only the ARM64 default-allocator constructor with the engine's own
   compatible DynamicHeap layout; do not suppress the five-region error branch
   or alter ARMv7.
3. Confirm the replacement's disassembly, vtable, field bounds, and calls
   against the matching official symbol build and the already-used in-binary
   constructor sequence.
4. Build, align, sign, install, and exercise the title/login path on an
   Android 11+ ARM64 runtime; retain the reporter's Pixel 7 Pro retest as the
   original-device acceptance boundary.
5. Run focused patch/setup coverage, the warning-strict full suite,
   compilation, diff/YAML checks, and clean-candidate publication gates before
   commit/push and an Issue 15 update.

Result:

- The generated plan now verifies the exact final ARM64 Unity member hash and
  constructor bytes, then builds the player's existing
  `DynamicHeapAllocator<LowLevelAllocator>` layout in the original 192-byte
  slots. ARMv7 and all other Unity code remain unchanged.
- Seventy focused setup/patcher tests passed. The warning-strict full suite
  passed all 619 tests in 120.005 seconds; compilation, profile JSON, endpoint
  YAML, and diff checks passed. An isolated clean candidate passed the
  prohibited-material preflight and independent-history audit.
- An aligned and v1/v2/v3-verified signed APK stayed live through title startup
  and 40 real server requests on ARM64-only Android 12 and Android 14. The
  12 GB Android 12 process reached a 66,027,632 kB virtual-memory peak without
  the allocator message or signal 11.
- The unpatched Android 12 control also stayed live, so these AVDs did not
  reproduce the Pixel allocation pattern. The reporter's fresh Pixel 7 Pro
  result remains the client-acceptance boundary; the issue must remain open
  until that result is available.

## 2026-07-29 GitHub Issue 22 post-restart Tutorial03 userdata save

Status: completed 2026-07-29.

Objective: let a final Android client that is closed after Chapter 1-1 resume
the Recruit tutorial and reach its next Pact without weakening the tutorial
phase conveyor.

Evidence boundary:

- The reporter's current-server event log records repeated HTTP 409
  `tutorial_state_conflict` results for `/gd/userdata` while the durable phase
  is `chapter1_1_cleared`.
- Those requests use the existing tutorial party-save field order:
  `chrdata`, `teamMembers`, `teamMembers_VS`, `teamBuddies_VS`, `teamNo`,
  `teamNo_VS`, `summonId`, and trailing `lastUpdate`.
- The attached Android log independently shows the restarted final 5.5.7
  client entering `Tutorial03_start`.
- The submitted field values other than `lastUpdate=1` were not included in
  the privacy-bounded event log. No exact raw request capture is claimed.

Required proof:

1. Add only a phase-preserving structural acknowledgment at
   `chapter1_1_cleared`, reusing the already modeled party-save field and JSON
   constraints.
2. Exercise clear 1-1, a full server restart, the restore write, its replay
   after another restart, and the following `kind=12` Pact over real HTTP.
3. Confirm the restore write does not move the phase or mint/mutate roster
   state.
4. Run the warning-strict full suite, compilation, profile/YAML validation,
   and clean-candidate publication gates.
5. Commit and push the bounded fix, then resolve Issue 22 with the evidence and
   remaining original-device retest boundary stated explicitly.

Result:

- The profile now owns the observed party-save structure in
  `chapter1_1_cleared` as a same-phase structural acknowledgment. Its stable
  selectors and JSON field types remain constrained; submitted roster and team
  arrays are not applied.
- The real-HTTP tutorial path passed Chapter 1-1 clear, restart, restore,
  phase/roster preservation, restart replay, and the following `kind=12` Pact.
- The warning-strict full suite passed all 617 tests in 118.867 seconds.
  Compilation, JSON/YAML parsing, and `git diff --check` passed.
- An isolated clean source candidate passed material preflight and independent
  repository-history audit. Original-client acceptance of the post-fix response
  remains with the Issue 22 reporter.

## 2026-07-28 dedicated-server final-version Eidolon default

Status: completed 2026-07-28.

Objective: make the server-only launcher match the guided final-version solo
policy by leaving retired Tavern Eidolon enhancement disabled unless an
operator explicitly requests the archival compatibility route.

Evidence boundary:

- Version 5.5.0 retired Eidolon enhancement and in-battle use with Co-op/VS.
- The final 5.5.7 solo gap is the converted Chapters 4100--4111 quest and
  collectible settlement path, not `summon_skill_unlock`.
- Guided tester setup already omits `--summon-skills`, while server-only
  `STANDARD_POLICY_FLAGS` still adds it. The live Beelink child command
  confirmed that inconsistency.
- The route, loader, recovered 44-tier table, tests, and explicit
  `bootstrap_server --summon-skills` opt-in remain archival evidence and are
  not removed.

Required proof:

1. Remove only `--summon-skills` from server-only default policy flags.
2. Pin both supported launchers to omit the flag by default.
3. Preserve explicit archival option coverage.
4. Run focused launcher/archival tests, the warning-strict full suite,
   compilation, diff/YAML checks, and clean-candidate publication gates.
5. Commit, push, deploy, and verify that the Beelink child command omits
   `--summon-skills` while state, required catalogs, and transport remain
   healthy.

Result:

- `server_setup.STANDARD_POLICY_FLAGS` no longer includes `--summon-skills`;
  guided and server-only defaults now agree.
- The archival handler, recovered 44-tier policy, catalog option, configuration
  field, and explicit CLI flag remain available and tested.
- Thirty-six focused launcher, configuration, policy, and real-HTTP archival
  mutation tests passed. The warning-strict full suite passed all 596 tests in
  116.003 seconds; compilation, diff, YAML, and publication gates passed.
- Implementation commit `3fe4336` was pushed and deployed to the Beelink. Its
  live child command omits `--summon-skills`, retains both required generated
  catalog arguments, preserves the pre-deploy state hash, and answers loopback
  and LAN transport checks with HTTP 200.

## 2026-07-28 remaining solo systems: master-backed Companion equip restrictions

Status: completed 2026-07-28; original-client combined-write certification
remains pending.

Objective: make a newly equipped or retargeted Companion obey the final
client's character-family and species restrictions while preserving the
already-atomic bidirectional equipment transaction.

Evidence boundary:

- Final-client `Buddy.CanEquip` reads `exclusiveChrID` and
  `exclusiveSpeciesID`. It accepts a character restriction when it matches
  either the target character ID or that character master's nonzero ancestor,
  and it compares a species restriction with the target's active-job species.
- `RequiredLevel` is not read by `Buddy.CanEquip`; it controls whether an
  equipped Companion's effects activate. Low-level characters may equip the
  Companion, so the server must not turn that activation threshold into an
  invented selection refusal.
- Final `ChrDatabase` and `BuddyDatabase` contain every required structural
  field. Guided setup can project a source-free catalog from the operator's
  own APK without publishing names, skills, descriptions, assets, or
  acquisition data.
- Only newly equipped or retargeted links are checked. Existing links are not
  globally invalidated by an unrelated character or party save.

Required proof:

1. Generate and strictly load an APK-hashed local catalog containing character
   ancestors, per-job species, and Companion character/species restrictions.
2. Refuse a restricted-character mismatch, restricted-species mismatch,
   unknown master, and missing-catalog equip without changing either half.
3. Accept direct-character, ancestor-family, species-matched, unrestricted,
   and below-RequiredLevel equipment through real HTTP.
4. Preserve exact replay and restart behavior and the existing standalone
   preference/party write paths.
5. Make guided tester setup generate and pass the catalog; make server-only
   setup discover the conventional file when it is deployed alongside state.
6. Run focused catalog/setup/transport tests, the warning-strict full suite,
   compilation, diff checks, YAML validation, and clean-candidate publication
   gates.

Result:

- Guided setup now generates and passes `companion-equipment.json`; server-only
  setup discovers the same file beside durable state and reports when it is
  absent.
- The strict APK-hashed projection includes only character ancestry, per-job
  species, and Companion character/species restrictions. `RequiredLevel` is
  deliberately excluded from selection authorization.
- New and retargeted links fail closed on missing or unknown master authority,
  character-family mismatch, species mismatch, or a one-sided relationship.
  Existing links and unequip remain available without the catalog.
- Real-HTTP tests accept direct, ancestor-family, species-matched,
  unrestricted level-one, exact replay, and restart cases, while every
  rejection leaves both arrays unchanged.
- Thirty-five focused catalog, setup, configuration, and transport tests
  passed. The warning-strict full suite passed all 596 tests in 115.659
  seconds; compilation, diff, YAML, and clean-candidate publication results
  are recorded in the status files.

## 2026-07-28 remaining solo systems: final-version Eidolon classification

Status: completed 2026-07-28; converted solo quest settlement remains
capture-gated.

Objective: distinguish retired multiplayer Eidolon mechanics from the
collection content that still exists in the final 5.5.7 client, so the solo
completion list does not require recreating an unreachable battle system.

Evidence boundary:

- Version 5.5.0 discontinued Co-op and VS. Eidolons can no longer be summoned
  in battle, and their Tavern enhancement function was discontinued.
- The former Co-op Eidolon quests were converted to single-player quests.
  Final-client static evidence retains the Mode 4 selector,
  `eidolonQuestList`, Chapters 4100--4111, and a distinct result path carrying
  Summon collectible rewards.
- Owned Eidolons remain visible as collectibles under Options. That surviving
  collection surface is separate from the removed charging gauge and battle
  summon mechanic.
- The recovered `summon_skill_unlock` transport and material table are useful
  archival compatibility evidence, but they are not a required or proven
  reachable final-version solo loop.

Result:

- Eidolon battle summoning, its charging gauge, Co-op/VS integration, and
  Tavern enhancement are no longer classified as remaining solo systems.
- The remaining optional solo gap is the converted Eidolon quest lifecycle:
  selector visibility, start/clear, and durable collectible acquisition for
  Chapters 4100--4111.
- No acquisition mapping, reward settlement, or selector semantics were
  invented. Implementing that optional slice still requires an
  original-client quest/result capture with before/after owned-Eidolon state.
- Documentation, capability labels, and launcher help now state this boundary.
  Guided setup no longer enables the retired enhancement route by default;
  operators can still request its archival policy explicitly. No combat or
  acquisition behavior changed.
- Twenty-eight focused setup, configuration, and legacy-route tests passed.
  The warning-strict full suite passed all 589 tests in 116.973 seconds;
  compilation, diff checks, machine-readable YAML validation, and
  clean-candidate publication gates passed.

## 2026-07-28 remaining solo systems: Companion equip integrity

Status: completed 2026-07-28; master-backed eligibility and client acceptance
remain pending.

Objective: make the already-recognized combined `chrdata`, `buddyInfo`,
`lastUpdate` equip form enforce the recovered owned, one-to-one bidirectional
relationship before either half becomes durable.

Evidence boundary:

- Dual-ABI serializer/equip paths establish the exact combined form and that
  both dirty arrays represent one coupled mutation.
- A character's nonzero `buddy` is a Companion inventory ID; that Companion's
  `chrID` must point back to the same owned character. The resulting account
  may not assign one Companion to multiple characters.
- Required-level, exclusive-character/ancestor, and species eligibility require
  additional Companion/job master fields that the current public runtime does
  not carry. This slice must not invent those values or claim that wider
  lifecycle complete.

Required proof:

1. Project the Companion delta without mutating live state, merge the character
   delta, and validate the complete candidate relationship.
2. Accept a real-HTTP equip move, persist both directions together, replay it
   exactly, and retain it after restart.
3. Reject a one-sided/mismatched move with neither half changed.
4. Preserve standalone Companion preference writes and ordinary party writes.
5. Run focused transport tests, the warning-strict full suite, compilation,
   diff checks, and clean-candidate publication preflight.

Result:

- Companion deltas are now projected without mutating live state. Combined
  equip writes validate the merged character roster and projected Companion
  inventory before either is committed.
- Each nonzero character `buddy` must be an owned, uniquely assigned Companion
  inventory ID whose `chrID` points back to that character. Standalone
  Companion preference writes can no longer retarget `chrID`.
- A focused real-HTTP regression proves atomic mismatch and one-sided
  rejection, valid equip movement, exact replay, and persistence after a full
  server restart. Existing Companion preference and ordinary party tests pass.
- The warning-strict full suite passed 589 tests in 115.497 seconds.
  Compilation, diff checks, and clean-candidate publication preflight passed.
- Required-level, exclusive-character/ancestor, and species validation remains
  gated on adding the relevant generated master fields to the public runtime.
  Original-client combined-equip acceptance remains unclaimed.

## 2026-07-28 remaining solo systems: Fellowship Ticket Pacts

Status: completed 2026-07-28; original-client acceptance remains pending.

Objective: close the permanent Item 81 ticket-funded Fellowship and
Fellowship-side Fate draw loop through the final client's exact `kind=20`
transport without broadening into unrecovered campaign/event rate tables.

Evidence boundary:

- Dual-ABI client metadata identifies `NormalItem=20`, Item 81 as Fellowship
  Ticket, and the shared ordered `do_slot` form.
- The recovered permanent forms are exactly one draw with
  `campaignChrID=0`, `eventFlag=0`, and either ordinary or Fate `luckType`.
- The public server already has bounded Fellowship/Fate pools and duplicate
  policy. Ticket draws reuse those policies; they do not introduce a new pool
  or claim retired-service odds.
- The success callback reads the post-spend inventory. A successful ticket
  response must therefore include a detached `itemList` snapshot alongside the
  normal wallet and character result fields.
- The missing-ticket error-2 mapping is compatibility policy pending a live
  original-client refusal capture.

Required proof:

1. The strict parser accepts only `kind=20,count=1` with zero campaign/event
   selectors, while existing coin/Energy batches remain unchanged.
2. Ordinary ticket draws apply Fellowship Skill Boost semantics; Fate ticket
   draws apply Fellowship-side Luck semantics.
3. Success consumes exactly one Item 81 without spending Coins or Energy and
   returns the persisted post-spend inventory.
4. A missing ticket refuses without changing inventory, wallet, roster, or
   random selection state.
5. An exact real-HTTP retry replays byte-identically, and a retry after server
   restart does not consume or grant twice.
6. Focused Pact tests, the warning-strict full suite, compilation, and diff
   checks pass. Original-client acceptance remains a separate certification
   boundary.

Result:

- The parser admits only the exact one-draw `kind=20` permanent envelope and
  continues to reject nonzero campaign/event selectors.
- Item 81 now pays for the existing Fellowship pool. Ordinary ticket results
  retain Skill Boost semantics; `luckType=true` results retain the bundled
  Fellowship-side Fate Luck semantics.
- Success consumes exactly one ticket, returns a detached post-spend
  `itemList`, and leaves Coins and Energy unchanged. A Fellowship coin request
  is refused while the ticket remains because mixed payment is unproved.
- Real-HTTP tests cover ticket priority, ordinary success, Fate duplicate
  behavior, missing inventory, exact same-process replay, and replay after a
  complete server restart.
- Ten focused Pact/catalog tests passed. The warning-strict full suite passed
  588 tests in 114.571 seconds. Compilation and diff checks passed. A clean
  tracked-source candidate with this diff passed publication material
  preflight; the working checkout itself retains ignored onboarding evidence
  under `build/` and `user-data/` and is therefore not a release candidate.
- Campaign/event variants, mixed ticket/coin batches, and original-client
  ticket-draw acceptance remain outside this completed slice.

## 2026-07-28 clean public-onboarding certification

Status: completed 2026-07-28.

Objective: prove that a first-time operator can start from the exact public
source plus their own final APK and matching Android resource tree, let guided
setup generate every required local catalog, install the resulting client, and
reach a restart-safe compatibility server without relying on this project's
previously generated IL2CPP or catalog output.

Execution boundaries:

1. Clone the pushed public commit into an ignored clean-candidate directory and
   create a new isolated Python environment.
2. Treat the original APK and resource archive as read-only user-supplied
   inputs. Do not copy or modify anything under the private project's `input/`.
3. Permit an externally installed Il2CppDumper executable and platform Android,
   Java, ADB, and AArch64-disassembly tools as documented prerequisites, but do
   not pass an existing `DummyDll`, `dump.cs`, character catalog, native/scenario
   encounter map, story-outcome catalog, signing key, or account state.
4. Run the setup prerequisite check before generation and preserve its result.
5. Run guided setup through fresh IL2CPP extraction, master-data import,
   native/scenario encounter recovery, story-outcome generation, manifest
   hashing, APK patch/sign/install, and server launch.
6. Use an explicit ADB serial for every device operation. Begin on
   `emulator-5560`; if that existing AVD cannot render the client, create a
   disposable fresh AVD and record its explicit serial separately. Preserve the
   generated APK, catalog provenance, setup output, client log, request log,
   state before and after restart, commands, versions, and hashes under the
   ignored candidate.
7. Require original-client bootstrap/login/userdata plus a hash-approved
   resource over the real transport path. Restart the isolated server and
   require the same account to load without regeneration or state loss.
8. If the clean path fails, fix only the evidenced onboarding defect, add a
   focused regression, rerun the affected clean stage, then run the
   warning-strict full suite, compilation, diff checks, and release gates.

Completion boundary:

- This run certifies reproducible onboarding and runtime bootstrap only. It does
  not replace the existing clean Chapter 2-1 canonical gameplay boundary unless
  the fresh client is independently played through and recorded to that clear.

Result:

- A clean clone of the public source and a fresh Python 3.14 environment
  installed the declared `master-import` dependencies successfully. The run
  supplied only the immutable final APK, matching resource tree, and external
  platform tools; it did not supply any previous `DummyDll`, `dump.cs`,
  generated catalog, signing key, or account state.
- The first real run found a preflight defect: an Il2CppDumper apphost existed
  but could not locate its .NET runtime, so `--check` passed and setup then
  failed. Preflight now starts the configured dumper without inputs, recognizes
  its usage output, and names the `.dll` route when the apphost cannot start.
- With that documented `.dll` route, setup freshly generated 48 `DummyDll`
  assemblies, `dump.cs`, the character/native/scenario/story catalogs, 23,594
  resource mappings, local Pact banners, a local signing key, and a signed APK.
  Provenance validation matched every generated catalog to the supplied APK and
  the APK passed zip alignment and v1/v2/v3 signature checks.
- The existing emulator and a fresh AVD using their default/host graphics
  backends returned successful resources but rendered black with
  `GL_FRAMEBUFFER_UNSUPPORTED` / `0x506`. Restarting the fresh AVD as the
  README directs with the software ANGLE path rendered the title and tutorial.
- The untouched client performed one signup, three logins, two userdata reads,
  one tutorial Pact mutation, and 541 other recorded requests: 548 events total,
  all HTTP 200. It visibly advanced into the Recruit tutorial. After a complete
  server stop and documented server-only restart, it loaded the same hashed
  account and the persisted post-Pact tutorial state without regenerating any
  derived data.
- The focused preflight suite passed 19 tests. The warning-strict full suite
  passed 585 tests in 112.308 seconds. This certifies fresh onboarding,
  extraction, bootstrap, mutation persistence, and restart only; Chapter 2-1
  remains the deepest canonical gameplay boundary.

## 2026-07-28 behavior-preserving refactoring pass

Status: completed 2026-07-28.

Objective: reduce structural duplication and oversized responsibilities across
the public compatibility server and guided setup without changing protocol
shapes, preservation-policy boundaries, durable state, replay behavior, or
client-visible results.

Execution boundaries:

1. Establish a warning-strict full-suite baseline over the current dirty
   worktree and inventory the largest/most coupled modules.
2. Prefer small extractions with existing public behavior pinned by focused
   tests; do not combine this pass with new endpoint or gameplay coverage.
3. Preserve transaction, request-body replay, restart, interruption, and
   privacy behavior on every touched mutation or transport path.
4. Exercise affected functionality through real HTTP where the refactor reaches
   the server; exercise the guided setup CLI without writing local inputs where
   the refactor reaches setup.
5. Run compilation, the warning-strict full suite, diff checks, and applicable
   release gates before declaring the pass complete.
6. Record remaining architectural risks instead of disguising unsupported or
   unverified behavior behind generic abstractions.

Result:

- The compatibility-profile operation registry, template requirements, body
  transitions, and structural transitions now have one validation authority.
- GET content/resource serving is isolated from profile-backed reads. POST
  transport now separates route admission, bounded body reads, authentication,
  operation selection, tutorial/catalog arbitration, and result emission.
- Guided setup delegates generic progress rendering and quiet-child supervision
  to `liminal_gate.setup_progress` while preserving its existing callable API.
- No state mutation method, response envelope, endpoint matrix status, policy
  value, or canonical client claim changed.
- The pre-refactor warning-strict baseline passed 578 tests. After the pass,
  581 tests passed in 112.991 seconds; focused transport/replay/restart,
  setup/import, profile/config, and GET/resource suites also passed.
- Compilation and `git diff --check` passed. An exact clean source candidate
  passed both publication-lane material preflight and repository-history audit.

## 2026-07-27 Hunting selector runtime stability

Status: discovery in progress.

Objective: stop the original client's Hunting selector from flashing while
retaining the real, progress-gated Hunting rows and their existing bounded
server lifecycle.

Evidence boundary:

- The selector renders its four unlocked tier-1 rows, then the whole list
  flashes around the Attack of the Coin Creeps card and loading indicator.
- Live server diagnostics record no banner/resource failure or selector-time
  endpoint error.
- Static client analysis identifies a per-frame `UISpecialSelect.Update`
  writer of the list root position that runs only when rows exist. The exact
  oscillator remains unproved at runtime.

Required proof before a client patch:

1. Capture the original client while the flash occurs and exclude a failing
   resource, event timer, or subjugation request.
2. Identify the exact ARM64 and ARMv7 instruction boundary responsible for the
   repeated movement without disabling list initialization, scrolling, or
   selection.
3. Add source-byte-guarded dual-ABI plan entries and tests only if that boundary
   is confirmed.
4. Rebuild locally and confirm stable rendering plus a successful Hunting
   start; do not add duplicate rows or unlock later tiers as a layout hack.

## 2026-07-28 external-reference quest expansion

Status: Crystal Road completed as the first recovered additional route; other
stage activation remains gated on its own identity and settlement contract.

Objective: use operator-approved wiki and Terra Battle Stats reference data to
fill only the remaining bounded Huntland/Arena quest gaps.

Result:

- Existing Coin Creeps and Metal Zone policy values are corroborated by the
  external sources; no broad reward rewrite was needed.
- Supplied final APK recovery identifies Crystal Road as 3004-1, title
  `クリスタルロード`, three battles, and seven stamina. Mode 7 plus the exact
  `sp_ch_3004-1` flag supplies its visible Hunting route. Client ItemSet names
  identify its bounded material (1--17), Metal Ticket (50), and power-up
  (53--56) channels. It is now a permanent Chapter-3 local policy with a
  two-item maximum; original-service probabilities remain unclaimed.
- The 20 named Arena Special Quest pages require per-stage client identity,
  resource, reward/recruit, and lifecycle contracts. They remain unavailable;
  Tower, co-op, and VS are outside this solo expansion.
- `docs/external-quest-reference-ledger.md` records source provenance, current
  reconciliation, and the promotion gate.

## 2026-07-27 bundled Strikes Back vertical slice

Status: published 2026-07-27 with original-client clear still pending.

Objective: restore the packaged non-collaboration Counter Descent families to
Huntland -> Strikes Back through the standard server-only path.

Evidence boundary:

- `UISpecialSelect` mode 8 reads `descentHuntingList`; the standard public
  server does not send that list.
- The final client contains Chapters 8000--8007, five sections each. Recovered
  BattleData fixes their stamina to 5/10/15/15/15 and records no static Coin or
  item reward.
- The prior private implementation advertised one folded `<chapter>-1` row per
  unlocked family, opening Chapters 8000 and 8001 for the current account.
- Historical dates and server-authored reward/drop behavior remain
  unrecovered, so unlocks are permanent local policy and clears are zero-base.

Required proof:

1. The standard `--hunting` policy supplies all 40 startable stage identities,
   but `descentHuntingList` advertises only one folded row per family after the
   documented Chapter 5--12 gates.
2. Login emits only flags paired with those advertised rows; Counter Descent
   rows do not leak into Arena -> Special Quests.
3. Start charges exact stamina once, refuses locked/wrong-cost entries, and
   replays across restart without a second charge.
4. Clear accepts only unchanged progress, roster, inventory, Summons, and a
   zero reward result; retry after restart cannot grant twice.
5. Focused real-HTTP tests, full warning-strict tests, deployment, and one
   original-client Strikes Back start/clear pass before publication.

Result:

- The standard Hunting policy supplies Chapters 8000--8007, five sections per
  family, while `descentHuntingList` folds each unlocked family to one tier-1
  selector row. The current account receives only Chapters 8000 and 8001.
- Login flags come from the same progress-filtered projection. Counter Descent
  rows remain separate from Arena -> Special Quests.
- Real-HTTP regressions prove exact stamina debit, locked and wrong-cost
  rejection, active-stage retry without a second debit, restart recovery,
  zero-base clear validation, and restart-safe clear replay.
- The full 440-test warning-strict suite, compilation, diff checks, deployment,
  live status/login projection, and original-client selector plus Chapter
  8000-1 fight entry passed.
- At the user's publication request, the original-client battle-clear callback
  had not yet been observed. That client-visible clear remains the next
  Strikes Back boundary; the passing synthetic real-HTTP clear is not presented
  as a substitute.

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
