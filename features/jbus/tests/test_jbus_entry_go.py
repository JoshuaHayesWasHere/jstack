"""The user's go is given to a plan entry once, and each row filed under it is approved by rule.

`jbus plan go <entry> --message <thread>/<message>` keeps the user's own message as the go of the
entry, bound to its head (its heading and its `Done when:` lines). Under the setting `go = "entry"`,
the default, jbus approves a row queued with `--entry <entry>` when it is queued and on each pass,
an edit of its brief too, while the go holds. The go stops holding when the head changes, when the
entry closes, or on `jbus plan stop`. A row whose brief names a case of `gates.md` on a `Holds:`
line waits for the user under every setting.

Under `go = "silence"`, a home parks its pick for a row as a gate whose default is `approve`. The
gate stays open for `go_quiet_minutes`, and its close by silence approves a row of size S or M with
one pull request. The tests run the real commands and the real pass against the kitchen's fakes.
"""

import json
from datetime import datetime, timedelta

import pytest

import jbus
from jbus import leftover, questions, queue, wakes
from jmerge import judgement
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_leftover import home
from test_jbus_queue import brief, rows, widened
from test_jbus_row_ends import result

HOME, MESSAGE = "mcp:a-home", "a-go-of-his"
HEARD_AT = "2026-10-12 10:30 ET"
PLAN = """\
# demo: plan

## epic: one path for each fact
Stage: planned
Size: M
Done when:
- it works
Decisions:
- "go on it"

## other: another entry
Stage: planned
Done when:
- it also works
"""
GATE = (
    "## Gate <n>: start {slug}?\nStatus: open\nAsked by: home, thread mcp:a-home\n"
    "Default: approve\nBuilt on it: nothing yet\nUndo: hold the row\n"
    "Option: start it (default, recommended): the row launches\nOption: wait: it waits\n"
)


class Frozen(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


@pytest.fixture
def kitchen(tmp_path, monkeypatch, jstack_config):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "plan.md").write_text(PLAN)
    monkeypatch.setattr(questions, "datetime", Frozen)
    made.settings = jstack_config
    yield made
    made.close()


def queued(kitchen, slug, entry="epic", text=None):
    argv = ["queue", "add", slug, "--priority", "1", *(["--entry", entry] if entry else [])]
    code, said = kitchen.main(*argv, stdin=text or brief(slug))
    assert code == 0, said
    return said


def plan_go(kitchen, entry="epic", message=MESSAGE, **more):
    kitchen.t3.says(HOME, message, "go on the epic", **more)
    return kitchen.main("plan", "go", entry, "--message", f"{HOME}/{message}")


def basis(kitchen, slug):
    """Return the basis and the reference of the row's go, or nothing for a row with none."""
    row = rows(kitchen)[slug]
    made = row.get("approval") or {}
    return (made.get("basis"), made.get("ref")) if row["approved"] else ()


def launched(kitchen, slug, status="running"):
    table = kitchen.state / "queue.json"
    listed = json.loads(table.read_text())
    for row in listed:
        if row["slug"] == slug:
            row.update(status=status, thread=f"mcp:crew-{slug}")
    table.write_text(json.dumps(listed))


def test_an_entry_go_approves_each_row_filed_under_it_and_an_edit_with_no_second_word(kitchen):
    queued(kitchen, "alpha")
    code, said = plan_go(kitchen)
    assert code == 0, said
    assert said.startswith("went epic: your go for the plan entry epic, 2026-10-12 10:30 ET")
    assert "approved beta" in queued(kitchen, "beta")
    queued(kitchen, "gamma", entry="other")
    assert basis(kitchen, "alpha") == basis(kitchen, "beta") == (queue.ENTRY, "epic")
    assert basis(kitchen, "gamma") == ()
    made = rows(kitchen)["alpha"]["approval"]
    assert (made["message"], made["words"], made["said_at"]) == (
        f"{HOME}/{MESSAGE}",
        "go on the epic",
        HEARD_AT,
    )
    assert rows(kitchen)["alpha"]["approved"].startswith(
        f"your go for the plan entry epic, {HEARD_AT}, in home: demo; run "
    )
    queued(kitchen, "alpha", text=widened("alpha"))
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")
    assert rows(kitchen)["alpha"]["brief_sha"] == judgement.brief_sha(widened("alpha"))
    code, said = kitchen.main("plan")
    assert code == 0, said
    (line,) = [one for one in said.splitlines() if one.startswith("epic |")]
    assert line.endswith(f"| go {HEARD_AT}")
    assert [one for one in said.splitlines() if one.startswith("other |")] == [
        "other | another entry | 0 of 1 merged, 1 queued not approved"
    ]


def test_a_row_whose_brief_changed_after_it_was_queued_launches_on_the_entry_go(kitchen):
    """No user read the row's brief, so the entry's go pins no sha: an edit is approved again
    by the entry's go and launches with no word of the user's."""
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "alpha", text=widened("alpha"))
    kitchen.poll()
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]
    assert "One more line." in kitchen.t3.launches[0]["message"]


def test_a_row_queued_before_the_go_is_approved_on_the_next_pass(kitchen):
    queued(kitchen, "alpha")
    assert basis(kitchen, "alpha") == ()
    assert plan_go(kitchen)[0] == 0
    kitchen.poll()
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_a_go_for_an_entry_with_no_row_is_refused_and_keeps_no_go(kitchen):
    code, said = plan_go(kitchen)
    assert code == 1, said
    assert said.startswith("refused: epic has no queue row: queue its first row, a scout's")
    assert not (kitchen.state / "goes.json").exists()
    queued(kitchen, "alpha")
    kitchen.poll()
    assert basis(kitchen, "alpha") == ()
    assert kitchen.t3.launches == []


def test_a_message_that_is_not_the_users_own_gives_no_go(kitchen):
    queued(kitchen, "alpha")
    code, said = plan_go(kitchen, createdBy="agent", creationSource="agent", type="agent_message")
    assert code == 1 and said.startswith(f"refused: message {HOME}/{MESSAGE} is not user's own")
    kitchen.poll()
    assert basis(kitchen, "alpha") == ()


def test_a_go_for_an_entry_the_plan_does_not_have_is_refused(kitchen):
    code, said = plan_go(kitchen, entry="nope")
    assert code == 1 and said.startswith("refused: ") and "has no entry nope" in said


def stop(kitchen):
    code, said = kitchen.main("plan", "stop", "epic")
    assert code == 0, said
    return said


def changed_head(kitchen):
    path = kitchen.home / "plan.md"
    path.write_text(path.read_text().replace("- it works\n", "- it works, and fast\n"))


def closed(kitchen):
    path = kitchen.home / "plan.md"
    path.write_text(
        path.read_text().split("## epic:")[0] + "## other:" + PLAN.split("## other:")[1]
    )


@pytest.mark.parametrize("end", [stop, changed_head, closed])
def test_a_go_that_ends_leaves_an_unlaunched_row_waiting_and_a_launched_one_going_on(kitchen, end):
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "beta")
    launched(kitchen, "beta")
    end(kitchen)
    kitchen.poll()
    assert basis(kitchen, "alpha") == ()
    assert not rows(kitchen)["alpha"].get("held")
    assert basis(kitchen, "beta") == (queue.ENTRY, "epic")
    assert "crew: alpha" not in [launch["title"] for launch in kitchen.t3.launches]
    queued(kitchen, "gamma")
    assert basis(kitchen, "gamma") == ()


def test_plan_stop_says_which_rows_wait_again_and_plan_shows_the_stop(kitchen):
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    said = stop(kitchen)
    assert said.startswith("stopped epic's go") and "alpha waits for the user's go" in said
    assert basis(kitchen, "alpha") == ()
    (line,) = [one for one in kitchen.main("plan")[1].splitlines() if one.startswith("epic |")]
    assert "| go stopped " in line
    assert plan_go(kitchen, message="a-second-go")[0] == 0
    kitchen.poll()
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")


def test_a_row_whose_brief_is_a_case_of_gates_md_waits_under_the_entry_go(kitchen):
    queued(kitchen, "alpha", text=brief("alpha", "Holds: spends money\n"))
    assert plan_go(kitchen)[0] == 0
    kitchen.poll()
    assert basis(kitchen, "alpha") == ()


def test_a_case_added_to_a_brief_with_a_go_takes_the_go_back(kitchen):
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "alpha", text=brief("alpha", "Holds: deletes data\n"))
    kitchen.poll()
    assert basis(kitchen, "alpha") == ()


def test_a_case_row_that_follows_a_row_with_the_entry_go_waits_for_the_users_word(kitchen):
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    said = queued(kitchen, "beta", text=brief("beta", "Follows: alpha\nHolds: spends money\n"))
    kitchen.poll()
    assert basis(kitchen, "beta") == ()
    assert "beta waits for the user's go, not a follow-up" in said and "spends money" in said


def silence(kitchen, minutes=30):
    kitchen.settings.write_text(
        kitchen.settings.read_text() + f'go = "silence"\ngo_quiet_minutes = {minutes}\n'
    )


def gate(kitchen, slug):
    code, said = kitchen.main("gate", slug, stdin=GATE.format(slug=slug))
    assert code == 0, said
    return int(said.split()[-1])


def waits_on_user(kitchen):
    kept = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    return [one["key"] for one in kept if one["kind"] == "gate"]


def test_under_silence_a_gated_s_row_is_approved_after_the_window_and_not_before(kitchen):
    silence(kitchen)
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    assert basis(kitchen, "alpha") == ()
    number = gate(kitchen, "alpha")
    kitchen.poll(NOW + timedelta(minutes=29))
    assert basis(kitchen, "alpha") == ()
    assert waits_on_user(kitchen) == [f"gate:q{number}"]
    assert kitchen.t3.launches == []
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha") == ("answer", str(number))
    made = rows(kitchen)["alpha"]["approval"]
    assert made["closed_by"] == questions.SILENCE
    assert [launch["title"] for launch in kitchen.t3.launches] == ["crew: alpha"]


def test_under_silence_a_row_that_follows_a_row_silence_started_waits(kitchen):
    silence(kitchen)
    queued(kitchen, "alpha")
    gate(kitchen, "alpha")
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha")[0] == queue.ANSWER
    big = brief("beta", "Follows: alpha\n").replace("Size: S\n", "Size: L\n")
    said = queued(kitchen, "beta", text=big)
    kitchen.poll(NOW + timedelta(minutes=32))
    assert basis(kitchen, "beta") == ()
    assert "alpha's go goes back to a gate's silence, not the user's word" in said


def test_under_silence_an_l_row_and_a_case_wait_after_the_window(kitchen):
    silence(kitchen)
    queued(kitchen, "alpha", text=brief("alpha").replace("Size: S\n", "Size: L\n"))
    queued(kitchen, "beta", text=brief("beta", "Holds: publishes\n"))
    gate(kitchen, "alpha")
    gate(kitchen, "beta")
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha") == basis(kitchen, "beta") == ()


def test_under_silence_an_answer_that_differs_approves_nothing(kitchen):
    silence(kitchen, minutes=5)
    queued(kitchen, "alpha")
    number = gate(kitchen, "alpha")
    code, said = kitchen.main(
        "answer", str(number), "--by", "user", "--at", "2026-10-12 11:01 ET", "--differs", "wait"
    )
    assert code == 0, said
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha") == ()


def test_under_the_entry_setting_a_go_gate_closes_at_once_and_approves_nothing(kitchen):
    queued(kitchen, "alpha")
    gate(kitchen, "alpha")
    kitchen.poll()
    assert waits_on_user(kitchen) == []
    assert basis(kitchen, "alpha") == ()


def test_under_silence_the_users_answer_that_keeps_a_go_gates_default_starts_its_row(kitchen):
    silence(kitchen)
    queued(kitchen, "alpha", entry=None)
    queued(kitchen, "beta", entry=None, text=brief("beta").replace("Size: S\n", "Size: L\n"))
    first, second = gate(kitchen, "alpha"), gate(kitchen, "beta")
    kitchen.clock_reads(HEARD_AT)
    for number in (first, second):
        code, said = kitchen.main(
            "answer", str(number), "--by", "user", "--at", HEARD_AT, "--default", "yes, start it"
        )
        assert code == 0, said
        assert "approved " in said
    assert basis(kitchen, "alpha") == ("answer", str(first))
    assert basis(kitchen, "beta") == ("answer", str(second))
    assert "closed_by" not in rows(kitchen)["alpha"]["approval"]
    kitchen.poll(NOW + timedelta(minutes=5))
    assert "crew: alpha" in [launch["title"] for launch in kitchen.t3.launches]


def test_under_silence_a_cleanup_of_a_row_silence_started_is_approved_by_the_follow_up_rule(
    kitchen,
):
    silence(kitchen)
    queued(kitchen, "alpha", entry=None)
    gate(kitchen, "alpha")
    kitchen.poll(NOW + timedelta(minutes=31))
    assert basis(kitchen, "alpha")[0] == queue.ANSWER
    queued(kitchen, "cleanup-alpha", entry=None, text=brief("cleanup-alpha", "Follows: alpha\n"))
    assert basis(kitchen, "cleanup-alpha") == (queue.RULE, queue.FOLLOW_REF)


def gate_lines(kitchen):
    kept = jbus.read_json(kitchen.state / "waiting-on-user.json", [])
    return {one["slug"]: one["line"] for one in kept if one["kind"] == "gate"}


def test_the_line_of_a_go_gate_says_silence_starts_only_a_row_it_will_start(kitchen):
    silence(kitchen)
    queued(kitchen, "alpha", entry=None)
    queued(kitchen, "beta", entry=None, text=brief("beta").replace("Size: S\n", "Size: L\n"))
    gate(kitchen, "alpha")
    gate(kitchen, "beta")
    kitchen.poll(NOW + timedelta(minutes=29))
    lines = gate_lines(kitchen)
    assert "it starts alpha when its quiet window ends" in lines["alpha"]
    assert "starts beta" not in lines["beta"]
    assert "silence starts nothing" in lines["beta"] and "its size is L" in lines["beta"]


FLOW_PLAN = PLAN.split("## other:")[0]


def test_a_scoped_homes_go_approves_its_own_rows_and_its_stop_takes_them_back(kitchen):
    scope = kitchen.home / "flow"
    scope.mkdir()
    (scope / "home-id").write_text("mcp:flow-home\n")
    (scope / "plan.md").write_text(FLOW_PLAN)
    kitchen.t3.says(HOME, MESSAGE, "go on the flow epic")
    queued(kitchen, "alpha", text=brief("alpha").replace("Home: mcp:a-home\n", "Home: flow\n"))
    code, said = kitchen.main(
        "plan", "go", "epic", "--scope", "flow", "--message", f"{HOME}/{MESSAGE}"
    )
    assert code == 0, said
    queued(kitchen, "beta")
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")
    assert basis(kitchen, "beta") == ()
    code, said = kitchen.main("plan", "stop", "epic")
    assert code == 1 and "epic has no go to stop" in said
    code, said = kitchen.main("plan", "stop", "epic", "--scope", "flow")
    assert code == 0 and "alpha waits for the user's go" in said, said
    assert basis(kitchen, "alpha") == ()


def test_under_silence_a_follow_up_two_hops_from_silences_go_waits_when_silence_would_not_start_it(
    kitchen,
):
    silence(kitchen)
    queued(kitchen, "alpha", entry=None)
    gate(kitchen, "alpha")
    kitchen.poll(NOW + timedelta(minutes=31))
    queued(kitchen, "cleanup-alpha", entry=None, text=brief("cleanup-alpha", "Follows: alpha\n"))
    assert basis(kitchen, "cleanup-alpha") == (queue.RULE, queue.FOLLOW_REF)
    big = brief("cleanup-cleanup-alpha", "Follows: cleanup-alpha\n").replace(
        "Size: S\n", "Size: L\n"
    )
    queued(kitchen, "cleanup-cleanup-alpha", entry=None, text=big)
    assert basis(kitchen, "cleanup-cleanup-alpha") == ()


def test_an_entry_a_follow_up_takes_from_its_parent_approves_nothing(kitchen):
    """The row counts for its parent's entry in `jbus plan`, and still waits for the user's go:
    only an entry the home gave with `--entry` is approved by that entry's go."""
    queued(kitchen, "alpha")
    assert plan_go(kitchen)[0] == 0
    queued(kitchen, "beta", entry="", text=brief("beta", "Follows: alpha\n"))
    kitchen.poll()
    assert rows(kitchen)["beta"]["parent_entry"] == "epic"
    assert basis(kitchen, "alpha") == (queue.ENTRY, "epic")
    assert basis(kitchen, "beta") == ()


JVIEW_PLAN = """\
# jview: plan

## jv-build: build the view
Stage: planned
Done when:
- it is built
"""


@pytest.fixture
def jview(kitchen):
    """The jv-build state: the root home and the scope jview with homes, and the entry jv-build of
    jview's plan with the user's go, whose one row is its design scout."""
    root, scoped = home(kitchen), home(kitchen, "jview")
    (kitchen.home / "jview" / "plan.md").write_text(JVIEW_PLAN)
    text = brief("jv-design").replace("Home: mcp:a-home\n", "Home: jview\n")
    queued(kitchen, "jv-design", entry="jv-build", text=text)
    kitchen.t3.says(HOME, MESSAGE, "go on jv-build")
    code, said = kitchen.main(
        "plan", "go", "jv-build", "--scope", "jview", "--message", f"{HOME}/{MESSAGE}"
    )
    assert code == 0, said
    return kitchen, root["threadId"], scoped["threadId"]


def reported(kitchen, slug):
    """End the row the way a crew ends it: its thread completed, its Result done with no pull
    request and nothing left."""
    made = kitchen.t3.thread(slug, "completed")
    launched(kitchen, slug, status="launched")
    table = kitchen.state / "queue.json"
    listed = json.loads(table.read_text())
    for row in listed:
        if row["slug"] == slug:
            row["thread"] = made["threadId"]
    table.write_text(json.dumps(listed))
    kitchen.brief(slug, "Home: jview\n" + result())


def owed_wakes(kitchen, thread):
    """The messages of the one list to the thread that name an owed entry."""
    return [
        given["message"]
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send"
        and given["threadId"] == thread
        and given["clientRequestId"].startswith("wakes|")
        and "owed " in given["message"]
    ]


def out(kitchen, scope="jview"):
    code, said = kitchen.main("--project", "demo", "out", "--scope", scope)
    assert code == 0, said
    return said.splitlines()


def test_a_holding_go_whose_last_row_ended_wakes_its_home_once_and_jbus_out_says_it(jview):
    """The replay of jv-build: its design scout reported, nothing else queued, and the go still
    holds. The home is woken once, the root once it is still open `CLOSE_MINUTES` later, and the
    item leaves the list on a new row."""
    kitchen, root, scoped = jview
    reported(kitchen, "jv-design")
    kitchen.poll(NOW)
    (said,) = owed_wakes(kitchen, scoped)
    assert "- owed jview/jv-build: go holds, no live row" in said
    assert "jbus queue add <slug> --entry jv-build" in said
    assert "jbus plan close jv-build --scope jview" in said
    assert "out entry jv-build: go holds, no live row" in out(kitchen)
    kitchen.poll(NOW + timedelta(minutes=5))
    assert len(owed_wakes(kitchen, scoped)) == 1
    assert owed_wakes(kitchen, root) == []
    kitchen.poll(NOW + timedelta(minutes=leftover.CLOSE_MINUTES + 1))
    (late,) = owed_wakes(kitchen, root)
    assert "- owed jview/jv-build: go holds, no live row" in late and scoped in late
    assert len(owed_wakes(kitchen, scoped)) == 1
    text = brief("jv-build-2").replace("Home: mcp:a-home\n", "Home: jview\n")
    queued(kitchen, "jv-build-2", entry="jv-build", text=text)
    assert not any(line.startswith("out entry ") for line in out(kitchen))
    kitchen.poll(NOW + timedelta(minutes=leftover.CLOSE_MINUTES + 2))
    told = json.loads((kitchen.state / wakes.FILE).read_text())["threads"]
    assert not any(key.startswith("owed") for seen in told.values() for key in seen)


def test_an_entry_closed_after_its_home_was_told_leaves_the_list_and_never_reaches_the_root(jview):
    kitchen, root, scoped = jview
    reported(kitchen, "jv-design")
    kitchen.poll(NOW)
    code, said = kitchen.main("plan", "close", "jv-build", "--scope", "jview")
    assert code == 0, said
    assert out(kitchen) == []
    kitchen.poll(NOW + timedelta(minutes=leftover.CLOSE_MINUTES + 1))
    assert len(owed_wakes(kitchen, scoped)) == 1
    assert out(kitchen) == []


def test_an_entry_whose_live_row_waits_on_depends_raises_nothing(jview):
    kitchen, root, scoped = jview
    reported(kitchen, "jv-design")
    queued(kitchen, "jv-first", entry="other")
    code, said = kitchen.main(
        "queue",
        "add",
        "jv-next",
        "--priority",
        "1",
        "--entry",
        "jv-build",
        "--depends",
        "jv-first",
        stdin=brief("jv-next", "Builds on: jv-first\n").replace(
            "Home: mcp:a-home\n", "Home: jview\n"
        ),
    )
    assert code == 0, said
    kitchen.poll(NOW)
    assert owed_wakes(kitchen, scoped) == owed_wakes(kitchen, root) == []
    assert not any(line.startswith("out entry ") for line in out(kitchen))
