"""A row of the queue says why it waits and since when, and jbus keeps each change of its status.
Like `test_jbus_queue.py`, the tests run the real command and the real pass in a temporary state
directory, against a faked T3 Code server, `gh` and `jmerge`."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import cli, rotation
from test_jbus_kitchen import NOW, RESULT
from test_jbus_queue import add, brief, go, queued_before, rows, sha12, widened

FIRST, SECOND = "2026-10-12 11:00 ET", "2026-10-12 11:03 ET"
LATER = NOW + timedelta(minutes=3)
NO_REVIEW = "wait 8 https://example.test/pull/8: it has no review yet\n"


def transitions(kitchen):
    path = kitchen.state / "transitions.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def waits(kitchen):
    return {slug: (row["why"], row["since"]) for slug, row in rows(kitchen).items()}


def test_two_passes_keep_why_a_row_waits_since_when_and_each_change_of_status(kitchen):
    add(kitchen, "alpha", priority=1, approve=False)
    add(kitchen, "beta", priority=2)
    add(kitchen, "gamma", priority=3, depends="beta,alpha")
    kitchen.brief("alpha", RESULT)
    kitchen.set("open.json", [kitchen.opened("alpha", 8)])
    kitchen.set("jmerge.txt", NO_REVIEW)
    thread = kitchen.t3.thread("beta", "running")
    kitchen.poll()
    assert waits(kitchen) == {
        "alpha": ("wait: it has no review yet", FIRST),
        "beta": ("", ""),
        "gamma": ("depends on beta, alpha", FIRST),
    }
    thread["status"] = "completed"
    kitchen.brief("beta", RESULT)
    kitchen.set("open.json", [kitchen.opened("alpha", 8), kitchen.opened("beta", 9, "")])
    pending = "wait 9 https://example.test/pull/9: check has not passed\n"
    kitchen.set("jmerge.txt", NO_REVIEW + pending)
    kitchen.poll(LATER)
    assert waits(kitchen) == {
        "alpha": ("wait: it has no review yet", FIRST),
        "beta": ("wait: check has not passed", SECOND),
        "gamma": ("depends on beta, alpha", FIRST),
    }
    assert transitions(kitchen) == [
        {"slug": "alpha", "from": "queued", "to": "pr", "at": "2026-10-12T15:00:00+00:00"},
        {"slug": "beta", "from": "queued", "to": "running", "at": "2026-10-12T15:00:00+00:00"},
        {"slug": "beta", "from": "running", "to": "pr", "at": "2026-10-12T15:03:00+00:00"},
    ]
    shown = kitchen.main("queue", "show")[1].splitlines()
    assert shown[0].endswith("| checks | updated | why | since | role |")
    assert shown[2].endswith(
        f"| pr |  | #8 | passed | {FIRST} | wait: it has no review yet | {FIRST} |  |"
    )
    assert shown[3].endswith(
        f"| pr | mcp:thread-1 | #9 | pending | {SECOND} | wait: check has not passed "
        f"| {SECOND} |  |"
    )
    assert shown[4].endswith(f"| queued |  |  |  |  | depends on beta, alpha | {FIRST} |  |")


def test_a_quiet_pass_keeps_since_and_appends_no_transition(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    kitchen.poll(LATER)
    assert waits(kitchen) == {"alpha": ("not approved", FIRST)}
    assert transitions(kitchen) == []


def test_a_reason_that_changes_moves_since_and_not_updated(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.brief("alpha", RESULT)
    kitchen.set("open.json", [kitchen.opened("alpha", 8)])
    kitchen.set("jmerge.txt", NO_REVIEW)
    kitchen.poll()
    kitchen.set("jmerge.txt", "hold 8 alpha: needs a rebase\n")
    kitchen.poll(LATER)
    row = rows(kitchen)["alpha"]
    assert (row["why"], row["since"], row["updated"]) == ("hold: needs a rebase", SECOND, FIRST)
    assert kitchen.events("queue")[1:] == []
    assert len(transitions(kitchen)) == 1


def test_a_row_that_no_longer_waits_has_no_reason_and_no_since(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    kitchen.t3.thread("alpha", "running")
    kitchen.poll(LATER)
    assert waits(kitchen) == {"alpha": ("", "")}


def test_a_row_not_launched_says_which_of_the_reasons_stopped_it(kitchen):
    kitchen.brief("other")
    kitchen.t3.thread("other", "running")
    add(kitchen, "alpha", priority=1)
    changed = widened("alpha")
    add(kitchen, "alpha", priority=1, approve=False, text=changed)
    add(kitchen, "beta", priority=3)
    add(kitchen, "gamma", priority=2)
    kitchen.t3.thread("gamma", "failed", settled=True)
    kitchen.poll()
    assert waits(kitchen) == {
        "alpha": (f"brief changed after approval, now {sha12(changed)}", FIRST),
        "beta": ("no slot", FIRST),
        "gamma": ("a gate the Chef has", FIRST),
    }


def test_in_a_full_pass_a_row_says_no_slot_only_where_a_slot_is_all_that_stops_it(kitchen):
    """`other` holds the one slot, so `alpha` is the first row that cannot launch for want of a
    slot. The pass reads the rows after `alpha` without sending a gate for any of them. Of those,
    `gamma` and `delta` wait for a slot. `gamma`'s brief has no `Design:` line, which a launch no
    longer asks for, so its go is still valid."""
    kitchen.brief("other")
    kitchen.t3.thread("other", "running")
    add(kitchen, "alpha", priority=1)
    add(kitchen, "beta", priority=2)
    kitchen.t3.thread("beta", "failed", settled=True)
    queued_before(kitchen, "gamma", brief("gamma").replace("Design: none, a test\n", ""), 3)
    add(kitchen, "delta", priority=4)
    kitchen.poll()
    assert kitchen.lines("gate") == []
    assert {slug: (row["status"], row["why"]) for slug, row in rows(kitchen).items()} == {
        "alpha": ("queued", "no slot"),
        "beta": ("queued", ""),
        "gamma": ("queued", "no slot"),
        "delta": ("queued", "no slot"),
    }


def test_one_failed_jmerge_between_two_good_passes_keeps_why_and_since(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.brief("alpha", RESULT)
    kitchen.set("open.json", [kitchen.opened("alpha", 8)])
    kitchen.set("jmerge.txt", NO_REVIEW)
    kitchen.poll()
    kitchen.set("jmerge-dies", "jmerge: gh is not installed")
    said = kitchen.poll(LATER)
    assert "wait demo: jmerge did not run (jmerge: gh is not installed)" in said
    assert waits(kitchen) == {"alpha": ("wait: it has no review yet", FIRST)}
    (kitchen.stub / "jmerge-dies").unlink()
    kitchen.poll(LATER + timedelta(minutes=3))
    assert waits(kitchen) == {"alpha": ("wait: it has no review yet", FIRST)}


def test_a_jmerge_that_dies_after_one_line_keeps_the_reason_of_the_row_it_did_not_reach(kitchen):
    for slug in ("alpha", "beta"):
        add(kitchen, slug, approve=False)
        kitchen.brief(slug, RESULT)
    kitchen.set("open.json", [kitchen.opened("alpha", 8), kitchen.opened("beta", 9)])
    pending = "wait 9 https://example.test/pull/9: check has not passed\n"
    kitchen.set("jmerge.txt", NO_REVIEW + pending)
    kitchen.poll()
    kitchen.set("jmerge.txt", "hold 8 alpha: needs a rebase\n")
    kitchen.set("jmerge-dies-late", "jmerge: gh stopped answering")
    said = kitchen.poll(LATER)
    assert "wait demo: jmerge stopped after 1 lines (jmerge: gh stopped answering)" in said
    assert waits(kitchen) == {
        "alpha": ("hold: needs a rebase", SECOND),
        "beta": ("wait: check has not passed", FIRST),
    }


def test_a_jmerge_that_ran_and_said_nothing_of_a_pull_request_clears_its_reason(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.brief("alpha", RESULT)
    kitchen.set("open.json", [kitchen.opened("alpha", 8)])
    kitchen.set("jmerge.txt", NO_REVIEW)
    kitchen.poll()
    kitchen.set("jmerge.txt", "")
    kitchen.poll(LATER)
    assert waits(kitchen) == {"alpha": ("", "")}


def test_where_jmerge_ran_here_a_line_it_logged_before_is_not_the_reason(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.brief("alpha", RESULT)
    kitchen.set("open.json", [kitchen.opened("alpha", 8)])
    (kitchen.home / "merge.log.last").write_text(json.dumps({"8": NO_REVIEW.strip()}))
    kitchen.poll()
    assert kitchen.log("jmerge") == [""]
    assert waits(kitchen) == {"alpha": ("", "")}


@pytest.mark.parametrize(
    "off, alpha, beta",
    [
        ("config", ("dispatch is off", SECOND), ("dispatch is off", SECOND)),
        ("stop", ("the stop file is there", SECOND), ("the stop file is there", SECOND)),
        ("raised", ("depends on gamma", FIRST), ("", "")),
    ],
)
def test_a_pass_in_which_dispatch_read_no_row_says_so_or_keeps_what_still_holds(
    kitchen, off, alpha, beta
):
    add(kitchen, "alpha", priority=1, depends="gamma")
    add(kitchen, "beta", priority=2, approve=False)
    add(kitchen, "gamma", priority=3, approve=False)
    kitchen.poll()
    assert waits(kitchen) == {
        "alpha": ("depends on gamma", FIRST),
        "beta": ("not approved", FIRST),
        "gamma": ("not approved", FIRST),
    }
    assert go(kitchen, "beta")[0] == 0
    if off == "config":
        kitchen.config(dispatch=False)
    elif off == "stop":
        (kitchen.state_dir / "stop").write_text("")
    else:

        def share(*_):
            raise RuntimeError("no launch step")

        kitchen.monkeypatch.setattr(rotation, "share", share)
    assert cli.poll(jbus.load(), LATER, lambda _: None) == (off == "raised")
    assert waits(kitchen) == {"alpha": alpha, "beta": beta, "gamma": ("not approved", FIRST)}
