"""Derive the local Pact banner PNGs required by the reviewed Android client."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile
import zipfile


class PactBannerImportError(ValueError):
    """User-local banner inputs or optional extraction tooling are unavailable."""


METADATA_MEMBER = "assets/bin/Data/Managed/Metadata/global-metadata.dat"
MAGIC = b"ENCA"
FORWARD_TABLE_OFFSET = 0x601BAD
INVERSE_TABLE_OFFSET = 0x601CAD
TABLE_SIZE = 256
FORWARD_TABLE_SHA1 = "d2b37ec3ab3e6174465daf8661396e710fb31867"
INVERSE_TABLE_SHA1 = "35f949bc321303b064a418f45a93bb5b2056c0b1"
PactBanner = tuple[str, str]
PACT_BANNERS: tuple[PactBanner, ...] = (
    ("sl_truth_01", "f66e8ffea74d9c1be227039f35cc0ec9sl_truth_01.bin"),
    ("sl_friend_01", "79261d8212253267c8852fcdac65c803sl_friend_01.bin"),
    ("slb_truth_01", "a8d4944c472e83b3b4b044d8a5be8953slb_truth_01.bin"),
    ("slb_friend_01", "e2a4f7553d46450a19a88158315d959dslb_friend_01.bin"),
)


def _sha1(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def _load_inverse_table(apk: Path) -> bytes:
    try:
        with zipfile.ZipFile(apk) as archive:
            metadata = archive.read(METADATA_MEMBER)
    except (OSError, KeyError, zipfile.BadZipFile) as error:
        raise PactBannerImportError("could not read the reviewed APK metadata") from error
    forward = metadata[FORWARD_TABLE_OFFSET : FORWARD_TABLE_OFFSET + TABLE_SIZE]
    inverse = metadata[INVERSE_TABLE_OFFSET : INVERSE_TABLE_OFFSET + TABLE_SIZE]
    if len(forward) != TABLE_SIZE or _sha1(forward) != FORWARD_TABLE_SHA1:
        raise PactBannerImportError("the APK does not contain the reviewed banner decode table")
    if len(inverse) != TABLE_SIZE or _sha1(inverse) != INVERSE_TABLE_SHA1:
        raise PactBannerImportError("the APK does not contain the reviewed banner decode table")
    if any(inverse[forward[value]] != value for value in range(TABLE_SIZE)):
        raise PactBannerImportError("the APK banner decode tables are inconsistent")
    return inverse


def _calc_index(index: int, size: int) -> int:
    low = index & 0xFF
    if (index >> 8) != ((size - 1) >> 8):
        low ^= 0xFF
    return (index & ~0xFF) | low


def _transform_byte(value: int) -> int:
    return ((value >> 4) | ((value & 0x0F) << 4)) ^ 0xFF


def decrypt_enca(source: bytes, inverse_table: bytes) -> bytes:
    """Decode a reviewed local ENCA bundle without retaining a decoded bundle."""
    if not source.startswith(MAGIC):
        return source
    size = len(source) - len(MAGIC)
    if size == 0:
        return b""
    plain = bytearray(size)
    for source_index, value in enumerate(source[len(MAGIC) :]):
        plain[_calc_index(size - 1 - source_index, size)] = _transform_byte(inverse_table[value])
    return bytes(plain)


def prepare_pact_banners(apk: Path, resource_root: Path, output_root: Path) -> Path:
    """Extract four user-local Unity texture bundles as locally served PNGs."""
    try:
        import UnityPy
    except ImportError as error:
        raise PactBannerImportError(
            "Pact banner extraction requires UnityPy; install it with: python3 -m pip install '.[master-import]'"
        ) from error
    inverse = _load_inverse_table(apk)
    banner_root = output_root / "banners"
    banner_root.mkdir(parents=True, exist_ok=True)
    for name, filename in PACT_BANNERS:
        source = resource_root / "Banner" / filename
        if not source.is_file():
            raise PactBannerImportError(f"required local Pact banner is unavailable: Banner/{filename}")
        environment = UnityPy.load(decrypt_enca(source.read_bytes(), inverse))
        texture = next((item.read() for item in environment.objects if item.type.name == "Texture2D"), None)
        if texture is None:
            raise PactBannerImportError(f"local Pact banner has no Texture2D: Banner/{filename}")
        output = banner_root / f"{name}_en.png"
        with tempfile.NamedTemporaryFile(dir=banner_root, suffix=".png", delete=False) as stream:
            temporary = Path(stream.name)
        try:
            texture.image.save(temporary, format="PNG")
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)
    return banner_root
