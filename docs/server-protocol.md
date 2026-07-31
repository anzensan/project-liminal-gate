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

The tutorial uses phase-bound structural `userdata` writes, not ordinary
free-roam roster authority. After Chapter 1-1, a restarted final client can
send the established ordered party-save structure while it resumes
`Tutorial03_start`. At `chapter1_1_cleared` the server acknowledges that write
as a same-phase no-op: client roster arrays are not applied, and only the
following `kind=12` Pact advances to `knight_granted`. The acknowledgment and
its body-scoped replay survive restart.

The permanent Fellowship Ticket form is
`kind=20&count=1&luckType=<false|true>&campaignChrID=0&eventFlag=0&lastUpdate=1`.
Item 81 pays for the existing Fellowship pool: ordinary draws use the local
Skill Boost duplicate policy, while `luckType=true` uses the Fellowship-side
Fate Luck policy. A successful transaction consumes exactly one ticket,
returns the post-spend `itemList`, and does not charge Coins or Energy. A
Fellowship-side coin draw is refused while a ticket remains because no mixed
ticket/coin batch has been recovered. Missing-ticket error 2 is compatibility
policy pending a live refusal capture. Nonzero campaign/event selectors remain
unsupported.

Combined Companion equip writes use the exact ordered
`chrdata`, `buddyInfo`, `lastUpdate` form. Both values are dirty-record arrays,
projected over the server-owned roster and Companion inventory before mutation.
Every nonzero character `buddy` inventory ID must point to an owned Companion
whose `chrID` points back to that character, and one Companion cannot be linked
to multiple characters. A mismatched or one-sided move changes neither half.
Standalone `buddyInfo`, `lastUpdate` writes may change the recovered
seen/favorite flags but cannot retarget `chrID`. A newly equipped or retargeted
link also requires the generated, APK-hashed Companion equipment catalog. An
`exclusiveChrID` accepts the direct character or its recovered nonzero
ancestor; `exclusiveSpeciesID` must match the active job's species. Unknown
masters and a missing catalog are refused without changing either half.
Existing links and unequip remain available without the catalog. The server
does not apply `RequiredLevel` as an equip restriction: final-client
`Buddy.CanEquip` does not read it, and the client instead uses that field to
activate the effects of a Companion that is already equipped.

`summon_skill_unlock` is a recovered archival transport with a bounded local
material-cost policy. It does not imply a required or reachable final-version
solo feature: Version 5.5.0 discontinued Tavern Eidolon enhancement along with
Co-op/VS and in-battle Eidolon use. Final 5.5.7 solo coverage instead has a
separate optional gap in Chapters 4100--4111, whose former Co-op quests were
converted to single-player and award collectible Eidolons through a distinct
result path. That quest/acquisition path remains unsupported until its selector
and before/after ownership mapping are captured; the server does not fabricate
them from the legacy skill-cost table. Guided setup leaves the legacy route
disabled, as does the server-only launcher; an operator must select its
archival option explicitly.

Ticket-backed Metal starts commit Item 50 at entry and retain that payment
choice. The final client repeats its pre-entry ticket count in the later clear;
only that one stale slot is reconciled, and the server-owned lower balance is
returned. Stamina fallback and every other inventory slot remain exact.

## Server constants

`get_server_status` returns the complete required constants object. A partial
object is not served because client setters directly index required economy,
version, and country fields. Hunting selector lists are added per account from
the enabled Hunting and event catalogs and current progress.
`specialQuestList` merges the generated Archive Special Quest rows with the
bundled Chapter 3003-1 row whenever their gates are open. Before any real row
unlocks, a closed recovered entry suppresses the client's fixed 50-entry
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

Guided setup also composes Archive Special Quests for recovered Chapters 2000,
2001, 2002, 2004, and 2006 from the tester's own BattleData and character
catalog. Their section economics and flags are client-derived. Permanent
Chapter 2/4/10/13/20 unlocks, zero clear Coins, and granting the associated
character on the first section are local archive policy. The same generic
quest transaction provides body-scoped replay and restart persistence; no
original-client archive clear is claimed yet.

The bundled Special Quest uses that same Hunting transaction: Chapter 3003-1
charges 5 stamina, accepts no EXP, items, or Companions, and has a local 1,800
Coin ceiling. That ceiling is compatibility-bounded by an Issue 25 final-client
clear, not by a recovered historical reward table. Start, clear, refusal,
replay, and restart behavior are otherwise identical to the bounded Hunting
lifecycle. Permanent availability remains local policy; only the stage
identity, entry cost, visibility flag, and observed 1,800-Coin result are
client-backed.

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
