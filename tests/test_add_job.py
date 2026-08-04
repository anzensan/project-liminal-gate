from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.job_catalog import build_bundled_job_policy, load_job_catalog
from tests.support import bootstrap_profile, post, start_server, stop_server, write_json


class AddJobTest(unittest.TestCase):
    def test_http_job_unlock_errors_collision_and_restart(self) -> None:
        document = {"schema_version": 1, "provenance": "user-supplied", "item_slots": 2, "unlocks": [{"character_id": 3, "job_index": 1, "coins": 2, "materials": {"1": 1}}, {"character_id": 3, "job_index": 2, "coins": 3, "materials": {"2": 1}}]}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path = write_json(root / "jobs.json", document)
            profile = bootstrap_profile()
            state = root / "state.json"; catalog = load_job_catalog(path)
            server, thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state), job_catalog=catalog)
            try:
                server.state.create_account("token", "account", {"chrdata": [{"id": 3, "jobLevels": [1.0, 0.0, 0.0]}], "itemList": [2, 2], "coins": 5})
                status, first = post(server, "/gd/add_job", "one", "targetID=3&lastUpdate=1")
                self.assertEqual(200, status); self.assertEqual((True, [1.0, 1.0, 0.0], [1, 2], 3), (first["success"], first["chrdata"]["jobLevels"], first["itemList"], first["coins"]))
                self.assertEqual((status, first), post(server, "/gd/add_job", "one", "targetID=3&lastUpdate=1"))
                # A different body reusing a spent requestID is its own request,
                # not a tampered retry: it unlocks the next job, and its own
                # retry still replays rather than unlocking a third.
                status, second = post(server, "/gd/add_job", "one", "targetID=3")
                self.assertEqual((200, [1.0, 1.0, 1.0], [1, 1], 0), (status, second["chrdata"]["jobLevels"], second["itemList"], second["coins"]))
                self.assertEqual((status, second), post(server, "/gd/add_job", "one", "targetID=3"))
                status, none = post(server, "/gd/add_job", "two", "targetID=3")
                self.assertEqual((200, True, 4), (status, none["success"], none["cmdError"]))
            finally:
                stop_server(server, thread)
            restarted, restarted_thread = start_server(("127.0.0.1", 0), profile, BootstrapState(state), job_catalog=catalog)
            try:
                self.assertEqual((200, first), post(restarted, "/gd/add_job", "one", "targetID=3&lastUpdate=1"))
            finally:
                stop_server(restarted, restarted_thread)


class BundledJobPolicyRuntimeTest(unittest.TestCase):
    def test_bundled_costs_are_charged_through_the_real_route(self) -> None:
        """The bundled table must settle a real unlock, not merely load."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = bootstrap_profile()
            state = BootstrapState(root / "state.json")
            # Character 3's third job costs 16000 Coins plus items 2x15,
            # 11x15, and 23x3 in the recovered ChrDatabase rows.
            items = [0] * 181
            for item_id, count in ((2, 20), (11, 20), (23, 5)):
                items[item_id - 1] = count
            state.create_account("token", "account", {
                "coins": 20000, "itemList": items,
                "chrdata": [{"id": 3, "jobID": 0, "jobLevels": [1.0, 1.0, 0.0], "jobSlots": []}],
            })
            server, thread = start_server(("127.0.0.1", 0), profile, state, job_catalog=build_bundled_job_policy())
            try:
                status, payload = post(server, "/gd/add_job", "bundled", "targetID=3&lastUpdate=1")
            finally:
                stop_server(server, thread)
            self.assertEqual(200, status)
            self.assertEqual(4000, payload["coins"])
            self.assertEqual([1.0, 1.0, 1.0], payload["chrdata"]["jobLevels"])
            self.assertEqual([5, 5, 2], [payload["itemList"][item_id - 1] for item_id in (2, 11, 23)])
