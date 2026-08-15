from dataclasses import replace
import json
from http.client import HTTPConnection
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import (
    CLASS_LIMIT_ERROR_CODE,
    NOT_ENOUGH_ITEMS_ERROR_CODE,
    BootstrapServer,
    BootstrapState,
)
from liminal_gate.bootstrap_parsers import _valid_generic_character_record
from liminal_gate.event_catalog import (
    EventCatalog,
    EventStage,
    build_bundled_collab_special_policy,
    build_bundled_counter_descent_policy,
)
from liminal_gate.event_flag_data import music_event_flags
from liminal_gate.hunting_catalog import build_bundled_hunting_policy
from liminal_gate.save_validation import ITEM_SLOTS, MAX_ITEM_STACK
from liminal_gate.tuning import DEFAULT_TUNING
from tests.support import bootstrap_profile, get, request, start_server, stop_server
from tests.support import post as support_post, request as support_request
from tests.support import serve


def character(character_id: int) -> dict[str, object]:
    return {"id": character_id, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0], "jobLevels": [1, 0, 0], "jobID": 0, "flags": 0, "skillBoost": 0}


class EventRuntimeTest(unittest.TestCase):
    def test_folded_archive_selector_opens_every_cataloged_section_over_http(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 0x01000000 | (21 << 6) | 1, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((
                EventStage("yamamoto", "sp_ch_2007", 2007, 1, 15, 0, 0, (), unlock_after_chapter=10, selector_id="2007"),
                EventStage("yamamoto", "sp_ch_2007", 2007, 2, 30, 0, 0, (), unlock_after_chapter=10, selector_id="2007"),
                EventStage("mechtula", "sp_ch_2017", 2017, 5, 35, 0, 0, (), unlock_after_chapter=20, selector_id="2017-5"),
            ))
            profile = bootstrap_profile()
            server = BootstrapServer(("127.0.0.1", 0), profile, state, event_catalog=catalog)
            thread = serve(server)
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", f"/gd/get_server_status?otk={token}&requestID=folded-status")
                status_response = connection.getresponse(); status_payload = json.loads(status_response.read()); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", f"/gd/login?otk={token}&uuid=account&requestID=folded-login")
                login_response = connection.getresponse(); login_payload = json.loads(login_response.read()); connection.close()
                body = b"stamina=30&coins=0&chapter=2007&section=2&lastUpdate=1"
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=folded-start", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                start_response = connection.getresponse(); start_payload = json.loads(start_response.read()); connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, status_response.status)
            self.assertEqual(
                ["2007", "2017-5"],
                status_payload["constants"]["specialQuestList"],
            )
            self.assertEqual(200, login_response.status)
            self.assertTrue(login_payload["eventFlags"]["sp_ch_2007"]["value"])
            self.assertTrue(login_payload["eventFlags"]["sp_ch_2017"]["value"])
            self.assertEqual((200, True), (start_response.status, start_payload["success"]))
            self.assertEqual(
                {"chapter": 2007, "section": 2},
                server.state.accounts["account"]["active_generic_story"],
            )

    def test_event_start_is_accepted_over_real_http_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 16777473, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 15, 0, 0, (25,)),))
            profile = bootstrap_profile()
            server = BootstrapServer(
                ("127.0.0.1", 0),
                profile,
                state,
                event_catalog=catalog,
                hunting_catalog=build_bundled_hunting_policy(),
                stamina=True,
            )
            thread = serve(server)
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", f"/gd/get_server_status?otk={token}")
                status_response = connection.getresponse()
                status_payload = json.loads(status_response.read())
                connection.close()
                connection = HTTPConnection(*server.server_address)
                body = b"stamina=15&coins=0&chapter=2000&section=1&lastUpdate=1"
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
                connection = HTTPConnection(*server.server_address)
                collision_body = b"stamina=14&coins=0&chapter=2000&section=1&lastUpdate=1"
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=collision_body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                collision = connection.getresponse(); collision_payload = json.loads(collision.read()); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-reenter", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
                reenter = connection.getresponse(); reenter_payload = json.loads(reenter.read()); connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"])
            # Replay is body scoped: the same request ID with a different,
            # invalid entry is evaluated and refused on its own merits.
            self.assertEqual(
                (501, "unsupported_start_quest"),
                (collision.status, collision_payload["error"]),
            )
            # Entry debits the stamina meter, so the fill origin moves off zero.
            self.assertGreater(payload["refillStartTime"], 0.0)
            # Entry moved the stamina meter, so the Energy wallet is intact.
            self.assertEqual(
                100,
                server.state.accounts["account"]["userdata"]["energy"],
            )
            self.assertEqual(200, reenter.status)
            self.assertEqual(payload, reenter_payload)
            self.assertEqual(200, status_response.status)
            self.assertEqual(
                ["2000-1", "3003-1"],
                status_payload["constants"]["specialQuestList"],
            )

    def test_lucia_entry_key_spends_once_and_survives_retry_clear_and_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            token, account_id = "lucia-token", "lucia-account"
            item_list = [0] * ITEM_SLOTS
            item_list[109] = 1  # Item 110, Key of Hearts.
            initial = {
                "coins": 0,
                "energy": 0,
                "freeEnergy": 0,
                "progressCode": 0x01000000 | (14 << 6) | 1,
                "worldMapNo": 0,
                "chrdata": [character(3)],
                "itemList": item_list,
                "summonList": [],
            }
            state = BootstrapState(state_path)
            state.create_account(token, account_id, initial)
            state.accounts[account_id]["tutorial_phase"] = "free_roam"
            state._persist_locked()
            state.close()
            catalog = EventCatalog((
                EventStage(
                    "lucia_archive", "sp_ch_2006", 2006, 2,
                    35, 0, 0, (), unlock_after_chapter=13,
                    selector_id="2006", entry_item_id=110,
                    entry_item_count=1,
                ),
            ))
            start = (
                b"stamina=35&coins=0&itemID=110&itemCount=1&"
                b"chapter=2006&section=2&lastUpdate=1"
            )
            collision = (
                b"stamina=35&coins=0&itemID=110&itemCount=2&"
                b"chapter=2006&section=2&lastUpdate=1"
            )

            def post(
                server: BootstrapServer, route: str, request_id: str, body: bytes,
            ) -> tuple[int, dict]:
                return support_post(
                    server, f"/gd/{route}", request_id, body, token=token,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
                event_catalog=catalog,
            )
            try:
                status, started = post(server, "start_quest", "lucia-start", start)
                self.assertEqual((200, True, 0), (
                    status, started["success"], started["itemList"][109],
                ))
                self.assertEqual((status, started), post(
                    server, "start_quest", "lucia-start", start,
                ))
                refused_status, refused = post(
                    server, "start_quest", "lucia-start", collision,
                )
                self.assertEqual(
                    (501, "unsupported_start_quest"),
                    (refused_status, refused["error"]),
                )
                self.assertEqual(
                    0,
                    server.state.accounts[account_id]["userdata"]["itemList"][109],
                )
            finally:
                stop_server(server, thread)

            # A new request ID after process restart is re-entry into the same
            # active battle. It returns the committed inventory without a
            # second spend, covering a response lost after durable commit.
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
                event_catalog=catalog,
            )
            stale_pre_entry = list(item_list)
            clear = urlencode({
                "progressCode": initial["progressCode"],
                "worldMapNo": 0,
                "valuables": json.dumps({
                    "energyAppStore": 0, "energy": 0, "energyAndApp": 0,
                    "freeEnergy": 0, "energyGooglePlay": 0, "coins": 0,
                }),
                "chrdata": json.dumps(initial["chrdata"]),
                # Also accept the exact interruption shape: a client that
                # missed the start response can repeat only the pre-entry key.
                "itemList": json.dumps(stale_pre_entry),
                "summonList": "[]",
                "battle_result": json.dumps({
                    "coins": 0, "buddies": [], "items": {}, "exp": 0,
                    "section": 2, "monsters": [], "summons": [],
                    "luckynum": 0, "chapter": 2006,
                    "unableluckdrop": False, "boostup": [0] * 6,
                }),
                "itmp0": 0, "itmp1": 0, "lastUpdate": 1,
            }).encode()
            try:
                status, reentered = post(
                    server, "start_quest", "lucia-reenter", start,
                )
                self.assertEqual((200, True, 0), (
                    status, reentered["success"], reentered["itemList"][109],
                ))
                clear_status, cleared = post(
                    server, "clear_quest", "lucia-clear", clear,
                )
                self.assertEqual((200, 0), (
                    clear_status, cleared["itemList"][109],
                ))
                missing_status, missing = post(
                    server, "start_quest", "lucia-missing-key", start,
                )
                self.assertEqual(
                    (200, True, NOT_ENOUGH_ITEMS_ERROR_CODE),
                    (missing_status, missing["success"], missing["cmdError"]),
                )
                self.assertEqual(
                    ("free_roam", 0),
                    (
                        server.state.accounts[account_id]["tutorial_phase"],
                        server.state.accounts[account_id]["userdata"]["itemList"][109],
                    ),
                )
            finally:
                stop_server(server, thread)

            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
                event_catalog=catalog,
            )
            try:
                self.assertEqual(
                    (clear_status, cleared),
                    post(server, "clear_quest", "lucia-clear", clear),
                )
                self.assertEqual(
                    0,
                    server.state.accounts[account_id]["userdata"]["itemList"][109],
                )
            finally:
                stop_server(server, thread)

    def test_a_flagged_event_chapter_grows_luck_below_the_stamina_gate(self) -> None:
        """2006 Lucia and 7010 Cryptid Forest are `allowLucky` and reach the
        client through the generic-story handler rather than the Hunting one,
        so the source has to be offered there too.

        Both stages here cost five stamina, under `LUCK_GAIN_MIN_STAMINA`, so
        the battle-end gain cannot fire and any Luck is the Lucky-enemy source.
        The unflagged control proves the confirmed rule still holds.
        """
        for chapter, flagged in ((2006, True), (2000, False)):
            with self.subTest(chapter=chapter):
                with tempfile.TemporaryDirectory() as directory:
                    path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
                    state.create_account(token, "account", {
                        "coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 16777346,
                        "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": [],
                        "teamMembers": [3, 0, 0, 0, 0, 0],
                    })
                    state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
                    catalog = EventCatalog((EventStage("test", "sp_test", chapter, 1, 5, 0, 0, ()),))
                    server = BootstrapServer(
                        ("127.0.0.1", 0), bootstrap_profile(), state, event_catalog=catalog,
                    )
                    thread = serve(server)
                    start = f"stamina=5&coins=0&chapter={chapter}&section=1&lastUpdate=1".encode()
                    clear = urlencode({
                        "progressCode": 16777346, "worldMapNo": 0,
                        "valuables": json.dumps({
                            "energyAppStore": 0, "energy": 0, "energyAndApp": 0,
                            "freeEnergy": 0, "energyGooglePlay": 0, "coins": 0,
                        }),
                        "chrdata": json.dumps([character(3)]), "itemList": "[]", "summonList": "[]",
                        "battle_result": json.dumps({
                            "coins": 0, "buddies": [], "items": {}, "exp": 0, "section": 1,
                            "monsters": [], "summons": [], "luckynum": 0, "chapter": chapter,
                            "unableluckdrop": False, "boostup": [0] * 6,
                        }),
                        "itmp0": 0, "itmp1": 0, "lastUpdate": 1,
                    }).encode()
                    try:
                        for attempt in range(24):
                            connection = HTTPConnection(*server.server_address)
                            connection.request(
                                "POST", f"/gd/start_quest?otk={token}&requestID=luck-start-{attempt}",
                                body=start, headers={"Content-Type": "application/x-www-form-urlencoded"},
                            )
                            self.assertEqual(200, connection.getresponse().status); connection.close()
                            connection = HTTPConnection(*server.server_address)
                            connection.request(
                                "POST", f"/gd/clear_quest?otk={token}&requestID=luck-clear-{attempt}",
                                body=clear, headers={"Content-Type": "application/x-www-form-urlencoded"},
                            )
                            self.assertEqual(200, connection.getresponse().status); connection.close()
                    finally:
                        server.shutdown(); thread.join(); server.server_close()
                    luck = next(
                        int(row.get("luck", 0))
                        for row in state.accounts["account"]["userdata"]["chrdata"]
                        if row["id"] == 3
                    )
                    if flagged:
                        self.assertGreater(luck, 0, "a flagged event chapter granted no Luck")
                    else:
                        self.assertEqual(0, luck, "a five-stamina unflagged chapter granted Luck")

    def test_event_clear_grants_character_over_real_http_transport(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 16777346, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 15, 0, 0, (25,)),))
            profile = bootstrap_profile()
            server = BootstrapServer(("127.0.0.1", 0), profile, state, event_catalog=catalog)
            thread = serve(server)
            start = b"stamina=15&coins=0&chapter=2000&section=1&lastUpdate=1"
            clear = urlencode({"progressCode": 16777346, "worldMapNo": 0, "valuables": json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 0}), "chrdata": json.dumps([character(3)]), "itemList": "[]", "summonList": "[]", "battle_result": json.dumps({"coins": 0, "buddies": [], "items": {}, "exp": 0, "section": 1, "monsters": [], "summons": [], "luckynum": 0, "chapter": 2000, "unableluckdrop": False, "boostup": [0] * 6}), "itmp0": 0, "itmp1": 0, "lastUpdate": 1}).encode()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=start, headers={"Content-Type": "application/x-www-form-urlencoded"})
                self.assertEqual(200, connection.getresponse().status); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/clear_quest?otk={token}&requestID=event-clear", body=clear, headers={"Content-Type": "application/x-www-form-urlencoded"})
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", f"/gd/userdata?otk={token}")
                userdata_response = connection.getresponse(); userdata = json.loads(userdata_response.read()); connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertEqual([3, 25], [row["id"] for row in payload["chrdata"]])
            self.assertEqual(200, userdata_response.status)
            granted = next(row for row in userdata["chrdata"] if row["id"] == 25)
            self.assertEqual([1.0, 0.0, 0.0], granted["jobLevels"])
            # The durable roster holds one shape. A grant that stored the
            # result-screen shape instead refused every later clear, because
            # each settlement check reads the roster through this validator.
            self.assertTrue(_valid_generic_character_record(granted))

    def test_party_save_after_interrupted_event_returns_account_to_free_roam(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 77, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 15, 0, 0, (25,)),))
            profile = bootstrap_profile()
            server = BootstrapServer(("127.0.0.1", 0), profile, state, event_catalog=catalog)
            thread = serve(server)
            start = b"stamina=15&coins=0&chapter=2000&section=1&lastUpdate=1"
            party = urlencode({
                "chrdata": json.dumps([character(3)]), "teamMembers": json.dumps([3, 0, 0, 0, 0, 0]),
                "teamMembers_VS": json.dumps([0] * 18), "teamBuddies_VS": json.dumps([0] * 18),
                "teamNo": "1", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
            }).encode()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/start_quest?otk={token}&requestID=event-start", body=start, headers={"Content-Type": "application/x-www-form-urlencoded"})
                self.assertEqual(200, connection.getresponse().status); connection.close()
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", f"/gd/userdata?otk={token}&requestID=decline-resume", body=party, headers={"Content-Type": "application/x-www-form-urlencoded"})
                response = connection.getresponse(); payload = json.loads(response.read()); connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            self.assertEqual(200, response.status)
            self.assertTrue(payload["success"])
            self.assertEqual("free_roam", state.accounts["account"]["tutorial_phase"])
            self.assertIsNone(state.accounts["account"]["active_generic_story"])

    def test_event_clear_grants_character_once_and_replays_after_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"; token = "token"; state = BootstrapState(path)
            state.create_account(token, "account", {"coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 77, "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": []})
            state.accounts["account"]["tutorial_phase"] = "free_roam"; state._persist_locked()
            catalog = EventCatalog((EventStage("test", "sp_test", 2000, 1, 1, 0, 0, (25,)),))
            start = b"stamina=1&coins=0&chapter=2000&section=1&lastUpdate=1"
            self.assertEqual("success", state.apply_generic_story_start(token, "start", start, catalog)[0])
            clear = urlencode({"progressCode": 77, "worldMapNo": 0, "valuables": json.dumps({"energyAppStore":0,"energy":0,"energyAndApp":0,"freeEnergy":0,"energyGooglePlay":0,"coins":0}), "chrdata": json.dumps([character(3)]), "itemList":"[]", "summonList":"[]", "battle_result":json.dumps({"coins":0,"buddies":[],"items":{},"exp":0,"section":1,"monsters":[],"summons":[],"luckynum":0,"chapter":2000,"unableluckdrop":False,"boostup":[0]*6}), "itmp0":0,"itmp1":0,"lastUpdate":1}).encode()
            self.assertEqual("success", state.apply_generic_story_clear(token, "clear", clear, catalog)[0])
            state.close()
            restarted = BootstrapState(path)
            try:
                replay = restarted.apply_generic_story_clear(token, "clear", clear, catalog)
                self.assertEqual("replay", replay[0]); self.assertEqual([3, 25], [row["id"] for row in restarted.accounts["account"]["userdata"]["chrdata"]])
            finally:
                restarted.close()

    def test_jade_clear_reconciles_reported_and_fixed_coins_and_replays(self) -> None:
        """Regress the original-client 2004-1 result contract over real HTTP."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            token, account_id = "jade-token", "jade-account"
            state = BootstrapState(path)
            state.create_account(
                token,
                account_id,
                {
                    "coins": 11005,
                    "energy": 0,
                    "freeEnergy": 25,
                    "progressCode": 16777735,
                    "worldMapNo": 0,
                    "chrdata": [character(3), character(673)],
                    "itemList": [0] * 181,
                    "summonList": [0] * 16,
                },
            )
            state.accounts[account_id]["tutorial_phase"] = "free_roam"
            state._persist_locked()
            catalog = EventCatalog((
                EventStage(
                    "jade_dragon_hunt", "sp_ch_2004", 2004, 1,
                    15, 0, 0, (673,), unlock_after_chapter=4,
                ),
            ))
            profile = bootstrap_profile()

            def post(
                server: BootstrapServer, request_id: str, body: bytes,
                route: str = "clear_quest",
            ) -> tuple[int, dict]:
                return support_post(
                    server, f"/gd/{route}", request_id, body, token=token,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            def clear_body(*, wallet_coins: int = 11824, itmp0: int = -1) -> bytes:
                advanced = character(3)
                advanced["jobLevels"] = [4097, 0, 0]
                advanced["skillBoost"] = 2
                items = [0] * 181
                for item_id, count in {16: 1, 105: 1, 122: 1, 123: 1, 181: 8}.items():
                    items[item_id - 1] = count
                return urlencode({
                    "progressCode": 16777735,
                    "worldMapNo": 0,
                    "valuables": json.dumps({
                        "energyAppStore": 0,
                        "energy": 0,
                        "energyAndApp": 0,
                        "freeEnergy": 25,
                        "energyGooglePlay": 0,
                        "coins": wallet_coins,
                    }),
                    "chrdata": json.dumps([advanced, character(673)]),
                    "itemList": json.dumps(items),
                    "summonList": json.dumps([0] * 16),
                    "battle_result": json.dumps({
                        "coins": 819,
                        "buddies": [],
                        "items": {"16": 1, "105": 1, "122": 1, "123": 1, "181": 8},
                        "exp": 6851,
                        "section": 1,
                        "monsters": [],
                        "summons": [],
                        "luckynum": 0,
                        "chapter": 2004,
                        "unableluckdrop": False,
                        "boostup": [2, 0, 0, 0, 0, 0],
                    }),
                    "itmp0": itmp0,
                    "itmp1": 0,
                    "lastUpdate": 1,
                }).encode()

            state.close()
            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(path),
                event_catalog=catalog,
            )
            start = b"stamina=15&coins=0&chapter=2004&section=1&lastUpdate=1"
            try:
                start_status, start_payload = post(
                    server, "jade-start", start, "start_quest"
                )
                self.assertEqual(
                    (200, True),
                    (start_status, start_payload["success"]),
                )
                sentinel_status, sentinel_payload = post(
                    server, "bad-sentinel", clear_body(itmp0=-2)
                )
                self.assertEqual(
                    (501, "unsupported_clear_quest"),
                    (sentinel_status, sentinel_payload["error"]),
                )
                wallet_status, wallet_payload = post(
                    server, "stale-wallet", clear_body(wallet_coins=12124)
                )
                self.assertEqual(
                    (409, "event_clear_wallet_conflict"),
                    (wallet_status, wallet_payload["error"]),
                )
                clear = clear_body()
                status, payload = post(server, "jade-clear", clear)
                self.assertEqual((200, 11824), (status, payload["coins"]))
                self.assertEqual(
                    (status, payload),
                    post(server, "jade-clear", clear),
                )
            finally:
                stop_server(server, thread)

            durable = json.loads(path.read_text(encoding="utf-8"))["accounts"][account_id]
            self.assertEqual("free_roam", durable["tutorial_phase"])
            self.assertIsNone(durable["active_generic_story"])
            self.assertEqual(11824, durable["userdata"]["coins"])
            self.assertEqual(27, durable["userdata"]["freeEnergy"])
            self.assertEqual(2, len(durable["userdata"]["chrdata"]))
            self.assertEqual(1, durable["userdata"]["itemList"][15])
            self.assertEqual(8, durable["userdata"]["itemList"][180])

            restarted, restarted_thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(path),
                event_catalog=catalog,
            )
            try:
                self.assertEqual(
                    (status, payload),
                    post(restarted, "jade-clear", clear),
                )
            finally:
                stop_server(restarted, restarted_thread)
            durable = json.loads(path.read_text(encoding="utf-8"))["accounts"][account_id]
            self.assertEqual((11824, 27), (
                durable["userdata"]["coins"],
                durable["userdata"]["freeEnergy"],
            ))


class EidolonRuntimeTest(unittest.TestCase):
    """Converted solo Eidolon drops persist at the result-screen boundary."""

    def test_visibility_drop_and_restart_replay_over_real_http(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            token, account_id = "eidolon-token", "eidolon-account"
            state = BootstrapState(state_path)
            initial = {
                "coins": 0,
                "energy": 0,
                "freeEnergy": 20,
                "progressCode": 0x01000000 | (4 << 6) | 1,
                "worldMapNo": 0,
                "chrdata": [character(3)],
                "itemList": [0] * 181,
                "summonList": [0] * 16,
            }
            state.create_account(token, account_id, initial)
            state.accounts[account_id]["tutorial_phase"] = "free_roam"
            state._persist_locked()
            state.close()
            catalog = EventCatalog((
                EventStage(
                    "eidolon_artemis", "sp_ch_4100", 4100, 1,
                    10, 0, 0, (), summon_ids=(4,), selector="eidolon",
                    unlock_after_chapter=3,
                ),
            ))
            profile = bootstrap_profile()

            def request(
                server: BootstrapServer, method: str, path: str,
                body: bytes | None = None,
            ) -> tuple[int, dict]:
                return support_request(
                    server, method, path, body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

            clear = urlencode({
                "progressCode": initial["progressCode"],
                "worldMapNo": 0,
                "valuables": json.dumps({
                    "energyAppStore": 0, "energy": 0, "energyAndApp": 0,
                    "freeEnergy": 20, "energyGooglePlay": 0, "coins": 0,
                }),
                "chrdata": json.dumps(initial["chrdata"]),
                "itemList": json.dumps(initial["itemList"]),
                # ClearQuest serializes this before ShowSummonGet adds the drop.
                "summonList": json.dumps(initial["summonList"]),
                "battle_result": json.dumps({
                    "coins": 0, "buddies": [], "items": {}, "exp": 0,
                    "section": 1, "monsters": [], "summons": [4],
                    "luckynum": 0, "chapter": 4100,
                    "unableluckdrop": False, "boostup": [0] * 6,
                }),
                "itmp0": 0, "itmp1": 0, "lastUpdate": 1,
            }).encode()
            start = b"stamina=10&coins=0&chapter=4100&section=1&lastUpdate=1"

            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                event_catalog=catalog,
            )
            try:
                status, server_status = request(
                    server, "GET", f"/gd/get_server_status?otk={token}"
                )
                self.assertEqual(200, status)
                self.assertEqual(
                    ["4100-1"],
                    server_status["constants"]["eidolonQuestList"],
                )
                status, _ = request(
                    server, "POST",
                    f"/gd/start_quest?otk={token}&requestID=eidolon-start",
                    start,
                )
                self.assertEqual(200, status)
                status, cleared = request(
                    server, "POST",
                    f"/gd/clear_quest?otk={token}&requestID=eidolon-clear",
                    clear,
                )
                self.assertEqual(200, status, cleared)
                self.assertNotIn("summonList", cleared)
                self.assertEqual(
                    1,
                    server.state.accounts[account_id]["userdata"]["summonList"][3],
                )
            finally:
                server.shutdown(); thread.join(); server.server_close()

            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                event_catalog=catalog,
            )
            try:
                status, replayed = request(
                    server, "POST",
                    f"/gd/clear_quest?otk={token}&requestID=eidolon-clear",
                    clear,
                )
                self.assertEqual((200, cleared), (status, replayed))
                self.assertEqual(
                    1,
                    server.state.accounts[account_id]["userdata"]["summonList"][3],
                )
            finally:
                server.shutdown(); thread.join(); server.server_close()

    def test_unlisted_owned_or_multiple_drop_is_rejected_without_mutation(self) -> None:
        catalog = EventCatalog((
            EventStage(
                "eidolon_artemis", "sp_ch_4100", 4100, 1,
                10, 0, 0, (), summon_ids=(4,), selector="eidolon",
            ),
        ))
        for reported, owned in (([9], False), ([4], True), ([4, 4], False)):
            with self.subTest(reported=reported, owned=owned), tempfile.TemporaryDirectory() as directory:
                state = BootstrapState(Path(directory) / "state.json")
                summons = [0] * 16
                if owned:
                    summons[3] = 1
                userdata = {
                    "coins": 0, "energy": 0, "freeEnergy": 20,
                    "progressCode": 1, "worldMapNo": 0,
                    "chrdata": [character(3)], "itemList": [],
                    "summonList": summons,
                }
                state.create_account("token", "account", userdata)
                state.accounts["account"]["tutorial_phase"] = "free_roam"
                state._persist_locked()
                start = b"stamina=10&coins=0&chapter=4100&section=1&lastUpdate=1"
                self.assertEqual(
                    "success",
                    state.apply_generic_story_start("token", "start", start, catalog)[0],
                )
                clear = urlencode({
                    "progressCode": 1, "worldMapNo": 0,
                    "valuables": json.dumps({
                        "energyAppStore": 0, "energy": 0, "energyAndApp": 0,
                        "freeEnergy": 20, "energyGooglePlay": 0, "coins": 0,
                    }),
                    "chrdata": json.dumps(userdata["chrdata"]),
                    "itemList": "[]", "summonList": json.dumps(summons),
                    "battle_result": json.dumps({
                        "coins": 0, "buddies": [], "items": {}, "exp": 0,
                        "section": 1, "monsters": [], "summons": reported,
                        "luckynum": 0, "chapter": 4100,
                        "unableluckdrop": False, "boostup": [0] * 6,
                    }),
                    "itmp0": 0, "itmp1": 0, "lastUpdate": 1,
                }).encode()
                before = list(summons)
                self.assertEqual(
                    "invalid_local_event_result",
                    state.apply_generic_story_clear(
                        "token", "clear", clear, catalog
                    )[0],
                )
                self.assertEqual(
                    before,
                    state.accounts["account"]["userdata"]["summonList"],
                )
                self.assertEqual(
                    "generic_story_active",
                    state.accounts["account"]["tutorial_phase"],
                )
                state.close()


class TowerRuntimeTest(unittest.TestCase):
    """The first Tower stage uses the solo event transport and durable state."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.profile = bootstrap_profile()
        self.catalog = EventCatalog((
            EventStage(
                "tower_of_temptation",
                "sp_ch_9010",
                9010,
                1,
                15,
                0,
                0,
                (),
                selector="tower",
                unlock_after_chapter=3,
            ),
        ))
        self.token, self.account_id = "tower-token", "tower-account"
        state = BootstrapState(self.state_path)
        state.create_account(
            self.token,
            self.account_id,
            {
                "coins": 0,
                "energy": 20,
                "freeEnergy": 2,
                "progressCode": 0x01000000 | (4 << 6) | 1,
                "worldMapNo": 0,
                "chrdata": [character(3)],
                "itemList": [],
                "summonList": [],
            },
        )
        state.accounts[self.account_id]["tutorial_phase"] = "free_roam"
        state._persist_locked()
        state.close()
        self.start_server()

    def tearDown(self) -> None:
        self.stop_server()
        self.temporary_directory.cleanup()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0),
            self.profile,
            BootstrapState(self.state_path),
            event_catalog=self.catalog,
            stamina=True,
        )

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def get(self, path: str) -> tuple[int, dict]:
        return get(self.server, path)

    def post(self, path: str, body: bytes) -> tuple[int, dict]:
        return request(
            self.server, "POST", path, body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][self.account_id]

    def clear_body(
        self, *, coins: int = 0, wallet_coins: int | None = None,
    ) -> bytes:
        userdata = self.account()["userdata"]
        return urlencode({
            "progressCode": userdata["progressCode"],
            "worldMapNo": userdata["worldMapNo"],
            "valuables": json.dumps({
                "energyAppStore": 0,
                "energy": userdata["energy"],
                "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"],
                "energyGooglePlay": 0,
                "coins": (
                    userdata["coins"] + coins
                    if wallet_coins is None
                    else wallet_coins
                ),
            }),
            "chrdata": json.dumps(userdata["chrdata"]),
            "itemList": json.dumps(userdata["itemList"]),
            "summonList": json.dumps(userdata["summonList"]),
            "battle_result": json.dumps({
                "coins": coins,
                "buddies": [],
                "items": {},
                "exp": 0,
                "section": 1,
                "monsters": [],
                "summons": [],
                "luckynum": 0,
                "chapter": 9010,
                "unableluckdrop": False,
                "boostup": [0] * 6,
            }),
            "itmp0": 0,
            "itmp1": 0,
            "lastUpdate": 1,
        }).encode()

    def test_locked_floor_is_hidden_and_refused_over_http(self) -> None:
        self.stop_server()
        state = BootstrapState(self.state_path)
        state.accounts[self.account_id]["userdata"]["progressCode"] = (
            0x01000000 | (3 << 6) | 1
        )
        state._persist_locked()
        state.close()
        self.start_server()

        status, server_status = self.get(
            f"/gd/get_server_status?otk={self.token}&requestID=status-locked"
        )
        self.assertEqual(200, status)
        self.assertEqual([], server_status["constants"]["towerQuestList"])
        start = b"stamina=15&coins=0&chapter=9010&section=1&lastUpdate=1"
        status, refused = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=locked",
            start,
        )
        self.assertEqual((409, "event_stage_locked"), (status, refused["error"]))
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_visibility_entry_clear_and_restart_replay(self) -> None:
        status, server_status = self.get(
            f"/gd/get_server_status?otk={self.token}&requestID=status"
        )
        self.assertEqual(200, status)
        constants = server_status["constants"]
        self.assertEqual(["9010-1"], constants["towerQuestList"])
        self.assertEqual(["3003-1"], constants["specialQuestList"])

        status, login = self.get(
            f"/gd/login?otk={self.token}&uuid={self.account_id}&requestID=login"
        )
        self.assertEqual(200, status)
        self.assertIn("sp_ch_9010", login["eventFlags"])
        # Only this fixture's own stage is flagged. Melting Pot (9100--9102) is
        # a separate catalog slice with its own tests; it is absent here because
        # this catalog does not carry it, not because the range is disabled.
        self.assertNotIn("sp_ch_9100", login["eventFlags"])

        status, multiplayer = self.get(
            f"/gd/multiplay_enable?otk={self.token}&requestID=multiplayer"
        )
        self.assertEqual(200, status)
        self.assertEqual(
            {"success": True, "enable": False, "enablemain": False},
            {
                key: multiplayer[key]
                for key in ("success", "enable", "enablemain")
            },
        )

        start = b"stamina=15&coins=0&chapter=9010&section=1&lastUpdate=1"
        status, started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=start",
            start,
        )
        self.assertEqual((200, True), (status, started["success"]))
        refill_start = self.account()["userdata"]["refillStartTime"]
        self.assertGreater(refill_start, 0.0)
        self.assertEqual("generic_story_active", self.account()["tutorial_phase"])

        collision = b"stamina=16&coins=0&chapter=9010&section=1&lastUpdate=1"
        status, refused = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=start",
            collision,
        )
        self.assertEqual((501, "unsupported_start_quest"), (status, refused["error"]))
        self.assertEqual(refill_start, self.account()["userdata"]["refillStartTime"])

        status, retried = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=start-again",
            start,
        )
        self.assertEqual((200, started), (status, retried))
        self.assertEqual(refill_start, self.account()["userdata"]["refillStartTime"])

        unknown = b"stamina=15&coins=0&chapter=9010&section=2&lastUpdate=1"
        status, refused = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=unknown",
            unknown,
        )
        self.assertEqual((501, "unsupported_start_quest"), (status, refused["error"]))

        donation = b"stamina=5&coins=0&chapter=9100&section=1&lastUpdate=1"
        status, refused = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=donation",
            donation,
        )
        self.assertEqual((501, "unsupported_start_quest"), (status, refused["error"]))

        self.restart()
        status, refused = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=bad-clear",
            self.clear_body(coins=1, wallet_coins=0),
        )
        self.assertEqual(
            (409, "event_clear_wallet_conflict"),
            (status, refused["error"]),
        )
        self.assertEqual("generic_story_active", self.account()["tutorial_phase"])

        clear = self.clear_body()
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clear",
            clear,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual("free_roam", self.account()["tutorial_phase"])
        self.assertIsNone(self.account()["active_generic_story"])
        self.assertEqual(
            0x01000000 | (4 << 6) | 1,
            self.account()["userdata"]["progressCode"],
        )

        self.restart()
        self.assertEqual(
            (status, cleared),
            self.post(
                f"/gd/clear_quest?otk={self.token}&requestID=clear",
                clear,
            ),
        )


class _CounterDescentRangeHarness:
    """Server lifecycle and clear form for the 8000-series families.

    Shared rather than copied because that is the claim being made about these
    chapters: Strikes Back and the two Special Quest families in the same range
    take the same start, the same durable settlement, and the same clear body.
    A subclass changes the catalog it serves and the progress it serves it to,
    and nothing else.
    """

    progress_chapter = 7

    def build_catalog(self) -> EventCatalog:
        return build_bundled_counter_descent_policy()

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.profile = bootstrap_profile()
        self.catalog = self.build_catalog()
        self.token, self.account_id = "descent-token", "descent-account"
        state = BootstrapState(self.state_path)
        state.create_account(
            self.token,
            self.account_id,
            {
                "coins": 0,
                "energy": 20,
                "freeEnergy": 2,
                "progressCode": 0x01000000 | (self.progress_chapter << 6) | 1,
                "worldMapNo": 0,
                "chrdata": [character(3)],
                # The client's own inventory and Summon shapes: a projected
                # settlement is checked against them, so a toy array here would
                # exercise a save the client cannot produce.
                "itemList": [0] * ITEM_SLOTS,
                "summonList": [0] * 16,
            },
        )
        state.accounts[self.account_id]["tutorial_phase"] = "free_roam"
        state._persist_locked()
        state.close()
        self.start_server()

    def tearDown(self) -> None:
        self.stop_server()
        self.temporary_directory.cleanup()

    def start_server(self) -> None:
        self.server, self.thread = start_server(
            ("127.0.0.1", 0),
            self.profile,
            BootstrapState(self.state_path),
            event_catalog=self.catalog,
            stamina=True,
        )

    def stop_server(self) -> None:
        stop_server(self.server, self.thread)

    def restart(self) -> None:
        self.stop_server()
        self.start_server()

    def get(self, path: str) -> tuple[int, dict]:
        return get(self.server, path)

    def post(self, path: str, body: bytes) -> tuple[int, dict]:
        return request(
            self.server, "POST", path, body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    def account(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][self.account_id]

    def clear_body(
        self, *, chapter: int = 8000, section: int = 4,
        experience: int = 0, coins: int = 0,
        items: dict[str, int] | None = None,
        summons: list[int] | None = None,
        inventory: list[int] | None = None,
        buddies: list[int] | None = None,
    ) -> bytes:
        """Compose a clear the way the surviving client composes one.

        ``items`` are the drops the battle reports, and the submitted inventory
        defaults to the durable counts plus exactly those drops -- the one array
        a projected settlement accepts. ``inventory`` overrides it so a
        mismatched submission can be exercised on its own.
        """
        userdata = self.account()["userdata"]
        reported = items or {}
        if inventory is None:
            inventory = list(userdata["itemList"])
            for item_id, count in reported.items():
                inventory[int(item_id) - 1] = min(
                    MAX_ITEM_STACK, inventory[int(item_id) - 1] + count,
                )
        return urlencode({
            "progressCode": userdata["progressCode"],
            "worldMapNo": userdata["worldMapNo"],
            "valuables": json.dumps({
                "energyAppStore": 0,
                "energy": userdata["energy"],
                "energyAndApp": 0,
                "freeEnergy": userdata["freeEnergy"],
                "energyGooglePlay": 0,
                "coins": userdata["coins"] + coins,
            }),
            "chrdata": json.dumps(userdata["chrdata"]),
            "itemList": json.dumps(inventory),
            "summonList": json.dumps(userdata["summonList"]),
            "battle_result": json.dumps({
                "coins": coins,
                "buddies": buddies or [],
                "items": reported,
                "exp": experience,
                "section": section,
                "monsters": [],
                "summons": summons or [],
                "luckynum": 0,
                "chapter": chapter,
                "unableluckdrop": False,
                "boostup": [0] * 6,
            }),
            "itmp0": 0,
            "itmp1": 0,
            "lastUpdate": 1,
        }).encode()


class CounterDescentRuntimeTest(_CounterDescentRangeHarness, unittest.TestCase):
    """The standard Strikes Back slice uses the real HTTP and durable path."""

    def test_visibility_charge_projected_clear_and_restart_replay(self) -> None:
        status, server_status = self.get(
            f"/gd/get_server_status?otk={self.token}&requestID=status"
        )
        self.assertEqual(200, status)
        constants = server_status["constants"]
        self.assertEqual(["8000", "8001"], constants["descentHuntingList"])
        self.assertEqual(["3003-1"], constants["specialQuestList"])
        status, login = self.get(
            f"/gd/login?otk={self.token}&uuid={self.account_id}&requestID=login"
        )
        self.assertEqual(200, status)
        self.assertEqual(
            sorted([
                *music_event_flags(),
                *(f"sp_ch_8000-{section}" for section in range(1, 5)),
                *(f"sp_ch_8001-{section}" for section in range(1, 5)),
            ]),
            sorted(login["eventFlags"]),
        )

        locked = b"stamina=5&coins=0&chapter=8002&section=1&lastUpdate=1"
        status, refused = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=locked",
            locked,
        )
        self.assertEqual((409, "event_stage_locked"), (status, refused["error"]))
        wrong = b"stamina=5&coins=0&chapter=8000&section=4&lastUpdate=1"
        self.assertEqual(
            501,
            self.post(
                f"/gd/start_quest?otk={self.token}&requestID=wrong",
                wrong,
            )[0],
        )

        start = b"stamina=15&coins=0&chapter=8000&section=4&lastUpdate=1"
        status, started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=start",
            start,
        )
        self.assertEqual((200, True), (status, started["success"]))
        # Entry debits the stamina meter, never the Energy wallet.
        self.assertEqual((20, 2), (
            self.account()["userdata"]["energy"],
            self.account()["userdata"]["freeEnergy"],
        ))
        self.assertGreater(self.account()["userdata"]["refillStartTime"], 0.0)
        # A different request id for the same active stage is an accepted retry,
        # but it cannot debit the entry a second time.
        self.assertEqual(
            200,
            self.post(
                f"/gd/start_quest?otk={self.token}&requestID=start-again",
                start,
            )[0],
        )
        self.assertEqual(20, self.account()["userdata"]["energy"])

        self.restart()
        # An inventory that is not the durable counts plus the drops the battle
        # declared is the one item refusal left: the array cannot become a grant
        # channel beside `items`.
        overstated = list(self.account()["userdata"]["itemList"])
        overstated[180] = 90
        status, refused = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=bad-clear",
            self.clear_body(items={"181": 70}, inventory=overstated),
        )
        self.assertEqual(
            (409, "invalid_local_event_result"),
            (status, refused["error"]),
        )
        self.assertEqual("generic_story_active", self.account()["tutorial_phase"])
        # No recovered source states an event stage's Summon outcome, so a
        # reported Summon stays refused rather than settled unauthored.
        status, refused = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=bad-summon",
            self.clear_body(summons=[3]),
        )
        self.assertEqual(
            (409, "invalid_local_event_result"),
            (status, refused["error"]),
        )
        self.assertEqual("generic_story_active", self.account()["tutorial_phase"])

        # A won battle reports its own experience, Coins, and drops. Refusing
        # those was the earlier zero-base policy, and it stranded the client on
        # the reward screen retrying a settlement it could never complete.
        clear = self.clear_body(experience=5400, coins=280, items={"181": 70})
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clear",
            clear,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual("free_roam", self.account()["tutorial_phase"])
        self.assertEqual(0x01000000 | (7 << 6) | 1, self.account()["userdata"]["progressCode"])
        settled = self.account()["userdata"]
        self.assertEqual(70, settled["itemList"][180])
        self.assertEqual(ITEM_SLOTS, len(settled["itemList"]))
        self.assertEqual(280, settled["coins"])
        self.assertEqual(70, cleared["itemList"][180])
        self.assertEqual(280, cleared["coins"])
        self.restart()
        self.assertEqual(
            (status, cleared),
            self.post(
                f"/gd/clear_quest?otk={self.token}&requestID=clear",
                clear,
            ),
        )
        # The drop settles once: a second clear under a fresh request id cannot
        # mint another 70.
        self.assertEqual(70, self.account()["userdata"]["itemList"][180])

    def test_late_families_settle_and_collaboration_rows_remain_refused(self) -> None:
        self.stop_server()
        state = BootstrapState(self.state_path)
        state.accounts[self.account_id]["userdata"]["progressCode"] = (
            0x01000000 | (19 << 6) | 1
        )
        state._persist_locked()
        state.close()
        self.start_server()

        status, server_status = self.get(
            f"/gd/get_server_status?otk={self.token}&requestID=late-status"
        )
        self.assertEqual(200, status)
        self.assertEqual(
            [
                *(str(chapter) for chapter in range(8000, 8008)),
                *(str(chapter) for chapter in range(8012, 8018)),
            ],
            server_status["constants"]["descentHuntingList"],
        )

        for chapter in (8008, 8011, 8018):
            body = (
                f"stamina=5&coins=0&chapter={chapter}&section=1&lastUpdate=1"
            ).encode()
            refused_status, refused = self.post(
                f"/gd/start_quest?otk={self.token}&requestID=refuse-{chapter}",
                body,
            )
            self.assertEqual(
                (501, "unsupported_start_quest"),
                (refused_status, refused["error"]),
            )

        start = b"stamina=15&coins=0&chapter=8017&section=3&lastUpdate=1"
        status, started = self.post(
            f"/gd/start_quest?otk={self.token}&requestID=late-start",
            start,
        )
        self.assertEqual((200, True), (status, started["success"]))
        active = self.account()["active_generic_story"]
        self.assertEqual({"chapter": 8017, "section": 3}, active)

        self.restart()
        clear = self.clear_body(chapter=8017, section=3)
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=late-clear",
            clear,
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual("free_roam", self.account()["tutorial_phase"])
        self.assertIsNone(self.account()["active_generic_story"])

        self.restart()
        self.assertEqual(
            (status, cleared),
            self.post(
                f"/gd/clear_quest?otk={self.token}&requestID=late-clear",
                clear,
            ),
        )


class CollabSpecialRuntimeTest(_CounterDescentRangeHarness, unittest.TestCase):
    """Battle Champs over the real HTTP path, in the menu the client drew it in.

    The harness is the Strikes Back one on purpose: these five chapters take
    the same start and the same settlement, and reusing it is what demonstrates
    that. Only the catalog, the progress that opens it, and the Companion
    channel differ. Chapter 24 is past the last of the five unlocks.
    """

    progress_chapter = 24

    def build_catalog(self) -> EventCatalog:
        return build_bundled_collab_special_policy()

    def test_the_two_cards_are_special_quests_not_strikes_back(self) -> None:
        status, server_status = self.get(
            f"/gd/get_server_status?otk={self.token}&requestID=status"
        )
        self.assertEqual(200, status)
        constants = server_status["constants"]
        # Two rows, not five: the four Battle Champs chapters are one card the
        # client expands into all eight of its tiers itself.
        self.assertEqual(["8008", "8018-1"], constants["specialQuestList"])
        self.assertEqual([], constants["descentHuntingList"])
        # Mode 3's list is present and empty rather than absent: this catalog
        # carries no Descent family, and the key is served either way.
        self.assertEqual([], constants["descentQuestList"])

    def test_login_flags_every_tier_that_exists_and_no_chapter(self) -> None:
        status, login = self.get(
            f"/gd/login?otk={self.token}&uuid={self.account_id}&requestID=login"
        )
        self.assertEqual(200, status)
        self.assertEqual(
            sorted([
                *music_event_flags(),
                *(
                    f"sp_ch_{chapter}-{section}"
                    for chapter in range(8008, 8012)
                    for section in (1, 2)
                ),
                "sp_ch_8018-1",
            ]),
            sorted(login["eventFlags"]),
        )
        # A chapter key would answer `CheckQuestFlag` for the three tiers the
        # folded card offers and BattleData does not have.
        self.assertNotIn("sp_ch_8008", login["eventFlags"])

    def test_a_declared_companion_drop_settles_the_battle(self) -> None:
        start = b"stamina=15&coins=0&chapter=8008&section=2&lastUpdate=1"
        self.assertEqual(
            200,
            self.post(f"/gd/start_quest?otk={self.token}&requestID=start", start)[0],
        )
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clear",
            self.clear_body(chapter=8008, section=2, buddies=[367]),
        )
        self.assertEqual(200, status, cleared)
        self.assertEqual("free_roam", self.account()["tutorial_phase"])

    def test_a_companion_the_section_never_declared_is_refused(self) -> None:
        """The bound these five carry that the rest of the range does not.

        368 is a real Companion and a real drop -- of Chapter 8009, not this
        one. The manifest is per section, so the refusal is too.
        """
        start = b"stamina=15&coins=0&chapter=8008&section=2&lastUpdate=1"
        self.assertEqual(
            200,
            self.post(f"/gd/start_quest?otk={self.token}&requestID=start", start)[0],
        )
        status, refused = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clear",
            self.clear_body(chapter=8008, section=2, buddies=[368]),
        )
        self.assertEqual(
            (409, "invalid_local_event_result"), (status, refused["error"]),
        )
        # The battle stays open, so the client's retry has something to settle.
        self.assertEqual(
            {"chapter": 8008, "section": 2},
            self.account()["active_generic_story"],
        )

    def test_a_tier_that_declares_no_drop_accepts_none(self) -> None:
        start = b"stamina=5&coins=0&chapter=8008&section=1&lastUpdate=1"
        self.assertEqual(
            200,
            self.post(f"/gd/start_quest?otk={self.token}&requestID=start", start)[0],
        )
        status, refused = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clear",
            self.clear_body(chapter=8008, section=1, buddies=[367]),
        )
        self.assertEqual(
            (409, "invalid_local_event_result"), (status, refused["error"]),
        )
        status, cleared = self.post(
            f"/gd/clear_quest?otk={self.token}&requestID=clean",
            self.clear_body(chapter=8008, section=1),
        )
        self.assertEqual(200, status, cleared)


class CaptiveGolemClassLimitTest(unittest.TestCase):
    """Captive Golem admits only parties inside its declared class band.

    Chapter 2008's four sections are the only ones in the game that carry
    `classMin`/`classMax`, and the client's own start gate never reads them, so
    an over-class party walked straight in
    ([reported against Sayu, class 8](https://github.com/anzensan/project-liminal-gate)).
    """

    #: Class 8, above every Captive Golem section; and class 3, inside them all.
    OVER_CLASS, WITHIN_CLASS = 831, 25

    def catalog(self) -> EventCatalog:
        stages = tuple(
            EventStage(
                "captive_golem_archive", "sp_ch_2008", 2008, section, 15, 0, 0, (),
                class_min=low, class_max=high,
            )
            for section, (low, high) in ((1, (1, 6)), (2, (1, 5)), (3, (1, 4)), (4, (1, 3)))
        )
        return EventCatalog(stages, {self.OVER_CLASS: 8, self.WITHIN_CLASS: 3})

    def start(self, party: list[int], section: int = 1, tuning=None) -> tuple[int, dict]:
        with tempfile.TemporaryDirectory() as directory:
            state = BootstrapState(Path(directory) / "state.json", tuning)
            state.create_account("token", "account", {
                "coins": 0, "energy": 100, "freeEnergy": 0, "progressCode": 16777473,
                "worldMapNo": 0, "chrdata": [character(3)], "itemList": [], "summonList": [],
                "teamMembers": party,
            })
            state.accounts["account"]["tutorial_phase"] = "free_roam"
            state._persist_locked()
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), state, event_catalog=self.catalog(),
            )
            try:
                return support_post(
                    server, "/gd/start_quest", "golem",
                    f"stamina=15&coins=0&chapter=2008&section={section}&lastUpdate=1",
                    token="token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
            finally:
                stop_server(server, thread)

    def test_an_over_class_party_is_refused_in_the_clients_own_shape(self) -> None:
        status, payload = self.start([self.OVER_CLASS, 0, 0, 0, 0, 0])
        # A refusal, not a transport error: 200 carrying the client's own
        # ClassLimit code, so the game shows its dialog and the screen returns.
        # A route's own refusal code rides `cmdError`; see docs/server-protocol.md.
        self.assertEqual(200, status, payload)
        self.assertEqual(CLASS_LIMIT_ERROR_CODE, payload["cmdError"])

    def test_a_party_inside_the_band_still_enters(self) -> None:
        status, payload = self.start([self.WITHIN_CLASS, 0, 0, 0, 0, 0])
        self.assertEqual((200, True), (status, payload["success"]))

    def test_the_band_tightens_with_each_section(self) -> None:
        """Class 3 clears every rung; the ladder is 6, 5, 4, then 3."""
        for section in (1, 2, 3, 4):
            with self.subTest(section=section):
                status, payload = self.start([self.WITHIN_CLASS, 0, 0, 0, 0, 0], section)
                self.assertEqual((200, True), (status, payload["success"]))
        for section in (1, 2, 3, 4):
            with self.subTest(section=section, party="over"):
                status, payload = self.start([self.OVER_CLASS, 0, 0, 0, 0, 0], section)
                self.assertEqual(CLASS_LIMIT_ERROR_CODE, payload["cmdError"])

    def test_an_uncapped_stage_admits_anyone(self) -> None:
        """Every other section in the game declares no band and is unaffected."""
        stage = EventStage("test", "sp_test", 2000, 1, 15, 0, 0, ())
        self.assertTrue(stage.admits_class(8))
        catalog = EventCatalog((stage,), {self.OVER_CLASS: 8})
        self.assertFalse(catalog.over_class_limit(stage, [self.OVER_CLASS, 0, 0, 0, 0, 0]))

    def test_a_character_the_catalog_cannot_describe_is_not_refused(self) -> None:
        """The gate restores a declared limit; it does not invent one."""
        catalog = self.catalog()
        stage = catalog.by_identity()[(2008, 4)]
        self.assertFalse(catalog.over_class_limit(stage, [999999, 0, 0, 0, 0, 0]))

    def test_an_operator_can_decline_the_band(self) -> None:
        """Off by request only: the default refuses this very party above."""
        relaxed = replace(DEFAULT_TUNING, gates=replace(DEFAULT_TUNING.gates, class_bands=False))
        status, payload = self.start([self.OVER_CLASS, 0, 0, 0, 0, 0], tuning=relaxed)
        self.assertEqual((200, True), (status, payload["success"]))
        self.assertNotIn("cmdError", payload)


class RaidRangeLoginParamsTest(unittest.TestCase):
    """A stage in Chapters 9000--9009 needs its raid entry on the login reply.

    The client asks `ChapterInterface.IsRaidQuest` before it asks anything of
    the server, and an absent `eventQuestParams` decodes to `RaidStatus.Lock`,
    which refuses the start on the device. Tower of Temptation is served from
    9000--9003, so this is the whole difference between a playable card and a
    dead end no server log records.
    """

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.token, self.account_id = "raid-token", "raid-account"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def login(self, chapter: int) -> dict:
        catalog = EventCatalog((
            EventStage(
                "tower_of_temptation", f"sp_ch_{chapter}", chapter, 1, 15, 0, 0, (),
                selector="tower", unlock_after_chapter=3,
            ),
        ))
        state = BootstrapState(self.state_path)
        state.create_account(
            self.token, self.account_id,
            {
                "coins": 0, "energy": 20, "freeEnergy": 2,
                "progressCode": 0x01000000 | (4 << 6) | 1, "worldMapNo": 0,
                "chrdata": [character(3)], "itemList": [], "summonList": [],
            },
        )
        state.accounts[self.account_id]["tutorial_phase"] = "free_roam"
        state._persist_locked()
        state.close()
        server, thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(self.state_path),
            event_catalog=catalog,
        )
        try:
            status, payload = get(
                server,
                f"/gd/login?otk={self.token}&uuid={self.account_id}&requestID=login",
            )
            self.assertEqual(200, status)
            return payload
        finally:
            stop_server(server, thread)

    def test_a_raid_range_stage_is_answered_with_an_unlocked_status(self) -> None:
        payload = self.login(9000)
        self.assertEqual(
            {"status": 2, "remainHp": 1.0}, payload["eventQuestParams"]["9000-1"],
        )

    def test_a_tower_range_stage_needs_no_entry(self) -> None:
        # 9010--9099 is the client's own Tower of Temptation range and takes the
        # ordinary start path, so nothing is declared for it.
        self.assertNotIn("eventQuestParams", self.login(9010))
