"""`--message <thread id>/last` names the user's newest message of the thread.

jbus finds that message in T3 Code's own store, the newest the store has as the user's own (role
`user`, `createdBy` `user`, not streaming), and reads it from T3 Code as it reads a message by its
id, so a message an agent sent never passes. The record keeps the message's id, never `last`.
Every test runs the real command against the faked server of `test_jbus_kitchen` and a small
store laid out as T3 Code lays out its own, under `T3CODE_HOME`.
"""

import json
import sqlite3

from jbus import acts, cli, t3, threadview
from test_jbus_approval import go
from test_jbus_queue import add, rows

HOME = "mcp:a-home"
OLDER, NEWEST, AGENTS = "an-older-message", "the-newest-message", "an-agents-message"


def stored(tmp_path, monkeypatch, messages, threads=(), runs=()):
    """Write T3 Code's store with `messages`, as (id, thread, role, createdBy, streaming,
    created_at, updated_at, text), `threads` as (id, title, archived_at, payload) and `runs` as
    (thread, ordinal, status, requested_at, completed_at), and point `T3CODE_HOME` at it."""
    home = tmp_path / "t3"
    (home / threadview.STORE).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(home / threadview.STORE)
    db.executescript(
        """
        create table orchestration_v2_projection_messages (
            message_id text primary key, thread_id text not null, run_id text, node_id text,
            role text not null, streaming integer not null, created_at text not null,
            updated_at text not null, payload_json text not null);
        create index orchestration_v2_projection_messages_latest_user_idx
            on orchestration_v2_projection_messages(thread_id, updated_at desc, message_id desc)
            where role = 'user';
        create table orchestration_v2_projection_threads (
            thread_id text primary key, project_id text not null, title text not null,
            created_at text not null, updated_at text not null, archived_at text,
            deleted_at text, payload_json text not null);
        create table orchestration_v2_projection_runs (
            run_id text primary key, thread_id text not null, ordinal integer not null,
            status text not null, requested_at text not null, completed_at text,
            payload_json text not null);
        """
    )
    db.executemany(
        "insert into orchestration_v2_projection_messages values (?, ?, null, null, ?, ?, ?, ?, ?)",
        [
            (
                one,
                thread,
                role,
                int(streaming),
                created,
                updated,
                json.dumps({"createdBy": by, "text": text}),
            )
            for one, thread, role, by, streaming, created, updated, text in messages
        ],
    )
    db.executemany(
        "insert into orchestration_v2_projection_threads values (?, 'p', ?, 't', ?, ?, null, ?)",
        [
            (one, title, f"2026-11-10T1{n}:00:00Z", archived, json.dumps(payload))
            for n, (one, title, archived, payload) in enumerate(threads)
        ],
    )
    db.executemany(
        "insert into orchestration_v2_projection_runs values (?, ?, ?, ?, ?, ?, '{}')",
        [(f"{thread}:{ordinal}", thread, ordinal, *rest) for thread, ordinal, *rest in runs],
    )
    db.commit()
    db.close()
    monkeypatch.setenv("T3CODE_HOME", str(home))


def user(one, at, by="user", streaming=False, thread=HOME):
    return (one, thread, "user", by, streaming, at, at, one)


def test_last_approves_on_the_users_newest_message(kitchen, tmp_path, monkeypatch):
    stored(
        tmp_path,
        monkeypatch,
        [
            user(OLDER, "2026-10-12T14:00:00Z"),
            user(NEWEST, "2026-10-12T14:30:00Z"),
            user(AGENTS, "2026-10-12T14:40:00Z", by="agent"),
            user("still-typing", "2026-10-12T14:50:00Z", streaming=True),
            user("in-another-thread", "2026-10-12T15:00:00Z", thread="mcp:another"),
        ],
    )
    kitchen.t3.says(HOME, OLDER, "hold alpha")
    kitchen.t3.says(HOME, NEWEST, "yes,\n  launch alpha")
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--message", f"{HOME}/{t3.LAST}")[0] == 0
    approval = rows(kitchen)["alpha"]["approval"]
    assert (approval["ref"], approval["words"]) == (f"{HOME}/{NEWEST}", "yes, launch alpha")


def test_last_never_names_a_message_an_agent_sent(kitchen, tmp_path, monkeypatch):
    stored(tmp_path, monkeypatch, [user(AGENTS, "2026-10-12T14:40:00Z", by="agent")])
    add(kitchen, "alpha", approve=False)
    said = go(kitchen, "alpha", "--message", f"{HOME}/{t3.LAST}")
    assert said == (1, f"refused: thread {HOME} has no message of the user's\n")
    assert rows(kitchen)["alpha"]["approved"] == ""


def test_a_pick_of_last_approves_on_the_box_the_user_answered_last(kitchen, tmp_path, monkeypatch):
    """`jbus.boxes.resolved` turns the pick's `last` into the box's item id, kept as the ref."""
    from test_jbus_approve_by_pick import QUESTION, shown
    from test_jbus_approve_by_pick import REF as BOX
    from test_jbus_approve_by_pick import stored as answered

    shown(kitchen)
    answered(tmp_path, monkeypatch, {QUESTION: ["alpha (S)"]})
    add(kitchen, "alpha", approve=False)
    assert go(kitchen, "alpha", "--pick", f"{HOME}/{t3.LAST}")[0] == 0
    assert rows(kitchen)["alpha"]["approval"]["ref"] == BOX


def test_evidence_of_last_is_kept_as_the_message_it_named(kitchen, tmp_path, monkeypatch):
    """`cli.main` resolves `--evidence t3-message:<thread>/last` before the verb reads it."""
    stored(tmp_path, monkeypatch, [user(NEWEST, "2026-10-12T14:30:00Z")])
    kitchen.t3.says(HOME, NEWEST, "launch alpha")
    evidence = f"{cli.EVIDENCE['message']}{HOME}/{t3.LAST}"
    assert kitchen.main("word", "--to", "demo", "--evidence", evidence)[0] == 0
    assert acts.read(kitchen.state)[-1]["evidence"]["ref"] == f"{HOME}/{NEWEST}"


def test_a_pick_of_last_in_a_thread_with_no_answered_box_is_refused(kitchen, tmp_path, monkeypatch):
    """`jbus.boxes.resolved` refuses in one line naming the thread."""
    from test_jbus_approve_by_pick import stored as answered

    answered(tmp_path, monkeypatch, {}, status="pending")
    add(kitchen, "alpha", approve=False)
    said = go(kitchen, "alpha", "--pick", f"{HOME}/{t3.LAST}")
    assert said == (1, f"refused: thread {HOME} has no answered question box\n")
