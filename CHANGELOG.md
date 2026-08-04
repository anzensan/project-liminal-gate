# Changelog

## Unreleased

### Added

- **Daily login rewards now arrive through the original inbox** (issue 34).
  Guided core-story servers issue the published eight-day consecutive cycle
  and cumulative rewards for days 1--10, 30, 60, 100, and every 50th day
  thereafter. Eligibility turns over at 00:00 UTC. Same-day relogins do not
  duplicate a present, a missed UTC day resets only the consecutive count, and
  the cumulative count survives. Issuance commits with the account before the
  login response exposes either present; the existing inbox read/delete
  transaction then grants Coins and Energy once across retries and restarts.
  Login now projects only unread presents, so a claimed message cannot be
  reconstructed as a fresh menu badge; its durable record remains available
  for exact read replay and explicit deletion.
  The separately branded seven-day newcomer campaign is not folded into these
  standard rewards: its item and Companion identities remain a distinct event
  policy to audit.

- **`--disable-google-services` gets the client past an Android 16 launch
  crash.** The 2017 client dies on `NoSuchMethodError` in `bitter.jnibridge` the
  moment a Google Play Services bind completes: Android 16 added an
  `onServiceConnected(ComponentName, IBinder, IBinderSession)` overload, and
  Unity's `java.lang.reflect.Proxy` for `ServiceConnection` is handed `default`
  methods rather than inheriting them, so the 2017 bridge is asked for a
  signature it does not know. The bridge is Unity's and cannot be rebuilt, but
  the crash needs a *completed* bind, so the flag rewrites the final byte of
  each of 18 bind actions and the Intent resolves to nothing. Two are Google
  Play Billing: a physical Galaxy S24 FE log ends `UnityIAP: Billing service
  connected.` immediately before the fatal, which makes billing the confirmed
  cause. Play Billing lives in `com.android.vending`, a different package from
  Play Services, so the 16 Play Services actions — inferred from the same
  mechanism rather than observed — do not reach it. Play Games, the ads SDK, Google auth, and Nearby have no live service
  to reach. The two `ICommonService`/`ICommonCallbacks` binder descriptors are
  deliberately untouched. Available on both routes, since both install the same
  client. The patch plan schema is version 2: a dex edit invalidates the
  `checksum` the runtime enforces and the `signature` ART reports as
  `dex-id-...` and caches against, so patches declare `repair_dex_header` and
  both fields are recomputed. A dex `string_ids` table is also *sorted*, and an
  in-place edit preserves every offset but not the order, so plan generation
  refuses any replacement that would not still sort between its neighbours —
  an unsorted table is rejected by the runtime and the app dies at load.
  Not every Google interaction can be stopped this way: once GMS loads a
  Dynamite module into the app's process, that module binds using its own string
  constants, which no edit to the client's dex can reach.
  **Off by default, and it should not stay that way.** It rests on one Android
  16 device. A build carrying only the Play Services actions got that device
  past its launch crash and as far as the billing bind, so the mechanism is
  established; the billing actions that follow from its log are not yet
  confirmed to finish the job. Make it the default once a patched build reaches
  gameplay on Android 16 *and* one clean Android 14/15 run shows no regression.

- **The on-device save can be moved off the device.**
  `python3 -m liminal_gate.on_device_state export|import|update --device SERIAL`
  reaches the packaged Android build's save through the embedded server's new
  loopback `/local/state` route over `adb forward`. Until now that save had no
  route out at all: the app is not debuggable, so `run-as` is unavailable, and
  `adb backup` stopped carrying app data for release packages after Android 11.
  `export` changes nothing on the device and writes a full copy under
  `user-data/on-device-state/`. `import` refuses a file that breaks the client's
  invariants or that has lost an account the device holds, replaces the
  in-memory state and the file together so a running server cannot undo it,
  rotates the replaced save into `state.json.bak.1`, and restarts the app to
  confirm the result. `update` exports before it builds and never uninstalls —
  on a signing-key mismatch it stops and prints the recovery steps. Every
  workstation command in `liminal_gate.account_state`, including `adopt` for a
  reinstalled client's new UUID, now applies to an on-device save through the
  exported copy. The route is served only by a loopback-bound listener, so a
  LAN-bound server does not publish a downloadable, replaceable save to the
  network; on the device itself, any app can reach it while the game runs.

- **A toolchain doctor removes the `PATH` and `JAVA_HOME` step.**
  `python3 -m liminal_gate.doctor` reports which build tools this machine has;
  `--install-missing` fetches a Temurin JDK, the Android SDK packages through
  Google's own `sdkmanager`, pinned Android NDK r27d for its AArch64-capable
  `llvm-objdump`, Il2CppDumper v6.7.46, and — only where the managed dumper build
  needs one — a private .NET runtime. Direct archives are verified against
  published checksums, SDK/NDK packages use Google's repository verification,
  and everything — including the on-device builder's pinned Gradle distribution
  — lands under ignored `user-data/`. Locations
  are recorded in `user-data/toolchain.json` and replayed into the environment
  by `tester_setup` and `on_device_setup`, so no shell variable has to be
  exported in any terminal. A variable the operator set themselves still wins.
  The Android SDK licences are never accepted without being asked. Android
  Studio and emulator images remain the operator's choice; a system-wide LLVM
  installation no longer is.

- A source-only private on-device build path packages the tester's reviewed
  client, complete local resources, dual-ABI Python compatibility server, and
  readiness-gated launcher into one locally signed APK. Readiness identity is
  bound to the patched client, packaged content, and embedded host sources; the
  installer starts the exact replacement activity instead of relying on a
  one-event `monkey` command. Generated packages,
  resources, keys, state, and Android build products remain private/ignored;
  full physical-client and ARMv7 acceptance are still pending.

### Fixed

- **Guided setup could not unpack Google's command line tools on Windows**
  (issue 38). `liminal_gate.doctor --install-missing` downloaded the archive,
  verified it, and then failed with `could not unpack
  commandlinetools-win-...zip: [Errno 2] No such file or directory` naming a
  file it was in the middle of creating. The archive names both a directory and
  the jar inside it `listenablefuture-9999.0-empty-to-avoid-conflict-with-guava`,
  which spends 165 characters before the destination contributes any; unpacking
  beneath a checkout in `Documents\GitHub` crossed Windows' 260-character path
  limit, and Win32 reports that as a missing file. Extraction, and the moves and
  deletions that follow it, now address the filesystem through the `\\?\` prefix
  that lifts the limit, and the staging directory has been shortened by twelve
  characters so the unprefixed path has room to spare as well. Archive members
  are still checked against the plain destination before anything is written, so
  nothing an archive may write has widened. Reported by @Cryo6325.

- **Hunting and Daily Quest clears no longer reject the original client's
  rewards just because a reconstructed ceiling is incomplete.** The client
  executes these battles and reports their Coins, EXP, items, recruits, and
  Companions at clear. The server now trusts that report by default after
  checking the exact active stage, wallet arithmetic, item projection,
  ticket-spend reconciliation, Companion-box integrity, and durable one-time
  settlement. `--outcome-strict` restores per-stage catalog maxima as an audit
  mode. This directly accepts the Pixel 7 Pro Crystal Road result that reported
  280 Coins and 5,400/5,625 EXP against the old zero placeholders. Companion
  IDs still need catalog level data because the server must author a row the
  clear form does not contain.

- **A game over in a Daily Quest no longer ends in a Network Error.** The
  client offers Continue when a Daily Quest is lost and posts `/gd/continue`
  for it, but the server accepted Continue only in the generic-story phase, so
  a Hunting battle — which every Daily Quest is — answered
  `continue_unavailable` at 409 and the client showed a transport failure with
  no way past it. Continue now applies the same coin policy to a Hunting
  battle. Chapter 1100 stays excluded, as its own notice requires: it runs as a
  world-map special. A Continue that genuinely cannot be offered is now
  soft-refused on `cmdError` like an out-of-rotation Daily Quest entry, so the
  client shows its own message rather than a transport error.

- **An abandoned battle no longer strands the account.** Nothing the client
  sends on the way out of a lost battle released the open stage, and a Daily
  Quest could not be re-entered to release it either — the day is spent at
  accepted start, so the client greys out the one stage that would have. Every
  other quest then answered 409 until the UTC day rolled over. A start for a
  different stage now counts as the player having left, since the client runs
  one battle at a time. Explicit local policy, alongside the existing release
  on a roster or party save. The spent day still stands.

- **Guided setup starts the server against the resource root it built the
  manifest from.** `--resource-root` accepts any of the enclosing directories
  and setup reports the `data_u2017/android` directory it detected inside one,
  but the launch that followed was handed the operator's own argument. Every
  mapped file was then looked up a level or more too high, so a setup that had
  just built and installed the APK ended on `resource file is unavailable`
  instead of serving. The detected directory is now resolved once and used for
  both. `server_setup` and `on_device_setup` were already correct.

- **The setup rehearsal finds the tools the doctor installed.** Every run gets
  an empty data directory, and guided setup replays recorded tool locations
  from the data directory it is given, so a machine provisioned by
  `liminal_gate.doctor --install-missing` failed the rehearsal's own
  prerequisite check on an Il2CppDumper it had. The record is now copied into
  the run; `--toolchain` names it when the doctor was run with a different
  `--data-dir`.

- **A Yamamoto Puzzle Quest clear no longer wedges the account** (issue 29).
  6011-1 and 6011-2 are the only two Daily Quests whose own `BattleData` section
  declares a `dropBuddies` manifest, and their two packed codes decode to
  Companion 267 and Companion 140 at one copy each. The bundled policy declared
  no Companion for any Daily Quest, so the client rolled the drop its own data
  allows, reported it, and had the whole clear refused with `409
  invalid_local_hunting_result` — which never releases the active battle, so
  every unrelated stage was refused afterwards too, across restarts. Both
  Companions now settle, at level 1 and at most one per clear; the other twelve
  quests still refuse a reported Companion outright. To recover an already
  wedged save, replay the same Puzzle Quest and finish it: re-entering a stage
  that is already active does not charge or consume the day again.

- **Three more Daily Quest ceilings that could refuse an honest clear.** All
  fourteen stages carried a zero EXP ceiling, which refuses the ordinary battle
  EXP a Daily Quest pays and which Metal Runner Rampage pays *only*; both Puzzle
  Quests bounded just their first reward tier, not the Tears, Particles and Ores
  the later tiers pay, and allowed roughly a third of the item total their waves
  can hold; and Rarity Rumble's Ores and Tearjerker Time's Tears and attribute
  rings were not declared at all. Each would have produced the same wedge on the
  stage that hit it. A bound in a client-settled family is only ever safely too
  generous, never too tight, and this family's bounds now say so.

- **A refused settlement now records which channel it refused.** The diagnostic
  logged chapter, section, coins and EXP, so eleven logged refusals of the same
  clear could not say whether an item, a Companion, a recruit or a Summon was at
  fault. It now also records how many of each a result claimed — counts only,
  never an identity or a string from the body.

- **The Hunting Zone selector flashed around Attack of the Coin Creeps.** The
  rows drew correctly and then the whole list strobed behind a loading circle,
  while Metal Zone and Strikes Back stayed perfectly stable. No request failed,
  because nothing was being requested.

  The client checks a selector row twice under two different rules.
  `UISpecialSelect.IsQuestOpen` excuses Chapters 1000--1099 from needing an
  `sp_ch_<chapter>-<section>` flag, and that is what builds the list — so the
  rows appeared. But the per-frame recheck in `UISpecialSelect.UpdateItems`
  calls `CheckQuestFlag` directly with no such exemption, drops every row that
  fails it, and then restarts the list-refresh coroutine, which rebuilds the
  rows so the next frame can drop them again.

  The server had been withholding flags for exactly Chapters 1000--1099,
  trusting the first rule. That covered all four tier-1 Hunting families and
  nothing else, which is precisely why the other selectors were unaffected.
  Every advertised row now carries its own exact section flag. (issue 20)

## 1.0.3 — 2026-08-01

### Added

- **Chapter 1100 now settles a Companion.** Each section's own recovered
  `dropBuddies` manifest admits at most one reported Companion per clear, minted
  at level 1, alongside the bounded experience. The community record's
  per-battle candidate lists match the manifests exactly; its roll weights, item
  drops, difficulty schedule, and the battle-4 character recruit remain refused.
- **Dragon Road grants its Steel Dragon recruit.** Re-reading the three
  recovered Road flags channel by channel found the earlier "drops nothing"
  reading too broad: empty `dropBuddies` rules out Companion drops and
  `allowLucky` 0 rules out the Luck chest, but `doNotDropExchangeItem` governs
  exchange items by its own name, and none of the three addresses
  battle-recruited monsters. Recruits are now bounded per stage through a
  declared `monster_recruit_maxima` rather than refused everywhere.
- The Trading Post rotation is anchored to a dated real-world Friday rather than
  to the epoch, and further external-reference findings are applied as labeled
  bounded policy.

### Fixed

- The setup rehearsal handled `--reuse-il2cpp` and resource roots given above
  `data_u2017/android`, both of which failed an otherwise successful run.

- **A changed IP address emptied the entire world.** Tower, Eidolon, Strikes
  Back, Archive, Metal Zone, and Hunting would all vanish from the client's
  menus at once, leaving a server that appeared to support none of them.

  The client fetches `get_server_status` *before* it logs in, and that response
  carries every stage list. Resolving which account is asking fell back to "the
  only account on this save" — but only while no client host had ever been
  bound. After the first login bound one, a device arriving on a new address
  resolved nothing, and the lists came back empty. The login immediately
  afterwards re-bound the address, so the save was never wrong and gameplay kept
  working; the menus for that session were simply built from nothing. A router
  lease renewal was enough to trigger it.

  The fallback now depends only on the save holding exactly one account, which
  is the condition that was doing the real work: with one account there is no
  second player to expose, these lists say only which stages exist, and reaching
  an account still requires its UUID. With two or more accounts an unrelated
  address resolves nothing, exactly as before.

  Relaunching the client was always enough to recover, because by then the login
  had bound the new address — which is also why this could look intermittent.

## 1.0.2 — 2026-08-01

### Changed

- **The verified original-client boundary is now Chapter 9**, played
  continuously on physical hardware with no client-visible failure. Chapter 2-1
  remains the deepest point backed by preserved request traces; the two answer
  different questions — whether the wire shapes are exact, and whether the game
  is actually finishable — so both are recorded rather than one replacing the
  other.

### Fixed

- **A Chapter-1100 clear could add characters to the roster.** Paying that
  chapter's experience in 1.0.1 meant accepting a changed roster, because levels
  live in it — but the check that replaced was requiring the roster back
  *unchanged*, so the loosening also let a submitted roster name someone the
  account never held. That is exactly the grant the same clear's Companion check
  refuses, arriving through another door. Levels may now advance; the set of
  characters may not.
- The inbox read no longer touches the account when a message grants neither a
  character nor a Companion, so an ordinary coin present cannot create a roster
  or Companion box that was not already there.
- `setup_rehearsal --keep` now prunes only directories it named itself
  (`YYYYmmdd-HHMMSS`). Recursive deletion was applied to whatever `--run-root`
  contained, and that argument is an ordinary path an operator can mistype.

## 1.0.1 — 2026-08-01

### Fixed

- **Dragon Road, Machine Road, and the Chapter-1100 routes rejected the battles
  you won.** All three had a zero experience ceiling, so a clear reporting any
  EXP — which every won battle does — returned `409` and the stamina was
  already spent. 1.0.0 documented this as "these areas award nothing"; that was
  wrong twice over. They do not award nothing, and what they were doing was
  worse than awarding nothing.

  Reading the sections out of the APK settled it. Each declares the absence of
  the *other* rewards itself: empty `dropBuddies`, `allowLucky` 0, and on the
  Roads `doNotDropExchangeItem` 1. So Coins, items, and Companions are still
  refused, now on the game's own authority rather than for want of evidence.
  Experience was never one of those channels — and the Roads are species-locked
  training zones (`species` 128 Dragon and 256 Machine at `assumedLevel` 35),
  where gaining it is the entire purpose of entering.

  Both now pay experience, bounded by a ceiling derived from the same selector's
  own tiers: the Roads' assumed level 35 sits between Metal Zone 3 and 4, and
  the higher neighbour is taken; a single Chapter-1100 battle is bounded by
  Metal Zone 7's five-battle allowance. The bounds err high on purpose. They
  exist to stop a tampered client, and a bound that is too tight refuses honest
  clears — which is the failure being fixed.

## 1.0.0 — 2026-08-01

The first release. What 1.0 claims is narrow and deliberate:

> Every single-player system the retired client had is present, playable, and
> restart-safe, with reward settlement explicitly labeled local preservation
> policy.

It does **not** claim historical fidelity. Where the retired service computed a
value and the client only rendered it, this server either labels its own choice
as local policy or refuses rather than inventing one. See
[PARITY_ROADMAP.md](PARITY_ROADMAP.md) for the three-way split between what is
implemented, what is permanently unrecoverable, and what is still open.

### Playable

Bootstrap, tutorial, and ordinary story Chapters 2--42 · Fellowship and Truth
Pacts including the Fate variant and the permanent Item 81 ticket draw ·
Companion draw, sale, strengthen, evolution, and the full equipment lifecycle
with party selection · job unlock, Rebirth, status-up items · Battle Summon
skill progression across all 44 recovered tiers · Trading Post with its
eight-week, 126-offer rotation · Hunting, Metal Zone, Money Money Time, Crystal
Road, and the two Roads · all fourteen Daily Quests · Archive Special Quests,
the Tower solo adapter, solo Eidolon quests, and eight Strikes Back families ·
Chapter-1100 world-map routes · inbox lifecycle with the retail chapter-ticket
presents · hash-validated serving of your own resource tree.

### Added in this release

- **Setup rehearsal** (`liminal_gate.setup_rehearsal`) — one command reruns the
  entire real setup pipeline on a clean copy of the source in an isolated
  environment, drives onboarding over real HTTP across a server restart, and
  compares every input hash, artifact hash, catalog count, and transport result
  against a baseline. The unit suite fakes the IL2CPP dump, the master-data
  import, the catalog derivations, and the signing; this covers what it cannot.
  See [docs/setup-rehearsal.md](docs/setup-rehearsal.md).
- **Daily Quests** — all fourteen recovered stages, resolved by matching every
  APK banner texture against the community record's own banner images, gated
  once per UTC day, and now enabled by both launchers.
- **Character and Companion inbox rewards** — the client's `chr` and `buddy`
  message channels are settled durably. A read that cannot deliver every reward
  it displays refuses rather than settling the affordable half. `summon` and
  `title` are refused at catalog load: no owner is modeled for either, and a
  displayed-but-undelivered reward is worse than an honest refusal.

### Fixed

- **The server could not start from the command line.** `--daily-quests` was
  defined by the parser and read by `main`, but never carried by
  `ServerConfig`, so every launch — including the one guided setup performs —
  died with `AttributeError` before serving a request. A structural test now
  requires every launch option `main` reads to be a field the configuration
  carries.
- **A feature could reach no operator.** Guided setup and the dedicated server
  built their flag lists independently, so Daily Quests shipped complete and
  unreachable. A test now requires the two launchers to enable the same
  gameplay policies in both directions.

### Documented

- Dragon Road, Machine Road, and the Chapter-1100 routes cost stamina and award
  nothing, because the operator's own game data carries no reward table for
  them. This is now stated plainly for players in
  [docs/scope-and-status.md](docs/scope-and-status.md) rather than left to look
  like a fault.
- The parity roadmap now separates work still to do from evidence that no
  longer exists — Luck Treasure Chest contents, Pact odds, event banner rates,
  and the Trading Post's rotation phase are closed questions, not backlog.
