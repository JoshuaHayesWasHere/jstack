"""The split of a run's tests into parts by time, and the two tables it reads, with no pytest: the
check's `reuse` job deals its parts in plain `python3` before any `uv sync`
(`scripts/select_tests.py --parts`), and `testing/shard.py`'s `--shard` splits a collection.

The parts are split by time, so that they end together: a job's wall is its part's, and the check
waits on its slowest part. `testing/shard-times.tsv` holds the seconds of each test that took
`FLOOR` or more in CI, by `key`, a short sha256 of its node id, and the test's file: a node id
can hold a placeholder in the shape of a private value, such as a thread id, which the push hook
refuses, and the keys keep the table small. A test the table does not hold counts as `FLOOR`:
half the suite takes less, and the table leaves those out to stay small, and a new test is most
likely one of them.

`testing/shard-file-times.tsv` holds the same times by test file: the seconds of each file's
tests, summed, each test at `FLOOR` at least, the ones under it too, and the seconds of its
slowest test. The check's parts are dealt from it with no collection, and a file past a part's
share is cut by test from the first table's rows of that file.

A part runs its tests on `WORKERS` workers at once, so it ends once its tests' summed time over
`WORKERS` has passed, and never before its slowest test, which one worker runs alone. The items
are dealt out slowest first, each to the part it would end soonest in, and where it would end as
soon in several, to the one with the fewest seconds so far. So a test longer than the others'
share of a part gets a part of its own, and tests that move no part's end spread over the parts
by their seconds, and do not pile onto the part whose slowest test leaves its workers room.
`WORKERS` is the Makefile's TEST_WORKERS in CI, one for each of the 4 cores of GitHub's hosted
runner: a constant, not this machine's count, so every job deals the same parts.

`uv run python -m testing.shard` writes both tables from CI's full runs, and `--shard-record`
from a run of this machine (`testing/shard.py`)."""

import hashlib
from pathlib import Path

TIMES = Path(__file__).with_name("shard-times.tsv")
FILE_TIMES = Path(__file__).with_name("shard-file-times.tsv")
FLOOR = 0.1
WORKERS = 4


def key(nodeid: str) -> str:
    """The test's key in the table: the first 16 hex digits of the sha256 of its node id."""
    return hashlib.sha256(nodeid.encode()).hexdigest()[:16]


def table(took: dict[str, float]) -> str:
    """The table's text from each test's seconds by node id: a line a test that took `FLOOR` or
    more, its seconds, a tab, its key, a tab, and its file, by key."""
    return "".join(
        f"{spent:.2f}\t{test}\t{file}\n"
        for test, spent, file in sorted(
            (key(nodeid), spent, nodeid.partition("::")[0]) for nodeid, spent in took.items()
        )
        if spent >= FLOOR
    )


def rows(path: Path) -> list[tuple[float, str, str]]:
    """The table's rows: each test's seconds, key and file, or no file in a row that has none, as
    a table written by hand for `--shard-times` can be."""
    if not path.exists():
        return []
    found = []
    for line in path.read_text().splitlines():
        spent, _, rest = line.partition("\t")
        test, _, file = rest.partition("\t")
        found.append((float(spent), test, file))
    return found


def read_times(path: Path) -> dict[str, float]:
    """The table's seconds by key. With no table every test counts as `FLOOR`, so the parts split
    by count."""
    return {test: spent for spent, test, _ in rows(path)}


def read_tests(path: Path) -> dict[str, dict[str, float]]:
    """The table's seconds by key, by file: the tests of a file that took `FLOOR` or more."""
    files: dict[str, dict[str, float]] = {}
    for spent, test, file in rows(path):
        if file:
            files.setdefault(file, {})[test] = spent
    return files


def seconds(times: dict[str, float], nodeid: str) -> float:
    """The test's seconds in the table, or `FLOOR` for a test it does not hold."""
    return times.get(key(nodeid), FLOOR)


def by_file(took: dict[str, float]) -> dict[str, tuple[float, float]]:
    """Each test file's summed seconds and its slowest test's, from each test's seconds by node
    id, a test under `FLOOR` counted as `FLOOR`."""
    files: dict[str, tuple[float, float]] = {}
    for nodeid, spent in took.items():
        file, spent = nodeid.partition("::")[0], max(spent, FLOOR)
        summed, slowest = files.get(file, (0.0, 0.0))
        files[file] = (summed + spent, max(slowest, spent))
    return files


def file_table(took: dict[str, float]) -> str:
    """The file table's text: a line a test file, its seconds, a tab, its slowest test's seconds,
    a tab, and its path, by path."""
    return "".join(
        f"{summed:.2f}\t{slowest:.2f}\t{file}\n"
        for file, (summed, slowest) in sorted(by_file(took).items())
    )


def read_file_times(path: Path) -> dict[str, tuple[float, float]]:
    """The file table's seconds and slowest test's seconds by file, or nothing with no table."""
    if not path.exists():
        return {}
    files = {}
    for line in path.read_text().splitlines():
        summed, slowest, file = line.split("\t", 2)
        files[file] = (float(summed), float(slowest))
    return files


def split(
    items: list[str], times: dict[str, float], parts: int, slowest: dict[str, float] | None = None
) -> list[list[str]]:
    """The items of each part, dealt slowest first to the part each would end soonest in, and of
    those to the one with the fewest seconds so far: a part ends at its items' summed seconds over
    `WORKERS`, and never before its slowest test. An item is a test, or a file of tests whose
    slowest test's seconds `slowest` gives."""
    slowest = slowest or {}
    summed = [0.0] * parts
    longest = [0.0] * parts
    dealt: list[list[str]] = [[] for _ in range(parts)]
    for item in sorted(items, key=lambda one: (-seconds(times, one), one)):
        took = seconds(times, item)
        slow = slowest.get(item, took)
        at = min(
            range(parts),
            key=lambda one: (
                max(longest[one], slow, (summed[one] + took) / WORKERS),
                summed[one],
                one,
            ),
        )
        dealt[at].append(item)
        summed[at] += took
        longest[at] = max(longest[at], slow)
    return dealt
