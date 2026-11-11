"""A `Status:` line that says `done` and a note in parentheses is done to every reader in jbus,
as `jbriefs.status` reads it: a scout's row ends done, not left, and a crew's Result leaves
nothing."""

from datetime import timedelta

import pytest

from jbus import mirror, watch, work
from test_jbus_entry_go import PLAN
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import go, rows
from test_jbus_scout import add, judged, reported, scout_thread

NOTED = "done (both ran the same cases)"


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    (made.home / "plan.md").write_text(PLAN)
    yield made
    made.close()


def test_a_scout_whose_report_says_done_with_a_note_ends_done_not_left(kitchen):
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    scout_thread(kitchen, "look")["status"] = "running"
    reported(kitchen, "look", status=NOTED)
    scout_thread(kitchen, "look")["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=3))

    assert rows(kitchen)["look"]["status"] == "done"
    assert judged(kitchen, "look")["scout"] == "report in"


def test_a_scout_whose_report_says_done_with_a_clause_stays_left(kitchen):
    add(kitchen, "look")
    assert go(kitchen, "look")[0] == 0
    kitchen.poll()
    scout_thread(kitchen, "look")["status"] = "running"
    reported(kitchen, "look", status="done, mostly")
    scout_thread(kitchen, "look")["status"] = "completed"
    kitchen.poll(NOW + timedelta(minutes=3))

    assert rows(kitchen)["look"]["status"] == "left"


RESULT = f"## Result\nStatus: {NOTED}\nBranch: look   Pull request: none\nLeft: none\n"


def test_a_crews_result_that_says_done_with_a_note_leaves_nothing():
    assert watch.left(RESULT) == ""
    assert watch.written(RESULT) == work.Written.CLEAN


def test_a_paused_result_with_a_note_waits_on_its_rows():
    result = "## Result\nStatus: paused (until a-b merges)\nWaits on: a-b\n"
    assert mirror.paused_on(result, {"a-b"}) == ("a-b",)
