# Arena and Hunting implementation plan

Status: Hunting, the bounded default Special Quest, the curated 42-stage Archive
Special Quest families, bundled Strikes Back, all 12 Tower solo-adapter stages, and the 12
battle/banner-backed solo Eidolon stages are implemented; Arena VS remains deliberately
disabled. This
document separates the solo content that can be made available through the
surviving client from the original online Arena system, which cannot be made
functional by adding ordinary HTTP responses.

## Progress against this plan

| Step | State |
| --- | --- |
| 0. Certify account and resource stability | Done. The account lifecycle and the whole Chapter 2--42 story are now certified by the public suite. |
| 1. Hunting discovery | Static client gates and selector list contract recovered; live historical-service schedule remains unavailable. |
| 2. Hunting vertical slice | Catalog, selector projection, lifecycle, costs, bounds, replay, and restart are implemented (`liminal_gate/hunting_catalog.py` and `liminal_gate/server_constants.py`). |
| 3. Expand by family | Bundled local policy declares the recovered Hunting, Metal, Crystal Road, and fourteen packaged non-collaboration Counter Descent families with explicit per-stage bounds. |
| 4. Arena -> Special Quests | Chapter 3003-1 is bundled after Chapter 3. Guided setup also derives 42 curated stages across Archive Chapters 2000--2011 and 2014--2018 from the tester's matching BattleData and character catalog. |
| 4a. Tower | All 12 BattleData-backed stages in Chapters 9010--9013 use the dedicated selector and normal durable event lifecycle as a labeled solo adapter. |
| 4b. Eidolon Quests | The 12 nonzero-battle rows with matching final-client banners use the dedicated selector; the 16 empty tier placeholders are excluded and solo collectible mapping awaits a result capture. |
| 5. Keep Arena VS disabled | Unchanged; no work planned or done. |

The selector lives in `get_server_status.constants`. The server sends the
complete required block and derives both selector lists from account progress;
it never attempts a one-field partial projection.

## Product boundary

| Client destination | Public goal | Explicit non-goal |
| --- | --- | --- |
| Hunting | User-local, solo Metal/Hunting stages selected and settled through the normal quest lifecycle. | Recreating retired rotations, paid-entry systems, or unbounded client-authoritative rewards. |
| Huntland -> Strikes Back | Packaged non-collaboration Counter Descent families, progress-gated and settled through the bounded normal quest lifecycle. | Claiming recovered historical dates, rotations, or rewards. |
| Arena -> Special Quests | Bundled Chapter 3003-1 plus the generated 42-stage curated Archive and any explicit reviewed override, using structurally validated Hunting/event settlement; Hunting reward maxima are optional strict-audit data. | Treating Special Quests as PvP or a live event schedule. |
| Tower | All 12 shipped battles, permanently available after a local Chapter 3 gate as a solo adapter. | Shared HP, staged achievements, rankings, historical rotations, or invented fixed rewards. |
| Eidolon Quests | The 12 converted solo battles with matching banners and zero fabricated collectible reward. | Empty tier placeholders, retired Co-op, in-battle summoning, enhancement, or server-side rerolling. |
| Arena VS / ranking | Remain visibly unavailable. | Photon rooms, friends, matchmaking, rankings, co-op, raids, or a simulated service presented as the original Arena. |

The current `GET /gd/multiplay_enable` response must remain the confirmed
disabled shape:

```json
{"success":true,"enable":false,"enablemain":false}
```

The client enters a Photon-backed real-time state machine if this becomes true;
that is an architectural boundary, not an endpoint backlog.

## Evidence already available

- The top-level Hunting and Arena screens are local setup screens. Their first
  meaningful network boundary is inside a selector or a quest lifecycle, not
  the button click itself. `reports/free_roam_endpoint_survey.md`.
- Huntland battles and their stage metadata are client-executed. The server
  needs only the normal `start_quest` / `clear_quest` lifecycle, durable active
  quest state, and bounded settlement. `reports/huntland_metal_hunting_preflight.md`.
- The private implementation proves a lifecycle design, not public data to
  copy: active-stage ownership, request-ID/body-hash replay, restart recovery,
  and server-side validation before settlement. The public implementation must
  derive any stage catalog from tester-supplied local inputs.
- Arena -> Special Quests is a solo selector. The public event-catalog path
  already provides one bounded pattern: user-local event metadata, local
  character catalog validation, start/clear replay, and a client-visible flag.
  `docs/advanced-configuration.md`.
- The exact final unlock thresholds and production rotations for Hunting were
  not captured. Any availability schedule must be labeled local policy rather
  than historical behavior.

## Remaining delivery boundary

Hunting now has strict bundled/user-local catalogs, account-progress selector
projection, bounded start/clear settlement, one-active-quest enforcement,
body-scoped replay, and restart coverage. These establish local preservation
behavior; a future private capture may refine historical unlock schedules or
stage-specific bounds without changing that architecture.

Strikes Back reuses the same lifecycle through the event catalog. The bundled
Counter Descent policy declares Chapters 8000--8007 with five tiers each and
Chapters 8012--8017 with three tiers each, folds every unlocked family to one
selector row, and validates a zero-base clear. Little Noah 8008--8011 and Hime
Rush 8018 remain excluded because their distinct progression/reward contracts
are unrecovered. Original-client selector navigation and Chapter 8000-1 entry
are confirmed; all Counter Descent clear callbacks and the added families'
selector acceptance are still outstanding.

Arena -> Special Quests merges recovered Chapter 3003-1 with 42 generated
Archive stages across Chapters 2000--2011 and 2014--2018 as their progress gates open.
The archive rows come from matching user-local BattleData and character
catalogs. Permanent gates, zero fixed clear-Coin increments, and first-section
associated character grants are local policy; variable battle Coins are
reconciled from the client result. Jade Dragon 2004-1 clear and return to free
roam are client-confirmed. An explicit reviewed catalog replaces the generated
Archive rows but not Chapter 3003-1 or bundled Strikes Back.

Arena VS stays explicitly disabled.

The corrected Tower selector and first-stage battle load are operator-confirmed
on the physical final client. A Tower clear/result return and every Eidolon
client path remain outstanding; local real-HTTP replay/restart coverage does
not replace those observations.

No HTTP implementation work is planned for `start_vs_quest`, `clear_vs_quest`,
ranking, or opponent routes. They depend on Photon room lifecycle, peer turns,
shared state, and multiplayer result handling.

If a future local-only mode is desired, create a separately named **Offline
Arena Trial** proposal. It must be an explicit redesign with a local opponent,
ordinary solo battle controller, separate save namespace, no ranking, and no
claim of online-service parity. It is not part of this plan.

## Common implementation invariants

Every new solo stage path must prove:

- an account owns exactly one active quest across story, Hunting, and Special
  Quests;
- an accepted request commits its state and replay response atomically;
- same request ID plus the same body replays, while a different body is
  evaluated on its own merits;
- a rejected request does not alter wallet, roster, party, or active quest;
- restart preserves the active-stage decision and completed result;
- direct client resource URLs resolve only through a hash-validated,
  tester-local resource manifest;
- unknown stages, schedules, and reward fields remain unavailable rather than
  receiving generic success.

## What is needed next

The next work packet is original-client acceptance for the default Special
Quest or the first reproducible post-Chapter-2-1 client failure. Useful public
input is a sanitized event-log excerpt and derived request shape. No APK,
resource archive, account save, token, authentication digest, or private
capture should enter the public repo.
