"""`--shard K/N`: run only the K-th of N parts of the tests the run selected, so that N jobs run
the suite side by side. `make check SHARD=K/N` passes it, and the check workflow's matrix runs
the eight parts of its check and the four of its full run that way. The split by time and its
tables are `testing/split.py`'s.

The split reads only the selected tests' node ids and the table, so every xdist worker and every
job works out the same parts for the same selection, and each test is in exactly one part. The
parts split what the run selected, so the tests `make check-fast` names are split as the whole
suite is. A part that holds none of them passes, since a small selection leaves some parts
empty. A selection with no tests at all fails in every part, as it fails whole: under xdist the
controller sets the exit status and never collects, so each worker tells it whether the
selection had tests. `testing/tests/test_shards.py` holds the parts to the whole collection.

`--shard-tests=<file>:<key>,<key>...` runs, of that file, only the tests it names by `key`, and
`--shard-skip=<file>:<key>,<key>...` runs all of that file's tests but those, each given once a
file: the check's job `reuse` deals a file whose tests sum past a part's share out by test
(`scripts/select_tests.py`'s `dealt`), from the table's rows of that file, and the part's list of
files carries these tokens for it, since a node id can hold a space or a quote, which
`make test TESTS=...` would split. One piece of such a file skips the others' tests rather than
naming its own, so a test the table does not hold, one under `FLOOR` or added since, runs in
exactly one part. A part those tokens leave with no test passes, as a part with no test of the
selection does.

The table holds CI's times, not a desk's: the tests run several times slower on the 4 cores of
GitHub's runner, and not by one factor. Each part of `full` keeps its junit report as the artifact
`junit-<attempt>-<k>`, and `uv run python -m testing.shard` writes both tables from the last `RUNS`
green full runs of main that kept them, each test's median over them: that command, run at a desk
with `gh` and its diff committed, is how the table is refreshed, when the parts' walls drift apart
or many tests are added; where the merge flow's TLC test's row moved, its pin below moves with it,
as test_flow_spec.py's test says. Main's full runs restore main's TLC cache, so the merge flow's TLC
test is in at its warm time, as the check's parts run it. `--shard-record PATH` writes them from a
run of this machine instead, the file table beside PATH:
`uv run pytest -n 4 -m "not browser" --shard-record PATH`. There a test whose time on this
machine is not its time in CI pins its CI seconds with `@pytest.mark.shard_seconds(S)`, and the
record writes S for it in place of the time it took, in both tables."""

import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from testing.split import FILE_TIMES, TIMES, file_table, key, read_times, split, table

RUNS = 5
REPO = Path(__file__).resolve().parent.parent
CHECK = REPO / ".github/workflows/check.yml"


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
    parser.addoption(
        "--shard-tests",
        metavar="FILE:KEYS",
        action="append",
        default=[],
        help="of FILE, run only the tests these comma-separated keys name",
    )
    parser.addoption(
        "--shard-skip",
        metavar="FILE:KEYS",
        action="append",
        default=[],
        help="of FILE, run every test but the ones these comma-separated keys name",
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


def scoped(words: list[str]) -> dict[str, set[str]]:
    """The keys of each file that `--shard-tests` or `--shard-skip` words name."""
    named: dict[str, set[str]] = {}
    for word in words:
        file, _, keys = word.rpartition(":")
        named.setdefault(file, set()).update(keys.split(","))
    return named


def picked(nodeids: list[str], only: dict[str, set[str]], skip: dict[str, set[str]]) -> list[str]:
    """The node ids `--shard-tests` and `--shard-skip` keep: of a file `only` names, the tests
    it names; of a file `skip` names, the tests it does not name; and every test of the others."""
    kept = []
    for nodeid in nodeids:
        file = nodeid.partition("::")[0]
        if file in only and key(nodeid) not in only[file]:
            continue
        if file in skip and key(nodeid) in skip[file]:
            continue
        kept.append(nodeid)
    return kept


def picking(config) -> bool:
    return bool(config.getoption("shard_tests") or config.getoption("shard_skip"))


@pytest.hookimpl(trylast=True)
def pytest_collection_modifyitems(config, items):
    which = shard(config)
    if which is None and not picking(config):
        return
    config.stash[SELECTED] = bool(items)
    if hasattr(config, "workeroutput"):
        config.workeroutput["selected"] = bool(items)
    if picking(config):
        only, skip = scoped(config.getoption("shard_tests")), scoped(config.getoption("shard_skip"))
        mine = set(picked([item.nodeid for item in items], only, skip))
        left = [item for item in items if item.nodeid not in mine]
        if left:
            config.hook.pytest_deselected(items=left)
            items[:] = [item for item in items if item.nodeid in mine]
    if which is None:
        return
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
        self.path.write_text(table(took))
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
    chosen = shard(session.config) or picking(session.config)
    if chosen and selected and exitstatus == pytest.ExitCode.NO_TESTS_COLLECTED:
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


def recorded(runs: list[list[Path]], nodeids: list[str]) -> tuple[dict[str, float], int, int]:
    """Each collected test's seconds from the junit reports of these runs, each run its parts'
    reports: its median over the runs that ran it, and none for a test no run ran, which both
    tables count as `FLOOR`. With it the count of the reports' tests, and of those no collected
    node id matches, which a test renamed since the runs leaves out."""
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
                took.setdefault(by[case], []).append(seconds)
            else:
                unknown += 1
    medians = {
        nodeid: statistics.median(took[nodeid]) if nodeid in took else 0.0 for nodeid in nodeids
    }
    return medians, read, unknown


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


def full_parts(workflow: Path) -> int:
    """How many parts the job `full-shard` of this workflow runs: its matrix's `shard` list."""
    job = re.search(r"^  full-shard:\n((?:(?:    .*)?\n)*)", workflow.read_text(), re.M)
    shards = job and re.search(r"^ +shard: \[(.*)\]$", job[1], re.M)
    if not shards:
        sys.exit(f"shard.py: {workflow} has no job full-shard with a matrix of shards")
    return len(shards[1].split(","))


def downloaded(count: int, branch: str, into: Path) -> list[list[Path]]:
    """The junit reports of the last `count` green runs of the check on `branch` that are not a
    pull request's and kept one from each of `full`'s parts, as many as check.yml's matrix gives
    it, each part's latest attempt: a run that skipped the suite on a green tree's marker keeps
    none, and a run of a full with another count of parts does not count."""
    want = full_parts(CHECK)
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
        if len(parts) == want:
            print(f"run {run['databaseId']}: {len(parts)} parts", file=sys.stderr)
            runs.append(parts)
        if len(runs) == count:
            break
    return runs


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="python -m testing.shard",
        description="write testing/shard-times.tsv and shard-file-times.tsv beside it from the"
        " junit reports of CI's full runs",
    )
    parser.add_argument("--runs", type=int, default=RUNS, help=f"how many runs (default {RUNS})")
    parser.add_argument("--branch", default="main", help="whose runs (default main)")
    parser.add_argument(
        "--out", type=Path, default=TIMES, help="the table to write, the file table beside it"
    )
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory() as into:
        runs = downloaded(args.runs, args.branch, Path(into))
        if not runs:
            sys.exit(f"shard.py: no green full run of {args.branch} kept its junit reports")
        took, read, unknown = recorded(runs, collected())
    written = table(took)
    args.out.write_text(written)
    args.out.with_name(FILE_TIMES.name).write_text(file_table(took))
    print(
        f"{args.out}: {written.count(chr(10))} tests from {len(runs)} runs,"
        f" {read} reports' tests of which {unknown} no collected test matches",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main(sys.argv[1:])
