from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
import zipfile

from liminal_gate.on_device_apk import (
    HOST_ACTIVITY, PACKAGED_MANIFEST, PACKAGED_PREFIX, OnDeviceApkError,
    assemble_on_device_apk, patch_binary_manifest,
)
from liminal_gate.resource_catalog import load_resource_catalog_document
from liminal_gate.resource_catalog_builder import build_resource_manifest


def _utf8(value: str) -> bytes:
    encoded = value.encode()
    return bytes([len(value), len(encoded)]) + encoded + b"\0"


def _utf16(value: str) -> bytes:
    encoded = value.encode("utf-16le")
    return struct.pack("<H", len(value)) + encoded + b"\0\0"


def _manifest(*, utf8: bool = True) -> bytes:
    # A minimal binary XML document: string pool plus uses-sdk and activity.
    values = ["uses-sdk", "minSdkVersion", "activity", "name", "com.unity3d.player.UnityPlayerActivity"]
    encoder = _utf8 if utf8 else _utf16
    strings = b"".join(encoder(value) for value in values)
    offsets = []; cursor = 0
    for value in values:
        offsets.append(cursor); cursor += len(encoder(value))
    pool_size = 28 + 4 * len(values) + len(strings)
    pool = struct.pack("<HHI5I", 1, 28, pool_size, len(values), 0, 0x100 if utf8 else 0, 28 + 4 * len(values), 0) + struct.pack("<" + "I" * len(values), *offsets) + strings
    def element(name: int, attrs: list[tuple[int, int]]) -> bytes:
        # ResXMLTree_node's line/comment precede the attribute extension.
        body = struct.pack("<IIIIHHHHHH", 0, 0xffffffff, 0xffffffff, name, 20, 20, len(attrs), 0, 0, 0)
        for attr_name, value in attrs:
            body += struct.pack("<IIIHBBI", 0xffffffff, attr_name, 0xffffffff, 8, 0, 0x10, value)
        return struct.pack("<HHI", 0x102, 36, 8 + len(body)) + body
    sdk = element(0, [(1, 16)])
    activity = element(2, [(3, 0)])
    # The activity literal is only needed in the string pool; the attribute's
    # typed value deliberately does not matter to this focused assembler test.
    document = pool + sdk + activity
    return struct.pack("<HHI", 3, 8, 8 + len(document)) + document


class OnDeviceApkTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name)
        self.source = self.root / "terra.apk"; self.host = self.root / "host.apk"; self.output = self.root / "combined.apk"
        self.resources = self.root / "resources"; self.resources.mkdir(); (self.resources / "Data.bin").write_bytes(b"resource bytes")
        with zipfile.ZipFile(self.source, "w", compression=zipfile.ZIP_DEFLATED) as apk:
            apk.writestr("AndroidManifest.xml", _manifest())
            apk.writestr("classes.dex", b"terra dex")
            apk.writestr("assets/original.bin", b"must remain exactly compressed")
            apk.writestr("lib/arm64-v8a/libil2cpp.so", b"native original")
            apk.writestr("lib/armeabi-v7a/libil2cpp.so", b"native original 32")
            apk.writestr("META-INF/CERT.SF", b"old signature")
        with zipfile.ZipFile(self.host, "w") as apk:
            apk.writestr("classes.dex", b"host dex")
            apk.writestr("META-INF/com/android/build/gradle/app-metadata.properties", b"agpVersion=8.9.2\n")
            apk.writestr("assets/chaquopy/bootstrap.py", b"host asset")
            apk.writestr("lib/arm64-v8a/libpython3.13.so", b"host native")
            apk.writestr("lib/armeabi-v7a/libpython3.13.so", b"host native 32")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _assemble(self, **kwargs: object) -> None:
        assemble_on_device_apk(self.source, self.host, self.output, patched_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(), resource_root=self.resources, build_id="a" * 64, **kwargs)

    def test_assembles_unsigned_payload_and_preserves_untouched_local_record(self) -> None:
        catalog = self.root / "event.json"; catalog.write_text('{"ready":true}\n')
        self._assemble(catalogs={"event.json": catalog})
        with zipfile.ZipFile(self.source) as original, zipfile.ZipFile(self.output) as combined:
            self.assertEqual(b"terra dex", combined.read("classes.dex"))
            self.assertEqual(b"host dex", combined.read("classes2.dex"))
            self.assertEqual(b"host asset", combined.read("assets/chaquopy/bootstrap.py"))
            self.assertEqual(b"host native", combined.read("lib/arm64-v8a/libpython3.13.so"))
            self.assertNotIn("META-INF/CERT.SF", combined.namelist())
            self.assertEqual(b"resource bytes", combined.read(PACKAGED_PREFIX + "resources/Data.bin"))
            manifest = json.loads(combined.read(PACKAGED_MANIFEST))
            self.assertEqual(2, manifest["schema_version"])
            self.assertEqual("/resources/Data.bin", manifest["resources"][0]["path"])
            self.assertEqual("event.json", manifest["catalogs"][0]["name"])
            self.assertEqual(PACKAGED_PREFIX + "resources/Data.bin", manifest["resources"][0]["member"])
            self.assertEqual(len(b"resource bytes"), manifest["resources"][0]["size"])
            self.assertEqual(0, combined.getinfo(PACKAGED_PREFIX + "resources/Data.bin").compress_type)
            # The whole local record, including the original compressed bytes,
            # is retained rather than read/recompressed by zipfile.
            source_raw = self.source.read_bytes(); output_raw = self.output.read_bytes()
            info = original.getinfo("assets/original.bin")
            next_info = original.getinfo("lib/arm64-v8a/libil2cpp.so")
            record = source_raw[info.header_offset:next_info.header_offset]
            output_info = combined.getinfo("assets/original.bin")
            self.assertEqual(record, output_raw[output_info.header_offset:output_info.header_offset + len(record)])
            patched = combined.read("AndroidManifest.xml")
            self.assertIn(HOST_ACTIVITY.encode(), patched)
            self.assertNotIn(b"com.unity3d.player.UnityPlayerActivity", patched)
            self.assertNotEqual(original.read("AndroidManifest.xml"), patched)
            # Changed/new local records and central-directory records must
            # agree on flags and DOS timestamps.
            for name in (
                "AndroidManifest.xml",
                "classes2.dex",
                PACKAGED_PREFIX + "resources/Data.bin",
            ):
                info = combined.getinfo(name)
                local = output_raw[info.header_offset:info.header_offset + 14]
                _, _, flags, _, time, date = struct.unpack("<IHHHHH", local)
                expected_time = (
                    (info.date_time[3] << 11)
                    | (info.date_time[4] << 5)
                    | (info.date_time[5] // 2)
                )
                expected_date = (
                    ((info.date_time[0] - 1980) << 9)
                    | (info.date_time[1] << 5)
                    | info.date_time[2]
                )
                self.assertEqual(info.flag_bits, flags)
                self.assertEqual((expected_time, expected_date), (time, date))

    def test_packaged_manifest_serves_the_same_urls_as_the_filesystem_manifest(self) -> None:
        # The client asks for the logical name; Android stores the bundle under
        # a 32-hex cache prefix. Both deployments must answer both spellings, or
        # a resource loads from a separate server and 404s on the packaged APK.
        prefixed = self.resources / "SE" / "bdb3334db029db0ef76e06637e4de9b9sun3.bin"
        prefixed.parent.mkdir()
        prefixed.write_bytes(b"local unity bundle")
        self._assemble()
        with zipfile.ZipFile(self.output) as combined:
            manifest = json.loads(combined.read(PACKAGED_MANIFEST))
        packaged = {entry["path"]: entry for entry in manifest["resources"]}
        self.assertEqual(
            {item["path"] for item in build_resource_manifest(self.resources)["resources"]},
            set(packaged),
        )
        member = PACKAGED_PREFIX + "resources/SE/bdb3334db029db0ef76e06637e4de9b9sun3.bin"
        for path in ("/resources/SE/sun3.bin", "/resources/SE/bdb3334db029db0ef76e06637e4de9b9sun3.bin"):
            # Both aliases resolve to the one stored member; the bytes are not
            # packaged twice.
            self.assertEqual(member, packaged[path]["member"])
            self.assertEqual(len(b"local unity bundle"), packaged[path]["size"])
        catalog = load_resource_catalog_document(
            {"schema_version": 2, "resources": manifest["resources"]}, self.output,
        )
        try:
            resolved = catalog.resolve("/resources/SE/sun3.bin")
            self.assertIsNotNone(resolved)
            with catalog.open(resolved) as stream:
                self.assertEqual(b"local unity bundle", stream.read())
        finally:
            catalog.close()

    def test_rejects_resources_that_collapse_onto_one_client_url(self) -> None:
        banner = self.resources / "Banner"
        banner.mkdir()
        (banner / "bdb3334db029db0ef76e06637e4de9b9sun3.bin").write_bytes(b"prefixed")
        (banner / "sun3.bin").write_bytes(b"logical")
        with self.assertRaisesRegex(OnDeviceApkError, "maps more than one file to /resources/Banner/sun3.bin"):
            self._assemble()

    def test_rejects_wrong_source_hash_and_collisions(self) -> None:
        with self.assertRaisesRegex(OnDeviceApkError, "SHA-256"):
            assemble_on_device_apk(self.source, self.host, self.output, patched_sha256="0" * 64, resource_root=self.resources, build_id="a" * 64)
        with zipfile.ZipFile(self.host, "a") as host:
            host.writestr("assets/original.bin", b"collision")
        with self.assertRaisesRegex(OnDeviceApkError, "duplicate member"):
            self._assemble()

    def test_manifest_requires_exact_expected_activity_and_min_sdk(self) -> None:
        with self.assertRaisesRegex(OnDeviceApkError, "exactly one expected activity"):
            patch_binary_manifest(_manifest().replace(b"com.unity3d.player.UnityPlayerActivity", b"x" * len(b"com.unity3d.player.UnityPlayerActivity")))
        bad = bytearray(_manifest())
        # In this synthetic document the sole typed integer 16 is minSdk.
        position = bad.find(struct.pack("<I", 16), 40)
        bad[position:position + 4] = struct.pack("<I", 21)
        with self.assertRaisesRegex(OnDeviceApkError, "not the expected value 16"):
            patch_binary_manifest(bytes(bad))

    def test_patches_utf16_activity_string_pool_entry(self) -> None:
        patched = patch_binary_manifest(_manifest(utf8=False))
        self.assertIn(HOST_ACTIVITY.encode("utf-16le"), patched)
        self.assertNotIn(b"com.unity3d.player.UnityPlayerActivity".decode().encode("utf-16le"), patched)

    def test_requires_both_native_abis_in_base_and_host(self) -> None:
        missing_host = self.root / "missing-host.apk"
        with zipfile.ZipFile(missing_host, "w") as apk:
            apk.writestr("classes.dex", b"host dex")
            apk.writestr("lib/arm64-v8a/libpython.so", b"only arm64")
        with self.assertRaisesRegex(OnDeviceApkError, "host APK is missing required native payload ABI: armeabi-v7a"):
            assemble_on_device_apk(self.source, missing_host, self.output, patched_sha256=hashlib.sha256(self.source.read_bytes()).hexdigest(), resource_root=self.resources, build_id="a" * 64)
        missing_base = self.root / "missing-base.apk"
        with zipfile.ZipFile(missing_base, "w") as apk:
            apk.writestr("AndroidManifest.xml", _manifest())
            apk.writestr("classes.dex", b"base dex")
            apk.writestr("lib/arm64-v8a/libil2cpp.so", b"only arm64")
        with self.assertRaisesRegex(OnDeviceApkError, "patched base APK is missing required native payload ABI: armeabi-v7a"):
            assemble_on_device_apk(missing_base, self.host, self.output, patched_sha256=hashlib.sha256(missing_base.read_bytes()).hexdigest(), resource_root=self.resources, build_id="a" * 64)

    def test_rejects_data_descriptor_host_payload(self) -> None:
        # Flip bit 3 consistently in the first local and central records. The
        # central directory still supplies sizes, so zipfile can open it and
        # the assembler's addition-specific guard gets exercised.
        raw = bytearray(self.host.read_bytes())
        local = raw.find(b"PK\x03\x04")
        central = raw.find(b"PK\x01\x02")
        raw[local + 6] |= 0x08
        raw[central + 8] |= 0x08
        self.host.write_bytes(raw)
        with self.assertRaisesRegex(OnDeviceApkError, "data descriptor"):
            self._assemble()
