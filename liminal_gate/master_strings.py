"""Decode the client's own encrypted master-data strings, locally.

The client stores every localized name and description as an `EncryptedString`:
a byte array run through a 256-entry substitution table and reversed.  Both
tables live in the user's own `global-metadata.dat`, so nothing here embeds game
text -- it reads the tester's copy and decodes it on their machine.

The substitution is checked by digest before use.  A wrong offset would still
"decode" to something, just to nonsense, and nonsense names in a save editor are
worse than no names at all.
"""

from __future__ import annotations

import hashlib
from typing import Any


#: Both tables sit at fixed offsets in the 5.5.7 metadata and are verified
#: before use, so a different build fails loudly instead of decoding noise.
FORWARD_TABLE_OFFSET = 0x601BAD
INVERSE_TABLE_OFFSET = 0x601CAD
TABLE_SIZE = 256
FORWARD_TABLE_SHA1 = "d2b37ec3ab3e6174465daf8661396e710fb31867"
INVERSE_TABLE_SHA1 = "35f949bc321303b064a418f45a93bb5b2056c0b1"
#: The locale a local editor labels IDs with.
DEFAULT_LANGUAGE = "en"


class MasterStringError(ValueError):
    """The metadata substitution tables or an encrypted string are unusable."""


def load_inverse_table(metadata: bytes) -> bytes:
    """Return the verified inverse substitution table from IL2CPP metadata."""
    tables = {}
    for label, offset, expected in (
        ("forward", FORWARD_TABLE_OFFSET, FORWARD_TABLE_SHA1),
        ("inverse", INVERSE_TABLE_OFFSET, INVERSE_TABLE_SHA1),
    ):
        table = metadata[offset : offset + TABLE_SIZE]
        if len(table) != TABLE_SIZE or hashlib.sha1(table).hexdigest() != expected:
            raise MasterStringError(
                f"the {label} substitution table is missing or does not match the reviewed "
                f"5.5.7 metadata; names cannot be decoded from this build"
            )
        tables[label] = table
    return tables["inverse"]


def decrypt_encrypted_string(value: object, inverse_table: bytes) -> str:
    """Reproduce the client's `EncryptedString.decrypt` (ARM64 RVA 0x1078014)."""
    if len(inverse_table) != TABLE_SIZE:
        raise MasterStringError("the inverse substitution table must be 256 bytes")
    data = value.get("data") if isinstance(value, dict) else None
    if not isinstance(data, list) or any(type(byte) is not int or not 0 <= byte <= 255 for byte in data):
        raise MasterStringError("an EncryptedString must carry a byte-list data field")
    # Substituted and reversed: the last plaintext byte comes from the first
    # ciphertext byte.
    plaintext = bytearray(len(data))
    for index, byte in enumerate(data):
        plaintext[len(data) - 1 - index] = inverse_table[byte]
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as error:
        raise MasterStringError("an EncryptedString did not decode to UTF-8") from error


def build_character_names(tree: object, inverse_table: bytes, language: str = DEFAULT_LANGUAGE) -> dict[str, str]:
    """Map character ID to name from a ChrDatabase tree the caller already read.

    `infos` is the authority: it carries one record per character, keyed by the
    same ID a save's roster uses.  The sibling `data` table holds a longer
    titled form but repeats each character once per job, so it cannot be keyed
    by character ID and is deliberately not used here.
    """
    infos = tree.get("infos") if isinstance(tree, dict) else None
    if not isinstance(infos, list) or not infos:
        raise MasterStringError("ChrDatabase must contain a nonempty infos array")
    names: dict[str, str] = {}
    for record in infos:
        if not isinstance(record, dict) or type(record.get("ID")) is not int:
            continue
        localized = record.get("NameString")
        if not isinstance(localized, dict) or language not in localized:
            continue
        name = decrypt_encrypted_string(localized[language], inverse_table)
        if name:
            names[str(record["ID"])] = name
    if not names:
        raise MasterStringError(f"no character names decoded for language {language!r}")
    return names


def build_name_file(characters: dict[str, str], apk_sha256: str, language: str = DEFAULT_LANGUAGE) -> dict[str, Any]:
    """Wrap decoded names in the shape the local save editor reads."""
    return {
        "schema_version": 1,
        "provenance": "decoded-from-user-apk",
        "language": language,
        "source_sha256": apk_sha256,
        "characters": dict(sorted(characters.items(), key=lambda pair: int(pair[0]))),
        # Item and Companion names come from the ItemSet and BuddyDatabase
        # objects, which this importer does not read yet.
        "items": {},
    }
