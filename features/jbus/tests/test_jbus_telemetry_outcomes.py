"""What each done row, scout and home turn came to, from the store's views: `row_outcomes` names
how each row that is over ended, `scout_rows` how the rows of a scout's entry stand, `row_causes`
the message a queued row came of, and `row_spend` counts a home's and a scout's units on the merged
rows they led to.

The test writes what jbus and the agents write: the queue, the merged rows and the brief versions
under jbus's state, a home's and a scout's and a crewmate's transcripts, and T3 Code's threads and
messages, then runs `jbus telemetry` and reads the views as any reader would."""

import json
from datetime import timedelta

import pytest

import test_jbus_telemetry_tokens as token_records
from jgauge import spend as jgauge_spend
from test_jbus_telemetry_tokens import NOW, iso, said

SONNET = "claude-sonnet-5-5"
MESSAGES = (
    "CREATE TABLE orchestration_v2_projection_messages (message_id TEXT PRIMARY KEY, "
    "thread_id TEXT NOT NULL, role TEXT NOT NULL, created_at TEXT NOT NULL, "
    "payload_json TEXT NOT NULL)"
)


def say(tokens, message, thread, at, role="user", by="user"):
    payload = {"text": "words", "createdBy": by if role == "user" else None}
    tokens.t3.execute(
        "INSERT INTO orchestration_v2_projection_messages VALUES (?, ?, ?, ?, ?)",
        (message, thread, role, iso(at), json.dumps(payload)),
    )


def spends(tokens, session, title, *calls):
    """A thread titled `title` on `session`, whose calls are (minutes after NOW, plain tokens)."""
    tokens.thread(f"mcp:{session}", title, "claudeAgent", session)
    tokens.claude(
        session,
        *(
            said(
                NOW + timedelta(minutes=at),
                f"m-{session}-{at}",
                (plain, 0, 0, 0),
                SONNET,
                session=session,
            )
            for at, plain in calls
        ),
    )


@pytest.fixture
def store(tmp_path, monkeypatch, t3_settings):
    """A home that queues two rows on one plan entry, after a typed message; a scout of that entry;
    and a row of each way a row ends."""
    machine = token_records.Machine(tmp_path, monkeypatch, t3_settings)
    state = machine.state_dir / "alpha"
    machine.t3.execute(MESSAGES)
    spends(machine, "home", "home: alpha", (1, 1_000), (12, 2_000), (40, 9_000))
    spends(machine, "scout", "scout: scout-a", (0, 600))
    spends(machine, "crew", "crew: row-merged", (15, 5_000))
    say(machine, "m-early", "mcp:home", NOW - timedelta(hours=1))
    say(machine, "m-typed", "mcp:home", NOW)
    say(machine, "m-reply", "mcp:home", NOW + timedelta(minutes=5), role="assistant")
    say(machine, "m-late", "mcp:home", NOW + timedelta(minutes=25), by="agent")
    home = {"session": "home"}
    rows = [
        {"slug": "scout-a", "status": "done", "role": "scout", "entry": "plan-a"},
        {
            "slug": "row-merged",
            "status": "merged",
            "entry": "plan-a",
            "queued_by": home,
            "approval": {"basis": "entry", "message": "mcp:home/m-go"},
        },
        {"slug": "row-also", "status": "merged", "entry": "plan-a", "queued_by": home},
        {"slug": "row-open", "status": "queued", "entry": "plan-a"},
        {"slug": "row-ended", "status": "done", "entry": "plan-a"},
        {"slug": "row-probe", "status": "done"},
        {"slug": "row-parent", "status": "done"},
        {"slug": "row-child", "status": "running", "approval": {"follows": "row-parent"}},
    ]
    (state / "queue.json").write_text(json.dumps(rows))
    (state / "merged.json").write_text(
        json.dumps(
            {
                slug: {"number": n, "mergedAt": iso(NOW + timedelta(hours=n))}
                for n, slug in enumerate(("row-merged", "row-also"), 1)
            }
        )
    )
    briefs = [("row-merged", 10, "open"), ("row-merged", 30, "none"), ("row-also", 20, "open")]
    briefs += [(slug, 0, "open") for slug in ("row-ended", "row-parent", "row-child")]
    briefs += [("row-probe", 0, "open"), ("row-probe", 1, "none")]
    with open(state / "brief-versions.jsonl", "w") as handle:
        handle.writelines(
            json.dumps(
                {
                    "at": iso(NOW + timedelta(minutes=at)),
                    "slug": slug,
                    "sha": f"{slug}-{at}",
                    "was": "",
                    "bytes": 80,
                    "pull": pull,
                }
            )
            + "\n"
            for slug, at, pull in briefs
        )
    machine.run()
    with machine.store() as store:
        yield store


def test_each_row_that_is_over_says_what_it_came_to(store):
    outcomes = store.execute("SELECT slug, outcome FROM row_outcomes ORDER BY slug").fetchall()
    assert outcomes == [
        ("row-also", "merged"),
        ("row-ended", "ended without one"),
        ("row-merged", "merged"),
        ("row-parent", "carried"),
        ("row-probe", "no pull request asked"),
        ("scout-a", "ended without one"),
    ]


def test_a_scout_counts_the_rows_of_its_entry_by_how_they_stand(store):
    scouts = store.execute("SELECT scout, entry, merged, open, none FROM scout_rows").fetchall()
    assert scouts == [("scout-a", "plan-a", 2, 1, 1)]


def test_a_queued_row_names_the_message_its_home_was_answering(store):
    causes = store.execute(
        "SELECT slug, session, thread, message, created_by, approval_message, minutes "
        "FROM row_causes ORDER BY slug"
    ).fetchall()
    assert causes == [
        ("row-also", "home", "mcp:home", "mcp:home/m-typed", "user", "", 20.0),
        ("row-merged", "home", "mcp:home", "mcp:home/m-typed", "user", "mcp:home/m-go", 10.0),
    ]


def test_a_merged_row_counts_the_home_turn_and_the_scout_that_led_to_it(store):
    """A home's call is the next row it queued, and one after its last row is none's; a scout's
    is split evenly over its entry's merged rows; a crewmate's stays its own row's."""
    units = {
        (slug, role): round(units / jgauge_spend.PLAIN, 6)
        for slug, role, units in store.execute("SELECT slug, role, units FROM row_spend")
    }
    assert units == {
        ("row-merged", "home"): 1_000,
        ("row-also", "home"): 2_000,
        ("row-merged", "scout"): 300,
        ("row-also", "scout"): 300,
        ("row-merged", "crew"): 5_000,
    }
