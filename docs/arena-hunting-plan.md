# Arena and Hunting implementation plan

Status: step 2 partially implemented; steps 1 and 4 still need a capture. This
document separates the solo content that can be made available through the
surviving client from the original online Arena system, which cannot be made
functional by adding ordinary HTTP responses.

## Progress against this plan

| Step | State |
| --- | --- |
| 0. Certify account and resource stability | Done. The account lifecycle and the whole Chapter 2--42 story are now certified by the public suite. |
| 1. Hunting discovery capture | **Outstanding.** Needs the real client at a checkpoint where a selector is enabled. |
| 2. Hunting vertical slice | Catalog, lifecycle, cost, bounds, replay, and restart are implemented (`liminal_gate/hunting_catalog.py`), with a bundled policy behind `--hunting`. The status/selector projection is **not**, and is correctly blocked on step 1. The pass condition is therefore not met. |
| 3. Expand by family | Pudding, Tin, Coin Creeps, and Puppet are declared by the bundled policy at all three zones. Metal remains absent: its EXP and Companion bounds are not expressible here, and results carrying Companions or Summons are refused. |
| 4. Arena -> Special Quests | Outstanding, and gated on the same kind of capture. |
| 5. Keep Arena VS disabled | Unchanged; no work planned or done. |

The selector is blocked for a concrete reason, not merely for lack of a
capture: it lives in `get_server_status.constants`, which this server does not
send at all, and `docs/server-protocol.md` records that a partial `constants`
object crashes the client because its setter directly indexes the first 31
keys. Populating it is a constants work packet, not a one-field addition.

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

## Delivery order

### 0. Prerequisite: certify account and resource stability

Before exposing new selectors, certify the current account path with a fresh
save, one normal Pact, party edit, app-to-title return, restart, and a resource
download pass. This prevents a selector investigation from being confused with
the roster/save defects fixed in `108e7f0`.

Pass condition: no non-200 `/gd/userdata` write and no missing selector asset
in `events.jsonl` for the chosen test path.

### 1. Hunting discovery capture

Use a single fresh test account at a controlled progression checkpoint and
record, without changing the public server:

1. the `get_server_status` response consumed before Hunting opens;
2. the first enabled Hunting selector and its displayed chapter/section;
3. the exact `POST /gd/start_quest` request;
4. the matching clear request, response, retry, and state before/after;
5. every resource request made while opening the selector and battle.

Preserve raw captures privately. The public work packet records only derived
field shapes, stage identity, and tester-supplied catalog provenance.

Decision required after capture: a local availability policy. Recommended
first policy is an explicit user-local catalog with one or more always-available
stages after the configured story checkpoint; do not emulate a retired calendar
until one is recovered.

### 2. Hunting vertical slice: one stage, one family

Implement the smallest end-to-end slice, recommended as one Pudding/Tin-style
Hunting stage before Metal:

- Add a strict user-local Hunting catalog importer/validator. It accepts stage
  identity, entry cost, unlock policy, and conservative allowed result bounds;
  it does not package enemy, reward, or resource data.
- Add a status/selector projection only after the capture establishes the
  client field name and wire type. It must expose only cataloged identities.
- Reuse normal start/clear transport but give the active stage its own durable
  namespace and body-hash/request-ID cache.
- Validate chapter/section, cost, one active quest, roster ownership, and the
  submitted result against catalog bounds before mutation.
- Make accepted result, rejected result, duplicate retry, request-ID collision,
  process restart mid-battle, and restart after settlement deterministic.

Pass condition: original client opens the selector, starts and clears the
single stage, returns to the map, and shows the durable local result after a
server restart.

### 3. Expand Hunting by family, not by a broad enable switch

Expand one independently certified family at a time:

1. Pudding/Tin (bounded item-only results);
2. Coin Creeps (bounded coin-only results);
3. Metal (ticket-or-stamina choice plus dynamic EXP/Companion result rules);
4. Puppet only after its timed-result boundary is captured and bounded.

Each family needs a separate catalog schema, validation matrix, resource smoke
test, and original-client proof. A client-visible 501/409 is preferable to a
success response that accepts an unbounded reward claim.

### 4. Arena -> Special Quests: extend the existing solo event path

Do not build a second Arena backend. Extend the current user-local event
catalog workflow instead:

- Capture the selector visibility condition and exact event flag/list shape
  for one additional solo Special Quest.
- Add that one stage to an operator-local event catalog with its matching
  locally derived character catalog when it grants a character.
- Exercise selector entry, start, clear, retry, restart, and any local
  resource/banner load.
- Keep absent flags/stages invisible rather than rendering an empty or
  fabricated live-event list.

Pass condition: Arena -> Special Quests shows the configured local stage and
completes it without enabling any VS/ranking option.

### 5. Keep Arena VS explicitly disabled

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
- same request ID plus different body returns a conflict without mutation;
- a rejected request does not alter wallet, roster, party, or active quest;
- restart preserves the active-stage decision and completed result;
- direct client resource URLs resolve only through a hash-validated,
  tester-local resource manifest;
- unknown stages, schedules, and reward fields remain unavailable rather than
  receiving generic success.

## What is needed next

The next work packet is the Hunting discovery capture in step 1. The useful
input is a sanitized event log plus the exact start/clear request shapes from
one selector that has actually become enabled. No APK, resource archive,
account save, token, digest, or private capture should enter the public repo.
