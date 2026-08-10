from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.hunting_catalog import (
    BUNDLED_ITEM_SLOTS,
    BUNDLED_MAX_STACK,
    HuntingCatalog,
    hunting_settlement_within_bounds,
)
from liminal_gate.secondary_world_data import (
    BREASOUL_EVENT_FLAG,
    BREASOUL_UNLOCK,
    BREASOUL_WORLD,
    FIVE_EMPERORS_EVENT_FLAGS,
    FIVE_EMPERORS_UNLOCK,
    FIVE_EMPERORS_WORLD,
    MAIN_WORLD,
    WORLD_COUNT,
    advanced_world_progress,
    build_bundled_breasoul_stages,
    build_bundled_five_emperors_stages,
    initial_world_progress,
    is_valid_world_progress,
    pack_world_progress,
    secondary_world_event_flags,
    unpack_world_progress,
    world_max_chapters,
)
from liminal_gate.server_constants import build_server_constants
from tests.support import bootstrap_profile, get, post, start_server, stop_server


def result(items=None, coins=0, exp=0, buddies=(), summons=(), monsters=()):
    return {
        "items": items or {}, "coins": coins, "exp": exp,
        "buddies": list(buddies), "summons": list(summons), "monsters": list(monsters),
    }


def progress(chapter: int, section: int) -> int:
    """Pack a chapter/section the way the client's progressCode does."""
    return (chapter << 6) | section


class BreasoulTest(unittest.TestCase):
    def test_twenty_sections_across_five_chapters(self) -> None:
        """BattleData gives 100 four sections, 104 one, and five each between."""
        stages = build_bundled_breasoul_stages()
        self.assertEqual(20, len(stages))
        counts = {chapter: 0 for chapter in range(100, 105)}
        for stage in stages:
            counts[stage.chapter] += 1
        self.assertEqual({100: 4, 101: 5, 102: 5, 103: 5, 104: 1}, counts)

    def test_every_section_costs_fifteen_stamina_and_no_coins(self) -> None:
        for stage in build_bundled_breasoul_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual(15, stage.stamina)
                self.assertEqual(0, stage.coins)
                self.assertEqual("hidden", stage.selector)

    def test_no_section_settles_a_companion(self) -> None:
        """Every one of the twenty declares an empty dropBuddies."""
        for stage in build_bundled_breasoul_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual({}, stage.companion_maxima)

    def test_experience_is_paid_but_coins_and_items_are_not(self) -> None:
        catalog = HuntingCatalog(build_bundled_breasoul_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        stage = catalog.by_identity()[(100, 1)]
        self.assertTrue(hunting_settlement_within_bounds(stage, result(exp=1_000)))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(coins=1)))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(items={1: 1})))

    def test_an_absurd_experience_claim_is_refused(self) -> None:
        catalog = HuntingCatalog(build_bundled_breasoul_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        stage = catalog.by_identity()[(100, 1)]
        self.assertFalse(hunting_settlement_within_bounds(stage, result(exp=99_000_000)))


class FiveEmperorsTest(unittest.TestCase):
    def test_ten_descents_one_per_chapter(self) -> None:
        stages = build_bundled_five_emperors_stages()
        self.assertEqual(10, len(stages))
        self.assertEqual(
            [(chapter, 1) for chapter in range(110, 120)],
            sorted((s.chapter, s.section) for s in stages),
        )

    def test_five_normal_at_fifteen_and_five_hard_at_twenty(self) -> None:
        stamina = [s.stamina for s in sorted(build_bundled_five_emperors_stages(), key=lambda s: s.chapter)]
        self.assertEqual([15] * 5 + [20] * 5, stamina)

    def test_no_descent_charges_coins(self) -> None:
        for stage in build_bundled_five_emperors_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual(0, stage.coins)

    def test_each_descent_names_one_or_two_candidates(self) -> None:
        for stage in build_bundled_five_emperors_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertIn(len(stage.companion_maxima), (1, 2))
                self.assertTrue(all(count == 1 for count in stage.companion_maxima.values()))

    def test_a_dropped_companion_arrives_at_level_one(self) -> None:
        for stage in build_bundled_five_emperors_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertTrue(all(level == 1 for level in stage.companion_drop_levels.values()))

    def test_one_manifest_companion_settles_and_a_second_does_not(self) -> None:
        """The record's rule for this manifest shape is a single exclusive roll."""
        catalog = HuntingCatalog(build_bundled_five_emperors_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        stage = catalog.by_identity()[(115, 1)]
        first, second = sorted(stage.companion_maxima)
        self.assertTrue(hunting_settlement_within_bounds(stage, result(buddies=[first])))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(buddies=[first, second])))

    def test_a_companion_the_manifest_does_not_name_is_refused(self) -> None:
        catalog = HuntingCatalog(build_bundled_five_emperors_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
        stage = catalog.by_identity()[(110, 1)]
        self.assertFalse(hunting_settlement_within_bounds(stage, result(buddies=[999])))


class SecondaryWorldGateTest(unittest.TestCase):
    """Both maps are permanent once open, which is archive policy."""

    def test_neither_map_opens_before_its_section(self) -> None:
        self.assertEqual({}, secondary_world_event_flags(19, 9))

    def test_the_five_emperors_open_first(self) -> None:
        flags = secondary_world_event_flags(*FIVE_EMPERORS_UNLOCK)
        self.assertEqual(set(FIVE_EMPERORS_EVENT_FLAGS), set(flags))
        self.assertNotIn(BREASOUL_EVENT_FLAG, flags)

    def test_breasoul_opens_at_its_own_section_and_both_stay_open(self) -> None:
        flags = secondary_world_event_flags(*BREASOUL_UNLOCK)
        self.assertIn(BREASOUL_EVENT_FLAG, flags)
        for name in FIVE_EMPERORS_EVENT_FLAGS:
            self.assertIn(name, flags)

    def test_the_map_needs_both_five_emperors_flags(self) -> None:
        """The expanded coordinate branch checks the second one."""
        self.assertEqual(2, len(FIVE_EMPERORS_EVENT_FLAGS))
        self.assertTrue(all(secondary_world_event_flags(30, 1)[n]["value"] for n in FIVE_EMPERORS_EVENT_FLAGS))

    def test_stages_are_locked_until_their_story_section(self) -> None:
        emperor = build_bundled_five_emperors_stages()[0]
        self.assertFalse(emperor.unlocked_at(progress(19, 9)))
        self.assertTrue(emperor.unlocked_at(progress(*FIVE_EMPERORS_UNLOCK)))
        breasoul = build_bundled_breasoul_stages()[0]
        self.assertFalse(breasoul.unlocked_at(progress(25, 9)))
        self.assertTrue(breasoul.unlocked_at(progress(*BREASOUL_UNLOCK)))


class WorldContractTest(unittest.TestCase):
    """The three client contracts the maps need, read out of the reviewed build."""

    def test_world_max_chapter_is_indexed_by_world_in_internal_chapters(self) -> None:
        """`get_worldChapterNo` clamps against this, so 104 and 119, not 5 and 10."""
        self.assertEqual([0, 104, 119], world_max_chapters())
        self.assertEqual(WORLD_COUNT, len(world_max_chapters()))

    def test_the_main_world_is_given_no_ceiling(self) -> None:
        """Both consumers return before reading index 0, so nothing is invented."""
        self.assertEqual(0, world_max_chapters()[0])

    def test_the_constant_is_sent_only_with_the_worlds(self) -> None:
        self.assertNotIn("worldMaxChapter", build_server_constants())
        self.assertEqual(
            world_max_chapters(),
            build_server_constants(secondary_worlds=True)["worldMaxChapter"],
        )

    def test_no_world_count_is_ever_sent(self) -> None:
        """`WORLD_NUM` is a client literal; the build carries no such key."""
        self.assertNotIn("WORLD_NUM", build_server_constants(secondary_worlds=True))

    def test_the_packing_is_the_one_set_world_new_chapter_writes(self) -> None:
        packed = pack_world_progress(110, 1, chapter_boundary=True)
        self.assertEqual((110, 1), unpack_world_progress(packed))
        self.assertEqual(0x3000000, packed & 0x3000000)
        self.assertEqual(1 << 24, pack_world_progress(101, 3) & 0x3000000)

    def test_each_world_starts_where_init_data_starts_it(self) -> None:
        seeded = initial_world_progress()
        self.assertEqual({str(BREASOUL_WORLD), str(FIVE_EMPERORS_WORLD)}, set(seeded))
        self.assertEqual((100, 1), unpack_world_progress(seeded[str(BREASOUL_WORLD)]))
        self.assertEqual((110, 1), unpack_world_progress(seeded[str(FIVE_EMPERORS_WORLD)]))


class WorldProgressionTest(unittest.TestCase):
    def test_a_clear_opens_the_next_section(self) -> None:
        cursor = initial_world_progress()[str(BREASOUL_WORLD)]
        cursor = advanced_world_progress(cursor, 100, 1)
        self.assertEqual((100, 2), unpack_world_progress(cursor))

    def test_the_last_section_of_a_chapter_opens_the_next_chapter(self) -> None:
        """Chapter 100 carries four sections, not five."""
        cursor = advanced_world_progress(pack_world_progress(100, 4), 100, 4)
        self.assertEqual((101, 1), unpack_world_progress(cursor))
        self.assertEqual(0x3000000, cursor & 0x3000000)

    def test_the_final_section_of_a_world_stays_put(self) -> None:
        cursor = advanced_world_progress(pack_world_progress(119, 1), 119, 1)
        self.assertEqual((119, 1), unpack_world_progress(cursor))
        cursor = advanced_world_progress(pack_world_progress(104, 1), 104, 1)
        self.assertEqual((104, 1), unpack_world_progress(cursor))

    def test_replaying_a_cleared_section_never_moves_the_cursor_back(self) -> None:
        """The seed carries both banner bits, so this cannot be an int compare."""
        cursor = pack_world_progress(103, 5)
        self.assertEqual(cursor, advanced_world_progress(cursor, 100, 1))

    def test_a_chapter_outside_the_worlds_advances_nothing(self) -> None:
        self.assertIsNone(advanced_world_progress(pack_world_progress(110, 1), 10, 1))

    def test_a_clear_past_the_frontier_does_not_leapfrog_it(self) -> None:
        """Honouring it would retire eight descents the player never saw."""
        cursor = pack_world_progress(110, 1)
        self.assertEqual(cursor, advanced_world_progress(cursor, 119, 1))
        self.assertEqual(cursor, advanced_world_progress(cursor, 112, 1))

    def test_a_cursor_the_client_could_not_read_is_refused(self) -> None:
        """It is sent as an `Int32`; a wider value freezes the userdata load."""
        self.assertFalse(is_valid_world_progress("2", 2 ** 31))
        self.assertFalse(is_valid_world_progress("2", 2 ** 40))
        self.assertFalse(is_valid_world_progress("2", -1))
        self.assertFalse(is_valid_world_progress("2", "110"))

    def test_a_world_key_that_is_not_a_plain_number_is_refused(self) -> None:
        """The key travels as written and the client resolves it with
        `Int32.Parse`. Python calls an Arabic-Indic digit a digit and converts
        it; whether that client's parse agrees is not a thing to find out on
        the wire."""
        self.assertFalse(is_valid_world_progress("١", pack_world_progress(100, 1)))
        self.assertFalse(is_valid_world_progress("one", pack_world_progress(100, 1)))
        self.assertFalse(is_valid_world_progress(1, pack_world_progress(100, 1)))
        self.assertTrue(is_valid_world_progress("1", pack_world_progress(100, 1)))

    def test_a_cursor_naming_a_section_its_world_lacks_is_refused(self) -> None:
        self.assertFalse(is_valid_world_progress("2", pack_world_progress(100, 1)))
        self.assertFalse(is_valid_world_progress("1", pack_world_progress(100, 5)))
        self.assertFalse(is_valid_world_progress("0", pack_world_progress(110, 1)))
        self.assertTrue(is_valid_world_progress("1", pack_world_progress(100, 4)))
        self.assertTrue(is_valid_world_progress("2", pack_world_progress(119, 1)))


def catalog() -> HuntingCatalog:
    return HuntingCatalog(
        build_bundled_breasoul_stages() + build_bundled_five_emperors_stages(),
        BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK,
    )


class SecondaryWorldTransactionTest(unittest.TestCase):
    """The cursor and the per-world progress, over real HTTP.

    Both were missing and each on its own is enough to make the maps unusable:
    without the cursor the server refuses every clear the player attempts once
    they have walked onto a secondary map, and without `worldProgressCode` the
    client's own menu predicate reads a zero for world 0 and never offers the
    swap at all.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.token, self.account_id = "world-token", "world-account"
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
        }
        self.start_server()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
            hunting_catalog=catalog(), secondary_worlds=True,
        )
        self.addCleanup(self.stop_server)
        if self.account_id not in self.server.state.accounts:
            self.server.state.create_account(self.token, self.account_id, {
                "coins": 100, "energy": 40, "freeEnergy": 20, "worldMapNo": 0,
                "progressCode": (1 << 24) | progress(30, 1), "chrdata": [self.character],
                "teamMembers": [self.character["id"], 0, 0, 0, 0, 0],
                "itemList": [0] * BUNDLED_ITEM_SLOTS, "summonList": [0, 0],
            })
            with self.server.state.lock:
                account = self.server.state.accounts[self.account_id]
                account["tutorial_phase"] = "free_roam"
                account["initial_userdata_served"] = True
                self.server.state._persist_locked()

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def post(self, route: str, request_id: str, fields: list) -> tuple:
        return post(
            self.server, route, request_id, urlencode(fields), token=self.token,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][self.account_id]

    def userdata(self) -> dict:
        return self.account()["userdata"]

    def read_userdata(self) -> dict:
        status, payload = get(self.server, f"/gd/userdata?otk={self.token}")
        self.assertEqual(200, status)
        return payload

    def world_cursor(self, world: int) -> int:
        """The `progressCode` the client reports while standing on ``world``.

        Not the story code unless the world *is* the story.
        `SerializeJsonUserData` sends `UserData.GetWorldProgressCode()`, which
        returns `worldProgressCode[worldNo]` for any non-zero world, so every
        body below carries the cursor of the map the client is on. Sending the
        story code here instead is what every one of these tests used to do,
        and it tested a request the client never makes.
        """
        if world == MAIN_WORLD:
            return self.userdata()["progressCode"]
        held = self.account().get("world_progress", {})
        return held.get(str(world), self.userdata()["progressCode"])

    def enter_world(self, request_id: str, world: int) -> tuple:
        return self.post("/gd/userdata", request_id, [
            ("progressCode", str(self.world_cursor(world))),
            ("worldMapNo", str(world)), ("lastUpdate", "1"),
        ])

    def start(self, request_id: str, chapter: int, section: int, stamina: int = 15) -> tuple:
        return self.post("/gd/start_quest", request_id, [
            ("stamina", str(stamina)), ("coins", "0"), ("chapter", str(chapter)),
            ("section", str(section)), ("lastUpdate", "1"),
        ])

    def clear(self, request_id: str, chapter: int, section: int, *, world: int) -> tuple:
        userdata = self.userdata()
        return self.post("/gd/clear_quest", request_id, [
            ("progressCode", str(self.world_cursor(world))), ("worldMapNo", str(world)),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"],
            })),
            ("chrdata", json.dumps([self.character])),
            ("itemList", json.dumps(userdata["itemList"])),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": chapter, "section": section, "coins": 0, "exp": 0,
                "items": {}, "buddies": [], "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def test_the_userdata_read_carries_the_three_world_cursors(self) -> None:
        served = self.read_userdata()["worldProgressCode"]
        self.assertEqual({"0", "1", "2"}, set(served))
        self.assertEqual(self.userdata()["progressCode"], served["0"])
        self.assertEqual((100, 1), unpack_world_progress(served["1"]))
        self.assertEqual((110, 1), unpack_world_progress(served["2"]))

    def test_the_cursors_are_an_object_because_an_array_would_not_load(self) -> None:
        """`LoadUserdataFromJson` parses each key with `Int32.Parse`."""
        served = self.read_userdata()["worldProgressCode"]
        self.assertIsInstance(served, dict)
        self.assertTrue(all(isinstance(key, str) and key.isdigit() for key in served))

    def test_world_zero_tracks_the_story_rather_than_being_stored_twice(self) -> None:
        """The menu predicate reads world 0, so a stale copy hides both maps."""
        with self.server.state.lock:
            self.server.state.accounts[self.account_id]["userdata"]["progressCode"] = (
                (1 << 24) | progress(35, 2)
            )
            self.server.state._persist_locked()
        self.assertEqual((1 << 24) | progress(35, 2), self.read_userdata()["worldProgressCode"]["0"])
        self.assertNotIn("world_progress", self.userdata())

    def test_entering_a_world_is_accepted_and_remembered(self) -> None:
        status, payload = self.enter_world("swap", FIVE_EMPERORS_WORLD)
        self.assertEqual((200, True), (status, payload["success"]))
        self.assertEqual(FIVE_EMPERORS_WORLD, self.userdata()["worldMapNo"])
        self.restart()
        self.assertEqual(FIVE_EMPERORS_WORLD, self.userdata()["worldMapNo"])

    def test_a_world_the_client_cannot_hold_is_refused(self) -> None:
        """`worldProgressCode` is three long and every index is bounds-checked."""
        status, _payload = self.enter_world("too-far", WORLD_COUNT)
        self.assertEqual(409, status)
        self.assertEqual(0, self.userdata()["worldMapNo"])

    def test_the_cursor_write_may_not_move_story_progress(self) -> None:
        status, _payload = self.post("/gd/userdata", "sneak", [
            ("progressCode", str((1 << 24) | progress(40, 1))),
            ("worldMapNo", str(BREASOUL_WORLD)), ("lastUpdate", "1"),
        ])
        self.assertEqual(409, status)
        self.assertEqual((1 << 24) | progress(30, 1), self.userdata()["progressCode"])

    def test_the_swap_carries_the_world_cursor_and_not_the_story_code(self) -> None:
        """`GetWorldProgressCode` renames the field the moment `worldNo` is set.

        The reviewed `0x19D9394` returns `worldProgressCode[worldNo]` for any
        non-zero world and rebuilds the story code only for zero, so this is the
        one body a player entering either map can produce. Requiring the story
        code refused it, which is why the menu opened onto a Network Error and
        `worldMapNo` never left zero on a tester's save.
        """
        status, payload = self.post("/gd/userdata", "swap", [
            ("progressCode", str(initial_world_progress()[str(FIVE_EMPERORS_WORLD)])),
            ("worldMapNo", str(FIVE_EMPERORS_WORLD)), ("lastUpdate", "1"),
        ])
        self.assertEqual((200, True), (status, payload["success"]))
        self.assertEqual(FIVE_EMPERORS_WORLD, self.userdata()["worldMapNo"])

    def test_the_story_code_is_refused_as_a_secondary_world_cursor(self) -> None:
        """The body the old contract expected names no section either world has."""
        status, _payload = self.post("/gd/userdata", "story-code", [
            ("progressCode", str(self.userdata()["progressCode"])),
            ("worldMapNo", str(FIVE_EMPERORS_WORLD)), ("lastUpdate", "1"),
        ])
        self.assertEqual(409, status)
        self.assertEqual(MAIN_WORLD, self.userdata()["worldMapNo"])

    def test_a_cursor_naming_no_declared_section_is_refused(self) -> None:
        """Accepted values are sent back, and the client reads them as `Int32`."""
        status, _payload = self.post("/gd/userdata", "phantom", [
            ("progressCode", str(pack_world_progress(110, 9))),
            ("worldMapNo", str(FIVE_EMPERORS_WORLD)), ("lastUpdate", "1"),
        ])
        self.assertEqual(409, status)

    def test_the_flush_after_a_clear_is_answered_rather_than_refused(self) -> None:
        """`UnlockNextSection` marks Progress dirty and posts the new cursor.

        Same world, moved cursor: the shape that reached none of the free-roam
        parsers and answered 501 to an ordinary side-world battle.
        """
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        self.assertEqual(200, self.start("start-110", 110, 1)[0])
        self.assertEqual(200, self.clear("clear-110", 110, 1, world=FIVE_EMPERORS_WORLD)[0])
        advanced = self.account()["world_progress"][str(FIVE_EMPERORS_WORLD)]
        self.assertEqual((111, 1), unpack_world_progress(advanced))
        status, payload = self.post("/gd/userdata", "flush", [
            ("progressCode", str(advanced)),
            ("worldMapNo", str(FIVE_EMPERORS_WORLD)), ("lastUpdate", "1"),
        ])
        self.assertEqual((200, True), (status, payload["success"]))

    def test_a_flush_ahead_of_the_frontier_is_answered_without_moving_it(self) -> None:
        """The cursor draws the map; it gates no start and no clear.

        Refusing an over-eager echo would strand the player on the map they are
        standing on, and following it would let a client declare sections open
        that it never played. Answered, and the frontier stays earned.
        """
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        status, payload = self.post("/gd/userdata", "ahead", [
            ("progressCode", str(pack_world_progress(119, 1))),
            ("worldMapNo", str(FIVE_EMPERORS_WORLD)), ("lastUpdate", "1"),
        ])
        self.assertEqual((200, True), (status, payload["success"]))
        self.assertEqual(
            (110, 1),
            unpack_world_progress(self.account()["world_progress"][str(FIVE_EMPERORS_WORLD)]),
        )

    def test_a_repeated_swap_replays_rather_than_settling_twice(self) -> None:
        first = self.enter_world("swap", BREASOUL_WORLD)
        self.assertEqual(200, first[0])
        self.assertEqual(first, self.enter_world("swap", BREASOUL_WORLD))

    def test_re_announcing_the_world_already_held_is_answered(self) -> None:
        """Refusing what the client is restating has no way out of the dialog."""
        self.assertEqual(200, self.enter_world("swap", BREASOUL_WORLD)[0])
        self.assertEqual(200, self.enter_world("again", BREASOUL_WORLD)[0])
        self.assertEqual(200, self.enter_world("and-again", BREASOUL_WORLD)[0])
        self.assertEqual(BREASOUL_WORLD, self.userdata()["worldMapNo"])

    def test_leaving_a_world_returns_the_cursor_to_the_story_map(self) -> None:
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        self.assertEqual(200, self.enter_world("home", 0)[0])
        self.assertEqual(0, self.userdata()["worldMapNo"])

    def test_a_descent_clears_against_its_own_world(self) -> None:
        """The whole defect: the client sends 2 here and the server held 0."""
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        status, started = self.start("start-110", 110, 1)
        self.assertEqual((200, True), (status, started["success"]))
        status, settled = self.clear("clear-110", 110, 1, world=FIVE_EMPERORS_WORLD)
        self.assertEqual((200, True), (status, settled["success"]))
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_a_clear_naming_the_wrong_world_is_still_refused(self) -> None:
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        self.assertEqual(200, self.start("start-110", 110, 1)[0])
        self.assertEqual(409, self.clear("clear-110", 110, 1, world=0)[0])

    def test_a_descent_advances_only_its_own_world(self) -> None:
        story = self.userdata()["progressCode"]
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        self.assertEqual(200, self.start("start-110", 110, 1)[0])
        self.assertEqual(200, self.clear("clear-110", 110, 1, world=FIVE_EMPERORS_WORLD)[0])
        served = self.read_userdata()["worldProgressCode"]
        self.assertEqual((111, 1), unpack_world_progress(served["2"]))
        self.assertEqual((100, 1), unpack_world_progress(served["1"]))
        self.assertEqual(story, self.userdata()["progressCode"])

    def test_a_breasoul_section_advances_inside_its_chapter(self) -> None:
        self.assertEqual(200, self.enter_world("swap", BREASOUL_WORLD)[0])
        self.assertEqual(200, self.start("start-100", 100, 1)[0])
        self.assertEqual(200, self.clear("clear-100", 100, 1, world=BREASOUL_WORLD)[0])
        served = self.read_userdata()["worldProgressCode"]
        self.assertEqual((100, 2), unpack_world_progress(served["1"]))

    def test_an_advance_survives_a_restart(self) -> None:
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        self.assertEqual(200, self.start("start-110", 110, 1)[0])
        self.assertEqual(200, self.clear("clear-110", 110, 1, world=FIVE_EMPERORS_WORLD)[0])
        self.restart()
        self.assertEqual((111, 1), unpack_world_progress(self.read_userdata()["worldProgressCode"]["2"]))

    def test_an_open_battle_does_not_block_the_swap(self) -> None:
        """A force-close leaves the phase active and every later start renews it,
        so refusing here answers Network Error until a battle happens to finish."""
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        self.assertEqual(200, self.start("start-110", 110, 1)[0])
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])
        self.assertEqual(200, self.enter_world("mid-battle", BREASOUL_WORLD)[0])
        self.assertEqual(BREASOUL_WORLD, self.userdata()["worldMapNo"])

    def test_a_clear_past_the_frontier_settles_without_moving_it(self) -> None:
        self.assertEqual(200, self.enter_world("swap", FIVE_EMPERORS_WORLD)[0])
        self.assertEqual(200, self.start("start-119", 119, 1, stamina=20)[0])
        self.assertEqual(200, self.clear("clear-119", 119, 1, world=FIVE_EMPERORS_WORLD)[0])
        served = self.read_userdata()["worldProgressCode"]
        self.assertEqual((110, 1), unpack_world_progress(served["2"]))

    def test_a_hand_edited_cursor_never_reaches_the_client(self) -> None:
        """`op_Explicit` wants an Int32; a wider one freezes the load."""
        self.stop_server()
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        document["accounts"][self.account_id]["world_progress"] = {
            "1": 2 ** 40, "2": "not an int", "0": 5, "9": 1,
        }
        self.state_path.write_text(json.dumps(document), encoding="utf-8")
        self.start_server()
        served = self.read_userdata()["worldProgressCode"]
        self.assertEqual({"0", "1", "2"}, set(served))
        self.assertTrue(all(0 <= value <= 2 ** 31 - 1 for value in served.values()))
        self.assertEqual((100, 1), unpack_world_progress(served["1"]))
        self.assertEqual((110, 1), unpack_world_progress(served["2"]))

    def test_a_stored_world_zero_cannot_override_the_story(self) -> None:
        """That entry gates both menu rows; a stale copy would misreport progress."""
        with self.server.state.lock:
            self.server.state.accounts[self.account_id]["world_progress"]["0"] = 999
            self.server.state._persist_locked()
        self.assertEqual(
            self.userdata()["progressCode"], self.read_userdata()["worldProgressCode"]["0"],
        )

    def test_a_real_cursor_survives_the_migration(self) -> None:
        self.stop_server()
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        document["accounts"][self.account_id]["world_progress"]["1"] = pack_world_progress(102, 3)
        self.state_path.write_text(json.dumps(document), encoding="utf-8")
        self.start_server()
        self.assertEqual(
            (102, 3), unpack_world_progress(self.read_userdata()["worldProgressCode"]["1"]),
        )

    def test_a_save_written_before_the_worlds_is_migrated_in_place(self) -> None:
        self.stop_server()
        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        del document["accounts"][self.account_id]["world_progress"]
        self.state_path.write_text(json.dumps(document), encoding="utf-8")
        self.start_server()
        served = self.read_userdata()["worldProgressCode"]
        self.assertEqual((100, 1), unpack_world_progress(served["1"]))
        self.assertEqual((110, 1), unpack_world_progress(served["2"]))


class TutorialMapWriteTest(unittest.TestCase):
    """The tutorial's own map write must survive the flag being on.

    It shares all three fields with the world swap and is separated from it only
    by moving `progressCode`. Getting that wrong left every account stranded at
    `chapter1_5_cleared` on any server carrying `--secondary-worlds` — which is
    every guided one, since the flag is in `STANDARD_POLICY_FLAGS`.
    """

    FINAL_MAP_WRITE = "progressCode=16777345&worldMapNo=0&lastUpdate=1"

    def run_final_map_write(self, *, secondary_worlds: bool) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), state,
                secondary_worlds=secondary_worlds,
            )
            try:
                state.create_account("tut-token", "tut-account", {
                    "coins": 0, "worldMapNo": 0, "progressCode": 50331777,
                    "chrdata": [], "teamMembers": [0] * 6,
                    "itemList": [0] * BUNDLED_ITEM_SLOTS, "summonList": [0, 0],
                })
                with state.lock:
                    state.accounts["tut-account"]["tutorial_phase"] = "chapter1_5_cleared"
                    state._persist_locked()
                status, _payload = post(
                    server, "/gd/userdata", "final-map", self.FINAL_MAP_WRITE,
                    token="tut-token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                return status, state.accounts["tut-account"]["tutorial_phase"]
            finally:
                stop_server(server, thread)

    def test_the_flag_does_not_change_the_tutorial(self) -> None:
        self.assertEqual((200, "free_roam"), self.run_final_map_write(secondary_worlds=False))
        self.assertEqual((200, "free_roam"), self.run_final_map_write(secondary_worlds=True))


class WithoutSecondaryWorldsTest(unittest.TestCase):
    """Nothing on the wire changes for a server that was not asked for them."""

    def test_the_cursors_are_not_served(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            # Stated rather than defaulted: this test's whole subject is the
            # flag being off, so it must not inherit an on default from anything.
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), state, secondary_worlds=False,
            )
            try:
                state.create_account("plain-token", "plain-account", {
                    "coins": 0, "worldMapNo": 0, "progressCode": (1 << 24) | progress(30, 1),
                    "chrdata": [], "teamMembers": [0] * 6,
                    "itemList": [0] * BUNDLED_ITEM_SLOTS, "summonList": [0, 0],
                })
                status, payload = get(server, "/gd/userdata?otk=plain-token")
                self.assertEqual(200, status)
                self.assertNotIn("worldProgressCode", payload)
            finally:
                stop_server(server, thread)


if __name__ == "__main__":
    unittest.main()
