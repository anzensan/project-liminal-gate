"""Recover the Daily Quest rotation from the operator's own APK.

The final client schedules Daily Quests itself.  ``DailyQuestManager`` picks up
to three of them a day from ``DailyQuestData.questOrder`` and its own clock, so
the rotation is a client asset rather than anything the retired service sent.
That asset is a ``MonoBehaviour`` in ``assets/bin/Data/data.unity3d``, which is
why it appears in neither BattleData nor the master trees the other importers
read.

This module reads it, so the daily stage set is **recovered** rather than
chosen.  What it deliberately does not attempt is the day-to-index rule: the
client owns that, computes today's entries itself, and the server never needs
to agree with it.  The server's only interest is which stages are legitimate
Daily Quests at all.

An IL2CPP build strips the field names, so the serialised ``MonoBehaviour``
cannot be read through a type tree.  It does not need one.  ``DailyQuestData``
declares exactly one field, so the payload after the standard header is a
single length-prefixed string array, and a parse that consumes the object
exactly -- no trailing bytes -- is self-validating.  The importer requires that
and refuses anything else.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import struct
import zipfile

from liminal_gate.file_digests import sha256_file as _sha256_file
from liminal_gate.reviewed_build import APK_DATA_MEMBER


class DailyQuestImportError(ValueError):
    """The APK does not carry a readable Daily Quest rotation."""


UNITY_DATA_MEMBER = APK_DATA_MEMBER
DAILY_QUEST_DATA_CLASS = "DailyQuestData"
STAGE_PATTERN = re.compile(r"\A([1-9][0-9]{0,4})-([1-9][0-9]{0,2})\Z")

# ``ChapterInterface`` keeps the Daily Quest chapters in their own block. A
# rotation naming anything outside it would mean this asset is not the one the
# Huntland Daily Quest menu reads, so it is refused rather than trusted.
DAILY_QUEST_CHAPTER_RANGE = (6000, 6099)

# GameObject PPtr, m_Enabled, m_Script PPtr. Unity writes a PPtr as a 4-byte
# file index followed by an 8-byte path ID.
_HEADER_SIZE = 12 + 4 + 12


@dataclass(frozen=True)
class DailyQuestRotation:
    """The recovered rotation and the stages it names."""

    order: tuple[str, ...]
    stages: tuple[tuple[int, int], ...]
    apk_sha256: str


def _align4(offset: int) -> int:
    return offset + (-offset) % 4


def _read_string_array(raw: bytes) -> tuple[str, ...]:
    """Read the one field ``DailyQuestData`` declares, or refuse the object."""
    offset = _HEADER_SIZE
    try:
        (name_length,) = struct.unpack_from("<i", raw, offset)
        if not 0 <= name_length <= len(raw):
            raise DailyQuestImportError("the Daily Quest object has an unreadable name")
        offset = _align4(offset + 4 + name_length)
        (count,) = struct.unpack_from("<i", raw, offset)
        offset += 4
        if not 1 <= count <= 1024:
            raise DailyQuestImportError("the Daily Quest rotation has an implausible length")
        entries: list[str] = []
        for _ in range(count):
            (length,) = struct.unpack_from("<i", raw, offset)
            offset += 4
            if not 1 <= length <= 64 or offset + length > len(raw):
                raise DailyQuestImportError("the Daily Quest rotation has an unreadable entry")
            entries.append(raw[offset : offset + length].decode("ascii"))
            offset = _align4(offset + length)
    except (struct.error, UnicodeDecodeError) as error:
        raise DailyQuestImportError("the Daily Quest object is not the expected layout") from error
    # The self-validating part: one field means the object ends with the array.
    if offset != len(raw):
        raise DailyQuestImportError("the Daily Quest object carries unexpected trailing fields")
    return tuple(entries)


def _parse_stage(entry: str) -> tuple[int, int]:
    matched = STAGE_PATTERN.match(entry)
    if matched is None:
        raise DailyQuestImportError(f"the Daily Quest rotation names an invalid stage: {entry!r}")
    chapter, section = int(matched.group(1)), int(matched.group(2))
    low, high = DAILY_QUEST_CHAPTER_RANGE
    if not low <= chapter <= high:
        raise DailyQuestImportError(f"the Daily Quest rotation names a non-daily chapter: {chapter}")
    return chapter, section


def recover_daily_quest_rotation(apk: Path) -> DailyQuestRotation:
    """Return the rotation declared by this APK's own ``DailyQuestData``."""
    try:
        import UnityPy  # noqa: PLC0415 -- optional, and only this importer needs it
    except ImportError as error:
        raise DailyQuestImportError(
            "recovering the Daily Quest rotation needs UnityPy; install it with "
            'python3 -m pip install ".[master-import]"'
        ) from error
    try:
        with zipfile.ZipFile(apk) as archive:
            bundle = archive.read(UNITY_DATA_MEMBER)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise DailyQuestImportError("could not read the APK's Unity data bundle") from error

    environment = UnityPy.load(io.BytesIO(bundle))
    script_path_ids = {
        object_.path_id
        for object_ in environment.objects
        if object_.type.name == "MonoScript"
        and str(getattr(object_.read(), "m_ClassName", "")) == DAILY_QUEST_DATA_CLASS
    }
    if not script_path_ids:
        raise DailyQuestImportError(f"the APK declares no {DAILY_QUEST_DATA_CLASS} script")

    recovered: list[tuple[str, ...]] = []
    for object_ in environment.objects:
        if object_.type.name != "MonoBehaviour":
            continue
        script = getattr(object_.read(check_read=False), "m_Script", None)
        if getattr(script, "path_id", None) in script_path_ids:
            recovered.append(_read_string_array(object_.get_raw_data()))
    if not recovered:
        raise DailyQuestImportError(f"the APK carries no {DAILY_QUEST_DATA_CLASS} instance")
    if len({entry for entries in recovered for entry in (entries,)}) != 1:
        raise DailyQuestImportError("the APK carries disagreeing Daily Quest rotations")

    order = recovered[0]
    stages = sorted({_parse_stage(entry) for entry in order})
    return DailyQuestRotation(order, tuple(stages), _sha256_file(apk))


def write_daily_quest_catalog(rotation: DailyQuestRotation, output: Path) -> Path:
    """Write the recovered rotation as a runtime catalog."""
    document = {
        "schema_version": 1,
        "provenance": "user-derived",
        "source": {"apk_sha256": rotation.apk_sha256, "asset": UNITY_DATA_MEMBER, "script": DAILY_QUEST_DATA_CLASS},
        "order": list(rotation.order),
        "stages": [{"chapter": chapter, "section": section} for chapter, section in rotation.stages],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def load_daily_quest_catalog(path: Path) -> DailyQuestRotation:
    """Load a previously written catalog, refusing a foreign or edited one."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DailyQuestImportError("could not read the local Daily Quest catalog JSON") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1 or document.get("provenance") != "user-derived":
        raise DailyQuestImportError("the Daily Quest catalog has an invalid schema or provenance")
    order, stages = document.get("order"), document.get("stages")
    if not isinstance(order, list) or not order or not all(isinstance(entry, str) for entry in order):
        raise DailyQuestImportError("the Daily Quest catalog has an invalid rotation")
    if not isinstance(stages, list) or not stages:
        raise DailyQuestImportError("the Daily Quest catalog has no stages")
    parsed = tuple(sorted({_parse_stage(entry) for entry in order}))
    declared = tuple(sorted(
        (stage["chapter"], stage["section"])
        for stage in stages
        if isinstance(stage, dict) and type(stage.get("chapter")) is int and type(stage.get("section")) is int
    ))
    if declared != parsed:
        raise DailyQuestImportError("the Daily Quest catalog's stages do not match its rotation")
    source = document.get("source")
    apk_sha256 = source.get("apk_sha256") if isinstance(source, dict) else None
    if not isinstance(apk_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", apk_sha256):
        raise DailyQuestImportError("the Daily Quest catalog has no APK provenance digest")
    return DailyQuestRotation(tuple(order), parsed, apk_sha256)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", type=Path, required=True, help="the operator's own matching APK")
    parser.add_argument("--output", type=Path, required=True, help="where to write the recovered catalog")
    arguments = parser.parse_args(argv)
    rotation = recover_daily_quest_rotation(arguments.apk)
    write_daily_quest_catalog(rotation, arguments.output)
    print(f"recovered {len(rotation.order)} Daily Quest rotation entries across {len(rotation.stages)} stages")
    print(f"wrote {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
