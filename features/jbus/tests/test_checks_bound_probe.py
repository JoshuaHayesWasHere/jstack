"""`checks_bound_probe.round_end` ends a head's round of checks where jmerge's verdict on it is
settled: at its first failed required job, or at the end of its last required job. A job of a
workflow no required check names, such as `browser`, neither ends a round nor holds one open.

The check runs are shaped as GitHub's `commits/<head>/check-runs` gives them: the workflow run of
each is the number in its `html_url`.

The probe itself runs against a stand-in `gh` on PATH, which answers from files as GitHub's API
does, ETags included, and a `work.json` the test writes.
"""

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from checks_bound_probe import round_end

REQUIRED = ("check", "borders", "macos")
WORKFLOW_OF = {"1": "check", "2": "borders", "3": "macos", "4": "browser"}
RUN_OF = {workflow: run for run, workflow in WORKFLOW_OF.items()}
INOTIFY = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="inotify: the probe watches work.json through libc.so.6's inotify, which only Linux has",
)
"""A test that runs the probe itself, which only runs on Linux, beside a jbus that runs there."""


def job(name: str, workflow: str, ended: str = "", conclusion: str = "success") -> dict:
    return {
        "name": name,
        "status": "completed" if ended else "in_progress",
        "conclusion": conclusion if ended else None,
        "completed_at": f"2026-11-08T05:{ended}Z" if ended else None,
        "html_url": f"https://github.com/o/r/actions/runs/{RUN_OF[workflow]}/job/{len(name)}",
    }


def at(ended: str) -> float:
    return datetime.fromisoformat(f"2026-11-08T05:{ended}Z").timestamp()


PASSED = [
    *(job(f"check {n} of 8", "check", f"20:{n:02}") for n in range(1, 9)),
    job("check", "check", "20:30"),
    job("borders", "borders", "19:40"),
    job("macos 1 of 3", "macos", "20:10"),
    job("macos", "macos", "20:20"),
]


def test_a_failed_required_job_ends_the_round_while_others_go():
    runs = [
        job("check 1 of 8", "check"),
        job("check 2 of 8", "check", "18:44", "failure"),
        job("check 6 of 8", "check", "19:08", "failure"),
        job("borders", "borders", "18:10"),
        job("macos 1 of 3", "macos"),
        job("browser", "browser", "18:00", "failure"),
    ]
    assert round_end(runs, WORKFLOW_OF, REQUIRED) == (at("18:44"), "failed")


def test_a_passed_round_ends_at_its_last_required_job():
    assert round_end(PASSED, WORKFLOW_OF, REQUIRED) == (at("20:30"), "passed")


def test_a_late_non_required_job_neither_holds_nor_moves_the_end():
    going = [*PASSED, job("browser", "browser")]
    ended = [*PASSED, job("browser", "browser", "21:50", "failure")]
    assert round_end(going, WORKFLOW_OF, REQUIRED) == (at("20:30"), "passed")
    assert round_end(ended, WORKFLOW_OF, REQUIRED) == (at("20:30"), "passed")


def test_a_required_check_github_lists_no_run_of_yet_holds_the_round():
    """GitHub lists `check` only once the shards it needs have ended (#1246)."""
    shards = [one for one in PASSED if one["name"] != "check"]
    assert round_end(shards, WORKFLOW_OF, REQUIRED) is None


GH = """#!{python}
import hashlib, os, sys
from pathlib import Path

state = Path(os.environ["PROBE_GH"])
path = sys.argv[2]
with (state / "calls").open("a") as calls:
    calls.write(path + "\\n")
kind = path.split("/")[3]
name = {{"pulls": "pull", "commits": path.split("/")[-2], "actions": "workflow"}}[kind]
body = (state / f"{{name}}.json").read_text()
etag = '"' + hashlib.sha1(body.encode()).hexdigest() + '"'
if f"If-None-Match: {{etag}}" in sys.argv:
    print(f"HTTP/2.0 304 Not Modified\\netag: {{etag}}\\n")
else:
    print(f"HTTP/2.0 200 OK\\netag: {{etag}}\\n\\n{{body}}")
"""


class GitHub:
    """The stand-in's state: the pull request's head and the check runs of each head."""

    def __init__(self, folder: Path):
        self.folder = folder
        folder.mkdir()
        (folder / "workflow.json").write_text(json.dumps({"name": "check"}))
        (folder / "bin").mkdir()
        gh = folder / "bin" / "gh"
        gh.write_text(GH.format(python=sys.executable))
        gh.chmod(0o755)

    def head(self, sha: str, ended: float | None) -> None:
        """Make `sha` the head, with its one required job going, or ended at `ended`."""
        check = job("check", "check")
        if ended is not None:
            check["status"], check["conclusion"] = "completed", "success"
            check["completed_at"] = datetime.fromtimestamp(ended, UTC).isoformat()
        (self.folder / f"{sha}.json").write_text(json.dumps({"check_runs": [check]}))
        (self.folder / "pull.json").write_text(json.dumps({"head": {"sha": sha}}))

    def asked(self, path: str) -> None:
        calls = self.folder / "calls"
        until = time.time() + 10
        while time.time() < until:
            if calls.exists() and path in calls.read_text().splitlines():
                return
            time.sleep(0.05)
        raise AssertionError(f"the probe never asked GitHub for {path}")


class Probe:
    """The probe, run against the stand-in GitHub and a `work.json` the test writes.

    GitHub gives a job's end to the second, so a test waits a second after the row's line first
    has the pull request before it ends a head: an end floored to the second could otherwise come
    before it, and the probe would rightly record no round."""

    def __init__(self, tmp_path: Path):
        self.github = GitHub(tmp_path / "gh")
        self.work = tmp_path / "jbus" / "work.json"
        self.work.parent.mkdir()
        self.required = tmp_path / "required-checks"
        self.required.write_text("check\n")
        self.out = tmp_path / "rounds.jsonl"

    def line(self, says: str, ended: str = "") -> None:
        """Write the row's line of pull request #7 saying `says`, naming `ended` as ended."""
        self.work.write_text(
            json.dumps(
                {"work": [{"pr": "#7", "value": says, **({"ended": ended} if ended else {})}]}
            )
        )

    def no_line(self) -> None:
        """Write a `work.json` whose row has no pull request yet."""
        self.work.write_text(json.dumps({"work": [{"key": "a-task", "value": "under way"}]}))

    def start(self) -> None:
        self.run = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).with_name("checks_bound_probe.py")),
                *("--repo", "o/r", "--pr", "7", "--work", str(self.work), "--wait", "10"),
                *("--required", str(self.required), "--out", str(self.out)),
            ],
            env={
                **os.environ,
                "PATH": f"{self.github.folder / 'bin'}{os.pathsep}{os.environ['PATH']}",
                "PROBE_GH": str(self.github.folder),
            },
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

    def rounds(self) -> tuple[list[dict], str]:
        """The rounds the probe recorded once it stopped, and what it printed."""
        try:
            said, _ = self.run.communicate(timeout=20)
        finally:
            self.run.kill()
        return [json.loads(one) for one in self.out.read_text().splitlines()], said


@INOTIFY
def test_a_probe_started_after_a_head_settled_records_the_next_heads_round(tmp_path):
    """On #1264 the probe started after head 1's checks had settled, and recorded nothing."""
    probe = Probe(tmp_path)
    probe.line("checks passed", "aaa")
    probe.github.head("aaa", int(time.time()) - 60)
    probe.start()
    probe.github.asked("repos/o/r/commits/aaa/check-runs")
    probe.github.head("bbb", None)
    probe.github.asked("repos/o/r/commits/bbb/check-runs")
    time.sleep(1.1)
    probe.github.head("bbb", int(time.time()))
    time.sleep(1.5)
    probe.line("checks passed at bbb", "bbb")
    rounds, said = probe.rounds()
    assert [(one["head"], one["verdict"], one["says"]) for one in rounds] == [
        ("bbb", "passed", "checks passed at bbb")
    ], said
    assert 1 <= rounds[0]["delay"] < 5, said


@INOTIFY
def test_a_round_ends_at_the_first_write_that_names_its_head_as_ended(tmp_path):
    """On #1271, 8 of 12 failed rounds were timed to a pass's write at its start, which named no
    verdict, before the tick had read the head at all (sa-checks-bound-measure-8)."""
    probe = Probe(tmp_path)
    probe.line("checks running", "aaa")
    probe.github.head("bbb", None)
    probe.start()
    probe.github.asked("repos/o/r/commits/bbb/check-runs")
    time.sleep(1.1)
    probe.github.head("bbb", int(time.time()))
    time.sleep(1.2)
    probe.line("pass started", "aaa")
    time.sleep(1.5)
    probe.line("checks passed at bbb", "bbb")
    rounds, said = probe.rounds()
    assert [(one["head"], one["says"]) for one in rounds] == [("bbb", "checks passed at bbb")], said
    assert 2.5 <= rounds[0]["delay"] < 6, said


@INOTIFY
def test_a_round_that_ended_before_the_line_had_the_pull_request_is_not_recorded(tmp_path):
    """On #1271 round 1 counted the 14 s before the row's line had `pr #1271` at all."""
    probe = Probe(tmp_path)
    probe.no_line()
    probe.github.head("bbb", None)
    probe.start()
    probe.github.asked("repos/o/r/commits/bbb/check-runs")
    probe.github.head("bbb", int(time.time()) - 1)
    time.sleep(1.5)
    probe.line("checks passed at bbb", "bbb")
    time.sleep(1.1)
    probe.github.head("ccc", None)
    probe.github.asked("repos/o/r/commits/ccc/check-runs")
    probe.github.head("ccc", int(time.time()))
    time.sleep(1.5)
    probe.line("checks passed at ccc", "ccc")
    rounds, said = probe.rounds()
    assert [(one["head"], one["says"]) for one in rounds] == [("ccc", "checks passed at ccc")], said
    assert 1 <= rounds[0]["delay"] < 5, said
