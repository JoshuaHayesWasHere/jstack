"""Each verb that moves a row's go writes one line `{slug, go, by, at}` to `transitions.jsonl`, in
the batch that moves it, so `statechart replay` walks the go of `features/jbus/spec/RowLife.tla`
as it walks the status. A go taken from a parent is taken from each follow-up whose go rests on
it, with a line for each."""

import json
from datetime import timedelta

import pytest

from jbus import questions, queue
from test_jbus_door_runs import DEPLOY, PROD
from test_jbus_entry_go import PLAN, Frozen, basis, gate, plan_go, queued, silence, stop
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add, brief, rows


def goes(kitchen):
    """The go lines of the kitchen's log, as (slug, go) in the order they were written."""
    log = kitchen.state / "transitions.jsonl"
    lines = [json.loads(line) for line in log.read_text().splitlines()]
    return [(one["slug"], one["go"]) for one in lines if "go" in one]


@pytest.fixture
def planned(tmp_path, monkeypatch, jstack_config):
    """A kitchen whose home has a plan, so a row is filed under its entry `epic`."""
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "plan.md").write_text(PLAN)
    monkeypatch.setattr(questions, "datetime", Frozen)
    made.settings = jstack_config
    yield made
    made.close()


def test_an_approve_a_hold_that_keeps_a_lift_and_a_hold_each_write_the_rows_go(kitchen):
    add(kitchen, "alpha")
    assert queue.hold(kitchen.state, "alpha", keep=True).startswith("held alpha")
    assert queue.lift(kitchen.state, "alpha").startswith("lifted alpha")
    assert kitchen.main("queue", "hold", "alpha")[0] == 0
    assert goes(kitchen) == [
        ("alpha", "approved"),
        ("alpha", "kept"),
        ("alpha", "approved"),
        ("alpha", "held"),
    ]


def test_a_hold_of_a_parent_holds_its_follow_up_and_writes_a_held_line_for_each(planned):
    queued(planned, "alpha")
    assert plan_go(planned)[0] == 0
    queued(planned, "beta", entry="", text=brief("beta", "Follows: alpha\n"))
    assert basis(planned, "beta") == (queue.RULE, queue.FOLLOW_REF)
    code, said = planned.main("queue", "hold", "alpha")
    assert code == 0 and "beta with it" in said, said
    assert rows(planned)["beta"]["held"] is True
    assert goes(planned)[-2:] == [("alpha", "held"), ("beta", "held")]


def test_a_plan_stop_sends_a_row_and_its_follow_up_back_to_waiting_with_a_line_each(planned):
    queued(planned, "alpha")
    assert plan_go(planned)[0] == 0
    queued(planned, "beta", entry="", text=brief("beta", "Follows: alpha\n"))
    assert "alpha, beta waits for the user's go" in stop(planned)
    assert goes(planned)[-2:] == [("alpha", "waiting"), ("beta", "waiting")]


def test_an_edit_that_opens_a_door_takes_the_go_back_with_a_waiting_line(kitchen):
    add(kitchen, "plain")
    edited = brief("plain", f"Holds: {PROD}\n").replace(
        "Proves it: `make check`", f"Proves it: `make check`, then `{DEPLOY}`"
    )
    code, said = kitchen.main("queue", "add", "plain", "--priority", "1", stdin=edited)
    assert code == 0 and f"plain's go is taken back: its brief now holds for {PROD}" in said, said
    assert goes(kitchen)[-1] == ("plain", "waiting")


def test_a_gate_that_closes_on_silence_approves_its_row_with_an_approved_line(planned):
    silence(planned)
    queued(planned, "alpha")
    assert plan_go(planned)[0] == 0
    gate(planned, "alpha")
    planned.poll(NOW + timedelta(minutes=31))
    assert basis(planned, "alpha")[0] == queue.ANSWER
    assert goes(planned)[-1] == ("alpha", "approved")
