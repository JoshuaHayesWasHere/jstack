"""The repo's merge lock: one run of `jmerge` at a time reads main's tip and merges over it.

A run takes the lock before it reads the tip of the pull request's base and gives it back once
its merge returned, so no other run's merge lands between the read and the merge. A run that
finds the lock held waits for its next run rather than merge over a tip it may not have read.
The lock is a `flock` on a file in the home's state directory, so a run that dies gives it back.
"""

from __future__ import annotations

import fcntl
from pathlib import Path
from typing import IO

FILE = "merge.lock"


class MergeLock:
    def __init__(self, state: Path) -> None:
        self.path = state / FILE
        self.held: IO[str] | None = None

    def take(self) -> bool:
        """Take the lock if no other run holds it, and say whether this run holds it now."""
        if self.held is not None:
            return True
        held = open(self.path, "a")
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            held.close()
            return False
        self.held = held
        return True

    def give(self) -> None:
        if self.held is not None:
            self.held.close()
            self.held = None
