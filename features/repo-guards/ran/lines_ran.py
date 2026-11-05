"""A pytest plugin that stops a run under coverage once every line it waits for has run.

`test_new_lines_run.unrun` loads it into the run of the tests that name the code a branch adds,
with `NEW_LINES_RAN` the path of a JSON file: `{"lines": {<absolute path>: [<line>, ...]}, "data":
<coverage's data file>, "stopped": <a path>}`. After each test, a process that runs tests reads
what coverage has measured in it so far, writes that to a file of its own beside the data file,
and reads the same from every other process: the other workers, and each process a test started
that has ended and saved its data. Once every line waited for is among them, it writes the
`stopped` file and stops the run, and pytest ends 2. It waits only for the lines coverage counts
as statements, so a line a pragma excludes holds no run to its end. Lines seen here did run, so a
stop never hides a line no test runs: the verdict is still the data coverage combines once the run
ends.
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
        self.data = Path(said["data"])
        self.stopped = Path(said["stopped"])
        self.mine = self.data.parent / f"ran.{os.getpid()}.json"
        self.read: dict[Path, tuple[float, int]] = {}
        self.seen: dict[Path, set[int]] = {}

    def add(self, data: coverage.CoverageData) -> None:
        for name in data.measured_files():
            path = Path(name).resolve()
            if path in self.lines:
                self.seen.setdefault(path, set()).update(data.lines(name) or ())

    def others(self) -> None:
        """The lines in each data file of an ended process, and each other worker's file, read
        again whenever it changed."""
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
                for path, lines in ran.items():
                    self.seen.setdefault(Path(path), set()).update(lines)

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

    def done(self, cov: coverage.Coverage) -> bool:
        self.add(cov.get_data())
        here = {str(path): sorted(self.seen.get(path, ())) for path in self.lines}
        part = self.mine.with_suffix(".part")
        part.write_text(json.dumps(here))
        part.replace(self.mine)
        self.others()
        return all(lines <= self.seen.get(path, set()) for path, lines in self.lines.items())


def pytest_configure(config: pytest.Config) -> None:
    controller = config.getoption("dist", "no") != "no" and not hasattr(config, "workerinput")
    cov = coverage.Coverage.current()
    if SAID and cov and not controller:
        config.pluginmanager.register(Stop(Waiting(json.loads(Path(SAID).read_text()), cov), cov))


class Stop:
    def __init__(self, waiting: Waiting, cov: coverage.Coverage) -> None:
        self.waiting = waiting
        self.cov = cov

    @pytest.hookimpl(trylast=True)
    def pytest_runtest_teardown(self, item: pytest.Item) -> None:
        if self.waiting.done(self.cov):
            self.waiting.stopped.touch()
            item.session.shouldstop = "every line waited for has run"
