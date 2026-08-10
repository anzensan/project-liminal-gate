# "To another world" side scenarios

Status: implemented, unplayed. The stages had been served since 2026-08-02; the
two mechanisms that make them reachable were added on 2026-08-09. Nothing here
has been played against a client, and the evidence is the client's own handlers
rather than a capture. Expect defects.

This document began as a plan written on a wrong premise -- that no stage in
Chapters 100--199 was modelled and that the wire shapes could not be settled
without an emulator. Both were false. It is kept as the record of what the
premise cost and what the client actually says.

## What the content is

Two scenarios reachable from the world map's "To another world" menu.

| World | Scenario | Chapters | Stages | Stamina | Battles |
| --- | --- | --- | --- | --- | --- |
| 1 | BreaSoul (a.k.a. The Death of Shay and Arionne) | 100--104 | 20 (4/5/5/5/1) | 15 | 1--5 |
| 2 | The Five Emperors (a.k.a. Ultimate Five) | 110--119 | 10 (1 each) | 15--20 | 1 |

Counts are from the reviewed APK's own BattleData. All thirty reserved section
slots carry a nonzero `battleCnt`, so unlike Chapter 20 there is no padding to
filter. The world indices are the client's own: `UserData.InitData` seeds world
1 at 100-1 and world 2 at 110-1.

## What the original plan got wrong

- **"No stages exist in Chapters 100--199."** They had existed since
  `d9cb79b`, behind `--secondary-worlds`, as a BreaSoul and Five Emperors
  extension of the Hunting catalog. The reported `unsupported_start_quest` was
  a server run without that flag, not a missing catalog.
- **"One `progressCode` serves every world," inflating the stamina cap.** It
  cannot arise here. These settle through the Hunting path, which requires
  `progressCode` to be *unchanged* and never moves it. The per-world cursor
  problem is real, but it is about the side worlds' own progress, not the
  story's.
- **"Phase 0 is blocking and needs the client on an emulator."** Every question
  it named is answered by reading the handlers. See `docs/findings.md`,
  2026-08-09, for the addresses.
- **"`WORLD_NUM` is a server constant."** It is not. The build carries no such
  string literal; `UserData..cctor` assigns the literal 3.

Two blockers it named were real, and both were fatal on their own.

## The two real blockers, and what fixed them

1. **The menu could never appear.** `IsWorld1ChangeEnable` and
   `IsWorld2ChangeEnable` each call `IsSectionUnlocked`, which reads
   `worldProgressCode` -- for world 0, because the thresholds (26-1 and 20-1)
   are main-story sections. That key was never sent, `InitData` leaves the array
   zeroed, and so both predicates were false for every account regardless of the
   map flags. Fixed by projecting `worldProgressCode` onto every userdata read.
2. **The world cursor was never written.** `UIMap.SetWorld` writes
   `UserData.worldNo`, which is the wire's `worldMapNo`, and marks the record
   dirty. The swap posts a three-field userdata write this server refused, and
   every clear afterwards carried a world the server compared against a stored
   zero. Fixed by accepting the write and remembering the cursor.

## What is served now, and in what shape

All three are confirmed from the reviewed 5.5.7-170 `libil2cpp.so`; the
disassembly addresses are in `docs/findings.md`.

- **`userdata.worldProgressCode`** -- an *object* keyed by world index in
  decimal string form, values packed as
  `section | chapter << 6 | newStage << 24 | showProgress << 25`, the same
  packing as `progressCode`. Not the array its `int[]` declaration implies:
  `LoadUserdataFromJson` walks `.Keys` and `Int32.Parse`s each one, and LitJson
  throws on an array. World 0 is derived from `progressCode` on every read;
  worlds 1 and 2 are durable in the account document under `world_progress`,
  seeded by an explicit migration. Server-to-client only -- no client handler
  serializes it back, so the server owns every advance.
- **`constants.worldMaxChapter`** -- an *array* of internal chapter numbers
  indexed by world, `[0, 104, 119]`. Index 0 is a placeholder, not a ceiling:
  both consumers return before reading it when `worldNo` is zero. The client
  rewrites index 2 to 114 itself unless `sp_five_emperors2` is set, which is how
  the five hard descents stay behind their own flag.
- **`userdata.worldMapNo`** -- accepted from the client's own three-field write
  when it moves only the cursor, and compared against on every clear as before.

Two rules sit beside them, and both are this server's rather than the client's.
A clear may move a world's cursor only from at or behind that world's frontier,
so a section the map never offered settles its rewards without retiring the
sections in between. And a stored cursor is validated against the sections its
world declares and the `Int32` the client reads it with, because a hand-edited
save is a supported way to reach this server and a wider value would arrive as
a freeze inside the userdata load rather than an error.

Both unlock gates are now recovered rather than community record:
`IsSectionUnlocked(26, 1)` for BreaSoul and `IsSectionUnlocked(20, 1)` for the
Five Emperors, as literal immediates in the two predicates.

## Deployment

Server-side only, so a **server restart** on the dedicated route and an **APK
rebuild** for on-device testers, who get every server change that way because
the combined package bakes the server in. `--secondary-worlds` gates all of it,
and it is already in `server_config.STANDARD_POLICY_FLAGS`, so both launchers
carry it without a new flag.

## Validation boundary

Unchanged from the original plan, and it is the part that still stands.
Nothing here has been played. The stage counts come from the operator's own
BattleData, the client contracts from its own handlers, and the thirty stages
have never run against this server.
