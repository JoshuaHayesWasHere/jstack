"""The root home is woken of a one-way door alone (`jbus.wakes.door`).

The user, 2026-11-08, in the root-hierarchy home: "we never have any random \"agent jbus\" message
in this root home ... the child homes don't bubble up messages unless it's a one way door
scenario". The scout rh-every-row-in-a-child-home counted what woke the root in the 7 days to
2026-11-08: approve 177, left 77, stale 74, home-stall 25, question 18, ci 17, alert 16, owed 13,
stall 10, rulefile 8, prose 3, main 2, brief 2, unasked 1. A kind's route does not depend on how
many of it there are, so one of each stands for its count.

The replay places ten of the kinds in one kitchen, by the source jbus reads each from (approve,
which wakes no thread since #1292, left, stale, home-stall, question, ci, alert, rulefile, prose,
main), beside a gate that holds, and runs the real pass over it past `leftover.CLOSE_MINUTES`,
when the late copies went out. The other four are shown by a test of their own: owed
(`test_jbus_entry_go.py`), stall (`test_jbus_clock.py`), unasked (`view/test_view_owner.py`),
and brief, an entry of a plan routed as owed is (`wakes._plan_home`).
"""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import alert, leftover, passes, t3, wakes
from test_jbus_kitchen import NOW, Kitchen, sends
from test_jbus_leftover import ended, home
from test_jbus_queue import add, brief
from test_jbus_wakes import runs

MIN = timedelta(minutes=1)
DOOR = "Should the old state tree be deleted?"
ASKED = "Which name should the sidebar's new row take?"
GATES = f"""## Gate 1: {DOOR}
Status: open
Asked by: home, thread mcp:home
Default: keep it, and hold for the answer
Built on it: nothing
Undo: nothing to undo
Holds: deletes data
Fail-safe: a bundle at /tmp/tree.bundle

## Gate 2: {ASKED}
Status: open
Asked by: pa-name, thread mcp:crew
Built on it: nothing
Undo: rename it
"""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def items(kitchen, thread):
    """The item lines of each one-list message the thread got."""
    return [
        line
        for given in sends(kitchen)
        if given["threadId"] == thread and given["clientRequestId"].startswith("wakes|")
        for line in given["message"].splitlines()
        if line.startswith("- ")
    ]


def test_the_seven_day_mix_wakes_the_root_of_its_one_way_doors_alone(kitchen):
    root = home(kitchen)["threadId"]
    catchall = home(kitchen, "uncategorized")["threadId"]
    pantry = home(kitchen, "pantry")["threadId"]
    kitchen.quiet()
    for slug in ("pa-approve", "pa-name"):
        text = brief(slug).replace("Home: uncategorized\n", "Home: pantry\n")
        add(kitchen, slug, approve=False, text=text)
        kitchen.brief(slug, "Home: pantry\n")
    (kitchen.home / "gates.md").write_text(GATES)
    ended(kitchen, "pa-left", head="Home: pantry\n")
    runs(kitchen, "dependabot/pip/oat")
    (kitchen.home / "standing.md").write_text("1. Never do the thing.\n")
    (kitchen.home / "holds.json").write_text(json.dumps({"5": "a" * 40}))
    jbus.write_json(
        kitchen.state / "main.json", {"at": NOW.isoformat(), "main": "b" * 40, "check": "failed"}
    )
    config = jbus.load()
    for key, line in (
        ("home-stall pantry", "alert: home pantry is quiet with 1 out, 3 nudges"),
        ("once 1", "alert: demo: the main checkout is not pulled"),
        ("once 2", "alert: demo: install.sh was not run again after a merge"),
        (alert.SNAPSHOT, "alert: snapshot failed 3 times"),
    ):
        alert.raise_(config, key, line, owner="demo", now=NOW)
    plan = kitchen.home / "pantry" / "plan.md"
    plan.write_text("# pantry\n")
    kitchen.poll(NOW)
    plan.write_text("# pantry\n\n- brief the rename once the sidebar lands\n")
    for minutes in (1, 10, 20, 31, 45, leftover.CLOSE_MINUTES * 3):
        kitchen.poll(NOW + minutes * MIN)
    door = f"- gate 1: {DOOR[:-1]}, it holds (deletes data) for your answer"
    assert items(kitchen, root) == [door]
    told = items(kitchen, catchall)
    for said in ("ci dependabot", "rulefile ", "home pantry is quiet", "not pulled", "install.sh"):
        assert [line for line in told if said in line], said
    told = items(kitchen, pantry)
    for said in (ASKED[:-1], "left pa-left", "prose:pantry/plan.md"):
        assert [line for line in told if said in line], said
    every = [line for thread in (root, catchall, pantry) for line in items(kitchen, thread)]
    assert not [line for line in every if line.startswith("- approve ")]
    quiet = json.loads(config.status_path.read_text())["projects"]["demo"]["quiet"]
    assert [line for line in quiet if line.startswith("jbus tidy stale: ")]


@pytest.mark.parametrize(
    ("need", "woken"),
    [
        ({"kind": "hold", "key": "#5", "number": 5, "line": "hold #5: a protected path"}, (1, 0)),
        ({"kind": "config", "key": "config:token", "line": "config: no token"}, (1, 0)),
        ({"kind": "approve", "key": "approve:pa-approve", "slug": "pa-approve"}, (0, 0)),
    ],
)
def test_a_hold_and_a_config_need_are_the_roots_and_a_row_to_approve_wakes_no_home(
    kitchen, need, woken
):
    """A row to approve waits on the user alone (#1292), and the root hears of the doors."""
    root = home(kitchen)["threadId"]
    pantry = home(kitchen, "pantry")["threadId"]
    text = brief("pa-approve").replace("Home: uncategorized\n", "Home: pantry\n")
    add(kitchen, "pa-approve", approve=False, text=text)
    kitchen.brief("pa-approve", "Home: pantry\n")
    since = (NOW - 30 * MIN).isoformat()
    listed = [{"line": f"{need['kind']} {need['key']}", "since": since} | need]
    jbus.write_json(kitchen.state / "wake.json", {"began": (NOW - 60 * MIN).isoformat()})
    config = jbus.load()
    run = passes.Pass(config, config.projects[0], NOW)
    wakes.tell(run, t3.Client(config.server, config.token_path), listed)
    assert (len(items(kitchen, root)), len(items(kitchen, pantry))) == woken
