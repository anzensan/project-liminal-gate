from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from liminal_gate.setup_rehearsal import (
    OPTIONAL_ARTIFACTS,
    REQUIRED_ARTIFACTS,
    RehearsalError,
    RehearsalRun,
    compare,
    describe_generation,
    first_resource_path,
    onboard,
    prune_runs,
    render_summary,
    setup_arguments,
    stage_source,
    summarize_transport,
    verify_restart,
)


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


class StageSourceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.repository = self.root / "repository"
        (self.repository / "liminal_gate").mkdir(parents=True)
        (self.repository / "liminal_gate" / "committed.py").write_text("committed\n", encoding="utf-8")
        (self.repository / ".gitignore").write_text("user-data/\nbuild/\n", encoding="utf-8")
        _git(self.repository, "init", "--initial-branch=main")
        _git(self.repository, "config", "user.email", "rehearsal@example.invalid")
        _git(self.repository, "config", "user.name", "Rehearsal")
        _git(self.repository, "add", ".")
        _git(self.repository, "commit", "-m", "initial")
        self.addCleanup(self.temporary_directory.cleanup)

    def test_working_tree_mode_copies_uncommitted_source_and_no_generated_material(self) -> None:
        (self.repository / "liminal_gate" / "new_module.py").write_text("new\n", encoding="utf-8")
        (self.repository / "liminal_gate" / "committed.py").write_text("edited\n", encoding="utf-8")
        (self.repository / "user-data").mkdir()
        (self.repository / "user-data" / "bootstrap-state.json").write_text("{}", encoding="utf-8")

        destination = self.root / "staged"
        facts = stage_source(self.repository, destination, None)

        self.assertEqual("working tree", facts["source_mode"])
        self.assertTrue(facts["source_dirty"])
        self.assertEqual("edited\n", (destination / "liminal_gate" / "committed.py").read_text(encoding="utf-8"))
        self.assertTrue((destination / "liminal_gate" / "new_module.py").is_file())
        self.assertFalse((destination / "user-data").exists())

    def test_a_revision_is_staged_as_the_committed_source_only(self) -> None:
        (self.repository / "liminal_gate" / "committed.py").write_text("edited\n", encoding="utf-8")
        (self.repository / "liminal_gate" / "uncommitted.py").write_text("new\n", encoding="utf-8")

        destination = self.root / "worktree"
        facts = stage_source(self.repository, destination, "HEAD")
        self.addCleanup(
            subprocess.run,
            ("git", "-C", str(self.repository), "worktree", "remove", "--force", str(destination)),
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

        self.assertFalse(facts["source_dirty"])
        self.assertEqual("committed\n", (destination / "liminal_gate" / "committed.py").read_text(encoding="utf-8"))
        self.assertFalse((destination / "liminal_gate" / "uncommitted.py").exists())

    def test_a_file_deleted_in_the_working_tree_does_not_stop_the_copy(self) -> None:
        (self.repository / "liminal_gate" / "committed.py").unlink()
        destination = self.root / "staged"
        stage_source(self.repository, destination, None)
        self.assertFalse((destination / "liminal_gate" / "committed.py").exists())


class GenerationFactsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.apk = self.root / "input.apk"
        self.apk.write_bytes(b"local-apk")
        self.data = self.root / "user-data"
        self.addCleanup(self.temporary_directory.cleanup)

    def _generate(self, apk_sha256: str = "") -> None:
        from liminal_gate.setup_rehearsal import sha256_file

        digest = apk_sha256 or "0" * 64
        # Written first: the event catalog names this file's hash, which is how
        # it is tied to the APK it never names itself.
        characters = self.data / "character-catalog.json"
        characters.parent.mkdir(parents=True, exist_ok=True)
        characters.write_text(
            json.dumps({"source": {"apk_sha256": digest}, "characters": [{"id": 1}, {"id": 2}]}),
            encoding="utf-8",
        )
        documents = {
            "companion-equipment.json": {"source": {"apk_sha256": digest}, "rows": []},
            "event-catalog.json": {
                "character_catalog_sha256": sha256_file(characters),
                "stages": [
                    {"event_id": "archive", "stage": 1},
                    {"event_id": "archive", "stage": 2},
                    {"event_id": "tower", "stage": 1},
                ],
            },
            "story-outcomes.json": {"source": {"apk_sha256": digest}, "rules": [{"stage": "1-1"}]},
            "resources.json": {
                "schema_version": 1,
                "resources": [{"path": "/resources/a", "file": "a", "sha256": "aa", "content_type": "text/plain"}],
            },
            "names.json": {"characters": {}},
            "derived/native-encounters.json": {"source": {"apk_sha256": digest}, "stages": [{"stage": 1}]},
            "derived/scenario-encounters.json": {"stages": [{"stage": 2}, {"stage": 3}]},
        }
        for name, document in documents.items():
            path = self.data / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(document), encoding="utf-8")
        (self.data / "il2cpp").mkdir(parents=True, exist_ok=True)
        (self.data / "il2cpp" / "dump.cs").write_text("// dump\n", encoding="utf-8")
        for index in range(3):
            (self.data / "il2cpp").mkdir(parents=True, exist_ok=True)
            (self.data / "il2cpp" / "DummyDll").mkdir(parents=True, exist_ok=True)
            (self.data / "il2cpp" / "DummyDll" / f"Assembly{index}.dll").write_bytes(b"dll")
        (self.data / "liminal-gate-unsigned.apk").write_bytes(b"unsigned")
        (self.data / "liminal-gate-test.apk").write_bytes(b"signed")

    def test_counts_and_provenance_describe_what_setup_produced(self) -> None:
        from liminal_gate.setup_rehearsal import sha256_file

        self._generate(sha256_file(self.apk))
        facts = describe_generation(self.data, self.apk)

        self.assertEqual(3, facts["dummy_dll_count"])
        self.assertEqual(2, facts["counts"]["characters"])
        self.assertEqual(3, facts["counts"]["event_stages"])
        self.assertEqual(2, facts["counts"]["event_families"])
        self.assertEqual(1, facts["counts"]["resource_mappings"])
        self.assertEqual(2, facts["counts"]["scenario_stages"])
        self.assertEqual(1, facts["counts"]["native_stages"])
        self.assertTrue(all(facts["provenance"].values()))
        self.assertEqual(
            set(REQUIRED_ARTIFACTS) | set(OPTIONAL_ARTIFACTS), set(facts["artifacts"]),
        )

    def test_a_catalog_generated_from_another_apk_is_reported_not_hidden(self) -> None:
        self._generate("f" * 64)
        facts = describe_generation(self.data, self.apk)
        self.assertFalse(facts["provenance"]["character_catalog_apk_match"])

    def test_a_missing_required_artifact_fails_by_name(self) -> None:
        self._generate()
        (self.data / "story-outcomes.json").unlink()
        with self.assertRaises(RehearsalError) as raised:
            describe_generation(self.data, self.apk)
        self.assertIn("story-outcomes.json", str(raised.exception))

    def test_an_optional_artifact_is_omitted_rather_than_fatal(self) -> None:
        self._generate()
        (self.data / "names.json").unlink()
        facts = describe_generation(self.data, self.apk)
        self.assertNotIn("names.json", facts["artifacts"])

    def test_the_smallest_mapped_resource_is_chosen_for_the_transport_check(self) -> None:
        self._generate()
        self.assertEqual("/resources/a", first_resource_path(self.data))


class BaselineComparisonTest(unittest.TestCase):
    def _summary(self, **overrides: object) -> dict[str, object]:
        summary: dict[str, object] = {
            "schema_version": 1,
            "started": "2026-08-01T00:00:00Z",
            "finished": "2026-08-01T00:20:00Z",
            "duration_seconds": 1200.0,
            "run_directory": "/tmp/run-a",
            "source_commit": "a" * 40,
            "source_dirty": False,
            "source_mode": "working tree",
            "python": "3.13.1",
            "build_port": 8697,
            "apk_sha256": "abc",
            "artifacts": {"story-outcomes.json": "1111"},
            "counts": {"story_rules": 780},
            "recorded_artifacts": {"liminal-gate-test.apk": "signed-a"},
        }
        summary.update(overrides)
        return summary

    def test_a_run_that_only_differs_where_runs_always_differ_compares_clean(self) -> None:
        baseline = self._summary()
        current = self._summary(
            started="2026-08-02T00:00:00Z",
            finished="2026-08-02T00:19:00Z",
            duration_seconds=1140.0,
            run_directory="/tmp/run-b",
            source_commit="b" * 40,
            source_dirty=True,
            python="3.13.2",
            recorded_artifacts={"liminal-gate-test.apk": "signed-b"},
        )
        self.assertEqual([], compare(baseline, current))

    def test_the_rolled_starter_is_not_a_regression_but_its_loss_still_is(self) -> None:
        """The tutorial Pact rolls; only the invariants around it are compared."""
        baseline = self._summary(smoke={"granted_character": 1, "surviving_characters": [1], "replay_matched": True})
        rolled = self._summary(smoke={"granted_character": 3, "surviving_characters": [3], "replay_matched": True})
        self.assertEqual([], compare(baseline, rolled))
        broken = self._summary(smoke={"granted_character": 3, "surviving_characters": [3], "replay_matched": False})
        self.assertEqual(["smoke.replay_matched: true -> false"], compare(baseline, broken))

    def test_a_different_build_port_is_compared_because_it_changes_the_apk(self) -> None:
        differences = compare(self._summary(), self._summary(build_port=9000))
        self.assertEqual(["build_port: 8697 -> 9000"], differences)

    def test_a_changed_catalog_is_named_with_both_values(self) -> None:
        differences = compare(
            self._summary(), self._summary(artifacts={"story-outcomes.json": "2222"}),
        )
        self.assertEqual(["artifacts.story-outcomes.json: 1111 -> 2222"], differences)

    def test_a_lost_row_count_is_reported_as_a_number_change(self) -> None:
        differences = compare(self._summary(), self._summary(counts={"story_rules": 12}))
        self.assertEqual(["counts.story_rules: 780 -> 12"], differences)

    def test_an_artifact_that_stopped_being_produced_is_reported_as_removed(self) -> None:
        differences = compare(self._summary(), self._summary(artifacts={}))
        self.assertEqual(1, len(differences))
        self.assertIn("removed", differences[0])

    def test_skipping_the_smoke_stage_compares_the_rest_instead_of_the_absence(self) -> None:
        baseline = self._summary(smoke={"replay_matched": True})
        generated_only = self._summary()
        self.assertNotIn("smoke", generated_only)
        self.assertEqual([], compare(baseline, generated_only))
        generated_only["counts"] = {"story_rules": 12}
        self.assertEqual(["counts.story_rules: 780 -> 12"], compare(baseline, generated_only))

    def test_a_baseline_from_another_apk_refuses_to_be_compared(self) -> None:
        differences = compare(self._summary(apk_sha256="different"), self._summary())
        self.assertEqual(1, len(differences))
        self.assertIn("record a new baseline", differences[0])

    def test_the_rendered_summary_is_one_greppable_field_per_line(self) -> None:
        rendered = render_summary({"counts": {"story_rules": 780}, "apk_sha256": "abc"})
        self.assertIn("counts.story_rules=780", rendered)
        self.assertIn("apk_sha256=abc", rendered)


class TransportSummaryTest(unittest.TestCase):
    def test_the_servers_own_event_log_becomes_operation_and_status_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "events.jsonl"
            log.write_text(
                "\n".join(
                    json.dumps(event) for event in (
                        {"method": "GET", "path": "/gd/login", "status": 200},
                        {"method": "GET", "path": "/gd/userdata", "status": 200},
                        {"method": "GET", "path": "/gd/userdata", "status": 200},
                        {"method": "POST", "path": "/gd/do_slot", "status": 200},
                        {"not": "an event"},
                        "unparseable",
                    )
                ) + "\n",
                encoding="utf-8",
            )
            transport = summarize_transport(log, [{"method": "GET", "path": "/gd/login", "status": 200}])

        self.assertEqual(5, transport["events"])
        self.assertEqual(2, transport["operations"]["/gd/userdata"])
        self.assertEqual(4, transport["statuses"]["200"])
        self.assertEqual([], transport["client_non_200"])

    def test_a_non_200_answer_is_kept_for_the_failure_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            transport = summarize_transport(
                Path(directory) / "absent.jsonl",
                [{"method": "GET", "path": "/gd/userdata", "status": 401}],
            )
        self.assertEqual(0, transport["events"])
        self.assertEqual(1, len(transport["client_non_200"]))


class FakeClient:
    """A scripted stand-in for the local transport, keyed by route."""

    def __init__(self, responses: dict[str, object], resource: bytes = b"resource") -> None:
        self.responses = responses
        self.resource = resource
        self.exchanges: list[dict[str, object]] = []

    def get(self, path: str) -> tuple[int, object]:
        return self._answer(path)

    def post(self, path: str, body: str) -> tuple[int, object]:
        return self._answer(path)

    def raw(self, path: str) -> tuple[int, bytes]:
        return 200, self.resource

    def _answer(self, path: str) -> tuple[int, object]:
        route = path.split("?", 1)[0]
        self.exchanges.append({"method": "GET", "path": route, "status": 200})
        return 200, self.responses[route]


def _healthy_responses(character_id: int = 1) -> dict[str, object]:
    pact = {
        "success": True,
        "chrdata": [{"id": character_id}],
        "teamMembers": [character_id],
    }
    return {
        "/gd/get_current_time": {"success": True, "time": 1.0},
        "/gd/get_server_status": {"success": True},
        "/gd/signup": {"success": True, "id": "rehearsal-account"},
        "/gd/login": {"success": True, "id": "rehearsal-account"},
        "/gd/userdata": {"success": True, "chrdata": [], "teamMembers": []},
        "/gd/do_slot": pact,
    }


class OnboardingSequenceTest(unittest.TestCase):
    def test_a_healthy_server_grants_exactly_one_starter(self) -> None:
        client = FakeClient(_healthy_responses())
        result = onboard(client, "/resources/a")
        self.assertEqual(1, result["granted_character"])
        self.assertEqual("/resources/a", result["resource_path"])

    def test_a_new_account_that_already_has_characters_fails(self) -> None:
        responses = _healthy_responses()
        responses["/gd/userdata"] = {"success": True, "chrdata": [{"id": 9}], "teamMembers": [9]}
        with self.assertRaises(RehearsalError) as raised:
            onboard(FakeClient(responses), "/resources/a")
        self.assertIn("already granted", str(raised.exception))

    def test_a_pact_that_grants_nothing_fails(self) -> None:
        responses = _healthy_responses()
        responses["/gd/do_slot"] = {"success": True, "chrdata": [], "teamMembers": []}
        with self.assertRaises(RehearsalError) as raised:
            onboard(FakeClient(responses), "/resources/a")
        self.assertIn("exactly one starter", str(raised.exception))

    def test_a_failing_answer_is_reported_with_its_route(self) -> None:
        responses = _healthy_responses()
        responses["/gd/signup"] = {"success": False, "error": "no"}
        with self.assertRaises(RehearsalError) as raised:
            onboard(FakeClient(responses), "/resources/a")
        self.assertIn("signup", str(raised.exception))

    def test_a_restart_that_keeps_the_account_and_replays_the_pact_passes(self) -> None:
        responses = _healthy_responses()
        before = onboard(FakeClient(responses), "/resources/a")
        after_responses = dict(responses)
        after_responses["/gd/userdata"] = {"success": True, "chrdata": [{"id": 1}], "teamMembers": [1]}
        result = verify_restart(FakeClient(after_responses), before)
        self.assertEqual([1], result["surviving_characters"])
        self.assertTrue(result["replay_matched"])

    def test_a_restart_that_lost_the_starter_fails(self) -> None:
        responses = _healthy_responses()
        before = onboard(FakeClient(responses), "/resources/a")
        after_responses = dict(responses)
        after_responses["/gd/userdata"] = {"success": True, "chrdata": [], "teamMembers": []}
        with self.assertRaises(RehearsalError) as raised:
            verify_restart(FakeClient(after_responses), before)
        self.assertIn("lost the granted starter", str(raised.exception))

    def test_a_replay_signed_for_the_new_session_still_counts_as_a_replay(self) -> None:
        """The signature is per response; the result it signs is what replays."""
        responses = _healthy_responses()
        responses["/gd/do_slot"] = dict(responses["/gd/do_slot"], digest="F8C1D4131A7098A2")
        before = onboard(FakeClient(responses), "/resources/a")
        after_responses = dict(responses)
        after_responses["/gd/userdata"] = {"success": True, "chrdata": [{"id": 1}], "teamMembers": [1]}
        after_responses["/gd/do_slot"] = dict(responses["/gd/do_slot"], digest="168A7E3A430B5A47")
        self.assertTrue(verify_restart(FakeClient(after_responses), before)["replay_matched"])

    def test_a_repeated_pact_that_rerolled_after_restart_fails(self) -> None:
        responses = _healthy_responses()
        before = onboard(FakeClient(responses), "/resources/a")
        after_responses = dict(responses)
        after_responses["/gd/userdata"] = {"success": True, "chrdata": [{"id": 1}], "teamMembers": [1]}
        after_responses["/gd/do_slot"] = {"success": True, "chrdata": [{"id": 2}], "teamMembers": [2]}
        with self.assertRaises(RehearsalError) as raised:
            verify_restart(FakeClient(after_responses), before)
        self.assertIn("different result after restart", str(raised.exception))


class RunDirectoryTest(unittest.TestCase):
    def test_setup_arguments_never_configure_interactively_or_touch_a_device(self) -> None:
        arguments = setup_arguments(
            Path("/venv/bin/python"), Path("input.apk"), Path("."), Path("data"), 8696, None,
        )
        self.assertIn("--no-configure", arguments)
        self.assertNotIn("--device", arguments)
        self.assertIn("liminal_gate.tester_setup", arguments)

    def test_a_reused_il2cpp_dump_is_passed_through(self) -> None:
        arguments = setup_arguments(
            Path("/venv/bin/python"), Path("input.apk"), Path("."), Path("data"), 8696, Path("DummyDll"),
        )
        self.assertIn("--dummy-dll-dir", arguments)

    def test_only_the_newest_run_directories_are_kept(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("20260101-000000", "20260102-000000", "20260103-000000"):
                (root / name).mkdir()
            prune_runs(root, 2)
            self.assertEqual(
                ["20260102-000000", "20260103-000000"],
                sorted(path.name for path in root.iterdir()),
            )

    def test_a_run_lays_its_directories_out_predictably(self) -> None:
        run = RehearsalRun(Path("/runs/20260101-000000"))
        self.assertEqual(Path("/runs/20260101-000000/source"), run.source)
        self.assertEqual(Path("/runs/20260101-000000/user-data"), run.data_directory)
        self.assertEqual(Path("/runs/20260101-000000/logs"), run.logs)


if __name__ == "__main__":
    unittest.main()
