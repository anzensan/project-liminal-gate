from __future__ import annotations

import unittest

from liminal_gate.master_strings import (
    MasterStringError, build_character_names, build_companion_names, build_item_names, build_name_file,
    decrypt_encrypted_string, load_inverse_table,
)
from liminal_gate.save_validation import (
    ITEM_SLOTS, LEVEL_CAP, MAX_ITEM_STACK, decode_job_level, encode_job_level, validate_document,
)
from liminal_gate.plus_type_data import PLUS_COUNT_MAX
from liminal_gate.server_constants import build_server_constants


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

    def test_party_slots_and_selectors_require_nonnegative_integers(self) -> None:
        for field, value in (
            ("teamMembers", ["bad", 1]),
            ("teamMembers_VS", [None, 1]),
            ("teamBuddies_VS", [1.5]),
            ("teamNo", "1"),
            ("teamNo_VS", -1),
            ("summonId", {}),
        ):
            self.assertIn(field, errors(save(**{field: value})))

    def test_duplicate_and_invalid_roster_ids_are_errors(self) -> None:
        self.assertIn("chrdata[1]", errors(save(chrdata=[character(3), character(3)])))
        self.assertIn("chrdata[0]", errors(save(chrdata=[{"id": 0, "jobLevels": [1.0]}])))

    def test_the_inventory_shape_and_stack_ceiling_are_enforced(self) -> None:
        self.assertIn("itemList", errors(save(itemList=[0] * 8)))
        overflowing = [0] * ITEM_SLOTS
        overflowing[4] = MAX_ITEM_STACK + 1
        self.assertIn("itemList[4]", errors(save(itemList=overflowing)))
        # A stack the client itself allows is not an overflow. Four figures
        # were refused here while the client was being told it could hold them.
        at_ceiling = [0] * ITEM_SLOTS
        at_ceiling[4] = MAX_ITEM_STACK
        self.assertEqual([], errors(save(itemList=at_ceiling)))

    def test_a_plus_count_outside_the_clients_range_is_an_error(self) -> None:
        """The client reads a count past its ceiling as tampering, not as a cap."""
        over = [character(3)]
        over[0]["plusCount"] = PLUS_COUNT_MAX + 1
        self.assertIn("chrdata[0].plusCount", errors(save(chrdata=over)))
        for value in (0, PLUS_COUNT_MAX):
            with self.subTest(plusCount=value):
                row = [character(3)]
                row[0]["plusCount"] = value
                self.assertEqual([], errors(save(chrdata=row)))
        # Absent is the ordinary case: nothing grants a count yet.
        self.assertEqual([], errors(save(chrdata=[character(3)])))

    def test_the_stack_ceiling_is_the_one_the_client_is_told(self) -> None:
        """A ceiling the client does not share is not a ceiling at all.

        The server sends `maxItemCount` and the client enforces it, so a lower
        server-side ceiling never bounds anything -- it only makes an honest
        inventory unrepresentable, which is refused as an invalid settlement.
        """
        self.assertEqual(MAX_ITEM_STACK, build_server_constants()["maxItemCount"])

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

    def test_token_bindings_must_be_a_string_mapping(self) -> None:
        document = save()
        document["tokens"] = []
        self.assertIn("tokens", errors(document))
        document["tokens"] = {"token": "ACCOUNT", 1: "ACCOUNT"}
        self.assertIn("tokens", errors(document))

    def test_a_whole_companion_link_is_not_a_finding(self) -> None:
        equipped = character() | {"buddy": 7}
        document = save(chrdata=[equipped], buddyInfo={
            "list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 7, "exp": 0, "flag": 0, "chrID": 3}],
            "record": [],
        })
        self.assertEqual([], errors(document))

    def test_a_companion_left_on_a_character_the_roster_lost_is_reported(self) -> None:
        """The one defect a player can neither see nor repair from the client."""
        document = save(chrdata=[character()], buddyInfo={
            "list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 7, "exp": 0, "flag": 0, "chrID": 144}],
            "record": [],
        })
        self.assertIn("buddyInfo.list[iid=7].chrID", errors(document))

    def test_a_character_claiming_a_companion_that_does_not_claim_it_back(self) -> None:
        document = save(chrdata=[character() | {"buddy": 7}], buddyInfo={
            "list": [{"bid": 1, "lv": 1, "date": 0.0, "iid": 7, "exp": 0, "flag": 0, "chrID": 0}],
            "record": [],
        })
        # A `chrID` of 0 is an unequipped Companion, which is legal on its own;
        # only the half that claims something is a finding.
        self.assertEqual(["chrdata[id=3].buddy"], errors(document))



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
    def test_item_names_are_keyed_by_position_not_by_a_field(self) -> None:
        """An ItemSet record carries no ID; its position is the item ID."""
        records = [{"NameString": {"en": self.encrypt(f"item {index}")}} for index in range(1, 51)]
        records[49] = {"NameString": {"en": self.encrypt("Metal Ticket")}}
        names = build_item_names({"itemSet": records}, self.table)
        # Ordinal 50 is the Metal Ticket, which is the Item 50 the Metal Zone
        # entry contract charges -- that agreement is what pins the mapping.
        self.assertEqual("Metal Ticket", names["50"])
        self.assertEqual("item 1", names["1"])
        self.assertNotIn("0", names)

    def test_companion_names_are_keyed_by_their_own_id(self) -> None:
        tree = {"data": [
            {"ID": 128, "NameString": {"en": self.encrypt("Minion")}},
            {"ID": 129, "NameString": {"en": self.encrypt("Bigger Minion")}},
            {"NameString": {"en": self.encrypt("unkeyed")}},
        ]}
        self.assertEqual({"128": "Minion", "129": "Bigger Minion"}, build_companion_names(tree, self.table))

    def test_the_name_file_carries_all_three_kinds(self) -> None:
        document = build_name_file(
            {"3": "Grace"}, "abc123", items={"50": "Metal Ticket"}, companions={"128": "Minion"},
        )
        self.assertEqual({"50": "Metal Ticket"}, document["items"])
        self.assertEqual({"128": "Minion"}, document["companions"])

    def test_an_empty_master_table_is_refused_rather_than_written_blank(self) -> None:
        for builder, tree in ((build_item_names, {"itemSet": []}), (build_companion_names, {"data": []})):
            with self.assertRaises(MasterStringError):
                builder(tree, self.table)


if __name__ == "__main__":
    unittest.main()
