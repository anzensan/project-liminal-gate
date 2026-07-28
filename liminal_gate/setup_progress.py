"""Progress reporting for long, local setup operations.

This module knows nothing about Android, APKs, or Terra Battle. It only owns
the terminal behavior needed by any setup phase that reads many bytes or waits
on a quiet child process.
"""

from __future__ import annotations

import subprocess
import sys
import time
from typing import Sequence


DEFAULT_PROGRESS_INTERVAL_SECONDS = 2.0


def format_bytes(count: int) -> str:
    """Render a byte count the way an operator would say it aloud."""
    size = float(count)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if size < 1024 or unit == "GiB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GiB"


class ProgressLine:
    """A throttled, single-line terminal progress display."""

    def __init__(
        self,
        label: str,
        total: int = 0,
        stream: object | None = None,
        interval: float = DEFAULT_PROGRESS_INTERVAL_SECONDS,
    ) -> None:
        self._label, self._total = label, total
        self._stream = sys.stdout if stream is None else stream
        self._interactive = bool(getattr(self._stream, "isatty", lambda: False)())
        self._interval = interval
        self._last = 0.0
        self._width = 0

    def _paint(self, text: str) -> None:
        if not self._interactive:
            return
        padding = max(0, self._width - len(text))
        self._width = len(text)
        print(f"\r{text}{' ' * padding}", end="", flush=True, file=self._stream)

    def update(self, done: int, detail: str = "") -> None:
        """Report progress towards the known total, at most every interval."""
        now = time.monotonic()
        if done < self._total and now - self._last < self._interval:
            return
        self._last = now
        share = f"{done}/{self._total}" if self._total else str(done)
        self._paint(f"  {self._label} {share}{f' ({detail})' if detail else ''}")

    def advance(self, done: int, total: int, detail: str = "") -> None:
        """Report progress towards a total the caller only learns as it goes."""
        self._total = total
        self.update(done, detail)

    def tick(self, detail: str) -> None:
        """Report that an open-ended phase is still running."""
        now = time.monotonic()
        if now - self._last < self._interval:
            return
        self._last = now
        self._paint(f"  {self._label} {detail}")

    def done(self, summary: str) -> None:
        """Close the line with the one message worth keeping in a log."""
        if self._interactive and self._width:
            print(f"\r{' ' * self._width}\r", end="", file=self._stream)
        self._width = 0
        print(f"  {self._label}: {summary}", file=self._stream)


def run_with_heartbeat(
    command: Sequence[str],
    label: str,
    timeout: float,
    interval: float = DEFAULT_PROGRESS_INTERVAL_SECONDS,
) -> subprocess.CompletedProcess:
    """Capture a quiet child process while showing bounded terminal liveness."""
    started = time.monotonic()
    progress = ProgressLine(label, interval=interval)
    with subprocess.Popen(
        tuple(command),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=interval)
                break
            except subprocess.TimeoutExpired:
                # `communicate` may be retried while the child stays live. Only
                # the total elapsed budget ends the operation.
                elapsed = time.monotonic() - started
                if elapsed >= timeout:
                    process.kill()
                    process.communicate()
                    raise subprocess.TimeoutExpired(tuple(command), timeout) from None
                progress.tick(f"still running, {int(elapsed)}s elapsed")
        returncode = process.returncode
    progress.done(f"finished in {int(time.monotonic() - started)}s")
    return subprocess.CompletedProcess(tuple(command), returncode, stdout, stderr)
