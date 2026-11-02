"""retro's first step builds a dataset of a past window that gives the same counts on every run,
and its codebook is frozen before anything reads an outcome. The tests write jbus's records and
a T3 Code database as the machine keeps them, and run the skill's own blocks."""

import json
import sqlite3
import subprocess
import sys

import pytest

from skill_blocks import block, home, linked, repo, run
from testing.paths import REPO

__all__ = ["home", "repo"]

SCRIPT = REPO / "features" / "skill-library" / "skills" / "retro" / "scripts" / "retro_data.py"
WINDOW = {"start='<YYYY-MM-DD>'": "start='2026-10-25'", "days='<7>'": "days='7'"}


def records(folder):
    """One project's jbus records and a T3 Code database, in a base week and the week after it,
    with one record of each kind past the window's end, and a row that started before both."""
    state = folder / ".local" / "state" / "jbus" / "demo"
    state.mkdir(parents=True)
    (state / "queue.json").write_text("[]")
    moves = [
        ("a", "launched", "2026-10-20T15:00:00+00:00"),
        ("a", "merged", "2026-10-26T15:00:00+00:00"),
        ("b", "launched", "2026-10-27T15:00:00+00:00"),
        ("b", "pr", "2026-10-28T15:00:00+00:00"),
        ("c", "launched", "2026-11-03T15:00:00+00:00"),
        ("z", "launched", "2026-10-01T15:00:00+00:00"),
        ("z", "pr", "2026-10-26T15:00:00+00:00"),
    ]
    with (state / "transitions.jsonl").open("w") as file:
        for slug, to, at in moves:
            file.write(json.dumps({"slug": slug, "to": to, "at": at}) + "\n")
    with (state / "events.jsonl").open("w") as file:
        for at in ("2026-10-26T01:00:00+00:00", "2026-11-03T01:00:00+00:00"):
            file.write(json.dumps({"at": at, "event": "queue", "slug": "b", "line": "x"}) + "\n")
    database = folder / ".t3" / "userdata" / "statev2.sqlite"
    database.parent.mkdir(parents=True)
    with sqlite3.connect(database) as made:
        made.execute("create table projection_projects (project_id, workspace_root)")
        made.execute(
            "create table orchestration_v2_projection_threads (thread_id, project_id, title)"
        )
        made.execute(
            "create table orchestration_v2_projection_messages"
            " (message_id, thread_id, role, created_at, payload_json)"
        )
        made.execute("insert into projection_projects values ('p', '/r/demo')")
        made.execute("insert into orchestration_v2_projection_threads values ('t', 'p', 'home')")
        said = [
            ("m1", "2026-10-21T15:00:00.000Z", {"createdBy": "user", "text": "why are we stalled"}),
            ("m2", "2026-10-26T15:00:00.000Z", {"createdBy": "user", "text": "/retro last week"}),
            ("m3", "2026-10-26T16:00:00.000Z", {"createdBy": "agent", "text": "jbus: woke"}),
            ("m4", "2026-11-03T15:00:00.000Z", {"createdBy": "user", "text": "later"}),
        ]
        for message, at, payload in said:
            made.execute(
                "insert into orchestration_v2_projection_messages values (?, 't', 'user', ?, ?)",
                (message, at, json.dumps(payload)),
            )


def top():
    """The block at the top of the skill, with the window filled in."""
    found = block("retro", "R=$(basename")
    for placeholder, value in WINDOW.items():
        found = found.replace(placeholder, value)
    return found


def test_the_dataset_step_prints_the_same_counts_twice_and_reads_nothing_past_the_window(
    home, repo
):
    records(home)
    linked(home, "retro")

    said = run(block("retro", "rerunnable"), repo, home, before=top())

    assert said[-1] == "rerunnable: the same counts twice"
    data = home / ".local" / "state" / "home" / "demo" / "reports" / "retro-2026-10-25-data"
    found = {name: count for count, name in (line.split(None, 1) for line in said[:-1])}
    assert found["transitions.jsonl"] == "5"
    assert found["rows.jsonl"] == "2"
    assert found["events.jsonl"] == "1"
    assert found["messages.jsonl"] == "2"
    assert found["filter_decisions.jsonl"] == "3"
    weeks = {
        json.loads(line)["slug"]: json.loads(line)["week"] for line in open(data / "rows.jsonl")
    }
    assert weeks == {"a": "base", "b": "window"}


def freeze(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def test_the_codebook_freezes_once_and_a_later_edit_is_caught(tmp_path):
    book = tmp_path / "retro-2026-10-25-codebook.md"
    assert freeze("freeze", str(book)).returncode != 0
    book.write_text("# Codebook\n")

    frozen = freeze("freeze", str(book))

    assert frozen.returncode == 0 and frozen.stdout.startswith("frozen: ")
    assert freeze("check", str(book)).stdout == frozen.stdout
    with pytest.raises(PermissionError):
        book.write_text("# Codebook, changed\n")
    book.chmod(0o644)
    book.write_text("# Codebook, changed\n")
    assert freeze("check", str(book)).returncode != 0
    assert freeze("freeze", str(book)).returncode != 0


def test_a_window_still_to_come_is_refused(tmp_path):
    built = freeze("build", "--start", "2999-01-01", "--out", str(tmp_path / "data"))

    assert built.returncode != 0
    assert "still to come" in built.stderr
