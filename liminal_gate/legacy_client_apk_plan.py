"""Generate a source-hash-guarded local server-redirection plan.

This clean-room compatibility profile redirects the legacy client to a
user-selected local server. It does not contain an APK hash, signing material,
or generated plan; those stay on the user's local machine.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

from liminal_gate.il2cpp_plan_generator import PlanGenerationError, generate_plan


METADATA_MEMBER = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
API_BASE_LITERAL = b"https://gdappserver.appspot.com/"
RESOURCE_BASE_LITERAL = b"http://storage.googleapis.com/gdresources/data_u2017/android/"
WEBSITE_BASE_LITERAL = b"http://www.terra-battle.com"

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
    return origin


def generate_legacy_client_plan(source_apk: Path, server_origin: str) -> dict[str, object]:
    """Generate only local routing edits for a selected APK."""
    origin = normalize_server_origin(server_origin)
    replacements = (
        (API_BASE_LITERAL, (origin + "/").encode("ascii")),
        (RESOURCE_BASE_LITERAL, (origin + "/resources/").encode("ascii")),
        (WEBSITE_BASE_LITERAL, origin.encode("ascii")),
    )
    plan = generate_plan(source_apk, METADATA_MEMBER, replacements)
    plan["patches"].extend({"member": member, "offset": offset, "expected_hex": old, "replacement_hex": new} for member, offset, old, new in (*IAP_MODAL_PATCHES, *TERMS_CONFIRMATION_PATCHES))
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
