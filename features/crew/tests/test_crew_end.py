"""The crew skill's "End" decides who is told, and when a thread settles or stays."""

import os
import subprocess

import pytest

import test_tool_calls as tools
from crew_helpers import BRIEF, block, git, said

DONE = "Status: done\nBranch: alpha   Pull request: none\nLeft: none\n"


class NoPullRequest:
    """A crewmate's worktree on its own branch, in a clone whose remote has a default branch,
    and the brief that the crewmate wrote its Result into."""

    def __init__(self, tmp_path, result=DONE):
        origin = tmp_path / "origin.git"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        self.main = tmp_path / "main"
        git(tmp_path, "clone", "-q", str(origin), str(self.main))
        git(self.main, "commit", "-q", "--allow-empty", "-m", "start")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        git(self.main, "remote", "set-head", "origin", "main")
        self.worktree = tmp_path / "alpha"
        git(self.main, "worktree", "add", "-q", "-b", "alpha", str(self.worktree), "origin/main")
        self.state = tmp_path / "state"
        (self.state / "tasks").mkdir(parents=True)
        self.brief = self.state / "tasks" / "alpha.md"
        self.brief.write_text(f'# alpha: a task\nTask: "do it"\n\n## Result\n{result}')

    def commit(self, name):
        (self.worktree / name).write_text("new\n")
        git(self.worktree, "add", name)
        git(self.worktree, "commit", "-q", "-m", f"add {name}")

    def says(self, cwd=None):
        ran = subprocess.run(
            ["sh", "-c", block("End", "settle").replace("<slug>", "alpha")],
            capture_output=True,
            text=True,
            env={**os.environ, "H": str(self.state)},
            cwd=cwd or self.worktree,
            check=True,
        )
        assert ran.stderr == ""
        return ran.stdout


def test_a_crewmate_that_is_done_with_nothing_left_and_no_pull_request_settles(tmp_path):
    assert NoPullRequest(tmp_path).says() == "settle\n"


def test_a_branch_whose_commits_are_on_the_default_branch_settles(tmp_path):
    crewmate = NoPullRequest(tmp_path)
    crewmate.commit("a.py")
    git(crewmate.worktree, "push", "-q", "origin", "alpha:main")
    git(crewmate.worktree, "fetch", "-q", "origin")
    assert crewmate.says() == "settle\n"


@pytest.mark.parametrize(
    ("result", "why"),
    [
        (DONE.replace("done", "not done"), "the last Result does not say Status: done"),
        (DONE.replace("done", "blocked"), "the last Result does not say Status: done"),
        ("", "the last Result does not say Status: done"),
        (
            DONE.replace("Left: none", "Left: the docs are not written"),
            "the last Result does not say Left: none",
        ),
        (DONE.replace("Left: none\n", ""), "the last Result does not say Left: none"),
        ("Status: done\nLeft: none\n", "the last Result has no Branch line"),
        (
            DONE.replace("Pull request: none", "Pull request: https://example.test/pull/1"),
            "it has a pull request, and T3 Code settles this thread when that merges or closes",
        ),
        (
            DONE + "\n## Result, follow-up (2026-10-11, a steer)\nStatus: blocked\n",
            "the last Result does not say Status: done",
        ),
        (
            "Status: blocked\nLeft: a.py\n\n## Result, follow-up (2026-10-11, unblocked)\n" + DONE,
            None,
        ),
    ],
)
def test_a_crewmate_settles_only_on_what_its_last_result_says(result, why, tmp_path):
    said = NoPullRequest(tmp_path, result).says()
    assert said == (f"stay: {why}\n" if why else "settle\n")


PAUSED = "Status: paused\nBranch: alpha   Pull request: {}\nLeft: the docs, first read a.py\n"


URL = "https://example.test/pull/1"


RESUMED = "\n## Result, follow-up (2026-10-11, the word to resume)\n"


def paused(pull="none", more=""):
    """A brief whose crewmate paused, with the Result that step 4 of
    `features/crew/playbooks/pause-safely.md` writes."""
    said = PAUSED.format(pull).replace("Status: paused", f"Status: paused{more}")
    return f'# alpha: a task\nTask: "do it"\n\n## Result\n{said}'


MORE = ["", ", wip at abc123", " (wip at abc123)", "."]


@pytest.mark.parametrize("more", MORE)
def test_a_paused_crewmate_with_no_pull_request_tells_its_home_it_has_not_ended(more, tmp_path):
    assert said(tmp_path, "End", "tell the home", paused(more=more)) == [
        "tell the home: the task is paused and has not ended"
    ]


def test_a_paused_crewmate_with_a_pull_request_sends_its_home_nothing(tmp_path):
    assert said(tmp_path, "End", "tell the home", paused(URL)) == [
        f"send nothing: {URL} is open, and a home that merges hears of it once, "
        "when its checks have passed"
    ]


def test_a_task_resumed_and_ended_is_not_said_to_be_paused(tmp_path):
    brief = paused() + RESUMED + DONE
    assert said(tmp_path, "End", "tell the home", brief) == [
        "tell the home: the task ends with no pull request"
    ]


@pytest.mark.parametrize("pull", ["none", URL])
@pytest.mark.parametrize("more", MORE)
def test_a_paused_crewmate_stays_and_says_it_is_paused(pull, more, tmp_path):
    result = PAUSED.format(pull).replace("Status: paused", f"Status: paused{more}")
    said = NoPullRequest(tmp_path, result).says()
    assert said == "stay: the task is paused, the last Result says Status: paused\n"


@pytest.mark.parametrize(
    ("brief", "is_paused"),
    [
        pytest.param(paused(), True, id="paused"),
        pytest.param(paused(URL), True, id="paused with a pull request"),
        pytest.param(paused(URL, ", wip at abc123"), True, id="paused, and more"),
        pytest.param(paused(URL, " (wip at abc123)"), True, id="paused (and more)"),
        pytest.param(paused(URL, "."), True, id="paused."),
        pytest.param(paused(URL, "ly"), False, id="another word"),
        pytest.param(paused(URL) + "Woken: a check failed.\n", True, id="woken before"),
        pytest.param(BRIEF, False, id="done"),
        pytest.param(BRIEF.replace("Status: done", "Status: not done"), False, id="not done"),
        pytest.param("# alpha: a task\nStatus: paused\n", False, id="no result"),
        pytest.param(paused(URL) + RESUMED + "Status: not done\n", False, id="resumed"),
        pytest.param(paused(URL) + RESUMED + DONE, False, id="resumed and done"),
        pytest.param(BRIEF + RESUMED + PAUSED.format(URL), True, id="paused in a follow-up"),
    ],
)
def test_a_wake_finds_the_thread_paused_only_by_its_last_result(brief, is_paused, tmp_path):
    (line,) = said(tmp_path, "Stay on the pull request", "paused", brief)
    assert line.startswith("paused: " if is_paused else "not paused: ")


def test_a_brief_with_no_result_does_not_settle(tmp_path):
    crewmate = NoPullRequest(tmp_path)
    crewmate.brief.write_text('# alpha: a task\nTask: "do it"\nStatus: done\nLeft: none\n')
    assert crewmate.says() == "stay: the last Result does not say Status: done\n"


def test_uncommitted_work_keeps_the_thread(tmp_path):
    crewmate = NoPullRequest(tmp_path)
    (crewmate.worktree / "notes.txt").write_text("not committed\n")
    assert crewmate.says() == "stay: the worktree has uncommitted work\n"


def test_a_commit_that_is_not_on_the_default_branch_keeps_the_thread(tmp_path):
    crewmate = NoPullRequest(tmp_path)
    crewmate.commit("a.py")
    assert crewmate.says() == "stay: the branch has a commit that is not on origin/main\n"
    git(crewmate.worktree, "push", "-q", "origin", "alpha")
    assert crewmate.says() == "stay: the branch has a commit that is not on origin/main\n"


def test_a_clone_that_does_not_know_the_default_branch_keeps_the_thread(tmp_path):
    crewmate = NoPullRequest(tmp_path)
    git(crewmate.main, "remote", "set-head", "origin", "--delete")
    assert crewmate.says() == "stay: the remote's default branch is not known here\n"


def test_outside_a_git_repo_the_thread_stays(tmp_path):
    crewmate = NoPullRequest(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
        assert crewmate.says(elsewhere) == "stay: git status could not be run here\n"


def test_a_default_branch_that_cannot_be_compared_with_keeps_the_thread(tmp_path):
    crewmate = NoPullRequest(tmp_path)
    git(crewmate.main, "update-ref", "-d", "refs/remotes/origin/main")
    assert crewmate.says() == "stay: the branch could not be compared with origin/main\n"


def test_the_first_reason_to_stay_is_the_one_said(tmp_path):
    crewmate = NoPullRequest(tmp_path, DONE.replace("Left: none", "Left: a.py"))
    (crewmate.worktree / "a.py").write_text("not committed\n")
    assert crewmate.says() == "stay: the last Result does not say Left: none\n"


def test_the_settle_is_a_call_the_tool_takes():
    (settle,) = [
        call
        for call in tools.CALLS
        if call.where.startswith("crew:") and call.tool == "t3_thread_organize"
    ]
    assert settle.given == {"action": "settle"}
    assert tools.errors(settle, settle.given) == []
