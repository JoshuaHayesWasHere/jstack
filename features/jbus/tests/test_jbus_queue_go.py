"""A row's go given or given back by rule, through the queue's own verbs: a lift puts back the go
a hold kept (`queue.hold` with `keep`, `queue.lift`), the entry pass approves a row while its
plan entry's go holds and gives it back to the user once it does not (`queue.entered`), and a go
gate closed on its default approves its row where silence may start it (`queue.gone_ahead`).
Like `test_jbus_queue.py`, the tests run the real queue against the kitchen's fakes, and read
what each row holds afterwards."""

import pytest

import jsettings
from jbus import queue
from jmerge import judgement
from test_jbus_queue import AT, add, brief, kitchen, rows, sha12, widened

__all__ = ["kitchen"]


GO_COLUMNS = ("approved", "approval", "brief_sha")


def test_a_lift_puts_back_the_go_a_hold_kept_and_a_changed_brief_stays_held(kitchen):
    """A hold that keeps its go (`queue.hold` with `keep`), as `jbus.stall.twice` holds a row
    whose check failed twice, is ended by `queue.lift`, which puts that go back as it was. A
    row whose brief changed since that go stays held: the go was for another brief."""
    add(kitchen, "alpha")
    had = {column: rows(kitchen)["alpha"][column] for column in GO_COLUMNS}
    assert had["approved"]
    queue.hold(kitchen.state, "alpha", keep=True)
    assert rows(kitchen)["alpha"]["held"] and not rows(kitchen)["alpha"]["approved"]
    said = queue.lift(kitchen.state, "alpha")
    assert said == f"lifted alpha's hold, and its go is back: {had['approved']}"
    row = rows(kitchen)["alpha"]
    assert {column: row[column] for column in GO_COLUMNS} == had
    assert "held" not in row and "hold" not in row
    queue.hold(kitchen.state, "alpha", keep=True)
    add(kitchen, "alpha", approve=False, text=widened("alpha"))
    with pytest.raises(queue.Refused, match="alpha's brief changed since the go its hold took"):
        queue.lift(kitchen.state, "alpha")
    row = rows(kitchen)["alpha"]
    assert row["held"] and not row["approved"] and "approval" not in row


def entry_go(holds):
    """The go of a plan entry as `jbus.plan.entry_go` gives it: the user's words where the go
    holds for the brief and the entry, and nothing where it does not."""
    said = queue.Said("go on the epic", AT, "mcp:a-home", True, "mcp:a-home/a-go")
    return lambda text, entry: said if holds and entry == "epic" else None


def test_the_entry_pass_approves_a_row_while_its_entrys_go_holds_and_takes_it_back_after(kitchen):
    """`queue.entered`, run by jbus's pass and `jbus plan go` or `stop`, approves a row queued
    under an entry whose go holds, and gives an unlaunched row back to the user once that go no
    longer holds, with no hold, so a new go of the entry approves it again."""
    code, said = kitchen.main(
        "queue", "add", "alpha", "--priority", "1", "--entry", "epic", stdin=brief("alpha")
    )
    assert code == 0, said
    assert not rows(kitchen)["alpha"]["approved"]
    user = jsettings.Settings()
    (line,) = queue.entered(kitchen.state, user, entry_go(True))
    row = rows(kitchen)["alpha"]
    assert line.startswith(f"approved alpha: brief {sha12(brief('alpha'))}, ")
    assert row["approved"].startswith(f"your go for the plan entry epic, {AT}")
    assert (row["approval"]["basis"], row["approval"]["ref"]) == (queue.ENTRY, "epic")
    assert row["brief_sha"] == judgement.brief_sha(brief("alpha"))
    assert queue.entered(kitchen.state, user, entry_go(True)) == []
    said = queue.entered(kitchen.state, user, entry_go(False))
    assert said == ["alpha waits for the user's go: the go of its plan entry epic no longer holds"]
    row = rows(kitchen)["alpha"]
    assert (row["approved"], row["brief_sha"]) == ("", "")
    assert "approval" not in row and "held" not in row


def test_a_go_gate_closed_on_its_default_approves_its_row_only_where_silence_may(kitchen):
    """`queue.gone_ahead` runs when a gate whose default is `approve` closes on that default.
    Silence starts the row only under the setting `go = "silence"`; the user's answer that kept
    the default is their word, and starts it under any setting."""
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    entry = jsettings.Settings(go=jsettings.ENTRY)
    said = queue.gone_ahead(kitchen.state, "alpha", 3, AT, entry, None)
    assert (
        said
        == "alpha waits for the user's go after question 3: the setting go is entry, not silence"
    )
    assert not rows(kitchen)["alpha"]["approved"]
    silence = jsettings.Settings(go=jsettings.SILENCE)
    said = queue.gone_ahead(kitchen.state, "alpha", 3, AT, silence, None)
    row = rows(kitchen)["alpha"]
    assert said.startswith(f"approved alpha: brief {sha12(brief('alpha'))}, ")
    made = row["approval"]
    assert (made["basis"], made["ref"], made["closed_by"]) == (queue.ANSWER, "3", "silence")
    assert row["brief_sha"] == judgement.brief_sha(brief("alpha"))
    heard = queue.Said("start it", AT, "mcp:a-home", True, "mcp:a-home/an-answer")
    said = queue.gone_ahead(kitchen.state, "beta", 4, AT, entry, heard)
    row = rows(kitchen)["beta"]
    assert said.startswith(f"approved beta: brief {sha12(brief('beta'))}, ")
    assert (row["approval"]["basis"], row["approval"]["ref"]) == (queue.ANSWER, "4")
    assert row["approval"]["words"] == "start it"
