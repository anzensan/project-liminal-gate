"""Hash each immutable local input once per run rather than once per consumer.

The guided setup inventories the resource tree twice: an input manifest that
records what the operator supplied, and a resource manifest that maps client
URLs onto files. Both need a SHA-256 per file, and on a multi-gigabyte pack that
second pass is the slowest thing setup does for no gain at all -- the inputs do
not change while setup runs, so the second consumer can read the first one's
digest instead of the disk.

Only immutable inputs belong in the cache. A file this process writes and then
hashes must be hashed for real, because a stale digest would be recorded as
provenance for content that has since changed.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable


#: Read size used for every digest here. Large enough that the syscall overhead
#: disappears against a multi-gigabyte tree, small enough to stay bounded.
CHUNK_BYTES = 1024 * 1024


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of one file, reading it in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_files(root: Path) -> int:
    """Count the regular files beneath root without reading any of them.

    Used to give the hashing pass a total to count towards. It walks metadata
    only, so it costs a stat per file against the many megabytes per file the
    hashing itself reads.
    """
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("*") if path.is_file() and not path.is_symlink())


class DigestCache:
    """Memoize SHA-256 by resolved path for the length of one run.

    Callers pass an instance where a plain hashing function is expected, so a
    consumer that is handed one shares digests with every other consumer and a
    consumer that is not behaves exactly as before.
    """

    def __init__(self, on_hash: Callable[[int, int], None] | None = None) -> None:
        self._digests: dict[Path, str] = {}
        self._on_hash = on_hash
        #: Files actually read, bytes actually read, and cache hits. Reported at
        #: the end of the hashing phase so the saving is visible rather than
        #: claimed.
        self.hashed_files = 0
        self.hashed_bytes = 0
        self.reused = 0

    def __call__(self, path: Path) -> str:
        key = path.resolve()
        cached = self._digests.get(key)
        if cached is not None:
            self.reused += 1
            return cached
        digest = sha256_file(key)
        self._digests[key] = digest
        self.hashed_files += 1
        try:
            self.hashed_bytes += key.stat().st_size
        except OSError:
            # Only the progress total is affected, and a file that hashed a
            # moment ago is not worth failing a run over.
            pass
        if self._on_hash is not None:
            self._on_hash(self.hashed_files, self.hashed_bytes)
        return digest
