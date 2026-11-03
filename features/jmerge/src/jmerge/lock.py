"""The repo's two locks. The run lock (`running`) is held by every run of `jmerge` that may write,
for the whole run, so one merger runs at a time whoever started it. The merge lock (`MergeLock`)
is held from the read of main's tip to the merge over it.

A run takes the merge lock before it reads the tip of the pull request's base and gives it back
once its merge returned, so no other run's merge lands between the read and the merge. A run that
finds the lock held waits for its next run rather than merge over a tip it may not have read.
Each lock is a `flock` on a file in the home's state directory, so a run that dies gives it back.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

FILE = "merge.lock"


class MergeLock:
    def __init__(self, state: Path) -> None:
        self.path = state / FILE
        self.held: int | None = None

    def take(self) -> bool:
        """Take the lock if no other run holds it, and say whether this run holds it now."""
        if self.held is not None:
            return True
        held = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o666)
        try:
            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(held)
            return False
        self.held = held
        return True

    def give(self) -> None:
        if self.held is not None:
            os.close(self.held)
            self.held = None


RUN = "run.lock"
BUSY = 75
"""The exit of a run with `--if-free` that found another run holding `RUN`: it did nothing."""
BUSY_LINE = "busy: another run of jmerge holds {path}"


@contextmanager
def running(state: Path, wait: bool) -> Iterator[bool]:
    """Hold the repo's run lock for the whole of one run of `jmerge` that may write, and say
    whether this run holds it.

    Every such run (jbus's pass, jbus's merge tick, a run by hand) takes it, so no two read and
    write the repo's state files together or merge at once. With `wait` the run waits for
    another to end, and without it, it holds nothing and the caller does nothing. A run that
    dies gives it back. `merge.lock` stays inside it: `RUN` is a file of its own, since a
    second `flock` on one file in the same process would not be granted.
    """
    with open(state / RUN, "a") as held:
        try:
            fcntl.flock(held, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
