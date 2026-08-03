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
from urllib.parse import urlsplit
import zipfile

from liminal_gate.il2cpp_plan_generator import PlanGenerationError, generate_plan


METADATA_MEMBER = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
DATA_BUNDLE_MEMBER = "assets/bin/Data/data.unity3d"
API_BASE_LITERAL = b"https://gdappserver.appspot.com/"
RESOURCE_BASE_LITERAL = b"http://storage.googleapis.com/gdresources/data_u2017/android/"
WEBSITE_BASE_LITERAL = b"http://www.terra-battle.com"

# The final catalog skips Attack of Coin Creeps even though the selector still
# advertises all three Chapter 1003 sections. Copying the retained 3003-1 record
# supplies the same 610x140/version metadata under the missing logical names;
# resource setup separately prefers exact operator-owned sp1003 bundles and
# otherwise derives internally renamed bundles from retained Coin Creeps art.
COIN_CREEPS_BANNER_ALIASES = {
    "member": DATA_BUNDLE_MEMBER,
    "asset_name": "AssetVersions",
    "collection": "SpecialBanner",
    "source_name": "sp3003-1",
    "aliases": ["sp1003-1", "sp1003-2", "sp1003-3"],
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


def generate_legacy_client_plan(source_apk: Path, server_origin: str) -> dict[str, object]:
    """Generate only local routing edits for a selected APK."""
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
    plan["text_asset_json_aliases"] = [COIN_CREEPS_BANNER_ALIASES]
    return plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-apk", required=True, type=Path)
    parser.add_argument("--server-origin", required=True, help="for example: http://192.168.1.10:8642")
    parser.add_argument("--output-plan", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = generate_legacy_client_plan(args.source_apk, args.server_origin)
        args.output_plan.parent.mkdir(parents=True, exist_ok=True)
        args.output_plan.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, PlanGenerationError) as error:
        raise SystemExit(f"legacy client plan generation failed: {error}") from error
    print(f"wrote local legacy-client patch plan: {args.output_plan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
