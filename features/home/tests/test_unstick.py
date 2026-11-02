"""unstick's script names each stalled row's cause from jbus's records, with its age and what to
do. Each test writes a project's state as a pass leaves it, runs the script as the skill does,
and reads what it prints."""

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

from testing.paths import REPO

SCRIPT = REPO / "features" / "home" / "skills" / "unstick" / "scripts" / "unstick.py"
NOW = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)


def stamp(hours):
    return (NOW - timedelta(hours=hours)).isoformat()


def project(state, rows, events=(), questions=(), history=()):
    """Write one project's state: each row as (slug, status, value, hours in status, extra)."""
    folder = state / "demo"
    folder.mkdir(parents=True)
    queue, work, moves = [], [], list(history)
    for slug, status, value, hours, extra in rows:
        thread = f"mcp:{slug}-thread"
        queue.append({"slug": slug, "status": status, "thread": thread, "pr": "#7"} | extra)
        work.append({"kind": "row", "slug": slug, "value": value, "waits": "something"})
        moves.append({"slug": slug, "from": "queued", "to": status, "at": stamp(hours)})
    (folder / "queue.json").write_text(json.dumps(queue))
    (folder / "work.json").write_text(json.dumps({"work": work}))
    (folder / "questions.json").write_text(json.dumps({"next": 9, "records": list(questions)}))
    (folder / "transitions.jsonl").write_text("".join(json.dumps(m) + "\n" for m in moves))
    (folder / "events.jsonl").write_text("".join(json.dumps(e) + "\n" for e in events))


def unstick(tmp_path, *args, waiters=()):
    locks = tmp_path / "locks"
    locks.mkdir(exist_ok=True)
    (locks / "test-slot-waiters.json").write_text(json.dumps(list(waiters)))
    env = os.environ | {"JBUS_STATE_DIR": str(tmp_path / "state"), "JGAUGE_LOCKS_DIR": str(locks)}
    ran = subprocess.run(
        [sys.executable, str(SCRIPT), "--now", NOW.isoformat(), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return ran.stdout


def by_slug(tmp_path, **kwargs):
    return {one["slug"]: one for one in json.loads(unstick(tmp_path, "--json", **kwargs))}


def test_a_stalled_row_of_each_cause_is_named_with_its_age_and_what_to_do(tmp_path):
    state = tmp_path / "state"
    question = {"slug": "asks", "number": 4, "question": "which base?", "answer": None}
    settled = {"slug": "red", "number": 3, "question": "?", "answer": {"closed_by": "silence"}}
    lifts = (NOW + timedelta(hours=3)).isoformat()
    capped = {
        "at": stamp(2),
        "event": "stall",
        "slug": "capped",
        "line": f"stall capped: claudeAgent is capped until {lifts}",
    }
    project(
        state,
        [
            ("asks", "running", "working", 5, {}),
            ("unreviewed", "pr", "review", 5, {}),
            ("red", "pr", "check", 5, {"checks": "failed"}),
            ("slotted", "running", "quiet", 5, {}),
            ("capped", "running", "quiet", 5, {}),
            ("silent", "running", "hung", 5, {}),
            ("gone", "running", "lost", 5, {}),
        ],
        events=[capped],
        questions=[question, settled],
    )
    waiter = {"thread": "slotted-thread", "lane": "full", "since": stamp(4)}

    found = by_slug(tmp_path, waiters=[waiter])

    causes = {slug: (one["cause"], one["kind"]) for slug, one in found.items()}
    assert causes == {
        "asks": ("gate", "user"),
        "unreviewed": ("review", "act"),
        "red": ("checks", "act"),
        "slotted": ("slot", "wait"),
        "capped": ("usage-limit", "wait"),
        "silent": ("dead-thread", "act"),
        "gone": ("dead-thread", "gate"),
    }
    assert {one["age_minutes"] for one in found.values()} == {300}
    assert found["asks"]["action"] == "answer it: jbus --project demo answer 4"
    assert (
        found["unreviewed"]["action"]
        == "send mcp:unreviewed-thread: /pr-review run unreviewed again"
    )


def test_a_row_inside_its_stage_p90_is_not_stalled(tmp_path):
    history = [
        {"slug": f"old{n}", "from": "pr", "to": step, "at": stamp(at)}
        for n in range(6)
        for step, at in (("pr", 100), ("merged", 90))
    ]
    project(
        tmp_path / "state",
        [("young", "pr", "review", 5, {}), ("old", "pr", "review", 11, {})],
        history=history,
    )

    found = by_slug(tmp_path)

    assert sorted(found) == ["old"]
    assert found["old"]["p90_minutes"] == 600


def test_a_check_still_running_waits_and_a_fresh_word_from_jbus_is_not_sent_again(tmp_path):
    told = {"at": stamp(0.2), "event": "expedite", "slug": "told", "line": "expedite told: ..."}
    project(
        tmp_path / "state",
        [("running", "pr", "check", 5, {"checks": "pending"}), ("told", "pr", "review", 5, {})],
        events=[told],
    )

    found = by_slug(tmp_path)

    assert (found["running"]["cause"], found["running"]["kind"]) == ("checks", "wait")
    assert (found["told"]["cause"], found["told"]["kind"]) == ("review", "wait")


def test_nothing_stalled_says_so(tmp_path):
    project(tmp_path / "state", [("young", "running", "working", 0.1, {})])

    assert unstick(tmp_path) == "nothing is stalled: 1 open rows, each inside its stage's p90\n"
