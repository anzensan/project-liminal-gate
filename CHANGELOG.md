# Changelog

## Unreleased

### Fixed

- **A Luck Treasure Chest could show a Companion and give you nothing.** Chests
  award four kinds of reward. Coins and items were settled from the start; the
  other two were computed and then dropped on the floor. `chest_companions()`
  existed, was unit-tested, and had no caller anywhere in the server, while the
  chest pools carried thirty-nine Companion rewards across twenty-seven stage
  and tier slots. A clear returned 200, the items and Coins landed, and the
  Companion was simply gone. Nothing in the suite looked at an authored chest
  end to end, which is how it shipped.

  The asymmetry is structural rather than a slip. The generic story clear body
  is an exact field tuple — `chrdata`, `itemList`, `summonList` and no Companion
  box — so there is no field for the client to report a chest Companion back
  through, and no amount of reconciliation could have caught it. Coins and items
  work because the client folds those into the balances it submits. The server
  authored the chest at battle start and persists it in `active_luck_result`, so
  it now grants what it authored, inside the clear's own transaction: an exact
  replay returns the cached payload and cannot grant twice, and the grant
  survives a restart.

### Added

- **Sixty-five character rewards recovered into the Luck chest pools.** The
  scrape behind those pools dropped ninety-nine rewards it could not resolve,
  sixty-eight of them character icons, and character rewards were consequently
  absent from every pool even though the record shows chests award them. The
  icons kept their names, so sixty-five resolve by exact match against the
  operator's own `ChrDatabase` and are now emitted in the client's `M` wire
  form. Nineteen of the thirty pooled stages still lose at least one reward,
  down from twenty-eight.

  Three do not resolve, and it is a real ambiguity rather than a lookup failure:
  the wiki writes `Mage (Ice)` and `Lizardfolk Mage (Fire)` while the master
  data holds four characters named `Mage` and four named `Lizardfolk Mage`,
  separated by an element the catalog does not name. Choosing one would be a
  guess, so they stay unresolved and are named in the module.

  Recorded and deliberately not acted on: the four rewards the scrape filed as
  unresolvable *item* names are not items. Three name characters the master data
  holds, and the fourth, `Metal Minion`, is Companion 128 — already used by
  these pools elsewhere. All four look like a wiki editor reaching for
  `{{Item icon}}` where the reward was not an item. Correcting a source is a
  different decision from reading it, and is left to be made deliberately.

  Adding rewards to a tier changes which one a given seed selects from that
  tier. Nothing durable depends on a seed-to-reward mapping, and the per-tier
  draw already isolates neighbouring tiers, so this affects only which reward a
  future chest rolls.


- **A Companion delivered by an inbox present was owned but invisible.** A
  reporter opened the Companions screen after a present granted one, saw
  nothing, restarted the app, still saw nothing, then drew a Companion and
  immediately held two. Nothing was lost at any point — the present's Companion
  had been granted and persisted correctly the whole time.

  `buddyInfo` carries two halves: `list`, the Companions owned, and `record`,
  the book with one entry per distinct Companion. `record` is a projection of
  `list`, not a second store, and every grant path rebuilds both together
  through `_companion_info` — a battle drop, a draw, a Trading Post exchange, a
  sale, a strengthen, an evolution. The inbox present was the one exception: it
  appended to `list` and left `record` untouched. The box the client renders
  therefore never learned about the Companion, and a restart could not help,
  because the save itself was inconsistent rather than the client's copy being
  stale. Any later mutation rebuilt the box wholesale and the missing Companion
  reappeared alongside whatever had just been added, which is the "pulled once,
  now I have two" the report describes.

  The present now rebuilds both halves like everything else, and a save that
  already drifted is repaired when it loads — the owned list is the truth, so
  the book is rebuilt from it and nothing is granted or taken. That is the same
  treatment the stale wallet projection got in 1.0.4, and for the same reason:
  a projection nothing recomputes is a per-site chore that some site will
  eventually forget.

  A test already covered this present and asserted only `list`, which is what
  let it ship; the replacement asserts the invariant, that `record` is always
  derivable from `list`.

  One question this deliberately does not answer: whether the original client's
  book was monotonic — whether selling your last copy of a Companion should
  forget it. Every path here derives the book from what is currently owned, so
  it does forget, and that behaviour is unchanged rather than newly decided.

## 1.0.5 — 2026-08-06

### Added

- **Orbling Cavern and Cryptid Forest are reachable.** Both draw a permanent map
  point on World 1 and neither had ever appeared, which several testers asked
  about. They were not partially implemented or subtly broken: they were absent,
  and the cause was a single missing thing on the server side.

  The client builds each point only if `EventManager.IsEnabledAny` finds an
  enabled event flag under a prefix -- `sp_ch_700` for Orbling Cavern and
  `sp_ch_701` for Cryptid Forest -- in the `eventFlags` object login and status
  send. This server had never sent a key under either, so neither point was
  constructed, and a map point that is never constructed reports nothing. The
  chapter identities are Confirmed from `ChapterInterface::.cctor`: 7000--7009
  is Orbling Cavern and 7010--7019 is Cryptid Forest, with sections only in 7000
  and 7010, so the two areas are four stages between them.

  Unusually, that flag is all the server can contribute. `UISpecialSelect`
  modes 1 and 2 read a hardcoded list apiece -- `["7000-1", "7000-2"]` and
  `["7010-1", "7010-2"]`, set in the client's own static constructor -- and
  never consult a served list the way the Archive selector consults
  `specialQuestList`. All four stages are therefore unadvertised, like the Daily
  Quests and the two secondary world maps, and the server's job is to honour a
  start rather than to publish a menu.

  Both areas cost one stamina and no Coins. Each Orbling Cavern card awards the
  one Companion its own `dropBuddies` manifest declares -- Bahl OIII on 7000-1
  and Grace OIII on 7000-2 -- and the reporter states the drop is guaranteed
  while that Companion is unowned and does not occur once it is held, so a later
  clear reporting nothing is ordinary rather than a fault. Each Cryptid Forest
  card farms one of Dracorin's two job-material sets: the client's Kirin
  constructors hand the engine items 150 and 151 on 7010-1 and 152 and 153 on
  7010-2, and the operator's own ChrDatabase independently prices Dracorin's
  first job at exactly 150 and 151 and its second at 152 and 153. Cryptid Forest
  also carries the Lucky Runner, which already had a Luck policy written for
  chapter 7010 and no stage to attach it to; a one-stamina entry still pays it,
  because the eight-stamina battle-end rule does not govern that source.

  Both open on the client's own gate: Cryptid Forest after Chapter 5 and Orbling
  Cavern after Chapter 6, read out of the `openChapter` each map point is built
  with. The server sends each area's flags no earlier, so a drawn point never
  leads to a start this server would refuse. Enabled by every launcher as part
  of the standard policy set, or on its own with `--cavern-forest`.

  One inference is recorded as withdrawn rather than quietly dropped. Orbling
  Cavern's sections declare `battleCnt` 0, which this project has read elsewhere
  as a stage with no battle program, and reading it that way here would have
  written the area off as an empty placeholder. Twenty-six chapters declare
  all-zero `battleCnt`, including two implemented Archive events and both
  Yamamoto Puzzle Quests and Lucky Orbling, all confirmed playable on hardware.
  See `docs/findings.md` for what actually distinguishes a placeholder.

  Physical-client confirmation of both selectors, and of the Companion award,
  remains pending.

### Fixed

- **`--disable-google-services` now stops the bind that actually crashes.** A
  Galaxy S26 on Android 16 crashed on launch with the flag correctly applied —
  `NoSuchMethodError` on `ServiceConnection.onServiceConnected(ComponentName,
  IBinder, IBinderSession)`, the same failure the flag exists to prevent.

  The flag rewrote 18 bind actions in the client's `classes.dex`. It turns out
  the crashing bind is not one of them and never was: Unity's own `libunity.so`
  binds Play Services from native code to read the advertising ID, using its own
  copy of `com.google.android.gms.ads.identifier.service.START` that no edit to
  the dex reaches. The flag now rewrites that copy too, in both ABIs.

  Only Unity's connection was ever vulnerable. It is built as a
  `java.lang.reflect.Proxy`, which hands an interface's `default` methods to its
  handler rather than inheriting them, so Android 16's new three-argument
  overload arrives at a 2017 bridge that has never heard of it. Every ordinary
  Java class inherits that overload correctly, and all twelve classes in the
  client dex that implement `ServiceConnection` are ordinary classes.

  That last point retracts the earlier diagnosis. A Galaxy S24 FE log showed
  `UnityIAP: Billing service connected.` immediately before the fatal and Play
  Billing was recorded as the crashing bind; billing's connection is
  `com.unity.purchasing.googleplay.BillingServiceManager$1`, an ordinary class,
  so it could not have thrown this and the line ordering was coincidence. The
  billing and Play Services actions stay neutralized — they cost nothing — but
  they are no longer described as the fault.

  The cost of the new edit is that Unity cannot read the advertising ID, which
  is analytics for a service retired years ago; Unity already handles the bind
  failing and has its own message for it. The self-hosted route was never
  affected, because its host guard catches the callback whatever caused the bind.

  Also corrected: how to tell whether a build carries the flag. On the
  separate-server route `/healthz` cannot answer it, and the generated plan must
  not be used either — it is rewritten by every setup run, so it describes the
  last build rather than the installed one. `docs/troubleshooting.md` now reads
  the installed APK instead. Physical confirmation that the extended flag clears
  the crash is pending.

## 1.0.4 — 2026-08-06

### Fixed

- **A Pact draw paid with Energy left the save failing its own validator.** The
  nested `valuables` block is a projection the client reads; the flat wallet
  fields beside it are what this server spends and grants. Keeping the two in
  step was a per-site chore, and most sites did not do it -- a Pact draw, an
  inbox present's Coins, a Rebirth, a stamina refill and a Trading Post
  exchange all moved the flat value and left the projection behind. A tester's
  exported save showed it after a ten-draw: `valuables.freeEnergy` read 72
  against `freeEnergy` 22, the difference being the fifty the draw had spent,
  and `account_state validate` refused the file.
  The projection is now rebuilt from the flat wallet on every persist, so it is
  an invariant of the save rather than something each mutation has to remember;
  every mutation already ends in a persist. Saves that drifted before this are
  repaired when they load, taking the flat value as the truth -- the
  disagreement is only ever the projection being stale, never the player having
  been charged twice.

- **An inbox present now pays out, and a stage started afterwards no longer
  hangs.** Opening a present displayed its rewards but credited nothing, and
  the next chapter stage froze. One cause: the read reply was shaped wrong at
  the top, so the client's callback died partway and left its copy of the
  account mid-update.

  The read-messages callback opens with `if (json.Contains("result"))` and then
  *rebinds its receiver* to `json["result"]`. Every field it goes on to read —
  the six wallet values, `buddyInfo`, `chrdata`, `itemList`, `summonList`,
  `achivementFlags` and `readlist` — is looked up inside that object, not
  beside it. This server answered `result: true` with those fields alongside
  it, so the client called `Contains` on a boolean and threw
  `InvalidOperationException: Instance of JsonData is not a dictionary`.

  Before that could even be reached, `AppServerUtil.callAPI` indexes `success`,
  `digest` and `lastupdate` off every response, unguarded, before dispatching
  to any endpoint callback. The mail routes answered `result` and nothing else,
  so the wrapper raised `KeyNotFoundException` first. Every other mutation
  already carried those fields, which is why only mail was affected.

  Both are fixed: the read reply nests its payload under `result` and both mail
  replies carry the wrapper fields. Verified on an emulator end to end — a
  present carrying 500 Coins, 3 Energy and two Metal Tickets moves the wallet
  from 1000 to 1500 on opening, and Chapter 3-1 then loads its squad screen and
  starts its battle with `start_quest` answering 200.

  The delete reply is canonicalized for the same reason the read reply already
  was: its digest is computed over the serialized text, so an unsorted payload
  signs differently once replayed from the save after a restart. The delete
  callback is not nested this way — it reads `deletelist` straight off the root.

- **A won Strikes Back battle now settles instead of stranding the client on
  its reward screen.** Clearing a Counter Descent stage showed the rewards, then
  looped Network Errors on the item screen and never added them
  ([#46](https://github.com/anzensan/project-liminal-gate/issues/46), reported
  against Spinetrich Kino Chapter 8000-1 on a Pixel 7 Pro).

  The family settled under a zero-base policy that required a clear to grant
  *nothing*: zero Coins, zero experience, no items, no monsters, no Lucky enemy,
  and the roster and inventory returned unchanged. That was adopted while the
  family's clear callback was unobserved, and a real won battle contradicts
  every clause of it. Each clear was refused with `invalid_local_event_result`,
  which reaches the client as an unsigned 409 — a transport failure, not an
  endpoint refusal — so it showed the network dialog and retried. The refusal
  also leaves the battle open, so the retry was refused identically, and the
  reward screen became a dead end. All fourteen packaged families were affected,
  not only the one reported.

  A Counter Descent clear now settles the way a Hunting clear does, which is the
  policy this server already applies wherever the surviving client is the only
  remaining account of what a battle paid: the report is trusted, and the
  inventory accompanying it must be exactly the durable counts plus the drops it
  declares, capped at the client's own stack ceiling, so the item array cannot
  become a grant channel beside the drops. Experience, Coins, Skill Boost,
  recruited monsters, and Lucky enemies are kept through the same trusted merge
  every other event and story clear uses, and a Companion drop stays bounded by
  the stage's own recovered `dropBuddies` manifest. A reported Summon is still
  refused: no recovered source states an event stage's Summon outcome.

  Chapter 1100 keeps the bounded shape this replaces — it is a real level-90
  battle whose experience a won fight must keep, and nothing else about its
  rewards was recovered.

- **The troubleshooting guide now points at the right request log.** It named
  `user-data/events.jsonl` unconditionally, which does not exist on the
  on-device route: that server writes to its own app-private
  `files/events.jsonl`. A tester following the old text found nothing and could
  reasonably read that as the server having refused nothing. Both locations are
  now documented, along with how to capture a logcat that actually contains the
  failure rather than ending before it.

### Added

- **An inbox present now shows the reward it carries.** Opening a present drew
  its text over an empty space: no Coins, no Energy, no items, no character, no
  Companion, and the plain "Message from the admin" heading rather than the
  gift one. The rewards were granted correctly the whole time; the client was
  never told about them.

  The reviewed client reads every reward out of a `gifts` entry and looks at
  nothing else. It never reads a top-level `coins`, `energy`, `chr`, `item`,
  `buddy`, `summon` or `title` — which is exactly what this server had been
  sending — so `Message.coins` and its siblings stayed zero, `get_hasGift`
  answered false, and the mail screen drew the no-gift presentation over a
  present that really did carry something.

  The shape was recovered by resolving the constructor's own key literals
  through the GOT relocations that supply them, which reads the keys out of the
  binary instead of guessing at them: `json["gifts"]` is indexed by integer,
  and inside an entry `coins`, `energy`, `chr`, `summon` and `title` are
  scalars, `item` is another integer-indexed array of `{id, num}` pairs, and
  `buddy` is one such pair. `title` lands on the client's `multiplayTitle`.
  `messages` is an object read by the keys `default`, `ja` and `en`, and `date`
  stays a JSON real even though the field is a `long`, because the constructor
  reads it through LitJson's `(double)` conversion.

  Verified against the reviewed client on an emulator across every reward
  channel: a present carrying 500 Coins, 3 Energy and two Metal Tickets now
  opens as "Gift from the admin" and lists all three, and one carrying a
  character and a Companion lists Joker Λ and Excalibur x 1 by name. Standard,
  because the shape it replaces cannot display a reward at all.

  Two earlier readings of the same class were wrong and are recorded here
  because of how they failed rather than that they failed. `date` as an integer
  and `messages` as a positional array each threw out of `Message..ctor` —
  `InvalidCastException: Instance of JsonData doesn't hold a double`, then
  `InvalidOperationException: Instance of JsonData is not a dictionary` — and
  the exception killed the login callback, leaving the client on `Connecting...`
  indefinitely with no error dialog. One malformed field in one message hangs
  the client on a loading screen; that is what a stall of this kind looks like
  from the outside, and it is worth knowing when a tester reports a freeze.

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

- **The combined APK survives the Android 16 service-connection crash.**
  `HostedActivity` installs a main-thread guard before Unity starts. It drops
  exactly one error — `NoSuchMethodError` naming
  `ServiceConnection.onServiceConnected` — logs every occurrence under the
  `LiminalGate` tag, stops after 64 of them, and lets every other throwable end
  the process as it would have. Always on: it does nothing until an exception
  that would otherwise kill the app.
  This exists because the string patch below cannot finish the job. A device log
  showed the fatal bind arriving as `com.google.android.gms.ads.service.CACHE`
  *after* that action had been rewritten in the client, alongside `appset`,
  `safebrowsing`, `safetynet`, and `dynamiclinks` binds whose strings are absent
  from the client entirely: Play Services loads code into the process through
  Dynamite and binds with its own constants, which no edit to the APK can reach.
  Dropping the callback is equivalent to the bind never completing, which is the
  state the same reporter confirmed loads the game. Verified on an emulator by
  throwing the exact error on the main thread: swallowed once, UI still pumping
  three seconds later, no fatal. The separate-server route has no host DEX and
  is not covered.

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

### Changed

- **`release_audit` no longer sweeps ignored, untracked material.** The audit
  reports what a clone of a release carries, and Git omits ignored files from
  every clone; sweeping them anyway buried the boundary findings the tool
  exists for under thousands of lines about a working checkout's own local
  inputs. On this repository it drops from 6071 findings to whatever is
  genuinely wrong. The skip list comes from `git ls-files --others --ignored
  --exclude-standard --directory`, whose `--others` is load-bearing: it lists
  only untracked paths, and Git does not apply ignore rules to a tracked file,
  so a committed `.apk` can never be skipped however `.gitignore` reads. The
  history scan is unchanged, a root that is not a repository is still swept in
  full, and `--include-ignored` restores the whole disk sweep for a release
  handed over as a directory rather than as a clone. `release_preflight` is
  deliberately untouched and remains the unconditional filesystem gate.

- **Only story and event clears pay preservation Energy.** Hunting, Metal Zone,
  the special quest, the Daily Quests, and the Chapter 1100 Roads paid the same
  per-stage award as a story stage, on the first clear and on every clear after
  it. Those areas repeat without bound, so the wallet's local income was really
  priced in Metal Zone runs: a Pact, a job unlock, or a stamina refill cost
  whatever a repeatable stage could be replayed enough times to cover. They now
  mint nothing and record no first-clear key, and the archive's only stage
  income is the story an account is actually advancing — unchanged rates, and
  the one-time chapter-completion award is untouched. The refusal lives in
  `archive_economy.ENERGY_BEARING_KINDS`, so a stage family added later has to
  state which side of the line it is on.

- **The stamina meter no longer gates quest entry, on any launcher.** Entry
  charges nothing, the bar the client draws stays full, and the refill route
  answers the client's own `NoNeedToRefill` instead of selling an Energy for a
  meter nothing spends. A save carrying a fill origin from a charged run is
  returned to full on the next `GET /gd/userdata` rather than reading back as a
  half-filled bar nothing will ever finish debiting.
  The recovered model is intact and unchanged: `--enable-stamina` runs
  `GameManager.CalcStamina` and `UserData.GetMaxStamina` exactly as before, and
  `scripts/install_systemd_service.sh PORT --enable-stamina` writes the flag
  into the systemd unit for a dedicated host. A refilling meter paces a live
  service; there is no longer a live service to pace. The client always draws
  the bar — it is `ServerConstants` and local `UserData`, not server-side UI —
  so off means a meter that is always full, not one that is hidden.
  The four entry routes now ask one `entry_stamina_origin` helper rather than
  repeating the same pair of `userdata` reads around `spend_stamina`.

- **One policy source for all three launchers.** Guided setup, the dedicated
  server, and the packaged Android host previously each carried their own copy
  of the gameplay-policy set (sixteen constant booleans threaded through the
  guided command builder, a literal flag tuple, and an inline JSON document),
  held together only by a drift-guard test. All three now derive from
  `server_config.STANDARD_POLICY_FLAGS`, so a recovered feature cannot ship
  enabled on one path and unreachable on another. Per-policy selection remains
  a `bootstrap_server` command-line capability, unchanged. The long-retired
  interactive-setup compatibility argument (`choose_local_server_options`'s
  `ask`) is gone with it.

- **A maintenance pass consolidated long-copied scaffolding** without behavior
  change: one shared `sha256_file`, one atomic JSON writer, one home for the
  reviewed-build identity and client inventory-shape constants, the profile /
  wire-encoding / request-parser layers lifted out of `bootstrap_server`, and
  shared test scaffolding replacing per-file copies across fifty test files.
  Command lines, generated-file bytes, and wire behavior are unchanged. The
  pass also fixed a latent builtin-`ImportError` shadowing in `tester_setup`,
  gave `native_encounter_importer` the `--force` overwrite guard its scenario
  sibling had, made the story-outcome generator refuse invalid baseline IDs
  before writing, and made an unmapped mutation result answer HTTP 500
  instead of crashing the handler thread.

### Fixed

- **Cryptid Forest paid a Lucky Orbling's Luck, and its enemy is a Lucky
  Runner.** The `allowLucky` source granted all five flagged chapters +0.3 at a
  50% chance. Chapter 7010 is `EidolonForestChapter` inside the client, which
  is how this repository recorded it, but its player-facing name is Cryptid
  Forest — and under that name the community record documents its enemies
  outright: one Lucky Runner always spawns, a second spawns with a 30% chance,
  and a pincer from any direction grants 0.1 to the whole party. The stage was
  therefore granting three times the documented Luck, from the wrong enemy, on
  a coin flip where a guarantee was stated. 7010 now takes the Runner's
  documented population and gain; the other four keep the Orbling policy and
  their draw sequence is unchanged, because the chapter is not seed material.
  The record's conditional 50% second spawn (a party carrying Dracorin Λ's
  *Cryptid Ruler*) and its app-restart suppression are recorded and not
  implemented, since this server models neither party skills nor client
  lifecycle. `roll_luck_up_table` now takes the stage's `lucky_chapter` instead
  of an `allow_lucky` flag each caller computed for itself — that duplication
  is what let the flag and the species disagree. See `docs/findings.md`,
  2026-08-05.

- **The Tavern kept playing the menu theme, and the live-recorded tracks were
  unreachable** (issue 44). Three of the flags the client reads to decide which
  track belongs to which screen were never sent, so every branch that would
  have switched music was skipped and whatever the previous scene started
  carried on. Reported as "Evening at the Tavern" never starting while the
  battle, boss, and victory transitions all worked; those are client-side scene
  changes that consult no flag, which is why only the menu-to-menu case showed
  it.
  `use_sakaba_bgm_for_bar` is the Tavern's own theme and
  `use_another_bgm_for_hunting` the Huntland equivalent. `EnableLiveMusic` cost
  the most: the one client method that names it also names `BGM100` through
  `BGM103`, so the live-recorded tracks are reachable through that flag and
  nothing else. Their bundles are in every tester's resource set and the client
  downloads them at startup, so the server was shipping five tracks to the
  device that nothing could ever play.
  All three now ride every login, ungated. Each selects audio and nothing else
  -- no stage, no item, nothing the save records -- so none is a policy an
  operator needs to choose. `UseLiveMusicAsDefault` and `ReverseTitleMusicOrder`
  remain deliberately unsent: both change a default rather than reach otherwise
  unreachable audio, and the retired service's value for each is unrecovered.

- **Luck could not grow anywhere except the ordinary story.** The preceding
  Luck fix stopped a stale client rolling the stat *back*, and it worked — a
  reporter confirmed a character kept its 10% across Metal Zone runs — but a
  second report that Luck never rose showed the preservation was the only half
  implemented. The server has three battle start/clear pairs and only the
  generic story one ever rolled a `luckUpTable`: Hunting Zones, Metal Zone, the
  Roads, every Daily Quest, and the Chapter 1100 Roads set no
  `active_luck_up` at entry, so their clears had nothing to apply. That silently
  excluded every stage the ≥8 stamina rule already qualified — Metal Zone zones
  2--7 at 8 to 20 stamina, the Roads at 15, Coin Creeps at 10 to 20, and Chapter
  1100 at 25. Both handlers now roll at entry and apply at clear, after the
  roster merge and once per battle, with the entry's table replayed rather than
  re-rolled. `LUCK_GAIN_MIN_STAMINA` is untouched: it is the developer's own
  confirmed rule, it reads the stage's *declared* cost rather than what the
  meter was charged, and so it never depended on `--enable-stamina` either way.
  No Luck Treasure Chest is authored on any of these stages; the community
  record's own no-chest list names the Hunting and Metal zones, and Chapter
  1100's chests stay refused as labeled local policy. `luckResult` accompanies a
  gain only as the six empty slots an ordinary story stage with no documented
  pool already sends.

- **The Lucky Orbling quest granted no Luck, which is the one thing it is for.**
  The recovered `allowLucky` flag is 1 on exactly five chapters — 2006 Lucia,
  3003 Money Money Time, 3004 Crystal Road, 6010 Lucky Orbling, and 7010 Eidolon
  Forest — and `docs/findings.md` reads it as "Lucky-type enemies may spawn
  here", a Luck *source* rather than the chest gate an earlier reading took it
  for. Nothing implemented it: `LUCKY_ORBLING_GAIN_TENTHS` and its pincer chance
  sat in `luck_data` unreferenced by any code path. A reporter saw 1.8 on every
  character during the quest and nothing in the party menu afterwards, which is
  the client rendering its own in-battle pincer and the server never hearing
  about it — the confirmed final client omits the optional `luck` member from a
  clear, so the gain has no way back. The five chapters now carry a server-side
  Lucky-enemy source, delivered through `luckUpTable` because that is the only
  channel the client renders a Luck gain through. It is deliberately *not*
  governed by the stamina gate, and it could not be: Lucky Orbling is free,
  Money Money Time costs five and Crystal Road seven, so folding it into the
  battle-end gain would leave the three stages the record most clearly documents
  as Luck sources unable to grant any. One invented number is added and isolated
  beside the existing one — `LUCKY_ENEMIES_PER_BATTLE`, how many pincer chances
  one battle on a flagged chapter offers. The record fixes the +0.3 gain and the
  50% chance but never states a population, and the spawn lives in client-side
  battle data this server does not read, so the invented claim is held to a
  count rather than a distribution.

- **An inbox present stranded the account it was delivered to.** A message
  carrying a character wrote that character onto the durable roster in the
  shape its own *response* carries — `isNew` and `levelAdded`, a one-element
  `jobLevels`, an empty `jobSlots` — rather than the generic record the save
  otherwise holds. Every settlement check reads the durable roster through
  `_valid_generic_character_record`, which requires the exact eight-key record
  and length-three arrays, so a single present refused every stage clear the
  account attempted from then on. Nothing recovered on its own, across
  restarts included: the roster merge that would have rewritten the row is
  only reached by a clear that was accepted first, so the one repair path was
  behind the refusal it caused. Reported as the client stalling on a character
  pull or on entering a stage after opening mail.
  The same row was written by four grant paths, not one: inbox presents, event
  stage characters, Hunting and Daily Quest grants, and the battle-recruit
  backstop. All four now persist the generic record — the Pact draw already
  drew this distinction, keeping the response shape out of the save — and the
  `isNew`/`levelAdded` a result screen reads are projected onto the response
  instead of stored. What the client receives is otherwise unchanged.
  Saves already carrying the bad row are repaired when the server next loads
  them, keeping the packed level, Skill Boost, and Luck the row accumulated
  while it was unusable. Only a row carrying *both* response-only keys is
  rewritten, which is the exact signature a grant left; the client's own
  free-roam roster write carries `isNew` alone and is left as it was sent.

- **Setup packaged a half-extracted resource tree without saying so.** The
  resource root was accepted on the strength of its nine category directories
  *existing*; nothing checked that any of them held a file. An `Illust/` or
  `Pieces/` that was empty or partly copied therefore passed every check, the
  manifest named only what was there, the build succeeded, and the package
  installed — and the first sign of trouble was the client reaching a screen
  whose artwork the package had never carried, stalling with the music still
  playing, days later and on someone else's device.
  Resolution now refuses a required category that contains no files at all,
  naming every empty one and the root to re-extract into, while the tester is
  still at a prompt that can fix it. Because the tree is the tester's own
  extraction there is no absolute count to check a partial one against, so each
  build also prints its per-category inventory and compares it against the last
  manifest written to the same data directory: a category that has *shrunk*
  since the previous successful build is reported as a warning naming both
  counts. A first build, or an unreadable previous manifest, simply declines to
  compare rather than refusing to build.

- **A Bahl starter was shown recruiting an Archer and given a Warrior.** The
  tutorial's Chapter 1-2 recruit is the generic that completes the Circle of
  Carnage against your starter — an Archer for Bahl, a Warrior for Grace — and
  the client picks that completion itself and animates it. The bundled profile
  named the Warrior outright, captured from a Grace run where the Warrior is
  the right answer, so the signed roster replacement overwrote what a Bahl
  player had just been shown. Every first-Pact outcome now declares its recruit
  beside its starter, and the two commit together when the outcome is selected;
  the grant and every later party projection resolve from that durable pair.
  Grace runs are unchanged. A save with no recruit field keeps the Warrior it
  was already granted, whichever starter it holds, rather than switching to a
  character its client never received.

- **The self-contained build served resources under only one of their two
  names.** Android caches many client bundles under a 32-hex-prefixed filename
  while the client asks for the logical name, so both spellings have to
  resolve. The filesystem manifest the separate server reads has always
  registered both; the packaged manifest the on-device APK carries registered
  only the on-disk spelling. Every prefixed resource therefore answered
  `resource_not_found` on the packaged build and the client reported a network
  error — the inbox is where testers hit it — while the identical content
  loaded correctly from a separate server. Nothing was wrong with the mail
  routes themselves: they are shared by all three launchers and were reached
  and settled normally. Both manifest builders now derive their URL set from
  one shared alias rule, and the packaged manifest points every alias at the
  same stored member rather than packaging the bytes twice. A resource tree
  that collapses two files onto one client URL is refused at assembly time, as
  the filesystem builder already refused it. This changes the packaged
  manifest and so the build id: on-device testers need a rebuilt APK, not a
  restart.

- **The stamina gauge read full over a meter the entry had already spent**
  (issue 31). Quest settlements answered without `refillStartTime`, and to this
  client that is not an omission: zero is its own representation of a meter that
  refilled at the epoch, so a silent settlement and a full bar are the same
  statement. A tester saw the bar return to full on leaving a cleared stage and
  stay full across a relaunch, then watched the next entry refused as
  insufficient against a gauge still showing maximum. The server's arithmetic
  was never wrong: entry debited the meter correctly, the durable origin
  survived restart, `GET /gd/userdata` reported it accurately, and the refusal
  was correct. Only the settlement callbacks were silent. All three now restate
  the post-clear origin — generic story and event, Hunting, and World Map
  Special — which is the entry's own post-spend value everywhere except an
  ordinary chapter boundary, where it is the full meter that boundary already
  grants. The tutorial's Chapter 1 clears are unchanged: those stages charge
  nothing, so a full bar is what their meter actually holds.
  This widens three response shapes beyond what capture confirmed. The
  justification is the same one behind the chapter-boundary refill already
  documented as local policy: the server knows the meter and the client cannot
  derive it, so declining to send it is a choice to let the bar go wrong.

- **`on_device_state` could not find the toolchain `doctor` had installed.**
  `liminal_gate.doctor` and `liminal_gate.on_device_setup` both succeeded on a
  machine where `on_device_state update` failed on a missing AArch64
  disassembler — and earlier, on missing build tools and SDK platform — with no
  flag able to correct it, since that command names only `--adb` and
  `--build-tools`. The doctor records where it put each tool in
  `user-data/toolchain.json`, and every launcher replays that record into its
  own environment before its first resolver runs; this one never did. It was
  the only entry point that missed the step, so the tools it needed were the
  ones deliberately kept off `PATH` — the privately installed pinned NDK
  `llvm-objdump` above all. `main` now replays the record ahead of everything
  else, for `export` and `import` as well as `update`, and a test asserts that
  ordering for all three.
  An operator has since confirmed both `export` and `update` from a Windows
  build host against a physical Pixel 7 Pro on Android 15 carrying real gameplay
  progress; `update` rebuilt and installed in place with the accounts intact.

- **`guided derivations` reported FAIL inside an activated virtual environment
  after an install that had really succeeded.** The same check passed in a plain
  PowerShell window, which is the shape of the report. The Windows launcher
  honours an active environment only when no version is spelled out, so
  `py -3 -m pip install ".[master-import]"` typed at a `(.venv)` prompt installs
  into the system Python; the check then reads `.venv`, which genuinely lacks
  the package. Nothing was wrong with either the install or the check — they
  were looking at different interpreters, and the documentation told the tester
  to use `py -3` for every command after creating the environment.
  Both messages raised by that probe now name the interpreter they actually
  read, quoted for a shell, so the printed remedy can no longer be the command
  that caused the failure. Inside an environment the message also names
  `sys.prefix` and says why a `py -3` install went elsewhere. The Windows
  instructions in `install-tools.md` and `on-device-setup.md` now stop at
  `py -3 -m venv`, which is correct because no environment exists yet, and use
  plain `python -m` from the `(.venv)` prompt onward; `troubleshooting.md`
  carries the symptom under both the setup checks and the PowerShell section.

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
