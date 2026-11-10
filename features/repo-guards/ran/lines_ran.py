"""A pytest plugin that stops a run under coverage once every file it waits on is decided.

`test_new_lines_run.unrun` loads it, beside `part_lines`, into the run of the tests that name the
code a branch adds, with `NEW_LINES_RAN` the path of a JSON file: `{"lines": {<absolute path>:
[<line>, ...]}, "names": {<absolute path>: [<test file from the repo's root>, ...]}, "reach":
{<absolute path>: [<absolute test file>, ...]}, "data": <coverage's data file>, "stopped": <a
path>}`. A line has run here only where one of the test files that names its module, its `names`,
ran it: the context `part_lines` gives each line, the rule the guard counts by, so the run never
stops on a line another module's test ran and the guard would not count. A file is decided once
each of its lines has run so, or once every test of the test files that can reach it, its
`reach`, has ended. After each test, a process that runs tests reads what coverage has measured
in it so far and the tests it has ended, writes that to a file of its own beside the data file,
and reads the same from every other process: the other workers, and each process a test started
that has ended and saved its data. Once every file waited on is decided, it writes the `stopped`
file and stops the run, and pytest ends 2. It waits only for the lines coverage counts as
statements, so a line a pragma excludes holds no run to its end. Lines seen here did run, so a
stop never hides a line no test runs: the verdict is still the data the run folds once it ends.
"""

import json
import os
from pathlib import Path

import coverage
import pytest

SAID = os.environ.get("NEW_LINES_RAN")


class Waiting:
    def __init__(self, said: dict, cov: coverage.Coverage) -> None:
        self.lines = {
            Path(path).resolve(): set(lines) & set(cov.analysis2(path)[1])
            for path, lines in said["lines"].items()
        }
        self.names = {Path(path).resolve(): set(tests) for path, tests in said["names"].items()}
        self.reach = {
            Path(path).resolve(): {Path(test).resolve() for test in tests}
            for path, tests in said["reach"].items()
        }
        self.data = Path(said["data"])
        self.stopped = Path(said["stopped"])
        self.mine = self.data.parent / f"ran.{os.getpid()}.json"
        self.read: dict[Path, tuple[float, int]] = {}
        self.seen: dict[Path, set[int]] = {}
        self.tests: dict[Path, set[str]] = {}
        self.ended: set[str] = set()
        self.ours: list[str] = []

    def collected(self, items: list[pytest.Item]) -> None:
        """The tests of the run that each file waited on can be reached by."""
        self.tests = {path: set() for path in self.lines}
        for item in items:
            for path, tests in self.reach.items():
                if item.path.resolve() in tests:
                    self.tests[path].add(item.nodeid)

    def add(self, data: coverage.CoverageData) -> None:
        for name in data.measured_files():
            path = Path(name).resolve()
            if path in self.lines:
                self.seen.setdefault(path, set()).update(
                    number
                    for number, contexts in data.contexts_by_lineno(name).items()
                    if self.names[path] & set(contexts)
                )

    def others(self) -> None:
        """The lines in each data file of an ended process, and the lines and ended tests in each
        other worker's file, read again whenever it changed."""
        for file in self.data.parent.glob(f"{self.data.name}.*"):
            if self.changed(file):
                saved = coverage.CoverageData(basename=str(file))
                try:
                    saved.read()
                except Exception:
                    self.read.pop(file, None)
                    continue
                self.add(saved)
        for file in self.data.parent.glob("ran.*.json"):
            if file != self.mine and self.changed(file):
                try:
                    ran = json.loads(file.read_text())
                except ValueError:
                    self.read.pop(file, None)
                    continue
                for path, lines in ran["lines"].items():
                    self.seen.setdefault(Path(path), set()).update(lines)
                self.ended.update(ran["ended"])

    def changed(self, file: Path) -> bool:
        try:
            stat = file.stat()
        except FileNotFoundError:
            return False
        mark = (stat.st_mtime, stat.st_size)
        if self.read.get(file) == mark:
            return False
        self.read[file] = mark
        return True

    def done(self, cov: coverage.Coverage, test: str) -> bool:
        self.add(cov.get_data())
        self.ended.add(test)
        self.ours.append(test)
        here = {str(path): sorted(self.seen.get(path, ())) for path in self.lines}
        part = self.mine.with_suffix(".part")
        part.write_text(json.dumps({"lines": here, "ended": self.ours}))
        part.replace(self.mine)
        self.others()
        return all(
            lines <= self.seen.get(path, set()) or self.tests[path] <= self.ended
            for path, lines in self.lines.items()
        )


def pytest_configure(config: pytest.Config) -> None:
    controller = config.getoption("dist", "no") != "no" and not hasattr(config, "workerinput")
    cov = coverage.Coverage.current()
    if SAID and cov and not controller:
        config.pluginmanager.register(Stop(Waiting(json.loads(Path(SAID).read_text()), cov), cov))


class Stop:
    def __init__(self, waiting: Waiting, cov: coverage.Coverage) -> None:
        self.waiting = waiting
        self.cov = cov

    def pytest_collection_finish(self, session: pytest.Session) -> None:
        self.waiting.collected(session.items)

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_teardown(self, item: pytest.Item) -> None:
        if self.waiting.done(self.cov, item.nodeid):
            self.waiting.stopped.touch()
            item.session.shouldstop = "every file waited on has run or its tests have ended"
