from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.achievement_catalog import load_achievement_catalog
from liminal_gate.bootstrap_server import BootstrapState
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class AchievementClaimTest(unittest.TestCase):
    def test_toml_catalog_loads_strictly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "achievements.toml"
            path.write_text(
                'schema_version = 1\nprovenance = "user-supplied"\nitem_slots = 3\nmax_free_energy = 9\nmax_coins = 99\nmax_stack = 8\n\n[[achievements]]\nachievement_id = 1\nrequired_chapter = 5\nfree_energy = 1\ncoins = 0\nitems = { "2" = 1 }\n',
                encoding="utf-8",
            )
            catalog = load_achievement_catalog(path)
            self.assertEqual((3, 5, {2: 1}), (catalog.item_slots, catalog.achievements[1].required_chapter, catalog.achievements[1].items))

    def test_http_claim_denial_collision_and_restart_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            catalog_path = write_json(root / "achievements.json", {
                "schema_version": 1, "provenance": "user-supplied", "item_slots": 3,
                "max_free_energy": 9, "max_coins": 99, "max_stack": 8,
                "achievements": [{"achievement_id": 1, "required_chapter": 5, "free_energy": 2, "coins": 3, "items": {"2": 4}}],
            })
            profile = bootstrap_profile()
            state_path = root / "state.json"

            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), achievement_catalog=load_achievement_catalog(catalog_path))
            try:
                server.state.create_account("token", "account", {"progressCode": 6 << 6, "freeEnergy": 1, "coins": 2, "itemList": [0, 1, 0]})
                status, success = post(server, "/gd/achived", "one", "id=1&lastUpdate=1")
                self.assertEqual(200, status)
                # `success` is not optional on any signed body: the transport
                # casts it to bool unguarded, so a claim answered without it
                # raised inside the client's own coroutine and hung the screen.
                self.assertEqual({"success", "achivementFlags", "freeEnergy", "coins", "itemList", "digest"}, set(success))
                self.assertIs(True, success["success"])
                self.assertEqual(([2], 3, 5, [0, 5, 0]), (success["achivementFlags"], success["freeEnergy"], success["coins"], success["itemList"]))
                self.assertEqual((status, success), post(server, "/gd/achived", "one", "id=1&lastUpdate=1"))
                # Reusing a spent requestID with a different body is no longer
                # read as a tampered retry; this body is simply invalid.
                status, reused = post(server, "/gd/achived", "one", "id=1&lastUpdate=0")
                self.assertEqual((501, "unsupported_achievement"), (status, reused["error"]))
                status, duplicate = post(server, "/gd/achived", "two", "id=1&lastUpdate=1")
                self.assertEqual((409, "invalid_local_achievement"), (status, duplicate["error"]))
                server.state.create_account("locked", "locked-account", {"progressCode": 5 << 6, "itemList": [0, 0, 0]})
                status, locked = post(server, "/gd/achived", "locked-one", "id=1&lastUpdate=1", "locked")
                self.assertEqual((409, "invalid_local_achievement"), (status, locked["error"]))
            finally:
                stop_server(server, thread)

            restarted, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path), achievement_catalog=load_achievement_catalog(catalog_path))
            try:
                self.assertEqual((200, success), post(restarted, "/gd/achived", "one", "id=1&lastUpdate=1"))
            finally:
                stop_server(restarted, thread)

    def test_marking_rows_read_is_accepted_in_any_phase(self) -> None:
        """The achievements screen posts this the moment it is opened.

        Every other userdata write is a roster, party or Companion change and
        belongs to free roam. This one fell through to those parsers, matched
        none of them, and answered 501 -- which this client renders as a Network
        Error -- so opening the screen this project had just made reachable
        threw an error at the player. The account that exposed it was
        mid-chapter, which is why the phase here is deliberately not free roam.
        """
        with tempfile.TemporaryDirectory() as directory:
            profile = bootstrap_profile()
            state_path = Path(directory) / "state.json"
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state_path))
            try:
                server.state.create_account("token", "account", {"progressCode": 6 << 6, "refillStartTime": 12.0})
                server.state.accounts["account"]["tutorial_phase"] = "generic_story_active"
                body = "achivementReadFlags=%5B7%2C0%2C1%5D&lastUpdate=1"
                status, saved = post(server, "/gd/userdata", "read-one", body)
                self.assertEqual(200, status)
                # `callAPI` indexes `success` and `lastupdate` off every reply
                # before the callback runs, and this callback then reads
                # `refillStartTime`; a reply missing any of them raises there.
                self.assertEqual({"success", "lastupdate", "refillStartTime", "digest"}, set(saved))
                self.assertIs(True, saved["success"])
                self.assertEqual(12.0, saved["refillStartTime"])
                self.assertEqual([7, 0, 1], server.state.accounts["account"]["userdata"]["achivementReadFlags"])
                # The flags are what the next userdata read serves back, or the
                # rows the player just cleared come back wearing NEW again.
                self.assertEqual([7, 0, 1], server.state.userdata_for("token")["achivementReadFlags"])
                # Replay is byte-identical. A spent id with a different body is
                # a different request rather than a tampered retry, exactly as
                # the claim route treats one, so the later flags win.
                self.assertEqual((200, saved), post(server, "/gd/userdata", "read-one", body))
                status, again = post(server, "/gd/userdata", "read-one", "achivementReadFlags=%5B15%5D&lastUpdate=1")
                self.assertEqual(200, status)
                self.assertEqual([15], server.state.accounts["account"]["userdata"]["achivementReadFlags"])
                post(server, "/gd/userdata", "read-restore", body)
                # A malformed bitfield is still refused rather than stored.
                status, refused = post(server, "/gd/userdata", "read-two", "achivementReadFlags=%5B-1%5D&lastUpdate=1")
                self.assertEqual((501, "unsupported_userdata_write"), (status, refused["error"]))
                self.assertEqual([7, 0, 1], server.state.accounts["account"]["userdata"]["achivementReadFlags"])
            finally:
                stop_server(server, thread)
