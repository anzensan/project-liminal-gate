"""Validate local event stages and provide the bounded Counter Descent policy."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

from liminal_gate.event_flag_data import event_flags_for
from liminal_gate.event_manifest_data import (
    EVENT_MANIFEST_ROWS,
    SECTION_CLASS_LIMITS,
    STANDING_SPECIAL_MANIFEST_ROWS,
)


def _character_classes(characters: object) -> dict[int, int]:
    """Map character ID to class from a local character catalog document."""
    if not isinstance(characters, dict):
        return {}
    return {
        row["character_id"]: row["rarity"]
        for row in characters.get("characters", [])
        if isinstance(row, dict)
        and type(row.get("character_id")) is int
        and type(row.get("rarity")) is int
    }


DEFAULT_EVENT_CATALOG = "event-catalog.json"

#: The chapters this client treats as Raid quests, whatever family a server
#: advertises there. Recovered as literals from `ChapterInterface..cctor`
#: (ARM64 `0xD0741C`), which writes `RaidQuestChapter` at static offset 0x54 and
#: `RaidQuestEndChapter` at 0x58; Tower of Temptation is the *next* range,
#: 9010--9099, and Melting Pot's Donation range follows at 9100--9199. See
#: `EventCatalog.raid_quest_params` for what the range costs a server that
#: advertises inside it.
RAID_QUEST_CHAPTER = 9000
RAID_QUEST_END_CHAPTER = 9009

#: `UISpecialItem.RaidStatus.Subjugating`. The enum is `Lock` 1, `Subjugating`
#: 2, `Overkilling` 3, `Completed` 4; the start path refuses 1 and 4, so this is
#: the plainest of the two that pass.
RAID_STATUS_SUBJUGATING = 2


class EventCatalogError(ValueError):
    """A user-local event catalog is malformed."""


@dataclass(frozen=True)
class EventStage:
    event_id: str
    flag: str
    chapter: int
    section: int
    stamina: int
    coins: int
    clear_coins: int
    character_ids: tuple[int, ...]
    summon_ids: tuple[int, ...] = ()
    selector: str = "special"
    unlock_after_chapter: int | None = None
    #: Settle this stage's clear from the drops the client reports, projected by
    #: the server, because no reward table for it was ever recovered. Counter
    #: Descent is the only family that carries it; see `_projected_event_items`.
    projected_rewards: bool = False
    selector_id: str | None = None
    #: The class band this section admits, or `(0, 0)` for the stages that
    #: declare none -- which is every section in the game but Captive Golem's
    #: four. Recovered; see `SECTION_CLASS_LIMITS`.
    class_min: int = 0
    class_max: int = 0

    def identity_label(self) -> str:
        return f"{self.chapter}-{self.section}"

    def admits_class(self, character_class: int) -> bool:
        """Whether a character of this class may enter the section."""
        if not self.class_max:
            return True
        return self.class_min <= character_class <= self.class_max

    def unlocked_at(self, progress_code: int | None) -> bool:
        if self.unlock_after_chapter is None:
            return True
        if progress_code is None:
            return False
        current_chapter = (progress_code & 0xFFFF) >> 6
        completed_chapter = max(0, current_chapter - 1)
        return completed_chapter >= self.unlock_after_chapter


@dataclass(frozen=True)
class EventCatalog:
    stages: tuple[EventStage, ...]
    #: Character ID to class, from the same local character catalog the stages
    #: were validated against. Only the class-limited sections read it, and an
    #: empty map disables the check rather than barring an unknown character.
    character_classes: dict[int, int] | None = None

    def by_identity(self) -> dict[tuple[int, int], EventStage]:
        return {(stage.chapter, stage.section): stage for stage in self.stages}

    def over_class_limit(self, stage: EventStage, party: object) -> bool:
        """Whether a party names a character the stage's class band excludes.

        A character the local catalog does not describe is not refused: this
        gate exists to restore a declared limit, not to invent one for state it
        cannot read.
        """
        if not stage.class_max or not self.character_classes or not isinstance(party, list):
            return False
        return any(
            not stage.admits_class(self.character_classes[member])
            for member in party
            if type(member) is int and member in self.character_classes
        )

    def flags(self, progress_code: int | None = None) -> dict[str, dict[str, object]]:
        """Return every `sp_ch_` key the unlocked stages need.

        A folded Counter Descent family is flagged per section and, unlike
        every other family here, **not** by its chapter. That looks backwards
        for a card the client lists by chapter, and it is the only shape that
        works, because `CheckQuestFlag` falls back: an unset
        `sp_ch_<chapter>-<section>` is retried as everything left of its last
        `-`, so one chapter key answers for every section in the chapter.

        The card still lists. `UISpecialSelect.<GetList>` admits a folded row
        when any `IsQuestOpen("<chapter>-<i>")` holds for `i` up to
        `GetSectionCount`, and `UpdateItems` revalidates it the same way each
        frame, so a flagged tier 1 is enough to open the card and keep it.

        What the chapter key would cost is the tiers that do not exist.
        `GetSectionCount` returns the hard-coded five of
        `ChapterInterface.NumOfCounterDescentQuestSections` for the whole
        8000--8999 range, so a three-tier family expands to five rows. For a
        row no section backs, `IsQuestOpen` finds no section and defers to the
        flag alone -- which a chapter key would answer true, offering a tier
        whose stamina and battles do not exist and whose start this server
        refuses. Flagged per section, those two rows fail and are dropped.
        `sp_ch_8001-2`, `-3`, and `-4` survive in the community flag table, so
        the retired service named these sections individually too.
        """
        unlocked = [
            stage for stage in self.stages if stage.unlocked_at(progress_code)
        ]
        names = [
            event_flags_for(stage.chapter, stage.section)[1]
            if stage.selector == "descent_hunting"
            else stage.flag
            for stage in unlocked
        ]
        return {name: {"name": name, "value": True} for name in names}

    def raid_quest_params(self, progress_code: int | None = None) -> dict[str, dict[str, object]]:
        """Return the `eventQuestParams` entry every advertised raid-range stage needs.

        Chapters 9000--9009 are **Raid quests** to this client, whatever the
        family a server advertises there. `ChapterInterface..cctor`
        (ARM64 `0xD0741C`) writes the ranges as literals:
        `CounterDescentQuestChapter` 8000--8999, `RaidQuestChapter`
        9000--**9009**, `TowerOfTemptationChapter` 9010--9099, and
        `DonationQuestChapter` 9100--9199. Tower of Temptation is served from
        9000--9003 because those are the copies carrying compiled chapter
        programs and retained banners -- so every Tower card lands in the raid
        range, and the range decides the start path rather than the family does.

        `UISpecialSelect2.StartSpecial` (`0xF82590`) asks
        `ChapterInterface.IsRaidQuest(chapter)` first, and for a raid chapter it
        reads `EventManager.GetRaidQuestStatus("<chapter>-<section>")`
        (`0xD96EC0`), which is `GetQuestParam(id)["status"]` over the
        `eventQuestParams` object the login response carries. With the key
        unsent the lookup misses and the accessor returns
        `UISpecialItem.RaidStatus.Lock` (1), which raises
        "You don't meet the requirements to unlock this quest" and stops the
        start before any request leaves the device. That is a refusal no server
        log can show, because the client never asks.

        `Subjugating` (2) is the plainest open state the enum has -- `Lock` (1)
        and `Completed` (4) are the two the start path refuses, and
        `Overkilling` (3) claims a boss already past its threshold. It is a
        local policy rather than a recovered value: what the retired service put
        here is not in any capture, and the client only needs the field to not
        say closed.

        `remainHp` is sent beside it because `GetRaidQuestRemainHp`
        (`0xD96F50`) reads it with LitJson's `double` accessor, which throws on
        an integer rather than converting -- the same trap `jobLevels` and
        `questClearDate` carry. A full bar is the honest value for a boss no
        player has fought on this server.

        No `overkillEndDate` is sent, and its absence is doing real work.
        `UISpecialSelect2.UpdateItems` (`0xF8AE00`) draws the raid countdown and
        HP bar only once that date is present, so withholding it keeps the cards
        rendering as the ordinary quest cards they are, rather than dressing
        them in a live-service schedule this project never recovered.
        """
        return {
            stage.identity_label(): {"status": RAID_STATUS_SUBJUGATING, "remainHp": 1.0}
            for stage in self.stages
            if RAID_QUEST_CHAPTER <= stage.chapter <= RAID_QUEST_END_CHAPTER
            and stage.unlocked_at(progress_code)
        }

    def client_lists(self, progress_code: int | None) -> dict[str, list[str]]:
        """Project Special, Tower, and folded Strikes Back selector rows."""
        special = list(dict.fromkeys(
            stage.selector_id or stage.identity_label()
            for stage in self.stages
            if stage.selector == "special" and stage.unlocked_at(progress_code)
        ))
        tower = [
            stage.identity_label()
            for stage in self.stages
            if stage.selector == "tower" and stage.unlocked_at(progress_code)
        ]
        eidolon = [
            stage.identity_label()
            for stage in self.stages
            if stage.selector == "eidolon" and stage.unlocked_at(progress_code)
        ]
        descent_chapters: dict[int, None] = {}
        for stage in self.stages:
            if (
                stage.selector == "descent_hunting"
                and stage.unlocked_at(progress_code)
            ):
                descent_chapters.setdefault(stage.chapter, None)
        return {
            "specialQuestList": special,
            "towerQuestList": tower,
            "eidolonQuestList": eidolon,
            # Counter Descent is a folded card, and the client folds on the
            # shape of the id alone: `UISpecialSelect.IsFolded` is
            # `!id.Contains("-")`. The bare chapter is therefore the row, and
            # `UISpecialItem.OnClickedBtn` expands it into the tiers
            # `GetSectionCount` declares. A `8000-1` row reads as an ordinary
            # single stage instead, and tapping it starts tier 1 directly --
            # which is what hid every higher tier behind a card that never
            # opened.
            "descentHuntingList": [
                str(chapter) for chapter in descent_chapters
            ],
        }

    def client_list(self) -> list[str]:
        """Compatibility accessor for the normal Special selector."""
        return self.client_lists(None)["specialQuestList"]


#: Chapters 8000--8007 carry a fifth section in `BattleData`, with a real
#: battle and 15 stamina like the two before it, and this policy used to offer
#: it.  The retired service did not.  Every family in the 8000--8018 range
#: ships exactly one Special banner per card it lists -- three for 8012--8017,
#: two for 8008--8011, one for 8018 -- and these eight ship four, not five.
#: The client has no name for the fifth either: it falls back to the literal
#: placeholder `text`.  So a tester's selector showed four playable cards and
#: then a black rectangle labelled `text`, which is what an unlisted stage
#: looks like when a server lists it anyway.
#:
#: The section is left out rather than given a borrowed banner.  What the fifth
#: was for is not recovered -- unreleased, staff-only, or simply cut -- and
#: dressing an unknown in the fourth card's artwork would be inventing a stage
#: the service never showed, which is a worse answer than not showing it.
_FOUR_TIER_COUNTER_DESCENT_STAMINA = (5, 10, 15, 15)
_THREE_TIER_COUNTER_DESCENT_STAMINA = (5, 10, 15)


def _counter_descent_stamina(chapter: int) -> tuple[int, ...] | None:
    if 8000 <= chapter <= 8007:
        return _FOUR_TIER_COUNTER_DESCENT_STAMINA
    if 8012 <= chapter <= 8017:
        return _THREE_TIER_COUNTER_DESCENT_STAMINA
    return None


def _is_melting_pot(chapter: int) -> bool:
    """Melting Pot: the three chapters inside the client's Donation range.

    They settle from the client's own reported drops for the same reason
    Counter Descent does -- no service reward table survives -- but on stronger
    evidence than Counter Descent has. Their drops are attached per spawn in
    the chapter program itself: `Init_DROPPOD` calls
    `SetDropItem(e, 0, 100, {175, 176, 177})` and each race's six boss spawns
    call `SetDropItem(e, 1, 3, {161, 162, 163})`, which is where the Candyboxes
    and Candy a player collects here actually come from. Bounding the stages by
    those operands is possible follow-up work; see `findings.md`, 2026-08-07.
    """
    return 9100 <= chapter <= 9102


def _is_standing_special(chapter: int) -> bool:
    """The six standing Special Quests named in `STANDING_SPECIAL_MANIFEST_ROWS`.

    They settle from the client's own reported drops for the same reason Counter
    Descent and Melting Pot do: the retired result service authored their
    rewards, every one of them declares an empty `dropBuddies`, and no capture
    of a clear survives. Membership is read off the manifest rather than a
    duplicated range test so the two cannot drift apart.
    """
    return chapter in {row[1] for row in STANDING_SPECIAL_MANIFEST_ROWS}


def build_bundled_counter_descent_policy() -> EventCatalog:
    """Return the fourteen packaged non-collaboration Strikes Back families.

    Chapter identities, flags, section counts, and stamina are recovered from
    the final client. Permanent Chapter 5--18 unlocks are explicit preservation
    policy because the historical schedule was not captured, and because the
    retired result service was not either, a clear settles from the client's own
    reported drops under `projected_rewards`. Little Noah 8008--8011 and Hime
    Rush 8018 are deliberately excluded because their progression/reward
    contracts are distinct and unrecovered.
    """
    manifests = [
        row
        for row in EVENT_MANIFEST_ROWS
        if _counter_descent_stamina(row[2]) is not None
    ]
    if len(manifests) != 14:
        raise EventCatalogError("bundled Counter Descent manifest is incomplete")
    stages = tuple(
        EventStage(
            event_id=event_id,
            flag=flag,
            chapter=chapter,
            section=section,
            stamina=stamina,
            coins=0,
            clear_coins=0,
            character_ids=(),
            selector="descent_hunting",
            unlock_after_chapter=unlock_after_chapter,
            projected_rewards=True,
        )
        for event_id, flag, chapter, unlock_after_chapter, _character_ids in manifests
        for section, stamina in enumerate(
            _counter_descent_stamina(chapter) or (), start=1
        )
    )
    return EventCatalog(stages)


def merge_event_catalogs(*catalogs: EventCatalog | None) -> EventCatalog | None:
    """Combine policies while keeping the first owner of an exact stage.

    The standard server's Counter Descent rows stay authoritative when an
    advanced generated catalog also contains those chapters, so their projected
    settlement is not lost to a duplicate. All other user-local event stages are
    retained.
    """
    stages: dict[tuple[int, int], EventStage] = {}
    for catalog in catalogs:
        if catalog is None:
            continue
        for stage in catalog.stages:
            stages.setdefault((stage.chapter, stage.section), stage)
    return EventCatalog(tuple(stages.values())) if stages else None


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_event_catalog(path: Path, character_catalog_path: Path) -> EventCatalog:
    try:
        document = json.loads(path.read_text())
        characters = json.loads(character_catalog_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise EventCatalogError(
            "could not read local event or character catalog JSON"
        ) from error
    if (
        set(document)
        != {"schema_version", "provenance", "character_catalog_sha256", "stages"}
        or document["schema_version"] != 1
        or document["provenance"] != "user-supplied"
    ):
        raise EventCatalogError("event catalog has an invalid schema or provenance")
    if document["character_catalog_sha256"] != _hash(character_catalog_path):
        raise EventCatalogError(
            "event catalog does not match the local character catalog"
        )
    character_ids = {
        row.get("character_id")
        for row in characters.get("characters", [])
        if isinstance(row, dict)
    }
    stages: list[EventStage] = []
    raw_stages = document["stages"] if isinstance(document["stages"], list) else []
    for raw in raw_stages:
        required = {
            "event_id", "flag", "chapter", "section", "stamina", "coins",
            "clear_coins", "character_ids",
        }
        optional = {"unlock_after_chapter", "summon_ids", "selector_id"}
        if (
            not isinstance(raw, dict)
            or not required.issubset(raw)
            or not set(raw).issubset(required | optional)
        ):
            raise EventCatalogError("each event stage has an invalid schema")
        if (
            not isinstance(raw["event_id"], str)
            or not isinstance(raw["flag"], str)
            or any(
                type(raw[field]) is not int or raw[field] < 0
                for field in (
                    "chapter", "section", "stamina", "coins", "clear_coins",
                )
            )
        ):
            raise EventCatalogError("event stage has invalid values")
        unlock_after_chapter = raw.get("unlock_after_chapter")
        if (
            unlock_after_chapter is not None
            and (
                type(unlock_after_chapter) is not int
                or unlock_after_chapter < 0
            )
        ):
            raise EventCatalogError(
                "event stage unlock_after_chapter must be a nonnegative integer"
            )
        selector_id = raw.get("selector_id")
        identity_label = f"{raw['chapter']}-{raw['section']}"
        chapter_label = str(raw["chapter"])
        if (
            selector_id is not None
            and (
                not isinstance(selector_id, str)
                or selector_id not in {identity_label, chapter_label}
            )
        ):
            raise EventCatalogError(
                "event selector_id must be its chapter or exact stage identity"
            )
        if (
            selector_id == chapter_label
            and raw["flag"] != f"sp_ch_{chapter_label}"
        ):
            raise EventCatalogError(
                "a folded chapter selector_id requires its chapter event flag"
            )
        # The client constructs this key and looks it up by exact name. Any
        # other flag is inert: the row disappears without a useful error.
        permitted = event_flags_for(raw["chapter"], raw["section"])
        if raw["flag"] not in permitted:
            raise EventCatalogError(
                f"event stage flag {raw['flag']!r} cannot gate stage "
                f"{raw['chapter']}-{raw['section']}; the client only reads "
                f"{permitted[0]!r} or {permitted[1]!r}"
            )
        grants = raw["character_ids"]
        if (
            not isinstance(grants, list)
            or any(
                type(character_id) is not int or character_id not in character_ids
                for character_id in grants
            )
            or grants != sorted(set(grants))
        ):
            raise EventCatalogError(
                "event grants must be ordered local character IDs"
            )
        summon_ids = raw.get("summon_ids", [])
        if (
            not isinstance(summon_ids, list)
            or any(type(summon_id) is not int or not 1 <= summon_id <= 16 for summon_id in summon_ids)
            or summon_ids != sorted(set(summon_ids))
            or summon_ids and not 4100 <= raw["chapter"] <= 4111
        ):
            raise EventCatalogError(
                "event summon grants must be ordered Summon IDs from 1 through 16"
            )
        chapter = raw["chapter"]
        stages.append(
            EventStage(
                raw["event_id"],
                raw["flag"],
                chapter,
                raw["section"],
                raw["stamina"],
                raw["coins"],
                raw["clear_coins"],
                tuple(grants),
                tuple(summon_ids),
                selector=(
                    "descent_hunting"
                    if _counter_descent_stamina(chapter) is not None
                    else "tower"
                    if 9000 <= chapter <= 9003
                    else "eidolon"
                    if 4100 <= chapter <= 4111
                    else "special"
                ),
                unlock_after_chapter=unlock_after_chapter,
                projected_rewards=(
                    _counter_descent_stamina(chapter) is not None
                    or _is_melting_pot(chapter)
                    or _is_standing_special(chapter)
                ),
                selector_id=selector_id,
                # Applied from the recovered table rather than read off the
                # document, so an operator's catalog generated before this
                # existed still carries the limit its own client declares.
                class_min=SECTION_CLASS_LIMITS.get((chapter, raw["section"]), (0, 0))[0],
                class_max=SECTION_CLASS_LIMITS.get((chapter, raw["section"]), (0, 0))[1],
            )
        )
    if (
        not stages
        or len({(stage.chapter, stage.section) for stage in stages}) != len(stages)
    ):
        raise EventCatalogError("event stages must be nonempty and unique")
    return EventCatalog(tuple(stages), _character_classes(characters))
