"""Compare the outputs with the files on disk, or write them.

`diff` names each output whose bytes or executable bit differ from the file at its path, or
whose file is missing, and each file in an output's own folder that no output writes. `write`
writes only those, each to a temporary file beside it that is then renamed into place, and
removes the strays, so a run stopped halfway leaves every file whole, and a second run writes
nothing.
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


def _strays(want: dict[str, File], root: Path, dirs: tuple[str, ...]) -> list[str]:
    return sorted(
        found.relative_to(root).as_posix()
        for folder in dirs
        if (root / folder).is_dir()
        for found in (root / folder).rglob("*")
        if (found.is_file() or found.is_symlink())
        and found.relative_to(root).as_posix() not in want
    )


def diff(want: dict[str, File], root: Path, dirs: tuple[str, ...] = ()) -> list[str]:
    stale = []
    for path, file in sorted(want.items()):
        target = root / path
        try:
            if target.read_bytes() == file.content and _executable(target) == file.executable:
                continue
        except FileNotFoundError:
            pass
        stale.append(path)
    return sorted(stale + _strays(want, root, dirs))


def write(want: dict[str, File], root: Path, dirs: tuple[str, ...] = ()) -> list[str]:
    written = diff(want, root, dirs)
    for path in written:
        target = root / path
        if path not in want:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.jtrees")
        temporary.write_bytes(want[path].content)
        temporary.chmod(0o755 if want[path].executable else 0o644)
        os.replace(temporary, target)
    for folder in dirs:
        for empty in sorted((root / folder).rglob("*"), reverse=True):
            if empty.is_dir() and not any(empty.iterdir()):
                empty.rmdir()
    return written
