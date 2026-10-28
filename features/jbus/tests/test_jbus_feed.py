"""The feed: what changed since a bot's cursor, as versioned records, by `jbus feed` and by the
view's `GET /feed`, with a long poll, and a reset with the `needs` snapshot when the cursor is
unknown or expired. Each need carries its doors, so a bot can tell what it may not act on.

The tests run the real command and the real view server over a kitchen's state.
"""

import http.client
import json
import threading
import time
from datetime import UTC, datetime, timedelta

import pytest

import jbus
import jsettings
from jbus import feed, wake
from jbus import view as jview
from jbus.view import state as view_state
from jbus.view.panels.you import panel as you
from test_jbus_acts import CHAT, HOLDS, Route, bot_go, gate, stored
from test_jbus_kitchen import GATE, Kitchen
from test_jbus_queue import add, brief, sha12
from view.scene import free_port

FIELDS = ("project", "slug", "sha", "kind", "what", "default", "since", "doors")
"""What the bots asked to see of each item that waits on the user
(scouts/bot-authority-shape.bots-reply.md, item 4): project, slug and the brief's sha, its
kind, the exact ask, the default, when it started waiting, and whether it is a one-way door."""
EVENT = ("v", "id", "at", "project", "kind", "subject", "line", "need", "act")


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


@pytest.fixture
def route(kitchen):
    made = Route(kitchen)
    yield made
    made.close()


def box(kitchen):
    """The project's log, in a project the view knows: one with a queue, here an empty one."""
    queued = kitchen.state / "queue.json"
    if not queued.exists():
        jbus.write_json(queued, [])
    return wake.Box(kitchen.state, jbus.load().project("demo"))


def fed(kitchen, *more):
    code, said = kitchen.main("feed", *more)
    assert code == 0, said
    return json.loads(said)


class View:
    """The view's server over the kitchen's state, started afresh for each `View`."""

    def __init__(self, kitchen):
        sources = view_state.Sources(
            kitchen.state_dir, kitchen.root / "home", user=jsettings.load()
        )
        self.port = free_port()
        self.doors = jview.Doors(jview.App(sources), self.port)
        self.doors.open()

    def get(self, path):
        link = http.client.HTTPConnection("127.0.0.1", self.port, timeout=60)
        try:
            link.request("GET", path, headers={"Host": f"127.0.0.1:{self.port}"})
            answer = link.getresponse()
            return answer.status, json.loads(answer.read())
        finally:
            link.close()

    def feed(self, after="", wait=None):
        query = f"/feed?project=demo&after={after}" + (f"&wait={wait}" if wait is not None else "")
        status, said = self.get(query)
        assert status == 200, said
        return said

    def close(self):
        self.doors.close()


def lines(page):
    return [one["line"] for one in page["events"]]


def test_a_cursor_reads_every_event_after_it_once_across_a_restart(kitchen):
    first = box(kitchen)
    first.send("alpha", "queue", "queue demo: alpha is queued")
    start = fed(kitchen)
    assert (start["v"], start["reset"], start["events"]) == (1, True, [])
    cursor = start["cursor"]
    first.send("beta", "queue", "queue demo: beta is queued")
    first.send("beta", "queue", "queue demo: beta is queued")
    first.record("note", "note demo: kept")
    view = View(kitchen)
    try:
        read = view.feed(cursor)
    finally:
        view.close()
    assert (read["v"], read["reset"]) == (1, False)
    assert lines(read) == ["queue demo: beta is queued"] * 2 + ["note demo: kept"]
    again = box(kitchen)
    again.send("gamma", "queue", "queue demo: gamma is queued")
    view = View(kitchen)
    try:
        after = view.feed(read["cursor"])
        empty = view.feed(after["cursor"])
    finally:
        view.close()
    assert lines(after) == ["queue demo: gamma is queued"]
    assert (empty["events"], empty["cursor"], empty["reset"]) == ([], after["cursor"], False)
    every = read["events"] + after["events"]
    assert len({one["id"] for one in every}) == 4
    assert [one["id"] for one in every][-1] == after["cursor"]
    assert fed(kitchen, "--after", cursor)["events"] == every
    (one, *_) = every
    assert {key: one[key] for key in EVENT if key not in ("id", "at")} == {
        "v": 1,
        "project": "demo",
        "kind": "queue",
        "subject": "beta",
        "line": "queue demo: beta is queued",
        "need": None,
        "act": None,
    }


def test_an_unknown_or_expired_cursor_resets_with_the_needs_to_catch_up_on(kitchen, monkeypatch):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    box(kitchen).send("alpha", "queue", "queue demo: alpha is queued")
    newest = json.loads(kitchen.main("events")[1].splitlines()[-1])["id"]
    for page in (fed(kitchen, "--after", "not-an-id"), fed(kitchen)):
        assert (page["v"], page["reset"], page["events"], page["cursor"]) == (1, True, [], newest)
        assert [(one["kind"], one["slug"]) for one in page["needs"]] == [("approve", "alpha")]
    view = View(kitchen)
    try:
        assert view.feed("not-an-id")["needs"] == fed(kitchen)["needs"]
    finally:
        view.close()
    old = datetime.now(UTC) - wake.LOG_KEEP - timedelta(days=1)
    with monkeypatch.context() as then:
        then.setattr(wake.Box, "clock", staticmethod(lambda: old))
        box(kitchen).send("beta", "queue", "queue demo: beta is queued")
    expired = fed(kitchen)["cursor"]
    box(kitchen).send("gamma", "queue", "queue demo: gamma is queued")
    kept = fed(kitchen)["cursor"]
    box(kitchen).send("delta", "queue", "queue demo: delta is queued")
    box(kitchen).forget(datetime.now(UTC) - wake.LOG_KEEP)
    assert fed(kitchen, "--after", expired)["reset"] is True
    assert lines(fed(kitchen, "--after", kept)) == ["queue demo: delta is queued"]


def test_a_long_poll_returns_at_the_first_new_event_or_at_its_timeout(kitchen):
    first = box(kitchen)
    first.send("alpha", "queue", "queue demo: alpha is queued")
    cursor = fed(kitchen)["cursor"]
    view = View(kitchen)
    try:
        began = time.monotonic()
        quiet = view.feed(cursor, wait=1)
        took = time.monotonic() - began
        assert (quiet["events"], quiet["cursor"], quiet["reset"]) == ([], cursor, False)
        assert 1 <= took < 5
        later = threading.Timer(1, first.send, ("beta", "queue", "queue demo: beta is queued"))
        later.start()
        began = time.monotonic()
        woke = view.feed(cursor, wait=60)
        took = time.monotonic() - began
        later.join()
        assert lines(woke) == ["queue demo: beta is queued"]
        assert took < 10
        status, said = view.get(f"/feed?project=demo&after={cursor}&wait=soon")
        assert (status, said) == (400, {"error": "wait is a number of seconds, 0 to 600"})
    finally:
        view.close()
    began = time.monotonic()
    page = fed(kitchen, "--after", woke["cursor"], "--wait", "1")
    assert (page["events"], page["reset"]) == ([], False)
    assert time.monotonic() - began >= 1


HOME_GATE = GATE.format(n=3, asked="drop the old tables?", status="open", slug="beta").replace(
    "Option:", "Holds: deletes data\nFail-safe: a dump at ~/old.sql\nOption:", 1
)


def test_each_need_carries_the_fields_the_bots_asked_for_and_its_doors(kitchen, route):
    add(kitchen, "alpha", approve=False, text=brief("alpha", HOLDS))
    add(kitchen, "beta", approve=False)
    kitchen.poll()
    number = gate(kitchen, holds=True)
    (kitchen.home / "gates.md").write_text(HOME_GATE)
    cursor = fed(kitchen)["cursor"]
    needs = {(one["kind"], one["slug"] or one["subj"]): one for one in fed(kitchen)["needs"]}
    alpha = needs["approve", "alpha"]
    assert {field: alpha[field] for field in FIELDS} == {
        "project": "demo",
        "slug": "alpha",
        "sha": sha12(stored(kitchen, "alpha")),
        "kind": "approve",
        "what": "alpha: a task",
        "default": you.IDLE["approve"],
        "since": alpha["since"],
        "doors": ["rewrites history"],
    }
    assert alpha["since"] is not None
    assert needs["approve", "beta"]["doors"] == []
    asked = needs["gate", "alpha"]
    assert (asked["key"], asked["what"], asked["doors"]) == (
        f"gate:q{number}",
        "which history?",
        ["rewrites history"],
    )
    view = View(kitchen)
    try:
        status, stack = view.get("/stack.json")
    finally:
        view.close()
    assert status == 200
    shown = {(one["kind"], one["slug"] or one["subj"]): one["doors"] for one in stack["needs"]}
    assert shown == {key: one["doors"] for key, one in needs.items()}
    (filed,) = [one for one in stack["proceeds"] if one["slug"] == "beta"]
    assert (filed["what"], filed["doors"]) == ("drop the old tables?", ["deletes data"])
    assert bot_go(route, kitchen, "alpha")[0] == 200
    (acted,) = [one for one in fed(kitchen, "--after", cursor)["events"] if one["kind"] == "act"]
    assert sorted(acted) == sorted(EVENT)
    assert (acted["v"], acted["subject"], acted["act"]["v"], acted["act"]["outcome"]) == (
        1,
        "alpha",
        1,
        "gated",
    )
    assert acted["act"]["evidence"]["ref"] == CHAT.removeprefix("bot-chat:")
    assert (acted["need"]["kind"], acted["need"]["doors"]) == ("approve", ["rewrites history"])


def test_a_go_seen_after_the_second_of_two_equal_events_is_not_stale(kitchen, route):
    add(kitchen, "beta", approve=False)
    box(kitchen).send("beta", "queue", "queue demo: beta is queued")
    cursor = fed(kitchen)["cursor"]
    for _ in range(2):
        box(kitchen).send("beta", "queue", "queue demo: beta's brief changed")
    first, second = (one["id"] for one in fed(kitchen, "--after", cursor)["events"])
    status, said = bot_go(route, kitchen, "beta", seen=first)
    assert (status, said["error"]) == (
        409,
        f"refused: stale: beta changed after event {first}, in event {second} "
        "(queue demo: beta's brief changed)",
    )
    status, said = bot_go(route, kitchen, "beta", seen=second)
    assert (status, said["act"]["outcome"]) == (200, "done")


@pytest.mark.parametrize("after", ["", "not-an-id"])
def test_the_feed_names_a_project_the_state_has(kitchen, after):
    view = View(kitchen)
    try:
        status, _ = view.get(f"/feed?project=nowhere&after={after}")
    finally:
        view.close()
    assert status == 404


def test_a_long_poll_sees_an_event_written_while_it_read_the_log(kitchen, monkeypatch):
    made = box(kitchen)
    made.send("alpha", "queue", "queue demo: alpha is queued")
    cursor = fed(kitchen)["cursor"]
    entries, reads = wake.entries, []

    def read_then_write(state):
        found = entries(state)
        reads.append(len(found))
        if len(reads) == 1:
            made.send("beta", "queue", "queue demo: beta is queued")
        return found

    monkeypatch.setattr(wake, "entries", read_then_write)
    ticks = iter(range(1000))
    page = feed.wait(
        kitchen.state,
        "demo",
        cursor,
        5,
        list,
        sleep=lambda _: None,
        clock=lambda: next(ticks) / 100,
    )
    assert lines(page) == ["queue demo: beta is queued"]
