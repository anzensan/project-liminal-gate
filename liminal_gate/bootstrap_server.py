"""Profile-driven bootstrap compatibility server with local durable state.

The engine can serve either a bundled, narrowly reviewed profile or a
user-local compatibility profile. Each profile declares only the operations it
actually supports; every other route deliberately remains unsupported.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import dataclass
import hashlib
import json
import math
import os
import random
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
from threading import Lock
import time
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from liminal_gate.resource_catalog import ResourceCatalog, ResourceCatalogError, load_resource_catalog
from liminal_gate.companion_catalog import CompanionCatalog, CompanionCatalogError, load_companion_catalog
from liminal_gate.companion_strengthen_catalog import CompanionStrengthenCatalog, CompanionStrengthenCatalogError, load_companion_strengthen_catalog
from liminal_gate.clear_state_catalog import ClearStateCatalog, ClearStateCatalogError, load_clear_state_catalog
from liminal_gate.companion_evolution_catalog import CompanionEvolutionCatalog, CompanionEvolutionCatalogError, load_companion_evolution_catalog
from liminal_gate.companion_draw_catalog import CompanionDrawCatalog, CompanionDrawCatalogError, load_companion_draw_catalog
from liminal_gate.pact_draw_catalog import BundledPactPolicy, PactDrawCatalog, PactDrawCatalogError, build_bundled_pact_policy, load_pact_draw_catalog
from liminal_gate.achievement_catalog import AchievementCatalog, AchievementCatalogError, load_achievement_catalog
from liminal_gate.message_catalog import MessageCatalog, MessageCatalogError, load_message_catalog
from liminal_gate.exchange_catalog import ExchangeCatalog, ExchangeCatalogError, load_exchange_catalog
from liminal_gate.server_config import ServerConfig, ServerConfigError, load_server_config
from liminal_gate.rebirth_catalog import RebirthCatalog, RebirthCatalogError, load_rebirth_catalog
from liminal_gate.job_catalog import JobCatalog, JobCatalogError, load_job_catalog
from liminal_gate.settlement_catalog import SettlementCatalog, SettlementCatalogError, load_settlement_catalog
from liminal_gate.statusup_catalog import StatusupCatalog, StatusupCatalogError, load_statusup_catalog
from liminal_gate.story_catalog import StoryCatalog, StoryCatalogError, StoryStage, load_story_catalog
from liminal_gate.story_progression_catalog import StoryProgressionCatalog, StoryProgressionCatalogError, build_core_story_policy, load_story_progression_catalog
from liminal_gate.story_outcome_catalog import StoryOutcomeCatalog, StoryOutcomeCatalogError, allowed as outcome_allowed, load_story_outcome_catalog
from liminal_gate.summon_skill_catalog import SummonSkillCatalog, SummonSkillCatalogError, load_summon_skill_catalog


PROFILE_SCHEMA_VERSION = 1
PACT_BANNER_FILES = {
    "/public_data/banners/sl_truth_01_en.png": "sl_truth_01_en.png",
    "/public_data/banners/slb_truth_01_en.png": "slb_truth_01_en.png",
    "/public_data/banners/sl_friend_01_en.png": "sl_friend_01_en.png",
    "/public_data/banners/slb_friend_01_en.png": "slb_friend_01_en.png",
    "/public_data/banners/sl_luck_01_en.png": "sl_truth_01_en.png",
}


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


def load_profile(path: Path) -> BootstrapProfile:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ProfileError("could not read compatibility profile") from error
    if not isinstance(document, dict) or document.get("schema_version") != PROFILE_SCHEMA_VERSION:
        raise ProfileError(f"schema_version must be {PROFILE_SCHEMA_VERSION}")
    routes = document.get("routes")
    supported_operations = {
        "time", "status", "signup", "login", "userdata", "userdata_after_close",
        "multiplay_enable", "special_event", "do_slot", "start_quest", "clear_quest",
        "continue", "change_uname", "refill_stamina", "unlock_metal_zone", "achived", "read_messages", "delete_messages", "get_current_exchange", "exchange", "add_exchange_count", "statusup_item", "add_job", "rebirth", "summon_skill_unlock", "sell_buddy", "sell_buddies", "buddy_strengthen", "buddy_evolve", "do_buddy_slot",
    }
    if not isinstance(routes, dict) or not routes or not set(routes) <= supported_operations:
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
    required_responses = {operation for operation in ("signup", "login", "status", "multiplay_enable", "special_event") if operation in routes}
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
        required_summon_fields = {"body", "phase", "next_phase", "response"}
        if not all(isinstance(item, dict) and set(item) == required_summon_fields for item in tutorial_summons):
            raise ProfileError("every tutorial summon must define body, phase, next_phase, and response")
        if not all(
            isinstance(item["body"], str)
            and isinstance(item["phase"], str)
            and isinstance(item["next_phase"], str)
            and isinstance(item["response"], dict)
            for item in tutorial_summons
        ):
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
        required_start_fields = {"body", "phase", "next_phase", "response"}
        if not all(isinstance(item, dict) and set(item) == required_start_fields for item in story_starts):
            raise ProfileError("every story start must define body, phase, next_phase, and response")
        if not all(
            isinstance(item["body"], str)
            and isinstance(item["phase"], str)
            and isinstance(item["next_phase"], str)
            and isinstance(item["response"], dict)
            for item in story_starts
        ):
            raise ProfileError("story start values have invalid types")
        if len({item["body"] for item in story_starts}) != len(story_starts):
            raise ProfileError("story start bodies must be unique")
    elif story_starts != []:
        raise ProfileError("story_starts is only valid when start_quest is enabled")
    story_clears = document.get("story_clears", [])
    if "clear_quest" in routes:
        if not isinstance(story_clears, list) or not story_clears:
            raise ProfileError("story_clears must be a nonempty list when clear_quest is enabled")
        required_clear_fields = {"field_names", "fixed_fields", "json_fields", "phase", "next_phase", "response", "userdata_update"}
        if not all(isinstance(item, dict) and set(item) == required_clear_fields for item in story_clears):
            raise ProfileError("every story clear has invalid fields")
        valid_json_kinds = {"object", "array"}
        if not all(
            isinstance(item["field_names"], list)
            and item["field_names"]
            and all(isinstance(name, str) and name for name in item["field_names"])
            and isinstance(item["fixed_fields"], dict)
            and all(isinstance(name, str) and isinstance(value, str) for name, value in item["fixed_fields"].items())
            and isinstance(item["json_fields"], dict)
            and all(isinstance(name, str) and kind in valid_json_kinds for name, kind in item["json_fields"].items())
            and isinstance(item["phase"], str)
            and isinstance(item["next_phase"], str)
            and isinstance(item["response"], dict)
            and isinstance(item["userdata_update"], dict)
            for item in story_clears
        ):
            raise ProfileError("story clear values have invalid types")
        if len({(tuple(item["field_names"]), item["phase"]) for item in story_clears}) != len(story_clears):
            raise ProfileError("story clear field/phase combinations must be unique")
    elif story_clears != []:
        raise ProfileError("story_clears is only valid when clear_quest is enabled")
    structural_writes = document.get("structural_writes", [])
    if not isinstance(structural_writes, list):
        raise ProfileError("structural_writes must be a list")
    required_structural_fields = {"field_names", "fixed_fields", "json_fields", "phase", "next_phase", "response", "userdata_update"}
    if not all(isinstance(item, dict) and set(item) == required_structural_fields for item in structural_writes):
        raise ProfileError("every structural write has invalid fields")
    valid_json_kinds = {"object", "array"}
    if not all(
        isinstance(item["field_names"], list) and item["field_names"]
        and all(isinstance(name, str) and name for name in item["field_names"])
        and isinstance(item["fixed_fields"], dict)
        and all(isinstance(name, str) and isinstance(value, str) for name, value in item["fixed_fields"].items())
        and isinstance(item["json_fields"], dict)
        and all(isinstance(name, str) and kind in valid_json_kinds for name, kind in item["json_fields"].items())
        and isinstance(item["phase"], str) and isinstance(item["next_phase"], str)
        and isinstance(item["response"], dict) and isinstance(item["userdata_update"], dict)
        for item in structural_writes
    ):
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


class BootstrapState:
    """Atomic local account state for the extracted bootstrap sequence."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = Lock()
        self.tokens: dict[str, str] = {}
        self.active_account_id: str | None = None
        self.accounts = self._load()

    def create_account(self, token: str, account_id: str, seed: dict[str, Any], message_catalog: MessageCatalog | None = None, exchange_catalog: ExchangeCatalog | None = None) -> None:
        with self.lock:
            if account_id not in self.accounts:
                self.accounts[account_id] = {
                    "userdata": copy.deepcopy(seed),
                    "tutorial_phase": "initial",
                    "tutorial_requests": {},
                    "initial_userdata_served": False,
                    "username": "Player",
                    "username_changed_at": 0.0,
                    "rebirth_used_material_ids": [],
                    "claimed_achievements": [],
                    "achievement_requests": {},
                    "messages": _initial_messages(message_catalog),
                    "message_requests": {},
                    "exchange_remaining": _initial_exchange_remaining(exchange_catalog),
                    "exchange_total": 0,
                    "exchange_requests": {},
                }
            changed = self.tokens.get(token) != account_id or self.active_account_id != account_id
            if self.tokens.get(token) != account_id:
                self.tokens[token] = account_id
            self.active_account_id = account_id
            if changed:
                self._persist_locked()

    def bind_login_token(self, token: str, account_id: str) -> bool:
        with self.lock:
            if account_id not in self.accounts:
                return False
            changed = self.tokens.get(token) != account_id or self.active_account_id != account_id
            if self.tokens.get(token) != account_id:
                self.tokens[token] = account_id
            self.active_account_id = account_id
            if changed:
                self._persist_locked()
            return True

    def bind_rotated_token(self, token: str) -> bool:
        """Bind a client-rotated OTK to the active local account.

        The surviving client replaces its OTK after the signup/login exchange,
        while later mutations carry only the replacement token.  Signup and
        login durably record that account as active, so a local state which has
        retained older test accounts can still resume the current client.  Old
        state files without that marker retain the conservative single-account
        fallback rather than guessing an owner.
        """
        with self.lock:
            account_id = self.active_account_id
            # A tester's emulator can retain an older OTK while the server
            # state has accumulated abandoned accounts from earlier setup
            # attempts.  This is a single-player local server: once signup or
            # login identifies the active save, route every subsequent client
            # token to that save rather than resurrecting an abandoned one.
            if account_id in self.accounts:
                if self.tokens.get(token) != account_id:
                    self.tokens[token] = account_id
                    self._persist_locked()
                return True
            if account_id is None and len(self.accounts) == 1:
                account_id = next(iter(self.accounts))
                self.active_account_id = account_id
            if account_id not in self.accounts:
                return False
            self.tokens[token] = account_id
            self._persist_locked()
            return True

    def userdata_for(self, token: str) -> dict[str, Any] | None:
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            if account is None:
                return None
            userdata = account["userdata"]
            changed = False
            # Older local saves retained the flattened currency mirror but not
            # the client-consumed userdata.valuables container. Project that
            # already-persisted local state once instead of returning a
            # zero-balance client default after a restart.
            if "valuables" not in userdata and type(userdata.get("coins")) is int:
                currency_fields = (
                    "energyAppStore", "energy", "energyAndApp", "freeEnergy",
                    "energyGooglePlay", "coins",
                )
                values = {name: userdata.get(name, 0) for name in currency_fields}
                if all(type(value) is int and value >= 0 for value in values.values()):
                    userdata["valuables"] = values
                    changed = True
            if not account.setdefault("initial_userdata_served", False):
                account["initial_userdata_served"] = True
                changed = True
            if changed:
                self._persist_locked()
            return copy.deepcopy(userdata)

    def change_uname(self, token: str, request_id: str, body: bytes) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return ("replay", copy.deepcopy(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None)
            name = _parse_change_uname(body)
            if name is None:
                return "unsupported_change_uname", None
            now = time.time()
            if account.get("username_changed_at", 0.0) and now - float(account["username_changed_at"]) < 30 * 86400:
                payload = {"errorCode": 1}
                requests[request_id] = {"body_sha256": digest, "payload": payload}
                self._persist_locked()
                return "success", payload
            account["username"] = name
            account["username_changed_at"] = now
            payload = {"success": True, "name": name, "changeUsernameDate": float(621355968000000000 + int(now * 10_000_000))}
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def refill_stamina(self, token: str, request_id: str, body: bytes) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (
                    ("replay", _ordered_refill_payload(cached["payload"]))
                    if cached.get("body_sha256") == digest
                    else ("request_collision", None)
                )
            if _parse_refill_stamina(body) != 1:
                return "unsupported_refill_stamina", None
            data = account["userdata"]
            # `0.0` is the client-visible local representation for a full
            # stamina meter.  The retired service's actual meter calculation
            # is not recovered, so a nonzero user-local refill origin means
            # this account needs a refill; it is not inferred from wallets.
            if data.get("refillStartTime") == 0.0:
                payload = {"success": False, "errorCode": 1}
            else:
                free, energy = int(data.get("freeEnergy", 0)), int(data.get("energy", 0))
                if free + energy < 1:
                    payload = {"success": False, "errorCode": 2}
                else:
                    data["freeEnergy"] = max(0, free - 1)
                    data["energy"] = max(0, energy - max(0, 1 - free))
                    data["refillStartTime"] = 0.0
                    payload = {
                        "success": True,
                        "refillStartTime": 0.0,
                        "energy": data["energy"],
                        "energyAppStore": int(data.get("energyAppStore", 0)),
                        "energyGooglePlay": int(data.get("energyGooglePlay", 0)),
                        "energyAndApp": int(data.get("energyAndApp", 0)),
                        "freeEnergy": data["freeEnergy"],
                        "bonusStamina": int(data.get("bonusStamina", 0)),
                    }
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def unlock_metal_zone(self, token: str, request_id: str, body: bytes) -> tuple[str, dict[str, Any] | None]:
        """Open the local Metal Zone window using the recovered empty POST form.

        The client-visible callback and one-Energy cost are recovered. The
        one-hour window is explicit local preservation policy, rather than a
        claim about the retired service's schedule.
        """
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return ("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None)
            if body != b"":
                return "unsupported_unlock_metal_zone", None
            data = account["userdata"]
            free, energy = int(data.get("freeEnergy", 0)), int(data.get("energy", 0))
            if free + energy < 1:
                payload: dict[str, Any] = {"success": False, "errorCode": 2}
            else:
                free_spend = min(1, free)
                free -= free_spend
                energy -= 1 - free_spend
                now = int(time.time())
                unlock_time = max(int(data.get("metalZoneUnlockTime", 0)), now) + 3600
                data["freeEnergy"] = free
                data["energy"] = energy
                data["metalZoneUnlockTime"] = float(unlock_time)
                payload = {
                    "success": True,
                    "metalZoneUnlockTime": float(unlock_time),
                    "energy": energy,
                    "energyAppStore": int(data.get("energyAppStore", 0)),
                    "energyGooglePlay": int(data.get("energyGooglePlay", 0)),
                    "energyAndApp": int(data.get("energyAndApp", 0)),
                    "freeEnergy": free,
                }
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def claim_achievement(self, token: str, request_id: str, body: bytes, catalog: AchievementCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            digest = hashlib.sha256(body).hexdigest()
            requests = account.setdefault("achievement_requests", {})
            cached = requests.get(request_id)
            if cached is not None:
                return ("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None)
            achievement_id = _parse_achievement_claim(body)
            if catalog is None or achievement_id is None:
                return "unsupported_achievement", None
            achievement = catalog.achievements.get(achievement_id)
            data = account["userdata"]
            claimed = account.setdefault("claimed_achievements", [])
            progress = data.get("progressCode", 0)
            if achievement is None or achievement_id in claimed or type(progress) is not int or ((progress & 0xFFFF) >> 6) <= achievement.required_chapter:
                return "invalid_local_achievement", None
            items = data.get("itemList")
            if not isinstance(items, list) or len(items) != catalog.item_slots or any(type(value) is not int or value < 0 for value in items):
                return "unsupported_achievement", None
            updated_items = list(items)
            for item_id, amount in achievement.items.items():
                updated_items[item_id - 1] = min(catalog.max_stack, updated_items[item_id - 1] + amount)
            data["itemList"] = updated_items
            data["freeEnergy"] = min(catalog.max_free_energy, int(data.get("freeEnergy", 0)) + achievement.free_energy)
            data["coins"] = min(catalog.max_coins, int(data.get("coins", 0)) + achievement.coins)
            claimed.append(achievement_id)
            claimed.sort()
            data["achivementFlags"] = _achievement_flags(claimed)
            payload = _canonical_payload({"achivementFlags": data["achivementFlags"], "freeEnergy": data["freeEnergy"], "coins": data["coins"], "itemList": updated_items})
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def login_messages(self, account_id: str) -> list[dict[str, Any]]:
        with self.lock:
            account = self.accounts.get(account_id)
            return [] if account is None else [_message_wire(message) for _, message in sorted(account.setdefault("messages", {}).items())]

    def read_messages(self, token: str, request_id: str, body: bytes, catalog: MessageCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            digest = hashlib.sha256(body).hexdigest()
            requests = account.setdefault("message_requests", {})
            cached = requests.get(request_id)
            if cached is not None:
                return ("replay", _canonical_payload(cached["payload"])) if cached.get("operation") == "read" and cached.get("body_sha256") == digest else ("request_collision", None)
            message_ids = _parse_message_ids(body)
            if catalog is None or message_ids is None:
                return "unsupported_message_read", None
            messages = account.setdefault("messages", {})
            selected = [messages.get(message_id) for message_id in message_ids]
            if any(message is None for message in selected):
                return "invalid_local_message", None
            data = account["userdata"]
            items = data.get("itemList")
            if not isinstance(items, list) or len(items) != catalog.item_slots or any(type(value) is not int or value < 0 for value in items):
                return "unsupported_message_read", None
            updated_items = list(items)
            coins, energy = int(data.get("coins", 0)), int(data.get("freeEnergy", 0))
            for message in selected:
                assert message is not None
                if message["read"]:
                    continue
                coins = min(catalog.max_coins, coins + message["coins"])
                energy = min(catalog.max_free_energy, energy + message["free_energy"])
                for item_id, amount in message["items"].items():
                    updated_items[int(item_id) - 1] = min(catalog.max_stack, updated_items[int(item_id) - 1] + amount)
                message["read"] = True
            data["coins"], data["freeEnergy"], data["itemList"] = coins, energy, updated_items
            payload = _canonical_payload({"result": True, "readlist": message_ids, "itemList": updated_items, "coins": coins, "energy": int(data.get("energy", 0)), "freeEnergy": energy, **_message_reload_projection(data, account)})
            requests[request_id] = {"operation": "read", "body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def delete_messages(self, token: str, request_id: str, body: bytes, catalog: MessageCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            digest = hashlib.sha256(body).hexdigest()
            requests = account.setdefault("message_requests", {})
            cached = requests.get(request_id)
            if cached is not None:
                return ("replay", _canonical_payload(cached["payload"])) if cached.get("operation") == "delete" and cached.get("body_sha256") == digest else ("request_collision", None)
            message_ids = _parse_message_ids(body)
            if catalog is None or message_ids is None:
                return "unsupported_message_delete", None
            messages = account.setdefault("messages", {})
            if any(message_id not in messages or not messages[message_id].get("read") for message_id in message_ids):
                return "invalid_local_message", None
            for message_id in message_ids:
                del messages[message_id]
            payload = {"deletelist": message_ids}
            requests[request_id] = {"operation": "delete", "body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def current_exchange(self, token: str, catalog: ExchangeCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None: return "unknown_account", None
            if catalog is None: return "unsupported_exchange", None
            remaining = account.setdefault("exchange_remaining", _initial_exchange_remaining(catalog))
            offers = [{"ID": offer.offer_id, "targetItemID": offer.target_item_id, "targetBuddyID": 0, "coins": offer.coins, "targetCount": offer.target_count, "count": remaining.get(str(offer.offer_id), offer.initial_count), "weeklyItemCount": offer.weekly_item_count, "items": [[item_id, count] for item_id, count in sorted(offer.ingredients.items())]} for offer in catalog.offers.values()]
            return "success", {"totalCount": account.setdefault("exchange_total", 0), "itemList": [{"weeklyItem": catalog.weekly_item, "endDate": catalog.end_date, "items": offers}] if offers else []}

    def exchange(self, token: str, request_id: str, body: bytes, catalog: ExchangeCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None: return "unknown_account", None
            digest=hashlib.sha256(body).hexdigest(); cache=account.setdefault("exchange_requests", {}).get(request_id)
            if cache is not None: return ("replay", _canonical_payload(cache["payload"])) if cache.get("body_sha256")==digest else ("request_collision",None)
            request=_parse_exchange(body)
            if catalog is None or request is None: return "unsupported_exchange",None
            offer=catalog.offers.get(request[0]); data=account["userdata"]
            items=data.get("itemList"); remaining=account.setdefault("exchange_remaining",_initial_exchange_remaining(catalog))
            if offer is None or not isinstance(items,list) or len(items)!=catalog.item_slots: return "invalid_local_exchange",None
            amount=request[1]; stock=remaining.get(str(offer.offer_id),offer.initial_count)
            if amount>stock: payload={"success":False,"errorCode":6}
            elif any(type(items[i-1]) is not int or items[i-1]<n*amount for i,n in offer.ingredients.items()): payload={"success":False,"errorCode":3}
            elif items[offer.target_item_id-1]+offer.target_count*amount>catalog.max_stack: payload={"success":False,"errorCode":4}
            else:
                updated=list(items)
                for item_id,count in offer.ingredients.items(): updated[item_id-1]-=count*amount
                updated[offer.target_item_id-1]+=offer.target_count*amount
                remaining[str(offer.offer_id)]=stock-amount; account["exchange_total"]+=amount; data["itemList"]=updated
                payload={"success":True,"buddyInfo":copy.deepcopy(data.get("buddyInfo",{"list":[],"record":[]})),"itemList":updated,"coins":int(data.get("coins",0)),"totalCount":account["exchange_total"],"remainCount":remaining[str(offer.offer_id)]}
            payload = _canonical_payload(payload)
            account["exchange_requests"][request_id]={"body_sha256":digest,"payload":copy.deepcopy(payload)}; self._persist_locked(); return "success",payload

    def use_statusup_item(
        self, token: str, request_id: str, body: bytes, catalog: StatusupCatalog | None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Apply one user-catalogued status item without imported master data."""
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (
                    ("replay", _canonical_payload(cached["payload"]))
                    if cached.get("body_sha256") == digest
                    else ("request_collision", None)
                )
            values = _parse_statusup_item(body)
            if catalog is None or values is None:
                return "unsupported_statusup_item", None
            target_id, item_id, amount = values
            userdata = account["userdata"]
            rows = userdata.get("chrdata")
            items = userdata.get("itemList")
            target = catalog.characters.get(target_id)
            effect = catalog.items.get(item_id)
            if effect is None:
                payload = {"success": False, "errorCode": 2}
            elif target is None:
                payload = {"success": False, "errorCode": 4}
            elif effect.species is not None and effect.species != target.species:
                payload = {"success": False, "errorCode": 3}
            elif not isinstance(rows, list) or not isinstance(items, list) or len(items) != catalog.item_slots or item_id > len(items):
                return "unsupported_statusup_item", None
            elif not isinstance(items[item_id - 1], int) or items[item_id - 1] < amount:
                payload = {"success": False, "errorCode": 1}
            else:
                row = next((item for item in rows if isinstance(item, dict) and item.get("id") == target_id), None)
                if row is None or not isinstance(row.get("jobLevels"), list):
                    payload = {"success": False, "errorCode": 4}
                else:
                    changed, deltas = _apply_statusup_effect(row, effect, target, catalog, amount)
                    if changed is None:
                        payload = {"success": False, "errorCode": 3}
                    else:
                        rows[rows.index(row)] = changed
                        items[item_id - 1] -= amount
                        payload = {
                            "chrdata": copy.deepcopy(rows),
                            "itemList": copy.deepcopy(items),
                            "resultValues": deltas,
                        }
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def add_job(self, token: str, request_id: str, body: bytes, catalog: JobCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            target_id = _parse_add_job(body)
            if catalog is None or target_id is None:
                return "unsupported_add_job", None
            userdata = account["userdata"]
            rows, items = userdata.get("chrdata"), userdata.get("itemList")
            row = next((item for item in rows if isinstance(item, dict) and item.get("id") == target_id), None) if isinstance(rows, list) else None
            if row is None or not isinstance(row.get("jobLevels"), list):
                payload = {"success": True, "cmdError": 4}
            else:
                levels = row["jobLevels"]
                next_index = next((index for index, value in enumerate(levels) if type(value) in {int, float} and int(value) == 0), None)
                rule = None if next_index is None else catalog.unlocks.get((target_id, next_index))
                if rule is None or not isinstance(items, list) or len(items) != catalog.item_slots:
                    payload = {"success": True, "cmdError": 4}
                elif type(userdata.get("coins", 0)) is not int or userdata.get("coins", 0) < rule.coins:
                    payload = {"success": True, "cmdError": 2}
                elif any(item_id > len(items) or type(items[item_id - 1]) is not int or items[item_id - 1] < count for item_id, count in rule.materials.items()):
                    payload = {"success": True, "cmdError": 3}
                else:
                    candidate = copy.deepcopy(row)
                    candidate["jobLevels"][next_index] = 1.0
                    new_items = copy.deepcopy(items)
                    for item_id, count in rule.materials.items():
                        new_items[item_id - 1] -= count
                    rows[rows.index(row)] = candidate
                    userdata["itemList"] = new_items
                    userdata["coins"] -= rule.coins
                    payload = {"success": True, "chrdata": candidate, "itemList": new_items, "coins": userdata["coins"], "energy": int(userdata.get("energy", 0)), "freeEnergy": int(userdata.get("freeEnergy", 0))}
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def rebirth(self, token: str, request_id: str, body: bytes, catalog: RebirthCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest(); cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            request = _parse_rebirth(body)
            if catalog is None or request is None:
                return "unsupported_rebirth", None
            recipe_id, use_joker = request; recipe = catalog.recipes.get(recipe_id)
            data = account["userdata"]; rows, items = data.get("chrdata"), data.get("itemList")
            source = next((row for row in rows if isinstance(row, dict) and recipe and row.get("id") == recipe.source_character_id), None) if isinstance(rows, list) else None
            if recipe is None or source is None:
                payload = {"success": False, "errorCode": 6}
            elif not isinstance(source.get("jobLevels"), list) or any(type(value) not in {int, float} or int(value) & 0xFFF < 80 for value in source["jobLevels"] if int(value) != 0):
                payload = {"success": False, "errorCode": 1}
            elif type(data.get("coins", 0)) is not int or data.get("coins", 0) < recipe.coins:
                payload = {"success": False, "errorCode": 2}
            elif not isinstance(items, list) or len(items) != catalog.item_slots or any(item_id > len(items) or type(items[item_id - 1]) is not int or items[item_id - 1] < count for item_id, count in recipe.items.items()):
                payload = {"success": False, "errorCode": 3}
            else:
                used = set(account.setdefault("rebirth_used_material_ids", [])); missing = False
                for material_id, level in recipe.materials:
                    material = next((row for row in rows if isinstance(row, dict) and row.get("id") == material_id), None)
                    if material_id in used: payload = {"success": False, "errorCode": 5}; break
                    if material is None or not isinstance(material.get("jobLevels"), list) or max((int(value) & 0xFFF for value in material["jobLevels"]), default=0) < level: missing = True
                else:
                    joker = next((row for row in rows if isinstance(row, dict) and row.get("id") == catalog.joker_character_id), None)
                    if missing and not use_joker: payload = {"success": False, "errorCode": 7 if joker is not None and catalog.joker_character_id not in used else 4}
                    elif missing and (joker is None or catalog.joker_character_id in used): payload = {"success": False, "errorCode": 4}
                    else:
                        new_rows = [copy.deepcopy(row) for row in rows if row is not source and row.get("id") != recipe.destination_character_id]
                        destination = copy.deepcopy(source); destination.update({"id": recipe.destination_character_id, "jobLevels": [1.0, 0.0, 0.0], "jobID": 0, "buddy": 0})
                        new_rows.append(destination); new_rows.sort(key=lambda row: int(row["id"]))
                        new_items = copy.deepcopy(items)
                        for item_id, count in recipe.items.items(): new_items[item_id - 1] -= count
                        used.update(material_id for material_id, _ in recipe.materials); used.update({catalog.joker_character_id} if missing and use_joker else set())
                        data["chrdata"], data["itemList"], data["coins"], account["rebirth_used_material_ids"] = new_rows, new_items, data["coins"] - recipe.coins, sorted(used)
                        payload = {"success": True, "buddyInfo": {"list": [], "record": []}, "chrdata": copy.deepcopy(new_rows), "itemList": new_items, "coins": data["coins"], "overlapped": False}
            payload = _canonical_payload(payload); requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}; self._persist_locked(); return "success", payload

    def apply_tutorial_transition(
        self,
        token: str,
        request_id: str,
        body: bytes,
        transitions: tuple[dict[str, Any], ...],
        *,
        kind: str,
    ) -> tuple[str, dict[str, Any] | None]:
        """Atomically settle or replay one profile-declared tutorial transition."""
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            body_hash = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                if cached.get("body_sha256") != body_hash:
                    return "request_collision", None
                return "replay", copy.deepcopy(cached["payload"])
            if kind in {"summon", "start"}:
                transition = next(
                    (item for item in transitions if item["body"].encode("utf-8") == body), None
                )
            elif kind in {"clear", "structural"}:
                try:
                    fields = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
                except (UnicodeDecodeError, ValueError):
                    fields = ()
                values = dict(fields)
                candidates = [
                    item for item in transitions
                    if tuple(name for name, _ in fields) == tuple(item["field_names"])
                    and all(values.get(name) == value for name, value in item["fixed_fields"].items())
                    and _json_fields_match(values, item["json_fields"])
                ]
                transition = next(
                    (item for item in candidates if item["phase"] == account.setdefault("tutorial_phase", "initial")),
                    candidates[0] if candidates else None,
                )
            else:
                try:
                    decoded_fields = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
                except (UnicodeDecodeError, ValueError):
                    decoded_fields = ()
                transition = next(
                    (item for item in transitions if tuple((name, value) for name, value in item["fields"]) == decoded_fields),
                    None,
                )
            if transition is None:
                errors = {
                    "summon": "unsupported_summon",
                    "write": "unsupported_userdata_write",
                    "start": "unsupported_start_quest",
                    "clear": "unsupported_clear_quest",
                }
                return errors.get(kind, "unsupported_userdata_write"), None
            if transition["phase"] == "initial" and not account.setdefault("initial_userdata_served", False):
                return "tutorial_state_conflict", None
            if account.setdefault("tutorial_phase", "initial") != transition["phase"]:
                return "tutorial_state_conflict", None
            payload = copy.deepcopy(transition["response"])
            userdata = account["userdata"]
            if kind == "summon" and "chrdata" in payload:
                existing = {item.get("id"): item for item in userdata.get("chrdata", []) if isinstance(item, dict)}
                existing.update({item["id"]: copy.deepcopy(item) for item in payload["chrdata"]})
                userdata["chrdata"] = list(existing.values())
            if kind == "summon" and "teamMembers" in payload:
                userdata["teamMembers"] = copy.deepcopy(payload["teamMembers"])
            if kind == "write":
                userdata.update(copy.deepcopy(transition["userdata_update"]))
            if kind in {"clear", "structural"}:
                userdata.update(copy.deepcopy(transition["userdata_update"]))
            if kind == "clear" and "chrdata" in payload:
                userdata["chrdata"] = copy.deepcopy(payload["chrdata"])
            account["tutorial_phase"] = transition["next_phase"]
            requests[request_id] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def summon_skill_unlock(self, token: str, request_id: str, body: bytes, catalog: SummonSkillCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            target_id = _parse_summon_skill_unlock(body)
            if catalog is None or target_id is None:
                return "unsupported_summon_skill_unlock", None
            userdata = account["userdata"]
            summons, items = userdata.get("summonList"), userdata.get("itemList")
            raw_summon = summons[target_id - 1] if isinstance(summons, list) and len(summons) == 16 else None
            if type(raw_summon) is not int:
                payload = {"success": False, "errorCode": 3}
            else:
                skill_level = raw_summon & 0xFF
                rule = catalog.levels.get((target_id, skill_level))
                if skill_level < 1 or skill_level >= catalog.level_counts[target_id] or rule is None:
                    payload = {"success": False, "errorCode": 3}
                elif type(userdata.get("coins", 0)) is not int or userdata["coins"] < rule.coins:
                    payload = {"success": False, "errorCode": 1}
                elif not isinstance(items, list) or len(items) != catalog.item_slots or any(item_id > len(items) or type(items[item_id - 1]) is not int or items[item_id - 1] < count for item_id, count in rule.materials.items()):
                    payload = {"success": False, "errorCode": 2}
                else:
                    new_items = copy.deepcopy(items)
                    for item_id, count in rule.materials.items():
                        new_items[item_id - 1] -= count
                    new_summons = copy.deepcopy(summons)
                    new_summons[target_id - 1] = (raw_summon & ~0xFF) | (skill_level + 1)
                    userdata["itemList"] = new_items
                    userdata["summonList"] = new_summons
                    userdata["coins"] -= rule.coins
                    payload = {"success": True, "itemList": new_items, "summonList": new_summons, "coins": userdata["coins"]}
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def sell_companions(self, token: str, request_id: str, body: bytes, catalog: CompanionCatalog | None, *, multiple: bool) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            inventory_ids = _parse_sell_companions(body, multiple=multiple)
            if catalog is None or inventory_ids is None:
                return "unsupported_companion_sale", None
            userdata = account["userdata"]
            buddy_info = userdata.get("buddyInfo")
            owned = buddy_info.get("list") if isinstance(buddy_info, dict) else None
            if not isinstance(owned, list):
                return "unsupported_companion_sale", None
            candidates = copy.deepcopy(owned)
            by_id: dict[int, dict[str, Any]] = {}
            for companion in candidates:
                if not isinstance(companion, dict) or type(companion.get("iid")) is not int or companion["iid"] <= 0 or companion["iid"] in by_id or type(companion.get("bid")) is not int or companion["bid"] not in catalog.masters or type(companion.get("lv")) is not int or companion["lv"] < 1 or type(companion.get("flag", 0)) is not int:
                    return "unsupported_companion_sale", None
                by_id[companion["iid"]] = companion
            selected = [by_id.get(inventory_id) for inventory_id in inventory_ids]
            if len(inventory_ids) != len(set(inventory_ids)) or any(companion is None or companion.get("flag", 0) & 2 for companion in selected):
                payload = {"success": False, "errorCode": 2}
            elif type(userdata.get("coins", 0)) is not int:
                return "unsupported_companion_sale", None
            else:
                sold = [companion for companion in selected if companion is not None]
                sold_ids = {companion["iid"] for companion in sold}
                remaining = [companion for companion in candidates if companion["iid"] not in sold_ids]
                new_rows = copy.deepcopy(userdata.get("chrdata", []))
                if not isinstance(new_rows, list):
                    return "unsupported_companion_sale", None
                for row in new_rows:
                    if isinstance(row, dict) and row.get("buddy") in sold_ids:
                        row["buddy"] = 0
                proceeds = sum(catalog.masters[companion["bid"]].base_coins * companion["lv"] for companion in sold)
                coins = min(catalog.coin_cap, userdata["coins"] + proceeds)
                userdata["buddyInfo"] = _companion_info(remaining)
                userdata["chrdata"] = new_rows
                userdata["coins"] = coins
                payload = {"success": True, "buddyInfo": copy.deepcopy(userdata["buddyInfo"]), "chrdata": new_rows, "coins": coins}
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def strengthen_companion(self, token: str, request_id: str, body: bytes, catalog: CompanionStrengthenCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            request = _parse_companion_strengthen(body)
            if catalog is None or request is None:
                return "unsupported_companion_strengthen", None
            base_id, material_ids = request
            userdata = account["userdata"]
            buddy_info = userdata.get("buddyInfo")
            owned = buddy_info.get("list") if isinstance(buddy_info, dict) else None
            if not isinstance(owned, list):
                return "unsupported_companion_strengthen", None
            candidates = copy.deepcopy(owned)
            by_id: dict[int, dict[str, Any]] = {}
            for companion in candidates:
                if not isinstance(companion, dict) or type(companion.get("iid")) is not int or companion["iid"] <= 0 or companion["iid"] in by_id or type(companion.get("bid")) is not int or companion["bid"] not in catalog.masters or type(companion.get("lv")) is not int or companion["lv"] < 1 or type(companion.get("exp", 0)) is not int or companion["exp"] < 0 or type(companion.get("flag", 0)) is not int:
                    return "unsupported_companion_strengthen", None
                by_id[companion["iid"]] = companion
            base = by_id.get(base_id)
            materials = [by_id.get(material_id) for material_id in material_ids]
            if base is None:
                payload = {"success": False, "errorCode": 2}
            elif any(material is None for material in materials):
                payload = {"success": False, "errorCode": 3}
            else:
                base_master = catalog.masters[base["bid"]]
                typed_materials = [material for material in materials if material is not None]
                base_level = base["lv"]
                cost = 50 * base_level * len(typed_materials)
                if base["lv"] >= base_master.max_level:
                    payload = {"success": False, "errorCode": 4}
                elif any(material.get("flag", 0) & 2 for material in typed_materials):
                    payload = {"success": False, "errorCode": 6}
                elif type(userdata.get("coins", 0)) is not int or userdata["coins"] < cost:
                    payload = {"success": False, "errorCode": 5}
                else:
                    total_exp = 0
                    for material in typed_materials:
                        master = catalog.masters[material["bid"]]
                        contribution = material["lv"] * master.base_exp
                        if material["bid"] == base["bid"]:
                            contribution *= master.same_bonus_bias * catalog.same_companion_multiplier
                        total_exp += contribution
                    if catalog.byebye_companion_id is not None and any(material["bid"] == catalog.byebye_companion_id for material in typed_materials):
                        total_exp = total_exp * catalog.byebye_multiplier_percent // 100
                    exp_bonus = _draw_companion_bonus(catalog)
                    additional_exp = total_exp * exp_bonus // 100
                    max_exp = _companion_exp_at(base_master, base_master.max_level)
                    base["exp"] = min(max_exp, base["exp"] + total_exp + additional_exp)
                    base["lv"] = _companion_level_at_exp(base_master, base["exp"])
                    consumed_ids = {material["iid"] for material in typed_materials}
                    remaining = [companion for companion in candidates if companion["iid"] not in consumed_ids]
                    rows = copy.deepcopy(userdata.get("chrdata", []))
                    if not isinstance(rows, list):
                        return "unsupported_companion_strengthen", None
                    for row in rows:
                        if isinstance(row, dict) and row.get("buddy") in consumed_ids:
                            row["buddy"] = 0
                    coins = userdata["coins"] - cost
                    userdata["buddyInfo"] = _companion_info(remaining)
                    userdata["chrdata"] = rows
                    userdata["coins"] = coins
                    payload = {"success": True, "buddyInfo": copy.deepcopy(userdata["buddyInfo"]), "chrdata": rows, "coins": coins, "totalEXP": total_exp, "additionalEXP": additional_exp, "expBonus": exp_bonus}
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def evolve_companion(self, token: str, request_id: str, body: bytes, catalog: CompanionEvolutionCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            base_id = _parse_companion_evolve(body)
            if catalog is None or base_id is None:
                return "unsupported_companion_evolution", None
            userdata = account["userdata"]
            buddy_info = userdata.get("buddyInfo")
            owned = buddy_info.get("list") if isinstance(buddy_info, dict) else None
            items = userdata.get("itemList")
            if not isinstance(owned, list) or not isinstance(items, list) or len(items) != catalog.item_slots:
                return "unsupported_companion_evolution", None
            candidates = copy.deepcopy(owned)
            by_id: dict[int, dict[str, Any]] = {}
            for companion in candidates:
                if not isinstance(companion, dict) or type(companion.get("iid")) is not int or companion["iid"] <= 0 or companion["iid"] in by_id or type(companion.get("bid")) is not int or type(companion.get("lv")) is not int or companion["lv"] < 1 or type(companion.get("flag", 0)) is not int:
                    return "unsupported_companion_evolution", None
                by_id[companion["iid"]] = companion
            base = by_id.get(base_id)
            recipe = None if base is None else catalog.recipes.get(base["bid"])
            if base is None or recipe is None:
                payload = {"success": False, "errorCode": 3}
            elif base.get("flag", 0) & 2:
                payload = {"success": False, "errorCode": 5}
            elif base["lv"] < recipe.max_level:
                payload = {"success": False, "errorCode": 4}
            elif type(userdata.get("coins", 0)) is not int or userdata["coins"] < recipe.coins:
                payload = {"success": False, "errorCode": 1}
            elif any(item_id > len(items) or type(items[item_id - 1]) is not int or items[item_id - 1] < count for item_id, count in recipe.items.items()):
                payload = {"success": False, "errorCode": 2}
            else:
                copies = sorted((companion for companion in candidates if companion["iid"] != base_id and companion["bid"] == base["bid"] and not companion.get("chrID", 0) and not companion.get("flag", 0) & 2), key=lambda companion: companion["iid"])
                if len(copies) < recipe.duplicate_source_count:
                    payload = {"success": False, "errorCode": 2}
                else:
                    new_items = copy.deepcopy(items)
                    for item_id, count in recipe.items.items():
                        new_items[item_id - 1] -= count
                    consumed_ids = {companion["iid"] for companion in copies[:recipe.duplicate_source_count]}
                    remaining = [companion for companion in candidates if companion["iid"] not in consumed_ids]
                    evolved = next(companion for companion in remaining if companion["iid"] == base_id)
                    evolved["bid"] = recipe.destination_companion_id
                    evolved["lv"] = 1
                    evolved["exp"] = 0
                    userdata["buddyInfo"] = _companion_info(remaining)
                    userdata["itemList"] = new_items
                    userdata["coins"] -= recipe.coins
                    payload = {"success": True, "buddyInfo": copy.deepcopy(userdata["buddyInfo"]), "chrdata": copy.deepcopy(userdata.get("chrdata", [])), "coins": userdata["coins"], "itemList": new_items}
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def draw_companions(self, token: str, request_id: str, body: bytes, catalog: CompanionDrawCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            request = _parse_companion_draw(body)
            if catalog is None or request is None:
                return "unsupported_companion_draw", None
            kind, count = request
            userdata = account["userdata"]
            items = userdata.get("itemList")
            buddy_info = userdata.get("buddyInfo", {"list": [], "record": []})
            owned = buddy_info.get("list") if isinstance(buddy_info, dict) else None
            if not isinstance(items, list) or len(items) != catalog.item_slots or type(items[catalog.ticket_item_id - 1]) is not int or items[catalog.ticket_item_id - 1] < 0 or not isinstance(owned, list) or type(userdata.get("energy", 0)) is not int or type(userdata.get("freeEnergy", 0)) is not int or type(userdata.get("coins", 0)) is not int:
                return "unsupported_companion_draw", None
            if len(owned) + count > catalog.max_owned:
                payload = {"success": False, "errorCode": 4}
            else:
                uses_ticket = items[catalog.ticket_item_id - 1] >= count
                ticket_only = kind == 21
                total_energy = catalog.energy_cost * count
                if (ticket_only and not uses_ticket) or (not uses_ticket and userdata["energy"] + userdata["freeEnergy"] < total_energy):
                    payload = {"success": False, "errorCode": 1}
                else:
                    candidates = copy.deepcopy(owned)
                    known_ids: set[int] = set()
                    for companion in candidates:
                        if not isinstance(companion, dict) or type(companion.get("iid")) is not int or companion["iid"] <= 0 or companion["iid"] in known_ids:
                            return "unsupported_companion_draw", None
                        known_ids.add(companion["iid"])
                    next_id = userdata.get("nextCompanionInventoryId", max(known_ids, default=0) + 1)
                    if type(next_id) is not int or next_id <= max(known_ids, default=0):
                        return "unsupported_companion_draw", None
                    drawn: list[dict[str, Any]] = []
                    results: list[dict[str, int]] = []
                    for _ in range(count):
                        selected = _draw_companion_id(catalog)
                        record = {"bid": selected, "lv": 1, "date": 0.0, "iid": next_id, "exp": 0, "flag": 0, "chrID": 0}
                        drawn.append(record)
                        results.append({"bid": selected, "lv": 1})
                        next_id += 1
                    new_items = copy.deepcopy(items)
                    energy = userdata["energy"]
                    free_energy = userdata["freeEnergy"]
                    if uses_ticket:
                        new_items[catalog.ticket_item_id - 1] -= count
                    else:
                        free_spend = min(free_energy, total_energy)
                        free_energy -= free_spend
                        energy -= total_energy - free_spend
                    candidates.extend(drawn)
                    userdata["buddyInfo"] = _companion_info(candidates)
                    userdata["itemList"] = new_items
                    userdata["energy"] = energy
                    userdata["freeEnergy"] = free_energy
                    userdata["nextCompanionInventoryId"] = next_id
                    payload = {"success": True, "coins": userdata["coins"], "energy": energy, "freeEnergy": free_energy, "itemList": new_items, "buddyInfo": copy.deepcopy(userdata["buddyInfo"]), "result": results}
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def draw_ordinary_pact(self, token: str, request_id: str, body: bytes, catalog: PactDrawCatalog | BundledPactPolicy | None) -> tuple[str, dict[str, Any] | None]:
        """Settle only the evidence-backed normal coin Pact form.

        Pool, rates, costs, duplicate effects, and level ceiling are all
        operator policy supplied by the catalog; no historical roster/rate
        data is bundled here.
        """
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            parsed = _parse_ordinary_pact_draw(body)
            if catalog is None or parsed is None:
                return "unsupported_ordinary_pact", None
            kind, count = parsed
            draws, cost = catalog.draws_for_kind(kind), catalog.cost_for_kind(kind)
            if not draws or cost is None:
                return "unsupported_ordinary_pact", None
            currency, unit_cost = cost
            userdata = account["userdata"]
            rows = userdata.get("chrdata")
            if not isinstance(rows, list) or type(userdata.get("coins")) is not int or type(userdata.get("energy", 0)) is not int or type(userdata.get("freeEnergy", 0)) is not int:
                return "unsupported_ordinary_pact", None
            total_cost = unit_cost * count
            if currency == "coins" and userdata["coins"] < total_cost:
                payload = {"success": False, "errorCode": 2}
            elif currency == "energy" and userdata["energy"] + userdata["freeEnergy"] < total_cost:
                payload = {"success": False, "errorCode": 1}
            else:
                candidates = copy.deepcopy(rows)
                by_id = {row.get("id"): row for row in candidates if isinstance(row, dict) and type(row.get("id")) is int}
                if len(by_id) != len(candidates):
                    return "unsupported_ordinary_pact", None
                results: list[dict[str, Any]] = []
                for _ in range(count):
                    if any(type(row.get("skillBoost", 0)) is not int for row in by_id.values()):
                        return "unsupported_ordinary_pact", None
                    eligible = [draw for draw in draws if not isinstance(by_id.get(draw.character_id), dict) or by_id[draw.character_id].get("skillBoost", 0) < catalog.max_skill_boost]
                    if not eligible:
                        payload = {"success": False, "errorCode": 3}
                        break
                    threshold = random.SystemRandom().randrange(sum(draw.weight for draw in eligible))
                    selected = eligible[-1]
                    for draw in eligible:
                        if threshold < draw.weight:
                            selected = draw
                            break
                        threshold -= draw.weight
                    current = by_id.get(selected.character_id)
                    if current is None:
                        current = {"id": selected.character_id, "jobID": 0, "jobLevels": [catalog.new_level], "jobSlots": [], "skillBoost": 0}
                        candidates.append(current); by_id[selected.character_id] = current
                        results.append({"id": selected.character_id, "jobID": 0, "jobLevels": [catalog.new_level], "jobSlots": [], "isNew": True, "levelAdded": catalog.new_level, "skillBoost": 0})
                    elif not isinstance(current.get("jobLevels"), list) or not current["jobLevels"] or type(current["jobLevels"][0]) is not int or type(current.get("skillBoost", 0)) is not int or type(current.get("jobID", 0)) is not int or not isinstance(current.get("jobSlots", []), list):
                        return "unsupported_ordinary_pact", None
                    else:
                        old_level, old_boost = current["jobLevels"][0], current.get("skillBoost", 0)
                        level = min(catalog.max_level, old_level + selected.duplicate_level_added)
                        boost = min(catalog.max_skill_boost, old_boost + selected.duplicate_skill_boost)
                        current["jobLevels"][0], current["skillBoost"] = level, boost
                        results.append({"id": selected.character_id, "jobID": int(current.get("jobID", 0)), "jobLevels": [level], "jobSlots": list(current.get("jobSlots", [])), "isNew": False, "levelAdded": level - old_level, "boostUp": boost - old_boost, "skillBoost": boost})
                else:
                    if currency == "coins":
                        userdata["coins"] -= total_cost
                    else:
                        free_spend = min(userdata["freeEnergy"], total_cost)
                        userdata["freeEnergy"] -= free_spend
                        userdata["energy"] -= total_cost - free_spend
                    userdata["chrdata"] = candidates
                    payload = {"success": True, "coins": userdata["coins"], "energy": userdata["energy"], "freeEnergy": userdata["freeEnergy"], "chrdata": results}
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def update_companion_userdata(self, token: str, request_id: str, body: bytes, submitted: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            userdata = account["userdata"]
            buddy_info = userdata.get("buddyInfo")
            owned = buddy_info.get("list") if isinstance(buddy_info, dict) else None
            if not isinstance(owned, list):
                return "unsupported_companion_userdata", None
            current = {companion.get("iid"): companion for companion in owned if isinstance(companion, dict) and type(companion.get("iid")) is int}
            if len(current) != len(owned) or not submitted or any(companion["iid"] not in current or any(companion[name] != current[companion["iid"]].get(name) for name in ("bid", "lv", "date", "iid", "exp", "chrID")) or companion["flag"] & ~0x3 or (current[companion["iid"]].get("flag", 0) & 1 and not companion["flag"] & 1) for companion in submitted):
                return "unsupported_companion_userdata", None
            candidates = copy.deepcopy(owned)
            updates = {companion["iid"]: companion for companion in submitted}
            for index, companion in enumerate(candidates):
                if companion["iid"] in updates:
                    candidates[index] = copy.deepcopy(updates[companion["iid"]])
            userdata["buddyInfo"] = _companion_info(candidates)
            payload = {"success": True, "lastupdate": 1.0}
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_generic_story_start(
        self, token: str, request_id: str, body: bytes, catalog: StoryCatalog | StoryProgressionCatalog,
        settlement_catalog: SettlementCatalog | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Start one catalog-declared local story stage after the tutorial."""
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            body_hash = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                if cached.get("body_sha256") != body_hash:
                    return "request_collision", None
                return "replay", copy.deepcopy(cached["payload"])
            values = _parse_generic_story_start(body)
            if values is None:
                return "unsupported_start_quest", None
            stage = catalog.by_identity().get((values["chapter"], values["section"]))
            if (
                stage is None
                or stage.stamina is not None and values["stamina"] != stage.stamina
                or stage.coins is not None and values["coins"] != stage.coins
            ):
                return "unsupported_start_quest", None
            if isinstance(catalog, StoryProgressionCatalog):
                current = int(account["userdata"].get("progressCode", 0))
                expected = catalog.expected_clear_progress(current, (stage.chapter, stage.section))
                if expected is None:
                    return "tutorial_state_conflict", None
            if account.setdefault("tutorial_phase", "initial") != "free_roam" or account.get("active_generic_story") is not None:
                return "tutorial_state_conflict", None
            payload = {"success": True, "refillStartTime": 0.0}
            account["tutorial_phase"] = "generic_story_active"
            account["active_generic_story"] = {"chapter": stage.chapter, "section": stage.section}
            requests[request_id] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_generic_story_clear(
        self, token: str, request_id: str, body: bytes, catalog: StoryCatalog | StoryProgressionCatalog,
        settlement_catalog: SettlementCatalog | None = None,
        outcome_catalog: StoryOutcomeCatalog | None = None,
        clear_state_catalog: ClearStateCatalog | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Settle one trusted-local catalog stage without imported master data.

        This deliberately records the submitted roster/item projections as a
        local self-hosted policy.  It is not the private reference's
        authoritative character/reward validation, which needs additional
        user-local master catalogs and remains a separate work packet.
        """
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            body_hash = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                if cached.get("body_sha256") != body_hash:
                    return "request_collision", None
                return "replay", copy.deepcopy(cached["payload"])
            clear = _parse_generic_story_clear(body)
            if clear is None:
                return "unsupported_clear_quest", None
            identity = (clear["battle_result"]["chapter"], clear["battle_result"]["section"])
            stage = catalog.by_identity().get(identity)
            if stage is None:
                return "unsupported_clear_quest", None
            active = account.get("active_generic_story")
            userdata = account["userdata"]
            dynamic = isinstance(catalog, StoryProgressionCatalog)
            reward_rule = None if settlement_catalog is None else settlement_catalog.rules.get(identity)
            clear_coins = (
                reward_rule.clear_coins
                if dynamic and reward_rule is not None and reward_rule.clear_coins is not None
                else clear["battle_result"]["coins"] if dynamic else stage.clear_coins
            )
            expected_progress = catalog.expected_clear_progress(int(userdata.get("progressCode", 0)), identity) if dynamic else stage.clear_progress_code
            expected_coins = int(userdata.get("coins", 0)) + clear_coins
            if (
                account.setdefault("tutorial_phase", "initial") != "generic_story_active"
                or active != {"chapter": identity[0], "section": identity[1]}
                or expected_progress is None
                or clear["progressCode"] != expected_progress
                or clear["worldMapNo"] != int(userdata.get("worldMapNo", 0))
                or clear["valuables"].get("coins") != expected_coins
                or clear["battle_result"].get("coins") != clear_coins
            ):
                return "tutorial_state_conflict", None
            if settlement_catalog is not None and not _settlement_matches(userdata, clear, identity, settlement_catalog):
                return "invalid_local_settlement", None
            if clear_state_catalog is not None and not _clear_state_matches(userdata, clear, clear_state_catalog):
                return "invalid_local_clear_state", None
            buddy_info = None if outcome_catalog is None else _outcome_buddy_info(userdata, clear, identity, outcome_catalog, clear_state_catalog)
            if outcome_catalog is not None and buddy_info is None:
                return "invalid_local_outcome", None
            userdata.update({
                "lastupdate": 1.0,
                "progressCode": expected_progress,
                "coins": expected_coins,
                "valuables": copy.deepcopy(clear["valuables"]),
                "chrdata": copy.deepcopy(clear["chrdata"]),
                "itemList": copy.deepcopy(clear["itemList"]),
                "summonList": copy.deepcopy(clear["summonList"]),
            })
            if buddy_info is not None:
                userdata["buddyInfo"] = buddy_info
            payload = {
                "success": True,
                "lastupdate": 1.0,
                "sentMessage": False,
                "coins": expected_coins,
                "chrdata": copy.deepcopy(userdata["chrdata"]),
                "itemList": copy.deepcopy(userdata["itemList"]),
            }
            if buddy_info is not None:
                payload["buddyInfo"] = copy.deepcopy(buddy_info)
            account["tutorial_phase"] = "free_roam"
            account["active_generic_story"] = None
            payload = _canonical_payload(payload)
            requests[request_id] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_story_progression_reveal(
        self, token: str, request_id: str, body: bytes, catalog: StoryProgressionCatalog,
    ) -> tuple[str, dict[str, Any] | None]:
        """Apply the exact post-chapter map write from the derived local sequence."""
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            body_hash = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                if cached.get("body_sha256") != body_hash:
                    return "request_collision", None
                return "replay", copy.deepcopy(cached["payload"])
            reveal = _parse_story_progression_reveal(body)
            if reveal is None:
                return "unsupported_story_progression_reveal", None
            userdata = account["userdata"]
            current = userdata.get("progressCode")
            world_map = userdata.get("worldMapNo")
            expected = catalog.expected_reveal_progress(current) if type(current) is int else None
            if (
                account.setdefault("tutorial_phase", "initial") != "free_roam"
                or expected is None
                or reveal["progressCode"] != expected
                or reveal["worldMapNo"] != world_map
            ):
                return "tutorial_state_conflict", None
            userdata["progressCode"] = expected
            userdata["lastupdate"] = float(reveal["lastUpdate"])
            payload = _canonical_payload({"success": True, "lastupdate": float(reveal["lastUpdate"])})
            requests[request_id] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_generic_story_continue(
        self, token: str, request_id: str, body: bytes, policy: dict[str, int]
    ) -> tuple[str, dict[str, Any] | None]:
        """Apply the explicit local coin Continue policy to an active generic story battle."""
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            body_hash = hashlib.sha256(body).hexdigest()
            cached = requests.get(request_id)
            if cached is not None:
                if cached.get("body_sha256") != body_hash:
                    return "request_collision", None
                return "replay", copy.deepcopy(cached["payload"])
            if _parse_continue(body) != policy["client_cost"]:
                return "unsupported_continue", None
            userdata = account["userdata"]
            coins = userdata.get("coins", 0)
            if (
                account.setdefault("tutorial_phase", "initial") != "generic_story_active"
                or not isinstance(account.get("active_generic_story"), dict)
                or type(coins) is not int
                or coins < policy["coin_cost"]
            ):
                return "continue_unavailable", None
            userdata["coins"] = coins - policy["coin_cost"]
            payload = {
                "success": True,
                "energy": int(userdata.get("energy", 0)),
                "freeEnergy": int(userdata.get("freeEnergy", 0)),
            }
            requests[request_id] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProfileError("could not read local bootstrap state") from error
        if not isinstance(document, dict) or not isinstance(document.get("accounts"), dict) or not isinstance(document.get("tokens"), dict):
            raise ProfileError("local bootstrap state is invalid")
        accounts = document["accounts"]
        self.tokens = document["tokens"]
        active_account_id = document.get("active_account_id")
        if not all(isinstance(token, str) and isinstance(value, dict) and isinstance(value.get("userdata"), dict) for token, value in accounts.items()):
            raise ProfileError("local bootstrap state contains invalid account data")
        if not all(isinstance(token, str) and isinstance(account_id, str) and account_id in accounts for token, account_id in self.tokens.items()):
            raise ProfileError("local bootstrap state contains invalid token bindings")
        if active_account_id is not None and (not isinstance(active_account_id, str) or active_account_id not in accounts):
            raise ProfileError("local bootstrap state contains an invalid active account")
        self.active_account_id = active_account_id
        for account in accounts.values():
            account.setdefault("tutorial_phase", "initial")
            account.setdefault("tutorial_requests", {})
            account.setdefault("initial_userdata_served", False)
            account.setdefault("active_generic_story", None)
            account.setdefault("claimed_achievements", [])
            account.setdefault("achievement_requests", {})
            account.setdefault("messages", {})
            account.setdefault("message_requests", {})
            if (
                not isinstance(account["tutorial_phase"], str)
                or not isinstance(account["tutorial_requests"], dict)
                or type(account["initial_userdata_served"]) is not bool
                or account["active_generic_story"] is not None and not isinstance(account["active_generic_story"], dict)
                or not isinstance(account["claimed_achievements"], list)
                or any(type(value) is not int or value < 1 for value in account["claimed_achievements"])
                or account["claimed_achievements"] != sorted(set(account["claimed_achievements"]))
                or not isinstance(account["achievement_requests"], dict)
                or not isinstance(account["messages"], dict)
                or not isinstance(account["message_requests"], dict)
            ):
                raise ProfileError("local bootstrap state contains invalid tutorial state")
        return accounts

    def _persist_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps({"accounts": self.accounts, "active_account_id": self.active_account_id, "tokens": self.tokens}, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)


def _safe_form_diagnostics(body: bytes) -> dict[str, Any]:
    """Record a small, non-secret view of a form request for local debugging."""
    try:
        fields = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return {"request_body_sha256": hashlib.sha256(body).hexdigest()}
    details: dict[str, Any] = {"request_fields": [name for name, _ in fields]}
    safe_values = {
        name: value for name, value in fields
        if name in {"progressCode", "worldMapNo", "lastUpdate", "chapter", "section"}
    }
    if safe_values:
        details["request_values"] = safe_values
    return details


class EventRecorder:
    """Append route diagnostics without retaining tokens or request bodies."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.lock = Lock()

    def record(
        self, method: str, target: str, status: HTTPStatus,
        details: dict[str, Any] | None = None,
    ) -> None:
        if self.path is None:
            return
        event = {
            "method": method,
            "path": urlsplit(target).path,
            "status": status.value,
            "timestamp_utc": int(time.time()),
        }
        if details:
            event.update(details)
        encoded = json.dumps(event, separators=(",", ":"), sort_keys=True) + "\n"
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(encoded)
                stream.flush()


class BootstrapServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        profile: BootstrapProfile,
        state: BootstrapState,
        event_log: Path | None = None,
        resource_catalog: ResourceCatalog | None = None,
        story_catalog: StoryCatalog | None = None,
        settlement_catalog: SettlementCatalog | None = None,
        story_outcome_catalog: StoryOutcomeCatalog | None = None,
        statusup_catalog: StatusupCatalog | None = None,
        job_catalog: JobCatalog | None = None,
        rebirth_catalog: RebirthCatalog | None = None,
        summon_skill_catalog: SummonSkillCatalog | None = None,
        companion_catalog: CompanionCatalog | None = None,
        companion_strengthen_catalog: CompanionStrengthenCatalog | None = None,
        companion_evolution_catalog: CompanionEvolutionCatalog | None = None,
        companion_draw_catalog: CompanionDrawCatalog | None = None,
        pact_draw_catalog: PactDrawCatalog | BundledPactPolicy | None = None,
        achievement_catalog: AchievementCatalog | None = None,
        message_catalog: MessageCatalog | None = None,
        exchange_catalog: ExchangeCatalog | None = None,
        clear_state_catalog: ClearStateCatalog | None = None,
        story_progression_catalog: StoryProgressionCatalog | None = None,
        public_data_root: Path | None = None,
    ) -> None:
        self.profile = profile
        self.state = state
        self.events = EventRecorder(event_log)
        self.resource_catalog = resource_catalog
        self.public_data_root = public_data_root.resolve() if public_data_root is not None else None
        self.story_catalog = story_catalog
        self.story_progression_catalog = story_progression_catalog
        self.settlement_catalog = settlement_catalog
        self.story_outcome_catalog = story_outcome_catalog
        self.statusup_catalog = statusup_catalog
        self.job_catalog = job_catalog
        self.rebirth_catalog = rebirth_catalog
        self.summon_skill_catalog = summon_skill_catalog
        self.companion_catalog = companion_catalog
        self.companion_strengthen_catalog = companion_strengthen_catalog
        self.companion_evolution_catalog = companion_evolution_catalog
        self.companion_draw_catalog = companion_draw_catalog
        self.pact_draw_catalog = pact_draw_catalog
        self.achievement_catalog = achievement_catalog
        self.message_catalog = message_catalog
        self.exchange_catalog = exchange_catalog
        self.clear_state_catalog = clear_state_catalog
        super().__init__(address, BootstrapHandler)


class BootstrapHandler(BaseHTTPRequestHandler):
    server: BootstrapServer

    def do_GET(self) -> None:
        target = urlsplit(self.path)
        if target.path == "/en/news/app":
            self._html(
                HTTPStatus.OK,
                "<!doctype html><html><head><meta charset=\"utf-8\"><title>Project Liminal Gate</title></head>"
                "<body><h1>Project Liminal Gate</h1><p>Your local preservation server is running.</p>"
                "<p>Check the project README for local setup and support details.</p></body></html>",
            )
            return
        if target.path == "/favicon.ico":
            self._empty(HTTPStatus.NO_CONTENT)
            return
        banner_name = PACT_BANNER_FILES.get(target.path)
        if banner_name is not None and self.server.public_data_root is not None:
            banner = self.server.public_data_root / "banners" / banner_name
            if banner.is_file() and banner.resolve().is_relative_to(self.server.public_data_root):
                self._file(HTTPStatus.OK, banner, "image/png")
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "local_banner_not_found"})
            return
        resource = self.server.resource_catalog.resolve(target.path) if self.server.resource_catalog else None
        if resource is not None:
            self._resource(HTTPStatus.OK, resource)
            return
        if target.path.startswith("/resources/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "resource_not_found"})
            return
        query = dict(parse_qsl(target.query, keep_blank_values=True))
        profile = self.server.profile
        if target.path == profile.routes.get("signup"):
            token = query.get("otk")
            account_id = query.get("uuid")
            if not token or not account_id:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "missing_local_account_identity"})
                return
            signup = _render(profile.responses["signup"], token, account_id)
            response_account_id = signup.get(profile.account_binding["signup_response_field"])
            if not isinstance(response_account_id, str) or not response_account_id:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "invalid_local_profile"})
                return
            self.server.state.create_account(token, response_account_id, profile.userdata_seed, self.server.message_catalog, self.server.exchange_catalog)
            self._signed(HTTPStatus.OK, token, signup)
            return
        token = query.get("otk")
        if target.path == profile.routes.get("time"):
            if not token:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "missing_local_account_token"})
                return
            self._signed(HTTPStatus.OK, token, {"success": True, "timestamp": float(int(time.time()))})
            return
        if target.path == profile.routes.get("status"):
            if not token:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "missing_local_account_token"})
                return
            self._signed(HTTPStatus.OK, token, _render(profile.responses["status"], token))
            return
        if target.path == profile.routes.get("login"):
            account_id = query.get(profile.account_binding["login_query_field"])
            if not token or not isinstance(account_id, str) or not self.server.state.bind_login_token(token, account_id):
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unknown_local_account"})
                return
            payload = _render(profile.responses["login"], token, account_id)
            payload["name"] = self.server.state.accounts[account_id].get("username", payload.get("name", "Player"))
            payload["messageList"] = self.server.state.login_messages(account_id)
            self._signed(HTTPStatus.OK, token, payload)
            return
        if target.path == profile.routes.get("userdata"):
            # The surviving client may rotate its OTK immediately after a
            # successful login, before its first read-only userdata request.
            # Bind before reading so an older emulator token cannot select an
            # abandoned local account after the active save has been resumed.
            if self.server.state.bind_rotated_token(token):
                userdata = self.server.state.userdata_for(token)
            else:
                userdata = None
            if userdata is None:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unknown_local_account"})
                return
            self._signed(HTTPStatus.OK, token, {"success": True, **userdata})
            return
        if target.path == profile.routes.get("userdata_after_close"):
            userdata = self.server.state.userdata_for(token)
            if userdata is None:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unknown_local_account"})
                return
            self._signed(HTTPStatus.OK, token, {"success": True, **userdata})
            return
        if target.path == profile.routes.get("multiplay_enable"):
            if not token:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "missing_local_account_token"})
                return
            self._signed(HTTPStatus.OK, token, _render(profile.responses["multiplay_enable"], token))
            return
        if target.path == profile.routes.get("special_event"):
            if not token:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "missing_local_account_token"})
                return
            self._signed(HTTPStatus.OK, token, _render(profile.responses["special_event"], token))
            return
        if target.path == profile.routes.get("get_current_exchange"):
            result, payload = self.server.state.current_exchange(token, self.server.exchange_catalog)
            if result == "success": self._signed(HTTPStatus.OK, token or "", {"success": True, **(payload or {})})
            else: self._json(HTTPStatus.NOT_IMPLEMENTED if result == "unsupported_exchange" else HTTPStatus.UNAUTHORIZED, {"error": result})
            return
        self._json(HTTPStatus.NOT_IMPLEMENTED, {"error": "route_not_implemented"})

    def do_POST(self) -> None:
        target = urlsplit(self.path)
        profile = self.server.profile
        if target.path not in {
            profile.routes.get("do_slot"),
            profile.routes.get("userdata"),
            profile.routes.get("start_quest"),
            profile.routes.get("clear_quest"),
            profile.routes.get("continue"),
            profile.routes.get("change_uname"),
            profile.routes.get("refill_stamina"),
            profile.routes.get("unlock_metal_zone"), profile.routes.get("achived"),
            profile.routes.get("read_messages"), profile.routes.get("delete_messages"),
            profile.routes.get("exchange"), profile.routes.get("add_exchange_count"),
            profile.routes.get("statusup_item"),
            profile.routes.get("add_job"),
            profile.routes.get("rebirth"),
            profile.routes.get("summon_skill_unlock"),
            profile.routes.get("sell_buddy"),
            profile.routes.get("sell_buddies"),
            profile.routes.get("buddy_strengthen"),
            profile.routes.get("buddy_evolve"),
            profile.routes.get("do_buddy_slot"),
        }:
            self._json(HTTPStatus.NOT_IMPLEMENTED, {"error": "route_not_implemented"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
            return
        body = self.rfile.read(length)
        self._event_details = _safe_form_diagnostics(body)
        query = dict(parse_qsl(target.query, keep_blank_values=True))
        token = query.get("otk")
        request_id = query.get("requestID")
        if not token or not request_id:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "missing_local_mutation_identity"})
            return
        if not self.server.state.bind_rotated_token(token):
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unknown_account"})
            return
        if target.path == profile.routes.get("do_slot"):
            result, payload = self.server.state.draw_ordinary_pact(token, request_id, body, self.server.pact_draw_catalog)
            transitions, kind = (profile.tutorial_summons, "summon") if result == "unsupported_ordinary_pact" else ((), "ordinary_pact")
        elif target.path == profile.routes.get("do_buddy_slot"):
            result, payload = self.server.state.draw_companions(token, request_id, body, self.server.companion_draw_catalog)
            transitions, kind = (), "do_buddy_slot"
        elif target.path == profile.routes.get("userdata"):
            transitions, kind = profile.tutorial_writes, "write"
            companion_write = _parse_companion_userdata_write(body)
            if companion_write is not None:
                result, payload = self.server.state.update_companion_userdata(token, request_id, body, companion_write)
                transitions, kind = (), "companion_userdata"
            if profile.structural_writes:
                try:
                    candidate_fields = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
                except (UnicodeDecodeError, ValueError):
                    candidate_fields = ()
                if any(tuple(name for name, _ in candidate_fields) == tuple(item["field_names"]) for item in profile.structural_writes):
                    transitions, kind = profile.structural_writes, "structural"
        elif target.path == profile.routes.get("start_quest"):
            transitions, kind = profile.story_starts, "start"
        elif target.path == profile.routes.get("continue"):
            result, payload = self.server.state.apply_generic_story_continue(
                token, request_id, body, profile.continue_policy
            )
            transitions, kind = (), "continue"
        elif target.path == profile.routes.get("change_uname"):
            result, payload = self.server.state.change_uname(token, request_id, body)
            transitions, kind = (), "change_uname"
        elif target.path == profile.routes.get("refill_stamina"):
            result, payload = self.server.state.refill_stamina(token, request_id, body)
            transitions, kind = (), "refill_stamina"
        elif target.path == profile.routes.get("unlock_metal_zone"):
            result, payload = self.server.state.unlock_metal_zone(token, request_id, body)
            transitions, kind = (), "unlock_metal_zone"
        elif target.path == profile.routes.get("achived"):
            result, payload = self.server.state.claim_achievement(token, request_id, body, self.server.achievement_catalog)
            transitions, kind = (), "achievement"
        elif target.path == profile.routes.get("read_messages"):
            result, payload = self.server.state.read_messages(token, request_id, body, self.server.message_catalog)
            transitions, kind = (), "read_messages"
        elif target.path == profile.routes.get("delete_messages"):
            result, payload = self.server.state.delete_messages(token, request_id, body, self.server.message_catalog)
            transitions, kind = (), "delete_messages"
        elif target.path == profile.routes.get("exchange"):
            result, payload = self.server.state.exchange(token, request_id, body, self.server.exchange_catalog)
            transitions, kind = (), "exchange"
        elif target.path == profile.routes.get("add_exchange_count"):
            result, payload, transitions, kind = "unsupported_exchange_count", None, (), "exchange_count"
        elif target.path == profile.routes.get("statusup_item"):
            result, payload = self.server.state.use_statusup_item(token, request_id, body, self.server.statusup_catalog)
            transitions, kind = (), "statusup_item"
        elif target.path == profile.routes.get("add_job"):
            result, payload = self.server.state.add_job(token, request_id, body, self.server.job_catalog)
            transitions, kind = (), "add_job"
        elif target.path == profile.routes.get("rebirth"):
            result, payload = self.server.state.rebirth(token, request_id, body, self.server.rebirth_catalog)
            transitions, kind = (), "rebirth"
        elif target.path == profile.routes.get("summon_skill_unlock"):
            result, payload = self.server.state.summon_skill_unlock(token, request_id, body, self.server.summon_skill_catalog)
            transitions, kind = (), "summon_skill_unlock"
        elif target.path == profile.routes.get("sell_buddy"):
            result, payload = self.server.state.sell_companions(token, request_id, body, self.server.companion_catalog, multiple=False)
            transitions, kind = (), "sell_buddy"
        elif target.path == profile.routes.get("sell_buddies"):
            result, payload = self.server.state.sell_companions(token, request_id, body, self.server.companion_catalog, multiple=True)
            transitions, kind = (), "sell_buddies"
        elif target.path == profile.routes.get("buddy_strengthen"):
            result, payload = self.server.state.strengthen_companion(token, request_id, body, self.server.companion_strengthen_catalog)
            transitions, kind = (), "buddy_strengthen"
        elif target.path == profile.routes.get("buddy_evolve"):
            result, payload = self.server.state.evolve_companion(token, request_id, body, self.server.companion_evolution_catalog)
            transitions, kind = (), "buddy_evolve"
        else:
            transitions, kind = profile.story_clears, "clear"
        result: str
        payload: dict[str, Any] | None
        if kind in {"continue", "change_uname", "refill_stamina", "unlock_metal_zone", "achievement", "read_messages", "delete_messages", "exchange", "exchange_count", "statusup_item", "add_job", "rebirth", "summon_skill_unlock", "sell_buddy", "sell_buddies", "buddy_strengthen", "buddy_evolve", "do_buddy_slot", "companion_userdata", "ordinary_pact"}:
            pass
        elif kind == "write" and self.server.story_progression_catalog is not None and _parse_story_progression_reveal(body) is not None:
            result, payload = self.server.state.apply_story_progression_reveal(token, request_id, body, self.server.story_progression_catalog)
        elif kind == "start" and (self.server.story_catalog is not None or self.server.story_progression_catalog is not None) and not any(item["body"].encode("utf-8") == body for item in transitions):
            result, payload = self.server.state.apply_generic_story_start(token, request_id, body, self.server.story_catalog or self.server.story_progression_catalog)
        elif kind == "clear" and (self.server.story_catalog is not None or self.server.story_progression_catalog is not None) and not _profile_clear_matches(body, transitions):
            result, payload = self.server.state.apply_generic_story_clear(token, request_id, body, self.server.story_catalog or self.server.story_progression_catalog, self.server.settlement_catalog, self.server.story_outcome_catalog, self.server.clear_state_catalog)
        else:
            result, payload = self.server.state.apply_tutorial_transition(
                token,
                request_id,
                body,
                transitions,
                kind=kind,
            )
        if result in {"success", "replay"}:
            self._signed(HTTPStatus.OK, token, payload or {})
            return
        statuses = {
            "unknown_account": HTTPStatus.UNAUTHORIZED,
            "request_collision": HTTPStatus.CONFLICT,
            "tutorial_state_conflict": HTTPStatus.CONFLICT,
            "unsupported_summon": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_userdata_write": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_story_progression_reveal": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_start_quest": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_clear_quest": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_continue": HTTPStatus.NOT_IMPLEMENTED,
            "continue_unavailable": HTTPStatus.CONFLICT,
            "unsupported_change_uname": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_refill_stamina": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_unlock_metal_zone": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_achievement": HTTPStatus.NOT_IMPLEMENTED,
            "invalid_local_achievement": HTTPStatus.CONFLICT,
            "unsupported_message_read": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_message_delete": HTTPStatus.NOT_IMPLEMENTED,
            "invalid_local_message": HTTPStatus.CONFLICT,
            "unsupported_exchange": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_exchange_count": HTTPStatus.NOT_IMPLEMENTED,
            "invalid_local_exchange": HTTPStatus.CONFLICT,
            "unsupported_statusup_item": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_add_job": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_rebirth": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_summon_skill_unlock": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_companion_sale": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_companion_strengthen": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_companion_evolution": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_companion_draw": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_companion_userdata": HTTPStatus.NOT_IMPLEMENTED,
            "unsupported_ordinary_pact": HTTPStatus.NOT_IMPLEMENTED,
            "invalid_local_settlement": HTTPStatus.CONFLICT,
            "invalid_local_clear_state": HTTPStatus.CONFLICT,
            "invalid_local_outcome": HTTPStatus.CONFLICT,
        }
        self._json(statuses[result], {"error": result})

    def do_HEAD(self) -> None:
        target = urlsplit(self.path)
        resource = self.server.resource_catalog.resolve(target.path) if self.server.resource_catalog else None
        if resource is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "resource_not_found"})
            return
        self._resource(HTTPStatus.OK, resource, include_body=False)

    def _signed(self, status: HTTPStatus, token: str, payload: dict[str, Any]) -> None:
        body = _signed_json(token, payload, self.server.profile.signing)
        self.server.events.record(self.command, self.path, status, getattr(self, "_event_details", None))
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
        details = dict(getattr(self, "_event_details", {}) or {})
        if isinstance(payload.get("error"), str):
            details["error"] = payload["error"]
        self.server.events.record(self.command, self.path, status, details)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _html(self, status: HTTPStatus, value: str) -> None:
        body = value.encode("utf-8")
        self.server.events.record(self.command, self.path, status)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _empty(self, status: HTTPStatus) -> None:
        self.server.events.record(self.command, self.path, status)
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _resource(self, status: HTTPStatus, resource: Any, *, include_body: bool = True) -> None:
        body = resource.file.read_bytes()
        self.server.events.record(self.command, self.path, status)
        self.send_response(status)
        self.send_header("Content-Type", resource.content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if include_body:
            self.wfile.write(body)

    def _file(self, status: HTTPStatus, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.server.events.record(self.command, self.path, status)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _json_fields_match(values: dict[str, str], expected_kinds: dict[str, str]) -> bool:
    for name, expected_kind in expected_kinds.items():
        try:
            value = json.loads(values[name])
        except (KeyError, json.JSONDecodeError):
            return False
        if expected_kind == "object" and not isinstance(value, dict):
            return False
        if expected_kind == "array" and not isinstance(value, list):
            return False
    return True


def _profile_clear_matches(body: bytes, transitions: tuple[dict[str, Any], ...]) -> bool:
    try:
        fields = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return False
    values = dict(fields)
    return any(
        tuple(name for name, _ in fields) == tuple(item["field_names"])
        and all(values.get(name) == value for name, value in item["fixed_fields"].items())
        and _json_fields_match(values, item["json_fields"])
        for item in transitions
    )


def _parse_generic_story_start(body: bytes) -> dict[str, int] | None:
    fields = ("stamina", "coins", "chapter", "section", "lastUpdate")
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != fields:
            return None
        values = {name: int(value) for name, value in pairs}
    except (UnicodeDecodeError, ValueError):
        return None
    if any(value < 0 for value in values.values()) or values["chapter"] < 2 or values["section"] < 1:
        return None
    return values


def _parse_generic_story_clear(body: bytes) -> dict[str, Any] | None:
    fields = ("progressCode", "worldMapNo", "valuables", "chrdata", "itemList", "summonList", "battle_result", "itmp0", "itmp1", "lastUpdate")
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != fields:
            return None
        raw = dict(pairs)
        result = {
            "progressCode": int(raw["progressCode"]), "worldMapNo": int(raw["worldMapNo"]),
            "valuables": json.loads(raw["valuables"]), "chrdata": json.loads(raw["chrdata"]),
            "itemList": json.loads(raw["itemList"]), "summonList": json.loads(raw["summonList"]),
            "battle_result": json.loads(raw["battle_result"]), "itmp0": int(raw["itmp0"]),
            "itmp1": int(raw["itmp1"]), "lastUpdate": int(raw["lastUpdate"]),
        }
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    if any(type(result[name]) is not int or result[name] < 0 for name in ("progressCode", "worldMapNo", "itmp0", "itmp1", "lastUpdate")):
        return None
    valuable_fields = {"energyAppStore", "energy", "energyAndApp", "freeEnergy", "energyGooglePlay", "coins"}
    if type(result["valuables"]) is not dict or set(result["valuables"]) != valuable_fields or any(type(value) is not int or value < 0 for value in result["valuables"].values()):
        return None
    if type(result["chrdata"]) is not list or not result["chrdata"] or any(not _valid_generic_character_record(row) for row in result["chrdata"]) or len({row["id"] for row in result["chrdata"]}) != len(result["chrdata"]):
        return None
    if type(result["itemList"]) is not list or any(type(value) is not int or value < 0 for value in result["itemList"]) or type(result["summonList"]) is not list or any(type(value) is not int or value < 0 for value in result["summonList"]):
        return None
    battle = result["battle_result"]
    battle_fields = {"coins", "buddies", "items", "exp", "section", "monsters", "summons", "luckynum", "chapter", "unableluckdrop", "boostup"}
    if not isinstance(battle, dict) or set(battle) - {"counters"} != battle_fields or any(type(battle.get(name)) is not int or battle[name] < 0 for name in ("coins", "exp", "section", "luckynum", "chapter")) or battle["chapter"] < 2 or battle["section"] < 1 or type(battle["unableluckdrop"]) is not bool:
        return None
    if "counters" in battle and type(battle["counters"]) is not str:
        return None
    if any(type(battle[name]) is not list or any(type(value) is not int or value < 0 for value in battle[name]) for name in ("buddies", "monsters", "summons")):
        return None
    if type(battle["items"]) is not dict or any(not isinstance(item_id, str) or not item_id.isdecimal() or int(item_id) <= 0 or type(count) is not int or count < 1 for item_id, count in battle["items"].items()):
        return None
    if type(battle["boostup"]) is not list or len(battle["boostup"]) != 6 or any(type(value) is not int or value < 0 for value in battle["boostup"]):
        return None
    return result


def _parse_story_progression_reveal(body: bytes) -> dict[str, int] | None:
    """Parse the reviewed ordered post-chapter userdata map write."""
    fields = ("progressCode", "worldMapNo", "lastUpdate")
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != fields:
            return None
        values = {name: int(value) for name, value in pairs}
    except (UnicodeDecodeError, ValueError):
        return None
    return values if all(value >= 0 for value in values.values()) else None


def _valid_generic_character_record(row: object) -> bool:
    fields = {"id", "buddy", "date", "jobSlots", "jobLevels", "jobID", "flags", "skillBoost"}
    if not isinstance(row, dict) or set(row) not in (fields, fields | {"luck"}):
        return False
    if any(type(row[name]) is not int or row[name] < 0 for name in ("id", "buddy", "jobID", "flags", "skillBoost")) or ("luck" in row and (type(row["luck"]) is not int or not 0 <= row["luck"] <= 1000)):
        return False
    if type(row["date"]) not in {int, float} or not math.isfinite(row["date"]) or row["date"] < 0:
        return False
    return all(isinstance(row[name], list) and len(row[name]) == 3 and all(type(value) in {int, float} and math.isfinite(value) and value >= 0 and int(value) == value and (name != "jobSlots" or value <= 0xFFFFFFFF) for value in row[name]) for name in ("jobSlots", "jobLevels"))


def _parse_continue(body: bytes) -> int | None:
    """Parse the final-client Continue form, allowing a trailing lastUpdate."""
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if pairs and pairs[-1][0] == "lastUpdate":
        pairs = pairs[:-1]
    if tuple(name for name, _ in pairs) != ("cost",):
        return None
    try:
        return int(pairs[0][1])
    except ValueError:
        return None


def _parse_change_uname(body: bytes) -> str | None:
    try:
        pairs = tuple(parse_qsl(body.decode("utf-8"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("name",):
        return None
    name = pairs[0][1]
    return name if 1 <= len(name) <= 13 else None


def _parse_refill_stamina(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        return int(pairs[0][1]) if tuple(name for name, _ in pairs) == ("cost",) else None
    except (UnicodeDecodeError, ValueError, IndexError):
        return None


def _parse_statusup_item(body: bytes) -> tuple[int, int, int] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("targetChrID", "useItemID", "useAmount"):
        return None
    values = tuple(value for _, value in pairs)
    if any(not value.isdecimal() or int(value) <= 0 for value in values):
        return None
    return tuple(int(value) for value in values)  # type: ignore[return-value]


def _parse_add_job(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    names = tuple(name for name, _ in pairs)
    if names not in (("targetID",), ("targetID", "isTutorial"), ("targetID", "lastUpdate"), ("targetID", "isTutorial", "lastUpdate")):
        return None
    target = pairs[0][1]
    if not target.isdecimal() or int(target) <= 0:
        return None
    if len(pairs) >= 2 and names[1] == "isTutorial" and pairs[1][1] != "True":
        return None
    if names[-1] == "lastUpdate" and pairs[-1][1] != "1":
        return None
    return int(target)


def _parse_rebirth(body: bytes) -> tuple[int, bool] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("rebirthID", "useJoker") or not pairs[0][1].isdecimal() or int(pairs[0][1]) <= 0 or pairs[1][1] not in {"False", "True"}:
        return None
    return int(pairs[0][1]), pairs[1][1] == "True"


def _parse_summon_skill_unlock(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("targetID",):
        return None
    target_id = pairs[0][1]
    if not target_id.isdecimal() or not 1 <= int(target_id) <= 16:
        return None
    return int(target_id)


def _parse_achievement_claim(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("id", "lastUpdate") or pairs[1][1] != "1":
        return None
    return int(pairs[0][1]) if pairs[0][1].isdecimal() and int(pairs[0][1]) > 0 else None


def _parse_sell_companions(body: bytes, *, multiple: bool) -> list[int] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    field = "sellList" if multiple else "inventoryID"
    if tuple(name for name, _ in pairs) != (field,):
        return None
    value = pairs[0][1].strip()
    if multiple and value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    values = value.split(",") if multiple else [value]
    if not values:
        return None
    try:
        ids = [int(item.strip()) for item in values]
    except ValueError:
        return None
    return ids if all(value > 0 for value in ids) and len(ids) == len(set(ids)) else None


def _companion_info(owned: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    records: dict[int, dict[str, Any]] = {}
    for companion in owned:
        current = records.get(companion["bid"])
        if current is None or (companion["lv"], companion["iid"]) > (current["lv"], current["iid"]):
            records[companion["bid"]] = copy.deepcopy(companion)
    return {"list": copy.deepcopy(owned), "record": [records[companion_id] for companion_id in sorted(records)]}


def _parse_companion_strengthen(body: bytes) -> tuple[int, list[int]] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if len(pairs) == 3 and pairs[-1] == ("lastUpdate", "1"):
        pairs = pairs[:-1]
    if tuple(name for name, _ in pairs) != ("baseID", "matList"):
        return None
    try:
        base_id = int(pairs[0][1])
    except ValueError:
        return None
    value = pairs[1][1].strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1].strip()
    try:
        materials = [int(item.strip()) for item in value.split(",")]
    except ValueError:
        return None
    if base_id <= 0 or not 1 <= len(materials) <= 4 or base_id in materials or any(item <= 0 for item in materials) or len(materials) != len(set(materials)):
        return None
    return base_id, materials


def _parse_companion_evolve(body: bytes) -> int | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if len(pairs) == 2 and pairs[-1] == ("lastUpdate", "1"):
        pairs = pairs[:-1]
    if tuple(name for name, _ in pairs) != ("baseID",):
        return None
    value = pairs[0][1]
    return int(value) if value.isdecimal() and int(value) > 0 else None


def _parse_companion_draw(body: bytes) -> tuple[int, int] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("kind", "count", "campaignID", "eventFlag", "lastUpdate"):
        return None
    try:
        values = {name: int(value) for name, value in pairs}
    except ValueError:
        return None
    if values["kind"] not in {1, 21} or not 1 <= values["count"] <= 100 or values["campaignID"] != 0 or values["eventFlag"] != 0 or values["lastUpdate"] < 0:
        return None
    return values["kind"], values["count"]


def _parse_ordinary_pact_draw(body: bytes) -> tuple[int, int] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
    except (UnicodeDecodeError, ValueError):
        return None
    if tuple(name for name, _ in pairs) != ("kind", "count", "luckType", "campaignChrID", "eventFlag", "lastUpdate"):
        return None
    values = dict(pairs)
    if values["kind"] not in {"0", "1"} or values["luckType"] != "false" or values["campaignChrID"] != "0" or values["eventFlag"] != "0" or not values["count"].isdecimal() or not values["lastUpdate"].isdecimal():
        return None
    kind, count = int(values["kind"]), int(values["count"])
    if count not in ({1, 10} if kind == 0 else {1, 5, 10}):
        return None
    return kind, count


def _parse_companion_userdata_write(body: bytes) -> list[dict[str, Any]] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        if tuple(name for name, _ in pairs) != ("buddyInfo", "lastUpdate") or int(pairs[1][1]) < 0:
            return None
        companions = json.loads(pairs[0][1])
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    fields = {"bid", "lv", "date", "iid", "exp", "flag", "chrID"}
    if not isinstance(companions, list) or not companions:
        return None
    if any(not isinstance(companion, dict) or set(companion) != fields or type(companion["bid"]) is not int or companion["bid"] <= 0 or type(companion["lv"]) is not int or companion["lv"] < 1 or type(companion["date"]) not in {int, float} or companion["date"] < 0 or any(type(companion[name]) is not int or companion[name] < 0 for name in ("iid", "exp", "flag", "chrID")) or companion["iid"] <= 0 for companion in companions):
        return None
    ids = [companion["iid"] for companion in companions]
    return companions if len(ids) == len(set(ids)) else None


def _draw_companion_id(catalog: CompanionDrawCatalog) -> int:
    threshold = random.SystemRandom().randrange(sum(draw.weight for draw in catalog.draws))
    for draw in catalog.draws:
        if threshold < draw.weight:
            return draw.companion_id
        threshold -= draw.weight
    raise AssertionError("invalid Companion-draw weights")


def _companion_exp_at(master: Any, level: int) -> int:
    if level <= 1:
        return 0
    return math.floor(master.exp_max * ((level - 1) / 98.0) ** master.exp_coeff)


def _companion_level_at_exp(master: Any, experience: int) -> int:
    level = 1
    for candidate in range(2, master.max_level + 1):
        if _companion_exp_at(master, candidate) > experience:
            break
        level = candidate
    return level


def _draw_companion_bonus(catalog: CompanionStrengthenCatalog) -> int:
    threshold = random.SystemRandom().randrange(sum(weight for _, weight in catalog.bonus_weights))
    for percent, weight in catalog.bonus_weights:
        if threshold < weight:
            return percent
        threshold -= weight
    raise AssertionError("invalid Companion-strengthen bonus weights")


def _apply_statusup_effect(
    row: dict[str, Any], effect: Any, character: Any, catalog: StatusupCatalog, amount: int,
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    candidate = copy.deepcopy(row)
    levels = candidate["jobLevels"]
    if not all(type(value) in {int, float} and value >= 0 for value in levels):
        return None, {}
    added_levels: dict[str, int] = {}
    for index, raw in enumerate(levels):
        packed = int(raw)
        if packed == 0:
            continue
        old = packed & 0xFFF
        new = min(catalog.level_cap, old + effect.level * amount)
        if new != old:
            levels[index] = float((packed & ~0xFFF) | new) if type(raw) is float else (packed & ~0xFFF) | new
            added_levels[str(index)] = new - old
    old_boost = candidate.get("skillBoost", 0)
    old_luck = candidate.get("luck", 0)
    if type(old_boost) is not int or type(old_luck) is not int or old_boost < 0 or old_luck < 0:
        return None, {}
    new_boost = min(catalog.skill_boost_cap, old_boost + effect.skill_boost * amount * 10)
    new_luck = min(character.luck_cap, old_luck + effect.luck * amount * 10)
    if not added_levels and new_boost == old_boost and new_luck == old_luck:
        return None, {}
    candidate["skillBoost"], candidate["luck"] = new_boost, new_luck
    return candidate, {
        "addedLevels": added_levels,
        "addedSkillBoost": (new_boost - old_boost) // 10,
        "addedLuck": (new_luck - old_luck) // 10,
    }


def _ordered_refill_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Restore the emitted refill-field order after sorted JSON state reload."""
    if payload.get("success") is False:
        return {"success": False, "errorCode": payload["errorCode"]}
    fields = (
        "success", "refillStartTime", "energy", "energyAppStore",
        "energyGooglePlay", "energyAndApp", "freeEnergy", "bonusStamina",
    )
    return {field: payload[field] for field in fields}


def _canonical_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Stabilize nested signed callback order through sorted JSON persistence."""
    return json.loads(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _achievement_flags(claimed: list[int]) -> list[int]:
    if not claimed:
        return []
    flags = [0] * (max(claimed) // 30 + 1)
    for achievement_id in claimed:
        flags[achievement_id // 30] |= 1 << (achievement_id % 30)
    return flags


def _initial_messages(catalog: MessageCatalog | None) -> dict[str, dict[str, Any]]:
    if catalog is None:
        return {}
    return {
        message.message_id: {
            "id": message.message_id, "date": message.date, "read": False, "days_last": message.days_last,
            "messages": copy.deepcopy(message.texts), "coins": message.coins, "free_energy": message.free_energy,
            "items": {str(item_id): amount for item_id, amount in message.items.items()},
        }
        for message in catalog.messages
    }


def _initial_exchange_remaining(catalog: ExchangeCatalog | None) -> dict[str, int]:
    return {} if catalog is None else {str(offer.offer_id): offer.initial_count for offer in catalog.offers.values()}


def _parse_exchange(body: bytes) -> tuple[int, int] | None:
    try:
        pairs=tuple(parse_qsl(body.decode("ascii"),keep_blank_values=True,strict_parsing=True))
    except (UnicodeDecodeError,ValueError): return None
    names=tuple(name for name,_ in pairs)
    if names not in (("exchangeItemID","amount"),("exchangeItemID","amount","lastUpdate")): return None
    if len(pairs)==3 and (not pairs[2][1].isdecimal() or int(pairs[2][1])<0): return None
    if not pairs[0][1].isdecimal() or not pairs[1][1].isdecimal(): return None
    return (int(pairs[0][1]),int(pairs[1][1])) if int(pairs[0][1])>0 and int(pairs[1][1])>0 else None


def _message_wire(message: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": message["id"], "date": float(message["date"]), "read": bool(message["read"]), "daysLast": int(message["days_last"]),
        "gifts": [], "coins": int(message["coins"]), "energy": int(message["free_energy"]), "chr": 0,
        "item": [{"id": int(item_id), "num": amount} for item_id, amount in sorted(message["items"].items(), key=lambda value: int(value[0]))],
        "summon": 0, "buddy": 0, "title": 0, "messages": copy.deepcopy(message["messages"]),
    }


def _message_reload_projection(userdata: dict[str, Any], account: dict[str, Any]) -> dict[str, Any]:
    buddy_info = userdata.get("buddyInfo", {"list": [], "record": []})
    return {
        "chrdata": copy.deepcopy(userdata.get("chrdata", [])), "buddyInfo": copy.deepcopy(buddy_info),
        "summonList": copy.deepcopy(userdata.get("summonList", [0] * 16)),
        "achivementFlags": _achievement_flags(account.get("claimed_achievements", [])),
        "energyAppStore": int(userdata.get("energyAppStore", 0)), "energyGooglePlay": int(userdata.get("energyGooglePlay", 0)),
        "energyAndApp": int(userdata.get("energyAndApp", 0)),
    }


def _parse_message_ids(body: bytes) -> list[str] | None:
    try:
        pairs = tuple(parse_qsl(body.decode("ascii"), keep_blank_values=True, strict_parsing=True))
        names = tuple(name for name, _ in pairs)
        if names not in (("idlist",), ("idlist", "lastUpdate")) or len(pairs) == 2 and (not pairs[1][1].isdecimal() or int(pairs[1][1]) < 0):
            return None
        identifiers = json.loads(pairs[0][1])
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None
    return identifiers if type(identifiers) is list and identifiers and len(identifiers) == len(set(identifiers)) and all(isinstance(identifier, str) and identifier for identifier in identifiers) else None


def _settlement_matches(userdata: dict[str, Any], clear: dict[str, Any], identity: tuple[int, int], catalog: SettlementCatalog) -> bool:
    rule = catalog.rules.get(identity)
    current = userdata.get("chrdata", [])
    submitted = clear["chrdata"]
    if not (rule and isinstance(current, list) and all(isinstance(row, dict) and type(row.get("id")) is int for row in current) and all(isinstance(row, dict) and type(row.get("id")) is int for row in submitted)):
        return False
    current_ids = {row["id"] for row in current}
    submitted_ids = {row["id"] for row in submitted}
    if len(submitted_ids) != len(submitted) or not current_ids <= submitted_ids or submitted_ids - current_ids != rule.character_rewards or not submitted_ids <= catalog.character_ids:
        return False
    return _projected_list(userdata.get("itemList", []), clear["itemList"], rule.item_rewards, catalog.item_slots, catalog.max_stack) and _projected_list(userdata.get("summonList", []), clear["summonList"], rule.summon_rewards, catalog.summon_slots, catalog.max_stack)


def _clear_state_matches(userdata: dict[str, Any], clear: dict[str, Any], catalog: ClearStateCatalog) -> bool:
    """Verify the persisted party's only legal EXP/boost clear projection."""
    current_rows = userdata.get("chrdata")
    submitted_rows = clear["chrdata"]
    team = userdata.get("teamMembers")
    if not (isinstance(current_rows, list) and isinstance(team, list) and len(team) == catalog.team_slots and all(type(value) is int and value >= 0 for value in team)):
        return False
    current = {row.get("id"): row for row in current_rows if _valid_generic_character_record(row)}
    submitted = {row.get("id"): row for row in submitted_rows if _valid_generic_character_record(row)}
    if len(current) != len(current_rows) or len(submitted) != len(submitted_rows) or not set(current) <= set(submitted) or any(character_id not in catalog.characters for character_id in submitted) or len([value for value in team if value]) != len(set(value for value in team if value)) or any(value and value not in current for value in team):
        return False
    if any(not _is_initial_story_character(submitted[character_id]) for character_id in set(submitted) - set(current)):
        return False
    eligible: list[int] = []
    for character_id in team:
        if not character_id:
            continue
        row = current[character_id]
        job_id = row["jobID"]
        if job_id >= 3:
            return False
        progression = catalog.characters[character_id].jobs[job_id]
        if int(row["jobLevels"][job_id]) >> 12 < progression.maximum_experience:
            eligible.append(character_id)
    experience = clear["battle_result"]["exp"]
    if experience and not eligible:
        return False
    share = experience // len(eligible) if eligible else 0
    boosts = {character_id: clear["battle_result"]["boostup"][slot] for slot, character_id in enumerate(team) if character_id}
    duplicates = Counter(clear["battle_result"].get("monsters", []))
    if any(value > catalog.max_skill_boost_per_battle or (not team[slot] and value) for slot, value in enumerate(clear["battle_result"]["boostup"])):
        return False
    immutable = ("id", "buddy", "date", "jobSlots", "jobID", "flags", "luck")
    for character_id, old in current.items():
        candidate = submitted[character_id]
        if any(old.get(name) != candidate.get(name) for name in immutable):
            return False
        job_id = old["jobID"]
        if job_id >= 3 or any(candidate["jobLevels"][index] != old["jobLevels"][index] for index in range(3) if index != job_id):
            return False
        progression = catalog.characters[character_id].jobs[job_id]
        old_experience = int(old["jobLevels"][job_id]) >> 12
        if old_experience > progression.maximum_experience:
            return False
        expected_experience = min(progression.maximum_experience, old_experience + (share if character_id in eligible else 0))
        expected_level = max(index + 1 for index, threshold in enumerate(progression.level_thresholds) if threshold <= expected_experience)
        if candidate["jobLevels"][job_id] != (expected_experience << 12) | expected_level:
            return False
        duplicate_gain = catalog.characters[character_id].duplicate_skill_boost * duplicates.get(character_id, 0)
        expected_boost = min(catalog.max_skill_boost, old["skillBoost"] + boosts.get(character_id, 0) + duplicate_gain)
        if candidate["skillBoost"] != expected_boost:
            return False
    return True


def _is_initial_story_character(row: dict[str, Any]) -> bool:
    """Return whether a newly reported character has the recovered Init shape."""
    return (
        row["buddy"] == 0
        and row["date"] == 0
        and row["jobID"] == 0
        and row["flags"] == 0
        and row["skillBoost"] == 0
        and int(row.get("luck", 0)) == 0
        and row["jobSlots"] == [0, 0, 0]
        and row["jobLevels"] == [1, 0, 0]
    )


def _outcome_buddy_info(userdata: dict[str, Any], clear: dict[str, Any], identity: tuple[int, int], catalog: StoryOutcomeCatalog, clear_state_catalog: ClearStateCatalog | None = None) -> dict[str, list[dict[str, Any]]] | None:
    """Validate client-reported outcome maxima and author local Companion rows."""
    rule = catalog.rules.get(identity)
    result = clear["battle_result"]
    current_rows = userdata.get("chrdata")
    submitted_rows = clear["chrdata"]
    if rule is None or not isinstance(current_rows, list) or any(not _valid_generic_character_record(row) or row["id"] not in catalog.character_ids for row in current_rows):
        return None
    current_ids = {row["id"] for row in current_rows}
    submitted_ids = {row["id"] for row in submitted_rows}
    if len(current_ids) != len(current_rows) or not current_ids <= submitted_ids or not submitted_ids <= catalog.character_ids:
        return None
    new_ids = submitted_ids - current_ids
    reported_monsters = Counter(result["monsters"])
    reported_new = Counter({character_id: count for character_id, count in reported_monsters.items() if character_id not in current_ids})
    reported_duplicates = reported_monsters - reported_new
    if Counter(new_ids) != reported_new or not outcome_allowed(reported_monsters, rule.character_maxima) or (reported_duplicates and clear_state_catalog is None):
        return None
    reported_items = Counter({int(item_id): count for item_id, count in result["items"].items()})
    if not outcome_allowed(reported_items, rule.item_maxima) or not _projected_list(userdata.get("itemList", []), clear["itemList"], dict(reported_items), catalog.item_slots, catalog.max_stack):
        return None
    if result["summons"] or clear["summonList"] != userdata.get("summonList", []):
        return None
    raw_info = userdata.get("buddyInfo", {"list": [], "record": []})
    owned = raw_info.get("list") if isinstance(raw_info, dict) else None
    if not isinstance(owned, list) or any(not isinstance(row, dict) or set(row) != {"bid", "lv", "date", "iid", "exp", "flag", "chrID"} or type(row.get("bid")) is not int or type(row.get("iid")) is not int or row["iid"] <= 0 for row in owned):
        return None
    known_ids = {row["iid"] for row in owned}
    if len(known_ids) != len(owned):
        return None
    reported_companions = Counter(result["buddies"])
    if not outcome_allowed(reported_companions, rule.companion_maxima) or any(companion_id not in catalog.companion_masters for companion_id in reported_companions) or len(owned) + len(result["buddies"]) > catalog.max_companions:
        return None
    next_id = userdata.get("nextCompanionInventoryId", max(known_ids, default=0) + 1)
    if type(next_id) is not int or next_id <= max(known_ids, default=0):
        return None
    rows = copy.deepcopy(owned)
    for companion_id in result["buddies"]:
        rows.append({"bid": companion_id, "lv": catalog.companion_masters[companion_id].drop_level, "date": 0.0, "iid": next_id, "exp": 0, "flag": 0, "chrID": 0})
        next_id += 1
    userdata["nextCompanionInventoryId"] = next_id
    return _companion_info(rows)


def _projected_list(current: object, submitted: object, rewards: dict[int, int], slots: int, maximum: int) -> bool:
    if not (isinstance(current, list) and isinstance(submitted, list) and len(current) == slots and len(submitted) == slots and all(type(value) is int and 0 <= value <= maximum for value in current)):
        return False
    expected = list(current)
    for item_id, count in rewards.items():
        if item_id > slots:
            return False
        expected[item_id - 1] = min(maximum, expected[item_id - 1] + count)
    return submitted == expected


def _render(value: Any, token: str, account_id: str | None = None) -> Any:
    if isinstance(value, str):
        rendered = value.replace("{otk}", token)
        return rendered if account_id is None else rendered.replace("{uuid}", account_id)
    if isinstance(value, list):
        return [_render(item, token, account_id) for item in value]
    if isinstance(value, dict):
        return {key: _render(item, token, account_id) for key, item in value.items()}
    return copy.deepcopy(value)


def _signed_json(token: str, payload: dict[str, Any], signing: SigningProfile) -> bytes:
    placeholder = "0" * (signing.digest_end - signing.digest_start)
    unsigned_payload = {**payload, "digest": placeholder}
    text = json.dumps(unsigned_payload, ensure_ascii=True) + "\n"
    marker = '"digest": "'
    digest_offset = text.index(marker) + len(marker)
    unsigned = text[:digest_offset] + text[digest_offset + len(placeholder):]
    digest = hashlib.md5((token + unsigned + signing.salt).encode("utf-8")).hexdigest().upper()
    selected = digest[signing.digest_start:signing.digest_end]
    return (text[:digest_offset] + selected + text[digest_offset + len(placeholder):]).encode("utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="strict user-local TOML launcher configuration")
    parser.add_argument("--profile", type=Path)
    parser.add_argument("--state-file", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument(
        "--event-log",
        type=Path,
        help="optional local JSONL diagnostics containing only method, path, status, and timestamp",
    )
    parser.add_argument("--resource-root", type=Path, help="user-local root containing manifest-mapped files")
    parser.add_argument("--resource-manifest", type=Path, help="user-local explicit resource mapping manifest")
    parser.add_argument("--public-data-root", type=Path, help="user-local derived PNGs for supported public-data image paths")
    parser.add_argument("--story-catalog", type=Path, help="user-local normalized generic-story catalog")
    parser.add_argument("--story-progression-catalog", type=Path, help="user-derived reviewed core-story progression catalog")
    parser.add_argument("--core-story", action="store_true", help="enable the bundled ordinary Chapter 2--42 progression policy without reward data")
    parser.add_argument("--settlement-catalog", type=Path, help="optional user-local generic-story identity/reward constraints")
    parser.add_argument("--story-outcome-catalog", type=Path, help="user-local generic-story reported-outcome bounds and Companion drop levels")
    parser.add_argument("--clear-state-catalog", type=Path, help="user-local generic-story character EXP and Skill-Boost constraints")
    parser.add_argument("--statusup-catalog", type=Path, help="user-local item/character rules for status-up progression")
    parser.add_argument("--job-catalog", type=Path, help="user-local ordered job-unlock costs")
    parser.add_argument("--rebirth-catalog", type=Path, help="user-local Rebirth recipe and Joker policy")
    parser.add_argument("--summon-skill-catalog", type=Path, help="user-local Battle Summon skill costs")
    parser.add_argument("--companion-catalog", type=Path, help="user-local Companion master values for ownership mutations")
    parser.add_argument("--companion-strengthen-catalog", type=Path, help="user-local Companion progression values and bonus policy")
    parser.add_argument("--companion-evolution-catalog", type=Path, help="user-local Companion evolution rows and costs")
    parser.add_argument("--companion-draw-catalog", type=Path, help="user-local Companion draw pool and costs")
    parser.add_argument("--pact-draw-catalog", type=Path, help="user-local ordinary Pact pool, rates, and duplicate policy")
    parser.add_argument("--pacts", action="store_true", help="enable the bundled local Fellowship and Truth Pact policy")
    parser.add_argument("--achievement-catalog", type=Path, help="user-local clear-chapter achievement thresholds and rewards")
    parser.add_argument("--message-catalog", type=Path, help="user-local inbox messages and bounded local rewards")
    parser.add_argument("--exchange-catalog", type=Path, help="user-local Trading Post offers and bounded settlements")
    return parser.parse_args()


def load_launch_config(args: argparse.Namespace) -> ServerConfig:
    fields = (
        "profile", "state_file", "host", "port", "event_log", "resource_root", "resource_manifest", "public_data_root",
        "story_catalog", "story_progression_catalog", "core_story", "settlement_catalog", "story_outcome_catalog", "clear_state_catalog", "statusup_catalog", "job_catalog",
        "rebirth_catalog", "summon_skill_catalog", "companion_catalog", "companion_strengthen_catalog",
        "companion_evolution_catalog", "companion_draw_catalog", "pact_draw_catalog", "pacts", "achievement_catalog", "message_catalog", "exchange_catalog",
    )
    if args.config is not None:
        if any(getattr(args, field, None) is not None for field in fields):
            raise ProfileError("--config cannot be combined with individual launcher options")
        return load_server_config(args.config)
    if args.profile is None or args.state_file is None:
        raise ProfileError("--profile and --state-file are required without --config")
    if args.host is not None and (not args.host or "\x00" in args.host):
        raise ProfileError("--host must be a nonempty string")
    if args.port is not None and not 1 <= args.port <= 65535:
        raise ProfileError("--port must be an integer from 1 through 65535")
    return ServerConfig(
        profile=args.profile, state_file=args.state_file,
        host="127.0.0.1" if args.host is None else args.host, port=8080 if args.port is None else args.port,
        event_log=args.event_log, resource_root=args.resource_root, resource_manifest=args.resource_manifest, public_data_root=getattr(args, "public_data_root", None),
        story_catalog=args.story_catalog, core_story=getattr(args, "core_story", False), settlement_catalog=args.settlement_catalog,
        story_progression_catalog=args.story_progression_catalog,
        story_outcome_catalog=args.story_outcome_catalog, clear_state_catalog=args.clear_state_catalog, statusup_catalog=args.statusup_catalog,
        job_catalog=args.job_catalog, rebirth_catalog=args.rebirth_catalog,
        summon_skill_catalog=args.summon_skill_catalog, companion_catalog=args.companion_catalog,
        companion_strengthen_catalog=args.companion_strengthen_catalog,
        companion_evolution_catalog=args.companion_evolution_catalog,
        companion_draw_catalog=args.companion_draw_catalog, pact_draw_catalog=args.pact_draw_catalog, pacts=getattr(args, "pacts", False),
        achievement_catalog=args.achievement_catalog,
        message_catalog=args.message_catalog,
        exchange_catalog=args.exchange_catalog,
    )


def main() -> int:
    args = parse_args()
    try:
        args = load_launch_config(args)
        if (args.resource_root is None) != (args.resource_manifest is None):
            raise ProfileError("--resource-root and --resource-manifest must be supplied together")
        resources = None if args.resource_root is None else load_resource_catalog(args.resource_manifest, args.resource_root)
        stories = None if args.story_catalog is None else load_story_catalog(args.story_catalog)
        if args.core_story and args.story_progression_catalog is not None:
            raise ProfileError("--core-story cannot be combined with --story-progression-catalog")
        progression = build_core_story_policy() if args.core_story else (None if args.story_progression_catalog is None else load_story_progression_catalog(args.story_progression_catalog))
        if stories is not None and progression is not None:
            raise ProfileError("--story-catalog and --story-progression-catalog cannot be combined")
        settlements = None if args.settlement_catalog is None else load_settlement_catalog(args.settlement_catalog)
        story_outcomes = None if args.story_outcome_catalog is None else load_story_outcome_catalog(args.story_outcome_catalog)
        clear_states = None if args.clear_state_catalog is None else load_clear_state_catalog(args.clear_state_catalog)
        statusup = None if args.statusup_catalog is None else load_statusup_catalog(args.statusup_catalog)
        jobs = None if args.job_catalog is None else load_job_catalog(args.job_catalog)
        rebirths = None if args.rebirth_catalog is None else load_rebirth_catalog(args.rebirth_catalog)
        summon_skills = None if args.summon_skill_catalog is None else load_summon_skill_catalog(args.summon_skill_catalog)
        companions = None if args.companion_catalog is None else load_companion_catalog(args.companion_catalog)
        companion_strengthen = None if args.companion_strengthen_catalog is None else load_companion_strengthen_catalog(args.companion_strengthen_catalog)
        companion_evolution = None if args.companion_evolution_catalog is None else load_companion_evolution_catalog(args.companion_evolution_catalog)
        companion_draw = None if args.companion_draw_catalog is None else load_companion_draw_catalog(args.companion_draw_catalog)
        if args.pacts and args.pact_draw_catalog is not None:
            raise ProfileError("--pacts cannot be combined with --pact-draw-catalog")
        pact_draw = build_bundled_pact_policy() if args.pacts else (None if args.pact_draw_catalog is None else load_pact_draw_catalog(args.pact_draw_catalog))
        achievements = None if args.achievement_catalog is None else load_achievement_catalog(args.achievement_catalog)
        messages = None if args.message_catalog is None else load_message_catalog(args.message_catalog)
        exchanges = None if args.exchange_catalog is None else load_exchange_catalog(args.exchange_catalog)
        server = BootstrapServer(
            (args.host, args.port),
            load_profile(args.profile),
            BootstrapState(args.state_file),
            args.event_log,
            resources,
            stories,
            settlements,
            story_outcomes,
            statusup,
            jobs,
            rebirths,
            summon_skills,
            companions,
            companion_strengthen,
            companion_evolution,
            companion_draw,
            pact_draw,
            achievements,
            messages,
            exchanges,
            clear_state_catalog=clear_states,
            story_progression_catalog=progression,
            public_data_root=args.public_data_root,
        )
    except (OSError, ProfileError, ServerConfigError, ResourceCatalogError, StoryCatalogError, StoryProgressionCatalogError, SettlementCatalogError, StoryOutcomeCatalogError, ClearStateCatalogError, StatusupCatalogError, JobCatalogError, RebirthCatalogError, SummonSkillCatalogError, CompanionCatalogError, CompanionStrengthenCatalogError, CompanionEvolutionCatalogError, CompanionDrawCatalogError, PactDrawCatalogError, AchievementCatalogError, MessageCatalogError, ExchangeCatalogError) as error:
        raise SystemExit(f"bootstrap server failed: {error}") from error
    print(f"bootstrap compatibility server listening on http://{args.host}:{args.port}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
