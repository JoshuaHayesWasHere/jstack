"""The corrections count over a small fixture store: each class's count, and what is not counted."""

import json
import os
import sqlite3
import subprocess
import sys
import urllib.parse

from testing.paths import REPO

READ_SET = ("features/evals/corrections/",)

SCRIPT = REPO / "features" / "evals" / "corrections" / "corrections.py"
HOME = "t-home"
OTHER = "t-crew"


def quote(reply: str, comment: str) -> str:
    """A message that quotes a reply and comments on it, as T3 Code writes one."""
    query = urllib.parse.urlencode(
        {"text": reply, "start": 0, "end": len(reply), "comment": comment}
    )
    return f"[Assistant quote](t3-citation://v1/p/{HOME}/message:x?{query})"


def store(path):
    """A store with the two tables the count reads, a home thread and a crew's, and a reply before
    each message the user types in them."""
    db = sqlite3.connect(path)
    db.execute(
        "create table orchestration_v2_projection_threads (thread_id text primary key, title text,"
        " payload_json text)"
    )
    db.execute(
        "create table orchestration_v2_projection_messages (message_id text primary key,"
        " thread_id text, role text, created_at text, payload_json text)"
    )
    db.executemany(
        "insert into orchestration_v2_projection_threads values (?, ?, '{}')",
        [(HOME, "home: jstack polish"), (OTHER, "po-some-task")],
    )
    said = [
        (HOME, "user", "user", "2026-11-01T12:00:00Z", "is that accurate? i see 6 merged"),
        (HOME, "assistant", None, "2026-11-02T09:00:00Z", "14 PRs merged today."),
        (HOME, "user", "user", "2026-11-02T09:01:00Z", "is that accurate or are you guessing?"),
        (
            HOME,
            "user",
            "user",
            "2026-11-02T09:02:00Z",
            "this was already done, and turned back off",
        ),
        (
            HOME,
            "user",
            "user",
            "2026-11-02T09:03:00Z",
            quote("Waiting on 3.", "but that wasn't it"),
        ),
        (HOME, "user", "user", "2026-11-02T09:04:00Z", "no lines should cross"),
        (HOME, "user", "user", "2026-11-02T09:05:00Z", "i want this top down, not horizontal"),
        (
            HOME,
            "user",
            "user",
            "2026-11-02T09:06:00Z",
            quote("The five calls.", "what are these??"),
        ),
        (HOME, "user", "user", "2026-11-02T09:07:00Z", "$unslop the language on this chart"),
        (HOME, "user", "user", "2026-11-02T09:08:00Z", "go on, and $unslop"),
        (HOME, "user", "user", "2026-11-02T09:09:00Z", quote("Merged.", "go")),
        (HOME, "user", "agent", "2026-11-02T09:10:00Z", "is that accurate?"),
        (HOME, "user", "user", "2026-11-04T09:00:00Z", "no guessing this time"),
        (OTHER, "assistant", None, "2026-11-02T09:00:00Z", "Done."),
        (OTHER, "user", "user", "2026-11-02T09:01:00Z", "is that accurate?"),
    ]
    db.executemany(
        "insert into orchestration_v2_projection_messages values (?, ?, ?, ?, ?)",
        [
            (f"m{i}", thread, role, at, json.dumps({"createdBy": by, "text": text}))
            for i, (thread, role, by, at, text) in enumerate(said)
        ],
    )
    db.commit()
    db.close()


def count(path, *window):
    run = subprocess.run(
        [sys.executable, str(SCRIPT), "--store", str(path), *window],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
        check=True,
    )
    first, *rows = run.stdout.splitlines()
    return first, {row.split()[1]: int(row.split()[0]) for row in rows}


def test_counts_each_class_in_the_window(tmp_path):
    path = tmp_path / "statev2.sqlite"
    store(path)
    before = path.read_bytes()

    first, counts = count(path, "--since", "2026-11-02", "--until", "2026-11-02")

    assert counts == {"unchecked": 3, "visual": 2, "missing": 1, "broken": 1}
    assert first.startswith("7 of 9 messages in home threads")
    assert path.read_bytes() == before


def test_until_counts_its_day_whole_and_a_first_message_corrects_nothing(tmp_path):
    path = tmp_path / "statev2.sqlite"
    store(path)

    first, counts = count(path, "--since", "2026-11-01", "--until", "2026-11-04")

    assert counts["unchecked"] == 4
    assert first.startswith("8 of 11 messages")
