"""The coverage data files of a folder that can be combined: those whose writer has ended.

Coverage names each process's data file for its pid, `data.<host>.pid<pid>.X<random>`, and writes
it as the process ends. A process a test started and left running may be writing its file when
the run's data is combined, and a half-written file breaks the combine (`no such table:
coverage_schema`) or, deleted under its writer, breaks the write (`attempt to write a readonly
database`). The combine leaves such a file, and its lines, out.
"""

import os
import re
from pathlib import Path


def ended(folder: Path) -> list[str]:
    """The data files in `folder` whose writer has ended, this process counting as ended."""
    return [
        str(one)
        for one in sorted(folder.glob("data.*"))
        if not one.name.endswith("-journal")
        and not running(int(re.search(r"\.pid(\d+)\.", one.name)[1]))
    ]


def running(pid: int) -> bool:
    if pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True
