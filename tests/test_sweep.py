"""What a finished thread left is listed and removed by one command, `jmerge --sweep`, which
the home skill tells a home to run at its start. The line is lifted from the skill and run, in
a temporary repo with a real `git worktree` for every line of both lists."""

import json
import os
import re
import shutil
import subprocess
import textwrap
from datetime import date

import pytest

import daemons
import test_scout as scout
from jbus import mirror
from jmerge import cli
from test_home_merge import NAME, git

THREAD = "mcp:thread-of-{}"
NOWHERE = "has a commit that is not in origin's main"
OR_MERGED = f"{NOWHERE} or in its merged pull request"
SWEEP = "jmerge --sweep"
OLD_GATE = "-".join(("no", "mistakes"))
WORKTREE, LOCAL, REMOTE = (
    "the worktree",
    "the local branch",
    "the remote branch",
)


def result(status="done", left="none", pull="none", branch="alpha"):
    return f"\n## Result\nStatus: {status}\nBranch: {branch}   Pull request: {pull}\nLeft: {left}\n"


class Scene:
    """A repo with an origin, the directory T3 Code puts its worktrees in, and the home's state."""

    def __init__(self, home, tmp_path):
        self.home = home
        self.main = home.main
        self.origin = home.origin
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(self.main, "remote", "add", "origin", str(self.origin))
        git(self.main, "push", "-q", "-u", "origin", "main")
        self.trees = home.user / ".t3" / "worktrees" / NAME
        self.trees.mkdir(parents=True)
        self.scouts = home.state / "scouts"
        self.scouts.mkdir()
        self.mirror = tmp_path / "mirror.git"
        self.pulls = 0

    def tree(self, branch, at=None):
        """A worktree where T3 Code makes one, on a new branch of its name."""
        at = at or self.trees / branch
        git(self.main, "worktree", "add", "-q", "-b", branch, str(at))
        return at

    def work(self, tree, push=True):
        """A commit in a worktree, pushed or not. Gives the commit."""
        branch = git(tree, "rev-parse", "--abbrev-ref", "HEAD")
        with (tree / f"{branch.replace('/', '-')}.txt").open("a") as file:
            file.write(f"the work of {branch}\n")
        git(tree, "add", "-A")
        git(tree, "commit", "-q", "-m", f"the work of {branch}")
        if push:
            git(tree, "push", "-q", "-u", "origin", branch)
        return git(tree, "rev-parse", "HEAD")

    def pull_request(self, head, state, base="main"):
        """A pull request as GitHub gives it and keeps it, under `refs/pull`. A merged one is
        a squash on the origin's main."""
        self.pulls += 1
        listed = {"state": state, "headRefOid": head, "baseRefName": base}
        (self.home.stub / f"pull-{self.pulls}.json").write_text(json.dumps(listed))
        git(self.origin, "update-ref", f"refs/pull/{self.pulls}/head", head)
        if state == "MERGED" and base == "main":
            was = git(self.origin, "rev-parse", "main")
            squash = git(
                self.origin, "commit-tree", f"{head}^{{tree}}", "-p", was, "-m", f"(#{self.pulls})"
            )
            git(self.origin, "update-ref", "refs/heads/main", squash)
        return f"https://example.test/pull/{self.pulls}"

    def brief(self, slug, said, thread=True):
        line = f"Thread: {THREAD.format(slug)}\n" if thread else ""
        (self.home.tasks / f"{slug}.md").write_text(
            f'# {slug}: a task\nTask: "do it"\n{line}{said}'
        )

    def crewmate(self, slug, state="MERGED", **said):
        """A crewmate's worktree with its work pushed, its pull request and its brief."""
        tree = self.tree(slug)
        head = self.work(tree)
        url = self.pull_request(head, state) if state else "none"
        self.brief(slug, result(pull=url, branch=slug, **said))
        return tree

    def scout(self, slug, report="## Report\nStatus: done\n"):
        """A scout's worktree, which has no commit of its own, and its request."""
        tree = self.tree(f"scout-{slug}")
        (self.scouts / f"{slug}.md").write_text(
            f"# {slug}: a question\nThread: {THREAD.format('scout-' + slug)}\n{report}"
        )
        return tree

    def mirrored(self, branch):
        """A second remote, a bare repo beside the origin, with the branch in it. It has the
        name of the remote the sweep once read."""
        if not self.mirror.exists():
            git(self.main, "init", "-q", "--bare", "-b", "main", str(self.mirror))
            git(self.main, "remote", "add", OLD_GATE, str(self.mirror))
        git(self.main, "push", "-q", OLD_GATE, f"{branch}:refs/heads/{branch}")
        git(self.main, "fetch", "-q", OLD_GATE)

    def run(self, *flags):
        said = self.home.run(*flags, about=SWEEP)
        assert self.home.stderr == ""
        assert self.home.code == 0
        return said

    def look(self):
        return self.run("--check")

    def everything(self):
        """Every byte under the worktrees, every ref of the three repos, and the home's state."""
        git(self.main, "fetch", "-q", "origin")
        held = {
            str(path.relative_to(self.trees)): path.read_bytes()
            for path in sorted(self.trees.rglob("*"))
            if path.is_file()
        }
        for repo in (self.main, self.origin, self.mirror):
            if repo.exists():
                listed = git(repo, "for-each-ref", "--format=%(refname) %(objectname)")
                held.update(
                    {f"{repo.name} {line.split()[0]}": line for line in listed.splitlines()}
                )
        held["worktrees"] = git(self.main, "worktree", "list", "--porcelain")
        for path in sorted(self.home.state.rglob("*.md")):
            held[str(path)] = path.read_bytes()
        return held

    def without(self, held, *branches):
        """What `everything` gave, less the worktrees and the refs of these branches."""
        left = {}
        for key, value in held.items():
            gone = any(
                key.startswith(f"{branch}/") or key.endswith(f"/{branch}") for branch in branches
            )
            if key == "worktrees":
                paragraphs = [
                    paragraph
                    for paragraph in value.split("\n\n")
                    if not any(f"refs/heads/{branch}" in paragraph for branch in branches)
                ]
                left[key] = "\n\n".join(paragraphs)
            elif not gone:
                left[key] = value
        return left

    def log(self):
        log = self.home.state / "merge.log"
        return log.read_text().splitlines() if log.exists() else []


@pytest.fixture
def scene(home, tmp_path):
    return Scene(home, tmp_path)


def removable(branch, *what):
    return f"removable {branch} {THREAD.format(branch)}: {', '.join(what)}"


def removed(branch, *what):
    return f"removed {branch} {THREAD.format(branch)}: {', '.join(what)}"


def test_a_merged_crewmates_worktree_and_both_branches_are_removable(scene):
    tree = scene.crewmate("alpha")
    before = scene.everything()
    assert scene.look() == [removable("alpha", WORKTREE, LOCAL, REMOTE)]
    assert scene.everything() == before
    assert scene.log() == []
    assert scene.run() == [removed("alpha", WORKTREE, LOCAL, REMOTE)]
    assert not tree.exists()
    assert scene.everything() == scene.without(before, "alpha")
    assert "alpha" not in git(scene.origin, "branch", "--format=%(refname:short)").split()
    assert scene.look() == []


def test_a_crewmate_that_ended_with_no_pull_request_and_no_commit_is_removable(scene):
    tree = scene.tree("alpha")
    scene.brief("alpha", result())
    assert scene.look() == [removable("alpha", WORKTREE, LOCAL)]
    assert scene.run() == [removed("alpha", WORKTREE, LOCAL)]
    assert not tree.exists()
    assert git(scene.main, "branch", "--format=%(refname:short)").split() == ["main"]


def test_a_scout_with_a_report_is_removable(scene):
    tree = scene.scout("find-out")
    before = scene.everything()
    assert scene.look() == [removable("scout-find-out", WORKTREE, LOCAL)]
    assert scene.run() == [removed("scout-find-out", WORKTREE, LOCAL)]
    assert not tree.exists()
    assert scene.everything() == scene.without(before, "scout-find-out")


def test_a_branch_whose_work_is_in_the_default_branch_is_removable_with_no_pull_request(scene):
    tree = scene.tree("alpha")
    head = scene.work(tree)
    git(scene.origin, "update-ref", "refs/heads/main", head)
    scene.brief("alpha", result())
    assert scene.run() == [removed("alpha", WORKTREE, LOCAL, REMOTE)]


def test_a_branch_behind_the_merged_head_is_removable(scene):
    tree = scene.tree("alpha")
    first = scene.work(tree)
    head = scene.work(tree)
    git(scene.main, "update-ref", "refs/heads/behind", first)
    git(tree, "checkout", "-q", "behind")
    git(scene.main, "branch", "-q", "-D", "alpha")
    git(scene.main, "worktree", "move", str(tree), str(scene.trees / "behind"))
    scene.brief("behind", result(pull=scene.pull_request(head, "MERGED")))
    assert scene.look() == [removable("behind", WORKTREE, LOCAL)]


def test_a_worktree_whose_directory_is_gone_is_removed_with_its_branches(scene):
    tree = scene.crewmate("alpha")
    shutil.rmtree(tree)
    assert scene.run() == [removed("alpha", WORKTREE, LOCAL, REMOTE)]
    assert "alpha" not in git(scene.main, "worktree", "list", "--porcelain")
    assert git(scene.main, "branch", "--format=%(refname:short)").split() == ["main"]


def test_a_worktree_nobody_names_whose_directory_is_gone_stays_listed(scene):
    shutil.rmtree(scene.crewmate("alpha"))
    stray = scene.tree("jstack/t-0059", scene.trees / "stray")
    shutil.rmtree(stray)
    assert scene.run() == [
        removed("alpha", WORKTREE, LOCAL, REMOTE),
        "kept stray: no brief or request names its branch jstack/t-0059",
    ]
    assert f"worktree {stray}" in git(scene.main, "worktree", "list", "--porcelain")


def test_a_report_may_say_more_after_done_and_a_page_of_none_is_no_page(scene):
    report = "## Report\nStatus: done (both ran the same cases)\nBrief: none   Page: none\n"
    scene.scout("find-out", report=report)
    assert scene.look() == [removable("scout-find-out", WORKTREE, LOCAL)]


PAGE = "its Report has a page, which may wait on the user"


@pytest.mark.parametrize(
    ("page", "waits"),
    [
        pytest.param(
            "Brief: none   Page: reports/find-out.html, http://127.0.0.1:4387/session/1\n",
            True,
            id="a real page",
        ),
        pytest.param("Brief: none   Page: none, lavish-axi is not installed\n", False, id="why"),
        pytest.param("Brief: none   Page: none,no lavish-axi\n", False, id="why, no space"),
        pytest.param("Brief: none   Page: none\n", False, id="none"),
        pytest.param("Brief: none   Page: none \n", False, id="none, and a blank"),
        pytest.param("", False, id="no line"),
    ],
)
def test_the_sweep_the_scout_and_jbus_agree_on_which_report_names_a_page(
    scene, tmp_path, page, waits
):
    report = f"## Report\nStatus: done\n{page}"
    assert bool(mirror.page(report)) == waits
    scene.scout("find-out", report=report)
    kept, removed_ = f"kept scout-find-out: {PAGE}", removable("scout-find-out", WORKTREE, LOCAL)
    assert scene.look() == [kept if waits else removed_]
    said = "page: settle once the user has ended its session" if waits else "settle"
    assert settles(tmp_path, report) == [said]


def test_branches_with_no_worktree_left_are_removed(scene):
    tree = scene.crewmate("alpha")
    git(scene.main, "worktree", "remove", str(tree))
    assert scene.look() == [removable("alpha", LOCAL, REMOTE)]
    assert scene.run() == [removed("alpha", LOCAL, REMOTE)]
    assert scene.look() == []


def test_a_branch_in_a_second_remote_is_neither_listed_nor_removed(scene):
    scene.crewmate("alpha")
    scene.mirrored("alpha")
    tracking = f"refs/remotes/{OLD_GATE}"
    there = git(scene.mirror, "for-each-ref"), git(scene.main, "for-each-ref", tracking)
    assert all(there)
    assert scene.look() == [removable("alpha", WORKTREE, LOCAL, REMOTE)]
    assert scene.run() == [removed("alpha", WORKTREE, LOCAL, REMOTE)]
    assert (git(scene.mirror, "for-each-ref"), git(scene.main, "for-each-ref", tracking)) == there


def test_a_brief_or_request_with_no_thread_line_says_so(scene):
    scene.tree("alpha")
    scene.brief("alpha", result(), thread=False)
    assert scene.look() == [f"removable alpha no-thread: {WORKTREE}, {LOCAL}"]


def no_result(scene):
    scene.tree("alpha")
    scene.brief("alpha", "")
    return "not done, tasks/alpha.md has no Result"


def not_done(scene):
    scene.crewmate("alpha", status="not done")
    return "not done, its Result says Status: not done"


def blocked(scene):
    scene.crewmate("alpha", status="blocked", left="half of it")
    return "blocked, its Result says Status: blocked"


def paused(scene):
    scene.crewmate("alpha", status="paused", left="the docs, first read a.py")
    return "paused, its Result says Status: paused"


def paused_and_more(scene):
    scene.crewmate("alpha", status="paused, wip at abc123", left="the docs")
    return "paused, its Result says Status: paused, wip at abc123"


def paused_with_a_pull_request_open(scene):
    scene.crewmate("alpha", state="OPEN", status="paused", left="the docs")
    return "paused, its Result says Status: paused"


def left(scene):
    scene.crewmate("alpha", left="a file not committed")
    return "Left, its Result does not say Left: none"


def no_branch_line(scene):
    scene.tree("alpha")
    scene.brief("alpha", "\n## Result\nStatus: done\nLeft: none\n")
    return "its Result has no Branch line"


def pull_request_open(scene):
    scene.crewmate("alpha", state="OPEN")
    return "its pull request is open"


def closed_unmerged(scene):
    scene.crewmate("alpha", state="CLOSED")
    return "its pull request closed unmerged"


def github_does_not_answer(scene):
    scene.crewmate("alpha")
    (scene.home.stub / "pull-1.json").write_text("<html></html>\n")
    return "could not ask GitHub about its pull request: gh exited 0: its output was not JSON"


def dirty(scene):
    tree = scene.crewmate("alpha")
    (tree / "notes.txt").write_text("not committed\n")
    return f"dirty, {tree} has uncommitted work"


def unpushed(scene):
    tree = scene.crewmate("alpha")
    scene.work(tree, push=False)
    return f"unpushed, the local branch {OR_MERGED}"


def unpushed_with_no_pull_request(scene):
    tree = scene.tree("alpha")
    scene.work(tree, push=False)
    scene.brief("alpha", result())
    return f"unpushed, the local branch {NOWHERE}"


def pushed_after_the_merge(scene):
    tree = scene.crewmate("alpha")
    scene.work(tree)
    git(tree, "reset", "-q", "--hard", "HEAD~1")
    return f"the remote branch {OR_MERGED}"


def merged_into_another_branch(scene):
    tree = scene.tree("alpha")
    url = scene.pull_request(scene.work(tree), "MERGED", base="another-task")
    scene.brief("alpha", result(pull=url))
    return f"unpushed, the local branch {NOWHERE}"


def a_worktree_somewhere_else(scene):
    tree = scene.tree("alpha", scene.home.user / "elsewhere")
    scene.brief("alpha", result())
    return f"its worktree {tree} is not under {scene.trees}"


def no_report(scene):
    scene.scout("alpha", report="")
    return "not done, scouts/alpha.md has no Report"


def report_not_done(scene):
    scene.scout("alpha", report="## Report\nStatus: not done\n")
    return "not done, its Report says Status: not done"


def report_blocked(scene):
    scene.scout("alpha", report="## Report\nStatus: blocked\n")
    return "blocked, its Report says Status: blocked"


def report_with_a_page(scene):
    page = "reports/alpha.html, http://127.0.0.1:4387/session/1"
    scene.scout("alpha", report=f"## Report\nStatus: done\nBrief: none   Page: {page}\n")
    return "its Report has a page, which may wait on the user"


def result_that_says_more_than_done(scene):
    scene.crewmate("alpha", status="done (all but the last line)")
    return "its Result says more than Status: done"


def two_records(scene):
    scene.scout("alpha")
    scene.brief("scout-alpha", result())
    return "tasks/scout-alpha.md and scouts/alpha.md both name it"


def named_by_nobody(scene):
    scene.work(scene.tree("alpha"), push=False)
    return "no brief or request names its branch alpha"


KEPT = [
    no_result,
    not_done,
    blocked,
    paused,
    paused_and_more,
    paused_with_a_pull_request_open,
    left,
    no_branch_line,
    pull_request_open,
    closed_unmerged,
    github_does_not_answer,
    dirty,
    unpushed,
    unpushed_with_no_pull_request,
    pushed_after_the_merge,
    merged_into_another_branch,
    a_worktree_somewhere_else,
    no_report,
    report_not_done,
    report_blocked,
    report_with_a_page,
    result_that_says_more_than_done,
    two_records,
    named_by_nobody,
]


@pytest.mark.parametrize("case", KEPT, ids=lambda case: case.__name__)
def test_what_is_not_finished_clean_and_safe_is_kept_with_the_first_reason(scene, case):
    why = case(scene)
    (branch,) = [
        name
        for name in git(scene.main, "branch", "--format=%(refname:short)").split()
        if name != "main"
    ]
    before = scene.everything()
    assert scene.look() == [f"kept {branch}: {why}"]
    assert scene.run() == [f"kept {branch}: {why}"]
    assert scene.everything() == before


def test_a_worktree_a_process_is_running_in_is_kept(scene):
    tree = scene.scout("find-out")
    running = daemons.start(["sleep", "60"], cwd=tree)
    try:
        before = scene.everything()
        why = f"a process is running in {tree} (pid {running.pid})"
        assert scene.run() == [f"kept scout-find-out: {why}"]
        assert scene.everything() == before
    finally:
        running.kill()
        running.wait()
    assert scene.look() == [removable("scout-find-out", WORKTREE, LOCAL)]


def test_a_worktree_is_kept_when_no_process_list_can_be_read(scene, monkeypatch, capsys, tmp_path):
    tree = scene.scout("find-out")
    home = scene.home
    for name, value in {
        "HOME": str(home.user),
        "PATH": f"{home.stub}:{os.environ['PATH']}",
        "STUB": str(home.stub),
        "ORIGIN": str(home.origin),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.chdir(scene.main)
    monkeypatch.setattr(cli, "PROC", tmp_path / "no-proc")
    before = scene.everything()
    assert cli.main(["--sweep"]) == 0
    why = f"no process list could be read to tell whether a process is running in {tree}"
    assert capsys.readouterr().out.splitlines() == [f"kept scout-find-out: {why}"]
    assert scene.everything() == before
    monkeypatch.undo()
    assert scene.look() == [removable("scout-find-out", WORKTREE, LOCAL)]


@pytest.mark.parametrize("listable", [False, True], ids=["unlistable", "without this process"])
def test_a_process_list_that_cannot_be_read_whole_is_no_answer(tmp_path, monkeypatch, listable):
    proc = tmp_path / "proc"
    other = proc / str(os.getpid() + 1 if listable else os.getpid())
    other.mkdir(parents=True)
    (other / "cwd").symlink_to(tmp_path)
    if not listable:
        proc.chmod(0o111)
    monkeypatch.setattr(cli, "PROC", proc)
    try:
        assert cli._running(str(tmp_path)) is None
    finally:
        proc.chmod(0o755)


def test_a_readable_process_list_finds_this_process(tmp_path, monkeypatch):
    assert cli._running(str(tmp_path)) == 0
    monkeypatch.chdir(tmp_path)
    assert cli._running(str(tmp_path)) == os.getpid()


def test_the_first_reason_is_the_records_before_the_worktrees(scene):
    tree = scene.crewmate("alpha", state="OPEN", status="not done", left="a file")
    (tree / "notes.txt").write_text("not committed\n")
    assert scene.look() == ["kept alpha: not done, its Result says Status: not done"]
    scene.brief("alpha", result(pull="https://example.test/pull/1", left="a file"))
    assert scene.look() == ["kept alpha: Left, its Result does not say Left: none"]
    scene.brief("alpha", result(pull="https://example.test/pull/1"))
    assert scene.look() == ["kept alpha: its pull request is open"]


def test_a_follow_up_result_is_the_one_that_counts(scene):
    scene.tree("alpha")
    follow_up = result().replace("## Result", "## Result, follow-up (2026-10-11, a steer)")
    scene.brief("alpha", result(status="not done") + follow_up)
    assert scene.look() == [removable("alpha", WORKTREE, LOCAL)]
    scene.brief("alpha", result() + follow_up.replace("Left: none", "Left: a file"))
    assert scene.look() == ["kept alpha: Left, its Result does not say Left: none"]


def test_what_no_brief_or_request_names_is_never_listed_and_never_touched(scene):
    git(scene.main, "branch", "-q", "jstack/t-0059")
    git(scene.main, "checkout", "-q", "-b", "fm/old")
    git(scene.main, "commit", "-q", "--allow-empty", "-m", "the first jstack")
    git(scene.main, "push", "-q", "origin", "fm/old", "jstack/t-0059")
    git(scene.main, "checkout", "-q", "main")
    git(scene.main, "branch", "-q", "-D", "fm/old")
    scene.crewmate("alpha")
    before = scene.everything()
    assert scene.run() == [removed("alpha", WORKTREE, LOCAL, REMOTE)]
    after = scene.everything()
    assert after == scene.without(before, "alpha")
    assert after[f"{NAME} refs/heads/jstack/t-0059"] and after["origin.git refs/heads/fm/old"]


def test_a_brief_named_for_the_default_branch_removes_nothing(scene):
    scene.brief("main", result(branch="main"))
    before = scene.everything()
    assert scene.run() == ["kept main: it is the default branch"]
    assert scene.everything() == before


def test_both_lists_at_once_and_only_the_first_is_removed(scene):
    scene.crewmate("merged")
    scene.scout("asked")
    scene.crewmate("open", state="OPEN")
    scene.crewmate("closed", state="CLOSED")
    untidy = scene.crewmate("untidy")
    (untidy / "notes.txt").write_text("not committed\n")
    ahead = scene.crewmate("ahead")
    scene.work(ahead, push=False)
    scene.scout("asking", report="")
    scene.work(scene.tree("stray"), push=False)
    before = scene.everything()
    kept = [
        f"kept ahead: unpushed, the local branch {OR_MERGED}",
        "kept closed: its pull request closed unmerged",
        "kept open: its pull request is open",
        "kept scout-asking: not done, scouts/asking.md has no Report",
        "kept stray: no brief or request names its branch stray",
        f"kept untidy: dirty, {untidy} has uncommitted work",
    ]
    assert scene.look() == [
        removable("merged", WORKTREE, LOCAL, REMOTE),
        removable("scout-asked", WORKTREE, LOCAL),
        *kept,
    ]
    assert scene.everything() == before
    assert scene.log() == []
    said = scene.run()
    assert said == [
        removed("merged", WORKTREE, LOCAL, REMOTE),
        removed("scout-asked", WORKTREE, LOCAL),
        *kept,
    ]
    assert scene.everything() == scene.without(before, "merged", "scout-asked")
    today = date.today().isoformat()
    logged = scene.log()
    assert [line.split(" ", 2)[2] for line in logged] == said
    assert all(re.match(rf"{today} \d\d:\d\d ", line) for line in logged)
    assert scene.look() == kept


def test_a_step_git_refuses_is_said_and_the_rest_is_left(scene):
    tree = scene.crewmate("alpha")
    git(scene.main, "worktree", "lock", str(tree))
    before = scene.everything()
    (said,) = scene.run()
    assert said.startswith("kept alpha: the worktree could not be removed (")
    assert {key: value for key, value in scene.everything().items() if key != "worktrees"} == {
        key: value for key, value in before.items() if key != "worktrees"
    }


def test_a_remote_branch_git_cannot_delete_is_said_after_what_was_removed(scene):
    scene.crewmate("alpha")
    hook = scene.origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    (said,) = scene.run()
    start = f"removed alpha {THREAD.format('alpha')}: {WORKTREE}, {LOCAL}, kept: {REMOTE} ("
    assert said.startswith(start)
    assert scene.look() == [removable("alpha", REMOTE)]
    config = ["git", "config", "--get-regexp", "^branch[.]alpha[.]"]
    assert subprocess.run(config, cwd=scene.main, capture_output=True, text=True).stdout == ""


def test_an_origin_that_cannot_be_read_is_a_job_not_done(scene):
    scene.crewmate("alpha")
    before = scene.everything()
    git(scene.main, "remote", "set-url", "origin", str(scene.origin) + "-gone")
    assert scene.home.run(about=SWEEP) == ["wait: could not read origin"]
    assert scene.home.code == 1
    git(scene.main, "remote", "set-url", "origin", str(scene.origin))
    assert scene.everything() == before


def settles(tmp_path, report):
    """Run the block of the scout skill's End that says whether the scout settles itself."""
    (block,) = [block for block in scout.given("End") if "settle" in block]
    state = tmp_path / "state" / "scouts"
    state.mkdir(parents=True)
    (state / "find-out.md").write_text(f"# find-out: a question\nHome: mcp:home\n{report}")
    ran = subprocess.run(
        ["sh", "-c", f'H="$STATE"\nS=find-out\n{textwrap.dedent(block)}'],
        capture_output=True,
        text=True,
        env={**os.environ, "STATE": str(state.parent)},
    )
    assert ran.stderr == ""
    return ran.stdout.splitlines()


REPORT = "## Report\nStatus: {}\nRecommendation: do it\nBrief: none   Page: {}\nSteers: none\n"


@pytest.mark.parametrize(
    ("report", "said"),
    [
        (REPORT.format("done", "none"), "settle"),
        (REPORT.format("done (both ran the same cases)", "none"), "settle"),
        ("", "stay: the request has no Report"),
        (REPORT.format("blocked", "none"), "stay: the Report does not say Status: done"),
        (REPORT.format("not done", "none"), "stay: the Report does not say Status: done"),
        pytest.param(
            "## Report\nStatus: done\n", "settle", id="a report that names no page has none"
        ),
        (
            REPORT.format("done", "reports/find-out.html, http://127.0.0.1:4387/session/1"),
            "page: settle once the user has ended its session",
        ),
        pytest.param(
            REPORT.format("done", "none") + REPORT.format("blocked", "none"),
            "stay: the Report does not say Status: done",
            id="of two reports the last one counts",
        ),
    ],
)
def test_a_scout_settles_itself_when_its_report_is_done_and_no_page_waits(tmp_path, report, said):
    assert settles(tmp_path, report) == [said]
