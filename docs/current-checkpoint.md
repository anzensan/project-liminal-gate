# Current Checkpoint

Date: 2026-08-22

Mode: public-release implementation hardening and private on-device packaging.

Deepest verified client path: clean local setup played through Chapter 9 on a
physical device without a client-visible failure.

Evidence note: Chapter 2-1 remains the deepest point backed by preserved request
traces. The playthrough and the traces answer different questions -- whether the
game is finishable, and whether the wire shapes are exact -- so both are kept.

Latest event Luck Treasure Chest correction: Issue 76 reports that no Strikes
Back clear ever showed a Luck reward, at 81.0 average party Luck and on three
separate families. An event `start_quest` is served by the event branch of
`_select_mutation`, which matches the event catalog before the story dispatch
below it ever runs, and that branch was never handed `luck_pool_catalog`. Every
event stage therefore rolled against the bundled record alone, which documents
thirty-one core-story stages and nothing else, so all 177 of them -- Strikes
Back, Special Quests, Descent Quests, the Tower and the Eidolon quests --
returned six empty slots however lucky the party was. The clear half had always
been ready, folding chest Coins into the wallet it expects and granting what the
chest authored, which is why nothing failed loudly. The branch now forwards the
resolver the launcher built. What a chest holds is unchanged and still not
recovered: an operator's `--luck-pool-catalog` first, then the donated pools of
the nearest documented chapter, which for the 8000-series is Chapter 36.

Latest 8-Bit Golem Lambda duplicate correction: a physical-client result in
Strikes Back Chapter 8006 announces +1.0 Luck for a repeated 8-Bit Golem Lambda
recruit, while three repeats left its durable Luck unchanged. The Counter
Descent policy had no character-grant contract, so settlement could preserve the
client's roster but could not apply the client-announced delta. Chapter 8006
now identifies character 897 and commits the observed +10-tenths increment
before replying; focused real-HTTP coverage proves the value and exact replay
survive a restart. The screenshot establishes this family and value only; the
other Strikes Back families remain unmodeled until their result evidence exists.

Latest Chapter-1100 Give Up correction: Issue 73's new-build event record
reached an active Shin'en or Mutoh battle and then sent the client-shaped
`POST /gd/userdata` form containing only `chrdata,lastUpdate`; the server
returned `409 tutorial_state_conflict` while the account remained in
`world_map_special_active`. The generic active-battle exit correctly knew that
phase, but the earlier parser-admission predicate omitted it, so the otherwise
valid two-field write never reached the exit. Chapter-1100 now admits that
ordinary roster write, releases the active battle in the existing durable
transaction, and keeps exact replay, restart, and a fresh route re-entry
covered by focused real-HTTP testing. An original-client retest is pending;
the report supplies field names but not a privacy-reviewed request body.

Latest Lucia entry correction: a tester reports that Lucia the Explorer II
returns Network Error on entry. The reviewed BattleData answers the proposed
cause exactly: Chapter 2006-2 costs 35 stamina plus Item 110 (Key of Hearts) x1,
and 2006-3 costs 40 stamina plus Item 111 (Key of Diamonds) x1. The generated
event catalog previously discarded both entry-item fields, and the Archive
handler accepted only the five-field stamina form. ARM64
`AppServerUtil.<StartQuest>c__Iterator20.MoveNext` at `0xFC4F78` reads
`BattleData.Section.itemID` at offset `0x34`, reads `itemCount` at `0x38`, and
emits both fields whenever both are positive; there is no Metal-only chapter
guard. BattleData import and event generation now preserve the pair, and event
start charges stamina and the declared item in one durable commit, returns the
post-spend inventory, refuses an absent key through the client's own
NotEnoughItems code, and keeps the spend through exact retry, lost-response
re-entry, clear, and service restart. Focused real-HTTP validation passes;
physical-client Lucia II entry remains pending. Dedicated deployments must
regenerate the event catalog and restart; on-device deployments need an APK
rebuild because the generated catalog and server are packaged together.

Latest duplicate-grant and roster-write correction: two testers reported Luck
that appeared after a battle and was gone afterwards, and one reported a Hunt
For Joker duplicate paying +20% Skill Boost and +1 Luck where the client's own
recruit message announced +10% and +10. Disassembly settles who owns what:
`Character.ToHashTable` (`0xD0A318`) serializes exactly `id`, `jobID`, `flags`,
`jobLevels`, `jobSlots`, `skillBoost`, `buddy`, `date`, while
`Character.LoadFromJson` (`0xD07C5C`) additionally calls `set_luck` and reads
`plusCount` — so the client transmits Luck on no route at all, and
`UITeamStateItem.UpdateForResult` applying `luckUpTable` at the result screen is
an in-memory change the next userdata read replaces. Two defects followed from
that split and are fixed: the Joker duplicate's Skill Boost was granted after
the clear merged a row the client had already raised, paying it twice, and is
now granted before the merge; and the free-roam roster write merged submitted
members with a bare dictionary update, letting a stale client walk `skillBoost`
and `jobLevels` backwards, and now runs through the same monotonic merge every
clear uses. `_JOKER_DUPLICATE_LUCK` returns to 100 tenths to match the
announcement the client renders. Focused real-HTTP regressions cover a
duplicate clear that reports the raised Skill Boost, one that does not, and a
stale roster write. Both deployments are affected: dedicated servers restart,
on-device testers need an APK rebuild. The originally reported Luck loss on the
Lucky Orbling daily is **not** explained by these two: that settlement commits
correctly in a focused real-HTTP reproduction, so the reporting testers' server
logs around a daily clear are still wanted.

Latest Puppet Show audit correction: a tester reports receiving 74 items in a
single otherwise-stock battle, disproving the bundled strict-audit aggregate of
60. `puppet_show_item_aggregate` now defaults to the observed 74. This remains
local policy rather than a recovered maximum because the real-time board has no
cumulative spawn counter and no raw capture accompanied the report. The ceiling
applies only under `--outcome-strict`: exceeding it refuses the complete clear;
it never discards chests after the limit. Focused real-HTTP coverage proves 75
is rejected without mutation, 74 settles once, and exact replay survives a
server restart. Normal preservation mode remains structurally bounded rather
than applying catalog reward maxima.

Latest optional-selector refresh correction: two testers reported that newly
eligible Metal, Huntland, and Arena solo stages remained absent until the app
restarted. The server split the two client-owned halves of visibility:
`get_server_status` carried progress-gated selector lists in `constants`, while
login carried their matching `eventFlags`. ARM64 static analysis confirms that
both callbacks accept both objects: status calls `EventManager.SetFlags` at
`0xFB5568` and tail-calls `UserData.SetServerConstants` at `0xFB5644`; login
calls the same setters at `0xFB7998` and `0xFB7B28`. Both responses now derive
and send a progress-consistent pair. A focused real-HTTP regression proves a
locked row and flag are absent, a progress transition followed by login alone
publishes both without mutation, status agrees, and restart preserves the
result. Original-client confirmation without a relaunch remains pending; no
affected-run raw capture was supplied.

Fast validation lane:

```sh
PYTHONWARNINGS='error::ResourceWarning' python3 -m unittest discover -s tests -v
python3 -m compileall -q liminal_gate tests
```

Latest reachability correction: Orbling Cavern and Cryptid Forest, the two
standing World 1 areas, had never appeared for any tester. The client builds
each map point only when `EventManager.IsEnabledAny` finds an enabled flag under
`sp_ch_700` or `sp_ch_701`, a prefix scan over the served `eventFlags`, and no
key under either had ever been sent. `ChapterInterface::.cctor` identifies
7000--7009 and 7010--7019 as the two ranges; only 7000 and 7010 carry sections,
so four stages. `--cavern-forest` sends the four per-section flags once an
account passes the client's own `openChapter`, and the stages settle through the
Hunting transaction as unadvertised rows -- `UISpecialSelect` modes 1 and 2 read
hardcoded lists and never consult a served one, so the server opens the door and
nothing more. Physical-client confirmation is complete: an operator
opened both map points and both two-card selectors, cleared Orbling Cavern
and received its Companion, and cleared Cryptid Forest with its job
materials and Luck settling.

Latest Android-host correction: the Android 16 launch crash is Unity's own
advertising-ID bind, not Play Billing. A Galaxy S26 crashed with all eighteen
`--disable-google-services` dex edits verified applied; `libunity.so` carries its
own copy of `com.google.android.gms.ads.identifier.service.START`, once per ABI,
that no dex edit reaches, and builds its `ServiceConnection` as a
`java.lang.reflect.Proxy` -- the only kind here that fails, because a Proxy
routes an interface's `default` methods to its handler while an ordinary class
inherits them. All twelve classes in the client dex implementing
`ServiceConnection` are ordinary classes, which retracts the earlier attribution
to Play Billing. The flag now patches both `libunity.so` members. Physical
confirmation is complete: a Galaxy Tab A9+ on Android 16, API 36,
runs a separate-server build carrying all three edits through launch and real
gameplay, which is the route with no host guard and the configuration the S26
crashed in. No unpatched control was taken on that tablet, so the crash and the
fix are each confirmed on Android 16 but on different devices.

Latest Luck-state correction: a user report that every character returned to
zero after a battle matches a confirmed final-client wire detail: valid
`clear_quest.chrdata` may omit the optional `luck` member. The shared roster
merge preserved stale-safe job progression and Skill Boost but not Luck, so an
omitted or explicit stale zero could replace the durable value before the
server returned the roster. The merge now preserves the greater Luck value and
then applies the cached `luckUpTable` gain inside the same clear transaction.
A focused real-HTTP regression starts with Luck 5.0, submits the client-shaped
omission, applies one authored 0.2 gain, returns 5.2, replays without another
gain, and persists 5.2 across restart; a lower explicit value is also preserved
against. The 23-test focused story/Luck lane passes. Physical-client validation
remains pending. The complete warning-strict suite
passes all 957 tests with five expected skips; compilation, endpoint YAML, and
diff checks pass. Values already lost from a save cannot be inferred and need
a pre-reset backup for exact recovery.

Latest Luck-growth correction: two operator reports separated preservation from
growth -- a character kept 10% Luck across Metal Zone runs while nothing
anywhere raised it, and the Lucky Orbling quest showed 1.8 in battle and
nothing in the party menu. Only the generic story handler rolled and applied
`luckUpTable`, so the Hunting family and Chapter 1100 could not raise Luck at
all despite costing up to 25 stamina, and the `allowLucky` Lucky-enemy source
the record documents was never implemented. Both start/clear pairs now author
the table at entry and apply it once after the roster merge, and the five
flagged chapters carry the Lucky-enemy source, which is deliberately outside
the confirmed ≥8 stamina gate because three of them are free or cheaper than
that. Real-HTTP checks over the repository's own Hunting fixture confirm a
flagged seven-stamina stage grants +0.3 on about half its battles and persists
to `state.json`, while an unflagged three-stamina stage grants nothing across
24 runs. The complete warning-strict suite passes all 1005 tests. Physical-client
confirmation remains pending, and Luck already lost to the earlier defect cannot
be reconstructed without a backup.

Latest daily-drop validation: Issue 35 identified the missing gate for the
final client's native ordinary-story rotation. Guided core story now supplies
the exact boolean `enableDailyBonus` event flag during login. Dual-ABI client
analysis confirms that the client selects item x2, monster-recruit x2, or no
bonus from a 15-day cycle anchored to 2015-01-01, using the server-corrected
instant and the device-local calendar day; Companion and Battle Summon drops
are not doubled. The linked Terra Battle Stats calendar independently resolves
to the same cycle and chapter groups. Focused real-HTTP tests cover the exact
nested flag and disabled/enabled boundary. Continuous activation is explicit
preservation policy because the retired service's event window was not
captured. Physical confirmation of the map badge and an eligible roll remains
pending. The focused login/setup lane passes 67 tests and the complete
warning-strict suite passes all 955 tests with five expected skips; compilation,
endpoint YAML, and diff checks pass.

Latest login-reward validation: guided core story issues the published
standard consecutive and cumulative login presents through `messageList`.
Eligibility is account-local and turns at 00:00 UTC; the message and updated
last-day/consecutive/total counters commit before login exposes it. Focused
real-HTTP tests cover day-1 dual issuance, read/delete, same-day relogin,
restart, next-day continuation, missed-day reset, and omission of claimed
messages from the next login projection so the new badge cannot recur. Reward
values and timing are settled community-recorded local policy; inbox transport
and settlement reuse the existing replay-safe client path. Original-client
rendering and claim acceptance remain pending. The separately branded
seven-day newcomer event remains a distinct unaudited policy.

Latest settlement-policy correction: Hunting, Metal, default Special, and
Daily Quest clears now trust the surviving client's structurally valid result
for its exact active battle. The server still enforces identity, wallet
arithmetic, item/ticket projection, Companion-box integrity, replay, and
durable one-time commit. Per-stage reward maxima moved behind the existing
`--outcome-strict` audit option. The Issue 20 Pixel attachment contains 25
Crystal Road 3004-1 refusals: every result reports 280 Coins, with 21 reporting
5,400 EXP and four reporting 5,625 EXP, against the old zero placeholders. A
real-HTTP regression accepts 280/5,625 by default and proves exact restart
replay grants the Coins once; strict mode retains the old refusal tests.
The focused Hunting/Daily lane passes 74 tests and the complete warning-strict
suite passes all 919 tests in 147.266 seconds; compilation, structured-file,
and diff checks pass. Original-client retest after this policy change remains
pending.

Toolchain checkpoint: `doctor --install-missing` now covers the last mandatory
command-line prerequisite. When no existing disassembler reports AArch64
support, it installs Google's pinned side-by-side Android NDK r27d under
`user-data/`, verifies the exact host `llvm-objdump` with the same capability
probe guided derivation uses, and records it atomically. Android SDK licence
acceptance remains explicit. Android Studio and emulator creation remain
optional/out of scope; no gameplay or protocol boundary changes with this
tooling path.

On-device checkpoint: the source-hash-guarded private builder, dual-ABI
Chaquopy host, packaged resource catalog, loopback health gate, app-private
state bootstrap, signing, and installation path are implemented. The real
5.5.7-170 full build packaged all 11,806 retained resources (940,138,388 bytes),
passed alignment/signature/package/SDK/launcher/dual-ABI inspection, and
the immediately preceding full-resource payload launched on an API 34 ARM64
emulator. It returned its matching build ID over `127.0.0.1:8002/healthz`,
initialized Unity only after that boundary, served a manifest-selected resource
with exact size/SHA-256, and recovered after force-stop/relaunch in a new
process. The final source-exact artifact is SHA-256
`aeba11eade3b507d62403ee806b3e7390bb3a2abced03a0219e3ec4633685ef0`,
payload ID `53d043cbb585337d19a749ef1a1735b31c5499bbe00c1376123d9600900fff93`;
it passed offline package/signature/transport inspection but the validation
emulator lacked space to replace the prior 1-GiB install. Final-artifact
physical ARM64, ARMv7 runtime, and combined-APK Chapter 2-1 acceptance remain
pending and do not change the canonical gameplay boundary above.

Latest on-device seed correction: Issue 30's Pixel 7 Pro/Android 15 diagnostic
reached `python_start` and then refused the hard link used to publish an embedded
first-install save. Seed publication now takes the state store's existing
single-writer lock, rechecks absence, and atomically renames a fully written and
fsynced temporary file. Focused real-HTTP startup tests cover Android-style hard
link denial, interruption before commit followed by retry, existing-save
preservation, and matching `/healthz`. Physical-device seeded startup and
force-stop/relaunch remain pending.

Latest on-device save-transfer confirmation: an operator on a Windows build
host reports that `on_device_state export` and `update` both succeed against a
physical Pixel 7 Pro running Android 15 that carries real gameplay progress,
after commit `839cf9d` made `main` replay the recorded `user-data/toolchain.json`
for all three subcommands. This is the first physical-hardware report of the
combined APK reaching gameplay, and the first of an in-place `update`
preserving an app-private save; it supersedes the "establishes no new device
acceptance" note on the 2026-08-03 save-transfer entry. It does not identify
the installed artifact as the final source-exact build, and `import`, the
ARMv7 runtime, and a Chapter 2-1 clear backed by preserved traces remain
pending. Whether this is the same device as the Issue 30 seed diagnostic above
was not established, so that entry's pending seeded startup stands.

Latest chapter-ticket compatibility correction: Issue 33 supplied the first
physical-client presentation result for the guided milestone inbox. The final
client displayed the Chapter 7 row and its text, but an empty reward area and
an unread badge survived opening it. The prior real-HTTP proof therefore did
not establish client acceptance. Guided core story now settles each eligible
Chapter 5/7 Metal Ticket and Chapter 6/8/10 Companion Ticket directly into the
durable item inventory before login responds and omits its internal read record
from `messageList`. Existing unread milestone mail is granted once and marked
read; existing read or deleted milestones are adopted without another grant.
Focused real-HTTP tests cover first settlement, same-process retry, migration
of Issue-33-style unread state, later threshold crossing, and restart. Physical
client confirmation that the stuck row disappears and Item 50 increases by two
remains pending. User-authored and daily-login messages still use the separate
inbox transport and retain their own original-client acceptance boundary.

Earlier chapter-ticket validation: the live Chapter 8-9 account retained read
Chapter 5 Metal Ticket x2 and Chapter 6 Companion Ticket x3 messages but lacked
the already-earned Chapter 7 Metal Ticket x2 present. Guided core story now
issues the retail Chapter 5/7 Metal and Chapter 6/8/10 Companion Ticket presents
through the inbox. Progress must have entered the following chapter. A durable
issued-ID sentinel is committed before login exposes a message and survives
read/delete, so neither relog nor restart can recreate a claimed reward. On a
copy of the live save the migration adopted the two existing messages, created
only Chapter 7, left both inventory balances unchanged until read, and did not
issue Chapter 8 early. Real-HTTP tests cover read replay, deletion, restart, and
Chapter 8 issuance after entering Chapter 9. All 656 warning-strict repository
tests pass; compilation and diff checks pass. Publication, Beelink deployment,
and original-client inbox acceptance were the remaining boundaries at that
test checkpoint. Commit `d976bd5` is now pushed and deployed on the Beelink
under systemd PID 264479. A live login at progress 8-10 returned the existing
read Chapter 5/6 messages plus exactly one unread Chapter 7 Item 50 x2 message;
durable Item 50 and Item 112 balances remained zero until read. Original-client
inbox/read acceptance remained pending and is now superseded by the Issue 33
compatibility correction above.

Latest curated Archive validation: dual-ABI `UISpecialSelect.SetMode(0)`
analysis confirms that a nonempty server `specialQuestList` overrides the
embedded fallback array. Guided setup now derives 42 release-facing stages
across 17 chapters, with folded or explicit selector identities matching the
final client. Matching BattleData, compiled chapter programs, backgrounds, and
required explicit banners exist for every selected stage. Test Chapter 2012,
bannerless Chapter 2013, and empty 2015-4--6 placeholders remain excluded.
The permanent gates and first-section character grants remain labeled local
policy. At that deployment checkpoint the retained inputs generated 140 stages
across 47 families; the later Eidolon correction below replaces the 28 raw
Eidolon rows with twelve battle/banner-backed rows.
Focused warning-strict validation passed 139 tests and the complete suite
passed all 653 tests in 128.357 seconds; compilation, profile JSON, endpoint
YAML, and diff checks passed. See `solo-event-completion-audit.md`; broader
physical-client acceptance remains a separate boundary. Commit
`5302fb0` is now deployed at `/opt/project-liminal-gate`; the Beelink generated
that exact catalog hash and systemd relaunched the server under PID 250477.
For the active Chapter 8 account, real HTTP returned Archive cards `2000`,
`2004-1`, and `3003-1`, three unlocked Strikes Back cards, all 12 Tower rows,
and the then-incorrect 28-row Eidolon list. The exact multiplayer response remained
`enable=false, enablemain=false`, news returned HTTP 200, and the durable save
hash remained
`cb0ccb214f6a13b3337b8410996788e6e386d287ad49ddf46bfe3b0c04655c3c`
across restart. The maintainer subsequently opened the single Bahamut `2000`
card in the physical final client and observed all four sections. The Beelink
tail records the corresponding fresh login/status session, but no battle start;
this confirms folded selector presentation only. Bahamut entry and result
settlement remain the next boundary.

Latest Archive client validation: the original Android client cleared Jade
Dragon Chapter 2004-1 and exited its result screen after the server returned
HTTP 200. The exact preserved form reports 819 battle Coins, 6,851 EXP, and
`itmp0=-1`; after a clean login its wallet reported 11,824, matching durable
11,005 plus those 819 battle Coins. Event settlement now reconciles that
client-reported amount in addition to the catalog's zero fixed clear increment,
while values below `itmp0=-1` and stale wallets remain refused. Counter Descent
results were refused here too; issue 46 showed that clause refusing every real
clear of that family, and it now settles them from the client's own report. The save returned to `free_roam` with no active quest,
11,824 Coins, 27 free Energy, 78 characters including Jade Dragon, and the
submitted item counts. Its SHA-256 remained
`cb0ccb214f6a13b3337b8410996788e6e386d287ad49ddf46bfe3b0c04655c3c`
after a service restart from PID 218246 to 219886. Other Archive clears remain
unverified. Thirty-six focused event tests and all 642 warning-strict
repository tests passed; compilation, profile JSON, endpoint YAML, and diff
checks passed.

Latest tutorial Pact validation: the mandatory `kind=10` draw now declares
equal weights for Bahl (character 1) and Grace (character 3), following the
maintainer-supplied retail rule. The selected starter commits with the roster,
team, canonical response, and replay entry. Real-HTTP tests force each branch;
the Bahl branch survives restart, replays without another random draw, receives
A'misandra into `[1, 25]`, and settles the following tutorial userdata without
introducing Grace. Legacy saves without the explicit starter retain their prior
Grace behavior. The exact request and Grace client path are confirmed; a clean
original-client Bahl result and continuation remain unverified, including the
Bahl-specific packed level/EXP projection returned after Chapter 1-2. Thirty-two
focused bootstrap/profile tests and all 641 warning-strict repository tests
passed; compilation, structured-file, and diff checks passed.

Latest Tower/Eidolon validation: the physical client exposed the flaw in the
initial 28-row Eidolon projection because sixteen cards lacked banners.
APK-matched BattleData has exactly twelve nonzero-battle rows, and those exact
identities are the only Chapter-4100--4111 entries in the final Android
`SpecialBanner` catalog and retained resources. The generator now projects
4100-3, 4101-3, 4102-3, 4103-1, 4104-3, 4105-3, 4106-1, 4107-3, 4108-3,
4109-3, 4110-1, and 4111-1, refuses BattleData shape drift, and generates no
solo collectible ceiling. Older Co-op enemy drops do not prove the reward on
these different solo programs. Local output is 124 rows across 47 families
with SHA-256
`1b99bc264ac6dbba4f81f4d89105e54e804b9f12cdaa4078d516886b3044ceeb`.
Forty focused tests and all 654 repository tests pass warning-strict;
compilation, JSON/YAML parsing, and diff checks pass. Both publication gates
pass from a clean candidate. Commit, Beelink deployment, and corrected device
banner confirmation remain pending.

Prior Tower/Eidolon validation: final-client static output contains the
dedicated Tower and Eidolon lists, selector modes, Tower Chapters 9010--9013,
Donation Chapters 9100--9102, converted solo Eidolon Chapters 4100--4111, and
the distinct result-screen Summon acquisition path. Guided setup projects all
12 Tower solo-adapter stages and initially all 28 raw solo Eidolon rows from
matching user-local BattleData behind a permanent Chapter 3 local gate. It
does not expose Donation. Eight disabled first-tier Eidolon rows carried one statically recovered
Summon ceiling; the generic server path accepts no drop
or that one previously unowned ID and durably records raw value `1`. Real-HTTP
tests cover visibility, entry, accepted clear, exact restart replay, and the
absence of a synthetic response `summonList`; focused mutation tests refuse an
unlisted, duplicate, or already-owned report without changing state.
The maintainer subsequently opened the corrected Tower selector on the
physical final client and its first entry loaded the battle after a retry.
That confirms Tower navigation and entry at the operator-observation level;
no preserved request trace or successful Tower clear/result return is claimed.
The over-broad Eidolon selector rendered on the physical client, which exposed
its missing-banner rows; corrected selector, battle, and result acceptance remain open. The earlier
9100--9102 Tower claim was retracted after the authoritative
range audit identified those chapters as Donation. The corrected generator
emitted 115 rows across 35 families: exactly 12 Tower rows, no Donation rows,
and the then-incorrect 28 Eidolon rows. Focused validation passed 106 tests, and all 648
warning-strict repository tests passed in 127.822 seconds.

Latest clean-onboarding validation: 585 warning-strict tests passed in 112.308
seconds. A clean public clone with no prior derived output generated IL2CPP and
master-data catalogs, built and installed the client, completed fresh
signup/login/userdata and the first tutorial Pact mutation, then loaded the same
account and persisted tutorial state after a full server restart. All 548
captured requests returned HTTP 200. This certifies the onboarding and restart
path; it is not a new client boundary beyond Chapter 2-1.

Latest source validation: 619 warning-strict tests passed in 118.143 seconds.
That run includes the Issue 25 real-HTTP Special Quest settlement recovery,
Issue 22 tutorial recovery, and the exact hash/byte-guarded Issue 15 ARM64
constructor replacement. Compilation, profile JSON, endpoint YAML, and diff
checks pass. An exact clean source candidate passed both publication gates.

Prior guided archive-event validation: setup derives `event-catalog.json`
from matching local BattleData and character inputs and starts it by default.
At that checkpoint, Archive Chapters 2000, 2001, 2002, 2004, and 2006 merged with Chapter 3003-1;
bundled Counter Descent remains authoritative for Strikes Back Chapters
8000--8007 and 8012--8017; collaboration/special Chapters 8008--8011 and 8018
remain unavailable. Archive gates, zero fixed clear-Coin increments, and
first-section associated character grants are labeled local policy; variable
battle Coins come from the client result. Focused real-HTTP tests cover
selector projection, start, body-scoped same-ID/different-body handling,
bounded clear, replay, and restart. The warning-strict full suite passed all
635 tests in 118.402 seconds; compilation, profile JSON, endpoint YAML, and
diff checks passed. Physical-client Jade Dragon clear is now confirmed;
Bahamut and Strikes Back clears remain open.

Prior guided-setup validation: preflight and the real build resolve the same
explicit or generated `(DummyDll, dump.cs)` pair and validate port and
device-host routing before expensive work. The focused warning-strict setup
suite passed 123 tests; the complete warning-strict suite passed all 625 tests
in 118.332 seconds, and compilation and diff checks passed.

Latest client blocker: Issue 25 captured a final-client Chapter 3003-1 clear
reporting 1,800 Coins. The old local 1,500 ceiling rejected settlement and
durably retained `hunting_active`, which correctly survived restart but blocked
all unrelated stage starts. The bounded policy now accepts the observed 1,800
and refuses 1,801; real-HTTP rejection, recovery, replay, and restart validation
passed. Reporter retest remains the client-visible completion boundary.

Latest ARM64 portability validation: the Issue 15 plan replaces the exact final
Unity 2017 default-allocator constructor with the `DynamicHeapAllocator`
already present in that player. A signed APK remained live through title
startup and real HTTP on ARM64-only Android 12 with 11,940 MB reported RAM and
Android 14. The Android 12 process peaked at 66,027,632 kB virtual memory with
no old allocator message or signal 11. Its unpatched control also stayed live,
so the AVD did not reproduce the Pixel 7 Pro allocation pattern;
original-device acceptance remains the next boundary.

Latest live deployment: Beelink commit `99a6143` loads the corrected generated
Archive/Tower/Eidolon event catalog and its matching character authority.
Both identify final Android APK SHA-256
`f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15`;
the deployed event and character files have SHA-256
`8e23ea0f63614050c73bf7cf7154ca27d641688b69ac54f575c5c298ca457cf9` and
`ff79204f1020ff44022ae95fa30ee87e2b0e2a9e656d4b2f85d5fe52f3b980be`.
After a clean launcher restart, the real `/gd/get_server_status` transport for
the active Chapter 8 account returned all 12 Tower identities from 9010-1
through 9013-3, the then-incorrect 28-row Eidolon list, and zero Donation
identity from Chapters 9100--9102. `multiplay_enable` still returned
`enable=false` and `enablemain=false`. The durable account state remained
byte-identical at SHA-256
`cb0ccb214f6a13b3337b8410996788e6e386d287ad49ddf46bfe3b0c04655c3c`,
and the loopback news request returned HTTP 200 after the systemd-owned service
restarted under PID 241704. Jade Dragon card rendering and clear are
client-confirmed. Tower navigation and first-entry battle loading are now
operator-confirmed on the physical device; Tower clear/result return and all
Eidolon client acceptance remain to be observed.

Publication lane:

```sh
python3 -m liminal_gate.release_preflight
python3 -m liminal_gate.release_audit
```

Current deliberate boundary: Chapter 2-2 through Chapter 42 is enabled as
ordered local progression policy, not canonical proof of every original
reward, drop, encounter, or scripted scene.

Current Eidolon boundary: Version 5.5.0 retired in-battle Eidolon summoning,
its multiplayer charging gauge, and Tavern enhancement, so none is required
for final 5.5.7 solo completeness. The former Co-op Eidolon quests became
single-player quests, and final-client static evidence retains their Mode 4
selector, Chapters 4100--4111, and collectible result path. The public server
now projects the twelve battle/banner-backed solo stages. Its generic explicit
catalog settlement remains replay-safe, but generated collectible mapping is
capture-gated. Original-client clear/result acceptance and before/after
owned-Eidolon observation remain pending. The recovered
skill-unlock route remains archival
compatibility evidence behind an explicit option, not a guided or server-only
default or a claimed reachable final-version UI loop.

Current optional-content observation: a resumed migrated account displays
Hunting and Metal selector rows after pre-login progress resolution. Metal
owns both regular and All Hail the King rows plus both Roads; Hunting also
receives bounded Crystal Road 3004-1 after Chapter 3, with its exact event
flag. Arena -> Special Quests no longer inherits the client's built-in Metal
fallback list and, after Chapter 3, receives bundled Chapter 3003-1 through
the structurally validated Hunting lifecycle. Catalog reward maxima are an
optional `--outcome-strict` audit. Permanent
Fate reaches the ordinary Pact transaction with the captured `luckType=true`
form. The statically recovered one-draw Item 81 Fellowship Ticket form now
settles ordinary and Fellowship-side Fate draws through real HTTP with durable
replay/restart coverage; original-client acceptance is pending. Combined
Companion equip writes now require an atomic owned bidirectional link across
their character and Companion dirty arrays. Newly equipped or retargeted links
also require an APK-hashed generated catalog and enforce the recovered direct
character, ancestor-family, and active-job species restrictions, with real-HTTP
rejection, replay, and restart proof. `RequiredLevel` controls effect activation
in the final client and is not an equip restriction. Original-client acceptance
of this combined transport remains pending. A
ticket-backed Metal Zone 1 result also settles live: the client repeats its
pre-entry Item 50 count, the server retains the already-committed spend, and
the bounded Companion drop persists. Guided setup now derives the five
recovered Archive families and merges their progress-gated rows with Money
Money Time. Strikes Back shows its first two progress-gated families and the
original client entered Spinetrich Kino Chapter 8000-1. Its clear callback was
then observed by issue 46, which reported all of the experience, Coins, and
drops the zero-base settlement had required it to withhold; that family now
settles from the client's own report, and physical retest is pending. Jade
Dragon Chapter 2004-1 navigation, clear, and return to free roam are now
confirmed. Other Archive clears remain open. These
are fast-lane client observations, not a replacement for the Chapter 2-1
canonical certification boundary.

Issue 20's selector is now reported stable, exposing a second presentation
gap: Attack of Coin Creeps had a blank card because the final APK catalog and
retained archives omit every `sp1003` banner. Guided APK preparation now adds
the three missing catalog identities; setup derives internally renamed ENCA
bundles from retained `sp3003-1` Coin Creeps-family art when exact `sp1003`
resources are unavailable, without changing the Chapter 1003 route. The
rebuilt APK, all three derived bundle identities, and real HTTP bytes are verified;
physical-client rendering after reinstall remains pending.

Security boundary: the server listens on the local network for Android device
compatibility. Signup/login associates a client host with an account; a new
token from an unidentified host is refused once ownership exists. Request
bodies are capped at 4 MiB.

Persistence boundary: mutations and body-scoped replay responses commit
atomically. Save-editor cache clearing covers tutorial, achievement, message,
and exchange response caches together. Account-state safety copies use
exclusive creation and cannot overwrite another same-second copy.
Ticket-backed Metal starts retain the payment choice so clear-time stale-client
reconciliation cannot restore the ticket or apply to stamina fallback.
After a Chapter 1-1 restart, the final client may emit its already modeled
tutorial party-save structure while still in `chapter1_1_cleared`; that write
is acknowledged without applying client roster data or advancing the tutorial.
The next Pact remains the forward transition. This fix is transport/restart
confirmed and awaits the Issue 22 reporter's client retest.

Derived-catalog boundary: story-outcome generation rejects native encounter or
character catalogs whose recorded APK hash differs from the selected APK.
Generated catalogs retain their input hashes and native calibration label. The
Companion equipment catalog is likewise bound to the selected APK and projects
only character ancestry, per-job species, and equip restrictions; it contains
no names, skills, descriptions, or assets.

Next unknown boundaries: original-client acceptance of the Item 81
Fellowship/Fate ticket draw and Crystal Road 3004-1; Issue 25 reporter
acceptance after the observed 1,800-Coin Special Quest settlement; the first
reproducible original-client failure after Chapter 8-4; the
another Archive-family clear and associated-character result;
the Strikes Back Chapter 8000-1 clear callback; Tower clear/result return; one
converted solo Eidolon quest result with before/after collectible state; and
the Hunting selector flash after its rows render. The Hunting flash
produced no corresponding server resource request or 404 and needs a client
runtime capture.
