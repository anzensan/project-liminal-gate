"""Profile-driven bootstrap compatibility server with local durable state.

The engine can serve either a bundled, narrowly reviewed profile or a
user-local compatibility profile. Each profile declares only the operations it
actually supports; every other route deliberately remains unsupported.
"""

from __future__ import annotations

import argparse
from collections import Counter
import copy
from dataclasses import dataclass, replace
import hashlib
import json
import math
import os
import random
import shutil
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import tempfile
from threading import Lock
import time
from typing import Any, Callable

try:  # POSIX advisory locking
    import fcntl
except ImportError:  # pragma: no cover - exercised on Windows only
    fcntl = None
try:  # Windows advisory locking
    import msvcrt
except ImportError:  # pragma: no cover - exercised on Windows only
    msvcrt = None
from urllib.parse import parse_qsl, urlencode, urlsplit

from liminal_gate.archive_economy import award_chapter_energy, award_stage_energy
from liminal_gate.bootstrap_profile import (
    BODY_TRANSITION_FIELDS,
    MUTATION_ROUTE_NAMES,
    PROFILE_SCHEMA_VERSION,
    READ_ROUTE_NAMES,
    STRUCTURAL_TRANSITION_FIELDS,
    SUPPORTED_PROFILE_OPERATIONS,
    TEMPLATED_RESPONSE_OPERATIONS,
    LEGACY_TUTORIAL_RECRUIT_ID,
    TUTORIAL_RECRUIT_TOKEN,
    TUTORIAL_STARTER_TOKEN,
    TUTORIAL_SUMMON_BASE_FIELDS,
    TUTORIAL_SUMMON_OUTCOME_FIELDS,
    VALID_JSON_FIELD_KINDS,
    BootstrapProfile,
    MutationDispatch,
    MutationOperation,
    ProfileError,
    SigningProfile,
    _resolve_tutorial_template,
    _tutorial_recruit_id,
    _tutorial_starter_id,
    _valid_body_transition,
    _valid_structural_transition,
    _valid_tutorial_summon_transition,
    load_profile,
)
from liminal_gate.bootstrap_parsers import (
    _TICKET_START_FIELDS,
    _apply_companion_delta,
    _companion_info,
    _companion_target_allowed,
    _decoded_companions,
    _decoded_roster,
    _identity_chapter,
    _parse_achievement_claim,
    _parse_add_job,
    _parse_change_uname,
    _parse_companion_draw,
    _parse_companion_equip_userdata_write,
    _parse_companion_evolve,
    _parse_companion_strengthen,
    _parse_companion_userdata_write,
    _parse_continue,
    _parse_free_roam_character_userdata_write,
    _parse_free_roam_party_layout_userdata_write,
    _parse_free_roam_party_userdata_write,
    _parse_generic_story_clear,
    _parse_generic_story_start,
    _parse_hunting_start,
    _parse_ordinary_pact_draw,
    _parse_party_companion_userdata_write,
    _parse_rebirth,
    _parse_refill_stamina,
    _parse_sell_companions,
    _parse_statusup_item,
    _parse_story_progression_reveal,
    _parse_summon_skill_unlock,
    _profile_clear_matches,
    _project_companion_delta,
    _started_hunting_identity,
    _valid_companion_equipment,
    _valid_generic_character_record,
)
from liminal_gate.bootstrap_wire import (
    _drop_trailing_last_update,
    _endpoint_refusal_envelope,
    _json_fields_match,
    _render,
    _signed_json,
    _valid_last_update,
)
from liminal_gate.coin_creeps_banner import ALIASES as COIN_CREEPS_BANNER_ALIASES, hashed_resource_name
from liminal_gate.resource_catalog import ResourceCatalog, ResourceCatalogError, load_resource_catalog
from liminal_gate.stamina_meter import (
    FULL_METER_ORIGIN,
    chapter_for_progress,
    current_stamina,
    max_stamina_for_chapter,
    spend_stamina,
)
from liminal_gate.companion_catalog import CompanionCatalog, CompanionCatalogError, build_bundled_companion_policy, load_companion_catalog
from liminal_gate.companion_equipment_catalog import (
    CompanionEquipmentCatalog,
    CompanionEquipmentCatalogError,
    load_companion_equipment_catalog,
)
from liminal_gate.companion_strengthen_catalog import CompanionStrengthenCatalog, CompanionStrengthenCatalogError, build_bundled_companion_strengthen_policy, load_companion_strengthen_catalog
from liminal_gate.clear_state_catalog import ClearStateCatalog, ClearStateCatalogError, load_clear_state_catalog
from liminal_gate.companion_evolution_catalog import CompanionEvolutionCatalog, CompanionEvolutionCatalogError, build_bundled_companion_evolution_policy, load_companion_evolution_catalog
from liminal_gate.companion_draw_catalog import BundledCompanionDrawPolicy, CompanionDraw, CompanionDrawCatalog, CompanionDrawCatalogError, build_bundled_companion_draw_policy, load_companion_draw_catalog
from liminal_gate.pact_draw_catalog import BundledPactPolicy, PactDrawCatalog, PactDrawCatalogError, build_bundled_pact_policy, load_character_rarity, load_pact_draw_catalog, validate_bundled_pools
from liminal_gate.achievement_catalog import AchievementCatalog, AchievementCatalogError, build_bundled_achievement_policy, load_achievement_catalog
from liminal_gate.message_catalog import (
    MessageCatalog,
    MessageCatalogError,
    build_bundled_chapter_message_policy,
    eligible_chapter_messages,
    login_bonus_messages,
    load_message_catalog,
)
from liminal_gate.exchange_catalog import ExchangeCatalog, ExchangeCatalogError, active_week_index, build_bundled_exchange_policy, load_exchange_catalog
from liminal_gate.server_config import ServerConfig, ServerConfigError, load_server_config
from liminal_gate.rebirth_catalog import RebirthCatalog, RebirthCatalogError, build_bundled_rebirth_policy, load_rebirth_catalog
from liminal_gate.job_catalog import JobCatalog, JobCatalogError, build_bundled_job_policy, load_job_catalog
from liminal_gate.settlement_catalog import SettlementCatalog, SettlementCatalogError, load_settlement_catalog
from liminal_gate.statusup_catalog import StatusupCatalog, StatusupCatalogError, build_bundled_statusup_policy, load_statusup_catalog
from liminal_gate.story_catalog import StoryCatalog, StoryCatalogError, StoryStage, load_story_catalog
from liminal_gate.story_progression_catalog import StoryProgressionCatalog, StoryProgressionCatalogError, build_core_story_policy, load_story_progression_catalog
from liminal_gate.story_outcome_catalog import StoryOutcomeCatalog, StoryOutcomeCatalogError, allowed as outcome_allowed, load_story_outcome_catalog
from liminal_gate.drop_eligibility import login_chr_buddy_data
from liminal_gate.event_catalog import (
    EventCatalog,
    EventCatalogError,
    build_bundled_counter_descent_policy,
    load_event_catalog,
    merge_event_catalogs,
)
from liminal_gate.event_log import EventRecorder, refused_write_shapes, safe_form_diagnostics
from liminal_gate.event_flag_data import daily_bonus_event_flags, music_event_flags
from liminal_gate.hunting_catalog import BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK, HuntingCatalog, HuntingCatalogError, build_bundled_hunting_policy, hunting_settlement_within_bounds, load_hunting_catalog
from liminal_gate.daily_quest_data import (
    build_bundled_daily_quest_stages,
    daily_quest_event_flags,
    daily_quest_rotation,
)
from liminal_gate.cavern_forest_data import (
    build_bundled_cryptid_forest_stages,
    build_bundled_orbling_cavern_stages,
    cavern_forest_event_flags,
)
from liminal_gate.secondary_world_data import (
    build_bundled_breasoul_stages,
    build_bundled_five_emperors_stages,
    secondary_world_event_flags,
)
from liminal_gate.luck_runtime import (
    EMPTY_SLOT,
    apply_luck_up_table,
    chest_characters,
    chest_coins,
    chest_companions,
    chest_items,
    party_team_luck,
    roll_luck_result,
    roll_luck_up_table,
)
from liminal_gate.luck_pool_interpolation import build_luck_pools
from liminal_gate.luck_pool_catalog import LuckPoolCatalog, LuckPoolCatalogError, load_luck_pool_catalog
from liminal_gate.save_validation import HELP_ITEM_IDS
from liminal_gate.server_constants import LOCAL_LOGIN_COUNTRY_FIELDS, build_server_constants
from liminal_gate.summon_skill_catalog import SummonSkillCatalog, SummonSkillCatalogError, build_bundled_summon_skill_policy, load_summon_skill_catalog
from liminal_gate.world_map_special import (
    WORLD_MAP_SPECIAL_CHAPTER,
    WORLD_MAP_SPECIAL_EXP_CEILING,
    WorldMapSpecialCatalog,
    WorldMapSpecialStage,
    build_bundled_world_map_special_policy,
    initial_route_progress,
    world_map_special_companions_within_bounds,
)


# Recent-history windows for the durable save.  Both caches only ever answer an
# immediate retry or the client's current token, so these are far larger than
# any observed live burst while still keeping the state file a bounded size.
RETAINED_REQUESTS_PER_ACCOUNT = 512
RETAINED_TOKENS_PER_ACCOUNT = 512
# Every per-account replay-cache bucket. `_bound_locked` trims exactly these,
# so a mutation family that caches its responses under a new name must be
# added here or its bucket grows without bound.
REPLAY_CACHE_FIELDS = (
    "tutorial_requests",
    "achievement_requests",
    "message_requests",
    "exchange_requests",
)
# The largest observed mutation is a complete local userdata projection. Keep
# generous headroom for a full roster while refusing an unbounded read from a
# LAN peer: the guided server must listen beyond loopback for a physical device.
MAX_REQUEST_BODY_BYTES = 4 * 1024 * 1024
# Operator save transfer, served only by a loopback-bound server. The packaged
# Android build keeps its save where no workstation command can reach it, so
# this route is the export/import path `liminal_gate.on_device_state` drives.
# It is deliberately outside the profile's route table: the client never calls
# it, and it must not be reachable through the mutation transport.
LOCAL_STATE_ROUTE = "/local/state"
# Committed states kept beside the save, newest first, so a bad write, a manual
# edit, or a damaged file is recoverable instead of terminal.
ACCOUNT_STATE_BACKUP_COUNT = 5
PACT_BANNER_FILES = {
    "/public_data/banners/sl_truth_01_en.png": "sl_truth_01_en.png",
    "/public_data/banners/slb_truth_01_en.png": "slb_truth_01_en.png",
    "/public_data/banners/sl_friend_01_en.png": "sl_friend_01_en.png",
    "/public_data/banners/slb_friend_01_en.png": "slb_friend_01_en.png",
    "/public_data/banners/sl_luck_01_en.png": "sl_truth_01_en.png",
}
COIN_CREEPS_BANNER_FILES = {
    path: hashed_resource_name(alias)
    for alias in COIN_CREEPS_BANNER_ALIASES
    for path in (
        f"/resources/Banner/{alias}.bin",
        f"/resources/Banner/{hashed_resource_name(alias)}",
        f"/Banner/{alias}.bin",
        f"/Banner/{hashed_resource_name(alias)}",
    )
}
# Final-client `UIBarSlot.NormalSlotItemId`. Unlike campaign/event selectors,
# this permanent payment identity is embedded in the surviving client.
FELLOWSHIP_TICKET_ITEM_ID = 81


# These mutation kinds have already called their state operation during initial
# route dispatch. The remaining kinds still need profile/catalog arbitration.
RESOLVED_MUTATION_KINDS = frozenset({
    "continue",
    "change_uname",
    "refill_stamina",
    "unlock_metal_zone",
    "achievement",
    "read_messages",
    "delete_messages",
    "exchange",
    "exchange_count",
    "statusup_item",
    "add_job",
    "rebirth",
    "summon_skill_unlock",
    "sell_buddy",
    "sell_buddies",
    "buddy_strengthen",
    "buddy_evolve",
    "do_buddy_slot",
    "companion_userdata",
    "character_userdata",
    "party_userdata",
    "ordinary_pact",
    "event_start",
})

#: The refusal code each retired paid or advertised route answers with, on the
#: `cmdError` field `_endpoint_refusal_envelope` hoists it onto.
#:
#: `buy_energy` gets `BuyEnergyErrorCode.FailedToVerifyReceipt` (3), which is
#: literally true here: the client hands over a store receipt, and no local
#: server holds the Google Play or App Store key that would verify one. The
#: adjacent `FailedToConnectVerifyServer` (2) would claim a verifier exists and
#: was merely unreachable, which invites the retry this change is removing.
#:
#: The two ad routes get 1. Unlike every other endpoint the client declares no
#: error enum for them -- the retired service had no reason to refuse a video it
#: had just served -- so there is no recovered constant to cite. 1 is the first
#: error slot in all fifteen enums this client does declare (`None` is always 0),
#: and the value matters less than the shape: a signed body carrying any nonzero
#: `cmdError` reaches the callback that asked, which the unsigned 501 never did.
REFUSAL_ROUTE_CODES = {
    "buy_energy": 3,
    "showed_ad_movie_main": 1,
    "showed_ad_movie_continue": 1,
}

MUTATION_RESULT_STATUSES = {
    "unknown_account": HTTPStatus.UNAUTHORIZED,
    "request_collision": HTTPStatus.CONFLICT,
    "tutorial_state_conflict": HTTPStatus.CONFLICT,
    "event_clear_phase_conflict": HTTPStatus.CONFLICT,
    "event_clear_active_stage_conflict": HTTPStatus.CONFLICT,
    "event_clear_progress_conflict": HTTPStatus.CONFLICT,
    "event_clear_world_map_conflict": HTTPStatus.CONFLICT,
    "event_clear_wallet_conflict": HTTPStatus.CONFLICT,
    "event_clear_battle_coins_conflict": HTTPStatus.CONFLICT,
    "unsupported_summon": HTTPStatus.NOT_IMPLEMENTED,
    "unsupported_userdata_write": HTTPStatus.NOT_IMPLEMENTED,
    "unsupported_story_progression_reveal": HTTPStatus.NOT_IMPLEMENTED,
    "unsupported_start_quest": HTTPStatus.NOT_IMPLEMENTED,
    "unsupported_hunting_start": HTTPStatus.NOT_IMPLEMENTED,
    "unsupported_hunting_clear": HTTPStatus.NOT_IMPLEMENTED,
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
    "event_stage_locked": HTTPStatus.CONFLICT,
    "invalid_local_event_result": HTTPStatus.CONFLICT,
    "hunting_stage_locked": HTTPStatus.CONFLICT,
    "invalid_local_hunting_result": HTTPStatus.CONFLICT,
    "world_map_special_locked": HTTPStatus.CONFLICT,
    "invalid_local_world_map_special_result": HTTPStatus.CONFLICT,
    "invalid_local_settlement": HTTPStatus.CONFLICT,
    "invalid_local_clear_state": HTTPStatus.CONFLICT,
    "invalid_local_outcome": HTTPStatus.CONFLICT,
}


def _select_tutorial_response(
    transition: dict[str, Any],
) -> tuple[dict[str, Any], int | None, int | None]:
    """Select once; the caller commits the chosen response into replay state.

    The starter and the recruit that completes its Circle of Carnage are chosen
    together and committed together: the recruit is not granted until a later
    chapter, but deriving it then from a durable starter would put the pairing
    in two places instead of the one outcome that declares it.
    """
    if "response" in transition:
        return copy.deepcopy(transition["response"]), None, None
    outcomes = transition["outcomes"]
    threshold = random.SystemRandom().randrange(
        sum(outcome["weight"] for outcome in outcomes)
    )
    for outcome in outcomes:
        if threshold < outcome["weight"]:
            return (
                copy.deepcopy(outcome["response"]),
                outcome["starter_character_id"],
                outcome["recruit_character_id"],
            )
        threshold -= outcome["weight"]
    raise AssertionError("validated tutorial outcome weights must select a response")


def _replay_key(request_id: str, body: bytes, operation: str = "") -> str:
    """Identify one mutation by its request id *and* its body.

    A retry replays `requestID` and body byte for byte, so it lands on the same
    key and replays.  Two unrelated requests that happen to share a `requestID`
    land on different keys and each proceed, which is what they are.

    Message reads and deletes share one cache and can be issued with the same
    body, so they name their operation to stay distinct from each other.
    """
    prefix = f"{operation}." if operation else ""
    return f"{prefix}{request_id}.{hashlib.sha256(body).hexdigest()}"


def _migrate_replay_keys(account: dict[str, Any]) -> None:
    """Re-key a save written before the replay cache was scoped by body.

    Each old entry already records the body it settled, so this is an exact
    move rather than a guess.  Without it a retry that spans the upgrade would
    miss its entry and be applied a second time.
    """
    for name in ("tutorial_requests", "achievement_requests", "message_requests", "exchange_requests"):
        cache = account.get(name)
        if not isinstance(cache, dict):
            continue
        for key, entry in list(cache.items()):
            digest = entry.get("body_sha256") if isinstance(entry, dict) else None
            if not isinstance(digest, str) or key.endswith(f".{digest}"):
                continue
            operation = entry.get("operation")
            prefix = f"{operation}." if isinstance(operation, str) and operation else ""
            del cache[key]
            cache[f"{prefix}{key}.{digest}"] = entry


def _migrate_granted_character_rows(account: dict[str, Any]) -> None:
    """Repair roster rows a grant wrote in the result-screen shape.

    Message, event, Hunting, and battle-recruit grants used to persist the
    shape their response carries -- `isNew` and `levelAdded`, a one-element
    `jobLevels`, an empty `jobSlots` -- rather than the generic record the save
    otherwise holds.  Every settlement check reads the durable roster through
    `_valid_generic_character_record`, so one such row refused every clear the
    account attempted afterwards, and nothing repaired it on its own: the merge
    that would have is only reached by a clear that was accepted first.

    Only a row carrying *both* response-only keys is rewritten, which is the
    exact signature a grant left and one the client's own free-roam roster
    write never has: that write carries `isNew` alone, so it is left as the
    client sent it.  A roster damaged some other way still fails visibly rather
    than being quietly reshaped into something that loads.  What the row
    accumulated in the meantime -- a duplicate draw's packed level and Skill
    Boost, a Luck gain -- is carried across rather than reset.
    """
    userdata = account.get("userdata")
    rows = userdata.get("chrdata") if isinstance(userdata, dict) else None
    if not isinstance(rows, list):
        return
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or not {"isNew", "levelAdded"} <= set(row):
            continue
        if type(row.get("id")) is not int or _valid_generic_character_record(row):
            continue
        levels = row.get("jobLevels")
        packed = levels[0] if isinstance(levels, list) and levels and type(levels[0]) in {int, float} else 1
        repaired = _granted_character_row(row["id"])
        repaired["jobLevels"] = [float(packed), 0.0, 0.0]
        for name in ("jobID", "skillBoost", "luck"):
            if type(row.get(name)) is int:
                repaired[name] = row[name]
        rows[index] = repaired


def _migrate_companion_record(account: dict[str, Any]) -> None:
    """Re-project a Companion book that an inbox present left behind.

    `buddyInfo.record` is derived from `buddyInfo.list` -- one entry per
    distinct Companion, the best copy held -- and every grant path rebuilds
    both together except the inbox present, which appended to `list` alone. A
    Companion that arrived that way was owned and persisted but absent from the
    book, and stayed absent across restarts, until some unrelated mutation
    rebuilt the box and it appeared alongside whatever had just been added.

    The owned list is the truth here, so the book is rebuilt from it. Nothing
    is granted or taken: a save repaired this way holds exactly the Companions
    it already held.
    """
    userdata = account.get("userdata")
    if not isinstance(userdata, dict):
        return
    info = userdata.get("buddyInfo")
    if not isinstance(info, dict) or not isinstance(info.get("list"), list):
        return
    if any(
        not isinstance(row, dict) or type(row.get("bid")) is not int
        or type(row.get("iid")) is not int or type(row.get("lv")) is not int
        for row in info["list"]
    ):
        return
    rebuilt = _companion_info(info["list"])
    if info.get("record") != rebuilt["record"]:
        userdata["buddyInfo"] = rebuilt


def _migrate_wallet_projection(account: dict[str, Any]) -> None:
    """Re-project a nested wallet that a mutation left behind.

    The flat fields are what this server spends and grants, so they are the
    truth here and the projection is rebuilt from them.  A save written before
    the projection became an invariant can disagree -- a ten-draw paid with
    Energy debited `freeEnergy` and left `valuables.freeEnergy` at its old
    value, which `account_state validate` reports as an error -- and the
    disagreement is only ever the projection being stale, never the player
    having been charged twice.
    """
    userdata = account.get("userdata")
    if isinstance(userdata, dict):
        _synchronize_wallet_projection(userdata)


def _lock_exclusive(stream: Any) -> None:
    """Take a non-blocking exclusive advisory lock the OS drops on exit.

    Both mechanisms are released automatically when the process ends, so a
    crashed server never leaves a lock a tester has to clear by hand.
    """
    if fcntl is not None:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    elif msvcrt is not None:  # pragma: no cover - exercised on Windows only
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)


def _fsync_directory(directory: Path) -> None:
    """Flush a rename or a fresh link, where the platform allows it at all.

    Writing a file durably is two steps: fsync the contents, then fsync the
    directory the rename published them through.  Windows has no handle for the
    second step -- opening a directory there fails with `Permission denied` --
    and neither does every network filesystem, so a refusal means this platform
    does not offer the guarantee, not that the caller did anything wrong.  The
    data is already fsynced either way; only the ordering promise is lost.
    """
    try:
        handle = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(handle)
    except OSError:
        pass
    finally:
        os.close(handle)


def _parse_state_document(document: object) -> tuple[
    dict[str, dict[str, Any]], dict[str, str], str | None, dict[str, str], dict[str, str],
]:
    """Validate and normalize one state document without binding it to a server.

    Loading the save and accepting an imported one must agree exactly about what
    a valid document is: an import that skipped a check here would write a file
    the next start refuses, stranding the save inside app-private storage where
    the retained backups cannot be reached.  Both paths therefore share this one
    function rather than restating the rules.  The account dictionaries are
    normalized in place, so callers pass a document they own.
    """
    if not isinstance(document, dict) or not isinstance(document.get("accounts"), dict) or not isinstance(document.get("tokens"), dict):
        raise ProfileError("local bootstrap state is invalid")
    accounts = document["accounts"]
    tokens = document["tokens"]
    active_account_id = document.get("active_account_id")
    if not all(isinstance(token, str) and isinstance(value, dict) and isinstance(value.get("userdata"), dict) for token, value in accounts.items()):
        raise ProfileError("local bootstrap state contains invalid account data")
    if not all(isinstance(token, str) and isinstance(account_id, str) and account_id in accounts for token, account_id in tokens.items()):
        raise ProfileError("local bootstrap state contains invalid token bindings")
    if active_account_id is not None and (not isinstance(active_account_id, str) or active_account_id not in accounts):
        raise ProfileError("local bootstrap state contains an invalid active account")
    for account in accounts.values():
        _migrate_replay_keys(account)
        _migrate_granted_character_rows(account)
        _migrate_wallet_projection(account)
        _migrate_companion_record(account)
    # Absent in saves written before per-client routing; an empty map simply
    # falls back to the active account, which is the earlier behaviour.
    client_hosts = document.get("client_hosts", {})
    if not isinstance(client_hosts, dict) or not all(
        isinstance(host, str) and isinstance(account_id, str) and account_id in accounts
        for host, account_id in client_hosts.items()
    ):
        raise ProfileError("local bootstrap state contains invalid client host bindings")
    # Absent in saves written before device linking; an empty map means no
    # UUID resolves to anything but itself, which is the earlier behaviour.
    # A device UUID may name an account or an alias, never both, or signup
    # and login would disagree about which save the device plays.
    account_aliases = document.get("account_aliases", {})
    if not isinstance(account_aliases, dict) or not all(
        isinstance(device, str) and device and device not in accounts
        and isinstance(account_id, str) and account_id in accounts
        for device, account_id in account_aliases.items()
    ):
        raise ProfileError("local bootstrap state contains invalid linked-device aliases")
    for account in accounts.values():
        account.setdefault("tutorial_phase", "initial")
        account.setdefault("tutorial_requests", {})
        account.setdefault("initial_userdata_served", False)
        account.setdefault("active_generic_story", None)
        account.setdefault("active_hunt", None)
        account.setdefault("active_hunt_ticket_spent", None)
        account.setdefault("active_world_map_special", None)
        account.setdefault("claimed_achievements", [])
        account.setdefault("achievement_requests", {})
        account.setdefault("messages", {})
        account.setdefault("chapter_milestones_issued", [])
        account.setdefault("login_bonus_last_utc_day", None)
        account.setdefault("login_bonus_consecutive_days", 0)
        account.setdefault("login_bonus_total_days", 0)
        account.setdefault("message_requests", {})
        if (
            not isinstance(account["tutorial_phase"], str)
            or not isinstance(account["tutorial_requests"], dict)
            or type(account["initial_userdata_served"]) is not bool
            or (
                "tutorial_starter_character_id" in account
                and (
                    type(account["tutorial_starter_character_id"]) is not int
                    or account["tutorial_starter_character_id"] <= 0
                )
            )
            or (
                "tutorial_recruit_character_id" in account
                and (
                    type(account["tutorial_recruit_character_id"]) is not int
                    or account["tutorial_recruit_character_id"] <= 0
                )
            )
            or account["active_generic_story"] is not None and not isinstance(account["active_generic_story"], dict)
            or account["active_hunt"] is not None and not isinstance(account["active_hunt"], dict)
            or account["active_hunt_ticket_spent"] is not None and type(account["active_hunt_ticket_spent"]) is not bool
            or account["active_world_map_special"] is not None and not isinstance(account["active_world_map_special"], dict)
            or not isinstance(account["claimed_achievements"], list)
            or any(type(value) is not int or value < 1 for value in account["claimed_achievements"])
            or account["claimed_achievements"] != sorted(set(account["claimed_achievements"]))
            or not isinstance(account["achievement_requests"], dict)
            or not isinstance(account["messages"], dict)
            or not isinstance(account["chapter_milestones_issued"], list)
            or any(not isinstance(value, str) or not value for value in account["chapter_milestones_issued"])
            or account["chapter_milestones_issued"] != sorted(set(account["chapter_milestones_issued"]))
            or account["login_bonus_last_utc_day"] is not None
            and (type(account["login_bonus_last_utc_day"]) is not int or account["login_bonus_last_utc_day"] < 0)
            or type(account["login_bonus_consecutive_days"]) is not int
            or account["login_bonus_consecutive_days"] < 0
            or type(account["login_bonus_total_days"]) is not int
            or account["login_bonus_total_days"] < 0
            or account["login_bonus_consecutive_days"] > account["login_bonus_total_days"]
            or account["login_bonus_last_utc_day"] is None
            and (account["login_bonus_consecutive_days"] != 0 or account["login_bonus_total_days"] != 0)
            or account["login_bonus_last_utc_day"] is not None
            and (account["login_bonus_consecutive_days"] < 1 or account["login_bonus_total_days"] < 1)
            or not isinstance(account["message_requests"], dict)
        ):
            raise ProfileError("local bootstrap state contains invalid tutorial state")
    return accounts, tokens, active_account_id, client_hosts, account_aliases


class BootstrapState:
    """Atomic local account state for the extracted bootstrap sequence."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = Lock()
        self.tokens: dict[str, str] = {}
        # The only durable per-client discriminator available: `otk` is a pure
        # three-second time bucket, so two clients playing at once send
        # byte-identical tokens and cannot be told apart by token alone.
        self.client_hosts: dict[str, str] = {}
        # Linked devices: a second device's UUID resolves to the account its
        # owner already plays.  Written only by the operator's `link` command,
        # never by the wire protocol, which has no account-transfer route.
        self.account_aliases: dict[str, str] = {}
        self.active_account_id: str | None = None
        self._lock_stream: Any = None
        self._acquire_file_lock()
        try:
            self.accounts = self._load()
        except ProfileError as error:
            # A save that will not load is the one moment the retained history
            # matters, so name it here rather than leaving a tester to discover
            # the files themselves.
            backups = self.available_backups()
            self.close()
            if not backups:
                raise
            raise ProfileError(
                f"{error}. {len(backups)} retained state(s) sit beside it, newest first: "
                f"{', '.join(item.name for item in backups)}. Stop the server, copy one "
                "over the save, and start again."
            ) from error
        except BaseException:
            self.close()
            raise

    def _acquire_file_lock(self) -> None:
        """Refuse to share one save with another server.

        Each server holds the whole state in memory and republishes all of it on
        every mutation, so two of them on one file do not interleave — the
        second simply overwrites the first's progress with its own stale copy,
        silently and with no error on either side.  This is reachable today: the
        README documents changing `--port`, while `--data-dir` (and so the state
        file) keeps its default, so a forgotten server and a new one share a save.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self.path.with_name(f".{self.path.name}.lock")
        stream = lock_path.open("a+b")
        try:
            _lock_exclusive(stream)
        except OSError as error:
            stream.close()
            raise ProfileError(
                f"local account state is already in use by another server: {self.path}. "
                "Stop the other server, or start this one with its own --data-dir."
            ) from error
        self._lock_stream = stream

    def close(self) -> None:
        """Release the save so another server may take it."""
        if self._lock_stream is not None:
            self._lock_stream.close()
            self._lock_stream = None

    def _claim_host_locked(self, client_host: str | None, account_id: str) -> bool:
        """Record which client an identified account belongs to.

        Only signup and login carry `uuid`, so these are the two moments the
        server ever learns an account's owner for certain.  A later setup
        attempt from the same client simply reclaims the host, which keeps the
        existing behaviour of routing to the newest save rather than an
        abandoned one.
        """
        if not isinstance(client_host, str) or not client_host:
            return False
        if self.client_hosts.get(client_host) == account_id:
            return False
        self.client_hosts[client_host] = account_id
        return True

    def _resolve_alias_locked(self, account_id: str) -> str:
        """The account a linked device's UUID plays; unlinked UUIDs are themselves."""
        return self.account_aliases.get(account_id, account_id)

    def create_account(self, token: str, account_id: str, seed: dict[str, Any], message_catalog: MessageCatalog | None = None, exchange_catalog: ExchangeCatalog | None = None, client_host: str | None = None) -> None:
        with self.lock:
            # A linked device that clears its app data signs up again with its
            # linked UUID.  The shared save must win over creating a fresh
            # empty account for it.
            account_id = self._resolve_alias_locked(account_id)
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
                    "chapter_milestones_issued": [],
                    "login_bonus_last_utc_day": None,
                    "login_bonus_consecutive_days": 0,
                    "login_bonus_total_days": 0,
                    "message_requests": {},
                    "exchange_remaining": _initial_exchange_remaining(exchange_catalog),
                    "exchange_total": 0,
                    "exchange_requests": {},
                }
            changed = self.tokens.get(token) != account_id or self.active_account_id != account_id
            changed = self._claim_host_locked(client_host, account_id) or changed
            if self.tokens.get(token) != account_id:
                self.tokens[token] = account_id
            self.active_account_id = account_id
            if changed:
                self._persist_locked()

    def bind_login_token(self, token: str, account_id: str, client_host: str | None = None) -> str | None:
        """Bind a login's token, returning the account it resolved to.

        The resolved id matters to the caller: a linked device logs in with
        its own UUID, and every later lookup must use the shared account's id,
        not the UUID the wire carried.
        """
        with self.lock:
            account_id = self._resolve_alias_locked(account_id)
            if account_id not in self.accounts:
                return None
            changed = self.tokens.get(token) != account_id or self.active_account_id != account_id
            changed = self._claim_host_locked(client_host, account_id) or changed
            if self.tokens.get(token) != account_id:
                self.tokens[token] = account_id
            self.active_account_id = account_id
            if changed:
                self._persist_locked()
            return account_id

    def bind_rotated_token(self, token: str, client_host: str | None = None) -> bool:
        """Bind a client-rotated OTK to the account that client owns.

        The client replaces its OTK every three seconds, and only signup and
        login carry `uuid`, so almost every mutation arrives on a token the
        server has never seen.  Resolving those by "whichever account logged in
        most recently" is correct for one player and wrong for a household: two
        clients playing at once send byte-identical tokens, and the second to
        log in silently captures the first's mutations.

        The requesting client's own address is the discriminator that works
        without a protocol change, so an unknown token resolves to the account
        that client last identified itself as.  The active-account fallback
        stays for clients that have not identified yet, and for saves written
        before hosts were recorded.
        """
        # Every persisted token is a JSON object key.  A missing `otk` query
        # parameter would otherwise insert `None` here, which makes *every*
        # later `_persist_locked` raise while sorting mixed key types and so
        # silently stops the account saving for the rest of the process.
        if not isinstance(token, str) or not token:
            return False
        with self.lock:
            # Internal callers and migrations that have no transport address
            # may still confirm an existing durable binding. HTTP handlers
            # always pass a host and therefore take the host-ownership path.
            if client_host is None and self.tokens.get(token) in self.accounts:
                return True
            owned = self.client_hosts.get(client_host) if isinstance(client_host, str) else None
            if owned in self.accounts:
                # OTK values collide across clients because they are coarse
                # time buckets. The host that most recently identified itself
                # by signup/login therefore outranks a pre-existing token
                # binding, including one created by another household client.
                if self.tokens.get(token) != owned:
                    self.tokens[token] = owned
                    self._persist_locked()
                return True
            if self.client_hosts:
                # Once at least one client has identified itself, an unrelated
                # LAN host must not inherit the active save merely by sending an
                # arbitrary fresh token. It can establish ownership through the
                # normal signup/login route, both of which carry a UUID.
                return False
            # Compatibility migration for a legacy single-account save written
            # before host ownership was persisted. The first successful
            # rotated request claims its host; subsequent unknown hosts are
            # refused by the branch above.
            account_id = self.tokens.get(token)
            if account_id not in self.accounts:
                account_id = self.active_account_id
            if account_id in self.accounts:
                if isinstance(client_host, str) and client_host:
                    self.client_hosts[client_host] = account_id
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
            if isinstance(client_host, str) and client_host:
                self.client_hosts[client_host] = account_id
            self._persist_locked()
            return True

    def safe_account_context(self, token: str) -> dict[str, Any]:
        """Return routing diagnostics without persisting account identifiers."""
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            active = self.accounts.get(self.active_account_id)
            return {
                "resolved_account_phase": None if account is None else account.get("tutorial_phase"),
                "active_account_phase": None if active is None else active.get("tutorial_phase"),
                "resolved_account_is_active": account_id == self.active_account_id,
            }

    def progress_for_status(
        self,
        token: str,
        client_host: str | None,
    ) -> int | None:
        """Resolve progress for the pre-login status request without binding it.

        The final client fetches server status before login and rotates its OTK,
        so a direct token lookup misses resumed accounts. A known client host
        uses its existing ownership.

        A save holding exactly one account falls back to it whatever the host.
        This used to require that *no* host had ever been bound, and that made
        the whole world vanish on a router lease: the address changes, the
        pre-login status request resolves nothing, and the client builds its
        menus from empty Tower, Eidolon, Strikes Back, Metal, and Hunting lists.
        The login that follows re-binds the host, but the menus were already
        drawn, so the player sees a server that appears to support none of it.
        Guarding on the account count is what actually matters: with one account
        there is no second player to expose, and these lists say which stages
        exist, not anything about the account. Reaching the account still needs
        its UUID.
        """
        with self.lock:
            account_id = self.tokens.get(token)
            if account_id not in self.accounts and isinstance(client_host, str):
                account_id = self.client_hosts.get(client_host)
            if account_id not in self.accounts and len(self.accounts) == 1:
                account_id = (
                    self.active_account_id
                    if self.active_account_id in self.accounts
                    else next(iter(self.accounts))
                )
            account = self.accounts.get(account_id)
            progress = (
                None
                if account is None
                else account.get("userdata", {}).get("progressCode")
            )
            return progress if type(progress) is int and progress >= 0 else None

    def replays_cleared_stage(self, token: str, identity: tuple[int, int] | None, catalog: StoryProgressionCatalog | None) -> bool:
        """Whether the account has already cleared the stage it is asking for.

        A profile's scripted transitions match on the request body alone, and
        the tutorial's last scripted stage leaves the account in `free_roam` --
        the state it returns to after *every* later stage.  Replaying that one
        stage therefore re-fires the script forever.  The progression catalog
        can tell the two apart: it answers a not-yet-cleared stage with an
        advance and an already-cleared one with the account's current progress.
        """
        if catalog is None or identity is None or identity not in catalog.by_identity():
            return False
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return False
            current = account["userdata"].get("progressCode")
            if type(current) is not int:
                return False
            return catalog.expected_clear_progress(current, identity) == current

    def allows_story_progression(self, token: str) -> bool:
        """Whether a token has crossed the opening tutorial boundary."""
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            return account is not None and account.get("tutorial_phase") == "free_roam"

    def allows_ordinary_userdata_write(self, token: str) -> bool:
        """Whether an ordinary roster save can be the account's active exit.

        Give Up uses the same minimal ``chrdata`` save as an ordinary character
        screen. During an active local battle that save is the observed abandon
        signal; Cancel itself has no server request. Tutorial structural writes
        remain outside this set so their phase-bound conveyor keeps owning them.
        """
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            return account is not None and account.get("tutorial_phase") in {
                "free_roam", "generic_story_active", "hunting_active",
            }

    def userdata_for(self, token: str, *, stamina: bool = False) -> dict[str, Any] | None:
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            if account is None:
                return None
            userdata = account["userdata"]
            changed = False
            # A save written while the stamina policy was on carries a fill
            # origin the client still turns into a partial bar.  Nothing debits
            # that meter once the policy is off, so the read returns it to the
            # client's own full-meter representation rather than leaving a bar
            # that only time can finish filling.
            if not stamina and float(userdata.get("refillStartTime", 0.0)) != FULL_METER_ORIGIN:
                userdata["refillStartTime"] = FULL_METER_ORIGIN
                changed = True
            # The client reads the nested ``valuables`` object on login, while
            # local mutations update the flat wallet fields.  Rebuild the
            # nested projection on every read so a Pact/quest mutation cannot
            # reappear as an old wallet after a restart.
            changed = _synchronize_wallet_projection(userdata) or changed
            # The client reads ChrData.jobLevels with LitJson's double accessor.
            # Locally persisted values can otherwise be integers after a manual
            # test seed or a permissive local write, which makes the client fail
            # while parsing an otherwise successful userdata response.
            rows = userdata.get("chrdata")
            if isinstance(rows, list):
                for row in rows:
                    levels = row.get("jobLevels") if isinstance(row, dict) else None
                    if isinstance(levels, list):
                        for index, value in enumerate(levels):
                            if type(value) is int:
                                levels[index] = float(value)
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
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                return ("replay", copy.deepcopy(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None)
            name = _parse_change_uname(body)
            if name is None:
                return "unsupported_change_uname", None
            now = time.time()
            if account.get("username_changed_at", 0.0) and now - float(account["username_changed_at"]) < 30 * 86400:
                payload = {"errorCode": 1}
                requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": payload}
                self._persist_locked()
                return "success", payload
            account["username"] = name
            account["username_changed_at"] = now
            payload = {"success": True, "name": name, "changeUsernameDate": float(621355968000000000 + int(now * 10_000_000))}
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def refill_stamina(
        self, token: str, request_id: str, body: bytes, *, stamina: bool = False,
    ) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                return (
                    ("replay", _ordered_refill_payload(cached["payload"]))
                    if cached.get("body_sha256") == digest
                    else ("request_collision", None)
                )
            if _parse_refill_stamina(body) != 1:
                return "unsupported_refill_stamina", None
            data = account["userdata"]
            # `RefillStaminaErrorCode.NoNeedToRefill`.  Comparing the derived
            # meter rather than the raw origin matters once entry actually
            # debits stamina: an origin left nonzero by an earlier quest refills
            # on its own over time, and charging an Energy to "refill" a bar
            # that already reached its maximum would quietly waste it.  With the
            # policy off nothing debits the meter at all, so every refill takes
            # that same refusal rather than selling an Energy for nothing.
            chapter = chapter_for_progress(int(data.get("progressCode", 0)))
            origin = float(data.get("refillStartTime", 0.0))
            if not stamina or current_stamina(origin, chapter, time.time()) >= max_stamina_for_chapter(chapter):
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
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
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def claim_achievement(self, token: str, request_id: str, body: bytes, catalog: AchievementCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            digest = hashlib.sha256(body).hexdigest()
            requests = account.setdefault("achievement_requests", {})
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def login_messages(
        self, account_id: str, chapter_milestones: bool = False,
        login_bonuses: bool = False, now: float | None = None,
        message_catalog: MessageCatalog | None = None,
        original_mail_shape: bool = False,
    ) -> list[dict[str, Any]]:
        with self.lock:
            account = self.accounts.get(account_id)
            if account is None:
                return []
            issued_at = time.time() if now is None else now
            if chapter_milestones and message_catalog is None:
                raise ProfileError("chapter milestone settlement requires a message catalog")
            changed = chapter_milestones and _settle_chapter_milestone_rewards(
                account, issued_at,
                max_stack=message_catalog.max_stack,
            )
            if login_bonuses:
                changed = _synchronize_login_bonus_messages(account, issued_at) or changed
            if changed:
                # Commit before exposing the gift. A restart between login and
                # read must retain both the message and its eligibility state.
                self._persist_locked()
            # The final client marks each ID from `readlist` locally, but a
            # later login reconstructs its inbox from this array. Re-projecting
            # claimed entries makes its menu badge announce them as new again.
            # Keep the durable record for exact read replay and explicit delete,
            # while only exposing presents that are still claimable.
            return [
                _message_wire(message, original_mail_shape)
                for _, message in sorted(account.setdefault("messages", {}).items())
                if not message.get("read")
            ]

    def read_messages(self, token: str, request_id: str, body: bytes, catalog: MessageCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            digest = hashlib.sha256(body).hexdigest()
            requests = account.setdefault("message_requests", {})
            cached = requests.get(_replay_key(request_id, body, "read"))
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
            unread = [message for message in selected if message is not None and not message["read"]]
            # Character and Companion grants are resolved before anything is
            # written, because they are the two rewards that can legitimately
            # fail -- a malformed roster, a full Companion box. Settling coins
            # first and discovering that afterwards would leave a message read
            # and its headline reward never delivered.
            grants = _message_grants(data, unread, catalog)
            if grants is None:
                return "unsupported_message_read", None
            updated_items = list(items)
            coins, energy = int(data.get("coins", 0)), int(data.get("freeEnergy", 0))
            for message in unread:
                coins = min(catalog.max_coins, coins + message["coins"])
                energy = min(catalog.max_free_energy, energy + message["free_energy"])
                for item_id, amount in message["items"].items():
                    updated_items[int(item_id) - 1] = min(catalog.max_stack, updated_items[int(item_id) - 1] + amount)
                message["read"] = True
            data["coins"], data["freeEnergy"], data["itemList"] = coins, energy, updated_items
            announced = _apply_message_grants(data, grants)
            payload = _canonical_payload({**_API_ENVELOPE_FIELDS, "result": {
                "readlist": message_ids, "itemList": updated_items, "coins": coins,
                "energy": int(data.get("energy", 0)), "freeEnergy": energy,
                **_message_reload_projection(data, account, announced),
            }})
            requests[_replay_key(request_id, body, "read")] = {"operation": "read", "body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def delete_messages(self, token: str, request_id: str, body: bytes, catalog: MessageCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            digest = hashlib.sha256(body).hexdigest()
            requests = account.setdefault("message_requests", {})
            cached = requests.get(_replay_key(request_id, body, "delete"))
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
            payload = _canonical_payload({**_API_ENVELOPE_FIELDS, "deletelist": message_ids})
            requests[_replay_key(request_id, body, "delete")] = {"operation": "delete", "body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def current_exchange(self, token: str, catalog: ExchangeCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None: return "unknown_account", None
            if catalog is None: return "unsupported_exchange", None
            open_offers = _restock_exchange_week(account, catalog)
            remaining = account["exchange_remaining"]
            offers = [{"ID": offer.offer_id, "targetItemID": offer.target_item_id, "targetBuddyID": offer.target_buddy_id, "coins": offer.coins, "targetCount": offer.target_count, "count": remaining.get(str(offer.offer_id), offer.initial_count), "weeklyItemCount": offer.weekly_item_count, "items": [[item_id, count] for item_id, count in sorted(offer.ingredients.items())]} for offer in open_offers.values()]
            return "success", {"totalCount": account.setdefault("exchange_total", 0), "itemList": [{"weeklyItem": catalog.weekly_item, "endDate": catalog.end_date, "items": offers}] if offers else []}

    def exchange(self, token: str, request_id: str, body: bytes, catalog: ExchangeCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None: return "unknown_account", None
            digest=hashlib.sha256(body).hexdigest(); cache=account.setdefault("exchange_requests", {}).get(_replay_key(request_id, body))
            if cache is not None: return ("replay", _canonical_payload(cache["payload"])) if cache.get("body_sha256")==digest else ("request_collision",None)
            request=_parse_exchange(body)
            if catalog is None or request is None: return "unsupported_exchange",None
            open_offers=_restock_exchange_week(account, catalog)
            # Only this week's offers are tradable, exactly as only they render.
            offer=open_offers.get(request[0]); data=account["userdata"]
            items=data.get("itemList"); remaining=account["exchange_remaining"]
            if offer is None or not isinstance(items,list) or len(items)!=catalog.item_slots: return "invalid_local_exchange",None
            amount=request[1]; stock=remaining.get(str(offer.offer_id),offer.initial_count)
            raw_info=data.get("buddyInfo",{"list":[],"record":[]}); owned=raw_info.get("list") if isinstance(raw_info,dict) else None
            minted=offer.target_buddy_id and offer.target_count*amount
            if amount>stock: payload={"success":False,"errorCode":6}
            elif any(type(items[i-1]) is not int or items[i-1]<n*amount for i,n in offer.ingredients.items()): payload={"success":False,"errorCode":3}
            elif offer.target_buddy_id and not isinstance(owned,list): return "invalid_local_exchange",None
            # A Companion offer fills the box rather than an item slot, so each
            # target checks only the ceiling that actually applies to it.
            elif minted and len(owned)+minted>catalog.max_owned: payload={"success":False,"errorCode":4}
            elif offer.target_item_id and items[offer.target_item_id-1]+offer.target_count*amount>catalog.max_stack: payload={"success":False,"errorCode":4}
            else:
                updated=list(items)
                for item_id,count in offer.ingredients.items(): updated[item_id-1]-=count*amount
                if offer.target_item_id: updated[offer.target_item_id-1]+=offer.target_count*amount
                if minted:
                    known={row["iid"] for row in owned if isinstance(row,dict) and type(row.get("iid")) is int}
                    next_id=data.get("nextCompanionInventoryId",max(known,default=0)+1)
                    if type(next_id) is not int or next_id<=max(known,default=0): return "invalid_local_exchange",None
                    rows=copy.deepcopy(owned)
                    for _ in range(minted):
                        rows.append({"bid":offer.target_buddy_id,"lv":1,"date":0.0,"iid":next_id,"exp":0,"flag":0,"chrID":0}); next_id+=1
                    data["buddyInfo"]=_companion_info(rows); data["nextCompanionInventoryId"]=next_id
                remaining[str(offer.offer_id)]=stock-amount; account["exchange_total"]+=amount; data["itemList"]=updated
                payload={"success":True,"buddyInfo":copy.deepcopy(data.get("buddyInfo",{"list":[],"record":[]})),"itemList":updated,"coins":int(data.get("coins",0)),"totalCount":account["exchange_total"],"remainCount":remaining[str(offer.offer_id)]}
            payload = _canonical_payload(payload)
            account["exchange_requests"][_replay_key(request_id, body)]={"body_sha256":digest,"payload":copy.deepcopy(payload)}; self._persist_locked(); return "success",payload

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
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def add_job(self, token: str, request_id: str, body: bytes, catalog: JobCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def rebirth(self, token: str, request_id: str, body: bytes, catalog: RebirthCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest(); cached = requests.get(_replay_key(request_id, body))
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
                        overlapped = any(isinstance(row, dict) and row.get("id") == recipe.destination_character_id for row in rows)
                        new_rows = [copy.deepcopy(row) for row in rows if row is not source and row.get("id") != recipe.destination_character_id]
                        destination = copy.deepcopy(source); destination.update({"id": recipe.destination_character_id, "jobLevels": [1.0, 0.0, 0.0], "jobID": 0, "buddy": 0})
                        new_rows.append(destination); new_rows.sort(key=lambda row: int(row["id"]))
                        new_items = copy.deepcopy(items)
                        for item_id, count in recipe.items.items(): new_items[item_id - 1] -= count
                        used.update(material_id for material_id, _ in recipe.materials); used.update({catalog.joker_character_id} if missing and use_joker else set())
                        # The source leaves the roster, so any party slot naming
                        # it would point at a character the account no longer
                        # owns -- and every later party save would be refused
                        # for exactly that reason.  The rebirthed unit takes its
                        # own slot, unless the destination was already owned, in
                        # which case the slot empties rather than duplicating.
                        _retarget_party(data, recipe.source_character_id, 0 if overlapped else recipe.destination_character_id)
                        data["chrdata"], data["itemList"], data["coins"], account["rebirth_used_material_ids"] = new_rows, new_items, data["coins"] - recipe.coins, sorted(used)
                        payload = {"success": True, "buddyInfo": {"list": [], "record": []}, "chrdata": copy.deepcopy(new_rows), "itemList": new_items, "coins": data["coins"], "overlapped": overlapped}
            payload = _canonical_payload(payload); requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}; self._persist_locked(); return "success", payload

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
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                if cached.get("body_sha256") != body_hash:
                    return "request_collision", None
                return "replay", copy.deepcopy(cached["payload"])
            starter_character_id = _tutorial_starter_id(account)
            recruit_character_id = _tutorial_recruit_id(account)
            transitions = tuple(
                _resolve_tutorial_template(item, starter_character_id, recruit_character_id)
                for item in transitions
            )
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
            payload, selected_starter, selected_recruit = _select_tutorial_response(transition)
            if selected_starter is not None:
                account["tutorial_starter_character_id"] = selected_starter
            if selected_recruit is not None:
                account["tutorial_recruit_character_id"] = selected_recruit
            # State files sort object keys. Canonicalizing before the first
            # response keeps a retry byte-identical after a full restart,
            # including a weighted result selected only on the first request.
            payload = _canonical_payload(payload)
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
                _synchronize_wallet_projection(userdata)
            if kind == "clear" and "chrdata" in payload:
                userdata["chrdata"] = copy.deepcopy(payload["chrdata"])
            if kind == "clear" and transition["next_phase"] == "free_roam":
                # The client consumes these guarded fields from the clear
                # callback before its next userdata read.  Returning the
                # durable wallet avoids showing a zero starter balance until
                # the app is restarted.
                payload.setdefault("freeEnergy", int(userdata.get("freeEnergy", 0)))
                payload.setdefault("coins", int(userdata.get("coins", 0)))
            account["tutorial_phase"] = transition["next_phase"]
            requests[_replay_key(request_id, body)] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def summon_skill_unlock(self, token: str, request_id: str, body: bytes, catalog: SummonSkillCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def sell_companions(self, token: str, request_id: str, body: bytes, catalog: CompanionCatalog | None, *, multiple: bool) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def strengthen_companion(self, token: str, request_id: str, body: bytes, catalog: CompanionStrengthenCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def evolve_companion(self, token: str, request_id: str, body: bytes, catalog: CompanionEvolutionCatalog | None) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def draw_companions(self, token: str, request_id: str, body: bytes, catalog: CompanionDrawCatalog | BundledCompanionDrawPolicy | None) -> tuple[str, dict[str, Any] | None]:
        """Settle a Companion pull from whichever pool the wire kind names.

        Pool membership, both ticket items, and the two prices are catalog
        policy. The client picks the payment variant from what the player
        holds, so a pull that names a pool this catalog does not describe is
        refused rather than drawn from the other one.
        """
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            request = _parse_companion_draw(body)
            if catalog is None or request is None:
                return "unsupported_companion_draw", None
            kind, count = request
            draws = catalog.draws_for_kind(kind)
            cost = catalog.cost_for_kind(kind)
            ticket_item_id = catalog.ticket_item_for_kind(kind)
            if not draws or cost is None or ticket_item_id is None:
                return "unsupported_companion_draw", None
            currency, unit_cost = cost
            userdata = account["userdata"]
            items = userdata.get("itemList")
            buddy_info = userdata.get("buddyInfo", {"list": [], "record": []})
            owned = buddy_info.get("list") if isinstance(buddy_info, dict) else None
            if not isinstance(items, list) or len(items) != catalog.item_slots or type(items[ticket_item_id - 1]) is not int or items[ticket_item_id - 1] < 0 or not isinstance(owned, list) or type(userdata.get("energy", 0)) is not int or type(userdata.get("freeEnergy", 0)) is not int or type(userdata.get("coins", 0)) is not int:
                return "unsupported_companion_draw", None
            if len(owned) + count > catalog.max_owned:
                payload = {"success": False, "errorCode": 4}
            else:
                uses_ticket = items[ticket_item_id - 1] >= count
                # `SlotKind.BuddyItem` and `NormalItem` are the client's own
                # statement that it is paying with the ticket, so a batch it
                # can no longer cover is refused rather than silently charged.
                ticket_only = kind in {20, 21}
                total_currency = unit_cost * count
                affordable = (
                    userdata["coins"] >= total_currency
                    if currency == "coins"
                    else userdata["energy"] + userdata["freeEnergy"] >= total_currency
                )
                if (ticket_only and not uses_ticket) or not (uses_ticket or affordable):
                    # `DoBuddySlotErrorCode`: NotEnoughEnergy for the Rare pool,
                    # NotEnoughCoins for the Normal one. A ticket the player no
                    # longer holds is reported as the pool's own shortfall, the
                    # same compatibility policy the Pact route applies.
                    payload = {"success": False, "errorCode": 2 if currency == "coins" else 1}
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
                        selected = _draw_companion_id(draws)
                        record = {"bid": selected, "lv": 1, "date": 0.0, "iid": next_id, "exp": 0, "flag": 0, "chrID": 0}
                        drawn.append(record)
                        results.append({"bid": selected, "lv": 1})
                        next_id += 1
                    new_items = copy.deepcopy(items)
                    coins = userdata["coins"]
                    energy = userdata["energy"]
                    free_energy = userdata["freeEnergy"]
                    if uses_ticket:
                        new_items[ticket_item_id - 1] -= count
                    elif currency == "coins":
                        coins -= total_currency
                    else:
                        free_spend = min(free_energy, total_currency)
                        free_energy -= free_spend
                        energy -= total_currency - free_spend
                    candidates.extend(drawn)
                    userdata["buddyInfo"] = _companion_info(candidates)
                    userdata["itemList"] = new_items
                    userdata["coins"] = coins
                    userdata["energy"] = energy
                    userdata["freeEnergy"] = free_energy
                    userdata["nextCompanionInventoryId"] = next_id
                    payload = {"success": True, "coins": coins, "energy": energy, "freeEnergy": free_energy, "itemList": new_items, "buddyInfo": copy.deepcopy(userdata["buddyInfo"]), "result": results}
            payload = _canonical_payload(payload)
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
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
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            parsed = _parse_ordinary_pact_draw(body)
            if catalog is None or parsed is None:
                return "unsupported_ordinary_pact", None
            kind, count, luck_type = parsed
            if luck_type and not isinstance(catalog, BundledPactPolicy):
                # User-supplied schema version 1 catalogs define only ordinary
                # Skill Boost duplicates. They cannot silently acquire an
                # invented Fate/Luck policy.
                return "unsupported_ordinary_pact", None
            ticket_draw = kind == 20
            # NormalItem is a payment variant of the Fellowship-side pool, not
            # a third pool. The exact recovered client form permits one result.
            draw_kind = 0 if ticket_draw else kind
            userdata = account["userdata"]
            # Fellowship membership is cumulative in the account's own story
            # progress, the same `_chapterNo` low bits this server already
            # gates achievements and stage entry on. The ticket variant pays
            # differently but draws the same gated pool.
            draws = catalog.draws_for_kind(draw_kind, chapter_for_progress(int(userdata.get("progressCode", 0))))
            cost = ("ticket", 1) if ticket_draw else catalog.cost_for_kind(kind)
            if not draws or cost is None:
                return "unsupported_ordinary_pact", None
            currency, unit_cost = cost
            rows = userdata.get("chrdata")
            if not isinstance(rows, list) or type(userdata.get("coins")) is not int or type(userdata.get("energy", 0)) is not int or type(userdata.get("freeEnergy", 0)) is not int:
                return "unsupported_ordinary_pact", None
            items = userdata.get("itemList")
            ticket_index = FELLOWSHIP_TICKET_ITEM_ID - 1
            valid_ticket_inventory = (
                isinstance(items, list)
                and len(items) > ticket_index
                and all(type(value) is int and value >= 0 for value in items)
            )
            ticket_count = items[ticket_index] if valid_ticket_inventory else 0
            if ticket_draw and not valid_ticket_inventory:
                return "unsupported_ordinary_pact", None
            total_cost = unit_cost * count
            # The final client exposes NormalItem as a distinct one-ticket
            # operation. No mixed ticket/coin batch has been recovered, so a
            # Fellowship-side coin request must spend the visible ticket first.
            if currency == "ticket" and ticket_count < total_cost:
                payload = {"success": False, "errorCode": 2}
            elif currency == "coins" and ticket_count:
                payload = {"success": False, "errorCode": 2}
            elif currency == "coins" and userdata["coins"] < total_cost:
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
                    eligibility_field = "luck" if luck_type else "skillBoost"
                    eligibility_cap = catalog.max_luck if luck_type else catalog.max_skill_boost
                    if any(
                        type(row.get(eligibility_field, 0)) is not int
                        for row in by_id.values()
                    ):
                        return "unsupported_ordinary_pact", None
                    eligible = [
                        draw
                        for draw in draws
                        if not isinstance(by_id.get(draw.character_id), dict)
                        or by_id[draw.character_id].get(eligibility_field, 0)
                        < eligibility_cap
                    ]
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
                        current = {
                            "id": selected.character_id,
                            "buddy": 0,
                            "date": 0.0,
                            "jobSlots": [0.0, 0.0, 0.0],
                            "jobLevels": [float(catalog.new_level), 0.0, 0.0],
                            "jobID": 0,
                            "flags": 0,
                            "skillBoost": 0,
                        }
                        if luck_type:
                            current["luck"] = 0
                        candidates.append(current); by_id[selected.character_id] = current
                        result = {
                            "id": selected.character_id,
                            "jobID": 0,
                            "jobLevels": [catalog.new_level],
                            "jobSlots": [],
                            "isNew": True,
                            "levelAdded": catalog.new_level,
                            "skillBoost": 0,
                        }
                        if luck_type:
                            result["luck"] = 0
                        results.append(result)
                    elif (
                        not isinstance(current.get("jobLevels"), list)
                        or not current["jobLevels"]
                        or type(current["jobLevels"][0]) not in {int, float}
                        or not math.isfinite(current["jobLevels"][0])
                        or current["jobLevels"][0] < 0
                        or int(current["jobLevels"][0]) != current["jobLevels"][0]
                        or type(current.get("skillBoost", 0)) is not int
                        or type(current.get("jobID", 0)) is not int
                        or not isinstance(current.get("jobSlots", []), list)
                        or (
                            luck_type
                            and type(current.get("luck", 0)) is not int
                        )
                    ):
                        return "unsupported_ordinary_pact", None
                    else:
                        packed_level = int(current["jobLevels"][0])
                        old_level = packed_level & 0xFFF
                        old_boost = current.get("skillBoost", 0)
                        level = min(catalog.max_level, old_level + selected.duplicate_level_added)
                        encoded_level = (packed_level & ~0xFFF) | level
                        current["jobLevels"][0] = (
                            float(encoded_level)
                            if type(current["jobLevels"][0]) is float
                            else encoded_level
                        )
                        result = {
                            "id": selected.character_id,
                            "jobID": int(current.get("jobID", 0)),
                            "jobLevels": [level],
                            "jobSlots": [],
                            "isNew": False,
                            "levelAdded": level - old_level,
                            "skillBoost": old_boost,
                        }
                        if luck_type:
                            old_luck = current.get("luck", 0)
                            luck = min(
                                catalog.max_luck,
                                old_luck + catalog.fate_duplicate_luck,
                            )
                            current["luck"] = luck
                            result |= {
                                "luck": luck,
                                "luckup": luck - old_luck,
                            }
                        else:
                            boost = min(
                                catalog.max_skill_boost,
                                old_boost + selected.duplicate_skill_boost,
                            )
                            current["skillBoost"] = boost
                            result |= {
                                "boostUp": boost - old_boost,
                                "skillBoost": boost,
                            }
                        results.append(result)
                else:
                    if currency == "coins":
                        userdata["coins"] -= total_cost
                    elif currency == "energy":
                        free_spend = min(userdata["freeEnergy"], total_cost)
                        userdata["freeEnergy"] -= free_spend
                        userdata["energy"] -= total_cost - free_spend
                    else:
                        assert isinstance(items, list)
                        new_items = copy.deepcopy(items)
                        new_items[ticket_index] -= total_cost
                        userdata["itemList"] = new_items
                    userdata["chrdata"] = candidates
                    payload = {"success": True, "coins": userdata["coins"], "energy": userdata["energy"], "freeEnergy": userdata["freeEnergy"], "chrdata": results}
                    if currency == "ticket":
                        payload["itemList"] = copy.deepcopy(userdata["itemList"])
            payload = _canonical_payload(payload)
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def update_companion_userdata(self, token: str, request_id: str, body: bytes, submitted: list[dict[str, Any]]) -> tuple[str, dict[str, Any] | None]:
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                return (("replay", _canonical_payload(cached["payload"])) if cached.get("body_sha256") == digest else ("request_collision", None))
            if not _apply_companion_delta(account["userdata"], submitted):
                return "unsupported_companion_userdata", None
            payload = {"success": True, "lastupdate": 1.0}
            payload = _canonical_payload(payload)
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def update_character_userdata(
        self, token: str, request_id: str, body: bytes, characters: list[dict[str, Any]] | None,
        party: dict[str, Any] | None = None, companions: list[dict[str, Any]] | None = None,
        companion_equipment_catalog: CompanionEquipmentCatalog | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Persist a client-authored free-roam roster or party layout locally."""
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            phase = account.get("tutorial_phase")
            abandoning_active_story = (
                phase in {"generic_story_active", "hunting_active", "world_map_special_active"}
                and (characters is not None or party is not None)
            )
            if phase != "free_roam" and not abandoning_active_story:
                return "tutorial_state_conflict", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                return (
                    ("replay", _canonical_payload(cached["payload"]))
                    if cached.get("body_sha256") == digest
                    else ("request_collision", None)
                )
            userdata = account["userdata"]
            current_rows = userdata.get("chrdata", [])
            if not isinstance(current_rows, list):
                return "unsupported_userdata_write", None
            candidate_rows = copy.deepcopy(current_rows)
            candidate_indices: dict[int, int] = {}
            for index, row in enumerate(candidate_rows):
                character_id = row.get("id") if isinstance(row, dict) else None
                if type(character_id) is not int or character_id <= 0 or character_id in candidate_indices:
                    return "unsupported_userdata_write", None
                candidate_indices[character_id] = index
            if characters is not None:
                # The client can submit only the character it just inspected
                # while retaining a party that names the rest of its roster.
                # Treat that as a delta over the server-owned roster, rather
                # than replacing the roster before validation.  This makes a
                # rejected party save non-destructive and prevents a UI close
                # from discarding earlier Pact results.
                for character in characters:
                    character_id = character["id"]
                    index = candidate_indices.get(character_id)
                    if index is None:
                        return "unsupported_userdata_write", None
                    merged = copy.deepcopy(candidate_rows[index])
                    merged.update(copy.deepcopy(character))
                    candidate_rows[index] = merged
            if party is not None:
                roster_ids = {
                    row.get("id") for row in candidate_rows
                    if isinstance(row, dict) and type(row.get("id")) is int and row["id"] > 0
                }
                if not {member for member in party["teamMembers"] if member}.issubset(roster_ids):
                    return "tutorial_state_conflict", None
            # Project and validate both halves before either is applied, so an
            # equip write cannot leave a one-sided character/Companion link.
            candidate_companions = None
            if companions is not None:
                current_buddy_info = userdata.get("buddyInfo")
                current_companions = (
                    current_buddy_info.get("list")
                    if isinstance(current_buddy_info, dict)
                    else None
                )
                candidate_companions = _project_companion_delta(
                    userdata, companions, allow_equipment=True,
                )
                if (
                    not isinstance(current_companions, list)
                    or candidate_companions is None
                    or not _valid_companion_equipment(
                        candidate_rows,
                        candidate_companions,
                        current_companions,
                        companion_equipment_catalog,
                    )
                ):
                    return "unsupported_companion_userdata", None
            if characters is not None:
                userdata["chrdata"] = candidate_rows
            if party is not None:
                userdata.update(copy.deepcopy(party))
            if candidate_companions is not None:
                userdata["buddyInfo"] = _companion_info(candidate_companions)
            if abandoning_active_story:
                # Give Up and a declined interrupted-battle resume both send
                # normal userdata saves (the former may contain only chrdata).
                # Treat either durable write as an explicit local abandon,
                # rather than leaving the account trapped in the active stage.
                account["tutorial_phase"] = "free_roam"
                account["active_generic_story"] = None
                account["active_hunt"] = None
                account["active_hunt_ticket_spent"] = None
                account["active_world_map_special"] = None
                account["active_battle_continue_coins"] = 0
            userdata["lastupdate"] = 1.0
            payload = _canonical_payload({"success": True, "lastupdate": 1.0})
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_hunting_start(
        self, token: str, request_id: str, body: bytes, catalog: HuntingCatalog,
        now: float | None = None, *, stamina: bool = False,
    ) -> tuple[str, dict[str, Any] | None]:
        """Authorise and charge one cataloged local Hunting entry."""
        now = time.time() if now is None else now
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                if cached.get("body_sha256") != digest:
                    return "request_collision", None
                return "replay", _canonical_payload(cached["payload"])
            values = _parse_hunting_start(body)
            stage = None if values is None else catalog.by_identity().get((values["chapter"], values["section"]))
            # Only the ticket contract puts an entry pair on the wire: the
            # client serializes `itemID`/`itemCount` for Metal Zone and for
            # nothing else, so any other stage must arrive without them.
            entry_pair = (stage.entry_item_id, stage.entry_item_count) if stage is not None and stage.ticket_optional else (0, 0)
            if (
                values is None or stage is None
                or values["stamina"] != stage.stamina or values["coins"] != stage.coins
                or (values["itemID"], values["itemCount"]) != entry_pair
                or values["ticket_form"] != int(stage.ticket_optional)
            ):
                return "unsupported_hunting_start", None
            userdata = account["userdata"]
            phase = account.setdefault("tutorial_phase", "initial")
            active = account.get("active_hunt")
            identity = {"chapter": stage.chapter, "section": stage.section}
            if phase == "hunting_active" and active == identity:
                # A retry under a *new* request id must not charge again.
                payload = _canonical_payload({"success": True, "refillStartTime": float(userdata.get("refillStartTime", 0.0))})
                requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
                self._persist_locked()
                return "success", payload
            # One active battle per account, shared with story and event stages.
            # A start for a different stage releases the one still open: the
            # client cannot be in two, so this is the player having left.
            if phase != "free_roam":
                release_abandoned_battle(account)
                phase = account["tutorial_phase"]
            if phase != "free_roam" or account.get("active_generic_story") is not None:
                return "tutorial_state_conflict", None
            if not stage.unlocked_at(int(userdata.get("progressCode", 0))):
                return "hunting_stage_locked", None
            # A Daily Quest pays out once per UTC day, and only the two quests
            # the day's rotation names can be entered at all. The client greys
            # both cases out from the fields login sends, so reaching either
            # refusal means the client asked for something it was not offering.
            # They use the soft shape rather than an error, so a player who gets
            # here anyway sees the client's own refusal, not a Network Error.
            if stage.once_per_utc_day and (
                stage.identity_label() not in daily_quest_rotation(_utc_day(now))
                or _daily_quest_played_today(account, stage, now)
            ):
                return "success", _canonical_payload({"success": False, "errorCode": 1})
            items = userdata.get("itemList")
            if not isinstance(items, list) or len(items) != catalog.item_slots or any(type(value) is not int for value in items):
                return "unsupported_hunting_start", None
            coins = int(userdata.get("coins", 0))
            held = items[stage.entry_item_id - 1] if stage.entry_item_id else 0
            # A ticket is an alternative to stamina, so holding none is not a
            # failure: the entry falls back to the stamina cost the client
            # displays in that case.  Only an entry item the stage charges *in
            # addition* to stamina can refuse for want of the item.
            spends_ticket = stage.ticket_optional and held >= stage.entry_item_count
            stamina_due = 0 if spends_ticket else stage.stamina
            # The Power-Up Item is read before the entry item is debited so that
            # both spends see the same starting inventory; the projection is
            # discarded unless the entry itself is accepted.
            help_result, help_items = help_item_debit(
                userdata, values["helpItemID"], catalog.item_slots,
            )
            if help_result == "unsupported":
                return "unsupported_hunting_start", None
            origin = entry_stamina_origin(userdata, stamina_due, now, enabled=stamina)
            if coins < stage.coins or origin is None:
                return "success", _canonical_payload({"success": False, "errorCode": 1})
            if help_result == "unavailable" or (
                stage.entry_item_id and not stage.ticket_optional and held < stage.entry_item_count
            ):
                return "success", _canonical_payload({"success": False, "errorCode": 2})
            userdata["refillStartTime"] = origin
            userdata["coins"] = coins - stage.coins
            if help_items is not None:
                # Re-bind rather than mutate: the entry-item debit below indexes
                # the live list, so both spends have to land on the same object.
                items[:] = help_items
            if stage.entry_item_id and (spends_ticket or not stage.ticket_optional):
                items[stage.entry_item_id - 1] = items[stage.entry_item_id - 1] - stage.entry_item_count
            _synchronize_wallet_projection(userdata)
            account["tutorial_phase"] = "hunting_active"
            account["active_hunt"] = identity
            account["active_battle_continue_coins"] = 0
            if stage.once_per_utc_day:
                # The day is consumed at accepted start, not at clear: the
                # retired service updated `lastDailyQuestPlayTime` from
                # start_quest, so an abandoned run spent the attempt. The clear
                # stamps again, which is a no-op on the same day and keeps a run
                # started before this behaviour existed coherent.
                _stamp_daily_quest_clear(account, stage, now)
            # The final client does not remove a Metal Ticket from its local
            # item list at start. Its later clear therefore repeats the
            # pre-entry count even though the server has already committed the
            # spend. Retain the entry choice so only that one stale slot can be
            # reconciled at clear time; stamina fallback must remain exact.
            account["active_hunt_ticket_spent"] = spends_ticket
            # Luck rises here for the same reasons it rises on an ordinary story
            # stage. `LUCK_GAIN_MIN_STAMINA` is a rule about what a battle cost,
            # not about which selector offered it, so the declared cost is what
            # it reads -- a Metal Ticket standing in for stamina buys the same
            # battle and must not quietly cost the party its Luck.  The
            # `allowLucky` chapters add their own source on top, which is what
            # reaches free Lucky Orbling and the two cheap flagged Hunting
            # stages the battle-end rule cannot.
            luck_up = roll_luck_up_table(
                userdata, stage.stamina, request_id, digest,
                lucky_chapter=stage.chapter,
            )
            payload = _canonical_payload({"success": True, "refillStartTime": origin})
            if help_items is not None:
                # An inventory is reported only when a Power-Up Item was spent,
                # so an ordinary entry keeps the shape it has always had.  The
                # list carries the entry ticket's debit too, which the client
                # would otherwise repeat stale at clear; `_projected_hunting_items`
                # accepts either count, so both orders settle.
                payload = _canonical_payload(payload | {"itemList": list(items)})
            if any(luck_up):
                # No chest is authored: the community record's own no-chest list
                # names the Hunting and Metal zones, and `luckResult` is sent
                # only as the empty six slots that accompany a gain, which is
                # the same shape an ordinary story stage with no documented pool
                # already sends.
                payload = _canonical_payload(payload | {
                    "luckResult": [EMPTY_SLOT] * 6, "luckUpTable": list(luck_up),
                })
            account["active_luck_up"] = list(luck_up)
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_hunting_clear(
        self, token: str, request_id: str, body: bytes, catalog: HuntingCatalog,
        now: float | None = None, *, outcome_strict: bool = False,
    ) -> tuple[str, dict[str, Any] | None]:
        """Settle one structurally valid result for the active Hunting stage.

        The surviving client executes the battle and reports its outcome.  By
        default the local preservation server trusts that report while still
        requiring exact stage ownership, wallet arithmetic, inventory
        projection, and a single durable settlement.  ``outcome_strict`` turns
        the catalog's recovered reward ceilings back into an audit gate.

        Companion grants remain limited to ids for which the catalog supplies
        the level needed to author the response row; accepting an unknown id
        would require inventing state the client did not send.
        """
        now = time.time() if now is None else now
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                if cached.get("body_sha256") != digest:
                    return "request_collision", None
                return "replay", _canonical_payload(cached["payload"])
            clear = _parse_generic_story_clear(body)
            if clear is None:
                return "unsupported_hunting_clear", None
            result = clear["battle_result"]
            identity = (result["chapter"], result["section"])
            stage = catalog.by_identity().get(identity)
            userdata = account["userdata"]
            if (
                stage is None
                or account.setdefault("tutorial_phase", "initial") != "hunting_active"
                or account.get("active_hunt") != {"chapter": identity[0], "section": identity[1]}
            ):
                return "tutorial_state_conflict", None
            # A Hunting battle settles rewards; it never moves story progress.
            expected_coins = int(userdata.get("coins", 0)) + result["coins"]
            if (
                clear["progressCode"] != int(userdata.get("progressCode", 0))
                or clear["worldMapNo"] != int(userdata.get("worldMapNo", 0))
                or clear["valuables"].get("coins") not in _settled_wallet_coins(account, expected_coins)
                or clear["summonList"] != userdata.get("summonList", [])
            ):
                return "tutorial_state_conflict", None
            # Hunting has no recovered Summon authoring contract. Accepting a
            # reported Summon here would acknowledge the clear while silently
            # discarding its reward, which is neither trust nor compatibility.
            if result["summons"]:
                return "invalid_local_hunting_result", None
            if outcome_strict and not hunting_settlement_within_bounds(stage, result):
                return "invalid_local_hunting_result", None
            gains = {int(item_id): count for item_id, count in result["items"].items()}
            projected_items = _projected_hunting_items(
                userdata.get("itemList"), clear["itemList"], gains, stage,
                account.get("active_hunt_ticket_spent"), catalog.item_slots,
                catalog.max_stack,
            )
            if projected_items is None:
                return "invalid_local_hunting_result", None
            companions = _granted_hunting_companions(userdata, stage, result, catalog.max_companions)
            if companions is None:
                return "invalid_local_hunting_result", None
            wallet_fields = ("energyAppStore", "energy", "energyAndApp", "freeEnergy", "energyGooglePlay", "coins")
            userdata.update({
                "lastupdate": 1.0,
                "coins": expected_coins,
                "valuables": {name: expected_coins if name == "coins" else int(userdata.get(name, 0)) for name in wallet_fields},
                "itemList": projected_items,
                # The roster is merged, never replaced: a stale client must not
                # delete a grant it had not read back.  See `_preserved_roster`.
                "chrdata": _preserved_roster(userdata.get("chrdata"), clear["chrdata"]),
            })
            # After the merge, so the entry's authored gain lands on the roster
            # the clear settled rather than on the one it replaced, and once,
            # because the entry is what rolled it.
            active_luck_up = account.get("active_luck_up")
            if isinstance(active_luck_up, list):
                apply_luck_up_table(userdata, active_luck_up)
            announced: dict[int, int] = {}
            if stage.character_grants:
                announced |= _apply_hunting_character_grants(userdata, stage)
            if result["monsters"]:
                announced |= _apply_monster_recruits(userdata, result["monsters"])
            if stage.once_per_utc_day:
                _stamp_daily_quest_clear(account, stage, now)
            account["tutorial_phase"] = "free_roam"
            account["active_luck_up"] = []
            account["active_hunt"] = None
            account["active_hunt_ticket_spent"] = None
            account["active_battle_continue_coins"] = 0
            # Hunting, Metal Zone, the special quest and the Daily Quests pay no
            # preservation Energy: they repeat without bound, and the income is
            # reserved for story progress that cannot. See `archive_economy`.
            # The wallet projection written above therefore already carries the
            # balance this response reports.
            payload = _canonical_payload({
                "success": True, "lastupdate": 1.0, "sentMessage": False,
                "coins": expected_coins, "freeEnergy": int(userdata.get("freeEnergy", 0)),
                # Restated for the reason the generic story clear restates it:
                # silence about the meter reads as a full one.  Hunting never
                # refills at a boundary, so this is always the entry's own
                # post-spend origin.
                "refillStartTime": float(userdata.get("refillStartTime", 0.0)),
                "chrdata": _announced_roster(userdata["chrdata"], announced), "itemList": copy.deepcopy(userdata["itemList"]),
            })
            # Only a settlement that actually granted Companions touches the box
            # or reports it, so the four item and Coin families keep the exact
            # response they were verified with.
            if result["buddies"]:
                userdata["buddyInfo"] = companions
                payload = _canonical_payload(payload | {"buddyInfo": copy.deepcopy(companions)})
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_world_map_special_start(
        self, token: str, request_id: str, body: bytes, catalog: WorldMapSpecialCatalog,
        now: float | None = None, *, stamina: bool = False,
    ) -> tuple[str, dict[str, Any] | None]:
        """Start one Chapter-1100 battle behind the native Chapter-34 map gate."""
        now = time.time() if now is None else now
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                if cached.get("body_sha256") != digest:
                    return "request_collision", None
                return "replay", _canonical_payload(cached["payload"])
            values = _parse_generic_story_start(body)
            stage = None if values is None else catalog.by_identity().get((values["chapter"], values["section"]))
            if (
                values is None or stage is None
                or values["stamina"] != stage.stamina or values["coins"] != stage.coins
                # The client hides the Power-Up Item slot on a World-0 map
                # special -- `IsHelpItemEnabled` refuses on `InWMSpecial` -- so
                # a start naming one here is not a form it produces.
                or values["helpItemID"]
            ):
                return "unsupported_start_quest", None
            userdata = account["userdata"]
            progress = int(userdata.get("progressCode", 0))
            if not catalog.unlocked_at(chapter_for_progress(progress)):
                return "world_map_special_locked", None
            frontier = self._world_map_special_progress(account, catalog)
            if stage.battle > frontier[stage.route]:
                return "world_map_special_locked", None
            phase = account.setdefault("tutorial_phase", "initial")
            identity = {"chapter": stage.chapter, "section": stage.section}
            if phase == "world_map_special_active" and account.get("active_world_map_special") == identity:
                # A retry under a fresh request id reports the meter without
                # debiting it twice, as the story and Hunting starts do.
                payload = _canonical_payload({"success": True, "refillStartTime": float(userdata.get("refillStartTime", 0.0))})
                requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
                self._persist_locked()
                return "success", payload
            # One active battle per account, shared with story and Hunting. A
            # start for a different stage releases the one still open.
            if phase != "free_roam":
                release_abandoned_battle(account)
                phase = account["tutorial_phase"]
            if phase != "free_roam" or account.get("active_generic_story") is not None:
                return "tutorial_state_conflict", None
            origin = entry_stamina_origin(userdata, stage.stamina, now, enabled=stamina)
            if origin is None:
                return "success", _canonical_payload({"success": False, "errorCode": 1})
            userdata["refillStartTime"] = origin
            _synchronize_wallet_projection(userdata)
            account["tutorial_phase"] = "world_map_special_active"
            account["active_world_map_special"] = identity
            account["active_battle_continue_coins"] = 0
            # Chapter 1100 charges 25 stamina, which clears the battle-end gate
            # comfortably; its recovered `allowLucky` is 0, so it carries no
            # Lucky-enemy source.  Its chests stay refused as labeled local
            # policy, so as on Hunting only the empty slots accompany a gain.
            luck_up = roll_luck_up_table(userdata, stage.stamina, request_id, digest)
            payload = _canonical_payload({"success": True, "refillStartTime": origin})
            if any(luck_up):
                payload = _canonical_payload(payload | {
                    "luckResult": [EMPTY_SLOT] * 6, "luckUpTable": list(luck_up),
                })
            account["active_luck_up"] = list(luck_up)
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_world_map_special_clear(
        self, token: str, request_id: str, body: bytes, catalog: WorldMapSpecialCatalog,
    ) -> tuple[str, dict[str, Any] | None]:
        """Settle a Chapter-1100 clear inside its bounded reward policy.

        This route must never move the core `progressCode`, which belongs to
        the ordinary story and would be corrupted by a World-0 special claiming
        it; that stays a refusal, not a silent correction.  Two channels pay:
        the battle's own experience within `WORLD_MAP_SPECIAL_EXP_CEILING`, and
        at most one reported Companion from the stage's own recovered
        `dropBuddies` manifest -- the bounded acceptance the community record
        supports; see :mod:`liminal_gate.world_map_special`.  Every other
        reward channel, including the record's documented item drops and the
        battle-4 character recruit, remains refused for lack of recovered
        identities.
        """
        with self.lock:
            account = self.accounts.get(self.tokens.get(token))
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            digest = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                if cached.get("body_sha256") != digest:
                    return "request_collision", None
                return "replay", _canonical_payload(cached["payload"])
            clear = _parse_generic_story_clear(body)
            if clear is None:
                return "unsupported_clear_quest", None
            identity = (clear["battle_result"]["chapter"], clear["battle_result"]["section"])
            stage = catalog.by_identity().get(identity)
            userdata = account["userdata"]
            if (
                stage is None
                or account.setdefault("tutorial_phase", "initial") != "world_map_special_active"
                or account.get("active_world_map_special") != {"chapter": identity[0], "section": identity[1]}
            ):
                return "tutorial_state_conflict", None
            if (
                clear["progressCode"] != int(userdata.get("progressCode", 0))
                or clear["worldMapNo"] != int(userdata.get("worldMapNo", 0))
                or clear["valuables"].get("coins") != int(userdata.get("coins", 0))
            ):
                return "tutorial_state_conflict", None
            if not _bounded_special_result_matches(
                userdata, clear, WORLD_MAP_SPECIAL_EXP_CEILING,
            ):
                return "invalid_local_world_map_special_result", None
            result = clear["battle_result"]
            if not world_map_special_companions_within_bounds(stage, result["buddies"]):
                return "invalid_local_world_map_special_result", None
            # Paying EXP means the roster changes, because levels live in it, so
            # this can no longer require the roster back unchanged. It does
            # require the same *characters*: this chapter mints no character,
            # and accepting an arbitrary roster would let the id list become a
            # grant channel alongside the bounded Companion box grant below.
            if not _same_roster_membership(userdata.get("chrdata"), clear["chrdata"]):
                return "invalid_local_world_map_special_result", None
            companions = None
            if result["buddies"]:
                companions = _granted_hunting_companions(
                    userdata, stage, result, _WORLD_MAP_SPECIAL_COMPANION_BOX,
                )
                if companions is None:
                    return "invalid_local_world_map_special_result", None
            # The battle really was fought, so the levels it produced are kept
            # the way every other EXP-bearing clear keeps them: as a trusted
            # local client report, merged so a stale client cannot delete a
            # grant it never read back.
            userdata["chrdata"] = _preserved_roster(userdata.get("chrdata"), clear["chrdata"])
            # After the merge, and once, for the reason the Hunting clear gives.
            active_luck_up = account.get("active_luck_up")
            if isinstance(active_luck_up, list):
                apply_luck_up_table(userdata, active_luck_up)
            frontier = self._world_map_special_progress(account, catalog)
            if stage.battle == frontier[stage.route] and stage.battle < catalog.final_battle(stage.route):
                frontier[stage.route] = stage.battle + 1
            account["world_map_special_progress"] = frontier
            userdata["lastupdate"] = 1.0
            account["tutorial_phase"] = "free_roam"
            account["active_luck_up"] = []
            account["active_world_map_special"] = None
            account["active_battle_continue_coins"] = 0
            # The Chapter 1100 Roads pay no preservation Energy either: they are
            # repeatable training zones, and the income is reserved for story
            # progress. See `archive_economy`.
            _synchronize_wallet_projection(userdata)
            payload = _canonical_payload({
                "success": True, "lastupdate": 1.0, "sentMessage": False,
                "coins": int(userdata.get("coins", 0)),
                "freeEnergy": int(userdata.get("freeEnergy", 0)),
                # Restated for the reason the generic story clear restates it:
                # silence about the meter reads as a full one.  Chapter 1100
                # never refills at a boundary, so this is always the entry's own
                # post-spend origin.
                "refillStartTime": float(userdata.get("refillStartTime", 0.0)),
                "chrdata": copy.deepcopy(userdata.get("chrdata", [])),
                "itemList": copy.deepcopy(userdata.get("itemList", [])),
            })
            # Only a settlement that actually granted a Companion touches the
            # box or reports it, matching the Hunting clear's contract.
            if companions is not None:
                userdata["buddyInfo"] = companions
                payload = _canonical_payload(payload | {"buddyInfo": copy.deepcopy(companions)})
            requests[_replay_key(request_id, body)] = {"body_sha256": digest, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    @staticmethod
    def _world_map_special_progress(
        account: dict[str, Any], catalog: WorldMapSpecialCatalog,
    ) -> dict[str, int]:
        """The per-route frontier battle, defaulted for accounts saved before it."""
        stored = account.get("world_map_special_progress")
        frontier = initial_route_progress(catalog)
        if isinstance(stored, dict):
            for route in frontier:
                value = stored.get(route)
                if type(value) is int and 1 <= value <= catalog.final_battle(route):
                    frontier[route] = value
        return frontier

    def apply_generic_story_start(
        self, token: str, request_id: str, body: bytes, catalog: StoryCatalog | StoryProgressionCatalog | EventCatalog,
        settlement_catalog: SettlementCatalog | None = None, now: float | None = None,
        *, stamina: bool = False, luck_pool_catalog: LuckPoolCatalog | None = None,
    ) -> tuple[str, dict[str, Any] | None]:
        """Start one catalog-declared local story stage after the tutorial."""
        now = time.time() if now is None else now
        with self.lock:
            account_id = self.tokens.get(token)
            account = self.accounts.get(account_id)
            if account is None:
                return "unknown_account", None
            requests = account.setdefault("tutorial_requests", {})
            body_hash = hashlib.sha256(body).hexdigest()
            cached = requests.get(_replay_key(request_id, body))
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
            event = isinstance(catalog, EventCatalog)
            userdata = account["userdata"]
            if event and not stage.unlocked_at(
                int(userdata.get("progressCode", 0))
            ):
                return "event_stage_locked", None
            if isinstance(catalog, StoryProgressionCatalog):
                current = int(userdata.get("progressCode", 0))
                expected = catalog.expected_clear_progress(current, (stage.chapter, stage.section))
                if expected is None:
                    return "tutorial_state_conflict", None
            identity = {"chapter": stage.chapter, "section": stage.section}
            if (
                account.setdefault("tutorial_phase", "initial") == "generic_story_active"
                and account.get("active_generic_story") == identity
            ):
                # A fresh request id for the stage already active is a retry,
                # so it reports the meter without debiting it a second time.
                payload = {"success": True, "refillStartTime": float(userdata.get("refillStartTime", 0.0))}
                requests[_replay_key(request_id, body)] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
                self._persist_locked()
                return "success", payload
            # A start for a different stage releases the battle still open.
            if account["tutorial_phase"] != "free_roam":
                release_abandoned_battle(account)
            if account["tutorial_phase"] != "free_roam" or account.get("active_generic_story") is not None:
                return "tutorial_state_conflict", None
            # Entry debits the stamina meter, never the Energy wallet.  The two
            # are different currencies: `refillStartTime` is a fill origin the
            # client turns back into a bar (see `stamina_meter`), while Energy
            # is the premium balance Pacts and refills spend.  A catalog that
            # declares no cost defers to the cost the client itself submitted,
            # matching how a dynamic catalog already defers on clear coins.
            stamina_cost = stage.stamina if stage.stamina is not None else values["stamina"]
            # Coins are asymmetric with stamina on purpose.  Stamina refills on
            # its own, so honouring a client-declared cost the catalog does not
            # know costs a tester minutes at worst.  Coins are durable and have
            # no such floor, so an undeclared coin cost is charged as zero
            # rather than on the client's word.
            coin_cost = stage.coins if stage.coins is not None else 0
            help_result, help_items = help_item_debit(userdata, values["helpItemID"])
            if help_result == "unsupported":
                return "unsupported_start_quest", None
            origin = entry_stamina_origin(userdata, stamina_cost, now, enabled=stamina)
            if origin is None or int(userdata.get("coins", 0)) < coin_cost:
                return "success", _canonical_payload(
                    {"success": False, "errorCode": 1}
                )
            if help_result == "unavailable":
                return "success", _canonical_payload({"success": False, "errorCode": 2})
            userdata["refillStartTime"] = origin
            userdata["coins"] = int(userdata.get("coins", 0)) - coin_cost
            if help_items is not None:
                userdata["itemList"] = help_items
            _synchronize_wallet_projection(userdata)
            payload = {"success": True, "refillStartTime": origin}
            if help_items is not None:
                payload["itemList"] = list(help_items)
            # The Luck Treasure Chest is decided here, not at clear: the client
            # holds no chest table and renders whatever this names. Seeded from
            # the request identity so a retry cannot re-roll a better chest.
            luck_slots = roll_luck_result(
                stage.chapter, stage.section, party_team_luck(userdata),
                request_id, body_hash, catalog=luck_pool_catalog,
            )
            # 2006 Lucia and 7010 Cryptid Forest reach the client through this
            # handler rather than the Hunting one, so the `allowLucky` source
            # has to be offered here too.
            luck_up = roll_luck_up_table(
                userdata, stamina_cost, request_id, body_hash,
                lucky_chapter=stage.chapter,
            )
            if any(luck_slots) or any(luck_up):
                payload["luckResult"] = list(luck_slots)
                payload["luckUpTable"] = list(luck_up)
            account["tutorial_phase"] = "generic_story_active"
            account["active_generic_story"] = identity
            account["active_battle_continue_coins"] = 0
            # Retained because the client folds the chest into the balances it
            # reports at clear; settlement has to know what it handed out.
            account["active_luck_result"] = list(luck_slots)
            account["active_luck_up"] = list(luck_up)
            requests[_replay_key(request_id, body)] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def apply_generic_story_clear(
        self, token: str, request_id: str, body: bytes, catalog: StoryCatalog | StoryProgressionCatalog | EventCatalog,
        settlement_catalog: SettlementCatalog | None = None,
        outcome_catalog: StoryOutcomeCatalog | None = None,
        clear_state_catalog: ClearStateCatalog | None = None,
        outcome_strict: bool = False,
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
            cached = requests.get(_replay_key(request_id, body))
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
            event = isinstance(catalog, EventCatalog)
            reward_rule = None if settlement_catalog is None else settlement_catalog.rules.get(identity)
            fixed_clear_coins = (
                reward_rule.clear_coins
                if dynamic and reward_rule is not None and reward_rule.clear_coins is not None
                else clear["battle_result"]["coins"] if dynamic else stage.clear_coins
            )
            reported_battle_coins = clear["battle_result"]["coins"]
            expected_progress = catalog.expected_clear_progress(int(userdata.get("progressCode", 0)), identity) if dynamic else int(userdata.get("progressCode", 0)) if event else stage.clear_progress_code
            # Archive battles are executed by the surviving client. Its clear
            # form reports the variable battle Coins separately from the fixed
            # post-battle increment represented by EventStage.clear_coins. The
            # wallet must reconcile both. Counter Descent carries no reward
            # catalog, so its inventory is additionally projected from the drops
            # the client reports; see _projected_event_items below.
            # The Luck chest is a second reward layer, and an invisible one: a
            # real captured clear shows chest rewards absent from
            # `battle_result` (`luckynum=0`) while already inside the balances
            # the client submits. Settling without expecting them reads a
            # legitimate chest as an over-claim and refuses a won battle.
            authored_chest = account.get("active_luck_result")
            authored_chest = authored_chest if isinstance(authored_chest, list) else []
            expected_coins = (
                int(userdata.get("coins", 0))
                + fixed_clear_coins
                + (reported_battle_coins if event else 0)
                + chest_coins(authored_chest)
            )
            checks = (
                ("phase", account.setdefault("tutorial_phase", "initial") == "generic_story_active"),
                ("active_stage", active == {"chapter": identity[0], "section": identity[1]}),
                ("progress", expected_progress is not None and clear["progressCode"] == expected_progress),
                ("world_map", clear["worldMapNo"] == int(userdata.get("worldMapNo", 0))),
                ("wallet", clear["valuables"].get("coins") in _settled_wallet_coins(account, expected_coins)),
                (
                    "battle_coins",
                    event or reported_battle_coins == fixed_clear_coins,
                ),
            )
            failed = next((name for name, passed in checks if not passed), None)
            if failed is not None:
                return (f"event_clear_{failed}_conflict" if event else "tutorial_state_conflict"), None
            projected_items = None
            if event and stage.projected_rewards:
                projected_items = _projected_event_items(
                    userdata, clear, chest_items(authored_chest),
                )
                if projected_items is None:
                    return "invalid_local_event_result", None
            eidolon_summons = None
            if event and stage.selector == "eidolon":
                eidolon_summons = _eidolon_summon_projection(
                    userdata, clear, stage.summon_ids
                )
                if eidolon_summons is None:
                    return "invalid_local_event_result", None
            if settlement_catalog is not None and not _settlement_matches(
                userdata, clear, identity, settlement_catalog,
                extra_item_rewards=chest_items(authored_chest),
            ):
                return "invalid_local_settlement", None
            if clear_state_catalog is not None and not _clear_state_matches(userdata, clear, clear_state_catalog):
                return "invalid_local_clear_state", None
            buddy_info = None if outcome_catalog is None else _outcome_buddy_info(userdata, clear, identity, outcome_catalog, clear_state_catalog, outcome_strict)
            if outcome_catalog is not None and buddy_info is None:
                return "invalid_local_outcome", None
            wallet_fields = (
                "energyAppStore", "energy", "energyAndApp", "freeEnergy",
                "energyGooglePlay", "coins",
            )
            canonical_valuables = {
                field: expected_coins if field == "coins" else int(userdata.get(field, 0))
                for field in wallet_fields
            }
            userdata.update({
                "lastupdate": 1.0,
                "progressCode": expected_progress,
                "coins": expected_coins,
                "valuables": canonical_valuables,
                "chrdata": _preserved_roster(userdata.get("chrdata"), clear["chrdata"]),
                # A projected settlement persists the array the server derived,
                # not the one the client sent; they are equal by construction,
                # and taking the server's keeps the durable counts authoritative.
                "itemList": (
                    projected_items
                    if projected_items is not None
                    else _preserved_counts(userdata.get("itemList"), clear["itemList"])
                ),
                "summonList": (
                    eidolon_summons
                    if eidolon_summons is not None
                    else _preserved_counts(
                        userdata.get("summonList"), clear["summonList"]
                    )
                ),
            })
            if buddy_info is not None:
                userdata["buddyInfo"] = buddy_info
            # Preservation income; see `archive_economy`.  The wallet projection
            # is resynchronised afterwards so the client's nested `valuables`
            # copy carries the new balance rather than the pre-clear one.
            award_stage_energy(account, "event" if event else "story", *identity)
            if dynamic and stage.chapter_boundary:
                award_chapter_energy(account, stage.chapter)
                # Local preservation policy requested for the guided ordinary
                # story: completing a whole chapter refills the confirmed
                # client-side meter.  Zero is the client's own full-meter
                # representation, not an arbitrary balance.  Keep this out of
                # event, Hunting, and individual non-boundary stage clears.
                userdata["refillStartTime"] = 0.0
            canonical_valuables["freeEnergy"] = int(userdata.get("freeEnergy", 0))
            userdata["valuables"] = canonical_valuables
            announced: dict[int, int] = {}
            if event:
                by_id = {row.get("id"): row for row in userdata["chrdata"] if isinstance(row, dict)}
                for character_id in stage.character_ids:
                    if character_id not in by_id:
                        row = _granted_character_row(character_id)
                        userdata["chrdata"].append(row); by_id[character_id] = row
                        announced[character_id] = 1
            # The chest's own Companions and characters. Granted after the
            # roster merge for the same reason the Luck gain below is: a stale
            # client's `chrdata` must not overwrite what this clear awarded.
            announced |= _award_chest_grants(userdata, authored_chest)
            # The Luck gain rolled at start is committed here, after the roster
            # merge, so a stale client's chrdata cannot overwrite it -- the same
            # ordering `_preserved_roster` exists to guarantee for grants.
            active_luck_up = account.get("active_luck_up")
            if isinstance(active_luck_up, list):
                apply_luck_up_table(userdata, active_luck_up)
            payload = {
                "success": True,
                "lastupdate": 1.0,
                "sentMessage": False,
                "coins": expected_coins,
                "freeEnergy": int(userdata.get("freeEnergy", 0)),
                # The settlement callback restates the fill origin for the same
                # reason the start callback carries it: zero is not a missing
                # value to the client, it is the assertion that the meter
                # refilled at the epoch.  A settlement that stays silent about
                # the meter is read as a full one, so a client that rebuilds its
                # `UserData` from this response draws a full bar over stamina
                # the entry really spent.  This is the post-clear origin, so it
                # also carries the chapter-boundary refill above rather than
                # leaving that policy to be inferred from a later read.
                "refillStartTime": float(userdata.get("refillStartTime", 0.0)),
                "chrdata": _announced_roster(userdata["chrdata"], announced),
                "itemList": copy.deepcopy(userdata["itemList"]),
            }
            if buddy_info is not None:
                payload["buddyInfo"] = copy.deepcopy(buddy_info)
            account["tutorial_phase"] = "free_roam"
            account["active_generic_story"] = None
            account["active_battle_continue_coins"] = 0
            account["active_luck_result"] = []
            account["active_luck_up"] = []
            payload = _canonical_payload(payload)
            requests[_replay_key(request_id, body)] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
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
            cached = requests.get(_replay_key(request_id, body))
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
            requests[_replay_key(request_id, body)] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
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
            cached = requests.get(_replay_key(request_id, body))
            if cached is not None:
                if cached.get("body_sha256") != body_hash:
                    return "request_collision", None
                return "replay", copy.deepcopy(cached["payload"])
            if _parse_continue(body) != policy["client_cost"]:
                return "unsupported_continue", None
            userdata = account["userdata"]
            coins = userdata.get("coins", 0)
            phase = account.setdefault("tutorial_phase", "initial")
            # A Hunting battle continues on the same terms as an ordinary story
            # one. The client offers Continue after a game over in a Daily
            # Quest and posts it here, so refusing on the phase alone answered a
            # button the client was really showing -- and, because the refusal
            # carried a 409, the player saw a Network Error rather than any
            # answer. Chapter 1100 stays excluded: it runs as a world-map
            # special, and its own notice says it cannot be continued.
            in_battle = (
                (phase == "generic_story_active" and isinstance(account.get("active_generic_story"), dict))
                or (phase == "hunting_active" and isinstance(account.get("active_hunt"), dict))
            )
            if not in_battle or type(coins) is not int or coins < policy["coin_cost"]:
                # Soft-refused rather than 409, the same way an out-of-rotation
                # Daily Quest entry is: a state the client should not have
                # offered is still the client's to report, and a transport error
                # is the one answer it cannot show the player usefully.
                return "success", _canonical_payload({"success": False, "errorCode": 1})
            userdata["coins"] = coins - policy["coin_cost"]
            # The client does not take this off its own wallet, and cannot: the
            # coin cost is local policy, while what the client thinks it spent
            # is the `client_cost` unit this answer reports back as Energy. Its
            # clear therefore repeats the pre-Continue coin total, and the
            # settlement compares that figure against the server's. Remember
            # what was charged so exactly that much can be reconciled there --
            # the same accommodation `active_hunt_ticket_spent` makes for the
            # Metal Ticket the client leaves in its own item list at entry.
            account["active_battle_continue_coins"] = (
                _continue_coins_charged(account) + policy["coin_cost"]
            )
            payload = {
                "success": True,
                "energy": int(userdata.get("energy", 0)),
                "freeEnergy": int(userdata.get("freeEnergy", 0)),
            }
            requests[_replay_key(request_id, body)] = {"body_sha256": body_hash, "payload": copy.deepcopy(payload)}
            self._persist_locked()
            return "success", payload

    def available_backups(self) -> list[Path]:
        """Retained states beside this save, newest first."""
        candidates = (
            self.path.with_name(f"{self.path.name}.bak.{index}")
            for index in range(1, ACCOUNT_STATE_BACKUP_COUNT + 1)
        )
        return [candidate for candidate in candidates if candidate.is_file()]

    def _load(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ProfileError("could not read local bootstrap state") from error
        accounts, tokens, active_account_id, client_hosts, account_aliases = _parse_state_document(document)
        self.tokens = tokens
        self.active_account_id = active_account_id
        self.client_hosts = client_hosts
        self.account_aliases = account_aliases
        return accounts

    def document(self) -> dict[str, Any]:
        """The exact document `_persist_locked` would write for this state."""
        with self.lock:
            return self._document_locked()

    def _document_locked(self) -> dict[str, Any]:
        return {
            "accounts": self.accounts,
            "active_account_id": self.active_account_id,
            "tokens": self.tokens,
            "client_hosts": self.client_hosts,
            "account_aliases": self.account_aliases,
        }

    def replace_document(self, document: object) -> str | None:
        """Adopt an imported save, returning the account the client will play.

        The in-memory copy has to move with the file.  This server holds the
        whole state and republishes all of it on the next mutation, so writing
        only the file would leave the import to be overwritten by whatever the
        running process still believed.
        """
        accounts, tokens, active_account_id, client_hosts, account_aliases = _parse_state_document(document)
        with self.lock:
            self.accounts = accounts
            self.tokens = tokens
            self.active_account_id = active_account_id
            self.client_hosts = client_hosts
            self.account_aliases = account_aliases
            # Rotation happens inside the persist, so the save this import
            # replaced stays beside it as `.bak.1` and an unwanted import is
            # recoverable by the same route as any other bad write.
            self._persist_locked()
            return self.active_account_id

    def _synchronize_wallets_locked(self) -> None:
        """Hold the nested wallet equal to the flat one across every mutation.

        `valuables` is a projection the client reads; the flat fields beside it
        are what this server actually spends and grants.  Keeping the two in
        step was a per-site chore, and most sites did not do it: a Pact draw
        paid with Energy, an inbox present's Coins, a Rebirth, a stamina refill
        and a Trading Post exchange all moved the flat value and left the
        projection behind.  A tester's exported save showed exactly that after a
        ten-draw -- `valuables.freeEnergy` 72 against `freeEnergy` 22, the
        difference being the fifty the draw had spent -- and
        `account_state validate` refused it.

        Doing it here instead makes it an invariant of the save rather than
        something each mutation has to remember, because every mutation ends in
        a persist.  Loading repairs a save that already drifted; see
        `_migrate_wallet_projection`.
        """
        for account in self.accounts.values():
            userdata = account.get("userdata")
            if isinstance(userdata, dict):
                _synchronize_wallet_projection(userdata)

    def _bound_locked(self) -> None:
        """Keep the durable save bounded by recent history, not session length.

        The replay caches and the token map are both append-only in the wire
        protocol: `requestID` is near-unique per request and `otk` is a
        three-second time bucket, so a long session adds an entry to each every
        few seconds and never removes one.  Every entry is re-encoded and
        fsynced on *every* later save, so an account that is played enough
        turns each save into a progressively slower whole-file rewrite.  Both
        are only ever read for an immediate retry or the client's current
        token, so retaining a generous recent window is equivalent in
        behaviour and constant in cost.  Dicts preserve insertion order, so the
        oldest entries are the ones dropped.
        """
        for account in self.accounts.values():
            for name in REPLAY_CACHE_FIELDS:
                cache = account.get(name)
                if isinstance(cache, dict) and len(cache) > RETAINED_REQUESTS_PER_ACCOUNT:
                    for key in list(cache)[:len(cache) - RETAINED_REQUESTS_PER_ACCOUNT]:
                        del cache[key]
        # Bound tokens *per account* rather than globally: a household's second
        # save must keep its own recent identity even while another account is
        # the busier one, or an evicted binding would fall back to the active
        # account and replay against the wrong save.
        retained: dict[str, int] = {}
        for token, account_id in reversed(list(self.tokens.items())):
            seen = retained.get(account_id, 0)
            if seen >= RETAINED_TOKENS_PER_ACCOUNT:
                del self.tokens[token]
            else:
                retained[account_id] = seen + 1

    def _rotate_backups_locked(self) -> None:
        """Keep the last committed states beside the save before replacing it.

        The write itself is atomic, so this is not crash protection — it is
        recovery from a save that is intact but wrong: a bad merge, a hand
        edit, a client that reported nonsense.  Without it the durable account
        has exactly one copy and any damage to it is terminal.
        """
        if not self.path.exists():
            return
        for index in range(ACCOUNT_STATE_BACKUP_COUNT, 1, -1):
            older = self.path.with_name(f"{self.path.name}.bak.{index - 1}")
            if older.exists():
                os.replace(older, self.path.with_name(f"{self.path.name}.bak.{index}"))
        temporary = self.path.with_name(f".{self.path.name}.bak.tmp")
        try:
            shutil.copyfile(self.path, temporary)
            os.replace(temporary, self.path.with_name(f"{self.path.name}.bak.1"))
        finally:
            temporary.unlink(missing_ok=True)

    def _restore_from_disk_locked(self) -> None:
        """Drop every unpublished in-memory change by re-reading the save.

        `_persist_locked` republishes the whole document, so a failure means
        nothing of this mutation reached the disk and the file still holds the
        last state that did.  Re-reading it therefore reverts the mutation
        *and* the replay-cache entry the caller had already inserted, because
        that cache lives inside the account dicts this replaces.

        An absent file is the same situation with nothing to read back: the
        state that was never published is simply gone.
        """
        if not self.path.exists():
            self.accounts, self.tokens = {}, {}
            self.active_account_id, self.client_hosts, self.account_aliases = None, {}, {}
            return
        self.accounts = self._load()

    def _persist_locked(self) -> None:
        try:
            self._publish_locked()
        except BaseException:
            # Without this the caller keeps a mutation the disk never took and,
            # worse, the replay entry answering for it: an exact retry would
            # then be served from that cache with a success the save does not
            # contain, and the change would vanish at the next restart. If the
            # save cannot be re-read either, that failure propagates in place of
            # this one -- being unable to read the state is the graver of the
            # two, and Python chains the write failure onto it as context.
            self._restore_from_disk_locked()
            raise

    def _publish_locked(self) -> None:
        self._bound_locked()
        self._synchronize_wallets_locked()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encoded = (json.dumps(self._document_locked(), separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
        with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            self._rotate_backups_locked()
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)
        # The file contents are fsynced above, but the rename that publishes
        # them is only a directory update.  Without this the save can still be
        # lost to a hard emulator kill or power cut, which reads to a player as
        # progress that silently rolled back.
        _fsync_directory(self.path.parent)


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
        companion_draw_catalog: CompanionDrawCatalog | BundledCompanionDrawPolicy | None = None,
        pact_draw_catalog: PactDrawCatalog | BundledPactPolicy | None = None,
        achievement_catalog: AchievementCatalog | None = None,
        message_catalog: MessageCatalog | None = None,
        exchange_catalog: ExchangeCatalog | None = None,
        clear_state_catalog: ClearStateCatalog | None = None,
        story_progression_catalog: StoryProgressionCatalog | None = None,
        event_catalog: EventCatalog | None = None,
        drop_eligibility: bool = False,
        hunting_catalog: HuntingCatalog | None = None,
        daily_quests: bool = False,
        secondary_worlds: bool = False,
        cavern_forest: bool = False,
        luck_pool_catalog: LuckPoolCatalog | None = None,
        world_map_special_catalog: WorldMapSpecialCatalog | None = None,
        public_data_root: Path | None = None,
        outcome_strict: bool = False,
        companion_equipment_catalog: CompanionEquipmentCatalog | None = None,
        chapter_milestones: bool = False,
        login_bonuses: bool = False,
        original_mail_shape: bool = False,
        build_id: str = "development",
        daily_drop_bonuses: bool = False,
        stamina: bool = False,
    ) -> None:
        self.profile = profile
        self.state = state
        self.events = EventRecorder(event_log)
        self.resource_catalog = resource_catalog
        if not isinstance(build_id, str) or not build_id:
            raise ProfileError("build_id must be a nonempty string")
        self.build_id = build_id
        self.public_data_root = public_data_root.resolve() if public_data_root is not None else None
        self.story_catalog = story_catalog
        self.story_progression_catalog = story_progression_catalog
        self.event_catalog = event_catalog
        self.drop_eligibility = drop_eligibility
        self.settlement_catalog = settlement_catalog
        self.story_outcome_catalog = story_outcome_catalog
        self.outcome_strict = outcome_strict
        self.statusup_catalog = statusup_catalog
        self.job_catalog = job_catalog
        self.rebirth_catalog = rebirth_catalog
        self.summon_skill_catalog = summon_skill_catalog
        self.companion_catalog = companion_catalog
        self.companion_equipment_catalog = companion_equipment_catalog
        self.companion_strengthen_catalog = companion_strengthen_catalog
        self.companion_evolution_catalog = companion_evolution_catalog
        self.companion_draw_catalog = companion_draw_catalog
        self.pact_draw_catalog = pact_draw_catalog
        self.achievement_catalog = achievement_catalog
        self.message_catalog = (
            build_bundled_chapter_message_policy()
            if (chapter_milestones or login_bonuses) and message_catalog is None
            else message_catalog
        )
        self.chapter_milestones = chapter_milestones
        self.login_bonuses = login_bonuses
        self.original_mail_shape = original_mail_shape
        self.daily_drop_bonuses = daily_drop_bonuses
        self.exchange_catalog = exchange_catalog
        self.clear_state_catalog = clear_state_catalog
        self.hunting_catalog = hunting_catalog
        self.daily_quests = daily_quests
        self.secondary_worlds = secondary_worlds
        self.cavern_forest = cavern_forest
        self.luck_pool_catalog = luck_pool_catalog
        # The client always draws a stamina bar -- it is `ServerConstants` and
        # local `UserData`, not a server-side UI this server could remove.  Off
        # therefore means the meter is pinned full: entry debits nothing and
        # refuses nothing, which is the behaviour a preserved single-player
        # archive wants and the one this server ships by default.
        self.stamina = stamina
        # The client draws both Chapter-1100 map points itself once the story
        # has passed Chapter 34, so the route is bundled and always accepted
        # rather than advertised behind a flag.
        self.world_map_special_catalog = (
            build_bundled_world_map_special_policy()
            if world_map_special_catalog is None else world_map_special_catalog
        )
        try:
            super().__init__(address, BootstrapHandler)
        except BaseException:
            try:
                if resource_catalog is not None:
                    resource_catalog.close()
            finally:
                state.close()
            raise

    def server_close(self) -> None:
        """Hand the save back so a replacement server can start immediately."""
        try:
            super().server_close()
        finally:
            try:
                if self.resource_catalog is not None:
                    self.resource_catalog.close()
            finally:
                self.state.close()


class BootstrapHandler(BaseHTTPRequestHandler):
    server: BootstrapServer

    def _client_host(self) -> str | None:
        """The requesting client's address, used only to route unknown tokens."""
        address = getattr(self, "client_address", None)
        host = address[0] if isinstance(address, tuple) and address else None
        return host if isinstance(host, str) and host else None

    def _serve_local_content(self, path: str) -> bool:
        """Serve operator UI, derived banners, or manifested local resources."""
        if path == "/en/news/app":
            self._html(
                HTTPStatus.OK,
                "<!doctype html><html><head><meta charset=\"utf-8\"><title>Project Liminal Gate</title></head>"
                "<body><h1>Project Liminal Gate</h1><p>Your local preservation server is running.</p>"
                "<p>Check the project README for local setup and support details.</p></body></html>",
            )
            return True
        if path == "/favicon.ico":
            self._empty(HTTPStatus.NO_CONTENT)
            return True
        banner_name = PACT_BANNER_FILES.get(path)
        if banner_name is not None and self.server.public_data_root is not None:
            banner = self.server.public_data_root / "banners" / banner_name
            if banner.is_file() and banner.resolve().is_relative_to(self.server.public_data_root):
                self._file(HTTPStatus.OK, banner, "image/png")
            else:
                self._json(HTTPStatus.NOT_FOUND, {"error": "local_banner_not_found"})
            return True
        coin_creeps_name = COIN_CREEPS_BANNER_FILES.get(path)
        if coin_creeps_name is not None and self.server.public_data_root is not None:
            banner = self.server.public_data_root / "banner_resources" / coin_creeps_name
            if banner.is_file() and banner.resolve().is_relative_to(self.server.public_data_root):
                self._file(HTTPStatus.OK, banner, "application/octet-stream")
                return True
            # Fall through so an exact operator-owned sp1003 resource in the
            # hash-validated manifest can satisfy the same URL.
        resource = (
            self.server.resource_catalog.resolve(path)
            if self.server.resource_catalog else None
        )
        # Some client resource URLs use the CDN root directly (for example,
        # `/Profile/...`) instead of the patched `/resources/` prefix.  The
        # resource manifest remains the authority: this is only an alias for
        # an already hash-validated user-local entry, never filesystem lookup.
        if (
            resource is None
            and self.server.resource_catalog is not None
            and path.startswith("/")
        ):
            resource = self.server.resource_catalog.resolve("/resources" + path)
        if resource is not None:
            self._resource(HTTPStatus.OK, resource)
            return True
        if path.startswith("/resources/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "resource_not_found"})
            return True
        return False

    def _required_account_token(self, query: dict[str, str]) -> str | None:
        token = query.get("otk")
        if token:
            return token
        self._json(
            HTTPStatus.BAD_REQUEST,
            {"error": "missing_local_account_token"},
        )
        return None

    def _retired_route_refusal(self, path: str) -> int | None:
        """The refusal code for a retired paid or advertised route, if this is one."""
        for name, code in REFUSAL_ROUTE_CODES.items():
            if path == self.server.profile.routes.get(name):
                return code
        return None

    def _refuse_retired_route(self, code: int, query: dict[str, str]) -> None:
        """Refuse one retired route in the endpoint's own namespace.

        The soft shape the Daily Quest gate already uses: a signed body whose
        refusal code `_endpoint_refusal_envelope` moves to `cmdError`, so the
        screen that asked runs its own callback. Nothing is read, written, or
        charged, so there is no replay cache to consult -- refusing twice under
        one request id refuses identically.
        """
        token = self._required_account_token(query)
        if token is None:
            return
        self._signed(
            HTTPStatus.OK, token,
            _canonical_payload({"success": False, "errorCode": code}),
        )

    def _serves_local_state(self, path: str) -> bool:
        """Whether this server answers the operator save-transfer route here.

        The packaged Android server is the reason the route exists: its save
        lives in app-private storage no workstation command can reach, so an
        HTTP route through the loopback listener is the only way in or out.  A
        LAN-bound server has no such problem — its save is an ordinary file on
        the machine running it — and publishing a downloadable, replaceable save
        to every device on the network is not a trade the route is worth.

        A profile that claimed this path for a game route would keep it: the
        client's transport is the one that cannot be broken from here.
        """
        if path != LOCAL_STATE_ROUTE or path in set(self.server.profile.routes.values()):
            return False
        address = getattr(self.server, "server_address", None)
        return isinstance(address, tuple) and bool(address) and address[0] in {"127.0.0.1", "::1"}

    def do_GET(self) -> None:
        target = urlsplit(self.path)
        if target.path == "/healthz":
            self._json(
                HTTPStatus.OK,
                {"service": "project-liminal-gate", "status": "ok", "build_id": self.server.build_id},
            )
            return
        if self._serves_local_state(target.path):
            self._json(HTTPStatus.OK, self.server.state.document())
            return
        if self._serve_local_content(target.path):
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
            self.server.state.create_account(token, response_account_id, profile.userdata_seed, self.server.message_catalog, self.server.exchange_catalog, self._client_host())
            self._signed(HTTPStatus.OK, token, signup)
            return
        token = query.get("otk")
        if target.path == profile.routes.get("time"):
            token = self._required_account_token(query)
            if token is None:
                return
            self._signed(HTTPStatus.OK, token, {"success": True, "timestamp": float(int(time.time()))})
            return
        if target.path == profile.routes.get("status"):
            token = self._required_account_token(query)
            if token is None:
                return
            payload = _render(profile.responses["status"], token)
            payload["constants"] = self._server_constants(token)
            self._signed(HTTPStatus.OK, token, payload)
            return
        if target.path == profile.routes.get("login"):
            account_id = query.get(profile.account_binding["login_query_field"])
            resolved = (
                self.server.state.bind_login_token(token, account_id, self._client_host())
                if token and isinstance(account_id, str) else None
            )
            if resolved is None:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unknown_local_account"})
                return
            # The response echoes the UUID the client sent — its own stored
            # credential — while state lookups use the account it resolved to,
            # which differs for a linked device.
            payload = _render(profile.responses["login"], token, account_id)
            # Required, not decorative: once the status route advertises the
            # final-major client version, the client's own final-major login
            # branch indexes `CountryCodes` with this stored value, and reaches
            # the country-selection modal when nothing is stored.
            payload |= dict(LOCAL_LOGIN_COUNTRY_FIELDS)
            payload["name"] = self.server.state.accounts[resolved].get("username", payload.get("name", "Player"))
            now = time.time()
            payload["messageList"] = self.server.state.login_messages(
                resolved, self.server.chapter_milestones,
                self.server.login_bonuses, now, self.server.message_catalog,
                self.server.original_mail_shape,
            )
            # Reads as an ordinary login statistic and is not one. The client
            # stores it as `UserData.lastLoginTime`, and `DailyQuestManager`
            # opens a slot only when that time is newer than the slot's last
            # play. Left unsent it stays zero, no slot ever opens, and the
            # Huntland button is disabled even with the category flag on and
            # today's two quests named.
            payload["lastLogin"] = now
            # Ungated, unlike every other source below: these three name no
            # stage, cost nothing, and touch no saved state, so there is no
            # policy for an operator to decide. A server that answers a login
            # at all is a server whose client should be playing the right
            # track for the screen it is on.
            event_flags: dict[str, Any] = music_event_flags()
            progress = self.server.state.accounts[resolved].get(
                "userdata", {}
            ).get("progressCode", 0)
            if self.server.event_catalog is not None:
                event_flags |= self.server.event_catalog.flags(
                    progress if type(progress) is int and progress >= 0 else None
                )
            if self.server.hunting_catalog is not None:
                if type(progress) is int and progress >= 0:
                    event_flags |= self.server.hunting_catalog.client_event_flags(
                        progress
                    )
            if self.server.secondary_worlds and type(progress) is int and progress >= 0:
                # Unlike the Daily Quests these do carry a story gate: the
                # client's own map predicates check a section threshold before
                # offering the swap, and the flag is the half the server owns.
                event_flags |= secondary_world_event_flags(
                    (progress & 0xFFFF) >> 6, progress & 0x3F,
                )
            if self.server.cavern_forest and type(progress) is int and progress >= 0:
                # These carry a story gate for the same reason the secondary
                # worlds do: the client's own map point compares cleared
                # progress against an `openChapter` before drawing, and the
                # flag is the half the server owns. Sending it earlier would
                # draw nothing; sending it never is what kept both areas
                # invisible, because the point is built behind a prefix scan
                # over exactly these flags.
                event_flags |= cavern_forest_event_flags(
                    (progress & 0xFFFF) >> 6, progress & 0x3F,
                )
            if self.server.daily_quests:
                # The flags open the category; they never depend on story
                # progress, because Daily Quests carry no recovered story gate.
                event_flags |= daily_quest_event_flags()
                # The flags alone leave every entry drawn and greyed out. These
                # six fields are what the client's DailyQuestManager actually
                # reads to know which two quests today offers and whether they
                # are still playable.
                payload |= daily_quest_login_fields(
                    self.server.state.accounts[resolved], time.time(),
                )
            if self.server.daily_drop_bonuses:
                # This is only the recovered service-owned gate. The final
                # client computes the 15-day item/monster bonus itself from
                # the server-corrected instant and its local calendar day.
                event_flags |= daily_bonus_event_flags()
            if event_flags:
                payload["eventFlags"] = event_flags
            if self.server.drop_eligibility:
                # Without this the client marks every character and Companion
                # `canDrop = false` and silently discards each drop it rolls.
                payload["chrBuddyData"] = login_chr_buddy_data()
            self._signed(HTTPStatus.OK, token, payload)
            return
        if target.path in {
            profile.routes.get("userdata"),
            profile.routes.get("userdata_after_close"),
        }:
            # The surviving client may rotate its OTK immediately after a
            # successful login, before its first read-only userdata request.
            # Bind before reading so an older emulator token cannot select an
            # abandoned local account after the active save has been resumed.
            userdata = (
                self.server.state.userdata_for(token, stamina=self.server.stamina)
                if token and self.server.state.bind_rotated_token(token, self._client_host())
                else None
            )
            if userdata is None:
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unknown_local_account"})
                return
            self._signed(HTTPStatus.OK, token, {"success": True, **userdata})
            return
        for operation in ("multiplay_enable", "special_event"):
            if target.path == profile.routes.get(operation):
                token = self._required_account_token(query)
                if token is None:
                    return
                self._signed(
                    HTTPStatus.OK,
                    token,
                    _render(profile.responses[operation], token),
                )
                return
        if target.path == profile.routes.get("get_current_exchange"):
            # The OTK rotates every three seconds, so the token that opens the
            # trading post is almost never the one the last mutation bound.
            # Resolve it by client host exactly as the userdata read and every
            # mutation do, or an otherwise valid session gets a network error
            # at the counter.
            if token and not self.server.state.bind_rotated_token(token, self._client_host()):
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "unknown_account"})
                return
            result, payload = self.server.state.current_exchange(token, self.server.exchange_catalog)
            if result == "success": self._signed(HTTPStatus.OK, token or "", {"success": True, **(payload or {})})
            else: self._json(HTTPStatus.NOT_IMPLEMENTED if result == "unsupported_exchange" else HTTPStatus.UNAUTHORIZED, {"error": result})
            return
        refusal = self._retired_route_refusal(target.path)
        if refusal is not None:
            self._refuse_retired_route(refusal, query)
            return
        self._json(HTTPStatus.NOT_IMPLEMENTED, {"error": "route_not_implemented"})

    def _import_local_state(self) -> None:
        """Adopt an operator-supplied save in place of the running one."""
        body = self._read_mutation_body()
        if body is None:
            return
        try:
            document = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_local_state_document"})
            return
        try:
            active_account_id = self.server.state.replace_document(document)
        except ProfileError as error:
            # The refusal text is the one the next start would print for the
            # same file, so an import that would strand the save says so now.
            self._json(HTTPStatus.BAD_REQUEST, {"error": "rejected_local_state", "detail": str(error)})
            return
        self._json(HTTPStatus.OK, {"status": "imported", "active_account_id": active_account_id})

    def _read_mutation_body(self) -> bytes | None:
        """Read one bounded request body, emitting its transport error in place."""
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
            return None
        if length < 0:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_content_length"})
            return None
        if length > MAX_REQUEST_BODY_BYTES:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request_body_too_large"})
            return None
        body = self.rfile.read(length)
        if len(body) != length:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "incomplete_request_body"})
            return None
        return body

    def _select_mutation(
        self, path: str, token: str, request_id: str, body: bytes,
    ) -> MutationDispatch:
        """Select the most specific first-pass handler for one mutation route."""
        profile = self.server.profile
        state = self.server.state
        if path == profile.routes.get("do_slot"):
            result, payload = state.draw_ordinary_pact(
                token, request_id, body, self.server.pact_draw_catalog,
            )
            if result == "unsupported_ordinary_pact":
                return MutationDispatch("summon", profile.tutorial_summons, result, payload)
            return MutationDispatch("ordinary_pact", result=result, payload=payload)
        if path == profile.routes.get("do_buddy_slot"):
            result, payload = state.draw_companions(
                token, request_id, body, self.server.companion_draw_catalog,
            )
            return MutationDispatch("do_buddy_slot", result=result, payload=payload)
        if path == profile.routes.get("userdata"):
            return self._select_userdata_mutation(token, request_id, body)
        if path == profile.routes.get("start_quest"):
            dispatch = MutationDispatch("start", profile.story_starts)
            parsed = _parse_generic_story_start(body)
            if (
                self.server.event_catalog is not None
                and parsed is not None
                and (parsed["chapter"], parsed["section"])
                in self.server.event_catalog.by_identity()
            ):
                dispatch.result, dispatch.payload = state.apply_generic_story_start(
                    token, request_id, body, self.server.event_catalog,
                    stamina=self.server.stamina,
                )
                dispatch.kind, dispatch.transitions = "event_start", ()
            return dispatch

        direct: dict[str, tuple[str, MutationOperation]] = {
            "continue": (
                "continue",
                lambda: state.apply_generic_story_continue(
                    token, request_id, body, profile.continue_policy,
                ),
            ),
            "change_uname": (
                "change_uname",
                lambda: state.change_uname(token, request_id, body),
            ),
            "refill_stamina": (
                "refill_stamina",
                lambda: state.refill_stamina(
                    token, request_id, body, stamina=self.server.stamina,
                ),
            ),
            "unlock_metal_zone": (
                "unlock_metal_zone",
                lambda: state.unlock_metal_zone(token, request_id, body),
            ),
            "achived": (
                "achievement",
                lambda: state.claim_achievement(
                    token, request_id, body, self.server.achievement_catalog,
                ),
            ),
            "read_messages": (
                "read_messages",
                lambda: state.read_messages(
                    token, request_id, body, self.server.message_catalog,
                ),
            ),
            "delete_messages": (
                "delete_messages",
                lambda: state.delete_messages(
                    token, request_id, body, self.server.message_catalog,
                ),
            ),
            "exchange": (
                "exchange",
                lambda: state.exchange(
                    token, request_id, body, self.server.exchange_catalog,
                ),
            ),
            "statusup_item": (
                "statusup_item",
                lambda: state.use_statusup_item(
                    token, request_id, body, self.server.statusup_catalog,
                ),
            ),
            "add_job": (
                "add_job",
                lambda: state.add_job(token, request_id, body, self.server.job_catalog),
            ),
            "rebirth": (
                "rebirth",
                lambda: state.rebirth(token, request_id, body, self.server.rebirth_catalog),
            ),
            "summon_skill_unlock": (
                "summon_skill_unlock",
                lambda: state.summon_skill_unlock(
                    token, request_id, body, self.server.summon_skill_catalog,
                ),
            ),
            "sell_buddy": (
                "sell_buddy",
                lambda: state.sell_companions(
                    token, request_id, body, self.server.companion_catalog, multiple=False,
                ),
            ),
            "sell_buddies": (
                "sell_buddies",
                lambda: state.sell_companions(
                    token, request_id, body, self.server.companion_catalog, multiple=True,
                ),
            ),
            "buddy_strengthen": (
                "buddy_strengthen",
                lambda: state.strengthen_companion(
                    token, request_id, body, self.server.companion_strengthen_catalog,
                ),
            ),
            "buddy_evolve": (
                "buddy_evolve",
                lambda: state.evolve_companion(
                    token, request_id, body, self.server.companion_evolution_catalog,
                ),
            ),
        }
        for route_name, (kind, operation) in direct.items():
            if path == profile.routes.get(route_name):
                result, payload = operation()
                return MutationDispatch(kind, result=result, payload=payload)
        if path == profile.routes.get("add_exchange_count"):
            return MutationDispatch(
                "exchange_count", result="unsupported_exchange_count",
            )
        return MutationDispatch("clear", profile.story_clears)

    def _select_userdata_mutation(
        self, token: str, request_id: str, body: bytes,
    ) -> MutationDispatch:
        """Separate overlapping tutorial, roster, party, and Companion writes."""
        profile = self.server.profile
        state = self.server.state
        dispatch = MutationDispatch("write", profile.tutorial_writes)
        ordinary_write = state.allows_ordinary_userdata_write(token)
        party_write = _parse_free_roam_party_userdata_write(body)
        party_layout_write = (
            _parse_free_roam_party_layout_userdata_write(body)
            if party_write is None else None
        )
        character_write = (
            _parse_free_roam_character_userdata_write(body)
            if ordinary_write and party_write is None else None
        )
        # Equip moves and party swaps can carry both roster and Companion
        # deltas. Try those combined forms before either single-half form.
        party_companion_write = (
            _parse_party_companion_userdata_write(body)
            if party_write is None else None
        )
        equip_write = (
            _parse_companion_equip_userdata_write(body)
            if party_write is None and party_companion_write is None else None
        )
        companion_write = (
            _parse_companion_userdata_write(body)
            if (
                party_write is None
                and character_write is None
                and party_companion_write is None
                and equip_write is None
            )
            else None
        )
        if party_companion_write is not None:
            characters, party, companions = party_companion_write
            dispatch.result, dispatch.payload = state.update_character_userdata(
                token, request_id, body, characters, party, companions,
                self.server.companion_equipment_catalog,
            )
            dispatch.kind, dispatch.transitions = "party_userdata", ()
        elif equip_write is not None:
            characters, companions = equip_write
            dispatch.result, dispatch.payload = state.update_character_userdata(
                token, request_id, body, characters, None, companions,
                self.server.companion_equipment_catalog,
            )
            dispatch.kind, dispatch.transitions = "companion_userdata", ()
        elif party_write is not None:
            characters, party = party_write
            dispatch.result, dispatch.payload = state.update_character_userdata(
                token, request_id, body, characters, party,
            )
            dispatch.kind, dispatch.transitions = "party_userdata", ()
        elif party_layout_write is not None:
            dispatch.result, dispatch.payload = state.update_character_userdata(
                token, request_id, body, None, party_layout_write,
            )
            dispatch.kind, dispatch.transitions = "party_userdata", ()
        elif character_write is not None:
            dispatch.result, dispatch.payload = state.update_character_userdata(
                token, request_id, body, character_write,
            )
            dispatch.kind, dispatch.transitions = "character_userdata", ()
        elif companion_write is not None:
            dispatch.result, dispatch.payload = state.update_companion_userdata(
                token, request_id, body, companion_write,
            )
            dispatch.kind, dispatch.transitions = "companion_userdata", ()

        # Tutorial structural writes deliberately override a matching free-roam
        # parser until the account reaches the ordinary userdata boundary.
        if profile.structural_writes and not ordinary_write:
            try:
                candidate_fields = tuple(parse_qsl(
                    body.decode("ascii"), keep_blank_values=True, strict_parsing=True,
                ))
            except (UnicodeDecodeError, ValueError):
                candidate_fields = ()
            if any(
                tuple(name for name, _ in candidate_fields)
                == tuple(item["field_names"])
                for item in profile.structural_writes
            ):
                dispatch.kind = "structural"
                dispatch.transitions = profile.structural_writes
        return dispatch

    def _resolve_mutation(
        self, dispatch: MutationDispatch, token: str, request_id: str, body: bytes,
    ) -> tuple[str, dict[str, Any] | None]:
        """Arbitrate tutorial fallbacks against specific catalog operations."""
        state = self.server.state
        kind, transitions = dispatch.kind, dispatch.transitions
        if kind in RESOLVED_MUTATION_KINDS:
            if dispatch.result is None:
                raise RuntimeError(f"resolved mutation {kind!r} has no result")
            return dispatch.result, dispatch.payload
        if (
            kind == "write"
            and self.server.story_progression_catalog is not None
            and state.allows_story_progression(token)
            and _parse_story_progression_reveal(body) is not None
        ):
            return state.apply_story_progression_reveal(
                token, request_id, body, self.server.story_progression_catalog,
            )
        if kind == "start" and _identity_chapter(
            _started_identity(body)
        ) == WORLD_MAP_SPECIAL_CHAPTER:
            return state.apply_world_map_special_start(
                token, request_id, body, self.server.world_map_special_catalog,
                stamina=self.server.stamina,
            )
        if kind == "clear" and _identity_chapter(
            _cleared_identity(body)
        ) == WORLD_MAP_SPECIAL_CHAPTER:
            return state.apply_world_map_special_clear(
                token, request_id, body, self.server.world_map_special_catalog,
            )
        if (
            kind == "start"
            and self.server.hunting_catalog is not None
            and _started_hunting_identity(body) in self.server.hunting_catalog.by_identity()
        ):
            return state.apply_hunting_start(
                token, request_id, body, self.server.hunting_catalog,
                stamina=self.server.stamina,
            )
        if kind == "start" and (
            self.server.event_catalog is not None
            or self.server.story_catalog is not None
            or self.server.story_progression_catalog is not None
        ) and (
            not any(item["body"].encode("utf-8") == body for item in transitions)
            or state.replays_cleared_stage(
                token, _started_identity(body), self.server.story_progression_catalog,
            )
        ):
            parsed = _parse_generic_story_start(body)
            event_identity = (
                None if parsed is None else (parsed["chapter"], parsed["section"])
            )
            event = (
                self.server.event_catalog
                if (
                    self.server.event_catalog is not None
                    and event_identity in self.server.event_catalog.by_identity()
                )
                else None
            )
            catalog = event or self.server.story_catalog or self.server.story_progression_catalog
            return (
                state.apply_generic_story_start(
                    token, request_id, body, catalog, stamina=self.server.stamina,
                    luck_pool_catalog=self.server.luck_pool_catalog,
                )
                if catalog is not None
                else ("unsupported_start_quest", None)
            )
        if (
            kind == "clear"
            and self.server.hunting_catalog is not None
            and _cleared_identity(body) in self.server.hunting_catalog.by_identity()
        ):
            return state.apply_hunting_clear(
                token, request_id, body, self.server.hunting_catalog,
                outcome_strict=self.server.outcome_strict,
            )
        if kind == "clear" and (
            self.server.event_catalog is not None
            or self.server.story_catalog is not None
            or self.server.story_progression_catalog is not None
        ):
            clear = _parse_generic_story_clear(body)
            identity = (
                None
                if clear is None
                else (
                    clear["battle_result"]["chapter"],
                    clear["battle_result"]["section"],
                )
            )
            event = (
                self.server.event_catalog
                if (
                    self.server.event_catalog is not None
                    and identity in self.server.event_catalog.by_identity()
                )
                else None
            )
            replaying = state.replays_cleared_stage(
                token, identity, self.server.story_progression_catalog,
            )
            if event is not None or replaying or not _profile_clear_matches(body, transitions):
                catalog = event or self.server.story_catalog or self.server.story_progression_catalog
                return (
                    state.apply_generic_story_clear(
                        token,
                        request_id,
                        body,
                        catalog,
                        self.server.settlement_catalog,
                        self.server.story_outcome_catalog,
                        self.server.clear_state_catalog,
                        self.server.outcome_strict,
                    )
                    if catalog is not None
                    else ("unsupported_clear_quest", None)
                )
        return state.apply_tutorial_transition(
            token, request_id, body, transitions, kind=kind,
        )

    def _write_mutation_result(
        self, token: str, body: bytes, result: str, payload: dict[str, Any] | None,
    ) -> None:
        """Emit one mutation result and attach bounded refusal diagnostics."""
        if result in {"success", "replay"}:
            self._signed(HTTPStatus.OK, token, payload or {})
            return
        if result.startswith("unsupported_"):
            shapes = refused_write_shapes(body)
            if shapes:
                details = dict(getattr(self, "_event_details", None) or {})
                details["request_shapes"] = shapes
                self._event_details = details
        status = MUTATION_RESULT_STATUSES.get(result)
        if status is None:
            # A result string missing from the table is a wiring mistake in
            # this server, not client behavior. Answer it as one instead of
            # raising inside the handler thread and dropping the connection.
            self._json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"unmapped_mutation_result:{result}"})
            return
        self._json(status, {"error": result})

    def do_POST(self) -> None:
        target = urlsplit(self.path)
        # Ahead of the mutation dispatch below, which answers every unknown
        # path with 501 and would otherwise swallow this route.
        if self._serves_local_state(target.path):
            self._import_local_state()
            return
        profile = self.server.profile
        # Which verb the retired routes used is not recovered -- this client
        # sends both, and a receipt argues for POST -- so they are answered on
        # either. The body is drained first regardless: a kept-alive connection
        # whose unread body is left in the socket parses as the next request.
        refusal = self._retired_route_refusal(target.path)
        if refusal is not None:
            if self._read_mutation_body() is None:
                return
            self._refuse_retired_route(
                refusal, dict(parse_qsl(target.query, keep_blank_values=True)),
            )
            return
        mutation_routes = {profile.routes.get(name) for name in MUTATION_ROUTE_NAMES}
        if target.path not in mutation_routes:
            self._json(HTTPStatus.NOT_IMPLEMENTED, {"error": "route_not_implemented"})
            return
        body = self._read_mutation_body()
        if body is None:
            return
        self._event_details = safe_form_diagnostics(body)
        query = dict(parse_qsl(target.query, keep_blank_values=True))
        token = query.get("otk")
        request_id = query.get("requestID")
        if not token or not request_id:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "missing_local_mutation_identity"})
            return
        if not self.server.state.bind_rotated_token(token, self._client_host()):
            self._json(HTTPStatus.UNAUTHORIZED, {"error": "unknown_account"})
            return
        self._event_details.update(self.server.state.safe_account_context(token))
        dispatch = self._select_mutation(target.path, token, request_id, body)
        result, payload = self._resolve_mutation(dispatch, token, request_id, body)
        self._write_mutation_result(token, body, result, payload)

    def do_HEAD(self) -> None:
        target = urlsplit(self.path)
        if target.path == "/healthz":
            self._head(HTTPStatus.OK, "application/json", len(
                (json.dumps({"service": "project-liminal-gate", "status": "ok", "build_id": self.server.build_id}, separators=(",", ":")) + "\n").encode("utf-8")
            ))
            return
        resource = self.server.resource_catalog.resolve(target.path) if self.server.resource_catalog else None
        if resource is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "resource_not_found"})
            return
        self._resource(HTTPStatus.OK, resource, include_body=False)

    def _signed(self, status: HTTPStatus, token: str, payload: dict[str, Any]) -> None:
        body = _signed_json(token, _endpoint_refusal_envelope(payload), self.server.profile.signing)
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

    def _head(self, status: HTTPStatus, content_type: str, size: int) -> None:
        self.server.events.record(self.command, self.path, status)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.end_headers()

    def _resource(self, status: HTTPStatus, resource: Any, *, include_body: bool = True) -> None:
        # Opened before anything is sent, because opening is what re-checks a
        # filesystem resource against the manifest.  Discovering a changed file
        # after `Content-Length` had gone out would leave the client reading a
        # body that cannot match the header, which it reports as a transport
        # failure rather than as the stale manifest it is.
        try:
            stream = self.server.resource_catalog.open(resource)
        except ResourceCatalogError as error:
            self._json(HTTPStatus.SERVICE_UNAVAILABLE, {
                "error": "resource_changed_on_disk", "detail": str(error),
            })
            return
        with stream:
            self.server.events.record(self.command, self.path, status)
            self.send_response(status)
            self.send_header("Content-Type", resource.content_type)
            self.send_header("Content-Length", str(resource.size))
            self.end_headers()
            if not include_body:
                return
            shutil.copyfileobj(stream, self.wfile, length=1024 * 1024)

    def _file(self, status: HTTPStatus, path: Path, content_type: str) -> None:
        body = path.read_bytes()
        self.server.events.record(self.command, self.path, status)
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _server_constants(self, token: str) -> dict[str, Any]:
        """Return the constants block for whichever account holds this token.

        The client refetches the status route after every login and after
        clears, so the zone lists here follow story progress without any push.
        Dedicated list keys are always present, even when empty: the client's setter
        reads them directly, and an absent key is not the same as no zones.
        """
        pacts = self.server.pact_draw_catalog
        coins = None if pacts is None else pacts.cost_for_kind(0)
        energy = None if pacts is None else pacts.cost_for_kind(1)
        constants = build_server_constants(
            normal_slot_coins=None if coins is None else coins[1],
            rare_slot_energy=None if energy is None else energy[1],
        )
        constants |= {
            "metalHuntingList": [],
            "huntingHuntingList": [],
            "descentHuntingList": [],
            "towerQuestList": [],
            "eidolonQuestList": [],
        }
        progress = self.server.state.progress_for_status(
            token,
            self._client_host(),
        )
        local_special_events: list[str] = []
        if self.server.event_catalog is not None:
            event_lists = self.server.event_catalog.client_lists(progress)
            if event_lists["specialQuestList"]:
                local_special_events = event_lists["specialQuestList"]
                constants["specialQuestList"] = local_special_events
            constants["descentHuntingList"] = event_lists["descentHuntingList"]
            constants["towerQuestList"] = event_lists["towerQuestList"]
            constants["eidolonQuestList"] = event_lists["eidolonQuestList"]
        if progress is not None and self.server.hunting_catalog is not None:
            hunting_lists = self.server.hunting_catalog.client_lists(progress)
            constants["metalHuntingList"] = hunting_lists["metalHuntingList"]
            constants["huntingHuntingList"] = hunting_lists["huntingHuntingList"]
            # Archive rows and the bounded built-in Special Quest are separate
            # preservation slices. Keep both when their gates are open, while
            # preserving the closed sentinel below every unlock so the client
            # never falls back to its built-in 50-row Metal list.
            if hunting_lists["specialQuestList"]:
                constants["specialQuestList"] = list(dict.fromkeys(
                    local_special_events + hunting_lists["specialQuestList"]
                ))
        return constants

    def log_message(self, format: str, *args: object) -> None:
        return


def _cleared_identity(body: bytes) -> tuple[int, int] | None:
    """The chapter/section a clear request settles, if it is well formed."""
    clear = _parse_generic_story_clear(body)
    return None if clear is None else (clear["battle_result"]["chapter"], clear["battle_result"]["section"])


def _started_identity(body: bytes) -> tuple[int, int] | None:
    """The chapter/section a start request names, if it is well formed."""
    values = _parse_generic_story_start(body)
    return None if values is None else (values["chapter"], values["section"])


#: The phases that mean one battle is open. Free roam and the tutorial states
#: are not among them: only these three own an active stage to release.
ACTIVE_BATTLE_PHASES = frozenset({"generic_story_active", "hunting_active", "world_map_special_active"})


def _settled_wallet_coins(account: dict[str, Any], expected: int) -> tuple[int, ...]:
    """The coin totals a clear may honestly report for this battle.

    Normally one: the server's own total plus what the battle paid. A battle
    that was continued has a second, higher one, because the client never took
    the local coin cost off its wallet -- it is not a cost the client knows
    about. The widening is exactly what this battle's Continues charged and
    nothing else, and the settlement still commits `expected`, so continuing
    costs what it says it costs.
    """
    charged = _continue_coins_charged(account)
    return (expected,) if charged == 0 else (expected, expected + charged)


def _continue_coins_charged(account: dict[str, Any]) -> int:
    """Coins this battle's Continues have taken that the client has not.

    Zero for a save written before Continue charged anything, and for any value
    that is not a plain count: this only ever widens a settlement check, so a
    malformed one must widen it by nothing.
    """
    charged = account.get("active_battle_continue_coins")
    return charged if type(charged) is int and charged > 0 else 0


def release_abandoned_battle(account: dict[str, Any]) -> bool:
    """Drop an open battle the client has demonstrably left, and say whether it did.

    Explicit local policy, not recovered behaviour. The client runs one battle
    at a time, so a start for a *different* stage is proof the last one was
    abandoned -- and until that counted as proof, an abandoned battle left the
    account unable to start anything at all.  A Daily Quest reached that state
    from an ordinary game over: the day is spent at accepted start, so the
    client greys out the one stage whose re-entry would have released it, and
    every other start answered 409 until the UTC day rolled over.

    A save carrying a roster or party already releases a battle the same way
    (see `write_userdata`); this covers the client that starts something else
    without writing one first.
    """
    if account.get("tutorial_phase") not in ACTIVE_BATTLE_PHASES:
        return False
    account["tutorial_phase"] = "free_roam"
    account["active_generic_story"] = None
    account["active_hunt"] = None
    account["active_hunt_ticket_spent"] = None
    account["active_world_map_special"] = None
    account["active_battle_continue_coins"] = 0
    return True


def help_item_debit(
    userdata: dict[str, Any], help_item_id: int, slots: int = BUNDLED_ITEM_SLOTS,
) -> tuple[str, list[int] | None]:
    """Project the inventory a start's Power-Up Item choice leaves behind.

    Returns `("ok", items)` with the projected list when one was spent,
    `("ok", None)` when the start named none, and a refusal otherwise.  Nothing
    is written here: the caller commits only once the entry itself is accepted,
    so a start that goes on to refuse for stamina or Coins does not eat the item.

    The server is the sole authority for this spend.  `UITeamPopup.SetHelpItem`
    only paints the slot -- it never touches the held count -- and the client
    then overwrites its whole inventory from this response's `itemList`
    (`UserData.LoadItemlistFromJson`).  So unlike the Metal Ticket, whose count
    the client repeats stale at clear, the following clear reports the number
    this debit produced and needs no reconciliation.

    An ID outside the client's own HelpItem set is a wire-form refusal rather
    than a soft failure: `UIHelpItemSelect` cannot offer one, so a start
    carrying it did not come from the pre-battle slot.  `slots` is the caller's
    own inventory width -- the Hunting catalogs declare theirs -- so an ID past
    the end of a narrower one is refused rather than indexed for.
    """
    if help_item_id == 0:
        return "ok", None
    if help_item_id not in HELP_ITEM_IDS or help_item_id > slots:
        return "unsupported", None
    items = userdata.get("itemList")
    if (
        not isinstance(items, list) or len(items) != slots
        or any(type(value) is not int for value in items)
    ):
        return "unsupported", None
    held = items[help_item_id - 1]
    if held < 1:
        return "unavailable", None
    projected = list(items)
    projected[help_item_id - 1] = held - 1
    return "ok", projected


def entry_stamina_origin(
    userdata: dict[str, Any], cost: int, now: float, *, enabled: bool,
) -> float | None:
    """The fill origin quest entry leaves behind, or `None` if the meter is short.

    All four entry routes -- generic story, event, Hunting, and the Chapter-1100
    special -- debit one meter from the same two fields, so they ask here rather
    than repeating the pair of `userdata` reads `spend_stamina` needs.

    With the stamina policy off the meter is pinned to the client's own
    full-meter origin: entry never refuses for want of stamina, and an origin an
    earlier stamina-enabled run left behind returns to full on the next quest
    rather than lingering as a bar nothing will ever debit again.
    """
    if not enabled:
        return FULL_METER_ORIGIN
    return spend_stamina(
        float(userdata.get("refillStartTime", 0.0)), cost,
        chapter_for_progress(int(userdata.get("progressCode", 0))), now,
    )


def _utc_day(now: float) -> int:
    """The UTC day a moment falls in. Daily Quests roll over at 00:00 UTC."""
    return int(now // 86_400)


def _daily_quest_played_today(account: dict[str, Any], stage: Any, now: float) -> bool:
    played = account.get("daily_quest_clears")
    if not isinstance(played, dict):
        return False
    return played.get(stage.identity_label()) == _utc_day(now)


def _stamp_daily_quest_clear(account: dict[str, Any], stage: Any, now: float) -> None:
    played = account.setdefault("daily_quest_clears", {})
    if isinstance(played, dict):
        played[stage.identity_label()] = _utc_day(now)
    # The exact moment is what the client greys the entry out from, so it is
    # kept beside the day rather than reconstructed from it.
    times = account.setdefault("daily_quest_play_times", {})
    if isinstance(times, dict):
        times[stage.identity_label()] = float(now)


def _daily_quest_play_time(account: dict[str, Any], quest_id: str, now: float) -> float:
    """The moment this quest was played today, or 0.0 if it has not been.

    A stamp from an earlier day reports as zero rather than as itself: the
    client compares the value against its own clock, and yesterday's timestamp
    left in place is how a quest stays greyed out after it should have reset.
    """
    played = account.get("daily_quest_clears")
    times = account.get("daily_quest_play_times")
    if not isinstance(played, dict) or played.get(quest_id) != _utc_day(now):
        return 0.0
    stamp = times.get(quest_id) if isinstance(times, dict) else None
    # A save written before play times were recorded still knows the day, which
    # is enough to keep a quest played today greyed out.
    return float(stamp) if isinstance(stamp, (int, float)) else float(_utc_day(now) * 86_400)


def daily_quest_login_fields(account: dict[str, Any], now: float) -> dict[str, Any]:
    """Return the six Daily Quest fields the client's login callback reads.

    ``DailyQuestManager`` stores ``dailyQuest``/``1``/``2`` as its
    ``todaysQuest`` strings and decides playability from them together with the
    matching ``lastDailyQuestPlayTime``. Slot zero is deliberately empty: the
    final schedule serves two quests a day and the client's legacy first slot
    went unused.
    """
    slot1, slot2 = daily_quest_rotation(_utc_day(now))
    return {
        "dailyQuest": "",
        "dailyQuest1": slot1,
        "dailyQuest2": slot2,
        "lastDailyQuestPlayTime": 0.0,
        "lastDailyQuestPlayTime1": _daily_quest_play_time(account, slot1, now),
        "lastDailyQuestPlayTime2": _daily_quest_play_time(account, slot2, now),
    }


def _granted_character_row(character_id: int, level: int = 1) -> dict[str, Any]:
    """Mint the durable roster row a server-side grant adds.

    The save holds exactly one roster shape: the generic record that
    `_valid_generic_character_record` accepts, which is what the client submits
    and what every settlement check reads the durable roster through. `isNew`
    and `levelAdded` are result-screen vocabulary rather than durable state --
    the Pact draw has always kept them out of the save and put them only in its
    reply -- so a grant persists this row and announces itself through
    `_announced_roster`.
    """
    return {
        "id": character_id, "buddy": 0, "date": 0.0,
        "jobSlots": [0.0, 0.0, 0.0], "jobLevels": [float(level), 0.0, 0.0],
        "jobID": 0, "flags": 0, "skillBoost": 0,
    }


def _announced_roster(rows: Any, granted: dict[int, int]) -> list[Any]:
    """Project a roster, marking the characters this one request just granted.

    The client's result screen reads `isNew` and `levelAdded` off the roster it
    is handed back. Both describe a single response rather than the account, so
    they are added to the projection instead of being stored on the row.
    """
    if not isinstance(rows, list):
        return []
    return [
        {**copy.deepcopy(row), "isNew": True, "levelAdded": granted[row["id"]]}
        if isinstance(row, dict) and row.get("id") in granted
        else copy.deepcopy(row)
        for row in rows
    ]


def _apply_hunting_character_grants(userdata: dict[str, Any], stage: Any) -> dict[int, int]:
    """Grant this stage's characters, or raise a duplicate the way a Pact does.

    A first grant arrives as an ordinary new roster row. A duplicate raises
    Skill Boost and Luck by the stage's declared amounts, both capped at the
    client's absolute 100.0 ceiling in its own tenths.

    Returns the levels each newly granted character arrived at, for the caller
    to announce on its response.
    """
    granted: dict[int, int] = {}
    rows = userdata.get("chrdata")
    if not isinstance(rows, list):
        return granted
    by_id = {row.get("id"): row for row in rows if isinstance(row, dict)}
    for character_id in stage.character_grants:
        current = by_id.get(character_id)
        if current is None:
            row = _granted_character_row(character_id)
            rows.append(row); by_id[character_id] = row
            granted[character_id] = 1
            continue
        if stage.duplicate_grant_skill_boost:
            current["skillBoost"] = min(
                int(current.get("skillBoost", 0)) + stage.duplicate_grant_skill_boost, 1000,
            )
        if stage.duplicate_grant_luck:
            current["luck"] = min(
                int(current.get("luck", 0)) + stage.duplicate_grant_luck, 1000,
            )
    return granted


def _apply_monster_recruits(userdata: dict[str, Any], recruited: list[int]) -> dict[int, int]:
    """Ensure each accepted battle-recruited monster is on the roster.

    The reported recruits have already been checked against the stage's
    declared `monster_recruit_maxima`.  A client that rolled the recruit
    normally submits the new roster row itself, and the merged roster already
    carries it; this backstop adds the row when the report and the submitted
    roster disagree.  A duplicate recruit changes nothing: no record of a
    duplicate rule survives for these, so none is invented.

    Returns the levels each added recruit arrived at, for the caller to
    announce on its response.
    """
    granted: dict[int, int] = {}
    rows = userdata.get("chrdata")
    if not isinstance(rows, list):
        return granted
    known = {row.get("id") for row in rows if isinstance(row, dict)}
    for character_id in recruited:
        if character_id not in known:
            rows.append(_granted_character_row(character_id))
            known.add(character_id)
            granted[character_id] = 1
    return granted


# The Chapter-1100 settlement shares the Hunting grant path below and the same
# 1000-Companion box ceiling every bundled Companion policy uses.
_WORLD_MAP_SPECIAL_COMPANION_BOX = 1000

#: The client's own Companion box capacity, which a chest may not push past.
_CHEST_COMPANION_BOX = 1000
#: A chest-dropped Companion arrives at level 1, as every other drop does.
_CHEST_COMPANION_DROP_LEVEL = 1


def _award_chest_grants(userdata: dict[str, Any], slots: list[str]) -> dict[int, int]:
    """Grant the Companions and characters an authored chest awards.

    Coins and items are reconciled against the client's own submission, because
    the client folds those into the balances it sends. The other two reward
    forms have no such field: the generic story clear body carries `chrdata`,
    `itemList` and `summonList` and no Companion box at all, so nothing the
    client does can report either one back. The chest was authored by this
    server at battle start and persisted in `active_luck_result`, so it is
    granted here from what was authored rather than from what was claimed.

    Before this existed the two forms were simply dropped. A chest could show a
    Companion -- thirty-nine of them across twenty-seven stage and tier slots --
    and the clear settled Coins and items, returned 200, and kept none of it.

    Runs inside the clear's own transaction, so an exact replay returns the
    cached payload and cannot grant twice. Returns the levels each newly
    granted character arrived at, for the caller to announce, matching
    `_apply_message_grants`.
    """
    granted: dict[int, int] = {}
    companions = chest_companions(slots)
    characters = chest_characters(slots)
    if not companions and not characters:
        return granted
    rows = userdata.setdefault("chrdata", [])
    held = {row.get("id") for row in rows if isinstance(row, dict)}
    for character_id in characters:
        # A duplicate grants nothing. A Pact raises a duplicate's Skill Boost,
        # but no source says a chest did, and inventing one would be a reward
        # this project made up -- the reasoning an inbox present already uses.
        if character_id in held:
            continue
        rows.append(_granted_character_row(character_id))
        held.add(character_id)
        granted[character_id] = 1
    if not companions:
        return granted
    info = userdata.setdefault("buddyInfo", {"list": [], "record": []})
    owned = info.setdefault("list", [])
    next_id = userdata.get("nextCompanionInventoryId", max((row["iid"] for row in owned), default=0) + 1)
    for companion_id in companions:
        if len(owned) >= _CHEST_COMPANION_BOX:
            # A full box drops the remainder rather than refusing the clear:
            # the alternative strands a won battle over a reward the player
            # cannot make room for in the middle of settlement.
            break
        owned.append({
            "bid": companion_id, "lv": _CHEST_COMPANION_DROP_LEVEL, "date": 0.0,
            "iid": next_id, "exp": 0, "flag": 0, "chrID": 0,
        })
        next_id += 1
    userdata["nextCompanionInventoryId"] = next_id
    userdata["buddyInfo"] = _companion_info(owned)
    return granted


def _granted_hunting_companions(
    userdata: dict[str, Any], stage: HuntingStage | WorldMapSpecialStage, result: dict[str, Any], box_capacity: int,
) -> dict[str, Any] | None:
    """Project a Metal Zone clear's Companion drops onto the account's box.

    Returns the new Companion box, or `None` when the account's own box is
    malformed or the grant would overflow it.  The reported drops have already
    been checked against the stage's declared manifest; what is verified here is
    the box this grant is being applied to.
    """
    raw_info = userdata.get("buddyInfo", {"list": [], "record": []})
    owned = raw_info.get("list") if isinstance(raw_info, dict) else None
    if not isinstance(owned, list) or any(
        not isinstance(row, dict) or type(row.get("iid")) is not int or row["iid"] <= 0 for row in owned
    ):
        return None
    known_ids = {row["iid"] for row in owned}
    if len(known_ids) != len(owned) or len(owned) + len(result["buddies"]) > box_capacity:
        return None
    next_id = userdata.get("nextCompanionInventoryId", max(known_ids, default=0) + 1)
    if type(next_id) is not int or next_id <= max(known_ids, default=0):
        return None
    rows = copy.deepcopy(owned)
    for companion_id in result["buddies"]:
        level = stage.companion_drop_levels.get(companion_id)
        if level is None:
            return None
        rows.append({"bid": companion_id, "lv": level, "date": 0.0, "iid": next_id, "exp": 0, "flag": 0, "chrID": 0})
        next_id += 1
    userdata["nextCompanionInventoryId"] = next_id
    return _companion_info(rows)


def _draw_companion_id(draws: tuple[CompanionDraw, ...]) -> int:
    threshold = random.SystemRandom().randrange(sum(draw.weight for draw in draws))
    for draw in draws:
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


def _synchronize_wallet_projection(userdata: dict[str, Any]) -> bool:
    """Keep the client-consumed nested wallet equal to durable flat values."""
    if type(userdata.get("coins")) is not int:
        return False
    fields = (
        "energyAppStore", "energy", "energyAndApp", "freeEnergy",
        "energyGooglePlay", "coins",
    )
    values = {name: userdata.get(name, 0) for name in fields}
    if not all(type(value) is int and value >= 0 for value in values.values()) or userdata.get("valuables") == values:
        return False
    userdata["valuables"] = values
    return True


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
        message.message_id: _message_state(message)
        for message in catalog.messages
    }


def _message_grants(
    userdata: dict[str, Any], unread: list[dict[str, Any]], catalog: MessageCatalog,
) -> tuple[list[int], list[tuple[int, int]]] | None:
    """Resolve the character and Companion rewards a read is about to deliver.

    Returns the characters to add and the `(companion_id, level)` pairs to mint,
    or `None` when the account cannot receive them. Nothing is written here: a
    read that cannot deliver every reward it displays must refuse rather than
    settle the affordable half.
    """
    characters = [message["character_id"] for message in unread if message.get("character_id")]
    companions = [
        (message["companion_id"], message.get("companion_level", 1))
        for message in unread if message.get("companion_id")
    ]
    if not characters and not companions:
        return [], []
    rows = userdata.get("chrdata")
    if characters and (
        not isinstance(rows, list)
        or any(not isinstance(row, dict) for row in rows)
    ):
        return None
    if companions and _companion_box_room(userdata, len(companions), catalog.max_owned) is None:
        return None
    return characters, companions


def _companion_box_room(
    userdata: dict[str, Any], wanted: int, capacity: int,
) -> tuple[list[dict[str, Any]], int] | None:
    """Return the account's Companion box and next inventory id, if it has room."""
    raw_info = userdata.get("buddyInfo", {"list": [], "record": []})
    owned = raw_info.get("list") if isinstance(raw_info, dict) else None
    if not isinstance(owned, list) or any(
        not isinstance(row, dict) or type(row.get("iid")) is not int or row["iid"] <= 0
        for row in owned
    ):
        return None
    known = {row["iid"] for row in owned}
    if len(known) != len(owned) or len(owned) + wanted > capacity:
        return None
    next_id = userdata.get("nextCompanionInventoryId", max(known, default=0) + 1)
    if type(next_id) is not int or next_id <= max(known, default=0):
        return None
    return owned, next_id


def _apply_message_grants(
    userdata: dict[str, Any], grants: tuple[list[int], list[tuple[int, int]]],
) -> dict[int, int]:
    """Add the resolved characters and Companions to the account.

    A character the account already holds is left untouched. A Pact raises a
    duplicate's Skill Boost, but nothing records what an inbox present did with
    one, and inventing a second source of Skill Boost would be a reward this
    project made up.

    Returns the levels each newly granted character arrived at, for the caller
    to announce on its response.
    """
    granted: dict[int, int] = {}
    characters, companions = grants
    if not characters and not companions:
        # The overwhelmingly common case: an ordinary coin/item present. Return
        # before touching the account so a read that grants neither cannot
        # create a roster or a Companion box that was not already there.
        return granted
    rows = userdata.setdefault("chrdata", [])
    held = {row.get("id") for row in rows if isinstance(row, dict)}
    for character_id in characters:
        if character_id in held:
            continue
        rows.append(_granted_character_row(character_id))
        held.add(character_id)
        granted[character_id] = 1
    if not companions:
        return granted
    info = userdata.setdefault("buddyInfo", {"list": [], "record": []})
    owned = info.setdefault("list", [])
    next_id = userdata.get("nextCompanionInventoryId", max((row["iid"] for row in owned), default=0) + 1)
    for companion_id, level in companions:
        owned.append({
            "bid": companion_id, "lv": level, "date": 0.0,
            "iid": next_id, "exp": 0, "flag": 0, "chrID": 0,
        })
        next_id += 1
    userdata["nextCompanionInventoryId"] = next_id
    # `record` is a projection of `list`, not a second store, and appending to
    # one without rebuilding the other is what made a mail-granted Companion
    # invisible: it was owned, it survived a restart, and the box did not show
    # it until some later mutation happened to rebuild the box wholesale.
    # Every other grant path already returns through `_companion_info`.
    userdata["buddyInfo"] = _companion_info(owned)
    return granted


def _message_state(message: Any) -> dict[str, Any]:
    return {
        "id": message.message_id,
        "date": message.date,
        "read": False,
        "days_last": message.days_last,
        "messages": copy.deepcopy(message.texts),
        "coins": message.coins,
        "free_energy": message.free_energy,
        "items": {str(item_id): amount for item_id, amount in message.items.items()},
        "character_id": message.character_id,
        "companion_id": message.companion_id,
        "companion_level": message.companion_level,
    }


def _settle_chapter_milestone_rewards(
    account: dict[str, Any], issued_at: float | None = None, *, max_stack: int,
) -> bool:
    """Settle each earned chapter ticket once without the unproven mail UI.

    Issue 33 supplied the missing physical-client evidence: the final client
    rendered a chapter message but left its reward area empty and did not
    clear the unread state.  Keep the recovered progress/reward table, while
    treating direct inventory settlement as explicit compatibility policy.

    Existing states need a careful bridge.  An unread milestone message has
    not granted its items, so settle it here and mark it read.  A read message,
    or an issued ID whose message was deleted, was already settled by the old
    route and must never grant again.  New milestones are recorded as read
    messages so the existing issued/read state remains the durable ledger.
    """
    messages = account.setdefault("messages", {})
    issued = account.setdefault("chapter_milestones_issued", [])
    userdata = account.get("userdata", {})
    progress = userdata.get("progressCode", 0)
    eligible = eligible_chapter_messages(
        progress, time.time() if issued_at is None else issued_at,
    )
    items = userdata.get("itemList")
    if (
        not isinstance(items, list)
        or any(type(value) is not int or value < 0 for value in items)
        or any(item_id < 1 or item_id > len(items) for message in eligible for item_id in message.items)
    ):
        return False
    eligible_ids = {message.message_id for message in eligible}
    changed = False

    # Saves predating the sentinel may already contain read or unread milestone
    # messages. Adopt those IDs before backfilling so an upgrade cannot issue a
    # second copy of an earlier reward.
    for message_id in sorted(eligible_ids.intersection(messages)):
        if message_id not in issued:
            issued.append(message_id)
            changed = True
    for message in eligible:
        state = messages.get(message.message_id)
        if message.message_id not in issued:
            state = _message_state(message)
            messages[message.message_id] = state
            issued.append(message.message_id)
            changed = True
        if state is None or state.get("read"):
            continue
        updated_items = list(userdata["itemList"])
        for item_id, amount in message.items.items():
            updated_items[item_id - 1] = min(
                max_stack, updated_items[item_id - 1] + amount,
            )
        userdata["itemList"] = updated_items
        state["read"] = True
        changed = True
    if changed:
        issued.sort()
    return changed


def _synchronize_login_bonus_messages(account: dict[str, Any], now: float) -> bool:
    """Issue at most one retail login-bonus set for the current UTC day."""
    if type(now) not in {int, float} or not math.isfinite(now) or now < 0:
        return False
    utc_day = int(now) // 86_400
    last_day = account.setdefault("login_bonus_last_utc_day", None)
    if last_day is not None and utc_day <= last_day:
        return False

    consecutive = account.setdefault("login_bonus_consecutive_days", 0)
    total = account.setdefault("login_bonus_total_days", 0)
    consecutive = consecutive + 1 if last_day is not None and utc_day == last_day + 1 else 1
    total += 1
    messages = account.setdefault("messages", {})
    for message in login_bonus_messages(consecutive, total, now):
        messages[message.message_id] = _message_state(message)
    account["login_bonus_last_utc_day"] = utc_day
    account["login_bonus_consecutive_days"] = consecutive
    account["login_bonus_total_days"] = total
    return True


def _restock_exchange_week(account: dict[str, Any], catalog: ExchangeCatalog) -> dict[int, Any]:
    """Open the current week's offers, restocking when the rotation turns over.

    The Trading Post restocked every Friday.  Stock is per account, so the turn
    is detected by comparing the week the account last saw against the week that
    is open now; a catalog without weeks never turns over and keeps its stock.
    """
    week = active_week_index(time.time(), catalog.week_count())
    offers = catalog.offers_open_at(week)
    if catalog.weeks and account.get("exchange_week") != week:
        account["exchange_week"] = week
        account["exchange_remaining"] = {str(offer.offer_id): offer.initial_count for offer in offers.values()}
    else:
        account.setdefault("exchange_remaining", _initial_exchange_remaining(catalog))
    return offers


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


#: The client packs a reward identity and its count into one integer.
#: ``ItemCode``/``ItemCode2`` both construct from ``(id << 16) | count`` --
#: recovered from ``.ctor(int _id, int _num)``, whose whole body is
#: ``orr w8, w19, w20, lsl #16``, and read back by ``get_id`` (``asr #16``)
#: and ``get_count`` (a halfword load).
_ITEM_CODE_SHIFT = 16
_ITEM_CODE_COUNT_MASK = 0xFFFF


def _packed_item_code(identity: int, count: int) -> int:
    """Encode one reward the way the client's own ItemCode constructor does."""
    return (int(identity) << _ITEM_CODE_SHIFT) | (int(count) & _ITEM_CODE_COUNT_MASK)


def _message_wire(message: dict[str, Any], original_shape: bool = False) -> dict[str, Any]:
    """Project one inbox message for the client's mail screen.

    ``original_shape`` serves the shape recovered from the client's own
    ``Message`` constructor, which every launcher now asks for.  Without it a
    present displays no reward at all: the client reads Coins, Energy, the
    character, the items, the Summon and the Companion out of one ``gifts``
    entry and never looks at the top-level fields this server sent before, so
    ``get_hasGift`` answered false and the mail screen drew its plain "message"
    presentation over a present that really did carry something.

    The keys were read out of the binary rather than inferred, by resolving the
    constructor's own literals through the GOT entries that supply them.
    ``gifts`` is indexed by integer; inside an entry ``coins``, ``energy``,
    ``chr``, ``summon`` and ``title`` are scalars, ``item`` is another
    integer-indexed array of ``{id, num}`` pairs, and ``buddy`` is one such
    pair.  ``title`` lands on the client's ``multiplayTitle``.

    Two fields look like something they are not, and each one hung the client
    outright when served the obvious way.  ``date`` is a ``long`` on the class
    but must travel as a JSON real, because the constructor reads it through
    LitJson's ``(double)`` conversion.  ``messages`` is an object read by the
    keys ``default``/``ja``/``en``, even though the fields behind it are named
    ``mes_default``/``mes_ja``/``mes_en`` and none of those names is a literal
    anywhere in the client.  Getting either wrong throws out of
    ``Message..ctor``, and that exception kills the login callback: the client
    then sits on ``Connecting...`` with no error dialog at all.
    """
    if not original_shape:
        return {
            "id": message["id"], "date": float(message["date"]), "read": bool(message["read"]), "daysLast": int(message["days_last"]),
            "gifts": [], "coins": int(message["coins"]), "energy": int(message["free_energy"]),
            "chr": int(message.get("character_id", 0)),
            "item": [{"id": int(item_id), "num": amount} for item_id, amount in sorted(message["items"].items(), key=lambda value: int(value[0]))],
            # Summon and title stay zero: no owner is modeled for either, so a
            # nonzero value would render a reward the read could not deliver.
            "summon": 0, "buddy": int(message.get("companion_id", 0)), "title": 0,
            "messages": copy.deepcopy(message["messages"]),
        }
    texts = message["messages"]
    companion_id = int(message.get("companion_id", 0))
    return {
        # `date` stays a JSON real. The field is a `long`, which is what made an
        # integer look right, but the constructor reads it through LitJson's
        # `(double)` conversion, and that refuses a JsonData holding an int.
        "id": message["id"], "date": float(message["date"]),
        "read": bool(message["read"]), "daysLast": int(message["days_last"]),
        # Every reward the client reads lives in one `gifts` entry. The
        # constructor never looks at a top-level `coins`, `energy`, `chr`,
        # `item`, `buddy`, `summon` or `title` -- which is why a present
        # carrying 500 Coins still answered `get_hasGift` false and drew the
        # plain "message" title instead of the gift one. Recovered by resolving
        # the constructor's own key literals through the GOT relocations that
        # supply them: `gifts` is indexed by integer, and inside an entry
        # `item` is another integer-indexed array of `{id, num}` while `buddy`
        # is one such pair.
        "gifts": [{
            "coins": int(message["coins"]),
            "energy": int(message["free_energy"]),
            "chr": int(message.get("character_id", 0)),
            "item": [
                {"id": int(item_id), "num": amount}
                for item_id, amount in sorted(message["items"].items(), key=lambda value: int(value[0]))
            ],
            # Summon stays zero for the reason it always has: no owner is
            # modeled, so a nonzero value would render a reward the read could
            # not deliver. `title` lands on `multiplayTitle`, which has no
            # owner modeled here either.
            "summon": 0,
            "buddy": {"id": companion_id, "num": 1 if companion_id else 0},
            "title": 0,
        }],
        # An object, read with exactly these three keys.
        "messages": copy.deepcopy(texts),
    }


#: The read-messages callback opens with `if (json.Contains("result"))` and
#: then *rebinds* its receiver to `json["result"]`, so every field it goes on to
#: read -- the six wallet values, `buddyInfo`, `chrdata`, `itemList`,
#: `summonList`, `achivementFlags`, `multiplayData` and `readlist` -- is looked
#: up inside that object rather than beside it. Answering `result: true` with
#: those fields alongside it therefore called `Contains` on a boolean and threw
#: `InvalidOperationException: Instance of JsonData is not a dictionary`, which
#: killed the callback before a single reward reached the client. Each field is
#: individually guarded, so the object may carry only what this server models.
#: The delete route is not nested this way: its callback reads `deletelist`
#: straight off the root, unguarded.
#: What the client's generic `callAPI` wrapper reads off *every* response
#: before it ever reaches the endpoint's own callback: `success`, `digest`,
#: `lastupdate`, and -- on the paths that take them -- `errorCode`/`cmdError`.
#: It indexes them without guarding, so a response missing one raises
#: `KeyNotFoundException` inside `callAPI` and the callback never runs at all.
#: `digest` is added by signing; the other two travel here. Every other
#: mutation already carried them, which is why only the mail routes, whose
#: replies said `result` and nothing else, were losing their callback.
_API_ENVELOPE_FIELDS = {"success": True, "lastupdate": 1.0}


def _message_reload_projection(
    userdata: dict[str, Any], account: dict[str, Any], granted: dict[int, int] | None = None,
) -> dict[str, Any]:
    buddy_info = userdata.get("buddyInfo", {"list": [], "record": []})
    return {
        "chrdata": _announced_roster(userdata.get("chrdata", []), granted or {}), "buddyInfo": copy.deepcopy(buddy_info),
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


def _bounded_special_result_matches(
    userdata: dict[str, Any], clear: dict[str, Any], max_exp: int,
) -> bool:
    """Require a Chapter 1100 clear to grant nothing unrecovered.

    It is a real level-90 battle, so its own experience is permitted up to
    ``max_exp`` and with it the roster the client reports back, and its
    Companion channel is left to `world_map_special_companions_within_bounds`,
    which accepts it against the stage's own recovered manifest.

    Every other channel is refused rather than trusted, because this chapter's
    chests are labeled local policy and its remaining rewards were never
    recovered: accepting a Coin, item, monster, Summon, or Lucky enemy here
    would author state the record does not carry.  Counter Descent took the
    same shape until a real clear proved the client reports all of it; that
    family now settles through `_projected_event_items` instead.
    """
    result = clear["battle_result"]
    return (
        result["coins"] == 0
        and result["exp"] <= max_exp
        and result["items"] == {}
        and result["monsters"] == []
        and result["summons"] == []
        and result["luckynum"] == 0
        and result["boostup"] == [0] * 6
        and clear["itemList"] == userdata.get("itemList")
        and clear["summonList"] == userdata.get("summonList")
    )


def _eidolon_summon_projection(
    userdata: dict[str, Any], clear: dict[str, Any], allowed: tuple[int, ...],
) -> list[int] | None:
    """Validate and durably project the final client's result-screen grant.

    ``summonList`` is serialized before the result screen processes drops, so
    it must match the server's current 16-slot raw-data vector. The battle
    result may report no drop or one allowed, previously unowned Summon. The
    result screen constructs a new ``SummonInfo(id, 1, 0)``, whose raw value is
    exactly 1; the clear callback does not consume a returned summonList.
    """
    current = userdata.get("summonList")
    submitted = clear["summonList"]
    reported = clear["battle_result"]["summons"]
    if (
        not isinstance(current, list)
        or len(current) != 16
        or any(type(value) is not int or value < 0 for value in current)
        or submitted != current
        or len(reported) > 1
        or any(summon_id not in allowed for summon_id in reported)
        or any(current[summon_id - 1] != 0 for summon_id in reported)
    ):
        return None
    projected = list(current)
    for summon_id in reported:
        projected[summon_id - 1] = 1
    return projected


def _settlement_matches(
    userdata: dict[str, Any], clear: dict[str, Any], identity: tuple[int, int],
    catalog: SettlementCatalog, extra_item_rewards: dict[int, int] | None = None,
) -> bool:
    """Check a clear against its declared rewards, plus any chest this battle
    was handed at start. The chest is not in the catalog and never can be: the
    server authored it per battle, so it is passed in rather than looked up."""
    rule = catalog.rules.get(identity)
    current = userdata.get("chrdata", [])
    submitted = clear["chrdata"]
    if not (rule and isinstance(current, list) and all(isinstance(row, dict) and type(row.get("id")) is int for row in current) and all(isinstance(row, dict) and type(row.get("id")) is int for row in submitted)):
        return False
    current_ids = {row["id"] for row in current}
    submitted_ids = {row["id"] for row in submitted}
    if len(submitted_ids) != len(submitted) or not current_ids <= submitted_ids or submitted_ids - current_ids != rule.character_rewards or not submitted_ids <= catalog.character_ids:
        return False
    item_rewards = dict(rule.item_rewards)
    for item_id, count in (extra_item_rewards or {}).items():
        item_rewards[item_id] = item_rewards.get(item_id, 0) + count
    return _projected_list(userdata.get("itemList", []), clear["itemList"], item_rewards, catalog.item_slots, catalog.max_stack) and _projected_list(userdata.get("summonList", []), clear["summonList"], rule.summon_rewards, catalog.summon_slots, catalog.max_stack)


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


def _outcome_buddy_info(userdata: dict[str, Any], clear: dict[str, Any], identity: tuple[int, int], catalog: StoryOutcomeCatalog, clear_state_catalog: ClearStateCatalog | None = None, strict: bool = False) -> dict[str, list[dict[str, Any]]] | None:
    """Author local Companion rows, bounded by the stage's recovered ceiling.

    The Companion ceiling is always enforced, and it is the one ceiling that is
    completely evidenced: every stage carries its own
    ``BattleData.Section.dropBuddies`` allowlist inside the client.  A roll above
    it, or naming a Companion the stage does not declare, is refused.

    ``strict`` additionally bounds the reported items, recruited monsters, and
    Summons.  It is off by default because those two ceilings come from joining
    an encounter map to ``EnemyData``, and no encounter map reaches every stage:
    the chapters whose enemy rows the client never shipped have none, and neither
    do the archived event chapters.  Enforcing a ceiling nobody could recover
    refuses ordinary play, so the default leaves those outcomes exactly as
    unconstrained as they are when no catalog is supplied at all.

    Where strictness *is* asked for, it applies per stage rather than per server:
    `StoryOutcomeRule` records whether a source could speak to each stage's item
    and character outcome, so a joined stage whose enemies genuinely carry
    nothing still refuses a reported item, while an unjoinable one does not.

    One clause is deliberately absent from the strict roster check: that the
    durable roster be a subset of the submitted one.  `_preserved_roster`
    documents why the two legitimately diverge -- the server can hold a character
    the client has not read back yet, from a Pact draw whose response never
    arrived or an event, achievement, or message grant -- and refusing a clear
    over that lag says nothing about the outcome being reported.
    """
    rule = catalog.rules.get(identity)
    result = clear["battle_result"]
    current_rows = userdata.get("chrdata")
    submitted_rows = clear["chrdata"]
    if rule is None:
        return None
    if strict:
        if not isinstance(current_rows, list) or any(not _valid_generic_character_record(row) or row["id"] not in catalog.character_ids for row in current_rows):
            return None
        current_ids = {row["id"] for row in current_rows}
        submitted_ids = {row["id"] for row in submitted_rows}
        if len(current_ids) != len(current_rows) or not submitted_ids <= catalog.character_ids:
            return None
        new_ids = submitted_ids - current_ids
        reported_monsters = Counter(result["monsters"])
        reported_new = Counter({character_id: count for character_id, count in reported_monsters.items() if character_id not in current_ids})
        reported_duplicates = reported_monsters - reported_new
        if Counter(new_ids) != reported_new or (reported_duplicates and clear_state_catalog is None):
            return None
        if rule.character_evidence and not outcome_allowed(reported_monsters, rule.character_maxima):
            return None
        reported_items = Counter({int(item_id): count for item_id, count in result["items"].items()})
        if rule.item_evidence and (not outcome_allowed(reported_items, rule.item_maxima) or not _projected_list(userdata.get("itemList", []), clear["itemList"], dict(reported_items), catalog.item_slots, catalog.max_stack)):
            return None
        # No recovered source states a per-stage Summon outcome, so strict mode
        # permits none rather than inventing a ceiling for them.
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


def _retarget_party(userdata: dict[str, Any], removed_id: int, replacement_id: int) -> None:
    """Point every party slot naming a departing character somewhere valid.

    A character can leave the roster while still being in the party -- Rebirth
    transforms one into another.  Leaving the old id behind makes the account's
    own party fail the membership check on the next save, so the slot follows
    the transformation or empties.
    """
    for name in ("teamMembers", "teamMembers_VS"):
        members = userdata.get(name)
        if not isinstance(members, list):
            continue
        for index, member in enumerate(members):
            if member == removed_id:
                members[index] = replacement_id


def _same_roster_membership(current: object, submitted: object) -> bool:
    """Whether two rosters name exactly the same characters.

    Used where a clear may advance levels but must not add or lose anyone.
    """
    def identities(rows: object) -> set[int] | None:
        if not isinstance(rows, list):
            return None
        found: set[int] = set()
        for row in rows:
            if not isinstance(row, dict) or type(row.get("id")) is not int:
                return None
            found.add(row["id"])
        return found

    held, reported = identities(current), identities(submitted)
    return held is not None and held == reported


def _preserved_roster(current: object, submitted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Settle a clear's roster without dropping a character the client omitted.

    The submitted roster is the client's own view plus the battle's progression,
    so it is authoritative for every character it names.  It is *not* evidence
    that a character the server holds was lost: nothing removes a character at
    clear time, so an id present only in the durable roster is a grant the
    client had not read back yet — a Pact draw whose response never reached it,
    an event character, an achievement or message reward — and replacing the
    roster wholesale would delete it.

    When a settlement, clear-state, or outcome catalog validates the clear this
    is exactly an identity: each of them already requires the submitted ids to
    be a superset of the durable ones.  It is the unvalidated configuration the
    public tester actually runs that needs it.
    """
    held: dict[int, dict[str, Any]] = {}
    if isinstance(current, list):
        held = {
            row["id"]: row for row in current
            if isinstance(row, dict) and type(row.get("id")) is int
        }
    rows = [
        copy.deepcopy(row) if not isinstance(row, dict) or held.get(row.get("id")) is None
        else _preserved_progress(held[row["id"]], row)
        for row in submitted
    ]
    known = {row["id"] for row in rows if isinstance(row, dict) and type(row.get("id")) is int}
    for character_id, row in held.items():
        if character_id not in known:
            rows.append(copy.deepcopy(row))
    return rows


def _preserved_progress(held: dict[str, Any], reported: dict[str, Any]) -> dict[str, Any]:
    """Keep the progression a stale client would otherwise roll back.

    Preserving a whole character is not enough on its own: a client that is
    stale about a character it *does* know still reports that character's older
    level, skill boost, and Luck, and taking its row wholesale undoes a gain the
    server had already committed.  The final client is also confirmed to omit
    the optional ``luck`` member from a valid clear.  Job experience, skill
    boost, and Luck only ever accumulate — every spend has its own route — so
    the larger of the two values is the true one.  Everything else (active job,
    equipped slots, flags) is a player choice that legitimately moves in either
    direction, and stays client-authoritative.
    """
    merged = copy.deepcopy(reported)
    levels, reported_levels = held.get("jobLevels"), merged.get("jobLevels")
    if isinstance(levels, list) and isinstance(reported_levels, list) and len(levels) == len(reported_levels):
        merged["jobLevels"] = [
            max(kept, told) if type(kept) in {int, float} and type(told) in {int, float} else told
            for kept, told in zip(levels, reported_levels)
        ]
    if type(held.get("skillBoost")) is int and type(merged.get("skillBoost")) is int:
        merged["skillBoost"] = max(held["skillBoost"], merged["skillBoost"])
    if type(held.get("luck")) is int:
        reported_luck = merged.get("luck")
        merged["luck"] = (
            max(held["luck"], reported_luck)
            if type(reported_luck) is int else held["luck"]
        )
    return merged


def _preserved_counts(current: object, submitted: list[int]) -> list[int]:
    """Settle a clear's item/summon slots without dropping a server-side grant.

    These are fixed-length count-per-slot arrays, not owned-id lists.  Every
    decrease is applied through its own route (`use_statusup_item`, `exchange`,
    `rebirth`), so the durable count is already current and a client only ever
    reports its base plus this battle's drops.  A submitted count *below* the
    durable one therefore means the client's base was stale, not that the items
    were spent, and taking it would silently destroy the grant it had not read.

    As above this is an identity under a validating catalog, whose
    `_projected_list` requires the submission to equal the durable counts plus
    the declared rewards.
    """
    if not isinstance(current, list) or len(current) != len(submitted):
        return list(submitted)
    return [
        max(held, reported) if type(held) is int and type(reported) is int else reported
        for held, reported in zip(current, submitted)
    ]


def _count_projection(current: object, submitted: object, rewards: dict[int, int], slots: int, maximum: int) -> list[int] | None:
    """Return the one count-per-slot array a clear reporting ``rewards`` may submit.

    ``None`` means the submission is not that array, which is the refusal every
    caller wants; the accepted array is returned rather than a bare `True` so a
    settlement can persist the server's own projection instead of re-deriving it
    from the client's word.
    """
    if not (isinstance(current, list) and isinstance(submitted, list) and len(current) == slots and len(submitted) == slots and all(type(value) is int and 0 <= value <= maximum for value in current)):
        return None
    expected = list(current)
    for item_id, count in rewards.items():
        if item_id > slots:
            return None
        expected[item_id - 1] = min(maximum, expected[item_id - 1] + count)
    return expected if submitted == expected else None


def _projected_list(current: object, submitted: object, rewards: dict[int, int], slots: int, maximum: int) -> bool:
    return _count_projection(current, submitted, rewards, slots, maximum) is not None


def _projected_event_items(
    userdata: dict[str, Any], clear: dict[str, Any], chest: dict[int, int],
) -> list[int] | None:
    """Return the server-owned inventory for a client-reported event clear.

    Counter Descent has no recovered reward table and the result service that
    would have authored one is gone, so the surviving client's own report is the
    only account of what a won battle paid.  This settles it exactly as
    `apply_hunting_clear` settles a Hunting result: the report is trusted, but
    the inventory accompanying it must be the durable counts plus the drops it
    declares, capped at the client's stack ceiling, so the item array cannot
    become a grant channel beside the drops.  The chest the start authored is
    added to those drops because the client folds it into the same array and
    never reports it in `battle_result`; see `apply_generic_story_clear`.

    The earlier policy required the family to grant *nothing*, taken while its
    clear callback was unobserved.  A won Chapter 8000 battle reports its own
    experience, Coins, and drops, so that policy refused every real clear -- and
    because a refusal leaves the battle open, the client retried the settlement
    it could never complete and stranded the player on the reward screen.

    Two channels stay refused for want of anything that could author them:
    Summons, which no recovered source states a per-stage outcome for, and a
    durable inventory that is not the client's own 181-slot shape.  Experience,
    Skill Boost, recruited monsters, and Lucky enemies need no authoring here --
    they reach the roster through the same trusted merge every story and event
    clear already uses, and a story-outcome catalog bounds them when the
    operator asks for one.
    """
    result = clear["battle_result"]
    if result["summons"] or clear["summonList"] != userdata.get("summonList"):
        return None
    gains = {int(item_id): count for item_id, count in result["items"].items()}
    for item_id, count in chest.items():
        gains[item_id] = gains.get(item_id, 0) + count
    return _count_projection(
        userdata.get("itemList"), clear["itemList"], gains,
        BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK,
    )


def _projected_hunting_items(
    current: object,
    submitted: object,
    rewards: dict[int, int],
    stage: HuntingStage,
    ticket_spent: bool | None,
    slots: int,
    maximum: int,
) -> list[int] | None:
    """Return the server-owned Hunting item projection, if the clear matches.

    The final client repeats its pre-entry Item 50 count when clearing a Metal
    battle. The server has already committed that ticket spend at start, so an
    exact clear can differ by the one entry ticket in that slot only. New starts
    retain whether a ticket was actually spent; ``None`` is limited to an
    already-active battle loaded from a pre-fix save. In every accepted case the
    returned inventory keeps the server's lower, already-charged ticket count.
    """
    if not (
        isinstance(current, list)
        and isinstance(submitted, list)
        and len(current) == slots
        and len(submitted) == slots
        and all(type(value) is int and 0 <= value <= maximum for value in current)
    ):
        return None
    expected = list(current)
    for item_id, count in rewards.items():
        if item_id > slots:
            return None
        expected[item_id - 1] = min(maximum, expected[item_id - 1] + count)
    if submitted == expected:
        return expected
    if not stage.ticket_optional or ticket_spent is False:
        return None
    ticket_index = stage.entry_item_id - 1
    repeated_pre_entry = list(expected)
    repeated_pre_entry[ticket_index] += stage.entry_item_count
    if repeated_pre_entry[ticket_index] > maximum or submitted != repeated_pre_entry:
        return None
    return expected


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
    parser.add_argument("--public-data-root", type=Path, help="user-local derived UI and resource payloads")
    parser.add_argument("--story-catalog", type=Path, help="user-local normalized generic-story catalog")
    parser.add_argument("--story-progression-catalog", type=Path, help="user-derived reviewed core-story progression catalog")
    parser.add_argument("--core-story", action="store_true", help="enable the bundled ordinary Chapter 2--42 progression policy without reward data")
    parser.add_argument("--settlement-catalog", type=Path, help="optional user-local generic-story identity/reward constraints")
    parser.add_argument("--story-outcome-catalog", type=Path, help="user-local generic-story reported-outcome bounds and Companion drop levels")
    parser.add_argument("--outcome-strict", action="store_true", help="audit client-reported outcomes against available story and Hunting reward catalogs instead of trusting structurally valid active-battle results")
    parser.add_argument("--clear-state-catalog", type=Path, help="user-local generic-story character EXP and Skill-Boost constraints")
    parser.add_argument("--statusup-catalog", type=Path, help="user-local item/character rules for status-up progression")
    parser.add_argument("--job-catalog", type=Path, help="user-local ordered job-unlock costs")
    parser.add_argument("--rebirth-catalog", type=Path, help="user-local Rebirth recipe and Joker policy")
    parser.add_argument("--summon-skill-catalog", type=Path, help="user-local archival Eidolon skill costs for the retired enhancement route")
    parser.add_argument("--companion-catalog", type=Path, help="user-local Companion master values for ownership mutations")
    parser.add_argument("--companion-equipment-catalog", type=Path, help="user-derived character-family and species restrictions for Companion equipment")
    parser.add_argument("--companion-strengthen-catalog", type=Path, help="user-local Companion progression values and bonus policy")
    parser.add_argument("--companion-evolution-catalog", type=Path, help="user-local Companion evolution rows and costs")
    parser.add_argument("--companion-draw-catalog", type=Path, help="user-local Companion draw pool and costs")
    parser.add_argument("--pact-draw-catalog", type=Path, help="user-local ordinary Pact pool, rates, and duplicate policy")
    parser.add_argument("--event-catalog", type=Path, help="user-local event stages, flags, and character grants")
    parser.add_argument("--character-catalog", type=Path, help="matching user-derived character catalog for local event grants")
    parser.add_argument("--pacts", action="store_true", help="enable the bundled local Fellowship and Truth Pact policy")
    parser.add_argument("--hunting-catalog", type=Path, help="user-local Hunting stage catalog; cannot be combined with --hunting")
    parser.add_argument("--hunting", action="store_true", help="enable the bundled local Pudding/Tin/Coin Creeps/Puppet Hunting policy")
    parser.add_argument("--daily-quests", action="store_true", help="enable the fourteen recovered Daily Quest stages with bounded local settlement")
    parser.add_argument("--secondary-worlds", action="store_true", help="enable the BreaSoul and Five Emperors secondary world maps with bounded local settlement")
    parser.add_argument("--no-interpolated-luck-pools", action="store_true", help="roll chests only for the thirty story stages the community record documents, instead of also donating a nearby documented chapter's pools to the rest")
    parser.add_argument("--luck-pool-catalog", type=Path, help="operator-supplied Luck Treasure Chest pools for stages the community record does not document; see liminal_gate/luck_pool_catalog.py")
    parser.add_argument("--cavern-forest", action="store_true", help="enable Orbling Cavern and Cryptid Forest, the two standing World 1 areas, with bounded local settlement")
    parser.add_argument("--jobs", action="store_true", help="enable the bundled local job-unlock cost policy")
    parser.add_argument("--rebirth", action="store_true", help="enable the bundled local Rebirth recipe policy")
    parser.add_argument("--status-items", action="store_true", help="enable the bundled local status-up item policy")
    parser.add_argument("--companion-draw", action="store_true", help="enable the bundled local Companion draw pool and costs")
    parser.add_argument("--companion-sale", action="store_true", help="enable the bundled local Companion sale values")
    parser.add_argument("--drop-eligibility", action="store_true", help="send the bundled login drop-eligibility allowlist so the client keeps the drops it rolls")
    parser.add_argument("--achievements", action="store_true", help="enable the bundled local clear-chapter achievement policy")
    parser.add_argument("--summon-skills", action="store_true", help="enable the bundled archival Eidolon skill costs for the retired enhancement route")
    parser.add_argument("--companion-strengthen", action="store_true", help="enable the bundled local Companion strengthen progression")
    parser.add_argument("--companion-evolution", action="store_true", help="enable the bundled local Companion evolution recipes")
    parser.add_argument("--trading-post", action="store_true", help="enable the bundled local Trading Post offers")
    parser.add_argument("--enable-stamina", action="store_true", help="charge the client's own stamina meter for quest entry instead of pinning it full")
    parser.add_argument("--original-mail-shape", action="store_true", help="serve inbox messages in the field shape recovered from the client's own Message class, so presents render their text and rewards")
    parser.add_argument("--achievement-catalog", type=Path, help="user-local clear-chapter achievement thresholds and rewards")
    parser.add_argument("--message-catalog", type=Path, help="user-local inbox messages and bounded local rewards")
    parser.add_argument("--exchange-catalog", type=Path, help="user-local Trading Post offers and bounded settlements")
    return parser.parse_args()


def load_launch_config(args: argparse.Namespace) -> ServerConfig:
    value_fields = (
        "profile", "state_file", "host", "port", "event_log", "resource_root", "resource_manifest", "public_data_root",
        "story_catalog", "story_progression_catalog", "settlement_catalog", "story_outcome_catalog", "clear_state_catalog", "statusup_catalog", "job_catalog",
        "rebirth_catalog", "summon_skill_catalog", "companion_catalog", "companion_equipment_catalog", "companion_strengthen_catalog",
        "companion_evolution_catalog", "companion_draw_catalog", "pact_draw_catalog", "event_catalog", "character_catalog", "hunting_catalog",
        "achievement_catalog", "message_catalog", "exchange_catalog",
        "luck_pool_catalog",
    )
    flag_fields = (
        "core_story", "pacts", "hunting", "daily_quests", "secondary_worlds", "cavern_forest", "no_interpolated_luck_pools", "jobs", "rebirth", "status_items",
        "companion_draw", "companion_sale", "companion_strengthen",
        "companion_evolution", "trading_post", "drop_eligibility",
        "achievements", "summon_skills", "outcome_strict", "enable_stamina",
        "original_mail_shape",
    )
    if args.config is not None:
        if (
            any(getattr(args, field, None) is not None for field in value_fields)
            or any(getattr(args, field, False) for field in flag_fields)
        ):
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
        story_outcome_catalog=args.story_outcome_catalog, outcome_strict=getattr(args, "outcome_strict", False),
        clear_state_catalog=args.clear_state_catalog, statusup_catalog=args.statusup_catalog,
        job_catalog=args.job_catalog, rebirth_catalog=args.rebirth_catalog,
        summon_skill_catalog=args.summon_skill_catalog, companion_catalog=args.companion_catalog,
        companion_equipment_catalog=getattr(args, "companion_equipment_catalog", None),
        companion_strengthen_catalog=args.companion_strengthen_catalog,
        companion_evolution_catalog=args.companion_evolution_catalog,
        companion_draw_catalog=args.companion_draw_catalog, pact_draw_catalog=args.pact_draw_catalog, pacts=getattr(args, "pacts", False),
        event_catalog=args.event_catalog, character_catalog=args.character_catalog,
        drop_eligibility=getattr(args, 'drop_eligibility', False),
        hunting_catalog=args.hunting_catalog, hunting=getattr(args, 'hunting', False),
        daily_quests=getattr(args, 'daily_quests', False),
        secondary_worlds=getattr(args, 'secondary_worlds', False),
        cavern_forest=getattr(args, 'cavern_forest', False),
        no_interpolated_luck_pools=getattr(args, 'no_interpolated_luck_pools', False),
        jobs=getattr(args, 'jobs', False),
        rebirth=getattr(args, 'rebirth', False),
        status_items=getattr(args, 'status_items', False),
        companion_draw=getattr(args, 'companion_draw', False),
        companion_sale=getattr(args, 'companion_sale', False),
        companion_strengthen=getattr(args, 'companion_strengthen', False),
        companion_evolution=getattr(args, 'companion_evolution', False),
        trading_post=getattr(args, 'trading_post', False),
        achievement_catalog=args.achievement_catalog, achievements=getattr(args, 'achievements', False),
        summon_skills=getattr(args, 'summon_skills', False),
        enable_stamina=getattr(args, 'enable_stamina', False),
        original_mail_shape=getattr(args, 'original_mail_shape', False),
        message_catalog=args.message_catalog,
        exchange_catalog=args.exchange_catalog,
    )


def build_server(
    args: ServerConfig,
    *,
    resource_catalog: ResourceCatalog | None = None,
    build_id: str = "development",
) -> BootstrapServer:
    """Construct the compatibility server for either CLI or embedded hosts.

    This deliberately performs the same catalog/policy validation as the CLI;
    an Android host may only replace the resource source with its already-opened
    APK-backed catalog and must not gain a separate gameplay configuration.
    """
    resources = resource_catalog
    try:
        if (args.resource_root is None) != (args.resource_manifest is None):
            raise ProfileError("--resource-root and --resource-manifest must be supplied together")
        if resources is None and args.resource_root is not None:
            resources = load_resource_catalog(args.resource_manifest, args.resource_root)
        stories = None if args.story_catalog is None else load_story_catalog(args.story_catalog)
        if args.core_story and args.story_progression_catalog is not None:
            raise ProfileError("--core-story cannot be combined with --story-progression-catalog")
        progression = build_core_story_policy() if args.core_story else (None if args.story_progression_catalog is None else load_story_progression_catalog(args.story_progression_catalog))
        if stories is not None and progression is not None:
            raise ProfileError("--story-catalog and --story-progression-catalog cannot be combined")
        settlements = None if args.settlement_catalog is None else load_settlement_catalog(args.settlement_catalog)
        story_outcomes = None if args.story_outcome_catalog is None else load_story_outcome_catalog(args.story_outcome_catalog)
        clear_states = None if args.clear_state_catalog is None else load_clear_state_catalog(args.clear_state_catalog)
        if args.status_items and args.statusup_catalog is not None:
            raise ProfileError("--status-items cannot be combined with --statusup-catalog")
        statusup = build_bundled_statusup_policy() if args.status_items else (None if args.statusup_catalog is None else load_statusup_catalog(args.statusup_catalog))
        if args.jobs and args.job_catalog is not None:
            raise ProfileError("--jobs cannot be combined with --job-catalog")
        jobs = build_bundled_job_policy() if args.jobs else (None if args.job_catalog is None else load_job_catalog(args.job_catalog))
        if args.rebirth and args.rebirth_catalog is not None:
            raise ProfileError("--rebirth cannot be combined with --rebirth-catalog")
        rebirths = build_bundled_rebirth_policy() if args.rebirth else (None if args.rebirth_catalog is None else load_rebirth_catalog(args.rebirth_catalog))
        if args.summon_skills and args.summon_skill_catalog is not None:
            raise ProfileError("--summon-skills cannot be combined with --summon-skill-catalog")
        summon_skills = build_bundled_summon_skill_policy() if args.summon_skills else (None if args.summon_skill_catalog is None else load_summon_skill_catalog(args.summon_skill_catalog))
        if args.companion_sale and args.companion_catalog is not None:
            raise ProfileError("--companion-sale cannot be combined with --companion-catalog")
        companions = build_bundled_companion_policy() if args.companion_sale else (None if args.companion_catalog is None else load_companion_catalog(args.companion_catalog))
        companion_equipment = (
            None
            if args.companion_equipment_catalog is None
            else load_companion_equipment_catalog(args.companion_equipment_catalog)
        )
        if args.companion_strengthen and args.companion_strengthen_catalog is not None:
            raise ProfileError("--companion-strengthen cannot be combined with --companion-strengthen-catalog")
        companion_strengthen = build_bundled_companion_strengthen_policy() if args.companion_strengthen else (None if args.companion_strengthen_catalog is None else load_companion_strengthen_catalog(args.companion_strengthen_catalog))
        if args.companion_evolution and args.companion_evolution_catalog is not None:
            raise ProfileError("--companion-evolution cannot be combined with --companion-evolution-catalog")
        companion_evolution = build_bundled_companion_evolution_policy() if args.companion_evolution else (None if args.companion_evolution_catalog is None else load_companion_evolution_catalog(args.companion_evolution_catalog))
        if args.companion_draw and args.companion_draw_catalog is not None:
            raise ProfileError("--companion-draw cannot be combined with --companion-draw-catalog")
        companion_draw = build_bundled_companion_draw_policy() if args.companion_draw else (None if args.companion_draw_catalog is None else load_companion_draw_catalog(args.companion_draw_catalog))
        if args.pacts and args.pact_draw_catalog is not None:
            raise ProfileError("--pacts cannot be combined with --pact-draw-catalog")
        # Rarity comes from the operator's own catalog when one was supplied,
        # which is what lets duplicate gains and Truth rates follow the class
        # bands instead of a flat uniform default.
        pact_rarity = load_character_rarity(args.character_catalog) if args.pacts and args.character_catalog is not None else None
        if pact_rarity is not None:
            validate_bundled_pools(pact_rarity)
        pact_draw = build_bundled_pact_policy(pact_rarity) if args.pacts else (None if args.pact_draw_catalog is None else load_pact_draw_catalog(args.pact_draw_catalog))
        if (args.event_catalog is None) != (args.character_catalog is None):
            raise ProfileError("--event-catalog and --character-catalog must be supplied together")
        events = None if args.event_catalog is None else load_event_catalog(args.event_catalog, args.character_catalog)
        if args.hunting and args.hunting_catalog is not None:
            raise ProfileError("--hunting cannot be combined with --hunting-catalog")
        hunts = build_bundled_hunting_policy() if args.hunting else (None if args.hunting_catalog is None else load_hunting_catalog(args.hunting_catalog))
        if args.hunting:
            events = merge_event_catalogs(
                build_bundled_counter_descent_policy(),
                events,
            )
        if args.daily_quests:
            # Daily Quests reuse the Hunting settlement path but are never
            # advertised, so they extend whichever catalog is active rather
            # than needing one of their own. Without any Hunting catalog they
            # still need a container to live in.
            if hunts is None:
                hunts = HuntingCatalog(build_bundled_daily_quest_stages(), BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
            else:
                hunts = replace(hunts, stages=hunts.stages + build_bundled_daily_quest_stages())
        if args.secondary_worlds:
            # The two secondary world maps are hidden for the same reason the
            # Daily Quests are: the client draws their map points itself and
            # never asks a selector which stages exist.
            secondary = build_bundled_breasoul_stages() + build_bundled_five_emperors_stages()
            if hunts is None:
                hunts = HuntingCatalog(secondary, BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
            else:
                hunts = replace(hunts, stages=hunts.stages + secondary)
        if args.cavern_forest:
            # Hidden for a stronger reason than the two families above: the
            # client's Orbling Cavern and Cryptid Forest selectors read a
            # hardcoded list apiece and never consult a served one, so an
            # advertised row here could only duplicate them into a menu they
            # do not belong to.
            areas = build_bundled_orbling_cavern_stages() + build_bundled_cryptid_forest_stages()
            if hunts is None:
                hunts = HuntingCatalog(areas, BUNDLED_ITEM_SLOTS, BUNDLED_MAX_STACK)
            else:
                hunts = replace(hunts, stages=hunts.stages + areas)
        # Interpolation is on unless refused: the record covers thirty story
        # stages and the rest of the game would otherwise never show a chest.
        # It only ever answers where the record is silent.
        luck_pools = build_luck_pools(
            None if args.luck_pool_catalog is None else load_luck_pool_catalog(args.luck_pool_catalog),
            interpolate=not args.no_interpolated_luck_pools,
        )
        if args.achievements and args.achievement_catalog is not None:
            raise ProfileError("--achievements cannot be combined with --achievement-catalog")
        achievements = build_bundled_achievement_policy() if args.achievements else (None if args.achievement_catalog is None else load_achievement_catalog(args.achievement_catalog))
        messages = (
            build_bundled_chapter_message_policy()
            if args.core_story and args.message_catalog is None
            else (None if args.message_catalog is None else load_message_catalog(args.message_catalog))
        )
        if args.core_story and messages is not None and messages.item_slots < 112:
            raise ProfileError(
                "--core-story chapter milestones require a message catalog with at least 112 item slots"
            )
        if args.trading_post and args.exchange_catalog is not None:
            raise ProfileError("--trading-post cannot be combined with --exchange-catalog")
        exchanges = build_bundled_exchange_policy() if args.trading_post else (None if args.exchange_catalog is None else load_exchange_catalog(args.exchange_catalog))
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
            event_catalog=events,
            drop_eligibility=getattr(args, 'drop_eligibility', False),
            hunting_catalog=hunts,
            daily_quests=args.daily_quests,
            secondary_worlds=args.secondary_worlds,
            cavern_forest=args.cavern_forest,
            luck_pool_catalog=luck_pools,
            public_data_root=args.public_data_root,
            outcome_strict=getattr(args, "outcome_strict", False),
            companion_equipment_catalog=companion_equipment,
            chapter_milestones=getattr(args, "core_story", False),
            login_bonuses=getattr(args, "core_story", False),
            original_mail_shape=getattr(args, "original_mail_shape", False),
            build_id=build_id,
            daily_drop_bonuses=getattr(args, "core_story", False),
            stamina=getattr(args, "enable_stamina", False),
        )
    except (OSError, ProfileError, ServerConfigError, ResourceCatalogError, StoryCatalogError, StoryProgressionCatalogError, SettlementCatalogError, StoryOutcomeCatalogError, ClearStateCatalogError, StatusupCatalogError, JobCatalogError, RebirthCatalogError, SummonSkillCatalogError, CompanionCatalogError, CompanionEquipmentCatalogError, CompanionStrengthenCatalogError, CompanionEvolutionCatalogError, CompanionDrawCatalogError, PactDrawCatalogError, EventCatalogError, HuntingCatalogError, AchievementCatalogError, MessageCatalogError, ExchangeCatalogError) as error:
        if resources is not None:
            resources.close()
        raise ProfileError(f"bootstrap server failed: {error}") from error
    return server


def main() -> int:
    try:
        args = load_launch_config(parse_args())
        server = build_server(args)
    except (OSError, ProfileError, ServerConfigError, ResourceCatalogError) as error:
        raise SystemExit(f"bootstrap server failed: {error}") from error
    print(f"bootstrap compatibility server listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
