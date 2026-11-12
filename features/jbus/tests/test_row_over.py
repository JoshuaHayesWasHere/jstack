"""A row is over in one place (`work.over`), and once over it stays so.

The tests run the real pass against the faked T3 Code and GitHub of `test_jbus_queue.py`. The
queue's reader is the table a pass writes (`queue.final`), the watcher's reader is what `dispatch`
launches by (`watch.final`): a row that depends on one that is not over waits, and jmerge's reader
is `jmerge.bus.over`, which jbus answers (`jbus.port`).
"""

import json
from datetime import timedelta

from jbus import port, queue, states, work
from jmerge import bus
from test_jbus_kitchen import NOW
from test_jbus_queue import add, gates, rows
from test_work import judged, result

LATER = NOW + timedelta(minutes=3)


def moves(kitchen):
    path = kitchen.state / "transitions.jsonl"
    lines = path.read_text().splitlines() if path.exists() else []
    return [(one["from"], one["to"]) for one in map(json.loads, lines) if "from" in one]


def test_a_clean_result_from_a_thread_still_at_work_is_not_over_for_the_queue_or_the_watcher(
    kitchen,
):
    add(kitchen, "alpha")
    add(kitchen, "beta", depends="alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", "running")
    kitchen.poll()
    row = rows(kitchen)["alpha"]
    assert row["status"] == "running"
    assert not work.over(row) and not bus.over(row)
    assert "alpha" not in queue.final(list(rows(kitchen).values()))
    assert kitchen.t3.launches == []
    assert rows(kitchen)["beta"]["why"] == "depends on alpha"
    assert judged(kitchen, "beta")["facts"]["row"] == "approved and behind"


def test_a_pull_request_opened_after_a_row_is_done_keeps_it_done_and_opens_a_gate(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    assert rows(kitchen)["alpha"]["status"] == "done"
    kitchen.set("open.json", [kitchen.opened("alpha", 9)])
    kitchen.poll(LATER)
    row = rows(kitchen)["alpha"]
    assert (row["status"], row["pr"]) == ("done", "#9")
    assert work.over(row) and bus.over(row)
    assert isinstance(bus.found(), port.Port)
    (gate,) = [line for line in gates(kitchen) if line.startswith("condition alpha:")]
    assert gate == f"condition alpha: {states.REOPENED.format(pull='#9', was='done')}"
    assert [move for move in moves(kitchen) if move[0] in work.FINAL] == []


def test_a_done_row_whose_pull_request_merges_is_merged(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    kitchen.poll(LATER)
    assert rows(kitchen)["alpha"]["status"] == "merged"
    assert moves(kitchen)[-1] == ("done", "merged")
