"""A task that ended with something left is sent to its home to close, and waits on the user
only where it has no home or the home did not close it.

Run as `tests/test_jbus_row_ends.py` runs: the real pass, against a faked T3 Code server,
`gh` and `jmerge`, over briefs that are made up. The view is the real server over what
those passes left, asked over HTTP."""

import json
import re
from datetime import timedelta

import pytest

import jbus
import jsettings
from jbus import leftover, threads, view
from test_jbus_kitchen import NOW
from test_jbus_queue import add
from test_jbus_row_ends import PULL, column, listed, result, sends
from test_jbus_view import Served

NOTE = "the docs page for the new flag, " + "section by section, " * 12 + "to its end"
ASK = (
    "## Gate <n>: tea or coffee?\nStatus: open\nDefault: tea\n"
    "Option: tea (default): nothing changes\nOption: coffee: one thing more\n"
)


def home(kitchen, scope="", **more):
    """A home that runs: its thread, as T3 Code lists it, and its `home-id`."""
    thread = kitchen.t3.thread("demo", "completed", title=f"home: demo {scope}".strip(), **more)
    where = kitchen.home / scope
    where.mkdir(exist_ok=True)
    (where / "home-id").write_text(thread["threadId"] + "\n")
    return thread


def ended(kitchen, slug="alpha", left="the docs", head=""):
    """A row whose thread ended with a Result that leaves something, and no pull request."""
    add(kitchen, slug)
    kitchen.brief(slug, head + result(left))
    return kitchen.t3.thread(slug, "completed")


def merged(kitchen, slug="alpha", left="the docs", number=9):
    add(kitchen, slug)
    kitchen.t3.thread(slug, "completed", settled=True)
    kitchen.brief(slug, result(left, pull=PULL))
    kitchen.set("merged.json", [kitchen.merged(slug, number, "a" * 40)])


def loud(kitchen):
    return [event["line"] for event in kitchen.events() if event["loud"] == "user"]


def later(minutes):
    return NOW + timedelta(minutes=minutes)


class Page:
    """The view over a kitchen, as `Served` opens one."""

    def __init__(self, kitchen, now=NOW):
        self.kitchen, self.now = kitchen, now

    def app(self):
        sources = view.Sources(
            state_dir=self.kitchen.state_dir,
            home_dir=self.kitchen.root / "home",
            user=jsettings.load(),
        )
        return view.App(sources, clock=lambda: self.now)


def state(kitchen, now=NOW):
    served = Served(Page(kitchen, now))
    try:
        return served.json("/state.json")
    finally:
        served.close()


def test_three_passes_send_the_home_one_message_and_a_new_left_text_a_second(kitchen):
    at = home(kitchen)
    merged(kitchen, left=NOTE)
    assert kitchen.main("gate", "alpha", stdin=ASK)[0] == 0
    assert kitchen.main("gate", "alpha", stdin=ASK.replace("tea or coffee", "milk"))[0] == 0
    answered = kitchen.main(
        "answer", "1", "--by", "user", "--at", "2026-10-12 10:00 ET", "--default", "tea it is"
    )
    assert answered[0] == 0, answered[1]
    for _ in range(3):
        kitchen.poll()
    (sent,) = sends(kitchen)
    assert (sent["threadId"], sent["mode"]) == (at["threadId"], "queue")
    assert sent["clientRequestId"].startswith("leftover|alpha|")
    said = sent["message"]
    assert said.startswith("jbus: alpha ended with something left")
    assert f"Its pull request #9 {PULL} is merged." in said
    assert f"Left: {NOTE}\n" in said
    assert 'Question 1: tea or coffee? It is answered: "tea it is", by user' in said
    assert "Question 2: milk? It is open, and the default was taken: tea." in said
    assert "write a brief for what is left and queue it as a follow-up" in said
    assert "`Left: none`" in said and "`jbus gate alpha`" in said
    kitchen.brief("alpha", result("only the index page", pull=PULL))
    for _ in range(3):
        kitchen.poll()
    first, second = sends(kitchen)
    assert first == sent and second["clientRequestId"] != sent["clientRequestId"]
    assert "Left: only the index page\n" in second["message"]
    assert len(kitchen.lines("leftover")) == 2


def test_a_task_that_ended_with_no_pull_request_says_so_to_its_home(kitchen):
    home(kitchen)
    ended(kitchen)
    kitchen.poll()
    (sent,) = sends(kitchen)
    assert (
        "It ended with no pull request.\nLeft: the docs\nIt asked no question." in (sent["message"])
    )


def test_a_leftover_its_home_has_is_not_on_the_users_list_and_the_view_says_who_has_it(kitchen):
    kitchen.quiet()
    home(kitchen)
    merged(kitchen, left=NOTE)
    for _ in range(2):
        kitchen.poll()
    assert column(kitchen) == ("merged", "#9", "left: " + NOTE[:95] + "[cut]")
    assert jbus.read_json(kitchen.state / "waiting-on-user.json", None) == []
    assert loud(kitchen) == [] and kitchen.waiting() == []
    built = state(kitchen)
    assert built["waiting"] == []
    (task,) = built["tasks"]
    told = jsettings.load().stamp(NOW)
    assert (task["slug"], task["step"], task["who"]) == ("alpha", "running", "home")
    assert (task["state"]["kind"], task["state"]["name"]) == ("leftover", "Ended, with a leftover")
    assert task["state"]["waits"] == "its home"
    assert task["state"]["say"] == (
        f"its pull request #9 is merged. Its crewmate left a note: {NOTE}. "
        f"jbus told its home {told}. The home closes it: a follow-up task for what was left, "
        "or a Left: none line in its brief with the reason"
    )
    assert task["since"] == NOW.isoformat(timespec="seconds")
    assert [one for one in built["tasks"] if one["who"] == "user"] == []


def test_a_home_that_has_not_closed_it_in_time_is_one_stall_that_names_its_thread(kitchen):
    kitchen.quiet()
    at = home(kitchen)["threadId"]
    ended(kitchen)
    kitchen.poll(NOW)
    kitchen.poll(later(leftover.CLOSE_MINUTES - 1))
    assert listed(kitchen) == [] and loud(kitchen) == []
    late = f"its home, thread {at}, has not closed it 30 min after jbus told it"
    for minutes in (30, 31, 95):
        kitchen.poll(later(minutes))
        assert listed(kitchen) == [f"left alpha: left: the docs; {late}"]
    stall = f"stall alpha: it ended with something left, and {late}; left: the docs"
    assert loud(kitchen) == [stall]
    assert len(sends(kitchen)) == 1
    built = state(kitchen, later(95))
    (task,) = built["tasks"]
    assert (task["step"], task["who"]) == ("gate", "user")
    assert (
        f"left a note of something it did not do: the docs. It waits on you: {late}. "
        in (task["state"]["say"])
    )
    assert [one["line"] for one in built["waiting"]] == [task["state"]["say"]]
    kitchen.brief("alpha", result("the index page"))
    kitchen.poll(later(96))
    assert listed(kitchen) == [] and len(sends(kitchen)) == 2
    kitchen.poll(later(130))
    assert [line.partition("; ")[0] for line in listed(kitchen)] == [
        "left alpha: left: the index page"
    ]
    assert loud(kitchen) == [stall]


def test_a_leftover_goes_from_the_record_when_its_brief_says_left_none(kitchen):
    home(kitchen)
    ended(kitchen)
    kitchen.poll()
    assert list(leftover.read(kitchen.state)) == ["alpha"]
    kitchen.brief(
        "alpha", result("the docs") + result().replace("## Result", "## Result, follow-up")
    )
    kitchen.poll(later(45))
    assert column(kitchen) == ("done", "", "")
    assert leftover.read(kitchen.state) == {} and listed(kitchen) == []
    assert loud(kitchen) == [] and len(sends(kitchen)) == 1


def test_a_row_with_no_home_is_the_users_at_once_and_the_line_says_why(kitchen):
    kitchen.quiet()
    ended(kitchen)
    kitchen.poll()
    why = "it has no home: no home-id names a thread for the home of its brief"
    assert listed(kitchen) == [f"left alpha: left: the docs; {why}"]
    assert sends(kitchen) == [] and loud(kitchen) == []
    (task,) = state(kitchen)["tasks"]
    assert (task["step"], task["who"]) == ("gate", "user")
    assert f"the docs. It waits on you: {why}. Either of two things ends it" in task["state"]["say"]


@pytest.mark.parametrize("how", ["settled", "unlisted", "handed off"])
def test_a_home_whose_thread_is_not_listed_as_not_settled_is_no_home_to_tell(kitchen, how):
    kitchen.quiet()
    at = home(kitchen, settled=how == "settled")
    if how == "unlisted":
        at = {"threadId": "mcp:a-thread-t3-code-does-not-list"}
        (kitchen.home / "home-id").write_text(at["threadId"])
    if how == "handed off":
        (kitchen.home / "handoff.md").write_text(f"# handoff\nWas home: {at['threadId']}\n")
    ended(kitchen)
    kitchen.poll()
    why = {
        "handed off": leftover.NO_HOME,
    }.get(how, f"its home's thread {at['threadId']} is not one T3 Code lists as not settled")
    assert listed(kitchen) == [f"left alpha: left: the docs; {why}"]
    assert sends(kitchen) == [] and loud(kitchen) == []


def test_a_home_that_starts_later_is_told_then_and_the_row_leaves_the_users_list(kitchen):
    ended(kitchen)
    kitchen.poll()
    assert len(listed(kitchen)) == 1
    at = home(kitchen)
    kitchen.poll(later(50))
    assert listed(kitchen) == [] and [one["threadId"] for one in sends(kitchen)] == [at["threadId"]]
    assert loud(kitchen) == []


def test_a_scoped_homes_brief_goes_to_that_scope_by_its_name_or_its_thread(kitchen):
    root, scope = home(kitchen), home(kitchen, "speed")
    ended(kitchen, "alpha", head="Home: speed\n")
    ended(kitchen, "beta", head=f"Home: {scope['threadId']}\n")
    ended(kitchen, "gamma", head=f"Home: {root['threadId']}\n")
    ended(kitchen, "delta", head="Home: mcp:a-thread-that-is-no-home\n")
    kitchen.poll()
    went = {one["clientRequestId"].split("|")[1]: one["threadId"] for one in sends(kitchen)}
    assert went == {
        "alpha": scope["threadId"],
        "beta": scope["threadId"],
        "gamma": root["threadId"],
        "delta": root["threadId"],
    }


def test_a_message_t3_code_does_not_take_is_sent_on_the_next_pass(kitchen):
    at = home(kitchen)["threadId"]
    ended(kitchen)
    kitchen.t3.lose_send = True
    said = kitchen.poll()
    assert [line for line in said if line.startswith("wait alpha: its home could not be told")]
    why = f"T3 Code did not take the message to its home's thread {at}"
    assert kitchen.t3.messages == {} and listed(kitchen) == [f"left alpha: left: the docs; {why}"]
    kitchen.t3.lose_send = False
    kitchen.poll(later(40))
    assert len(kitchen.t3.messages) == 1 and listed(kitchen) == [] and loud(kitchen) == []


def test_a_message_t3_code_refuses_leaves_the_row_the_users_with_the_reason(kitchen):
    at = home(kitchen)["threadId"]
    ended(kitchen)
    kitchen.t3.refuse_send = True
    kitchen.poll()
    why = f"T3 Code refused the message to its home's thread {at}"
    assert listed(kitchen) == [f"left alpha: left: the docs; {why}"]


def test_a_row_that_leaves_nothing_or_is_still_out_has_no_record_and_no_message(kitchen):
    home(kitchen)
    add(kitchen, "alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", "completed")
    add(kitchen, "beta")
    kitchen.brief("beta")
    kitchen.t3.thread("beta", "running")
    add(kitchen, "gamma")
    kitchen.brief("gamma", result(status="blocked"))
    kitchen.t3.thread("gamma", "completed")
    for _ in range(2):
        kitchen.poll()
    assert leftover.read(kitchen.state) == {} and sends(kitchen) == []
    assert listed(kitchen) == ["left gamma: status: blocked"]
    assert not (kitchen.state / leftover.NAME).exists()


def test_a_record_that_is_not_one_is_read_as_none(kitchen):
    kitchen.state.mkdir(parents=True, exist_ok=True)
    for written in ("[]", '{"alpha": {"note": "x"}}', "not json"):
        (kitchen.state / leftover.NAME).write_text(written)
        assert leftover.read(kitchen.state) == {}
    kept = {"alpha": {"left": "the docs", "told": NOW.isoformat()}}
    (kitchen.state / leftover.NAME).write_text(json.dumps(kept))
    (record,) = leftover.read(kitchen.state).values()
    assert leftover.his(record, later(29)) == "" and leftover.his(record, later(30)) != ""


def test_a_home_that_took_over_is_told_too_and_its_thirty_minutes_start_then(kitchen):
    kitchen.quiet()
    first = home(kitchen)
    ended(kitchen)
    kitchen.poll()
    first["settled"] = True
    (kitchen.home / "handoff.md").write_text(f"# handoff\nWas home: {first['threadId']}\n")
    kitchen.poll(later(10))
    assert listed(kitchen) == [f"left alpha: left: the docs; {leftover.NO_HOME}"]
    kitchen.poll(later(40))
    assert loud(kitchen) == []
    second = home(kitchen)
    (kitchen.home / "handoff.md").unlink()
    kitchen.poll(later(41))
    assert [one["threadId"] for one in sends(kitchen)] == [first["threadId"], second["threadId"]]
    assert listed(kitchen) == [] and loud(kitchen) == []
    kitchen.poll(later(70))
    assert listed(kitchen) == [] and loud(kitchen) == []
    kitchen.poll(later(71))
    late = f"its home, thread {second['threadId']}, has not closed it 30 min after jbus told it"
    assert loud(kitchen) == [
        f"stall alpha: it ended with something left, and {late}; left: the docs"
    ]


def test_a_home_told_and_then_settled_is_the_users_with_that_reason_and_no_stall(kitchen):
    kitchen.quiet()
    at = home(kitchen)
    ended(kitchen)
    kitchen.poll()
    at["settled"] = True
    for minutes in (5, 30, 60):
        kitchen.poll(later(minutes))
        why = f"its home's thread {at['threadId']} is not one T3 Code lists as not settled"
        assert listed(kitchen) == [f"left alpha: left: the docs; {why}"]
    assert loud(kitchen) == []
    at["settled"] = False
    kitchen.poll(later(61))
    assert len(loud(kitchen)) == 1 and len(sends(kitchen)) == 1


def test_a_pass_that_cannot_list_the_threads_out_leaves_an_untold_row_the_users(kitchen):
    kitchen.quiet()
    home(kitchen)
    ended(kitchen)
    listing = threads.out
    kitchen.monkeypatch.setattr(threads, "out", lambda *_, **__: None)
    kitchen.poll()
    assert listed(kitchen) == [f"left alpha: left: the docs; {leftover.UNSEEN}"]
    assert sends(kitchen) == []
    kitchen.monkeypatch.setattr(threads, "out", listing)
    kitchen.poll(later(1))
    assert listed(kitchen) == [] and len(sends(kitchen)) == 1
    kitchen.monkeypatch.setattr(threads, "out", lambda *_, **__: None)
    kitchen.poll(later(2))
    assert listed(kitchen) == [] and len(sends(kitchen)) == 1


@pytest.mark.parametrize(
    ("made", "why"),
    [
        (result("the docs", status="partial"), "status: partial"),
        (result("the docs", pull=PULL), "pull request #9 is not open and not merged"),
    ],
)
def test_a_row_the_home_closes_as_the_message_says_is_done(kitchen, made, why):
    kitchen.quiet()
    home(kitchen)
    add(kitchen, "alpha")
    kitchen.brief("alpha", made)
    kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    assert column(kitchen) == ("left", "", "left: the docs")
    (sent,) = sends(kitchen)
    path = kitchen.home / "tasks" / "alpha.md"
    copied = [line for line in made.splitlines() if line.startswith(("Status:", "Branch:"))]
    follow = "\n## Result, follow-up (2026-10-12, nothing more is wanted)\n"
    path.write_text(path.read_text() + follow + "\n".join([*copied, "Left: none"]) + "\n")
    kitchen.poll(later(1))
    assert column(kitchen) == ("left", "", why)
    closing = re.search(r"with three lines: `([^`]+)`, `([^`]+)` and `([^`]+)`", sent["message"])
    status, branch, left = (one.replace("<its branch>", "alpha") for one in closing.groups())
    path.write_text(path.read_text() + follow + "\n".join((status, branch, left)) + "\n")
    kitchen.poll(later(2))
    assert column(kitchen) == ("done", "", "")
    assert listed(kitchen) == [] and leftover.read(kitchen.state) == {}
