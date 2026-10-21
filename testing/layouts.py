"""A harness's layout for a test that reads the skills as an agent does: `assembled` makes it
from this checkout as the install does (`jinstall.layout`), once a process. Kept apart from
`paths`, which nearly every test imports, so only the tests that read a layout import
`jinstall`."""

import atexit
import functools
import shutil
import tempfile
from pathlib import Path

from jinstall import layout
from jinstall.harnesses import HARNESSES
from testing.paths import REPO


def place(at: Path, harness: str = "claude-code", root: Path = REPO) -> Path:
    """`harness`'s layout as the install assembles it from the source `root`
    (`jinstall.layout`), written at `at`: each entry a link to its file in `root`, or the file
    the assembly writes. A test reads the skills from it as an agent does."""
    (row,) = [one for one in HARNESSES if one.name == harness]
    for path, entry in layout.assemble(root, row).entries.items():
        target = at / path
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(entry, layout.Linked):
            target.symlink_to(entry.source)
        else:
            target.write_bytes(entry.content)
    return at


@functools.cache
def assembled(harness: str = "claude-code") -> Path:
    """This checkout's layout for `harness`, placed once a process in a folder of its own,
    removed when the process ends."""
    at = Path(tempfile.mkdtemp(prefix=f"jstack-{harness}-"))
    atexit.register(shutil.rmtree, at, True)
    return place(at / harness, harness)
