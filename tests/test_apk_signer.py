from __future__ import annotations

import os
import json
from pathlib import Path
import stat
import tempfile
import unittest

from liminal_gate.apk_signer import ApkSigningError, sign_apk


class ApkSignerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.unsigned = self.root / "unsigned.apk"
        self.unsigned.write_bytes(b"unsigned-local-apk")
        self.keystore = self.root / "user.keystore"
        self.keystore.write_bytes(b"local-key-material")
        self.store_password = self.root / "store.pass"
        self.key_password = self.root / "key.pass"
        self.store_password.write_text("not-printed", encoding="utf-8")
        self.key_password.write_text("also-not-printed", encoding="utf-8")
        self.log = self.root / "tool.log"
        self.zipalign = self._tool("zipalign", "import pathlib,sys\npathlib.Path(sys.argv[-1]).write_bytes(pathlib.Path(sys.argv[-2]).read_bytes())")
        self.apksigner = self._tool("apksigner", "import json,pathlib,sys\na=sys.argv[1:]\nif a[0] == 'sign':\n pathlib.Path(a[a.index('--out')+1]).write_bytes(pathlib.Path(a[-1]).read_bytes())\n pathlib.Path(__file__).with_name('apksigner-args.json').write_text(json.dumps(a))\nelif a[0] != 'verify': raise SystemExit(2)")

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def _tool(self, name: str, body: str) -> Path:
        path = self.root / name
        path.write_text("#!/usr/bin/env python3\n" + body + "\n", encoding="utf-8")
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    def test_aligns_signs_and_verifies_local_apk(self) -> None:
        output = self.root / "signed.apk"
        sign_apk(self.unsigned, output, self.zipalign, self.apksigner, self.keystore, "user-key", self.store_password, self.key_password)
        self.assertEqual(self.unsigned.read_bytes(), output.read_bytes())
        arguments = json.loads(self.root.joinpath("apksigner-args.json").read_text(encoding="utf-8"))
        self.assertEqual(f"file:{self.store_password}", arguments[arguments.index("--ks-pass") + 1])
        self.assertEqual(f"file:{self.key_password}", arguments[arguments.index("--key-pass") + 1])

    def test_rejects_missing_local_tool_or_in_place_output(self) -> None:
        with self.assertRaisesRegex(ApkSigningError, "differ"):
            sign_apk(self.unsigned, self.unsigned, self.zipalign, self.apksigner, self.keystore, "user-key", self.store_password, self.key_password)
        with self.assertRaisesRegex(ApkSigningError, "zipalign"):
            sign_apk(self.unsigned, self.root / "signed.apk", self.root / "missing", self.apksigner, self.keystore, "user-key", self.store_password, self.key_password)

    def test_uses_keystore_password_when_the_key_password_file_is_the_same(self) -> None:
        output = self.root / "signed-same-password.apk"
        sign_apk(self.unsigned, output, self.zipalign, self.apksigner, self.keystore, "user-key", self.store_password, self.store_password)
        arguments = json.loads(self.root.joinpath("apksigner-args.json").read_text(encoding="utf-8"))
        self.assertNotIn("--key-pass", arguments)
