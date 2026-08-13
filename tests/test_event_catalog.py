import hashlib,json,tempfile,unittest
from pathlib import Path
from liminal_gate.event_catalog import (
    EventCatalog,
    EventCatalogError,
    EventStage,
    build_bundled_collab_special_policy,
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

 def test_entry_item_pair_is_loaded_and_incomplete_pairs_are_refused(self):
  with tempfile.TemporaryDirectory() as d:
   r=Path(d); c=r/'c.json'; c.write_text(json.dumps({'characters':[]}))
   base={'schema_version':1,'provenance':'user-supplied','character_catalog_sha256':hashlib.sha256(c.read_bytes()).hexdigest(),'stages':[{'event_id':'lucia','flag':'sp_ch_2006','chapter':2006,'section':2,'stamina':35,'coins':0,'clear_coins':0,'character_ids':[],'entry_item_id':110,'entry_item_count':1}]}
   e=r/'e.json'; e.write_text(json.dumps(base))
   stage=load_event_catalog(e,c).stages[0]
   self.assertEqual((110,1),(stage.entry_item_id,stage.entry_item_count))
   base['stages'][0].pop('entry_item_count')
   e.write_text(json.dumps(base))
   with self.assertRaisesRegex(EventCatalogError,'entry item'):
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
   self.assertEqual(['2000'],loaded.client_lists(None)['descentQuestList'])

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
                    (range(8000, 8008), 4),
                    (range(8012, 8018), 3),
                )
                for chapter in chapters
                for section in range(1, section_count + 1)
            ],
            sorted(self.catalog.by_identity()),
        )
        for chapter in range(8000, 8008):
            self.assertEqual(
                [5, 10, 15, 15],
                [
                    self.catalog.by_identity()[(chapter, section)].stamina
                    for section in range(1, 5)
                ],
            )
            # The fifth BattleData section is deliberately absent: the retired
            # service shipped four banners per family and the client has no
            # name for a fifth.
            self.assertNotIn((chapter, 5), self.catalog.by_identity())
            self.assertTrue(
                all(
                    self.catalog.by_identity()[(chapter, section)].projected_rewards
                    for section in range(1, 5)
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
                    self.catalog.by_identity()[(chapter, section)].projected_rewards
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
        self.assertEqual(["8000", "8001"], lists["descentHuntingList"])
        self.assertEqual([], lists["specialQuestList"])
        self.assertEqual([], lists["towerQuestList"])
        self.assertEqual([], lists["eidolonQuestList"])
        # Per section and never by chapter: `CheckQuestFlag` retries an unset
        # section key as its chapter, so a chapter key would answer for tiers
        # that do not exist.
        self.assertEqual(
            [
                *(f"sp_ch_8000-{section}" for section in range(1, 5)),
                *(f"sp_ch_8001-{section}" for section in range(1, 5)),
            ],
            sorted(self.catalog.flags(self.progress_at(7))),
        )
        self.assertEqual(
            [
                *(str(chapter) for chapter in range(8000, 8008)),
                *(str(chapter) for chapter in range(8012, 8018)),
            ],
            self.catalog.client_lists(self.progress_at(19))[
                "descentHuntingList"
            ],
        )

    def test_a_three_tier_family_flags_only_the_sections_it_has(self) -> None:
        """The client expands every 8000-series card to five rows regardless.

        `GetSectionCount` reads the hard-coded
        `ChapterInterface.NumOfCounterDescentQuestSections`, so a Chapter 8012
        card offers `8012-4` and `8012-5`, which no section backs and
        `start_quest` would refuse. Withholding the chapter key is what removes
        those two rows: `CheckQuestFlag` retries an unset section key as its
        chapter, so `sp_ch_8012` would answer true for both of them.
        """
        flags = self.catalog.flags(self.progress_at(19))
        self.assertEqual(
            ["sp_ch_8012-1", "sp_ch_8012-2", "sp_ch_8012-3"],
            sorted(name for name in flags if name.startswith("sp_ch_8012")),
        )
        self.assertEqual(
            [f"sp_ch_8007-{section}" for section in range(1, 5)],
            sorted(name for name in flags if name.startswith("sp_ch_8007")),
        )

    def test_bundled_projected_reward_rows_own_generated_duplicates(self) -> None:
        generated = EventCatalog((
            EventStage("generated", "sp_ch_8000", 8000, 1, 99, 0, 0, ()),
            EventStage("other", "sp_ch_2000", 2000, 1, 15, 0, 0, ()),
        ))
        merged = merge_event_catalogs(self.catalog, generated)
        self.assertIsNotNone(merged)
        self.assertEqual(5, merged.by_identity()[(8000, 1)].stamina)
        self.assertTrue(merged.by_identity()[(8000, 1)].projected_rewards)
        self.assertIn((2000, 1), merged.by_identity())


class BundledCollabSpecialPolicyTest(unittest.TestCase):
    """Battle Champs and 8-Bit Rush: the same range, a different menu.

    Both sit in the Counter Descent chapter range, so the client starts and
    settles them exactly as it does Strikes Back. The shutdown menu record
    lists them under Arena -> Special Quests instead, with no Strikes Back
    entry, which is the only thing that differs.
    """

    def setUp(self) -> None:
        self.catalog = build_bundled_collab_special_policy()

    @staticmethod
    def progress_at(chapter: int) -> int:
        return 0x01000000 | (chapter << 6) | 1

    def test_declares_the_recovered_sections_and_nothing_else(self) -> None:
        self.assertEqual(
            [
                (8008, 1), (8008, 2), (8009, 1), (8009, 2),
                (8010, 1), (8010, 2), (8011, 1), (8011, 2),
                (8018, 1),
            ],
            sorted(self.catalog.by_identity()),
        )
        for chapter in range(8008, 8012):
            self.assertEqual(
                [5, 15],
                [
                    self.catalog.by_identity()[(chapter, section)].stamina
                    for section in (1, 2)
                ],
            )
            # A third tier is what a `GetSectionCount` fold would offer and
            # what BattleData does not have.
            self.assertNotIn((chapter, 3), self.catalog.by_identity())
        self.assertEqual(15, self.catalog.by_identity()[(8018, 1)].stamina)
        self.assertTrue(
            all(stage.projected_rewards for stage in self.catalog.stages)
        )
        self.assertTrue(all(stage.selector == "special" for stage in self.catalog.stages))

    def test_battle_champs_folds_and_eight_bit_rush_does_not(self) -> None:
        """Four cards, not eight rows, and the fifth family is a lone section.

        Folding is what holds `specialQuestList` at the 30 rows the client can
        draw. 8018 has one section and no folded banner, so it is advertised as
        the section row its own artwork was drawn for.
        """
        lists = self.catalog.client_lists(self.progress_at(24))
        self.assertEqual(
            ["8008", "8009", "8010", "8011", "8018-1"],
            lists["specialQuestList"],
        )
        self.assertEqual([], lists["descentHuntingList"])
        self.assertEqual([], lists["descentQuestList"])

    def test_a_folded_card_flags_only_the_two_tiers_it_has(self) -> None:
        """The same rule the three-tier Strikes Back families rely on.

        `GetSectionCount` returns the hard-coded five for every chapter in this
        range, so a card offers `8008-3` through `8008-5` as well. None is
        backed by a section, and a chapter flag would answer `CheckQuestFlag`
        true for all three, so the flags stay per section.
        """
        self.assertEqual(
            ["sp_ch_8008-1", "sp_ch_8008-2"],
            sorted(self.catalog.flags(self.progress_at(20))),
        )

    def test_the_release_cadence_opens_one_family_at_a_time(self) -> None:
        self.assertEqual(
            [], self.catalog.client_lists(self.progress_at(19))["specialQuestList"],
        )
        self.assertEqual(
            ["8008"], self.catalog.client_lists(self.progress_at(20))["specialQuestList"],
        )

    def test_the_recovered_drop_manifests_bound_a_reported_claim(self) -> None:
        """The one thing these five carry that the rest of the range does not.

        Every Strikes Back section declares an empty `dropBuddies`; these are
        the only members of 8000--8018 that name a Companion. Tier I declares
        none, and declaring none is not the same as declaring nothing.
        """
        stages = self.catalog.by_identity()
        self.assertEqual((), stages[(8008, 1)].companion_manifest)
        self.assertFalse(stages[(8008, 1)].companions_within_manifest([367]))
        self.assertTrue(stages[(8008, 1)].companions_within_manifest([]))
        self.assertEqual(((367, 1), (369, 1)), stages[(8008, 2)].companion_manifest)
        self.assertTrue(stages[(8008, 2)].companions_within_manifest([367, 369]))
        # Its own packed cap is one apiece, so a second copy is over it.
        self.assertFalse(stages[(8008, 2)].companions_within_manifest([367, 367]))
        # A Companion another family drops is still not this one's.
        self.assertFalse(stages[(8008, 2)].companions_within_manifest([368]))
        self.assertEqual(
            ((422, 1), (423, 1), (424, 1)), stages[(8018, 1)].companion_manifest,
        )

    def test_a_stage_with_no_recovered_manifest_stays_unconstrained(self) -> None:
        """A gap in what was read is not evidence that a stage drops nothing."""
        unread = EventStage("archive", "sp_ch_2003-1", 2003, 1, 15, 0, 0, ())
        self.assertIsNone(unread.companion_manifest)
        self.assertTrue(unread.companions_within_manifest([1, 2, 3]))


class DescentQuestMenuTest(unittest.TestCase):
    """Arena -> Descent Quests is `UISpecialSelect` mode 3, not mode 0 or 8."""

    def catalog(self) -> EventCatalog:
        return EventCatalog((
            EventStage("bahamut", "sp_ch_2000", 2000, 1, 15, 0, 0, (), selector="descent_quest", selector_id="2000"),
            EventStage("dragon_king", "sp_ch_2010-1", 2010, 1, 15, 0, 0, (), selector="descent_quest"),
            EventStage("archive", "sp_ch_2003-1", 2003, 1, 15, 0, 0, ()),
        ))

    def test_descent_rows_leave_the_special_list_for_their_own(self) -> None:
        lists = self.catalog().client_lists(None)
        self.assertEqual(["2000", "2010-1"], lists["descentQuestList"])
        self.assertEqual(["2003-1"], lists["specialQuestList"])
        # Strikes Back is a different menu again, and stays empty here.
        self.assertEqual([], lists["descentHuntingList"])

    def test_the_move_does_not_disturb_the_flags_a_row_carries(self) -> None:
        """The list a row is on picks the menu. It picks nothing else."""
        self.assertEqual(
            ["sp_ch_2000", "sp_ch_2003-1", "sp_ch_2010-1"],
            sorted(self.catalog().flags(None)),
        )


class RaidRangeQuestParamsTest(unittest.TestCase):
    """Chapters 9000--9009 are the client's Raid quest range, and it gates them.

    `UISpecialSelect2.StartSpecial` asks `ChapterInterface.IsRaidQuest` before
    anything else and refuses on `RaidStatus.Lock`, which is what an absent
    `eventQuestParams` decodes to. Tower of Temptation is served from
    9000--9003, so every one of its cards needs an entry here or it dead-ends
    inside the client with no request on the wire.
    """

    @staticmethod
    def progress_at(chapter: int) -> int:
        return ((chapter + 1) << 6) | 1

    def catalog(self, *chapters: int) -> EventCatalog:
        return EventCatalog(tuple(
            EventStage(
                "test", f"sp_ch_{chapter}", chapter, 1, 15, 0, 0, (),
                selector="tower", unlock_after_chapter=3,
            )
            for chapter in chapters
        ))

    def test_every_advertised_raid_range_stage_is_answered(self) -> None:
        params = self.catalog(9000, 9003).raid_quest_params(self.progress_at(19))
        self.assertEqual({"9000-1", "9003-1"}, set(params))

    def test_status_is_one_the_start_path_admits(self) -> None:
        # `Lock` (1) and `Completed` (4) are the two the client refuses.
        for entry in self.catalog(9000).raid_quest_params(self.progress_at(19)).values():
            self.assertNotIn(entry["status"], (1, 4))

    def test_remaining_hp_is_a_double_the_client_can_read(self) -> None:
        # `GetRaidQuestRemainHp` reads it with LitJson's `double` accessor,
        # which throws on `JsonType.Int` rather than converting -- the same
        # trap `jobLevels` and `questClearDate` carry.
        for entry in self.catalog(9000).raid_quest_params(self.progress_at(19)).values():
            self.assertIs(float, type(entry["remainHp"]))

    def test_no_overkill_end_date_is_declared(self) -> None:
        # Its presence is what makes `UpdateItems` draw the raid countdown and
        # HP bar. This server has no recovered schedule to put there.
        for entry in self.catalog(9000).raid_quest_params(self.progress_at(19)).values():
            self.assertEqual({"status", "remainHp"}, set(entry))

    def test_chapters_outside_the_raid_range_are_left_alone(self) -> None:
        # 8999 is the last Counter Descent chapter and 9010 the first Tower of
        # Temptation one; neither takes the raid path.
        catalog = self.catalog(8999, 9010, 9100)
        self.assertEqual({}, catalog.raid_quest_params(self.progress_at(19)))

    def test_a_stage_the_account_cannot_see_is_not_answered(self) -> None:
        self.assertEqual({}, self.catalog(9000).raid_quest_params(self.progress_at(1)))
