"""The crew skill's rebase: the ref of the head before it, the push, the lines it dropped,
and a review that is running."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

import jsettings
import test_home_merge as merge
from crew_helpers import (
    BRIEF,
    GH,
    SKILL,
    STOPPED,
    Failed,
    Link,
    PullRequest,
    asked,
    block,
    git,
    sections,
    stays,
    with_field,
)
from jmerge import cli, ready
from test_home_thread import as_read

REVIEWING = "a review of {} is running: rebase after its section is written"


def kept_at(pr, before, slug="a-task"):
    """The commit the backup ref of a head is at, as the main checkout sees it."""
    return git(pr.stub.parent / "main", "rev-parse", f"refs/jstack/pre-rebase/{slug}/{before[:12]}")


def test_a_conflicts_rebase_keeps_the_head_before_it_under_a_ref(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    before = pr.head()
    assert stays(pr, "mergeable") == ["rebased onto origin/main"]
    assert pr.head() != before
    assert kept_at(pr, before) == before
    assert cli.patch_id(tmp_path / "main", "main", before) is not None


def test_a_links_move_keeps_the_head_before_it_under_a_ref(tmp_path):
    link = Link(tmp_path, "main")
    before = link.head()
    about = block("Stay on the pull request", "--onto").replace("<slug>", "a-link")
    about = about.replace("was='<the branch it sat on>'", "was='under'")
    assert link.run_text(about).splitlines() == ["moved from under onto origin/main"]
    assert link.head() != before
    assert kept_at(link, before, "a-link") == before


def test_the_ref_of_a_head_before_a_rebase_outlives_the_branch_the_sweep_removes(tmp_path):
    import test_sweep as sweep

    scene = sweep.Scene(merge.Home(tmp_path), tmp_path)
    tree = scene.crewmate("alpha")
    head = git(tree, "rev-parse", "HEAD")
    about = block("Stay on the pull request", "mergeable").replace("<slug>", "alpha")
    (keep,) = re.findall(r"git update-ref \"refs/jstack/pre-rebase/[^;]*HEAD", about)
    subprocess.run(["sh", "-c", keep], cwd=tree, check=True)
    ref = f"refs/jstack/pre-rebase/alpha/{head[:12]}"
    assert git(scene.main, "rev-parse", ref) == head

    assert scene.run() == [sweep.removed("alpha", sweep.WORKTREE, sweep.LOCAL, sweep.REMOTE)]
    assert not tree.exists()
    assert git(scene.main, "for-each-ref", "refs/heads/alpha") == ""
    assert git(scene.main, "rev-parse", ref) == head
    assert git(scene.origin, "for-each-ref", "refs/jstack") == ""


def rebased(tmp_path):
    """A pull request rebased for a conflict, not yet pushed."""
    pr = PullRequest(tmp_path, None, "other.txt")
    asked(pr, "CONFLICTING")
    before = pr.head()
    assert stays(pr, "mergeable") == ["rebased onto origin/main"]
    return pr, before


def test_a_rebased_head_is_pushed_over_the_head_the_pull_request_had(tmp_path):
    pr, before = rebased(tmp_path)
    record = pr.git_dir / "crew-before-rebase"
    assert record.read_text().splitlines() == [f"{before} main {before}"]
    assert stays(pr, "force-with-lease") == [f"pushed {pr.head()} over {before}"]
    assert git(tmp_path / "origin.git", "rev-parse", "a-task") == pr.head()
    assert not record.exists()
    (said,) = stays(pr, "force-with-lease")
    assert said.startswith("no push: ")


def test_a_branch_somebody_pushed_to_since_the_rebase_started_is_not_pushed_over(tmp_path):
    pr, before = rebased(tmp_path)
    other, origin = tmp_path / "other", tmp_path / "origin.git"
    git(other, "fetch", "-q", "origin", "a-task")
    git(other, "checkout", "-q", "-b", "a-task", "FETCH_HEAD")
    pr.commit(other, "late.txt", "pushed while the crew rebased\n", "late")
    git(other, "push", "-q", "origin", "a-task")
    late = git(other, "rev-parse", "HEAD")
    git(pr.work, "fetch", "-q", "origin")
    assert git(pr.work, "rev-parse", "origin/a-task") == late

    (said,) = stays(pr, "force-with-lease")
    assert said.startswith(f"the push was refused: origin's a-task is no longer at {before}")
    assert git(origin, "rev-parse", "a-task") == late
    assert (pr.git_dir / "crew-before-rebase").exists()
    git(pr.work, "push", "-q", "--force-with-lease", "origin", "HEAD:refs/heads/a-task")
    assert git(origin, "rev-parse", "a-task") == pr.head()


class Overlap(PullRequest):
    """A pull request and a default branch that both changed one file since it started."""

    def __init__(self, tmp_path, start, ours, theirs):
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "gh").write_text(GH)
        (self.stub / "gh").chmod(0o755)
        origin, other, self.main = tmp_path / "origin.git", tmp_path / "other", tmp_path / "main"
        self.work = tmp_path / "trees" / "a-task"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(other))
        self.commit(other, "shared.txt", start, "start")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(tmp_path, "clone", "-q", str(origin), str(self.main))
        git(self.main, "worktree", "add", "-q", "-b", "a-task", str(self.work))
        self.git_dir = Path(git(self.work, "rev-parse", "--absolute-git-dir"))
        self.commit(self.work, "shared.txt", ours, "the task")
        self.commit(self.work, "mine.txt", "the task\n", "more of the task")
        git(self.work, "push", "-q", "-u", "origin", "a-task")
        self.commit(other, "shared.txt", theirs, "theirs")
        git(other, "push", "-q", "origin", "HEAD:main")
        asked(self, "CONFLICTING")

    def resolve(self, text):
        """Rebase, settle the one file the rebase stops on as the crewmate would, and give
        the head before the rebase."""
        before = self.head()
        assert stays(self, "mergeable") == [STOPPED, "shared.txt"]
        (self.work / "shared.txt").write_text(text)
        git(self.work, "add", "shared.txt")
        git(self.work, "-c", "core.editor=true", "rebase", "--continue")
        assert not self.rebasing()
        return before


RESOLUTIONS = {
    "both sides kept": (
        "one\n",
        "one\nthe task\n",
        "theirs\n",
        "theirs\nthe task\n",
        "Kept: every line, in mine.txt shared.txt",
    ),
    "the pull request's side taken over main's line": (
        "one\n",
        "one\nthe task\n",
        "theirs\n",
        "one\nthe task\n",
        "Dropped: 1 of main's lines in shared.txt",
    ),
    "its own line lost": (
        "one\n",
        "one\nthe task\nand more\n",
        "theirs\n",
        "theirs\nthe task\n",
        "Dropped: 1 of its own in shared.txt",
    ),
    "a line of each lost": (
        "one\n",
        "one\nthe task\nand more\n",
        "theirs\ntheirs\n",
        "theirs\nthe task  \n",
        "Dropped: 1 of main's lines in shared.txt, 1 of its own in shared.txt",
    ),
    "a line the pull request deletes and main moved": (
        "a\nb\nc\nd\n",
        "b\nc\nd\nthe task\n",
        "b\nc\nd\na\n",
        "b\nc\nd\nthe task\n",
        "Kept: every line, in mine.txt shared.txt",
    ),
    "a line main deletes and the pull request moved": (
        "a\nb\nc\nd\n",
        "b\nc\nd\na\n",
        "b\nc\nd\ntheirs\n",
        "b\nc\nd\ntheirs\n",
        "Kept: every line, in mine.txt shared.txt",
    ),
}


@pytest.mark.parametrize("case", RESOLUTIONS)
def test_a_rebase_is_looked_through_for_lines_it_dropped_as_jmerge_looks(case, tmp_path):
    start, ours, theirs, resolved, says = RESOLUTIONS[case]
    pr = Overlap(tmp_path, start, ours, theirs)
    before = pr.resolve(resolved)
    assert stays(pr, "Kept:") == [says]
    assert stays(pr, "Kept:") == [says]

    git(pr.main, "fetch", "-q", "origin")
    head = pr.head()
    repo = cli.Repo(pr.main, tmp_path / "home", None, False, user=jsettings.DEFAULTS)
    rebase = repo.rebase_since_review("main", before, head)
    assert rebase == ready.Rebase("changed", ("mine.txt", "shared.txt"), before, head)
    lost = repo.dropped("main", rebase, head)
    held = ready.drops(lost, "", head, user=jsettings.DEFAULTS)
    if says.startswith("Kept:"):
        assert held == ("", "")
        return
    dropped = says.removeprefix("Dropped: ").replace(", ", " and ")
    unsaid = f"the rebase dropped {dropped} with no Dropped on rebase line at {head[:12]}"
    assert held == ("wait", unsaid)
    shape = re.search(r"`(Dropped on rebase: <file>[^`]+)`", as_read(SKILL))[1]
    assert shape == ("Dropped on rebase: <file>, <k> of main's, <j> of its own, at <head12>: <why>")
    said = "".join(
        shape.replace("<file>", one.file)
        .replace("<k>", str(one.mains))
        .replace("<j>", str(one.own))
        .replace("<head12>", head[:12])
        .replace("<why>", "the task replaces it")
        + "\n"
        for one in lost
    )
    assert ready.drops(lost, said, head, user=jsettings.DEFAULTS) == (
        "wait",
        "the scoped review has not ruled on the drops in shared.txt",
    )


@pytest.mark.skipif(shutil.which("zsh") is None, reason="zsh is not installed")
@pytest.mark.parametrize("about", ["mergeable", "Kept:", "force-with-lease"])
def test_the_blocks_of_a_rebase_say_the_same_in_zsh_which_splits_no_words(about, tmp_path):
    said = {}
    for shell in ("sh", "zsh"):
        (tmp_path / shell).mkdir()
        pr = Overlap(tmp_path / shell, "one\n", "one\nthe task\n", "theirs\n")
        ran = [stays(pr, "mergeable", shell=shell if about == "mergeable" else "sh")]
        (pr.work / "shared.txt").write_text("one\nthe task\n")
        git(pr.work, "add", "shared.txt")
        git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
        for block_of in ("Kept:", "force-with-lease"):
            ran.append(stays(pr, block_of, shell=shell if about == block_of else "sh"))
        said[shell] = [[line.replace(pr.head(), "<head>") for line in lines] for lines in ran]
    assert said["zsh"][1] == ["Dropped: 1 of main's lines in shared.txt"]
    assert [
        [re.sub(r"\b[0-9a-f]{40}\b", "<commit>", line) for line in lines] for lines in said["zsh"]
    ] == [[re.sub(r"\b[0-9a-f]{40}\b", "<commit>", line) for line in lines] for lines in said["sh"]]


def test_a_record_whose_base_is_not_here_proves_nothing(tmp_path):
    pr = Overlap(tmp_path, "one\n", "one\nthe task\n", "theirs\n")
    pr.resolve("theirs\nthe task\n")
    record = pr.git_dir / "crew-before-rebase"
    record.write_text(record.read_text().replace(" main ", " gone ", 1))
    (said,) = stays(pr, "Kept:")
    assert said.startswith("could not look: ")


def test_lines_put_back_after_the_rebase_are_kept_and_no_rebase_is_nothing_to_look_through(
    tmp_path,
):
    pr = Overlap(tmp_path, "one\n", "one\nthe task\n", "theirs\n")
    assert stays(pr, "Kept:") == ["no rebase to look through"]
    assert stays(pr, "mergeable") == [STOPPED, "shared.txt"]
    (unfinished,) = stays(pr, "Kept:")
    assert unfinished.startswith("the rebase is not finished: ")
    (pr.work / "shared.txt").write_text("one\nthe task\n")
    git(pr.work, "add", "shared.txt")
    git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    assert stays(pr, "Kept:") == ["Dropped: 1 of main's lines in shared.txt"]
    pr.commit(pr.work, "shared.txt", "theirs\nthe task\n", "put main's line back")
    assert stays(pr, "Kept:") == ["Kept: every line, in mine.txt shared.txt"]


REVIEW = "\n## Review\nVerdict: clean\nHead: {}\nFindings:\n- none\nDropped: 0\n"


REVIEWS = [
    ("", False),
    ("Reviewer: mcp:1\n", True),
    ("Reviewer: mcp:1\n" + REVIEW, False),
    ("Reviewer: none, the brief says Review: none\n", False),
    ("Reviewer: none, no launch tool in this session\n", False),
    ("Reviewer: mcp:1\nSecond reviewer: mcp:2\n" + REVIEW, True),
    ("Reviewer: mcp:1\nSecond reviewer: none, no launch tool in this session\n" + REVIEW, False),
    ("Reviewer: mcp:1\nSecond reviewer: mcp:2\n" + REVIEW + REVIEW, False),
    ("Reviewer: mcp:1\nScoped reviewer: mcp:3\n" + REVIEW, True),
    ("Reviewer: mcp:1\nScoped reviewer: mcp:3\n" + REVIEW + REVIEW, False),
    pytest.param(
        f"Reviewer: mcp:1\nScoped reviewer: mcp:4, of {'c' * 40}\n" + REVIEW + REVIEW,
        False,
        id="a scoped reviewer put in place of one that stopped is one line",
    ),
    pytest.param(
        f"Reviewer: mcp:1\nScoped reviewer: mcp:3, of {'d' * 40}\nScoped reviewer: mcp:4, "
        f"of {'c' * 40}\n" + REVIEW + REVIEW,
        True,
        id="one added under a reviewer that stopped waits for good",
    ),
    pytest.param(
        "Reviewer: mcp:1\nScoped reviewer: mcp:3\nScoped reviewer: mcp:4\n" + REVIEW + REVIEW,
        True,
        id="a second rebase's scoped reviewer has its own line",
    ),
    pytest.param(
        "Reviewer: mcp:1\n\n## Review\nVerdict: findings\n",
        True,
        id="a section started and not finished has no head yet",
    ),
]


@pytest.mark.parametrize(("under", "running"), REVIEWS)
@pytest.mark.parametrize("why", [None, "stale"])
def test_a_rebase_waits_for_a_review_that_is_running(under, running, why, tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    asked(pr, "CONFLICTING")
    before = pr.head()
    brief = BRIEF + under.replace("{}", before)
    if running:
        assert stays(pr, "mergeable", brief, why) == [REVIEWING.format(before)]
        assert pr.head() == before
        assert not (pr.git_dir / "crew-before-rebase").exists()
    else:
        assert stays(pr, "mergeable", brief, why) == ["rebased onto origin/main"]
        assert pr.head() != before


def test_the_words_of_a_reviewer_line_in_the_task_are_no_review_that_is_running(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    asked(pr, "CONFLICTING")
    brief = BRIEF.replace("Decisions:\n", "Decisions:\nReviewer: mcp:1\n")
    assert stays(pr, "mergeable", brief) == ["rebased onto origin/main"]


def test_a_rebase_that_has_stopped_is_finished_under_a_review_too(tmp_path):
    pr = PullRequest(tmp_path, None, "shared.txt")
    asked(pr, "CONFLICTING")
    assert stays(pr, "mergeable", BRIEF) == [STOPPED, "shared.txt"]
    (unfinished, file) = stays(pr, "mergeable", BRIEF + "Reviewer: mcp:1\n")
    assert unfinished.startswith("the rebase is not finished: ")
    assert file == "shared.txt"


@pytest.mark.parametrize("under", ["Reviewer: mcp:1\n", "Scoped reviewer: mcp:3\n"])
def test_a_links_move_waits_for_a_review_that_is_running(under, tmp_path):
    link = Link(tmp_path, "main")
    before = link.head()
    (tmp_path / "home" / "tasks").mkdir(parents=True)
    (tmp_path / "home" / "tasks" / "a-link.md").write_text(BRIEF + under)
    about = block("Stay on the pull request", "--onto").replace("<slug>", "a-link")
    about = about.replace("was='<the branch it sat on>'", "was='under'")
    said = link.run_text(about, H=str(tmp_path / "home")).splitlines()
    assert said == [REVIEWING.format(before)]
    assert link.head() == before


def test_the_scoped_review_of_a_rebase_is_launched_as_the_review_is_and_holds_a_rebase():
    text = sections()["Stay on the pull request"]
    (rule,) = [line for line in text.splitlines() if "Scoped reviewer: <threadId>" in line]
    assert "`the rebase changed the content after its review`" in rule
    assert "`/pr-review run <slug> scoped <old range> <new range>`" in rule
    assert "`git range-diff`" in rule
    about = block("Stay on the pull request", "mergeable")
    (counted,) = re.findall(r"/\^\(([^)]*)\): /", about)
    assert "Scoped reviewer" in counted.split("|")


@pytest.mark.parametrize("mergeable", ["MERGEABLE", "UNKNOWN", "CONFLICTING"])
@pytest.mark.parametrize("main_edits", ["other.txt", "shared.txt"])
def test_the_message_that_main_changed_its_files_rebases_whatever_github_says(
    mergeable, main_edits, tmp_path
):
    pr = PullRequest(tmp_path, None, main_edits)
    asked(pr, mergeable)
    before = pr.head()
    said = stays(pr, "mergeable", BRIEF, "stale")
    if main_edits == "other.txt":
        assert said == ["rebased onto origin/main"]
        assert git(pr.work, "rev-parse", "HEAD~1") == pr.landed
        assert stays(pr, "Kept:") == ["Kept: every line, in shared.txt"]
        assert stays(pr, "force-with-lease") == [f"pushed {pr.head()} over {before}"]
    else:
        assert said == [STOPPED, "shared.txt"]
    assert kept_at(pr, before) == before


@pytest.mark.parametrize("why", [None, "conflict"])
def test_without_that_message_a_default_branch_that_moved_is_still_no_reason(why, tmp_path):
    pr = PullRequest(tmp_path, None, "shared.txt")
    asked(pr, "MERGEABLE")
    before = pr.head()
    assert stays(pr, "mergeable", BRIEF, why) == ["no conflict: no rebase"]
    assert pr.head() == before
    assert git(tmp_path / "main", "for-each-ref", "refs/jstack") == ""


def test_the_message_never_rebases_a_link_of_a_stack_by_itself(tmp_path):
    link = Link(tmp_path, "main")
    asked(link, "MERGEABLE")
    before = link.head()
    brief = with_field("Stack: billing 2 on under")
    (said,) = stays(link, "mergeable", brief, "stale", slug="a-link")
    assert said.startswith("a link of a stack: no rebase here")
    assert link.head() == before


def test_the_message_for_a_branch_that_holds_its_base_rebases_nothing(tmp_path):
    pr = PullRequest(tmp_path, None, "other.txt")
    git(pr.work, "fetch", "-q", "origin")
    git(pr.work, "merge", "-q", "--no-edit", "origin/main")
    asked(pr, "MERGEABLE")
    before = pr.head()
    assert stays(pr, "mergeable", BRIEF, "stale") == ["already on origin/main: no rebase"]
    assert pr.head() == before


def test_a_stale_base_is_rebased_once_the_message_has_come(tmp_path):
    failed = Failed(tmp_path, holds_base=False)
    before = failed.head()
    assert failed.says("passed").split(": ")[0] == "stale"
    assert failed.head() == before
    said = stays(failed, "mergeable", why="stale", slug="alpha", state=failed.state)
    assert said == ["rebased onto origin/main"]
    assert git(failed.work, "rev-parse", "HEAD~1") == failed.landed
    assert stays(failed, "force-with-lease") == [f"pushed {failed.head()} over {before}"]
