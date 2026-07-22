"""Generate a local patch plan for user-supplied IL2CPP metadata literals.

The caller supplies the APK member and every old/new literal. This module does
not name an application, endpoint, or metadata location; generated plans stay
local because they contain source-specific hashes and bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
from typing import Iterable
import zipfile

from liminal_gate.apk_patcher import PATCH_PLAN_SCHEMA_VERSION, sha256_file


IL2CPP_METADATA_MAGIC = 0xFAB11BAF


class PlanGenerationError(ValueError):
    """A user-local metadata literal cannot be safely planned."""


def generate_plan(source_apk: Path, metadata_member: str, replacements: Iterable[tuple[bytes, bytes]]) -> dict[str, object]:
    """Create source-hash-guarded patches for unique, non-growing literals."""
    if not metadata_member or metadata_member.startswith("/") or ".." in Path(metadata_member).parts:
        raise PlanGenerationError("metadata member must be a safe archive path")
    pairs = tuple(replacements)
    if not pairs:
        raise PlanGenerationError("at least one literal replacement is required")
    try:
        with zipfile.ZipFile(source_apk) as archive:
            metadata = archive.read(metadata_member)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise PlanGenerationError("could not read the selected metadata member") from error
    table_offset, table_size, data_offset, data_size = _literal_tables(metadata)
    patches: list[dict[str, object]] = []
    for old, new in pairs:
        if not old or not new or len(new) > len(old):
            raise PlanGenerationError("replacement literal must be nonempty and no longer than source literal")
        record_offset, literal_offset = _find_unique_literal(metadata, table_offset, table_size, data_offset, data_size, old)
        padded = new + old[len(new):]
        patches.extend((
            {"member": metadata_member, "offset": record_offset, "expected_hex": struct.pack("<I", len(old)).hex(), "replacement_hex": struct.pack("<I", len(new)).hex()},
            {"member": metadata_member, "offset": literal_offset, "expected_hex": old.hex(), "replacement_hex": padded.hex()},
        ))
    _reject_overlaps(patches)
    return {"schema_version": PATCH_PLAN_SCHEMA_VERSION, "source_sha256": sha256_file(source_apk), "patches": sorted(patches, key=lambda patch: (str(patch["member"]), int(patch["offset"])))}


def parse_replacement(value: str) -> tuple[bytes, bytes]:
    old, separator, new = value.partition("=")
    if separator != "=" or not old or not new:
        raise argparse.ArgumentTypeError("literal replacement uses OLD=NEW")
    try:
        old_bytes, new_bytes = old.encode("ascii"), new.encode("ascii")
    except UnicodeEncodeError as error:
        raise argparse.ArgumentTypeError("literals must be ASCII") from error
    if len(new_bytes) > len(old_bytes):
        raise argparse.ArgumentTypeError("replacement literal may not be longer than source literal")
    return old_bytes, new_bytes


def _literal_tables(metadata: bytes) -> tuple[int, int, int, int]:
    if len(metadata) < 24:
        raise PlanGenerationError("metadata is too short")
    magic, _version, table_offset, table_size, data_offset, data_size = struct.unpack_from("<IIIIII", metadata)
    if magic != IL2CPP_METADATA_MAGIC:
        raise PlanGenerationError("selected member is not IL2CPP global metadata")
    if table_size == 0 or table_size % 8 or table_offset + table_size > len(metadata) or data_offset + data_size > len(metadata):
        raise PlanGenerationError("metadata string-literal tables are invalid")
    return table_offset, table_size, data_offset, data_size


def _find_unique_literal(metadata: bytes, table_offset: int, table_size: int, data_offset: int, data_size: int, old: bytes) -> tuple[int, int]:
    matches: list[tuple[int, int]] = []
    for record_offset in range(table_offset, table_offset + table_size, 8):
        length, index = struct.unpack_from("<II", metadata, record_offset)
        literal_offset = data_offset + index
        if index + length <= data_size and length == len(old) and metadata[literal_offset:literal_offset + length] == old:
            matches.append((record_offset, literal_offset))
    if len(matches) != 1:
        raise PlanGenerationError("source literal must match exactly one IL2CPP string-literal record")
    return matches[0]


def _reject_overlaps(patches: list[dict[str, object]]) -> None:
    ranges: list[tuple[int, int]] = []
    for patch in patches:
        start = int(patch["offset"])
        end = start + len(bytes.fromhex(str(patch["expected_hex"])))
        if any(start < previous_end and previous_start < end for previous_start, previous_end in ranges):
            raise PlanGenerationError("literal replacements produce overlapping metadata patches")
        ranges.append((start, end))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-apk", required=True, type=Path)
    parser.add_argument("--metadata-member", required=True)
    parser.add_argument("--replace", action="append", required=True, type=parse_replacement)
    parser.add_argument("--output-plan", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = generate_plan(args.source_apk, args.metadata_member, args.replace)
        args.output_plan.parent.mkdir(parents=True, exist_ok=True)
        args.output_plan.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, PlanGenerationError) as error:
        raise SystemExit(f"plan generation failed: {error}") from error
    print(f"wrote local patch plan: {args.output_plan}")
    return 0
