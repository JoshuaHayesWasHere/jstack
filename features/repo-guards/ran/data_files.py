"""The coverage data files of a folder that can be combined: those whose writer has ended, and
that coverage can read.

Coverage names each process's data file for its pid, `data.<host>.pid<pid>.X<random>`, and writes
it as the process ends. A process a test started and left running may be writing its file when
the run's data is combined, and a half-written file breaks the combine (`no such table:
coverage_schema`) or, deleted under its writer, breaks the write (`attempt to write a readonly
database`). A process killed as it saves, once SQLite has made its file and before the schema is
in it, leaves an empty file under a pid that is gone, and the combine breaks on it the same way,
since coverage reads a file with no schema by writing one into it. The combine leaves each such
file, and its lines, out.
"""

import os
import re
import sqlite3
from pathlib import Path

from coverage import CoverageData
from coverage.exceptions import CoverageException


def ended(folder: Path) -> list[str]:
    """The data files in `folder` whose writer has ended, this process counting as ended, and
    that coverage can read."""
    return [
        str(one)
        for one in sorted(folder.glob("data.*"))
        if not one.name.endswith("-journal")
        and not running(int(re.search(r"\.pid(\d+)\.", one.name)[1]))
        and readable(one)
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


def readable(file: Path) -> bool:
    data = CoverageData(str(file), read_only=True)
    try:
        data.read()
    except (CoverageException, sqlite3.Error):
        return False
    finally:
        data.close()
    return True
