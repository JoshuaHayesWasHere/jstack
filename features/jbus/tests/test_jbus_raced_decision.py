"""A pass raises a decision only on ground it reads again just before it sends, and tells no one
when the item leaves the list of what waits (`jbus.blockers`).

A row to approve is raised only once it has waited unapproved for `APPROVE_GRACE_SECONDS`, so a
home that queues a row and approves it a moment later never puts it to the user. A gate that holds
is raised at once. Every test runs the real pass against the kitchen's fakes."""

from datetime import timedelta

import jbus
from jbus import blockers, digest, waiting
from test_jbus_kitchen import NOW
from test_jbus_one_wake import ASK
from test_jbus_queue import add, go


def later(minutes):
    return NOW + timedelta(minutes=minutes)


def decisions(kitchen, slug):
    return [one["line"] for one in kitchen.events("decision") if one["slug"] == slug]


def test_a_row_queued_and_approved_a_moment_later_raises_no_decision(kitchen):
    kitchen.poll()
    add(kitchen, "alpha", approve=False)
    kitchen.poll(later(10))
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll(later(10) + timedelta(seconds=1))
    kitchen.poll(later(20))
    assert decisions(kitchen, "alpha") == []
    assert not [said for post in kitchen.wakes.said for said in post if "alpha" in said]


def test_a_row_approved_between_the_list_and_the_raise_is_not_raised(kitchen, monkeypatch):
    kitchen.poll()
    add(kitchen, "alpha", approve=False)
    kitchen.poll(later(10))
    kept = waiting.keep

    def approved_after_the_list(*args, **kwargs):
        listed = kept(*args, **kwargs)
        assert go(kitchen, "alpha")[0] == 0
        return listed

    monkeypatch.setattr(waiting, "keep", approved_after_the_list)
    kitchen.poll(later(20))
    assert "approve:alpha" in [one["key"] for one in waiting.read(kitchen.state)]
    assert decisions(kitchen, "alpha") == []


def test_a_gate_answered_between_the_list_and_the_raise_is_not_raised(kitchen, monkeypatch):
    kitchen.poll()
    safe = "Holds: deletes data\nFail-safe: the dry-run lists what goes\n"
    holds = ASK.replace("Undo: pick the other\n", f"Undo: pick the other\n{safe}")
    assert kitchen.main("gate", "alpha", stdin=holds) == (0, "queued: question 1\n")
    kept = waiting.keep

    def answered_after_the_list(*args, **kwargs):
        listed = kept(*args, **kwargs)
        kitchen.t3.says("mcp:a-home", "other-1", "the other")
        said = ("--message", "mcp:a-home/other-1", "--differs")
        assert kitchen.main("--as", "user", "answer", "1", *said)[0] == 0
        return listed

    monkeypatch.setattr(waiting, "keep", answered_after_the_list)
    kitchen.poll(later(10))
    assert decisions(kitchen, "alpha") == []


def test_a_row_still_unapproved_after_the_grace_is_raised_once(kitchen):
    kitchen.poll()
    add(kitchen, "alpha", approve=False)
    kitchen.poll(later(10))
    assert decisions(kitchen, "alpha") == []
    kitchen.poll(later(10) + timedelta(seconds=blockers.APPROVE_GRACE_SECONDS))
    kitchen.poll(later(30))
    (decided,) = decisions(kitchen, "alpha")
    assert decided.startswith("decision alpha: approve alpha: jbus --project demo queue approve")


def test_a_gate_that_holds_is_raised_in_the_pass_that_lists_it(kitchen):
    kitchen.poll()
    safe = "Holds: deletes data\nFail-safe: the dry-run lists what goes\n"
    holds = ASK.replace("Undo: pick the other\n", f"Undo: pick the other\n{safe}")
    assert kitchen.main("gate", "alpha", stdin=holds) == (0, "queued: question 1\n")
    kitchen.poll(later(10))
    assert decisions(kitchen, "alpha") == [
        "decision alpha: question 1: which one, it holds (deletes data) for your answer. "
        'Reply: "demo question 1: default"'
    ]


def test_a_raised_row_approved_in_the_next_pass_tells_no_one_it_left(kitchen):
    kitchen.poll()
    add(kitchen, "alpha", approve=False)
    kitchen.poll(later(10))
    kitchen.poll(later(20))
    assert len(decisions(kitchen, "alpha")) == 1
    posts = len(kitchen.wakes.posts)
    assert go(kitchen, "alpha")[0] == 0
    kitchen.poll(later(30))
    kitchen.poll(later(40))
    assert len(decisions(kitchen, "alpha")) == 1 and len(kitchen.wakes.posts) == posts
    built = digest.build(jbus.load(), now=later(41))["projects"]["demo"]
    assert "approve:alpha" not in [one["key"] for one in built["waiting"]]
