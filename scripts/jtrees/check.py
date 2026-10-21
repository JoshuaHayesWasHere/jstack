"""Compare the outputs with the files on disk, or write them.

`diff` names each output whose bytes differ from the file at its path, or whose file is
missing. `write` writes only those, each to a temporary file beside it that is then renamed
into place, so a run stopped halfway leaves every file whole, and a second run writes nothing.
"""

from __future__ import annotations

import os
from pathlib import Path


def diff(want: dict[str, bytes], root: Path) -> list[str]:
    stale = []
    for path, content in sorted(want.items()):
        try:
            if (root / path).read_bytes() == content:
                continue
        except FileNotFoundError:
            pass
        stale.append(path)
    return stale


def write(want: dict[str, bytes], root: Path) -> list[str]:
    written = diff(want, root)
    for path in written:
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.jtrees")
        temporary.write_bytes(want[path])
        os.replace(temporary, target)
    return written
