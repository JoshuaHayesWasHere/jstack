"""`jbus follow` restates a thread's line of `work.json` from T3 Code's events; the pass checks it.

The kitchen's T3 Code answers the pass. Beside it, `Events` stands in for T3 Code's store: the
table `orchestration_events` of `statev2.sqlite`, with the columns the follower reads, which a
test writes as T3 Code would. The follower runs as `jbus follow` does, in a thread of its own.
"""

import json
import sqlite3
import threading
import time
from datetime import timedelta

import pytest

import jbus
from jbus import follow, queue, restated, states, work
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add

WAIT = 3.0


class Events:
    """T3 Code's store, as far as the follower reads it."""

    def __init__(self, where):
        self.where = where
        where.parent.mkdir(parents=True, exist_ok=True)
        self.make()

    def make(self):
        with sqlite3.connect(self.where) as db:
            db.execute("pragma journal_mode = wal")
            db.execute(
                "create table orchestration_events (sequence integer primary key autoincrement,"
                " aggregate_kind text not null, stream_id text not null, event_type text not null,"
                " occurred_at text not null, payload_json text not null)"
            )
        db.close()

    def emit(self, thread, kind, status=None, at=NOW):
        payload = json.dumps({"threadId": thread, **({"status": status} if status else {})})
        occurred = at.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with sqlite3.connect(self.where) as db:
            db.execute(
                "insert into orchestration_events"
                " (aggregate_kind, stream_id, event_type, occurred_at, payload_json)"
                " values ('thread', ?, ?, ?, ?)",
                (thread, kind, occurred, payload),
            )
        db.close()

    def replace(self):
        """Put another file in the store's place, as a restore or a compaction into a copy does."""
        for one in self.where.parent.glob(self.where.name + "*"):
            one.unlink()
        self.make()


class Follower:
    def __init__(self, events):
        self.events, self.said = events, []
        self.start()
        until(lambda: any("from event" in one for one in self.said))

    def start(self):
        """Start the follower, as `jbus follow` starts: again after it stopped, too."""
        self.stop = threading.Event()
        self.thread = threading.Thread(
            target=follow.follow,
            args=(jbus.load(), self.said.append, self.stop, self.events.where),
            daemon=True,
        )
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(WAIT)


def until(check, wait=WAIT):
    end = time.monotonic() + wait
    while time.monotonic() < end:
        if check():
            return True
        time.sleep(0.01)
    return False


def line(kitchen, key="alpha"):
    kept = json.loads((kitchen.state / work.NAME).read_text())
    return {one["key"]: one for one in kept["work"]}[key]


def shows(kitchen, value, thread):
    return lambda: (line(kitchen)["value"], line(kitchen)["facts"]["thread"]) == (value, thread)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    monkeypatch.setattr(queue, "clock", lambda: NOW)
    monkeypatch.setenv("T3CODE_HOME", str(tmp_path / "t3"))
    yield made
    made.close()


@pytest.fixture
def events(tmp_path):
    return Events(tmp_path / "t3" / "userdata" / "statev2.sqlite")


@pytest.fixture
def follower(kitchen, events):
    made = Follower(events)
    yield made
    made.close()


def lost_row(kitchen):
    """A row whose thread ended with nothing written: the pass judges it lost."""
    add(kitchen, "alpha")
    kitchen.poll()
    (thread,) = kitchen.t3.threads
    thread.update(status="completed")
    kitchen.poll(NOW + timedelta(minutes=3))
    assert (line(kitchen)["value"], line(kitchen)["thread"]) == ("lost", thread["threadId"])
    return thread


def test_a_turn_that_starts_shows_before_any_pass_and_the_pass_reads_the_same(
    kitchen, events, follower
):
    thread = lost_row(kitchen)
    events.emit(thread["threadId"], "run.updated", "running", NOW + timedelta(minutes=4))
    assert until(shows(kitchen, "working", "moving"))
    assert line(kitchen)[restated.FOLLOWED] == restated.moment(NOW + timedelta(minutes=4))
    thread.update(status="running")
    kitchen.poll(NOW + timedelta(minutes=5))
    assert (line(kitchen)["value"], line(kitchen)["facts"]["thread"]) == ("working", "moving")
    assert kitchen.events(states.DRIFT) == []


def test_a_question_and_its_answer_show_before_any_pass(kitchen, events, follower):
    thread = lost_row(kitchen)
    events.emit(thread["threadId"], "run.updated", "waiting", NOW + timedelta(minutes=4))
    assert until(shows(kitchen, "waiting", "waiting"))
    assert line(kitchen)["who"] == "user"
    events.emit(thread["threadId"], "run.updated", "running", NOW + timedelta(minutes=5))
    assert until(shows(kitchen, "working", "moving"))


def test_a_turn_that_ends_with_nothing_written_is_left_for_the_pass_to_call_lost(
    kitchen, events, follower
):
    thread = lost_row(kitchen)
    events.emit(thread["threadId"], "run.updated", "running", NOW + timedelta(minutes=4))
    assert until(shows(kitchen, "working", "moving"))
    events.emit(thread["threadId"], "run.updated", "completed", NOW + timedelta(minutes=6))
    events.emit(thread["threadId"], "thread.settled", at=NOW + timedelta(minutes=6))
    assert not until(lambda: line(kitchen)["facts"]["thread"] != "moving", wait=0.5)
    thread.update(status="completed", settled=True)
    kitchen.poll(NOW + timedelta(minutes=7))
    assert (line(kitchen)["value"], line(kitchen)["facts"]["thread"]) == ("lost", "settled")
    assert kitchen.events(states.DRIFT) == []


def test_a_settled_thread_whose_result_is_written_shows_settled_and_done(kitchen, events, follower):
    add(kitchen, "alpha")
    kitchen.poll()
    (thread,) = kitchen.t3.threads
    kitchen.brief(
        "alpha", "\n## Result\nStatus: done\nBranch: alpha   Pull request: none\nLeft: none\n"
    )
    thread.update(status="running")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert (line(kitchen)["value"], line(kitchen)["facts"]["thread"]) == ("done", "moving")
    events.emit(thread["threadId"], "run.updated", "completed", NOW + timedelta(minutes=2))
    assert until(shows(kitchen, "done", "completed"))
    events.emit(thread["threadId"], "thread.settled", at=NOW + timedelta(minutes=3))
    assert until(shows(kitchen, "done", "settled"))


def test_an_event_after_the_pass_began_outlives_a_pass_that_read_t3_code_before_it(
    kitchen, events, follower
):
    thread = lost_row(kitchen)
    events.emit(thread["threadId"], "run.updated", "running", NOW + timedelta(minutes=10))
    assert until(shows(kitchen, "working", "moving"))
    kitchen.poll(NOW + timedelta(minutes=9))
    assert (line(kitchen)["value"], line(kitchen)["facts"]["thread"]) == ("working", "moving")
    assert kitchen.events(states.DRIFT) == []


def test_a_lost_stream_is_opened_again_and_the_pass_corrects_what_it_missed_as_drift(
    kitchen, events, follower
):
    thread = lost_row(kitchen)
    follower.close()
    events.emit(thread["threadId"], "run.updated", "running", NOW + timedelta(minutes=4))
    follower.start()
    assert until(lambda: sum("from event" in one for one in follower.said) == 2)
    assert not until(lambda: line(kitchen)["value"] != "lost", wait=0.3)
    events.replace()
    assert until(lambda: any("the stream is lost" in one for one in follower.said))
    assert until(lambda: sum("from event" in one for one in follower.said) == 3)
    assert follower.said[-1].endswith("from event 0")
    record = jbus.read_json(kitchen.state_dir / restated.FOLLOW, {})
    assert record["lost"] == 1 and "another file" in record["why"]
    thread.update(status="running")
    kitchen.poll(NOW + timedelta(minutes=5))
    assert (line(kitchen)["value"], line(kitchen)["facts"]["thread"]) == ("working", "moving")
    drifted = [one["line"] for one in kitchen.events(states.DRIFT)]
    assert drifted == ["work-drift alpha: thread 'completed' for 'moving'"]
    events.emit(thread["threadId"], "run.updated", "waiting", NOW + timedelta(minutes=6))
    assert until(shows(kitchen, "waiting", "waiting"))


def test_with_no_follower_a_thread_s_facet_is_no_drift(kitchen):
    thread = lost_row(kitchen)
    thread.update(status="running")
    kitchen.poll(NOW + timedelta(minutes=5))
    assert line(kitchen)["value"] == "working"
    assert kitchen.events(states.DRIFT) == []


def test_an_event_read_twice_or_after_a_later_one_writes_nothing(kitchen):
    thread = lost_row(kitchen)
    later, earlier = (
        restated.moment(NOW + timedelta(minutes=5)),
        restated.moment(NOW + timedelta(minutes=4)),
    )
    assert restated.followed(kitchen.state, thread["threadId"], work.Thread.MOVING, later) == [
        "alpha"
    ]
    written = (kitchen.state / work.NAME).read_text()
    assert restated.followed(kitchen.state, thread["threadId"], work.Thread.MOVING, later) == []
    assert restated.followed(kitchen.state, thread["threadId"], work.Thread.WAITING, earlier) == []
    assert (kitchen.state / work.NAME).read_text() == written


def test_each_event_gives_the_facet_the_pass_gives_the_status_it_leaves():
    said = {
        ("run.updated", "running"): work.Thread.MOVING,
        ("run.updated", "waiting"): work.Thread.WAITING,
        ("run.updated", "completed"): work.Thread.COMPLETED,
        ("run.updated", "interrupted"): work.Thread.FAILED,
        ("run.updated", "failed"): work.Thread.FAILED,
        ("run.created", "queued"): None,
        ("run.created", "starting"): None,
        ("thread.settled", None): work.Thread.SETTLED,
        ("thread.archived", None): work.Thread.ARCHIVED,
    }
    assert {key: follow.facet(*key) for key in said} == said
