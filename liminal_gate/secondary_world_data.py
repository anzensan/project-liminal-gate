"""BreaSoul and the Five Emperors: the client's two secondary world maps.

`UIMap` can swap the world map for one of two others. `IsWorld1ChangeEnable`
opens BreaSoul and `IsWorld2ChangeEnable` opens the Five Emperors, each behind a
client version predicate that is already true for the supported 5.5.7 APK, a
story threshold, and a map flag the server sends. Neither family appears in a
Hunting or Special selector, so both use the `hidden` selector the Daily Quests
already use: the client draws the map point itself and asks this server only to
honour the entry.

**Confirmed, from the operator's own embedded `BattleData`.** Every identity,
stamina cost and Coin cost below, and the Companion candidate manifests. BreaSoul
is twenty sections across Chapters 100--104, each 15 stamina and zero Coins, and
every one of them declares an *empty* `dropBuddies`. The Five Emperors are ten
sections, one per chapter across 110--119, zero Coins throughout, 15 stamina for
the five normal descents and 20 for the five marked hard, each declaring one or
two candidate Companions.

The story thresholds are recovered too, and were previously labeled local
policy here: section 26-1 for BreaSoul and 20-1 for the Five Emperors are the
literal `IsSectionUnlocked` arguments inside the client's own two map
predicates. What this server owns is only whether to send the flag beside them.

**Local policy, labeled as such.** Two things.

Experience is paid, under a ceiling, on the same reasoning the two Roads already
use here: EXP is the battle's own product rather than a reward the retired
service chose, and refusing it means a player wins a battle and is told no. The
ceiling exists to refuse an absurd claim, not to reproduce a rate.

The Companion payout is a bounded acceptance, not a reproduction. A Five
Emperors clear may report at most one Companion its own manifest names, minted
at level 1 -- the rule Chapter 1100 already uses, for the identical situation of
a manifest that proves candidates without proving a roll. BreaSoul's manifests
are empty, so it settles no Companion at all, on the game's own authority.

Coins and items are refused for both. No section declares a Coin reward and no
item manifest survives, so there is nothing to bound them against.

**The world cursor and per-world progress.** Opening either map is only half of
what the client needs, and this module owns the other half. `UIMap.SetWorld`
writes `UserData.worldNo` and marks the record dirty, and `worldNo` is the wire
field this server already knows as `worldMapNo` -- `LoadUserdataFromJson` stores
the parsed `worldMapNo` straight into that field. So a player standing on a
secondary map sends a *non-zero* `worldMapNo` on every write and clear, and a
server that only ever compares it against a stored zero refuses everything the
player does there.

Progress inside a world is separate from `progressCode` and reaches the client
in `worldProgressCode`. Its values use the same packing as `progressCode`
(`section | chapter << 6 | newStage << 24 | showProgress << 25`), which is
`UserData.SetWorldNewChapter`'s own arithmetic, and `GetWorldChapterNo` /
`GetWorldSectionNo` read the two halves back out with `(v >> 6) & 0x3FF` and
`v & 0x3F`.

**It comes back under another name, and missing that is what kept both maps
broken after the menu opened.** `worldProgressCode` is written by exactly one
handler, so a scan for the literal reads as server-to-client only -- but the
value returns in the `progressCode` field. `SerializeJsonUserData` does not
send `UserData.progressCode` for the Progress kind; it sends
`UserData.GetWorldProgressCode()` (`0x19D9394`), which returns
`worldProgressCode[worldNo]` for any non-zero world and rebuilds the story code
from `chapterNo`/`sectionNo` only for world 0.

So `progressCode` means the story on world 0 and *that world's cursor*
everywhere else. It carries the cursor on the swap that arrives at a map, on
every Progress flush after it -- `UnlockNextSection` marks the record dirty
after each clear -- and on the clear each side-world battle posts. A server
comparing the field against the stored story code refuses all three, which is
one Network Error at the menu and a second on every battle behind it.

All of this is confirmed from the reviewed client's `libil2cpp.so`, and it
settles three questions this project had previously left open:

- `worldProgressCode` is read as a JSON **object keyed by the world index in
  decimal string form**, not as the array its `int[]` declaration implies:
  `LoadUserdataFromJson` walks `.Keys`, calls `Int32.Parse` on each key, and
  indexes the value with `get_Item(string)`. LitJson's `Keys` throws on a JSON
  array, which is the boot failure another reimplementation reported.
- `worldMaxChapter` is a JSON **array of internal chapter numbers indexed by
  world**, not per-world display indices: `get_worldChapterNo` clamps the
  world's chapter against `worldMaxChapter[worldNo]`. Index 0 is never read --
  both consumers return early when `worldNo` is zero -- so this server declares
  no ceiling for the main story.
- `WORLD_NUM` is **not a served constant at all**. No such string literal exists
  in the build; `UserData..cctor` assigns the literal 3, and `InitData`
  allocates `worldProgressCode` at that length.

The two unlock thresholds are confirmed with them, so they are no longer local
policy: `IsWorld1ChangeEnable` calls `IsSectionUnlocked(26, 1)` and
`IsWorld2ChangeEnable` calls `IsSectionUnlocked(20, 1)`, each alongside its
version predicate and its map flag. `IsSectionUnlocked` resolves the chapter to
its world through `ChapterInterface.GetWorldNoByChapter` and then reads
`worldProgressCode` for *that* world -- so both menu entries are gated on world
0's entry, which is why sending the flags alone never opened either map.
"""

from __future__ import annotations

from liminal_gate.companion_master_data import companion_drop_level

from liminal_gate.hunting_catalog import HuntingStage

#: The client's own map flags. `sp_matsuno` opens the BreaSoul map; the Five
#: Emperors need both of theirs, because the final map's expanded coordinate
#: branch checks the second once the world-2 selector is on.
BREASOUL_EVENT_FLAG = "sp_matsuno"
FIVE_EMPERORS_EVENT_FLAGS = ("sp_five_emperors", "sp_five_emperors2")

#: **Confirmed.** The story sections at which each map becomes reachable, read
#: out of the client's own `IsWorld1ChangeEnable` / `IsWorld2ChangeEnable` as
#: the literal arguments to `IsSectionUnlocked`.
BREASOUL_UNLOCK = (26, 1)
FIVE_EMPERORS_UNLOCK = (20, 1)

#: **Confirmed.** `UserData.WORLD_NUM`, the literal `UserData..cctor` assigns
#: and the length `InitData` allocates `worldProgressCode` at. Not a served
#: constant: the build carries no `WORLD_NUM` string literal.
WORLD_COUNT = 3

#: **Confirmed.** Which world index each map is, from `InitData`'s own seeding
#: (`SetWorldNewChapter(1, 100, 1)` and `SetWorldNewChapter(2, 110, 1)`).
BREASOUL_WORLD = 1
FIVE_EMPERORS_WORLD = 2
MAIN_WORLD = 0

#: The packing `SetWorldNewChapter` writes and `GetWorldChapterNo` /
#: `GetWorldSectionNo` read back, shared with the main-story `progressCode`.
_SECTION_MASK = 0x3F
_CHAPTER_SHIFT = 6
_CHAPTER_MASK = 0x3FF
_NEW_STAGE_BIT = 1 << 24
_SHOW_PROGRESS_BIT = 1 << 25

#: **Local policy.** An EXP ceiling per entry, taken from the Metal Zone tier
#: whose stamina these stages match, exactly as the two Roads take theirs.
_BREASOUL_EXP_CEILING = 1_560_000
_FIVE_EMPERORS_EXP_CEILING = 1_560_000
_FIVE_EMPERORS_HARD_EXP_CEILING = 2_270_000

#: **Confirmed.** Chapter to its section count. 100 carries four sections and
#: 104 carries one; the three between carry five each, twenty in total.
_BREASOUL_SECTIONS: tuple[tuple[int, int], ...] = (
    (100, 4), (101, 5), (102, 5), (103, 5), (104, 1),
)

#: **Confirmed.** Chapter, stamina, and the Companion candidates its own
#: `dropBuddies` manifest names. The five hard descents cost 20.
_FIVE_EMPERORS_ROWS: tuple[tuple[int, int, tuple[int, ...]], ...] = (
    (110, 15, (464,)),
    (111, 15, (462,)),
    (112, 15, (460,)),
    (113, 15, (466,)),
    (114, 15, (471, 48)),
    (115, 20, (470, 478)),
    (116, 20, (473, 480)),
    (117, 20, (472, 481)),
    (118, 20, (469, 479)),
    (119, 20, (468, 49)),
)



def build_bundled_breasoul_stages() -> tuple[HuntingStage, ...]:
    """Return BreaSoul's twenty sections as bounded, unadvertised stages."""
    return tuple(
        HuntingStage(
            family="breasoul", chapter=chapter, section=section,
            stamina=15, coins=0, entry_item_id=0, entry_item_count=0,
            unlock_chapter=BREASOUL_UNLOCK[0], unlock_section=BREASOUL_UNLOCK[1],
            max_coins=0, max_exp=_BREASOUL_EXP_CEILING,
            max_items_total=0, item_maxima={},
            # Empty `dropBuddies` in every one of the twenty: the game says
            # this family drops no Companion, so none is accepted.
            companion_maxima={},
            selector="hidden",
        )
        for chapter, sections in _BREASOUL_SECTIONS
        for section in range(1, sections + 1)
    )


def build_bundled_five_emperors_stages() -> tuple[HuntingStage, ...]:
    """Return the ten Five Emperors descents as bounded, unadvertised stages."""
    return tuple(
        HuntingStage(
            family="five_emperors", chapter=chapter, section=1,
            stamina=stamina, coins=0, entry_item_id=0, entry_item_count=0,
            unlock_chapter=FIVE_EMPERORS_UNLOCK[0],
            unlock_section=FIVE_EMPERORS_UNLOCK[1],
            max_coins=0,
            max_exp=_FIVE_EMPERORS_HARD_EXP_CEILING if stamina == 20 else _FIVE_EMPERORS_EXP_CEILING,
            max_items_total=0, item_maxima={},
            # One per candidate, but the total is what bounds a clear: the
            # record's rule for this shape of manifest is a single exclusive
            # roll, so a clear naming two of them is refused.
            companion_maxima={companion: 1 for companion in candidates},
            # The manifest proves which Companions a descent can give, not how
            # many. One exclusive roll is the record's rule for this shape, so
            # a clear naming both candidates of a two-candidate descent is
            # refused rather than paying twice.
            max_companions_total=1,
            companion_drop_levels={
                companion: companion_drop_level(companion) for companion in candidates
            },
            selector="hidden",
        )
        for chapter, stamina, candidates in _FIVE_EMPERORS_ROWS
    )


#: Each secondary world's sections in play order, keyed by world index. This is
#: the successor graph a clear advances along, and it is the same `BattleData`
#: reading the two stage builders above use rather than a second transcription.
_WORLD_SECTIONS: dict[int, tuple[tuple[int, int], ...]] = {
    BREASOUL_WORLD: tuple(
        (chapter, section)
        for chapter, sections in _BREASOUL_SECTIONS
        for section in range(1, sections + 1)
    ),
    FIVE_EMPERORS_WORLD: tuple((chapter, 1) for chapter, _stamina, _drops in _FIVE_EMPERORS_ROWS),
}

#: Which stage family belongs to which world, so a Hunting settlement can find
#: the world it should advance without re-deriving it from the chapter.
WORLD_FOR_FAMILY: dict[str, int] = {
    "breasoul": BREASOUL_WORLD,
    "five_emperors": FIVE_EMPERORS_WORLD,
}


def pack_world_progress(chapter: int, section: int, *, chapter_boundary: bool = False) -> int:
    """Pack one world cursor the way `SetWorldNewChapter` packs it.

    ``chapter_boundary`` sets `showProgress` alongside `newStage`, matching both
    the client's own seeding and the main story's codes, where a section
    advance carries bit 24 and a chapter advance carries bits 24 and 25.
    """
    packed = (section & _SECTION_MASK) | ((chapter & _CHAPTER_MASK) << _CHAPTER_SHIFT) | _NEW_STAGE_BIT
    return packed | _SHOW_PROGRESS_BIT if chapter_boundary else packed


def unpack_world_progress(packed: int) -> tuple[int, int]:
    """Return the chapter and section a packed world cursor names."""
    return (packed >> _CHAPTER_SHIFT) & _CHAPTER_MASK, packed & _SECTION_MASK


def world_for_chapter(chapter: int) -> int:
    """Return the world whose map a chapter is drawn on.

    Deliberately *not* `ChapterInterface.GetWorldNoByChapter` (`0xD062E4`),
    which is `(unsigned)(ch - 100) < 10` and so answers 1 for chapters 100--109
    and 0 for everything else -- including the Five Emperors' 110--119, even
    though the client's own `InitData` seeds world 2 at chapter 110. That
    function was never extended past the world it shipped with, and its five
    callers are all cosmetic here: two display labels, a shader pick, and
    `IsSectionUnlocked` / `IsSectionCleared`, which the map points and the
    stage-entry path never consult. Nothing this server owns may inherit the
    gap, because it is what decides which world a clear advances.
    """
    for world, sections in _WORLD_SECTIONS.items():
        if any(chapter == declared for declared, _section in sections):
            return world
    return MAIN_WORLD


def initial_world_progress() -> dict[str, int]:
    """Return the per-world cursors an untouched account starts from.

    These are the client's own defaults rather than a choice here: `InitData`
    seeds world 1 at 100-1 and world 2 at 110-1, with both banner bits set.
    World 0 is absent because it is `progressCode` and is projected from it.
    """
    return {
        str(world): pack_world_progress(*sections[0], chapter_boundary=True)
        for world, sections in _WORLD_SECTIONS.items()
    }


def advanced_world_progress(packed: int, chapter: int, section: int) -> int | None:
    """Return the world cursor a clear of ``chapter``-``section`` leaves behind.

    ``None`` when the stage names no modelled secondary-world section. The
    cursor records the furthest section the world has *unlocked*, which is what
    `IsSectionUnlocked` compares against, so a clear moves it to the cleared
    section's successor and the last section of a world leaves it where it is.
    A clear behind the frontier never moves it backwards.
    """
    world = world_for_chapter(chapter)
    sections = _WORLD_SECTIONS.get(world)
    if sections is None or (chapter, section) not in sections:
        return None
    # Compared as a chapter/section pair, never as the packed integer: the two
    # banner bits outrank both halves, so a stored cursor that still carries
    # `showProgress` would win an integer comparison against the section after
    # it and the world would never advance.
    frontier = unpack_world_progress(packed)
    if (chapter, section) > frontier:
        # A clear of a section this world has not opened yet. The client draws
        # its own map from this cursor and would not offer one, so this is a
        # body it does not produce -- and honouring it would advance the cursor
        # *past* every section in between, silently retiring content the player
        # never saw. The clear still settles; only the frontier holds.
        return packed
    index = sections.index((chapter, section))
    last = index + 1 == len(sections)
    reached = (chapter, section) if last else sections[index + 1]
    if frontier >= reached:
        return packed
    return pack_world_progress(
        *reached, chapter_boundary=not last and reached[0] != chapter,
    )


def is_valid_world_progress(world: str, packed: object) -> bool:
    """Whether a stored cursor is one this world could actually hold.

    Checked because the value is sent to the client, and the client reads it
    with LitJson's `Int32` accessor: a number past that range raises
    `InvalidCastException` inside the userdata load, which reaches a tester as
    a freeze rather than an error. A hand-edited save is a supported way to
    reach this server -- `tools/save-editor.html` exists -- so the save layer,
    not the wire, is where an impossible cursor has to stop.
    """
    if type(packed) is not int or packed < 0 or packed > _NEW_STAGE_BIT | _SHOW_PROGRESS_BIT | 0xFFFF:
        return False
    # `isascii` as well as `isdigit`, because the key is sent as written and the
    # client resolves it with `Int32.Parse`. Python calls an Arabic-Indic digit
    # a digit and converts it; whether that client's parse agrees is exactly the
    # kind of thing this project does not put on the wire to find out.
    if not (type(world) is str and world.isascii() and world.isdigit()):
        return False
    sections = _WORLD_SECTIONS.get(int(world))
    return sections is not None and unpack_world_progress(packed) in sections


def world_max_chapters() -> list[int]:
    """Return the `worldMaxChapter` constant, indexed by world.

    Index 0 is a placeholder rather than a ceiling for the main story: both
    client consumers -- `get_worldChapterNo` and `NeedShowProgress` -- return
    before reading it when `worldNo` is zero, so declaring a number there would
    be inventing one this server has no basis for and the client never uses.
    The other two are the last chapter each secondary world declares.
    """
    ceilings = [0] * WORLD_COUNT
    for world, sections in _WORLD_SECTIONS.items():
        ceilings[world] = max(chapter for chapter, _section in sections)
    return ceilings


def secondary_world_event_flags(progress_chapter: int, progress_section: int) -> dict[str, dict[str, object]]:
    """Return whichever secondary-world map flags this account has reached.

    Both maps are permanent once open, which is archive policy: their
    historical availability windows were live-service state and were never
    captured.
    """
    flags: dict[str, dict[str, object]] = {}
    reached = (progress_chapter, progress_section)
    if reached >= BREASOUL_UNLOCK:
        flags[BREASOUL_EVENT_FLAG] = {"name": BREASOUL_EVENT_FLAG, "value": True}
    if reached >= FIVE_EMPERORS_UNLOCK:
        for name in FIVE_EMPERORS_EVENT_FLAGS:
            flags[name] = {"name": name, "value": True}
    return flags
