"""`--shard K/N`: run only the K-th of N parts of the tests the run selected, so that N jobs run
the suite side by side. `make check SHARD=K/N` passes it, and the check workflow's matrix runs
the four parts of its full run that way. The split by time and its tables are
`testing/split.py`'s.

The split reads only the selected tests' node ids and the table, so every xdist worker and every
job works out the same parts for the same selection, and each test is in exactly one part. The
parts split what the run selected, so the tests `make check-fast` names are split as the whole
suite is. A part that holds none of them passes, since a small selection leaves some parts
empty. A selection with no tests at all fails in every part, as it fails whole: under xdist the
controller sets the exit status and never collects, so each worker tells it whether the
selection had tests. `testing/tests/test_shards.py` holds the parts to the whole collection.

`--shard-record PATH` writes the table from a run, and the file table beside it:
`uv run pytest -n 4 -m "not browser" --shard-record testing/shard-times.tsv` after tests are
added or grow slow. A test whose time on this machine is not its time in CI, as the merge flow's
TLC test runs in well under a second where its cache holds the runs, pins its CI seconds with
`@pytest.mark.shard_seconds(S)`, and the record writes S for it in place of the time it took, in
both tables."""

from pathlib import Path

import pytest

from testing.split import FILE_TIMES, FLOOR, TIMES, file_table, key, read_times, split


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
        help="write the seconds of each test in this run that took 0.1 s or more to PATH, and"
        " each test file's to shard-file-times.tsv beside it",
    )


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


PINNED = "shard_seconds"


class Record:
    """Each test's setup, call and teardown, summed, written to the table at the end where it is
    `FLOOR` or more, or the seconds its `shard_seconds` marker pins in their place, and each test
    file's to the file table beside it. It runs where the reports end up: under xdist on the
    controller, which hears every worker's, and a report carries the pin there in its user
    properties."""

    def __init__(self, path: Path):
        self.path = path
        self.seconds: dict[str, float] = {}
        self.pinned: dict[str, float] = {}

    def pytest_runtest_logreport(self, report):
        self.seconds[report.nodeid] = self.seconds.get(report.nodeid, 0.0) + report.duration
        for name, value in report.user_properties:
            if name == PINNED:
                self.pinned[report.nodeid] = value

    def pytest_sessionfinish(self):
        took = {test: self.pinned.get(test, spent) for test, spent in self.seconds.items()}
        self.path.write_text(
            "".join(
                f"{spent:.2f}\t{test}\n"
                for test, spent in sorted((key(test), spent) for test, spent in took.items())
                if spent >= FLOOR
            )
        )
        self.path.with_name(FILE_TIMES.name).write_text(file_table(took))


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        f"{PINNED}(seconds): the test's seconds in CI, which --shard-record writes in place of"
        " the time it took here",
    )
    record = config.getoption("shard_record")
    if record and not hasattr(config, "workerinput"):
        config.pluginmanager.register(Record(Path(record)), "shard-record")


def pytest_itemcollected(item):
    """Put the test's pinned seconds in its user properties, which each of its reports carries,
    also from an xdist worker to the controller where the record runs, and also where it is
    skipped, as on a machine with no Java."""
    marker = item.get_closest_marker(PINNED)
    if marker and item.config.getoption("shard_record"):
        item.user_properties.append((PINNED, float(marker.args[0])))


def pytest_sessionfinish(session, exitstatus):
    selected = session.config.stash.get(SELECTED, False)
    if shard(session.config) and selected and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
        session.exitstatus = pytest.ExitCode.OK
