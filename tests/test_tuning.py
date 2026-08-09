"""Cover the operator tuning document and the three things it reaches.

The document's whole point is that a partial one is legal -- an operator
turning off a species lock must not have to restate every Pact rate to do it --
so most of what is worth asserting here is that an omitted key keeps its
bundled value while a *misspelled* one is refused rather than silently doing
the same thing.
"""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

from liminal_gate.bootstrap_server import (
    ProfileError,
    _exp_credited_roster,
    build_server,
    load_launch_config,
    parse_args,
)
from liminal_gate.clear_state_catalog import CharacterProgression, ClearStateCatalog, JobProgression
from liminal_gate.companion_draw_catalog import build_bundled_companion_draw_policy
from liminal_gate.companion_strengthen_catalog import build_bundled_companion_strengthen_policy
from liminal_gate.hunting_catalog import build_bundled_hunting_policy
from liminal_gate.pact_draw_catalog import build_bundled_pact_policy
from liminal_gate.tuning import (
    DEFAULT_TUNING,
    DEFAULT_TUNING_DOCUMENT,
    DEFAULT_TUNING_TEMPLATE,
    CompanionTuning,
    ExpTuning,
    GateTuning,
    HuntingTuning,
    PactTuning,
    TuningError,
    load_tuning,
    write_default_tuning,
)


PUBLIC_ROOT = Path(__file__).resolve().parents[1]
_HEAD = 'schema_version = 1\nprovenance = "user-supplied"\n'


def _tuning(body: str = "", head: str = _HEAD):
    """Write a tuning document to a temporary file and load it."""
    directory = tempfile.TemporaryDirectory()
    path = Path(directory.name) / "tuning.toml"
    path.write_text(head + body, encoding="utf-8")
    return path, directory


class TuningDocumentTest(unittest.TestCase):
    def load(self, body: str = "", head: str = _HEAD):
        path, directory = _tuning(body, head)
        self.addCleanup(directory.cleanup)
        return load_tuning(path)

    def test_an_empty_document_is_exactly_the_bundled_defaults(self) -> None:
        self.assertEqual(DEFAULT_TUNING, self.load())

    def test_an_omitted_key_keeps_its_bundled_value(self) -> None:
        """The reason the document is partial-by-design, asserted directly."""
        tuning = self.load("[gates]\nspecies_limits = false\n")
        self.assertFalse(tuning.gates.species_limits)
        # Everything it did not mention is untouched, including the other gate.
        self.assertTrue(tuning.gates.class_bands)
        self.assertEqual(DEFAULT_TUNING.pact, tuning.pact)
        self.assertEqual(DEFAULT_TUNING.exp, tuning.exp)

    def test_a_misspelled_key_is_refused_rather_than_defaulted(self) -> None:
        """The failure the strict-parsing policy exists to prevent.

        A rate that silently keeps its default because the key was misspelled
        is indistinguishable, from the outside, from one the server ignored.
        """
        with self.assertRaises(TuningError) as caught:
            self.load("[pact]\nplus_chance_pcnt = 5\n")
        self.assertEqual("[pact] has an invalid schema", str(caught.exception))

    def test_an_unknown_section_is_refused(self) -> None:
        with self.assertRaises(TuningError) as caught:
            self.load("[drops]\nrate = 1\n")
        self.assertEqual("tuning document has an invalid schema", str(caught.exception))

    def test_truth_shares_must_name_every_class_and_total_one_million(self) -> None:
        with self.assertRaises(TuningError) as caught:
            self.load('[pact]\ntruth_class_share_ppm = { z = 500000, ss = 500000 }\n')
        self.assertEqual(
            "truth_class_share_ppm must name exactly these classes: z, ss, s, a_and_below",
            str(caught.exception),
        )
        with self.assertRaises(TuningError) as caught:
            self.load('[pact]\ntruth_class_share_ppm = { z = 1, ss = 1, s = 1, a_and_below = 1 }\n')
        self.assertEqual(
            "truth_class_share_ppm must total exactly 1000000 parts per million",
            str(caught.exception),
        )

    def test_a_plus_pact_range_must_ascend(self) -> None:
        with self.assertRaises(TuningError) as caught:
            self.load("[pact]\nplus_levels = [5, 2]\n")
        self.assertEqual("plus_levels must be two ascending positive integers", str(caught.exception))

    def test_the_plus_pact_can_be_turned_off_but_a_rate_cannot_exceed_certainty(self) -> None:
        self.assertEqual(0, self.load("[pact]\nplus_chance_percent = 0\n").pact.plus_chance_percent)
        with self.assertRaises(TuningError):
            self.load("[pact]\nplus_chance_percent = 101\n")

    def test_an_exp_multiplier_below_one_hundred_is_refused(self) -> None:
        """This credits EXP on top of the client's own and cannot take it away."""
        with self.assertRaises(TuningError) as caught:
            self.load("[exp]\nmultiplier_percent = 50\n")
        self.assertEqual(
            "multiplier_percent must be an integer from 100 through 10000", str(caught.exception),
        )

    def test_provenance_and_schema_version_are_required(self) -> None:
        with self.assertRaises(TuningError):
            self.load(head='schema_version = 1\nprovenance = "bundled"\n')
        with self.assertRaises(TuningError):
            self.load(head='schema_version = 2\nprovenance = "user-supplied"\n')


class TunedPactPolicyTest(unittest.TestCase):
    def test_the_bundled_policy_carries_the_tuned_costs_and_gains(self) -> None:
        tuning = replace(
            DEFAULT_TUNING.pact, coin_cost=1, energy_cost=2, fate_duplicate_luck=3,
            duplicate_gains={"z": (9, 9), "ss_s": (8, 8), "a_and_below": (7, 7)},
        )
        # Rarity 8 is the Z band, so its duplicate gain is the tuned Z entry.
        policy = build_bundled_pact_policy({character_id: 8 for character_id in range(1, 1300)}, tuning)
        self.assertEqual((1, 2, 3), (policy.coin_cost, policy.energy_cost, policy.fate_duplicate_luck))
        self.assertEqual({(9, 9)}, {(draw.duplicate_level_added, draw.duplicate_skill_boost) for draw in policy.truth_draws})

    def test_tuned_truth_shares_move_the_weights(self) -> None:
        """A class given the whole pool must outweigh one given almost none."""
        rarity = {1: 8, 2: 4}
        generous = build_bundled_pact_policy(
            rarity,
            replace(DEFAULT_TUNING.pact, truth_class_share_ppm={"z": 999_997, "ss": 1, "s": 1, "a_and_below": 1}),
        )
        weights = {draw.character_id: draw.weight for draw in generous.truth_draws}
        self.assertGreater(weights[1], weights[2])

    def test_the_uniform_fallback_ignores_tuning_because_it_has_no_classes(self) -> None:
        """Without a character catalog nothing can be classified, so no
        per-class table applies -- only the costs, which are not per class."""
        policy = build_bundled_pact_policy(None, replace(DEFAULT_TUNING.pact, coin_cost=42))
        self.assertEqual(42, policy.coin_cost)
        self.assertEqual({1}, {draw.weight for draw in policy.truth_draws})


class TunedCompanionPolicyTest(unittest.TestCase):
    def test_rare_shares_reweight_the_whole_pool(self) -> None:
        """The Rare pool is lopsided the opposite way from its rates, so the
        weighting is what keeps a displayed 49% from drawing like 1.8%."""
        loaded = replace(
            DEFAULT_TUNING.companion,
            rare_class_share_ppm={"z": 1, "ss": 1, "s": 1, "a": 1, "b": 999_996},
        )
        tuned = {draw.companion_id: draw.weight for draw in build_bundled_companion_draw_policy(loaded).rare_draws}
        bundled = {draw.companion_id: draw.weight for draw in build_bundled_companion_draw_policy().rare_draws}
        self.assertEqual(set(bundled), set(tuned))
        self.assertNotEqual(bundled, tuned)

    def test_the_normal_pool_stays_uniform_because_no_record_covers_it(self) -> None:
        loaded = replace(
            DEFAULT_TUNING.companion,
            rare_class_share_ppm={"z": 1, "ss": 1, "s": 1, "a": 1, "b": 999_996},
        )
        policy = build_bundled_companion_draw_policy(loaded)
        self.assertEqual({1}, {draw.weight for draw in policy.normal_draws})

    def test_strengthen_bonus_weights_are_carried(self) -> None:
        policy = build_bundled_companion_strengthen_policy(
            replace(DEFAULT_TUNING.companion, strengthen_bonus_weights=((0, 1), (100, 99))),
        )
        self.assertEqual(((0, 1), (100, 99)), policy.bonus_weights)

    def test_the_rare_shares_must_name_the_displayed_classes(self) -> None:
        """These are the displayed classes, not the Pact's bands."""
        path, directory = _tuning(
            '[companion]\nrare_class_share_ppm = { z = 500000, ss_s = 500000 }\n',
        )
        self.addCleanup(directory.cleanup)
        with self.assertRaises(TuningError) as caught:
            load_tuning(path)
        self.assertIn("z, ss, s, a, b", str(caught.exception))

    def test_a_repeated_bonus_percent_is_refused(self) -> None:
        path, directory = _tuning("[companion]\nstrengthen_bonus_weights = [[0, 5], [0, 9]]\n")
        self.addCleanup(directory.cleanup)
        with self.assertRaises(TuningError) as caught:
            load_tuning(path)
        self.assertEqual(
            "strengthen_bonus_weights must not repeat a bonus percent", str(caught.exception),
        )


class TunedHuntingPolicyTest(unittest.TestCase):
    def stages(self, tuning=None):
        return build_bundled_hunting_policy(tuning or DEFAULT_TUNING.hunting).stages

    def test_the_bundled_thresholds_are_unchanged(self) -> None:
        stages = self.stages()
        self.assertEqual([4, 10, 19], sorted({s.unlock_chapter for s in stages if s.family == "pudding_time"}))
        self.assertEqual(
            [4, 9, 13, 18, 22, 27, 31],
            sorted({s.unlock_chapter for s in stages if s.family == "metal_zone"}),
        )

    def test_availability_can_be_opened_early(self) -> None:
        """The retired rotations were never captured, so this schedule is ours."""
        tuning = replace(
            DEFAULT_TUNING.hunting, tier_unlock_chapters=(1, 1, 1), metal_unlock_chapters=(1,) * 7,
        )
        stages = self.stages(tuning)
        self.assertEqual(
            {2}, {s.unlock_chapter for s in stages if s.family in {"pudding_time", "metal_zone"}},
        )

    def test_the_puppet_show_aggregate_moves_with_its_slots(self) -> None:
        """The aggregate and the slots that ride it must not drift apart."""
        stages = [s for s in self.stages(replace(DEFAULT_TUNING.hunting, puppet_show_item_aggregate=99)) if s.family == "puppet_show"]
        self.assertEqual({99}, {stage.max_items_total for stage in stages})
        for stage in stages:
            self.assertEqual(99, max(stage.item_maxima[item] for item in range(1, 9)))
        # The third zone's alternating slots keep their recovered ceiling of 2.
        third = next(stage for stage in stages if stage.section == 3)
        self.assertEqual({2}, {third.item_maxima[item] for item in (2, 4, 6, 8)})

    def test_an_unlock_ladder_must_be_complete_and_not_decrease(self) -> None:
        for body, message in (
            ("[hunting]\ntier_unlock_chapters = [3, 9]\n", "tier_unlock_chapters must be 3 nonnegative integers"),
            ("[hunting]\ntier_unlock_chapters = [9, 3, 18]\n", "tier_unlock_chapters must not decrease"),
            ("[hunting]\nmetal_unlock_chapters = [1, 2, 3]\n", "metal_unlock_chapters must be 7 nonnegative integers"),
        ):
            with self.subTest(body=body):
                path, directory = _tuning(body)
                self.addCleanup(directory.cleanup)
                with self.assertRaises(TuningError) as caught:
                    load_tuning(path)
                self.assertEqual(message, str(caught.exception))

    def test_equal_neighbours_are_allowed(self) -> None:
        """Opening two tiers at once is a coherent thing to want."""
        path, directory = _tuning("[hunting]\ntier_unlock_chapters = [3, 3, 18]\n")
        self.addCleanup(directory.cleanup)
        self.assertEqual((3, 3, 18), load_tuning(path).hunting.tier_unlock_chapters)


class ExpMultiplierTest(unittest.TestCase):
    """The credit itself, away from the transport that carries it."""

    def setUp(self) -> None:
        job = JobProgression(100_000, tuple(index * 1_000 for index in range(50)))
        idle = JobProgression(0, (0,))
        self.curve = ClearStateCatalog(6, 1000, 100, {7: CharacterProgression(7, 0, (job, idle, idle))})
        self.team = [7, 0, 0, 0, 0, 0]

    def row(self, experience: int, level: int) -> list[dict[str, object]]:
        return [{"id": 7, "jobID": 0, "jobLevels": [(experience << 12) | level, 0, 0], "skillBoost": 0}]

    def credited(self, rows, multiplier, battle_exp=1_000, curve=...):
        packed = _exp_credited_roster(
            rows, self.team, battle_exp, multiplier, self.curve if curve is ... else curve,
        )[0]["jobLevels"][0]
        return int(packed) >> 12, int(packed) & 0xFFF

    def test_the_bonus_is_credited_and_the_level_recomputed(self) -> None:
        """Level must move with experience: `jobLevels` packs both, and a stale
        level would show the client a character that had not levelled."""
        self.assertEqual((7_000, 8), self.credited(self.row(5_000, 6), 300))

    def test_one_hundred_percent_changes_nothing(self) -> None:
        self.assertEqual((5_000, 6), self.credited(self.row(5_000, 6), 100))

    def test_the_credit_never_passes_the_jobs_own_maximum(self) -> None:
        """It raises a number the game already bounded; it does not unbound it."""
        self.assertEqual(100_000, self.credited(self.row(99_500, 49), 10_000, battle_exp=100_000)[0])

    def test_nothing_is_credited_without_a_curve(self) -> None:
        self.assertEqual((5_000, 6), self.credited(self.row(5_000, 6), 300, curve=None))

    def test_a_character_the_curve_does_not_describe_is_left_alone(self) -> None:
        rows = [{"id": 99, "jobID": 0, "jobLevels": [(5_000 << 12) | 6, 0, 0]}]
        packed = _exp_credited_roster(rows, [99, 0, 0, 0, 0, 0], 1_000, 300, self.curve)[0]["jobLevels"][0]
        self.assertEqual(5_000, packed >> 12)

    def test_a_repeated_party_slot_is_credited_once(self) -> None:
        """Only the generic-story path validates that a party has no repeats.

        Hunting does not, so a repeated id reaching the credit must not
        multiply its own share: at 200% a lone member takes the whole battle's
        EXP again, and naming them twice must not make that twice over.
        """
        credited = _exp_credited_roster(self.row(0, 1), [7, 7, 0, 0, 0, 0], 1_000, 200, self.curve)
        self.assertEqual(1_000, int(credited[0]["jobLevels"][0]) >> 12)

    def test_the_share_is_split_across_the_party_the_client_split_it_across(self) -> None:
        """Two eligible members each take half the bonus one would have taken,
        so a boosted clear stays proportional to an unboosted one."""
        job = self.curve.characters[7].jobs[0]
        curve = replace(
            self.curve,
            characters={
                identifier: CharacterProgression(identifier, 0, (job, job, job))
                for identifier in (7, 8)
            },
        )
        rows = [
            {"id": 7, "jobID": 0, "jobLevels": [(5_000 << 12) | 6, 0, 0]},
            {"id": 8, "jobID": 0, "jobLevels": [(5_000 << 12) | 6, 0, 0]},
        ]
        credited = _exp_credited_roster(rows, [7, 8, 0, 0, 0, 0], 1_000, 300, curve)
        # 1000 split two ways is 500 each; at 300% that is a further 1000 each.
        self.assertEqual([6_000, 6_000], [int(row["jobLevels"][0]) >> 12 for row in credited])


class CreditedRosterOutpacesTheClientTest(unittest.TestCase):
    """The interaction that makes the multiplier and the EXP audit exclusive.

    A credited roster is by construction ahead of the client's own copy, so the
    client's honest next report is lower than durable-plus-share. Left audited,
    the clear after a boosted one is refused -- and a refused clear leaves the
    battle active, so every later stage is refused too. That reads to a player
    as a corrupted install rather than as one strict setting meeting another.
    """

    def setUp(self) -> None:
        job = JobProgression(100_000, tuple(index * 1_000 for index in range(50)))
        idle = JobProgression(0, (0,))
        self.curve = ClearStateCatalog(6, 1000, 100, {7: CharacterProgression(7, 0, (job, idle, idle))})

    def row(self, experience: int, level: int) -> dict[str, object]:
        return {
            "id": 7, "buddy": 0, "date": 0.0, "jobSlots": [0, 0, 0],
            "jobLevels": [(experience << 12) | level, 0, 0],
            "jobID": 0, "flags": 0, "skillBoost": 0, "luck": 0,
        }

    def matches(self, durable, submitted, *, audit: bool) -> bool:
        from liminal_gate.bootstrap_server import _clear_state_matches

        return _clear_state_matches(
            {"chrdata": [durable], "teamMembers": [7, 0, 0, 0, 0, 0]},
            {
                "chrdata": [submitted],
                "battle_result": {
                    "exp": 1_000, "boostup": [0] * 6, "monsters": [],
                    "items": {}, "summons": [], "coins": 0,
                },
            },
            self.curve, audit,
        )

    def test_an_unboosted_clear_is_audited_exactly_as_before(self) -> None:
        self.assertTrue(self.matches(self.row(1_000, 2), self.row(2_000, 3), audit=True))
        self.assertFalse(self.matches(self.row(1_000, 2), self.row(9_000, 3), audit=True))

    def test_the_audit_refuses_a_client_working_from_its_own_baseline(self) -> None:
        """The bug this exclusion exists for, pinned so it cannot come back."""
        # Durable 2000 because the last clear credited a bonus; the client only
        # ever saw its own 1000, so it honestly reports 1000 + 1000.
        self.assertFalse(self.matches(self.row(2_000, 3), self.row(2_000, 3), audit=True))

    def test_dropping_the_experience_audit_admits_that_same_clear(self) -> None:
        self.assertTrue(self.matches(self.row(2_000, 3), self.row(2_000, 3), audit=False))

    def test_every_other_clear_state_rule_still_applies(self) -> None:
        """Only the experience equality is dropped, not the whole catalog."""
        # Skill Boost past the per-battle ceiling is still refused.
        durable, submitted = self.row(2_000, 3), self.row(2_000, 3)
        submitted["skillBoost"] = 500
        self.assertFalse(self.matches(durable, submitted, audit=False))
        # So is a mutation of an immutable field.
        durable, submitted = self.row(2_000, 3), self.row(2_000, 3)
        submitted["flags"] = 9
        self.assertFalse(self.matches(durable, submitted, audit=False))

    def test_a_stale_client_cannot_roll_the_credited_gain_back(self) -> None:
        """What protects the durable value once the audit is off."""
        from liminal_gate.bootstrap_server import _preserved_roster

        merged = _preserved_roster([self.row(5_000, 6)], [self.row(2_000, 3)])
        self.assertEqual(5_000, int(merged[0]["jobLevels"][0]) >> 12)


class TuningTemplateTest(unittest.TestCase):
    """The file setup writes, and the one property that keeps it honest."""

    def test_the_template_as_written_is_exactly_the_bundled_defaults(self) -> None:
        """A fresh install must be byte-for-byte the bundled policy."""
        path, directory = _tuning("", head=DEFAULT_TUNING_TEMPLATE)
        self.addCleanup(directory.cleanup)
        self.assertEqual(DEFAULT_TUNING, load_tuning(path))

    def test_uncommenting_every_override_still_yields_the_defaults(self) -> None:
        """The guard against the template drifting from the code.

        Each commented assignment claims to show its bundled default. Turning
        all of them on must therefore change nothing -- if someone edits a
        number here without editing `DEFAULT_TUNING`, or the other way round,
        this is where it shows up.
        """
        lines = [
            re.sub(r"^# (?=[a-z_]+ = )", "", line)
            for line in DEFAULT_TUNING_TEMPLATE.splitlines()
        ]
        assignments = [
            line for line in lines
            if re.match(r"^[a-z_]+ = ", line)
            and not line.startswith(("schema_version", "provenance"))
        ]
        # Every tunable field, so a new knob added to the code without a line
        # in the template fails here rather than going unmentioned.
        expected = sum(
            len(fields(section)) for section in (PactTuning, CompanionTuning, HuntingTuning, GateTuning, ExpTuning)
        )
        self.assertEqual(expected, len(assignments))
        path, directory = _tuning("", head="\n".join(lines))
        self.addCleanup(directory.cleanup)
        self.assertEqual(DEFAULT_TUNING, load_tuning(path))

    def test_it_is_written_once_and_never_over_an_operators_edits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / DEFAULT_TUNING_DOCUMENT
            self.assertTrue(write_default_tuning(path))
            path.write_text(
                path.read_text(encoding="utf-8").replace(
                    "# species_limits = true", "species_limits = false",
                ),
                encoding="utf-8",
            )
            # A setup rerun is exactly the moment an edit would be lost.
            self.assertFalse(write_default_tuning(path))
            self.assertFalse(load_tuning(path).gates.species_limits)
            # And overriding one knob leaves every other one tracking its default.
            self.assertEqual(DEFAULT_TUNING.pact, load_tuning(path).pact)


class TuningLaunchTest(unittest.TestCase):
    def config(self, *extra: str, state: str):
        argv = [
            "bootstrap_server",
            "--profile", str(PUBLIC_ROOT / "profiles" / "legacy-client-bootstrap.json"),
            "--state-file", state, *extra,
        ]
        with patch.object(sys, "argv", argv):
            return load_launch_config(parse_args())

    def test_the_launcher_carries_the_tuning_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config = self.config("--tuning", "t.toml", state=str(Path(directory) / "s.json"))
        self.assertEqual(Path("t.toml"), config.tuning)

    def test_every_launcher_reaches_a_conventional_tuning_document(self) -> None:
        """A policy no launcher passes is a policy nobody can use.

        That is how Daily Quests once shipped -- implemented, tested,
        documented, and reachable from neither launcher -- so both are asserted
        here rather than only the one a change happened to touch.
        """
        from liminal_gate.server_setup import server_arguments as dedicated
        from liminal_gate.tester_setup import server_arguments as guided

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            for name, command in (
                ("guided", guided(Path("resources"), data, 8696)),
                ("dedicated", dedicated(Path("resources"), data, "0.0.0.0", 8642)),
            ):
                with self.subTest(name, present=False):
                    # Nothing generates this file, so naming one that is not
                    # there would fail every install that never wrote one.
                    self.assertNotIn("--tuning", command)
            (data / DEFAULT_TUNING_DOCUMENT).write_text(_HEAD, encoding="utf-8")
            for name, command in (
                ("guided", guided(Path("resources"), data, 8696)),
                ("dedicated", dedicated(Path("resources"), data, "0.0.0.0", 8642)),
            ):
                with self.subTest(name, present=True):
                    self.assertEqual(
                        str((data / DEFAULT_TUNING_DOCUMENT).resolve()),
                        command[command.index("--tuning") + 1],
                    )

    def test_an_explicit_path_overrides_the_conventional_one(self) -> None:
        from liminal_gate.server_setup import server_arguments as dedicated
        from liminal_gate.tester_setup import server_arguments as guided

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / DEFAULT_TUNING_DOCUMENT).write_text(_HEAD, encoding="utf-8")
            chosen = Path(directory) / "elsewhere.toml"
            for name, command in (
                ("guided", guided(Path("resources"), data, 8696, None, chosen)),
                ("dedicated", dedicated(Path("resources"), data, "0.0.0.0", 8642, tuning=chosen)),
            ):
                with self.subTest(name):
                    # Resolved, the way every other catalog path is, so a unit
                    # or a subprocess started elsewhere still finds the file.
                    self.assertEqual(str(chosen.resolve()), command[command.index("--tuning") + 1])

    def test_the_guided_command_line_the_launcher_builds_still_parses(self) -> None:
        """The tuning flag must survive the round trip into `ServerConfig`."""
        from liminal_gate.tester_setup import server_arguments as guided

        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / DEFAULT_TUNING_DOCUMENT).write_text(_HEAD, encoding="utf-8")
            command = guided(Path("resources"), data, 8696)[3:]
            with patch.object(sys, "argv", ["bootstrap_server", *command]):
                config = load_launch_config(parse_args())
        self.assertEqual((data / DEFAULT_TUNING_DOCUMENT).resolve(), config.tuning)

    def test_an_exp_multiplier_without_a_level_curve_refuses_the_launch(self) -> None:
        """Serving 100 silently would leave the operator no way to tell."""
        path, directory = _tuning("[exp]\nmultiplier_percent = 200\n")
        self.addCleanup(directory.cleanup)
        with tempfile.TemporaryDirectory() as state:
            config = self.config("--tuning", str(path), state=str(Path(state) / "s.json"))
            with self.assertRaises(ProfileError) as caught:
                build_server(config)
        self.assertIn(
            "an EXP multiplier requires --clear-state-catalog", str(caught.exception),
        )


if __name__ == "__main__":
    unittest.main()
