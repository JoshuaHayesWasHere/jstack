"""`--shard K/N`: run only the K-th of N parts of the tests the run selected, so that N jobs run
the suite side by side. `make check SHARD=K/N` passes it, and the check workflow's matrix runs
the eight parts of its check and the four of its full run that way.

The parts are split by time, so that they end together: a job's wall is its part's, and the check
waits on its slowest part. `testing/shard-times.tsv` holds the seconds of each test that took
`FLOOR` or more in a whole run of the suite, by `key`, a short sha256 of its node id: a node id
can hold a placeholder in the shape of a private value, such as a thread id, which the push hook
refuses, and the keys keep the table small. A test the table does not hold counts as `FLOOR`:
half the suite takes less, and the table leaves those out to stay small, and a new test is most
likely one of them.

A part runs its tests on `WORKERS` workers at once, so it ends once its tests' summed time over
`WORKERS` has passed, and never before its slowest test, which one worker runs alone. The
selected tests are dealt out slowest first, each to the part it would end soonest in, and where
it would end as soon in several, to the one with the fewest seconds so far. So a test longer than
the others' share of a part gets a part of its own, and tests that move no part's end spread
over the parts by their seconds, and do not pile onto the part whose slowest test leaves its
workers room.
`WORKERS` is the Makefile's TEST_WORKERS in CI, one for each of the 4 cores of GitHub's hosted
runner: a constant, not this machine's count, so every job deals the same parts.

The split reads only the selected tests' node ids and the table, so every xdist worker and every
job works out the same parts for the same selection, and each test is in exactly one part. The
parts split what the run selected, so the tests `make check-fast` names are split as the whole
suite is. A part that holds none of them passes, since a small selection leaves some parts
empty. A selection with no tests at all fails in every part, as it fails whole: under xdist the
controller sets the exit status and never collects, so each worker tells it whether the
selection had tests. `testing/tests/test_shards.py` holds the parts to the whole collection.

`--shard-tests=<key>,<key>...` runs, of each file one of whose tests it names by `key`, only the
tests it names, and every test of the other files: the check's job `select` deals a file whose
tests sum past a part's share out by test (`scripts/select_tests.py`'s `dealt`), and the part's
list of files carries this token for them, since a node id can hold a space or a quote, which
`make test TESTS=...` would split.

The table holds CI's times, not a desk's: the tests run several times slower on the 4 cores of
GitHub's runner, and not by one factor. Each part of `full` keeps its junit report as the
artifact `junit-<attempt>-<k>`, and `uv run python -m testing.shard` writes the table from the last
`RUNS` green full runs of main that kept them, each test's median over them: that command, run at
a desk with `gh` and its diff committed, is how the table is refreshed, when the parts' walls
drift apart or many tests are added. Main's full runs restore main's TLC cache, so the merge
flow's TLC test is in at its warm time, as the check's parts run it. `--shard-record PATH` writes it from a run of this machine instead:
`uv run pytest -n 4 -m "not browser" --shard-record PATH`. There a test whose time on this
machine is not its time in CI pins its CI seconds with `@pytest.mark.shard_seconds(S)`, and the
record writes S for it in place of the time it took."""

import argparse
import hashlib
import json
import re
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

TIMES = Path(__file__).with_name("shard-times.tsv")
FLOOR = 0.1
WORKERS = 4
RUNS = 5
REPO = Path(__file__).resolve().parent.parent


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
    parser.addoption(
        "--shard-tests",
        metavar="KEYS",
        help="of each file one of whose tests these comma-separated keys name, run only those",
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


def shard(config) -> tuple[int, int] | None:
    text = config.getoption("shard")
    if not text:
        return None
    one, _, of = text.partition("/")
    if not (one.isdigit() and of.isdigit() and 1 <= int(one) <= int(of)):
        raise pytest.UsageError(f"--shard takes K/N with 1 <= K <= N, not {text!r}")
    return int(one), int(of)


SELECTED = pytest.StashKey[bool]()


def picked(nodeids: list[str], keys: set[str]) -> list[str]:
    """The node ids `--shard-tests` keeps: every test of a file none of whose tests `keys` names,
    and of the other files only the tests it names."""
    named = {nodeid.partition("::")[0] for nodeid in nodeids if key(nodeid) in keys}
    return [
        nodeid
        for nodeid in nodeids
        if nodeid.partition("::")[0] not in named or key(nodeid) in keys
    ]


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    keys = config.getoption("shard_tests")
    if keys:
        mine = set(picked([item.nodeid for item in items], set(keys.split(","))))
        left = [item for item in items if item.nodeid not in mine]
        if left:
            config.hook.pytest_deselected(items=left)
            items[:] = [item for item in items if item.nodeid in mine]
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
    `FLOOR` or more, or the seconds its `shard_seconds` marker pins in their place. It runs where
    the reports end up: under xdist on the controller, which hears every worker's, and a report
    carries the pin there in its user properties."""

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
        self.path.write_text(
            "".join(
                f"{took:.2f}\t{test}\n"
                for test, took in sorted(
                    (key(test), self.pinned.get(test, took)) for test, took in self.seconds.items()
                )
                if took >= FLOOR
            )
        )


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


def mangled(nodeid: str) -> tuple[str, str]:
    """The classname and name pytest's junit report gives the test of this node id."""
    path, bracket, params = nodeid.partition("[")
    names = path.split("::")
    names[0] = re.sub(r"\.py$", "", names[0].replace("/", "."))
    names[-1] += bracket + params
    return ".".join(names[:-1]), names[-1]


def cases(report: Path) -> dict[tuple[str, str], float]:
    """Each test's seconds in a junit report, by its classname and name: its setup, call and
    teardown, as pytest's junit report sums them."""
    return {
        (case.get("classname", ""), case.get("name", "")): float(case.get("time") or 0)
        for case in ET.parse(report).getroot().iter("testcase")
    }


def recorded(runs: list[list[Path]], nodeids: list[str]) -> tuple[str, int, int]:
    """The table from the junit reports of these runs, each run its parts' reports: each
    collected test's median seconds over the runs that ran it, where that is `FLOOR` or more.
    With it the count of the reports' tests, and of those no collected node id matches, which
    a test renamed since the runs leaves out."""
    by = {mangled(nodeid): nodeid for nodeid in nodeids}
    took: dict[str, list[float]] = {}
    read = unknown = 0
    for parts in runs:
        run: dict[tuple[str, str], float] = {}
        for report in parts:
            run |= cases(report)
        read += len(run)
        for case, seconds in run.items():
            if case in by:
                took.setdefault(key(by[case]), []).append(seconds)
            else:
                unknown += 1
    rows = sorted((test, statistics.median(each)) for test, each in took.items())
    return "".join(f"{each:.2f}\t{test}\n" for test, each in rows if each >= FLOOR), read, unknown


def collected() -> list[str]:
    """The node ids of the whole suite but its browser tests, as `make check` runs it."""
    ran = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"]
        + ["-m", "not browser"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    if ran.returncode:
        sys.exit(f"shard.py: pytest could not collect the suite:\n{ran.stdout}{ran.stderr}")
    return [line for line in ran.stdout.splitlines() if "::" in line]


def downloaded(count: int, branch: str, into: Path) -> list[list[Path]]:
    """The junit reports of the last `count` green runs of the check on `branch` that are not a
    pull request's and kept one from each of `full`'s 4 parts, each part's latest attempt: a run
    that skipped the suite on a green tree's marker keeps none."""
    listed = subprocess.run(
        ["gh", "run", "list", "--workflow", "check.yml", "--branch", branch, "--status"]
        + ["success", "--limit", "100", "--json", "databaseId,event"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    runs = []
    for run in json.loads(listed.stdout):
        if run["event"] == "pull_request":
            continue
        at = into / str(run["databaseId"])
        got = subprocess.run(
            ["gh", "run", "download", str(run["databaseId"]), "--pattern", "junit-*"]
            + ["--dir", str(at)],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        latest: dict[str, tuple[int, Path]] = {}
        for report in at.glob("junit-*-*/*.xml") if got.returncode == 0 else []:
            attempt, _, part = report.parent.name.removeprefix("junit-").partition("-")
            latest[part] = max(latest.get(part, (0, report)), (int(attempt), report))
        parts = [report for _, report in sorted(latest.values())]
        if len(parts) == WORKERS:
            print(f"run {run['databaseId']}: {len(parts)} parts", file=sys.stderr)
            runs.append(parts)
        if len(runs) == count:
            break
    return runs


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m testing.shard",
        description="write testing/shard-times.tsv from the junit reports of CI's full runs",
    )
    parser.add_argument("--runs", type=int, default=RUNS, help=f"how many runs (default {RUNS})")
    parser.add_argument("--branch", default="main", help="whose runs (default main)")
    parser.add_argument("--out", type=Path, default=TIMES, help="the table to write")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as into:
        runs = downloaded(args.runs, args.branch, Path(into))
        if not runs:
            sys.exit(f"shard.py: no green full run of {args.branch} kept its junit reports")
        table, read, unknown = recorded(runs, collected())
    args.out.write_text(table)
    print(
        f"{args.out}: {table.count(chr(10))} tests from {len(runs)} runs,"
        f" {read} reports' tests of which {unknown} no collected test matches",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
