# Project Status

## Current phase

Public-release hardening and client-compatible single-player expansion.

## Verified boundary

- The original Android client path is verified through Chapter 2-1.
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
- 2026-07-27 Strikes Back vertical slice: the standard Hunting policy now
  exposes the eight packaged non-collaboration Counter Descent families through
  the dedicated, progress-gated `descentHuntingList`, with five startable tiers
  per family and exact recovered stamina costs. Start and zero-base clear are
  bounded, replay-safe, and restart-safe. The live client displayed Spinetrich
  Kino and Kraken Kino and entered Chapter 8000-1 successfully; its battle-clear
  callback remains unobserved and is not claimed as client-certified.
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

## Blockers and unresolved fidelity

- Hunting selector flashing/loading after its rows render. Live diagnostics
  show no associated banner/resource request or 404, so a client runtime
  capture is still needed before changing server behavior.
- Original-client Strikes Back battle clear and return to free roam. Selector,
  tier navigation, and Chapter 8000-1 entry are confirmed; clear is currently
  covered only by the real-HTTP regression.
- Retired Tavern “Watch Video” controls are client/ad-SDK UI. The server does
  not advertise or implement an ad service; hiding those controls requires a
  separately validated APK patch.
- Canonical original-client certification beyond Chapter 2-1.
- Exact ordinary-story reward/drop authority and scripted-stage exceptions.
- Battle Summon acquisition and complete equipment/party lifecycle.
- Historical event schedules, campaign behavior, and live-service families.
- Differential certification against excluded private reference evidence.
- Emulator audio cutoff inside the Unity 2017.4/FMOD producer path. Native
  translation and the 24 kHz client track are candidate discriminators, not
  confirmed causes; a matched working Pixel 4 profile capture is outstanding.

## Next recommended task

Capture and certify the next original-client failure after Chapter 2-1, then
implement only that smallest evidence-backed client-visible boundary.
