import hashlib,json,tempfile,unittest
from pathlib import Path
from liminal_gate.event_catalog import (
    EventCatalog,
    EventCatalogError,
    EventStage,
    build_bundled_counter_descent_policy,
    load_event_catalog,
    merge_event_catalogs,
)
from tests.support import write_json
class EventCatalogTest(unittest.TestCase):
 def test_local_event_grant_matches_catalog(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; e=r/'e.json'; c.write_text(json.dumps({'characters':[{'character_id':3}]})); e.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'test','flag':'sp_ch_2000-1','chapter':2000,'section':1,'stamina':1,'coins':0,'clear_coins':0,'character_ids':[3]}]})); self.assertEqual((3,),load_event_catalog(e,c).stages[0].character_ids)

 def test_legacy_catalog_without_unlock_cadence_remains_loadable(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; e=r/'e.json'; c.write_text(json.dumps({'characters':[{'character_id':3}]})); e.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'test','flag':'sp_ch_2000','chapter':2000,'section':1,'stamina':1,'coins':0,'clear_coins':0,'character_ids':[3]}]})); self.assertIsNone(load_event_catalog(e,c).stages[0].unlock_after_chapter)

 def test_invalid_unlock_cadence_is_refused(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; e=r/'e.json'; c.write_text(json.dumps({'characters':[{'character_id':3}]})); e.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'test','flag':'sp_ch_2000','chapter':2000,'section':1,'stamina':1,'coins':0,'clear_coins':0,'unlock_after_chapter':True,'character_ids':[3]}]}))
   with self.assertRaisesRegex(EventCatalogError, "unlock_after_chapter"):
    load_event_catalog(e,c)

 def test_invalid_summon_ceiling_is_refused(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; e=r/'e.json'; c.write_text(json.dumps({'characters':[]})); e.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'test','flag':'sp_ch_4100','chapter':4100,'section':1,'stamina':10,'coins':0,'clear_coins':0,'character_ids':[],'summon_ids':[4,4]}]}))
   with self.assertRaisesRegex(EventCatalogError, "Summon IDs"):
    load_event_catalog(e,c)

 def test_folded_selector_identity_is_loaded_and_deduplicated(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; e=r/'e.json'; c.write_text(json.dumps({'characters':[]})); e.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'folded','flag':'sp_ch_2000','chapter':2000,'section':section,'stamina':15,'coins':0,'clear_coins':0,'character_ids':[],'selector_id':'2000'} for section in (1,2)]}))
   loaded=load_event_catalog(e,c)
   self.assertEqual(['2000'],loaded.client_lists(None)['specialQuestList'])

 def test_unrelated_selector_identity_is_refused(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; e=r/'e.json'; c.write_text(json.dumps({'characters':[]})); e.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'bad','flag':'sp_ch_2000','chapter':2000,'section':1,'stamina':15,'coins':0,'clear_coins':0,'character_ids':[],'selector_id':'2001'}]}))
   with self.assertRaisesRegex(EventCatalogError, 'selector_id'):
    load_event_catalog(e,c)

 def test_folded_selector_with_section_only_flag_is_refused(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; e=r/'e.json'; c.write_text(json.dumps({'characters':[]})); e.write_text(json.dumps({'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'bad-fold','flag':'sp_ch_2000-1','chapter':2000,'section':1,'stamina':15,'coins':0,'clear_coins':0,'character_ids':[],'selector_id':'2000'}]}))
   with self.assertRaisesRegex(EventCatalogError, 'chapter event flag'):
    load_event_catalog(e,c)


class EventFlagRuleTest(unittest.TestCase):
    """A stage's flag must be one the client will actually ask about."""

    def catalog(self, flag: str, chapter: int = 2000, section: int = 1):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            characters = root / "characters.json"
            write_json(characters, {"characters": [{"character_id": 3}]})
            events = root / "events.json"
            write_json(events, {
                "schema_version": 1, "provenance": "user-supplied",
                "character_catalog_sha256": hashlib.sha256(characters.read_bytes()).hexdigest(),
                "stages": [{"event_id": "test", "flag": flag, "chapter": chapter, "section": section,
                            "stamina": 1, "coins": 0, "clear_coins": 0, "character_ids": [3]}],
            })
            return load_event_catalog(events, characters)

    def test_accepts_the_chapter_and_stage_keys_the_client_builds(self) -> None:
        # `CheckQuestFlag` concatenates "sp_ch_" with the chapter or with
        # chapter-section; the chapter key is the fallback for every stage.
        for flag in ("sp_ch_2000", "sp_ch_2000-1"):
            with self.subTest(flag=flag):
                self.assertEqual(flag, self.catalog(flag).stages[0].flag)

    def test_rejects_a_flag_that_cannot_gate_its_own_stage(self) -> None:
        for flag in ("sp_test", "sp_ch_2001-1", "sp_ch_2000-2", "SP_CH_2000", "sp_ch_2000-01"):
            with self.subTest(flag=flag):
                with self.assertRaises(EventCatalogError) as refused:
                    self.catalog(flag)
                self.assertIn("cannot gate stage", str(refused.exception))

    def test_the_error_names_both_keys_the_client_would_read(self) -> None:
        with self.assertRaises(EventCatalogError) as refused:
            self.catalog("sp_wrong", chapter=7010, section=2)
        message = str(refused.exception)
        self.assertIn("sp_ch_7010", message)
        self.assertIn("sp_ch_7010-2", message)


class BundledCounterDescentPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.catalog = build_bundled_counter_descent_policy()

    @staticmethod
    def progress_at(chapter: int) -> int:
        return 0x01000000 | (chapter << 6) | 1

    def test_declares_all_fourteen_non_collaboration_families(self) -> None:
        self.assertEqual(
            [
                (chapter, section)
                for chapters, section_count in (
                    (range(8000, 8008), 5),
                    (range(8012, 8018), 3),
                )
                for chapter in chapters
                for section in range(1, section_count + 1)
            ],
            sorted(self.catalog.by_identity()),
        )
        for chapter in range(8000, 8008):
            self.assertEqual(
                [5, 10, 15, 15, 15],
                [
                    self.catalog.by_identity()[(chapter, section)].stamina
                    for section in range(1, 6)
                ],
            )
            self.assertTrue(
                all(
                    self.catalog.by_identity()[(chapter, section)].zero_base
                    for section in range(1, 6)
                )
            )
        for chapter in range(8012, 8018):
            self.assertEqual(
                [5, 10, 15],
                [
                    self.catalog.by_identity()[(chapter, section)].stamina
                    for section in range(1, 4)
                ],
            )
            self.assertTrue(
                all(
                    self.catalog.by_identity()[(chapter, section)].zero_base
                    for section in range(1, 4)
                )
            )
        self.assertFalse(
            {
                (chapter, section)
                for chapter in (*range(8008, 8012), 8018)
                for section in range(1, 4)
            }
            & set(self.catalog.by_identity())
        )

    def test_projects_one_folded_row_per_unlocked_family(self) -> None:
        self.assertEqual(
            [],
            self.catalog.client_lists(self.progress_at(5))[
                "descentHuntingList"
            ],
        )
        lists = self.catalog.client_lists(self.progress_at(7))
        self.assertEqual(["8000-1", "8001-1"], lists["descentHuntingList"])
        self.assertEqual([], lists["specialQuestList"])
        self.assertEqual([], lists["towerQuestList"])
        self.assertEqual([], lists["eidolonQuestList"])
        self.assertEqual(
            ["sp_ch_8000", "sp_ch_8001"],
            sorted(self.catalog.flags(self.progress_at(7))),
        )
        self.assertEqual(
            [
                *(f"{chapter}-1" for chapter in range(8000, 8008)),
                *(f"{chapter}-1" for chapter in range(8012, 8018)),
            ],
            self.catalog.client_lists(self.progress_at(19))[
                "descentHuntingList"
            ],
        )

    def test_bundled_zero_base_rows_own_generated_duplicates(self) -> None:
        generated = EventCatalog((
            EventStage("generated", "sp_ch_8000", 8000, 1, 99, 0, 0, ()),
            EventStage("other", "sp_ch_2000", 2000, 1, 15, 0, 0, ()),
        ))
        merged = merge_event_catalogs(self.catalog, generated)
        self.assertIsNotNone(merged)
        self.assertEqual(5, merged.by_identity()[(8000, 1)].stamina)
        self.assertTrue(merged.by_identity()[(8000, 1)].zero_base)
        self.assertIn((2000, 1), merged.by_identity())
