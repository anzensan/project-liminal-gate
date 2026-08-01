"""Rehearse guided setup end to end and compare the result with a known-good run.

Guided setup is the one path every operator takes and the one path the unit
suite cannot reach: `tests/test_tester_setup.py` proves the decisions setup
makes, with the IL2CPP dump, the master-data import, the catalog derivations,
the APK patch, and the signing all replaced by fakes.  Proving the real pipeline
still works has meant resetting a checkout by hand, running setup, and reading
the output -- which is slow enough that it happens rarely and by eye, so a
catalog that quietly lost half its rows looks exactly like one that did not.

This module turns that manual rehearsal into one command.  It stages a clean
copy of the source, builds an isolated environment, runs guided setup against
the operator's own immutable inputs, then starts the server the same way setup
would and drives a real onboarding sequence over HTTP through a restart.  What
it produces is a summary of facts -- input hashes, generated-artifact hashes,
catalog row counts, and the transport result -- which is compared field by field
against a stored baseline.  A regression therefore reports itself as a named
changed field rather than as something the operator has to notice.

The baseline is derived from the operator's own APK and resource tree, so it is
never committed: it lives beside the save, under `--data-dir`, and a run refuses
to compare against a baseline recorded from different inputs.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
from http.client import HTTPConnection, HTTPException
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, Iterator, Sequence

from liminal_gate.tester_setup import (
    DEFAULT_COMPANION_EQUIPMENT_CATALOG,
    DEFAULT_EVENT_CATALOG,
    DEFAULT_OUTCOME_CATALOG,
    IL2CPP_OUTPUT_DIRECTORY,
    resolve_resource_root,
)


REHEARSAL_SCHEMA_VERSION = 1

DEFAULT_RUN_ROOT = Path("build/rehearsal")
# The port guided setup is rehearsed with.  Fixed so the patched APK is
# byte-identical between runs, four digits because that is what the client's
# compiled-in address has room for, and not the documented 8696 so a rehearsal
# does not collide with the server an operator already has running.
DEFAULT_BUILD_PORT = 8697
# Beside the save rather than inside a run directory: runs are pruned, and a
# baseline that disappeared with the run that recorded it would compare nothing.
DEFAULT_BASELINE = Path("user-data/rehearsal-baseline.json")

# The scripted client's identity.  Fixed rather than generated because every run
# gets an empty data directory, and a constant keeps two summaries comparable.
REHEARSAL_ACCOUNT = "rehearsal-account"
REHEARSAL_SIGNUP_TOKEN = "rehearsal-signup"
REHEARSAL_FIRST_TOKEN = "rehearsal-session-1"
REHEARSAL_SECOND_TOKEN = "rehearsal-session-2"
REHEARSAL_PACT_REQUEST = "rehearsal-first-pact"
# The client's own first Pact body.  Taken from the profile's tutorial summon so
# the rehearsal exercises the real scripted grant rather than an invented draw.
REHEARSAL_PACT_BODY = "kind=10&count=1&luckType=false&campaignChrID=0&eventFlag=0&lastUpdate=1"

# Signed per response rather than per result, so two identical answers reached
# with different session tokens carry different values here.
SIGNATURE_FIELDS = frozenset({"digest"})

SERVER_READY_TIMEOUT_SECONDS = 90.0
SERVER_STOP_TIMEOUT_SECONDS = 30.0

# Generated files whose content is fully determined by the inputs, and whose
# hash is therefore worth comparing between runs.  The signed APK is absent on
# purpose: it carries a signature from a keystore this harness creates fresh
# every run, so its hash differs between two identical builds.
REQUIRED_ARTIFACTS = (
    "character-catalog.json",
    DEFAULT_COMPANION_EQUIPMENT_CATALOG,
    DEFAULT_EVENT_CATALOG,
    DEFAULT_OUTCOME_CATALOG,
    "resources.json",
    "derived/native-encounters.json",
    "derived/scenario-encounters.json",
    f"{IL2CPP_OUTPUT_DIRECTORY}/dump.cs",
    "liminal-gate-unsigned.apk",
)

# Compared when present, and reported when they appear or disappear.  Name
# decoding is allowed to fail without stopping setup, so its absence is a real
# result rather than a reason to call the whole rehearsal broken.
OPTIONAL_ARTIFACTS = ("names.json",)

COMPARED_ARTIFACTS = REQUIRED_ARTIFACTS + OPTIONAL_ARTIFACTS

RECORDED_ARTIFACTS = ("liminal-gate-test.apk",)

# Facts that legitimately differ between two correct runs of the same inputs,
# named by their dotted path in the summary.  Recorded for the operator, never
# compared.
VOLATILE_FIELDS = frozenset({
    "schema_version",
    "started",
    "finished",
    "duration_seconds",
    "run_directory",
    "source_commit",
    "source_dirty",
    "source_mode",
    "python",
    "recorded_artifacts",
    # The tutorial Pact really does roll between starters.  Which one it lands
    # on is not a regression; the assertions in `onboard` and `verify_restart`
    # are what hold it to one starter that survives a restart.
    "smoke.granted_character",
    "smoke.surviving_characters",
})


class RehearsalError(RuntimeError):
    """A rehearsal stage could not run, or ran and did not hold."""


@dataclass
class StageLog:
    """Where one stage's output went, so a failure can name a readable file."""

    name: str
    path: Path

    def tail(self, lines: int = 25) -> str:
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "(no output was captured)"
        return "\n".join(text.splitlines()[-lines:])


@dataclass
class RehearsalRun:
    """One rehearsal's directories, chosen once and passed to every stage."""

    root: Path
    source: Path = field(init=False)
    data_directory: Path = field(init=False)
    logs: Path = field(init=False)

    def __post_init__(self) -> None:
        self.source = self.root / "source"
        self.data_directory = self.root / "user-data"
        self.logs = self.root / "logs"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(repository), *arguments),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RehearsalError(
            f"git {' '.join(arguments)} failed in {repository}: {completed.stderr.strip()}"
        )
    return completed.stdout


def stage_source(repository: Path, destination: Path, revision: str | None) -> dict[str, Any]:
    """Put a clean copy of the source under `destination` and describe it.

    Two modes, because the two questions are different.  With no revision this
    copies exactly the files Git tracks plus the untracked ones it would not
    ignore -- the working tree as it stands, including a module added but not
    yet committed, and none of the generated material beside it.  That is what a
    rehearsal before a commit has to test.  With a revision it uses a real
    worktree, which is the stronger claim: this is the source as published.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    head = _git(repository, "rev-parse", "HEAD").strip()
    dirty = bool(_git(repository, "status", "--porcelain", "--untracked-files=all").strip())
    if revision is not None:
        _git(repository, "worktree", "add", "--detach", str(destination), revision)
        resolved = _git(destination, "rev-parse", "HEAD").strip()
        return {"source_mode": f"worktree at {revision}", "source_commit": resolved, "source_dirty": False}
    listed = _git(repository, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    names = [name for name in listed.split("\0") if name]
    if not names:
        raise RehearsalError(f"{repository} listed no source files to copy")
    destination.mkdir(parents=True, exist_ok=True)
    for name in names:
        origin = repository / name
        # A path Git still lists after a delete has no file behind it.  Skipping
        # it copies the working tree as it is rather than failing on a removal.
        if not origin.is_file():
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origin, target)
    return {"source_mode": "working tree", "source_commit": head, "source_dirty": dirty}


def release_source(repository: Path, destination: Path, revision: str | None) -> None:
    """Detach a staged worktree so a kept run directory is not a live checkout."""
    if revision is None:
        return
    try:
        _git(repository, "worktree", "remove", "--force", str(destination))
    except RehearsalError:
        # Removal is a courtesy: the evidence is worth more than the tidiness,
        # and `git worktree prune` recovers the bookkeeping either way.
        pass


def create_environment(source: Path, venv: Path, log: StageLog, reuse: Path | None) -> Path:
    """Return the interpreter that will run setup, building one if needed.

    A reused environment is still re-pointed at this run's staged source.  The
    project is installed editable, so an environment built for an earlier run
    resolves `liminal_gate` to *that* run's copy: reusing one without this step
    would rehearse the previous source while reporting the current one.
    """
    if reuse is not None:
        interpreter = _venv_python(reuse)
        if not interpreter.is_file():
            raise RehearsalError(f"no Python interpreter in the reused environment at {reuse}")
        run_step(log, (str(interpreter), "-m", "pip", "install", "--no-deps", "-e", "."), cwd=source)
        return interpreter
    run_step(log, (sys.executable, "-m", "venv", str(venv)), cwd=source)
    interpreter = _venv_python(venv)
    run_step(log, (str(interpreter), "-m", "pip", "install", "--upgrade", "pip"), cwd=source)
    run_step(log, (str(interpreter), "-m", "pip", "install", "-e", ".[master-import]"), cwd=source)
    return interpreter


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts" if os.name == "nt" else "bin") / ("python.exe" if os.name == "nt" else "python")


def run_step(log: StageLog, arguments: Sequence[str], cwd: Path) -> None:
    """Run one child, append its output to the stage log, and fail loudly.

    Output is appended rather than streamed because these children are long and
    chatty; the operator gets a named log and, on failure, its last lines.
    """
    log.path.parent.mkdir(parents=True, exist_ok=True)
    with log.path.open("a", encoding="utf-8") as stream:
        stream.write(f"\n$ {' '.join(arguments)}\n")
        stream.flush()
        completed = subprocess.run(
            tuple(arguments),
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0:
        raise RehearsalError(
            f"{log.name} failed with exit status {completed.returncode}; "
            f"see {log.path}\n{log.tail()}"
        )


def setup_arguments(
    interpreter: Path, apk: Path, resource_root: Path, data_directory: Path, port: int,
    reuse_il2cpp: Path | None,
) -> list[str]:
    """The guided-setup command line both rehearsal stages share."""
    arguments = [
        str(interpreter), "-m", "liminal_gate.tester_setup",
        "--apk", str(apk.resolve()),
        "--resource-root", str(resource_root.resolve()),
        "--data-dir", str(data_directory.resolve()),
        "--port", str(port),
        "--no-configure",
    ]
    if reuse_il2cpp is not None:
        arguments.extend(("--dummy-dll-dir", str(reuse_il2cpp.resolve())))
    return arguments


def free_port() -> int:
    """Ask the operating system for a port nothing else holds."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def describe_generation(data_directory: Path, apk: Path, reuse_il2cpp: Path | None = None) -> dict[str, Any]:
    """Read what setup produced and reduce it to comparable facts.

    Hashes alone would report *that* something changed; the counts beside them
    report what, which is the difference between a diff an operator can act on
    and one they have to investigate from scratch.

    With `reuse_il2cpp`, setup reuses the operator's existing dump in place
    rather than extracting one under the data directory, so the dump facts are
    read from the reused directory's own root.  They still land in the same
    summary fields: the dump's identity is a compared input either way.
    """
    reused_root = reuse_il2cpp.resolve().parent if reuse_il2cpp is not None else None
    facts: dict[str, Any] = {"apk_sha256": sha256_file(apk)}
    artifacts: dict[str, str] = {}
    for name in REQUIRED_ARTIFACTS:
        path = data_directory / name
        if not path.is_file() and reused_root is not None and name == f"{IL2CPP_OUTPUT_DIRECTORY}/dump.cs":
            path = reused_root / "dump.cs"
        if not path.is_file():
            raise RehearsalError(f"guided setup did not produce {name} under {data_directory}")
        artifacts[name] = sha256_file(path)
    for name in OPTIONAL_ARTIFACTS:
        path = data_directory / name
        if path.is_file():
            artifacts[name] = sha256_file(path)
    facts["artifacts"] = artifacts
    facts["recorded_artifacts"] = {
        name: sha256_file(data_directory / name)
        for name in RECORDED_ARTIFACTS
        if (data_directory / name).is_file()
    }

    dummy_dll = data_directory / IL2CPP_OUTPUT_DIRECTORY / "DummyDll"
    if not dummy_dll.is_dir() and reuse_il2cpp is not None:
        dummy_dll = reuse_il2cpp.resolve()
    facts["dummy_dll_count"] = len(sorted(dummy_dll.glob("*.dll"))) if dummy_dll.is_dir() else 0

    characters = _read_json(data_directory / "character-catalog.json")
    outcomes = _read_json(data_directory / DEFAULT_OUTCOME_CATALOG)
    events = _read_json(data_directory / DEFAULT_EVENT_CATALOG)
    resources = _read_json(data_directory / "resources.json")
    scenario = _read_json(data_directory / "derived" / "scenario-encounters.json")
    native = _read_json(data_directory / "derived" / "native-encounters.json")

    facts["counts"] = {
        "characters": _length(characters, ("characters", "chrdata", "rows")),
        "story_rules": _length(outcomes, ("rules", "stages", "outcomes")),
        "event_stages": _length(events, ("stages",)),
        "event_families": len({
            row.get("event_id") for row in _rows(events, ("stages",)) if isinstance(row, dict)
        }),
        "resource_mappings": _length(resources, ("resources",)),
        "scenario_stages": _length(scenario, ("stages", "chapters", "encounters")),
        "native_stages": _length(native, ("stages", "chapters", "encounters")),
    }
    # Provenance is the check that a catalog belongs to these inputs.  Setup
    # already refuses a mismatch; recording it means the summary shows the tie
    # rather than implying it.  The event catalog names no APK -- it is bound to
    # the character catalog, which is bound to the APK -- so that is the link
    # worth checking for it.
    facts["provenance"] = {
        "character_catalog_apk_match": _source_matches(characters, facts["apk_sha256"]),
        "story_outcome_apk_match": _source_matches(outcomes, facts["apk_sha256"]),
        "native_encounters_apk_match": _source_matches(native, facts["apk_sha256"]),
        "event_catalog_character_match": (
            isinstance(events, dict)
            and events.get("character_catalog_sha256") == artifacts["character-catalog.json"]
        ),
    }
    return facts


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise RehearsalError(f"could not read generated {path}: {error}") from error


def _rows(document: Any, names: Sequence[str]) -> list[Any]:
    if isinstance(document, list):
        return document
    if not isinstance(document, dict):
        return []
    for name in names:
        value = document.get(name)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            return list(value.values())
    return []


def _length(document: Any, names: Sequence[str]) -> int:
    return len(_rows(document, names))


def _source_matches(document: Any, apk_sha256: str) -> bool:
    """Report whether a generated document names this APK as its source."""
    if not isinstance(document, dict):
        return False
    return apk_sha256 in json.dumps(document.get("source", {}))


class LocalClient:
    """The smallest client that can drive the real transport path."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.exchanges: list[dict[str, Any]] = []

    def get(self, path: str) -> tuple[int, Any]:
        return self._exchange("GET", path, None)

    def post(self, path: str, body: str) -> tuple[int, Any]:
        return self._exchange("POST", path, body)

    def raw(self, path: str) -> tuple[int, bytes]:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            payload = response.read()
            self.exchanges.append({"method": "GET", "path": _without_query(path), "status": response.status})
            return response.status, payload
        finally:
            connection.close()

    def _exchange(self, method: str, path: str, body: str | None) -> tuple[int, Any]:
        connection = HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            headers = {"Content-Type": "application/x-www-form-urlencoded"} if body is not None else {}
            connection.request(method, path, body=None if body is None else body.encode("utf-8"), headers=headers)
            response = connection.getresponse()
            raw = response.read()
            self.exchanges.append({"method": method, "path": _without_query(path), "status": response.status})
            try:
                return response.status, json.loads(raw)
            except ValueError:
                return response.status, raw
        finally:
            connection.close()


def _without_query(path: str) -> str:
    return path.split("?", 1)[0]


@contextmanager
def running_server(
    interpreter: Path, source: Path, resource_root: Path, data_directory: Path, port: int,
    log: StageLog,
) -> Iterator[LocalClient]:
    """Start the server exactly as guided setup starts it, and stop it after.

    The argument list is asked of the staged source rather than assembled here,
    so a change to what setup passes the server is exercised by the rehearsal
    instead of being quietly duplicated in it.
    """
    arguments = _server_arguments(interpreter, source, resource_root, data_directory, port)
    log.path.parent.mkdir(parents=True, exist_ok=True)
    with log.path.open("a", encoding="utf-8") as stream:
        stream.write(f"\n$ {' '.join(arguments)}\n")
        stream.flush()
        process = subprocess.Popen(
            arguments,
            cwd=str(source),
            stdin=subprocess.DEVNULL,
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
        try:
            _wait_for_server(process, port, log)
            yield LocalClient(port)
        finally:
            _stop(process)


def _server_arguments(
    interpreter: Path, source: Path, resource_root: Path, data_directory: Path, port: int,
) -> list[str]:
    program = (
        "import json, sys; from pathlib import Path;"
        " from liminal_gate.tester_setup import server_arguments;"
        " print(json.dumps(server_arguments(Path(sys.argv[1]).resolve(), Path(sys.argv[2]), int(sys.argv[3]))))"
    )
    completed = subprocess.run(
        (str(interpreter), "-c", program, str(resource_root.resolve()), str(data_directory.resolve()), str(port)),
        cwd=str(source),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RehearsalError(f"the staged source could not describe its own server command: {completed.stderr.strip()}")
    return list(json.loads(completed.stdout))


def _wait_for_server(process: subprocess.Popen, port: int, log: StageLog) -> None:
    """Wait for the listening socket rather than for a request.

    A readiness probe that spoke HTTP would put a variable number of requests
    into the event log the summary counts, so two identical runs would disagree
    about their own transport totals.
    """
    deadline = time.monotonic() + SERVER_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RehearsalError(f"the server exited with status {process.returncode} before serving\n{log.tail()}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return
        except OSError:
            time.sleep(0.25)
    raise RehearsalError(f"the server did not listen on port {port} within {SERVER_READY_TIMEOUT_SECONDS:.0f}s\n{log.tail()}")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=SERVER_STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=SERVER_STOP_TIMEOUT_SECONDS)


def onboard(client: LocalClient, resource_path: str) -> dict[str, Any]:
    """Drive first-run onboarding and return what the server answered."""
    _expect(client.get("/gd/get_current_time?otk=pre-signup"), "get_current_time")
    _expect(client.get("/gd/get_server_status?otk=pre-signup"), "get_server_status")
    _, signup = _expect(
        client.get(f"/gd/signup?uuid={REHEARSAL_ACCOUNT}&otk={REHEARSAL_SIGNUP_TOKEN}&requestID=rehearsal-signup"),
        "signup",
    )
    if signup.get("id") != REHEARSAL_ACCOUNT:
        raise RehearsalError(f"signup bound a different account: {signup.get('id')!r}")
    _expect(
        client.get(f"/gd/login?uuid={REHEARSAL_ACCOUNT}&otk={REHEARSAL_FIRST_TOKEN}&requestID=rehearsal-login"),
        "login",
    )
    _, initial = _expect(
        client.get(f"/gd/userdata?otk={REHEARSAL_FIRST_TOKEN}&requestID=rehearsal-userdata"),
        "userdata",
    )
    if initial.get("chrdata"):
        raise RehearsalError("a new account started with characters already granted")
    _, pact = _expect(
        client.post(
            f"/gd/do_slot?otk={REHEARSAL_FIRST_TOKEN}&requestID={REHEARSAL_PACT_REQUEST}",
            REHEARSAL_PACT_BODY,
        ),
        "do_slot",
    )
    granted = [row.get("id") for row in pact.get("chrdata", [])]
    if len(granted) != 1 or pact.get("teamMembers") != granted:
        raise RehearsalError(f"the first Pact did not grant exactly one starter: {granted!r}")

    status, payload = client.raw(resource_path)
    if status != 200:
        raise RehearsalError(f"the served resource {resource_path} answered {status}")
    return {
        "granted_character": granted[0],
        "resource_path": resource_path,
        "resource_sha256": hashlib.sha256(payload).hexdigest(),
        "pact_response": pact,
    }


def verify_restart(client: LocalClient, before: dict[str, Any]) -> dict[str, Any]:
    """Confirm a restarted server serves the same account without regenerating.

    A fresh session token is used deliberately: the client gets a new one every
    launch, so reusing the first would test a path the app never takes.
    """
    _expect(
        client.get(f"/gd/login?uuid={REHEARSAL_ACCOUNT}&otk={REHEARSAL_SECOND_TOKEN}&requestID=rehearsal-relogin"),
        "login after restart",
    )
    _, reloaded = _expect(
        client.get(f"/gd/userdata?otk={REHEARSAL_SECOND_TOKEN}&requestID=rehearsal-userdata-after-restart"),
        "userdata after restart",
    )
    surviving = [row.get("id") for row in reloaded.get("chrdata", [])]
    if surviving != [before["granted_character"]]:
        raise RehearsalError(
            f"the restarted server lost the granted starter: {surviving!r} != [{before['granted_character']!r}]"
        )
    _, replay = _expect(
        client.post(
            f"/gd/do_slot?otk={REHEARSAL_SECOND_TOKEN}&requestID={REHEARSAL_PACT_REQUEST}",
            REHEARSAL_PACT_BODY,
        ),
        "do_slot replay after restart",
    )
    if _replayable(replay) != _replayable(before["pact_response"]):
        raise RehearsalError("a repeated first Pact returned a different result after restart")
    return {"surviving_characters": surviving, "replay_matched": True}


def _replayable(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop what a replayed answer is not expected to repeat.

    The response signature is derived from the session it was signed for, so a
    replay reached with a second launch's token carries a different one while
    the result it signs is byte-identical.  Comparing it would report every
    correct replay as a regression.
    """
    return {key: value for key, value in payload.items() if key not in SIGNATURE_FIELDS}


def _expect(result: tuple[int, Any], what: str) -> tuple[int, dict[str, Any]]:
    status, payload = result
    if status != 200 or not isinstance(payload, dict):
        raise RehearsalError(f"{what} answered {status} with {payload!r}")
    if payload.get("success") is False:
        raise RehearsalError(f"{what} answered a failure: {payload!r}")
    return status, payload


def first_resource_path(data_directory: Path) -> str:
    """Choose one small mapped resource to fetch over the real transport path."""
    manifest = _read_json(data_directory / "resources.json")
    resources = manifest.get("resources") if isinstance(manifest, dict) else None
    if not resources:
        raise RehearsalError("the generated resource manifest maps no files")
    smallest = min(resources, key=lambda row: len(str(row.get("path", ""))))
    return str(smallest["path"])


def summarize_transport(event_log: Path, exchanges: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Reduce the server's own event log to counts worth comparing."""
    operations: dict[str, int] = {}
    statuses: dict[str, int] = {}
    total = 0
    if event_log.is_file():
        for line in event_log.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            # A line the log wrote as something other than an object is not an
            # event; counting it would inflate a number the baseline compares.
            if not isinstance(event, dict):
                continue
            total += 1
            operations[str(event.get("path"))] = operations.get(str(event.get("path")), 0) + 1
            statuses[str(event.get("status"))] = statuses.get(str(event.get("status")), 0) + 1
    return {
        "events": total,
        "operations": dict(sorted(operations.items())),
        "statuses": dict(sorted(statuses.items())),
        "client_exchanges": len(exchanges),
        "client_non_200": [row for row in exchanges if row["status"] != 200],
    }


def compare(baseline: dict[str, Any], summary: dict[str, Any]) -> list[str]:
    """Return the fields that differ, ignoring the ones that always will."""
    if baseline.get("apk_sha256") != summary.get("apk_sha256"):
        return [
            "apk_sha256: this baseline was recorded from a different APK "
            f"({baseline.get('apk_sha256')}) than this run used ({summary.get('apk_sha256')}); "
            "record a new baseline instead of comparing against this one"
        ]
    if "smoke" not in summary:
        # `--skip-smoke` compared less than the baseline covers.  Reporting the
        # whole transport section as "removed" would bury the fields that did
        # get compared; main says plainly that it was skipped instead.
        baseline = {key: value for key, value in baseline.items() if key != "smoke"}
    differences: list[str] = []
    _walk(baseline, summary, (), differences)
    return differences


def _walk(baseline: Any, current: Any, trail: tuple[str, ...], differences: list[str]) -> None:
    if isinstance(baseline, dict) and isinstance(current, dict):
        for key in sorted(set(baseline) | set(current)):
            path = trail + (key,)
            if ".".join(path) in VOLATILE_FIELDS:
                continue
            if key not in baseline:
                differences.append(f"{'.'.join(path)}: added ({_render(current[key])})")
            elif key not in current:
                differences.append(f"{'.'.join(path)}: removed (was {_render(baseline[key])})")
            else:
                _walk(baseline[key], current[key], path, differences)
        return
    if baseline != current:
        name = ".".join(trail) or "summary"
        differences.append(f"{name}: {_render(baseline)} -> {_render(current)}")


def _render(value: Any) -> str:
    rendered = json.dumps(value, sort_keys=True) if not isinstance(value, str) else value
    return rendered if len(rendered) <= 120 else rendered[:117] + "..."


def render_summary(summary: dict[str, Any]) -> str:
    """A flat, greppable rendering of the same facts the baseline compares."""
    lines: list[str] = []

    def emit(prefix: str, value: Any) -> None:
        if isinstance(value, dict):
            for key in sorted(value):
                emit(f"{prefix}.{key}" if prefix else str(key), value[key])
            return
        lines.append(f"{prefix}={json.dumps(value, sort_keys=True) if not isinstance(value, str) else value}")

    emit("", summary)
    return "\n".join(lines) + "\n"


def rehearse(
    repository: Path, run: RehearsalRun, apk: Path, resource_root: Path,
    revision: str | None, reuse_venv: Path | None, reuse_il2cpp: Path | None,
    run_smoke: bool, build_port: int = DEFAULT_BUILD_PORT,
) -> dict[str, Any]:
    """Run every requested stage and return the summary they produced."""
    started = time.time()
    run.logs.mkdir(parents=True, exist_ok=True)
    summary: dict[str, Any] = {
        "schema_version": REHEARSAL_SCHEMA_VERSION,
        "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "run_directory": str(run.root.resolve()),
    }

    print("Staging a clean source copy...")
    summary.update(stage_source(repository, run.source, revision))

    print("Building an isolated environment...")
    interpreter = create_environment(
        run.source, run.root / "venv", StageLog("environment", run.logs / "environment.log"), reuse_venv,
    )
    summary["python"] = _interpreter_version(interpreter)

    # The build port is fixed, not borrowed from the operating system: it is
    # compiled into the patched APK, so a different one every run would change
    # that file's hash and report a regression where nothing had changed.
    arguments = setup_arguments(interpreter, apk, resource_root, run.data_directory, build_port, reuse_il2cpp)
    summary["build_port"] = build_port

    print("Checking prerequisites the way an operator would...")
    run_step(StageLog("preflight", run.logs / "preflight.log"), (*arguments, "--check"), cwd=run.source)

    print("Running guided setup (IL2CPP dump, catalogs, resource inventory, APK patch and signing)...")
    run_step(StageLog("setup", run.logs / "setup.log"), (*arguments, "--prepare-only"), cwd=run.source)

    print("Reading what setup produced...")
    summary.update(describe_generation(run.data_directory, apk, reuse_il2cpp))

    if run_smoke:
        print("Driving onboarding through a server restart...")
        # A borrowed port is right here and wrong above: nothing is baked into a
        # file, and two rehearsals should be able to run at once.
        summary["smoke"] = smoke(interpreter, run, resource_root, free_port())

    finished = time.time()
    summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(finished))
    summary["duration_seconds"] = round(finished - started, 1)
    return summary


def smoke(interpreter: Path, run: RehearsalRun, resource_root: Path, port: int) -> dict[str, Any]:
    """Serve the generated data to a scripted client, across a real restart."""
    log = StageLog("server", run.logs / "server.log")
    # Setup generated the manifest against the *detected* Android root, so the
    # smoke server must resolve the operator's argument the same way setup
    # did, or every manifest path misses under a common-parent root.
    resource_root = resolve_resource_root(resource_root)
    resource_path = first_resource_path(run.data_directory)
    with running_server(interpreter, run.source, resource_root, run.data_directory, port, log) as client:
        before = onboard(client, resource_path)
    catalogs_before = _catalog_fingerprint(run.data_directory)
    with running_server(interpreter, run.source, resource_root, run.data_directory, port, log) as restarted:
        after = verify_restart(restarted, before)
        client.exchanges.extend(restarted.exchanges)
    if _catalog_fingerprint(run.data_directory) != catalogs_before:
        raise RehearsalError("a restart regenerated derived catalogs instead of reusing them")
    transport = summarize_transport(run.data_directory / "events.jsonl", client.exchanges)
    if transport["client_non_200"]:
        raise RehearsalError(f"the scripted client saw non-200 answers: {transport['client_non_200']}")
    return {
        "granted_character": before["granted_character"],
        "resource_path": before["resource_path"],
        "resource_sha256": before["resource_sha256"],
        "surviving_characters": after["surviving_characters"],
        "replay_matched": after["replay_matched"],
        "transport": transport,
    }


def _catalog_fingerprint(data_directory: Path) -> dict[str, str]:
    return {
        name: sha256_file(data_directory / name)
        for name in COMPARED_ARTIFACTS
        if (data_directory / name).is_file()
    }


def _interpreter_version(interpreter: Path) -> str:
    completed = subprocess.run(
        (str(interpreter), "-c", "import platform; print(platform.python_version())"),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, check=False,
    )
    return completed.stdout.strip() or "unknown"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", type=Path, required=True, help="your own copy of the final APK; never modified")
    parser.add_argument("--resource-root", type=Path, required=True, help="your own Android resource tree; never modified")
    parser.add_argument("--repository", type=Path, default=Path("."), help="the checkout to rehearse (default: here)")
    parser.add_argument(
        "--revision",
        help="rehearse a committed revision in a Git worktree instead of the working tree as it stands",
    )
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT, help="where run directories are kept")
    parser.add_argument("--run-dir", type=Path, help="an explicit run directory instead of a timestamped one")
    parser.add_argument("--reuse-venv", type=Path, help="an existing environment, instead of building one")
    parser.add_argument(
        "--reuse-il2cpp", type=Path,
        help="an existing Il2CppDumper DummyDll directory; faster, but no longer proves fresh extraction",
    )
    parser.add_argument("--skip-smoke", action="store_true", help="generate only; do not run the server")
    parser.add_argument(
        "--build-port", type=int, default=DEFAULT_BUILD_PORT,
        help=f"the port setup bakes into the rehearsed APK (default {DEFAULT_BUILD_PORT}); changing it changes that APK's hash",
    )
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE, help=f"baseline to compare against (default: {DEFAULT_BASELINE})")
    parser.add_argument("--update-baseline", action="store_true", help="record this run as the baseline")
    parser.add_argument("--keep", type=int, default=3, help="how many previous run directories to keep")
    return parser.parse_args(argv)


#: A run directory's name: `YYYYmmdd-HHMMSS`, exactly what `main` creates.
_RUN_DIRECTORY = re.compile(r"^\d{8}-\d{6}$")


def prune_runs(run_root: Path, keep: int) -> None:
    """Delete the oldest run directories; each one holds an APK and a venv.

    Only directories this tool named are considered. `--run-root` is an
    ordinary path an operator can mistype, and recursive deletion is the one
    genuinely destructive thing here, so it is confined to the timestamp shape
    rather than applied to whatever the directory happens to contain.
    """
    if keep < 0 or not run_root.is_dir():
        return
    runs = sorted(
        (path for path in run_root.iterdir() if path.is_dir() and _RUN_DIRECTORY.match(path.name)),
        key=lambda path: path.name,
    )
    for stale in runs[: max(0, len(runs) - keep)]:
        shutil.rmtree(stale, ignore_errors=True)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    repository = args.repository.resolve()
    if args.run_dir is not None:
        run = RehearsalRun(args.run_dir.resolve())
    else:
        prune_runs(args.run_root, max(0, args.keep - 1))
        run = RehearsalRun((args.run_root / time.strftime("%Y%m%d-%H%M%S", time.gmtime())).resolve())
    baseline_path = args.baseline.resolve()
    stored_baseline = (
        json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.is_file() else None
    )

    try:
        summary = rehearse(
            repository, run, args.apk, args.resource_root, args.revision,
            args.reuse_venv, args.reuse_il2cpp, not args.skip_smoke, args.build_port,
        )
    except RehearsalError as error:
        print(f"\nRehearsal failed: {error}", file=sys.stderr)
        return 1
    finally:
        release_source(repository, run.source, args.revision)

    (run.root / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (run.root / "summary.txt").write_text(render_summary(summary), encoding="utf-8")
    print(f"\nRehearsal completed in {summary['duration_seconds']}s; evidence under {run.root}")

    if args.update_baseline:
        baseline_path.parent.mkdir(parents=True, exist_ok=True)
        baseline_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"Recorded this run as the baseline at {baseline_path}.")
        return 0
    if stored_baseline is None:
        print(
            f"No baseline at {baseline_path}. Nothing was compared. "
            "Rerun with --update-baseline once you trust this result."
        )
        return 0
    if "smoke" not in summary and "smoke" in stored_baseline:
        print("The onboarding and restart result was not compared: this run skipped it.")
    differences = compare(stored_baseline, summary)
    if not differences:
        print(f"Identical to the baseline at {baseline_path} in every compared field.")
        return 0
    report = "\n".join(f"  {line}" for line in differences)
    (run.root / "baseline-diff.txt").write_text(report + "\n", encoding="utf-8")
    print(f"\n{len(differences)} field(s) differ from the baseline:\n{report}")
    print("\nIf these changes are intended, rerun with --update-baseline.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
