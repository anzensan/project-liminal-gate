from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.message_catalog import (
    MessageCatalogError,
    build_bundled_chapter_message_policy,
    eligible_chapter_messages,
    load_message_catalog,
)
from tests.support import bootstrap_profile, get, post, start_server, stop_server


class MessageLifecycleTest(unittest.TestCase):
    def test_retail_chapter_milestones_settle_directly_once_and_survive_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            profile = bootstrap_profile()
            catalog = build_bundled_chapter_message_policy()

            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                message_catalog=catalog, chapter_milestones=True,
            )
            try:
                seed = {
                    "progressCode": (8 << 6) | 9,
                    "chrdata": [], "buddyInfo": {"list": [], "record": []},
                    "summonList": [0] * 16, "itemList": [0] * 181,
                    "coins": 0, "freeEnergy": 0, "energy": 0,
                    "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0,
                }
                server.state.create_account("signup", "account", seed, catalog)
                status, login = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual((200, []), (status, login["messageList"]))
                self.assertNotIn("chapter:8:item:112", {message["id"] for message in login["messageList"]})
                self.assertEqual(
                    ["chapter:5:item:50", "chapter:6:item:112", "chapter:7:item:50"],
                    server.state.accounts["account"]["chapter_milestones_issued"],
                )
                userdata = server.state.accounts["account"]["userdata"]
                self.assertEqual((4, 3), (userdata["itemList"][49], userdata["itemList"][111]))
                self.assertTrue(all(
                    server.state.accounts["account"]["messages"][message_id]["read"]
                    for message_id in server.state.accounts["account"]["chapter_milestones_issued"]
                ))
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                message_catalog=catalog, chapter_milestones=True,
            )
            try:
                status, login = get(restarted, "/gd/login?otk=token&uuid=account")
                self.assertEqual((200, []), (status, login["messageList"]))
                self.assertEqual(
                    (4, 3),
                    tuple(restarted.state.accounts["account"]["userdata"]["itemList"][index] for index in (49, 111)),
                )
                with restarted.state.lock:
                    restarted.state.accounts["account"]["userdata"]["progressCode"] = (9 << 6) | 1
                    restarted.state._persist_locked()
                status, login = get(restarted, "/gd/login?otk=token&uuid=account")
                self.assertEqual((200, []), (status, login["messageList"]))
                self.assertEqual(6, restarted.state.accounts["account"]["userdata"]["itemList"][111])
                self.assertTrue(restarted.state.accounts["account"]["messages"]["chapter:8:item:112"]["read"])
            finally:
                stop_server(restarted, thread)

    def test_unread_chapter_mail_migrates_to_one_direct_grant(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            profile = bootstrap_profile()
            catalog = build_bundled_chapter_message_policy()
            seed = {
                "progressCode": (8 << 6) | 9,
                "chrdata": [], "buddyInfo": {"list": [], "record": []},
                "summonList": [0] * 16, "itemList": [0] * 181,
                "coins": 0, "freeEnergy": 0, "energy": 0,
                "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0,
            }
            state = BootstrapState(state_path)
            state.create_account("signup", "account", seed, catalog)
            account = state.accounts["account"]
            old_messages = eligible_chapter_messages((8 << 6) | 9, 123.0)
            for message in old_messages:
                account["messages"][message.message_id] = {
                    "id": message.message_id, "date": message.date, "read": True,
                    "days_last": message.days_last, "messages": dict(message.texts),
                    "coins": 0, "free_energy": 0,
                    "items": {str(item_id): amount for item_id, amount in message.items.items()},
                    "character_id": 0, "companion_id": 0, "companion_level": 1,
                }
            account["messages"]["chapter:7:item:50"]["read"] = False
            account["chapter_milestones_issued"] = sorted(account["messages"])
            with state.lock:
                state._persist_locked()
            state.close()

            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                message_catalog=catalog, chapter_milestones=True,
            )
            try:
                status, login = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual((200, []), (status, login["messageList"]))
                userdata = server.state.accounts["account"]["userdata"]
                self.assertEqual((2, 0), (userdata["itemList"][49], userdata["itemList"][111]))
                self.assertTrue(server.state.accounts["account"]["messages"]["chapter:7:item:50"]["read"])
                status, again = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual((200, []), (status, again["messageList"]))
                self.assertEqual(2, server.state.accounts["account"]["userdata"]["itemList"][49])
            finally:
                stop_server(server, thread)

            restarted = BootstrapState(state_path)
            self.assertEqual(2, restarted.accounts["account"]["userdata"]["itemList"][49])
            restarted.close()

    def test_interrupted_chapter_settlement_retries_from_durable_unread_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            catalog = build_bundled_chapter_message_policy()
            state = BootstrapState(state_path)
            state.create_account("signup", "account", {
                "progressCode": (6 << 6) | 1,
                "chrdata": [], "buddyInfo": {"list": [], "record": []},
                "summonList": [0] * 16, "itemList": [0] * 181,
                "coins": 0, "freeEnergy": 0, "energy": 0,
                "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0,
            }, catalog)
            with patch.object(state, "_persist_locked", side_effect=OSError("interrupted")):
                with self.assertRaises(OSError):
                    state.login_messages(
                        "account", chapter_milestones=True, now=123.0,
                        message_catalog=catalog,
                    )
            state.close()

            retried = BootstrapState(state_path)
            self.assertEqual(0, retried.accounts["account"]["userdata"]["itemList"][49])
            self.assertEqual([], retried.login_messages(
                "account", chapter_milestones=True, now=124.0,
                message_catalog=catalog,
            ))
            self.assertEqual(2, retried.accounts["account"]["userdata"]["itemList"][49])
            retried.close()

            restarted = BootstrapState(state_path)
            self.assertEqual(2, restarted.accounts["account"]["userdata"]["itemList"][49])
            restarted.close()

    def test_retail_chapter_message_table_is_exact(self) -> None:
        messages = eligible_chapter_messages((11 << 6) | 1, 123.0)
        self.assertEqual(
            [
                ("chapter:5:item:50", {50: 2}),
                ("chapter:6:item:112", {112: 3}),
                ("chapter:7:item:50", {50: 2}),
                ("chapter:8:item:112", {112: 3}),
                ("chapter:10:item:112", {112: 4}),
            ],
            [(message.message_id, message.items) for message in messages],
        )

    def test_login_read_delete_collision_and_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = root / "messages.toml"
            catalog_path.write_text(
                'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 3\nmax_free_energy = 9\nmax_coins = 99\nmax_stack = 8\n\n[[messages]]\nid = "local-1"\ndate = 1.0\ndays_last = 0\nmessages = { default = "Local message", ja = "Local message", en = "Local message" }\ncoins = 3\nfree_energy = 2\nitems = { "2" = 4 }\n',
                encoding="utf-8",
            )
            profile = bootstrap_profile()
            state_path = root / "state.json"

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), message_catalog=load_message_catalog(catalog_path))
            try:
                server.state.create_account("signup", "account", {"chrdata": [], "buddyInfo": {"list": [], "record": []}, "summonList": [0] * 16, "itemList": [0, 1, 0], "coins": 2, "freeEnergy": 1, "energy": 7, "energyAppStore": 4, "energyGooglePlay": 5, "energyAndApp": 6}, load_message_catalog(catalog_path))
                status, login = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual(200, status)
                message = login["messageList"][0]
                self.assertEqual({"id", "date", "read", "daysLast", "gifts", "coins", "energy", "chr", "item", "summon", "buddy", "title", "messages"}, set(message))
                self.assertEqual(("local-1", False, [{"id": 2, "num": 4}]), (message["id"], message["read"], message["item"]))
                read_body = urlencode({"idlist": json.dumps(["local-1"]), "lastUpdate": "1"})
                status, before_read = post(server, "/gd/delete_messages", "delete-before", read_body)
                self.assertEqual((409, "invalid_local_message"), (status, before_read["error"]))
                status, read = post(server, "/gd/read_messages", "read-one", read_body)
                self.assertEqual(200, status)
                self.assertEqual((True, ["local-1"], 5, 3, [0, 5, 0]), (read["result"], read["readlist"], read["coins"], read["freeEnergy"], read["itemList"]))
                self.assertTrue({"chrdata", "buddyInfo", "summonList", "achivementFlags", "energyAppStore", "energyGooglePlay", "energyAndApp"} <= set(read))
                status, after_read_login = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual((200, []), (status, after_read_login["messageList"]))
                self.assertTrue(server.state.accounts["account"]["messages"]["local-1"]["read"])
                self.assertEqual((status, read), post(server, "/gd/read_messages", "read-one", read_body))
                # Reusing a spent requestID with a different body is no longer
                # read as a tampered retry: this is a fresh read of a message
                # already read, which must grant nothing further.
                status, reread = post(server, "/gd/read_messages", "read-one", urlencode({"idlist": json.dumps(["local-1"])}))
                self.assertEqual((200, True, ["local-1"]), (status, reread["result"], reread["readlist"]))
                self.assertEqual((read["coins"], read["itemList"]), (reread["coins"], reread["itemList"]))
                status, deleted = post(server, "/gd/delete_messages", "delete-one", read_body)
                self.assertEqual((200, ["local-1"]), (status, deleted["deletelist"]))
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), message_catalog=load_message_catalog(catalog_path))
            try:
                self.assertEqual((200, read), post(restarted, "/gd/read_messages", "read-one", read_body))
                self.assertEqual((200, deleted), post(restarted, "/gd/delete_messages", "delete-one", read_body))
            finally:
                stop_server(restarted, thread)


class MessageRewardKindTest(unittest.TestCase):
    """The client's record carries four reward channels beside coins and items.

    Two of them can be delivered here, because this server already owns the
    durable models they need: the roster a character joins, and the box a
    Companion enters. The other two are refused rather than displayed and
    dropped, which would look to a player like a reward that never arrived.
    """

    def _catalog(self, root: Path, body: str) -> object:
        path = root / "messages.toml"
        path.write_text(
            'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 3\n'
            'max_free_energy = 9\nmax_coins = 99\nmax_stack = 8\n\n' + body,
            encoding="utf-8",
        )
        return load_message_catalog(path)

    def _serve(self, catalog: object, state_path: Path, userdata: dict[str, object]):
        server, thread = start_server(
            ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
            message_catalog=catalog,
        )
        server.state.create_account("signup", "account", userdata, catalog)
        return server, thread

    def _account(self) -> dict[str, object]:
        return {
            "chrdata": [], "buddyInfo": {"list": [], "record": []}, "summonList": [0] * 16,
            "itemList": [0, 0, 0], "coins": 0, "freeEnergy": 0, "energy": 0,
            "energyAppStore": 0, "energyGooglePlay": 0, "energyAndApp": 0,
        }

    def _read(self, server, request_id: str = "read"):
        body = urlencode({"idlist": json.dumps(["local-1"]), "lastUpdate": "1"})
        return post(server, "/gd/read_messages", request_id, body)

    MESSAGE = (
        '[[messages]]\nid = "local-1"\ndate = 1.0\ndays_last = 0\n'
        'messages = { default = "d", ja = "j", en = "e" }\ncoins = 0\nfree_energy = 0\nitems = {}\n'
    )

    def test_a_character_present_joins_the_roster_and_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            catalog = self._catalog(root, self.MESSAGE + "character_id = 1018\n")
            server, thread = self._serve(catalog, state_path, self._account())
            try:
                status, read = self._read(server)
                self.assertEqual(200, status)
                self.assertEqual([1018], [row["id"] for row in read["chrdata"]])
                self.assertTrue(read["chrdata"][0]["isNew"])
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
                message_catalog=catalog,
            )
            try:
                held = restarted.state.accounts["account"]["userdata"]["chrdata"]
                self.assertEqual([1018], [row["id"] for row in held])
            finally:
                stop_server(restarted, thread)

    def test_a_companion_present_enters_the_box_at_its_declared_level(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self._catalog(root, self.MESSAGE + "companion_id = 42\ncompanion_level = 5\n")
            server, thread = self._serve(catalog, root / "state.json", self._account())
            try:
                status, read = self._read(server)
                self.assertEqual(200, status)
                owned = read["buddyInfo"]["list"]
                self.assertEqual([(42, 5)], [(row["bid"], row["lv"]) for row in owned])
                self.assertEqual(1, owned[0]["iid"])
            finally:
                stop_server(server, thread)

    def test_a_duplicate_character_present_grants_no_second_row(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self._catalog(root, self.MESSAGE + "character_id = 1018\n")
            account = self._account()
            account["chrdata"] = [{"id": 1018, "jobID": 0, "jobLevels": [1], "jobSlots": []}]
            server, thread = self._serve(catalog, root / "state.json", account)
            try:
                status, read = self._read(server)
                self.assertEqual(200, status)
                self.assertEqual([1018], [row["id"] for row in read["chrdata"]])
            finally:
                stop_server(server, thread)

    def test_a_full_companion_box_refuses_the_read_instead_of_half_settling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "messages.toml"
            path.write_text(
                'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 3\n'
                'max_free_energy = 9\nmax_coins = 99\nmax_stack = 8\n\n'
                '[[messages]]\nid = "local-1"\ndate = 1.0\ndays_last = 0\n'
                'messages = { default = "d", ja = "j", en = "e" }\ncoins = 7\nfree_energy = 0\n'
                'items = {}\ncompanion_id = 42\n',
                encoding="utf-8",
            )
            catalog = load_message_catalog(path)
            catalog = type(catalog)(
                catalog.item_slots, catalog.max_free_energy, catalog.max_coins,
                catalog.max_stack, catalog.messages, 1,
            )
            account = self._account()
            account["buddyInfo"] = {"list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 1, "exp": 0, "flag": 0, "chrID": 0}], "record": []}
            server, thread = self._serve(catalog, root / "state.json", account)
            try:
                status, refused = self._read(server)
                self.assertEqual(501, status)
                self.assertEqual("unsupported_message_read", refused["error"])
                # The coins on the same message must not have been paid either.
                self.assertEqual(0, server.state.accounts["account"]["userdata"]["coins"])
            finally:
                stop_server(server, thread)

    def test_a_summon_or_title_reward_is_refused_at_catalog_load(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for field in ("summon_id", "title_id"):
                with self.subTest(field):
                    with self.assertRaises(MessageCatalogError) as raised:
                        self._catalog(root, self.MESSAGE + f"{field} = 3\n")
                    self.assertIn("no owner", str(raised.exception))
