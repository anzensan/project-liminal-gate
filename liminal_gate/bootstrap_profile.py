"""The compatibility-profile contract: schema constants, types, and loading.

Split out of ``bootstrap_server`` so the profile schema can be read on its
own; every name here is imported back into that module, whose public and
test-visible surface is unchanged. This module must never import the server.

One deliberate absence: ``_select_tutorial_response`` stays in
``bootstrap_server`` because it draws from ``random.SystemRandom``, and tests
retarget randomness through that module's attributes.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Callable


PROFILE_SCHEMA_VERSION = 1

# Profile route names accepted by the mutation transport. Keeping this list in
# one place makes an added route explicit: it must be admitted here, dispatched
# below, and assigned a result status rather than accidentally falling through.
MUTATION_ROUTE_NAMES = frozenset({
    "do_slot",
    "userdata",
    "start_quest",
    "clear_quest",
    "continue",
    "change_uname",
    "refill_stamina",
    "unlock_metal_zone",
    "achived",
    "read_messages",
    "delete_messages",
    "exchange",
    "add_exchange_count",
    "statusup_item",
    "add_job",
    "rebirth",
    "summon_skill_unlock",
    "sell_buddy",
    "sell_buddies",
    "buddy_strengthen",
    "buddy_evolve",
    "do_buddy_slot",
})

READ_ROUTE_NAMES = frozenset({
    "time",
    "status",
    "signup",
    "login",
    "userdata",
    "userdata_after_close",
    "multiplay_enable",
    "special_event",
    "get_current_exchange",
})

SUPPORTED_PROFILE_OPERATIONS = READ_ROUTE_NAMES | MUTATION_ROUTE_NAMES
TEMPLATED_RESPONSE_OPERATIONS = frozenset({
    "signup",
    "login",
    "status",
    "multiplay_enable",
    "special_event",
})


class ProfileError(ValueError):
    """A user-local compatibility profile is malformed."""


@dataclass(frozen=True)
class SigningProfile:
    salt: str
    digest_start: int
    digest_end: int


@dataclass(frozen=True)
class BootstrapProfile:
    routes: dict[str, str]
    signing: SigningProfile
    account_binding: dict[str, str]
    responses: dict[str, dict[str, Any]]
    userdata_seed: dict[str, Any]
    tutorial_summons: tuple[dict[str, Any], ...]
    tutorial_writes: tuple[dict[str, Any], ...]
    story_starts: tuple[dict[str, Any], ...]
    story_clears: tuple[dict[str, Any], ...]
    structural_writes: tuple[dict[str, Any], ...]
    continue_policy: dict[str, int]


@dataclass
class MutationDispatch:
    """The operation selected for one authenticated mutation request.

    Profile-backed tutorial routes begin unresolved and are arbitrated against
    the more specific catalog handlers afterwards. Dedicated state operations
    carry their result immediately.
    """

    kind: str
    transitions: tuple[dict[str, Any], ...] = ()
    result: str | None = None
    payload: dict[str, Any] | None = None


MutationOperation = Callable[[], tuple[str, dict[str, Any] | None]]
BODY_TRANSITION_FIELDS = frozenset({"body", "phase", "next_phase", "response"})
TUTORIAL_SUMMON_BASE_FIELDS = frozenset({"body", "phase", "next_phase"})
TUTORIAL_SUMMON_OUTCOME_FIELDS = frozenset({
    "weight", "starter_character_id", "recruit_character_id", "response",
})
TUTORIAL_STARTER_TOKEN = "{{tutorial_starter_id}}"
#: The tutorial's scripted recruit completes the Circle of Carnage against the
#: starter the first Pact granted, so it is not one identity but one per
#: outcome: the client picks the completing class itself and animates recruiting
#: it, and a server that answers with a different character overwrites what the
#: player was just shown.  Declaring it beside ``starter_character_id`` keeps
#: the pairing in the profile rather than encoding a class rule in code.
TUTORIAL_RECRUIT_TOKEN = "{{tutorial_recruit_id}}"
#: Saves written before the recruit was declared per outcome were granted this
#: character on every path, whichever starter they hold.  It is what those
#: accounts actually own, so it is the only continuation that still matches the
#: client's own roster.
LEGACY_TUTORIAL_RECRUIT_ID = 63
STRUCTURAL_TRANSITION_FIELDS = frozenset({
    "field_names",
    "fixed_fields",
    "json_fields",
    "phase",
    "next_phase",
    "response",
    "userdata_update",
})
VALID_JSON_FIELD_KINDS = frozenset({"object", "array"})


def _valid_body_transition(item: object) -> bool:
    return (
        isinstance(item, dict)
        and item.keys() == BODY_TRANSITION_FIELDS
        and isinstance(item["body"], str)
        and isinstance(item["phase"], str)
        and isinstance(item["next_phase"], str)
        and isinstance(item["response"], dict)
    )


def _valid_tutorial_summon_transition(item: object) -> bool:
    if not isinstance(item, dict):
        return False
    fields = frozenset(item)
    if fields == BODY_TRANSITION_FIELDS:
        return _valid_body_transition(item)
    if fields != TUTORIAL_SUMMON_BASE_FIELDS | {"outcomes"}:
        return False
    outcomes = item["outcomes"]
    return (
        isinstance(item["body"], str)
        and isinstance(item["phase"], str)
        and isinstance(item["next_phase"], str)
        and isinstance(outcomes, list)
        and bool(outcomes)
        and all(
            isinstance(outcome, dict)
            and frozenset(outcome) == TUTORIAL_SUMMON_OUTCOME_FIELDS
            and type(outcome["weight"]) is int
            and outcome["weight"] > 0
            and type(outcome["starter_character_id"]) is int
            and outcome["starter_character_id"] > 0
            and type(outcome["recruit_character_id"]) is int
            and outcome["recruit_character_id"] > 0
            and isinstance(outcome["response"], dict)
            and isinstance(outcome["response"].get("chrdata"), list)
            and len(outcome["response"]["chrdata"]) == 1
            and outcome["response"]["chrdata"][0].get("id")
                == outcome["starter_character_id"]
            and isinstance(outcome["response"].get("teamMembers"), list)
            and outcome["response"]["teamMembers"]
                == [outcome["starter_character_id"]]
            for outcome in outcomes
        )
    )


def _tutorial_starter_id(account: dict[str, Any]) -> int:
    """Resolve new explicit starter state or an older Grace-only save."""
    stored = account.get("tutorial_starter_character_id")
    if type(stored) is int and stored > 0:
        return stored
    for row in account.get("userdata", {}).get("chrdata", []):
        if isinstance(row, dict) and row.get("id") in {1, 3}:
            return int(row["id"])
    # Saves made before the weighted rule have no field and could only contain
    # the old deterministic Grace path.
    return 3


def _tutorial_recruit_id(account: dict[str, Any]) -> int:
    """Resolve the recruit paired with this account's durable starter."""
    stored = account.get("tutorial_recruit_character_id")
    if type(stored) is int and stored > 0:
        return stored
    return LEGACY_TUTORIAL_RECRUIT_ID


def _resolve_tutorial_template(
    value: Any, starter_character_id: int, recruit_character_id: int,
) -> Any:
    """Resolve the durable starter and recruit in tutorial projections."""
    if isinstance(value, str):
        if value == TUTORIAL_STARTER_TOKEN:
            return starter_character_id
        if value == TUTORIAL_RECRUIT_TOKEN:
            return recruit_character_id
        return (
            value
            .replace(TUTORIAL_STARTER_TOKEN, str(starter_character_id))
            .replace(TUTORIAL_RECRUIT_TOKEN, str(recruit_character_id))
        )
    if isinstance(value, list):
        return [
            _resolve_tutorial_template(item, starter_character_id, recruit_character_id)
            for item in value
        ]
    if isinstance(value, dict):
        return {
            key: _resolve_tutorial_template(item, starter_character_id, recruit_character_id)
            for key, item in value.items()
        }
    return copy.deepcopy(value)


def _valid_structural_transition(item: object) -> bool:
    return (
        isinstance(item, dict)
        and item.keys() == STRUCTURAL_TRANSITION_FIELDS
        and isinstance(item["field_names"], list)
        and bool(item["field_names"])
        and all(isinstance(name, str) and name for name in item["field_names"])
        and isinstance(item["fixed_fields"], dict)
        and all(
            isinstance(name, str) and isinstance(value, str)
            for name, value in item["fixed_fields"].items()
        )
        and isinstance(item["json_fields"], dict)
        and all(
            isinstance(name, str) and kind in VALID_JSON_FIELD_KINDS
            for name, kind in item["json_fields"].items()
        )
        and isinstance(item["phase"], str)
        and isinstance(item["next_phase"], str)
        and isinstance(item["response"], dict)
        and isinstance(item["userdata_update"], dict)
    )


def load_profile(path: Path) -> BootstrapProfile:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError("could not read compatibility profile") from error
    if not isinstance(document, dict) or document.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ProfileError(f"schema_version must be {PROFILE_SCHEMA_VERSION}")
    routes = document.get("routes")
    if (
        not isinstance(routes, dict)
        or not routes
        or not set(routes) <= SUPPORTED_PROFILE_OPERATIONS
    ):
        raise ProfileError("routes must define a nonempty subset of supported bootstrap operations")
    if not all(isinstance(path, str) and path.startswith("/") for path in routes.values()):
        raise ProfileError("every route must be an absolute path")
    if len(set(routes.values())) != len(routes):
        raise ProfileError("routes must be unique")
    raw_signing = document.get("response_signing")
    if not isinstance(raw_signing, dict) or raw_signing.get("algorithm") != "md5-uppercase-slice":
        raise ProfileError("response_signing algorithm must be md5-uppercase-slice")
    salt = raw_signing.get("salt")
    digest_start = raw_signing.get("digest_start")
    digest_end = raw_signing.get("digest_end")
    if not isinstance(salt, str) or not salt or type(digest_start) is not int or type(digest_end) is not int:
        raise ProfileError("response_signing requires salt, digest_start, and digest_end")
    if not 0 <= digest_start < digest_end <= 32:
        raise ProfileError("response signing slice must be inside MD5 output")
    needs_account_binding = "signup" in routes or "login" in routes
    account_binding = document.get("account_binding", {})
    if needs_account_binding and (not isinstance(account_binding, dict) or set(account_binding) != {"signup_response_field", "login_query_field"}):
        raise ProfileError("account_binding must define signup_response_field and login_query_field")
    if not needs_account_binding and account_binding != {}:
        raise ProfileError("account_binding is only valid when signup or login is enabled")
    if not all(isinstance(value, str) and value for value in account_binding.values()):
        raise ProfileError("account_binding values must be nonempty strings")
    responses = document.get("responses")
    required_responses = TEMPLATED_RESPONSE_OPERATIONS & routes.keys()
    if not isinstance(responses, dict) or set(responses) != required_responses:
        raise ProfileError("responses must define exactly the enabled signup, login, and status operations")
    if not all(isinstance(value, dict) for value in responses.values()):
        raise ProfileError("every response template must be an object")
    userdata_seed = document.get("userdata_seed", {})
    if "signup" in routes and not isinstance(userdata_seed, dict):
        raise ProfileError("userdata_seed must be an object when signup is enabled")
    if "signup" not in routes and userdata_seed != {}:
        raise ProfileError("userdata_seed is only valid when signup is enabled")
    tutorial_summons = document.get("tutorial_summons", [])
    if "do_slot" in routes:
        if not isinstance(tutorial_summons, list) or not tutorial_summons:
            raise ProfileError("tutorial_summons must be a nonempty list when do_slot is enabled")
        if not all(
            isinstance(item, dict)
            and frozenset(item) in {
                BODY_TRANSITION_FIELDS,
                TUTORIAL_SUMMON_BASE_FIELDS | {"outcomes"},
            }
            for item in tutorial_summons
        ):
            raise ProfileError(
                "every tutorial summon must define body, phase, next_phase, "
                "and either response or outcomes"
            )
        if not all(_valid_tutorial_summon_transition(item) for item in tutorial_summons):
            raise ProfileError("tutorial summon values have invalid types")
        if len({item["body"] for item in tutorial_summons}) != len(tutorial_summons):
            raise ProfileError("tutorial summon bodies must be unique")
    elif tutorial_summons != []:
        raise ProfileError("tutorial_summons is only valid when do_slot is enabled")
    tutorial_writes = document.get("tutorial_writes", [])
    if not isinstance(tutorial_writes, list):
        raise ProfileError("tutorial_writes must be a list")
    required_write_fields = {"fields", "phase", "next_phase", "response", "userdata_update"}
    if not all(isinstance(item, dict) and set(item) == required_write_fields for item in tutorial_writes):
        raise ProfileError("every tutorial write must define fields, phase, next_phase, response, and userdata_update")
    if not all(
        isinstance(item["fields"], list)
        and item["fields"]
        and all(isinstance(pair, list) and len(pair) == 2 and all(isinstance(value, str) for value in pair) for pair in item["fields"])
        and isinstance(item["phase"], str)
        and isinstance(item["next_phase"], str)
        and isinstance(item["response"], dict)
        and isinstance(item["userdata_update"], dict)
        for item in tutorial_writes
    ):
        raise ProfileError("tutorial write values have invalid types")
    story_starts = document.get("story_starts", [])
    if "start_quest" in routes:
        if not isinstance(story_starts, list) or not story_starts:
            raise ProfileError("story_starts must be a nonempty list when start_quest is enabled")
        if not all(
            isinstance(item, dict) and item.keys() == BODY_TRANSITION_FIELDS
            for item in story_starts
        ):
            raise ProfileError("every story start must define body, phase, next_phase, and response")
        if not all(_valid_body_transition(item) for item in story_starts):
            raise ProfileError("story start values have invalid types")
        if len({item["body"] for item in story_starts}) != len(story_starts):
            raise ProfileError("story start bodies must be unique")
    elif story_starts != []:
        raise ProfileError("story_starts is only valid when start_quest is enabled")
    story_clears = document.get("story_clears", [])
    if "clear_quest" in routes:
        if not isinstance(story_clears, list) or not story_clears:
            raise ProfileError("story_clears must be a nonempty list when clear_quest is enabled")
        if not all(
            isinstance(item, dict) and item.keys() == STRUCTURAL_TRANSITION_FIELDS
            for item in story_clears
        ):
            raise ProfileError("every story clear has invalid fields")
        if not all(_valid_structural_transition(item) for item in story_clears):
            raise ProfileError("story clear values have invalid types")
        if len({(tuple(item["field_names"]), item["phase"]) for item in story_clears}) != len(story_clears):
            raise ProfileError("story clear field/phase combinations must be unique")
    elif story_clears != []:
        raise ProfileError("story_clears is only valid when clear_quest is enabled")
    structural_writes = document.get("structural_writes", [])
    if not isinstance(structural_writes, list):
        raise ProfileError("structural_writes must be a list")
    if not all(
        isinstance(item, dict) and item.keys() == STRUCTURAL_TRANSITION_FIELDS
        for item in structural_writes
    ):
        raise ProfileError("every structural write has invalid fields")
    if not all(_valid_structural_transition(item) for item in structural_writes):
        raise ProfileError("structural write values have invalid types")
    continue_policy = document.get("continue_policy", {})
    if "continue" in routes:
        if (
            not isinstance(continue_policy, dict)
            or set(continue_policy) != {"client_cost", "coin_cost"}
            or any(type(value) is not int for value in continue_policy.values())
            or continue_policy["client_cost"] != 1
            or continue_policy["coin_cost"] <= 0
        ):
            raise ProfileError("continue_policy must declare client_cost=1 and a positive coin_cost")
    elif continue_policy != {}:
        raise ProfileError("continue_policy is only valid when continue is enabled")
    return BootstrapProfile(
        routes=dict(routes),
        signing=SigningProfile(salt, digest_start, digest_end),
        account_binding=dict(account_binding),
        responses=copy.deepcopy(responses),
        userdata_seed=copy.deepcopy(userdata_seed),
        tutorial_summons=tuple(copy.deepcopy(tutorial_summons)),
        tutorial_writes=tuple(copy.deepcopy(tutorial_writes)),
        story_starts=tuple(copy.deepcopy(story_starts)),
        story_clears=tuple(copy.deepcopy(story_clears)),
        structural_writes=tuple(copy.deepcopy(structural_writes)),
        continue_policy=copy.deepcopy(continue_policy),
    )
