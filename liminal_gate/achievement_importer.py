"""Recover the client's own achievement master from your APK.

The 99 achievements this game shows are not server data.  They are an
``AchivementSet`` ``MonoBehaviour`` inside ``assets/bin/Data/data.unity3d`` --
the same place, and the same shape of problem, as the Daily Quest rotation that
:mod:`liminal_gate.daily_quest_importer` recovers.  An IL2CPP build strips the
field names, so the serialised object is an untyped blob; the layout below comes
from ``AchivementInfo`` in the dump and is self-checking, because the array
consumes the object exactly and any wrong field width desynchronises the rest.

**Why the achievements menu was empty.**  Each record carries a ``showFlag``,
and ``AchievementUtil.IsShow`` resolves it through
``EventManager.GetBoolean(showFlag)`` -- the same gate ``enableDailyBonus`` and
the ``sp_ch_*`` stage flags ride, where an absent key reads *false*.  This
server never sent an ``achive-*`` flag, so every achievement evaluated as not
shown, ``UIAchivements`` built an empty list, and the menu entry rendered bare.
The eight-row bundled claim policy was never the missing half: it settles a
claim, and nothing was listing anything to claim.

Only three flags exist across the 99 records, which is what makes the fix
small: ``achive-1`` on the 42 ordinary achievements, ``achive-hide`` on the 56
Co-op, VS, Twitter, Line and survey entries the retired service owned, and one
empty-keyed placeholder carrying neither.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

from liminal_gate.daily_quest_importer import UNITY_DATA_MEMBER

#: The `MonoScript` whose instance carries the master.
ACHIEVEMENT_SET_CLASS = "AchivementSet"

#: `AchivementPresentType`.  A claim pays these; `Buddy` never appears in the
#: recovered table and is listed for completeness rather than handled.
PRESENT_ENERGY, PRESENT_COIN, PRESENT_ITEM, PRESENT_TITLE, PRESENT_BUDDY = range(5)

#: The flag the 42 ordinary achievements ride.  Sending it is what makes the
#: menu populate; it is a visibility gate and grants nothing by itself.
VISIBLE_SHOW_FLAG = "achive-1"

#: The flag on entries whose unlock conditions the retired service owned --
#: Co-op, VS, Twitter, Line, and the survey and placeholder rows.  Left unsent:
#: they are hidden in the final client for the same reason they are unreachable
#: here, and showing a permanently unachievable row is worse than omitting it.
HIDDEN_SHOW_FLAG = "achive-hide"

#: Where the array begins inside the serialised object: the MonoBehaviour
#: header (GameObject PPtr, enabled, script PPtr, name) ahead of `data`.
_ARRAY_OFFSET = 32
#: `LocalizedString` is six `EncryptedString`s, each a length-prefixed blob.
_LOCALIZED_LANGUAGES = 6


class AchievementImportError(RuntimeError):
    """The APK's achievement master could not be recovered."""


@dataclass(frozen=True)
class AchievementPresent:
    type: int
    id: int
    num: int


@dataclass(frozen=True)
class AchievementRecord:
    id: int
    key: str
    show_flag: str
    icon: str
    parent_id: int
    priority: int
    unlock_type: int
    unlock_values: tuple[int, int, int]
    presents: tuple[AchievementPresent, ...]
    device_type: int

    @property
    def visible(self) -> bool:
        """Whether the final client would list this one at all."""
        return self.show_flag == VISIBLE_SHOW_FLAG


@dataclass(frozen=True)
class AchievementMaster:
    records: tuple[AchievementRecord, ...]
    apk_sha256: str

    def show_flags(self) -> tuple[str, ...]:
        """The flags to send so the client lists what it can evaluate."""
        return tuple(sorted({record.show_flag for record in self.records if record.visible}))


class _Reader:
    """A little-endian Unity serialisation reader with 4-byte alignment."""

    def __init__(self, data: bytes, offset: int = 0) -> None:
        self.data, self.offset = data, offset

    def int32(self) -> int:
        if self.offset + 4 > len(self.data):
            raise AchievementImportError("achievement master ended mid-record")
        value = struct.unpack_from("<i", self.data, self.offset)[0]
        self.offset += 4
        return value

    def _align(self) -> None:
        self.offset = (self.offset + 3) & ~3

    def blob(self) -> bytes:
        length = self.int32()
        if length < 0 or self.offset + length > len(self.data):
            raise AchievementImportError(f"achievement master declares an impossible length {length}")
        value = self.data[self.offset:self.offset + length]
        self.offset += length
        self._align()
        return value

    def string(self) -> str:
        return self.blob().decode("utf-8", "replace")


def _record(reader: _Reader) -> AchievementRecord:
    identifier, key, show_flag = reader.int32(), reader.string(), reader.string()
    icon, parent_id, priority = reader.string(), reader.int32(), reader.int32()
    for _ in range(2 * _LOCALIZED_LANGUAGES):
        # The name and description are `EncryptedString`s. They are read past
        # rather than decoded: the client renders them from its own copy, and
        # this project has no need of the text to list or settle anything.
        reader.blob()
    unlock_type = reader.int32()
    unlock_values = (reader.int32(), reader.int32(), reader.int32())
    presents = tuple(
        AchievementPresent(reader.int32(), reader.int32(), reader.int32())
        for _ in range(reader.int32())
    )
    return AchievementRecord(
        identifier, key, show_flag, icon, parent_id, priority,
        unlock_type, unlock_values, presents, reader.int32(),
    )


def recover_achievement_master(apk: Path) -> AchievementMaster:
    """Return the achievement table declared by this APK's own ``AchivementSet``."""
    try:
        import UnityPy  # noqa: PLC0415 -- optional, and only this importer needs it
    except ImportError as error:
        raise AchievementImportError(
            "recovering the achievement master needs UnityPy; install it with "
            'python3 -m pip install ".[master-import]"'
        ) from error
    try:
        with zipfile.ZipFile(apk) as archive:
            bundle = archive.read(UNITY_DATA_MEMBER)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise AchievementImportError("could not read the APK's Unity data bundle") from error

    environment = UnityPy.load(io.BytesIO(bundle))
    script_path_ids = {
        object_.path_id
        for object_ in environment.objects
        if object_.type.name == "MonoScript"
        and str(getattr(object_.read(), "m_ClassName", "")) == ACHIEVEMENT_SET_CLASS
    }
    if not script_path_ids:
        raise AchievementImportError(f"the APK declares no {ACHIEVEMENT_SET_CLASS} script")

    raw: bytes | None = None
    for object_ in environment.objects:
        if object_.type.name != "MonoBehaviour":
            continue
        script = getattr(object_.read(check_read=False), "m_Script", None)
        if getattr(script, "path_id", None) in script_path_ids:
            if raw is not None:
                raise AchievementImportError(f"the APK carries more than one {ACHIEVEMENT_SET_CLASS}")
            raw = object_.get_raw_data()
    if raw is None:
        raise AchievementImportError(f"the APK carries no {ACHIEVEMENT_SET_CLASS} instance")

    reader = _Reader(raw, _ARRAY_OFFSET)
    declared = reader.int32()
    if not 0 < declared < 10_000:
        raise AchievementImportError(f"achievement master declares an implausible count {declared}")
    records = tuple(_record(reader) for _ in range(declared))
    # The parse is self-validating: a wrong field width desynchronises every
    # later record, and the array is the whole object, so anything but an exact
    # consumption means the layout is wrong rather than merely unexpected.
    if reader.offset != len(raw):
        raise AchievementImportError(
            f"achievement master left {len(raw) - reader.offset} byte(s) unread; the layout is wrong"
        )
    identifiers = [record.id for record in records]
    if len(set(identifiers)) != len(identifiers):
        raise AchievementImportError("achievement master repeats an id")
    digest = hashlib.sha256(apk.read_bytes()).hexdigest()
    return AchievementMaster(records, digest)


def write_achievement_catalog(master: AchievementMaster, output: Path) -> Path:
    """Write the recovered master as a runtime catalog."""
    document = {
        "schema_version": 1,
        "provenance": "user-derived",
        "source": {
            "apk_sha256": master.apk_sha256,
            "asset": UNITY_DATA_MEMBER,
            "script": ACHIEVEMENT_SET_CLASS,
        },
        "show_flags": list(master.show_flags()),
        "achievements": [
            {
                "id": record.id, "key": record.key, "show_flag": record.show_flag,
                "icon": record.icon, "parent_id": record.parent_id, "priority": record.priority,
                "unlock_type": record.unlock_type, "unlock_values": list(record.unlock_values),
                "device_type": record.device_type,
                "presents": [
                    {"type": present.type, "id": present.id, "num": present.num}
                    for present in record.presents
                ],
            }
            for record in master.records
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def main() -> int:
    import argparse  # noqa: PLC0415 -- only the command line needs it

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--force", action="store_true", help="overwrite an existing output")
    arguments = parser.parse_args()
    if arguments.output.exists() and not arguments.force:
        raise SystemExit(f"{arguments.output} already exists; pass --force to replace it")
    try:
        master = recover_achievement_master(arguments.apk)
        write_achievement_catalog(master, arguments.output)
    except AchievementImportError as error:
        raise SystemExit(f"achievement import failed: {error}") from error
    visible = sum(1 for record in master.records if record.visible)
    print(
        f"Recovered {len(master.records)} achievements ({visible} listed, "
        f"{len(master.records) - visible} hidden in the final client) to {arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
