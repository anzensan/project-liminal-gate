"""Assemble the unsigned, private on-device Liminal Gate APK.

The assembler deliberately does not sign or align its output. It accepts only
the output of the separately reviewed loopback-literal patch: that patcher must
first verify the immutable original APK digest, then this module verifies the
resulting patched APK digest. It retains the patched APK's local ZIP records
byte-for-byte where no declared manifest edit is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import mimetypes
from pathlib import Path, PurePosixPath
import struct
import zlib
import zipfile

from liminal_gate.resource_catalog_builder import resource_url_aliases


SOURCE_ACTIVITY = "com.unity3d.player.UnityPlayerActivity"
HOST_ACTIVITY = "org.liminalgate.android.HostedActivity"
PACKAGED_PREFIX = "assets/liminal_gate/"
PACKAGED_RESOURCES_PREFIX = PACKAGED_PREFIX + "resources/"
PACKAGED_CATALOGS_PREFIX = PACKAGED_PREFIX + "catalogs/"
PACKAGED_RUNTIME_PREFIX = PACKAGED_PREFIX + "runtime/"
PACKAGED_MANIFEST = PACKAGED_PREFIX + "packaged-resource-manifest.json"
PACKAGED_SEED_STATE = PACKAGED_PREFIX + "seed-state.json"
PACKAGED_RESOURCE_MANIFEST_SCHEMA_VERSION = 2
SIGNATURE_SUFFIXES = (".EC", ".RSA", ".DSA", ".SF")
IGNORED_HOST_MEMBERS = frozenset({
    "AndroidManifest.xml",
    "resources.arsc",
    "META-INF/com/android/build/gradle/app-metadata.properties",
})


class OnDeviceApkError(ValueError):
    """An APK input cannot safely be combined."""


@dataclass(frozen=True)
class AssemblyResult:
    output_sha256: str
    resource_count: int
    catalog_count: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def assemble_on_device_apk(
    patched_apk: Path,
    host_apk: Path,
    output_apk: Path,
    *,
    patched_sha256: str,
    resource_root: Path,
    catalogs: dict[str, Path] | None = None,
    runtime_files: dict[str, Path] | None = None,
    build_id: str = "",
    seed_state: Path | None = None,
) -> AssemblyResult:
    """Merge a patched Terra Battle APK and host payload into an unsigned APK.

    ``catalogs`` maps a short safe catalog name to its generated local file.
    Resources and catalogs are intentionally stored, not compressed: the
    packaged manifest names their exact APK members and SHA-256 digests.
    """
    if patched_apk.resolve() == output_apk.resolve() or host_apk.resolve() == output_apk.resolve():
        raise OnDeviceApkError("output APK must differ from both inputs")
    if not _is_sha256(patched_sha256) or sha256_file(patched_apk) != patched_sha256:
        raise OnDeviceApkError("patched APK SHA-256 does not match the reviewed patched base")
    resources = _resource_members(resource_root)
    if not _is_sha256(build_id):
        raise OnDeviceApkError("build_id must be exactly 64 lowercase hexadecimal characters")
    catalog_files = _catalog_members(catalogs or {})
    runtime_members = _runtime_members(runtime_files or {})
    seed_member = _seed_member(seed_state)
    try:
        source = zipfile.ZipFile(patched_apk)
        host = zipfile.ZipFile(host_apk)
    except zipfile.BadZipFile as error:
        raise OnDeviceApkError("APK input is not a readable ZIP archive") from error
    with source, host:
        _validate_archive(source, "source")
        _validate_archive(host, "host")
        _require_dual_abi_native_payload(source, "patched base")
        _require_dual_abi_native_payload(host, "host")
        source_names = {info.filename for info in source.infolist() if not _is_signature(info.filename)}
        source_cases = {name.casefold(): name for name in source_names}
        manifest = _one_info(source, "AndroidManifest.xml", "source")
        patched_manifest = patch_binary_manifest(source.read(manifest))
        additions = _host_additions(host, source_names, source_cases)
        extra_names = [name for name, _ in additions] + [name for name, _ in resources] + [name for name, _ in catalog_files] + [name for name, _ in runtime_members] + ([seed_member[0]] if seed_member else []) + [PACKAGED_MANIFEST]
        _validate_new_names(extra_names, source_names, source_cases)
        output_apk.parent.mkdir(parents=True, exist_ok=True)
        _write_combined(patched_apk, source, output_apk, patched_manifest, additions, resources, catalog_files, runtime_members, seed_member, build_id)
    return AssemblyResult(sha256_file(output_apk), len(resources), len(catalog_files))


def patch_binary_manifest(data: bytes) -> bytes:
    """Patch only the expected activity string and typed minSdk value 16 -> 24."""
    if len(SOURCE_ACTIVITY) != len(HOST_ACTIVITY):
        raise AssertionError("activity replacement must remain length-preserving")
    replacements = [
        (SOURCE_ACTIVITY.encode("utf-8"), HOST_ACTIVITY.encode("utf-8")),
        (SOURCE_ACTIVITY.encode("utf-16le"), HOST_ACTIVITY.encode("utf-16le")),
    ]
    occurrences = sum(data.count(old) for old, _ in replacements)
    if occurrences != 1:
        raise OnDeviceApkError("AndroidManifest.xml must contain exactly one expected activity string")
    patched = data
    for old, new in replacements:
        if old in patched:
            patched = patched.replace(old, new, 1)
    strings = _axml_strings(patched)
    min_sdk_offsets = _axml_min_sdk_offsets(patched, strings)
    if len(min_sdk_offsets) != 1:
        raise OnDeviceApkError("AndroidManifest.xml must contain exactly one typed minSdkVersion")
    offset = min_sdk_offsets[0]
    value = struct.unpack_from("<I", patched, offset)[0]
    if value != 16:
        raise OnDeviceApkError("AndroidManifest.xml minSdkVersion is not the expected value 16")
    return patched[:offset] + struct.pack("<I", 24) + patched[offset + 4:]


def _resource_members(root: Path) -> list[tuple[str, Path]]:
    try:
        root = root.resolve(strict=True)
    except OSError as error:
        raise OnDeviceApkError("resource root is unavailable") from error
    if not root.is_dir():
        raise OnDeviceApkError("resource root must be a directory")
    result: list[tuple[str, Path]] = []
    for file in sorted(root.rglob("*")):
        if file.is_symlink():
            raise OnDeviceApkError("resource root must not contain symbolic links")
        if file.is_file():
            relative = file.relative_to(root).as_posix()
            _safe_name(relative)
            result.append((PACKAGED_RESOURCES_PREFIX + relative, file))
    if not result:
        raise OnDeviceApkError("resource root contains no regular files")
    return result


def _catalog_members(catalogs: dict[str, Path]) -> list[tuple[str, Path]]:
    result = []
    for name, path in sorted(catalogs.items()):
        if not isinstance(name, str) or not name or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for c in name):
            raise OnDeviceApkError("catalog names must be lowercase safe filenames")
        try:
            path = path.resolve(strict=True)
        except OSError as error:
            raise OnDeviceApkError(f"catalog is unavailable: {name}") from error
        if not path.is_file() or path.is_symlink():
            raise OnDeviceApkError(f"catalog must be a regular file: {name}")
        result.append((PACKAGED_CATALOGS_PREFIX + name, path))
    return result


def _runtime_members(files: dict[str, Path]) -> list[tuple[str, Path]]:
    """Return small generated runtime inputs that Android extracts on first launch."""
    result = []
    for name, path in sorted(files.items()):
        _safe_name(name)
        try:
            path = path.resolve(strict=True)
        except OSError as error:
            raise OnDeviceApkError(f"runtime file is unavailable: {name}") from error
        if not path.is_file() or path.is_symlink():
            raise OnDeviceApkError(f"runtime file must be a regular file: {name}")
        result.append((PACKAGED_RUNTIME_PREFIX + name, path))
    return result


def _seed_member(seed_state: Path | None) -> tuple[str, Path] | None:
    if seed_state is None:
        return None
    try:
        seed_state = seed_state.resolve(strict=True)
    except OSError as error:
        raise OnDeviceApkError("seed state is unavailable") from error
    if not seed_state.is_file() or seed_state.is_symlink():
        raise OnDeviceApkError("seed state must be a regular file")
    return PACKAGED_SEED_STATE, seed_state


def _host_additions(host: zipfile.ZipFile, source_names: set[str], source_cases: dict[str, str]) -> list[tuple[str, bytes]]:
    dex = sorted((info for info in host.infolist() if _dex_number(info.filename) is not None), key=lambda item: _dex_number(item.filename) or 0)
    if not dex:
        raise OnDeviceApkError("host APK has no classes.dex payload")
    source_dex = [_dex_number(name) for name in source_names if _dex_number(name) is not None]
    next_dex = max(source_dex, default=0) + 1
    result: list[tuple[str, bytes]] = []
    for info in dex:
        _validate_host_payload_info(info)
        result.append(("classes" + ("" if next_dex == 1 else str(next_dex)) + ".dex", host.read(info)))
        next_dex += 1
    for info in host.infolist():
        name = info.filename
        if name.startswith(("assets/", "lib/")):
            _validate_host_payload_info(info)
            result.append((name, host.read(info)))
        elif name not in IGNORED_HOST_MEMBERS and _dex_number(name) is None and not _is_signature(name):
            raise OnDeviceApkError(f"unsupported host APK member: {name}")
    return result


def _write_combined(source_path: Path, source: zipfile.ZipFile, output_path: Path, patched_manifest: bytes, additions: list[tuple[str, bytes]], resources: list[tuple[str, Path]], catalogs: list[tuple[str, Path]], runtime_files: list[tuple[str, Path]], seed_member: tuple[str, Path] | None, build_id: str) -> None:
    original = source_path.read_bytes()
    infos = source.infolist()
    start_dir = source.start_dir
    with output_path.open("wb") as output:
        central: list[bytes] = []

        def emit(info: zipfile.ZipInfo, raw: bytes) -> None:
            offset = output.tell()
            if offset >= 0xFFFFFFFF:
                raise OnDeviceApkError("ZIP64 output is not supported")
            output.write(raw)
            central.append(_central_record(info, offset))

        for index, info in enumerate(infos):
            if _is_signature(info.filename):
                continue
            if info.filename == "AndroidManifest.xml":
                changed = _new_info(info.filename, info, patched_manifest, info.compress_type)
                emit(changed, _local_record(changed, patched_manifest))
                continue
            next_offset = infos[index + 1].header_offset if index + 1 < len(infos) else start_dir
            emit(info, original[info.header_offset:next_offset])
        for name, data in additions:
            # Android must be able to map extracted/native host libraries directly;
            # keep them stored like normal APK lib entries. Other host payload can
            # use ordinary deflate compression.
            compression = zipfile.ZIP_STORED if name.startswith("lib/") else zipfile.ZIP_DEFLATED
            added = _new_info(name, None, data, compression)
            emit(added, _local_record(added, data))
        manifest_resources = []
        # One stored member can answer to more than one URL, so the aliases all
        # point at the same member rather than packaging the bytes twice.
        mapped_paths: set[str] = set()
        for name, path in resources:
            data = path.read_bytes()
            added = _new_info(name, None, data, zipfile.ZIP_STORED)
            emit(added, _local_record(added, data))
            relative = name[len(PACKAGED_RESOURCES_PREFIX):]
            digest = hashlib.sha256(data).hexdigest()
            content_type = mimetypes.guess_type(relative)[0] or "application/octet-stream"
            for url in resource_url_aliases(relative):
                if url in mapped_paths:
                    raise OnDeviceApkError(f"resource root maps more than one file to {url}")
                mapped_paths.add(url)
                manifest_resources.append({"path": url, "member": name, "sha256": digest, "size": len(data), "content_type": content_type})
        manifest_catalogs = []
        for name, path in catalogs:
            data = path.read_bytes()
            added = _new_info(name, None, data, zipfile.ZIP_STORED)
            emit(added, _local_record(added, data))
            manifest_catalogs.append({"name": name[len(PACKAGED_CATALOGS_PREFIX):], "member": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        manifest_runtime = []
        for name, path in runtime_files:
            data = path.read_bytes()
            added = _new_info(name, None, data, zipfile.ZIP_STORED)
            emit(added, _local_record(added, data))
            manifest_runtime.append({"name": name[len(PACKAGED_RUNTIME_PREFIX):], "member": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
        manifest_seed = None
        if seed_member is not None:
            name, path = seed_member
            data = path.read_bytes()
            added = _new_info(name, None, data, zipfile.ZIP_STORED)
            emit(added, _local_record(added, data))
            manifest_seed = {"member": name, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        manifest_data = (json.dumps({"schema_version": PACKAGED_RESOURCE_MANIFEST_SCHEMA_VERSION, "build_id": build_id, "resources": manifest_resources, "catalogs": manifest_catalogs, "runtime": manifest_runtime, "seed": manifest_seed}, sort_keys=True, separators=(",", ":")) + "\n").encode()
        added = _new_info(PACKAGED_MANIFEST, None, manifest_data, zipfile.ZIP_STORED)
        emit(added, _local_record(added, manifest_data))
        central_offset = output.tell()
        for record in central:
            output.write(record)
        central_size = output.tell() - central_offset
        if len(central) >= 0xFFFF or central_offset >= 0xFFFFFFFF or central_size >= 0xFFFFFFFF:
            raise OnDeviceApkError("ZIP64 output is not supported")
        output.write(struct.pack("<IHHHHIIH", 0x06054B50, 0, 0, len(central), len(central), central_size, central_offset, 0))


def _new_info(name: str, template: zipfile.ZipInfo | None, data: bytes, compression: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=template.date_time if template else (1980, 1, 1, 0, 0, 0))
    info.compress_type = compression
    # Every changed/new name is explicitly UTF-8 encoded. Normalize away any
    # source compression flags as well as data-descriptor state so the local
    # and central records describe exactly the bytes emitted below.
    info.flag_bits = 0x800
    info.external_attr = template.external_attr if template else 0
    info.create_system = template.create_system if template else 3
    info.CRC = zlib.crc32(data) & 0xffffffff
    info.file_size = len(data)
    info.compress_size = len(_compressed(data, compression))
    return info


def _local_record(info: zipfile.ZipInfo, data: bytes) -> bytes:
    encoded = info.filename.encode("utf-8")
    packed = _compressed(data, info.compress_type)
    dostime, dosdate = _dos_time_date(info)
    return struct.pack(
        "<IHHHHHIIIHH",
        0x04034B50,
        info.extract_version,
        info.flag_bits,
        info.compress_type,
        dostime,
        dosdate,
        info.CRC,
        len(packed),
        len(data),
        len(encoded),
        0,
    ) + encoded + packed


def _compressed(data: bytes, compression: int) -> bytes:
    if compression == zipfile.ZIP_STORED:
        return data
    if compression == zipfile.ZIP_DEFLATED:
        compressor = zlib.compressobj(9, zlib.DEFLATED, -15)
        return compressor.compress(data) + compressor.flush()
    raise OnDeviceApkError("unsupported compression method for changed member")


def _central_record(info: zipfile.ZipInfo, offset: int) -> bytes:
    if offset >= 0xFFFFFFFF:
        raise OnDeviceApkError("ZIP64 output is not supported")
    name = info.filename.encode("utf-8")
    extra = info.extra
    comment = info.comment
    dostime, dosdate = _dos_time_date(info)
    return struct.pack("<IHHHHHHIIIHHHHHII", 0x02014B50, info.create_version, info.extract_version, info.flag_bits, info.compress_type, dostime, dosdate, info.CRC, info.compress_size, info.file_size, len(name), len(extra), len(comment), 0, info.internal_attr, info.external_attr, offset) + name + extra + comment


def _dos_time_date(info: zipfile.ZipInfo) -> tuple[int, int]:
    year, month, day, hour, minute, second = info.date_time
    return (
        (hour << 11) | (minute << 5) | (second // 2),
        ((year - 1980) << 9) | (month << 5) | day,
    )


def _validate_archive(archive: zipfile.ZipFile, label: str) -> None:
    if archive.start_dir >= 0xFFFFFFFF or len(archive.infolist()) >= 0xFFFF:
        raise OnDeviceApkError(f"{label} APK uses unsupported ZIP64 limits")
    names: set[str] = set()
    cases: set[str] = set()
    for info in archive.infolist():
        _safe_name(info.filename)
        if info.filename in names:
            raise OnDeviceApkError(f"{label} APK has duplicate member: {info.filename}")
        if info.filename.casefold() in cases:
            raise OnDeviceApkError(f"{label} APK has case-colliding member: {info.filename}")
        names.add(info.filename)
        cases.add(info.filename.casefold())
        if info.flag_bits & 0x1:
            raise OnDeviceApkError(f"{label} APK has encrypted member: {info.filename}")
        if info.file_size >= 0xFFFFFFFF or info.compress_size >= 0xFFFFFFFF or info.header_offset >= 0xFFFFFFFF:
            raise OnDeviceApkError(f"{label} APK uses unsupported ZIP64 limits")


def _require_dual_abi_native_payload(archive: zipfile.ZipFile, label: str) -> None:
    required = ("arm64-v8a", "armeabi-v7a")
    available = {
        info.filename.split("/", 2)[1]
        for info in archive.infolist()
        if info.filename.startswith("lib/") and info.filename.count("/") >= 2
        and info.filename.endswith(".so")
    }
    missing = [abi for abi in required if abi not in available]
    if missing:
        raise OnDeviceApkError(f"{label} APK is missing required native payload ABI: {', '.join(missing)}")


def _validate_host_payload_info(info: zipfile.ZipInfo) -> None:
    if info.flag_bits & 0x1:
        raise OnDeviceApkError(f"host payload member is encrypted: {info.filename}")
    if info.flag_bits & 0x8:
        raise OnDeviceApkError(f"host payload member uses an unsupported data descriptor: {info.filename}")


def _validate_new_names(names: list[str], source_names: set[str], source_cases: dict[str, str]) -> None:
    seen: set[str] = set()
    folded: set[str] = set()
    for name in names:
        _safe_name(name)
        if name in source_names or name in seen:
            raise OnDeviceApkError(f"combined APK has duplicate member: {name}")
        if name.casefold() in source_cases or name.casefold() in folded:
            raise OnDeviceApkError(f"combined APK has case-colliding member: {name}")
        seen.add(name); folded.add(name.casefold())


def _one_info(archive: zipfile.ZipFile, name: str, label: str) -> zipfile.ZipInfo:
    matches = [info for info in archive.infolist() if info.filename == name]
    if len(matches) != 1:
        raise OnDeviceApkError(f"{label} APK must contain exactly one {name}")
    return matches[0]


def _safe_name(name: str) -> None:
    path = PurePosixPath(name)
    if not name or name.startswith("/") or "\\" in name or ".." in path.parts or "." in path.parts:
        raise OnDeviceApkError(f"unsafe APK member name: {name}")


def _dex_number(name: str) -> int | None:
    if not name.startswith("classes") or not name.endswith(".dex"):
        return None
    middle = name[7:-4]
    if middle == "": return 1
    return int(middle) if middle.isdigit() and int(middle) >= 2 else None


def _is_signature(name: str) -> bool:
    upper = name.upper()
    return upper == "META-INF/MANIFEST.MF" or (upper.startswith("META-INF/") and upper.endswith(SIGNATURE_SUFFIXES))


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _axml_strings(data: bytes) -> list[str]:
    if len(data) < 8 or struct.unpack_from("<H", data)[0] != 3:
        raise OnDeviceApkError("AndroidManifest.xml is not binary Android XML")
    offset = 8
    while offset + 8 <= len(data):
        kind, header, size = struct.unpack_from("<HHI", data, offset)
        if size < header or offset + size > len(data): break
        if kind == 1:
            count, styles, flags, strings_start, _ = struct.unpack_from("<IIIII", data, offset + 8)
            if styles or strings_start >= size: raise OnDeviceApkError("unsupported Android string pool")
            positions = [struct.unpack_from("<I", data, offset + 28 + i * 4)[0] for i in range(count)]
            return [_read_axml_string(data, offset + strings_start + position, bool(flags & 0x100)) for position in positions]
        offset += size
    raise OnDeviceApkError("AndroidManifest.xml has no string pool")


def _read_axml_string(data: bytes, offset: int, utf8: bool) -> str:
    if utf8:
        _, used = _axml_length(data, offset, 1); length, used2 = _axml_length(data, offset + used, 1)
        return data[offset + used + used2:offset + used + used2 + length].decode("utf-8")
    length, used = _axml_length(data, offset, 2)
    return data[offset + used:offset + used + length * 2].decode("utf-16le")


def _axml_length(data: bytes, offset: int, width: int) -> tuple[int, int]:
    first = data[offset] if width == 1 else struct.unpack_from("<H", data, offset)[0]
    if first & (0x80 if width == 1 else 0x8000):
        second = data[offset + width] if width == 1 else struct.unpack_from("<H", data, offset + width)[0]
        return ((first & (0x7f if width == 1 else 0x7fff)) << (7 if width == 1 else 15)) | second, width * 2
    return first, width


def _axml_min_sdk_offsets(data: bytes, strings: list[str]) -> list[int]:
    result: list[int] = []; offset = 8
    while offset + 8 <= len(data):
        kind, header, size = struct.unpack_from("<HHI", data, offset)
        if size < header or offset + size > len(data): break
        if kind == 0x0102 and header >= 16 and size >= 36:
            name_index = struct.unpack_from("<I", data, offset + 20)[0]
            attr_start, attr_size, attr_count = struct.unpack_from("<HHH", data, offset + 24)
            if name_index < len(strings) and strings[name_index] == "uses-sdk" and attr_size >= 20:
                start = offset + 16 + attr_start
                for number in range(attr_count):
                    attr = start + number * attr_size
                    attr_name = struct.unpack_from("<I", data, attr + 4)[0]
                    data_type = data[attr + 15]
                    if attr_name < len(strings) and strings[attr_name] == "minSdkVersion" and data_type in (0x10, 0x11): result.append(attr + 16)
        offset += size
    return result
