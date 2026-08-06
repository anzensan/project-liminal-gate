"""Orbling Cavern and Cryptid Forest, the two standing World 1 areas.

Both were complete content nobody could reach. The map point for each is built
behind a prefix scan over the `eventFlags` this server sends, and this server
sent no key under either prefix, so neither point was ever drawn. The prefix
property is asserted here directly, because it is the whole reason the flags
are shaped the way they are and nothing else in the suite would notice it
breaking.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.cavern_forest_data import (
    CRYPTID_FOREST_CHAPTER,
    CRYPTID_FOREST_UNLOCK,
    ORBLING_CAVERN_CHAPTER,
    ORBLING_CAVERN_UNLOCK,
    build_bundled_cryptid_forest_stages,
    build_bundled_orbling_cavern_stages,
    cavern_forest_event_flags,
)
from liminal_gate.hunting_catalog import (
    BUNDLED_ITEM_SLOTS,
    BUNDLED_MAX_STACK,
    HuntingCatalog,
    hunting_settlement_within_bounds,
)
from liminal_gate.job_unlock_data import JOB_UNLOCK_ROWS
from liminal_gate.luck_data import ALLOW_LUCKY_CHAPTERS
from tests.support import bootstrap_profile, get, post, start_server, stop_server


#: The two prefixes `UIMap::InitPoints0` scans with `EventManager.IsEnabledAny`
#: before it will build either map point.
CAVERN_MAP_PREFIX = "sp_ch_700"
FOREST_MAP_PREFIX = "sp_ch_701"

BAHL_COMPANION = 294
GRACE_COMPANION = 296
#: Dracorin's two job unlocks, which are what each Forest section farms.
DRACORIN = 188


def result(items=None, coins=0, exp=0, buddies=(), summons=(), monsters=()):
    return {
        "items": items or {}, "coins": coins, "exp": exp,
        "buddies": list(buddies), "summons": list(summons), "monsters": list(monsters),
    }


def progress(chapter: int, section: int) -> int:
    return (chapter << 6) | section


def catalog() -> HuntingCatalog:
    stages = build_bundled_orbling_cavern_stages() + build_bundled_cryptid_forest_stages()
    return HuntingCatalog(stages, BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)


class OrblingCavernTest(unittest.TestCase):
    def test_two_sections_at_one_stamina_and_no_coins(self) -> None:
        stages = build_bundled_orbling_cavern_stages()
        self.assertEqual(2, len(stages))
        self.assertEqual(
            [(ORBLING_CAVERN_CHAPTER, 1), (ORBLING_CAVERN_CHAPTER, 2)],
            sorted((s.chapter, s.section) for s in stages),
        )
        for stage in stages:
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual(1, stage.stamina)
                self.assertEqual(0, stage.coins)
                self.assertEqual("hidden", stage.selector)

    def test_each_section_names_the_one_companion_its_manifest_declares(self) -> None:
        """75265 and 75777 decode to Companion 294 count 1 and 296 count 1."""
        first, second = build_bundled_orbling_cavern_stages()
        self.assertEqual({BAHL_COMPANION: 1}, first.companion_maxima)
        self.assertEqual({GRACE_COMPANION: 1}, second.companion_maxima)
        for stage in (first, second):
            self.assertEqual(1, stage.max_companions_total)
            self.assertTrue(all(level == 1 for level in stage.companion_drop_levels.values()))

    def test_the_declared_companion_settles_and_another_does_not(self) -> None:
        stage = catalog().by_identity()[(ORBLING_CAVERN_CHAPTER, 1)]
        self.assertTrue(hunting_settlement_within_bounds(stage, result(buddies=[BAHL_COMPANION])))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(buddies=[GRACE_COMPANION])))
        self.assertFalse(
            hunting_settlement_within_bounds(stage, result(buddies=[BAHL_COMPANION, BAHL_COMPANION]))
        )

    def test_a_clear_reporting_no_companion_is_ordinary(self) -> None:
        """The drop is guaranteed while unowned and absent once held, so an
        empty report is the normal second visit rather than a fault."""
        stage = catalog().by_identity()[(ORBLING_CAVERN_CHAPTER, 1)]
        self.assertTrue(hunting_settlement_within_bounds(stage, result()))
        self.assertFalse(stage.once_per_utc_day)

    def test_experience_is_paid_but_coins_and_items_are_not(self) -> None:
        stage = catalog().by_identity()[(ORBLING_CAVERN_CHAPTER, 1)]
        self.assertTrue(hunting_settlement_within_bounds(stage, result(exp=1_000)))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(coins=1)))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(items={1: 1})))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(exp=99_000_000)))

    def test_no_lucky_enemy_source(self) -> None:
        """Both sections carry allowLucky 0; only the Forest is flagged."""
        self.assertNotIn(ORBLING_CAVERN_CHAPTER, ALLOW_LUCKY_CHAPTERS)


class CryptidForestTest(unittest.TestCase):
    def test_two_sections_at_one_stamina_and_no_coins(self) -> None:
        stages = build_bundled_cryptid_forest_stages()
        self.assertEqual(2, len(stages))
        self.assertEqual(
            [(CRYPTID_FOREST_CHAPTER, 1), (CRYPTID_FOREST_CHAPTER, 2)],
            sorted((s.chapter, s.section) for s in stages),
        )
        for stage in stages:
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual(1, stage.stamina)
                self.assertEqual(0, stage.coins)
                self.assertEqual("hidden", stage.selector)

    def test_neither_section_settles_a_companion(self) -> None:
        """Both declare an empty dropBuddies, so none is accepted."""
        for stage in build_bundled_cryptid_forest_stages():
            with self.subTest(stage=stage.identity_label()):
                self.assertEqual({}, stage.companion_maxima)
                self.assertFalse(hunting_settlement_within_bounds(stage, result(buddies=[1])))

    def test_each_section_accepts_exactly_its_own_dracorin_job_materials(self) -> None:
        """The client's Kirin constructors and ChrDatabase agree on these.

        `Init_KR_KIRIN` hands the engine [150, 151] and `Init_KR_KIRIN2` hands
        it [152, 153]; `JOB_UNLOCK_ROWS` prices Dracorin's first job at 150 and
        151 and its second at 152 and 153. A section accepting the other
        section's materials would break that correspondence silently.
        """
        priced = {
            index: {item for item, _count in materials}
            for character, index, _coins, materials in JOB_UNLOCK_ROWS
            if character == DRACORIN
        }
        first, second = build_bundled_cryptid_forest_stages()
        for stage, index in ((first, 1), (second, 2)):
            with self.subTest(stage=stage.identity_label()):
                # The job rows also price a common material the Kirin does not
                # carry, so the stage's items must be contained in the row.
                self.assertLessEqual(set(stage.item_maxima), priced[index])
                self.assertEqual(2, len(stage.item_maxima))
        self.assertEqual(set(), set(first.item_maxima) & set(second.item_maxima))

    def test_a_reported_job_material_settles_and_a_foreign_one_does_not(self) -> None:
        stage = catalog().by_identity()[(CRYPTID_FOREST_CHAPTER, 1)]
        first, second = sorted(stage.item_maxima)
        self.assertTrue(hunting_settlement_within_bounds(stage, result(items={first: 1})))
        self.assertTrue(hunting_settlement_within_bounds(stage, result(items={first: 1, second: 1})))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(items={999: 1})))

    def test_an_absurd_material_claim_is_refused(self) -> None:
        stage = catalog().by_identity()[(CRYPTID_FOREST_CHAPTER, 1)]
        first = min(stage.item_maxima)
        self.assertFalse(hunting_settlement_within_bounds(stage, result(items={first: 999})))

    def test_experience_is_paid_but_coins_are_not(self) -> None:
        stage = catalog().by_identity()[(CRYPTID_FOREST_CHAPTER, 1)]
        self.assertTrue(hunting_settlement_within_bounds(stage, result(exp=1_000)))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(coins=1)))
        self.assertFalse(hunting_settlement_within_bounds(stage, result(exp=99_000_000)))

    def test_the_lucky_runner_source_is_already_routed(self) -> None:
        """One stamina is far below LUCK_GAIN_MIN_STAMINA, and that rule does
        not govern the Lucky-enemy source, so the entry still pays it."""
        self.assertIn(CRYPTID_FOREST_CHAPTER, ALLOW_LUCKY_CHAPTERS)


class MapPointFlagTest(unittest.TestCase):
    """The gate that kept both areas invisible."""

    def test_every_flag_carries_the_prefix_its_map_point_scans(self) -> None:
        """`IsEnabledAny` is a prefix scan, so this is what draws the points."""
        flags = cavern_forest_event_flags(99, 1)
        cavern = {name for name in flags if name.startswith(CAVERN_MAP_PREFIX)}
        forest = {name for name in flags if name.startswith(FOREST_MAP_PREFIX)}
        self.assertEqual(2, len(cavern))
        self.assertEqual(2, len(forest))
        self.assertEqual(set(flags), cavern | forest)
        self.assertTrue(all(entry["value"] for entry in flags.values()))

    def test_the_two_prefixes_cannot_open_each_other(self) -> None:
        """`sp_ch_701...` must not satisfy the Cavern's `sp_ch_700` scan."""
        self.assertFalse(FOREST_MAP_PREFIX.startswith(CAVERN_MAP_PREFIX))
        forest = cavern_forest_event_flags(*CRYPTID_FOREST_UNLOCK)
        self.assertFalse(any(name.startswith(CAVERN_MAP_PREFIX) for name in forest))

    def test_each_flag_names_a_stage_the_catalog_will_honour(self) -> None:
        """A flag opening a card the catalog refuses is a dead selector row."""
        identities = set(catalog().by_identity())
        named = {
            tuple(int(part) for part in name.removeprefix("sp_ch_").split("-"))
            for name in cavern_forest_event_flags(99, 1)
        }
        self.assertEqual(identities, named)

    def test_neither_area_opens_before_its_chapter(self) -> None:
        self.assertEqual({}, cavern_forest_event_flags(4, 9))

    def test_the_forest_opens_first_and_both_stay_open(self) -> None:
        forest = cavern_forest_event_flags(*CRYPTID_FOREST_UNLOCK)
        self.assertEqual(2, len(forest))
        both = cavern_forest_event_flags(*ORBLING_CAVERN_UNLOCK)
        self.assertEqual(4, len(both))
        self.assertEqual(4, len(cavern_forest_event_flags(42, 1)))

    def test_stages_unlock_with_their_own_flags(self) -> None:
        """The server's gate must not outlast the client's, or a drawn map
        point leads to a start this server refuses."""
        cavern = build_bundled_orbling_cavern_stages()[0]
        forest = build_bundled_cryptid_forest_stages()[0]
        self.assertFalse(cavern.unlocked_at(progress(5, 1)))
        self.assertTrue(cavern.unlocked_at(progress(*ORBLING_CAVERN_UNLOCK)))
        self.assertFalse(forest.unlocked_at(progress(4, 9)))
        self.assertTrue(forest.unlocked_at(progress(*CRYPTID_FOREST_UNLOCK)))


class CavernForestLoginTest(unittest.TestCase):
    def login_flags(self, *, cavern_forest: bool, progress_code: int) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json")
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), state,
                hunting_catalog=catalog(), cavern_forest=cavern_forest,
            )
            try:
                self.assertEqual(200, get(server, "/gd/signup?uuid=acct&otk=sig&requestID=s1")[0])
                with server.state.lock:
                    server.state.accounts["acct"]["userdata"]["progressCode"] = progress_code
                    server.state._persist_locked()
                status, payload = get(server, "/gd/login?uuid=acct&otk=tok&requestID=l1")
                self.assertEqual(200, status)
                return payload["eventFlags"]
            finally:
                stop_server(server, thread)

    def test_login_opens_both_map_points_once_the_story_reaches_them(self) -> None:
        flags = self.login_flags(cavern_forest=True, progress_code=(1 << 24) | progress(10, 1))
        for chapter in (ORBLING_CAVERN_CHAPTER, CRYPTID_FOREST_CHAPTER):
            for section in (1, 2):
                self.assertTrue(flags[f"sp_ch_{chapter}-{section}"]["value"])

    def test_an_early_account_gets_neither(self) -> None:
        flags = self.login_flags(cavern_forest=True, progress_code=(1 << 24) | progress(1, 1))
        self.assertFalse(any(name.startswith("sp_ch_70") for name in flags))

    def test_the_areas_stay_closed_unless_asked_for(self) -> None:
        flags = self.login_flags(cavern_forest=False, progress_code=(1 << 24) | progress(42, 1))
        self.assertFalse(any(name.startswith("sp_ch_70") for name in flags))


class CavernForestTransactionTest(unittest.TestCase):
    """Real HTTP through the Hunting start and clear the stages actually use."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.token, self.account_id = "area-token", "area-account"
        self.character = {
            "id": 9001, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0,
        }
        self.start_server()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
            hunting_catalog=catalog(), cavern_forest=True,
        )
        self.addCleanup(self.stop_server)
        if self.account_id not in self.server.state.accounts:
            self.server.state.create_account(self.token, self.account_id, {
                "coins": 100, "energy": 40, "freeEnergy": 20, "worldMapNo": 0,
                "progressCode": (1 << 24) | progress(10, 1), "chrdata": [self.character],
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

    def start(self, request_id: str, chapter: int, section: int) -> tuple:
        return self.post("/gd/start_quest", request_id, [
            ("stamina", "1"), ("coins", "0"), ("chapter", str(chapter)),
            ("section", str(section)), ("lastUpdate", "1"),
        ])

    def clear(
        self, request_id: str, chapter: int, section: int,
        *, buddies=(), items=None, item_list=None, exp=0,
    ) -> tuple:
        userdata = self.userdata()
        return self.post("/gd/clear_quest", request_id, [
            ("progressCode", str(userdata["progressCode"])), ("worldMapNo", "0"),
            ("valuables", json.dumps({
                "energyAppStore": 0, "energy": userdata["energy"], "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"], "energyGooglePlay": 0,
                "coins": userdata["coins"],
            })),
            ("chrdata", json.dumps([self.character])),
            ("itemList", json.dumps(userdata["itemList"] if item_list is None else item_list)),
            ("summonList", json.dumps(userdata["summonList"])),
            ("battle_result", json.dumps({
                "chapter": chapter, "section": section, "coins": 0, "exp": exp,
                "items": items or {}, "buddies": list(buddies), "monsters": [], "summons": [],
                "luckynum": 0, "unableluckdrop": False, "boostup": [0, 0, 0, 0, 0, 0],
            })),
            ("itmp0", "0"), ("itmp1", "0"), ("lastUpdate", "1"),
        ])

    def test_a_cavern_clear_settles_its_companion_and_releases_the_account(self) -> None:
        status, started = self.start("c-start", ORBLING_CAVERN_CHAPTER, 1)
        self.assertEqual((200, True), (status, started["success"]))
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])

        status, cleared = self.clear("c-clear", ORBLING_CAVERN_CHAPTER, 1, buddies=[BAHL_COMPANION])
        self.assertEqual(200, status, cleared)
        self.assertEqual(
            [BAHL_COMPANION], [row["bid"] for row in self.userdata()["buddyInfo"]["list"]],
        )
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_an_exact_retry_after_restart_credits_the_companion_once(self) -> None:
        self.assertEqual(200, self.start("c-start", ORBLING_CAVERN_CHAPTER, 2)[0])
        self.assertEqual(
            200, self.clear("c-clear", ORBLING_CAVERN_CHAPTER, 2, buddies=[GRACE_COMPANION])[0],
        )
        self.restart()
        self.assertEqual(
            200, self.clear("c-clear", ORBLING_CAVERN_CHAPTER, 2, buddies=[GRACE_COMPANION])[0],
        )
        self.assertEqual(
            [GRACE_COMPANION], [row["bid"] for row in self.userdata()["buddyInfo"]["list"]],
        )

    def test_a_forest_clear_settles_the_job_materials_it_reports(self) -> None:
        stage = catalog().by_identity()[(CRYPTID_FOREST_CHAPTER, 1)]
        first, second = sorted(stage.item_maxima)
        self.assertEqual(200, self.start("f-start", CRYPTID_FOREST_CHAPTER, 1)[0])
        items = list(self.userdata()["itemList"])
        items[first - 1] += 2
        items[second - 1] += 1
        status, cleared = self.clear(
            "f-clear", CRYPTID_FOREST_CHAPTER, 1,
            items={str(first): 2, str(second): 1}, item_list=items, exp=1_000,
        )
        self.assertEqual(200, status, cleared)
        settled = self.userdata()["itemList"]
        self.assertEqual((2, 1), (settled[first - 1], settled[second - 1]))
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_the_forest_entry_pays_a_lucky_runner_despite_costing_one_stamina(self) -> None:
        """The chapter is `allowLucky`, and that source is not governed by the
        eight-stamina battle-end rule a one-stamina entry cannot meet."""
        status, started = self.start("f-luck", CRYPTID_FOREST_CHAPTER, 2)
        self.assertEqual(200, status)
        self.assertIn("luckUpTable", started)
        self.assertTrue(any(started["luckUpTable"]))

    def test_an_unreported_inventory_change_is_refused_without_mutation(self) -> None:
        """Trust covers the reported reward, not an unrelated inventory write.

        The per-stage ceilings are an audit-mode bound: ordinary Hunting
        settlement trusts what the client reports, because the client owns the
        battle. Reconciliation is what still holds, and it is what this stage
        relies on -- the submitted slot delta must say exactly what
        `battle_result.items` says.
        """
        first = min(catalog().by_identity()[(CRYPTID_FOREST_CHAPTER, 1)].item_maxima)
        self.assertEqual(200, self.start("f-start", CRYPTID_FOREST_CHAPTER, 1)[0])
        before = self.userdata()
        submitted = list(before["itemList"])
        submitted[first - 1] += 1
        submitted[49] = 999

        status, refused = self.clear(
            "f-bad", CRYPTID_FOREST_CHAPTER, 1,
            items={str(first): 1}, item_list=submitted,
        )

        self.assertEqual((409, "invalid_local_hunting_result"), (status, refused["error"]))
        self.assertEqual(before, self.userdata())
        # A refusal must not strand the battle; the stage stays open to retry.
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])

    def test_a_companion_the_section_does_not_declare_is_refused(self) -> None:
        """Companions are bounded even under trusted settlement, because a
        drop with no declared level cannot be minted at all."""
        self.assertEqual(200, self.start("c-bad-start", ORBLING_CAVERN_CHAPTER, 1)[0])
        status, _ = self.clear("c-bad", ORBLING_CAVERN_CHAPTER, 1, buddies=[GRACE_COMPANION])
        self.assertEqual(409, status)
        self.assertEqual([], self.userdata().get("buddyInfo", {}).get("list", []))
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])


class CavernForestStrictAuditTest(CavernForestTransactionTest):
    """The same stages under `--outcome-strict`, where the ceilings do apply."""

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
            hunting_catalog=catalog(), cavern_forest=True, outcome_strict=True,
        )
        self.addCleanup(self.stop_server)
        if self.account_id not in self.server.state.accounts:
            self.server.state.create_account(self.token, self.account_id, {
                "coins": 100, "energy": 40, "freeEnergy": 20, "worldMapNo": 0,
                "progressCode": (1 << 24) | progress(10, 1), "chrdata": [self.character],
                "teamMembers": [self.character["id"], 0, 0, 0, 0, 0],
                "itemList": [0] * BUNDLED_ITEM_SLOTS, "summonList": [0, 0],
            })
            with self.server.state.lock:
                account = self.server.state.accounts[self.account_id]
                account["tutorial_phase"] = "free_roam"
                account["initial_userdata_served"] = True
                self.server.state._persist_locked()

    def test_the_other_sections_material_is_refused_under_audit(self) -> None:
        other = min(catalog().by_identity()[(CRYPTID_FOREST_CHAPTER, 2)].item_maxima)
        self.assertEqual(200, self.start("f-audit-start", CRYPTID_FOREST_CHAPTER, 1)[0])
        items = list(self.userdata()["itemList"])
        items[other - 1] += 1
        status, refused = self.clear(
            "f-audit", CRYPTID_FOREST_CHAPTER, 1, items={str(other): 1}, item_list=items,
        )
        self.assertEqual((409, "invalid_local_hunting_result"), (status, refused["error"]))
        self.assertEqual("hunting_active", self.account()["tutorial_phase"])

    def test_neither_area_is_advertised_in_any_selector(self) -> None:
        """The client reads a hardcoded list for both, so an advertised row
        could only duplicate them into a menu they do not belong to."""
        lists = catalog().client_lists(progress(42, 1))
        for name, entries in lists.items():
            with self.subTest(list=name):
                self.assertEqual([], [row for row in entries if row.startswith("70")])


if __name__ == "__main__":
    unittest.main()
