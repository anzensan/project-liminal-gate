"""Which rewards a Luck Treasure Chest may hold, per stage and tier.

**Community record, and incomplete by its own admission.** The retired service
authored chest contents and the client only rendered them, so no table exists in
the APK to recover. What exists is the final wiki's per-stage reward lists,
scraped with page and revision provenance. Every row of that scrape carries
`community_table_incomplete`, and the wiki says so itself.

Two consequences are deliberate and should not be quietly fixed later:

* **Only seventy-three stages have a pool at all** -- thirty-one core-story
  stages and the forty-two Strikes Back quests recovered from the record's own
  template further down. Every other stage in the game has none, and a stage
  with no pool yields no chest rather than a guessed one.
  This is a floor on what the feature does, not a claim that other stages had no
  chests -- almost certainly they did, and the record simply does not cover them.
  The record does cover more than is here: the same template family also
  documents the Daily Quests, the Eidolon quests, and five standing Special
  Quests, and those remain unrecovered.
  An operator who wants to go past that floor supplies their own pools through
  :mod:`liminal_gate.luck_pool_catalog` and `--luck-pool-catalog`, which leaves
  this table exactly as sourced and says so in the server's startup output.
* **Sixty-five of the ninety-nine dropped rewards have since been recovered**,
  and nineteen of the thirty-one stages still lose at least one. Chapter 25-7,
  added after the first scrape missed its unheaded table, is not among them --
  every cell the record fills for it resolved. The scrape dropped
  sixty-eight character icons, four item names that resolved to nothing, and
  twenty-seven empty or generic cells. The icons carried their names, so
  sixty-five of them resolve by exact match against the operator's own
  `ChrDatabase` and are emitted here in the `M` form.

  Three icons do not, and the reason is a real ambiguity rather than a lookup
  failure: the wiki writes `Mage (Ice)` and `Lizardfolk Mage (Fire)`, while the
  master data holds four characters named `Mage` and four named `Lizardfolk
  Mage`, distinguished by an element the catalog does not name. They are 9-7
  Luck 80 and Luck 100, and 13-8 Luck 80. Choosing one would be a guess.

  The four `unresolved_item_name` rows are recorded here and deliberately not
  acted on. Three name characters the master data holds -- `Lizardfolk Archer`
  at 28-9 D, `Beastfolk Knight` at 31-1 D, `Lizardfolk Knight` at 31-2 D -- and
  the fourth, `Metal Minion` at 13-10 Luck 80, is Companion 128, already used
  by these pools elsewhere. All four look like a wiki editor reaching for
  `{{Item icon}}` where the reward was not an item. Acting on that means
  correcting the source rather than reading it, which is a different kind of
  decision from a name-to-ID join and is left to be made deliberately.

Rewards are wire-encoded the way the client reads a slot: `C` and an amount for
Coins, `I` and an item ID, `O` and a Companion ID, `M` and a character ID.

All four forms are delivered. Coins and items are reconciled against the
balances the client submits at clear, because the client folds them in itself;
Companions and characters cannot be, because the generic story clear body
carries no Companion box and no field to report either through, so the server
grants what it authored. See `_award_chest_grants`.

Selection within a tier is equal-weight, because the record carries no weights:
the scrape has no such column, and inventing one would be inventing the drop
rate this project refuses to invent. See `luck_data` for the appearance odds,
whose endpoints *are* sourced.
"""

from __future__ import annotations

#: The core story's pools, keyed by ``(chapter, section)`` and then by chest
#: tier. Entries marked ``# incomplete`` lost at least one reward the record
#: lists but the scrape could not resolve.
#:
#: This is the story half only. `DOCUMENTED_CHEST_POOLS` is what answers a
#: lookup; this name stays the story table because it is also the donor set
#: interpolation draws from, and only a story chapter may donate.
LUCK_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {
    (1, 1): {"A": ('C50', 'I11', 'I12', 'I1',), "B": ('C50', 'I5', 'I9',), "C": ('C50', 'I7', 'I11',), "D": ('I5', 'I3',), "Luck 80": ('C50', 'I11',), "Luck 100": ('C50',)},
    (1, 2): {"A": ('I3',), "B": ('I1',), "C": ('C50',), "Luck 80": ('I11',), "Luck 100": ('I5',)},  # incomplete
    (1, 3): {"A": ('I5',), "B": ('I10',), "C": ('I1',), "Luck 80": ('C50',), "Luck 100": ('I5',)},  # incomplete
    (1, 4): {"A": ('I9',), "B": ('I7',), "C": ('I11',), "Luck 80": ('I12',), "Luck 100": ('I12',)},  # incomplete
    (1, 5): {"A": ('C50', 'I9',), "B": ('C50', 'I7',), "C": ('C50',), "D": ('C50',), "Luck 80": ('I1', 'I3',), "Luck 100": ('I10', 'I5',)},
    (4, 1): {"A": ('C150', 'I83', 'I91', 'I89', 'I1', 'I11', 'I82',), "B": ('C150', 'I3', 'I5', 'I7', 'I91', 'I89', 'I1', 'I17', 'I82',), "C": ('C300', 'I89', 'I122', 'I10', 'I11', 'I9', 'I17', 'I82',), "D": ('C450', 'M175', 'O128',), "Luck 80": ('M199', 'M79', 'M84', 'M175', 'O128', 'O129',), "Luck 100": ('C300', 'M79', 'M175', 'O128', 'O129',)},
    (4, 10): {"A": ('C150',), "B": ('I91',), "C": ('I10',), "D": ('M175',), "Luck 80": ('M84',), "Luck 100": ('O128',)},
    (6, 8): {"A": ('I5', 'I92', 'I91', 'I89', 'I1', 'I10',), "B": ('C175', 'I3', 'I83', 'I7',), "C": ('I90',), "D": ('M71', 'O128',), "Luck 80": ('C350', 'M91', 'M71', 'O128', 'O129',), "Luck 100": ('C350', 'I50', 'M91', 'M71', 'M220', 'O129',)},
    (9, 7): {"A": ('I2',), "B": ('I5',)},  # incomplete
    (13, 8): {"A": ('I6', 'I9',), "B": ('C275', 'I14',), "C": ('I5', 'I82',), "Luck 80": ('O128', 'M203',), "Luck 100": ('I86', 'O129', 'M110',)},  # incomplete
    (13, 10): {"A": ('C275',), "B": ('I6',), "C": ('I89',), "Luck 100": ('C550',)},  # incomplete
    (16, 10): {"A": ('C325', 'I4', 'I91',), "B": ('C325', 'I83', 'I6', 'I8', 'I2', 'I11', 'I89',), "C": ('C650', 'I83', 'I91',), "D": ('M124', 'M73',), "Luck 80": ('O129', 'O128', 'M204',), "Luck 100": ('C650', 'I33', 'O129', 'O128', 'M204', 'M65',)},
    # The record's table for this stage carries no heading of any kind -- not the
    # `=== Luck Treasure Chests ===` of Chapter 16, nor the bold line Chapters 1,
    # 6 and 13 use -- which is how the original scrape walked past it. Its Luck
    # 100 cell is empty on the page; that is the record having nothing there, not
    # a reward this scrape failed to resolve, so the tier is absent rather than
    # guessed and the row is not marked incomplete. Every other cell resolved by
    # exact name: six items, Thornasaurus, and the two Metal Minion Companions.
    (25, 7): {"A": ('I82',), "B": ('I2', 'I3', 'I91',), "C": ('C900', 'I92',), "D": ('I96',), "Luck 80": ('C900', 'M314', 'O128', 'O129',)},
    (28, 3): {"A": ('C475', 'I165', 'I14', 'I90', 'I4', 'I91',), "B": ('C475', 'I14', 'I13', 'I92', 'I6', 'I90', 'I91', 'I2',), "C": ('C950', 'I91', 'I82', 'I89', 'I92', 'I10', 'I6',), "D": ('C1425', 'I120', 'O128',), "Luck 80": ('C950', 'O129', 'O128', 'M264', 'M70', 'M64',), "Luck 100": ('C950', 'O129', 'O128', 'M264', 'M70', 'M73', 'M64', 'M165',)},
    (28, 9): {"A": ('C475', 'I12', 'I4', 'I92', 'I83', 'I91', 'I90', 'I8', 'I6', 'I7', 'I11', 'I5', 'I17', 'I14',), "B": ('C475', 'I13', 'I2', 'I92', 'I14', 'I17', 'I11', 'I9', 'I7', 'I5', 'I82', 'I91', 'I89',), "C": ('C950', 'I7', 'I8', 'I5', 'I2', 'I90', 'I9', 'I14', 'I17', 'I12', 'I11', 'I92', 'I82',), "D": ('C1425', 'I121', 'M64', 'M264', 'O128', 'O129',), "Luck 80": ('C950', 'M64', 'M70', 'M73', 'M264', 'O128', 'O129',), "Luck 100": ('C950', 'I121', 'M73', 'M70', 'M166', 'M264',)},  # incomplete
    (31, 1): {"A": ('I6',), "B": ('I4',), "C": ('I91',)},  # incomplete
    (31, 2): {"A": ('C525',), "B": ('C525',), "C": ('I5',)},  # incomplete
    (31, 3): {"A": ('C525',), "B": ('I4',), "C": ('I4',)},  # incomplete
    (32, 10): {"A": ('C525',), "B": ('C525',), "C": ('I91',), "Luck 80": ('M63',), "Luck 100": ('I26',)},  # incomplete
    (34, 10): {"Luck 100": ('O455',)},  # incomplete
    (35, 8): {"A": ('C650', 'I3', 'I83', 'I46', 'I91', 'I90', 'I1', 'I106', 'I105', 'I2', 'I82',), "B": ('C650', 'I83', 'I7', 'I92', 'I91', 'I90', 'I1', 'I106', 'I105', 'I2',), "C": ('C1300', 'I5', 'I46', 'I8', 'I105',), "D": ('C1950', 'I20', 'O128', 'M67', 'M210', 'M211',), "Luck 80": ('C1300', 'O128', 'O129', 'M67',), "Luck 100": ('C1300', 'I19', 'I18', 'O128', 'O129', 'M67', 'M210',)},
    (36, 1): {"A": ('I83',), "B": ('C650',), "C": ('C1300',), "Luck 80": ('C1300',), "Luck 100": ('C1300',)},  # incomplete
    (36, 2): {"A": ('I5',), "B": ('C650',), "D": ('O128',), "Luck 80": ('O128',), "Luck 100": ('C1300',)},  # incomplete
    (36, 3): {"A": ('C650',), "B": ('I2',), "C": ('I89',), "D": ('M71',), "Luck 80": ('M202',), "Luck 100": ('M202',)},
    (36, 4): {"A": ('I82',), "B": ('C650',), "D": ('M68',), "Luck 80": ('M63',), "Luck 100": ('O129',)},  # incomplete
    (36, 5): {"A": ('I10',), "B": ('I5',), "C": ('I83',), "Luck 80": ('M71',), "Luck 100": ('M71',)},  # incomplete
    (36, 6): {"A": ('I1',), "B": ('C600', 'I1',), "C": ('C1300',), "D": ('M202',), "Luck 80": ('M63',), "Luck 100": ('O129',)},
    (36, 7): {"A": ('C650',), "B": ('C650',), "C": ('C1300',), "Luck 80": ('M63',), "Luck 100": ('O129',)},  # incomplete
    (36, 8): {"A": ('I82',), "B": ('I7',), "C": ('C1300',), "Luck 80": ('C1300',), "Luck 100": ('M63',)},  # incomplete
    (36, 9): {"A": ('I6',), "B": ('I7',), "C": ('I106',), "Luck 80": ('C1300',), "Luck 100": ('M68',)},  # incomplete
    (36, 10): {"A": ('C650', 'I2', 'I89', 'I105', 'I3', 'I6',), "B": ('C650', 'I10', 'I1', 'I89', 'I105', 'I91', 'I5', 'I2',), "C": ('C1300', 'I89', 'I8', 'I90', 'I4', 'I2', 'I106',), "D": ('C1950', 'I137', 'M68',), "Luck 80": ('C1300', 'M63', 'M68', 'M202', 'O128',), "Luck 100": ('C1300', 'I137', 'M63', 'M68', 'O128', 'O129',)},
}

#: **Community record, and the reason the story table above reads as the whole
#: of it.** The fourteen Strikes Back families document their chests through a
#: wiki *template* rather than an inline table: each page carries only
#:
#:     {{Luck Treasure Chests/Strikes Back
#:     |monster = 8-Bit Golem
#:     |omicron = 8-Bit Golem O
#:     |omicron2 = 8-Bit Golem OII
#:     |other omicron = S'naip OII
#:     }}
#:
#: and the template expands that into the three per-quest tables. Both earlier
#: scrapes searched the rendered shapes a story page uses -- the
#: `=== Luck Treasure Chests ===` heading, then the table's own
#: `!Chest !! Possible Rewards` header row -- and a page whose chest section
#: holds one template invocation has neither. Fourteen families were therefore
#: read as undocumented by a search that was looking at the right pages.
#:
#: Every family passes the same four names and no page overrides a single tier,
#: so the pools are generated here from those names exactly as the record
#: generates its own tables. Transcribing forty-two expanded tables by hand
#: would introduce a class of error the source does not have.
#:
#: All fifty-six names resolved by exact match against the operator's own
#: decoded `ChrDatabase` and Companion tables, after collapsing whitespace --
#: the master data itself carries double-space typos (`Marilith  Kino L`,
#: `Bahamut Kino  OII`), and the wiki and the master data disagree over Latin
#: `O` versus Greek Omicron in the Companion suffixes. The fourteen recruits
#: are a second, structural check on that join: the record names each one
#: `<monster> L`, and every ID matched is flagged `is_lambda` in the client's
#: own catalog. Chapter 8006 is a third: 897 is the character a physical
#: client's duplicate result independently identified.
#:
#: **Two tiers of every one of these stages are recorded and not encodable, so
#: each row is incomplete.** A and B pay a *quantity* of the run's event item
#: -- 8 or 18 Animata items at A, 20 or 60 at B, rising through the later
#: quests -- and neither half of that survives the trip. A slot in this wire
#: form is one reward with no count, and "the run's event item" was not one
#: item: the record's own schedule shows it rotating across eight Animata
#: items over the event's twenty-odd runs, and nothing in the archive fixes
#: which one a family carries. Encoding a single copy of a guessed item would
#: misstate a figure the record does state, which is worse than leaving the
#: tier empty. C is different and is filled: it names two item *classes* with
#: no quantity at all, so one copy is the record read literally rather than a
#: figure thrown away.
STRIKES_BACK_CHEST_ITEMS: tuple[str, ...] = (
    # Category:Weapon-type items -- Terra Swordsteel, Spearbronze, Bowstring, Staffwood.
    'I9', 'I10', 'I11', 'I12',
    # Category:Attribute-type items -- the ten Rings.
    'I13', 'I14', 'I15', 'I16', 'I17', 'I46', 'I122', 'I123', 'I164', 'I165',
)

#: The Companion the template names bare in every family's Luck 80 and Luck 100
#: chest. `Metal Minion L` (129) and `LL` (130) are separate Companions the
#: record does not name here, so only the base one is granted.
_METAL_MINION = 'O128'

#: ``(chapter, recruit, omicron, omicron2, other omicron)`` -- the four names
#: each family hands the record's template, resolved to IDs. The wiki revision
#: each row was read at is in the trailing comment.
STRIKES_BACK_FAMILY_REWARDS: tuple[tuple[int, int, int, int, int], ...] = (
    (8000, 853, 282, 317, 310),   # Spinetrich Kino, Sh'berdan OII (rev 83438)
    (8001, 855, 283, 340, 325),   # Kraken Kino, Zavison OII (rev 83437)
    (8002, 859, 285, 318, 330),   # Slugosaur Kino, Myne OII (rev 83423)
    (8003, 857, 284, 336, 332),   # Tiamat Kino, Mizell OII (rev 83454)
    (8004, 899, 288, 321, 315),   # 8-Bit Orbling, Burbaba OII (rev 83439)
    (8005, 895, 286, 319, 316),   # 8-Bit Spinetrich, Kem OII (rev 83422)
    (8006, 897, 287, 320, 322),   # 8-Bit Golem, S'naip OII (rev 83453)
    (8007, 901, 289, 335, 314),   # 8-Bit Hiso Alien, Amina OII (rev 83466)
    (8012, 965, 297, 298, 351),   # Lich Kino, Sha'plar OII (rev 83455)
    (8013, 967, 299, 300, 349),   # Marilith Kino, Bahl OII (rev 83467)
    (8014, 969, 301, 302, 341),   # Mechanic Kino, Eileen OII (rev 83479)
    (8015, 992, 391, 392, 343),   # Odin Kino, Okklitot OII (rev 83481)
    (8016, 1014, 400, 401, 337),  # Bahamut Kino, Daiana OII (rev 83468)
    (8017, 1016, 402, 403, 353),  # Leviathan Kino, A'merpact OII (rev 83480)
)


def _strikes_back_pools() -> dict[tuple[int, int], dict[str, tuple[str, ...]]]:
    """Expand the record's own template into a pool per stage and tier.

    The three quests a family documents are its sections 1, 2 and 3, matched by
    the stamina the record states for each -- 5, 10 and 15, which is exactly
    what `_counter_descent_stamina` serves. Chapters 8000--8007 carry a fourth
    section at 15 stamina that the record documents no quest for; it is left
    out rather than given the third quest's table, because a section the record
    never covered is not a section it covered identically.

    The ladder through the three quests is the record's, and it is the whole
    reason the Companions a player remembers these quests for are hard to
    reach: the second `OII` Companion appears only at Luck 100 of quest II,
    and the family's own `O`, its `OII` and the guest `OII` appear together
    only at Luck 100 of quest III -- one tier, of one quest, at 100.0 Luck.
    """
    pools: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {}
    for chapter, recruit, omicron, omicron2, other in STRIKES_BACK_FAMILY_REWARDS:
        character = f'M{recruit}'
        pools[(chapter, 1)] = {
            "C": STRIKES_BACK_CHEST_ITEMS,
            "D": (character,),
            "Luck 80": (character, _METAL_MINION),
            "Luck 100": (character, _METAL_MINION),
        }
        pools[(chapter, 2)] = {
            "C": STRIKES_BACK_CHEST_ITEMS,
            "D": (character,),
            "Luck 80": (character, _METAL_MINION),
            "Luck 100": (character, f'O{omicron2}', _METAL_MINION),
        }
        pools[(chapter, 3)] = {
            "C": STRIKES_BACK_CHEST_ITEMS,
            "D": (character,),
            "Luck 80": (character, f'O{omicron2}', _METAL_MINION),
            "Luck 100": (
                character, f'O{omicron}', f'O{omicron2}', f'O{other}', _METAL_MINION,
            ),
        }
    return pools


#: The Strikes Back half, expanded. Kept separate from `LUCK_CHEST_POOLS`
#: because only the story table may donate to an undocumented stage: chapter
#: numbers are a progression inside the story and an address space outside it,
#: so "the nearest documented chapter" means something for Chapter 10 and
#: nothing for Chapter 8006. See `luck_pool_interpolation.donor_chapters`.
STRIKES_BACK_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = (
    _strikes_back_pools()
)

#: Every stage the record documents, from both halves. Nothing keyed here is
#: interpolated, and a tier absent from a stage that appears here is the record
#: paying nothing rather than a gap to fill.
DOCUMENTED_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {
    **LUCK_CHEST_POOLS, **STRIKES_BACK_CHEST_POOLS,
}


#: **Community record, and the one statement here that refuses rather than
#: pays.** The Luck page names eleven quests that carry no Luck Treasure Chest
#: at all. It is a *primary* claim about the feature, on the page that
#: documents the feature, and it outranks a per-quest page: `The Hunt For
#: Joker` appears on this list and also carries the Daily Quest chest template
#: on its own page, which is the boilerplate every Daily Quest page carries
#: rather than a statement about that quest.
#:
#: Most of these were already silent because their family authors no chest.
#: Four were not: Hunting the Jade Dragon, Mobius Final Fantasy, The Captive
#: Golem and Vengeful Heart are event-catalog stages, and once event starts
#: began rolling against the interpolated pools they started paying chests the
#: record says they never had. That is what this list corrects.
#:
#: Keyed by chapter because every listed quest excludes all of its sections.
NO_CHEST_CHAPTERS: frozenset[int] = frozenset({
    1001,   # Pudding Time -- Hunting Zone
    1002,   # Tin Parade -- Hunting Zone
    1004,   # Puppet Show -- Hunting Zone
    1200,   # Dragon Road
    2004,   # Hunting the Jade Dragon
    2005,   # Mobius Final Fantasy, and Mobius Final Fantasy Strike
    2008,   # The Captive Golem
    2014,   # Vengeful Heart -- recorded here as `vengeful_vision_archive`
    3000,   # Metal Zones
    3002,   # Attack of the Coin Creeps -- Hunting Zone
    3004,   # Crystal Road -- listed on its own and as a Hunting Zone
    6012,   # The Hunt For Joker
    7000,   # Orbling Cavern
    7010,   # Cryptid Forest
})


def refuses_chest(chapter: int) -> bool:
    """Whether the record says this chapter carries no chest at all.

    Distinct from having no documented pool. An undocumented stage is a gap the
    record leaves and interpolation may fill; a listed one is the record
    stating an absence, so nothing derived fills it.

    An explicit `--luck-pool-catalog` still overrides it, for the same reason
    it overrides everything else here: naming a stage in that file is an
    operator deciding to go past the record, and this list is the record.
    """
    return chapter in NO_CHEST_CHAPTERS


def pool_for(chapter: int, section: int, tier: str) -> tuple[str, ...]:
    """Return one stage-and-tier reward pool, empty when undocumented."""
    if refuses_chest(chapter):
        return ()
    return DOCUMENTED_CHEST_POOLS.get((chapter, section), {}).get(tier, ())


def has_documented_pool(chapter: int, section: int) -> bool:
    """Whether this stage has any documented chest contents at all."""
    if refuses_chest(chapter):
        return False
    return bool(DOCUMENTED_CHEST_POOLS.get((chapter, section)))
