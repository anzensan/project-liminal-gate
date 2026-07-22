# Compatibility Scope

## Included account-bootstrap slice

The bundled `profiles/legacy-client-bootstrap.json` deliberately implements
only this bootstrap and initial-account boundary:

| Operation | Method and path | Accepted request boundary | Successful response boundary |
| --- | --- | --- | --- |
| Time synchronization | `GET /gd/get_current_time` | Requires a nonempty `otk`; other query fields are accepted but not retained. | Signed JSON with `success: true` and a floating-point Unix-seconds `timestamp`. |
| Server status | `GET /gd/get_server_status` | Requires a nonempty `otk`; client request fields such as platform/version may be present. | Signed JSON with `success: true`; optional status payloads are intentionally absent. |
| Account creation | `GET /gd/signup` | Requires nonempty `uuid` and `otk`; other client query fields are accepted but not retained. Repeating the request preserves the same local account. | Signed JSON with `success: true` and `id` equal to the supplied UUID. |
| Title login | `GET /gd/login` | Requires a locally created `uuid` and nonempty `otk`; other client query fields are accepted but not retained. | Signed JSON with the required identity/friend fields and an inert `weeklyChallenge` object. |
| Initial userdata | `GET /gd/userdata` | Requires an `otk` bound by signup or login. | Signed JSON with nonzero floating-point `lastupdate`, empty `chrdata`, and empty `teamMembers`. |
| Resume userdata refresh | `GET /gd/userdata_after_close` | Requires an `otk` bound by signup or login. | Signed authoritative local userdata projection, identical in shape to ordinary userdata. |
| Local multiplayer capability | `GET /gd/multiplay_enable` | Requires nonempty `otk`. | Signed `success:true`, `enable:false`, `enablemain:false`; multiplayer is explicitly unavailable locally. |
| Special-event parameters | `GET /gd/get_special_event_param` | Requires nonempty `otk`. | Signed `success:true` with no event rows, representing no active live events. |
| Tutorial summon 1 | `POST /gd/do_slot` | Requires the exact `kind=10` form and a new request ID after initial userdata. | Signed deterministic Grace result, local team `[3]`, and durable character state. |
| Tutorial summon 2 | `POST /gd/do_slot` | Requires the exact `kind=11` form and a new request ID after tutorial summon 1. | Signed deterministic A'misandra level-15 result, local team `[3, 25]`, and durable character state. |
| Tutorial state write | `POST /gd/userdata` | Requires the exact ordered ten-field form and a new request ID after tutorial summon 2. Equivalent URL escaping is accepted only when it decodes to the same field sequence. | Signed `lastupdate: 1.0`; atomically records the Chapter 1 transition state. |
| Map-reveal write | `POST /gd/userdata` | Requires the exact three-field form and a new request ID after the tutorial state write. | Signed `lastupdate: 1.0`; atomically records Chapter 1 map progress `16777281`. |
| Chapter 1-1 start | `POST /gd/start_quest` | Requires the exact five-field Chapter 1-1 form and a new request ID after the map-reveal write. | Signed `success: true` and JSON-double `refillStartTime: 0.0`; atomically records the active battle phase. |
| Chapter 1-1 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field clear grammar and a new request ID after the Chapter 1-1 start. Structured client-state fields must decode as their observed JSON types. | Signed `success: true` and JSON-double `lastupdate: 1.0`; atomically records Chapter 1-1 completion/progress and the reviewed local coin result. |
| Tavern Tutorial02 | `POST /gd/do_slot` | Requires the exact `kind=12` form and a new request ID after Chapter 1-1 clear. | Signed deterministic Knight level-10 result and durable local character state. |
| Knight state write | `POST /gd/userdata` | Requires ordered `chrdata`, `lastUpdate=1` after Tutorial02; `chrdata` must decode as JSON array. | Signed `lastupdate: 1.0`; atomically records the acknowledgement without importing client character state. |
| Knight party write | `POST /gd/userdata` | Requires the confirmed ordered eight-field party grammar after the Knight state write; structured fields must decode as JSON arrays. | Signed `lastupdate: 1.0`; atomically records local team `[3, 25, 64, 0, 0, 0]`. |
| Chapter 1-2 start | `POST /gd/start_quest` | Requires the exact five-field section-2 form after Knight party formation. | Signed `success: true` and JSON-double `refillStartTime: 0.0`; atomically records the active battle phase. |
| Chapter 1-2 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field clear grammar after Chapter 1-2 start. | Signed full roster replacement, `lastupdate: 1.0`, and `sentMessage: false`; atomically records Warrior/progress. |
| Warrior party write | `POST /gd/userdata` | Requires the confirmed ordered eight-field party grammar after Warrior grant. | Signed `lastupdate: 1.0`; atomically records local team `[3,25,64,63,0,0]`. |
| Chapter 1-3 start | `POST /gd/start_quest` | Requires the exact five-field section-3 form after Warrior party formation. | Signed `success: true` and JSON-double `refillStartTime: 0.0`; atomically records active battle phase. |
| Chapter 1-3 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field clear grammar after Chapter 1-3 start. | Signed `lastupdate: 1.0` and `sentMessage: false`; atomically records reviewed progress/coins. |
| Chapter 1-4 start/clear | `POST /gd/start_quest`, `POST /gd/clear_quest` | Exact five-field section-4 start followed by confirmed structural clear grammar. | Minimal signed start callback; clear records progress `16777285`, coins, and `sentMessage:false`. |
| Chapter 1-5 start/clear | `POST /gd/start_quest`, `POST /gd/clear_quest` | Exact five-field section-5 start followed by confirmed structural clear grammar. | Minimal signed start callback; clear records progress `50331777`, coins, and `sentMessage:false`. |
| Final tutorial map write | `POST /gd/userdata` | Requires exact `progressCode=16777345`, `worldMapNo=0`, `lastUpdate=1` after Chapter 1-5 clear. | Signed `lastupdate: 1.0`; atomically records free-roam progress. |
| Chapter 2-1 start | `POST /gd/start_quest` | Requires exact five-field Chapter 2 section-1 form after free-roam unlock. | Signed `success: true` and JSON-double `refillStartTime: 0.0`; atomically records active battle phase. |
| Chapter 2-1 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field Chapter 2 section-1 clear grammar. | Signed `lastupdate: 1.0` and `sentMessage:false`; atomically records reviewed progress/coins. |
| Derived Chapter 2--42 story | `POST /gd/start_quest`, `POST /gd/clear_quest` | Requires `--story-progression-catalog`, an ordered locally derived stage, the exact generic form, and a new request ID. Skipped stages are rejected; cleared stages may replay without regressing progress. | Signed start/clear callbacks; commits computed packed progress and the trusted-local reported battle-coin delta with replay/collision/restart protection. |
| Derived chapter map reveal | `POST /gd/userdata` | Requires `--story-progression-catalog`, a pending derived chapter-boundary flag, and exact ordered `progressCode`, `worldMapNo`, `lastUpdate` form. | Signed `success:true,lastupdate:1.0`; atomically clears the one-shot reveal bit with replay/collision/restart protection. |
| Generic-story Continue | `POST /gd/continue` | Requires an active catalog-declared generic story battle, a new request ID, and exact `cost=1` (optional trailing `lastUpdate`). | Signed `success:true`, integer `energy`, and integer `freeEnergy`; atomically debits the profile-declared 100 local coins. |
| Stamina refill | `POST /gd/refill_stamina` | Requires a new request ID and exact one-field `cost=1`. A local account needs refill only when `userdata.refillStartTime` is nonzero. | Signed full callback (`refillStartTime`, four Energy projections, `freeEnergy`, `bonusStamina`) or signed `success:false,errorCode:1|2`; commits/replays atomically. |
| Timed Metal Zone opening | `POST /gd/unlock_metal_zone` | Requires a new request ID and the recovered empty POST body. | Signed local `metalZoneUnlockTime` JSON-double plus five Energy projections, or signed `success:false,errorCode:2`; commits/replays atomically. One-hour duration/all-zone scope are local preservation policy. |
| Catalog-gated achievement claim | `POST /gd/achived` | Requires `--achievement-catalog`, a new request ID, and exact ordered `id`, `lastUpdate=1` fields. Stored local progress must exceed the operator-declared chapter threshold; each local ID is one-shot. | Signed local `achivementFlags`, free Energy, coins, and item projection; commits/replays atomically. Unknown/ineligible claims deliberately return `409 invalid_local_achievement`. |
| Catalog-gated inbox lifecycle | Login `messageList`; `POST /gd/read_messages`, `POST /gd/delete_messages` | Requires `--message-catalog`; Login uses recovered nested 13-key messages. Mutations require unique JSON `idlist` and optional nonnegative trailing `lastUpdate`. | Read returns the complete client-required local reload projection and commits local rewards once; delete removes only read entries. Both commit/replay atomically. Gifts, character/summon/title/Companion rewards remain unsupported. |
| Catalog-gated Trading Post | `GET /gd/get_current_exchange`; `POST /gd/exchange` | Requires `--exchange-catalog`; nested offer containers, strict ordered offer/amount form, and optional trailing nonnegative `lastUpdate`. | Signed nested offer projection; bounded local item settlement with stock, collision, and restart replay. Companion offers and `add_exchange_count` deliberately fail. |
| Status-up item | `POST /gd/use_statusup_item` | Requires `--statusup-catalog`, a new request ID, and exact ordered decimal `targetChrID`, `useItemID`, `useAmount` fields. | Signed authoritative local `chrdata`, `itemList`, `resultValues`, or signed `success:false,errorCode:1..4`; commits/replays atomically. |
| Job unlock | `POST /gd/add_job` | Requires `--job-catalog`, a new request ID, `targetID`, and the confirmed optional tutorial/trailing-update fields. | Signed `success:true` with changed local `chrdata`, `itemList`, coins, optional Energy, or endpoint-specific `cmdError:2..4`; commits/replays atomically. |
| Rebirth | `POST /gd/rebirth` | Requires `--rebirth-catalog`, a new request ID, and exact ordered `rebirthID`, capitalized `useJoker` fields. | Signed changed local roster/item/coin projection or signed `success:false,errorCode:1..7`; commits/replays atomically. |
| Battle Summon skill unlock | `POST /gd/summon_skill_unlock` | Requires `--summon-skill-catalog`, a new request ID, and exact decimal `targetID=1..16`. | Signed `success:true`, changed local `itemList`/`summonList`, and integer `coins`; or signed `success:false,errorCode:1..3`; commits/replays atomically. |
| Companion sale | `POST /gd/sell_buddy`, `POST /gd/sell_buddies` | Requires `--companion-catalog`, a new request ID, exact `inventoryID` or unique `sellList` of existing local owned-instance IDs. | Signed changed local `buddyInfo`/`chrdata`/coins or signed `success:false,errorCode:2`; commits/replays atomically. |
| Companion strengthen | `POST /gd/buddy_strengthen` | Requires `--companion-strengthen-catalog`, a new request ID, exact `baseID` and unique one-to-four entry `matList` of existing local owned-instance IDs. | Signed changed local `buddyInfo`/`chrdata`/coins plus `totalEXP`, `additionalEXP`, `expBonus`; or signed `success:false,errorCode:2..6`; commits/replays atomically. |
| Companion evolution | `POST /gd/buddy_evolve` | Requires `--companion-evolution-catalog`, a new request ID, exact decimal `baseID` with optional trailing `lastUpdate=1`. | Signed changed local `buddyInfo`/`chrdata`/itemList/coins or signed `success:false,errorCode:1..5`; commits/replays atomically. |
| Companion draw | `POST /gd/do_buddy_slot` | Requires `--companion-draw-catalog`, a new request ID, exact `kind`, `count`, `campaignID=0`, `eventFlag=0`, `lastUpdate` form. | Signed local currency/item/`buddyInfo` projection and level-1 `result` entries, or signed `success:false,errorCode:1|4`; commits/replays atomically. |
| Ordinary Pact draw | `POST /gd/do_slot` (`kind=0`) | Requires `--pact-draw-catalog`, a new request ID, and exact normal one/ten form. Operator supplies all pool IDs, weights, prices, and duplicate policy. | Signed local coin/energy projection and `chrdata` results, or signed `success:false,errorCode:2|3`; commits/replays atomically. Ticket/campaign variants are deliberately unsupported. |
| Catalog-bounded generic story outcomes | `POST /gd/clear_quest` | Requires a declared generic stage and `--story-outcome-catalog`; optional `--clear-state-catalog` additionally derives saved-party EXP/level/Skill-Boost deltas, preserves immutable fields, requires a confirmed baseline for new configured characters, and derives configured duplicate Skill-Boosts. Reported item/character/Companion outcome must remain within operator-declared maxima. | Signed local clear projection plus authoritative `buddyInfo`, or `409 invalid_local_outcome` / `invalid_local_clear_state`; commits/replays atomically. This validates client-reported outcomes and does not generate drop rolls. |
| Companion inventory write | `POST /gd/userdata` | Requires a new request ID and exact `buddyInfo=<JSON array>&lastUpdate=<nonnegative>` delta of existing local owned instances. | Signed `success:true,lastupdate:1.0`; atomically persists permitted local flags and replays across restart. |

The raw JSON response, including its whitespace and final newline, is signed.
The timestamp is emitted as a JSON floating-point value because this client
boundary requires a floating-point JSON token.

This is a narrow compatibility claim. It does not include game-data import,
resource mapping, later mutations, APK patching, or a claim of full-client
playability. Routes outside the table return `501` until their own source,
state, and transport reviews are complete.

## Run it locally

```sh
liminal-gate-bootstrap-server \
  --profile profiles/legacy-client-bootstrap.json \
  --state-file user-data/bootstrap-state.json
```

For an operator-owned multi-catalog installation, the launcher may instead use
one strict user-local TOML file via
`liminal-gate-bootstrap-server --config /path/to/server.toml`. It only resolves
the listed local paths and launch settings; no profile, catalog, resource, APK,
or acquisition information is bundled by this convenience layer.

The state file is atomically updated when an account is created or a login token
is bound. It also atomically commits each declared mutation/result and its
request-ID/body-hash cache. An identical retry replays the stored result; reuse
of the same request ID with a different body is rejected. The file is not a
session or cookie store.

## Evidence labels

- Route names, method, status request order, minimal response shape, and the
  floating-point timestamp requirement: confirmed against the surviving client.
- The signup → login → userdata transport progression and minimal accepted
  response types: confirmed for the supported initial-account boundary.
- The exact tutorial summon forms, result types, and client acceptance:
  confirmed. The scripted Grace/A'misandra selection is local preservation
  policy, not a claim about historical production reward selection.
- The exact map-reveal form, progress transition, and client acceptance:
  confirmed.
- The exact Chapter 1-1 start form, minimal response types, and client
  acceptance: confirmed. The profile records only that a battle is active; it
  does not reconstruct stamina, currency, battle data, or settlement.
- `userdata_after_close` is confirmed GET-only and returns the same persisted
  local projection as userdata. `multiplay_enable` requires the two explicit
  false booleans; `get_special_event_param` accepts the signed success-only
  inert envelope. These routes introduce no matchmaking or live-event claim.
- The Chapter 1-1 clear field order, structured-field JSON types, minimal
  response types, and client acceptance: confirmed. The profile does not embed
  or import the captured client-state payload and does not treat it as authority
  for roster, inventory, or arbitrary rewards.
- The exact Tutorial02 form, Knight result shape, and client acceptance are
  confirmed. The deterministic grant is a local tutorial preservation policy,
  not an ordinary Tavern pool or historical probability claim.
- The post-recruit Knight write order, JSON-array shape, minimum callback, and
  client acceptance are confirmed. Submitted character state is not authority.
- The Continue route name, one-field request, and required integer callback
  fields are static-confirmed; a live original-client Continue capture remains
  unavailable. The active-battle guard and 100-coin debit are explicit local
  preservation policy, not recovered historic wallet behavior.
- The stamina-refill route, exact canonical `cost` form, seven successful
  callback keys, and error codes 1/2 are static-confirmed. The local
  full-meter marker and free-first wallet selection are preservation policy;
  historic recharge timing and platform-wallet billing behavior are not
  recovered.
- The status-up route's field order, item effects, caps, error enum, and
  callback field types are static-confirmed. The supplied catalog, complete
  roster projection, and request-ID cache are user-local preservation policy;
  no retired-service success body or public master-data row is included.
- The job route's field variants, sequential selection, costs, callback fields,
  and `cmdError` delivery are confirmed. User-provided costs, roster/inventory,
  full callback policy, and request cache remain local preservation policy.
- The Rebirth route's ordered request, semantic gate family, and callback
  projection are static-confirmed. User-provided recipes, material/Joker
  treatment, destination projection, and request cache remain local
  preservation policy; no retired-service settlement body or original-client
  Rebirth run is claimed.
- The Battle Summon skill route's exact one-field form, error enum, low-byte
  skill-level update, Checked-bit preservation, and callback fields are
  confirmed. User-provided job rows, material costs, account projection, and
  request cache remain local preservation policy; no funded original-client
  unlock is claimed.
- Companion-sale route names/forms, Favorite rejection, per-level coin return,
  and full callback projection are confirmed. User-provided master sale values,
  owned-instance state, and coin cap remain local preservation policy; no
  acquisition or original-client sale run is claimed.
- The Companion-strengthen route form, material limit, error family, cost,
  same-ID/ByeBye EXP rules, and callback fields are confirmed. User-provided
  master curves and bonus-weight policy remain local; no retired-service bonus
  odds or funded original-client strengthen run is claimed.
- The Companion-evolution route form, optional trailing update field, target,
  level/cost/item/Favorite gates, in-place reset, and callback fields are
  confirmed. User-provided evolution rows, costs, and duplicate policy remain
  local preservation policy; no funded original-client evolution run is claimed.
- The Companion-draw route forms, ticket-first local spend, capacity/error
  family, owned-instance response, and client acceptance are confirmed.
  User-provided draw pools, costs, ticket IDs, and capacity remain local policy;
  no historic pool or acquisition schedule is bundled.
- The post-draw Companion userdata write's exact field order, delta semantics,
  identity/authority checks, and callback are confirmed. The public server
  permits only the reviewed local flag update; equipment synchronization remains
  a separate boundary.
- Any route not listed above: unsupported, not inferred.
