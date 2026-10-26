"""The crew skill's "The review" and "A second pass": how each finding ends, the Fixed: line,
and the scoped review of a fix."""

import os
import re
import shutil
import subprocess

import pytest

import test_home_merge as merge
import test_jmerge_guarded as guarded
import test_jmerge_rangediff as rebases
from crew_helpers import (
    BRIEF,
    GUARDED,
    HAD,
    SKILL,
    TWO,
    Fix,
    block,
    opened,
    reviewed,
    said,
    with_field,
)
from test_home_thread import as_read
from testing.layouts import assembled

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
    assert said(tmp_path, "The review", "--left", brief) == [says]


def by(who, findings, head="a" * 40):
    """A section that one reviewer of several wrote: its `By:` line and the head it saw."""
    listed = "".join(f"- {finding}\n" for finding in findings) or "- none\n"
    return (
        f"\n## Review\nBy: {who}\nVerdict: findings\nHead: {head}\nFindings:\n{listed}Dropped: 0\n"
    )


LAUNCHED = "Reviewer: mcp:codex\nReviewer: mcp:cursor\n"


@pytest.mark.parametrize(
    ("brief", "says"),
    [
        pytest.param(
            BRIEF + LAUNCHED + by("codex gpt-6-sol xhigh", TWO[:1]),
            "wait: 1 of 2 reviewers have written their section",
            id="one of two reviewers written waits, whatever its findings",
        ),
        pytest.param(
            BRIEF + LAUNCHED + FIXED_ONE + by("codex gpt-6-sol xhigh", TWO[:1]),
            "wait: 1 of 2 reviewers have written their section",
            id="an ending written early does not stand for the reviewer still out",
        ),
        pytest.param(
            BRIEF
            + LAUNCHED
            + FIXED_ONE
            + ANSWERED_ONE
            + by("codex gpt-6-sol xhigh", TWO[:1])
            + by("cursor grok-4.7 xhigh", TWO[1:]),
            "write Fixed: <the head you pushed>, 2 findings each have their ending",
            id="the sections of one head are one review, and a fix for either is a fix",
        ),
        pytest.param(
            BRIEF
            + LAUNCHED
            + ANSWERED_ONE * 2
            + by("codex gpt-6-sol xhigh", TWO[:1])
            + by("cursor grok-4.7 xhigh", TWO[1:]),
            "write Fixed: none needed, <reason>: 2 findings, none fixed",
            id="both declined is none needed",
        ),
        pytest.param(
            BRIEF
            + LAUNCHED
            + FIXED_ONE
            + ANSWERED_ONE
            + ANSWERED_ONE
            + by("codex gpt-6-sol xhigh", TWO[:1])
            + by("cursor grok-4.7 xhigh", TWO[1:])
            + by("codex gpt-6-sol xhigh", TWO[1:], head="b" * 40),
            "write Fixed: none needed, <reason>: 1 findings of the last review, none fixed",
            id="a scoped review after the pair is the last review, and the pair is not",
        ),
    ],
)
def test_with_two_reviewers_the_findings_wait_for_both_and_are_one_review(brief, says, tmp_path):
    assert said(tmp_path, "The review", "--left", brief) == [says]


OLD_NONE = "Second pass: none, the fix stayed inside the files the findings named"


TESTS_ONLY = "write Scoped review: none, the fix changed files under tests/ only"


NOTHING_PUSHED = "write Scoped review: none, nothing was pushed for the findings"


NO_REVIEW_OF_IT = "none: no review of the fix, as the Result says"


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


@pytest.mark.parametrize("path", ["docs/a.md", "skills/crew/SKILL.md"], ids=["docs", "a skill"])
def test_the_review_of_a_fix_is_the_last_whatever_path_it_changes(path, tmp_path):
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
    fix.commit("the second fix")
    assert fix.says(launched, written) == [HAD]


def test_the_launch_of_a_fix_s_review_asks_no_tool_so_it_waits_for_no_green_check(tmp_path):
    fix = opened(tmp_path, "docs/a.md")
    stub = tmp_path / "stub"
    stub.mkdir()
    for tool in ("gh",):
        (stub / tool).write_text(f"#!/bin/sh\necho {tool} >> {stub}/calls\nexit 1\n")
        (stub / tool).chmod(0o755)
    brief = BRIEF + owed(fix, "the fix changed docs/a.md") + fix.review
    (fix.state / "tasks" / "alpha.md").write_text(brief)
    path = f"{stub}{os.pathsep}{os.environ['PATH']}"
    ran = subprocess.run(
        ["sh", "-c", block("The review", "Second pass:").replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        cwd=fix.work,
        env={
            **os.environ,
            "H": str(fix.state),
            "T": str(assembled() / "templates"),
            "PATH": path,
        },
        check=True,
    )
    assert ran.stdout.splitlines() == [launch(fix, fix.saw, fix.fixed)]
    assert not (stub / "calls").exists()


INFO = ["info a.py:9 a name could say more", "info b.py:1 a comment says the code again"]


NONE_FIXED = "write Fixed: none needed, <reason>: 2 findings, none fixed"


ALL_INFO = "Fixed: none needed, every finding is info and left for a follow-up\n"


def declined(findings=INFO):
    """The `Finding:` lines of info findings that a crewmate declines, in the skill's own words."""
    found = re.findall(r"`(Finding: not fixed, <[^>]+>, because info: [^`]+)`", as_read(SKILL))
    (shape,) = set(found)
    words = [finding.split(" ", 2)[2] for finding in findings]
    return "".join(re.sub("<[^>]+>", said, shape) + "\n" for said in words)


def test_a_review_of_info_findings_all_declined_pushes_nothing_and_is_handled(tmp_path):
    fix = Fix(tmp_path, [], INFO)
    brief = merge.brief(fix.review, declined())
    assert said(fix.state, "The review", "--left", brief) == [NONE_FIXED]
    assert said(fix.state, "The review", "Second pass:", brief, cwd=fix.work) == [NOTHING_PUSHED]
    home = merge.Home(tmp_path)
    handled = f"{NOTHING_PUSHED.removeprefix('write ')}\n{ALL_INFO}"
    (home.tasks / "alpha.md").write_text(merge.brief(fix.review, declined() + handled))
    home.open_pull_request(fix.saw)
    assert home.ready() == [f"ready 7 {fix.saw} alpha alpha"]


def test_a_warning_fixed_beside_info_findings_declined_gets_the_review_of_its_fix(tmp_path):
    fix = Fix(tmp_path, ["a.py"], ["warning a.py:3 it runs twice", *INFO])
    brief = merge.brief(fix.review, FIXED_ONE + declined())
    assert said(fix.state, "The review", "--left", brief) == [
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
    assert said(state, "The review", "--left", brief) == [NONE_FIXED]
    assert said(state, "The review", "Second pass:", brief, cwd=proven_merged.tree) == [
        NOTHING_PUSHED
    ]
    rebased.brief(reviews, declined() + ALL_INFO)
    assert guarded.jmerge(proven_merged, rules, "--check") == [
        f"ready 7 {rebased.head} alpha alpha"
    ]


SHELLS = [
    "sh",
    pytest.param("zsh", marks=pytest.mark.skipif(not shutil.which("zsh"), reason="no zsh")),
]


@pytest.mark.parametrize("shell", SHELLS)
def test_a_scoped_review_owed_is_launched_once_for_its_head_and_is_the_last(shell, tmp_path):
    fix = opened(tmp_path, GUARDED)
    needed = owed(fix, f"the fix changed {GUARDED}")
    assert fix.says("", shell=shell) == [f"write {needed.strip()}"]
    decided = f"{OLD_NONE}\n{needed}"
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
    fix.commit("the second fix")
    assert fix.says(launched, proven) == ["none: no second pass, as the Result says"]


@pytest.mark.parametrize("path", ["docs/a.md", GUARDED], ids=["docs", "a skill"])
def test_a_fix_is_decided_by_what_it_changed_whatever_path_the_pull_request_changes(path, tmp_path):
    fix = opened(tmp_path, path)
    assert fix.says("") == [f"write {owed(fix, f'the fix changed {path}').strip()}"]
    assert fix.says("", fix.review + fix.review) == [
        f"write {owed(fix, f'the fix changed {path}').strip()}"
    ]
    assert fix.says("Second pass: none, the fix stayed inside\n") == [
        "none: no second pass, as the Result says"
    ]


def test_the_shipped_list_guards_no_path_so_a_fix_to_a_skill_is_asked_no_scoped_review(tmp_path):
    fix = opened(tmp_path, GUARDED, fix=["tests/c.py"])
    assert fix.says("") == [TESTS_ONLY]
    assert fix.says("Second pass: none, the fix stayed inside\n") == [
        "none: no second pass, as the Result says"
    ]


@pytest.mark.parametrize(
    "moved",
    [
        "CI fix: {fixed}, after the review of {saw}\n",
        "Rebase: patch unchanged, before {saw}, head {fixed}\n",
        "Rebase: patch changed in a.py, before {saw}, head {fixed}\n",
    ],
    ids=["a push for a failed check", "a rebase", "a rebase that changed the patch"],
)
def test_a_head_jmerge_compares_by_range_diff_is_asked_no_scoped_review_here(moved, tmp_path):
    fix = opened(tmp_path, GUARDED)
    none = ["none: no second pass, as the Result says"]
    result = "Second pass: none, nothing was pushed\n" + moved.format(fixed=fix.fixed, saw=fix.saw)
    for fixed in ("", f"Fixed: {fix.fixed}\n"):
        assert fix.says(fixed + result) == none
        assert fix.says(result + fixed) == none


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
