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

## Blockers and unresolved fidelity

- Hunting selector flashing/loading after its rows render. Live diagnostics
  show no associated banner/resource request or 404, so a client runtime
  capture is still needed before changing server behavior.
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
