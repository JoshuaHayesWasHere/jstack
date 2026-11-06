"""Every reason `jmerge.ready` gives, of every step, is a wait its crew hears of, or one no crew can
fix, or one another part of jbus tells the crew of. #1004 added eight `Proved:` reasons, none had a
row of `expedite.TABLE`, and by the next hour eight green pull requests sat held on them with their
crews idle. The table is held to `jmerge.ready` here, so the next reason of any step cannot be
quiet the same way. The pass tests run the real pass against the kitchen's fakes, as
`test_jbus_expedite.py` does."""

import pytest

from jbriefs import skills
from jbus import expedite, merge
from jmerge import judgement, ready
from test_jbus_expedite import URL, Short, said_to
from test_jbus_unlock import sends
from testing.paths import REPO

PROVED_MISSING = ready.PROVED_MISSING.format(tests="tests/test_a.py")
SAYS_MISSING = (
    "Run the proof block of the crew skill's do-the-task.md, its step \"Once the check passed, "
    'prove the change with the tests it changes", in your worktree, with the work committed: it '
    "appends the `Proved:` line to the Result itself, and `jmerge` reads the last one. The Result "
    "has no `Proved:` line, and the pull request changes the tests the reason names. Push nothing "
    "for it: the line is in the Result, not the branch."
)


@pytest.fixture
def short(kitchen):
    return Short(kitchen)


def test_every_reason_of_every_step_is_a_row_a_crew_is_told_or_named_with_why_it_is_not():
    rows = {row.reason.code: row for row in expedite.TABLE}
    given = {one.code for one in ready.reasons().values()}
    untold, elsewhere = set(expedite.UNTOLD), set(expedite.ELSEWHERE)
    assert given - rows.keys() - untold - elsewhere == set()
    assert rows.keys() | untold | elsewhere <= given
    assert rows.keys() & untold == rows.keys() & elsewhere == untold & elsewhere == set()
    assert all(expedite.UNTOLD.values()) and all(expedite.ELSEWHERE.values())
    for code, row in rows.items():
        assert row.word == judgement.verb(row.reason), code


def test_a_reason_jmerge_adds_with_no_row_and_no_why_fails_the_guard(monkeypatch):
    """The guard reads `ready` itself, so a reason added there with nothing beside it fails."""
    monkeypatch.setattr(ready, "NEW_WAIT", ready.Reason("check", "a new wait", "new-wait"), False)
    with pytest.raises(AssertionError):
        test_every_reason_of_every_step_is_a_row_a_crew_is_told_or_named_with_why_it_is_not()


@pytest.mark.parametrize(
    "reason",
    [
        PROVED_MISSING,
        ready.PROVED_UNREAD.format(fault="has no base exit"),
        ready.PROVED_NOT_EXEMPT.format(tests="tests/test_a.py"),
        ready.PROVED_NOT_KIND.format(kinds="docs", path="src/a.py"),
        ready.PROVED_UNNAMED.format(tests="tests/test_a.py"),
        ready.PROVED_BASE_PASSED.format(exit=0, base="a" * 12),
        ready.PROVED_HEAD_FAILED.format(exit=1, head="b" * 12),
        ready.PROVED_STALE.format(at="a" * 12, head="b" * 12),
        ready.SKILLS_UNRUN.format(names="architect"),
    ],
)
def test_a_line_jmerge_prints_for_a_result_reason_finds_its_row_by_its_text(reason):
    """`jmerge` prints the reason's text, and the row is found by the code that text gives."""
    row = expedite.short_of(merge.Line("wait", 7, URL, str(reason)))
    assert row is not None and row.reason.code == reason.code


def test_a_pull_request_with_no_proved_line_tells_its_crew_once_per_head(short, kitchen):
    short.out(PROVED_MISSING)
    short.passes(2)
    assert sends(kitchen) == []
    said = short.passes(1)
    assert sends(kitchen) == [said_to(short, "proved-missing", PROVED_MISSING, SAYS_MISSING)]
    line = f"expedite alpha: told the crew what #7 is short of (proved-missing, {short.head[:12]})"
    assert line in said
    short.passes(6)
    assert len(sends(kitchen)) == 1
    head = short.commit("a new head")
    short.out(PROVED_MISSING, head=head)
    short.passes(3)
    assert [one["clientRequestId"] for one in sends(kitchen)] == [
        f"proved-missing|alpha|{short.head[:12]}",
        f"proved-missing|alpha|{head[:12]}",
    ]


def test_a_skill_with_no_artifact_tells_the_crew_the_item_it_owes(short, kitchen):
    named = "Review: review\nSkills: architect\n"
    short.launched = short.launched.replace("Review: review\n", named)
    short.out(ready.SKILLS_UNRUN.format(names="architect"))
    short.passes(3)
    (sent,) = sends(kitchen)
    assert sent["clientRequestId"] == f"skills|alpha|{short.head[:12]}"
    assert f"The items it owes: `- architect: {skills.owed('architect')}`." in sent["message"]
    short.passes(3)
    assert len(sends(kitchen)) == 1


AGAIN = "/pr-review run alpha again"
RERUN = (REPO / "features/crew/templates/rerun.md").read_text().strip().replace("{slug}", "alpha")
SAYS_NO_VERDICT = (
    "The last `## Review` has no verdict `jmerge` reads, so no review has judged the head. Send "
    "the thread of the Result's last `Reviewer:`, `Second reviewer:` or `Scoped reviewer:` line, "
    f"the one that wrote that `## Review`, the one line `{AGAIN}` with `t3_thread_send`, and write "
    f"`Woke: jbus, sent {AGAIN}` in the Result, the line as sent. Never write or mend a review's "
    f"line yourself, and launch no second reviewer. {RERUN}"
)
UNJUDGED = "\n## Review\nHead: {saw}\nFindings:\n- minor a.py:1 a made up one\n"


def test_a_review_with_no_verdict_tells_the_crew_to_run_its_reviewer_again(short, kitchen):
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    result = f"Reviewer: {reviewer['threadId']}\n" + UNJUDGED.format(saw=short.saw)
    short.out(ready.NO_VERDICT, result=result, review=False)
    short.passes(2)
    assert sends(kitchen) == []
    said = short.passes(1)
    assert sends(kitchen) == [said_to(short, "no-verdict", ready.NO_VERDICT, SAYS_NO_VERDICT)]
    line = f"expedite alpha: told the crew what #7 is short of (no-verdict, {short.head[:12]}), "
    assert line + f"sent `{AGAIN}`" in said
    short.passes(6)
    assert len(sends(kitchen)) == 1


def test_a_review_with_no_verdict_is_not_told_while_its_reviewer_is_at_work(short, kitchen):
    kitchen.t3.thread("alpha", title="review: alpha")
    short.out(ready.NO_VERDICT, result=UNJUDGED.format(saw=short.saw), review=False)
    short.passes(5)
    assert sends(kitchen) == []


def unruled(short):
    command = f"git range-diff --no-color {short.start}..{short.saw} {short.start}..{short.head}"
    return ready.SCOPED_UNRULED.format(files="a.py", command=command)


def says_unruled(short):
    scoped = f"/pr-review run alpha scoped {short.start}..{short.saw} {short.start}..{short.head}"
    return (
        "No scoped review ruled yet on the drops your Result explains. "
        f"Where the Result has no `Scoped reviewer:` line of {short.head}, launch ONE scoped "
        'reviewer, not a full review, the way the crew skill\'s "The review" launches a reviewer, '
        f"with the message `{scoped}`, and add `Scoped reviewer: <threadId>, of {short.head}` to "
        "the Result. Where it has one and that "
        "thread ended its turn with no `## Review`, send that thread the same line with "
        "`t3_thread_send`, and launch no second one. Push nothing and do not rebase until its "
        "`## Review` is written."
    )


def test_drops_no_scoped_review_ruled_on_are_told_once_whoever_tells_first(short, kitchen):
    """`jbus.rebase` asks for the scoped review on the first pass, and the row is of the same kind,
    so the crew hears of the head once, never twice."""
    short.out(unruled(short))
    short.passes(9)
    assert [one["clientRequestId"] for one in sends(kitchen)] == [
        f"rereview|alpha|{short.head[:12]}"
    ]


def test_drops_whose_scoped_reviewer_ended_with_no_review_tell_the_crew_its_line(short, kitchen):
    """`jbus.rebase` asks nothing where the Result names a scoped reviewer of the head. That
    reviewer ended its turn with no `## Review`, so this row is the one that tells the crew."""
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha, scoped")
    named = f"Scoped reviewer: {reviewer['threadId']}, of {short.head}\n"
    short.out(unruled(short), result=named)
    short.passes(2)
    assert sends(kitchen) == []
    said = short.passes(1)
    assert sends(kitchen) == [said_to(short, "rereview", unruled(short), says_unruled(short))]
    scoped = f"/pr-review run alpha scoped {short.start}..{short.saw} {short.start}..{short.head}"
    line = f"expedite alpha: told the crew what #7 is short of (rereview, {short.head[:12]}), "
    assert line + f"sent `{scoped}`" in said
    short.passes(6)
    assert len(sends(kitchen)) == 1


@pytest.mark.parametrize(
    ("kind", "word", "reason"),
    [
        ("no-head", "wait", ready.NO_HEAD),
        ("fresh-conflict", "wait", ready.FRESH_CONFLICT),
        (
            "merged-tree",
            "wait",
            ready.MERGED_TREE_FAILS.format(base="main", tip="a" * 12, guard="test_a.py"),
        ),
        ("base", "wait", ready.BASE.format(base="other", default="main")),
        ("not-upheld", "hold", ready.NOT_UPHELD.format(user="user", refused="a.py")),
        ("rereview", "wait", ready.SCOPED_UNRULED.format(files="a.py", command="nothing")),
    ],
)
def test_each_new_row_as_jmerge_gives_it_tells_the_crew_once_in_words_it_can_run(
    kind, word, reason, short, kitchen
):
    """Each sentence is formatted with the pull request's own fields, so a stray brace would fail
    the pass. A scoped review whose reason names no range-diff takes its ranges from the head the
    crew kept before its rebase, as the `unruled` row does."""
    short.out(reason, word)
    said = short.passes(3)
    assert not [line for line in said if line.startswith("pass failed")]
    (sent,) = sends(kitchen)
    assert sent["clientRequestId"] == f"{kind}|alpha|{short.head[:12]}"
    assert f"({reason})" in sent["message"] and "{" not in sent["message"]
    if kind == "rereview":
        ranges = f"{short.start}..{short.saw} {short.start}..{short.head}"
        assert f"`/pr-review run alpha scoped {ranges}`" in sent["message"]
    short.passes(6)
    assert len(sends(kitchen)) == 1


def test_a_scoped_review_with_no_range_anywhere_tells_no_crew_and_fails_no_pass(short, kitchen):
    kitchen.git("update-ref", "-d", f"refs/jstack/pre-rebase/alpha/{short.saw[:12]}")
    short.out(ready.SCOPED_UNRULED.format(files="a.py", command="nothing"))
    said = short.passes(3)
    assert not [line for line in said if line.startswith("pass failed")]
    assert f"wait alpha: {expedite.NO_RANGES}" in said
    short.passes(3)
    assert sends(kitchen) == []
