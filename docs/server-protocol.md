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
ownership exists. A UUID linked by the operator's `link` command resolves to
its shared account on both identity-bearing routes; the wire itself has no
account or transfer system. See `multi-account-design.md` for limitations.

Response signing remains token-derived according to the included compatibility
profile. Event diagnostics never record tokens, authentication digests, query
strings, account IDs, rosters, or request bodies.

## Mutation contract

Supported mutations validate the exact ordered form and relevant catalog
boundary before changing state. State and the response used for retry are
committed together. Replay identity includes operation, request ID, and body,
so the same ID with a different body is not mistaken for the earlier request.
Caches are bounded and survive restart.

The exact first tutorial Pact form (`kind=10`) selects one of two profile
outcomes with equal integer weight: Bahl (character 1) or Grace (character 3).
Selection happens only after phase and request validation. The selected starter,
roster/team mutation, canonical signed payload, and replay record commit in the
same atomic state write, so an exact retry cannot reroll and returns identical
bytes after restart. Later tutorial response and party templates resolve from
that durable starter. Older saves without the explicit field retain Grace, the
only outcome the earlier profile could produce.

The tutorial uses phase-bound structural `userdata` writes, not ordinary
free-roam roster authority. After Chapter 1-1, a restarted final client can
send the established ordered party-save structure while it resumes
`Tutorial03_start`. At `chapter1_1_cleared` the server acknowledges that write
as a same-phase no-op: client roster arrays are not applied, and only the
following `kind=12` Pact advances to `knight_granted`. The acknowledgment and
its body-scoped replay survive restart.

The equal Bahl/Grace retail rule is maintainer-supplied historical evidence.
The `kind=10` wire form and Grace response shape are client-confirmed; Bahl's
character identity is corroborated by the operator's derived character names.
Original-client Bahl navigation beyond the first result remains an acceptance
boundary rather than a confirmed public capture.

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

The guided core-story path issues the retail first-clear ticket presents through
the existing inbox transport: Metal Ticket (Item 50) x2 after Chapters 5 and 7,
and Companion Ticket (Item 112) x3/x3/x4 after Chapters 6, 8, and 10. Eligibility
requires the next chapter to be unlocked, so a player within Chapter 8 has not
yet earned its present. Login backfills any eligible missing message and commits
a separate issued-ID sentinel before returning it. Reading still performs the
inventory mutation; deleting a read message leaves the sentinel intact, so
login, retry, deletion, interruption, and restart cannot mint a second copy.
The quantities are documented retail behavior; Item IDs and inventory limits
are corroborated by the final client.

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
version, country, and selector fields. Hunting and Tower selector lists are
added per account from the enabled Hunting and event catalogs and current
progress.
`specialQuestList` merges the generated Archive Special Quest rows with the
bundled Chapter 3003-1 row whenever their gates are open. Dual-ABI
`UISpecialSelect.SetMode(0)` analysis confirms that this nonempty server list
owns the selector; the embedded 50-entry array is only its null/empty fallback.
Before any real row unlocks, a closed recovered entry suppresses that fallback,
which would otherwise leak Chapter 3000 rows into Arena -> Special Quests.
Advertised non-1000-series entries receive exact section flags rather
than one broad chapter flag: this includes Crystal Road (3004-1) in
`huntingHuntingList`. `descentHuntingList` separately folds each progress-unlocked
Counter Descent family to its tier-1 identity; login supplies only the matching
chapter flags. Detailed static evidence and local-policy labels live in
`../liminal_gate/server_constants.py` and `findings.md`.

`towerQuestList` is always present. After Chapter 3, the generated event
catalog contributes all 12 BattleData-backed identities in Chapters
9010--9013 and login supplies the matching chapter flags. Entry uses the
ordinary `start_quest` transaction with each stage's recovered stamina and
zero entry Coins; clear uses the same durable event settlement and does not
advance story progress. The permanent gate and zero fixed clear Coins are
local policy. This is a solo adapter, not a recreation of the original shared
HP and staged achievement state. Donation Chapters 9100--9102 remain disabled
because their community aggregate and reward state are unrecovered.
Physical-client Tower navigation and first-stage battle loading are
operator-confirmed. A preserved transport trace and the clear/result return
remain unverified.

`eidolonQuestList` is likewise always present. After Chapter 3, it advertises
the 12 Chapter-4100--4111 sections that have both a nonzero BattleData battle
count and a matching final-client banner. Sixteen zero-battle tier placeholders
are excluded. The clear request's `summonList` is the pre-result-screen 16-slot
raw-data vector. A reviewed explicit catalog may bound a reported `summons`
entry to one previously unowned Summon; a grant is persisted as raw
value `1`, matching `UserData.AddSummon(id)` constructing
`SummonInfo(id, 1, 0)`. The response intentionally omits `summonList`: the
client's clear callback does not read it, and `ShowSummonGet` adds the drop
locally. Invalid, duplicate, unlisted, or already-owned reports are refused
before mutation. The generated catalog currently declares no solo Eidolon
acquisition ceiling because the older Co-op drop records do not establish the
banner-backed solo result. Exact accepted replays remain stable after restart.

Counter Descent starts use the ordinary `start_quest` route. The bundled policy
accepts Chapters 8000--8007, sections 1--5, at 5/10/15/15/15 stamina and
Chapters 8012--8017, sections 1--3, at 5/10/15 stamina. It explicitly excludes
Little Noah 8008--8011 and Hime Rush 8018 because their distinct contracts are
unrecovered. A successful entry commits the debit and active stage together;
retry or restart cannot debit it again. `clear_quest` requires unchanged
progress, roster, inventory, Summons, and a zero base reward because no
server-authored reward was recovered. This is preservation policy, not a claim
about historical event schedules or rewards.

Guided setup also composes 42 curated Archive Special Quests across Chapters
2000--2011 and 2014--2018 from the tester's own BattleData and character
catalog. Their section economics, flags, and folded or explicit selector
identities are client-derived. Permanent story gates, zero fixed clear-Coin
increments, and granting associated characters on the first section are local
archive policy. Event
clear reconciles the wallet as durable Coins plus that fixed increment plus the
client-reported battle Coins. The exact Jade Dragon 2004-1 form establishes
that variable channel and the `itmp0=-1` sentinel; lower sentinels and wallet
conflicts are refused without mutation. The original client received HTTP 200,
left the result screen, and the settled state survived restart. Other Archive
families still require their own client-clear observations.

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
