# Project Status

## Current phase

**1.0 released 2026-08-01; 1.1.0 released 2026-08-10.** What that claims is
narrow and stated in `RELEASE_SCOPE.md`: every single-player system the retired
client had is present, playable, and restart-safe, with reward settlement
explicitly labeled local preservation policy. It is not a fidelity or parity
claim, and 1.1 does not widen it — the minor bump records the size of what
landed between the two, not a stronger claim.

`PARITY_ROADMAP.md` now separates implemented behavior from permanently
unrecoverable behavior from open work. The unrecoverable set — Luck Treasure
Chest contents, Pact odds, event banner rates, the Trading Post rotation phase,
exact story reward settlement — are closed questions, not backlog: the retired
service computed each and the client only rendered it.

Next phase: extending original-client verification beyond Chapter 9, and
backing more of it with preserved traces rather than playthrough alone.

Issue 33 corrected the chapter-ticket boundary. A Pixel 7 Pro rendered the
Chapter 7 milestone row with an empty reward area and retained its unread badge,
disproving the prior server-only inbox acceptance. Guided core story now grants
eligible chapter tickets directly and atomically before login. Existing unread
milestone records migrate to one grant and read state; existing read/deleted
records do not grant again. Physical confirmation of Item 50 x2 and removal of
the stuck row remains pending.

Issue 35 restored the dormant ordinary-story daily bonus mechanism. Guided
core story now supplies the client-confirmed `enableDailyBonus` boolean during
login. The final client—not the server—uses its server-corrected instant and
local calendar day to select the recovered 15-day item-x2, monster-x2, or no
bonus slot and eligible chapter group. The schedule mechanism is dual-ABI
confirmed and independently matches the linked community calendar; keeping its
gate continuously enabled is explicit preservation policy because the retired
service event window was not captured. Physical badge and drop confirmation
remain pending.

An audit of the Pact of Fellowship against the community availability record
found the bundled pool flat where the record describes it as cumulative: 54 of
its 103 members open at Chapter 1, the rest across twenty-one gates to
Chapter 38, so roughly half the roster was drawable ahead of its recorded
unlock. Each member now carries its earliest chapter and the draw route filters
on the account's own `progressCode`, reusing the chapter reading that already
gates achievements and stage entry. The same audit found ID 122 in the roster —
an ID naming no character in the client — standing in for 126, Megacell, which
was consequently unobtainable. Truth keeps its whole pool, having no comparable
record, and `validate_bundled_pools` now refuses to start a Pact-enabled server
when a pool member does not resolve in the operator's character catalog. Pact
selection odds are unchanged and remain local policy. Whether Truth has its own
availability curve is unread.

The reported post-battle Luck reset exposed a regression in the shared roster
merge. A confirmed final-client clear legitimately omits the optional `luck`
member, but the merge protected only monotonic levels and Skill Boost, so it
discarded the durable field before returning the roster. Battle clears now
preserve the greater durable/reported Luck and then apply the cached
`luckUpTable` gain once inside the existing atomic clear transaction. Focused
real-HTTP coverage proves omission, explicit stale zero, exact replay, and
restart behavior. Already-reset values remain unrecoverable without a backup;
physical-client confirmation remains pending.

## Verified boundary

- The original Android client path is verified through **Chapter 9**, played
  continuously on physical hardware with no client-visible failure.
- Chapter 2-1 remains the deepest point backed by preserved request traces. The
  two are different kinds of evidence and both are recorded: traces prove the
  wire shapes exactly, the playthrough proves the game is finishable.
- The guided server provides ordered ordinary-story progression through
  Chapter 42 as explicit local policy.
- Supported mutations use durable atomic state and body-scoped replay across
  restart.
- Unknown LAN hosts cannot inherit the active account after signup/login.
- Public release checks inspect the proposed tree and prohibited Git-history
  paths.

See `docs/current-checkpoint.md` and `protocol/endpoint_matrix.yaml` for the
machine-readable/current capability boundary.

## Completed hardening

- 2026-08-09 the two secondary worlds became reachable, having been served and
  unreachable since 2026-08-02. A tester reported entering a Five Emperors
  descent and being refused, which read like a missing stage catalog; the
  stages were already there. Two other things were not, and either alone was
  fatal. The client's own "To another world" predicates call
  `IsSectionUnlocked` against `worldProgressCode` — for **world 0**, because
  both thresholds are main-story sections — and that key had never been sent,
  so the menu could not appear no matter which map flags were on. And
  `UIMap.SetWorld` writes `UserData.worldNo`, which is the wire's
  `worldMapNo`, so a player who had swapped maps sent a world this server
  compared against a stored zero in four places and wrote in none: the swap
  itself was refused, and then so was every clear behind it.
  `worldProgressCode` is now projected onto every userdata read as the object
  keyed by world index that `LoadUserdataFromJson` actually parses — an array
  throws inside LitJson, which is the boot hang another reimplementation
  reported and this project had never reproduced — with world 0 derived from
  `progressCode` and worlds 1 and 2 durable behind an explicit migration.
  `worldMaxChapter` is sent as the int array of internal chapter numbers
  `get_worldChapterNo` clamps against. The three-field cursor write is accepted
  when it moves only the world, and refused when it would also move story
  progress, which is the map-reveal route's business. A secondary-world clear
  advances that world's cursor and nothing else, so the per-world stamina-cap
  inflation another reimplementation recorded cannot arise here. All of it
  behind the existing `--secondary-worlds`. Three contracts this project had
  declined to guess at are now recovered rather than guessed — the
  `worldProgressCode` shape, what `worldMaxChapter` is compared against, and
  the fact that `WORLD_NUM` is not a served key at all — and so are both unlock
  thresholds, which were labeled local policy and are literal immediates in the
  client's predicates. See `docs/findings.md`, 2026-08-09.

  An adversarial pass over the change caught four defects the 1,372-test suite
  did not, and the worst is the one worth carrying forward: the three-field
  userdata form carries the tutorial's own final map write as well as the swap
  and the map reveal, and a dispatch rule separating only the latter two left
  the tutorial unfinishable — on *every* guided server, because
  `--secondary-worlds` is in `STANDARD_POLICY_FLAGS`. No test covered the
  tutorial with the flag on. Running the whole suite a second time with the flag
  forced on is now the cheap check for that whole class, and it is what proved
  the fix. The other three: a `free_roam` gate that a force-closed battle could
  never clear, a clear past a world's frontier advancing the cursor past every
  section in between, and a hand-edited cursor reaching the client outside the
  `Int32` it is read with. Server restart, and an APK rebuild for on-device
  testers. Unplayed: the thirty stages have still never run against a client.

- 2026-08-06 Attack of Coin Creeps cards stop blanking at random. Two reports
  described the same defect from different sides: one card blank after an
  unrelated Crystal Road run, another missing and later back on its own. The
  2026-08-03 derivation renames each copy's texture, container path, and bundle
  identity, but all three copies kept the serialized file name inherited from
  the retained `sp3003-1` source. Unity keys a loaded bundle by that internal
  file and refuses to load a second bundle providing it, so any two cards whose
  loads overlapped left one empty; `AssetManager` unloads each bundle on a delay
  after reading its texture, making it a timing race rather than a fixed blank.
  Decoding 1,200 retained bundles yielded 1,274 distinct internal names and no
  duplicates, establishing uniqueness as an archive invariant the derivation had
  broken. Each derived bundle now carries its own. Because the client stores
  images as `<asset>_<ver>.bin` and reuses them without asking again -- both
  `LoadImageAsset` download paths use `Application.temporaryCachePath`, and no
  route supplies a version -- the three aliased catalog records also carry
  version 111 so an install holding the broken bytes discards them. This one
  needs a rebuilt, reinstalled client, not only a server restart; saves are
  unaffected. Real inputs verified both halves: three derivations from the
  operator's own archive now hold three distinct internal names, all four
  distinct from the source, at unchanged 610x140 artwork, and a real patched
  `AssetVersions` carries the three alias records at version 111 beside the
  untouched 110 source. Physical-client confirmation after reinstall is pending.

- 2026-08-06 Fellowship Tickets settle in batches, and reach the Companion
  page. Two reports -- a Network Error on every multi-ticket press, and no
  Companion draw working with tickets at all -- turned out to be two different
  gaps behind one unsigned 501. The character-page ticket form had been read
  from a single one-ticket capture as a one-result-only form; the client's
  ten-pull control reaches the same `SlotKind.NormalItem` and sizes the batch
  from the tickets held, so every bulk press was refused. It now settles one
  through ten, one ticket per result, refusing a batch that outruns the
  remaining tickets rather than part-paying it. The Companion page turned out
  to carry four payment variants, not two: the implemented Energy pull and
  Companion Ticket, plus a Coin pull and its Fellowship Ticket variant drawing
  a separate 81-Companion pool, which was not a supported wire kind at all.
  Both pools now settle, each spending its own ticket ahead of its own
  currency, with the pool's own `DoBuddySlotErrorCode` on a shortfall. Pool
  membership is recovered from BuddyDatabase and cross-checked by
  reproducing the existing 114-member rare pool exactly; uniform selection
  within the new pool stays declared local policy, as the rare pool's already
  was. A user-supplied `--companion-draw-catalog` has no shape for a second
  pool, so under one the Coin kinds stay refused rather than drawing from the
  wrong pool. Eight focused tests; all 1135 repository tests pass.

- 2026-08-06 chests reach the whole game. The community record documents thirty
  story stages, so every other stage rolled six empty slots and a player past
  those chapters never saw a chest. An undocumented stage is now answered with
  the pools the record documents for the two chapters it sits between, merged
  across their sections and deduplicated -- on by default, with
  `--no-interpolated-luck-pools` restoring record-only behaviour, and
  `--luck-pool-catalog` still overriding both for any stage an operator names.
  No reward is invented: a test asserts every reward the rule can produce
  appears in the record for an adjacent chapter, and no Coin curve is fitted
  because the record's own values do not sit on one. Both bracketing chapters
  are taken rather than the nearer one, since single-chapter coverage is often a
  two-reward stub. The thirty sourced stages are never touched and a documented
  stage's empty tier stays empty, so what the record says stays separable from
  what this project arranged, and the server names its mode on every start.
  `PARITY_ROADMAP.md` continues to classify the real rates and pools as
  unrecoverable, because arranging the record's contents does not recover the
  retired service's table. Twenty-six focused tests; all 1126 repository tests
  pass warning-strict.


- 2026-08-06 Luck chest delivery and character-reward recovery. A tester asking
  why the post-battle chest screen never populated turned up two expected
  reasons — chapter 10 has no documented pool, and their team Luck was 0.1
  rather than the Skill Boost figure they were reading — and one defect. Chests
  award four wire forms; Coins and items were reconciled against the client's
  submission and the other two were dropped. `chest_companions` existed, was
  unit-tested and had no caller, while the pools carried thirty-nine Companion
  rewards across twenty-seven stage and tier slots; a real-HTTP clear confirmed
  the Companions vanish with the clear returning 200. The clear body is an exact
  field tuple with no Companion box, so the client cannot report them and the
  server now grants what it authored, inside the clear transaction, replay-safe
  and restart-safe. Separately, sixty-five of the sixty-eight character icons
  the pool scrape dropped resolve by exact name match against the operator's own
  `ChrDatabase` and are emitted in the `M` form; nineteen of thirty stages still
  lose a reward, down from twenty-eight. Three stay unresolved because the wiki
  distinguishes `Mage (Ice)` and `Lizardfolk Mage (Fire)` by an element the
  catalog does not carry against four same-named characters each. Four rows the
  scrape filed as unresolvable item names are recorded as actually naming three
  characters and Companion 128, and deliberately left alone: correcting a source
  is not the same decision as reading it. Eleven focused tests cover the four
  wire forms, the grant, duplicates, a full box, replay and restart; all 1100
  repository tests pass warning-strict. The thirty-stage pool coverage is
  unchanged and remains a limit of the record.


- 2026-08-06 inbox-present Companion visibility. A reporter's Companion screen
  stayed empty after a present granted one, survived a restart empty, and then
  showed two after a single draw. `buddyInfo.record` is a projection of
  `buddyInfo.list`, and `_apply_message_grants` was the only grant path that
  appended to the list without rebuilding the book; every other path returns
  through `_companion_info`. The Companion was granted, persisted and owned
  throughout, so nothing was lost — it was absent from the book the client
  renders, and only a later mutation that rebuilt the box wholesale exposed it.
  The present now rebuilds both halves, and a save that already drifted repairs
  on load from the owned list, granting and taking nothing. Four focused tests
  cover the present entering the book, a present arriving beside an owned
  Companion, load-time repair, and the invariant itself; the pre-existing test
  for this present asserted only the list, which is what let it ship. All 1089
  repository tests pass warning-strict. Whether the original client's book was
  monotonic is left open and unchanged: every path here derives it from what is
  currently owned.


- 2026-08-06 Android 16 launch crash re-diagnosed and the flag corrected. A
  Galaxy S26 crashed with all eighteen `--disable-google-services` dex edits
  verified applied, which ruled the dex out. `libunity.so` binds Play Services
  from native code for the advertising ID and carries its own copy of
  `com.google.android.gms.ads.identifier.service.START`, once per ABI, that no
  dex edit reaches; beside it sits the JNI table Unity builds its connection
  proxy from, declaring only the two-argument `onServiceConnected`. That proxy
  is the whole defect: a `java.lang.reflect.Proxy` routes an interface's
  `default` methods to its handler, while an ordinary class inherits them, and
  all twelve classes in the client dex implementing `ServiceConnection` are
  ordinary classes. The earlier attribution to Play Billing is therefore
  retracted — `BillingServiceManager$1` is an ordinary class and could not have
  thrown it; the S24 FE log line ordering was coincidence. The flag now rewrites
  the action's first byte in both `libunity.so` members, under per-member digest
  guards, with offsets read from the member rather than recorded and a member
  carrying the action twice refused. The head rather than the tail because a C
  toolchain may tail-merge string literals. The dex half stays at no cost. Seven
  focused tests cover both ABIs, the single-byte head edit, neighbour survival,
  and all three refusals; all 1085 repository tests pass warning-strict. The
  separate-server verification procedure is corrected too: `/healthz` cannot
  answer it on that route and the generated plan must not be used, since it is
  rewritten by every setup run and describes the last build rather than the
  installed one. Physical confirmation is complete: a Galaxy Tab A9+ (SM-X210)
  on Android 16, API 36, runs a separate-server build carrying all three edits
  through launch and real gameplay. That route has no host guard to mask the
  result and is the configuration the S26 crashed in, and it retires the
  standing risk in editing Unity's binary. No unpatched control was taken on the
  tablet, so the crash and the fix are each confirmed on Android 16 but on
  different devices.


- 2026-08-06 Orbling Cavern and Cryptid Forest reached. Repeated tester reports
  asked whether either was implemented; neither was, and neither was partially
  broken. `ChapterInterface::.cctor` identifies Chapters 7000--7009 as Orbling
  Cavern and 7010--7019 as Cryptid Forest, with sections only in 7000 and 7010.
  `UIMap::InitPoints0` builds each area's permanent World 1 map point only when
  `EventManager.IsEnabledAny` finds an enabled flag under `sp_ch_700` or
  `sp_ch_701`, a prefix scan over the served `eventFlags`; this server had never
  sent a key under either, so neither point was constructed and nothing reported
  it. `--cavern-forest` now sends four per-section flags, each of which answers
  its own card's `CheckQuestFlag` and carries its area's prefix, once an account
  has passed the client's own `openChapter` -- 5 for Cryptid Forest and 6 for
  Orbling Cavern. The four stages settle through the Hunting transaction as
  unadvertised rows, because `UISpecialSelect` modes 1 and 2 read hardcoded
  lists and never consult a served one, so the server can open the door and
  nothing more. Costs are one stamina and zero Coins throughout. Each Cavern
  card awards the single Companion its own `dropBuddies` names, Bahl OIII and
  Grace OIII, which the reporter states drops at 100% while unowned and not at
  all once held. Each Forest card farms one of Dracorin's two job-material sets,
  identified twice over: the client's Kirin constructors carry items 150/151 and
  152/153 at the chapter's `JobItemDropRatio` of 75, and the operator's own
  ChrDatabase prices character 188's two jobs at exactly those pairs. The
  chapter's constructor also corroborates the 2026-08-05 finding from inside the
  binary, carrying `luckyAddRate` 30 and `luckyAddRateSpecial` 50 -- the record's
  second-Runner chance and its Dracorin Λ *Cryptid Ruler* variant. One prior
  inference is withdrawn: `battleCnt` 0 does not mark a placeholder, since
  twenty-six chapters carry it including two implemented Archive events and the
  three confirmed-playable Daily Quests, and the real discriminator is whether
  the binary carries a `ChapterNNNN` class. Thirty-six focused tests cover the
  data policy, the flag gate and prefix property, real-HTTP entry, settlement,
  replay across restart, refusal without stranding the battle, and the same
  transactions again under `--outcome-strict`. Physical-client confirmation is complete: an
  operator opened both map points and both two-card selectors on hardware,
  cleared Orbling Cavern and received its Companion, and cleared Cryptid
  Forest with its job materials and Luck settling. Every claim these four
  stages carried is now closed.


- 2026-08-05 Issue 46 Strikes Back settlement: the first observed Counter
  Descent clear refuted the zero-base policy the family had carried since its
  vertical slice. That policy required a clear to grant nothing — zero Coins,
  zero experience, no items, no monsters, no Lucky enemy, roster and inventory
  returned unchanged — and a won Chapter 8000-1 battle reports all of it. Every
  real clear was refused `invalid_local_event_result`, which reaches the client
  as an unsigned 409 and so shows the transport dialog rather than an endpoint
  refusal; because a refusal leaves the battle open, the retry was refused
  identically and the reward screen became a dead end. All fourteen packaged
  families shared the defect. Counter Descent now settles as Hunting does: the
  client's report is trusted, and the inventory accompanying it must be the
  durable counts plus the drops it declares, capped at the client's stack
  ceiling, so the item array cannot grant beside the drops. Experience, Coins,
  Skill Boost, monsters, and Lucky enemies keep the trusted merge every other
  event clear uses; a Companion drop stays bounded by the stage's own recovered
  `dropBuddies` manifest; a reported Summon stays refused for want of any source
  that states one. Chapter 1100 keeps the bounded shape under its own name. Real
  HTTP coverage settles a clear reporting 5,400 EXP, 280 Coins, and 70 of item
  181, proves restart replay credits it once, and keeps refusals for an
  overstated inventory and a reported Summon. All 1,037 repository tests and the
  release audit pass. Physical-client retest by the reporter is pending, as is
  confirming their generated story-outcome catalog carries rules for chapters
  8000--8017: without one for the cleared identity, `_outcome_buddy_info`
  refuses the clear for a different reason.

- 2026-08-03 battle-clear Luck preservation: the shared roster merge now keeps
  monotonic Luck alongside job progression and Skill Boost. A real-HTTP story
  clear reproduces the final client's omitted field, keeps durable Luck 5.0,
  applies one authored 0.2 gain, returns 5.2, replays without another gain, and
  persists 5.2 across restart. An explicit stale zero is also unable to lower
  the save. The focused story/Luck lane passes 23 tests and all 957
  warning-strict repository tests pass with five expected skips. The correction
  reaches every clear family using the shared merge; physical-client
  confirmation remains pending.

- 2026-08-03 Issue 35 daily drop rotation: guided core story supplies the exact
  boolean `enableDailyBonus` login event flag. The final client computes the
  15-day five-chapter-group rotation and doubles only item or monster-recruit
  rolls; Companion and Battle Summon drops remain unchanged. Focused real-HTTP
  coverage proves the flag is absent by default, present with the exact nested
  shape when enabled, and enabled by `--core-story`. The focused login/setup
  lane passes 67 tests and all 955 warning-strict repository tests pass with
  five expected skips. This changes no durable state. Physical-client badge and
  eligible-drop confirmation remain pending.

- 2026-08-03 Issue 34 daily login rewards: guided core story now issues the
  community-recorded standard login schedule through the client's existing
  inbox. The consecutive reward follows an eight-day cycle, the cumulative
  track pays days 1--10, 30, 60, 100, and every 50 days after 100, and UTC
  midnight owns eligibility. Account state records the last eligible UTC day,
  current consecutive count, and total count in the same atomic save as the
  generated messages. Focused real-HTTP coverage proves dual day-1 issuance,
  read/delete settlement, same-day suppression, restart persistence,
  next-day advancement, and missed-day streak reset. Login projects only unread
  messages, preventing a claimed entry from returning as a new badge while its
  durable record remains available for replay and deletion. This is settled
  community-schedule local policy through a recovered inbox transport;
  original-client rendering/claim acceptance is still pending. The separate
  seven-day newcomer campaign remains outside this standard schedule until its
  item and Companion identities are audited.

- 2026-08-03 Attack of Coin Creeps card-art recovery: the final APK's embedded
  306-row `SpecialBanner` catalog contains `sp1001`, `sp1002`, and `sp1004`
  families but no `sp1003` record, matching the reporter's stable but blank
  Chapter 1003 card. The guarded local APK plan now derives `sp1003-1` through
  `sp1003-3` catalog aliases from the retained 610x140 `sp3003-1` record. Setup
  prefers exact operator-owned `sp1003` bundles and otherwise derives three
  ENCA bundles with matching internal texture/container names from the retained
  Coin Creeps-family art. A real final-APK rebuild round-tripped all three
  records; each derived bundle round-tripped through ENCA/Unity parsing, and
  real HTTP returned the 172,451-byte section-1 derivation exactly. All 927
  warning-strict repository tests pass. The APK/resource inputs remain
  unchanged; physical-client confirmation after reinstall is pending.

- 2026-08-03 client-trusted Hunting settlement: per-stage reward maxima no
  longer block ordinary Hunting, Metal, Special, or Daily Quest play by
  default. The final client owns the battle and reports its outcome; the server
  continues to require the exact active stage, wallet arithmetic, item/ticket
  reconciliation, Companion authoring data and box integrity, replay, and a
  durable one-time commit. `--outcome-strict` retains the maxima as an audit
  mode and no longer requires a story-outcome catalog when auditing Hunting.
  The Issue 20 Pixel log proves Crystal Road can report 280 Coins and
  5,400/5,625 EXP despite the old zero placeholders. Focused real-HTTP coverage
  accepts 280/5,625 and proves restart replay credits it once; strict-mode
  refusal coverage remains. Seventy-four focused tests and all 919
  warning-strict repository tests pass; compilation, structured-file, and diff
  checks pass. Physical-client retest is pending.

- 2026-08-04 first physical on-device gameplay report. An operator building on
  Windows installed the combined APK on a Pixel 7 Pro running Android 15,
  reached real gameplay progress, and then ran both
  `liminal_gate.on_device_state export` and `update` against it successfully —
  the latter rebuilding and installing in place with the accounts intact. This
  is the device acceptance the save-transfer entry below explicitly disclaimed,
  and it is recorded in `docs/on-device-setup.md` under Known-good setups and
  in the `COMPATIBILITY_SCOPE.md` Android host table. The report does not match
  the installed artifact against the final source-exact hash, does not exercise
  `import`, and carries no ARMv7 or preserved-trace claim; the Pixel 7 Pro is
  64-bit only and cannot serve as the ARMv7 check.

- 2026-08-03 on-device save transfer. The app-private `state.json` now has a
  supported route on and off the device, which supersedes the "no export/import
  exists yet" boundary recorded below. `liminal_gate.on_device_state`
  export/import/update drives a loopback-only `/local/state` route over
  `adb forward`; the same document the server would persist is served, and an
  import replaces memory and file together before rotating the displaced save
  into `state.json.bak.1`. `BootstrapState` load and import now share one
  parser, so an accepted import is by construction a document the next start
  will load. The destructive paths are unchanged and still destructive:
  `update` never uninstalls, and restoring onto a cleared install still needs
  `adopt` for the client's regenerated UUID. This is workstation tooling and
  establishes no new device acceptance.

- 2026-08-03 setup review pass, two defects fixed and the launcher checks made
  structural. Guided setup started the server against the operator's own
  `--resource-root` while the manifest had been built against the
  `data_u2017/android` directory detected inside it, so any accepted parent
  form built and installed the APK and then died on `resource file is
  unavailable`; the detected directory is now resolved once and used for both.
  The setup rehearsal gave setup an empty data directory and therefore never
  saw the tool locations `doctor --install-missing` records in
  `user-data/toolchain.json`, failing its own prerequisite check on an
  Il2CppDumper the machine had; the record is now carried into the run
  (`--toolchain`). Three hand-kept policy lists were replaced by checks derived
  from `LocalServerOptions` and compared across all three launchers — guided,
  dedicated, and the Android on-device runtime, which was previously unchecked
  and whose config feeds `ServerConfig` where every policy defaults off. The
  old lists already omitted `daily_quests` and `secondary_worlds`. Complete
  suite: 907 tests. A full rehearsal against the working tree was identical to
  the baseline in every compared field. Setup prerequisites and the guided
  launch path only; no protocol behavior or verified-boundary change.

- 2026-08-02 doctor-managed AArch64 disassembler: `doctor --install-missing`
  now installs Google's pinned side-by-side Android NDK r27d
  (`ndk;27.3.13750724`) below ignored `user-data/` when no existing objdump can
  read AArch64. It locates the official host `llvm-objdump`, executes the same
  capability probe the real derivation uses, and only then atomically records
  its exact path. SDK licence acceptance remains explicit; `sdkmanager` owns
  Google package retrieval and repository verification. Android Studio remains
  optional for physical-device use, while emulator creation stays outside the
  doctor. This changes setup prerequisites only, not protocol behavior or the
  verified client boundary. The warning-strict focused suite passed 113 tests
  and the complete suite passed 895 tests; a fixture executable exercised the
  production AArch64 capability probe. A real NDK download was not performed,
  because accepting Google's Android SDK licence is deliberately the tester's
  action.

- 2026-08-02 self-hosted APK operator documentation: the README now presents
  the separate-server and self-hosted layouts as explicit alternatives, and
  `docs/on-device-setup.md` carries one complete private-input-to-launch path.
  It records defaults, exact preflight and success output, device selection,
  first-run/restart verification, safe in-place updates, first-install seeding,
  generated artifacts, and self-hosted troubleshooting. The LAN physical-device
  guide is now clearly scoped to the separate-server layout. Save documentation
  no longer implies that workstation tools protect the app-private `state.json`:
  no supported export/import exists yet, so uninstall, clear-data,
  signing-key loss, and `--replace-existing` are called out as destructive.
  This improves reproducibility but establishes no new device acceptance.

- 2026-08-02 toolchain doctor: `liminal_gate.doctor` reports the build tools
  this machine has and, with `--install-missing`, fetches a Temurin JDK, the
  Android SDK Platform-Tools, Build-Tools, and Platform 35 through Google's own
  `sdkmanager`, pinned Il2CppDumper
  v6.7.46, and a private .NET runtime where the managed dumper build needs one.
  Each download, including pinned Gradle for the on-device host, is verified
  against a published checksum and unpacked with
  member-path and executable-bit handling; each success is recorded in
  `user-data/toolchain.json` as it happens, so an interrupted run keeps what it
  installed. `tester_setup` and `on_device_setup` replay that record into their
  own environment before resolving anything, which retires the per-OS `PATH`
  and `JAVA_HOME` setup that `docs/install-tools.md` used to lead with. A
  variable the operator exported still wins. Verified on macOS/arm64 with
  `PATH` reduced to `/usr/bin:/bin` and no `ANDROID_*` or `JAVA_HOME` set:
  `tester_setup --check` resolved adb, build tools, Il2CppDumper, and the
  disassembler from the record alone. Android Studio and emulator system images
  remain the operator's choice; the AArch64 LLVM tool no longer does. Google's
  SDK licences are never accepted without an explicit answer.

- 2026-08-02 private on-device server package: the reviewed source hash now
  drives one local command which repeats the complete guided derivations,
  redirects the client to fixed Android loopback, builds a dual-ABI
  Chaquopy/Python 3.11 host, embeds the full tester-owned resource tree, signs,
  and optionally installs/launches one APK. The replacement activity waits for
  a matching `/healthz` build ID before constructing Unity; app-private state
  retains the existing atomic/replay behavior and an optional seed cannot
  overwrite it. Schema-v2 resources stream from stored APK members while small
  catalogs/configuration are digest-checked and extracted atomically. The full
  retained tree produced 11,806 packaged resources (940,138,388 bytes) in a
  1.0-GiB APK; the final private artifact is
  `aeba11eade3b507d62403ee806b3e7390bb3a2abced03a0219e3ec4633685ef0`
  with payload ID
  `53d043cbb585337d19a749ef1a1735b31c5499bbe00c1376123d9600900fff93`.
  Package/SDK/launcher/dual-ABI inspection, new ZIP-header consistency,
  alignment, and v2/v3 signature verification passed. A preceding full-resource
  payload on API 34 ARM64 returned its matching health identity, initialized
  Unity, streamed a 129,018-byte resource with the exact manifest hash, and
  recovered after force-stop in a new process. The final payload could not
  replace it because that emulator had only 1.2 GiB free; its physical/device
  acceptance remains pending rather than inferred from the preceding build. ADB
  incremental install falsely reported success for this size and was replaced
  with a regression-tested non-incremental install. Physical-device, ARMv7
  runtime, and Chapter 2-1 acceptance are still separate pending evidence.
- 2026-08-01 repeatable setup rehearsal: guided setup is the path every operator
  takes and the one path the unit suite cannot reach, because it replaces the
  IL2CPP dump, the master-data import, the catalog derivations, the APK patch,
  and the signing with fakes. `liminal_gate.setup_rehearsal` now runs the real
  pipeline on a clean copy of the source in an isolated environment, then serves
  the generated catalogs to a scripted client over real HTTP — signup, login,
  userdata, the tutorial Pact, one hash-checked resource — across a full server
  stop and restart requiring the same account, the surviving starter, and a
  replayed rather than rerolled Pact. Every run's input hashes, artifact hashes,
  catalog counts, provenance, and transport result are compared field by field
  against a baseline kept beside the save, so a regression names itself instead
  of needing to be noticed. No device is involved; device certification is
  unchanged and still manual. Its first complete run found a defect the whole
  722-test suite could not see: `--daily-quests` was defined by the parser and
  read by `main` but never carried by `ServerConfig`, so **every command-line
  launch died with `AttributeError` before serving a request**, including the
  one guided setup performs. Fixed, with a structural test asserting that every
  launch option `main` reads is a field the configuration carries. See
  [docs/setup-rehearsal.md](docs/setup-rehearsal.md).
- 2026-08-01 Daily Quests implemented: the chapter-to-quest mapping was resolved
  by matching all fourteen APK banner textures pixel-wise against the community
  record's own banner images, giving a clean bijection — eleven matched at a
  distance under 1.1 where the nearest rival sat near 50. Three assignments had
  been predicted independently beforehand and are confirmed by it: 6006-1 Sweet
  Temptation from the client's `EnergyGetChapter`, 6011-1/2 as the two Yamamoto
  variants from being the only two-section chapter, and 6010-1 Lucky Orbling
  forced by the rotation's frequency classes. Those classes are separate
  evidence: each quest appears in the 41-day schedule exactly twice as often as
  its stage appears in `questOrder`, so both records partition identically.
  `bootstrap_server --daily-quests` now enables the category, sending
  `enableDailyQuest` plus a per-stage flag and accepting free entry and bounded
  clears on all fourteen. Stages use the `hidden` selector because the client
  lists Daily Quests from its own asset and never asks the server which exist.
  Reward ceilings are secondary-source local policy and cannot become recovered
  values, since the retired server owned rewards and the client only rendered
  them; item identities resolved through the operator's own master data and
  cross-check, with `Energy` landing on 80, exactly the client's `EnergyItemId`.
  Both gaps this work originally recorded are now closed. The Hunt For Joker
  grants Joker Λ through a new `character_grants` channel on `HuntingStage`,
  applied after the roster merge where `_preserved_roster` already protects a
  server-side grant; a duplicate raises Skill Boost 10.0% and Luck 10.0, capped
  at the client's ceiling. Every stage carries `once_per_utc_day`, the clear
  stamps the account's UTC day, and a second start that day is refused with the
  client's soft `success:false, errorCode` shape rather than an error. Real-HTTP
  coverage confirms login advertises `enableDailyQuest` plus all fourteen stage
  flags, and that the category stays off unless asked for. 691 repository tests
  pass, compilation clean. Remaining caveat: the soft refusal reuses the
  insufficient-resource code, so the client's wording may not name the real
  reason; sending the real `lastDailyQuestPlayTime` fields would fix that, but
  their wire format is not recovered and is not worth guessing.

- 2026-08-01 Daily Quest rotation recovered: `liminal_gate/daily_quest_importer.py`
  reads `DailyQuestData.questOrder` out of `assets/bin/Data/data.unity3d` in the
  operator's own APK, which is where the client keeps the schedule it computes
  itself. The downloaded resource pack does not carry it. An IL2CPP build leaves
  no type tree, and none is needed: the class declares one field, so the payload
  after the 28-byte header is a single length-prefixed string array and a parse
  that consumes the object exactly is self-validating. On 5.5.7-170 this
  recovers a 41-entry rotation across 14 stages, Chapters 6000--6012 plus
  section 2 of 6011, consuming 528 of 528 bytes, and that stage set matches the
  6000-block BattleData rows exactly in both directions. Nine focused tests use
  synthetic objects and need no APK; 671 repository tests pass. The day-to-index
  rule was not reproduced and does not need to be, since the client owns it.
  **Daily Quests remain unimplemented at runtime.** Thirteen of the fourteen
  stages have no battle program, stamina or coins, so a clear has no recovered
  outcome; nothing consumes the catalog, the three `lastDailyQuestPlayTime`
  fields are still unpersisted, and `DeleteDailyQuestPlayTime` is still absent.
  The community record names only two Daily Quests against fourteen recovered
  stages, which is unresolved and should be settled before any settlement rule
  is written. See the matching `PLANS.md` entry.

- 2026-07-31 Pact pool cap covered, Daily Quests blocked: removal from the pool
  at 100% Skill Boost turned out to be already implemented — the draw path
  filters on the catalog cap, `skillBoost` for an ordinary pull and `luck` for
  Fate, and refuses with `success:true, cmdError:3` when nothing eligible
  remains — so the audit was wrong to list it as unmodeled. It had no test; one
  now covers both the per-character exclusion and the exhausted pool, including
  that the coin balance is untouched by the refusal. All 662 repository tests
  pass. Daily Quests are **not** implemented and should not be until one thing
  is recovered. The server side is small (three `lastDailyQuestPlayTime` save
  fields, the `enableDailyQuest` flag, the `DeleteDailyQuestPlayTime` reset, and
  entry/clear), but in the 6000--6012 daily chapter block the operator's own
  BattleData gives exactly one row a battle program, 6007; 6006, which the
  client names `EnergyGetChapter`, is a zero-battle placeholder, and
  `BoostUpChapter` 6077 is absent entirely. Building it now would mean inventing
  the rotation, the rewards, and most of the stage set, the same reasoning that
  excluded the empty Eidolon placeholders and the Donation stages. Unblock
  condition: recover `DailyQuestData.questOrder` from the operator's Unity
  assets with UnityPy. See the matching `PLANS.md` entry.

- 2026-07-31 secondary-source audit of the bundled local policies: every value
  labeled local policy was checked against the community record. Thirteen
  bundled values are now independently corroborated rather than merely
  asserted, including the Metal Zone 6 and 7 gates at Chapters 26 and 30, where
  the commonly cited 27 and 34 are the pre-4.6.0 schedule and wrong for 5.5.7.
  Two were demonstrably wrong and are corrected: Pact duplicate gains were a
  flat +1 level and +1.0% Skill Boost for every class and are now banded
  (Z +6/+12.0%, SS and S +5/+10.0%, A and below +1/+5.0%), and Pact of Truth
  selection was uniform and is now weighted 4/10/15/71 across Z, SS, S and
  A-plus-B. Both are keyed on the `rarity` field of the operator's own
  APK-derived character catalog, so no roster data is bundled; without
  `--character-catalog` the old flat behavior is preserved. Neither table can
  be promoted to a recovered value, because
  `UIPactResult.PrepareShow(chrId, addedLevels, addedSkillBoost, addedLuck)`
  shows the client rendering server-computed gains and the only rate-adjacent
  client symbol is `RareSlotEnergy`; they are labeled secondary-source local
  policy wherever they appear. The class banding is cross-validated against
  recovered client behavior: `Character.get_luckMax` derives its cap from the
  same field and its non-Lambda caps fall on exactly those three groups.
  Documentation claiming eight Strikes Back families gated at Chapters 5
  through 12 was wrong in both numbers and now reads fourteen at Chapters 5
  through 18, matching `event_manifest_data.py`. Five focused tests added; all
  661 repository tests pass and compilation is clean. Open items are recorded
  under the matching `PLANS.md` entry, the most consequential being that the
  community record says 5.5.0 left Metal Zones reachable only as All Hail the
  King while this bundle advertises all fourteen sections and a tester
  previously confirmed a regular row on hardware. That conflict needs a device
  check.

- 2026-07-31 chapter-ticket milestone correction in progress: live state at
  Chapter 8-9 confirmed that the account had read the Chapter 5 Metal Ticket x2
  and Chapter 6 Companion Ticket x3 presents, held zero of each, and never
  received the earned Chapter 7 Metal Ticket x2 present. The guided core-story
  path now issues the retail Chapter 5/7 Metal and Chapter 6/8/10 Companion
  Ticket milestones through the existing inbox. Eligibility is based on the
  next unlocked chapter; issued IDs persist separately from messages so a
  read/delete/relogin/restart cannot duplicate a reward. Focused real-HTTP
  validation covers Chapter 8-9 backfill, early Chapter 8 exclusion, read
  replay, deletion, restart, and later Chapter 8 issuance. A migration run on a
  copy of the live save adopted Chapters 5/6, added only Chapter 7, and changed
  no inventory balance before read. All 656 warning-strict repository tests,
  compilation, diff checks, and both clean-candidate publication gates pass.
  Commit `d976bd5` is pushed and deployed on the Beelink under systemd PID
  264479. Live login at progress 8-10 retained the read Chapter 5/6 messages,
  created exactly one unread Chapter 7 Item 50 x2 message, and left Item 50 and
  Item 112 at zero until read. Physical-client inbox/read acceptance remains
  pending.

- 2026-07-31 solo Eidolon selector correction in progress: the maintainer's
  physical client showed the flaw in the 28-row projection because sixteen
  cards lacked banners. APK-matched BattleData has exactly twelve nonzero-battle
  rows in Chapters 4100--4111, and those identities exactly match the final
  Android `SpecialBanner` catalog and retained Android resources. The generator
  now emits only 4100-3, 4101-3, 4102-3, 4103-1, 4104-3, 4105-3, 4106-1,
  4107-3, 4108-3, 4109-3, 4110-1, and 4111-1, and refuses mismatched BattleData
  shape. Local output is 124 stages across 47 families with SHA-256
  `1b99bc264ac6dbba4f81f4d89105e54e804b9f12cdaa4078d516886b3044ceeb`.
  Forty focused tests and all 654 repository tests pass warning-strict;
  compilation, JSON/YAML parsing, and diff checks pass. The previous eight
  acquisition ceilings belonged to
  disabled raw tier rows and are no longer generated; moving them to the solo
  rows requires a real result capture. Both publication gates pass from a clean
  candidate. Commit, deployment, and device banner confirmation remain pending.

- 2026-07-31 tester documentation restructure: repeated reports that the setup
  instructions were not followable prompted splitting the 1,422-line README into
  a 245-line install path plus nine task-scoped documents under `docs/`. The
  README previously placed its first actionable step at line 313, interleaved
  three operating systems inside every step, wedged the dedicated-server/systemd/
  Tailscale material between "arrange your files" and "run setup", and buried the
  one-command invocation about 50 lines into its own section. The new order is
  install tools, `--check`, arrange files, start emulator, one command, play, with
  per-OS instructions separated in `docs/install-tools.md`. New files:
  `docs/install-tools.md`, `docs/emulator.md`, `docs/device-setup.md`,
  `docs/scope-and-status.md`, `docs/setup-manual.md`, `docs/saves.md`,
  `docs/troubleshooting.md` (regrouped by symptom location),
  `docs/dedicated-server.md`, and `docs/generated-files.md`. No instruction
  content was dropped and no command changed. The policy of not documenting how
  to obtain the APK or resource pack is unchanged and stated verbatim.
  `tests/test_systemd_unit.py` now asserts the dedicated-server lifecycle against
  `docs/dedicated-server.md` rather than a README heading range; all 654 tests
  pass and every relative link and anchor across the 40 Markdown files resolves.
  The stale README claim that solo Eidolon Chapters 4100--4111 were unsupported
  was replaced in `docs/scope-and-status.md` with the twelve battle/banner-backed
  stages that `docs/advanced-configuration.md` already documents.

- 2026-07-31 curated solo Archive expansion: dual-ABI
  `UISpecialSelect.SetMode(0)` analysis establishes that the server's nonempty
  `specialQuestList` owns the normal selector and the embedded 50-entry array
  is only a fallback. Guided setup now derives 42 release-facing stages across
  17 Archive chapters from matching user-local BattleData and character data,
  using the final selector's folded or explicit card identities. Native battle
  programs, archived backgrounds, and required explicit banners are present
  for every selected row. Test Chapter 2012, bannerless Chapter 2013, and empty
  2015-4--6 placeholders remain excluded. Historical schedules, complete
  rewards, and the local story gates/first-section grants are not claimed as
  recovered service behavior. At that checkpoint the retained inputs generated 140 stages across
  47 families; 139 focused warning-strict tests and all 653 repository tests
  passed, along with compilation and structured-file checks. See
  `docs/solo-event-completion-audit.md`. Commit `5302fb0` is pushed and deployed
  at `/opt/project-liminal-gate`. The Beelink regenerated the same 140-stage
  catalog with SHA-256
  `364048ce39141cad2712aba16561864bad9ad75a612c18c2f6c79bb2f753a863`.
  Systemd relaunched the service under PID 250477; Chapter 8 live status
  returned Archive cards `2000`, `2004-1`, and `3003-1`, three unlocked Counter
  Descent cards, all 12 Tower identities, and the then-incorrect 28-row Eidolon list.
  `/gd/multiplay_enable` returned `enable=false` and `enablemain=false`, local
  news returned HTTP 200, and the durable save remained byte-identical at
  SHA-256
  `cb0ccb214f6a13b3337b8410996788e6e386d287ad49ddf46bfe3b0c04655c3c`.
  The maintainer then opened the one Bahamut `2000` card in the physical final
  client and observed its four-section list. A fresh login/status session is
  present in the Beelink event tail. This is operator-confirmed folded-selector
  presentation, not yet Bahamut entry or result-screen certification.
- 2026-07-31 corrected Tower identity and solo-adapter implementation:
  authoritative final-client range predicates identify Chapters 9010--9013 as
  Tower of Temptation and 9100--9102 as Donation. The earlier public mapping
  was wrong. Guided setup derived all 12 actual Tower stages and initially all
  28 raw solo Eidolon rows from matching user-local BattleData; the later
  correction above narrows Eidolon to twelve battle/banner-backed rows. It
  explicitly excludes all 45 Donation stages. The dedicated selector lists
  open after a permanent Chapter 3 local gate; Arena VS and multiplayer remain
  disabled. Tower is labeled a solo adapter because shared HP, staged
  achievement, and reward state are unrecovered.
  Final-client native analysis establishes that ClearQuest sends the existing
  16-slot `summonList`, reports drops separately, and lets the result screen
  call `AddSummon`; its constructor establishes raw value `1`. Chapter-program
  to EnemyData ordinal mapping bounded eight disabled first-tier rows to one possible
  collectible each. The generic server path accepts no drop or that one unowned ID, commits
  it atomically, omits an unused response `summonList`, and refuses unlisted,
  duplicate, or already-owned reports without mutation. Exact replay survives
  restart. A real catalog generated 115 stages across 35 families and retained
  the BattleData SHA-256
  `be6fee15b28fd192d12c2ee5c8ac4cce30f25addda3135f77deec3dc65596767`.
  Focused generator/runtime validation confirms the exact 12 Tower rows, zero
  Donation rows, the then-incorrect 28 Eidolon rows, ordinary durable Tower entry/clear/replay,
  and the disabled multiplayer response. All 648 warning-strict repository
  tests passed in 127.822 seconds; compilation, structured-file validation, and
  diff checks passed. Both publication gates passed from clean commit
  `99a6143`. The Beelink fast-forwarded to that commit, regenerated a 115-stage
  catalog with SHA-256
  `8e23ea0f63614050c73bf7cf7154ca27d641688b69ac54f575c5c298ca457cf9`,
  and restarted under PID 241704. Live status returned the 12 exact Tower rows,
  the then-incorrect 28 Eidolon rows, and no Donation row; `multiplay_enable` remains false and
  loopback news returns HTTP 200. The durable save remained byte-identical at
  SHA-256
  `cb0ccb214f6a13b3337b8410996788e6e386d287ad49ddf46bfe3b0c04655c3c`.
  The maintainer then opened the corrected Tower selector on the physical
  final client and retried its first entry; the battle loaded successfully.
  That is operator acceptance of Tower navigation and entry, not yet a
  preserved trace or a Tower clear/result certification. Eidolon client
  acceptance and Tower result-screen return remain pending.
- 2026-07-31 late non-collaboration Counter Descent expansion: the bundled
  solo policy now includes Chapters 8012--8017 in addition to 8000--8007.
  Final-client static identities and the retained APK-matched BattleData
  establish three sections per added family with exact stamina costs of
  5/10/15 and zero entry Coins. Permanent Chapter 13--18 gates and zero-base
  settlement remain explicit local policy because the retired schedule and
  reward service were not captured. Little Noah Chapters 8008--8011 and Hime
  Rush 8018 remain unavailable rather than being forced through the ordinary
  event lifecycle. Real-HTTP coverage proves projection, explicit exclusion,
  exact entry, restart before clear, durable settlement, and exact replay
  after another restart. Arena VS remains disabled. Original-client selector,
  battle, and result acceptance for the added families remain pending. Thirty
  focused event tests and all 644 warning-strict repository tests passed; a
  fresh local catalog generated 76 stages across 20 families with all 18 added
  rows and none of the excluded chapters. Compilation, profile JSON, endpoint
  YAML, and diff checks passed.
- 2026-07-31 Jade Dragon original-client settlement: an exact Chapter 2004-1
  clear showed that Archive results use the client's reported battle Coins in
  addition to any cataloged fixed clear increment, and that the final client
  can send the observed `itmp0=-1` sentinel. The server now accepts that
  bounded shape, rejects a stale wallet and sentinels below `-1`, and retains
  Counter Descent's separate zero-base restriction. After deployment, the
  maintainer retried the retained result and the physical client exited the
  result screen after HTTP 200 without another network error. Durable state
  returned to `free_roam` with 11,824 Coins, 27 free Energy, 78 characters
  including Jade Dragon, and the submitted item counts; its SHA-256 remained
  byte-identical after the service
  restarted under a new PID. Real-HTTP tests cover refusal, settlement, exact
  replay, and restart replay. Thirty-six focused tests and all 642
  warning-strict repository tests passed; compilation, structured-file, and
  diff checks passed. Other Archive families and Strikes Back remain separate
  client-clear boundaries.
- Superseded 2026-07-31 live Archive/Tower catalog deployment: regenerated the local
  event catalog from the retained APK-matched BattleData projection and
  character catalog, producing 58 stages across 14 event families. The
  character catalog hash matches the authority already recorded by the live
  story-outcome catalog. Beelink commit `05d2980` now loads both generated
  files; a real Chapter 8 `get_server_status` response advertised Bahamut,
  Jade Dragon, Money Money Time, three unlocked Strikes Back families, and
  what was then mislabeled Tower 9100-1. The service restarted under its existing systemd unit, the
  account state validated, and loopback HTTP returned 200. Arena VS remains
  disabled and the optional converted Eidolon quest lifecycle remains
  unsupported.
- 2026-07-31 first tutorial Pact retail outcome: the exact mandatory `kind=10`
  request now selects Bahl (character 1) or Grace (character 3) from two equal
  weights instead of always granting Grace. Selection, starter identity, roster,
  team, canonical response, and replay cache commit atomically. Exact retry does
  not reroll and remains byte-stable after restart. All later tutorial party and
  response projections resolve from the durable starter; older Grace-only saves
  without the new field remain compatible. Real-HTTP regressions force both
  outcomes and carry Bahl through A'misandra and the next tutorial userdata
  settlement. The 50/50 rule is maintainer-supplied retail evidence; an
  original-client Bahl run remains pending. Thirty-two focused tests and all
  641 warning-strict repository tests passed; compilation, structured-file,
  and diff checks passed.
- Retracted 2026-07-31 — 2026-07-30 Tower 9100-1 vertical slice: guided setup
  derives one five-stamina, zero-Coin Tower row from the tester's matching
  BattleData and advertises it through `towerQuestList` after Chapter 3. The
  final client statically contains that dedicated list, Tower selector mode,
  Tower chapter-range handling, and Chapter 9100 battle code; the mapping is
  strongly inferred rather than original-client accepted. The other 44
  recovered 9100--9102 floors remain unavailable. Focused real-HTTP coverage
  proves the progress gate, exact selector and login flag, entry, body-scoped
  retry/refusal, rejected-clear stability, successful clear, restart replay,
  unchanged story progress, and the unchanged disabled Arena VS response.
  The permanent Chapter 3 gate and zero clear Coins are local policy. The
  warning-strict full suite passed all 638 tests in 120.460 seconds. This
  result is retained as an audit record only: 9100--9102 are Donation, not
  Tower, and the corrective implementation removes them;
  compilation, profile JSON, endpoint YAML, and diff checks passed.
- 2026-07-30 Il2CppDumper exit-code defect: a Windows tester's complete dump was
  rejected because Il2CppDumper v6.7.46 ends even a successful run with a
  "press any key to exit" `Console.ReadKey` that .NET refuses while setup
  captures the process, leaving an unhandled exception and a non-zero exit.
  `ensure_il2cpp_dump` now decides on the produced `DummyDll/*.dll` and
  `dump.cs`, reports the non-zero exit instead of failing on it, always keeps
  the run in `user-data/il2cpp/il2cppdumper-last-run.log`, and ranks the refused
  keypress below any other reported fault. See `docs/findings.md`.
- 2026-07-30 guided Archive Special Quests and Strikes Back: complete guided
  setup now writes `event-catalog.json` from the same user-owned BattleData and
  character catalog it already derives. The normal server loads Archive
  Chapters 2000, 2001, 2002, 2004, and 2006 automatically, merges their
  Special Quest rows with bounded Chapter 3003-1, and retains the bundled
  five-tier policy as the authoritative owner of Strikes Back Chapters
  8000--8007 at that checkpoint. The Chapter 2/4/10/13/20 archive gates, zero
  fixed clear-Coin increment, and first-section associated-character grants
  are explicitly local policy; variable battle Coins are reconciled from the
  client result.
  Older explicit catalogs without an unlock gate still load. Generated
  catalogs are atomic and hash-bound to the matching character catalog;
  server-only setup discovers both together or fails clearly. Affected-domain
  real-HTTP tests cover merged selector projection, entry, body-scoped
  same-ID/different-body refusal, bounded character settlement, replay, and
  restart for Archive and Strikes Back. The existing final-client-derived
  BattleData projection contains every advertised Archive/Strikes chapter and
  expected section economy. The warning-strict full suite passed all 635 tests
  in 118.402 seconds; compilation, JSON/YAML, and diff checks passed.
  Original-client Jade Dragon clear is now confirmed; Bahamut and Strikes Back
  clears remain pending.
- 2026-07-30 guided setup usability: `tester_setup --check` and the real build
  now share one complete IL2CPP-artifact resolver. A supplied `DummyDll`
  without sibling `dump.cs` fails before hashing, while a complete generated
  pair beneath the selected `--data-dir` is reused without requiring
  Il2CppDumper to remain installed. Preflight also reports invalid port ranges,
  explicitly requested devices that are not ready, and physical devices paired
  with the emulator-only host as required failures rather than deferring them
  to the build or raising a traceback. The normal TTY path no longer asks a
  first-time tester about advanced local events; the existing reviewed path is
  enabled explicitly with `--event-catalog`. The focused warning-strict setup
  suite passed 123 tests and all 625 warning-strict tests passed in 118.332
  seconds; compilation and diff checks passed. No APK/device run was performed,
  so Windows and physical-device operator confirmation remain pending.
- 2026-07-30 Issue 25 Chapter 3003-1 settlement deadlock: the reporter's
  privacy-filtered event log contains 34 rejected clears for the same
  final-client 1,800-Coin result, followed by 19 rejected unrelated actions;
  all 53 records retain the durable `hunting_active` phase. The bundled Special
  Quest ceiling was 1,500, so the correct non-mutating refusal also preserved
  the active operation across client/server restart and blocked every later
  stage start. The ceiling now accepts the observed 1,800 while refusing 1,801.
  A real-HTTP regression restarts before both the rejected and accepted clear,
  then verifies exact replay, a further restart, one Coin grant, and
  `free_roam`. Thirty-five focused tests and all 619 warning-strict tests
  passed; compilation, JSON/YAML, diff checks, and both clean-candidate
  publication gates passed. This is compatibility evidence for one observed
  result, not a recovered historical reward distribution. Reporter retest
  remains pending.
- 2026-07-29 Issue 15 ARM64 title crash: the reporter's Pixel 7 Pro log is a
  Unity 2017 allocator failure, not a network or firewall failure. Matching
  official 2017.4.37f1 symbols identify the five-region
  `UnityDefaultAllocator` page tracker, while Unity's fixed 2018.4.30 path
  switches Android to `DynamicHeapAllocator`. The exact final 2017 player
  already carries and constructs that allocator elsewhere, and its 176-byte
  object fits the existing 192-byte slots. Generated plans now hash-gate the
  Unity member and replace only its ARM64 default constructor with the
  in-binary DynamicHeap layout. Signed builds survived title startup and real
  HTTP on ARM64-only Android 12/14; the 12 GB Android 12 process reached a
  66,027,632 kB virtual-memory peak without the old message or signal 11. That
  AVD did not reproduce the old crash in its unpatched control, so Pixel 7 Pro
  acceptance remains pending. The earlier 32-bit suggestion was inapplicable:
  Pixel 7/7 Pro accept 64-bit apps only. The reporter's later command also
  named a directory instead of the APK and did not update the checkout.
  Seventy focused setup/patcher tests and all 619 warning-strict tests passed;
  compilation, profile JSON, endpoint YAML, diff checks, and both clean
  candidate publication gates passed.
- 2026-07-29 Issue 22 post-restart Recruit recovery: a current-server event
  log showed the final client repeatedly receiving HTTP 409
  `tutorial_state_conflict` from `/gd/userdata` after Chapter 1-1, while the
  attached Android log showed `Tutorial03_start`. The request used the same
  ordered party-save shape already modeled later in the tutorial, but no
  structural acknowledgment existed at `chapter1_1_cleared`. The profile now
  accepts that exact structural family as a phase-preserving no-op: it neither
  mutates the roster nor advances past the still-required `kind=12` Pact. The
  real-HTTP regression covers clear, restart, restore, replay after another
  restart, preserved roster/phase, and the following Pact. The warning-strict
  suite passed all 617 tests in 118.867 seconds. Reporter retest remains
  pending.
- 2026-07-28 the master-data readers no longer stage the APK member on disk:
  `character_catalog_importer`, `battledata_importer`, and
  `scenario_encounter_importer` each wrote `data.unity3d` into a temporary
  directory and handed UnityPy its path. A temporary file the reader still
  holds cannot be removed on Windows, so the cleanup that ends the `with` block
  raises *after* the work has succeeded and inside the try that reports the
  work as failed -- which is where a tester's run stopped, with `could not read
  chapter TextAssets from the APK` and no cause. UnityPy accepts the bytes
  directly; loading the reviewed member both ways yields identical serialized
  files and the same 13,726 `resources.assets` objects, and the scenario import
  still recovers all 50 chapter 2-7 stages and 182 placements. All three
  reports now carry the underlying exception type and message, and one
  unreadable TextAsset among thousands is skipped rather than ending the import:
  a chapter lost that way is already named by the missing-asset check.
  Unverified on Windows.
- 2026-07-28 a failed dump says what the dumper said: the report was the last
  line of its output, which for an unhandled .NET exception is the innermost
  stack frame -- a Windows tester was told only that something happened at a
  line number in Il2CppDumper's own source. Stack frames are now dropped, the
  line stating the fault is preferred over the progress notes around it, and
  the whole output and exact command are written to
  `user-data/il2cpp/il2cppdumper-last-run.log`. Both APK members are also
  checked against the magic the dumper recognises them by (ELF, and metadata's
  `0xFAB11BAF`) before it is started, so a wrong or split APK names itself
  instead of surfacing as a crash inside someone else's source. The output
  directory is passed with a trailing separator, which releases predating the
  `Path.GetFullPath` normalization concatenate rather than join.
- 2026-07-28 the readiness probe no longer asks Il2CppDumper to prompt: it ran
  the tool with no arguments to read the usage line a console build answers
  with, which is how the Windows release is asked to open a file picker. The
  reporting tester's `--check` put two dialogs on screen, failed whatever was
  chosen, and reported that a correctly installed tool could not start. The
  probe now passes three arguments naming paths inside a discarded temporary
  directory, so there is nothing to prompt for and nothing is written, and
  readiness is that the process ran rather than what it printed -- a complaint
  about inputs it cannot parse proves as much about the runtime as a usage line.
  A probe that outlives its timeout is also accepted, since a process cannot
  block without having started, and it is killed either way. The missing-.NET
  case it exists to catch is still failed, now recognised by the apphost's own
  text. Those three arguments name *staged files that exist*: the tool skips an
  argument whose path is absent rather than refusing it, so the first attempt at
  this fix -- absent paths -- left the same nothing behind as no arguments at
  all, and the tester met both dialogs again. Confirmed against stubs
  reproducing each rule. Still macOS-only verification.
- 2026-07-28 the dumper variable says why it did not work: a Windows tester
  passed every other `--check` line and could not pass this one with the tool
  installed, because `LIMINAL_GATE_IL2CPPDUMPER` naming the extracted release
  directory, and naming a path that does not exist, both printed the text for a
  variable that was never set. The variable now also accepts that directory
  (`Il2CppDumper.exe`, `Il2CppDumper`, then `Il2CppDumper.dll`, so a release
  shipping both needs no .NET runtime), and each failure names its own cause:
  unset, nonexistent path, directory holding no release, or an assembly with no
  `dotnet`. Only the unset case still advises installing the tool. Surrounding
  double quotes are stripped, since a value set with `setx` keeps them.
  Discovery remains `PATH` and that variable; the current directory is not
  searched, which the README now says. 10 focused tests added; the full
  warning-strict suite passed all 606 tests in 116.807 seconds; compilation
  passed. Not yet confirmed by the reporting tester on Windows.
- 2026-07-28 final-version Eidolon classification: Version 5.5.0 retired
  Eidolon battle summoning, its multiplayer charging-gauge use, and Tavern
  enhancement. Those are not missing solo systems for the final 5.5.7 client.
  Former Co-op Eidolon quests were converted to single-player, however, and
  the final client retains their selector and distinct collectible result
  path. The remaining optional gap is therefore Chapters 4100--4111 quest
  visibility/start/clear and durable collectible acquisition, not an Eidolon
  combat mechanic. The existing skill-unlock route is retained as archival
  static compatibility evidence behind an explicit option, not enabled by
  either supported default launcher or claimed as a reachable final-version
  UI loop.
- 2026-07-28 remaining solo equipment integrity: combined
  `chrdata`+`buddyInfo` equip writes now project both dirty arrays before
  mutation and require every nonzero character `buddy` link to match the owned
  Companion inventory record's `chrID` in both directions. One-sided
  Companion-only retargets and mismatched combined moves are refused without
  changing either half. Guided setup now derives an APK-hashed, source-free
  catalog containing the exact character ancestry, per-job species, and
  Companion restriction fields used by final-client `Buddy.CanEquip`. New or
  retargeted links enforce direct-character/ancestor-family and active-job
  species restrictions; unknown or missing authority fails closed. Existing
  links and unequip remain usable. `RequiredLevel` is deliberately not an
  equip prohibition because the final client uses it for effect activation
  after selection. Real-HTTP acceptance, rejection, exact replay, and restart
  coverage passes; original-client combined-write certification remains open.
- 2026-07-28 remaining solo Pact payment slice: the strict permanent
  `kind=20,count=1` form now spends one Item 81 Fellowship Ticket through the
  existing bounded Fellowship pool. Ordinary draws retain Skill Boost
  duplicate behavior; `luckType=true` uses the Fellowship-side Fate Luck
  policy. Success returns the detached post-spend inventory without charging
  Coins or Energy. Missing-ticket, ticket-priority, exact replay, and restart
  paths are covered over real HTTP. Campaign/event selectors and mixed
  ticket/coin batches remain unsupported, and original-client acceptance is
  still pending.
- 2026-07-28 clean public onboarding: a clean public-source clone, fresh Python
  environment, immutable final APK, matching resource tree, and external
  platform tools completed the whole documented path without any pre-generated
  IL2CPP output, catalog, key, or account state. Setup freshly produced 48
  `DummyDll` assemblies, `dump.cs`, all required generated catalogs, 23,594
  resource mappings, a signed APK, and durable state. The untouched client then
  completed signup/login/userdata, loaded hash-approved resources, visibly
  entered the Recruit tutorial, committed its first Pact mutation, and loaded
  the same account and tutorial state after a full server restart. All 548
  captured requests returned HTTP 200. This run also caught and fixed a real
  first-run defect: `--check` accepted an Il2CppDumper apphost that existed but
  could not start because its .NET runtime was undiscoverable. Preflight now
  executes a non-writing readiness probe and directs affected users to the
  `.dll` route. The focused preflight suite passed 19 tests and the
  warning-strict full suite passed 585 tests in 112.308 seconds. This is clean
  onboarding/restart certification, not a new gameplay claim beyond Chapter
  2-1.
- 2026-07-28 behavior-preserving refactor: compatibility-profile route and
  transition schemas now have centralized validation; GET content serving is
  separate from profile reads; POST handling is split into bounded transport,
  authenticated dispatch, userdata-shape selection, catalog/tutorial
  arbitration, and response emission; and generic setup progress/process
  supervision lives in `liminal_gate/setup_progress.py` behind the existing
  `tester_setup` API. No endpoint, wire shape, state transaction, replay rule,
  preservation-policy value, or client-certification claim changed. The
  warning-strict baseline passed 578 tests; the refactored tree passed 581
  tests in 112.991 seconds, including focused real-HTTP collision/restart
  coverage, plus compilation and diff checks. An exact clean source candidate
  passed release material preflight and independent-history audit.
- 2026-07-28 guided-setup usability: first-run friction reduced without
  changing what setup produces. `--check` reports every prerequisite in one
  pass and writes nothing; the disassembler and `master-import` checks moved up
  beside the SDK tools, so an incomplete toolchain no longer surfaces only
  after the resource tree has been hashed and an IL2CPP dump produced; the
  resource tree is hashed once and shared between the input and resource
  manifests instead of read twice; hashing and disassembly report progress
  rather than going silent for minutes; the throwaway local key password is
  generated by default (`--prompt-key-password` restores the prompt); and the
  `--port` default now matches the documented `8696`. `README.md` lists
  Il2CppDumper, the AArch64 disassembler, and the `master-import` packages
  under "What you need" rather than partway through the setup walkthrough.
- 2026-07-28 Crystal Road: supplied final APK analysis recovered Chapter 3004-1
  (*Crystal Road*), its three battles, seven-stamina entry, mode-7 Huntland
  selector, and required exact event flag. The bundled policy now enables it
  after Chapter 3 with a two-item material/Ticket/power-up ceiling from the
  operator-approved reference table. The permanent availability and the
  absence of server-side random rolls are explicit local policy; original
  service probability/settlement capture remains unavailable.
- 2026-07-28 external-reference reconciliation: operator-approved Terra Battle
  Wiki and Terra Battle Stats entries now have a durable ledger. They
  corroborate the bundled Coin Creeps and Metal policy values. Supplied final
  APK recovery then resolved Crystal Road; the remaining Arena Special Quest
  pages still remain per-stage work packets. This preserves the distinction
  between an external reward table and client-compatible behavior.
- 2026-07-28 default Special Quest support: the guided server now advertises
  recovered Chapter 3003-1 (*Money Money Time*) after Chapter 3, together with
  its exact `sp_ch_3003-1` flag. It uses the Hunting start and clear
  transaction, so its five-stamina entry, strict-audit refusal behavior,
  body-scoped replay, and restart handling are covered by real HTTP tests. Its
  1,800-Coin ceiling is now bounded by Issue 25 final-client evidence; the
  permanent unlock remains explicit local preservation policy, not a claim
  about the retired event rotation or complete reward rule. Generated Archive
  rows merge with this default; an explicit override replaces only those
  Archive rows. The supposed Tower 9100-1 slice was later retracted; the actual
  12-stage Tower 9010--9013 solo adapter and solo Eidolon archive are described
  in the later 2026-07-31 work above.
  Arena VS remains unsupported.
- 2026-07-28 story Companion drops settle instead of being silently discarded,
  and the outcome catalog stops refusing what it merely cannot evidence. A live
  account cleared the whole story seeing only Metal Zone's Companions: the
  client rolled the rest correctly, `clear_quest` returned `200`, and the roll
  was thrown away because minting `buddyInfo` requires a story-outcome catalog
  and the guided launcher never passed one. Metal Zone was unaffected only
  because it mints through the bundled Hunting policy on another path.
  Supplying the catalog was not by itself a fix, because the same option bounded
  reported items, monsters, roster, and Summons, and an empty ceiling *forbids*
  — so every stage the encounter join could not reach would have started
  refusing clears that report an ordinary item drop. Four changes together:
  (1) the Companion ceiling, the one that is complete for every stage from its
  own `dropBuddies` allowlist, is now always enforced and always minted, and the
  item/character ceilings moved behind `--outcome-strict`;
  (2) evidence is recorded per stage, so "drops nothing" and "nobody could know"
  stop being the same empty dict — a joined stage keeps forbidding, an unjoined
  one does not, and a catalog without the field behaves as before;
  (3) variant enemy symbols resolve by peeling one suffix at a time and
  re-checking membership instead of stripping the whole run, plus bare trailing
  digits, which recovered 15 symbols and 10 whole stages across chapters 12--42
  that had been failing because `CH31_LEAD_S_WITH_PARENT` overshot the real
  member `CH31_LEAD_S`;
  (4) `--scenario-encounters` feeds the MoonSharp-derived chapter 2--7
  encounters, which have no compiled battle program, through the same
  `EnemyData` join under separately validated provenance.
  Result: 291 of 393 core story stages can mint a Companion (was 277), item
  ceilings cover 349 stages (was 289) and character ceilings 166 (was 120), and
  the only core chapters left without evidence are 38--42, whose enemy rows the
  client never shipped. The roster subset check is gone even under strict:
  `_preserved_roster` documents that the durable roster can legitimately lead
  the client's copy, and charging the player a clear for that lag is a
  regression, which a test now pins.
- 2026-07-28 ordinary chapter completion restores stamina as explicit local
  preservation policy: a successful core-story chapter-boundary clear commits
  `refillStartTime: 0.0`, the final client's own full-meter representation.
  The same durable clear transaction and cached response protect retry and
  restart behavior; individual story stages, Hunting, events, and World Map
  Special remain unchanged. This is not a claim about the historical service.
- 2026-07-28 a refused write says why: an `unsupported_*` result recorded only
  the field list, which cannot distinguish a supported form from a refused one
  — six live equip writes were refused on a field tuple that the same client
  had accepted minutes earlier, and nothing in the log could name the half or
  the key at fault. Refusals now record `request_shapes`: per JSON-valued
  field, its type, entry count, distinct key-set count, and the value types
  seen against each key. The privacy boundary is unchanged and now explicit —
  key names appear only when this server already models them, so no string
  from a body can reach the log. The existing log-privacy regression caught
  the first draft echoing body key names.
- 2026-07-27 endpoint refusals reach the screen that asked: every route that
  refused an action semantically emitted `success:false` with its own code in
  `errorCode`. That is the *transport* namespace (`AppServerUtil.ErrorCode`:
  1, 90, 100-115), read only when `success` is false, on a path that shows the
  common error dialog and never invokes the endpoint callback. Refusing a
  Trading Post trade with `NotEnoughItems` (3) therefore produced a bare
  "ErrorCode : 3" server error rather than the counter's own message. A route's
  code rides `cmdError` on an accepted success, which the client defaults to
  zero and passes as the callback's first argument; the Add Job route was
  already corrected, and the wire boundary now applies that shape to all of
  them. Every field the exchange callback reads is `Contains`-guarded, so a
  refusal body carries no state refresh.
- 2026-07-27 the Trading Post names its currency: the bundled rotation prices
  all 126 offers in Animata Cores but sent `weeklyItem: 0`. The screen counts
  how many of `weeklyItem` you hold and files every other exchange currency
  under a parenthesised remainder, so the header read "0 (+249)" for a player
  holding 249 Cores. The catalog now derives the field from the rotation's own
  single cost item. `endDate` remains empty: the rotation's real-world phase
  was never recorded, and the client's expected date format is unconfirmed.
- 2026-07-27 rotated-token authenticated reads: the client replaces its OTK
  about every three seconds, so an authenticated read almost never arrives on a
  token an earlier mutation bound. `get_current_exchange` resolved its token by
  raw lookup and answered `401 unknown_account`, which surfaced on a live
  server as a network error when the player entered the trading post. Both it
  and `userdata_after_close` now resolve through `bind_rotated_token`, exactly
  as the `userdata` read and every mutation already did. The household guard is
  unchanged and covered by test: an unidentified LAN host is still refused once
  any client has identified itself. `RotatedTokenReadTest` closes the gap that
  hid this, where every exchange test reused the literal signup token.
- 2026-07-27 Strikes Back vertical slice: the standard Hunting policy exposed
  the eight then-packaged non-collaboration Counter Descent families through
  the dedicated, progress-gated `descentHuntingList`, with five startable tiers
  per family and exact recovered stamina costs. Start and zero-base clear are
  bounded, replay-safe, and restart-safe. The live client displayed Spinetrich
  Kino and Kraken Kino and entered Chapter 8000-1 successfully; its battle-clear
  callback remains unobserved and is not claimed as client-certified. Issue 46
  later observed it, and it refuted the zero-base clear recorded here; see the
  2026-08-05 entry.
- 2026-07-27 Metal/Special selector ownership: the bundled Metal list now
  includes both regular sections 1--7 and All Hail the King sections 11--17,
  plus both Roads. Exact per-section flags replace the broad Chapter 3000 flag,
  and an explicit server-owned Special Quest list suppresses the client's
  50-entry fallback. The live status/login payload matched that projection and
  the relaunched original client confirmed the corrected menu ownership.
- 2026-07-27 live Metal clear recovery: an original-client Chapter 3000 clear
  repeated its pre-entry Item 50 count even though the server had already
  committed the ticket spend. Ticket-backed starts now retain that choice;
  clear accepts only that one stale slot and preserves the lower durable
  balance. Exact-capture replay, restart, stamina-fallback, and non-minting
  regressions passed. The paused live clear then returned HTTP 200, retained
  3 tickets, granted Companion 128 once, and returned the account to free roam.
- 2026-07-27 resumed-account Huntland/Tavern compatibility: pre-login status
  resolves migrated progress without exposing it to an unrelated owned host;
  advertised Metal rows receive their required client flags; permanent
  `luckType=true` Fate draws and original-client packed roster records now
  settle and replay through the ordinary Pact transaction. Live client
  validation showed Hunting and Metal selectors and completed a Pact summon;
  locally derived Pact banners are served without adding game images to the
  repository.
- 2026-07-27 persistent Linux service: the generic systemd template and
  `scripts/install_systemd_service.sh PORT` install the server-only path as the
  invoking unprivileged user, restart it after any exit, and enable it for
  normal multi-user boot. Live validation confirmed an active and enabled unit,
  recovery to a new PID after a forced main-process failure, and identical
  resource delivery over LAN and private-overlay paths. The public README
  documents prerequisites, foreground validation, client preparation on
  another computer, systemd lifecycle commands, and optional subnet-routed
  access without embedding validation-host details.
- 2026-07-27 dedicated server-only setup:
  `python3 -m liminal_gate.server_setup --port PORT` validates and hashes the
  resource tree, retains durable state beneath `user-data/`, enables every
  standard bundled policy, and runs on the LAN without inspecting an APK or
  invoking Android SDK, ADB, Java, signing, emulator, or device paths. A live
  dedicated-host run served the same hash-validated resource over LAN and
  private-overlay paths; no new original-client boundary was claimed.
- Source-only public repository and noncommercial framing.
- Hash-validated user-owned resource serving and guarded local APK tooling.
- Account backup, recovery, adoption, validation, and save editor.
- Bounded request bodies and explicit unsupported-route behavior.
- Privacy-safe event diagnostics isolated from transport and account-state
  implementation.
- Replay-safe story, Hunting, Pact, Companion, Trading Post, message,
  achievement, job, Rebirth, and status-item local policies where declared.
- Release preflight, Git-history audit, CI matrix, and publication checklist.
- 2026-07-26 strict validation: 287 tests passed with resource leaks promoted
  to errors; the exact clean source candidate passed preflight and history
  audit.
- 2026-07-26 GitHub issue 16 audio discovery: paired working/silent captures
  prove the app track and Android mixer keep advancing with zero underruns after
  audible output disappears. Public guidance no longer attributes the cutoff
  to `swangle`, core count, or an AudioFlinger/HAL stall.
- 2026-07-27 tester setup diagnostics: failed `zipalign` or `apksigner` runs
  now report the Android tool's exit code and captured error output while
  continuing to pass signing passwords only through local files.
- 2026-07-27 full-review follow-up: repaired TOML-only launch and strict
  policy-boolean validation; made account safety copies non-overwriting;
  restored fresh-reinstall account selection; bound generated story outcomes
  to exact APK provenance; restricted optional mutation trailers to
  `lastUpdate=1`; and corrected the parity roadmap's item/character ceiling
  claim.
- 2026-07-27 strict validation: 417 tests passed with resource leaks promoted
  to errors; compilation and focused transport, persistence, parser, launcher,
  and provenance regressions passed.
- 2026-07-27 combined release validation: 429 tests passed with resource leaks
  promoted to errors; compilation, diff checks, and clean-candidate preflight
  and repository-history audits passed.
- 2026-07-27 Huntland/Tavern validation: 434 tests passed with resource leaks
  promoted to errors; compilation, diff checks, and clean-candidate preflight
  and repository-history audits passed.
- 2026-07-27 Metal clear validation: 436 tests passed with resource leaks
  promoted to errors; exact captured-state replay, compilation, and diff checks
  passed.
- 2026-07-27 selector ownership validation: 436 tests passed with resource
  leaks promoted to errors; 61 focused catalog/runtime/HTTP tests, compilation,
  diff checks, live HTTP projection, and original-client acceptance passed.
- 2026-07-27 Strikes Back validation: 440 tests passed with resource leaks
  promoted to errors; focused catalog and real-HTTP restart/replay checks,
  compilation, diff checks, live projection, and original-client fight entry
  passed.
- 2026-07-28 Fellowship Ticket validation: 10 focused Pact/catalog tests and
  the full 588-test warning-strict suite passed; compilation and diff checks
  passed. No original-client ticket draw is claimed yet.
- 2026-07-28 combined-equip validation: four focused real-HTTP
  Companion/party tests and the full 589-test warning-strict suite passed in
  115.497 seconds; compilation, diff checks, and clean-candidate material
  preflight passed.
- 2026-07-28 final-version Eidolon classification validation: 28 focused
  setup/configuration/legacy-route tests and the full 589-test warning-strict
  suite passed in 116.973 seconds; compilation, diff checks, YAML validation,
  and clean-candidate publication gates passed.
- 2026-07-28 master-backed Companion equipment validation: 35 focused catalog,
  setup, configuration, and real-HTTP transport tests passed. The full
  warning-strict suite passed all 596 tests in 115.659 seconds. Direct,
  ancestor-family, species-matched, unrestricted level-one, rejection,
  missing-catalog, exact replay, and restart behavior are covered.
  Compilation, diff checks, YAML validation, and exact clean-candidate material
  preflight and independent-history audit passed.
- 2026-07-28 final-version server-default validation: the server-only launcher
  now agrees with guided setup and omits retired `--summon-skills` by default.
  The explicit archival route and recovered cost table remain intact. Thirty-six
  focused launcher/configuration/policy/HTTP tests and all 596 warning-strict
  tests passed in 116.003 seconds. Implementation commit `3fe4336` was deployed
  to the Beelink: its live child command omits the retired flag, retains the
  story-outcome and Companion-equipment catalogs, preserves the exact
  pre-deploy state hash, and passes loopback and LAN HTTP checks.

- 2026-08-02 Daily Quest settlement correction (issue 29): a Yamamoto Puzzle
  Quest clear reporting the Companion the client's own `dropBuddies` manifest
  allows was refused, and a refused settlement never releases the active
  battle — so the account stayed `hunting_active` across a force-close and
  every unrelated stage was refused afterwards, which is what the tester
  reported as a corrupted installation. 6011-1 and 6011-2 are the only two of
  the fourteen with a manifest; their codes decode to Companions 267 and 140,
  one copy each, now settled at level 1. The same review found three more
  bounds in the family that would each have wedged an account the same way:
  a zero EXP ceiling on all fourteen, both Puzzle Quests bounding only their
  first reward tier and a third of their item capacity, and Rarity Rumble's
  Ores and Tearjerker Time's Tears and rings left undeclared. The refusal
  diagnostic now names the channel by count, which it could not before. All 889
  warning-strict tests passed in 143.977 seconds, including a real-HTTP
  regression that starts 6011-1, settles the reported Companion, and proves the
  account returns to `free_roam`.

## Blockers and unresolved fidelity

- Full-resource combined-APK acceptance on physical ARM64 hardware and an
  ARMv7 runtime, including cold start, force-stop/relaunch, one exact resource,
  tutorial Pact, and Chapter 2-1 state/retry/restart proof.
- Original-client confirmation that the Hunting selector no longer flashes. The
  cause is identified and fixed server-side: `UISpecialSelect.UpdateItems`
  revalidates every drawn row with `CheckQuestFlag` and has none of the
  Chapter 1000--1099 exemption that `IsQuestOpen` applies while building the
  list, so the unflagged tier-1 Hunting rows were removed and rebuilt once per
  frame. Every advertised row now carries its own exact `sp_ch_` flag. No APK
  patch is required; the earlier per-frame `set_localPosition` candidate was
  ruled out by disassembly and must not be patched.
- Original-client Strikes Back battle clear and return to free roam. Selector,
  tier navigation, and Chapter 8000-1 entry are confirmed; clear is currently
  covered only by the real-HTTP regression.
- Original-client Archive Special Quest navigation, Chapter 2000-1 entry,
  battle clear, associated-character result, and return to free roam, plus one
  injected late explicit Archive card. Jade Dragon 2004-1 is client-confirmed;
  the broader curated archive currently has static/master/resource proof plus
  generated-catalog and real-HTTP regressions.
- Retired Tavern “Watch Video” controls are client/ad-SDK UI. The server does
  not advertise or implement an ad service; hiding those controls requires a
  separately validated APK patch.
- Original-client verification beyond Chapter 9, and trace-backed evidence for
  more of the path already played.
- Exact ordinary-story reward/drop authority and scripted-stage exceptions.
- Original-client Tower clear/result return and acceptance of converted solo
  Eidolon Chapters 4100--4111, including before/after collectible state for one
  successful Eidolon drop. Tower navigation and first-stage battle loading are
  operator-confirmed on the physical final client; their local durable result
  lifecycles are implemented. Eidolon battle summoning and enhancement are not
  gaps because Version 5.5.0 retired them with multiplayer.
- End-to-end original-client certification of the combined Companion
  equipment/party transport. Master-backed selection restrictions are covered
  statically and over real HTTP; `RequiredLevel` is client-side effect
  activation, not an equip restriction.
- Original-client acceptance of the permanent Item 81 Fellowship/Fate ticket
  draw; current proof is static client evidence plus real-HTTP regression.
- Historical event schedules, campaign behavior, and live-service families.
- Differential certification against excluded private reference evidence.
- Emulator audio cutoff inside the Unity 2017.4/FMOD producer path. Native
  translation and the 24 kHz client track are candidate discriminators, not
  confirmed causes; a matched working Pixel 4 profile capture is outstanding.

## Next recommended task

Capture the evidence behind the physical on-device install. A Pixel 7 Pro on
Android 15 has now reached gameplay with the combined APK, so what remains is
the recorded proof rather than the question of whether it runs: confirm the
installed artifact against the final source-exact hash, then record cold start,
one manifest-approved resource, signup/login, tutorial Pact, and a Chapter 2-1
clear with exact retry plus force-stop/relaunch state proof. Repeat the
startup/resource boundary on an ARMv7 runtime, which that device cannot supply. Then, on the final client,
clear Bahamut 2000-1 through its result screen and certify Strikes Back 8000-1,
Tower 9010-1, and Eidolon 4100-3 one at a time with before/after state and
restart proof.
