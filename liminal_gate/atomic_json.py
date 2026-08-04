"""Write one derived JSON document atomically, with stable bytes.

Every importer and generator publishes its projection the same way: encode
with sorted keys and a trailing newline, write a sibling temporary file,
fsync, and rename over the target.  The bytes are provenance -- derived
catalogs pin each other's SHA-256 -- so the indent is a caller decision that
must never change for an existing artifact kind, which is why it is a
required keyword rather than a default.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def write_json_document(path: Path, document: Any, *, indent: int) -> None:
    """Atomically publish `document` at `path`, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (json.dumps(document, indent=indent, sort_keys=True) + "\n").encode("utf-8")
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
