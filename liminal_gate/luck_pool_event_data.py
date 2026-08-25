"""The chest pools the record documents for events and the two side worlds.

Split from :mod:`liminal_gate.luck_pool_data`, which keeps the core story, for
a reason that is load-bearing rather than tidy: **only a story chapter may
donate to an undocumented stage.** Interpolation brackets a silent chapter
between the documented ones above and below it, which is a claim about chapter
numbers being a progression -- true inside the story, and false the moment the
Eidolons sit at 4100 and Strikes Back at 8000. Keeping the two tables apart is
what lets `pool_for` answer from both while `donor_chapters` reads only one.

Four families are recovered here, and all four were missed by the same thing.
The story pools were scraped by searching for the *rendered* shape a story page
uses -- a `=== Luck Treasure Chests ===` heading, then the table's own
`!Chest !! Possible Rewards` header row. An event page has neither. It carries
a template invocation, and the wiki expands that into the tables. Fourteen
Strikes Back families, twelve Eidolons, ten Daily Quests and thirty side-world
stages were all read as undocumented by searches looking straight at them.

Where the record is itself a template, so is this module: the pools are
composed from the same parameters each page hands its template rather than
transcribed from the expanded tables. That is not a shortcut. Transcribing
ninety-six expanded tables by hand introduces a class of error the source does
not have, and every composition here was checked against the wiki's own
expansion of the same invocation, tier for tier.

**Names were resolved against the operator's own decoded tables**, and two
hazards are handled rather than hoped over. Whitespace is collapsed, because
the master data carries double-space typos (`Marilith  Kino L`,
`Bahamut Kino  OII`) and the wiki disagrees with it over Latin `O` versus Greek
Omicron in Companion suffixes. And a name is resolved by *name* whenever it is
unique across the three tables, falling back to the record's own icon size --
items render at 20px and characters and Companions at 50px -- only to break a
tie. Eight names are both an item and a Companion, Masamune and Trident among
them, so resolving by name alone would silently return the wrong one; one name,
`Vajra`, is both an item and a character, and the record disambiguates it in
the page text.
"""

from __future__ import annotations

#: The four item classes the record links rather than enumerates, as the
#: operator's own decoded `ItemSet` resolves them. A class carries no quantity
#: on any page that names one, so one copy per slot is the record read
#: literally rather than a figure discarded.
SPECIES_TYPE_ITEMS: tuple[str, ...] = (
    'I3', 'I83', 'I5', 'I7', 'I92', 'I91', 'I89', 'I6',
    'I90', 'I1', 'I8', 'I4', 'I106', 'I105', 'I2', 'I82',
)
WEAPON_TYPE_ITEMS: tuple[str, ...] = ('I9', 'I10', 'I11', 'I12')
ATTRIBUTE_TYPE_ITEMS: tuple[str, ...] = (
    'I16', 'I13', 'I123', 'I46', 'I14', 'I15', 'I165', 'I122', 'I164', 'I17',
)
POWER_UP_ITEMS: tuple[str, ...] = (
    'I56', 'I54', 'I55', 'I166', 'I172', 'I167', 'I180', 'I53',
)

#: Cipher Cell, which the Eidolon template excludes from the species class by
#: the material's own name: "Species-type items (except Oxsecian)".
_OXSECIAN = 'I83'
SPECIES_TYPE_ITEMS_EXCEPT_OXSECIAN: tuple[str, ...] = tuple(
    item for item in SPECIES_TYPE_ITEMS if item != _OXSECIAN
)


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
STRIKES_BACK_CHEST_ITEMS: tuple[str, ...] = WEAPON_TYPE_ITEMS + ATTRIBUTE_TYPE_ITEMS

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


#: The Strikes Back half, expanded.
STRIKES_BACK_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = (
    _strikes_back_pools()
)


#: **Community record, through `Template:Luck Treasure Chests/Eidolon`.** Each
#: Eidolon page hands that template a `stages` count and the names its tables
#: are built from, and the count is exactly the section this archive serves:
#: the client's own BattleData gives a three-stage Eidolon sections 1, 2 and 3
#: and puts a battle in section 3 alone, so the served stage is the third
#: quest, and a one-stage Eidolon's is its only one. Twelve families, twelve
#: agreements -- the record's `stages` equals the section number in every case.
#:
#: Only the served table's parameters are carried. The first and second quests
#: of a three-stage family have tables on the page and no battle behind them,
#: so there is no stage here for those pools to attach to.

#: The eight families whose served stage is the third quest, as
#: ``(chapter, item3, companion3, omicron3, unique1, unique2)``. The two
#: `unique` rewards are the Eidolon's own Companion and its Lambda or Z form,
#: and for Bahamut, Odin and Leviathan *both* are Companions rather than one of
#: each -- which is why they are resolved rather than assumed.
EIDOLON_THIRD_QUEST_REWARDS: tuple[tuple[int, str, str, str, str, str], ...] = (
    (4100, 'I73', 'O86', 'O325', 'O358', 'M943'),   # Artemis (rev 79828)
    (4101, 'I77', 'O30', 'O331', 'O359', 'M964'),   # Chaos (rev 79829)
    (4102, 'I71', 'O84', 'O324', 'O361', 'M963'),   # Valkyrie (rev 79830)
    (4104, 'I76', 'O24', 'O326', 'O365', 'M994'),   # Raijin (rev 79833)
    (4105, 'I79', 'O2', 'O345', 'O366', 'M995'),    # Phoenix (rev 79832)
    (4107, 'I74', 'O12', 'O311', 'O385', 'O386'),   # Bahamut (rev 79835)
    (4108, 'I72', 'O85', 'O313', 'O408', 'O409'),   # Odin (rev 79836)
    (4109, 'I75', 'O18', 'O312', 'O425', 'O426'),   # Leviathan (rev 80566)
)

#: The four whose served stage is their only one, as ``(chapter, item1, item2,
#: item3, companion1, companion2, companion3, omicron1, unique1, unique2)``.
#:
#: Selene carries the literal word `Companion` where its second Companion and
#: its Omicron belong -- the template's own placeholder, left unfilled by an
#: editor rather than naming a reward. Those two are empty here and the row is
#: incomplete; the alternative is inventing the one reward the record declined
#: to name.
EIDOLON_SINGLE_QUEST_REWARDS: tuple[tuple[int, str, str, str, str, str, str, str, str, str], ...] = (
    (4103, 'I60', 'I70', 'I78', 'O189', 'O141', 'O50', 'O341', 'O364', 'M945'),   # Lamia (rev 79831)
    (4106, 'I60', 'I64', 'I140', 'O88', 'O166', 'O167', 'O343', 'O360', 'M939'),  # King Orbling (rev 79834)
    (4110, 'I59', 'I173', 'I174', 'O174', 'O170', 'O449', 'O327', 'O448', 'M1174'),  # Apollo (rev 82121)
    (4111, 'I60', 'I178', 'I179', 'O175', '', 'O483', '', 'O482', 'M1239'),       # Selene (rev 82995)
)


def _present(*rewards: str) -> tuple[str, ...]:
    """Drop the slots a page left unnamed, keeping the record's own order."""
    seen: list[str] = []
    for reward in rewards:
        if reward and reward not in seen:
            seen.append(reward)
    return tuple(seen)


def _eidolon_pools() -> dict[tuple[int, int], dict[str, tuple[str, ...]]]:
    """Expand the Eidolon template into the one stage each family serves."""
    pools: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {}
    for chapter, item, companion, omicron, unique1, unique2 in EIDOLON_THIRD_QUEST_REWARDS:
        pools[(chapter, 3)] = {
            "A": ('C600',) + SPECIES_TYPE_ITEMS_EXCEPT_OXSECIAN,
            "B": ('C600',) + SPECIES_TYPE_ITEMS_EXCEPT_OXSECIAN,
            "C": _present('C1200', item),
            "D": _present(unique1, unique2),
            "Luck 80": _present('C1500', item, companion),
            "Luck 100": _present(item, unique1, unique2, omicron),
        }
    for row in EIDOLON_SINGLE_QUEST_REWARDS:
        chapter, one, two, three, first, second, third, omicron, unique1, unique2 = row
        pools[(chapter, 1)] = {
            "A": ('C250',) + SPECIES_TYPE_ITEMS_EXCEPT_OXSECIAN,
            "B": ('C250',) + SPECIES_TYPE_ITEMS_EXCEPT_OXSECIAN,
            "C": _present('C500', one, two, three),
            "D": _present(unique1, unique2),
            "Luck 80": _present('C725', one, two, three, first, second),
            "Luck 100": _present(unique1, unique2, second, third, omicron),
        }
    return pools


EIDOLON_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = _eidolon_pools()

#: **Community record.** The one archived Special Quest whose page carries a
#: chest table of its own rather than through a family template.
#:
#: `A Chance Encounter With Sarah` is chapter 2018, and the join is confirmed
#: from the client rather than from the title: the table's own recruit resolves
#: to character 1288, which is the character 2018's recovered manifest
#: associates with the event. Its page marks the list incomplete itself.
ARCHIVE_SPECIAL_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {
    # rev 84085. Sarah, and the base and Lambda Metal Minion Companions.
    (2018, 1): {
        "A": ('C300',), "B": ('I90',), "C": ('I6',),
        "D": ('M1288', 'O129'),
        "Luck 80": ('O128',),
        "Luck 100": ('M1288', 'O128', 'O129'),
    },  # incomplete
}


#: **Community record, through `Template:Luck Treasure Chests/Daily Quest`.**
#: Every Daily Quest page invokes one template that supplies the same base
#: table and takes per-quest additions, so the base is carried once here and
#: the additions per chapter.
#:
#: Ten of the fourteen Daily Quest stages are covered. Particle Hoarder Horde
#: and both Yamamoto Puzzle Quests have no chest page at all. The Hunt For
#: Joker has one and is excluded anyway: it is named on the Luck page's own
#: list of chestless quests, and a page-level template every Daily Quest page
#: carries does not outrank the mechanic's own page naming the quest. See
#: `luck_pool_data.NO_CHEST_CHAPTERS`.
#:
#: The per-quest additions corroborate constants this project already
#: recovered from the client's enemy records rather than from the record:
#: Crystal Roundelay's four power-ups, Rarity Rumble's four Ores, Tearjerker
#: Time's four Tears and Hidden Stars' four Stars are the same sets
#: :mod:`liminal_gate.daily_quest_data` bounds a clear by.

#: The nine monsters every Daily Quest's C chest may hold, alongside the
#: weapon-type items: Kraken, Lich, Marilith, Tiamat, Celestial Dragon, Onyx
#: Dragon, Vajra, Cryowisp and Pyrowisp. `Vajra` is both an item and a
#: character, and the record disambiguates it in the page text.
DAILY_QUEST_MONSTERS: tuple[str, ...] = (
    'M165', 'M163', 'M164', 'M166', 'M237', 'M238', 'M239', 'M149', 'M150',
)

#: The eight second-form Companions every Daily Quest's D, Luck 80 and Luck
#: 100 chests share: A'merpact, Andelucia, Okklitot, Grace, Korin, Mizell,
#: Lacuma and Ra'prow, each in its `OII` form.
DAILY_QUEST_COMPANIONS: tuple[str, ...] = (
    'O353', 'O323', 'O343', 'O384', 'O339', 'O332', 'O345', 'O355',
)

#: Chapter -> the tiers that quest adds to the shared base, with the wiki
#: revision each was read at.
DAILY_QUEST_CHEST_EXTRAS: dict[int, dict[str, tuple[str, ...]]] = {
    # Metal Runner Rampage (rev 79814): the Helixes, the three Holes, Ether and Elixir.
    6000: {"Luck 80": ('I93', 'I94', 'I132', 'I137', 'I95', 'I96', 'I97', 'I98', 'I99')},
    # Puppet Pandemonium (rev 79815).
    6001: {"Luck 80": ('I93', 'I94', 'I132', 'I137', 'I95', 'I96', 'I97', 'I98', 'I99')},
    # Crystal Roundelay (rev 79810): the four power-ups Crystal Road also accepts.
    6002: {"Luck 80": ('I55', 'I56', 'I53', 'I54')},
    # Hedgehog Hullabaloo (rev 79811).
    6003: {"Luck 80": ('I93', 'I94', 'I132', 'I137', 'I95', 'I96', 'I97', 'I98', 'I99')},
    # Rarity Rumble (rev 79816): the four Ores its enemy records name.
    6005: {"Luck 80": ('I26', 'I27', 'I28', 'I29')},
    # Sweet Temptation (rev 79817).
    6006: {"Luck 80": ('I93', 'I94', 'I132', 'I137', 'I95', 'I96', 'I97', 'I98', 'I99')},
    # Tropical Haze (rev 80043): the only quest that adds to a tier other than
    # Luck 80, and it adds the same three tickets to both.
    6007: {"D": ('I50', 'I81', 'I112'), "Luck 80": ('I50', 'I81', 'I112')},
    # Tearjerker Time (rev 79818): the four Tears.
    6008: {"Luck 80": ('I18', 'I19', 'I20', 'I21')},
    # Hidden Stars (rev 79812): the four Stars.
    6009: {"Luck 80": ('I118', 'I119', 'I120', 'I121')},
    # Lucky Orbling (rev 79813).
    6010: {"Luck 80": ('I93', 'I94', 'I132', 'I137', 'I95', 'I96', 'I97', 'I98', 'I99')},
}


def _daily_quest_pools() -> dict[tuple[int, int], dict[str, tuple[str, ...]]]:
    """Compose the shared base with each quest's own additions."""
    materials = SPECIES_TYPE_ITEMS + WEAPON_TYPE_ITEMS + ATTRIBUTE_TYPE_ITEMS
    base = {
        "A": materials,
        "B": materials,
        "C": DAILY_QUEST_MONSTERS + WEAPON_TYPE_ITEMS,
        "D": DAILY_QUEST_COMPANIONS,
        "Luck 80": DAILY_QUEST_COMPANIONS,
        "Luck 100": DAILY_QUEST_COMPANIONS,
    }
    return {
        (chapter, 1): {
            tier: _present(*pool, *extras.get(tier, ()))
            for tier, pool in base.items()
        }
        for chapter, extras in DAILY_QUEST_CHEST_EXTRAS.items()
    }


DAILY_QUEST_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = (
    _daily_quest_pools()
)


#: **Community record.** The two secondary world maps, which the record
#: documents per stage rather than through a template, so these are
#: transcribed tables rather than composed ones.
#:
#: `The Death of Shay and Arionne` is the BreaSoul map. The identification is
#: structural on both sides: the page describes a scenario with its own World
#: Map and five chapters opening after Chapter 25, the client's
#: `IsWorld1ChangeEnable` opens BreaSoul at section 26-1, and the page's parts
#: come to 4, 5, 5, 5 and 1 -- the exact section counts of chapters 100 to 104.
#: Its author is Yasumi Matsuno, which is what the client's own map flag
#: `sp_matsuno` is named for.
#:
#: One table on that page sits outside any quest's rewards block, after Chapter
#: 2's fifth part already has one. It is an editor's leftover rather than a
#: twenty-first stage, so each part takes the first table that follows it and
#: the orphan is dropped.
BREASOUL_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {
    # Ch 1: The Rusty Swordsman
    (100, 1): {"A": ('I8',), "B": ('C500',), "Luck 80": ('C1000',), "Luck 100": ('O129',)},
    (100, 2): {"A": ('I8',), "B": ('I7',), "D": ('I169',), "Luck 80": ('I119',), "Luck 100": ('O129',)},
    (100, 3): {"A": ('I4',), "B": ('I90',), "Luck 80": ('I119',), "Luck 100": ('I169',)},
    (100, 4): {"A": ('I1',), "B": ('I92',), "Luck 80": ('I119',), "Luck 100": ('C1000',)},
    # Ch 2: Heading North
    (101, 1): {"A": ('C500',), "B": ('I92',), "C": ('I8',), "D": ('I118',), "Luck 80": ('O128',), "Luck 100": ('O128',)},
    (101, 2): {"A": ('I9', 'I90'), "B": ('I1', 'I4'), "C": ('C1000',), "D": ('I119',), "Luck 80": ('C1000', 'O128'), "Luck 100": ('C1000',)},
    (101, 3): {"A": ('C500',), "B": ('I6',), "Luck 80": ('O128',), "Luck 100": ('C1000',)},
    (101, 4): {"A": ('I4',), "B": ('I83',), "Luck 80": ('C1000',), "Luck 100": ('O129',)},
    (101, 5): {"A": ('C500',), "B": ('I83',), "C": ('C1000',), "Luck 80": ('O129',), "Luck 100": ('I169',)},
    # Ch 3: The Western Sorceress
    (102, 1): {"A": ('I83',), "B": ('C500',), "Luck 80": ('C1000',), "Luck 100": ('C1000',)},
    (102, 2): {"A": ('C500', 'I4', 'I89'), "B": ('C500', 'I2'), "C": ('C1000', 'I82'), "D": ('I119',), "Luck 80": ('C1000', 'O128'), "Luck 100": ('C1000', 'O128')},
    (102, 3): {"A": ('C500',), "B": ('I2',), "D": ('O129',), "Luck 80": ('C1000',), "Luck 100": ('C1000',)},
    (102, 4): {"A": ('C500',), "B": ('I89',), "C": ('I46',), "D": ('O128',), "Luck 80": ('C1000',), "Luck 100": ('O128',)},
    (102, 5): {"A": ('I4',), "B": ('I92',), "C": ('C1000',), "Luck 80": ('I119',), "Luck 100": ('C1000',)},
    # Ch 4: The Executioner
    (103, 1): {"A": ('C500',), "B": ('C500',), "C": ('I1',), "Luck 80": ('C1000',), "Luck 100": ('O128',)},
    (103, 2): {"A": ('C500',), "B": ('C500',), "C": ('C1000',), "D": ('O129',), "Luck 80": ('O129',), "Luck 100": ('O128',)},
    (103, 3): {"A": ('C500',), "B": ('I6',), "C": ('I7',), "Luck 80": ('I118',), "Luck 100": ('O129',)},
    (103, 4): {"A": ('I6', 'I46'), "B": ('C500', 'I91'), "C": ('C1000', 'I46'), "D": ('I171',), "Luck 80": ('I118',), "Luck 100": ('I169', 'O129')},
    (103, 5): {"A": ('I8',), "B": ('C500',), "Luck 80": ('I119',), "Luck 100": ('I170',)},
    # Ch 5: Murderous Angel Morgana
    (104, 1): {"A": ('C500', 'I1', 'I2', 'I4', 'I8', 'I7', 'I90', 'I83', 'I46'), "B": ('C500', 'I9', 'I12', 'I7', 'I90', 'I89'), "C": ('C1000', 'I12'), "D": ('I169',), "Luck 80": ('C1000', 'I119', 'I118', 'O128', 'O129'), "Luck 100": ('M1158', 'I169', 'I170')},
}

#: `Ultimate Five` is the Five Emperors map, and the page's order is confirmed
#: against the client rather than assumed. The five normal-mode sections name
#: the same first-clear Companion the recovered `dropBuddies` manifest gives
#: chapters 110 to 114, and the five hard-mode sections the same for 115 to
#: 119 -- ten agreements, including both members of every two-candidate
#: manifest.
FIVE_EMPERORS_CHEST_POOLS: dict[tuple[int, int], dict[str, tuple[str, ...]]] = {
    (110, 1): {"A": ('I106', 'I3'), "B": ('I7',), "D": ('O434', 'C2000'), "Luck 80": ('O465', 'O464'), "Luck 100": ('O465', 'O130')},  # Garuda
    (111, 1): {"A": ('I90', 'I8', 'I122'), "B": ('I4', 'I6', 'I122'), "C": ('O128',), "D": ('C2000', 'O475'), "Luck 80": ('O463', 'O129'), "Luck 100": ('O463', 'O475')},  # Gatekeeper
    (112, 1): {"A": ('I90',), "B": ('I7',), "C": ('C1250',), "D": ('O474',), "Luck 80": ('C2000',), "Luck 100": ('O461',)},  # Quyat
    (113, 1): {"A": ('I1',), "B": ('I106',), "C": ('O466',), "Luck 80": ('O466',), "Luck 100": ('O467',)},  # Apostolos
    (114, 1): {"A": ('I8', 'I2', 'I82', 'I90'), "B": ('C750', 'I105', 'I3', 'I11'), "C": ('C1250', 'O128', 'O48'), "D": ('I161', 'I162'), "Luck 80": ('C2000', 'O68', 'O129'), "Luck 100": ('I161', 'I162', 'O68', 'O130')},  # Agartha
    (115, 1): {"C": ('O464',), "D": ('O477',), "Luck 80": ('O476', 'O477', 'O465'), "Luck 100": ('O476', 'O477')},  # Garuda, hard
    (116, 1): {"A": ('I83',), "B": ('I83',), "D": ('C3000',), "Luck 80": ('O129',), "Luck 100": ('O477',)},  # Gatekeeper, hard
    (117, 1): {"A": ('I123', 'I106', 'I105', 'I89', 'I7', 'I6'), "B": ('C1000', 'I2', 'I105', 'I89', 'I7', 'I91', 'I4'), "C": ('C2000', 'O128'), "D": ('C3000',), "Luck 80": ('O476', 'O129', 'O461'), "Luck 100": ('O476', 'O477')},  # Quyat, hard
    (118, 1): {"D": ('C3000',), "Luck 80": ('O476',), "Luck 100": ('O130',)},  # Apostolos, hard
    (119, 1): {"A": ('I2', 'I8'), "B": ('I9', 'I12'), "Luck 80": ('O72',), "Luck 100": ('I163', 'O72')},  # Agartha, hard
}
