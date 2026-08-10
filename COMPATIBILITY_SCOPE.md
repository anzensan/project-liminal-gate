# Compatibility Scope

## Included account-bootstrap slice

The bundled `profiles/legacy-client-bootstrap.json` deliberately implements
only this bootstrap and initial-account boundary:

| Operation | Method and path | Accepted request boundary | Successful response boundary |
| --- | --- | --- | --- |
| Time synchronization | `GET /gd/get_current_time` | Requires a nonempty `otk`; other query fields are accepted but not retained. | Signed JSON with `success: true` and a floating-point Unix-seconds `timestamp`. |
| Server status | `GET /gd/get_server_status` | Requires a nonempty `otk`; client request fields such as platform/version may be present. | Signed JSON with `success: true`; optional status payloads are intentionally absent. |
| Account creation | `GET /gd/signup` | Requires nonempty `uuid` and `otk`; other client query fields are accepted but not retained. Repeating the request preserves the same local account. | Signed JSON with `success: true` and `id` equal to the supplied UUID. |
| Title login | `GET /gd/login` | Requires a locally created `uuid` and nonempty `otk`; other client query fields are accepted but not retained. | Signed JSON with the required identity/friend fields and an inert `weeklyChallenge` object. With `--drop-eligibility`, also the `chrBuddyData` allowlist the client requires before it will keep a rolled drop. |
| Initial userdata | `GET /gd/userdata` | Requires an `otk` bound by signup or login. | Signed JSON with nonzero floating-point `lastupdate`, empty `chrdata`, and empty `teamMembers`. |
| Resume userdata refresh | `GET /gd/userdata_after_close` | Requires an `otk` bound by signup or login. | Signed authoritative local userdata projection, identical in shape to ordinary userdata. |
| Local multiplayer capability | `GET /gd/multiplay_enable` | Requires nonempty `otk`. | Signed `success:true`, `enable:false`, `enablemain:false`; multiplayer is explicitly unavailable locally. |
| Special-event parameters | `GET /gd/get_special_event_param` | Requires nonempty `otk`. | Signed `success:true` with no event rows, representing no active live events. |
| Tutorial summon 1 | `POST /gd/do_slot` | Requires the exact `kind=10` form and request identity after initial userdata. | Signed equal-weight Bahl (ID 1) or Grace (ID 3) result. The selected starter, local team, response, and replay record commit atomically. |
| Tutorial summon 2 | `POST /gd/do_slot` | Requires the exact `kind=11` form and request identity after tutorial summon 1. | Signed deterministic A'misandra level-15 result, local team `[starter, 25]`, and durable character state. |
| Tutorial state write | `POST /gd/userdata` | Requires the exact ordered ten-field form for the selected Bahl or Grace branch and request identity after tutorial summon 2. Equivalent URL escaping is accepted only when it decodes to the same field sequence. | Signed `lastupdate: 1.0`; atomically records the Chapter 1 transition state without replacing the selected starter. |
| Map-reveal write | `POST /gd/userdata` | Requires the exact three-field form and request identity after the tutorial state write. | Signed `lastupdate: 1.0`; atomically records Chapter 1 map progress `16777281`. |
| Chapter 1-1 start | `POST /gd/start_quest` | Requires the exact five-field Chapter 1-1 form and request identity after the map-reveal write. | Signed `success: true` and JSON-double `refillStartTime: 0.0`; atomically records the active battle phase. |
| Chapter 1-1 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field clear grammar and request identity after the Chapter 1-1 start. Structured client-state fields must decode as their observed JSON types. | Signed `success: true` and JSON-double `lastupdate: 1.0`; atomically records Chapter 1-1 completion/progress and the reviewed local coin result. |
| Tavern Tutorial02 | `POST /gd/do_slot` | Requires the exact `kind=12` form and request identity after Chapter 1-1 clear. | Signed deterministic Knight level-10 result and durable local character state. |
| Knight state write | `POST /gd/userdata` | Requires ordered `chrdata`, `lastUpdate=1` after Tutorial02; `chrdata` must decode as JSON array. | Signed `lastupdate: 1.0`; atomically records the acknowledgement without importing client character state. |
| Knight party write | `POST /gd/userdata` | Requires the confirmed ordered eight-field party grammar after the Knight state write; structured fields must decode as JSON arrays. | Signed `lastupdate: 1.0`; atomically records local team `[starter, 25, 64, 0, 0, 0]`. |
| Chapter 1-2 start | `POST /gd/start_quest` | Requires the exact five-field section-2 form after Knight party formation. | Signed `success: true` and JSON-double `refillStartTime: 0.0`; atomically records the active battle phase. |
| Chapter 1-2 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field clear grammar after Chapter 1-2 start. | Signed full roster replacement, `lastupdate: 1.0`, and `sentMessage: false`; atomically records the starter's recruit/progress. The recruit completes the Circle of Carnage against the starter — Archer for Bahl, Warrior for Grace — and is the one declared by the outcome that chose that starter. |
| Recruit party write | `POST /gd/userdata` | Requires the confirmed ordered eight-field party grammar after the recruit grant. | Signed `lastupdate: 1.0`; atomically records local team `[starter,25,64,recruit,0,0]`. |
| Chapter 1-3 start | `POST /gd/start_quest` | Requires the exact five-field section-3 form after recruit party formation. | Signed `success: true` and JSON-double `refillStartTime: 0.0`; atomically records active battle phase. |
| Chapter 1-3 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field clear grammar after Chapter 1-3 start. | Signed `lastupdate: 1.0` and `sentMessage: false`; atomically records reviewed progress/coins. |
| Chapter 1-4 start/clear | `POST /gd/start_quest`, `POST /gd/clear_quest` | Exact five-field section-4 start followed by confirmed structural clear grammar. | Minimal signed start callback; clear records progress `16777285`, coins, and `sentMessage:false`. |
| Chapter 1-5 start/clear | `POST /gd/start_quest`, `POST /gd/clear_quest` | Exact five-field section-5 start followed by confirmed structural clear grammar. | Minimal signed start callback; clear records progress `50331777`, coins, and `sentMessage:false`. |
| Final tutorial map write | `POST /gd/userdata` | Requires exact `progressCode=16777345`, `worldMapNo=0`, `lastUpdate=1` after Chapter 1-5 clear. | Signed `lastupdate: 1.0`; atomically records free-roam progress. |
| Chapter 2-1 start | `POST /gd/start_quest` | Requires exact five-field Chapter 2 section-1 form after free-roam unlock. | Signed `success: true` and the account's post-spend `refillStartTime`; debits the stamina meter and atomically records active battle phase. |
| Chapter 2-1 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field Chapter 2 section-1 clear grammar. | Signed `lastupdate: 1.0` and `sentMessage:false`; atomically records reviewed progress/coins. |
| Built-in ordinary core story | `POST /gd/start_quest`, `POST /gd/clear_quest`, `POST /gd/userdata`; login `eventFlags` | Requires `--core-story`, the recovered ordered Chapter 2-42 identity sequence, normal generic forms, and in-order progression. The client provides nonnegative stamina/coin start fields and reported local clear result. Login supplies the exact `enableDailyBonus` boolean gate; the client computes the recovered 15-day item/monster x2 rotation itself. | Signed generic start/clear/map-reveal callbacks with durable ordered progress and replay/collision protection. Entry debits the stamina meter at the cost the client declares; an undeclared coin cost is charged as zero. Clears preserve monotonic Luck when the client omits or reports a stale lower value, then apply the cached authored gain once. They also pay preservation Energy and, at an ordinary chapter boundary, reset the meter to the client's full representation. Every clear reports the resulting `refillStartTime`, so the bar cannot read full over stamina the entry spent. Both rewards are local policy; this does not certify historical costs, rewards, drops, or scripted-stage outcomes. The always-enabled rotation gate is preservation policy over a client-confirmed formula. |
| Derived Chapter 2--42 story | `POST /gd/start_quest`, `POST /gd/clear_quest` | Requires `--story-progression-catalog`, an ordered locally derived stage, the exact generic form, and request identity. Skipped stages are rejected; cleared stages may replay without regressing progress. | Signed start/clear callbacks; commits computed packed progress and the trusted-local reported battle-coin delta with replay/collision/restart protection. At a chapter boundary it also resets the meter to the client's full representation as explicit local preservation policy. The clear callback reports the resulting `refillStartTime` either way. |
| Derived chapter map reveal | `POST /gd/userdata` | Requires `--story-progression-catalog`, a pending derived chapter-boundary flag, and exact ordered `progressCode`, `worldMapNo`, `lastUpdate` form. | Signed `success:true,lastupdate:1.0`; atomically clears the one-shot reveal bit with replay/collision/restart protection. |
| World Map Special Chapter 1100 start | `POST /gd/start_quest` | Requires the exact five-field generic start form naming Chapter 1100 with its recovered 25 stamina and zero coins, request identity, core progress past Chapter 34, and a battle at or below its route's frontier. No flag: the client draws both map points itself. | Signed `success:true` and the account's post-spend `refillStartTime`, or signed `success:true,cmdError:1` when the meter is short; atomically records the active battle. A retry under a fresh request ID reports the meter without charging again. |
| World Map Special Chapter 1100 clear | `POST /gd/clear_quest` | Requires the confirmed ordered ten-field clear grammar after a Chapter-1100 start, unchanged core `progressCode` and `worldMapNo`, exact reported-wallet arithmetic, experience within the recovered ceiling, and Companion authoring metadata when a Companion is reported. | Signed `success:true`, `lastupdate:1.0`, `sentMessage:false`, the entry's post-spend `refillStartTime`, and the client-reported Coin/roster/item/Summon/Companion projection; advances only that route's frontier and pays preservation Energy. Companions stay bounded by the stage's own `dropBuddies` manifest. Experience past the ceiling, and a reported Luck roll or Skill Boost gain, remain `409 invalid_local_world_map_special_result`: those are not drop channels and this server authors them elsewhere. |
| Hunting, Metal, Special, and Daily Quest settlement | `POST /gd/clear_quest` | Requires a catalog-declared stage that is the account's exact active hunt, the ordered clear form, unchanged story/world identity, exact reported-wallet arithmetic, a structurally matching item projection, and Companion authoring metadata when a Companion is reported. Per-stage reward maxima are enforced only with `--outcome-strict`. | Signed client-reported Coin/roster/item/Summon/Companion projection and the entry's post-spend `refillStartTime`; clears the active battle and commits/replays atomically. Unknown Companion rows and structurally inconsistent projections remain `409 invalid_local_hunting_result`. |
| Secondary world cursor write | `POST /gd/userdata` | Requires `--secondary-worlds`, an account past the tutorial, request identity, and the exact ordered `progressCode`, `worldMapNo`, `lastUpdate` form naming a world below the client's own count of three with `progressCode` unchanged. The client posts this when `UIMap.SetWorld` moves `UserData.worldNo`, which is this field. An open battle is deliberately no bar: a camera move is not a settlement, and refusing one is a refusal a force-closed session cannot get out of. | Signed `success:true` and `lastupdate`; atomically records the world the account is standing on, with replay/collision protection. A body that would also move story progress remains `409 tutorial_state_conflict`: that is the map-reveal route's business, and the tutorial's own final map write is told apart from a swap by exactly that test. |
| Secondary world progress | `GET /gd/userdata`; `GET /gd/get_server_status` | Requires `--secondary-worlds`. | The userdata read carries `worldProgressCode` as an object keyed by world index in decimal string form -- the shape `LoadUserdataFromJson` parses -- with world 0 derived from `progressCode` and worlds 1 and 2 held durably. The status block carries `worldMaxChapter` as an int array of internal chapter numbers indexed by world. A BreaSoul or Five Emperors clear advances only its own world's cursor, and only from at or behind that world's frontier -- a clear naming a section the world has not opened settles its rewards without moving the cursor past the sections in between. `progressCode` is unchanged by both, as the Hunting settlement path requires. A stored cursor outside the client's `Int32` range, or naming a section its world does not declare, is reseeded on load rather than sent. |
| Generic-story Continue | `POST /gd/continue` | Requires an active catalog-declared generic story battle, request identity, and exact `cost=1` (optional trailing `lastUpdate`). Deliberately unavailable during a Chapter-1100 battle, matching that chapter's own recovered notice that it cannot be continued after a game over. | Signed `success:true`, integer `energy`, and integer `freeEnergy`; atomically debits the profile-declared 100 local coins. |
| Stamina refill | `POST /gd/refill_stamina` | Requires request identity and exact one-field `cost=1`, with the client's trailing `lastUpdate` tolerated. A local account needs refill only when its derived stamina is below the chapter maximum, which without `--enable-stamina` is never. | Signed full callback (`refillStartTime`, four Energy projections, `freeEnergy`, `bonusStamina`) or signed `success:true,cmdError:1|2`; commits/replays atomically. Without `--enable-stamina` every request takes `cmdError:1` (`NoNeedToRefill`) and no Energy is spent. |
| Timed Metal Zone opening | `POST /gd/unlock_metal_zone` | Requires request identity and the recovered empty POST body. | Signed local `metalZoneUnlockTime` JSON-double plus five Energy projections, or signed `success:true,cmdError:2`; commits/replays atomically. One-hour duration/all-zone scope are local preservation policy. |
| Catalog-gated achievement claim | `POST /gd/achived` | Requires `--achievement-catalog`, request identity, and exact ordered `id`, `lastUpdate=1` fields. Stored local progress must exceed the operator-declared chapter threshold; each local ID is one-shot. | Signed local `achivementFlags`, free Energy, coins, and item projection; commits/replays atomically. Unknown/ineligible claims deliberately return `409 invalid_local_achievement`. |
| Inbox lifecycle and chapter rewards | Login `messageList`; `POST /gd/read_messages`, `POST /gd/delete_messages` | Guided `--core-story` directly settles the retail Chapter 5/7 Metal Ticket and Chapter 6/8/10 Companion Ticket rewards after each chapter is complete because Issue 33 disproved client acceptance of milestone mail. `--message-catalog` can add user-local messages. Login uses recovered nested 13-key messages. Mutations require unique JSON `idlist` and optional nonnegative trailing `lastUpdate`. | Eligible chapter rewards commit to inventory with a durable issued/read ledger before login; unread legacy milestone mail migrates to one grant, while read/deleted mail never re-grants. Other inbox reads return the complete client-required local reload projection and commit local rewards once; later login projections omit claimed entries. Character/summon/title/Companion message reward kinds remain unsupported. |
| Catalog-gated Trading Post | `GET /gd/get_current_exchange`; `POST /gd/exchange` | Requires `--exchange-catalog`; nested offer containers, strict ordered offer/amount form, and optional trailing nonnegative `lastUpdate`. | Signed nested offer projection naming the rotation's currency as `weeklyItem`; bounded local item or Companion settlement with stock and restart replay, or signed `success:true,cmdError:3|4|6` when the trade is unaffordable, over a ceiling, or out of stock. Untrusted `add_exchange_count` deliberately fails. |
| Status-up item | `POST /gd/use_statusup_item` | Requires `--statusup-catalog`, request identity, and exact ordered decimal `targetChrID`, `useItemID`, `useAmount` fields, with the client's trailing `lastUpdate` tolerated. | Signed authoritative local `chrdata`, `itemList`, `resultValues`, or signed `success:true,cmdError:1..4`; commits/replays atomically. |
| Job unlock | `POST /gd/add_job` | Requires `--job-catalog`, request identity, `targetID`, and the confirmed optional tutorial/trailing-update fields. | Signed `success:true` with changed local `chrdata`, `itemList`, coins, optional Energy, or endpoint-specific `cmdError:2..4`; commits/replays atomically. |
| Rebirth | `POST /gd/rebirth` | Requires `--rebirth-catalog`, request identity, and exact ordered `rebirthID`, capitalized `useJoker` fields, with the client's trailing `lastUpdate` tolerated. | Signed changed local roster/item/coin projection or signed `success:true,cmdError:1..7`; commits/replays atomically. |
| Battle Summon skill unlock | `POST /gd/summon_skill_unlock` | Requires `--summon-skill-catalog`, request identity, and exact decimal `targetID=1..16`, with the client's trailing `lastUpdate` tolerated. | Signed `success:true`, changed local `itemList`/`summonList`, and integer `coins`; or signed `success:true,cmdError:1..3`; commits/replays atomically. |
| Companion sale | `POST /gd/sell_buddy`, `POST /gd/sell_buddies` | Requires `--companion-catalog`, request identity, exact `inventoryID` or unique `sellList` of existing local owned-instance IDs, with the client's trailing `lastUpdate` tolerated. | Signed changed local `buddyInfo`/`chrdata`/coins or signed `success:true,cmdError:2`; commits/replays atomically. |
| Companion strengthen | `POST /gd/buddy_strengthen` | Requires `--companion-strengthen-catalog`, request identity, exact `baseID` and unique one-to-four entry `matList` of existing local owned-instance IDs. | Signed changed local `buddyInfo`/`chrdata`/coins plus `totalEXP`, `additionalEXP`, `expBonus`; or signed `success:true,cmdError:2..6`; commits/replays atomically. |
| Companion evolution | `POST /gd/buddy_evolve` | Requires `--companion-evolution-catalog`, request identity, exact decimal `baseID` with optional trailing `lastUpdate=1`. | Signed changed local `buddyInfo`/`chrdata`/itemList/coins or signed `success:true,cmdError:1..5`; commits/replays atomically. |
| Companion draw | `POST /gd/do_buddy_slot` | Requires `--companion-draw-catalog`, request identity, exact `kind`, `count`, `campaignID=0`, `eventFlag=0`, `lastUpdate` form. | Signed local currency/item/`buddyInfo` projection and level-1 `result` entries, or signed `success:true,cmdError:1|4`; commits/replays atomically. |
| Ordinary Pact draw | `POST /gd/do_slot` (`kind=0`) | Requires `--pact-draw-catalog`, request identity, and exact normal batch form. Operator supplies all pool IDs, weights, prices, and duplicate policy. | Signed local coin/energy projection and `chrdata` results, or signed `success:true,cmdError:2|3`; commits/replays atomically. Ticket/campaign variants are deliberately unsupported. |
| Built-in local Pacts | `POST /gd/do_slot` (`kind=0` Fellowship; `kind=1` Truth) | Requires `--pacts`, a request ID, the exact normal request envelope, and a count from 1 through 10. The broader count range is required because the client submits affordable remainder batches. | Durable local coin or Energy settlement and `chrdata` results. Pool membership is local policy. Truth selection is class-weighted (4% Z, 10% SS, 15% S, 71% A/B) and duplicate gains are class-banded (Z +6/+12.0%, SS and S +5/+10.0%, A and below +1/+5.0%), both read from the operator's own catalog `rarity` and both community-recorded local policy rather than recovered service values; Fellowship selection stays uniform. Fate, ticket, campaign, and event forms deliberately remain unsupported. |
| Catalog-bounded generic story outcomes | `POST /gd/clear_quest` | Requires a declared generic stage, `--story-outcome-catalog`, and `--outcome-strict`; optional `--clear-state-catalog` additionally derives saved-party EXP/level/Skill-Boost deltas, preserves immutable fields, requires a confirmed baseline for new configured characters, and derives configured duplicate Skill-Boosts. Reported item/character/Companion outcome must remain within operator-declared maxima, per stage and only where the catalog declares evidence for that ceiling. | Signed local clear projection plus authoritative `buddyInfo`, or `409 invalid_local_outcome` / `invalid_local_clear_state`; commits/replays atomically. This validates client-reported outcomes and does not generate drop rolls. |
| Story Companion drops | `POST /gd/clear_quest` | Requires a declared generic stage and `--story-outcome-catalog`. Bounds the reported Companion outcome by the stage's recovered `dropBuddies` ceiling and the catalog's declared drop levels; reported items, recruited monsters, and Summons are left as unconstrained as they are with no catalog unless `--outcome-strict` is also given. | Signed local clear projection plus authoritative `buddyInfo`, or `409 invalid_local_outcome` when the roll exceeds the stage ceiling or names an undeclared Companion; commits/replays atomically. Validates a client-reported roll and does not generate drop rolls. |
| Companion inventory write | `POST /gd/userdata` | Requires request identity and exact `buddyInfo=<JSON array>&lastUpdate=<nonnegative>` delta of existing local owned instances. | Signed `success:true,lastupdate:1.0`; atomically persists permitted local flags and replays across restart. |

The raw JSON response, including its whitespace and final newline, is signed.
The timestamp is emitted as a JSON floating-point value because this client
boundary requires a floating-point JSON token.

Every phrase above describing a debited meter — "debits the stamina meter", a
"post-spend `refillStartTime`", a refusal because "the meter is short" — states
the behavior under `--enable-stamina`, which no launcher passes by default.
Without it entry charges nothing and refuses nothing on stamina grounds: each of
those callbacks reports `refillStartTime: 0.0`, the client's own full-meter
representation. The wire shapes are otherwise unchanged, and the recovered meter
model itself is unchanged. See
[The stamina meter is off by default](docs/advanced-configuration.md#the-stamina-meter-is-off-by-default).

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
request-ID/body-hash cache. An identical retry replays the stored result.
Because the client derives request IDs from a low-precision floating-point
value, unrelated mutations can share one; the body hash therefore scopes the
identity, and the same request ID with a different body is evaluated as a
distinct request. The file is not a session or cookie store.

## Android host compatibility

The client is a 2017 Unity build and carries that engine's own Android
compatibility boundary, which is separate from the protocol slice above.

| Android target | State | Detail |
| --- | --- | --- |
| API 34 (Android 14) emulator, Google Play image with Translated ABI | Confirmed working | Reaches the title screen and streams local resources. Reported by an operator on a Pixel 4 image. |
| API 29 (Android 10) emulator | Cannot install | `INSTALL_FAILED_NO_MATCHING_ABIS`: that image has no ARM translation. Use a Translated ABI image. |
| Android 15, physical (Pixel 7 Pro, `arm64-v8a`) | Confirmed working | An operator installed the self-hosted combined APK, reached real gameplay progress, and then moved that save with `on_device_state export` and rebuilt in place with `update`, both from a Windows build host. This is the first physical-hardware gameplay report for the combined APK. It does not identify the installed artifact as the final source-exact build, and it carries no ARMv7 or preserved-trace claim. |
| Android 16, physical (Galaxy S24 FE, Galaxy S26, Galaxy Tab A9+) | Confirmed working on both routes: the combined APK carries a host guard and reaches gameplay on an S26; the separate-server route reaches gameplay on a Tab A9+ with `--disable-google-services` | Android 16 added an `onServiceConnected(ComponentName, IBinder, IBinderSession)` overload to `ServiceConnection`. Unity's `bitter.jnibridge` proxies that interface, and a `java.lang.reflect.Proxy` dispatches `default` methods to its handler rather than inheriting them, so the first completed Google Play Services bind asks the 2017 bridge for a signature it does not know and it throws `NoSuchMethodError` on the main thread. The bridge is Unity's and cannot be rebuilt. |

`--disable-google-services` rewrites the bind actions so they resolve to
nothing, which prevents the bind from completing and so prevents the crash: 18
in `classes.dex`, plus the advertising-ID action inside Unity's own
`libunity.so` in both ABIs. The last is the one that carries the crash. Unity
binds Play Services from native code using its own copy of that string, which no
dex edit reaches, and its connection is a `java.lang.reflect.Proxy` — the only
kind of `ServiceConnection` here that fails, because a Proxy routes an
interface's `default` methods to its handler while an ordinary class inherits
them. All twelve classes in the client dex that implement `ServiceConnection`
are ordinary classes, so none of them can raise this. An earlier reading
attributed the crash to Google Play Billing on the strength of a log line
ordering; that is withdrawn.

It remains opt-in because it edits client bytes no other supported path
touches, but it is now confirmed on Android 16 hardware: a Galaxy Tab A9+
(SM-X210, API 36) runs a separate-server build carrying all three edits through
launch and real gameplay, on the route that has no host guard to mask the
result. No unpatched control was taken on that tablet, so the crash and the fix
are each confirmed on Android 16 but on different devices. Nothing is given up — Play Games, the ads
SDK, Google auth, and Nearby have no live service to reach, and the advertising
ID is analytics for a retired service. One reporter established that the client
runs normally with Google Play Services disabled device-wide, which is the
runtime equivalent.

This is an engine boundary, not a protocol one: it applies equally to the
separate-server and self-hosted routes, because both install the same client.

## Evidence labels

- Route names, method, status request order, minimal response shape, and the
  floating-point timestamp requirement: confirmed against the surviving client.
- The signup → login → userdata transport progression and minimal accepted
  response types: confirmed for the supported initial-account boundary.
- The exact tutorial summon forms, result types, and Grace-path client
  acceptance are confirmed. The maintainer identifies the retail first-Pact
  distribution as equal-weight Bahl or Grace; that historical rule is
  operator-supplied rather than independently captured in this public source.
  Both branches, one-time random choice, byte-stable restart replay, and Bahl's
  continuation through the next Pact and state write are real-HTTP tested.
  Original-client Bahl-path acceptance remains pending, including its packed
  starter level/EXP projection after Chapter 1-2.
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
  callback keys, and error codes 1/2 are static-confirmed. Platform-wallet
  billing behavior is not recovered.
- The stamina meter is confirmed. `GameManager.CalcStamina` (ARM64 `0xD9CFC0`)
  derives the bar from one Unix-seconds fill origin, `UserData.refillStartTime`,
  as `min((now - origin) / refillInterval, GetMaxStamina()) + bonusStamina`, and
  `UserData.GetMaxStamina` (`0x19D8BDC`) is a two-branch single-precision curve
  on the account's chapter scaled by `MaxStaminaBias`, which defaults to 100
  when the server omits it (`0x19D57AC`). A zero origin therefore means a full
  meter, not an unset field. Stamina and Energy are separate currencies: quest
  entry debits the meter, never the Energy wallet. Charging it is nonetheless
  **opt-in preservation policy** rather than a fidelity claim this server always
  makes: a refilling meter paces a live service, so entry charges the recovered
  model only under `--enable-stamina` and otherwise pins the origin at zero.
- Per-stage and per-chapter Energy income on clear is **local preservation
  policy, not recovered service behavior**. The retired service sold Energy and
  gifted it through campaigns and operator mail, none of which this archive can
  reproduce, and nothing in the client mints it. Without a replacement an
  account can only ever lose Energy. Only story and event stage clears pay: the
  optional areas — Hunting, Metal Zone, the special quest, Daily Quests and the
  Chapter 1100 Roads — repeat without bound, so paying them would price every
  Energy cost in the client in Metal Zone runs instead. See
  `liminal_gate/archive_economy.py` for the rates and the replay-safety
  argument.
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
