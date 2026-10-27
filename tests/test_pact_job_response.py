"""Pact replies must load every job in the surviving client's indexed loader."""

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.bootstrap_server import BootstrapState
from liminal_gate.pact_draw_catalog import PactDraw, build_bundled_pact_policy
from liminal_gate.save_validation import ITEM_SLOTS
from liminal_gate.tuning import DEFAULT_TUNING
from tests.support import bootstrap_profile, post, running_server


class PactJobResponseTest(unittest.TestCase):
    def test_capped_first_job_does_not_hide_other_jobs_on_any_payment_or_plus(self):
        selected = PactDraw(1, 1, 2, 5)
        policy = replace(
            build_bundled_pact_policy(),
            fellowship_draws=(selected,), truth_draws=(selected,),
        )
        for kind in (0, 1, 20):
            for luck_type in (False, True):
                for plus in (False, True):
                    for active in (0, 1):
                        with self.subTest(kind=kind, luck=luck_type, plus=plus, active=active):
                            tuning = replace(DEFAULT_TUNING, pact=replace(
                                DEFAULT_TUNING.pact, plus_chance_percent=100 if plus else 0,
                                plus_levels=(3, 3), plus_tenths=(5, 5),
                            ))
                            # Integral doubles are the client's packed level/EXP
                            # representation. J1 is capped; J2 is nearly capped;
                            # J3 is locked and must stay so.
                            levels = [float((123 << 12) | 90), float((456 << 12) | 87), 0.0]
                            items = [0] * ITEM_SLOTS
                            items[80] = int(kind == 20)
                            body = (
                                f"kind={kind}&count=1&luckType={str(luck_type).lower()}"
                                "&campaignChrID=0&eventFlag=0&lastUpdate=1"
                            )
                            with tempfile.TemporaryDirectory() as directory:
                                path = Path(directory) / "state.json"
                                with running_server(
                                    ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(path, tuning=tuning),
                                    pact_draw_catalog=policy,
                                ) as server:
                                    server.state.create_account("token", "account", {
                                        "coins": policy.coin_cost, "energy": policy.energy_cost,
                                        "freeEnergy": 0, "itemList": items,
                                        "chrdata": [{
                                            "id": 1, "jobID": active, "jobLevels": levels,
                                            "jobSlots": [0.0] * 3, "buddy": 0, "date": 0.0,
                                            "flags": 0, "skillBoost": 0, "luck": 0,
                                        }],
                                    })
                                    status, payload = post(server, "/gd/do_slot", "jobs", body)
                                    self.assertEqual((200, True), (status, payload["success"]))
                                    stored = server.state.userdata_for("token")
                                    expected = [float((123 << 12) | 90), float((456 << 12) | (90 if plus else 89)), 0.0]
                                    row = payload["chrdata"][0]
                                    self.assertEqual(expected, stored["chrdata"][0]["jobLevels"])
                                    # Character.LoadFromJson uses slot 0..Count-1,
                                    # independently of jobID. A singleton cannot
                                    # communicate J2's gain, even if J1 is capped.
                                    self.assertEqual(expected, row["jobLevels"])
                                    self.assertEqual(active, row["jobID"])
                                    self.assertEqual(0 if active == 0 else 2, row["levelAdded"])
                                    if plus:
                                        self.assertEqual(0 if active == 0 else 1, row["levelAdded2"])
                                    self.assertEqual(0 if kind == 0 else policy.coin_cost, stored["coins"])
                                    self.assertEqual(0 if kind == 1 else policy.energy_cost, stored["energy"])
                                    self.assertEqual(0, stored["itemList"][80])
                                    self.assertEqual((status, payload), post(server, "/gd/do_slot", "jobs", body))
                                    self.assertEqual(stored, server.state.userdata_for("token"))
                                with running_server(
                                    ("127.0.0.1", 0), bootstrap_profile(), BootstrapState(path, tuning=tuning),
                                    pact_draw_catalog=policy,
                                ) as server:
                                    with patch("liminal_gate.bootstrap_server.random.SystemRandom", side_effect=AssertionError("replay rerolled")):
                                        self.assertEqual((status, payload), post(server, "/gd/do_slot", "jobs", body))
                                    self.assertEqual(stored, server.state.userdata_for("token"))

    def test_batch_replies_keep_each_draws_own_full_snapshot(self):
        selected = PactDraw(1, 1, 2, 5)
        policy = replace(build_bundled_pact_policy(), truth_draws=(selected,))
        tuning = replace(DEFAULT_TUNING, pact=replace(
            DEFAULT_TUNING.pact, plus_chance_percent=100, plus_levels=(3, 3),
        ))
        with tempfile.TemporaryDirectory() as directory:
            with running_server(
                ("127.0.0.1", 0), bootstrap_profile(),
                BootstrapState(Path(directory) / "state.json", tuning=tuning),
                pact_draw_catalog=policy,
            ) as server:
                server.state.create_account("token", "account", {
                    "coins": 0, "energy": policy.energy_cost * 3, "freeEnergy": 0, "chrdata": [],
                })
                status, payload = post(server, "/gd/do_slot", "batch-jobs",
                    "kind=1&count=3&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1")
                self.assertEqual((200, True), (status, payload["success"]))
                self.assertEqual([[13, 0, 0], [18, 0, 0], [23, 0, 0]], [row["jobLevels"] for row in payload["chrdata"]])
                self.assertEqual([23, 0, 0], server.state.userdata_for("token")["chrdata"][0]["jobLevels"])
