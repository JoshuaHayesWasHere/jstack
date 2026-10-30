"""jbus's watch of the homes (`jbus.children`): a child or the root with work out that stays
quiet for its patience is nudged, the user hears of it at once, it is nudged once more, and then the
user is asked, and nothing more is sent in that spell. Something the child does that the root can
see ends the spell, and its home's reply to a nudge does not. A routine, a scope with a `rhythm`
file, is watched with nothing out. `jbus out --scope` says what a scope has out."""

from datetime import timedelta

import pytest

from jbus import children, questions
from test_jbus_kitchen import GATE, NOW, PROJECT
from test_jbus_leftover import home
from test_jbus_queue import add, brief
from test_jbus_row_ends import sends

P = children.PATIENCE
STALL = f"{children.STALL}|"


def minutes(n):
    return NOW + timedelta(minutes=n)


@pytest.fixture
def child(kitchen):
    """A root home, the scope `sc` with a home thread quiet for six hours, and a crew of its
    launched at NOW that writes nothing after."""
    home(kitchen)
    found = home(kitchen, "sc", idle=timedelta(hours=6))
    (kitchen.home / "sc" / "plan.md").write_text("# sc: plan\n")
    add(kitchen, "sc-alpha", text=brief("sc-alpha").replace("Home: root", "Home: sc"))
    kitchen.poll(NOW)
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: sc-alpha"]
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.forget()
    return kitchen, found, crew


def told(kitchen):
    return [e["line"] for e in kitchen.events(children.STALL)]


def test_a_quiet_child_is_nudged_twice_then_the_user_is_asked_and_nothing_more(child):
    kitchen, found, _ = child
    for n in range(10, 5 * P, 10):
        kitchen.poll(minutes(n))
        nudges = [one for one in sends(kitchen) if one["threadId"] == found["threadId"]]
        assert len(nudges) == (0 if n < P else 1 if n < 2 * P else 2)
        assert len(told(kitchen)) == (0 if n < P else 1 if n < 3 * P else 2)
    first, asked = told(kitchen)
    assert "nudged it" in first and "after two nudges" in asked


def test_each_step_of_a_spell_waits_a_patience_after_the_last_one_after_a_long_gap(child):
    """A child first checked long after it went quiet (jbus stopped overnight) is nudged at once,
    and the second nudge and the question each wait a patience after the step before."""
    kitchen, found, _ = child
    start = 10 * P
    for n in [start, start + 1, start + 2, start + P - 1]:
        kitchen.poll(minutes(n))
    assert len([one for one in sends(kitchen) if one["threadId"] == found["threadId"]]) == 1
    assert len(told(kitchen)) == 1
    kitchen.poll(minutes(start + P))
    assert len([one for one in sends(kitchen) if one["threadId"] == found["threadId"]]) == 2
    kitchen.poll(minutes(start + 2 * P - 1))
    assert len(told(kitchen)) == 1
    kitchen.poll(minutes(start + 2 * P))
    assert len(told(kitchen)) == 2


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
    nudged = [one for one in sends(kitchen) if not one["clientRequestId"].startswith("wakes|")]
    assert [one["threadId"] for one in nudged] == [found["threadId"]]
    (line,) = told(kitchen)
    assert kitchen.wakes.said == [line]


def test_a_child_with_nothing_out_is_not_watched(kitchen):
    home(kitchen)
    home(kitchen, "idle", idle=timedelta(hours=6))
    (kitchen.home / "idle" / "plan.md").write_text("# idle: plan\n")
    kitchen.poll(NOW)
    assert sends(kitchen) == [] and told(kitchen) == []


@pytest.fixture
def root(kitchen):
    """A root home with no scope, its thread quiet for six hours, and a crew of its launched at
    NOW that writes nothing after. Its thread keeps its count of items, so a wake queued to it is
    no write, as in T3 Code (`test_a_message_queued_to_a_silent_thread_is_no_write`)."""
    found = home(kitchen, idle=timedelta(hours=6), itemCount=40)
    add(kitchen, "alpha")
    kitchen.poll(NOW)
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: alpha"]
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.forget()
    return kitchen, found


def test_a_quiet_root_home_is_nudged_twice_then_the_user_is_asked(root):
    """The root home is watched as a scoped home is: its nudge names no scope."""
    kitchen, found = root
    for n in range(10, 5 * P, 10):
        kitchen.poll(minutes(n))
        nudges = [one for one in sends(kitchen) if one["clientRequestId"].startswith(STALL)]
        assert [one["threadId"] for one in nudges] == [found["threadId"]] * (
            0 if n < P else 1 if n < 2 * P else 2
        )
        assert len(told(kitchen)) == (0 if n < P else 1 if n < 3 * P else 2)
    first = nudges[0]
    assert "the root home has had" in first["message"] and "`jbus plan`" in first["message"]
    assert "--scope" not in first["message"]
    stalled, asked = told(kitchen)
    assert "nudged it" in stalled and "after two nudges" in asked


@pytest.mark.parametrize("name", ["queue.json", "questions.json"])
def test_a_file_that_does_not_parse_holds_the_watch_and_the_pass_still_ends(root, name):
    """A queue or question file that does not parse says nothing of what a home has out: the
    pass gates it and ends well, nudges no home, and the watch goes on once it parses again."""
    kitchen, found = root
    file = kitchen.state / name
    kept = file.read_text() if file.exists() else None
    file.write_text("not json")
    kitchen.poll(minutes(P + 10))
    assert f"condition demo: {name} does not parse" in kitchen.lines("condition")
    assert [one for one in sends(kitchen) if one["clientRequestId"].startswith(STALL)] == []
    if kept is None:
        file.unlink()
    else:
        file.write_text(kept)
    kitchen.poll(minutes(P + 20))
    nudges = [one for one in sends(kitchen) if one["clientRequestId"].startswith(STALL)]
    assert [one["threadId"] for one in nudges] == [found["threadId"]]


def test_a_root_home_with_nothing_out_is_not_watched(kitchen):
    home(kitchen, idle=timedelta(hours=6))
    kitchen.poll(NOW)
    kitchen.poll(minutes(3 * P))
    assert not [one for one in sends(kitchen) if one["clientRequestId"].startswith(STALL)]
    assert told(kitchen) == []


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


def test_jbus_out_says_unknown_while_the_last_pass_could_not_ask_t3_code(child):
    """The pass that cannot list the project's threads keeps the list an earlier pass left, so a
    crew launched since is not on it: `jbus out` says so, and the handoff keeps the scope open."""
    kitchen, _, _ = child
    kitchen.t3.down.add(PROJECT)
    kitchen.poll(minutes(1))
    code, said = kitchen.main("--project", "demo", "out", "--scope", "sc")
    assert code == 1
    assert said.startswith("unknown: jbus's last pass could not ask T3 Code about demo")


def test_a_root_home_with_only_a_gate_out_is_not_watched(kitchen):
    """An open gate waits on the user, not on the root home, and the root cannot be retired: with
    nothing else out, its quiet thread is neither nudged nor told of."""
    home(kitchen, idle=timedelta(hours=6))
    (kitchen.home / "gates.md").write_text("## Gate 1: ship it?\nStatus: open\n")
    assert children.out(kitchen.home, kitchen.home, kitchen.state, []) == ["out gate 1: ship it?"]
    for n in range(0, 5 * P, 10):
        kitchen.poll(minutes(n))
    assert not [one for one in sends(kitchen) if one["clientRequestId"].startswith(STALL)]
    assert told(kitchen) == []


def hold(kitchen, slug):
    """Ask the user a question for `slug` that deletes data, so it waits on the user's own answer
    and no pass settles it on its default."""
    lines = GATE.format(n=1, asked="drop the old rows?", status="open", slug=slug).replace(
        "Option:", "Holds: deletes data\nFail-safe: a dump of the rows at ~/rows.sql\nOption:", 1
    )
    return questions.ask(kitchen.state, kitchen.home, slug, lines, NOW)[0]


def test_a_child_whose_only_open_item_waits_on_the_user_is_not_watched(kitchen):
    """A child home with nothing out but a hold it asked the user and an open gate can do nothing
    until the user answers: its quiet thread is neither nudged nor raised to the user."""
    home(kitchen)
    found = home(kitchen, "sb", idle=timedelta(hours=6))
    (kitchen.home / "sb" / "plan.md").write_text("# sb: plan\n")
    (kitchen.home / "sb" / "gates.md").write_text("## Gate 1: ship it?\nStatus: open\n")
    asked = hold(kitchen, "home-sb")
    assert children.out(kitchen.home, kitchen.home / "sb", kitchen.state, []) == [
        f"out question {asked.number}: drop the old rows?",
        "out gate 1: ship it?",
    ]
    for n in range(0, 5 * P, 10):
        kitchen.poll(minutes(n))
    assert [one for one in sends(kitchen) if one["threadId"] == found["threadId"]] == []
    assert told(kitchen) == []


def test_a_child_with_a_hold_and_a_quiet_crew_is_still_nudged(child):
    """A hold waiting on the user does not shield the rest of what a child has out: its quiet crew
    still gets the child nudged twice, and then the user is asked."""
    kitchen, found, _ = child
    hold(kitchen, "home-sc")
    for n in range(10, 5 * P, 10):
        kitchen.poll(minutes(n))
    nudges = [one for one in sends(kitchen) if one["threadId"] == found["threadId"]]
    assert len(nudges) == 2 and "has had 2 things out" in nudges[0]["message"]
    first, asked = told(kitchen)
    assert "nudged it" in first and "after two nudges" in asked
