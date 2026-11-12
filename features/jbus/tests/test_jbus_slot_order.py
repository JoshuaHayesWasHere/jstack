"""A pass hands a free slot to the row that waits with the best priority it inherits, and among
rows of the same priority to the one that has waited longest (`queue.order`). A row inherits the
priority of a paused row whose Result's `Waits on:` names it, and of a launched row whose
`depends` names it. `jbus.dispatch.turns` reads each paused Result's `Waits on:` and sorts the
rows it hands out by that order."""

import json
from datetime import timedelta

import pytest

from jbus import queue
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add

PAUSED = (
    "\n## Result\nStatus: paused, at {head}\nDone when: the plan: does not hold\n"
    "Waits on: {rows}\nBranch: {slug}   Pull request: none\nLeft: waits on {rows}\n"
)
AT = NOW
"""The kitchen's clock stands for 22:22Z on 2026-11-11, when st-site-legend began to wait."""


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def launched(kitchen):
    crews = (one["title"] for one in kitchen.t3.launches if one["title"].startswith("crew: "))
    return [title.removeprefix("crew: ") for title in crews]


def end(kitchen, slug):
    """End the turn of the slug's crew thread, so it no longer holds a slot."""
    for thread in kitchen.t3.threads:
        if thread["title"] == f"crew: {slug}":
            thread["status"] = "completed"
            kitchen.t3.at_work.discard(thread["threadId"])


def test_the_2026_11_11_queue_launches_the_row_a_paused_row_waits_on_then_the_oldest(kitchen):
    """The statecharts home's queue of 2026-11-11, from 22:22Z: the home is at `max_per_home`,
    st-model-plan-scope (priority 3) has paused on st-site-legend (priority 50), and three more
    rows of priority 50 wait for a slot, st-gh-log-rotate-lock the newest of them."""
    kitchen.config(max_running=40, max_per_home=3)
    add(kitchen, "st-model-plan-scope", priority=3)
    add(kitchen, "st-busy-one", priority=1)
    add(kitchen, "st-busy-two", priority=1)
    kitchen.poll(AT - timedelta(minutes=30))
    assert sorted(launched(kitchen)) == ["st-busy-one", "st-busy-two", "st-model-plan-scope"]
    kitchen.config(max_running=40, max_per_home=2)

    add(kitchen, "st-retire-carries-fixes", priority=50)
    add(kitchen, "st-site-legend", priority=50)
    end(kitchen, "st-model-plan-scope")
    path = kitchen.home / "tasks" / "st-model-plan-scope.md"
    paused = PAUSED.format(head="e" * 12, rows="st-site-legend", slug="st-model-plan-scope")
    path.write_text(path.read_text() + paused)
    kitchen.poll(AT)
    add(kitchen, "st-tellonce-groups", priority=50)
    kitchen.poll(AT + timedelta(minutes=16))
    add(kitchen, "st-gh-log-rotate-lock", priority=50)
    kitchen.poll(AT + timedelta(minutes=28))
    assert len(launched(kitchen)) == 3

    end(kitchen, "st-busy-one")
    kitchen.poll(AT + timedelta(minutes=29))
    assert launched(kitchen)[3:] == ["st-site-legend"]

    for minute, ending in enumerate(("st-busy-two", "st-site-legend", "st-retire-carries-fixes")):
        end(kitchen, ending)
        kitchen.poll(AT + timedelta(minutes=30 + minute))
    assert launched(kitchen)[3:] == [
        "st-site-legend",
        "st-retire-carries-fixes",
        "st-tellonce-groups",
        "st-gh-log-rotate-lock",
    ]


def test_a_row_a_launched_row_depends_on_inherits_its_priority(kitchen):
    """A launched row whose `depends` names a row still queued waits on it, so that row launches
    ahead of an older row of its own priority."""
    kitchen.config(max_running=40, max_per_home=2)
    add(kitchen, "busy", priority=1)
    add(kitchen, "filler", priority=1)
    kitchen.poll(AT - timedelta(minutes=30))
    add(kitchen, "an-old", priority=50)
    kitchen.poll(AT - timedelta(minutes=20))
    add(kitchen, "zz-base", priority=50)
    kitchen.poll(AT - timedelta(minutes=10))
    path = kitchen.state / "queue.json"
    table = json.loads(path.read_text())
    for row in table:
        if row["slug"] == "busy":
            row["depends"] = ["zz-base"]
    path.write_text(json.dumps(table))

    end(kitchen, "filler")
    kitchen.poll(AT)
    assert launched(kitchen)[2:] == ["zz-base"]


def test_a_lift_runs_down_a_chain_of_waits_and_a_row_that_is_over_lifts_nothing():
    rows = [
        {"slug": "paused", "priority": 3, "status": "left"},
        {"slug": "launched", "priority": 50, "status": "running", "depends": ["base"]},
        {"slug": "base", "priority": 80, "status": "queued", "depends": ["root"]},
        {"slug": "root", "priority": 90, "status": "queued"},
        {"slug": "merged", "priority": 1, "status": "merged", "depends": ["root"]},
    ]
    lift = queue.lifted(rows, {"paused": ["launched"], "merged": ["root"]})
    assert lift == {"paused": 3, "launched": 3, "base": 3, "root": 90, "merged": 1}
    ordered = sorted(rows, key=lambda row: queue.order(row, lift))
    assert [row["slug"] for row in ordered] == ["merged", "base", "launched", "paused", "root"]
