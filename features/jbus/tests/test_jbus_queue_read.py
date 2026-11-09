"""A pass parses `queue.json` and `removed.json` once, and the read after a write sees it.

`queue.load` keeps each file's parse while the file is as it was (`queue._read`), so a pass's
thirty or so readers share one parse of the table. Like `test_jbus_queue.py`, the tests run the
real command and the real pass against a faked T3 Code server, `gh` and `jmerge`."""

import json
from datetime import timedelta

import pytest

from jbus import queue
from test_jbus_kitchen import GO, NOW, RAN, Kitchen
from test_jbus_queue import add, rows


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.word()
    yield made
    made.close()


def parses(monkeypatch, *files):
    """Count each parse of one of `files`, by its name: a `json.loads` of the bytes the file
    holds at that moment."""
    counted = {file.name: 0 for file in files}
    loads = json.loads

    def counting(text, *args, **kwargs):
        for file in files:
            if isinstance(text, bytes) and file.exists() and text == file.read_bytes():
                counted[file.name] += 1
        return loads(text, *args, **kwargs)

    monkeypatch.setattr(json, "loads", counting)
    return counted


def test_a_pass_parses_the_table_and_the_removed_slugs_once(kitchen, monkeypatch):
    for slug in ("alpha", "beta", "gamma"):
        add(kitchen, slug, approve=False)
    assert kitchen.main("queue", "remove", "gamma", "--by", "user", "--at", RAN)[0] == 0
    kitchen.t3.thread("alpha", "running")
    kitchen.poll()
    table, gone = kitchen.state / "queue.json", kitchen.state / "removed.json"
    for file in (table, gone):
        file.write_text(json.dumps(json.loads(file.read_text())))
    kitchen.t3.thread("beta", "running")
    counted = parses(monkeypatch, table, gone)
    kitchen.poll(NOW + timedelta(minutes=3))
    assert counted == {"queue.json": 1, "removed.json": 1}
    assert {slug: row["status"] for slug, row in rows(kitchen).items()} == {
        "alpha": "running",
        "beta": "running",
    }


def test_the_next_read_sees_a_write_and_a_hand_edit_and_no_readers_change(kitchen):
    add(kitchen, "alpha")
    assert queue.load(kitchen.state)[0]["approved"] == GO
    queue.hold(kitchen.state, "alpha")
    assert queue.load(kitchen.state)[0]["approved"] == ""
    table = json.loads((kitchen.state / "queue.json").read_text())
    table[0]["priority"] = 7
    (kitchen.state / "queue.json").write_text(json.dumps(table))
    queue.load(kitchen.state)[0]["priority"] = 99
    assert queue.load(kitchen.state)[0]["priority"] == 7
