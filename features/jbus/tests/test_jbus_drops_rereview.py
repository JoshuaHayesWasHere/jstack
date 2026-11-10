"""The replay of fl-drops-rereview (FlowBlockers' DropsRulingWithoutHand), brought in from
`reports/fl-statechart-verified/replay/test_replay_fl_drops_rereview.py` and inverted. That replay
passed while the bug stood: a crew that explained each line its rebase dropped got no ask for the
scoped review that rules on them, and after two misses of the clock the wait reached the home,
which sent the review by hand (#453, 2026-10-26). jbus now launches that review itself, and the
crew hears nothing of a clean one. Like `test_jbus_clock.py`, it runs the real pass against the
kitchen's fakes."""

import pytest

from jmerge import ready
from test_jbus_clock import N, to
from test_jbus_expedite import Short
from test_jbus_leftover import home


@pytest.fixture
def short(kitchen):
    return Short(kitchen)


def test_explained_drops_get_one_scoped_reviewer_and_neither_crew_nor_home_is_told(short, kitchen):
    desk = home(kitchen)
    short.thread["worktreePath"] = "/worktrees/alpha"
    old, new = f"{short.start}..{short.saw}", f"{short.start}..{short.head}"
    unruled = ready.SCOPED_UNRULED.format(
        files="a.py", command=f"git range-diff --no-color {old} {new}"
    )
    said = f"Dropped on rebase: a.py, 2 of main's, 0 of its own, at {short.head[:12]}: on purpose\n"
    short.out(unruled, result=said)
    short.passes(2)
    (reviewer,) = [one for one in kitchen.t3.threads if one["title"] == "review: alpha, scoped"]
    (launch,) = [one for one in kitchen.t3.launches if one["title"] == "review: alpha, scoped"]
    assert launch["message"] == f"/pr-review run alpha scoped {old} {new}"
    assert to(kitchen, short.thread) == []
    said += f"Scoped reviewer: {reviewer['threadId']}, of {short.head}\n"
    short.out(unruled, result=said)
    short.passes(N - 1)
    review = "\n## Review\nVerdict: clean\nScope: range-diff\nDrops: upheld a.py\n"
    review += f"Head: {short.head}\n"
    short.out("", result=said + review)
    short.passes(3 * N)
    assert to(kitchen, short.thread) == []
    assert to(kitchen, reviewer) == [] and to(kitchen, desk) == []
