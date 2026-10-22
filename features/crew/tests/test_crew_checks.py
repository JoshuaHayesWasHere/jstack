"""The crew skill's "The checks": the state of a pull request's checks, one of four answers."""

import os
import re
import subprocess

import pytest

import test_home_merge as merge
import test_tool_calls as tools
from crew_helpers import BRIEF, ROLLUPS, SKILL, block, git, said, sections, stub_gh
from jmerge import ready
from test_home_thread import as_read
from testing.paths import REPO


class Pushed:
    """A crewmate's worktree at the head its pull request has, and the brief with its Result."""

    def __init__(self, tmp_path, rollup):
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
        stub_gh(self.stub, self.head, rollup)

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
                "T": str(REPO / "features" / "crew" / "templates"),
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


def test_the_result_has_a_line_for_checks_that_did_not_run_and_none_that_stands_in(tmp_path):
    template = (REPO / "features" / "crew" / "templates" / "result.md").read_text()
    starts = [line.split("<")[0] for line in template.splitlines()]
    assert "Unrun: at " in starts
    assert not [start for start in starts if start.startswith("CI:")]
    pushed = Pushed(tmp_path, ROLLUPS["none ran"][0])
    assert pushed.says().removeprefix("unrun: no check ran at ") == pushed.head


def test_the_review_is_launched_when_the_pull_request_opens_and_not_on_a_green_wake(tmp_path):
    import test_pr_review_skill as review

    def launcher(name, rollup):
        (tmp_path / name).mkdir()
        return review.Launcher(tmp_path / name, rollup).says()

    ready_at = [f"a-task: ready, {review.URL} at {review.HEAD}"]
    pending = [{"__typename": "StatusContext", "state": "PENDING"}]
    assert launcher("pending", pending) == ready_at
    assert launcher("running", ROLLUPS["one still running"][0]) == ready_at
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
        "wait": "launch beside the checks",
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


def test_a_crewmate_links_its_pull_request_and_arms_no_watch():
    """The JSON calls of "Stay on the pull request", read as `test_tool_calls.py` reads every
    skill's: the link, which T3 Code takes, and no watch. jbus wakes the crewmate."""
    blocks, unread = tools.read("crew", sections()["Stay on the pull request"])
    called = []
    for _, language, body, lead_in in blocks:
        for inline in tools.INLINE.finditer(lead_in):
            called.append(tools.Call("crew", lead_in[: inline.start()], inline[1]))
        if language == "json":
            called.append(tools.Call("crew", lead_in, body))
    assert unread == [] and [call.tool for call in called] == ["link_pull_request"]
    assert [tools.errors(call, call.given) for call in called] == [[]]
    assert "watch_pull_request" not in tools.SCHEMAS


def test_the_ci_fix_line_the_skill_asks_for_is_one_jmerge_reads():
    (line,) = set(re.findall(r"`(CI fix: <[^`]+)`", as_read(SKILL)))
    head, reviewed = "b" * 40, "a" * 40
    filled = re.sub(r"<[^>]+>", "{}", line).format(head, reviewed)
    brief = merge.brief(merge.review("clean", reviewed), filled + "\n")
    assert ready.short_of(brief, head) == ""
    assert ready.to_range_diff(ready.rebase_of(brief, head), brief, head) == reviewed
