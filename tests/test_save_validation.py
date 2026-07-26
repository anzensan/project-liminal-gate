from __future__ import annotations

import unittest

from liminal_gate.master_strings import (
    MasterStringError, build_character_names, build_name_file, decrypt_encrypted_string, load_inverse_table,
)
from liminal_gate.save_validation import (
    ITEM_SLOTS, LEVEL_CAP, decode_job_level, encode_job_level, validate_document,
)


def character(character_id: int = 3, packed: float = 3930566726.0) -> dict:
    return {
        "id": character_id, "buddy": 0, "date": 0.0, "flags": 1, "jobID": 0,
        "jobLevels": [packed, 0.0, 0.0], "jobSlots": [0.0, 0.0, 0.0], "skillBoost": 1,
    }


def save(**userdata) -> dict:
    base = {
        "chrdata": [character()],
        "itemList": [0] * ITEM_SLOTS,
        "teamMembers": [3, 0, 0, 0, 0, 0],
        "coins": 801,
        "lastupdate": 1.0,
    }
    base.update(userdata)
    return {
        "accounts": {"ACCOUNT": {"userdata": base, "tutorial_phase": "free_roam"}},
        "tokens": {"token": "ACCOUNT"},
        "active_account_id": "ACCOUNT",
    }


def errors(document: dict) -> list[str]:
    return [finding.field for finding in validate_document(document) if finding.severity == "error"]


class PackedJobLevelTest(unittest.TestCase):
    """The level is the low twelve bits; everything above it is progression."""

    def test_decodes_a_real_packed_value(self) -> None:
        self.assertEqual((70, 959611), decode_job_level(3930566726.0))

    def test_round_trips_through_the_encoder(self) -> None:
        self.assertEqual(3930566726.0, encode_job_level(70, 959611))
        self.assertIsInstance(encode_job_level(70, 959611), float)

    def test_refuses_a_level_that_would_overflow_into_progression(self) -> None:
        with self.assertRaises(ValueError):
            encode_job_level(4096, 0)

    def test_a_plain_level_written_into_the_packed_field_is_caught(self) -> None:
        """Writing 90 keeps the level but destroys the progression above it."""
        self.assertEqual((90, 0), decode_job_level(90))
        # A plain 90 is itself a legal packed value -- level 90, no progression
        # -- so writing it is silent data loss rather than a detectable error.
        self.assertEqual([], errors(save(chrdata=[character(packed=90.0)])))
        # What the cap does catch is a number typed in as if it were a level but
        # large enough to land above it: 100000 decodes to level 1696.
        self.assertEqual(1696, decode_job_level(100000)[0])
        self.assertGreater(1696, LEVEL_CAP)
        self.assertIn("chrdata[0].jobLevels[0]", errors(save(chrdata=[character(packed=100000.0)])))


class SaveValidationTest(unittest.TestCase):
    def test_a_well_formed_save_reports_nothing(self) -> None:
        self.assertEqual([], validate_document(save()))

    def test_an_integer_where_the_client_reads_a_decimal_is_an_error(self) -> None:
        """LitJson's double accessor fails on a whole number, mid-response."""
        self.assertIn("chrdata[0].jobLevels[0]", errors(save(chrdata=[character(packed=3930566726)])))
        self.assertIn("lastupdate", errors(save(lastupdate=1)))
        broken = character()
        broken["date"] = 0
        self.assertIn("chrdata[0].date", errors(save(chrdata=[broken])))

    def test_a_party_naming_an_unowned_character_is_an_error(self) -> None:
        # Exactly the server's own rule: a party that is not a subset of the
        # roster makes every later party save fail.
        self.assertIn("teamMembers", errors(save(teamMembers=[3, 64, 0, 0, 0, 0])))
        self.assertEqual([], errors(save(teamMembers=[3, 0, 0, 0, 0, 0])))

    def test_duplicate_and_invalid_roster_ids_are_errors(self) -> None:
        self.assertIn("chrdata[1]", errors(save(chrdata=[character(3), character(3)])))
        self.assertIn("chrdata[0]", errors(save(chrdata=[{"id": 0, "jobLevels": [1.0]}])))

    def test_the_inventory_shape_and_stack_ceiling_are_enforced(self) -> None:
        self.assertIn("itemList", errors(save(itemList=[0] * 8)))
        overflowing = [0] * ITEM_SLOTS
        overflowing[4] = 1000
        self.assertIn("itemList[4]", errors(save(itemList=overflowing)))

    def test_a_wallet_that_disagrees_with_its_projection_is_an_error(self) -> None:
        disagreeing = save(coins=801)
        disagreeing["accounts"]["ACCOUNT"]["userdata"]["valuables"] = {"coins": 5}
        self.assertIn("valuables.coins", errors(disagreeing))
        agreeing = save(coins=801)
        agreeing["accounts"]["ACCOUNT"]["userdata"]["valuables"] = {"coins": 801}
        self.assertEqual([], errors(agreeing))

    def test_a_reused_companion_inventory_id_is_an_error(self) -> None:
        document = save(
            buddyInfo={"list": [{"bid": 128, "lv": 1, "iid": 1}, {"bid": 129, "lv": 1, "iid": 1}], "record": []},
            nextCompanionInventoryId=1,
        )
        found = errors(document)
        self.assertIn("buddyInfo.list[1]", found)
        self.assertIn("nextCompanionInventoryId", found)

    def test_a_stale_replay_cache_warns_rather_than_failing(self) -> None:
        document = save()
        document["accounts"]["ACCOUNT"]["tutorial_requests"] = {"key": {"payload": {}}}
        findings = validate_document(document)
        self.assertEqual(["warning"], [finding.severity for finding in findings])
        self.assertEqual([], errors(document))

    def test_a_token_pointing_at_no_account_is_an_error(self) -> None:
        document = save()
        document["tokens"]["stray"] = "MISSING"
        self.assertIn("tokens.stray", errors(document))



class MasterStringTest(unittest.TestCase):
    """Names are decoded from the tester's own metadata, never embedded."""

    def setUp(self) -> None:
        # A stand-in substitution: the real one is verified by digest and read
        # from the user's APK, so tests use an invertible table of their own.
        self.table = bytes((index * 7 + 3) % 256 for index in range(256))
        while len(set(self.table)) != 256:  # pragma: no cover - fixed by construction
            raise AssertionError("the test table must be a bijection")
        self.forward = {value: index for index, value in enumerate(self.table)}

    def encrypt(self, text: str) -> dict:
        return {"data": [self.forward[byte] for byte in reversed(text.encode())]}

    def test_decrypts_a_round_tripped_string(self) -> None:
        self.assertEqual("Grace", decrypt_encrypted_string(self.encrypt("Grace"), self.table))

    def test_rejects_a_table_that_is_not_the_reviewed_one(self) -> None:
        with self.assertRaisesRegex(MasterStringError, "substitution table"):
            load_inverse_table(b"\x00" * 0x700000)

    def test_rejects_a_malformed_encrypted_string(self) -> None:
        for value in ({}, {"data": "text"}, {"data": [300]}):
            with self.assertRaises(MasterStringError):
                decrypt_encrypted_string(value, self.table)

    def test_builds_names_from_the_infos_table_only(self) -> None:
        tree = {
            "infos": [
                {"ID": 3, "NameString": {"en": self.encrypt("Grace")}},
                {"ID": 25, "NameString": {"en": self.encrypt("A'misandra")}},
                {"ID": 9, "NameString": {"ja": self.encrypt("x")}},   # no English, skipped
                {"NameString": {"en": self.encrypt("no id")}},        # unkeyed, skipped
            ],
            # Repeats each character once per job, so it cannot key by ID.
            "data": [{"ID": 3, "NameString": {"en": self.encrypt("wrong")}}],
        }
        self.assertEqual({"3": "Grace", "25": "A'misandra"}, build_character_names(tree, self.table))

    def test_refuses_a_tree_with_no_decodable_names(self) -> None:
        with self.assertRaisesRegex(MasterStringError, "nonempty infos"):
            build_character_names({"infos": []}, self.table)
        with self.assertRaisesRegex(MasterStringError, "no character names"):
            build_character_names({"infos": [{"ID": 1}]}, self.table)

    def test_the_name_file_records_where_it_came_from(self) -> None:
        document = build_name_file({"3": "Grace"}, "abc123")
        self.assertEqual("decoded-from-user-apk", document["provenance"])
        self.assertEqual("abc123", document["source_sha256"])
        self.assertEqual({"3": "Grace"}, document["characters"])
        self.assertEqual({}, document["items"])

if __name__ == "__main__":
    unittest.main()
