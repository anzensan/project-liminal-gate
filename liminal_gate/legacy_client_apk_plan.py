"""Generate a source-hash-guarded local server-redirection plan.

This clean-room compatibility profile redirects the legacy client to a
user-selected local server. It does not contain an APK hash, signing material,
or generated plan; those stay on the user's local machine.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from urllib.parse import urlsplit
import zipfile

from liminal_gate.il2cpp_plan_generator import PlanGenerationError, generate_plan
from liminal_gate.reviewed_build import APK_DATA_MEMBER, IL2CPP_METADATA_MEMBER


METADATA_MEMBER = IL2CPP_METADATA_MEMBER
DATA_BUNDLE_MEMBER = APK_DATA_MEMBER
API_BASE_LITERAL = b"https://gdappserver.appspot.com/"
RESOURCE_BASE_LITERAL = b"http://storage.googleapis.com/gdresources/data_u2017/android/"
WEBSITE_BASE_LITERAL = b"http://www.terra-battle.com"

# The final catalog skips Attack of Coin Creeps even though the selector still
# advertises all three Chapter 1003 sections. Copying the retained 3003-1 record
# supplies the same 610x140 metadata under the missing logical names; resource
# setup separately prefers exact operator-owned sp1003 bundles and otherwise
# derives internally renamed bundles from retained Coin Creeps art.
#
# The client caches every downloaded image as `<asset>_<ver>.bin` and reuses it
# without asking again, deleting only the other versions of the same asset. A
# corrected bundle served at the unchanged URL would therefore never reach an
# install that had already cached the first one, so these aliases carry their
# own version. It is a local cache identity, not a claim about the retired
# service's versioning: it only has to differ from the 110 served before it.
COIN_CREEPS_BANNER_VERSION = 111
COIN_CREEPS_BANNER_ALIASES = {
    "member": DATA_BUNDLE_MEMBER,
    "asset_name": "AssetVersions",
    "collection": "SpecialBanner",
    "source_name": "sp3003-1",
    "aliases": ["sp1003-1", "sp1003-2", "sp1003-3"],
    "overrides": {"ver": COIN_CREEPS_BANNER_VERSION},
}

# The retired Unity IAP bootstrap always reports PurchasingUnavailable (zero).
# These source-byte-guarded branches dismiss only that startup modal; they do
# not create a store, authorize a purchase, or alter any wallet value.
IAP_MODAL_PATCHES = (
    ("lib/arm64-v8a/libil2cpp.so", 0xFED20C, "e8000037", "410c0034"),
    ("lib/armeabi-v7a/libil2cpp.so", 0xB0EA4C, "000050e3", "000051e3"),
    ("lib/armeabi-v7a/libil2cpp.so", 0xB0EA50, "0600001a", "6c00000a"),
)

# The offline title flow otherwise waits forever at its retired Terms branch.
# These retain the original local ConfirmedTOS save behavior while skipping only
# the unavailable confirmation branch.
TERMS_CONFIRMATION_PATCHES = (
    ("lib/arm64-v8a/libil2cpp.so", 0xD2E324, "e1010054", "1f2003d5"),
    ("lib/armeabi-v7a/libil2cpp.so", 0x7CADDC, "0c00001a", "0000a0e1"),
)

# Android 11 replaced jemalloc with Scudo. Unity 2017's ARM64
# UnityDefaultAllocator can track only five distinct 4 GB address regions and
# crashes once Scudo places live allocations in a sixth. The same player
# already carries and constructs DynamicHeapAllocator<LowLevelAllocator> for
# its fallback allocator. This exact-build patch replaces only the default
# allocator constructor with that in-binary 176-byte layout; the caller has
# already reserved 192 bytes for each object.
#
# The replacement is 39 AArch64 instructions and exactly fills the original
# constructor. Its salient targets are:
#   0x00d930c8  DynamicHeapAllocator vtable
#   0x00d719d0  BaseAllocator instance counter
#   0x00510e90  in-binary mutex constructor
ARM64_UNITY_MEMBER = "lib/arm64-v8a/libunity.so"
FINAL_ARM64_UNITY_SHA256 = "9980ea0174528f97c6f9d42a51cfc5f3bff31b1c62652028fbb22b01111c7090"
ARM64_SCUDO_ALLOCATOR_PATCHES = (
    (
        ARM64_UNITY_MEMBER,
        0x157420,
        "c86100f008e13c91084100911f3400b91fc002f81f4002f81fc001f81f4001f8"
        "080400a9c86000d00841279109fd5f882905001109fd0a88aaffff35f44fbea9"
        "fd7b01a9fd430091e861009008e10e9113e0009108410091091000b9080000f9"
        "08200291e90313aa3f0100b93f0500f9294100913f0108eb81ffff5400200291"
        "7ce60e94fd7b41a9e1031f2a020a8052e00313aaf44fc2a840c6fc17",
        "f44fbea9fd7b01a9fd430091f30300aaf40301aae861009008e1029108410091"
        "685200a9c86000d00841279109fd5f882905001109fd0a88aaffff35691200b9"
        "7f1600b97ffe01a97ffe02a97f1e00f97f2200f96922019169a604a96a620191"
        "6aaa05a960a2019182e60e9428008052685202390802a05268fe09a9e00313aa"
        "fd7b41a9f44fc2a8c0035fd61f2003d51f2003d51f2003d51f2003d5",
    ),
)


# Optional, off by default. Unity 2017's `bitter.jnibridge` builds a
# `java.lang.reflect.Proxy` for `ServiceConnection`, and a Proxy receives every
# interface method through its InvocationHandler — including `default` ones,
# whose implementations it does not inherit. Android 16 added the
# `onServiceConnected(ComponentName, IBinder, IBinderSession)` overload, so the
# first Google Play Services bind to *complete* asks the 2017 bridge to dispatch
# a signature it has never seen and it throws NoSuchMethodError on the main
# thread. The bridge is Unity's and cannot be rebuilt, but the crash needs a
# completed bind: an action string that resolves to nothing makes `bindService`
# return false, and the callback never fires.
#
# Only the final byte of each action is rewritten, and the patch builder below
# proves the result still sorts between its neighbours before emitting anything.
# That check is the point: a dex `string_ids` table is *sorted*, and the runtime
# verifier rejects one that is not. Editing bytes in place preserves every
# offset in the file but not the table's order, so a replacement that changes an
# early byte — say rewriting the shared `com.google.android.gms.` prefix — loads
# nowhere and takes the whole process down before any game code runs.
#
# Nothing is lost: this is an offline preservation build, and Play Games, the
# ads SDK, Google auth, and Nearby have no live service to reach.
#
# `com.google.android.gms.common.internal.service.ICommonService` and
# `.ICommonCallbacks` are deliberately absent. They are AIDL interface
# descriptors used by `Binder.attachInterface`, not bind actions; rewriting them
# would corrupt the binder handshake rather than prevent a bind.
CLIENT_DEX_MEMBER = "classes.dex"
FINAL_CLIENT_DEX_SHA256 = "9526a62b2e5fcea2c3d701dd678ad8fe4fd41d755805ee114a589f18f875c898"
#: Replaces each action's last byte. No GMS action ends this way, so the Intent
#: resolves to nothing; `_` also sorts above every letter, which is what keeps
#: the rewritten string ahead of the one it already preceded.
INERT_ACTION_BYTE = b"_"
#: `string_ids_size`, `string_ids_off`: the two fields at this fixed header
#: offset in every dex version this client ships.
DEX_STRING_IDS_HEADER_OFFSET = 56
GOOGLE_SERVICE_BIND_ACTIONS = (
    b"com.google.android.gms.ads.identifier.service.PERSISTENT_START",
    b"com.google.android.gms.ads.identifier.service.START",
    b"com.google.android.gms.ads.service.CACHE",
    b"com.google.android.gms.ads.service.HTTP",
    b"com.google.android.gms.ads.service.START",
    b"com.google.android.gms.auth.api.accounttransfer.service.START",
    b"com.google.android.gms.auth.api.credentials.service.START",
    b"com.google.android.gms.auth.api.phone.service.SmsRetrieverApiService.START",
    b"com.google.android.gms.auth.api.signin.service.START",
    b"com.google.android.gms.auth.service.START",
    b"com.google.android.gms.common.service.START",
    b"com.google.android.gms.games.service.START",
    b"com.google.android.gms.nearby.bootstrap.service.NearbyBootstrapService.START",
    b"com.google.android.gms.nearby.connection.service.START",
    b"com.google.android.gms.nearby.messages.service.NearbyMessagesService.START",
    b"com.google.android.gms.signin.service.START",
)

# Play Billing lives in `com.android.vending`, a different package from Play
# Services, so none of the actions above affect it. Nothing is given up: the
# store this talked to has been retired for years, and `IAP_MODAL_PATCHES`
# above already exists because the Unity IAP bootstrap always reports
# PurchasingUnavailable — the client is built to run without billing.
#
# `MarketBillingService.BIND` is the retired v2 billing endpoint, included for
# the same reason and by the same evidence about the store being gone.
#
# **These two are not the crash.** A Galaxy S24 FE log showed `UnityIAP:
# Billing service connected.` immediately before the fatal and this project
# read it as the cause; that reading is withdrawn. Billing's connection is
# `com.unity.purchasing.googleplay.BillingServiceManager$1`, a real class in
# `classes.dex`, and a class *inherits* an interface's `default` methods. Only
# a `java.lang.reflect.Proxy` routes them to its handler, so only a Proxy can
# raise this error. Twelve classes in the dex implement `ServiceConnection` and
# every one of them is a genuine class, which leaves none of them able to throw
# it. They stay neutralized because they cost nothing to neutralize, not
# because they were ever the fault.
PLAY_BILLING_BIND_ACTIONS = (
    b"com.android.vending.billing.InAppBillingService.BIND",
    b"com.android.vending.billing.MarketBillingService.BIND",
)

#: Every dex action the flag neutralizes. Kept as two named tuples above
#: because the evidence differs, though neither set is now believed to carry
#: the crash — see `UNITY_ADVERTISING_ID_ACTION`, which does.
DISABLED_BIND_ACTIONS = GOOGLE_SERVICE_BIND_ACTIONS + PLAY_BILLING_BIND_ACTIONS


# The bind that actually crashes, and the one the dex edits above cannot reach.
#
# Unity's own `libunity.so` binds Play Services from native code to read the
# advertising ID. It carries its own copy of the action, its own AIDL
# descriptor, and its own failure messages, none of which live in `classes.dex`:
#
#   com.google.android.gms.ads.identifier.service.START
#   com.google.android.gms
#   com.google.android.gms.ads.identifier.internal.IAdvertisingIdService
#   Failed to obtain GoogleAdsId from GooglePlayService
#   Cannot bind to GooglePlayService.
#
# and beside them the JNI method table it builds the connection proxy from,
# which declares exactly one connect method:
#
#   android/content/ServiceConnection
#     onServiceConnected  (Landroid/content/ComponentName;Landroid/os/IBinder;)V
#
# That is the whole defect. Unity creates this `ServiceConnection` as a
# `java.lang.reflect.Proxy` through `bitter.jnibridge`; Android 16's three-
# argument overload is a `default` method, a Proxy hands every interface method
# to its handler rather than inheriting it, and the 2017 bridge has no such
# signature. A physical Galaxy S26 on Android 16 crashed exactly this way with
# all eighteen dex actions already rewritten, which is what identified it: the
# dex copy was inert and Unity's own copy still resolved.
#
# Unlike the dex, an ELF `.rodata` string has no ordering to preserve, so any
# byte will do. The *first* is taken rather than the last because a C toolchain
# may tail-merge string literals — a shorter string can be a pointer into this
# one's suffix — and the head of a string is never shared that way. In the
# reviewed build the neighbouring `com.google.android.gms` is a separate,
# adjacent, NUL-terminated string rather than a merged suffix, so nothing here
# is shared either way; patching the head keeps that true for a build where it
# might not be.
#
# Nothing is lost. The advertising ID is analytics for a service retired years
# ago, and Unity already handles the bind failing — `Cannot bind to
# GooglePlayService.` is its own message for exactly this path.
UNITY_ADVERTISING_ID_ACTION = b"com.google.android.gms.ads.identifier.service.START"
ARMV7_UNITY_MEMBER = "lib/armeabi-v7a/libunity.so"
FINAL_ARMV7_UNITY_SHA256 = "c5e1eae55f03d0bca06d11fd5eae523c2ba49a8189e83bd1475ffeff16cd974d"
#: Member to the digest that proves which build its offset was read out of.
#: Both ABIs ship the string once, and both are patched: a device running
#: either one makes the same bind.
UNITY_BIND_ACTION_MEMBERS = {
    ARM64_UNITY_MEMBER: FINAL_ARM64_UNITY_SHA256,
    ARMV7_UNITY_MEMBER: FINAL_ARMV7_UNITY_SHA256,
}


def _dex_string_table(data: bytes) -> list[tuple[int, bytes]]:
    """Every dex string as `(offset of its bytes, its bytes)`, in table order.

    The table is sorted, and the runtime enforces that. Reading it is what lets
    an edit be checked against the order rather than assumed safe.
    """
    size, offset = struct.unpack_from("<II", data, DEX_STRING_IDS_HEADER_OFFSET)
    table = []
    for start in struct.unpack_from(f"<{size}I", data, offset):
        cursor = start
        while data[cursor] & 0x80:  # ULEB128 length, then MUTF-8 bytes and a NUL
            cursor += 1
        cursor += 1
        table.append((cursor, data[cursor:data.index(b"\0", cursor)]))
    return table


def _disabled_bind_action_patches(source_apk: Path) -> list[dict[str, object]]:
    """Rewrite each bind action's last byte, proving the table stays sorted.

    Offsets are read from the dex rather than recorded, so the digest guard is
    the single source of truth about which dex this applies to; a hardcoded
    table could disagree with it silently.
    """
    dex_sha256 = _sha256_member(source_apk, CLIENT_DEX_MEMBER)
    if dex_sha256 != FINAL_CLIENT_DEX_SHA256:
        raise PlanGenerationError(
            "selected APK's client dex does not match the supported final client "
            f"(member SHA-256 {dex_sha256}); refusing to rewrite bytes that were not reviewed"
        )
    with zipfile.ZipFile(source_apk) as archive:
        data = archive.read(CLIENT_DEX_MEMBER)
    table = _dex_string_table(data)
    positions = {value: index for index, (_offset, value) in enumerate(table)}
    known = set(positions)
    patches: list[dict[str, object]] = []
    for action in DISABLED_BIND_ACTIONS:
        index = positions.get(action)
        if index is None or index in (0, len(table) - 1):
            raise PlanGenerationError(f"reviewed dex must contain {action.decode()} as a string")
        previous, following = table[index - 1][1], table[index + 1][1]
        replacement = action[:-1] + INERT_ACTION_BYTE
        # Byte order equals the dex's UTF-16 order only while all three strings
        # are ASCII. Requiring the *original* to satisfy the same comparison
        # proves that here, and fails closed on a neighbour where it would not.
        if not previous < action < following:
            raise PlanGenerationError(
                f"cannot order-check {action.decode()} against its neighbours in the reviewed dex"
            )
        if not previous < replacement < following or replacement in known:
            raise PlanGenerationError(
                f"replacing {action.decode()} would leave the dex string table unsorted; "
                "the runtime rejects that dex outright"
            )
        known.add(replacement)
        patches.append({
            "member": CLIENT_DEX_MEMBER,
            "offset": table[index][0] + len(action) - 1,
            "expected_hex": action[-1:].hex(),
            "replacement_hex": INERT_ACTION_BYTE.hex(),
            "repair_dex_header": True,
        })
    return patches


def _disabled_unity_bind_action_patches(source_apk: Path) -> list[dict[str, object]]:
    """Neutralize the advertising-ID bind Unity's own native code makes.

    Offsets are read from each member rather than recorded, for the same reason
    the dex builder reads its own: the digest guard is then the single source of
    truth about which build this applies to, and a stale table cannot disagree
    with it in silence. Requiring exactly one occurrence is part of that -- two
    would mean a second call site this reasoning never looked at.
    """
    patches: list[dict[str, object]] = []
    for member, expected_sha256 in UNITY_BIND_ACTION_MEMBERS.items():
        actual = _sha256_member(source_apk, member)
        if actual != expected_sha256:
            raise PlanGenerationError(
                f"selected APK's {member} does not match the supported final client "
                f"(member SHA-256 {actual}); refusing to rewrite bytes that were not reviewed"
            )
        with zipfile.ZipFile(source_apk) as archive:
            data = archive.read(member)
        found = [
            offset for offset in range(len(data))
            if data.startswith(UNITY_ADVERTISING_ID_ACTION, offset)
        ]
        if len(found) != 1:
            raise PlanGenerationError(
                f"reviewed {member} must contain "
                f"{UNITY_ADVERTISING_ID_ACTION.decode()} exactly once, found {len(found)}"
            )
        patches.append({
            "member": member,
            "offset": found[0],
            "expected_hex": UNITY_ADVERTISING_ID_ACTION[:1].hex(),
            "replacement_hex": INERT_ACTION_BYTE.hex(),
        })
    return patches


def _sha256_member(source_apk: Path, member: str) -> str:
    digest = hashlib.sha256()
    with zipfile.ZipFile(source_apk) as archive:
        try:
            with archive.open(member) as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        except KeyError as error:
            raise PlanGenerationError(
                f"selected APK is missing required ARM64 Unity member {member}"
            ) from error
    return digest.hexdigest()


def max_server_origin_length() -> int:
    """The longest origin the guarded literal replacements can still express.

    A metadata string-literal patch may only shrink its source literal, so each
    routing replacement bounds the origin by the room left in the literal it
    overwrites.  The website literal is replaced by the bare origin and is the
    shortest of the three, so it sets the real limit.
    """
    return min(
        len(API_BASE_LITERAL) - len(b"/"),
        len(RESOURCE_BASE_LITERAL) - len(b"/resources/"),
        len(WEBSITE_BASE_LITERAL),
    )


def normalize_server_origin(value: str) -> str:
    """Accept an ASCII HTTP(S) origin without a path, query, or fragment."""
    if not value or value != value.strip() or not value.isascii():
        raise PlanGenerationError("server origin must be a nonempty ASCII URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PlanGenerationError("server origin must use http:// or https:// and include a host")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment or parsed.username or parsed.password:
        raise PlanGenerationError("server origin must contain only scheme, host, and optional port")
    origin = f"{parsed.scheme}://{parsed.netloc}"
    try:
        origin.encode("ascii")
    except UnicodeEncodeError as error:  # Defensive; isascii above should catch this.
        raise PlanGenerationError("server origin must be ASCII") from error
    limit = max_server_origin_length()
    if len(origin) > limit:
        # Reported here rather than as a generic literal failure deep in the
        # patch generator, because the usual cause is a chosen address and port
        # that the tester can still change.
        raise PlanGenerationError(
            f"server origin {origin!r} is {len(origin)} characters; the guarded routing "
            f"literals allow at most {limit}. An IPv4 address always fits when the port "
            f"has at most four digits; choose a shorter port or a shorter host name."
        )
    return origin


def generate_legacy_client_plan(
    source_apk: Path, server_origin: str, disable_google_services: bool = False,
) -> dict[str, object]:
    """Generate only local routing edits for a selected APK.

    `disable_google_services` additionally makes the client's Play Services bind
    actions unresolvable, in the dex and in Unity's own native runtime. It is
    off by default: it edits client bytes that no other supported path touches,
    and it exists for devices whose Android version crashes on the bind. See
    `DISABLED_BIND_ACTIONS` and `UNITY_ADVERTISING_ID_ACTION` -- the second is
    the one that carries the crash.
    """
    origin = normalize_server_origin(server_origin)
    unity_sha256 = _sha256_member(source_apk, ARM64_UNITY_MEMBER)
    if unity_sha256 != FINAL_ARM64_UNITY_SHA256:
        raise PlanGenerationError(
            "selected APK's ARM64 Unity player does not match the supported "
            f"final client (member SHA-256 {unity_sha256})"
        )
    replacements = (
        (API_BASE_LITERAL, (origin + "/").encode("ascii")),
        (RESOURCE_BASE_LITERAL, (origin + "/resources/").encode("ascii")),
        (WEBSITE_BASE_LITERAL, origin.encode("ascii")),
    )
    plan = generate_plan(source_apk, METADATA_MEMBER, replacements)
    plan["patches"].extend(
        {
            "member": member,
            "offset": offset,
            "expected_hex": old,
            "replacement_hex": new,
        }
        for member, offset, old, new in (
            *IAP_MODAL_PATCHES,
            *TERMS_CONFIRMATION_PATCHES,
            *ARM64_SCUDO_ALLOCATOR_PATCHES,
        )
    )
    if disable_google_services:
        plan["patches"].extend(_disabled_bind_action_patches(source_apk))
        plan["patches"].extend(_disabled_unity_bind_action_patches(source_apk))
    plan["text_asset_json_aliases"] = [COIN_CREEPS_BANNER_ALIASES]
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-apk", required=True, type=Path)
    parser.add_argument("--server-origin", required=True, help="for example: http://192.168.1.10:8642")
    parser.add_argument("--output-plan", required=True, type=Path)
    parser.add_argument(
        "--disable-google-services", action="store_true",
        help="also make the client's Play Services bind actions unresolvable; needed on Android versions whose ServiceConnection interface the 2017 client cannot proxy",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = generate_legacy_client_plan(
            args.source_apk, args.server_origin, args.disable_google_services,
        )
        args.output_plan.parent.mkdir(parents=True, exist_ok=True)
        args.output_plan.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, PlanGenerationError) as error:
        raise SystemExit(f"legacy client plan generation failed: {error}") from error
    print(f"wrote local legacy-client patch plan: {args.output_plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
