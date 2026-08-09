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
- Three routes the client still calls are refused in the *endpoint's* namespace
  rather than the transport's: `buy_energy`, `showed_ad_movie_main`, and
  `showed_ad_movie_continue`. Each answers a signed body whose refusal code
  rides `cmdError`, so the screen that asked runs its own callback. They are
  refusals, not implementations — no energy is granted, no receipt inspected,
  and no durable state touched. Answering them as unknown routes instead would
  send an unsigned body the client reads as a transport failure and retries
  against the same dead route, which is a loop only a force-stop escapes.

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

Guided core-story login includes `eventFlags.enableDailyBonus` as a nested
boolean event record. This is only the recovered server-owned gate. The final
client derives the current ordinary-story item/monster bonus from its
server-corrected instant, device-local calendar date, and chapter number. Its
native 15-day rotation doubles item drops or monster recruits on the matching
days and leaves Companion and Battle Summon drops unchanged. Keeping the gate
continuously enabled is explicit preservation policy; no historical service
event start/end window is claimed. The login flag is read-only and changes no
durable account or replay state.

## Mutation contract

Supported mutations validate the exact ordered form and relevant catalog
boundary before changing state. State and the response used for retry are
committed together. Replay identity includes operation, request ID, and body,
so the same ID with a different body is not mistaken for the earlier request.
Caches are bounded and survive restart.

Every signed body carries `success`. The transport casts `json["success"]` to
bool with no `Contains` guard, and LitJson raises on both a missing key and a
non-boolean, so an omitted verdict is not read as failure: it throws inside the
transport coroutine, after the mutation has been settled and answered. No
endpoint callback runs and no dialog appears — the screen simply keeps whatever
loading overlay it raised, which only a restart clears. A payload that carries
no verdict of its own is therefore stamped with the one it was returned under,
in the wire layer rather than at each route. An endpoint's own refusal code
still rides `cmdError`; see the `errorCode` note below.

The exact first tutorial Pact form (`kind=10`) selects one of two profile
outcomes with equal integer weight: Bahl (character 1) or Grace (character 3).
Selection happens only after phase and request validation. The selected starter,
roster/team mutation, canonical signed payload, and replay record commit in the
same atomic state write, so an exact retry cannot reroll and returns identical
bytes after restart. Later tutorial response and party templates resolve from
that durable starter. Older saves without the explicit field retain Grace, the
only outcome the earlier profile could produce.

A start carries `helpItemID` only when the player picked a Power-Up Item from
the pre-battle slot, which the `helpItemEnabled` constant opens. The client
omits the field rather than sending zero, and emits it in one fixed position in
each start form: after `coins` in the ordinary form, after `itemCount` in the
Metal Zone ticket form. Both forms are accepted with and without it; the field
elsewhere, or declaring zero, is not a form the client produces. The named item
must be one of the eight the client's own master data marks HelpItem kind (53,
54, 55, 56, 166, 167, 172, 180) — anything else is refused as an unsupported
form, since the selector cannot offer it — and one not held gets the soft
`cmdError` 2 shape. The server owns the spend: it debits one at accepted entry
and returns the resulting `itemList` with the start, which the client loads
over its whole inventory. Starts without a power-up return no `itemList` at
all. Chapter-1100 world-map specials refuse the field outright, matching the
client's own `InWMSpecial` gate.

The tutorial uses phase-bound structural `userdata` writes, not ordinary
free-roam roster authority. After Chapter 1-1, a restarted final client can
send the established ordered party-save structure while it resumes
`Tutorial03_start`. At `chapter1_1_cleared` the server acknowledges that write
as a same-phase no-op: client roster arrays are not applied, and only the
following `kind=12` Pact advances to `knight_granted`. The acknowledgment and
its body-scoped replay survive restart.

Battle-clear character rows treat job experience, Skill Boost, and Luck as
monotonic state. The final client is confirmed to omit the optional `luck`
member from a valid clear even after receiving a nonzero `luckUpTable`, so an
omission or lower stale value cannot erase the durable field. The server merges
the greater durable/reported value first, applies its cached battle-start Luck
gain afterward, and commits the roster plus replay response in the existing
atomic clear transaction. Exact retry and restart therefore cannot apply the
gain twice. Other row fields remain client-authoritative where their dedicated
mutations permit movement in either direction.

The equal Bahl/Grace retail rule is maintainer-supplied historical evidence.
The `kind=10` wire form and Grace response shape are client-confirmed; Bahl's
character identity is corroborated by the operator's derived character names.
Original-client Bahl navigation beyond the first result remains an acceptance
boundary rather than a confirmed public capture.

The permanent Fellowship Ticket form is
`kind=20&count=<1..10>&luckType=<false|true>&campaignChrID=0&eventFlag=0&lastUpdate=<n>`.
Item 81 pays for the existing Fellowship pool: ordinary draws use the local
Skill Boost duplicate policy, while `luckType=true` uses the Fellowship-side
Fate Luck policy. A successful transaction consumes exactly one ticket per
result, returns the post-spend `itemList`, and does not charge Coins or Energy.
The ticket is not a one-at-a-time form: `UIBarSlot` wires its ten-pull control
to `SlotKind.NormalItem` too, and `InitChrMenu` sizes that batch from the held
Item 81 count, so a player holding three tickets posts `count=3`. A batch
larger than the tickets still held is refused whole rather than part-paid. A
Fellowship-side coin draw is refused while a ticket remains because no mixed
ticket/coin batch has been recovered. Missing-ticket error 2 is compatibility
policy pending a live refusal capture. Nonzero campaign/event selectors remain
unsupported.

`do_buddy_slot` carries the same four payment variants for Companions, in the
one form `kind=<0|1|20|21>&count=<n>&campaignID=0&eventFlag=0&lastUpdate=<n>`.
`SlotKind.Normal` (0) draws the 81 normal-slot Companions for
`NormalBuddySlotCoins`, and `NormalItem` (20) is that pull paid with the same
Item 81 Fellowship Ticket the character page spends -- one ticket per result.
`Rare` (1) draws the 114 rare-slot Companions for `RareBuddySlotEnergy`, and
`BuddyItem` (21) is that pull paid with Item 112. Either pull spends its own
ticket ahead of its currency when the player holds enough, and a shortfall is
answered with the pool's own `DoBuddySlotErrorCode`: NotEnoughCoins (2) for the
normal pool, NotEnoughEnergy (1) for the rare one. A user-supplied
`--companion-draw-catalog` describes only the rare pool, so under one the two
normal-pool kinds stay unsupported rather than drawing from the wrong pool.

The guided core-story path settles the retail first-clear ticket rewards
directly: Metal Ticket (Item 50) x2 after Chapters 5 and 7, and Companion Ticket
(Item 112) x3/x3/x4 after Chapters 6, 8, and 10. Eligibility requires the next
chapter to be unlocked, so a player within Chapter 8 has not yet earned its
reward. Login commits inventory and the issued-ID/read ledger before returning.
Issue 33 showed that the final client could display the previous milestone mail
without rendering or clearing its reward, so direct settlement is explicit
compatibility policy, not a recovered service transport claim. An unread legacy
milestone is granted once and marked read; a read or deleted milestone is never
granted again across retry or restart. The quantities are documented retail
behavior; Item IDs and inventory limits are corroborated by the final client.

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

Every settled clear stamps `userdata.questClearDate` with
`"<chapter>-<section>"` and the settlement instant, as a decimal, and restates
the whole map in its response. This is the record chained event sections are
unlocked from: `UISpecialSelect.IsQuestOpen` drops a section from the list it
builds unless BattleData's `parentQuest` for that section has a nonzero clear
date, so without it Melting Pot, Tower, and every other chained chapter stay
one section long. The value must be a decimal, not a whole number: the client
reads it with LitJson's double accessor, which raises rather than converting.
Clears settled before this map existed are not reconstructed.

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
`huntingHuntingList`. `descentHuntingList` separately advertises each
progress-unlocked Counter Descent family as its bare chapter, because
`UISpecialSelect.IsFolded` is `!id.Contains("-")` and only a section-less id
opens as a card; login supplies one `sp_ch_<chapter>-<section>` flag per
declared tier and deliberately no chapter flag, because `CheckQuestFlag`
retries an unset section key as its chapter and the client offers five tiers
for every family whether or not five exist. Detailed
static evidence and local-policy labels live in
`../liminal_gate/server_constants.py` and `findings.md`.

`statusUpItems` is present only while a status-up policy is loaded, and is that
policy projected into the client's own shape: one `"<itemID>"` key per item
holding `[levels, skillBoostPercent, luckPercent, species]`, species zero
meaning no gate. It is not display data. `UIChrSelectWindow.CalcMaxUseNum`
looks the selected item up here before reading any character state, so an
absent block empties the item-use character list and reports that no character
can take the item. All four values are required because the advertised client
version puts `IsStatusUpItemsDesignatedSpeciesImplemented` past its 4.99
threshold, and each is read as an integer.

`towerQuestList` is always present. After Chapter 3, the generated event
catalog contributes all 12 BattleData-backed identities in Chapters
9010--9013 and login supplies the matching chapter flags. Entry uses the
ordinary `start_quest` transaction with each stage's recovered stamina and
zero entry Coins; clear uses the same durable event settlement and does not
advance story progress. The permanent gate and zero fixed clear Coins are
local policy. This is a solo adapter, not a recreation of the original shared
HP and staged achievement state. Chapters 9100--9102 sit in the range the
client files under Donation and are Melting Pot; they are generated and
advertised like any other local event, and only their unrecovered community
aggregate stays out. See `findings.md`, 2026-08-07.
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
retry or restart cannot debit it again. `clear_quest` requires unchanged progress
and Summons, and because no server-authored reward table was recovered it settles
the rewards the client itself reports: the submitted inventory must be the
durable counts plus exactly the drops `battle_result` declares, capped at the
client's stack ceiling, and the experience, Coins, Skill Boost, monsters, and
Lucky enemies it reports are kept through the same merge every other event clear
uses. A reported Summon is refused. This is preservation policy, not a claim
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
charges 5 stamina and retains the Issue 25 final-client 1,800-Coin observation
as audit data, not as the default acceptance ceiling. Start, clear, structural
refusal, replay, and restart behavior are identical to the Hunting lifecycle.
Permanent availability remains local policy; only the stage identity, entry
cost, visibility flag, and observed 1,800-Coin result are client-backed.

Crystal Road (3004-1) is another Hunting transaction. The supplied
final APK identifies its three-battle, seven-stamina entry and the mode-7
selector requires its exact `sp_ch_3004-1` flag. The bundled local policy
records two Items from the recovered material IDs 1--17 plus the
reference-backed Ticket/power-up channels (50 and 53--56); it does not roll or
claim the retired service's probabilities. A Pixel 7 Pro original-client clear
reported 280 Coins and 5,400/5,625 EXP, proving the former zero placeholders
were not compatibility bounds. Default settlement now trusts such a
structurally consistent active-battle result; `--outcome-strict` retains the
catalog ceilings as an operator audit. Exact replay and restart grant the
reported Coins once.

## Evidence labels

- **Confirmed:** surviving-client acceptance, exact static client read, or an
  executable regression proving the stated implementation contract.
- **Strongly inferred:** multiple consistent sources without live acceptance.
- **Tentative:** an open hypothesis that must not drive a success response.
- **Local policy:** deliberate preservation behavior, not a historical-service
  claim.
