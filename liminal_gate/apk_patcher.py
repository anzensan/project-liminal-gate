"""Apply a user-supplied binary patch plan to a local APK archive.

This module contains no application-specific patch plan, original bytes, or
signing material. It produces an unsigned archive; the user must align and sign
the result with locally installed Android tools before installation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import zipfile


PATCH_PLAN_SCHEMA_VERSION = 1
SIGNATURE_SUFFIXES = (".EC", ".RSA", ".DSA", ".SF")
NATIVE_LIBRARY_PREFIX = "lib/"


class PatchPlanError(ValueError):
    """A supplied patch plan is malformed or does not match the source APK."""


def native_abis(source_apk: Path) -> tuple[str, ...]:
    """Return the ABI directory names the archive carries native code for."""
    with zipfile.ZipFile(source_apk) as source:
        return tuple(sorted({
            abi for abi in (_member_abi(info.filename) for info in source.infolist()) if abi
        }))


def _member_abi(member: str) -> str | None:
    """Return the ABI a `lib/<abi>/...` member belongs to, if it is one."""
    if not member.startswith(NATIVE_LIBRARY_PREFIX):
        return None
    remainder = member[len(NATIVE_LIBRARY_PREFIX):]
    abi, separator, _ = remainder.partition("/")
    return abi if separator and abi else None


@dataclass(frozen=True)
class BinaryPatch:
    member: str
    offset: int
    expected: bytes
    replacement: bytes


@dataclass(frozen=True)
class TextAssetJsonAliases:
    """Names copied from one existing record in a Unity TextAsset JSON list."""

    member: str
    asset_name: str
    collection: str
    source_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class PatchPlan:
    source_sha256: str
    patches: tuple[BinaryPatch, ...]
    text_asset_json_aliases: tuple[TextAssetJsonAliases, ...] = ()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_patch_plan(path: Path) -> PatchPlan:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PatchPlanError("could not read patch plan JSON") from error
    if not isinstance(document, dict) or document.get("schema_version") != PATCH_PLAN_SCHEMA_VERSION:
        raise PatchPlanError(f"schema_version must be {PATCH_PLAN_SCHEMA_VERSION}")
    source_sha256 = document.get("source_sha256")
    if not isinstance(source_sha256, str) or not _is_sha256(source_sha256):
        raise PatchPlanError("source_sha256 must be lowercase hexadecimal")
    raw_patches = document.get("patches")
    if not isinstance(raw_patches, list) or not raw_patches:
        raise PatchPlanError("patches must be a nonempty array")
    raw_aliases = document.get("text_asset_json_aliases", [])
    if not isinstance(raw_aliases, list):
        raise PatchPlanError("text_asset_json_aliases must be an array")
    return PatchPlan(
        source_sha256,
        tuple(_parse_patch(item) for item in raw_patches),
        tuple(_parse_text_asset_json_aliases(item) for item in raw_aliases),
    )


def apply_patch_plan(
    source_apk: Path, output_apk: Path, plan: PatchPlan, drop_abis: tuple[str, ...] = (),
) -> None:
    """Create an unsigned patched APK from local source material and a plan.

    `drop_abis` removes whole `lib/<abi>/` trees. Android then runs the app
    against whichever ABI remains. Dropping `arm64-v8a` from a dual-ABI archive
    therefore leaves a 32-bit process, but that package cannot run on modern
    64-bit-app-only devices such as Pixel 7 and later.

    Patches aimed at a dropped tree are discarded with it, which is safe here
    and checked below: the routing literals live in the ABI-independent
    metadata, so the remaining library keeps every edit that matters.
    """
    if source_apk.resolve() == output_apk.resolve():
        raise PatchPlanError("output APK must differ from source APK")
    if sha256_file(source_apk) != plan.source_sha256:
        raise PatchPlanError("source APK SHA-256 does not match patch plan")
    if drop_abis:
        available = native_abis(source_apk)
        unknown = sorted(set(drop_abis) - set(available))
        if unknown:
            raise PatchPlanError(f"source APK has no native code for: {unknown}")
        if not set(available) - set(drop_abis):
            raise PatchPlanError(
                "dropping every ABI would leave no native code; the app could not start"
            )
    patches_by_member: dict[str, list[BinaryPatch]] = {}
    for patch in plan.patches:
        if _member_abi(patch.member) in drop_abis:
            continue
        patches_by_member.setdefault(patch.member, []).append(patch)
    aliases_by_member: dict[str, list[TextAssetJsonAliases]] = {}
    for aliases in plan.text_asset_json_aliases:
        if _member_abi(aliases.member) in drop_abis:
            continue
        aliases_by_member.setdefault(aliases.member, []).append(aliases)
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    seen_members: set[str] = set()
    with zipfile.ZipFile(source_apk) as source, zipfile.ZipFile(
        output_apk, "w", compression=zipfile.ZIP_DEFLATED
    ) as output:
        for source_info in source.infolist():
            if _is_signature_member(source_info.filename):
                continue
            if _member_abi(source_info.filename) in drop_abis:
                continue
            data = source.read(source_info.filename)
            for patch in patches_by_member.get(source_info.filename, []):
                data = _apply_patch(data, patch)
                seen_members.add(patch.member)
            for aliases in aliases_by_member.get(source_info.filename, []):
                data = _apply_text_asset_json_aliases(data, aliases)
                seen_members.add(aliases.member)
            output.writestr(_clone_zip_info(source_info), data)
    missing = sorted((set(patches_by_member) | set(aliases_by_member)) - seen_members)
    if missing:
        output_apk.unlink(missing_ok=True)
        raise PatchPlanError(f"patch members missing from source APK: {missing}")


def _parse_patch(value: object) -> BinaryPatch:
    if not isinstance(value, dict):
        raise PatchPlanError("each patch must be an object")
    member = value.get("member")
    offset = value.get("offset")
    expected_hex = value.get("expected_hex")
    replacement_hex = value.get("replacement_hex")
    if not isinstance(member, str) or not member or member.startswith("/") or ".." in Path(member).parts:
        raise PatchPlanError("patch member must be a safe archive path")
    if type(offset) is not int or offset < 0:
        raise PatchPlanError("patch offset must be a nonnegative integer")
    expected = _decode_hex(expected_hex, "expected_hex")
    replacement = _decode_hex(replacement_hex, "replacement_hex")
    if len(expected) != len(replacement):
        raise PatchPlanError("replacement_hex must have the same length as expected_hex")
    return BinaryPatch(member, offset, expected, replacement)


def _parse_text_asset_json_aliases(value: object) -> TextAssetJsonAliases:
    if not isinstance(value, dict):
        raise PatchPlanError("each text-asset alias patch must be an object")
    member = value.get("member")
    asset_name = value.get("asset_name")
    collection = value.get("collection")
    source_name = value.get("source_name")
    aliases = value.get("aliases")
    if not isinstance(member, str) or not member or member.startswith("/") or ".." in Path(member).parts:
        raise PatchPlanError("text-asset alias member must be a safe archive path")
    for name, field in (
        (asset_name, "asset_name"),
        (collection, "collection"),
        (source_name, "source_name"),
    ):
        if not isinstance(name, str) or not name:
            raise PatchPlanError(f"text-asset alias {field} must be a nonempty string")
    if (
        not isinstance(aliases, list)
        or not aliases
        or any(not isinstance(alias, str) or not alias for alias in aliases)
        or len(set(aliases)) != len(aliases)
        or source_name in aliases
    ):
        raise PatchPlanError("text-asset aliases must be unique nonempty strings distinct from source_name")
    return TextAssetJsonAliases(member, asset_name, collection, source_name, tuple(aliases))


def _decode_hex(value: object, name: str) -> bytes:
    if not isinstance(value, str) or not value or len(value) % 2:
        raise PatchPlanError(f"{name} must be nonempty even-length hexadecimal")
    try:
        return bytes.fromhex(value)
    except ValueError as error:
        raise PatchPlanError(f"{name} must be hexadecimal") from error


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _apply_patch(data: bytes, patch: BinaryPatch) -> bytes:
    end = patch.offset + len(patch.expected)
    if end > len(data) or data[patch.offset:end] != patch.expected:
        raise PatchPlanError(f"patch expectation did not match {patch.member} at offset {patch.offset}")
    return data[:patch.offset] + patch.replacement + data[end:]


def _apply_text_asset_json_aliases(data: bytes, patch: TextAssetJsonAliases) -> bytes:
    """Apply a declarative alias edit and repack the operator's Unity bundle."""
    try:
        import UnityPy
    except ImportError as error:
        raise PatchPlanError(
            'Unity TextAsset patching requires the pinned master-import extra: pip install ".[master-import]"'
        ) from error
    try:
        environment = UnityPy.load(data)
        matches = []
        for item in environment.objects:
            if item.type.name != "TextAsset":
                continue
            asset = item.read()
            if asset.m_Name == patch.asset_name:
                matches.append(asset)
        if len(matches) != 1:
            raise PatchPlanError(
                f"Unity member must contain exactly one TextAsset named {patch.asset_name}"
            )
        asset = matches[0]
        asset.m_Script = _alias_text_asset_document(asset.m_Script, patch)
        asset.save()
        bundles = [item for item in environment.files.values() if hasattr(item, "save")]
        if len(bundles) != 1:
            raise PatchPlanError("Unity member must contain exactly one writable bundle")
        return bundles[0].save(packer="original")
    except PatchPlanError:
        raise
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise PatchPlanError(f"could not patch Unity TextAsset aliases: {error}") from error


def _alias_text_asset_document(script: str | bytes, patch: TextAssetJsonAliases) -> str:
    document = json.loads(script)
    entries = document.get(patch.collection) if isinstance(document, dict) else None
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise PatchPlanError(
            f"TextAsset {patch.asset_name} has no object list named {patch.collection}"
        )
    sources = [entry for entry in entries if entry.get("name") == patch.source_name]
    if len(sources) != 1:
        raise PatchPlanError(
            f"TextAsset alias source {patch.source_name} must match exactly one record"
        )
    existing = {entry.get("name") for entry in entries}
    collisions = sorted(set(patch.aliases) & existing)
    if collisions:
        raise PatchPlanError(f"TextAsset alias already exists: {', '.join(collisions)}")
    source = sources[0]
    entries.extend({**source, "name": alias} for alias in patch.aliases)
    return json.dumps(document, ensure_ascii=False, separators=(",", ":"))


def _is_signature_member(name: str) -> bool:
    upper = name.upper()
    return upper == "META-INF/MANIFEST.MF" or (
        upper.startswith("META-INF/") and upper.endswith(SIGNATURE_SUFFIXES)
    )


def _clone_zip_info(source: zipfile.ZipInfo) -> zipfile.ZipInfo:
    clone = zipfile.ZipInfo(source.filename, date_time=source.date_time)
    clone.compress_type = source.compress_type
    clone.comment = source.comment
    clone.external_attr = source.external_attr
    clone.create_system = source.create_system
    clone.flag_bits = source.flag_bits
    return clone


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-apk", required=True, type=Path)
    parser.add_argument("--patch-plan", required=True, type=Path)
    parser.add_argument("--output-apk", required=True, type=Path)
    parser.add_argument(
        "--drop-abi", action="append", default=[], metavar="ABI",
        help="remove a lib/<ABI>/ tree; the target device must support an ABI that remains",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        apply_patch_plan(
            args.source_apk, args.output_apk, load_patch_plan(args.patch_plan),
            tuple(args.drop_abi),
        )
    except (OSError, PatchPlanError, zipfile.BadZipFile) as error:
        raise SystemExit(f"patch failed: {error}") from error
    if args.drop_abi:
        print(f"dropped native code for: {', '.join(sorted(set(args.drop_abi)))}")
    print(f"wrote unsigned patched APK: {args.output_apk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
