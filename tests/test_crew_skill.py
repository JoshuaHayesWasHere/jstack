import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import textwrap
import time
from datetime import timedelta
from pathlib import Path

import pytest

import jsettings
import test_home_merge as merge
import test_jmerge_guarded as guarded
import test_jmerge_rangediff as rebases
import test_room as room
import test_tool_calls as tools
from jmerge import cli, rangediff, ready
from test_jbus_kitchen import NOW, Kitchen
from test_jmerge_guarded import LISTED

SKILL = Path(__file__).parent.parent / "skills" / "crew" / "SKILL.md"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path / "kitchen", monkeypatch)
    yield made
    made.close()


def sections():
    found, name = {}, None
    for line in SKILL.read_text().splitlines():
        if line.startswith("## "):
            name = line[3:]
            found[name] = []
        elif name:
            found[name].append(line)
    return {name: "\n".join(lines) for name, lines in found.items()}


def block(heading, about):
    """The one `sh` block under a heading that has a word in it, as an agent reads it."""
    (found,) = [text for text in FENCED.findall(sections()[heading]) if about in text]
    return textwrap.dedent(found)


def test_the_skill_it_launches_by_is_found_from_any_repo(tmp_path):
    text = SKILL.read_text()
    (setting,) = [line for line in text.splitlines() if line.startswith("T=")]
    ((path, heading),) = re.findall(r'`(\$T/\S+/SKILL\.md)` "([^"]+)"', text)

    user = tmp_path / "user"
    (user / ".claude" / "skills").mkdir(parents=True)
    (user / ".claude" / "skills" / "crew").symlink_to(SKILL.parent)
    elsewhere = tmp_path / "another-repo"
    elsewhere.mkdir()
    found = subprocess.run(
        ["sh", "-c", f'{setting}\nprintf %s "{path}"'],
        capture_output=True,
        env={**os.environ, "HOME": str(user)},
        cwd=elsewhere,
        check=True,
    )
    assert f"## {heading}" in Path(found.stdout.decode()).read_text().splitlines()


BRIEF = """\
# alpha: a task
Task: "do it"
Decisions:
- A brief that only talks about `Review: none` or a `## Review` section still gets a review.
Pull request: open one when done

## Result
Status: done
Branch: alpha   Pull request: https://example.test/pull/1
"""


def said(tmp_path, heading, about, brief, notes=None, cwd=None):
    """What one of the skill's blocks prints for a brief, and for the repo's notes if any."""
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "alpha.md").write_text(brief)
    if notes is not None:
        (tmp_path / "notes.md").write_text(notes)
    ran = subprocess.run(
        ["sh", "-c", block(heading, about).replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        env={**os.environ, "H": str(tmp_path)},
        cwd=cwd,
        check=True,
    )
    return ran.stdout.splitlines()


def with_field(line):
    """The brief with a `Review:` line of its own, where the home writes it."""
    return BRIEF.replace("\n## Result", f"{line}\n\n## Result")


@pytest.mark.parametrize(
    ("brief", "mode", "launches"),
    [
        (BRIEF, "review", True),
        (with_field("Review: review"), "review", True),
        pytest.param(
            with_field("Review: review+test"),
            "review",
            True,
            id="a word from before the review ran no test step is read as a review",
        ),
        (with_field("Review: none"), "none", False),
        (with_field("Review: something else"), "review", True),
        pytest.param(
            with_field("Review: review") + "Review: none\n",
            "review",
            True,
            id="only the first Review line is the brief's",
        ),
        (with_field("Review: none") + "Review: review\n", "none", False),
        (BRIEF + "Reviewer: mcp:1111-aaaa\n", "review", False),
        (BRIEF + "Reviewer: none, no launch tool in this session\n", "review", False),
        (BRIEF + "\n## Review\nVerdict: clean\n", "review", False),
        (with_field("Review: review+test") + "Reviewer: mcp:1111-aaaa\n", "review", False),
        (
            with_field("Review: none") + "Reviewer: none, the brief says Review: none\n",
            "none",
            False,
        ),
    ],
)
def test_the_check_before_a_launch_prints_the_mode_and_whether_to_launch(
    brief, mode, launches, tmp_path
):
    (line,) = said(tmp_path, "The review", "launch a reviewer", brief)
    printed, what = line.split(": ", 1)
    assert printed == mode
    assert (what == "launch a reviewer") == launches
    assert launches or what.startswith("launch no reviewer, ")


def reviewed(findings, endings=""):
    """The brief once a reviewer wrote its section, and the crewmate its `Finding:` lines."""
    listed = "".join(f"- {finding}\n" for finding in findings) or "none\n"
    review = f"\n## Review\nVerdict: findings\nFindings:\n{listed}Dropped: 0\nSent to: mcp:1\n"
    return BRIEF + endings + review


TWO = ["warning a.py:3 it runs twice", "info b.py the file as a whole"]
FIXED_ONE = "Finding: fixed, it runs twice\n"
ANSWERED_ONE = "Finding: not fixed, the file as a whole, because it is the brief's own shape\n"


@pytest.mark.parametrize(
    ("brief", "says"),
    [
        (BRIEF, "wait: the review is not written in the brief yet"),
        (BRIEF + FIXED_ONE, "wait: the review is not written in the brief yet"),
        (reviewed(TWO), "not yet: 2 of 2 findings have no Finding: line"),
        (reviewed(TWO, FIXED_ONE), "not yet: 1 of 2 findings have no Finding: line"),
        pytest.param(
            reviewed(TWO, FIXED_ONE + "Finding: not fixed, the file as a whole\n"),
            "not yet: 1 of 2 findings have no Finding: line",
            id="not fixed with no reason is no ending",
        ),
        pytest.param(
            reviewed(TWO, FIXED_ONE + "Finding: not fixed, b.py: the file as a whole\n"),
            "not yet: 1 of 2 findings have no Finding: line",
            id="a colon in the finding's own words is not a reason",
        ),
        pytest.param(
            reviewed(["warning a.py:1 one\n  wrapped text", "error a.py:2 two\n", "error a.py:3 x"])
            + FIXED_ONE,
            "not yet: 2 of 3 findings have no Finding: line",
            id="a finding that wraps or follows a blank line is still a finding",
        ),
        pytest.param(
            reviewed(TWO, FIXED_ONE + ANSWERED_ONE) + reviewed(TWO).removeprefix(BRIEF),
            "not yet: 2 of 4 findings have no Finding: line",
            id="a second pass adds findings the first pass's endings do not answer",
        ),
        pytest.param(
            reviewed(TWO[:1], FIXED_ONE + ANSWERED_ONE * 4) + reviewed(TWO * 2).removeprefix(BRIEF),
            "write Fixed: none needed, <reason>: 4 findings of the last review, none fixed",
            id="a later review with every finding declined needs no fix, whatever was fixed before",
        ),
        pytest.param(
            reviewed(TWO[:1], ANSWERED_ONE + FIXED_ONE) + reviewed(TWO[:1]).removeprefix(BRIEF),
            "write Fixed: <the head you pushed>, 2 findings each have their ending",
            id="a fix for a later review is a fix",
        ),
        pytest.param(
            reviewed(TWO[:1], FIXED_ONE) + reviewed([]).removeprefix(BRIEF),
            "write Fixed: <the head you pushed>, 1 findings each have their ending",
            id="a clean later review leaves the fix as it is",
        ),
        pytest.param(
            reviewed(TWO, FIXED_ONE + "Noticed: a `Finding: fixed, x` line would count.\n"),
            "not yet: 1 of 2 findings have no Finding: line",
            id="words about a finding are not its line",
        ),
        (
            reviewed(TWO, FIXED_ONE + ANSWERED_ONE),
            "write Fixed: <the head you pushed>, 2 findings each have their ending",
        ),
        (
            reviewed(TWO[1:], ANSWERED_ONE),
            "write Fixed: none needed, <reason>: 1 findings, none fixed",
        ),
        (reviewed([]), "write Fixed: none needed, <reason>: the review has no findings"),
        (reviewed(["none"]), "write Fixed: none needed, <reason>: the review has no findings"),
        pytest.param(
            reviewed(TWO[:1], FIXED_ONE) + "- a note\n\n## Result, follow-up\n- a note\n",
            "write Fixed: <the head you pushed>, 1 findings each have their ending",
            id="lines after the list and a later Result are not findings",
        ),
    ],
)
def test_every_finding_has_its_ending_before_the_fixed_line_is_written(brief, says, tmp_path):
    assert said(tmp_path, "The review", "Finding:", brief) == [says]


class Fix:
    """A crewmate's worktree at the head a review saw, then at the head its fix pushed."""

    def __init__(
        self,
        tmp_path,
        fix,
        findings=("warning a.py:3 it runs twice",),
        task=("a.py", "b.py"),
        opened=False,
    ):
        self.state = tmp_path / "state"
        self.work = tmp_path / "work"
        (self.state / "tasks").mkdir(parents=True)
        self.work.mkdir()
        git(self.work, "init", "-q", "-b", "a-task")
        self.start = ""
        if opened:
            self.start = self.commit("start")
            git(self.work, "update-ref", "refs/remotes/origin/main", self.start)
            git(self.work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        for name in task:
            (self.work / name).parent.mkdir(parents=True, exist_ok=True)
            (self.work / name).write_text("the task\n")
        self.saw = self.commit("the task")
        for name in fix:
            (self.work / name).parent.mkdir(parents=True, exist_ok=True)
            (self.work / name).write_text("the fix\n")
        self.fixed = self.commit("the fix") if fix else self.saw
        self.findings = findings
        self.review = self.reviewed(self.saw)

    def reviewed(self, head):
        listed = "".join(f"- {finding}\n" for finding in self.findings)
        return (
            f"\n## Review\nVerdict: findings\nHead: {head}   Unchanged by the review: yes\n"
            f"Findings:\n{listed}Dropped: 0\nSent to: mcp:1\n"
        )

    def commit(self, message):
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.work, "rev-parse", "HEAD")

    def listed(self):
        """A copy of jmerge's package whose `guarded.txt` is the list the tests write: the
        shipped one is empty, and the block asks the package it finds first."""
        copy = self.state / "listed"
        if not copy.exists():
            source = SKILL.parents[2] / "src" / "jmerge"
            ignore = shutil.ignore_patterns("__pycache__")
            shutil.copytree(source, copy / "jmerge", ignore=ignore)
            (copy / "jmerge" / "guarded.txt").write_text(LISTED)
        return str(copy)

    def says(self, result, reviews=None, shell="sh", listed=True):
        """What the block prints for a Result's lines and the reviews written after it, over
        the list the tests write, or with `listed` false over the shipped one."""
        brief = BRIEF + result + (self.review if reviews is None else reviews)
        (self.state / "tasks" / "alpha.md").write_text(brief)
        told = {"H": str(self.state), "T": str(SKILL.parents[2] / "templates")}
        env = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"}
        if listed:
            env["PYTHONPATH"] = self.listed()
        ran = subprocess.run(
            [shell, "-c", block("The review", "Second pass:").replace("<slug>", "alpha")],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={**env, **told},
            check=True,
        )
        return ran.stdout.splitlines()


OLD_NONE = "Second pass: none, the fix stayed inside the files the findings named"
TESTS_ONLY = "write Scoped review: none, the fix changed files under tests/ only"
NOTHING_PUSHED = "write Scoped review: none, nothing was pushed for the findings"
NO_REVIEW_OF_IT = "none: no review of the fix, as the Result says"
HAD = "had: the review of the fix is written, and this head is owed none"
LAUNCHED = "scoped: the scoped reviewer is launched, and its findings come to this thread"


def owed(fix, why):
    return f"Scoped review: needed since {fix.saw}, {why}\n"


def launch(fix, saw, head):
    return (
        "scoped: launch the scoped reviewer, with /pr-review run alpha scoped "
        f"{fix.start}..{saw} {fix.start}..{head}"
    )


@pytest.mark.parametrize(
    ("fix", "outside"),
    [
        (["a.py"], "a.py"),
        (["b.py"], "b.py"),
        (["a.py", "tests/c.py", "docs/d.md"], "a.py docs/d.md"),
    ],
    ids=["inside the file a finding named", "in a file no finding named", "beside a test"],
)
def test_a_fix_that_changes_a_file_outside_tests_gets_one_scoped_review_of_it(
    fix, outside, tmp_path
):
    fix = Fix(tmp_path, fix, opened=True)
    needed = owed(fix, f"the fix changed {outside}")
    assert fix.says("") == [f"write {needed.strip()}"]
    assert fix.says(needed + f"Fixed: {fix.fixed}\n") == [launch(fix, fix.saw, fix.fixed)]


@pytest.mark.parametrize("finding", ["warning a.py:3 it runs twice", "warning - it has no test"])
def test_a_fix_that_changes_tests_only_gets_no_review(finding, tmp_path):
    fix = Fix(tmp_path, ["tests/c.py", "tests/unit/d.py"], [finding], opened=True)
    assert fix.says("") == [TESTS_ONLY]
    assert fix.says(TESTS_ONLY.removeprefix("write ") + "\n") == [NO_REVIEW_OF_IT]


def test_a_fix_that_declines_every_finding_gets_no_review(tmp_path):
    fix = Fix(tmp_path, [], opened=True)
    assert fix.says("") == [NOTHING_PUSHED]
    assert fix.says(NOTHING_PUSHED.removeprefix("write ") + "\n") == [NO_REVIEW_OF_IT]


def test_a_file_whose_name_only_starts_like_tests_is_outside_it_and_five_are_named(tmp_path):
    fix = Fix(tmp_path, ["tests.py", "tests/c.py"])
    assert fix.says("") == [f"write {owed(fix, 'the fix changed tests.py').strip()}"]
    many = Fix(tmp_path / "many", [f"src/{n}.py" for n in range(7)])
    named = " ".join(f"src/{n}.py" for n in range(5))
    assert many.says("") == [f"write {owed(many, f'the fix changed {named} and 2 more').strip()}"]


@pytest.mark.parametrize("saw", ["c" * 40, None])
def test_a_fix_that_cannot_be_compared_gets_a_scoped_review(saw, tmp_path):
    fix = Fix(tmp_path, ["a.py"], opened=True)
    review = fix.reviewed(saw) if saw else fix.review.replace("Head: ", "Run: ")
    needed = (
        f"Scoped review: needed since {saw or '-'}, the fix could not be compared with that head"
    )
    assert fix.says("", review) == [f"write {needed}"]
    assert fix.says(needed + "\n", review) == [
        f"scoped: the head the review saw, {saw or '-'}, is not a commit here, "
        "so its range cannot be given"
    ]


def test_a_worktree_that_does_not_know_its_default_branch_gives_no_range(tmp_path):
    fix = Fix(tmp_path, ["a.py"])
    assert fix.says(owed(fix, "the fix changed a.py")) == [
        "scoped: this worktree does not know its default branch, "
        "so the range of the fix cannot be given"
    ]


def test_before_the_review_there_is_nothing_to_decide(tmp_path):
    fix = Fix(tmp_path, ["a.py", "b.py"])
    assert fix.says("", reviews="") == ["wait: no review is written in the brief yet"]


def test_the_line_is_worked_out_before_the_fixed_line_is_written(tmp_path):
    fix = Fix(tmp_path, ["a.py", "b.py"])
    needed = [f"write {owed(fix, 'the fix changed a.py b.py').strip()}"]
    assert fix.says("") == needed
    assert fix.says(f"Fixed: {fix.fixed}\n") == needed


def test_what_was_decided_is_read_from_the_result_and_not_worked_out_again(tmp_path):
    fix = Fix(tmp_path, ["a.py", "b.py"])
    decided = "Second pass: none, the fix stayed inside\n"
    assert fix.says(decided) == ["none: no second pass, as the Result says"]


def test_a_second_pass_is_launched_once_and_is_the_last(tmp_path):
    fix = Fix(tmp_path, ["a.py", "b.py"])
    needed = f"Second pass: needed since {fix.saw}, the fix also changed b.py\n"
    assert fix.says(needed) == ["needed: launch the second reviewer"]
    launched = needed + "Second reviewer: mcp:2222-bbbb\n"
    waiting = ["needed: the second reviewer is launched, and its findings come to this thread"]
    assert fix.says(launched) == waiting
    assert fix.says(launched, fix.review + fix.review) == waiting
    not_run = fix.review + fix.reviewed(fix.fixed).replace("Verdict: findings", "Verdict: not run")
    assert fix.says(launched, not_run) == waiting
    second = fix.review + fix.reviewed(fix.fixed)
    had = ["had: the second pass is written, and it is the last"]
    assert fix.says(launched, second) == had
    (fix.work / "d.py").write_text("wider still\n")
    fix.commit("the second fix")
    assert fix.says(launched, second) == had


def test_a_fix_after_two_reviews_is_decided_by_what_it_changed_too(tmp_path):
    fix = Fix(tmp_path, ["a.py", "b.py"])
    assert fix.says("", fix.review + fix.review) == [
        f"write {owed(fix, 'the fix changed a.py b.py').strip()}"
    ]
    tests = Fix(tmp_path / "tests", ["tests/c.py"])
    assert tests.says("", tests.review + tests.review) == [TESTS_ONLY]


@pytest.mark.parametrize(
    "path", ["docs/a.md", "skills/crew/SKILL.md"], ids=["not guarded", "guarded"]
)
def test_the_review_of_a_fix_is_the_last_but_for_a_guarded_pull_request(path, tmp_path):
    fix = opened(tmp_path, path)
    needed = owed(fix, f"the fix changed {path}")
    assert fix.says("") == [f"write {needed.strip()}"]
    result = needed + f"Fixed: {fix.fixed}\n"
    launched = result + f"Scoped reviewer: mcp:3333-cccc, of {fix.fixed}\n"
    assert fix.says(launched) == [LAUNCHED]
    not_run = fix.review + fix.reviewed(fix.fixed).replace("Verdict: findings", "Verdict: not run")
    assert fix.says(launched, not_run) == [LAUNCHED]
    written = fix.review + fix.reviewed(fix.fixed)
    assert fix.says(launched, written) == [HAD]
    (fix.work / "d.py").write_text("for the scoped review's findings\n")
    again = fix.commit("the second fix")
    if path == "docs/a.md":
        assert fix.says(launched, written) == [HAD]
        return
    second = f"Scoped review: needed since {fix.fixed}, guarded\n"
    assert fix.says(launched, written) == [f"write {second.strip()}"]
    assert fix.says(launched + second, written) == [launch(fix, fix.fixed, again)]
    proved = written + fix.reviewed(again)
    assert fix.says(launched + second + f"Scoped reviewer: mcp:4, of {again}\n", proved) == [HAD]


def test_a_fix_under_tests_gets_its_scoped_review_on_a_guarded_pull_request(tmp_path):
    fix = opened(tmp_path, "skills/crew/SKILL.md", fix=["tests/c.py"])
    assert fix.says("") == [f"write {owed(fix, 'guarded').strip()}"]
    assert fix.says("", listed=False) == [TESTS_ONLY]


def test_the_launch_of_a_fix_s_review_asks_github_nothing_so_it_waits_for_no_green_check(tmp_path):
    fix = opened(tmp_path, "docs/a.md")
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "gh").write_text(f"#!/bin/sh\necho asked >> {stub}/calls\nexit 1\n")
    (stub / "gh").chmod(0o755)
    brief = BRIEF + owed(fix, "the fix changed docs/a.md") + fix.review
    (fix.state / "tasks" / "alpha.md").write_text(brief)
    path = f"{stub}{os.pathsep}{os.environ['PATH']}"
    ran = subprocess.run(
        ["sh", "-c", block("The review", "Second pass:").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        cwd=fix.work,
        env={**os.environ, "H": str(fix.state), "PATH": path},
        check=True,
    )
    assert ran.stdout.splitlines() == [launch(fix, fix.saw, fix.fixed)]
    assert not (stub / "calls").exists()


def opened(tmp_path, path, fix=None):
    """A pull request that changes `path` and b.py, with one finding in `path`, and a fix."""
    fix = [path] if fix is None else fix
    return Fix(tmp_path, fix, [f"warning {path}:3 it"], (path, "b.py"), opened=True)


INFO = ["info a.py:9 a name could say more", "info b.py:1 a comment says the code again"]
NONE_FIXED = "write Fixed: none needed, <reason>: 2 findings, none fixed"
ALL_INFO = "Fixed: none needed, every finding is info and left for a follow-up\n"


def declined(findings=INFO):
    """The `Finding:` lines of info findings a crewmate declines, in the skill's own words."""
    found = re.findall(r"`(Finding: not fixed, <[^>]+>, because info: [^`]+)`", SKILL.read_text())
    (shape,) = set(found)
    words = [finding.split(" ", 2)[2] for finding in findings]
    return "".join(re.sub("<[^>]+>", said, shape) + "\n" for said in words)


def test_a_review_of_info_findings_all_declined_pushes_nothing_and_is_handled(tmp_path):
    fix = Fix(tmp_path, [], INFO)
    brief = merge.brief(fix.review, declined())
    assert said(fix.state, "The review", "Finding:", brief) == [NONE_FIXED]
    assert said(fix.state, "The review", "Second pass:", brief, cwd=fix.work) == [NOTHING_PUSHED]
    home = merge.Home(tmp_path)
    handled = f"{NOTHING_PUSHED.removeprefix('write ')}\n{ALL_INFO}"
    (home.tasks / "alpha.md").write_text(merge.brief(fix.review, declined() + handled))
    home.open_pull_request(fix.saw)
    assert home.ready() == [f"ready 7 {fix.saw} alpha alpha"]


def test_a_warning_fixed_beside_info_findings_declined_gets_the_review_of_its_fix(tmp_path):
    fix = Fix(tmp_path, ["a.py"], ["warning a.py:3 it runs twice", *INFO])
    brief = merge.brief(fix.review, FIXED_ONE + declined())
    assert said(fix.state, "The review", "Finding:", brief) == [
        "write Fixed: <the head you pushed>, 3 findings each have their ending"
    ]
    assert said(fix.state, "The review", "Second pass:", brief, cwd=fix.work) == [
        f"write {owed(fix, 'the fix changed a.py').strip()}"
    ]


def test_a_scoped_review_of_info_findings_all_declined_is_handled_at_the_rebased_head(
    proven_merged, rules
):
    rebased = rebases.Rebased(proven_merged, {11: "theirs 11"}, rebases.BOTH)
    listed = "".join(f"- {finding}\n" for finding in INFO)
    section = guarded.proven("findings", rebased.head).replace(
        "Verdict: findings\n", f"Verdict: findings\nScope: range-diff {rebased.command()[26:]}\n"
    )
    section = re.sub(r"(?m)^- .*\n", listed, section)
    reviews = guarded.proven("clean", rebased.before) + section
    rebased.brief(reviews, declined())
    state, brief = proven_merged.home.state, (proven_merged.home.tasks / "alpha.md").read_text()
    assert said(state, "The review", "Finding:", brief) == [NONE_FIXED]
    assert said(state, "The review", "Second pass:", brief, cwd=proven_merged.tree) == [
        NOTHING_PUSHED
    ]
    rebased.brief(reviews, declined() + ALL_INFO)
    assert guarded.jmerge(proven_merged, rules, "--check") == [
        f"ready 7 {rebased.head} alpha alpha"
    ]


GUARDED = "skills/crew/SKILL.md"


SHELLS = [
    "sh",
    pytest.param("zsh", marks=pytest.mark.skipif(not shutil.which("zsh"), reason="no zsh")),
]


@pytest.mark.parametrize("shell", SHELLS)
def test_a_fix_to_a_guarded_pull_request_gets_a_scoped_review_however_narrow_it_is(shell, tmp_path):
    fix = opened(tmp_path, GUARDED)
    needed = f"Scoped review: needed since {fix.saw}, guarded"
    assert fix.says("", shell=shell) == [f"write {owed(fix, f'the fix changed {GUARDED}').strip()}"]
    decided = f"{OLD_NONE}\n{needed}\n"
    launch = (
        "scoped: launch the scoped reviewer, with /pr-review run alpha scoped "
        f"{fix.start}..{fix.saw} {fix.start}..{fix.fixed}"
    )
    assert fix.says(decided, shell=shell) == [launch]
    launched = decided + f"Scoped reviewer: mcp:3333-cccc, of {fix.fixed}\n"
    assert fix.says(launched, shell=shell) == [LAUNCHED]
    for other in ("Scoped reviewer: mcp:3\n", f"Scoped reviewer: mcp:3, of {fix.saw}\n"):
        assert fix.says(decided + other, shell=shell) == [launch]
        assert fix.says(decided + other + launched, shell=shell) == [LAUNCHED]
    none = f"Scoped reviewer: none, no launch tool in this session, of {fix.fixed}\n"
    assert fix.says(decided + none, shell=shell) == [
        "scoped: no scoped reviewer could be launched for this head, and the home was told"
    ]
    stopped = decided + f"Scoped reviewer: mcp:3, of {'d' * 40}\n"
    assert fix.says(stopped, shell=shell) == [
        launch.replace(", with", f" in place of the one that stopped at {'d' * 40}, with")
    ]
    proven = fix.review + fix.reviewed(fix.fixed)
    assert fix.says(launched, proven) == ["none: no second pass, as the Result says"]
    (fix.work / GUARDED).write_text("the second fix\n")
    again = fix.commit("the second fix")
    assert fix.says(launched, proven) == [f"write Scoped review: needed since {fix.fixed}, guarded"]
    assert fix.says(launched + f"Scoped review: needed since {fix.fixed}, guarded\n", proven) == [
        "scoped: launch the scoped reviewer, with /pr-review run alpha scoped "
        f"{fix.start}..{fix.fixed} {fix.start}..{again}"
    ]


def test_a_fix_to_a_guarded_pull_request_after_two_passes_gets_a_scoped_review(tmp_path):
    fix = opened(tmp_path, GUARDED, fix=["tests/c.py"])
    scoped = f"write Scoped review: needed since {fix.saw}, guarded"
    assert fix.says("", fix.review + fix.review) == [scoped]
    wide = opened(tmp_path / "wide", GUARDED, fix=[GUARDED, "b.py", "c.py"])
    needed = f"Second pass: needed since {wide.saw}, the fix also changed c.py\n"
    second = wide.review + wide.reviewed(wide.fixed)
    had = ["had: the second pass is written, and it is the last"]
    assert wide.says(needed + "Second reviewer: mcp:2222-bbbb\n", second) == had
    (wide.work / "d.py").write_text("for the second pass\n")
    wide.commit("the second fix")
    assert wide.says(needed + "Second reviewer: mcp:2222-bbbb\n", second) == [
        f"write Scoped review: needed since {wide.fixed}, guarded"
    ]


def test_a_guarded_check_that_did_not_run_is_said_and_a_file_moved_away_is_guarded(tmp_path):
    fix = opened(tmp_path, "docs/a.md", fix=["tests/c.py"])
    (fix.state / "tasks" / "alpha.md").write_text(BRIEF + fix.review)
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "uv").write_text("#!/bin/sh\nexit 2\n")
    (stub / "uv").chmod(0o755)
    path = f"{stub}{os.pathsep}{os.environ['PATH']}"
    ran = subprocess.run(
        ["sh", "-c", block("The review", "Second pass:").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        cwd=fix.work,
        env={**os.environ, "H": str(fix.state), "PATH": path},
        check=True,
    )
    assert ran.stdout.splitlines() == [
        "scoped: jmerge could not be asked whether this pull request changes a guarded path",
    ]
    moved = Fix(tmp_path / "moved", [], ["warning docs/a.md:3 it"], ("docs/a.md",), opened=True)
    git(moved.work, "update-ref", "refs/remotes/origin/main", moved.saw)
    git(moved.work, "mv", "docs/a.md", "docs/b.md")
    moved.commit("moved away")
    assert moved.says("Second pass: none, it stayed inside\n") == [
        "none: no second pass, as the Result says"
    ]
    (moved.work / GUARDED).parent.mkdir(parents=True)
    git(moved.work, "mv", "docs/b.md", GUARDED)
    start = moved.commit("into a guarded path")
    git(moved.work, "update-ref", "refs/remotes/origin/main", start)
    git(moved.work, "mv", GUARDED, "docs/c.md")
    moved.commit("and away again")
    assert moved.says("Second pass: none, it stayed inside\n") == [
        f"write Scoped review: needed since {moved.saw}, guarded"
    ]


def test_a_fix_to_a_pull_request_that_is_not_guarded_keeps_the_rule_it_had(tmp_path):
    fix = opened(tmp_path, "docs/a.md")
    assert fix.says("") == [f"write {owed(fix, 'the fix changed docs/a.md').strip()}"]
    assert fix.says("", fix.review + fix.review) == [
        f"write {owed(fix, 'the fix changed docs/a.md').strip()}"
    ]
    assert fix.says("Second pass: none, the fix stayed inside\n") == [
        "none: no second pass, as the Result says"
    ]


def test_the_shipped_list_guards_no_path_so_a_fix_to_a_skill_is_asked_no_scoped_review(tmp_path):
    fix = opened(tmp_path, GUARDED, fix=["tests/c.py"])
    assert fix.says("", listed=False) == [TESTS_ONLY]
    assert fix.says("Second pass: none, the fix stayed inside\n", listed=False) == [
        "none: no second pass, as the Result says"
    ]
    assert fix.says("Second pass: none, the fix stayed inside\n") == [
        f"write Scoped review: needed since {fix.saw}, guarded"
    ]


@pytest.mark.parametrize(
    ("moved", "after_a_fix"),
    [
        ("CI fix: {fixed}, after the review of {saw}\n", False),
        ("Rebase: patch unchanged, before {saw}, head {fixed}\n", False),
        ("Rebase: patch changed in a.py, before {saw}, head {fixed}\n", True),
    ],
    ids=["a push for a failed check", "a rebase", "a rebase that changed the patch"],
)
def test_a_head_jmerge_compares_by_range_diff_is_asked_no_scoped_review_here(
    moved, after_a_fix, tmp_path
):
    fix = opened(tmp_path, GUARDED)
    none = ["none: no second pass, as the Result says"]
    scoped = [f"write Scoped review: needed since {fix.saw}, guarded"]
    result = "Second pass: none, nothing was pushed\n" + moved.format(fixed=fix.fixed, saw=fix.saw)
    assert fix.says(result) == none
    for fixed in (f"Fixed: {fix.fixed}\n{result}", f"{result}Fixed: {fix.fixed}\n"):
        assert fix.says(fixed) == (none if after_a_fix else scoped)
    assert fix.says("Second pass: none, nothing was pushed\n") == scoped


def test_a_rebase_jmerge_compares_with_the_reviewed_head_is_asked_no_scoped_review(tmp_path):
    fix = opened(tmp_path, GUARDED)
    none = ["none: no second pass, as the Result says"]
    other = "d" * 40
    again = f"Rebase: patch changed in a.py, before {other}, head {fix.fixed}\n"
    clean = "Second pass: none, nothing was pushed\nFixed: none needed, a clean review\n"
    assert fix.says(clean + again) == none
    checked = (
        f"Second pass: none, nothing was pushed\nCI fix: {other}, after the review of {fix.saw}\n"
    )
    assert fix.says(checked + again) == none
    not_run = fix.review + fix.reviewed(other).replace("Verdict: findings", "Verdict: not run")
    assert fix.says(f"{clean}Fixed: {fix.fixed}\n{again}", not_run) == [
        f"write Scoped review: needed since {fix.saw}, guarded"
    ]


def test_a_rebase_of_a_fix_no_review_proved_is_asked_for_here(tmp_path):
    fix = opened(tmp_path, GUARDED)
    (fix.work / GUARDED).write_text("the fix, rebased\n")
    rebased = fix.commit("the rebase")
    result = (
        f"Second pass: none, it stayed inside\nFixed: {rebased}\n"
        f"Rebase: patch changed in {GUARDED}, before {fix.fixed}, head {rebased}\n"
    )
    assert fix.says(result) == [f"write Scoped review: needed since {fix.saw}, guarded"]
    proved = fix.review + fix.reviewed(fix.fixed)
    assert fix.says(result, proved) == ["none: no second pass, as the Result says"]


@pytest.mark.parametrize("endings", ["", FIXED_ONE + ANSWERED_ONE])
def test_the_lines_that_end_a_finding_change_nothing_the_other_blocks_read(endings, tmp_path):
    brief = with_field("Review: review") + endings
    assert said(tmp_path, "The review", "launch a reviewer", brief) == ["review: launch a reviewer"]
    ran = subprocess.run(
        ["sh", "-c", block("End", "tell the home").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        env={**os.environ, "H": str(tmp_path)},
        check=True,
    )
    assert ran.stdout.splitlines() == [
        "send nothing: https://example.test/pull/1 is open, "
        "and a home that merges hears of it once, when its checks have passed"
    ]


def checked(tmp_path, command, limit=60, heading="Do the task", then=None):
    """The check block of "Do the task" run once in a worktree of its own, as an agent runs
    it, waiting `limit` seconds at most: what it printed, its exit code and how long it took.
    `then` is called once the block has printed its first line, while it still waits."""
    repo, home, stub = tmp_path / "repo", tmp_path / "home", tmp_path / "stub"
    if not repo.exists():
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "file").write_text("one\n")
        stub.mkdir()
        room.uv(stub)
    script = block(heading, "<check command>").replace("<check command>", command)
    script = script.replace("limit=540", f"limit={limit}")
    began = time.monotonic()
    ran = subprocess.Popen(
        ["sh", "-c", script],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env={
            **os.environ,
            "HOME": str(home),
            "PATH": f"{stub}:{room.BIN}:{os.environ['PATH']}",
            "T": str(SKILL.parent.parent.parent / "templates"),
        },
    )
    first = ran.stdout.readline()
    if then:
        then()
    rest, _ = ran.communicate()
    return (first + rest).splitlines(), ran.returncode, time.monotonic() - began


def test_the_full_run_of_the_check_command_holds_a_test_slot_and_ends_with_its_exit_code(
    tmp_path,
):
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    held = f"! flock -n {locks}/test-slot.1.lock true && echo held; exit 3"
    said, code, _ = checked(tmp_path, held)
    assert (said[0].split(":")[0], said[-2:], code) == (
        "started",
        ["held", "done: the check exited 3"],
        3,
    )
    assert [path.name for path in locks.iterdir()] == ["test-slot.1.lock"]


def ended(tmp_path):
    """Wait, as a turn between two calls would, for the check to end with nobody calling."""
    found = tmp_path / "repo" / ".git" / "crew-check" / "exit"
    for _ in range(600):
        if found.exists():
            return
        time.sleep(0.1)
    raise AssertionError("the check did not end")


def test_the_check_is_waited_on_in_the_turn_and_never_started_twice(tmp_path):
    """A check longer than one call: each call waits its whole limit and says to call again,
    a second call joins the check the first started, and the last one has its exit code."""
    runs, go = tmp_path / "runs", tmp_path / "go"
    command = f"echo ran >> {runs}; while ! [ -f {go} ]; do sleep 0.1; done; echo all passed"

    said, code, took = checked(tmp_path, command, limit=1)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("started", "running", 0)
    assert "never end your turn while it runs" in said[-1]
    assert took >= 1

    said, code, took = checked(tmp_path, command, limit=1)
    assert (said[0].split(":")[0], said[-1].split(":")[0]) == ("joined", "running")
    assert took >= 1

    go.touch()
    said, code, took = checked(tmp_path, command, limit=30)
    assert (said[-2:], code) == (["all passed", "done: the check exited 0"], 0)
    assert took < 30
    assert runs.read_text() == "ran\n"


def test_a_check_that_ended_between_calls_is_told_once_and_then_runs_afresh(tmp_path):
    """The answer of a check that ended with no call waiting is given once: a failure that
    was a flake is run again by calling again, with nothing in the worktree changed."""
    runs = tmp_path / "runs"
    command = f"echo ran >> {runs}; sleep 1; [ $(wc -l < {runs}) -gt 1 ]"

    said, code, _ = checked(tmp_path, command, limit=0)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("started", "running", 0)
    ended(tmp_path)

    said, code, _ = checked(tmp_path, command)
    assert (said[0].split(":")[0], said[-1], code) == ("checked", "done: the check exited 1", 1)
    assert runs.read_text() == "ran\n"

    said, code, _ = checked(tmp_path, command)
    assert (said[0].split(":")[0], said[-1], code) == ("started", "done: the check exited 0", 0)
    assert runs.read_text() == "ran\nran\n"


def test_a_check_of_files_that_changed_while_it_ran_is_no_proof_and_runs_again(tmp_path):
    runs, go = tmp_path / "runs", tmp_path / "go"
    command = f"echo ran >> {runs}; while ! [ -f {go} ]; do sleep 0.1; done"

    said, code, _ = checked(tmp_path, command, limit=0)
    assert said[-1].split(":")[0] == "running"
    (tmp_path / "repo" / "file").write_text("two\n")

    said, code, _ = checked(tmp_path, command, then=go.touch)
    assert (said[0].split(":")[0], said[-1].split(":")[0], code) == ("joined", "stale", 75)
    assert "done" not in [line.split(":")[0] for line in said]

    said, code, _ = checked(tmp_path, command)
    assert (said[0].split(":")[0], said[-1], code) == ("started", "done: the check exited 0", 0)
    assert runs.read_text() == "ran\nran\n"


def test_no_block_of_do_the_task_asks_whose_the_full_run_is():
    """The full run is the crewmate's: the block that read the brief and the notes has gone."""
    blocks = FENCED.findall(sections()["Do the task"])
    assert [text for text in blocks if "full run" in text.lower() or "Review:" in text] == []
    assert len([text for text in blocks if "jgauge test-slot -- " in text]) == 1
    assert len([text for text in blocks if "jgauge test-slot --short --" in text]) == 1


def test_a_targeted_run_takes_the_short_lane_and_never_waits_on_a_full_suite(tmp_path):
    home, stub = tmp_path / "home", tmp_path / "stub"
    stub.mkdir()
    room.uv(stub)
    locks = home / ".local" / "state" / "locks"
    locks.mkdir(parents=True)
    held = []
    for n in (1, 2):
        fd = os.open(locks / f"test-slot.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        held.append(fd)
    took = f"! flock -n {locks}/test-slot-short.1.lock true && echo short; exit 3"
    script = block("Do the task", "test-slot --short").replace(
        "<the targeted tests>", f"sh -c '{took}'"
    )
    try:
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
            env={
                **os.environ,
                "HOME": str(home),
                "PATH": f"{stub}:{room.BIN}:{os.environ['PATH']}",
                "T": str(SKILL.parent.parent.parent / "templates"),
            },
        )
    finally:
        for fd in held:
            os.close(fd)
    assert (ran.returncode, ran.stdout, ran.stderr) == (3, "short\n", "")


def test_a_failed_check_on_the_pull_request_runs_the_check_block_it_names(tmp_path):
    """The `failed` answer of "The checks" names the section whose block runs the check
    command: that block holds a test slot and ends with the command's exit code."""
    (answer,) = [
        line
        for line in sections()["Stay on the pull request"].splitlines()
        if line.startswith("- `failed`: a check ran and failed.")
    ]
    (named,) = re.findall(r'the block of "([^"]+)" that runs it', answer)
    locks = tmp_path / "home" / ".local" / "state" / "locks"
    held = f"! flock -n {locks}/test-slot.1.lock true && echo held; exit 3"
    said, code, _ = checked(tmp_path, held, heading=named)
    assert (said[-2:], code) == (["held", "done: the check exited 3"], 3)


GH = """\
#!/bin/sh
case "$1 $2" in
    "pr view") cat "$STUB/view.json" 2> /dev/null ;;
    "run rerun")
        echo "$*" >> "$STUB/calls"
        [ ! -e "$STUB/no-rerun" ] ;;
    "api repos/someone/repo/actions/jobs/"*)
        cat "$STUB/job-${2##*/}.json" 2> /dev/null && exit
        echo '{"message":"Not Found","status":"404"}'
        exit 1 ;;
    *) exit 64 ;;
esac
"""


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    ran = subprocess.run(
        ["git", *identity, *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return ran.stdout.strip()


class PullRequest:
    """A crewmate's worktree with its branch pushed, and a default branch that has moved since."""

    def __init__(self, tmp_path, mergeable, main_edits):
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "gh").write_text(GH)
        (self.stub / "gh").chmod(0o755)
        if mergeable:
            view = f'{{"baseRefName": "main", "mergeable": "{mergeable}"}}'
            (self.stub / "view.json").write_text(view)

        origin, other, main = tmp_path / "origin.git", tmp_path / "other", tmp_path / "main"
        self.work = tmp_path / "trees" / "a-task"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(other))
        self.commit(other, "shared.txt", "one\n", "start")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(tmp_path, "clone", "-q", str(origin), str(main))
        git(main, "worktree", "add", "-q", "-b", "a-task", str(self.work))
        self.git_dir = Path(git(self.work, "rev-parse", "--absolute-git-dir"))
        self.commit(self.work, "shared.txt", "one\nthe task\n", "the task")
        git(self.work, "push", "-q", "-u", "origin", "a-task")
        self.commit(other, main_edits, "theirs\n", "theirs")
        git(other, "push", "-q", "origin", "HEAD:main")
        self.landed = git(other, "rev-parse", "HEAD")

    @staticmethod
    def commit(repo, name, text, message):
        (repo / name).write_text(text)
        git(repo, "add", name)
        git(repo, "commit", "-q", "-m", message)

    def head(self):
        return git(self.work, "rev-parse", "HEAD")

    def rebasing(self):
        states = ("rebase-merge", "rebase-apply")
        return any((self.git_dir / name).exists() for name in states)

    def run(self, about, home=None):
        script = block("Stay on the pull request", about)
        if home:
            script = script.replace("<slug>", "alpha")
        return subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.com",
                "GIT_EDITOR": "true",
                **({"H": str(home)} if home else {}),
            },
        ).stdout


ANSWERS = [
    ("MERGEABLE", "no conflict: no rebase"),
    ("UNKNOWN", "GitHub has not decided yet: no rebase"),
    (None, "could not ask GitHub: no rebase"),
]


@pytest.mark.parametrize(("mergeable", "says"), ANSWERS)
@pytest.mark.parametrize("main_edits", ["other.txt", "shared.txt"])
def test_a_default_branch_that_moved_is_not_rebased_onto(mergeable, says, main_edits, tmp_path):
    pr = PullRequest(tmp_path, mergeable, main_edits)
    before = pr.head()
    assert pr.run("mergeable").splitlines() == [says]
    assert pr.head() == before
    assert not pr.rebasing()
    assert not (pr.git_dir / "crew-before-rebase").exists()


def in_the_template(line):
    """Whether a line a block printed is the template's line of that label, with each of the
    template's `<...>` filled in and its note of when the line is there left off."""
    template = (SKILL.parent.parent.parent / "templates" / "result.md").read_text()
    (written,) = [text for text in template.splitlines() if text.split()[0] == line.split()[0]]
    shape, holes = written.split("   <")[0], 1
    while holes:
        shape, holes = re.subn(r"<[^<>]*>", "\0", shape)
    return bool(re.fullmatch(re.escape(shape).replace("\0", ".+"), line))


def test_a_rebase_that_cannot_start_is_not_reported_as_one(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    before = pr.head()
    git(pr.work, "config", "rebase.autoStash", "false")
    (pr.work / "shared.txt").write_text("an edit not committed\n")
    said = pr.run("mergeable")
    assert said.splitlines()[0] == "the rebase did not start: no rebase"
    assert "unstaged changes" in said
    assert pr.head() == before
    assert not pr.rebasing()
    assert not (pr.git_dir / "crew-before-rebase").exists()


def test_an_origin_that_cannot_be_reached_is_not_reported_as_a_rebase(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    before = pr.head()
    git(pr.work, "remote", "set-url", "origin", str(tmp_path / "gone.git"))
    assert pr.run("mergeable").splitlines() == ["could not fetch origin/main: no rebase"]
    assert pr.head() == before
    assert not (pr.git_dir / "crew-before-rebase").exists()


def test_a_conflict_that_rebases_cleanly_leaves_a_record_of_the_head_before_it(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    before = pr.head()
    pr.run("mergeable")
    assert pr.head() != before
    assert not pr.rebasing()
    assert git(pr.work, "rev-parse", "HEAD~1") == pr.landed
    assert (pr.git_dir / "crew-before-rebase").read_text().split() == [before, "main"]


def test_a_conflict_that_does_not_resolve_is_reported_and_then_its_changes_are(tmp_path):
    pr = PullRequest(tmp_path, "CONFLICTING", "shared.txt")
    before = pr.head()
    said = pr.run("mergeable")
    assert pr.rebasing()
    assert "shared.txt" in said.splitlines()
    assert "git rebase --continue" in said
    record = (pr.git_dir / "crew-before-rebase").read_text()
    again = pr.run("mergeable")
    assert "not finished" in again
    assert "shared.txt" in again.splitlines()
    assert (pr.git_dir / "crew-before-rebase").read_text() == record
    assert record.split() == [before, "main"]

    (pr.work / "shared.txt").write_text("theirs\nthe task\n")
    git(pr.work, "add", "shared.txt")
    git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    assert not pr.rebasing()
    assert git(pr.work, "rev-parse", "HEAD~1") == pr.landed
    assert (pr.git_dir / "crew-before-rebase").read_text() == record


def test_a_conflict_is_rebased_while_a_second_pass_is_still_needed(tmp_path):
    """Nothing refuses a rebased head, so neither waits: the second pass reviews what it gets."""
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    saw = pr.head()
    pr.commit(pr.work, "wider.txt", "the fix\n", "the fix")
    git(pr.work, "push", "-q", "origin", "a-task")
    state = tmp_path / "state"
    (state / "tasks").mkdir(parents=True)

    def review(head):
        found = "Findings:\n- warning shared.txt:2 it runs twice\nDropped: 0\n"
        return f"\n## Review\nVerdict: findings\nHead: {head}\n{found}"

    def second_pass(result, reviews):
        (state / "tasks" / "alpha.md").write_text(BRIEF + result + reviews)
        ran = subprocess.run(
            ["sh", "-c", block("The review", "Second pass:").replace("<slug>", "alpha")],
            capture_output=True,
            text=True,
            cwd=pr.work,
            env={**os.environ, "H": str(state)},
            check=True,
        )
        return ran.stdout.splitlines()

    owed = f"Scoped review: needed since {saw}, the fix changed wider.txt\n"
    assert second_pass("", review(saw)) == [f"write {owed.strip()}"]
    (asked,) = second_pass(owed, review(saw))
    assert asked.startswith("scoped: launch the scoped reviewer, with ")
    assert f"..{saw} " in asked and asked.endswith(f"..{pr.head()}")
    needed = f"Second pass: needed since {saw}, the fix also changed wider.txt\n"
    launch = ["needed: launch the second reviewer"]
    assert second_pass(needed, review(saw)) == launch
    fixed = pr.head()
    assert pr.run("mergeable").splitlines() == ["rebased onto origin/main"]
    assert pr.head() != fixed
    assert git(pr.work, "rev-parse", "HEAD~2") == pr.landed
    assert second_pass(needed, review(saw)) == launch
    (asked,) = second_pass(owed, review(saw))
    assert asked.endswith(f"..{saw} {pr.landed}..{pr.head()}")
    assert second_pass(owed, review(saw) + review(pr.head())) == [HAD]
    launched = needed + "Second reviewer: mcp:2222-bbbb\n"
    assert second_pass(launched, review(saw) + review(pr.head())) == [
        "had: the second pass is written, and it is the last"
    ]


def test_a_third_rebase_after_the_fixed_line_is_held_and_jmerge_waits_on_it(tmp_path):
    """Upstream's cap: past merge prep, trunk forcing a third rebase is held and reported.
    The block counts the rebases it made after the `Fixed:` line, writes the stop line in
    place of the third, and `jmerge` reads that line for the head it holds."""
    pr = PullRequest(tmp_path, "CONFLICTING", "other.txt")
    home = tmp_path / "home"
    (home / "tasks").mkdir(parents=True)
    brief = home / "tasks" / "alpha.md"
    brief.write_text(BRIEF)
    other = tmp_path / "other"

    def main_moves(name):
        pr.commit(other, name, "theirs\n", f"main changes {name}")
        git(other, "push", "-q", "origin", "HEAD:main")
        return git(other, "rev-parse", "HEAD")

    assert pr.run("mergeable", home).splitlines() == ["rebased onto origin/main"]
    assert "Rebased after fixed:" not in brief.read_text()
    brief.write_text(brief.read_text() + f"Fixed: {pr.head()}\n")

    for name in ("second.txt", "third.txt"):
        before, tip = pr.head(), main_moves(name)
        assert pr.run("mergeable", home).splitlines() == ["rebased onto origin/main"]
        assert git(pr.work, "rev-parse", "HEAD~1") == tip
        assert f"Rebased after fixed: {before} onto origin/main at {tip}\n" in brief.read_text()
    assert ready.rebase_held(brief.read_text(), pr.head()) == ""

    held, tip = pr.head(), main_moves("fourth.txt")
    third = "a third rebase after fixed and green"
    stop = f"Rebase hold: at {held}, {third}, onto origin/main at {tip}"
    told = [f"hold: no third rebase after fixed and green, the brief has the line {stop}"]
    assert pr.run("mergeable", home).splitlines() == told
    assert pr.head() == held
    assert not pr.rebasing()
    again = [f"held: no third rebase after fixed and green, and its gate is parked already: {stop}"]
    assert pr.run("mergeable", home).splitlines() == again
    assert brief.read_text().count("Rebase hold:") == 1
    assert brief.read_text().count("Rebased after fixed:") == 2
    assert ready.rebase_held(brief.read_text(), held) == ready.REBASE_HELD
    assert ready.rebase_held(brief.read_text(), tip) == ""

    brief.write_text(brief.read_text() + "Rebase hold lifted: question 7, by the user\n")
    assert ready.rebase_held(brief.read_text(), held) == ""
    assert pr.run("mergeable", home).splitlines() == ["rebased onto origin/main"]
    assert brief.read_text().count("Rebased after fixed:") == 3


def test_a_rebase_that_stops_after_the_fixed_line_counts_and_a_follow_up_counts_anew(tmp_path):
    """A follow-up with no `Fixed:` line of its own counts its rebases, and holds the third."""
    pr = PullRequest(tmp_path, "CONFLICTING", "shared.txt")
    home = tmp_path / "home"
    (home / "tasks").mkdir(parents=True)
    brief = home / "tasks" / "alpha.md"
    before = pr.head()
    brief.write_text(BRIEF + f"Fixed: {before}\nRebased after fixed: {'e' * 40}\n")
    said = pr.run("mergeable", home).splitlines()
    assert said[0] == "the rebase stopped: resolve these, then git rebase --continue"
    assert pr.rebasing()
    counted = f"Rebased after fixed: {before} onto origin/main at {pr.landed}\n"
    assert brief.read_text().endswith(counted)
    git(pr.work, "rebase", "--abort")

    brief.write_text(brief.read_text() + "\n## Result, follow-up (a steer)\nStatus: done\n")
    for count in (3, 4):
        assert pr.run("mergeable", home).splitlines()[0].startswith("the rebase stopped")
        assert brief.read_text().count("Rebased after fixed:") == count
        git(pr.work, "rebase", "--abort")
    (third,) = pr.run("mergeable", home).splitlines()
    assert third.startswith("hold: no third rebase after fixed and green, the brief has the line ")
    assert brief.read_text().count("Rebased after fixed:") == 4
    assert not pr.rebasing()


def covers(main, brief, head):
    """What `jmerge` makes of a head the brief says nothing of: the commit its review covers,
    and whether the review carries over to the head, by the range-diff run in the main
    checkout once it has fetched."""
    assert ready.short_of(brief, head) == ""
    covered = ready.to_range_diff(ready.rebase_of(brief, head), brief, head)
    git(main, "fetch", "-q", "origin")
    return covered, rangediff.verdict(main, covered, head, "main").clean


@pytest.mark.parametrize("main_edits", ["other.txt", "shared.txt"])
@pytest.mark.parametrize("fixed", [False, True])
def test_a_rebase_that_wrote_no_line_is_one_jmerge_carries_the_review_over(
    main_edits, fixed, tmp_path
):
    """The Result is as it was before the rebase: no `Rebase:` line, and a `Fixed:` line
    that names the commit it named then."""
    pr = PullRequest(tmp_path, "CONFLICTING", main_edits)
    saw = pr.head()
    pr.commit(pr.work, "mine.txt", "the task\n", "more of the task")
    before = pr.head()
    pr.run("mergeable")
    if pr.rebasing():
        (pr.work / "shared.txt").write_text("theirs\nthe task\n")
        git(pr.work, "add", "shared.txt")
        git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    assert pr.head() != before
    handled = f"Finding: fixed, it is wrong\nFixed: {before}\n" if fixed else ""
    review = merge.review("findings" if fixed else "clean", saw if fixed else before)
    assert covers(tmp_path / "main", BRIEF + handled + review, pr.head()) == (before, True)


def run(conclusion, job=None):
    """A check run as `gh pr view --json statusCheckRollup` lists it, with its job if it has one."""
    one = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": conclusion}
    if job:
        one["detailsUrl"] = f"https://github.com/someone/repo/actions/runs/5/job/{job}"
    return one


STEPS = {"1": [], "2": [{"name": "Run make check", "conclusion": "failure"}]}
RUNNING = {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}
ROLLUPS = {
    "all passed": ([run("SUCCESS"), run("SUCCESS", 2), run("SKIPPED")], "passed"),
    "a commit status that passed": (
        [{"__typename": "StatusContext", "state": "SUCCESS"}],
        "passed",
    ),
    "one ran and failed": ([run("SUCCESS"), run("FAILURE", 2)], "failed"),
    "one failed, and GitHub gives no job for it": ([run("FAILURE"), run("SKIPPED")], "failed"),
    "one failed, and its job cannot be asked for": ([run("FAILURE", 3), run("SKIPPED")], "failed"),
    "one timed out after it ran": ([run("TIMED_OUT", 2), run("SKIPPED")], "failed"),
    "a commit status that failed": (
        [{"__typename": "StatusContext", "state": "FAILURE"}],
        "failed",
    ),
    "one never started beside one that passed": ([run("SUCCESS"), run("FAILURE", 1)], "failed"),
    "none ran": ([run("FAILURE", 1), *[run("SKIPPED", 9)] * 3], "unrun"),
    "all skipped": ([run("SKIPPED"), run("SKIPPED")], "unrun"),
    "one still running": ([run("SUCCESS"), RUNNING], "wait"),
    "one still running beside one that never started": ([run("FAILURE", 1), RUNNING], "wait"),
    "none reported yet": ([], "wait"),
    "GitHub cannot be asked": (None, "wait"),
}


def stub_gh(stub, head, rollup, state="OPEN"):
    """A stub `gh` that says this of the pull request, or fails when there is no rollup."""
    stub.mkdir()
    (stub / "gh").write_text(GH)
    (stub / "gh").chmod(0o755)
    for job, steps in STEPS.items():
        (stub / f"job-{job}.json").write_text(json.dumps({"id": int(job), "steps": steps}))
    if rollup is not None:
        view = {"state": state, "headRefOid": head, "statusCheckRollup": rollup}
        (stub / "view.json").write_text(json.dumps(view))


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
            ["sh", "-c", block("Stay on the pull request", "checks()").replace("<slug>", "alpha")],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "H": str(self.state),
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
    template = (SKILL.parent.parent.parent / "templates" / "result.md").read_text()
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
    (line,) = set(re.findall(r"`(CI fix: <[^`]+)`", SKILL.read_text()))
    head, reviewed = "b" * 40, "a" * 40
    filled = re.sub(r"<[^>]+>", "{}", line).format(head, reviewed)
    brief = merge.brief(merge.review("clean", reviewed), filled + "\n")
    assert ready.short_of(brief, head) == ""
    assert ready.to_range_diff(ready.rebase_of(brief, head), brief, head) == reviewed


class Failed(PullRequest):
    """A pull request with a check that ran and failed at the pushed head, and its brief."""

    def __init__(self, tmp_path, holds_base=True):
        super().__init__(tmp_path, None, "other.txt")
        self.state = tmp_path / "state"
        (self.state / "tasks").mkdir(parents=True)
        self.brief = self.state / "tasks" / "alpha.md"
        self.brief.write_text(BRIEF)
        if holds_base:
            git(self.work, "fetch", "-q", "origin")
            git(self.work, "merge", "-q", "--no-edit", "origin/main")
        self.push()

    def push(self, checks=None):
        """GitHub has the head this worktree is at, and its failed check is job 2 of run 5."""
        view = {
            "headRefOid": self.head(),
            "baseRefName": "main",
            "statusCheckRollup": checks or [run("SUCCESS"), run("FAILURE", 2)],
        }
        (self.stub / "view.json").write_text(json.dumps(view))

    def says(self, here):
        """What the block prints, told what the check command did in this worktree."""
        text = block("Stay on the pull request", "run rerun").replace("<slug>", "alpha")
        text, filled = re.subn(
            r"^here='<[^>]*>'$", f"here='{here}'" if here else r"\g<0>", text, flags=re.M
        )
        assert filled == 1
        ran = subprocess.run(
            ["sh", "-c", text],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "H": str(self.state),
            },
            check=True,
        )
        (line,) = ran.stdout.splitlines()
        return line

    def reruns(self):
        calls = self.stub / "calls"
        return calls.read_text().splitlines() if calls.exists() else []


@pytest.mark.parametrize("holds_base", [True, False])
def test_a_failure_the_check_command_shows_here_is_the_changes_own(holds_base, tmp_path):
    failed = Failed(tmp_path, holds_base)
    assert failed.says("failed").split(": ")[0] == "fix"
    assert failed.reruns() == []


def test_a_failure_that_is_not_the_changes_on_a_branch_behind_its_base_is_a_stale_base(tmp_path):
    failed = Failed(tmp_path, holds_base=False)
    head = failed.head()
    said = failed.says("passed")
    assert said.split(": ")[0] == "stale"
    assert "origin/main" in said
    assert failed.reruns() == []
    assert failed.head() == head
    assert not failed.rebasing()
    assert git(failed.work, "status", "--porcelain") == ""


def test_any_other_failure_gets_one_fresh_run_of_the_whole_workflow_run(tmp_path):
    failed = Failed(tmp_path)
    failed.push([run("FAILURE", 2), run("TIMED_OUT", 3), run("SUCCESS", 4)])
    said = failed.says("passed")
    assert said.split(": ")[0] == "rerun"
    assert failed.reruns() == ["run rerun 5"]

    line = failed.brief.read_text().splitlines()[-1]
    assert line == f"Rerun: at {failed.head()}, workflow run 5 was run again whole"
    assert said.endswith(line)
    assert in_the_template(line)


def test_a_second_failure_at_a_head_is_not_a_flake_and_one_at_a_new_head_may_be(tmp_path):
    failed = Failed(tmp_path)
    assert failed.says("passed").split(": ")[0] == "rerun"
    assert failed.says("passed").split(": ")[0] == "stuck"
    assert failed.reruns() == ["run rerun 5"]

    git(failed.work, "commit", "-q", "--allow-empty", "-m", "a fix")
    failed.push()
    assert failed.says("passed").split(": ")[0] == "rerun"
    assert failed.reruns() == ["run rerun 5", "run rerun 5"]


def test_the_rerun_is_recorded_as_a_line_of_its_own_in_a_brief_with_no_last_newline(tmp_path):
    failed = Failed(tmp_path)
    failed.brief.write_text(BRIEF + "\n## Review\nHead: " + "a" * 40)
    assert failed.says("passed").split(": ")[0] == "rerun"
    last, line = failed.brief.read_text().splitlines()[-2:]
    assert last == "Head: " + "a" * 40
    assert line.startswith(f"Rerun: at {failed.head()}, ")
    assert failed.says("passed").split(": ")[0] == "stuck"
    assert failed.reruns() == ["run rerun 5"]


def test_a_rerun_the_brief_cannot_record_is_not_said_to_be_recorded(tmp_path):
    failed = Failed(tmp_path)
    failed.brief.chmod(0o444)
    said = failed.says("passed")
    assert said.split(": ")[0] == "wait"
    assert said.endswith(
        f"add the line Rerun: at {failed.head()}, workflow run 5 was run again whole"
    )
    assert failed.brief.read_text() == BRIEF


def test_a_failed_check_that_is_no_workflow_run_has_nothing_to_run_again(tmp_path):
    failed = Failed(tmp_path)
    failed.push([{"__typename": "StatusContext", "state": "FAILURE"}, run("FAILURE")])
    assert failed.says("passed").split(": ")[0] == "stuck"
    assert failed.reruns() == []


def not_told(failed):
    return None


def not_pushed(failed):
    git(failed.work, "commit", "-q", "--allow-empty", "-m", "not pushed")
    return "passed"


def not_committed(failed):
    (failed.work / "new.txt").write_text("more\n")
    return "failed"


def no_github(failed):
    (failed.stub / "view.json").unlink()
    return "passed"


def no_origin(failed):
    git(failed.work, "remote", "set-url", "origin", str(failed.stub / "gone.git"))
    return "passed"


def no_rerun(failed):
    (failed.stub / "no-rerun").write_text("")
    return "passed"


@pytest.mark.parametrize(
    "kept", [not_told, not_pushed, not_committed, no_github, no_origin, no_rerun]
)
def test_a_failed_check_the_block_cannot_judge_waits_and_changes_nothing(kept, tmp_path):
    failed = Failed(tmp_path)
    here = kept(failed)
    assert failed.says(here).split(": ")[0] == "wait"
    assert failed.reruns() == (["run rerun 5"] if kept is no_rerun else [])
    assert "Rerun:" not in failed.brief.read_text()


DONE = "Status: done\nBranch: alpha   Pull request: none\nLeft: none\n"


class NoPullRequest:
    """A crewmate's worktree on its own branch, in a clone whose remote has a default branch,
    and the brief the crewmate wrote its Result into."""

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
    """A brief whose crewmate paused, as `playbooks/pause-safely.md` step 4 writes its Result."""
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


def base_of(tmp_path, brief, knows_default=True):
    """What the block that prints a pull request's base says for a brief, in a clone of a
    repo whose default branch is `main`."""
    origin, work = tmp_path / "origin.git", tmp_path / "work"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "init", "-q", "-b", "main", str(work))
    PullRequest.commit(work, "a.txt", "one\n", "start")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "-q", "origin", "main")
    if knows_default:
        git(work, "remote", "set-head", "origin", "main")
    (tmp_path / "tasks").mkdir()
    (tmp_path / "tasks" / "alpha.md").write_text(brief)
    ran = subprocess.run(
        ["sh", "-c", block("Do the task", "Stack:").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        cwd=work,
        env={**os.environ, "H": str(tmp_path)},
        check=True,
    )
    (line,) = ran.stdout.splitlines()
    return line


def test_a_brief_with_no_stack_line_opens_its_pull_request_on_the_default_branch(tmp_path):
    assert base_of(tmp_path, BRIEF).startswith("base main: the default branch, ")


@pytest.mark.parametrize(
    ("line", "base", "place"),
    [
        ("Stack: billing 1 on main", "main", "1"),
        ("Stack: billing 2 on add-schema", "add-schema", "2"),
    ],
)
def test_a_link_of_a_stack_opens_its_pull_request_on_the_branch_its_brief_names(
    line, base, place, tmp_path
):
    said = base_of(tmp_path, with_field(line))
    assert said.split(": ")[0] == f"base {base}"
    assert said.endswith(f"link {place} of the stack billing")
    assert ready.stack_of(with_field(line)) == "billing"


def test_only_a_stack_line_in_the_head_of_the_brief_gives_a_base(tmp_path):
    said = base_of(tmp_path, BRIEF + "Stack: billing 2 on add-schema\n")
    assert said.startswith("base main: the default branch, ")


@pytest.mark.parametrize(
    "line",
    [
        "Stack: billing",
        "Stack: billing 2",
        "Stack: billing 2 add-schema",
        "Stack: billing two on x",
    ],
)
def test_a_stack_line_that_names_no_branch_gives_no_base_to_guess(line, tmp_path):
    said = base_of(tmp_path, with_field(line))
    assert said.startswith("no base: the brief's Stack: line is not ")


def test_a_clone_that_does_not_know_the_default_branch_gives_no_base(tmp_path):
    said = base_of(tmp_path, BRIEF, knows_default=False)
    assert said.startswith("no base: the brief has no Stack: line, and ")


class Link(PullRequest):
    """The second link of a stack: its worktree started from the branch of the link under it,
    which has since been squash-merged, and that branch is kept on the remote."""

    def __init__(self, tmp_path, base, edits="mine.txt", under_moved=False):
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "gh").write_text(GH)
        (self.stub / "gh").chmod(0o755)
        if base:
            (self.stub / "view.json").write_text(f'{{"baseRefName": "{base}"}}')

        origin, other, main = tmp_path / "origin.git", tmp_path / "other", tmp_path / "main"
        self.work = tmp_path / "trees" / "a-link"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(other))
        self.commit(other, "shared.txt", "one\n", "start")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(tmp_path, "clone", "-q", str(origin), str(main))
        git(main, "checkout", "-q", "-b", "under")
        if under_moved:
            self.commit(main, "bottom.txt", "one\n", "bottom, one")
            self.commit(main, "bottom.txt", "one\ntwo\n", "bottom, two")
        bottom = git(main, "rev-parse", "HEAD")
        self.commit(main, "under.txt", "one\n", "under, one")
        self.commit(main, "under.txt", "one\ntwo\n", "under, two")
        git(main, "push", "-q", "-u", "origin", "under")
        git(main, "worktree", "add", "-q", "-b", "a-link", str(self.work), "under")
        git(main, "checkout", "-q", "main")
        self.git_dir = Path(git(self.work, "rev-parse", "--absolute-git-dir"))
        self.commit(self.work, edits, "one\ntwo\nthe link\n", "the link")
        git(self.work, "push", "-q", "-u", "origin", "a-link")
        self.started_from = git(main, "rev-parse", "under")
        self.commit(other, "other.txt", "theirs\n", "theirs")
        git(other, "push", "-q", "origin", "HEAD:main")
        if under_moved:
            self.commit(other, "bottom.txt", "one\ntwo\n", "bottom (#1)")
            git(other, "push", "-q", "origin", "HEAD:main")
            git(main, "fetch", "-q", "origin")
            git(main, "checkout", "-q", "under")
            git(main, "rebase", "-q", "--onto", "origin/main", bottom)
            git(main, "push", "-q", "--force-with-lease", "origin", "under")
            git(main, "checkout", "-q", "main")
        self.commit(other, "under.txt", "one\ntwo\n", "under (#2)")
        git(other, "push", "-q", "origin", "HEAD:main")
        self.landed = git(other, "rev-parse", "HEAD")

    def move(self, was="under"):
        about = block("Stay on the pull request", "--onto")
        (placeholder,) = re.findall(r"^was='(<[^>]+>)'$", about, re.M)
        return self.run_text(about.replace(placeholder, was)).splitlines()

    def run_text(self, text, **env):
        return subprocess.run(
            ["sh", "-c", text],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                **env,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.com",
                "GIT_EDITOR": "true",
            },
        ).stdout


def test_a_link_whose_base_merged_moves_its_own_commits_onto_the_default_branch(tmp_path):
    link = Link(tmp_path, "main")
    before = link.head()
    assert link.move() == ["moved from under onto origin/main"]
    assert not link.rebasing()
    assert git(link.work, "rev-parse", "HEAD~1") == link.landed
    assert git(link.work, "log", "--format=%s", "origin/main..HEAD") == "the link"
    assert (link.work / "under.txt").read_text() == "one\ntwo\n"

    review = merge.review("clean", before)
    assert covers(tmp_path / "main", BRIEF + review, link.head()) == (before, False)
    assert link.move() == ["already on origin/main: no rebase"]


def test_a_link_does_not_move_before_the_home_changed_its_base(tmp_path):
    link = Link(tmp_path, "under")
    before = link.head()
    assert link.move() == ["already on origin/under: no rebase"]
    assert link.head() == before
    assert not (link.git_dir / "crew-before-rebase").exists()


def test_a_link_whose_parent_was_rewritten_under_it_is_rebased_from_where_it_started(tmp_path):
    link = Link(tmp_path, "under", under_moved=True)
    assert link.move() == ["moved from under onto origin/under"]
    assert not link.rebasing()
    assert git(link.work, "log", "--format=%s", "origin/under..HEAD") == "the link"


@pytest.mark.parametrize("mergeable", ["CONFLICTING", "MERGEABLE"])
def test_a_conflict_never_rebases_a_link_of_a_stack_by_itself(mergeable, tmp_path):
    link = Link(tmp_path, "main")
    view = f'{{"baseRefName": "main", "mergeable": "{mergeable}"}}'
    (link.stub / "view.json").write_text(view)
    before = link.head()
    (tmp_path / "tasks").mkdir()
    brief = tmp_path / "tasks" / "a-link.md"
    about = block("Stay on the pull request", "mergeable").replace("<slug>", "a-link")

    brief.write_text(with_field("Stack: billing 2 on under"))
    (said,) = link.run_text(about, H=str(tmp_path)).splitlines()
    assert said.startswith("a link of a stack: no rebase here")
    assert link.head() == before
    assert not (link.git_dir / "crew-before-rebase").exists()
    brief.write_text(BRIEF + "Stack: billing 2 on under\n")
    said = link.run_text(about, H=str(tmp_path)).splitlines()
    if mergeable == "MERGEABLE":
        assert said == ["no conflict: no rebase"]
    else:
        stopped = "the rebase stopped: resolve these, then git rebase --continue"
        assert said == [stopped, "under.txt"]


def test_a_link_does_not_move_when_github_cannot_be_asked(tmp_path):
    link = Link(tmp_path, None)
    before = link.head()
    assert link.move() == ["could not ask GitHub: no rebase"]
    assert link.head() == before


def only_the_link_moved(link):
    return (
        git(link.work, "rev-parse", "HEAD~1") == link.landed
        and git(link.work, "log", "--format=%s", "origin/main..HEAD") == "the link"
        and not link.rebasing()
    )


def test_a_link_whose_parent_was_moved_before_it_merged_still_moves_only_its_own_commits(
    tmp_path,
):
    link = Link(tmp_path, "main", under_moved=True)
    assert git(link.work, "log", "--format=%s", "origin/under..HEAD").splitlines() == [
        "the link",
        "under, two",
        "under, one",
        "bottom, two",
        "bottom, one",
    ]
    assert link.move() == ["moved from under onto origin/main"]
    assert only_the_link_moved(link)


@pytest.mark.parametrize("under_moved", [False, True])
def test_a_link_does_not_move_once_the_branch_it_sat_on_is_gone(under_moved, tmp_path):
    link = Link(tmp_path, "main", under_moved=under_moved)
    before = link.head()
    git(link.work, "branch", "-q", "-D", "under")
    git(link.work, "push", "-q", "origin", "--delete", "under")
    (said,) = link.move()
    assert said.startswith("not found: the commit this branch started from is not under, ")
    assert said.endswith(": no rebase")
    assert link.head() == before
    assert not (link.git_dir / "crew-before-rebase").exists()
    assert link.move(link.started_from) == [f"moved from {link.started_from} onto origin/main"]
    assert only_the_link_moved(link)


def test_a_link_does_not_move_from_a_commit_that_is_not_under_it(tmp_path):
    link = Link(tmp_path, "main")
    before = link.head()
    git(link.work, "push", "-q", "origin", "--delete", "under")
    (said,) = link.move(link.landed)
    assert said.startswith("not found: ")
    assert link.head() == before


def test_a_move_that_conflicts_stops_and_says_which_files(tmp_path):
    link = Link(tmp_path, "main", edits="other.txt")
    said = link.move()
    assert said == ["the rebase stopped: resolve these, then git rebase --continue", "other.txt"]
    assert link.rebasing()
    assert link.move()[0] == "the rebase is not finished: resolve these, then git rebase --continue"


def test_a_brief_that_came_in_the_launch_message_is_the_brief_the_skill_reads(kitchen, tmp_path):
    """`jbus` puts the brief under the first line of its launch, and step 1 writes that down."""
    brief = BRIEF.split("\n## Result")[0] + (
        "Done when:\n- it is done\nProves it: `make check`\nSize: S\nWhere: `src/alpha/`\n"
        "Design: none, a test\nReview: review+test\nPlaybook: feature\n"
    )
    assert kitchen.main("queue", "add", "alpha", "--priority", "1", stdin=brief)[0] == 0
    sha = hashlib.sha256(brief.encode()).hexdigest()[:12]
    at = ["--word", kitchen.word(), "--sha", sha]
    assert kitchen.main("queue", "approve", "alpha", *at)[0] == 0
    kitchen.poll()
    first, _, below = kitchen.t3.launches[0]["message"].partition("\n")
    assert first == "/crew alpha"
    on_disk = (kitchen.home / "tasks" / "alpha.md").read_text()
    assert on_disk == below.strip() + "\nThread: mcp:thread-1\n"
    home = tmp_path / "a-machine-with-no-brief-on-disk"
    home.mkdir()
    assert said(home, "The review", "mode=", below) == ["review: launch a reviewer"]


def where_the_findings_go(home):
    """What step 4 of the pr-review skill's "After the review" prints, then whom its
    "Telling the home" finds, for the brief `alpha` in a home's state directory."""
    skill = (SKILL.parent.parent / "pr-review" / "SKILL.md").read_text()
    printed = []
    for heading, about in (
        ("### After the review", "crewmate $thread"),
        ("### Telling the home", ""),
    ):
        under = skill.split(f"{heading}\n", 1)[1].split("```sh\n")[1:]
        found = next(text for text in under if about in text).split("```", 1)[0]
        script = 'B="$H/tasks/alpha.md"\n' + textwrap.dedent(found).replace("<slug>", "alpha")
        script = script.replace("<clean, findings or not run>", "findings")
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            env={**os.environ, "H": str(home)},
            check=True,
        )
        printed.append(ran.stdout.strip())
    return printed[0].split(":")[0], printed[1]


def test_with_no_home_the_findings_go_to_the_thread_line_as_they_do_with_one(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n")
    for home in ("", "mcp:a-home\n"):
        (kitchen.home / "home-id").write_text(home)
        assert where_the_findings_go(kitchen.home)[0] == "crewmate mcp"


def test_findings_with_no_thread_line_and_no_home_are_written_not_sent_and_jbus_parks_them(
    kitchen,
):
    """The reviewer writes the `Sent to:` line the pr-review skill gives for no home, and
    the next pass of jbus reads it."""
    from jbus import threads

    review = (
        "\n## Review\nVerdict: findings\nFindings:\n- warning a.py:1 wrong\n"
        "Sent to: not sent, no home\n"
    )
    brief = kitchen.brief("alpha", review)
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    (kitchen.home / "home-id").write_text("")
    assert where_the_findings_go(kitchen.home) == ("home", "")
    kitchen.poll()
    assert kitchen.lines("condition") == [
        "condition alpha: review findings with no thread to send them to"
    ]
    (kitchen.home / "home-id").write_text("mcp:a-home\n")
    assert where_the_findings_go(kitchen.home) == ("home", "mcp:a-home")
    (kitchen.home / "home-id").write_text("")
    brief.write_text(brief.read_text().replace("\n## Review", "Thread: mcp:crew\n\n## Review"))
    assert where_the_findings_go(kitchen.home)[0] == "crewmate mcp"
    kitchen.poll(NOW + timedelta(minutes=3))
    ((tool, given),) = [call for call in kitchen.t3.calls if call[0] == "t3_thread_send"]
    assert given["message"].startswith(threads.RELAY + "\n\n## Review\n")
    assert (given["threadId"], kitchen.lines("relayed")) == ("mcp:crew", ["relayed alpha"])


REVIEWING = "a review of {} is running: rebase after its section is written"
STOPPED = "the rebase stopped: resolve these, then git rebase --continue"


def stays(pr, about, brief=None, why=None, slug="a-task", state=None, shell="sh"):
    """What a block of "Stay on the pull request" prints in a crewmate's worktree, with the
    slug filled in, the home's state beside it, and `stale` given where the test gives it."""
    state = state or pr.stub.parent / "home"
    (state / "tasks").mkdir(parents=True, exist_ok=True)
    if brief is not None:
        (state / "tasks" / f"{slug}.md").write_text(brief)
    text = block("Stay on the pull request", about).replace("<slug>", slug)
    if why:
        text, filled = re.subn(r"^why='<[^>]*>'$", f"why='{why}'", text, flags=re.M)
        assert filled == 1
    if shell != "sh":
        text = f"exec {shell} -c {shlex.quote(text)}"
    return Link.run_text(pr, text, H=str(state)).splitlines()


def asked(pr, mergeable):
    """GitHub's answer about the pull request, with the head it has there."""
    view = {"baseRefName": "main", "mergeable": mergeable, "headRefOid": pr.head()}
    (pr.stub / "view.json").write_text(json.dumps(view))


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
    rebase = repo.unsaid("main", before, head)
    assert rebase == ready.Rebase("changed", ("mine.txt", "shared.txt"), before, head)
    lost = repo.dropped("main", rebase, head)
    held = ready.drops(lost, "", head, user=jsettings.DEFAULTS)
    if says.startswith("Kept:"):
        assert held == ("", "")
        return
    dropped = says.removeprefix("Dropped: ").replace(", ", " and ")
    unsaid = f"the rebase dropped {dropped} with no Dropped on rebase line at {head[:12]}"
    assert held == ("wait", unsaid)
    shape = re.search(r"`(Dropped on rebase: <file>[^`]+)`", SKILL.read_text())[1]
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


PROJECT = """\
[project]
name = "app"
version = "0"
requires-python = ">=3.12"
dependencies = [
{}]

[tool.uv]
package = false

[tool.uv.sources]
{}"""
SOURCE = '{0} = {{ path = "{0}", package = false }}\n'
LIBRARY = '[project]\nname = "{}"\nversion = "1"\nrequires-python = ">=3.12"\n'


class Locked(PullRequest):
    """A pull request and a default branch that each added a dependency, and locked it."""

    def __init__(self, tmp_path):
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "gh").write_text(GH)
        (self.stub / "gh").chmod(0o755)
        origin, other, main = tmp_path / "origin.git", tmp_path / "other", tmp_path / "main"
        self.work = tmp_path / "trees" / "a-task"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(other))
        for name in ("base", "core", "ours", "theirs"):
            (other / name).mkdir()
            (other / name / "pyproject.toml").write_text(LIBRARY.format(name))
        self.depend(other, "start")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(tmp_path, "clone", "-q", str(origin), str(main))
        git(main, "worktree", "add", "-q", "-b", "a-task", str(self.work))
        self.git_dir = Path(git(self.work, "rev-parse", "--absolute-git-dir"))
        self.depend(self.work, "the task", "ours")
        git(self.work, "push", "-q", "-u", "origin", "a-task")
        self.depend(other, "theirs", "theirs")
        git(other, "push", "-q", "origin", "HEAD:main")
        asked(self, "CONFLICTING")

    @staticmethod
    def project(*names):
        names = ("base", "core", *names)
        listed = "".join(f'    "{name}",\n' for name in names)
        return PROJECT.format(listed, "".join(SOURCE.format(name) for name in names))

    def depend(self, repo, message, *names):
        (repo / "pyproject.toml").write_text(self.project(*names))
        subprocess.run(["uv", "lock", "--offline"], cwd=repo, check=True, capture_output=True)
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "-m", message)


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
@pytest.mark.parametrize("notes", [None, "- Generated: `uv.lock` -> `uv lock --offline`\n"])
def test_a_lock_file_a_rebase_stops_on_is_made_again_from_both_sides(notes, tmp_path):
    pr = Locked(tmp_path)
    if notes:
        (tmp_path / "home").mkdir()
        (tmp_path / "home" / "notes.md").write_text(f"# notes\n\n- Check command: `true`\n{notes}")
    assert stays(pr, "Generated:") == ["no rebase is stopped here: nothing to make again"]
    assert stays(pr, "mergeable") == [STOPPED, "pyproject.toml", "uv.lock"]
    assert stays(pr, "Generated:") == [
        "resolve these by hand and git add them, then run this again:",
        "pyproject.toml",
    ]
    assert "<<<<<<<" in (pr.work / "uv.lock").read_text()
    (pr.work / "pyproject.toml").write_text(pr.project("ours", "theirs"))
    git(pr.work, "add", "pyproject.toml")
    command = "uv lock --offline" if notes else "uv lock"
    assert stays(pr, "Generated:") == [f"made again: uv.lock, by {command} over the base's version"]
    assert stays(pr, "Generated:") == ["nothing is left to resolve: git rebase --continue"]
    git(pr.work, "-c", "core.editor=true", "rebase", "--continue")
    assert not pr.rebasing()

    lock = (pr.work / "uv.lock").read_text()
    assert "<<<<<<<" not in lock
    assert 'name = "ours"' in lock
    assert 'name = "theirs"' in lock
    synced = subprocess.run(
        ["uv", "sync", "--locked", "--offline"],
        cwd=pr.work,
        capture_output=True,
        text=True,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(tmp_path / "venv")},
    )
    assert synced.returncode == 0, synced.stderr
    assert git(pr.work, "status", "--porcelain") == ""
    assert stays(pr, "Kept:") == ["Kept: every line, in pyproject.toml uv.lock"]


def test_a_file_the_notes_say_a_command_writes_is_made_by_that_command(tmp_path):
    pr = PullRequest(tmp_path, None, "shared.txt")
    asked(pr, "CONFLICTING")
    (tmp_path / "home").mkdir()
    made = "Generated: shared.txt -> echo made from both > shared.txt\n"
    (tmp_path / "home" / "notes.md").write_text(f"# notes\n{made}")
    assert stays(pr, "mergeable") == [STOPPED, "shared.txt"]
    assert stays(pr, "Generated:") == [
        "made again: shared.txt, by echo made from both > shared.txt over the base's version"
    ]
    assert (pr.work / "shared.txt").read_text() == "made from both\n"
    assert git(pr.work, "diff", "--name-only", "--diff-filter=U") == ""


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv is not installed")
def test_with_a_line_in_the_notes_a_lock_file_no_line_names_is_resolved_by_hand(tmp_path):
    pr = Locked(tmp_path)
    (tmp_path / "home").mkdir()
    (tmp_path / "home" / "notes.md").write_text("Generated: schema.json -> make schema\n")
    assert stays(pr, "mergeable") == [STOPPED, "pyproject.toml", "uv.lock"]
    assert stays(pr, "Generated:") == [
        "resolve these by hand and git add them, then run this again:",
        "pyproject.toml",
        "uv.lock",
    ]
