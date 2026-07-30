# Current Checkpoint

Date: 2026-07-30

Mode: public-release implementation hardening.

Deepest canonical client path: clean local setup through Chapter 2-1 clear.

Operator acceptance note: the maintainer has played continuously through
Chapter 8-4 on a physical device without a client-visible failure. That run is
not yet a preserved trace-based certification, so it does not replace the
canonical Chapter 2-1 checkpoint.

Fast validation lane:

```sh
PYTHONWARNINGS='error::ResourceWarning' python3 -m unittest discover -s tests -v
python3 -m compileall -q liminal_gate tests
```

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

Latest live deployment: Beelink implementation commit `3fe4336` runs without
the retired `--summon-skills` default. The child command still loads
`story-outcomes.json` and `companion-equipment.json`; durable state matched its
pre-deploy backup byte-for-byte, and loopback and LAN current-time requests
returned HTTP 200.

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
selector, Chapters 4100--4111, and collectible result path. This optional solo
quest/acquisition lifecycle remains unsupported until a successful
original-client result and before/after owned-Eidolon state establish its
mapping and settlement. The recovered skill-unlock route remains archival
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
the bounded Companion drop persists. Strikes Back now shows its first two
progress-gated families and the original client entered Spinetrich Kino Chapter
8000-1. Its clear callback has not yet been observed. These are fast-lane
client observations, not a replacement for the Chapter 2-1 canonical
certification boundary.

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
Strikes Back Chapter 8000-1 clear callback; and the Hunting selector flash
after its rows render. An optional later boundary is one converted solo
Eidolon quest result with before/after collectible state. The Hunting flash
produced no corresponding server resource request or 404 and needs a client
runtime capture.
