from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from http.client import HTTPConnection
from pathlib import Path
from urllib.parse import urlencode

from liminal_gate.bootstrap_server import BootstrapServer, BootstrapState, load_profile
from liminal_gate.event_log import refused_write_shapes, safe_form_diagnostics


ROSTER = [{"id": 1, "lv": 30, "exp": 4096}, {"id": 2, "lv": 12, "exp": 64}]
COMPANIONS = [{"bid": 31, "lv": 1, "date": 0.0, "iid": 2, "exp": 0, "flag": 1, "chrID": 0}]


class EventLogPrivacyTest(unittest.TestCase):
    def test_malformed_body_records_only_hash_and_size(self) -> None:
        body = b"\xffprivate-binary"
        self.assertEqual(
            {
                "request_body_sha256": hashlib.sha256(body).hexdigest(),
                "request_body_size": len(body),
            },
            safe_form_diagnostics(body),
        )

    def test_no_string_from_the_body_reaches_the_shape(self) -> None:
        # Values are account state, and an unmodelled key name is a string the
        # body chose. Neither may appear; the unknown key is counted instead.
        body = urlencode({
            "chrdata": json.dumps([{"id": 7654321, "nickname": "SECRET", "lv": 99}]),
            "buddyInfo": json.dumps({"list": COMPANIONS, "private": [{"bid": 8675309}]}),
            "lastUpdate": "1",
        }).encode()
        shapes = refused_write_shapes(body)
        rendered = json.dumps(shapes)
        for leaked in ("7654321", "SECRET", "99", "8675309", "nickname", "private"):
            self.assertNotIn(leaked, rendered)
        self.assertEqual(1, shapes["chrdata"]["unrecognized_entry_keys"])
        self.assertEqual({"type": "object", "keys": ["list"], "unrecognized_keys": 1},
                         shapes["buddyInfo"])


class SettlementDiagnosticTest(unittest.TestCase):
    """What a refused settlement has to say about itself.

    Issue 29 logged eleven identical refusals of one Daily Quest clear, and the
    only settlement facts in them were chapter, section, coins and EXP -- all
    of which were inside their bounds. The channel actually at fault, a
    reported Companion, was invisible, and the cause had to be recovered from
    the client's own data instead.
    """

    def body(self, **battle) -> bytes:
        result = {
            "chapter": 6011, "section": 1, "coins": 0, "exp": 0,
            "items": {}, "buddies": [], "monsters": [], "summons": [],
        }
        return urlencode({"battle_result": json.dumps(result | battle), "lastUpdate": "1"}).encode()

    def test_a_settlement_reports_how_much_of_each_channel_it_claimed(self) -> None:
        details = safe_form_diagnostics(self.body(buddies=[267], items={"9": 3, "18": 2}))
        self.assertEqual(
            {
                "chapter": 6011, "section": 1, "coins": 0, "exp": 0,
                "reported_buddies": 1, "reported_monsters": 0, "reported_summons": 0,
                "reported_item_stacks": 2, "reported_items_total": 5,
            },
            details["reported_battle_result"],
        )

    def test_the_counts_carry_no_identity(self) -> None:
        """Counts, never contents: an item or Companion id is still not logged."""
        rendered = json.dumps(safe_form_diagnostics(self.body(buddies=[267], items={"9": 3})))
        for leaked in ("267", '"9"'):
            self.assertNotIn(leaked, rendered)


class RefusedWriteShapeTest(unittest.TestCase):
    """A refusal must say which half of the write was wrong, and how."""

    def test_a_nested_companion_object_is_reported_as_an_object(self) -> None:
        body = urlencode({
            "chrdata": json.dumps(ROSTER),
            # The stored projection's shape, not the flat list a write takes.
            "buddyInfo": json.dumps({"list": COMPANIONS, "record": []}),
            "lastUpdate": "1",
        }).encode()
        shapes = refused_write_shapes(body)
        self.assertEqual({"type": "object", "keys": ["list", "record"]}, shapes["buddyInfo"])
        self.assertEqual("list", shapes["chrdata"]["type"])
        self.assertEqual(2, shapes["chrdata"]["entries"])

    def test_a_wrong_type_shows_up_against_the_key_that_holds_it(self) -> None:
        rows = [dict(COMPANIONS[0]), dict(COMPANIONS[0], iid=3, lv="1")]
        shapes = refused_write_shapes(urlencode({
            "buddyInfo": json.dumps(rows), "lastUpdate": "1",
        }).encode())
        self.assertEqual(["int", "str"], shapes["buddyInfo"]["entry_types"]["lv"])
        # Both rows agree on their keys, so the type is the only difference.
        self.assertEqual(1, shapes["buddyInfo"]["key_sets"])

    def test_a_missing_key_shows_up_as_a_second_key_set(self) -> None:
        rows = [dict(COMPANIONS[0]), {k: v for k, v in COMPANIONS[0].items() if k != "chrID"}]
        rows[1]["iid"] = 3
        shapes = refused_write_shapes(urlencode({
            "buddyInfo": json.dumps(rows), "lastUpdate": "1",
        }).encode())
        self.assertEqual(2, shapes["buddyInfo"]["key_sets"])

    def test_undecodable_json_is_named_rather_than_dropped(self) -> None:
        shapes = refused_write_shapes(b"chrdata=%7Bnot-json&lastUpdate=1")
        self.assertEqual({"type": "invalid_json"}, shapes["chrdata"])

    def test_a_body_that_is_not_a_form_reports_nothing(self) -> None:
        self.assertEqual({}, refused_write_shapes(b"\xffbinary"))


class RefusedWriteEventTest(unittest.TestCase):
    """The shape has to reach the log the operator actually reads."""

    def test_a_refused_write_records_its_shape(self) -> None:
        profile = load_profile(Path(__file__).resolve().parents[1] / "profiles" / "legacy-client-bootstrap.json")
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            state = BootstrapState(Path(directory) / "state.json")
            state.create_account("token", "account", {"coins": 0, "chrdata": []})
            server = BootstrapServer(("127.0.0.1", 0), profile, state, event_log=log)
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                connection = HTTPConnection(*server.server_address)
                connection.request("POST", "/gd/userdata?otk=token&requestID=refused", body=urlencode({
                    "chrdata": json.dumps(ROSTER),
                    "buddyInfo": json.dumps({"list": COMPANIONS, "record": []}),
                    "lastUpdate": "1",
                }))
                response = connection.getresponse()
                payload = json.loads(response.read())
                connection.close()
            finally:
                server.shutdown(); thread.join(); server.server_close()
            events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        self.assertEqual((501, "unsupported_userdata_write"), (response.status, payload["error"]))
        refusal = next(e for e in events if e.get("error") == "unsupported_userdata_write")
        # The field list alone was the whole diagnostic before, and the
        # accepted equip write carries exactly this tuple.
        self.assertEqual(["chrdata", "buddyInfo", "lastUpdate"], refusal["request_fields"])
        self.assertEqual("object", refusal["request_shapes"]["buddyInfo"]["type"])
        self.assertEqual("list", refusal["request_shapes"]["chrdata"]["type"])


if __name__ == "__main__":
    unittest.main()
