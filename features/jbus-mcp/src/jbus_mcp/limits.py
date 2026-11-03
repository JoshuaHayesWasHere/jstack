"""The server's log and its rate limits.

Every tool call and every sign-in step is one JSON line of `log.jsonl` in the server's state:
the time, the kind, the tool, the arguments with a brief kept only as its sha256 and length, and
what came of it. Past `CAP` bytes the file keeps only its newest lines, up to half that size.

A rate limit is a sliding window: at most `limit` events in any `seconds`. The server keeps one
for the reads, one for the writes and one for the sign-in endpoints.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = ["CAP", "FILE", "Log", "Window", "redacted"]

FILE = "log.jsonl"
CAP = 16 * 1024 * 1024


def redacted(arguments: Mapping[str, Any]) -> dict[str, Any]:
    """The arguments as the log keeps them: a brief only as its sha256 and its length."""
    kept = dict(arguments)
    if isinstance(kept.get("brief"), str):
        text = kept.pop("brief")
        kept["brief"] = {"sha256": hashlib.sha256(text.encode()).hexdigest(), "chars": len(text)}
    return kept


class Log:
    """The append-only log of one server, one JSON line an event."""

    def __init__(self, path: Path, cap: int = CAP, clock: Callable[[], datetime] | None = None):
        self.path, self.cap = path, cap
        self.clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()

    def write(self, kind: str, **fields: Any) -> dict[str, Any]:
        line = {"at": self.clock().isoformat(timespec="seconds"), "kind": kind, **fields}
        text = json.dumps(line, sort_keys=True, default=str) + "\n"
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as out:
                out.write(text)
            if self.path.stat().st_size > self.cap:
                self._trim()
        return line

    def _trim(self) -> None:
        kept: list[str] = []
        size = 0
        for one in reversed(self.path.read_text(encoding="utf-8").splitlines(keepends=True)):
            size += len(one.encode())
            if size > self.cap // 2:
                break
            kept.append(one)
        fresh = self.path.with_suffix(".tmp")
        fresh.write_text("".join(reversed(kept)), encoding="utf-8")
        os.chmod(fresh, 0o600)
        fresh.replace(self.path)

    def lines(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(one) for one in self.path.read_text(encoding="utf-8").splitlines()]


class Window:
    """At most `limit` events in any `seconds`, counted on a monotonic clock."""

    def __init__(self, limit: int, seconds: float, clock: Callable[[], float] | None = None):
        self.limit, self.seconds = limit, seconds
        self.clock = clock or time.monotonic
        self._times: deque[float] = deque()
        self._lock = threading.Lock()

    def take(self) -> float:
        """Count one event and return 0, or count nothing and return the seconds to wait."""
        with self._lock:
            now = self.clock()
            while self._times and now - self._times[0] >= self.seconds:
                self._times.popleft()
            if len(self._times) >= self.limit:
                return max(self.seconds - (now - self._times[0]), 0.001)
            self._times.append(now)
            return 0.0
