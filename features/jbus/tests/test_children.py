"""jbus's watch of the homes (`jbus.children`): a home with work out that stays quiet for its
patience is nudged, nudged once more, started again on a fresh thread, and then put on `jbus
needs`, and nothing more is sent in that spell. A home jbus started that stalls again is not started
a second time. Something the home does that jbus can see ends the spell, and its home's reply to a
nudge does not. A routine, a scope with a `rhythm` file, is watched with nothing out. The catch-all,
`uncategorized`, is kept running: a pass launches its home when it has no live thread. No home's
stall wakes the root. `jbus out --scope` says what a scope has out."""

import collections
import json
import os
import pathlib
from datetime import timedelta

import pytest

import jbus
from jbus import alert, blockers, children, passes, questions, stalls, watch
from jroles import ledger
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
    add(kitchen, "sc-alpha", text=brief("sc-alpha").replace("Home: uncategorized", "Home: sc"))
    kitchen.poll(NOW)
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: sc-alpha"]
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.forget()
    return kitchen, found, crew


def told(kitchen):
    return [e["line"] for e in kitchen.events(children.STALL)]


def homes(kitchen):
    """The launch of each home's thread a pass made."""
    return [one for one in kitchen.t3.launches if one["title"].startswith(children.TITLE)]


def needs(kitchen):
    """What `jbus needs` prints for the project."""
    code, said = kitchen.main("--project", "demo", "needs")
    assert code == 0
    return said


def test_a_quiet_child_is_nudged_twice_then_started_again_then_on_needs_and_nothing_more(child):
    """A home quiet with work out is nudged at its patience and again a patience later. A
    patience after the second nudge jbus launches `/home <scope>` on a fresh thread; a patience
    after that, still quiet, the home is on `jbus needs`, and nothing more is sent or launched."""
    kitchen, found, _ = child
    for n in range(10, 6 * P, 10):
        kitchen.poll(minutes(n))
        nudges = [one for one in sends(kitchen) if one["threadId"] == found["threadId"]]
        assert len(nudges) == (0 if n < P else 1 if n < 2 * P else 2)
        assert len(homes(kitchen)) == (0 if n < 3 * P else 1)
        assert len(told(kitchen)) == (0 if n < P else 1 if n < 4 * P else 2)
        assert ("stalled" in needs(kitchen)) == (n >= 4 * P)
    (launch,) = homes(kitchen)
    assert launch["message"] == "/home sc"
    assert launch["workspaceStrategy"] == {"type": "root"}
    assert (
        "after two nudges"
        in json.loads((kitchen.state / "relaunches.json").read_text())["sc"]["why"]
    )
    first, asked = told(kitchen)
    assert "nudged it" in first and "after jbus started it again" in asked
    assert "home-sc" in needs(kitchen) or "sc:" in needs(kitchen)


def test_a_home_jbus_started_again_that_stalls_again_is_on_needs_and_not_started_again(child):
    """The thread jbus launched starts and writes its `home-id`. A crew's write ends the spell.
    When the home then stalls again it is nudged twice and goes on `jbus needs` with no second
    launch."""
    kitchen, found, crew = child
    for n in range(10, 3 * P + 1, 10):
        kitchen.poll(minutes(n))
    assert len(homes(kitchen)) == 1
    ours = json.loads((kitchen.state / "relaunches.json").read_text())["sc"]["thread"]
    (fresh,) = [one for one in kitchen.t3.threads if one["threadId"] == ours]
    assert fresh is not found
    (kitchen.home / "sc" / "home-id").write_text(fresh["threadId"] + "\n")
    kitchen.t3.at_work.discard(fresh["threadId"])
    fresh.update(status="completed", itemCount=40)
    crew["updatedAt"] = minutes(3 * P + 5).isoformat().replace("+00:00", "Z")
    crew["items"] = 99
    kitchen.poll(minutes(3 * P + 6))
    assert json.loads((kitchen.state / "stalls.json").read_text())["sc"]["step"] == "calm"
    for n in range(3 * P + 10, 8 * P, 10):
        kitchen.poll(minutes(n))
    nudged = [one for one in sends(kitchen) if one["threadId"] == fresh["threadId"]]
    assert len([one for one in nudged if one["clientRequestId"].startswith(STALL)]) == 2
    assert len(homes(kitchen)) == 1
    (item,) = stalls.stalled(kitchen.state)
    assert item["slug"] == "home-sc"
    said = needs(kitchen)
    assert item["line"] in said
    assert blockers.needs(item) in said
    assert blockers.reply(item) in said


def test_no_home_stall_reaches_the_root(child):
    """Through a whole spell of a scope's stall, nothing about it is sent to the root's thread and
    no home-stall alert is open, while `jbus needs` lists the stalled home."""
    kitchen, _, _ = child
    root = (kitchen.home / "home-id").read_text().split()[0]
    for n in range(10, 6 * P, 10):
        kitchen.poll(minutes(n))
        to_root = [one["message"] for one in sends(kitchen) if one["threadId"] == root]
        assert not [one for one in to_root if children.STALL in one]
        streaks = alert.streaks(kitchen.state_dir)
        assert not [key for key in streaks if key.startswith(children.STALL)]
    assert "stalled" in needs(kitchen)


def test_a_home_stall_alert_left_open_from_before_is_retired(child):
    """An alert a stall raised before the stall went on `jbus needs` is retired on the next pass,
    so it no longer wakes the root."""
    kitchen, _, _ = child
    key = f"{children.STALL} demo sc"
    alert.raise_(jbus.load(), key, f"{children.STALL} sc: old", owner="demo", now=NOW)
    kitchen.poll(minutes(1))
    assert key not in alert.streaks(kitchen.state_dir)


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
    assert homes(kitchen) == []
    kitchen.poll(minutes(start + 2 * P))
    assert len(homes(kitchen)) == 1
    kitchen.poll(minutes(start + 3 * P - 1))
    assert len(told(kitchen)) == 1
    kitchen.poll(minutes(start + 3 * P))
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
    assert line not in kitchen.wakes.said


def test_a_child_with_nothing_out_is_not_watched(kitchen):
    home(kitchen)
    home(kitchen, "idle", idle=timedelta(hours=6))
    (kitchen.home / "idle" / "plan.md").write_text("# idle: plan\n")
    kitchen.poll(NOW)
    assert sends(kitchen) == [] and told(kitchen) == []


@pytest.fixture
def root(kitchen):
    """A root home with no scope, its thread quiet for six hours, and a crew of the catch-all's,
    which the root stands in for, launched at NOW that writes nothing after. Its thread keeps its
    count of items, so a wake queued to it is no write, as in T3 Code
    (`test_a_message_queued_to_a_silent_thread_is_no_write`)."""
    found = home(kitchen, idle=timedelta(hours=6), itemCount=40)
    add(kitchen, "alpha")
    kitchen.poll(NOW)
    (crew,) = [one for one in kitchen.t3.threads if one["title"] == "crew: alpha"]
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.forget()
    return kitchen, found


def test_a_quiet_catch_all_the_root_stands_in_for_is_nudged_twice_then_started(root):
    """The catch-all, `uncategorized`, is watched as a scoped home is. While it has no thread of
    its own, the root's thread is nudged for it, and its nudge names the root's plan, no scope.
    After the second, jbus makes its directory and launches `/home uncategorized`."""
    kitchen, found = root
    for n in range(10, 5 * P, 10):
        kitchen.poll(minutes(n))
        nudges = [one for one in sends(kitchen) if one["clientRequestId"].startswith(STALL)]
        assert [one["threadId"] for one in nudges] == [found["threadId"]] * (
            0 if n < P else 1 if n < 2 * P else 2
        )
        assert len(told(kitchen)) == (0 if n < P else 1 if n < 4 * P else 2)
    first = nudges[0]
    assert "the home uncategorized has had" in first["message"]
    assert "`jbus plan`" in first["message"]
    assert "--scope" not in first["message"]
    assert [one["message"] for one in homes(kitchen)] == ["/home uncategorized"]
    assert (kitchen.home / "uncategorized" / "plan.md").exists()
    stalled, asked = told(kitchen)
    assert "nudged it" in stalled and "after jbus started it again" in asked


def test_a_spell_kept_under_the_old_name_is_read_once_and_moved(root):
    """A state that holds only `children.json`, as an older jbus wrote it, goes on with the spell
    it keeps, the home nudged once, and the file is `stalls.json` from then on."""
    kitchen, _ = root
    kitchen.poll(minutes(P + 10))
    assert len(told(kitchen)) == 1
    spell = json.loads((kitchen.state / "stalls.json").read_text())
    assert spell["uncategorized"]["step"] == "nudged1"
    (kitchen.state / "stalls.json").replace(kitchen.state / "children.json")
    kitchen.poll(minutes(P + 20))
    assert not (kitchen.state / "children.json").exists()
    assert json.loads((kitchen.state / "stalls.json").read_text()) == spell


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
    assert len(homes(kitchen)) == 1
    first, asked = told(kitchen)
    assert "nudged it" in first and "after jbus started it again" in asked


@pytest.fixture
def started(kitchen):
    """A project whose home has started: a root `plan.md` and the root's thread."""
    home(kitchen)
    (kitchen.home / "plan.md").write_text("# plan\n")
    return kitchen


def test_a_pass_makes_the_catch_all_and_launches_its_home_once(started):
    """With no `uncategorized/`, a pass makes it with its plan and launches `/home
    uncategorized` in the project's own checkout. A pass while that launch starts launches
    nothing."""
    kitchen = started
    kitchen.poll(NOW)
    (launch,) = homes(kitchen)
    assert launch["message"] == "/home uncategorized"
    assert launch["title"] == "home: demo uncategorized"
    assert launch["workspaceStrategy"] == {"type": "root"}
    assert (kitchen.home / "uncategorized" / "plan.md").exists()
    kitchen.poll(minutes(10))
    kitchen.poll(minutes(P + 10))
    assert len(homes(kitchen)) == 1


@pytest.mark.parametrize("gone", ["archived", "missing"])
def test_a_catch_all_whose_thread_is_archived_or_missing_is_launched_again(started, gone):
    kitchen = started
    if gone == "archived":
        found = home(kitchen, "uncategorized")
        found["archived"] = True
    else:
        (kitchen.home / "uncategorized").mkdir()
        (kitchen.home / "uncategorized" / "home-id").write_text("mcp:no-such-thread\n")
    (kitchen.home / "uncategorized" / "plan.md").write_text("# uncategorized: plan\n")
    kitchen.poll(NOW)
    (launch,) = homes(kitchen)
    assert launch["message"] == "/home uncategorized"
    assert (
        "archived or gone"
        in json.loads((kitchen.state / "relaunches.json").read_text())["uncategorized"]["why"]
    )


def test_a_catch_all_whose_thread_is_live_launches_nothing(started):
    kitchen = started
    home(kitchen, "uncategorized", idle=timedelta(hours=6))
    (kitchen.home / "uncategorized" / "plan.md").write_text("# uncategorized: plan\n")
    for n in (0, 10, P + 10, 3 * P):
        kitchen.poll(minutes(n))
    assert homes(kitchen) == []


@pytest.mark.parametrize("answer", ["refused", "lost"])
def test_a_catch_all_whose_thread_cannot_be_read_is_not_launched_again(started, answer):
    """A read T3 Code refuses for a reason other than a gone thread, or whose reply is lost, says
    nothing of whether the thread is live, so the pass launches nothing and says why."""
    kitchen = started
    (kitchen.home / "uncategorized").mkdir()
    (kitchen.home / "uncategorized" / "home-id").write_text("mcp:unread\n")
    (kitchen.home / "uncategorized" / "plan.md").write_text("# uncategorized: plan\n")
    if answer == "lost":
        kitchen.t3.lose_read = True
    else:
        result = kitchen.t3.result

        def refusing(asked):
            if asked.get("params", {}).get("name") == "t3_thread_read":
                return {"isError": True, "content": [{"type": "text", "text": "not allowed"}]}
            return result(asked)

        kitchen.t3.result = refusing
    said = kitchen.poll(NOW)
    assert homes(kitchen) == []
    assert any("wait home: its thread mcp:unread could not be read" in one for one in said)


def test_a_launch_whose_reply_is_lost_is_not_launched_again_within_its_patience(started):
    kitchen = started
    kitchen.t3.lose = "after"
    said = kitchen.poll(NOW)
    assert any("launch home uncategorized: no reply" in one for one in said)
    kitchen.t3.lose = None
    kitchen.poll(minutes(10))
    assert len(homes(kitchen)) == 1
    kitchen.poll(minutes(P + 10))
    assert len(homes(kitchen)) == 2


@pytest.mark.parametrize("ended", ["failed", "completed"])
def test_a_catch_all_whose_launch_wrote_no_home_id_in_its_patience_is_launched_again(
    started, ended
):
    """A launch whose thread T3 Code still lists, but whose start failed or went idle with no
    `home-id` written, is launched again once it is older than `PATIENCE`, and at most once in
    that time."""
    kitchen = started
    kitchen.poll(NOW)
    (launch,) = homes(kitchen)
    (thread,) = [one for one in kitchen.t3.threads if one["title"] == launch["title"]]
    thread["status"] = ended
    kitchen.t3.at_work.discard(thread["threadId"])
    kitchen.poll(minutes(10))
    assert len(homes(kitchen)) == 1
    kitchen.poll(minutes(P + 10))
    assert len(homes(kitchen)) == 2
    assert not (kitchen.home / "uncategorized" / "home-id").exists()
    kitchen.poll(minutes(P + 20))
    assert len(homes(kitchen)) == 2


def test_a_catch_all_is_not_launched_while_the_dispatch_is_stopped(started):
    kitchen = started
    kitchen.state_dir.mkdir(parents=True, exist_ok=True)
    (kitchen.state_dir / "stop").write_text("")
    said = kitchen.poll(NOW)
    assert homes(kitchen) == []
    assert any("the dispatch is off or stopped" in one for one in said)


PRIME = "claudeAgent_claude_prime"


def test_a_catch_all_launches_on_the_model_the_role_map_gives_the_home(started, jstack_config):
    kitchen = started
    (jstack_config.parent / "roles").write_text(
        f"home: claudeAgent claude-opus-5-5 claudeAgent,{PRIME}\n"
    )
    kitchen.poll(NOW)
    (launch,) = homes(kitchen)
    assert launch["modelSelection"]["model"] == "claude-opus-5-5"
    assert launch["modelSelection"]["instanceId"] == "claudeAgent"


def test_a_catch_all_waits_when_no_instance_of_the_home_pool_can_run(started, jstack_config):
    kitchen = started
    (jstack_config.parent / "roles").write_text(
        f"home: claudeAgent claude-opus-5-5 claudeAgent,{PRIME}\n"
    )
    kitchen.machine(plan=None)
    weekly = "You've hit your weekly limit · resets Oct 18, 4pm (America/New_York)"
    for instance in ("claudeAgent", PRIME):
        ledger.write(ledger.cap_of([{"text": weekly}], NOW).record(instance))
    said = kitchen.poll(NOW)
    assert homes(kitchen) == []
    assert any("wait home uncategorized: no launch: " in one for one in said)


SIGNED_OUT = ["Provider is not authenticated."]


def test_a_catch_all_launches_on_the_first_instance_of_the_home_pool_that_can_sign_in(
    started, jstack_config
):
    """claudeAgent is first in the pool and signed out: the home starts on the next instance on
    its first try, and on claudeAgent again once it signs in."""
    kitchen = started
    (jstack_config.parent / "roles").write_text(
        f"home: claudeAgent claude-opus-5-5 claudeAgent,{PRIME}\n"
    )
    kitchen.t3.constraints["claudeAgent"] = SIGNED_OUT
    kitchen.poll(NOW)
    (launch,) = homes(kitchen)
    assert launch["modelSelection"]["instanceId"] == PRIME
    (thread,) = [one for one in kitchen.t3.threads if one["title"] == launch["title"]]
    thread["status"] = "failed"
    kitchen.t3.at_work.discard(thread["threadId"])
    kitchen.t3.constraints["claudeAgent"] = []
    kitchen.poll(minutes(P + 1))
    assert [one["modelSelection"]["instanceId"] for one in homes(kitchen)] == [PRIME, "claudeAgent"]


def test_a_catch_all_launches_nothing_while_no_instance_of_the_home_pool_can_sign_in(
    started, jstack_config
):
    kitchen = started
    (jstack_config.parent / "roles").write_text(
        f"home: claudeAgent claude-opus-5-5 claudeAgent,{PRIME}\n"
    )
    for instance in ("claudeAgent", PRIME):
        kitchen.t3.constraints[instance] = SIGNED_OUT
    for n in (0, P + 1):
        said = kitchen.poll(minutes(n))
        assert homes(kitchen) == []
        assert any(
            "wait home uncategorized: no launch: claudeAgent cannot sign in" in one for one in said
        )
    key = f"signed-out claudeAgent,{PRIME}"
    assert key in alert.streaks(kitchen.state_dir)


def test_a_catch_all_waits_when_the_role_map_gives_the_home_no_model(started, jstack_config):
    kitchen = started
    (jstack_config.parent / "roles").write_text("home: nobody\n")
    said = kitchen.poll(NOW)
    assert homes(kitchen) == []
    assert any("the role map gives the home no model" in one for one in said)


def test_a_project_whose_home_has_not_started_launches_no_catch_all(kitchen):
    home(kitchen)
    kitchen.poll(NOW)
    assert homes(kitchen) == []
    assert not (kitchen.home / "uncategorized").exists()


def reads_of_tasks(monkeypatch):
    """Count each read of a brief under a `tasks/` directory, by file name."""
    reads = collections.Counter()
    real = pathlib.Path.read_text

    def counted(self, *args, **kwargs):
        if self.parent.name == "tasks" and self.suffix == ".md":
            reads[self.name] += 1
        return real(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", counted)
    return reads


def test_the_watch_of_many_homes_reads_each_brief_once(child, monkeypatch):
    """However many scopes the root has, the watch of the homes reads each brief once a pass, and
    still finds the quiet child its brief names."""
    kitchen, found, _ = child
    home(kitchen, "sd", idle=timedelta(hours=6))
    home(kitchen, "se", idle=timedelta(hours=6))
    reads = reads_of_tasks(monkeypatch)
    during = collections.Counter()
    real = children.watch

    def watched(*args, **kwargs):
        before = reads.copy()
        real(*args, **kwargs)
        during.update(reads - before)

    monkeypatch.setattr(children, "watch", watched)
    kitchen.poll(minutes(P + 1))
    assert during["sc-alpha.md"] == 1
    assert [one for one in sends(kitchen) if one["threadId"] == found["threadId"]]


def test_a_brief_is_read_once_a_pass_until_it_is_rewritten(kitchen, monkeypatch):
    """`watch.brief_of` reads a brief once a pass however many steps ask for it, and a step that
    writes the brief later in the same pass is seen by the steps after it: a new text of the same
    size, a longer one, and the brief's removal from `tasks/`, which leaves the queued brief."""
    add(kitchen, "alpha")
    config = jbus.load()
    run = passes.Pass(config, config.projects[0], NOW, lambda _: None)
    task = kitchen.home / "tasks" / "alpha.md"
    task.write_text("# alpha\nStatus: one\n")
    reads = reads_of_tasks(monkeypatch)
    assert watch.brief_of(run, "alpha") == "# alpha\nStatus: one\n"
    assert watch.brief_of(run, "alpha") == "# alpha\nStatus: one\n"
    assert reads["alpha.md"] == 1
    stamp = task.stat().st_mtime_ns
    task.write_text("# alpha\nStatus: two\n")
    os.utime(task, ns=(stamp + 1, stamp + 1))
    assert watch.brief_of(run, "alpha") == "# alpha\nStatus: two\n"
    task.write_text("# alpha\nStatus: two\n\n## Result\nStatus: done\n")
    assert watch.brief_of(run, "alpha").endswith("## Result\nStatus: done\n")
    task.unlink()
    assert watch.brief_of(run, "alpha") == (run.state / "briefs" / "alpha.md").read_text()
