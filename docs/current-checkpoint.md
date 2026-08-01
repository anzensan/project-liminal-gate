# Current Checkpoint

Date: 2026-07-31

Mode: public-release implementation hardening.

Deepest verified client path: clean local setup played through Chapter 9 on a
physical device without a client-visible failure.

Evidence note: Chapter 2-1 remains the deepest point backed by preserved request
traces. The playthrough and the traces answer different questions -- whether the
game is finishable, and whether the wire shapes are exact -- so both are kept.

Fast validation lane:

```sh
PYTHONWARNINGS='error::ResourceWarning' python3 -m unittest discover -s tests -v
python3 -m compileall -q liminal_gate tests
```

Latest chapter-ticket validation: the live Chapter 8-9 account retained read
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
inbox/read acceptance remains pending.

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
while values below `itmp0=-1`, stale wallets, and Counter Descent nonzero-base
results remain refused. The save returned to `free_roam` with no active quest,
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
the bounded Hunting lifecycle. Permanent
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
original client entered Spinetrich Kino Chapter 8000-1. Its clear callback
remains unobserved; Jade Dragon Chapter 2004-1 navigation, clear, and return to
free roam are now confirmed. Other Archive clears remain open. These
are fast-lane client observations, not a replacement for the Chapter 2-1
canonical certification boundary.

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
