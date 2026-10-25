"""The root's watch of its child homes (`jbus.children`): a child with work out that stays quiet
for its patience is nudged, the user hears of it at once, it is nudged once more, and then the
user is asked, and nothing more is sent in that spell. Something the child does that the root can
see ends the spell, and its home's reply to a nudge does not. A routine, a scope with a `rhythm`
file, is watched with nothing out. `jbus out --scope` says what a scope has out."""

from datetime import timedelta

import pytest

from jbus import children
from test_jbus_kitchen import NOW
from test_jbus_leftover import home
from test_jbus_queue import add, brief
from test_jbus_row_ends import sends

P = children.PATIENCE


def minutes(n):
    return NOW + timedelta(minutes=n)


@pytest.fixture
def child(kitchen):
    """A root home, the scope `sc` with a home thread quiet for six hours, and a crew of its
    launched at NOW that writes nothing after."""
    home(kitchen)
    found = home(kitchen, "sc", idle=timedelta(hours=6))
    (kitchen.home / "sc" / "plan.md").write_text("# sc: plan\n")
    add(kitchen, "sc-alpha", text=brief("sc-alpha").replace("Home: mcp:a-home", "Home: sc"))
    kitchen.poll(NOW)
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: sc-alpha"]
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.forget()
    return kitchen, found, crew


def told(kitchen):
    return [
        e["line"] for e in kitchen.events() if e["loud"] == "user" and "home-stall" in e["line"]
    ]


def test_a_quiet_child_is_nudged_twice_then_the_user_is_asked_and_nothing_more(child):
    kitchen, found, _ = child
    for n in range(10, 5 * P, 10):
        kitchen.poll(minutes(n))
        nudges = [one for one in sends(kitchen) if one["threadId"] == found["threadId"]]
        assert len(nudges) == (0 if n < P else 1 if n < 2 * P else 2)
        assert len(told(kitchen)) == (0 if n < P else 1 if n < 3 * P else 2)
    first, asked = told(kitchen)
    assert "nudged it" in first and "after two nudges" in asked


def test_a_write_of_its_crew_ends_the_spell(child):
    kitchen, found, crew = child
    kitchen.poll(minutes(P + 1))
    assert len(told(kitchen)) == 1
    crew["updatedAt"] = minutes(P + 5).isoformat().replace("+00:00", "Z")
    crew["items"] = 99
    kitchen.poll(minutes(P + 6))
    for n in range(P + 10, 2 * P, 10):
        kitchen.poll(minutes(n))
    assert len([one for one in sends(kitchen) if one["threadId"] == found["threadId"]]) == 1


def test_the_homes_reply_to_a_nudge_does_not_end_the_spell(child):
    kitchen, found, _ = child
    kitchen.poll(minutes(P + 1))
    found["updatedAt"] = minutes(P + 2).isoformat().replace("+00:00", "Z")
    found["items"] = 99
    kitchen.poll(minutes(2 * P + 2))
    assert len([one for one in sends(kitchen) if one["threadId"] == found["threadId"]]) == 2


def test_a_routine_that_misses_its_beat_is_flagged_with_nothing_out(kitchen):
    home(kitchen)
    found = home(kitchen, "beat", idle=timedelta(hours=6))
    (kitchen.home / "beat" / "plan.md").write_text("# beat: plan\n")
    (kitchen.home / "beat" / "rhythm").write_text("30\n")
    kitchen.poll(NOW)
    assert [one["threadId"] for one in sends(kitchen)] == [found["threadId"]]
    assert len(told(kitchen)) == 1


def test_a_child_with_nothing_out_is_not_watched(kitchen):
    home(kitchen)
    home(kitchen, "idle", idle=timedelta(hours=6))
    (kitchen.home / "idle" / "plan.md").write_text("# idle: plan\n")
    kitchen.poll(NOW)
    assert sends(kitchen) == [] and told(kitchen) == []


def test_jbus_out_says_what_a_scope_has_out_and_refuses_one_with_no_plan(child):
    kitchen, _, _ = child
    kitchen.poll(minutes(1))
    code, said = kitchen.main("--project", "demo", "out", "--scope", "sc")
    assert code == 0
    assert said.splitlines()[0] == "out sc-alpha: row launched"
    assert any("crew thread" in line for line in said.splitlines())
    code, said = kitchen.main("--project", "demo", "out", "--scope", "nothing")
    assert code == 1 and said.startswith("refused: ")


def test_jbus_out_says_unknown_when_the_last_pass_is_too_old_to_trust(child, monkeypatch):
    kitchen, _, _ = child
    late = NOW + timedelta(minutes=children.STALE + 1)
    monkeypatch.setattr(children.queue, "clock", lambda: late)
    code, said = kitchen.main("--project", "demo", "out", "--scope", "sc")
    assert code == 1 and said.startswith("unknown: jbus's last pass is ")
