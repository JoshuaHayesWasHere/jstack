"""Compare the outputs with the files on disk, or write them.

`diff` names each output whose bytes or executable bit differ from the file at its path, or
whose file is missing. `write` writes only those, each to a temporary file beside it that is
then renamed into place, so a run stopped halfway leaves every file whole, and a second run
writes nothing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class File:
    content: bytes
    executable: bool = False


def _executable(path: Path) -> bool:
    return bool(path.stat().st_mode & 0o100)


def diff(want: dict[str, File], root: Path) -> list[str]:
    stale = []
    for path, file in sorted(want.items()):
        target = root / path
        try:
            if target.read_bytes() == file.content and _executable(target) == file.executable:
                continue
        except FileNotFoundError:
            pass
        stale.append(path)
    return stale


def write(want: dict[str, File], root: Path) -> list[str]:
    written = diff(want, root)
    for path in written:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.jtrees")
        temporary.write_bytes(want[path].content)
        temporary.chmod(0o755 if want[path].executable else 0o644)
        os.replace(temporary, target)
    return written
