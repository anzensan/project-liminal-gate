"""Derive missing Attack of Coin Creeps bundles from retained client artwork."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

from liminal_gate.pact_banner_importer import (
    MAGIC,
    _calc_index,
    _load_decode_tables,
    _transform_byte,
    decrypt_enca,
)


class CoinCreepsBannerError(ValueError):
    """The reviewed local fallback could not be derived safely."""


SOURCE_NAME = "sp3003-1"
ALIASES = ("sp1003-1", "sp1003-2", "sp1003-3")
RESOURCE_HASH_SALT = "tbguardmistkeycodehiso"


def hashed_resource_name(logical_name: str) -> str:
    digest = hashlib.md5((logical_name + RESOURCE_HASH_SALT).encode("utf-8")).hexdigest()
    return f"{digest}{logical_name}.bin"


def _encrypt_enca(source: bytes, forward_table: bytes) -> bytes:
    """Invert the reviewed ENCA decoder for a locally derived Unity bundle."""
    size = len(source)
    encrypted = bytearray(size)
    for output_index in range(size):
        source_index = _calc_index(size - 1 - output_index, size)
        encrypted[output_index] = forward_table[_transform_byte(source[source_index])]
    return MAGIC + bytes(encrypted)


def _find_unique_bundle(resource_root: Path, logical_name: str) -> Path | None:
    matches = tuple(sorted((resource_root / "Banner").glob(f"*{logical_name}.bin")))
    if len(matches) > 1:
        raise CoinCreepsBannerError(f"local Banner/*{logical_name}.bin is ambiguous")
    return matches[0] if matches else None


def prepare_coin_creeps_banners(apk: Path, resource_root: Path, output_root: Path) -> Path:
    """Create only the missing sp1003 transport bundles under ignored local data."""
    banner_root = output_root / "banner_resources"
    banner_root.mkdir(parents=True, exist_ok=True)
    missing = []
    for alias in ALIASES:
        if _find_unique_bundle(resource_root, alias) is None:
            missing.append(alias)
        else:
            # An exact resource added after an earlier setup must supersede and
            # remove the now-stale derived fallback served ahead of the manifest.
            (banner_root / hashed_resource_name(alias)).unlink(missing_ok=True)
    if not missing:
        return banner_root
    source = _find_unique_bundle(resource_root, SOURCE_NAME)
    if source is None:
        raise CoinCreepsBannerError(
            "Attack of Coin Creeps has no exact local banner and the retained "
            "Banner/*sp3003-1.bin fallback is unavailable"
        )
    try:
        import UnityPy
    except ImportError as error:
        raise CoinCreepsBannerError(
            'Coin Creeps banner derivation requires the pinned master-import extra: pip install ".[master-import]"'
        ) from error
    forward, inverse = _load_decode_tables(apk)
    decoded = decrypt_enca(source.read_bytes(), inverse)
    for alias in missing:
        try:
            environment = UnityPy.load(decoded)
            textures = [item.read() for item in environment.objects if item.type.name == "Texture2D"]
            bundles = [item.read() for item in environment.objects if item.type.name == "AssetBundle"]
            if len(textures) != 1 or textures[0].m_Name != SOURCE_NAME or len(bundles) != 1:
                raise CoinCreepsBannerError(
                    f"retained {SOURCE_NAME} bundle does not have the reviewed one-texture layout"
                )
            texture = textures[0]
            bundle = bundles[0]
            expected_path = f"assets/images/banner/{SOURCE_NAME}.png"
            if len(bundle.m_Container) != 1 or bundle.m_Container[0][0] != expected_path:
                raise CoinCreepsBannerError(
                    f"retained {SOURCE_NAME} bundle has an unexpected container path"
                )
            texture.m_Name = alias
            texture.save()
            bundle.m_Container[0] = (
                f"assets/images/banner/{alias}.png",
                bundle.m_Container[0][1],
            )
            filename = hashed_resource_name(alias)
            bundle.m_Name = filename
            bundle.m_AssetBundleName = filename
            bundle.save()
            writable = [item for item in environment.files.values() if hasattr(item, "save")]
            if len(writable) != 1:
                raise CoinCreepsBannerError("retained Coin Creeps resource is not one writable Unity bundle")
            encoded = _encrypt_enca(writable[0].save(packer="original"), forward)
            output = banner_root / filename
            with tempfile.NamedTemporaryFile(dir=banner_root, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.replace(temporary, output)
            finally:
                temporary.unlink(missing_ok=True)
        except CoinCreepsBannerError:
            raise
        except (AttributeError, OSError, TypeError, ValueError) as error:
            raise CoinCreepsBannerError(f"could not derive {alias} card bundle: {error}") from error
    return banner_root
