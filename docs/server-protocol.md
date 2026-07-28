# Server Protocol

This is the public, implementation-level protocol boundary. Capability status
is machine-readable in `../protocol/endpoint_matrix.yaml`.

## Transport

- The compatibility server uses local HTTP for the surviving Android client.
- It listens broadly only so a physical device or emulator can connect; it is
  intended for a trusted LAN and must not be Internet-exposed.
- POST bodies require a nonnegative `Content-Length`, are capped at 4 MiB, and
  must contain exactly the declared number of bytes.
- Unknown routes fail explicitly instead of returning generic success.

## Account routing and signing

Signup/login carry the client UUID and establish a durable source-host owner.
Most later routes carry `otk` and optional `requestID`, but no UUID. The OTK is
a three-second client time bucket, not an account-unique session identifier, so
the identified host owns later rotated tokens. An unknown host is refused once
ownership exists. See `multi-account-design.md` for limitations.

Response signing remains token-derived according to the included compatibility
profile. Event diagnostics never record tokens, authentication digests, query
strings, account IDs, rosters, or request bodies.

## Mutation contract

Supported mutations validate the exact ordered form and relevant catalog
boundary before changing state. State and the response used for retry are
committed together. Replay identity includes operation, request ID, and body,
so the same ID with a different body is not mistaken for the earlier request.
Caches are bounded and survive restart.

Ticket-backed Metal starts commit Item 50 at entry and retain that payment
choice. The final client repeats its pre-entry ticket count in the later clear;
only that one stale slot is reconciled, and the server-owned lower balance is
returned. Stamina fallback and every other inventory slot remain exact.

## Server constants

`get_server_status` returns the complete required constants object. A partial
object is not served because client setters directly index required economy,
version, and country fields. Hunting selector lists are added per account from
the enabled Hunting catalog and current progress. `specialQuestList` is always
nonempty: after Chapter 3 the bundled local Hunting policy supplies recovered
Chapter 3003-1; a validated user-local event catalog replaces it. Before that
threshold, a closed recovered entry suppresses the client's fixed 50-entry
fallback, which would otherwise leak Chapter 3000 rows into Arena -> Special
Quests. Advertised non-1000-series entries receive exact section flags rather
than one broad chapter flag: this includes Crystal Road (3004-1) in
`huntingHuntingList`. `descentHuntingList` separately folds each progress-unlocked
Counter Descent family to its tier-1 identity; login supplies only the matching
chapter flags. Detailed static evidence and local-policy labels live in
`../liminal_gate/server_constants.py` and `findings.md`.

Counter Descent starts use the ordinary `start_quest` route. The bundled policy
accepts only Chapters 8000--8007, sections 1--5, with exact stamina costs of
5/10/15/15/15. A successful entry commits the debit and active stage together;
retry or restart cannot debit it again. `clear_quest` requires unchanged
progress, roster, inventory, Summons, and a zero base reward because no
server-authored reward was recovered. This is preservation policy, not a claim
about historical event schedules or rewards.

The bundled Special Quest uses that same Hunting transaction: Chapter 3003-1
charges 5 stamina, accepts no EXP, items, or Companions, and has a local 1,500
Coin ceiling. Start, clear, refusal, replay, and restart behavior are therefore
identical to the bounded Hunting lifecycle. Its permanent availability and
Coin ceiling are local policy; only the stage identity, entry cost, and client
visibility flag are recovered.

Crystal Road (3004-1) is another bounded Hunting transaction. The supplied
final APK identifies its three-battle, seven-stamina entry and the mode-7
selector requires its exact `sp_ch_3004-1` flag. The bundled local policy
accepts a maximum of two Items from the recovered material IDs 1--17 plus the
reference-backed Ticket/power-up channels (50 and 53--56); it does not roll or
claim the retired service's probabilities. Start, clear, refusal, replay, and
restart follow the same real-HTTP-tested Hunting lifecycle. Original-client
acceptance of this new row remains unverified.

## Evidence labels

- **Confirmed:** surviving-client acceptance, exact static client read, or an
  executable regression proving the stated implementation contract.
- **Strongly inferred:** multiple consistent sources without live acceptance.
- **Tentative:** an open hypothesis that must not drive a success response.
- **Local policy:** deliberate preservation behavior, not a historical-service
  claim.
