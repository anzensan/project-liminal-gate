from __future__ import annotations

import copy
import json
from http.client import HTTPConnection
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import (
    MAX_REQUEST_BODY_BYTES,
    BootstrapServer,
    BootstrapState,
    ProfileError,
    load_profile,
)
from liminal_gate.story_progression_catalog import build_core_story_policy


PUBLIC_ROOT = Path(__file__).resolve().parents[1]


class BootstrapServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.root = root
        profile_path = root / "profile.json"
        profile_path.write_text(json.dumps({
            "schema_version": 1,
            "routes": {
                "time": "/local/time",
                "status": "/local/status",
                "signup": "/local/signup",
                "login": "/local/login",
                "userdata": "/local/userdata",
                "buy_energy": "/local/buy_energy",
                "showed_ad_movie_main": "/local/showed_ad_movie_main",
                "showed_ad_movie_continue": "/local/showed_ad_movie_continue",
            },
            "response_signing": {
                "algorithm": "md5-uppercase-slice",
                "salt": "user-local-test-value",
                "digest_start": 16,
                "digest_end": 32,
            },
            "account_binding": {
                "signup_response_field": "id",
                "login_query_field": "uuid",
            },
            "responses": {
                "signup": {"success": True, "id": "local-account"},
                "login": {"success": True, "message": "local"},
                "status": {"success": True, "maintenance": False},
            },
            "userdata_seed": {"coins": 0, "progressCode": 1},
        }), encoding="utf-8")
        self.state_path = root / "state.json"
        self.event_log_path = root / "events.jsonl"
        self.server = BootstrapServer(
            ("127.0.0.1", 0),
            load_profile(profile_path),
            BootstrapState(self.state_path),
            self.event_log_path,
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def request(self, path: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path)
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response.status, body

    def post(self, path: str, body: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST", path, body=body.encode("utf-8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def test_bootstrap_sequence_persists_account_and_signs_responses(self) -> None:
        status, signup = self.request("/local/time?otk=pre-signup-token")
        self.assertEqual(200, status)
        self.assertEqual(16, len(signup["digest"]))
        status, signup = self.request("/local/signup?uuid=local-account&otk=bootstrap-token")
        self.assertEqual(200, status)
        token = "login-token"
        self.assertEqual(16, len(signup["digest"]))
        for path in ("/local/status",):
            status, response = self.request(f"{path}?otk=bootstrap-token")
            self.assertEqual(200, status)
            self.assertEqual(16, len(response["digest"]))
        status, response = self.request(f"/local/login?otk={token}&uuid=local-account")
        self.assertEqual(200, status)
        self.assertEqual(16, len(response["digest"]))
        status, response = self.request(f"/local/userdata?otk={token}")
        self.assertEqual(200, status)
        self.assertEqual(16, len(response["digest"]))
        self.assertTrue(self.state_path.is_file())
        self.assertEqual(0, json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"]["local-account"]["userdata"]["coins"])

    def test_retired_paid_and_ad_routes_refuse_in_the_endpoint_namespace(self) -> None:
        # The point of the route class: a tester who hits one of these gets the
        # screen's own refusal. The unsigned 501 these used to fall to reads as
        # a transport failure, and the client retries it until it is force-stopped.
        expected = {
            "/local/buy_energy": 3,
            "/local/showed_ad_movie_main": 1,
            "/local/showed_ad_movie_continue": 1,
        }
        for path, code in expected.items():
            for status, response in (
                self.request(f"{path}?otk=refusal-token"),
                self.post(f"{path}?otk=refusal-token&requestID=refusal", "countryCode=US&platform=android"),
            ):
                self.assertEqual(200, status, path)
                self.assertEqual(16, len(response["digest"]), path)
                self.assertIs(True, response["success"], path)
                self.assertEqual(code, response["cmdError"], path)
                # `errorCode` is the transport namespace, and a code left there
                # shows the common error dialog instead of reaching the callback.
                self.assertNotIn("errorCode", response, path)
        status, response = self.request("/local/buy_energy")
        self.assertEqual(400, status)
        self.assertEqual("missing_local_account_token", response["error"])

    def test_healthz_is_unsigned_and_names_the_running_build(self) -> None:
        self.server.build_id = "combined-test-build"
        status, health = self.request("/healthz")
        self.assertEqual(200, status)
        self.assertEqual(
            {"service": "project-liminal-gate", "status": "ok", "build_id": "combined-test-build"},
            health,
        )

    def test_unknown_account_and_route_fail_explicitly(self) -> None:
        status, response = self.request("/local/userdata?otk=unknown")
        self.assertEqual(401, status)
        self.assertEqual("unknown_local_account", response["error"])
        status, response = self.request("/local/unknown")
        self.assertEqual(501, status)
        self.assertEqual("route_not_implemented", response["error"])
        events = [json.loads(line) for line in self.event_log_path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(
            [
                {"method": "GET", "path": "/local/userdata", "status": 401},
                {"method": "GET", "path": "/local/unknown", "status": 501},
            ],
            [{key: event[key] for key in ("method", "path", "status")} for event in events],
        )
        self.assertNotIn("otk=unknown", self.event_log_path.read_text(encoding="utf-8"))

    def test_serves_derived_local_pact_banner(self) -> None:
        banners = self.root / "public_data" / "banners"
        banners.mkdir(parents=True)
        payload = b"\x89PNG\r\n\x1a\nlocal"
        (banners / "sl_truth_01_en.png").write_bytes(payload)
        # Banner serving is stateless; give it its own save rather than a
        # second server sharing the one the fixture already holds.
        server = BootstrapServer(
            ("127.0.0.1", 0), self.server.profile, BootstrapState(self.root / "banner-state.json"), public_data_root=self.root / "public_data"
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            connection = HTTPConnection(*server.server_address)
            connection.request("GET", "/public_data/banners/sl_truth_01_en.png")
            response = connection.getresponse()
            body = response.read()
            content_type = response.getheader("Content-Type")
            connection.close()
        finally:
            server.shutdown()
            thread.join()
            server.server_close()
        self.assertEqual(200, response.status)
        self.assertEqual("image/png", content_type)
        self.assertEqual(payload, body)

    def test_serves_derived_coin_creeps_bundle_at_hashed_resource_url(self) -> None:
        banners = self.root / "public_data" / "banner_resources"
        banners.mkdir(parents=True)
        name = "824301495dd437d0dcd4392231844364sp1003-1.bin"
        payload = b"ENCA-local-derived-bundle"
        (banners / name).write_bytes(payload)
        server = BootstrapServer(
            ("127.0.0.1", 0), self.server.profile,
            BootstrapState(self.root / "coin-creeps-banner-state.json"),
            public_data_root=self.root / "public_data",
        )
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        try:
            for path in (f"/resources/Banner/{name}", "/Banner/sp1003-1.bin"):
                connection = HTTPConnection(*server.server_address)
                connection.request("GET", path)
                response = connection.getresponse()
                body = response.read()
                content_type = response.getheader("Content-Type")
                connection.close()
                self.assertEqual(200, response.status)
                self.assertEqual("application/octet-stream", content_type)
                self.assertEqual(payload, body)
        finally:
            server.shutdown()
            thread.join()
            server.server_close()

    def test_account_survives_server_restart(self) -> None:
        _, signup = self.request("/local/signup?uuid=local-account&otk=signup-token")
        self.assertEqual(16, len(signup["digest"]))
        token = "restart-token"
        status, _ = self.request(f"/local/login?otk={token}&uuid=local-account")
        self.assertEqual(200, status)
        # A real restart releases the save first; two servers may not share one.
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        restarted = BootstrapServer(
            ("127.0.0.1", 0), self.server.profile, BootstrapState(self.state_path)
        )
        thread = threading.Thread(target=restarted.serve_forever)
        thread.start()
        try:
            connection = HTTPConnection(*restarted.server_address)
            connection.request("GET", f"/local/userdata?otk={token}")
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
        finally:
            restarted.shutdown()
            thread.join()
            restarted.server_close()
        self.assertEqual(200, response.status)
        self.assertEqual(0, body["coins"])
        self.assertEqual({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 0}, body["valuables"])

    def test_a_second_server_may_not_share_one_save(self) -> None:
        """Two servers on one save silently overwrite each other's progress.

        Each holds the whole state in memory and republishes all of it on every
        mutation, so they do not interleave — the second's stale copy simply
        wins, with no error on either side.  Reachable today by changing
        `--port` while `--data-dir` keeps its default.
        """
        self.request("/local/signup?uuid=local-account&otk=signup-token")
        with self.assertRaises(ProfileError) as refused:
            BootstrapState(self.state_path)
        self.assertIn("already in use", str(refused.exception))
        # The lock is an OS advisory lock, so a stopped server frees the save
        # immediately and a genuine restart is never blocked by a stale file.
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        replacement = BootstrapState(self.state_path)
        self.assertEqual(["local-account"], sorted(replacement.accounts))
        replacement.close()

    def test_committed_states_are_retained_for_recovery(self) -> None:
        """The save is atomic, but a save that is intact and wrong is not.

        Without a retained history the durable account has exactly one copy, so
        a bad merge, a hand edit, or a client reporting nonsense is terminal.
        """
        self.request("/local/signup?uuid=local-account&otk=signup-token")
        for coins in (10, 20, 30):
            with self.server.state.lock:
                self.server.state.accounts["local-account"]["userdata"]["coins"] = coins
                self.server.state._persist_locked()
        self.assertEqual(30, json.loads(self.state_path.read_text())["accounts"]["local-account"]["userdata"]["coins"])
        # Newest first: .bak.1 is the state immediately before the last write.
        for index, coins in ((1, 20), (2, 10)):
            backup = self.state_path.with_name(f"{self.state_path.name}.bak.{index}")
            self.assertEqual(coins, json.loads(backup.read_text())["accounts"]["local-account"]["userdata"]["coins"])
        # A retained state is a complete, loadable save, not a fragment.
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        recovered_path = self.root / "recovered.json"
        recovered_path.write_bytes(self.state_path.with_name(f"{self.state_path.name}.bak.1").read_bytes())
        recovered = BootstrapState(recovered_path)
        self.assertEqual(20, recovered.accounts["local-account"]["userdata"]["coins"])
        recovered.close()

    def test_an_unknown_token_routes_only_to_an_identified_client(self) -> None:
        """Two players at once send byte-identical tokens.

        `otk` is a three-second time bucket, so a household's second client
        cannot be told apart from the first by token, and resolving unknown
        tokens to "whichever account logged in most recently" lets the second
        player's login silently capture the first player's mutations. The
        requesting client's own address is the discriminator that works.
        """
        state = self.server.state
        state.create_account("first-token", "local-account", {"coins": 1}, client_host="192.168.1.10")
        state.accounts["second-account"] = copy.deepcopy(state.accounts["local-account"])
        state.bind_login_token("second-token", "second-account", "192.168.1.11")
        self.assertEqual("second-account", state.active_account_id)

        # The first player's client keeps playing on a freshly rotated token.
        self.assertTrue(state.bind_rotated_token("rotated-for-first", "192.168.1.10"))
        self.assertEqual("local-account", state.tokens["rotated-for-first"])
        self.assertTrue(state.bind_rotated_token("rotated-for-second", "192.168.1.11"))
        self.assertEqual("second-account", state.tokens["rotated-for-second"])

        # A client that has never identified itself may not inherit whichever
        # account is active. The guided server listens on the LAN for physical
        # devices, so this is an account-integrity boundary.
        self.assertFalse(state.bind_rotated_token("rotated-for-stranger", "192.168.1.99"))
        self.assertNotIn("rotated-for-stranger", state.tokens)

        # The routing survives a restart, or the next session re-hijacks.
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        reloaded = BootstrapState(self.state_path)
        self.assertTrue(reloaded.bind_rotated_token("later-token", "192.168.1.10"))
        self.assertEqual("local-account", reloaded.tokens["later-token"])
        reloaded.close()

    def test_legacy_state_without_host_bindings_is_claimed_once(self) -> None:
        state = self.server.state
        state.create_account("old-token", "local-account", {"coins": 1})
        state.client_hosts = {}
        self.assertTrue(state.bind_rotated_token("rotated", "192.168.1.10"))
        self.assertEqual("local-account", state.tokens["rotated"])
        self.assertEqual("local-account", state.client_hosts["192.168.1.10"])
        self.assertFalse(state.bind_rotated_token("stranger", "192.168.1.99"))

    def test_a_linked_device_uuid_logs_in_to_the_shared_account(self) -> None:
        """The `link` command's aliases resolve on the wire's only two
        identity-bearing routes, so a second device's stored UUID opens the
        save its owner already plays instead of being refused as unknown."""
        self.request("/local/signup?uuid=local-account&otk=signup-token")
        with self.server.state.lock:
            self.server.state.account_aliases["linked-device"] = "local-account"
            self.server.state._persist_locked()
        status, _ = self.request("/local/login?uuid=linked-device&otk=tablet-token")
        self.assertEqual(200, status)
        self.assertEqual("local-account", self.server.state.tokens["tablet-token"])
        status, body = self.request("/local/userdata?otk=tablet-token")
        self.assertEqual(200, status)
        self.assertEqual(0, body["coins"])
        # The link survives a restart like every other binding.
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual({"linked-device": "local-account"}, saved["account_aliases"])

    def test_a_save_that_will_not_load_names_its_retained_states(self) -> None:
        self.request("/local/signup?uuid=local-account&otk=signup-token")
        with self.server.state.lock:
            self.server.state.accounts["local-account"]["userdata"]["coins"] = 42
            self.server.state._persist_locked()
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.state_path.write_text("{ this is not a save", encoding="utf-8")
        with self.assertRaises(ProfileError) as refused:
            BootstrapState(self.state_path)
        self.assertIn("state.json.bak.1", str(refused.exception))

    def test_userdata_normalizes_persisted_character_job_levels_to_doubles(self) -> None:
        self.request("/local/signup?uuid=local-account&otk=signup-token")
        with self.server.state.lock:
            self.server.state.accounts["local-account"]["userdata"]["chrdata"] = [
                {"id": 3, "jobID": 0, "jobLevels": [1, 0, 0], "jobSlots": []}
            ]
            self.server.state._persist_locked()
        status, body = self.request("/local/userdata?otk=signup-token")
        self.assertEqual(200, status)
        self.assertEqual([1.0, 0.0, 0.0], body["chrdata"][0]["jobLevels"])
        saved = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual([1.0, 0.0, 0.0], saved["accounts"]["local-account"]["userdata"]["chrdata"][0]["jobLevels"])

    def test_event_log_records_safe_form_diagnostics_for_rejected_write(self) -> None:
        self.request("/local/signup?uuid=local-account&otk=signup-token")
        self.request("/local/login?uuid=local-account&otk=login-token")
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST", "/local/userdata?otk=login-token&requestID=map-write",
            body="progressCode=7&worldMapNo=0&lastUpdate=1&username=private",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        response = connection.getresponse()
        self.assertEqual(501, response.status)
        response.read()
        connection.close()
        event = json.loads(self.event_log_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual("unsupported_userdata_write", event["error"])
        self.assertEqual(["progressCode", "worldMapNo", "lastUpdate", "username"], event["request_fields"])
        self.assertEqual({"progressCode": "7", "worldMapNo": "0", "lastUpdate": "1"}, event["request_values"])
        self.assertEqual("initial", event["resolved_account_phase"])
        self.assertEqual("initial", event["active_account_phase"])
        self.assertTrue(event["resolved_account_is_active"])
        self.assertNotIn("local-account", self.event_log_path.read_text(encoding="utf-8"))
        self.assertNotIn("private", self.event_log_path.read_text(encoding="utf-8"))

    def test_rejects_negative_and_oversized_request_bodies_before_reading(self) -> None:
        for length, expected_status, expected_error in (
            (-1, 400, "invalid_content_length"),
            (MAX_REQUEST_BODY_BYTES + 1, 413, "request_body_too_large"),
        ):
            connection = HTTPConnection(*self.server.server_address)
            connection.putrequest(
                "POST", "/local/userdata?otk=token&requestID=bounded-body"
            )
            connection.putheader("Content-Length", str(length))
            connection.endheaders()
            response = connection.getresponse()
            payload = json.loads(response.read())
            connection.close()
            self.assertEqual(
                (expected_status, expected_error),
                (response.status, payload["error"]),
            )

    def test_rejects_an_incomplete_request_body(self) -> None:
        connection = HTTPConnection(*self.server.server_address)
        connection.putrequest(
            "POST", "/local/userdata?otk=token&requestID=incomplete-body"
        )
        connection.putheader("Content-Length", "10")
        connection.endheaders(b"x=1")
        assert connection.sock is not None
        connection.sock.shutdown(socket.SHUT_WR)
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        self.assertEqual((400, "incomplete_request_body"), (response.status, payload["error"]))

    def test_event_log_records_only_clear_settlement_aggregates(self) -> None:
        self.request("/local/signup?uuid=local-account&otk=signup-token")
        body = urlencode({
            "progressCode": "7", "worldMapNo": "0", "lastUpdate": "1",
            "valuables": json.dumps({"coins": 321, "private": "no"}),
            "battle_result": json.dumps({"chapter": 2000, "section": 1, "coins": 110, "exp": 1718, "roster": "private"}),
            "chrdata": "private-roster",
        })
        connection = HTTPConnection(*self.server.server_address)
        connection.request("POST", "/local/userdata?otk=signup-token&requestID=clear-diagnostics", body=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        response = connection.getresponse(); response.read(); connection.close()
        event = json.loads(self.event_log_path.read_text(encoding="utf-8").splitlines()[-1])
        self.assertEqual(321, event["reported_wallet_coins"])
        self.assertEqual({"chapter": 2000, "section": 1, "coins": 110, "exp": 1718}, event["reported_battle_result"])
        self.assertNotIn("private", self.event_log_path.read_text(encoding="utf-8"))


class IncludedBootstrapProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        root = Path(self.temporary_directory.name)
        self.state_path = root / "state.json"
        self.profile_path = PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json"
        self.server = BootstrapServer(
            ("127.0.0.1", 0),
            load_profile(self.profile_path),
            BootstrapState(self.state_path),
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temporary_directory.cleanup()

    def request(self, path: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", path)
        response = connection.getresponse()
        body = json.loads(response.read())
        connection.close()
        return response.status, body

    def post(self, path: str, body: str) -> tuple[int, dict[str, object]]:
        connection = HTTPConnection(*self.server.server_address)
        connection.request(
            "POST", path, body=body.encode("utf-8"), headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        connection.close()
        return response.status, payload

    def restart(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.server = BootstrapServer(
            ("127.0.0.1", 0), load_profile(self.profile_path), BootstrapState(self.state_path)
        )
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()

    def test_first_tutorial_pull_can_choose_bahl_and_replays_without_rerolling(self) -> None:
        account_id = "bahl-tutorial-account"
        login_token = "bahl-tutorial-token"
        status, _ = self.request(
            f"/gd/signup?uuid={account_id}&otk=signup-token&requestID=signup"
        )
        self.assertEqual(200, status)
        status, _ = self.request(
            f"/gd/login?uuid={account_id}&otk={login_token}&requestID=login"
        )
        self.assertEqual(200, status)
        status, initial = self.request(
            f"/gd/userdata?otk={login_token}&requestID=initial-userdata"
        )
        self.assertEqual((200, [], []), (
            status, initial["chrdata"], initial["teamMembers"],
        ))

        first_body = (
            "kind=10&count=1&luckType=false&campaignChrID=0&"
            "eventFlag=0&lastUpdate=1"
        )
        with patch(
            "liminal_gate.bootstrap_server.random.SystemRandom.randrange",
            return_value=0,
        ) as draw:
            status, bahl = self.post(
                f"/gd/do_slot?otk={login_token}&requestID=first-pact",
                first_body,
            )
        self.assertEqual(200, status)
        draw.assert_called_once_with(2)
        self.assertEqual(([1], [1]), (
            bahl["teamMembers"],
            [row["id"] for row in bahl["chrdata"]],
        ))
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][account_id]
        self.assertEqual(1, persisted["tutorial_starter_character_id"])
        self.assertEqual([1], persisted["userdata"]["teamMembers"])

        self.restart()
        with patch(
            "liminal_gate.bootstrap_server.random.SystemRandom.randrange",
            side_effect=AssertionError("an exact retry must not reroll"),
        ):
            status, replay = self.post(
                f"/gd/do_slot?otk={login_token}&requestID=first-pact",
                first_body,
            )
        self.assertEqual(200, status)
        self.assertEqual(bahl, replay)

        second_body = (
            "kind=11&count=1&luckType=false&campaignChrID=0&"
            "eventFlag=0&lastUpdate=1"
        )
        status, amisandra = self.post(
            f"/gd/do_slot?otk={login_token}&requestID=second-pact",
            second_body,
        )
        self.assertEqual(200, status)
        self.assertEqual([1, 25], amisandra["teamMembers"])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][account_id]
        self.assertEqual([1, 25], [
            row["id"] for row in persisted["userdata"]["chrdata"]
        ])

        write_body = urlencode([
            (name, value.replace("{{tutorial_starter_id}}", "1"))
            for name, value in self.server.profile.tutorial_writes[0]["fields"]
        ])
        status, settled = self.post(
            f"/gd/userdata?otk={login_token}&requestID=tutorial-write",
            write_body,
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, settled["lastupdate"])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][account_id]
        self.assertEqual([1, 25, 0, 0, 0, 0], persisted["userdata"]["teamMembers"])
        self.assertNotIn(3, persisted["userdata"]["teamMembers"])

    def test_legacy_grace_state_without_starter_field_continues_as_grace(self) -> None:
        account_id = "legacy-grace-account"
        token = "legacy-grace-token"
        self.server.state.create_account(
            token,
            account_id,
            copy.deepcopy(self.server.profile.userdata_seed),
        )
        with self.server.state.lock:
            account = self.server.state.accounts[account_id]
            account["tutorial_phase"] = "grace_granted"
            account["initial_userdata_served"] = True
            account["userdata"]["chrdata"] = [
                {
                    "id": 3,
                    "jobID": 0,
                    "jobLevels": [1],
                    "jobSlots": [],
                    "isNew": True,
                    "levelAdded": 1,
                }
            ]
            account["userdata"]["teamMembers"] = [3]
            self.server.state._persist_locked()
        self.restart()

        status, amisandra = self.post(
            f"/gd/do_slot?otk={token}&requestID=legacy-second-pact",
            "kind=11&count=1&luckType=false&campaignChrID=0&"
            "eventFlag=0&lastUpdate=1",
        )
        self.assertEqual(200, status)
        self.assertEqual([3, 25], amisandra["teamMembers"])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][account_id]
        self.assertNotIn("tutorial_starter_character_id", persisted)
        self.assertEqual([3, 25], [
            row["id"] for row in persisted["userdata"]["chrdata"]
        ])

    def _seed_knight_party(
        self, account_id: str, token: str, starter: int, recruit: int | None,
    ) -> None:
        """Place an account where the Knight is held and the recruit is next."""
        self.server.state.create_account(
            token, account_id, copy.deepcopy(self.server.profile.userdata_seed),
        )
        with self.server.state.lock:
            account = self.server.state.accounts[account_id]
            account["tutorial_phase"] = "knight_party"
            account["initial_userdata_served"] = True
            account["tutorial_starter_character_id"] = starter
            if recruit is not None:
                account["tutorial_recruit_character_id"] = recruit
            account["userdata"]["chrdata"] = [
                {"id": identifier, "jobID": 0, "jobLevels": [1], "jobSlots": []}
                for identifier in (starter, 25, 64)
            ]
            account["userdata"]["teamMembers"] = [starter, 25, 64, 0, 0, 0]
            self.server.state._persist_locked()
        self.restart()

    def _clear_chapter1_2(self, token: str, tag: str) -> tuple[int, dict[str, object]]:
        status, _ = self.post(
            f"/gd/start_quest?otk={token}&requestID={tag}-start",
            "stamina=1&coins=0&chapter=1&section=2&lastUpdate=1",
        )
        self.assertEqual(200, status)
        return self.post(
            f"/gd/clear_quest?otk={token}&requestID={tag}-clear",
            urlencode({
                "progressCode": "16777283", "worldMapNo": "0",
                "valuables": json.dumps({"coins": 50}),
                "chrdata": json.dumps([]), "itemList": json.dumps([]),
                "summonList": json.dumps([]),
                "battle_result": json.dumps(
                    {"chapter": 1, "section": 2, "coins": 50, "exp": 1224}
                ),
                "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
            }),
        )

    def _assert_recruit_completes_the_circle(self, starter: int, recruit: int) -> None:
        """Clear Chapter 1-2 and prove which character the roster gains."""
        account_id, token = f"circle-{starter}", f"circle-token-{starter}"
        self._seed_knight_party(account_id, token, starter, recruit)
        status, cleared = self._clear_chapter1_2(token, "circle")
        self.assertEqual(200, status)
        self.assertEqual(
            [starter, 25, 64, recruit], [row["id"] for row in cleared["chrdata"]],
        )
        granted = cleared["chrdata"][-1]
        self.assertEqual((True, 1), (granted["isNew"], granted["levelAdded"]))

        # The grant survives a restart and an exact retry unchanged.
        self.restart()
        status, replay = self._clear_chapter1_2(token, "circle")
        self.assertEqual((200, cleared["chrdata"]), (status, replay["chrdata"]))

        # The party the client writes back is the one the server records.
        status, _ = self.post(
            f"/gd/userdata?otk={token}&requestID=circle-party",
            urlencode([
                ("chrdata", json.dumps([{"id": recruit, "flags": 1}])),
                ("teamMembers", json.dumps([starter, 25, 64, recruit, 0, 0])),
                ("teamMembers_VS", json.dumps([0] * 18)),
                ("teamBuddies_VS", json.dumps([0] * 18)),
                ("teamNo", "1"), ("teamNo_VS", "1"),
                ("summonId", "1"), ("lastUpdate", "1"),
            ]),
        )
        self.assertEqual(200, status)
        status, after = self.request(f"/gd/userdata?otk={token}&requestID=circle-after")
        self.assertEqual(
            (200, [starter, 25, 64, recruit, 0, 0]), (status, after["teamMembers"]),
        )

    def test_bahl_tutorial_recruits_the_archer_that_completes_the_circle(self) -> None:
        # The client picks the completing class itself and animates recruiting
        # it, so a server that answers with the other one overwrites what the
        # player was just shown: a Bahl run displayed an Archer and landed a
        # Warrior. Bahl already holds the Knight, so the Archer completes it.
        self._assert_recruit_completes_the_circle(1, 65)

    def test_grace_tutorial_still_recruits_the_warrior(self) -> None:
        self._assert_recruit_completes_the_circle(3, 63)

    def test_a_save_without_a_recruit_field_keeps_the_character_it_was_granted(self) -> None:
        # Bahl saves made before the recruit was declared per outcome already
        # hold the Warrior. Continuing them on the Archer would hand the client
        # a roster it never received, so the granted character is what counts.
        account_id, token = "legacy-recruit-account", "legacy-recruit-token"
        self._seed_knight_party(account_id, token, 1, None)
        status, cleared = self._clear_chapter1_2(token, "legacy-recruit")
        self.assertEqual(200, status)
        self.assertEqual([1, 25, 64, 63], [row["id"] for row in cleared["chrdata"]])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][account_id]
        self.assertNotIn("tutorial_recruit_character_id", persisted)

    def test_first_tutorial_pull_commits_the_recruit_with_the_starter(self) -> None:
        account_id, token = "pairing-account", "pairing-token"
        for path in (
            f"/gd/signup?uuid={account_id}&otk=pairing-signup&requestID=pairing-signup",
            f"/gd/login?uuid={account_id}&otk={token}&requestID=pairing-login",
            f"/gd/userdata?otk={token}&requestID=pairing-initial",
        ):
            status, _ = self.request(path)
            self.assertEqual(200, status)
        with patch(
            "liminal_gate.bootstrap_server.random.SystemRandom.randrange",
            return_value=0,
        ):
            status, _ = self.post(
                f"/gd/do_slot?otk={token}&requestID=pairing-first-pact",
                "kind=10&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
            )
        self.assertEqual(200, status)
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))[
            "accounts"
        ][account_id]
        self.assertEqual(
            (1, 65),
            (
                persisted["tutorial_starter_character_id"],
                persisted["tutorial_recruit_character_id"],
            ),
        )

    def test_profile_persists_the_declared_account_flow_and_rejects_later_routes(self) -> None:
        token = "0123456789ABCDEF"
        status, time_payload = self.request(f"/gd/get_current_time?otk={token}&digest2=client-value&requestID=request-id")
        self.assertEqual(200, status)
        self.assertTrue(time_payload["success"])
        self.assertIsInstance(time_payload["timestamp"], float)
        self.assertEqual(16, len(time_payload["digest"]))
        status, status_payload = self.request(
            f"/gd/get_server_status?platform=GooglePlay&app_version=5.57&otk={token}&digest2=client-value&requestID=request-id"
        )
        self.assertEqual(200, status)
        self.assertEqual({"success", "digest", "constants"}, set(status_payload))
        self.assertTrue(status_payload["success"])
        self.assertEqual(16, len(status_payload["digest"]))
        # Both version projections must clear 4.99 or the client disables every
        # Huntland card, and the country arrays must accompany them or its
        # final-major login branch dereferences a null.
        constants = status_payload["constants"]
        self.assertGreater(constants["currentVersion_iOS"], 4.99)
        self.assertGreater(constants["currentVersion_Android"], 4.99)
        for name in ("CountriesJa", "CountriesEn", "CountryCodes", "NoServiceCountryCodes"):
            self.assertIsInstance(constants[name], list)
        self.assertEqual(constants["CountryCodes"], ["US"])
        # A status call before any account exists still answers, with no zones.
        self.assertEqual([], constants["huntingHuntingList"])
        self.assertEqual([], constants["metalHuntingList"])
        # An empty list makes normal Special mode fall back to the client's
        # built-in 50 entries, including Metal. The closed recovered entry
        # keeps the server authoritative without rendering an unsupported row.
        self.assertEqual(["3003-1"], constants["specialQuestList"])
        # Both boxes must be set. Left unset, the client caps the roster at its
        # own default of 50 and refuses the pull that would exceed it.
        self.assertGreater(constants["maxCharacterCount"], 50)
        self.assertGreater(constants["maxBuddyBoxCount"], 50)
        # The Pact costs the client will now enforce must be the same numbers
        # the server charges, or it gates a draw the server would have allowed.
        pacts = self.server.pact_draw_catalog
        if pacts is not None:
            self.assertEqual(pacts.cost_for_kind(0)[1], constants["NormalSlotCoins"])
            self.assertEqual(pacts.cost_for_kind(1)[1], constants["RareSlotEnergy"])
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        status, signup_payload = self.request(
            f"/gd/signup?uuid={account_id}&token=&platform=GooglePlay&app_version=5.57&otk={token}&digest2=client-value&requestID=signup-request"
        )
        self.assertEqual(200, status)
        self.assertEqual(account_id, signup_payload["id"])
        self.assertEqual(16, len(signup_payload["digest"]))
        status, duplicate_signup = self.request(
            f"/gd/signup?uuid={account_id}&token=&platform=GooglePlay&app_version=5.57&otk={token}&digest2=client-value&requestID=signup-request"
        )
        self.assertEqual(200, status)
        self.assertEqual(account_id, duplicate_signup["id"])
        login_token = "FEDCBA9876543210"
        status, login_payload = self.request(
            f"/gd/login?uuid={account_id}&platform=GooglePlay&app_version=5.57&app_version_verify=client-value&titlelogin=True&otk={login_token}&digest2=client-value&requestID=login-request"
        )
        self.assertEqual(200, status)
        self.assertEqual(account_id, login_payload["id"])
        self.assertEqual("Player", login_payload["name"])
        self.assertEqual(0.0, login_payload["weeklyChallenge"]["startDate"])
        status, multiplay = self.request(f"/gd/multiplay_enable?otk={login_token}&digest2=client-value&requestID=multiplay-enable")
        self.assertEqual(200, status)
        self.assertEqual({"success": True, "enable": False, "enablemain": False}, {key: multiplay[key] for key in ("success", "enable", "enablemain")})
        status, special_event = self.request(f"/gd/get_special_event_param?otk={login_token}&digest2=client-value&requestID=special-event")
        self.assertEqual(200, status)
        self.assertEqual({"success", "digest"}, set(special_event))
        grace_body = "kind=10&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"
        status, early_grace = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=early-grace", grace_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", early_grace["error"])
        self.restart()
        status, userdata_payload = self.request(f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=userdata-request")
        self.assertEqual(200, status)
        self.assertEqual([], userdata_payload["chrdata"])
        self.assertEqual([], userdata_payload["teamMembers"])
        self.assertEqual(1.0, userdata_payload["lastupdate"])
        status, after_close = self.request(f"/gd/userdata_after_close?otk={login_token}&digest2=client-value&requestID=after-close")
        self.assertEqual(200, status)
        self.assertEqual({key: userdata_payload[key] for key in userdata_payload if key != "digest"}, {key: after_close[key] for key in after_close if key != "digest"})
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(persisted["accounts"]))
        with patch(
            "liminal_gate.bootstrap_server.random.SystemRandom.randrange",
            return_value=1,
        ):
            status, grace_payload = self.post(
                f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=grace-request", grace_body
            )
        self.assertEqual(200, status)
        self.assertEqual(3, grace_payload["chrdata"][0]["id"])
        status, grace_replay = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=retry-value&requestID=grace-request", grace_body
        )
        self.assertEqual(200, status)
        self.assertEqual(grace_payload["chrdata"], grace_replay["chrdata"])
        status, collision = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=grace-request",
            "kind=99&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1",
        )
        # Reusing a spent requestID with a different body is no longer read
        # as a tampered retry; it is answered on its own merits.
        self.assertEqual(501, status)
        self.assertEqual("unsupported_summon", collision["error"])
        self.restart()
        amisandra_body = "kind=11&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"
        status, amisandra_payload = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=amisandra-request", amisandra_body
        )
        self.assertEqual(200, status)
        self.assertEqual(25, amisandra_payload["chrdata"][0]["id"])
        self.assertEqual(15, amisandra_payload["chrdata"][0]["levelAdded"])
        write_body = urlencode([
            (name, value.replace("{{tutorial_starter_id}}", "3"))
            for name, value in self.server.profile.tutorial_writes[0]["fields"]
        ])
        status, write_payload = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=tutorial-write", write_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, write_payload["lastupdate"])
        status, write_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=tutorial-write", write_body
        )
        self.assertEqual(200, status)
        self.assertEqual(write_payload["lastupdate"], write_replay["lastupdate"])
        status, write_collision = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=tutorial-write", "progressCode=0"
        )
        # Reusing a spent requestID with a different body is no longer read
        # as a tampered retry; it is answered on its own merits.
        self.assertEqual(501, status)
        self.assertEqual("unsupported_userdata_write", write_collision["error"])
        map_body = urlencode([tuple(field) for field in self.server.profile.tutorial_writes[1]["fields"]])
        status, reordered_map = self.post(
            f"/gd/userdata?otk={login_token}&requestID=reordered-map",
            "worldMapNo=0&progressCode=16777281&lastUpdate=1",
        )
        self.assertEqual(501, status)
        self.assertEqual("unsupported_userdata_write", reordered_map["error"])
        self.server.story_progression_catalog = build_core_story_policy()
        status, map_payload = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=map-write", map_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, map_payload["lastupdate"])
        self.restart()
        status, final_userdata = self.request(f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=final-userdata")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 0, 0, 0, 0], final_userdata["teamMembers"])
        self.assertEqual([3, 25], [entry["id"] for entry in final_userdata["chrdata"]])
        self.assertEqual(16777281, final_userdata["progressCode"])
        status, map_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=map-write", map_body
        )
        self.assertEqual(200, status)
        self.assertEqual(map_payload["lastupdate"], map_replay["lastupdate"])
        start_body = self.server.profile.story_starts[0]["body"]
        status, start_payload = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-start", start_body
        )
        self.assertEqual(200, status)
        self.assertEqual({"success", "refillStartTime", "digest"}, set(start_payload))
        self.assertTrue(start_payload["success"])
        self.assertEqual(0.0, start_payload["refillStartTime"])
        status, start_collision = self.post(
            f"/gd/start_quest?otk={login_token}&requestID=chapter1-start", "stamina=0"
        )
        # Reusing a spent requestID with a different body is no longer read
        # as a tampered retry; it is answered on its own merits.
        self.assertEqual(501, status)
        self.assertEqual("unsupported_start_quest", start_collision["error"])
        self.restart()
        status, start_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-start", start_body
        )
        self.assertEqual(200, status)
        self.assertEqual(start_payload["refillStartTime"], start_replay["refillStartTime"])
        clear_fields = {
            "progressCode": "16777282",
            "worldMapNo": "0",
            "valuables": json.dumps({"coins": 30}),
            "chrdata": json.dumps([]),
            "itemList": json.dumps([]),
            "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 1, "coins": 30, "exp": 720}),
            "itmp0": "0",
            "itmp1": "0",
            "lastUpdate": "1",
        }
        clear_body = urlencode(clear_fields)
        status, clear_payload = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-clear", clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual({"success", "lastupdate", "digest"}, set(clear_payload))
        self.assertEqual(1.0, clear_payload["lastupdate"])
        status, clear_collision = self.post(
            f"/gd/clear_quest?otk={login_token}&requestID=chapter1-clear", "progressCode=0"
        )
        # Reusing a spent requestID with a different body is no longer read
        # as a tampered retry; it is answered on its own merits.
        self.assertEqual(501, status)
        self.assertEqual("unsupported_clear_quest", clear_collision["error"])
        self.restart()
        status, clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-clear", clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(clear_payload["lastupdate"], clear_replay["lastupdate"])
        status, repeated_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&requestID=chapter1-clear-new", clear_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", repeated_clear["error"])
        status, unknown_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&requestID=unknown-clear", "progressCode=0"
        )
        self.assertEqual(501, status)
        self.assertEqual("unsupported_clear_quest", unknown_clear["error"])
        status, final_userdata = self.request(f"/gd/userdata?otk={login_token}&requestID=after-clear")
        self.assertEqual(200, status)
        self.assertEqual(16777282, final_userdata["progressCode"])
        self.assertEqual(30, final_userdata["coins"])
        restart_restore_body = urlencode([
            ("chrdata", json.dumps(final_userdata["chrdata"])),
            ("teamMembers", json.dumps([3, 25, 0, 0, 0, 0])),
            ("teamMembers_VS", json.dumps([0] * 18)),
            ("teamBuddies_VS", json.dumps([0] * 18)),
            ("teamNo", "1"),
            ("teamNo_VS", "1"),
            ("summonId", "1"),
            ("lastUpdate", "1"),
        ])
        status, restart_restore = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=restart-restore",
            restart_restore_body,
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, restart_restore["lastupdate"])
        persisted_before_restore_replay = json.loads(
            self.state_path.read_text(encoding="utf-8")
        )["accounts"][account_id]
        self.assertEqual("chapter1_1_cleared", persisted_before_restore_replay["tutorial_phase"])
        self.assertEqual(final_userdata["chrdata"], persisted_before_restore_replay["userdata"]["chrdata"])
        self.restart()
        status, restart_restore_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=restart-restore",
            restart_restore_body,
        )
        self.assertEqual(200, status)
        self.assertEqual(restart_restore["lastupdate"], restart_restore_replay["lastupdate"])
        self.assertEqual(
            "chapter1_1_cleared",
            json.loads(self.state_path.read_text(encoding="utf-8"))["accounts"][account_id]["tutorial_phase"],
        )
        knight_body = "kind=12&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"
        status, knight_payload = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=client-value&requestID=knight-grant", knight_body
        )
        self.assertEqual(200, status)
        self.assertEqual(64, knight_payload["chrdata"][0]["id"])
        self.assertEqual(10, knight_payload["chrdata"][0]["levelAdded"])
        status, knight_collision = self.post(
            f"/gd/do_slot?otk={login_token}&requestID=knight-grant", grace_body
        )
        # Reusing a spent requestID with a different body is no longer read
        # as a tampered retry; it is answered on its own merits.
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", knight_collision["error"])
        self.restart()
        status, knight_replay = self.post(
            f"/gd/do_slot?otk={login_token}&digest2=retry-value&requestID=knight-grant", knight_body
        )
        self.assertEqual(200, status)
        self.assertEqual(knight_payload["chrdata"], knight_replay["chrdata"])
        status, after_knight = self.request(f"/gd/userdata?otk={login_token}&requestID=after-knight")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 64], [entry["id"] for entry in after_knight["chrdata"]])
        knight_write_body = urlencode([
            ("chrdata", json.dumps([{"id": 64, "jobID": 0, "jobLevels": [10.0, 0.0, 0.0]}])),
            ("lastUpdate", "1"),
        ])
        status, knight_write = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=knight-write", knight_write_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, knight_write["lastupdate"])
        self.restart()
        status, knight_write_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=knight-write", knight_write_body
        )
        self.assertEqual(200, status)
        self.assertEqual(knight_write["lastupdate"], knight_write_replay["lastupdate"])
        status, knight_write_collision = self.post(
            f"/gd/userdata?otk={login_token}&requestID=knight-write", "chrdata=%5B%5D&lastUpdate=1"
        )
        # Reusing a spent requestID with a different body is no longer read
        # as a tampered retry; it is answered on its own merits.
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", knight_write_collision["error"])
        status, repeated_knight_write = self.post(
            f"/gd/userdata?otk={login_token}&requestID=knight-write-new", knight_write_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", repeated_knight_write["error"])
        knight_party_body = urlencode([
            ("chrdata", json.dumps([{"id": 64, "flags": 1}])),
            ("teamMembers", json.dumps([3, 25, 64, 0, 0, 0])),
            ("teamMembers_VS", json.dumps([0] * 18)),
            ("teamBuddies_VS", json.dumps([0] * 18)),
            ("teamNo", "1"),
            ("teamNo_VS", "1"),
            ("summonId", "1"),
            ("lastUpdate", "1"),
        ])
        status, knight_party = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=knight-party", knight_party_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, knight_party["lastupdate"])
        self.restart()
        status, knight_party_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=knight-party", knight_party_body
        )
        self.assertEqual(200, status)
        self.assertEqual(knight_party["lastupdate"], knight_party_replay["lastupdate"])
        status, after_party = self.request(f"/gd/userdata?otk={login_token}&requestID=after-party")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 64, 0, 0, 0], after_party["teamMembers"])
        chapter1_2_body = "stamina=1&coins=0&chapter=1&section=2&lastUpdate=1"
        status, chapter1_2 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-2-start", chapter1_2_body
        )
        self.assertEqual(200, status)
        self.assertEqual(0.0, chapter1_2["refillStartTime"])
        self.restart()
        status, chapter1_2_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-2-start", chapter1_2_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_2["refillStartTime"], chapter1_2_replay["refillStartTime"])
        chapter1_2_clear_body = urlencode({
            "progressCode": "16777283", "worldMapNo": "0", "valuables": json.dumps({"coins": 50}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 2, "coins": 50, "exp": 1224}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter1_2_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-2-clear", chapter1_2_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter1_2_clear["sentMessage"])
        self.assertEqual([3, 25, 64, 63], [row["id"] for row in chapter1_2_clear["chrdata"]])
        self.restart()
        status, chapter1_2_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-2-clear", chapter1_2_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_2_clear["chrdata"], chapter1_2_clear_replay["chrdata"])
        warrior_party_body = urlencode([
            ("chrdata", json.dumps([{"id": 63, "flags": 1}])),
            ("teamMembers", json.dumps([3, 25, 64, 63, 0, 0])),
            ("teamMembers_VS", json.dumps([0] * 18)),
            ("teamBuddies_VS", json.dumps([0] * 18)),
            ("teamNo", "1"), ("teamNo_VS", "1"), ("summonId", "1"), ("lastUpdate", "1"),
        ])
        status, warrior_party = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=warrior-party", warrior_party_body
        )
        self.assertEqual(200, status)
        self.restart()
        status, warrior_party_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=warrior-party", warrior_party_body
        )
        self.assertEqual(200, status)
        self.assertEqual(warrior_party["lastupdate"], warrior_party_replay["lastupdate"])
        status, after_warrior_party = self.request(f"/gd/userdata?otk={login_token}&requestID=after-warrior-party")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 64, 63, 0, 0], after_warrior_party["teamMembers"])
        chapter1_3_body = "stamina=1&coins=0&chapter=1&section=3&lastUpdate=1"
        status, chapter1_3 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-3-start", chapter1_3_body
        )
        self.assertEqual(200, status)
        self.assertEqual(0.0, chapter1_3["refillStartTime"])
        self.restart()
        status, chapter1_3_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-3-start", chapter1_3_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_3["refillStartTime"], chapter1_3_replay["refillStartTime"])
        chapter1_3_clear_body = urlencode({
            "progressCode": "16777284", "worldMapNo": "0", "valuables": json.dumps({"coins": 90}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 3, "coins": 40, "exp": 960}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter1_3_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-3-clear", chapter1_3_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter1_3_clear["sentMessage"])
        self.restart()
        status, chapter1_3_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-3-clear", chapter1_3_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_3_clear["lastupdate"], chapter1_3_clear_replay["lastupdate"])
        chapter1_4_body = "stamina=1&coins=0&chapter=1&section=4&lastUpdate=1"
        status, chapter1_4 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-4-start", chapter1_4_body
        )
        self.assertEqual(200, status)
        self.assertEqual(0.0, chapter1_4["refillStartTime"])
        self.restart()
        status, chapter1_4_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-4-start", chapter1_4_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_4["refillStartTime"], chapter1_4_replay["refillStartTime"])
        chapter1_4_clear_body = urlencode({
            "progressCode": "16777285", "worldMapNo": "0", "valuables": json.dumps({"coins": 140}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 4, "coins": 50}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter1_4_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-4-clear", chapter1_4_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter1_4_clear["sentMessage"])
        self.restart()
        status, chapter1_4_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-4-clear", chapter1_4_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_4_clear["lastupdate"], chapter1_4_clear_replay["lastupdate"])
        chapter1_5_body = "stamina=1&coins=0&chapter=1&section=5&lastUpdate=1"
        status, chapter1_5 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter1-5-start", chapter1_5_body
        )
        self.assertEqual(200, status)
        chapter1_5_clear_body = urlencode({
            "progressCode": "50331777", "worldMapNo": "0", "valuables": json.dumps({"coins": 218}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 1, "section": 5, "coins": 78}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter1_5_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter1-5-clear", chapter1_5_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter1_5_clear["sentMessage"])
        self.restart()
        status, chapter1_5_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter1-5-clear", chapter1_5_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter1_5_clear["lastupdate"], chapter1_5_clear_replay["lastupdate"])
        final_map_body = "progressCode=16777345&worldMapNo=0&lastUpdate=1"
        status, final_map = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=final-map", final_map_body
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, final_map["lastupdate"])
        self.restart()
        status, final_map_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=final-map", final_map_body
        )
        self.assertEqual(200, status)
        self.assertEqual(final_map["lastupdate"], final_map_replay["lastupdate"])
        status, free_roam_userdata = self.request(f"/gd/userdata?otk={login_token}&requestID=free-roam-userdata")
        self.assertEqual(200, status)
        self.assertEqual(16777345, free_roam_userdata["progressCode"])
        post_tutorial_team_body = urlencode({
            "teamMembers": json.dumps([3, 25, 64, 63, 0, 0] * 12, separators=(",", ":")),
            "teamMembers_VS": json.dumps([0] * 18, separators=(",", ":")),
            "teamBuddies_VS": json.dumps([0] * 18, separators=(",", ":")),
            "teamNo": "1", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
        })
        status, team_write = self.post(
            f"/gd/userdata?otk={login_token}&digest2=client-value&requestID=post-tutorial-team",
            post_tutorial_team_body,
        )
        self.assertEqual(200, status)
        self.assertEqual(1.0, team_write["lastupdate"])
        self.restart()
        status, team_write_replay = self.post(
            f"/gd/userdata?otk={login_token}&digest2=retry-value&requestID=post-tutorial-team",
            post_tutorial_team_body,
        )
        self.assertEqual(200, status)
        self.assertEqual(team_write["lastupdate"], team_write_replay["lastupdate"])
        chapter2_1_body = "stamina=5&coins=0&chapter=2&section=1&lastUpdate=1"
        status, chapter2_1 = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=client-value&requestID=chapter2-1-start", chapter2_1_body
        )
        self.assertEqual(200, status)
        self.assertEqual(0.0, chapter2_1["refillStartTime"])
        self.restart()
        status, chapter2_1_replay = self.post(
            f"/gd/start_quest?otk={login_token}&digest2=retry-value&requestID=chapter2-1-start", chapter2_1_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter2_1["refillStartTime"], chapter2_1_replay["refillStartTime"])
        chapter2_1_clear_body = urlencode({
            "progressCode": "16777346", "worldMapNo": "0", "valuables": json.dumps({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 0, "energyGooglePlay": 0, "coins": 210}),
            "chrdata": json.dumps([]), "itemList": json.dumps([]), "summonList": json.dumps([]),
            "battle_result": json.dumps({"chapter": 2, "section": 1, "coins": 210, "exp": 3340}),
            "itmp0": "0", "itmp1": "0", "lastUpdate": "1",
        })
        status, chapter2_1_clear = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=client-value&requestID=chapter2-1-clear", chapter2_1_clear_body
        )
        self.assertEqual(200, status)
        self.assertFalse(chapter2_1_clear["sentMessage"])
        self.assertEqual(50, chapter2_1_clear["freeEnergy"])
        self.assertEqual(210, chapter2_1_clear["coins"])
        with self.server.state.lock:
            self.assertEqual(50, self.server.state.accounts[account_id]["userdata"]["valuables"]["freeEnergy"])
        self.restart()
        status, chapter2_1_clear_replay = self.post(
            f"/gd/clear_quest?otk={login_token}&digest2=retry-value&requestID=chapter2-1-clear", chapter2_1_clear_body
        )
        self.assertEqual(200, status)
        self.assertEqual(chapter2_1_clear["lastupdate"], chapter2_1_clear_replay["lastupdate"])
        status, after_chapter2_1 = self.request(f"/gd/userdata?otk={login_token}&requestID=after-chapter2-1")
        self.assertEqual(200, status)
        self.assertEqual(16777346, after_chapter2_1["progressCode"])
        self.assertEqual(210, after_chapter2_1["coins"])
        self.assertEqual({"energyAppStore": 0, "energy": 0, "energyAndApp": 0, "freeEnergy": 50, "energyGooglePlay": 0, "coins": 210}, after_chapter2_1["valuables"])
        status, repeated_knight = self.post(
            f"/gd/do_slot?otk={login_token}&requestID=knight-grant-new", knight_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", repeated_knight["error"])
        status, repeated_start = self.post(
            f"/gd/start_quest?otk={login_token}&requestID=chapter1-start-new", start_body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", repeated_start["error"])
        status, unknown_start = self.post(
            f"/gd/start_quest?otk={login_token}&requestID=unknown-start", "stamina=0"
        )
        self.assertEqual(501, status)
        self.assertEqual("unsupported_start_quest", unknown_start["error"])
        status, userdata_payload = self.post(
            f"/gd/userdata?otk={login_token}&requestID=unsupported-userdata", "progressCode=0"
        )
        self.assertEqual(501, status)
        self.assertEqual("unsupported_userdata_write", userdata_payload["error"])
        status, payload = self.post(f"/gd/do_slot?otk={login_token}&requestID=unsupported", "kind=0")
        self.assertEqual(501, status)
        self.assertEqual("unsupported_summon", payload["error"])

    def test_mutation_binds_rotated_token_to_active_account_durably(self) -> None:
        signup_token = "0123456789ABCDEF"
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        status, _ = self.request(
            f"/gd/signup?uuid={account_id}&token=&platform=GooglePlay&app_version=5.57"
            f"&otk={signup_token}&digest2=client-value&requestID=signup-request"
        )
        self.assertEqual(200, status)
        rotated_token = "E3ACCAAA6A4BAC90"
        body = "kind=10&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"
        status, payload = self.post(
            f"/gd/do_slot?otk={rotated_token}&digest2=client-value&requestID=rotated-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])
        self.assertEqual(account_id, self.server.state.tokens[rotated_token])
        self.restart()
        status, payload = self.post(
            f"/gd/do_slot?otk={rotated_token}&digest2=retry-value&requestID=rotated-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])
        # Sign the second account up over HTTP, the only way it becomes the
        # active account in the real protocol, so it claims this client too.
        self.request("/gd/signup?uuid=second-local-account&otk=second-token&requestID=second-signup")
        self.assertTrue(self.server.state.bind_rotated_token(rotated_token))
        # A later login may change the local fallback account, but it must not
        # steal an OTK already durably associated with the first account.
        self.assertEqual(account_id, self.server.state.tokens[rotated_token])
        self.restart()
        status, payload = self.post(
            f"/gd/do_slot?otk={rotated_token}&digest2=retry-value&requestID=rotated-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])
        status, payload = self.post(
            "/gd/do_slot?otk=unbound-token&digest2=client-value&requestID=ambiguous-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])
        self.assertEqual("second-local-account", self.server.state.tokens["unbound-token"])
        self.restart()
        status, payload = self.post(
            "/gd/do_slot?otk=unbound-token&digest2=retry-value&requestID=ambiguous-token-request", body
        )
        self.assertEqual(409, status)
        self.assertEqual("tutorial_state_conflict", payload["error"])

    def test_legacy_multi_account_state_keeps_unbound_rotated_token_unauthorized(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.state_path.write_text(json.dumps({
            "accounts": {
                "first": {"userdata": {}},
                "second": {"userdata": {}},
            },
            "tokens": {},
        }), encoding="utf-8")
        state = BootstrapState(self.state_path)
        try:
            self.assertFalse(state.bind_rotated_token("unbound-token"))
        finally:
            state.close()

    def test_user_data_binds_rotated_token_to_active_account_durably(self) -> None:
        signup_token = "0123456789ABCDEF"
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        status, _ = self.request(
            f"/gd/signup?uuid={account_id}&token=&platform=GooglePlay&app_version=5.57"
            f"&otk={signup_token}&digest2=client-value&requestID=signup-request"
        )
        self.assertEqual(200, status)
        login_token = "FEDCBA9876543210"
        status, _ = self.request(
            f"/gd/login?uuid={account_id}&platform=GooglePlay&app_version=5.57"
            f"&app_version_verify=client-value&titlelogin=True&otk={login_token}"
            "&digest2=client-value&requestID=login-request"
        )
        self.assertEqual(200, status)
        rotated_token = "E3ACCAAA6A4BAC90"
        status, payload = self.request(
            f"/gd/userdata?otk={rotated_token}&digest2=client-value&requestID=rotated-userdata"
        )
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        self.assertEqual(account_id, self.server.state.tokens[rotated_token])
        self.restart()
        status, payload = self.request(
            f"/gd/userdata?otk={rotated_token}&digest2=retry-value&requestID=rotated-userdata"
        )
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        # Sign the second account up over HTTP, the only way it becomes the
        # active account in the real protocol, so it claims this client too.
        self.request("/gd/signup?uuid=second-local-account&otk=second-token&requestID=second-signup")
        status, payload = self.request(
            "/gd/userdata?otk=unbound-token&digest2=client-value&requestID=ambiguous-userdata"
        )
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        self.assertEqual("second-local-account", self.server.state.tokens["unbound-token"])

    def test_a_shared_request_id_keeps_each_body_separately_replayable(self) -> None:
        """`requestID` alone cannot identify a mutation.

        The client derives it from a ~7-significant-digit float, so two
        unrelated requests can land on the same one.  Keyed by `requestID`
        alone the second was refused as a tampered retry -- and because a retry
        replays the same id *and* body byte for byte, it then collided forever
        and that one action could never complete.

        Scoping the cache by body settles all three cases at once: a retry
        replays, a genuine second request applies, and neither displaces the
        other's entry.
        """
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        token = "0123456789ABCDEF"
        self.request(f"/gd/signup?uuid={account_id}&otk={token}&requestID=signup")
        shared = f"/gd/change_uname?otk={token}&requestID=collided"

        status, named = self.post(shared, urlencode({"name": "Alcina"}))
        self.assertEqual((200, "Alcina"), (status, named["name"]))
        # A retry replays rather than spending the rename a second time.
        self.assertEqual((status, named), self.post(shared, urlencode({"name": "Alcina"})))

        # A different body under that same requestID is a different request. It
        # is answered on its own merits -- here refused by the rename cooldown,
        # which is exactly what proves it reached the handler at all.
        status, other = self.post(shared, urlencode({"name": "Brigid"}))
        self.assertEqual((200, 1), (status, other["cmdError"]))
        self.assertEqual("Alcina", self.server.state.accounts[account_id]["username"])

        # Settling the second body must not have displaced the first's entry.
        self.assertEqual((200, named), self.post(shared, urlencode({"name": "Alcina"})))
        self.restart()
        status, after_restart = self.post(shared, urlencode({"name": "Alcina"}))
        # Compared field-wise: `change_uname` does not canonicalise its payload,
        # so a reloaded save replays the same values in JSON key order.
        self.assertEqual(200, status)
        self.assertEqual(
            {key: named[key] for key in ("success", "name", "changeUsernameDate")},
            {key: after_restart[key] for key in ("success", "name", "changeUsernameDate")},
        )
        self.assertEqual("Alcina", self.server.state.accounts[account_id]["username"])

    def test_free_roam_character_and_party_writes_persist_and_replay(self) -> None:
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        token = "0123456789ABCDEF"
        self.request(f"/gd/signup?uuid={account_id}&otk={token}&requestID=signup")
        characters = [{"id": 3, "jobID": 0, "jobLevels": [1], "jobSlots": [], "isNew": False}]
        with self.server.state.lock:
            account = self.server.state.accounts[account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            account["userdata"]["chrdata"] = copy.deepcopy(characters)
            self.server.state._persist_locked()
        character_body = urlencode({"chrdata": json.dumps(characters), "lastUpdate": "1"})
        status, payload = self.post(f"/gd/userdata?otk={token}&requestID=character-close", character_body)
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        self.assertEqual((status, payload), self.post(f"/gd/userdata?otk={token}&requestID=character-close", character_body))
        party_body = urlencode({
            "chrdata": json.dumps(characters), "teamMembers": json.dumps([3, 0, 0, 0, 0, 0]),
            "teamMembers_VS": json.dumps([0] * 18), "teamBuddies_VS": json.dumps([0] * 18),
            "teamNo": "1", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
        })
        status, payload = self.post(f"/gd/userdata?otk={token}&requestID=party-close", party_body)
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        party_only_body = urlencode({
            "teamMembers": json.dumps([3, 0, 0, 0, 0, 0]),
            "teamMembers_VS": json.dumps([0] * 18), "teamBuddies_VS": json.dumps([0] * 18),
            "teamNo": "2", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
        })
        status, payload = self.post(f"/gd/userdata?otk={token}&requestID=party-only-close", party_only_body)
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        self.assertEqual((status, payload), self.post(f"/gd/userdata?otk={token}&requestID=party-only-close", party_only_body))
        self.restart()
        status, userdata = self.request(f"/gd/userdata?otk={token}&requestID=after-party")
        self.assertEqual(200, status)
        self.assertEqual(characters, userdata["chrdata"])
        self.assertEqual([3, 0, 0, 0, 0, 0], userdata["teamMembers"])
        self.assertEqual(2, userdata["teamNo"])

    def test_give_up_character_save_abandons_active_story_without_changing_coins(self) -> None:
        """The observed post-Give-Up chrdata write must release Chapter 2-2."""
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        token = "0123456789ABCDEF"
        self.request(f"/gd/signup?uuid={account_id}&otk={token}&requestID=signup")
        characters = [{"id": 3, "jobID": 0, "jobLevels": [1], "jobSlots": [], "isNew": False}]
        with self.server.state.lock:
            account = self.server.state.accounts[account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            account["userdata"].update({
                "progressCode": 16777346,
                "coins": 487,
                "valuables": {"coins": 487},
                "chrdata": copy.deepcopy(characters),
            })
            self.server.state._persist_locked()
        self.server.story_progression_catalog = build_core_story_policy()

        start = urlencode([
            ("stamina", "5"), ("coins", "0"), ("chapter", "2"),
            ("section", "2"), ("lastUpdate", "1"),
        ])
        status, _ = self.post(f"/gd/start_quest?otk={token}&requestID=chapter-2-2", start)
        self.assertEqual(200, status)
        self.assertEqual("generic_story_active", self.server.state.accounts[account_id]["tutorial_phase"])

        give_up = urlencode({"chrdata": json.dumps(characters), "lastUpdate": "1"})
        status, payload = self.post(f"/gd/userdata?otk={token}&requestID=give-up", give_up)
        self.assertEqual((200, True), (status, payload["success"]))
        self.assertEqual((status, payload), self.post(f"/gd/userdata?otk={token}&requestID=give-up", give_up))
        account = self.server.state.accounts[account_id]
        self.assertEqual(("free_roam", None, 487), (
            account["tutorial_phase"], account["active_generic_story"], account["userdata"]["coins"],
        ))

        self.restart()
        status, userdata = self.request(f"/gd/userdata?otk={token}&requestID=after-give-up")
        self.assertEqual(200, status)
        self.assertEqual(487, userdata["coins"])

    def test_free_roam_party_delta_never_discards_roster_on_rejection(self) -> None:
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        token = "0123456789ABCDEF"
        self.request(f"/gd/signup?uuid={account_id}&otk={token}&requestID=signup")
        roster = [
            {"id": 3, "jobID": 0, "jobLevels": [1], "jobSlots": []},
            {"id": 25, "jobID": 0, "jobLevels": [15], "jobSlots": []},
            {"id": 9001, "jobID": 0, "jobLevels": [10], "jobSlots": [], "skillBoost": 0},
        ]
        with self.server.state.lock:
            account = self.server.state.accounts[account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            account["userdata"]["chrdata"] = roster
            self.server.state._persist_locked()

        delta = [{"id": 9001, "isNew": False}]
        party_body = urlencode({
            "chrdata": json.dumps(delta), "teamMembers": json.dumps([3, 25, 9001, 0, 0, 0]),
            "teamMembers_VS": json.dumps([0] * 18), "teamBuddies_VS": json.dumps([0] * 18),
            "teamNo": "1", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
        })
        status, payload = self.post(f"/gd/userdata?otk={token}&requestID=party-delta", party_body)
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        persisted = self.server.state.userdata_for(token)
        assert persisted is not None
        self.assertEqual([3, 25, 9001], [row["id"] for row in persisted["chrdata"]])
        self.assertEqual(10, persisted["chrdata"][2]["jobLevels"][0])
        self.assertFalse(persisted["chrdata"][2]["isNew"])

        rejected_body = urlencode({
            "chrdata": json.dumps(delta), "teamMembers": json.dumps([3, 25, 9999, 0, 0, 0]),
            "teamMembers_VS": json.dumps([0] * 18), "teamBuddies_VS": json.dumps([0] * 18),
            "teamNo": "1", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
        })
        status, payload = self.post(f"/gd/userdata?otk={token}&requestID=bad-party", rejected_body)
        self.assertEqual((409, "tutorial_state_conflict"), (status, payload["error"]))
        persisted = self.server.state.userdata_for(token)
        assert persisted is not None
        self.assertEqual([3, 25, 9001], [row["id"] for row in persisted["chrdata"]])

        self.restart()
        status, userdata = self.request(f"/gd/userdata?otk={token}&requestID=after-party-delta")
        self.assertEqual(200, status)
        self.assertEqual([3, 25, 9001], [row["id"] for row in userdata["chrdata"]])

    def test_free_roam_party_layout_rejection_is_not_answered_by_a_scripted_success(self) -> None:
        """A rejected party-only save must not fall through to the tutorial script.

        The profile's last structural write has the same field names as the
        free-roam party-layout save and runs `free_roam -> free_roam`, but it
        only stores `lastupdate`.  If it can still settle a save that the
        free-roam handler rejected, the client is told `success` while its
        party is silently discarded and reverts on the next login.
        """
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        token = "0123456789ABCDEF"
        self.request(f"/gd/signup?uuid={account_id}&otk={token}&requestID=signup")
        with self.server.state.lock:
            account = self.server.state.accounts[account_id]
            account["tutorial_phase"] = "free_roam"
            account["initial_userdata_served"] = True
            account["userdata"]["chrdata"] = [
                {"id": 3, "jobID": 0, "jobLevels": [1], "jobSlots": []},
                {"id": 25, "jobID": 0, "jobLevels": [15], "jobSlots": []},
            ]
            account["userdata"]["teamMembers"] = [3, 25, 0, 0, 0, 0]
            self.server.state._persist_locked()

        def layout(members: list[int]) -> str:
            return urlencode({
                "teamMembers": json.dumps(members),
                "teamMembers_VS": json.dumps([0] * 18), "teamBuddies_VS": json.dumps([0] * 18),
                "teamNo": "1", "teamNo_VS": "1", "summonId": "1", "lastUpdate": "1",
            })

        status, payload = self.post(f"/gd/userdata?otk={token}&requestID=good-layout", layout([25, 3, 0, 0, 0, 0]))
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        persisted = self.server.state.userdata_for(token)
        assert persisted is not None
        self.assertEqual([25, 3, 0, 0, 0, 0], persisted["teamMembers"])

        status, payload = self.post(f"/gd/userdata?otk={token}&requestID=bad-layout", layout([25, 3, 9999, 0, 0, 0]))
        self.assertEqual((409, "tutorial_state_conflict"), (status, payload["error"]))
        self.restart()
        status, userdata = self.request(f"/gd/userdata?otk={token}&requestID=after-bad-layout")
        self.assertEqual(200, status)
        self.assertEqual([25, 3, 0, 0, 0, 0], userdata["teamMembers"])

    def test_userdata_read_without_a_token_cannot_break_later_saves(self) -> None:
        """A missing `otk` must not insert a non-string key into the token map.

        `_persist_locked` sorts the token keys, so a `None` key makes every
        later save raise and the account silently stops persisting for the rest
        of the process.
        """
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        token = "0123456789ABCDEF"
        self.request(f"/gd/signup?uuid={account_id}&otk={token}&requestID=signup")
        status, payload = self.request("/gd/userdata?requestID=no-token")
        self.assertEqual((401, "unknown_local_account"), (status, payload["error"]))
        self.assertEqual([token], [key for key in self.server.state.tokens])

        status, payload = self.post(f"/gd/change_uname?otk={token}&requestID=rename", urlencode({"name": "Alcina"}))
        self.assertEqual(200, status)
        self.assertTrue(payload["success"])
        self.restart()
        self.assertEqual("Alcina", self.server.state.accounts[account_id]["username"])

    def test_replay_caches_and_token_map_stay_bounded_across_a_long_session(self) -> None:
        """`requestID` and `otk` are append-only on the wire; the save is not.

        Both grow by an entry every few seconds of play and are re-encoded on
        every later save, so an unbounded window turns each save into a slower
        whole-file rewrite for as long as the account is played.
        """
        account_id = "0123456789ABCDEF0123456789ABCDEF"
        token = "0123456789ABCDEF"
        self.request(f"/gd/signup?uuid={account_id}&otk={token}&requestID=signup")
        with self.server.state.lock:
            account = self.server.state.accounts[account_id]
            account["tutorial_requests"] = {f"old-{index}": {"body_sha256": "", "payload": {}} for index in range(4000)}
            self.server.state.tokens.update({f"OTK{index:013X}": account_id for index in range(4000)})
            self.server.state._persist_locked()

        document = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(512, len(document["accounts"][account_id]["tutorial_requests"]))
        self.assertEqual(512, len(document["tokens"]))
        # The window is the *most recent* history, so the client's live token
        # and an in-flight retry both still resolve.
        self.assertIn("OTK0000000000F9F", document["tokens"])
        self.assertIn("old-3999", document["accounts"][account_id]["tutorial_requests"])
        self.assertNotIn("old-0", document["accounts"][account_id]["tutorial_requests"])
        status, userdata = self.request(f"/gd/userdata?otk=OTK0000000000F9F&requestID=late-read")
        self.assertEqual(200, status)
        self.assertTrue(userdata["success"])

    def test_local_news_page_and_favicon_are_not_protocol_errors(self) -> None:
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", "/en/news/app")
        response = connection.getresponse()
        page = response.read().decode("utf-8")
        self.assertEqual(200, response.status)
        self.assertEqual("text/html; charset=utf-8", response.getheader("Content-Type"))
        self.assertIn("Project Liminal Gate", page)
        connection.close()
        connection = HTTPConnection(*self.server.server_address)
        connection.request("GET", "/favicon.ico")
        response = connection.getresponse()
        self.assertEqual(204, response.status)
        self.assertEqual(0, len(response.read()))
        connection.close()
