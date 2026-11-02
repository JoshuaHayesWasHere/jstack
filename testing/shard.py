"""`--shard K/N`: run only the K-th of N parts of the tests the run selected, so that N jobs run
the suite side by side. `make check SHARD=K/N` passes it, and the check workflow's matrix runs
the eight parts of its check and the four of its full run that way.

The parts are split by time, so that they end together: a job's wall is its part's, and the check
waits on its slowest part. `testing/shard-times.tsv` holds the seconds of each test that took
`FLOOR` or more in a whole run of the suite, by `key`, a short sha256 of its node id: a node id
can hold a placeholder in the shape of a private value, such as a thread id, which the push hook
refuses, and the keys keep the table small. Then the selected tests are dealt out slowest first,
each to the part with the least time so far. A test the table does not hold counts as `FLOOR`:
half the suite takes less, and the table leaves those out to stay small, and a new test is most
likely one of them. No part then holds more than the slowest selected test's time over another.

The split reads only the selected tests' node ids and the table, so every xdist worker and every
job works out the same parts for the same selection, and each test is in exactly one part. The
parts split what the run selected, so the tests `make check-fast` names are split as the whole
suite is. A part that holds none of them passes, since a small selection leaves some parts
empty. A selection with no tests at all fails in every part, as it fails whole: under xdist the
controller sets the exit status and never collects, so each worker tells it whether the
selection had tests. `testing/tests/test_shards.py` holds the parts to the whole collection.

`--shard-record PATH` writes the table from a run: `uv run pytest -n 4 -m "not browser"
--shard-record testing/shard-times.tsv` after tests are added or grow slow."""

import hashlib
import heapq
from pathlib import Path

import pytest

TIMES = Path(__file__).with_name("shard-times.tsv")
FLOOR = 0.1


def pytest_addoption(parser):
    parser.addoption(
        "--shard",
        metavar="K/N",
        help="run only the K-th of N parts of the selected tests, split by each test's time",
    )
    parser.addoption(
        "--shard-times",
        metavar="PATH",
        default=str(TIMES),
        help="the seconds of each test that --shard splits by (default: testing/shard-times.tsv)",
    )
    parser.addoption(
        "--shard-record",
        metavar="PATH",
        help="write the seconds of each test in this run that took 0.1 s or more to PATH",
    )


def key(nodeid: str) -> str:
    """The test's key in the table: the first 16 hex digits of the sha256 of its node id."""
    return hashlib.sha256(nodeid.encode()).hexdigest()[:16]


def read_times(path: Path) -> dict[str, float]:
    """The table's seconds by key: a line is the seconds, a tab, and the key. With no table every
    test counts as `FLOOR`, so the parts split by count."""
    if not path.exists():
        return {}
    times = {}
    for line in path.read_text().splitlines():
        seconds, _, test = line.partition("\t")
        times[test] = float(seconds)
    return times


def seconds(times: dict[str, float], nodeid: str) -> float:
    """The test's seconds in the table, or `FLOOR` for a test it does not hold."""
    return times.get(key(nodeid), FLOOR)


def split(nodeids: list[str], times: dict[str, float], parts: int) -> list[list[str]]:
    """The tests of each part, dealt slowest first to the part with the least time so far."""
    load = [(0.0, at) for at in range(parts)]
    dealt: list[list[str]] = [[] for _ in range(parts)]
    for nodeid in sorted(nodeids, key=lambda test: (-seconds(times, test), test)):
        so_far, at = heapq.heappop(load)
        dealt[at].append(nodeid)
        heapq.heappush(load, (so_far + seconds(times, nodeid), at))
    return dealt


def shard(config) -> tuple[int, int] | None:
    text = config.getoption("shard")
    if not text:
        return None
    one, _, of = text.partition("/")
    if not (one.isdigit() and of.isdigit() and 1 <= int(one) <= int(of)):
        raise pytest.UsageError(f"--shard takes K/N with 1 <= K <= N, not {text!r}")
    return int(one), int(of)


SELECTED = pytest.StashKey[bool]()


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    which = shard(config)
    if which is None:
        return
    config.stash[SELECTED] = bool(items)
    if hasattr(config, "workeroutput"):
        config.workeroutput["selected"] = bool(items)
    one, of = which
    times = read_times(Path(config.getoption("shard_times")))
    mine = set(split([item.nodeid for item in items], times, of)[one - 1])
    kept, left = [], []
    for item in items:
        (kept if item.nodeid in mine else left).append(item)
    if left:
        config.hook.pytest_deselected(items=left)
        items[:] = kept


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    if getattr(node, "workeroutput", {}).get("selected"):
        node.config.stash[SELECTED] = True


class Record:
    """Each test's setup, call and teardown, summed, written to the table at the end where it is
    `FLOOR` or more. It runs where the reports end up: under xdist on the controller, which hears
    every worker's."""

    def __init__(self, path: Path):
        self.path = path
        self.seconds: dict[str, float] = {}

    def pytest_runtest_logreport(self, report):
        self.seconds[report.nodeid] = self.seconds.get(report.nodeid, 0.0) + report.duration

    def pytest_sessionfinish(self):
        self.path.write_text(
            "".join(
                f"{took:.2f}\t{test}\n"
                for test, took in sorted((key(test), took) for test, took in self.seconds.items())
                if took >= FLOOR
            )
        )


def pytest_configure(config):
    record = config.getoption("shard_record")
    if record and not hasattr(config, "workerinput"):
        config.pluginmanager.register(Record(Path(record)), "shard-record")


def pytest_sessionfinish(session, exitstatus):
    selected = session.config.stash.get(SELECTED, False)
    if shard(session.config) and selected and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
        session.exitstatus = pytest.ExitCode.OK
