"""A reason of `jmerge`'s `result` step is a wait its crew hears of, as `test_jbus_expedite.py`'s
reasons are. #1004 added eight `Proved:` reasons, none had a row of `expedite.TABLE`, and by the
next hour eight green pull requests sat held on them with their crews idle. The table is held to
`jmerge.ready` here, so the next reason of that step cannot be quiet the same way. The pass tests
run the real pass against the kitchen's fakes, as `test_jbus_expedite.py` does."""

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


def test_every_reason_of_the_result_step_is_a_row_a_crew_is_told_or_one_no_crew_can_fix():
    rows = {row.reason.code: row for row in expedite.TABLE}
    result = {one.code for one in ready.reasons().values() if one.step == "result"}
    told = result - set(expedite.UNTOLD)
    assert set(expedite.UNTOLD) <= result
    assert set(expedite.UNTOLD).isdisjoint(rows)
    assert {code for code in told if code not in rows} == set()
    for code in told:
        assert rows[code].word == judgement.verb(rows[code].reason) == "wait", code


def test_the_proof_step_a_crew_is_sent_to_is_the_one_do_the_task_has():
    said = (REPO / "features/crew/do-the-task.md").read_text()
    assert f"- {expedite.PROVE_STEP}:" in said
    proved = [row for row in expedite.TABLE if row.kind.startswith("proved-")]
    assert len(proved) == 8
    assert all(expedite.PROVE_STEP in row.sentence for row in proved)


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
