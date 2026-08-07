# Tower of Temptation preservation boundary

Status: all 12 packaged stages in Chapters 9010--9013 are implemented as a
bounded solo archive adapter. Physical-client navigation and first-stage battle
loading are operator-confirmed; clear/result return remains unverified. Arena
VS, Raid, and Donation remain disabled.

## Evidence and confidence

### Confirmed static client contract

- `ChapterInterface::.cctor` defines Chapters 9010--9099 as Tower of
  Temptation and 9100--9199 as the Donation range. The predicates are
  `IsTowerOfTemptationQuest` at ARM64 RVA `0xD060D4` and `IsDonationQuest` at
  `0xD0617C`; both are bounds checks against those `.cctor` literals. The
  chapters actually present in the Donation range are 9100--9102, and their
  BattleData titles name them Melting Pot rather than any donation content --
  see the 2026-08-07 entry in `findings.md`.
- The final client has a dedicated `ServerConstants.towerQuestList` field.
- `UISpecialSelect.Mode.TowerQuest` is mode 5, separate from ordinary Special
  Quests, Hunting, Counter Descent, and multiplayer Arena.
- Direct ARM64 call-site recovery finds the Tower predicate only in
  `UISpecialItem.Init` and `UISpecialSelect.GetTitle`; it does not select a
  separate network result method.
- `ChapterBase._execSection` calls ordinary `AppServerUtil.ClearQuest` for the
  completed solo-stage branch. Tower uses the same generic entry/result
  transport as other locally hosted solo events.
- **Withdrawn.** This plan previously held that "Donation has separate UI/state
  consumers, including `EventManager.GetDonationQuestAmount` and
  `UISpecialItem.DispDonationQuest`; a generic quest list cannot recreate it."
  Both named consumers are dead in the final build --
  `DispDonationQuest` (`0xF833F0`) is a single `ret`, and
  `GetDonationQuestAmount` and `InDonationQuest` have no callers. The claim was
  made from the presence of the symbols, not from their call sites.

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
- Chapters 9100--9102 are generated and advertised as Melting Pot, the content
  BattleData names them. They are ordinary local events settled under
  `projected_rewards`; the community-aggregate mechanic those chapters' class
  fields hint at is not reconstructed and is not claimed.
- `/gd/multiplay_enable` remains exactly `enable=false` and
  `enablemain=false`; no VS, matchmaking, rank, or peer route is enabled.

## Validation boundary

Local generation, schema validation, selector projection, entry, refusal,
clear, exact replay, and restart persistence are covered over real HTTP. On the
surviving final client, the maintainer has completed navigation and entry; the
first entry loaded its battle after a retry. That observation was not preserved
as a transport trace. The remaining acceptance steps are:

1. clear the entered first stage;
2. confirm the result returns to free roam without a network error.

Until those succeed, navigation and entry are operator-accepted, while the
complete Tower result lifecycle remains only locally transport-certified.
