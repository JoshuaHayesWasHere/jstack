"""The notice that a merge changed a skill (`jbus.reload`) goes only into a turn its thread already
runs: the outbox's `idle` rule holds it while the thread has none, so it starts no turn of its own,
and `reload.json` keeps the merge owed until the thread runs one, is settled, archived or gone. The
tests run the real pass against the kitchen's fakes."""

import json
from datetime import timedelta

from jbus import outbox
from test_jbus_kitchen import NOW
from test_jbus_row_ends import sends

CHANGED = 'merged 7 alpha abc1234def5 "a skill", skills changed: crew, revert: x\n'


def held(kitchen):
    """Return each held line of `outbox.jsonl` as its template and its rule."""
    lines = (kitchen.state / outbox.FILE).read_text().splitlines()
    return [
        (one["template"], one["rule"]) for one in map(json.loads, lines) if one["went"] == "held"
    ]


def owed(kitchen):
    return [one["number"] for one in json.loads((kitchen.state / "reload.json").read_text())]


def test_a_crew_with_no_turn_running_hears_of_a_changed_skill_in_its_next_turn(kitchen):
    """29 of 301 crew sessions in 72 h ran a turn that only read the notice and the skill again,
    at a median context of 164k tokens. An idle crew is not woken for it: the notice waits, and
    steers the next turn the crew runs."""
    crew = kitchen.t3.thread("alpha", "completed", idle=timedelta(minutes=30))
    kitchen.set("jmerge.txt", CHANGED)
    kitchen.poll()
    assert sends(kitchen) == []
    assert held(kitchen) == [("reload", "idle")]
    assert owed(kitchen) == [7]
    crew["status"] = "running"
    kitchen.set("jmerge.txt", "")
    kitchen.poll(NOW + timedelta(minutes=1))
    (told,) = sends(kitchen)
    assert told["threadId"] == crew["threadId"] and "skills: crew." in told["message"]
    assert told["mode"] == "auto"
    assert owed(kitchen) == []


def test_a_merge_whose_only_thread_is_archived_leaves_reload_json(kitchen):
    crew = kitchen.t3.thread("alpha", "completed", idle=timedelta(minutes=30))
    kitchen.set("jmerge.txt", CHANGED)
    kitchen.poll()
    assert owed(kitchen) == [7]
    crew["archived"] = True
    kitchen.set("jmerge.txt", "")
    kitchen.poll(NOW + timedelta(minutes=1))
    assert owed(kitchen) == []
    assert sends(kitchen) == []
