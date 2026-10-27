"""`jbus flow nudges` counts the owner's nudges in the home threads, from T3 Code's store.

The tests write a small store with the two tables T3 Code keeps its threads and messages in,
each row's `payload_json` in the shape T3 Code writes it, and run the real command over it in
the kitchen of `test_jbus_kitchen`. The owner's messages mix nudges with an approval, a decision,
a status question, a word carried to a second home, a slash command, and a "Go" said twice in
one thread.
"""

import argparse
import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from jbus import flow, word
from jbus.flow import nudges
from test_jbus_kitchen import Kitchen

T = datetime(2026, 10, 22, 23, 0, tzinfo=UTC)
ROOT, FLOW, CREW = "mcp:root", "mcp:flow", "mcp:crew"
CARRIED = word.MESSAGE.format(
    by="owner",
    at="2026-10-22 19:41 EDT",
    id="0123456789ab",
    words="Keep going on the flow work. [Sous Chef context: sent from the flow home]",
)
MESSAGES = [
    (-90, ROOT, "user", "user", "Are we stalled?"),
    (0, ROOT, "assistant", "agent", "Main is green again."),
    (1, ROOT, "user", "user", "we seem stalled again - why?\nnothing has merged since noon"),
    (2, ROOT, "assistant", "agent", 'Approve the gone-thread fix? My pick: yes. Reply "go".'),
    (3, ROOT, "user", "user", "Go"),
    (4, ROOT, "assistant", "agent", "Watching the landing until it merges."),
    (5, ROOT, "user", "agent", CARRIED.replace("Keep going on the flow work.", "Go")),
    (6, ROOT, "assistant", "agent", "Nothing needs you."),
    (8, ROOT, "user", "user", "Go"),
    (10, ROOT, "assistant", "agent", "Which base for the release branch, main or migration?"),
    (11, ROOT, "user", "user", "migration"),
    (12, ROOT, "user", "user", "status?"),
    (13, ROOT, "user", "user", "don't stall on the docs, ship the tests"),
    (14, ROOT, "user", "user", "/crew fl-stuck"),
    (15, ROOT, "user", "agent", "Background task completed: the crew is stuck on a slot."),
    (40, FLOW, "user", "user", "Keep going on the flow work."),
    (41, ROOT, "user", "agent", CARRIED),
    (42, CREW, "user", "user", "why are you stuck?"),
    (50, ROOT, "user", "user", "", True),
    (300, ROOT, "user", "user", "why is nothing moving?"),
]
THREADS = {ROOT: "home: demo", FLOW: "home: demo flow", CREW: "fl-nudges-tool"}


def stamp(minutes, at=T):
    return (
        (at + timedelta(minutes=minutes)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )


def write(path, threads, messages, at=T):
    """Write a store at `path` with T3 Code's two tables: `threads` maps a thread id to its
    title, and each of `messages` is `(minutes after at, thread, role, createdBy, text)`, with a
    sixth item for one still streaming."""
    with sqlite3.connect(path) as db:
        db.execute(
            "create table orchestration_v2_projection_threads"
            " (thread_id text primary key, title text not null, payload_json text not null)"
        )
        db.execute(
            "create table orchestration_v2_projection_messages (message_id text primary key,"
            " thread_id text not null, role text not null, streaming integer not null,"
            " created_at text not null, updated_at text not null, payload_json text not null)"
        )
        for thread, title in threads.items():
            payload = {"createdBy": "system", "id": thread, "title": title}
            db.execute(
                "insert into orchestration_v2_projection_threads values (?, ?, ?)",
                (thread, title, json.dumps(payload)),
            )
        for n, (minutes, thread, role, by, text, *streaming) in enumerate(messages):
            when = stamp(minutes, at)
            payload = {
                "createdBy": by,
                "creationSource": "web" if by == "user" else "server",
                "id": f"m{n}",
                "threadId": thread,
                "role": role,
                "text": text,
                "attachments": [],
                "streaming": bool(streaming),
                "createdAt": when,
                "updatedAt": when,
            }
            db.execute(
                "insert into orchestration_v2_projection_messages values (?, ?, ?, ?, ?, ?, ?)",
                (f"m{n}", thread, role, int(bool(streaming)), when, when, json.dumps(payload)),
            )
    return path


@pytest.fixture
def store(tmp_path):
    return write(tmp_path / "statev2.sqlite", THREADS, MESSAGES)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    return Kitchen(tmp_path, monkeypatch)


WINDOW = ("2026-10-22T22:00Z", "2026-10-23T02:00Z")


def test_the_nudges_are_counted_and_approvals_answers_and_status_are_not(kitchen, store):
    before = store.read_bytes()
    code, out = kitchen.main("flow", "nudges", *WINDOW, "--store", str(store))
    assert code == 0, out
    assert out.splitlines() == [
        "2026-10-22T23:01Z\thome: demo\tmcp:root\twe seem stalled again - why?",
        "2026-10-22T23:05Z\thome: demo\tmcp:root\tGo",
        "2026-10-22T23:08Z\thome: demo\tmcp:root\tGo",
        "2026-10-22T23:40Z\thome: demo flow\tmcp:flow\tKeep going on the flow work.",
        "messages 8, nudges 4",
    ]
    assert store.read_bytes() == before


def test_one_title_and_json_give_the_same_count_for_that_home(kitchen, store):
    code, out = kitchen.main(
        "flow", "nudges", *WINDOW, "--store", str(store), "--title", "home: demo flow", "--json"
    )
    assert code == 0, out
    said = json.loads(out)
    assert (said["messages"], said["nudges"]) == (1, 1)
    assert said["list"] == [
        {
            "at": "2026-10-22T23:40:00+00:00",
            "home": "home: demo flow",
            "thread": FLOW,
            "first": "Keep going on the flow work.",
        }
    ]


def test_a_word_carried_alone_counts_in_the_home_it_reached(kitchen, store):
    code, out = kitchen.main(
        "flow", "nudges", *WINDOW, "--store", str(store), "--title", "home: demo"
    )
    assert code == 0, out
    assert out.splitlines()[-2:] == [
        "2026-10-22T23:41Z\thome: demo\tmcp:root\tKeep going on the flow work.",
        "messages 8, nudges 4",
    ]


def test_flow_s_own_json_before_the_verb_gives_json_and_its_window_flags_are_refused(
    kitchen, store
):
    code, out = kitchen.main("flow", "--json", "nudges", *WINDOW, "--store", str(store))
    assert code == 0, out
    assert json.loads(out)["nudges"] == 4
    for given in (("--since", "2026-10-20"), ("--rows",)):
        code, out = kitchen.main("flow", *given, "nudges", *WINDOW, "--store", str(store))
        assert code == 1 and out.startswith(f"refused: {given[0]} is jbus flow's"), out


def test_every_flag_of_flow_but_json_is_refused_before_nudges(kitchen, store):
    parser = argparse.ArgumentParser()
    flow._arguments(parser)
    flags = {
        action.option_strings[0]: action.nargs != 0
        for action in parser._actions
        if action.option_strings and action.dest not in ("help", "json")
    }
    assert set(flags) == set(flow.FLOW_ONLY)
    for flag, takes_value in flags.items():
        given = (flag, "2026-10-20") if takes_value else (flag,)
        code, out = kitchen.main("flow", *given, "nudges", *WINDOW, "--store", str(store))
        assert code == 1 and out.startswith(f"refused: {flag} is jbus flow's"), out


def test_the_help_gives_the_definition_word_for_word(kitchen):
    code, out = kitchen.main("flow", "nudges", "--help")
    assert code == 0
    assert nudges.DEFINITION in " ".join(out.split())


def test_a_missing_store_and_a_window_that_ends_first_are_refused(kitchen, store, tmp_path):
    code, out = kitchen.main("flow", "nudges", *WINDOW, "--store", str(tmp_path / "gone"))
    assert code == 1 and out.startswith("refused:")
    code, out = kitchen.main("flow", "nudges", *reversed(WINDOW), "--store", str(store))
    assert code == 1 and out.startswith("refused:")
