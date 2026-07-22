"""Align, sign, and verify a local APK using only user-supplied Android tools."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import tempfile


class ApkSigningError(RuntimeError):
    """A locally supplied Android signing tool failed."""


def sign_apk(
    unsigned_apk: Path,
    output_apk: Path,
    zipalign: Path,
    apksigner: Path,
    keystore: Path,
    key_alias: str,
    store_password_file: Path,
    key_password_file: Path,
) -> None:
    """Align and sign an APK without reading or printing password contents."""
    if unsigned_apk.resolve() == output_apk.resolve():
        raise ApkSigningError("output APK must differ from unsigned APK")
    for path, label in ((unsigned_apk, "unsigned APK"), (zipalign, "zipalign"), (apksigner, "apksigner"), (keystore, "keystore"), (store_password_file, "store password file"), (key_password_file, "key password file")):
        if not path.is_file():
            raise ApkSigningError(f"{label} is unavailable")
    if not key_alias:
        raise ApkSigningError("key alias is required")
    output_apk.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output_apk.parent, prefix="liminal-gate-sign-") as temporary_directory:
        aligned = Path(temporary_directory) / "aligned.apk"
        _run((str(zipalign), "-f", "-p", "4", str(unsigned_apk), str(aligned)), "zipalign")
        sign_arguments = [
            str(apksigner), "sign", "--ks", str(keystore), "--ks-key-alias", key_alias,
            "--ks-pass", f"file:{store_password_file}",
        ]
        if store_password_file.resolve() != key_password_file.resolve():
            sign_arguments.extend(("--key-pass", f"file:{key_password_file}"))
        sign_arguments.extend(("--out", str(output_apk), str(aligned)))
        _run(tuple(sign_arguments), "apksigner sign")
        _run((str(apksigner), "verify", "--verbose", "--print-certs", str(output_apk)), "apksigner verify")


def _run(arguments: tuple[str, ...], label: str) -> None:
    try:
        subprocess.run(arguments, check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as error:
        raise ApkSigningError(f"{label} could not start") from error
    except subprocess.CalledProcessError as error:
        raise ApkSigningError(f"{label} failed") from error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unsigned-apk", required=True, type=Path)
    parser.add_argument("--output-apk", required=True, type=Path)
    parser.add_argument("--zipalign", required=True, type=Path)
    parser.add_argument("--apksigner", required=True, type=Path)
    parser.add_argument("--keystore", required=True, type=Path)
    parser.add_argument("--key-alias", required=True)
    parser.add_argument("--store-password-file", required=True, type=Path)
    parser.add_argument("--key-password-file", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        sign_apk(
            args.unsigned_apk, args.output_apk, args.zipalign, args.apksigner,
            args.keystore, args.key_alias, args.store_password_file, args.key_password_file,
        )
    except ApkSigningError as error:
        raise SystemExit(f"APK signing failed: {error}") from error
    print(f"wrote signed APK: {args.output_apk}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
