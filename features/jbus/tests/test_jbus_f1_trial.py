"""At each close by silence, jbus runs the narrow rule F1 over the user's words in T3 Code's store
and logs what it would have held, and the close is the same whatever F1 says or raises.

The tests run the real `jbus gate` and pass against the faked T3 Code server of
`test_jbus_kitchen`, with T3 Code's store laid out as T3 Code lays out its own, under
`T3CODE_HOME`.
"""

import json
import os
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from jbus import questions
from test_jbus_gate_silence import Frozen
from test_jbus_kitchen import NOW, PROJECT, Kitchen

RULE = "Always keep the widget ledger in jbus, every row reads it."
REMOVES = (
    "## Gate <n>: does the widget ledger go?\nStatus: open\nAsked by: alpha, thread mcp:a-thread\n"
    "Default: the widget ledger goes, rows read the queue\nBuilt on it: the cups\n"
    "Undo: put it back\n"
    "Option: drop it (default, recommended): the widget ledger goes\nOption: keep it: it stays\n"
)
KEEPS = (
    "## Gate <n>: tea or coffee?\nStatus: open\nAsked by: alpha, thread mcp:a-thread\n"
    "Default: made tea\nBuilt on it: the cups\nUndo: pour it out\n"
    "Option: tea (default, recommended): the cups stay\nOption: coffee: they go\n"
)
SILENCE = {
    "words": "default",
    "by": "jbus",
    "at": "2026-10-12T15:00:00+00:00",
    "where": "settled at once",
    "keeps": True,
    "told": "",
    "closed_by": "silence",
    "ref": "",
    "said_in": "",
    "checked": False,
}
NOTE = "note alpha: question 1 closed with its default, settled at once"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    made.brief("alpha", "Thread: mcp:crew-alpha\n")
    made.quiet()
    monkeypatch.setattr(questions, "datetime", Frozen)
    yield made
    made.close()


def store() -> Path:
    return Path(os.environ["T3CODE_HOME"]) / "userdata" / "statev2.sqlite"


def said(*words):
    """Write T3 Code's store with the user's words, a day before the gate, in a thread of the
    kitchen's project, and a hundred lines of chat in another project's thread."""
    db = sqlite3.connect(store())
    db.executescript(
        """
        create table orchestration_v2_projection_threads (thread_id text, project_id text);
        create table orchestration_v2_projection_messages (
            message_id text, thread_id text, role text, created_at text, payload_json text);
        """
    )
    db.executemany(
        "insert into orchestration_v2_projection_threads values (?, ?)",
        [("ours", PROJECT), ("theirs", "other")],
    )
    at = (NOW - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    rows = [(f"m-{n}", "ours", text) for n, text in enumerate(words)]
    rows += [(f"chat-{n}", "theirs", f"thanks, carry on with step {n}") for n in range(100)]
    db.executemany(
        "insert into orchestration_v2_projection_messages values (?, ?, 'user', ?, ?)",
        [
            (one, thread, at, json.dumps({"text": text, "createdBy": "user"}))
            for one, thread, text in rows
        ],
    )
    db.commit()
    db.close()


def closed(kitchen, lines):
    """Ask the gate, run a pass, and return how the pass closed it and the trial's log."""
    assert kitchen.main("gate", "alpha", stdin=lines)[0] == 0
    said = kitchen.poll(NOW)
    (one,) = json.loads((kitchen.state / "questions.json").read_text())["records"]
    assert (one["answer"], NOTE in said, kitchen.lines("note")) == (SILENCE, True, [NOTE])
    assert kitchen.t3.messages == {}
    log = kitchen.state / "f1-trial.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines()]


def test_a_close_f1_would_hold_logs_the_gate_and_the_matched_word_and_closes_as_ever(kitchen):
    said(RULE, "Keep the cups warm.")
    (line,) = closed(kitchen, REMOVES)
    assert line == {
        "at": "2026-10-12T15:00:00+00:00",
        "number": 1,
        "slug": "alpha",
        "asked_at": "2026-10-12T15:00:00+00:00",
        "would_hold": True,
        "words": [{"id": "m-0", "terms": ["ledger", "widget"]}],
    }
    assert "Always keep" not in (kitchen.state / "f1-trial.jsonl").read_text()


def test_a_close_f1_would_not_hold_is_logged_as_not_held(kitchen):
    said(RULE)
    (line,) = closed(kitchen, KEEPS)
    assert (line["number"], line["would_hold"], line["words"]) == (1, False, [])


def test_a_close_where_f1_errors_logs_the_error_and_closes_as_ever(kitchen):
    store().write_text("not a database")
    (line,) = closed(kitchen, REMOVES)
    assert (line["number"], "would_hold" in line) == (1, False)
    assert line["error"].startswith("DatabaseError: ")


def test_a_gate_that_holds_is_not_closed_and_logs_nothing(kitchen):
    said(RULE)
    holds = REMOVES.replace(
        "Option:", "Holds: deletes data\nFail-safe: bundle at ~/b.bundle, then hold\nOption:", 1
    )
    assert kitchen.main("gate", "alpha", stdin=holds)[0] == 0
    kitchen.poll(NOW)
    assert not (kitchen.state / "f1-trial.jsonl").exists()
