# Tower of Temptation preservation boundary

Status: Chapter 9100-1 is implemented as a bounded solo compatibility slice.
Original-client navigation and clear remain unverified. Arena VS remains
disabled and is not part of this work.

## Evidence and confidence

### Confirmed static client contract

- The final client has a dedicated `ServerConstants.towerQuestList` field.
- `UISpecialSelect.Mode.TowerQuest` is mode 5, separate from ordinary Special
  Quests, Hunting, Counter Descent, and multiplayer Arena.
- `ChapterInterface` contains a Tower of Temptation chapter range and
  `IsTowerOfTemptationQuest`.
- The client contains Chapter 9100 battle code and scenario identities.

The inspected derived `dump.cs` has SHA-256
`093b32f0015b1498be710fef7c857634ee1350b2ed065c55ae12b02bcb062a34`.
It was produced from the operator's final 5.5.7-170 client by Il2CppDumper
v6.7.46. The reusable generated location is
`user-data/il2cpp/dump.cs`; it is private derived output and is not committed.

### Confirmed local master data

`user-data/derived/battledata-stages.json`, SHA-256
`be6fee15b28fd192d12c2ee5c8ac4cce30f25addda3135f77deec3dc65596767`,
was derived from Android APK SHA-256
`f2c0ffa188255f4694f0f60e898a58b372c2cc3fff7dd312a01d593189bd7a15`.
It records Chapters 9100, 9101, and 9102 with fifteen five-battle sections
each. Sections 1--5 cost five stamina, 6--10 cost ten, and 11--15 cost
fifteen; entry Coins are zero.

### Strong inference and explicit local policy

The dedicated selector, Tower range, Chapter 9100 program, and fifteen-floor
shape strongly support mapping 9100--9102 to Tower of Temptation. That mapping
is not dynamically confirmed until the original client opens and clears it.

Only 9100-1 is enabled. Permanent availability after Chapter 3 and zero clear
Coins are local preservation policy, not recovered schedule or reward rules.
No item, Companion, character, ranking, or probability is invented.

## Implemented transport contract

- `GET /gd/get_server_status` always includes `towerQuestList`.
- Before the Chapter 3 gate the list is empty; afterward it is `["9100-1"]`.
- Login supplies the exact chapter flag `sp_ch_9100` only while the gate is
  open.
- `POST /gd/start_quest` accepts the exact ordered Tower form
  `stamina=5&coins=0&chapter=9100&section=1&lastUpdate=1`.
- Entry commits the stamina-meter origin and active stage atomically. A retry
  cannot debit twice; the same request ID with a different invalid body is
  evaluated and refused independently.
- `POST /gd/clear_quest` requires the active 9100-1 identity, unchanged story
  progress, matching wallet projection, and zero clear Coins. Generated
  outcome and clear-state catalogs remain the authority for any client-reported
  roster, item, Companion, EXP, or boost changes.
- Successful clear returns to `free_roam`; exact replay remains stable after
  restart.
- Every other Tower floor in the standard generated catalog remains
  unsupported and receives no generic success. A separately reviewed explicit
  catalog remains an expert override.

## Client-visible acceptance gate

From an account that has completed Chapter 3, the final client must:

1. show the Tower destination without showing Arena VS;
2. render exactly the first 9100-1 row;
3. enter the battle and send the expected start form;
4. clear it, accept the response, and return to free roam;
5. retain the settled state after server and client restart.

If the row fails to render, the smallest falsification capture is the
`get_server_status` response followed by the Tower button/navigation logs. If
it renders but does not enter, preserve the first request or client exception.
Do not expand the remaining floors until this boundary passes.

## Validation

- Twenty-seven focused event/catalog/transport tests passed.
- The warning-strict full suite passed all 638 tests in 120.460 seconds.
- Python compilation, profile JSON parsing, endpoint YAML parsing, and
  `git diff --check` passed.
- The matching user-derived BattleData composed exactly one Tower row:
  `9100-1`, five stamina, zero Coins, and no invented grant.
- No APK was built or installed and no physical-client run was performed.
