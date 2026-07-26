# Arena and Hunting implementation plan

Status: Hunting selector and bounded solo lifecycle implemented; Arena VS
remains deliberately disabled. This
document separates the solo content that can be made available through the
surviving client from the original online Arena system, which cannot be made
functional by adding ordinary HTTP responses.

## Progress against this plan

| Step | State |
| --- | --- |
| 0. Certify account and resource stability | Done. The account lifecycle and the whole Chapter 2--42 story are now certified by the public suite. |
| 1. Hunting discovery | Static client gates and selector list contract recovered; live historical-service schedule remains unavailable. |
| 2. Hunting vertical slice | Catalog, selector projection, lifecycle, costs, bounds, replay, and restart are implemented (`liminal_gate/hunting_catalog.py` and `liminal_gate/server_constants.py`). |
| 3. Expand by family | Bundled local policy declares the recovered Hunting and Metal families with explicit per-stage bounds. |
| 4. Arena -> Special Quests | Outstanding, and gated on the same kind of capture. |
| 5. Keep Arena VS disabled | Unchanged; no work planned or done. |

The selector lives in `get_server_status.constants`. The server sends the
complete required block and derives both selector lists from account progress;
it never attempts a one-field partial projection.

## Product boundary

| Client destination | Public goal | Explicit non-goal |
| --- | --- | --- |
| Hunting | User-local, solo Metal/Hunting stages selected and settled through the normal quest lifecycle. | Recreating retired rotations, paid-entry systems, or unbounded client-authoritative rewards. |
| Arena -> Special Quests | User-local, solo event/archive stages, using the existing local-event catalog path. | Treating Special Quests as PvP or a live event schedule. |
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

Arena -> Special Quests should continue through the existing user-local event
catalog rather than a second backend. Its next vertical slice needs one
sanitized selector/flag work packet and real-client acceptance. Absent stages
remain invisible.

Arena VS stays explicitly disabled.

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

The next work packet is the first reproducible Special Quest or post-Chapter
2-1 client failure. Useful public input is a sanitized event-log excerpt and
derived request shape. No APK, resource archive, account save, token,
authentication digest, or private capture should enter the public repo.
