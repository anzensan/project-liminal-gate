# Tower of Temptation preservation boundary

Status: all 12 packaged stages in Chapters 9010--9013 are implemented as a
bounded solo archive adapter. Original-client navigation and clear remain
unverified. Arena VS, Raid, and Donation remain disabled.

## Evidence and confidence

### Confirmed static client contract

- `ChapterInterface::.cctor` defines Chapters 9010--9013 as Tower of
  Temptation and Chapters 9100--9102 as Donation. The predicates are
  `IsTowerOfTemptationQuest` at ARM64 RVA `0xD060D4` and `IsDonationQuest` at
  `0xD0617C`.
- The final client has a dedicated `ServerConstants.towerQuestList` field.
- `UISpecialSelect.Mode.TowerQuest` is mode 5, separate from ordinary Special
  Quests, Hunting, Counter Descent, and multiplayer Arena.
- Direct ARM64 call-site recovery finds the Tower predicate only in
  `UISpecialItem.Init` and `UISpecialSelect.GetTitle`; it does not select a
  separate network result method.
- `ChapterBase._execSection` calls ordinary `AppServerUtil.ClearQuest` for the
  completed solo-stage branch. Tower uses the same generic entry/result
  transport as other locally hosted solo events.
- Donation has separate UI/state consumers, including
  `EventManager.GetDonationQuestAmount` and
  `UISpecialItem.DispDonationQuest`; a generic quest list cannot recreate it.

The inspected derived `dump.cs` has SHA-256
`093b32f0015b1498be710fef7c857634ee1350b2ed065c55ae12b02bcb062a34`.
It was produced from the operator's final 5.5.7-170 client by Il2CppDumper
v6.7.46. The reusable generated location is `user-data/il2cpp/dump.cs`; it is
private derived output and is not committed.

### Confirmed local master data

`user-data/derived/battledata-stages.json`, SHA-256
`be6fee15b28fd192d12c2ee5c8ac4cce30f25addda3135f77deec3dc65596767`,
was derived from Android APK SHA-256
`f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15`.
It records Chapters 9010, 9011, 9012, and 9013 with three one-battle sections
each. Every section costs 15 stamina and zero entry Coins.

### Explicit local policy

The original Tower depended on cooperative/shared HP, staged progression, and
achievement/reward state that has not been recovered. This implementation is
therefore a clearly labeled solo preservation adapter for the shipped battles,
not a reconstruction of the historical shared event.

All 12 stages are permanently available after Chapter 3. That gate and the
zero fixed clear-Coin increment are local policy, not a recovered schedule or
reward table. Client-reported battle Coins and local roster/item projections
use the existing trusted-local event settlement. No shared HP, ranking,
achievement tier, community total, fixed item, Companion, or character reward
is invented.

## Implemented transport contract

- `GET /gd/get_server_status` projects `9010-1` through `9013-3` only through
  `constants.towerQuestList` once the local Chapter 3 gate is met.
- Login supplies exact `sp_ch_9010` through `sp_ch_9013` flags only while the
  corresponding rows are unlocked.
- `POST /gd/start_quest` validates the listed identity, 15 stamina, zero Coins,
  and current free-roam state before durably debiting stamina.
- `POST /gd/clear_quest` requires the active Tower identity, unchanged story
  progress/world map, and a reconcilable wallet. It commits before reply and
  supports exact replay after restart.
- Chapters 9100--9102 are not generated or advertised. They remain disabled
  until Donation's community aggregate and reward semantics are recovered or
  a separately labeled redesign is deliberately chosen.
- `/gd/multiplay_enable` remains exactly `enable=false` and
  `enablemain=false`; no VS, matchmaking, rank, or peer route is enabled.

## Validation boundary

Local generation, schema validation, selector projection, entry, refusal,
clear, exact replay, and restart persistence are covered over real HTTP. The
remaining acceptance test is on the surviving final client:

1. open Arena, then Tower;
2. confirm the first row loads as Chapter 9010-1;
3. enter and clear it;
4. confirm the result returns to free roam without a network error.

Until that succeeds, the implementation is locally transport-certified but
not original-client accepted.
