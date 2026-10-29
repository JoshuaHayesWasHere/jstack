"""How every command of jstack keeps a file of state: read it, write it whole, add a line to a log
of records, and hold a lock from a read to its write.

- `read_json` and `read_dict`: a JSON file, or a default where it is missing or does not parse.
- `write_json`: the file written whole, a temp file and then a rename, so a reader never sees
  half of it.
- `append_jsonl`: records added to a log, one JSON line each, in one write.
- `locked`: a lock file held while a block runs.
- `LockedList`: a JSON list of records that threads change under its lock.

Each writer keeps the form its file has always had: `write_json` and `append_jsonl` take the
`json.dumps` options a file is written with, and a file's mode.
"""

from __future__ import annotations

import fcntl
import json
import os
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

APPEND = 0o666
"""The mode of a log `append_jsonl` makes, before the umask: what `open(path, "a")` gives."""


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def read_dict(path: Path) -> dict:
    """The JSON object in the file, or an empty one when the file is missing, unreadable or holds
    something else."""
    found = read_json(path, {})
    return found if isinstance(found, dict) else {}


def write_json(
    path: Path,
    value: Any,
    *,
    mode: int = 0o644,
    indent: int | None = 2,
    sort_keys: bool = True,
    temporary: Path | None = None,
) -> None:
    """Write the file whole: a temp file of this process's own, then a rename, so a reader or
    a second writer never sees half of it, and a write that fails leaves no temp behind. The temp
    file is `temporary` where a file has always been written through one of its own name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = temporary or path.with_name(f"{path.name}.{os.getpid()}.tmp")
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        try:
            text = json.dumps(value, indent=indent, sort_keys=sort_keys) + "\n"
            os.write(handle, text.encode())
            os.fsync(handle)
        finally:
            os.close(handle)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def append_jsonl(
    path: Path,
    records: Iterable[Any],
    *,
    mode: int = APPEND,
    sort_keys: bool = False,
) -> None:
    """Add each record to the log at `path` as one JSON line, all of them in one write, so no
    other writer's line lands between two of them. A log that is not there is made, with `mode`.
    """
    text = "".join(json.dumps(one, sort_keys=sort_keys) + "\n" for one in records)
    if not text:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, mode)
    try:
        os.write(handle, text.encode())
    finally:
        os.close(handle)


@contextmanager
def locked(state: Path, name: str, wait: bool = True) -> Iterator[None]:
    """Hold the lock file `name` under `state` from a state file's read to its write, so that no
    other pass or verb writes the file between the two. With `wait` False, a lock another holds
    raises `BlockingIOError` at once."""
    state.mkdir(parents=True, exist_ok=True)
    with open(state / name, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX if wait else fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield


@dataclass(frozen=True)
class LockedList[T]:
    """A JSON list of records, the file `name` in a directory, which threads change under the lock
    file `lock` beside it. Each change replaces the whole file with a rename, so a reader never
    sees half a list. `parse` makes the records of the file's list, and may raise `ValueError`,
    `TypeError` or `KeyError` on one it cannot read: a file that cannot be read is no records.
    A record is a dataclass with a `since` and an `id`, which order the list."""

    name: str
    lock: str
    parse: Callable[[Any], list[T]]

    def there(self, at: Path) -> bool:
        return (at / self.name).exists()

    @contextmanager
    def held(self, at: Path) -> Iterator[None]:
        with locked(at, self.lock):
            yield

    def peek(self, at: Path) -> list[T]:
        """The records, read with no lock, for a reader that must not make the lock file."""
        try:
            return self.parse(json.loads((at / self.name).read_text()))
        except (OSError, ValueError, TypeError, KeyError):
            return []

    def read(self, at: Path) -> list[T]:
        """Every record, the oldest first."""
        with self.held(at):
            return sorted(self.peek(at), key=lambda one: (one.since, one.id))

    def change(self, at: Path, how: Callable[[list[T]], list[T]]) -> None:
        """Replace the records with what `how` makes of them, and write the file only when that
        differs."""
        with self.held(at):
            was = self.peek(at)
            now = how(was)
            if now != was:
                records = [asdict(one) for one in now]
                temporary = at / f".{self.name}.{os.getpid()}"
                write_json(at / self.name, records, sort_keys=False, temporary=temporary)
