"""A review still counts after a rebase that changed no content, and a rebase that changed
content waits for one scoped review. `git range-diff` gives the verdict, which the tests read
in real repos: a branch reviewed at one head, a default branch that moved, and the branch
rebased onto it.

The tests then run `jmerge` as `features/jmerge/tests/test_jmerge_run.py` runs it, against the
fake `gh` and real origin of `test_home_merge`."""

import subprocess
from datetime import date

import pytest

import test_home_merge as merge
import test_jmerge_run as run
from jbus import rebase as asks
from jmerge import rangediff, ready

FILE = "f.txt"
LINES = [f"line {number}" for number in range(1, 31)]
LATER = {**merge.PASSED, "startedAt": f"{date.today().year + 1}-01-01T00:00:00Z"}


def write(tree, edits, path=FILE):
    lines = (tree / path).read_text().splitlines() if (tree / path).exists() else list(LINES)
    for number, text in edits.items():
        lines[number - 1] = text
    (tree / path).write_text("\n".join(lines) + "\n")


def commit(tree, message, edits, path=FILE):
    write(tree, edits, path)
    merge.git(tree, "add", path)
    merge.git(tree, "commit", "-q", "-m", message)
    return merge.git(tree, "rev-parse", "HEAD")


TASK = {10: "the task 10", 11: "the task 11", 12: "the task 12", 20: "the task 20"}


class Branch:
    """An origin whose main has a file of thirty lines, a checkout of it, and a branch that
    changes four of those lines in one commit, which is the head a review saw."""

    def __init__(self, tmp_path, commits=(TASK,)):
        self.origin = tmp_path / "branch-origin.git"
        self.main = tmp_path / "branch-main"
        self.main.mkdir()
        merge.git(tmp_path, "init", "-q", "--bare", "-b", "main", str(self.origin))
        merge.git(self.main, "init", "-q", "-b", "main")
        self.base = commit(self.main, "start", {})
        merge.git(self.main, "remote", "add", "origin", str(self.origin))
        merge.git(self.main, "push", "-q", "-u", "origin", "main")
        merge.git(self.main, "checkout", "-q", "-b", "alpha")
        for number, edits in enumerate(commits):
            self.reviewed = commit(self.main, f"the task, part {number}", edits)
        merge.git(self.main, "checkout", "-q", "main")

    def theirs(self, edits):
        """Another pull request lands on main."""
        self.tip = commit(self.main, "theirs", edits)
        merge.git(self.main, "push", "-q", "origin", "main")

    def rebase(self, resolved=None):
        merge.git(self.main, "checkout", "-q", "alpha")
        try:
            merge.git(self.main, "-c", "core.editor=true", "rebase", "-q", "origin/main")
        except subprocess.CalledProcessError:
            merge.git(self.main, "checkout", "--theirs", FILE)
            write(self.main, resolved)
            merge.git(self.main, "add", FILE)
            merge.git(self.main, "-c", "core.editor=true", "rebase", "--continue")
        self.head = merge.git(self.main, "rev-parse", "HEAD")
        merge.git(self.main, "checkout", "-q", "main")
        return self.verdict()

    def verdict(self):
        return rangediff.verdict(self.main, self.reviewed, self.head, "main")

    def command(self):
        return f"git range-diff --no-color {self.base}..{self.reviewed} {self.tip}..{self.head}"


@pytest.fixture
def branch(tmp_path):
    return Branch(tmp_path)


def test_a_rebase_over_a_disjoint_change_to_the_same_file_is_clean(branch):
    branch.theirs({28: "theirs 28"})
    said = branch.rebase()
    assert said == rangediff.Verdict(
        True,
        branch.command(),
        "the range-diff changes no content",
        f"{branch.base}..{branch.reviewed}",
        f"{branch.tip}..{branch.head}",
    )


def test_a_rebase_that_moved_only_a_context_line_under_a_hunk_is_clean(branch):
    branch.theirs({8: "theirs 8"})
    said = branch.rebase()
    assert (said.clean, said.why) == (True, "the range-diff changes no content")
    ran = subprocess.run(said.command.split(), cwd=branch.main, capture_output=True, text=True)
    assert " ! " in ran.stdout and "    - line 8\n    + theirs 8\n" in ran.stdout


def test_a_rebase_whose_conflict_resolution_changes_an_added_line_is_not_clean(branch):
    branch.theirs({11: "theirs 11"})
    said = branch.rebase({11: "the task 11, and theirs"})
    assert not said.clean and said.command == branch.command()
    assert said.why in (
        "the range-diff changes content: -+the task 11",
        "the range-diff changes content: --line 11",
        f"the commits do not pair up, and the two diffs differ in a/{FILE} b/{FILE}",
    )


def test_a_squash_of_two_reviewed_commits_with_the_same_content_is_clean(tmp_path):
    branch = Branch(tmp_path, commits=({10: "the task 10", 11: "the task 11"}, {20: "the task 20"}))
    branch.theirs({28: "theirs 28"})
    merge.git(branch.main, "checkout", "-q", "alpha")
    merge.git(branch.main, "-c", "core.editor=true", "rebase", "-q", "origin/main")
    merge.git(branch.main, "reset", "-q", "--soft", "origin/main")
    merge.git(branch.main, "commit", "-q", "-m", "the task, squashed")
    branch.head = merge.git(branch.main, "rev-parse", "HEAD")
    said = branch.verdict()
    assert (said.clean, said.command) == (True, branch.command())
    assert said.why == "the commits do not pair up, and the two diffs add and remove the same lines"


def test_a_squash_that_dropped_a_line_is_not_clean(tmp_path):
    branch = Branch(tmp_path, commits=({10: "the task 10", 11: "the task 11"}, {20: "the task 20"}))
    branch.theirs({28: "theirs 28"})
    merge.git(branch.main, "checkout", "-q", "alpha")
    merge.git(branch.main, "reset", "-q", "--hard", "origin/main")
    branch.head = commit(branch.main, "the task, squashed", {10: "the task 10", 20: "the task 20"})
    said = branch.verdict()
    assert not said.clean
    assert said.why == (
        f"the commits do not pair up, and the two diffs differ in a/{FILE} b/{FILE}"
    )


@pytest.mark.parametrize("moved", ["merge", "rebase"])
def test_a_commit_of_mains_in_the_reviewed_range_that_the_new_head_holds_is_left_out(branch, moved):
    """#562: its reviewed range, from where it forked from the link under it, held that link's
    squash merge on main, 7d5be3659 "(#561)", which the new head's base then held too."""
    branch.theirs({28: "the link under 28"})
    under = branch.tip
    merge.git(branch.main, "checkout", "-q", "alpha")
    merge.git(branch.main, "-c", "core.editor=true", "rebase", "-q", "origin/main")
    branch.reviewed = merge.git(branch.main, "rev-parse", "HEAD")
    merge.git(branch.main, "checkout", "-q", "main")
    branch.theirs({2: "theirs 2"})
    merge.git(branch.main, "checkout", "-q", "alpha")
    if moved == "merge":
        merge.git(branch.main, "merge", "-q", "--no-edit", "origin/main")
    else:
        merge.git(branch.main, "-c", "core.editor=true", "rebase", "-q", "origin/main")
    branch.head = merge.git(branch.main, "rev-parse", "HEAD")
    merge.git(branch.main, "checkout", "-q", "main")
    said = rangediff.verdict(branch.main, branch.reviewed, branch.head, "main", branch.base)
    old, new = f"{under}..{branch.reviewed}", f"{branch.tip}..{branch.head}"
    assert said == rangediff.Verdict(
        True,
        f"git range-diff --no-color {old} {new}",
        "the range-diff changes no content",
        old,
        new,
    )


def test_a_commit_of_its_own_the_new_head_left_out_is_still_a_change(tmp_path):
    """The reviewed range holds a commit of main's as #562's did, which is left out, and the
    rebase drops the second of its own two commits, which is not."""
    branch = Branch(tmp_path, commits=({10: "the task 10"}, {20: "the task 20"}))
    branch.theirs({28: "the link under 28"})
    under = branch.tip
    merge.git(branch.main, "checkout", "-q", "alpha")
    merge.git(branch.main, "-c", "core.editor=true", "rebase", "-q", "origin/main")
    branch.reviewed = merge.git(branch.main, "rev-parse", "HEAD")
    merge.git(branch.main, "checkout", "-q", "main")
    branch.theirs({2: "theirs 2"})
    merge.git(branch.main, "checkout", "-q", "-b", "beta", "origin/main")
    merge.git(branch.main, "cherry-pick", f"{branch.reviewed}~1")
    branch.head = merge.git(branch.main, "rev-parse", "HEAD")
    merge.git(branch.main, "checkout", "-q", "main")
    said = rangediff.verdict(branch.main, branch.reviewed, branch.head, "main", branch.base)
    assert (said.clean, said.old) == (False, f"{under}..{branch.reviewed}")


def test_a_commit_that_is_not_here_and_cannot_be_fetched_is_not_clean(branch):
    branch.theirs({28: "theirs 28"})
    branch.rebase()
    gone = "c" * 40
    said = rangediff.verdict(branch.main, gone, branch.head, "main")
    assert not said.clean
    assert said.why.startswith(f"the commit {gone} is not here and could not be fetched: git fetch")
    assert (
        said.command == f"git range-diff --no-color origin/main..{gone} origin/main..{branch.head}"
    )


def test_a_commit_the_origin_still_has_is_fetched_once(branch, tmp_path):
    branch.theirs({8: "theirs 8"})
    branch.rebase()
    merge.git(branch.main, "push", "-q", "origin", f"{branch.reviewed}:refs/heads/before")
    merge.git(branch.main, "push", "-q", "origin", f"{branch.head}:refs/heads/alpha")
    other = tmp_path / "other"
    merge.git(
        tmp_path, "clone", "-q", "--single-branch", "-b", "main", str(branch.origin), str(other)
    )
    said = rangediff.verdict(other, branch.reviewed, branch.head, "main")
    assert (said.clean, said.command) == (True, branch.command())


@pytest.mark.parametrize("reviewed", ["", "abc1234", "--upload-pack=/bin/true", "main"])
def test_a_reviewed_head_that_is_no_full_commit_is_not_clean_and_git_is_not_asked(branch, reviewed):
    branch.theirs({28: "theirs 28"})
    branch.rebase()
    said = rangediff.verdict(branch.main / "nowhere", reviewed, branch.head, "main")
    assert (said.clean, said.why) == (
        False,
        "the reviewed head and the head are not both full commits",
    )


def test_a_git_that_cannot_say_is_not_clean(branch, tmp_path):
    branch.theirs({28: "theirs 28"})
    branch.rebase()
    empty = tmp_path / "empty"
    empty.mkdir()
    said = rangediff.verdict(empty, branch.reviewed, branch.head, "main")
    assert not said.clean and "git fetch failed" in said.why


@pytest.mark.parametrize("path", ["Metadata.json", "Metadata", "Commit message"])
def test_a_file_named_as_git_names_a_part_of_a_commit_is_read_as_any_other(tmp_path, path):
    main = tmp_path / "named"
    main.mkdir()
    merge.git(main, "init", "-q", "-b", "main")
    commit(main, "start", {}, path)
    merge.git(main, "update-ref", "refs/remotes/origin/main", "HEAD")
    merge.git(main, "checkout", "-q", "-b", "alpha")
    reviewed = commit(main, "the task", TASK, path)
    merge.git(main, "checkout", "-q", "main")
    commit(main, "theirs", {11: "theirs 11"}, path)
    merge.git(main, "update-ref", "refs/remotes/origin/main", "HEAD")
    merge.git(main, "checkout", "-q", "alpha")
    with pytest.raises(subprocess.CalledProcessError):
        merge.git(main, "rebase", "-q", "origin/main")
    merge.git(main, "checkout", "--theirs", path)
    write(main, {11: 'the task 11; os.system("evil")'}, path)
    merge.git(main, "add", path)
    merge.git(main, "-c", "core.editor=true", "rebase", "--continue")
    head = merge.git(main, "rev-parse", "HEAD")
    said = rangediff.verdict(main, reviewed, head, "main")
    assert not said.clean
    ran = subprocess.run(said.command.split(), cwd=main, capture_output=True, text=True)
    assert f"    @@ {path}" in ran.stdout


def conflict(tmp_path, path, start, task, theirs, resolved):
    """A branch that writes `task` to a file, a main that writes `theirs` to it after the
    review, and a rebase resolved by hand to `resolved`. It returns the verdict."""
    main = tmp_path / "bytes"
    main.mkdir()
    merge.git(main, "init", "-q", "-b", "main")
    write(main, {})

    def put(data, message):
        (main / path).write_bytes(data)
        merge.git(main, "add", ".")
        merge.git(main, "commit", "-q", "-m", message)
        return merge.git(main, "rev-parse", "HEAD")

    put(start, "start")
    merge.git(main, "update-ref", "refs/remotes/origin/main", "HEAD")
    merge.git(main, "checkout", "-q", "-b", "alpha")
    write(main, TASK)
    reviewed = put(task, "the task")
    merge.git(main, "checkout", "-q", "main")
    put(theirs, "theirs")
    merge.git(main, "update-ref", "refs/remotes/origin/main", "HEAD")
    merge.git(main, "checkout", "-q", "alpha")
    with pytest.raises(subprocess.CalledProcessError):
        merge.git(main, "rebase", "-q", "origin/main")
    (main / path).write_bytes(resolved)
    merge.git(main, "add", path)
    merge.git(main, "-c", "core.editor=true", "rebase", "--continue")
    said = rangediff.verdict(main, reviewed, merge.git(main, "rev-parse", "HEAD"), "main")
    ran = subprocess.run(said.command.split(), cwd=main, capture_output=True, text=True)
    return said, ran.stdout


def test_a_binary_file_the_rebase_left_with_other_bytes_is_not_clean(tmp_path):
    blob = bytes(range(256)) * 4
    said, shown = conflict(
        tmp_path, "blob.bin", blob, blob + b"\0task", blob + b"\0theirs", blob + b"\0both"
    )
    assert rangediff.content_change(shown) == ("", False)
    assert (said.clean, said.why) == (
        False,
        "the range-diff shows no content, and the two diffs differ in a/blob.bin b/blob.bin",
    )


def test_a_rebase_that_dropped_the_newline_at_the_end_of_a_file_is_not_clean(tmp_path):
    said, shown = conflict(tmp_path, "end.txt", b"start\n", b"task\n", b"theirs\n", b"task")
    assert not said.clean
    assert "No newline at end of file" in shown or "do not pair up" in said.why


RANGE_DIFF = """\
1:  7d65a31 = 1:  0a1b2c3 a commit that is the same
2:  7d65a32 ! 2:  d940842 the task
    @@ Metadata
    -Author: one <one@example.com>
    +Author: two <two@example.com>
    @@ Commit message
    -    the tsak
    +    the task
    {message}
      ## f.txt ##
     @@
    - line 8
    + theirs 8
      line 9
    {patch}
     -line 10
     +the task 10
"""


@pytest.mark.parametrize(
    ("message", "patch", "first"),
    [
        ("     more of the message", "  line 9", ""),
        ("-    +a line of the message that starts with a sign", "  line 9", ""),
        (
            "-+a line git never prints in a message",
            "  line 9",
            "-+a line git never prints in a message",
        ),
        ("     more", "- ## Metadata ##", "- ## Metadata ##"),
        ("     more", "-Author: a line of a patch never starts so", ""),
        ("     more", "-@@ f.txt: def one():", ""),
        ("     more", "-", ""),
        ("     more", "-+the task 9", "-+the task 9"),
        ("     more", "+-line 9", "+-line 9"),
        ("     more", "++the task 9", "++the task 9"),
        ("     more", "--line 9", "--line 9"),
        ("     more", "+\\ No newline at end of file", "+\\ No newline at end of file"),
        ("     more", "+ ## g.txt (new) ##", "+ ## g.txt (new) ##"),
    ],
)
def test_content_is_a_line_added_or_removed_on_one_side_alone_outside_the_message(
    message, patch, first
):
    said = RANGE_DIFF.format(message=message, patch=patch)
    assert rangediff.content_change(said) == (f"    {first}" if first else "", False)


def test_a_commit_on_one_side_alone_is_said_and_a_line_that_cannot_be_read_is_content():
    unpaired = "1:  7d65a31 < -:  ------- one\n-:  ------- > 1:  d940842 two\n"
    assert rangediff.content_change(unpaired) == ("", True)
    assert rangediff.content_change("warning: something else\n") == (
        "warning: something else",
        False,
    )
    assert rangediff.content_change("") == ("", False)


class Rebased:
    """The ready pull request of `test_home_merge`, on a file of thirty lines. A review found it
    clean at one head, and then its crewmate rebased it over a change to that file that main
    took after the review."""

    def __init__(self, proven_merged, theirs, resolved=None, files=(FILE,)):
        self.proven_merged, self.files = proven_merged, files
        main, tree = proven_merged.home.main, proven_merged.tree
        commit(main, "the file", {})
        merge.git(main, "push", "-q", "origin", "main")
        merge.git(tree, "fetch", "-q", "origin")
        merge.git(tree, "rebase", "-q", "origin/main")
        self.before = commit(tree, "the task in the file", TASK)
        merge.git(tree, "push", "-q", "--force", "origin", "alpha")
        merge.git(main, "fetch", "-q", "origin")
        merge.git(
            main, "update-ref", f"refs/jstack/pre-rebase/alpha/{self.before[:12]}", self.before
        )
        self.base = merge.git(main, "rev-parse", "HEAD")
        self.tip = commit(main, "theirs", theirs)
        merge.git(main, "push", "-q", "origin", "main")
        merge.git(tree, "fetch", "-q", "origin")
        try:
            merge.git(tree, "-c", "core.editor=true", "rebase", "-q", "origin/main")
        except subprocess.CalledProcessError:
            merge.git(tree, "checkout", "--theirs", FILE)
            write(tree, resolved)
            merge.git(tree, "add", FILE)
            merge.git(tree, "-c", "core.editor=true", "rebase", "--continue")
        merge.git(tree, "push", "-q", "--force", "origin", "alpha")
        self.head = merge.git(tree, "rev-parse", "HEAD")
        proven_merged.home.open_pull_request(self.head, checks=(LATER,), files=list(files))
        self.brief(run.proven("clean", self.before))

    def brief(self, review, more=""):
        """The brief as the crewmate leaves it after the rebase, which says nothing of it: the
        crew's keep step kept the head before it under `refs/jstack/pre-rebase/alpha/`."""
        (self.proven_merged.home.tasks / "alpha.md").write_text(merge.brief(review, more))

    def command(self):
        return f"git range-diff --no-color {self.base}..{self.before} {self.tip}..{self.head}"

    def carried(self):
        return (
            f"review carried over: range-diff {self.base[:12]}..{self.before[:12]} "
            f"{self.tip[:12]}..{self.head[:12]} clean, every line kept"
        )

    def waits(self):
        return (
            f"wait 7 {merge.URL}: the rebase changed the content after its review; "
            f"scoped review of {self.command()}"
        )


BOTH = {11: "theirs 11\nthe task 11"}


def test_a_rebase_that_changed_no_content_carries_the_review_over_and_is_merged(
    proven_merged, rules
):
    rebased = Rebased(proven_merged, {8: "theirs 8"})
    ready_line = f"ready 7 {rebased.head} alpha alpha, {rebased.carried()}"
    assert run.jmerge(proven_merged, rules, "--check") == [ready_line]
    (said,) = run.jmerge(proven_merged, rules)
    commit_, pulled = proven_merged.on_main()
    assert said == merge.merged_line(commit_, rebased.carried())
    assert pulled == commit_
    assert proven_merged.log()[-1].endswith(said)


def test_a_rebase_that_changed_the_content_waits_for_one_scoped_review(proven_merged, rules):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    assert run.jmerge(proven_merged, rules) == [rebased.waits()]
    assert run.merges(proven_merged) == []


def test_a_review_of_the_rebased_head_is_the_scoped_review_it_waited_for(proven_merged, rules):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    rebased.brief(merge.review("clean", rebased.before) + run.proven("clean", rebased.head))
    assert run.jmerge(proven_merged, rules, "--check") == [f"ready 7 {rebased.head} alpha alpha"]


def test_after_a_fix_the_review_is_compared_from_the_commit_before_the_rebase(proven_merged, rules):
    rebased = Rebased(proven_merged, {8: "theirs 8"})
    ended = f"Finding: fixed, it is wrong\nFixed: {rebased.head}\n"
    rebased.brief(merge.review("findings", rebased.base), ended)
    assert run.jmerge(proven_merged, rules, "--check") == [
        f"ready 7 {rebased.head} alpha alpha, {rebased.carried()}"
    ]


def test_a_second_rebase_is_compared_with_the_head_the_review_saw(proven_merged, rules):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    reviewed, first, tree, main = (
        rebased.before,
        rebased.head,
        proven_merged.tree,
        proven_merged.home.main,
    )
    rebased.tip = commit(main, "theirs again", {}, "other.txt")
    merge.git(main, "push", "-q", "origin", "main")
    merge.git(tree, "fetch", "-q", "origin")
    merge.git(tree, "rebase", "-q", "origin/main")
    merge.git(tree, "push", "-q", "--force", "origin", "alpha")
    rebased.head = merge.git(tree, "rev-parse", "HEAD")
    proven_merged.home.open_pull_request(rebased.head, checks=(LATER,), files=[FILE])
    rebased.before = first
    rebased.brief(merge.review("clean", reviewed))
    rebased.before = reviewed
    assert run.jmerge(proven_merged, rules) == [rebased.waits()]


def test_a_rebase_that_left_the_patch_as_it_was_carries_the_review_over(proven_merged, rules):
    rebased = Rebased(proven_merged, {28: "theirs 28"})
    rebased.brief(merge.review("clean", rebased.before))
    assert run.jmerge(proven_merged, rules, "--check") == [
        f"ready 7 {rebased.head} alpha alpha, {rebased.carried()}"
    ]


@pytest.mark.parametrize(
    "line",
    [
        "Rebase: patch unchanged, before {before}, head {head}\n",
        "Rebase: patch unchanged, before {before:.7} (local, unpushed), head {head:.7}\n",
        "Rebase: patch unchanged, onto origin/main after it gained 1 commit, before the push\n",
    ],
    ids=["untrue", "short commits", "no commit"],
)
def test_a_rebase_line_a_crew_wrote_is_judged_as_the_brief_with_no_line(proven_merged, rules, line):
    """The old `Rebase:` shapes held a pull request as `rebase-untrue` and `rebase-unsaid`. Now
    `jmerge` works the rebase out from git and reads no such line, so each brief gets what the
    same brief with no line gets."""
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    rebased.brief(merge.review("clean", rebased.before))
    without = run.jmerge(proven_merged, rules, "--check")
    told = line.format(before=rebased.before, head=rebased.head)
    rebased.brief(merge.review("clean", rebased.before), told)
    assert run.jmerge(proven_merged, rules, "--check") == without == [rebased.waits()]


def test_a_review_that_names_no_head_has_nothing_to_compare_the_rebase_with(proven_merged, rules):
    rebased = Rebased(proven_merged, {8: "theirs 8"})
    review = merge.review("clean", rebased.before).replace(f"Head: {rebased.before}", "Head:")
    rebased.brief(review)
    assert run.jmerge(proven_merged, rules) == [
        f"wait 7 {merge.URL}: its review names no head to compare its rebase with"
    ]


FIXED = "Finding: fixed, it is wrong\nFixed: {}\n"
UNSAID = {
    "a clean review of the head before the rebase": ("clean", ""),
    "a fix at the head before the rebase, and a Fixed line that still names it": (
        "findings",
        FIXED,
    ),
}


def unsaid(rebased, case=tuple(UNSAID)[-1], more="", then=""):
    """The brief as a crewmate leaves it now: no `Rebase:` line, and a `Fixed:` line that names
    the commit it named before the rebase. `then` is a review written since."""
    verdict, fixed = UNSAID[case]
    review = run.proven(verdict, rebased.before if verdict == "clean" else rebased.base)
    rebased.brief(review + then, fixed.format(rebased.before) + more)


@pytest.mark.parametrize("case", UNSAID)
def test_a_rebased_head_no_line_names_is_merged_where_the_range_diff_is_clean(
    proven_merged, rules, case
):
    rebased = Rebased(proven_merged, {8: "theirs 8"})
    unsaid(rebased, case)
    ready_line = f"ready 7 {rebased.head} alpha alpha, {rebased.carried()}"
    assert run.jmerge(proven_merged, rules, "--check") == [ready_line]
    (said,) = run.jmerge(proven_merged, rules)
    commit_, pulled = proven_merged.on_main()
    assert said == merge.merged_line(commit_, rebased.carried())
    assert "review carried over" in said and pulled == commit_


@pytest.mark.parametrize("case", UNSAID)
def test_a_rebased_head_no_line_names_waits_where_the_rebase_changed_the_content(
    proven_merged, rules, case
):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    unsaid(rebased, case)
    assert run.jmerge(proven_merged, rules) == [rebased.waits()]
    assert run.merges(proven_merged) == []
    number, _, ask = asks.content(rebased.waits())
    assert (number, ask.kind, ask.head) == (7, "rereview", rebased.head)


def test_a_review_of_the_rebased_head_ends_the_wait_and_its_findings_are_still_to_handle(
    proven_merged, rules
):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    unsaid(rebased, then=merge.review("clean", rebased.head))
    assert run.jmerge(proven_merged, rules, "--check") == [f"ready 7 {rebased.head} alpha alpha"]
    unsaid(rebased, then=merge.review("findings", rebased.head))
    assert run.jmerge(proven_merged, rules) == [
        f"wait 7 {merge.URL}: its findings are not handled: nothing was pushed after them"
    ]


@pytest.mark.parametrize("line", ["Fixed: {}\n", ""])
@pytest.mark.parametrize("gone", ["c" * 40, None])
def test_a_covered_commit_that_cannot_be_had_waits_and_is_never_merged(
    proven_merged, rules, line, gone
):
    """When `gone` is `None`, the covered commit is the head's tree, an object that git has but
    cannot read as a commit."""
    rebased = Rebased(proven_merged, {8: "theirs 8"})
    gone = gone or merge.git(proven_merged.tree, "rev-parse", "HEAD^{tree}")
    verdict = "findings" if line else "clean"
    review = merge.review(verdict, rebased.base if line else gone)
    rebased.brief(review, ("Finding: fixed, it is wrong\n" + line.format(gone)) if line else "")
    assert run.jmerge(proven_merged, rules) == [
        f"wait 7 {merge.URL}: the rebase changed the content after its review; scoped review "
        f"of git range-diff --no-color origin/main..{gone} origin/main..{rebased.head}"
    ]
    assert run.merges(proven_merged) == []


def test_a_review_that_names_no_head_has_nothing_to_compare_a_moved_head_with(proven_merged, rules):
    rebased = Rebased(proven_merged, {8: "theirs 8"})
    review = merge.review("clean", rebased.before).replace(f"Head: {rebased.before}", "Head:")
    rebased.brief(review)
    assert run.jmerge(proven_merged, rules) == [f"wait 7 {merge.URL}: {ready.NO_HEAD}"]


def test_the_lines_a_rebase_dropped_are_counted_from_the_commit_the_review_covers(
    proven_merged, rules
):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, {11: "the task 11"})
    unsaid(rebased)
    silent = (
        f"wait 7 {merge.URL}: the rebase dropped 1 of main's lines in {FILE} "
        f"with no Dropped on rebase line at {rebased.head[:12]}"
    )
    assert run.jmerge(proven_merged, rules) == [silent]
    ack = f"Dropped on rebase: {FILE}, 1 of main's, 0 of its own, at {rebased.head[:12]}: ours\n"
    unsaid(rebased, more=ack)
    assert run.jmerge(proven_merged, rules) == [rebased.waits()]
    scoped = merge.review("clean", rebased.head)
    against = scoped.replace("Head:", f"Drops: not upheld {FILE}: main needs it\nHead:")
    unsaid(rebased, more=ack, then=against)
    (said,) = run.jmerge(proven_merged, rules)
    assert said.startswith(f"hold 7 {merge.URL}: needs ")
    assert said.endswith(f"the review did not uphold the drop in {FILE}: main needs it")
    unsaid(rebased, more=ack, then=scoped.replace("Head:", f"Drops: upheld {FILE}\nHead:"))
    assert run.jmerge(proven_merged, rules, "--check") == [f"ready 7 {rebased.head} alpha alpha"]
    assert run.merges(proven_merged) == []


def pushed_after(rebased, review_of):
    """The crew pushes a fix for a failed check on top of the rebased head and sets the brief's
    `Fixed:` line to that push. The brief's review, which had findings, saw `review_of`."""
    tree = rebased.proven_merged.tree
    pushed = commit(tree, "what the check asked for", {15: "what the check asked for"})
    merge.git(tree, "push", "-q", "origin", "alpha")
    rebased.proven_merged.home.open_pull_request(pushed, checks=(LATER,), files=[FILE])
    rebased.brief(merge.review("findings", review_of), FIXED.format(pushed))
    return pushed


def test_a_fixed_line_moved_past_a_rebase_no_review_saw_does_not_stand_for_that_review(
    proven_merged, rules
):
    """The fix is not on top of the head the review saw, so a rebase came between them."""
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    pushed = pushed_after(rebased, rebased.before)
    assert run.jmerge(proven_merged, rules) == [rebased.waits().replace(rebased.head, pushed)]
    assert run.merges(proven_merged) == []


def test_a_fixed_line_over_a_reviewed_head_git_cannot_have_waits_and_is_never_merged(
    proven_merged, rules
):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    gone = "c" * 40
    pushed = pushed_after(rebased, gone)
    assert run.jmerge(proven_merged, rules) == [
        f"wait 7 {merge.URL}: the rebase changed the content after its review; scoped review "
        f"of git range-diff --no-color origin/main..{gone} origin/main..{pushed}"
    ]
    assert run.merges(proven_merged) == []


def test_a_fixed_line_that_names_a_push_on_the_reviewed_head_is_ready_as_it_was(
    proven_merged, rules
):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, BOTH)
    pushed = pushed_after(rebased, rebased.head)
    assert run.jmerge(proven_merged, rules, "--check") == [f"ready 7 {pushed} alpha alpha"]


def test_the_dropped_lines_are_counted_under_a_ci_fix_line_too(proven_merged, rules):
    rebased = Rebased(proven_merged, {11: "theirs 11"}, {11: "the task 11"})
    line = f"CI fix: {rebased.head}, after the review of {rebased.before}\n"
    rebased.brief(merge.review("clean", rebased.before), line)
    assert run.jmerge(proven_merged, rules) == [
        f"wait 7 {merge.URL}: the rebase dropped 1 of main's lines in {FILE} "
        f"with no Dropped on rebase line at {rebased.head[:12]}"
    ]


STORE = tuple(f"api/pkg/store/{name}.go" for name in "abcde")
CLIENT = tuple(f"client/{name}.ts" for name in "abcde")


def mains(path):
    return f"main's 20 in {path}"


class Shaped:
    """The shape of Winnifred #154: two directories of many files, a pull request that adds a
    line to each, and a main that added one to each since. The rebase kept every line of
    both. The exception is main's lines that `edits` changes after the rebase, by editing a
    line in place or by removing it."""

    def __init__(self, proven_merged, edits):
        main, tree = proven_merged.home.main, proven_merged.tree
        for path in STORE + CLIENT:
            (main / path).parent.mkdir(parents=True, exist_ok=True)
            write(main, {}, path)
        merge.git(main, "add", "-A")
        merge.git(main, "commit", "-q", "-m", "the two directories")
        merge.git(main, "push", "-q", "origin", "main")
        merge.git(tree, "fetch", "-q", "origin")
        merge.git(tree, "rebase", "-q", "origin/main")
        for path in STORE + CLIENT:
            write(tree, {5: f"line 5\nthe task in {path}"}, path)
        merge.git(tree, "commit", "-q", "-am", "the task in both directories")
        self.before = merge.git(tree, "rev-parse", "HEAD")
        for path in STORE + CLIENT:
            write(main, {20: f"line 20\n{mains(path)}"}, path)
        merge.git(main, "commit", "-q", "-am", "main's audit trail")
        merge.git(main, "push", "-q", "origin", "main")
        merge.git(tree, "fetch", "-q", "origin")
        merge.git(tree, "rebase", "-q", "origin/main")
        for path, line in edits.items():
            text = (tree / path).read_text().replace(f"{mains(path)}\n", line)
            (tree / path).write_text(text)
        merge.git(tree, "commit", "-q", "-a", "--amend", "--no-edit")
        merge.git(tree, "push", "-q", "--force", "origin", "alpha")
        self.head = merge.git(tree, "rev-parse", "HEAD")
        proven_merged.home.open_pull_request(self.head, checks=(LATER,), files=[*STORE, *CLIENT])
        self.proven_merged = proven_merged

    def brief(self, told, more=""):
        """The brief with no `Rebase:` line, or with the `Rebase:` line of #154, which names
        directories in free text."""
        line = (
            "Rebase: patch changed in api/pkg/store (exports now a typed read in main's audit "
            f"trail, #146), client activity, before {self.before}, head {self.head}\n"
        )
        review = run.proven("clean", self.before)
        result = (line if told else "") + more
        (self.proven_merged.home.tasks / "alpha.md").write_text(merge.brief(review, result))

    def dropped(self, lost):
        return (
            f"wait 7 {merge.URL}: the rebase dropped {lost} "
            f"with no Dropped on rebase line at {self.head[:12]}"
        )


IN_PLACE = {STORE[0]: f"{mains(STORE[0])}, edited\n", CLIENT[2]: f"{mains(CLIENT[2])}, edited\n"}


@pytest.mark.parametrize("told", [True, False], ids=["a Rebase line naming directories", "none"])
def test_a_rebase_that_kept_mains_lines_counts_only_its_in_place_edits_each_in_its_file(
    proven_merged, rules, told
):
    shaped = Shaped(proven_merged, IN_PLACE)
    shaped.brief(told)
    assert run.jmerge(proven_merged, rules) == [
        shaped.dropped(f"1 of main's lines in {STORE[0]} and 1 of main's lines in {CLIENT[2]}")
    ]


def test_a_line_of_mains_the_rebase_lost_still_waits_once_the_in_place_edits_are_answered(
    proven_merged, rules
):
    shaped = Shaped(proven_merged, {**IN_PLACE, CLIENT[4]: ""})
    acked = "".join(
        f"Dropped on rebase: {path}, 1 of main's, 0 of its own, at {shaped.head[:12]}: edited\n"
        for path in IN_PLACE
    )
    shaped.brief(True, acked)
    assert run.jmerge(proven_merged, rules) == [shaped.dropped(f"1 of main's lines in {CLIENT[4]}")]
    assert run.merges(proven_merged) == []


def test_a_ci_fix_that_takes_out_a_line_of_its_own_with_no_rebase_drops_nothing(
    proven_merged, rules
):
    rebased = Rebased(proven_merged, {8: "theirs 8"})
    tree = proven_merged.tree
    pushed = commit(tree, "the check wanted line 20 back", {20: "line 20"})
    merge.git(tree, "push", "-q", "origin", "alpha")
    proven_merged.home.open_pull_request(pushed, checks=(LATER,), files=[FILE])
    line = f"CI fix: {pushed}, after the review of {rebased.head}\n"
    rebased.brief(merge.review("clean", rebased.head), line)
    (said,) = run.jmerge(proven_merged, rules)
    assert "dropped" not in said
    assert said == (
        f"wait 7 {merge.URL}: the rebase changed the content after its review; scoped review "
        f"of git range-diff --no-color {rebased.tip}..{rebased.head} {rebased.tip}..{pushed}"
    )


REVIEWED, BEFORE, FIRST, HEAD = ("a" * 40, "b" * 40, "c" * 40, "d" * 40)
TOLD = f"Rebase: patch changed in {FILE}, before {BEFORE}, head {FIRST}\n"


def test_a_rebase_line_of_an_older_brief_is_read_as_no_line():
    """A brief from before `jmerge` worked the rebase out from git may still say what its rebase
    did. Its review covers what it covers with the line or without it."""
    result = FIXED.format(FIRST)
    for told in ("", TOLD):
        text = merge.brief(merge.review("findings", REVIEWED), told + result)
        assert ready.rebase_of(text, FIRST) is None
        assert ready.to_range_diff(text, HEAD) == FIRST


def test_a_clean_review_after_the_fix_is_the_one_a_later_rebase_is_compared_with():
    fixed = FIXED.format(BEFORE)
    scoped = merge.review("findings", REVIEWED) + merge.review("clean", FIRST)
    assert ready.to_range_diff(merge.brief(scoped, fixed), HEAD) == FIRST
    assert ready.to_range_diff(merge.brief(merge.review("clean", REVIEWED), fixed), HEAD) == (
        BEFORE
    )
    findings = merge.review("findings", REVIEWED) + merge.review("findings", FIRST)
    assert ready.to_range_diff(merge.brief(findings, fixed), HEAD) == BEFORE


def test_findings_written_after_the_fixed_line_keep_a_head_that_moved_on_from_a_merge():
    reviews = merge.review("findings", REVIEWED) + merge.review("findings", FIRST)
    text = merge.brief(reviews, FIXED.format(BEFORE))
    assert ready.short_of(text, HEAD) == (
        "its findings are not handled: 1 of 2 have no Finding line"
    )
    assert (
        ready.short_of(merge.brief(reviews, "Finding: fixed, it\n" + FIXED.format(HEAD)), HEAD)
        == ""
    )


class CiFix:
    """The ready pull request of `test_home_merge`, on a file of thirty lines. A review found it
    clean at one head. Then its crewmate pushed to it again for a failed check, and wrote the
    line that the crew writes about such a push."""

    def __init__(
        self,
        proven_merged,
        edits,
        files=(FILE,),
        line="CI fix: {head}, after the review of {before}",
    ):
        self.proven_merged = proven_merged
        main, tree = proven_merged.home.main, proven_merged.tree
        commit(main, "the file", {})
        merge.git(main, "push", "-q", "origin", "main")
        merge.git(tree, "fetch", "-q", "origin")
        merge.git(tree, "rebase", "-q", "origin/main")
        self.before = commit(tree, "the task in the file", TASK)
        self.base = merge.git(main, "rev-parse", "HEAD")
        if edits:
            self.head = commit(tree, "what the check asked for", edits)
        else:
            merge.git(tree, "commit", "-q", "--allow-empty", "-m", "run the check again")
            self.head = merge.git(tree, "rev-parse", "HEAD")
        merge.git(tree, "push", "-q", "--force", "origin", "alpha")
        proven_merged.home.open_pull_request(self.head, checks=(LATER,), files=list(files))
        self.brief(run.proven("clean", self.before), line)

    def brief(self, review, line, more=""):
        result = line.format(head=self.head, before=self.before) + f"\n{more}"
        (self.proven_merged.home.tasks / "alpha.md").write_text(merge.brief(review, result))

    def ranges(self):
        return f"{self.base}..{self.before} {self.base}..{self.head}"

    def carried(self):
        short = " ".join(ready._short(one) for one in self.ranges().split())
        return f"review carried over: range-diff {short} clean, every line kept"

    def waits(self):
        return (
            f"wait 7 {merge.URL}: the rebase changed the content after its review; "
            f"scoped review of git range-diff --no-color {self.ranges()}"
        )


def test_a_ci_fix_that_changed_no_content_carries_the_review_over_and_is_merged(
    proven_merged, rules
):
    fix = CiFix(proven_merged, {})
    ready_line = f"ready 7 {fix.head} alpha alpha, {fix.carried()}"
    assert run.jmerge(proven_merged, rules, "--check") == [ready_line]
    (said,) = run.jmerge(proven_merged, rules)
    commit_, _ = proven_merged.on_main()
    assert said == merge.merged_line(commit_, fix.carried())


def test_a_ci_fix_that_changed_the_content_waits_for_one_scoped_review(proven_merged, rules):
    fix = CiFix(proven_merged, {15: "what the check asked for"})
    assert run.jmerge(proven_merged, rules) == [fix.waits()]
    assert run.merges(proven_merged) == []
    number, _, ask = asks.content(fix.waits())
    old, new = fix.ranges().split()
    assert (number, ask.kind, ask.head) == (7, "rereview", fix.head)
    assert f"`/pr-review run {{slug}} scoped {old} {new}`" in ask.message
    fix.brief(
        merge.review("clean", fix.before) + run.proven("clean", fix.head),
        "CI fix: {head}, after the review of {before}",
    )
    assert run.jmerge(proven_merged, rules, "--check") == [f"ready 7 {fix.head} alpha alpha"]


@pytest.mark.parametrize(
    "line",
    [
        pytest.param("", id="no line"),
        pytest.param(
            "CI fix: {before}, after the review of {before}", id="a line of an earlier push"
        ),
        pytest.param(
            f"CI fix: {{head}}, after the review of {'d' * 40}",
            id="a line whose review is not the one the brief has",
        ),
        "CI fix: {head}",
    ],
)
def test_a_push_no_review_saw_and_no_line_names_waits_for_a_scoped_review(
    proven_merged, rules, line
):
    """The push is not a rebase, because the head adds a commit to the ones the review saw."""
    fix = CiFix(proven_merged, {15: "what the check asked for"}, line=line)
    assert run.jmerge(proven_merged, rules) == [fix.waits()]
    assert run.merges(proven_merged) == []


def test_a_ci_fix_line_changes_nothing_of_a_fix_the_fixed_line_names(proven_merged, rules):
    fix = CiFix(proven_merged, {15: "what the check asked for"})
    ended = f"Finding: fixed, it is wrong\nFixed: {fix.head}\n"
    fix.brief(
        merge.review("findings", fix.before), "CI fix: {head}, after the review of {before}", ended
    )
    assert run.jmerge(proven_merged, rules, "--check") == [f"ready 7 {fix.head} alpha alpha"]


def test_a_ci_fix_after_a_rebase_is_compared_with_the_head_the_review_saw(proven_merged, rules):
    rebased = Rebased(proven_merged, {28: "theirs 28"})
    tree = proven_merged.tree
    pushed = commit(tree, "what the check asked for", {15: "what the check asked for"})
    merge.git(tree, "push", "-q", "origin", "alpha")
    proven_merged.home.open_pull_request(pushed, checks=(LATER,), files=[FILE])
    line = f"CI fix: {pushed}, after the review of {rebased.before}\n"
    rebased.brief(merge.review("clean", rebased.before), line)
    assert run.jmerge(proven_merged, rules) == [rebased.waits().replace(rebased.head, pushed)]
    line = f"CI fix: {pushed}, after the review of {rebased.head}\n"
    rebased.brief(merge.review("clean", rebased.head), line)
    assert run.jmerge(proven_merged, rules) == [
        f"wait 7 {merge.URL}: the rebase changed the content after its review; scoped review "
        f"of git range-diff --no-color {rebased.tip}..{rebased.head} {rebased.tip}..{pushed}"
    ]


CLEAN = rangediff.Verdict(
    True, "git range-diff", "", f"{'1' * 40}..{'2' * 40}", f"{'3' * 40}..{'4' * 40}"
)


def test_the_note_and_the_wait_are_read_off_the_verdict():
    changed = rangediff.Verdict(False, "git range-diff --no-color a..b c..d", "why")
    assert ready.rebase_note(None) == ready.rebase_note(changed) == ""
    assert ready.rebase_note(CLEAN) == (
        "review carried over: range-diff 111111111111..222222222222 333333333333..444444444444 "
        "clean"
    )
    assert ready.short_on_content(None) == ready.short_on_content(CLEAN) == ""
    assert ready.short_on_content(changed) == (
        "the rebase changed the content after its review; scoped review of "
        "git range-diff --no-color a..b c..d"
    )
