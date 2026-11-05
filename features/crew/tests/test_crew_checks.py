"""The crew skill's "The checks" gives the state of a pull request's checks as one of four
answers."""

import os
import re
import subprocess

import pytest

from crew_helpers import BRIEF, ROLLUPS, block, git, said, sections, stub_gh
from testing.layouts import assembled


class Pushed:
    """A crewmate's worktree at the head its pull request has, and the brief with its Result."""

    def __init__(self, tmp_path, rollup, draft=False):
        self.work = tmp_path / "work"
        self.work.mkdir()
        git(self.work, "init", "-q", "-b", "a-task")
        git(self.work, "commit", "-q", "--allow-empty", "-m", "the task")
        self.head = git(self.work, "rev-parse", "HEAD")
        self.state = tmp_path / "state"
        (self.state / "tasks").mkdir(parents=True)
        self.brief = self.state / "tasks" / "alpha.md"
        self.brief.write_text(BRIEF)
        self.stub = tmp_path / "stub"
        stub_gh(self.stub, self.head, rollup, draft=draft)

    def says(self):
        ran = subprocess.run(
            ["sh", "-c", block("Stay on the pull request", "--checks").replace("<slug>", "alpha")],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "H": str(self.state),
                "T": str(assembled() / "templates"),
            },
            check=True,
        )
        (line,) = ran.stdout.splitlines()
        return line


@pytest.mark.parametrize("case", ROLLUPS)
def test_the_state_of_the_checks_is_one_of_four_answers(case, tmp_path):
    rollup, answer = ROLLUPS[case]
    assert Pushed(tmp_path, rollup).says().split(": ")[0] == answer


def test_checks_that_passed_are_said_with_the_head_they_passed_at(tmp_path):
    pushed = Pushed(tmp_path, ROLLUPS["all passed"][0])
    assert pushed.says() == f"passed: every check passed at {pushed.head}"


@pytest.mark.parametrize("case", ["none ran", "all skipped"])
def test_checks_that_did_not_run_are_not_green_whatever_the_result_says_stood_in(case, tmp_path):
    pushed = Pushed(tmp_path, ROLLUPS[case][0])
    unrun = f"unrun: no check ran at {pushed.head}"
    assert pushed.says() == unrun
    with pushed.brief.open("a") as result:
        result.write(f"CI: did not run at {pushed.head}, `make check` passed in this worktree\n")
    assert pushed.says() == unrun


@pytest.mark.parametrize("case", ["all passed", "one ran and failed"])
def test_a_drafts_checks_are_read_as_any_pull_requests(case, tmp_path):
    """CI checks a draft on each push as it checks any open pull request (check.yml), so its
    rollup is read as any other's: green when its checks passed, red when one failed, and never
    a wait for being a draft."""
    pushed = Pushed(tmp_path, ROLLUPS[case][0], draft=True)
    assert pushed.says().split(":")[0] == ROLLUPS[case][1]


def test_the_review_is_launched_only_once_check_has_passed(tmp_path):
    """The deterministic checks prove or fail the work before a reviewer reads it: the crew
    launches on `passed` alone, and the reviewer's own readiness check agrees."""
    import test_pr_review_skill as review

    def launcher(name, rollup):
        (tmp_path / name).mkdir()
        return review.Launcher(tmp_path / name, rollup).says()

    ready_at = [f"a-task: ready, {review.URL} at {review.HEAD}"]
    running = ["a-task: not ready, its checks, wait: a check has not finished"]
    pending = [{"__typename": "StatusContext", "state": "PENDING"}]
    assert launcher("pending", pending) == running
    assert launcher("running", ROLLUPS["one still running"][0]) == running
    assert launcher("passed", ROLLUPS["all passed"][0]) == ready_at
    failure = [{"__typename": "StatusContext", "state": "FAILURE"}]
    assert launcher("failed", failure) == [
        "a-task: not ready, its checks, failed: a check ran and failed"
    ]
    (tmp_path / "crew").mkdir()
    assert Pushed(tmp_path / "crew", pending).says() == "wait: a check has not finished"

    when = block("The review", "checked=")
    does = {}
    for case in ("all passed", "one still running", "one ran and failed", "none ran"):
        (tmp_path / case).mkdir()
        printed = Pushed(tmp_path / case, ROLLUPS[case][0]).says()
        script = when.replace('<the line the block of "The checks" printed>', printed)
        ran = subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=True)
        does[printed.split(":")[0]] = ran.stdout.split(":")[0]
    assert does == {
        "passed": "launch",
        "wait": "no launch yet",
        "failed": "fix first",
        "unrun": "no launch",
    }

    stay = sections()["Stay on the pull request"]
    steps = re.findall(r"^(\d)\. (.*)$", stay.split("What wakes this thread")[0], re.M)
    (launch,) = [int(number) for number, step in steps if "start its review now" in step]
    (end,) = [int(number) for number, step in steps if step.startswith("End your turn")]
    assert launch < end
    (tmp_path / "state").mkdir()
    assert said(tmp_path / "state", "The review", "launch a reviewer", BRIEF) == [
        "review: launch a reviewer"
    ]
