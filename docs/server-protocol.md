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
nonempty: validated user-local event stages replace a closed recovered entry
used when no event catalog is configured. This prevents the client's fixed
50-entry fallback from leaking Chapter 3000 rows into Arena -> Special Quests.
Advertised Metal entries receive exact section flags rather than one broad
chapter flag. `descentHuntingList` separately folds each progress-unlocked
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

## Evidence labels

- **Confirmed:** surviving-client acceptance, exact static client read, or an
  executable regression proving the stated implementation contract.
- **Strongly inferred:** multiple consistent sources without live acceptance.
- **Tentative:** an open hypothesis that must not drive a success response.
- **Local policy:** deliberate preservation behavior, not a historical-service
  claim.
