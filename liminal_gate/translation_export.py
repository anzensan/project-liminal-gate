"""Export the client's own localized strings as a translator-editable CSV.

The final client already carries a `LocalizedString` for every character, item,
and Companion name and description, with a slot for each of the six languages it
shipped: `en`, `ja`, `fr`, `de`, `es`, and `zh_tw`.  The Spanish slots are
partly filled -- an official translation that covers early names and items and
then stops -- so a translation project is a gap-filling job, not a from-scratch
one, and this exporter is built to show the gaps.

Nothing here embeds game text.  Like :mod:`liminal_gate.master_strings`, it
decodes the operator's own APK on the operator's own machine, and it refuses to
write its output inside this source tree, because a filled-in sheet is exactly
the extracted asset content the project does not carry.

Two columns are worth explaining, because a translator will work from them:

`proven_chars` is the longest this same field is *already shipped* at, across
all six languages.  It is evidence rather than a guess: the client has rendered
that many characters in that label on real hardware.  A hard budget derived from
the English length alone would be false precision, and would reject the official
Spanish, which runs to 1.88x its English source in the widest case measured.

`occurrences` exists because the master tables repeat strings -- `ChrDatabase`'s
`data` array carries one row per character *job*, so a single name recurs many
times.  Distinct source strings are emitted once, and re-applied to every row
that shares them, which both shrinks the job and makes an inconsistent
translation of the same string impossible to introduce.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any, Iterator
import zipfile

from liminal_gate.character_catalog_importer import load_master_trees
from liminal_gate.file_digests import sha256_file
from liminal_gate.master_strings import (
    MasterStringError, decrypt_encrypted_string, load_inverse_table,
)
from liminal_gate.reviewed_build import APK_DATA_MEMBER, IL2CPP_METADATA_MEMBER


class TranslationExportError(ValueError):
    """The master data could not be read, or the destination is not allowed."""


#: Every slot `LocalizedString` declares, in field order (TypeDefIndex 3847).
LANGUAGES = ("en", "ja", "fr", "de", "es", "zh_tw")
SOURCE_LANGUAGE = "en"
DEFAULT_TARGET = "es"

#: Each exported field, as (category, master object, array, field). The category
#: is what a translator sees and sorts by, so it is worded for a reader who will
#: never open the master data itself.
EXPORTED_FIELDS = (
    ("character name", "ChrDatabase", "infos", "NameString"),
    ("character title", "ChrDatabase", "data", "NameString"),
    ("character profile", "ChrDatabase", "data", "ProfileString"),
    ("item name", "ItemSet", "itemSet", "NameString"),
    ("item description", "ItemSet", "itemSet", "DescString"),
    ("companion name", "BuddyDatabase", "data", "NameString"),
    ("companion description", "BuddyDatabase", "data", "DescString"),
)
MASTER_OBJECTS = ("ChrDatabase", "ItemSet", "BuddyDatabase")

#: `StringSet` holds the UI labels, chapter titles, and scenario text. It needs
#: its own loader rather than `load_master_trees`, because its generated type
#: tree cannot be used whole: the generator types `ngwords` (a `string[]`) as a
#: plain `string`, which consumes the wrong bytes and makes the following `lang`
#: field read off the end of the object. Every array this exporter wants is
#: stored *before* that field, so the tree is truncated after `scenarioSet` and
#: the two unreadable trailing fields are never read. Neither is translatable --
#: `ngwords` is a profanity filter and `lang` a default -- so nothing is lost.
STRING_SET_FILE = "resources.assets"
STRING_SET_PATH_ID = 12702
STRING_SET_ASSEMBLY = "Assembly-CSharp-firstpass.dll"
STRING_SET_CLASS = "StringSet"
#: The root fields, in serialized order, up to and including the last one read.
STRING_SET_PREFIX = (
    "m_GameObject", "m_Enabled", "m_Script", "m_Name", "chapterSet", "uiSet", "scenarioSet",
)

#: `StringSet`'s arrays hold `StringData`, which *is* a `LocalizedString` -- the
#: language slots sit on the record itself rather than under a named field, so
#: these are collected differently from the master-data tables above.
STRING_SET_FIELDS = (
    ("ui text", "uiSet"),
    ("chapter text", "chapterSet"),
    ("story text", "scenarioSet"),
)


def load_string_set(apk: Path, dummy_dll_dir: Path) -> dict[str, Any]:
    """Read `StringSet` with a tree truncated to the fields that decode."""
    try:
        import UnityPy
        from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator
    except ImportError as error:
        raise TranslationExportError(
            "reading StringSet requires UnityPy==1.25.2 and TypeTreeGeneratorAPI==0.0.10; "
            "install the master-import optional dependency"
        ) from error
    try:
        dlls = sorted(dummy_dll_dir.resolve(strict=True).glob("*.dll"))
    except OSError as error:
        raise TranslationExportError("local dummy-DLL directory is unavailable") from error
    try:
        with zipfile.ZipFile(apk) as archive:
            payload = archive.read(APK_DATA_MEMBER)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise TranslationExportError("APK does not contain the reviewed data.unity3d member") from error
    try:
        environment = UnityPy.load(payload)
        generator = TypeTreeGenerator("2017.4.37f1")
        for dll in dlls:
            generator.load_dll(dll.read_bytes())
        environment.typetree_generator = generator
        matches = [
            obj for obj in environment.objects
            if obj.assets_file.name == STRING_SET_FILE and obj.path_id == STRING_SET_PATH_ID
        ]
        if len(matches) != 1:
            raise TranslationExportError(f"expected one StringSet object, found {len(matches)}")
        root = generator.get_nodes_up(STRING_SET_ASSEMBLY, STRING_SET_CLASS)
        fields = tuple(child.m_Name for child in root.m_Children)
        # The truncation is only sound while the serialized order is the one it
        # was derived from. A different build that reorders or inserts a field
        # must fail here rather than quietly decode the wrong bytes.
        if fields[: len(STRING_SET_PREFIX)] != STRING_SET_PREFIX:
            raise TranslationExportError(
                f"StringSet field order is not the reviewed one; expected {STRING_SET_PREFIX} "
                f"but this build begins {fields[: len(STRING_SET_PREFIX)]}"
            )
        root.m_Children = list(root.m_Children)[: len(STRING_SET_PREFIX)]
        tree = matches[0].read_typetree(nodes=root, check_read=False)
    except TranslationExportError:
        raise
    except Exception as error:
        raise TranslationExportError(
            f"could not read StringSet with local type trees: {type(error).__name__}: {error}"
        ) from error
    if not isinstance(tree, dict):
        raise TranslationExportError("StringSet did not decode to an object")
    return tree

CATEGORY_ORDER = tuple(c for c, *_ in EXPORTED_FIELDS) + tuple(c for c, _ in STRING_SET_FIELDS)

COLUMNS = (
    "key", "category", "status", "english", "current_translation",
    "translation", "notes", "english_chars", "proven_chars", "occurrences",
)

#: Written into `status` so a translator can filter the sheet to real work.
STATUS_MISSING = "missing"
STATUS_UNTRANSLATED = "same as english"
STATUS_DONE = "already translated"


def _decode(value: object, inverse_table: bytes) -> str:
    """Decode one slot, treating an unusable slot as absent rather than fatal.

    A slot that is empty and a slot that is malformed are the same thing to a
    translator -- both mean "no text here" -- and one bad record should not cost
    the other several thousand.
    """
    if not isinstance(value, dict):
        return ""
    try:
        return decrypt_encrypted_string(value, inverse_table).strip()
    except MasterStringError:
        return ""


def _rows_for(trees: dict[str, Any], obj: str, array: str) -> Iterator[tuple[str, dict]]:
    """Yield `(id, record)` for one master array, keyed the way the game keys it.

    `ItemSet` records carry no ID of their own -- an item's ID is its position,
    one-based -- which is the same rule :mod:`liminal_gate.master_strings` uses.
    """
    tree = trees.get(obj)
    records = tree.get(array) if isinstance(tree, dict) else None
    if not isinstance(records, list) or not records:
        raise TranslationExportError(f"{obj}.{array} is missing or empty in this APK")
    for index, record in enumerate(records, 1):
        if not isinstance(record, dict):
            continue
        identifier = record.get("ID")
        yield (str(identifier) if type(identifier) is int else str(index)), record


def _collect(
    collected: dict[tuple[str, str], dict[str, Any]], category: str, identifier: str,
    localized: object, inverse_table: bytes, target: str,
) -> None:
    """Fold one localized record into the deduplicated row set."""
    if not isinstance(localized, dict):
        return
    english = _decode(localized.get(SOURCE_LANGUAGE), inverse_table)
    if not english:
        # Untranslatable by definition: there is no source text to work from.
        # A row like this needs an authoring decision, not a translator, so it
        # is left out rather than shipped as a blank.
        return
    existing = _decode(localized.get(target), inverse_table)
    shipped = max(len(_decode(localized.get(code), inverse_table)) for code in LANGUAGES)
    key = (category, english)
    row = collected.get(key)
    if row is None:
        collected[key] = {
            "key": f"{category.replace(' ', '-')}:{identifier}",
            "category": category,
            "status": (
                STATUS_MISSING if not existing
                else STATUS_UNTRANSLATED if existing == english
                else STATUS_DONE
            ),
            "english": english,
            "current_translation": existing,
            "translation": "",
            "notes": "",
            "english_chars": len(english),
            "proven_chars": shipped,
            "occurrences": 1,
        }
    else:
        row["occurrences"] += 1
        row["proven_chars"] = max(row["proven_chars"], shipped)


def build_rows(
    trees: dict[str, Any], inverse_table: bytes, target: str = DEFAULT_TARGET,
    string_set: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Collapse the master tables into one deduplicated row per source string."""
    if target not in LANGUAGES:
        raise TranslationExportError(
            f"{target!r} is not a language this client carries; expected one of {', '.join(LANGUAGES)}"
        )
    if target == SOURCE_LANGUAGE:
        raise TranslationExportError("the target language cannot be the source language")
    collected: dict[tuple[str, str], dict[str, Any]] = {}
    for category, obj, array, field in EXPORTED_FIELDS:
        for identifier, record in _rows_for(trees, obj, array):
            _collect(collected, category, identifier, record.get(field), inverse_table, target)
    for category, array in STRING_SET_FIELDS:
        if string_set is None:
            continue
        records = string_set.get(array)
        if not isinstance(records, list) or not records:
            raise TranslationExportError(f"StringSet.{array} is missing or empty in this APK")
        # A StringData *is* a LocalizedString, so the record itself carries the
        # language slots. Its id is its position, which is the ordinal of the
        # enum the client indexes the array with.
        for index, record in enumerate(records):
            _collect(collected, category, str(index), record, inverse_table, target)
    if not collected:
        raise TranslationExportError("no source strings decoded; this APK is not the reviewed build")
    order = {category: index for index, category in enumerate(CATEGORY_ORDER)}
    return sorted(collected.values(), key=lambda row: (order[row["category"]], -row["occurrences"], row["english"]))


#: Tracked directories a filled-in sheet must never land in. `user-data/` is
#: deliberately absent: it is gitignored and is where every other importer here
#: puts its user-derived output, so it is the expected destination.
PROTECTED_DIRECTORIES = ("liminal_gate", "docs", "tests", "protocol", "scripts", "deploy", "profiles")


def _checked_destination(path: Path) -> Path:
    """Refuse to write decoded game text into a tracked directory.

    The sheet carries the client's own strings, which is precisely the extracted
    asset content this project does not distribute. Landing one in a tracked
    directory would be a licensing problem committed by accident, so the export
    fails loudly instead.
    """
    destination = path.expanduser().resolve()
    source_tree = Path(__file__).resolve().parent.parent
    for name in PROTECTED_DIRECTORIES:
        protected = source_tree / name
        if destination == protected or protected in destination.parents:
            raise TranslationExportError(
                f"refusing to write decoded game text into the tracked directory {protected}; "
                f"write it to a gitignored location such as {source_tree / 'user-data'}"
            )
    return destination


def write_sheet(path: Path, rows: list[dict[str, Any]]) -> Path:
    """Write the translator's CSV, encoded so a spreadsheet opens it correctly.

    `utf-8-sig` rather than plain UTF-8: without the byte-order mark Excel
    decodes the file as the local codepage and mangles every accent, which is a
    silent corruption a non-technical translator would have no way to diagnose.
    """
    destination = _checked_destination(path)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(COLUMNS))
            writer.writeheader()
            writer.writerows(rows)
    except OSError as error:
        raise TranslationExportError(f"could not write {destination}: {error}") from error
    return destination


def summarize(rows: list[dict[str, Any]]) -> list[str]:
    """Report per-category coverage, which is what decides whether this is worth doing."""
    lines = []
    for category in CATEGORY_ORDER:
        group = [row for row in rows if row["category"] == category]
        if not group:
            continue
        done = sum(1 for row in group if row["status"] == STATUS_DONE)
        lines.append(f"  {category:<22} {len(group):>5} strings, {done:>4} already translated ({done / len(group):.0%})")
    return lines


def export(apk: Path, dummy_dll_dir: Path, output: Path, target: str = DEFAULT_TARGET) -> tuple[Path, list[str]]:
    """Read the operator's APK and write one translator-editable sheet."""
    try:
        with zipfile.ZipFile(apk) as archive:
            inverse_table = load_inverse_table(archive.read(IL2CPP_METADATA_MEMBER))
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise TranslationExportError("APK does not contain the reviewed IL2CPP metadata member") from error
    except MasterStringError as error:
        raise TranslationExportError(str(error)) from error
    trees = load_master_trees(apk, dummy_dll_dir, MASTER_OBJECTS)
    string_set = load_string_set(apk, dummy_dll_dir)
    rows = build_rows(trees, inverse_table, target, string_set)
    return write_sheet(output, rows), summarize(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export client strings as a translator-editable CSV.")
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument("--dummy-dll-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="destination CSV, outside this source tree")
    parser.add_argument("--target-language", default=DEFAULT_TARGET, choices=[c for c in LANGUAGES if c != SOURCE_LANGUAGE])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        apk = args.apk.resolve(strict=True)
        destination, summary = export(apk, args.dummy_dll_dir, args.output, args.target_language)
    except (TranslationExportError, OSError) as error:
        raise SystemExit(f"translation export failed: {error}") from error
    print(f"wrote translator sheet: {destination}")
    print(f"source APK sha256: {sha256_file(apk)}")
    for line in summary:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
