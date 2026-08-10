from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.bootstrap_parsers import _companion_info, _valid_generic_character_record
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
                result = read["result"]
                self.assertEqual((["local-1"], 5, 3, [0, 5, 0]), (result["readlist"], result["coins"], result["freeEnergy"], result["itemList"]))
                self.assertTrue({"chrdata", "buddyInfo", "summonList", "achivementFlags", "energyAppStore", "energyGooglePlay", "energyAndApp"} <= set(result))
                status, after_read_login = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual((200, []), (status, after_read_login["messageList"]))
                self.assertTrue(server.state.accounts["account"]["messages"]["local-1"]["read"])
                self.assertEqual((status, read), post(server, "/gd/read_messages", "read-one", read_body))
                # Reusing a spent requestID with a different body is no longer
                # read as a tampered retry: this is a fresh read of a message
                # already read, which must grant nothing further.
                status, reread = post(server, "/gd/read_messages", "read-one", urlencode({"idlist": json.dumps(["local-1"])}))
                self.assertEqual((200, ["local-1"]), (status, reread["result"]["readlist"]))
                self.assertEqual((result["coins"], result["itemList"]), (reread["result"]["coins"], reread["result"]["itemList"]))
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


class RecoveredMailShapeTest(unittest.TestCase):
    """The field shape recovered from the client's own `Message` class.

    Every expectation here is read from the reviewed client rather than from an
    observed exchange: the class declares `mes_default`/`mes_ja`/`mes_en`,
    `items` as a `List<ItemCode2>`, `buddy` as one `ItemCode`, and
    `multiplayTitle`, and declares no `gifts` member at all. Its constructor
    fills the three text fields positionally from `messages` through the LitJson
    array indexer, and `ItemCode.ctor(int, int)` packs `(id << 16) | count`.
    """

    CATALOG = (
        'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 181\n'
        'max_free_energy = 99\nmax_coins = 9999\nmax_stack = 99\n\n'
        '[[messages]]\nid = "local-1"\ndate = 7.0\ndays_last = 3\n'
        'messages = { default = "d-text", ja = "ja-text", en = "en-text" }\n'
        'coins = 0\nfree_energy = 0\nitems = { "50" = 4 }\n'
    )

    def _login(self, original_mail_shape: bool) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "messages.toml"
            path.write_text(self.CATALOG, encoding="utf-8")
            catalog = load_message_catalog(path)
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(root / "state.json"),
                message_catalog=catalog, original_mail_shape=original_mail_shape,
            )
            try:
                server.state.create_account("token", "account", {
                    "chrdata": [], "buddyInfo": {"list": [], "record": []},
                    "summonList": [0] * 16, "itemList": [0] * 181, "coins": 0,
                    "freeEnergy": 0, "energy": 0, "energyAppStore": 0,
                    "energyGooglePlay": 0, "energyAndApp": 0,
                }, catalog)
                status, login = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual(200, status)
                return login["messageList"][0]
            finally:
                stop_server(server, thread)

    def test_the_recovered_shape_carries_the_keys_the_constructor_reads(self) -> None:
        message = self._login(True)
        self.assertEqual({"id", "date", "read", "daysLast", "gifts", "messages"}, set(message))
        # `date` stays a real even though the field is a `long`: the constructor
        # reads it through LitJson's `(double)` conversion, which refuses a
        # JsonData holding an int and throws out of `Message..ctor`.
        self.assertEqual(7.0, message["date"])
        self.assertIs(float, type(message["date"]))
        # An object, not a positional array. None of `mes_default`/`mes_ja`/
        # `mes_en` is a literal in the client, which made an array look right,
        # but the constructor reads these three keys by name.
        self.assertEqual({"default": "d-text", "ja": "ja-text", "en": "en-text"}, message["messages"])

    def test_every_reward_travels_inside_one_gifts_entry(self) -> None:
        """`gifts` is the only reward channel the constructor reads.

        It never looks at a top-level `coins`, `energy`, `chr`, `item`,
        `buddy`, `summon` or `title`, which is why the shape shipped before
        this left `get_hasGift` false and drew no reward area at all.
        """
        message = self._login(True)
        self.assertNotIn("coins", message)
        self.assertNotIn("item", message)
        self.assertNotIn("gifts", set(message) - {"gifts"})
        self.assertEqual(1, len(message["gifts"]))
        gift = message["gifts"][0]
        self.assertEqual(
            {"coins", "energy", "chr", "item", "summon", "buddy", "title"}, set(gift),
        )
        # `item` is its own integer-indexed array of `{id, num}` pairs, and
        # `buddy` is one such pair.
        self.assertEqual([{"id": 50, "num": 4}], gift["item"])
        self.assertEqual({"id": 0, "num": 0}, gift["buddy"])
        self.assertEqual((0, 0, 0), (gift["coins"], gift["energy"], gift["chr"]))

    def test_the_shipped_shape_is_unchanged_while_the_flag_is_off(self) -> None:
        message = self._login(False)
        self.assertEqual(
            {"id", "date", "read", "daysLast", "gifts", "coins", "energy",
             "chr", "item", "summon", "buddy", "title", "messages"},
            set(message),
        )
        self.assertEqual({"default": "d-text", "ja": "ja-text", "en": "en-text"}, message["messages"])
        self.assertEqual([{"id": 50, "num": 4}], message["item"])


class MailApiEnvelopeTest(unittest.TestCase):
    """Both mail replies must carry what the client's `callAPI` wrapper reads.

    `callAPI` indexes `success`, `digest` and `lastupdate` off every response
    *before* dispatching to the endpoint's own callback, and it does so without
    guarding. A reply missing one raises `KeyNotFoundException` inside the
    wrapper, so the callback never runs: the rewards a read just granted are
    never applied to the client's copy of the account. Every other mutation
    already carried these; the mail routes answered `result` and nothing else.
    """

    CATALOG = (
        'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 181\n'
        'max_free_energy = 99\nmax_coins = 9999\nmax_stack = 99\n\n'
        '[[messages]]\nid = "m1"\ndate = 7.0\ndays_last = 3\n'
        'messages = { default = "d", ja = "j", en = "e" }\n'
        'coins = 500\nfree_energy = 3\nitems = { "50" = 2 }\n'
    )

    def test_read_and_delete_both_answer_the_wrapper_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "messages.toml"
            path.write_text(self.CATALOG, encoding="utf-8")
            catalog = load_message_catalog(path)
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(root / "state.json"),
                message_catalog=catalog,
            )
            try:
                server.state.create_account("token", "account", {
                    "chrdata": [], "buddyInfo": {"list": [], "record": []},
                    "summonList": [0] * 16, "itemList": [0] * 181, "coins": 1000,
                    "freeEnergy": 0, "energy": 0, "energyAppStore": 0,
                    "energyGooglePlay": 0, "energyAndApp": 0,
                }, catalog)
                get(server, "/gd/login?otk=token&uuid=account")
                body = urlencode({"idlist": json.dumps(["m1"]), "lastUpdate": "1"})
                status, read = post(server, "/gd/read_messages", "r1", body)
                self.assertEqual(200, status)
                self.assertEqual((True, 1.0), (read["success"], read["lastupdate"]))
                # `digest` is added by signing, and completes the trio.
                self.assertIn("digest", read)
                status, deleted = post(server, "/gd/delete_messages", "d1", body)
                self.assertEqual(200, status)
                self.assertEqual((True, 1.0), (deleted["success"], deleted["lastupdate"]))
                self.assertIn("digest", deleted)
                self.assertEqual(["m1"], deleted["deletelist"])
            finally:
                stop_server(server, thread)


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
                self.assertEqual([1018], [row["id"] for row in read["result"]["chrdata"]])
                self.assertTrue(read["result"]["chrdata"][0]["isNew"])
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
                message_catalog=catalog,
            )
            try:
                held = restarted.state.accounts["account"]["userdata"]["chrdata"]
                self.assertEqual([1018], [row["id"] for row in held])
                self.assertTrue(_valid_generic_character_record(held[0]))
            finally:
                stop_server(restarted, thread)

    def test_a_character_present_leaves_a_roster_every_clear_still_accepts(self) -> None:
        """A present must not strand the account it was delivered to.

        The read used to persist the shape its own response carries, which no
        settlement check accepts. One present then refused every clear the
        account attempted from then on, and the refusal outlived a restart:
        the roster merge that would have repaired the row is only reached by a
        clear that got accepted first.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self._catalog(root, self.MESSAGE + "character_id = 1018\n")
            server, thread = self._serve(catalog, root / "state.json", self._account())
            try:
                status, read = self._read(server)
                self.assertEqual(200, status)
                held = server.state.accounts["account"]["userdata"]["chrdata"]
                self.assertTrue(all(_valid_generic_character_record(row) for row in held))
                # The read that delivers the present still announces it, so the
                # client draws its "NEW" badge; only the save is left generic.
                self.assertEqual(
                    (True, 1), (read["result"]["chrdata"][0]["isNew"], read["result"]["chrdata"][0]["levelAdded"]),
                )
            finally:
                stop_server(server, thread)

    def test_a_present_already_written_in_the_response_shape_is_repaired_on_load(self) -> None:
        """Saves written before the fix carry the row that refused every clear."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = root / "state.json"
            catalog = self._catalog(root, self.MESSAGE + "character_id = 1018\n")
            server, thread = self._serve(catalog, state_path, self._account())
            try:
                with server.state.lock:
                    server.state.accounts["account"]["userdata"]["chrdata"] = [{
                        "id": 1018, "jobID": 0, "jobLevels": [9], "jobSlots": [],
                        "isNew": True, "levelAdded": 1, "skillBoost": 40, "luck": 20,
                    }]
                    server.state._persist_locked()
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
                message_catalog=catalog,
            )
            try:
                repaired = restarted.state.accounts["account"]["userdata"]["chrdata"][0]
                self.assertTrue(_valid_generic_character_record(repaired))
                # What the row accumulated while it was unusable is carried
                # across, not reset: the packed level, Skill Boost, and Luck.
                self.assertEqual(
                    ([9.0, 0.0, 0.0], 40, 20),
                    (repaired["jobLevels"], repaired["skillBoost"], repaired["luck"]),
                )
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
                owned = read["result"]["buddyInfo"]["list"]
                self.assertEqual([(42, 5)], [(row["bid"], row["lv"]) for row in owned])
                self.assertEqual(1, owned[0]["iid"])
            finally:
                stop_server(server, thread)

    def test_a_companion_present_also_enters_the_book(self) -> None:
        """The box is `list` and the book is `record`, and they are one thing.

        A reporter opened Companions after a present delivered one, saw nothing,
        restarted, still saw nothing, then drew a Companion and suddenly held
        two. The present had appended to `list` and left `record` behind, so the
        Companion was owned and persisted and invisible; the draw rebuilt the
        whole box and both appeared at once. Asserting only `list`, as the test
        beside this one did, is what let that ship.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self._catalog(root, self.MESSAGE + "companion_id = 42\ncompanion_level = 5\n")
            server, thread = self._serve(catalog, root / "state.json", self._account())
            try:
                status, read = self._read(server)
                self.assertEqual(200, status)
                box = read["result"]["buddyInfo"]
                self.assertEqual([(42, 5)], [(row["bid"], row["lv"]) for row in box["list"]])
                self.assertEqual([(42, 5)], [(row["bid"], row["lv"]) for row in box["record"]])
            finally:
                stop_server(server, thread)

    def test_a_present_arriving_beside_an_owned_companion_keeps_both_in_step(self) -> None:
        """The reported case had a box that was not empty to begin with."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self._catalog(root, self.MESSAGE + "companion_id = 42\ncompanion_level = 5\n")
            account = self._account()
            held = {"bid": 7, "lv": 3, "date": 0.0, "iid": 1, "exp": 0, "flag": 0, "chrID": 0}
            account["buddyInfo"] = {"list": [held], "record": [dict(held)]}
            account["nextCompanionInventoryId"] = 2
            server, thread = self._serve(catalog, root / "state.json", account)
            try:
                status, read = self._read(server)
                self.assertEqual(200, status)
                box = read["result"]["buddyInfo"]
                self.assertEqual([7, 42], sorted(row["bid"] for row in box["list"]))
                self.assertEqual([7, 42], sorted(row["bid"] for row in box["record"]))
            finally:
                stop_server(server, thread)

    def test_the_book_is_always_derivable_from_the_box(self) -> None:
        """The invariant itself, so a future grant path cannot quietly break it.

        `record` is a projection of `list` -- one entry per distinct Companion,
        the best copy held -- and never an independent store.
        """
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog = self._catalog(root, self.MESSAGE + "companion_id = 42\ncompanion_level = 5\n")
            server, thread = self._serve(catalog, root / "state.json", self._account())
            try:
                self.assertEqual(200, self._read(server)[0])
                box = server.state.accounts["account"]["userdata"]["buddyInfo"]
                self.assertEqual(_companion_info(box["list"]), box)
            finally:
                stop_server(server, thread)

    def test_a_save_that_already_drifted_repairs_when_it_loads(self) -> None:
        """Nothing is granted or taken: the owned list is the truth.

        A player whose present landed before the fix has a save carrying the
        Companion in `list` alone. Reloading it rebuilds the book rather than
        requiring an edit, which is how the stale wallet projection was handled.
        """
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            owned = {"bid": 42, "lv": 5, "date": 0.0, "iid": 1, "exp": 0, "flag": 0, "chrID": 0}
            account = self._account()
            account["buddyInfo"] = {"list": [owned], "record": []}
            server, thread = start_server(
                ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(state_path),
            )
            try:
                server.state.create_account("signup", "account", account)
                # Write the drift back the way a pre-fix present left it.
                with server.state.lock:
                    server.state.accounts["account"]["userdata"]["buddyInfo"] = {
                        "list": [dict(owned)], "record": [],
                    }
                    server.state._persist_locked()
            finally:
                stop_server(server, thread)

            reloaded = BootstrapState(state_path)
            box = reloaded.accounts["account"]["userdata"]["buddyInfo"]
            self.assertEqual([42], [row["bid"] for row in box["list"]])
            self.assertEqual([42], [row["bid"] for row in box["record"]])

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
                self.assertEqual([1018], [row["id"] for row in read["result"]["chrdata"]])
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


class TutorialGraduateInboxTest(unittest.TestCase):
    """Issue 54: the bundled profile's own account could not open a login bonus.

    Every other test in this file hand-builds a seed containing `itemList`, which
    is exactly what hid this: the one seed a real player actually starts from --
    `profiles/legacy-client-bootstrap.json` -- has never carried the field, and
    no scripted tutorial transition wrote one either.  These drive the shipped
    profile rather than a synthetic account, so the gap cannot reopen unseen.
    """

    def _clear_body(self, transition: dict, **overrides: str) -> str:
        """Build a clear form matching one profile transition, field order intact."""
        placeholders = {
            "valuables": json.dumps({"coins": 30}),
            "chrdata": json.dumps([]),
            "itemList": json.dumps([0] * 181),
            "summonList": json.dumps([0] * 16),
            "battle_result": json.dumps({"exp": 0, "coins": 30}),
            "teamMembers": json.dumps([]),
            "teamMembers_VS": json.dumps([]),
            "teamBuddies_VS": json.dumps([]),
        }
        values = {**placeholders, **transition["fixed_fields"], **overrides}
        return urlencode([(name, values[name]) for name in transition["field_names"]])

    def test_the_bundled_seed_carries_no_inventory_and_the_tutorial_must_supply_it(self) -> None:
        profile = bootstrap_profile()
        self.assertNotIn("itemList", profile.userdata_seed)
        clears = [item for item in profile.story_clears if "itemList" in item["field_names"]]
        self.assertTrue(clears, "the tutorial clears should still carry an inventory")

    def test_a_tutorial_clear_persists_the_inventory_it_accepts(self) -> None:
        profile = bootstrap_profile()
        transition = next(
            item for item in profile.story_clears if item["phase"] == "chapter1_1_active"
        )
        earned = [0] * 181
        earned[49] = 3
        with tempfile.TemporaryDirectory() as directory:
            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(Path(directory) / "state.json"),
                login_bonuses=True,
            )
            try:
                server.state.create_account(
                    "token", "account", profile.userdata_seed, server.message_catalog,
                )
                account = server.state.accounts["account"]
                account["tutorial_phase"] = "chapter1_1_active"
                self.assertIsNone(account["userdata"].get("itemList"))

                body = self._clear_body(transition, itemList=json.dumps(earned))
                status, _ = post(server, "/gd/clear_quest", "clear-1-1", body)
                self.assertEqual(200, status)
                self.assertEqual(earned, account["userdata"]["itemList"])

                # A later clear reporting a stale base must not erase the count.
                stale = [0] * 181
                account["tutorial_phase"] = "chapter1_1_active"
                status, _ = post(
                    server, "/gd/clear_quest", "clear-1-1-again",
                    self._clear_body(transition, itemList=json.dumps(stale)),
                )
                self.assertEqual(200, status)
                self.assertEqual(3, account["userdata"]["itemList"][49])
            finally:
                stop_server(server, thread)

    def test_a_tutorial_graduate_opens_both_login_bonuses(self) -> None:
        profile = bootstrap_profile()
        with tempfile.TemporaryDirectory() as directory:
            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(Path(directory) / "state.json"),
                login_bonuses=True,
            )
            try:
                server.state.create_account(
                    "token", "account", profile.userdata_seed, server.message_catalog,
                )
                account = server.state.accounts["account"]
                account["userdata"]["itemList"] = [0] * 181
                account["tutorial_phase"] = "free_roam"

                status, login = get(server, "/gd/login?otk=token&uuid=account")
                self.assertEqual(200, status)
                offered = [message["id"] for message in login["messageList"]]
                self.assertEqual(["login:consecutive:1", "login:overall:1"], offered)

                for message_id in offered:
                    body = urlencode(
                        {"idlist": json.dumps([message_id]), "lastUpdate": "1"},
                    )
                    status, payload = post(
                        server, "/gd/read_messages", f"read-{message_id}", body,
                    )
                    self.assertEqual(200, status, f"{message_id}: {payload}")
                    self.assertEqual([message_id], payload["result"]["readlist"])
            finally:
                stop_server(server, thread)

    def test_a_save_written_before_the_fix_gains_an_inventory_on_load(self) -> None:
        profile = bootstrap_profile()
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                login_bonuses=True,
            )
            try:
                server.state.create_account(
                    "token", "account", profile.userdata_seed, server.message_catalog,
                )
                server.state.accounts["account"]["tutorial_phase"] = "free_roam"
                with server.state.lock:
                    server.state._persist_locked()
            finally:
                stop_server(server, thread)

            # The stranded save on disk: a free-roam account with no inventory.
            document = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertNotIn("itemList", document["accounts"]["account"]["userdata"])

            restarted, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path),
                login_bonuses=True,
            )
            try:
                userdata = restarted.state.accounts["account"]["userdata"]
                self.assertEqual([0] * 181, userdata["itemList"])

                get(restarted, "/gd/login?otk=token&uuid=account")
                body = urlencode(
                    {"idlist": json.dumps(["login:consecutive:1"]), "lastUpdate": "1"},
                )
                status, _ = post(restarted, "/gd/read_messages", "read-after-load", body)
                self.assertEqual(200, status)
            finally:
                stop_server(restarted, thread)

    def test_a_real_inventory_survives_the_load_repair_untouched(self) -> None:
        """The repair seeds an absent array; it never resizes or zeroes a real one."""
        profile = bootstrap_profile()
        held = [7] * 200
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "state.json"
            server, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path), login_bonuses=True,
            )
            try:
                server.state.create_account(
                    "token", "account", profile.userdata_seed, server.message_catalog,
                )
                server.state.accounts["account"]["userdata"]["itemList"] = list(held)
                with server.state.lock:
                    server.state._persist_locked()
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(
                ("127.0.0.1", 0), profile, BootstrapState(state_path), login_bonuses=True,
            )
            try:
                self.assertEqual(
                    held, restarted.state.accounts["account"]["userdata"]["itemList"],
                )
            finally:
                stop_server(restarted, thread)
