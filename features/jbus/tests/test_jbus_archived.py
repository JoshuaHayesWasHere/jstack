"""A thread a home archived, or one T3 Code no longer has, is still its row's thread.

T3 Code's list of a project's threads leaves archived ones out and cannot be asked for them.
A row that ended must stay as it ended when its thread drops out of that list, and a row
that is still at work must be said, not launched again. Run as `test_jbus_queue.py`
runs: the real pass, against a faked T3 Code server (whose list leaves archived threads
out, as T3 Code's does), `gh` and `jmerge`."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import item, work
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, rows

PULL = "https://example.test/pull/9"


def result(left="none", status="done"):
    return f"\n## Result\nStatus: {status}\nBranch: alpha   Pull request: none\nLeft: {left}\n"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def judged(kitchen, key="alpha"):
    kept = json.loads((kitchen.state / work.NAME).read_text())
    return {one["key"]: one for one in kept["work"]}[key]


def launched(kitchen, slug="alpha", more=""):
    """A row that was approved and launched, whose thread then ended and wrote `more`."""
    add(kitchen, slug)
    kitchen.poll()
    (thread,) = kitchen.t3.threads
    thread["status"] = "completed"
    if more:
        path = kitchen.home / "tasks" / f"{slug}.md"
        path.write_text(path.read_text() + more)
    assert len(kitchen.t3.launches) == 1
    return thread


ENDINGS = {
    "done": (result(), "done"),
    "left": (result("a word from the user"), "left"),
}
GONE = {
    "archived": lambda kitchen, thread: thread.update(archived=True),
    "missing": lambda kitchen, thread: kitchen.t3.threads.clear(),
}


@pytest.mark.parametrize("how", GONE)
@pytest.mark.parametrize("ending", ENDINGS)
def test_a_row_that_ended_stays_as_it_ended_when_its_thread_leaves_the_list(kitchen, ending, how):
    more, status = ENDINGS[ending]
    thread = launched(kitchen, more=more)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert rows(kitchen)["alpha"]["status"] == status
    GONE[how](kitchen, thread)
    for minutes in (6, 9, 12):
        kitchen.poll(NOW + timedelta(minutes=minutes))
        assert rows(kitchen)["alpha"]["status"] == status
        assert judged(kitchen)["confirmed"]
    assert len(kitchen.t3.launches) == 1 and kitchen.lines("gate") == []


def test_a_merged_row_stays_merged_when_its_thread_is_archived(kitchen):
    thread = launched(kitchen, more=result())
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    thread["archived"] = True
    for minutes in (3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
        assert rows(kitchen)["alpha"]["status"] == "merged"
    assert len(kitchen.t3.launches) == 1


def test_a_thread_that_is_missing_is_told_apart_from_one_that_was_never_launched(kitchen):
    thread = launched(kitchen, more=result())
    add(kitchen, "beta", approve=False)
    kitchen.t3.threads.remove(thread)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert judged(kitchen)["facts"]["thread"] == "missing"
    assert judged(kitchen)["facts"]["launch"] == "launched"
    assert judged(kitchen, "beta")["facts"]["thread"] == "none"
    assert judged(kitchen, "beta")["facts"]["launch"] == "none"


def test_an_archived_thread_is_the_rows_thread_and_unarchiving_it_changes_nothing(kitchen):
    thread = launched(kitchen, more=result())
    thread["archived"] = True
    kitchen.poll(NOW + timedelta(minutes=3))
    assert judged(kitchen)["facts"]["thread"] == "archived"
    assert rows(kitchen)["alpha"]["thread"] == thread["threadId"]
    thread["archived"] = False
    kitchen.poll(NOW + timedelta(minutes=6))
    assert judged(kitchen)["facts"]["thread"] == "completed"
    assert rows(kitchen)["alpha"]["status"] == "done"


@pytest.mark.parametrize("how", GONE)
def test_a_finished_row_whose_thread_is_gone_launches_nothing_and_takes_no_slot(kitchen, how):
    thread = launched(kitchen, more=result())
    GONE[how](kitchen, thread)
    add(kitchen, "beta", priority=2)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [given["title"] for given in kitchen.t3.launches] == ["crew: alpha", "crew: beta"]


def test_a_finished_row_with_no_item_is_given_none_when_its_thread_is_archived(kitchen):
    """Item w4's case: the finished row's go was used by its launch, and must not approve
    an item minted for it after."""
    thread = launched(kitchen, more=result())
    kitchen.poll(NOW + timedelta(minutes=3))
    (kitchen.state / item.NAME).unlink()
    jbus.write_json(kitchen.state / item.COUNTER, {"next": 4})
    table = json.loads((kitchen.state / "queue.json").read_text())
    for row in table:
        row.pop("item", None)
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    thread["archived"] = True
    for minutes in (6, 9):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert rows(kitchen)["alpha"]["status"] == "done"
    assert not (kitchen.state / item.NAME).exists()
    assert len(kitchen.t3.launches) == 1


def test_a_row_at_work_whose_thread_is_archived_is_said_once_and_not_launched_again(kitchen):
    add(kitchen, "alpha")
    kitchen.poll()
    (thread,) = kitchen.t3.threads
    thread["archived"] = True
    for minutes in (3, 6, 9):
        kitchen.poll(NOW + timedelta(minutes=minutes))
        assert judged(kitchen)["value"] == "lost"
        assert rows(kitchen)["alpha"]["status"] != "queued"
    assert len(kitchen.t3.launches) == 1
    said = kitchen.lines("stale")
    assert len(said) == 1 and thread["threadId"] in said[0] and "archived" in said[0]


def test_a_row_stays_as_it_was_while_t3_code_cannot_say_what_became_of_its_thread(kitchen):
    thread = launched(kitchen, more=result())
    kitchen.poll(NOW + timedelta(minutes=3))
    thread["archived"] = True
    kitchen.t3.lose_read = True
    kitchen.poll(NOW + timedelta(minutes=6))
    assert rows(kitchen)["alpha"]["status"] == "done"
    assert not judged(kitchen)["confirmed"]
    kitchen.t3.lose_read = False
    kitchen.poll(NOW + timedelta(minutes=9))
    assert rows(kitchen)["alpha"]["status"] == "done" and judged(kitchen)["confirmed"]
    assert len(kitchen.t3.launches) == 1


def test_a_row_never_launched_is_still_queued_when_no_thread_is_listed(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    assert rows(kitchen)["alpha"]["status"] == "queued"
