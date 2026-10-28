"""The two days the overview is shot over, `T` and the overloaded `MANY` (`days.DAYS`), give
the counts they are made for, as `/stack.json` and `/panel/pipeline.json` answer them."""

from collections import Counter

import pytest

from view.days import DAYS
from view.scene import Served


@pytest.fixture
def answers(scene, request):
    """What the server says of the day `request.param` names: `/stack.json` and the board."""
    DAYS[request.param](scene)
    served = Served(scene)
    try:
        return served.json("/stack.json"), served.json("/panel/pipeline.json")["data"]
    finally:
        served.close()


def stages(board):
    return {one["key"]: one["count"] for one in board["stages"] if one["count"]}


def homes(stack):
    return {one["name"]: one["open"] for one in stack["projects"][0]["homes"]}


def check(stack):
    found = next(one for one in stack["slow"]["stages"] if one["key"] == "check")
    return found["rows"], found["checks"]


@pytest.mark.parametrize("answers", ["t"], indirect=True)
def test_the_t_moment_has_44_open_over_four_homes_and_18_failing_checks(answers):
    """44 open: the root 20, jview 15, flow 8 and macos 1. On the step check 36: 18 failing,
    2 running or queued, 6 passed, 2 with no run and 8 stacked, of which one held and one left
    wait on the user beside the row at its gate and the hold, so Needs you is 4. 6 gates go
    ahead on their default, and 27 merged today."""
    stack, board = answers
    project = stack["projects"][0]
    assert (project["open"], project["merged"]) == (44, 27)
    assert homes(stack) == {"": 20, "jview": 15, "flow": 8, "macos": 1}
    assert check(stack) == (36, {"failing": 18, "waiting": 2, "passed": 6, "stacked": 8})
    assert (len(stack["needs"]), len(stack["proceeds"])) == (4, 6)
    assert sorted(one["kind"] for one in stack["needs"]) == ["held", "hold", "left", "row"]
    assert stages(board) == {
        "crew": 4,
        "you": 4,
        "review2": 2,
        "check": 28,
        "stacked": 6,
        "merged": 27,
    }
    assert Counter(one["home"] for one in board["rows"]) == {
        "root": 20,
        "jview": 15,
        "flow": 8,
        "macos": 1,
    }
    waits = Counter(one["wait"] for one in board["rows"] if one["stage"] == "check")
    assert waits == {"failing": 18, "waiting": 2, "passed": 6, None: 2}


@pytest.mark.parametrize("answers", ["many"], indirect=True)
def test_the_overloaded_day_has_44_open_12_behind_its_head_and_7_on_the_user(answers):
    """44 open over the root, jview and flow: 12 behind `tea-kettle`, which is not approved,
    8 ready for a launch slot, and 7 that wait on the user, 4 to approve and 3 at a gate. 8
    gates go ahead on their default, and 12 merged today."""
    stack, board = answers
    project = stack["projects"][0]
    assert (project["open"], project["merged"]) == (44, 12)
    assert homes(stack) == {"": 19, "jview": 14, "flow": 12}
    assert (len(stack["needs"]), len(stack["proceeds"])) == (7, 8)
    assert Counter(one["kind"] for one in stack["needs"]) == {"approve": 4, "row": 3}
    behind = [one for one in board["rows"] if one["stage"] == "queued" and one["waits_on"]]
    assert {one["head"] for one in behind} == {"tea-kettle"}
    assert len(behind) == 12
    assert stages(board) == {
        "queued": 20,
        "crew": 6,
        "you": 7,
        "review": 4,
        "fix": 2,
        "review2": 1,
        "check": 3,
        "merge": 2,
        "merged": 12,
    }
