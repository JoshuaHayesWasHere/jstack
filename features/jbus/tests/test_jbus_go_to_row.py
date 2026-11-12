"""A plan entry with the user's go and no row gets its first row on the next pass, not when its
home next thinks of it.

The merge-rate scout found a go reached a queued row a mean 2.25 h later over a night of 71 merged
rows: `jbus plan go` refused an entry with no row, so the go waited, unrecorded, until its home
wrote the brief and queued the row, and no pass knew of it. Now the home records the go when the
user gives it, and each pass that sees a go holding over an entry with no row wakes the entry's
home, naming the entry and how long ago the go was said, until a row is queued under it
(`jbus.plan.owed`, `jbus.wakes.owed_items`). `jbus flow` reads, for each entry, the time from its
go to its first queued row (`jbus.flow.measure.go_to_queued`). The tests run the real commands and
the real pass against the kitchen's fakes.
"""

from datetime import UTC, datetime, timedelta

import pytest

from jbus import flow, questions
from jbus.flow import records
from test_jbus_entry_go import HOME, JVIEW_PLAN, MESSAGE, PLAN, Frozen, plan_go, queued
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_leftover import home


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "plan.md").write_text(PLAN)
    monkeypatch.setattr(questions, "datetime", Frozen)
    made.settings = jstack_config
    yield made
    made.close()


def wakes_of(kitchen, thread, key):
    """The messages of the one list sent to the thread that name the item `key`."""
    return [
        given["message"]
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send"
        and given["threadId"] == thread
        and given["clientRequestId"].startswith("wakes|")
        and f"- {key}:" in given["message"]
    ]


def test_a_go_on_an_entry_with_no_row_wakes_its_home_each_pass_until_its_first_row(kitchen):
    """The root's plan entry epic gets the user's go, 30 minutes before the pass, and no row. The
    pass wakes the home that briefs it with the entry and the time since the go, the next pass
    wakes it again, and once a row is queued under the entry no pass wakes it for that."""
    root = home(kitchen)["threadId"]
    code, said = plan_go(kitchen)
    assert code == 0, said
    assert "no row yet" in said
    kitchen.poll(NOW)
    (first,) = wakes_of(kitchen, root, "owed epic")
    assert "- owed epic: go 2026-10-12 10:30" in first
    assert "30 min ago, no row yet" in first
    assert "jbus queue add <slug> --entry epic" in first
    kitchen.poll(NOW + timedelta(minutes=5))
    later = wakes_of(kitchen, root, "owed epic")
    assert len(later) == 2
    assert "35 min ago, no row yet" in later[1]
    queued(kitchen, "alpha")
    kitchen.poll(NOW + timedelta(minutes=10))
    assert len(wakes_of(kitchen, root, "owed epic")) == 2


def test_a_scoped_entry_with_a_go_and_no_row_wakes_its_scope_and_not_the_root(kitchen):
    root, scoped = home(kitchen)["threadId"], home(kitchen, "jview")["threadId"]
    (kitchen.home / "jview" / "plan.md").write_text(JVIEW_PLAN)
    kitchen.t3.says(HOME, MESSAGE, "go on jv-build")
    code, said = kitchen.main(
        "plan", "go", "jv-build", "--scope", "jview", "--message", f"{HOME}/{MESSAGE}"
    )
    assert code == 0, said
    kitchen.poll(NOW)
    (woke,) = wakes_of(kitchen, scoped, "owed jview/jv-build")
    assert "30 min ago, no row yet" in woke
    assert "jbus queue add <slug> --entry jv-build" in woke
    assert wakes_of(kitchen, root, "owed jview/jv-build") == []


def test_an_entry_with_no_go_and_no_row_wakes_no_one(kitchen):
    """The decision of the brief: only an entry that holds the user's go is acted on."""
    root = home(kitchen)["threadId"]
    kitchen.poll(NOW)
    assert wakes_of(kitchen, root, "owed epic") == []
    assert wakes_of(kitchen, root, "owed other") == []


def test_flow_reports_the_time_from_each_entrys_go_to_its_first_queued_row():
    """Two entries: slow's go was said at 22:12 EDT and its row proposed at 06:49 the next
    morning; fast's go at 10:00 and its row at 10:06, its second row an hour later. Flow gives
    each entry its own minutes, and the median over the window."""
    lines = [
        '{"at": "2026-10-13T10:49:00+00:00", "event": "item.proposed", '
        '"line": "item demo: w1 proposed, slow-1: jbus queue add slow-1"}',
        '{"at": "2026-10-13T10:49:10+00:00", "event": "item.approved", "line": "item demo: w1 '
        "approved: row slow-1 has a go: your go for the plan entry slow, 2026-10-12 22:12 EDT, "
        "in home: demo; run 2026-10-13 06:49 EDT by jbus's pass\"}",
        '{"at": "2026-10-13T14:06:00+00:00", "event": "item.proposed", '
        '"line": "item demo: w2 proposed, fast-1: jbus queue add fast-1"}',
        '{"at": "2026-10-13T14:06:05+00:00", "event": "item.approved", "line": "item demo: w2 '
        "approved: row fast-1 has a go: your go for the plan entry fast, 2026-10-13 10:00 EDT, "
        "in home: demo; run 2026-10-13 10:06 EDT by jbus's pass\"}",
        '{"at": "2026-10-13T15:06:05+00:00", "event": "item.approved", "line": "item demo: w3 '
        "approved: row fast-2 has a go: your go for the plan entry fast, 2026-10-13 10:00 EDT, "
        "in home: demo; run 2026-10-13 11:06 EDT by jbus's pass\"}",
    ]
    project = records.events("demo", lines)
    since = datetime(2026, 10, 12, tzinfo=UTC)
    until = datetime(2026, 10, 14, tzinfo=UTC)
    said = flow.build([project], [], [], {}, {}, since, until)
    went = said["go_to_queued"]
    assert went["entries"] == [
        {"project": "demo", "entry": "slow", "go": "2026-10-13T02:12:00+00:00", "minutes": 517.0},
        {"project": "demo", "entry": "fast", "go": "2026-10-13T14:00:00+00:00", "minutes": 6.0},
    ]
    assert went["median_minutes"] == pytest.approx(261.5)
    shown = flow.text(said | {"missing": []})
    assert "go to queued: 2 entries, median 261.5 min" in shown
    assert "  demo/slow: 517.0 min" in shown
