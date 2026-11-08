"""Each piece of work has one state. The tests run `work.judge` over every set of facts there is,
and run each ending that a pass can meet as `features/jbus/tests/test_jbus_queue.py` runs,
against a faked T3 Code, `gh` and `jmerge`, with `work.json` read back."""

import configparser
import json
import time
from dataclasses import replace
from datetime import timedelta

import pytest

import jbus
from jbus import passes, queue, restated, states, tick, verbs, waiting, work
from jmerge import ready
from test_jbus_kitchen import ASK, NOW, REPO, SAID_AT, Kitchen, iso
from test_jbus_queue import add, adds, approves, batch, brief, go, rows, sha12
from test_jbus_row_ends import branched

PULL = "https://example.test/pull/9"
AT = "2026-10-12 10:00 ET"
TYPED_AT = "2026-10-12 10:58 ET"


def result(left="none", status="done", branch="alpha   Pull request: none"):
    return f"\n## Result\nStatus: {status}\nBranch: {branch}\nLeft: {left}\n"


def judged(kitchen, key="alpha"):
    """Return the line of `work.json` for a key, as the last pass wrote it."""
    kept = json.loads((kitchen.state / work.NAME).read_text())
    return {one["key"]: one for one in kept["work"]}[key]


def said(kitchen, key="alpha"):
    line = judged(kitchen, key)
    return line["value"], line["confirmed"]


def test_every_combination_of_the_facets_is_one_state_and_what_matches_none_is_unknown():
    began = time.monotonic()
    walked = unknown = answered_unknown = 0
    for facts in work.every():
        walked += 1
        matching = work.matching(facts)
        assert len(matching) <= 1, (facts, [one.value for one in matching])
        state = work.judge(facts)
        assert state.facts == facts
        heard = work.HEARD[facts.answered]
        if state.confirmed and state.value != "unknown":
            assert state.pattern.needs <= heard
            assert matching == [state.pattern]
        elif state.value == "unknown" and state.confirmed:
            assert heard == work.HEARD[work.Answered.BOTH] and matching == []
        else:
            assert heard != work.HEARD[work.Answered.BOTH]
            assert not any(one.needs <= heard for one in matching)
            again = work.judge(replace(facts, last="ready"))
            assert (again.value, again.confirmed, again.facts.last) == ("ready", False, "ready")
        unknown += state.value == "unknown"
        answered_unknown += state.value == "unknown" and state.confirmed
    assert walked == 6 * 11 * 2 * 4 * 12 * 2 * 4 == 50_688
    assert (unknown, answered_unknown) == (15_324, 444)
    assert time.monotonic() - began < 10


def test_the_projection_keeps_each_status_a_reader_knows_and_gives_no_other():
    seen = {work.status(work.judge(facts)) for facts in work.every()}
    assert seen <= set(queue.STATUSES)
    assert seen == set(queue.STATUSES)


def test_merged(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    kitchen.poll()
    assert said(kitchen) == ("merged", True)
    assert rows(kitchen)["alpha"]["status"] == "merged"


def test_merged_from_a_branch_not_named_for_the_slug(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(branch=f"another-branch   Pull request: {PULL}"))
    kitchen.t3.thread("alpha", "completed", settled=True)
    pulled = {**kitchen.merged("another-branch", 9, "a" * 40), "url": PULL}
    kitchen.set("merged.json", [pulled])
    kitchen.poll()
    assert said(kitchen) == ("merged", True)
    assert judged(kitchen)["facts"]["pull"] == "merged"


def test_merged_with_a_leftover(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(left="the docs page, after the merge"))
    kitchen.t3.thread("alpha", "completed", settled=True)
    kitchen.set("merged.json", [kitchen.merged("alpha", 9, "a" * 40)])
    kitchen.poll()
    line = judged(kitchen)
    assert (line["value"], line["name"], line["who"]) == (
        "leftover",
        "Ended, with a leftover",
        "home",
    )
    assert rows(kitchen)["alpha"]["status"] == "merged"


def test_done_with_no_pull_request(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    assert said(kitchen) == ("done", True)
    assert rows(kitchen)["alpha"]["status"] == "done"


def test_a_result_written_under_a_live_thread(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", "running")
    kitchen.poll()
    line = judged(kitchen)
    assert (line["value"], line["facts"]["thread"]) == ("done", "moving")
    assert rows(kitchen)["alpha"]["status"] == "done"


def test_a_thread_settled_with_nothing_written_is_lost(kitchen):
    add(kitchen, "alpha")
    kitchen.poll()
    (thread,) = kitchen.t3.threads
    thread.update(status="completed", settled=True)
    kitchen.poll(NOW + timedelta(minutes=3))
    line = judged(kitchen)
    assert (line["value"], line["who"], line["waits"]) == ("lost", "user", work.AGAIN)
    assert line["facts"] | {"answered": "both"} == {
        "row": "approved and free",
        "thread": "settled",
        "launch": "launched",
        "written": "none",
        "pull": "none",
        "question": "none",
        "answered": "both",
    }


def test_a_launch_record_with_no_thread_is_lost(kitchen):
    add(kitchen, "alpha")
    kitchen.poll()
    assert said(kitchen) == ("launching", True)
    kitchen.t3.threads.clear()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert said(kitchen) == ("lost", True)
    assert rows(kitchen)["alpha"]["status"] == "launched"


def test_a_pull_request_closed_unmerged_is_closed(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(branch=f"alpha   Pull request: {PULL}"))
    kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    assert said(kitchen) == ("closed", True)
    assert rows(kitchen)["alpha"]["status"] == "left"


def test_a_row_removed_leaves_its_thread_removed(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.clock_reads(AT)
    remove = ("--project", "demo", "queue", "remove", "alpha", "--by", "user", "--at", AT)
    assert kitchen.main(*remove)[0] == 0
    thread = kitchen.t3.thread("alpha", "running")
    kitchen.poll()
    line = judged(kitchen, thread["threadId"])
    assert (line["kind"], line["slug"], line["value"]) == ("thread", "alpha", "removed")
    assert "alpha" not in rows(kitchen)


@pytest.mark.parametrize(("asked", "written"), [("open one when done", "none"), ("none", None)])
def test_a_crew_thread_with_no_row_has_written_nothing_while_its_result_owes_its_pull_request(
    kitchen, asked, written
):
    """A crew thread out with no row is judged while it owes its pull request, and drops out of
    the list once its Result ends the task."""
    branched(kitchen, "alpha")
    kitchen.brief("alpha", f"Pull request: {asked}\n" + result())
    thread = kitchen.t3.thread("alpha", "completed")
    kitchen.poll()
    kept = json.loads((kitchen.state / work.NAME).read_text())["work"]
    lines = [one["facts"]["written"] for one in kept if one["key"] == thread["threadId"]]
    assert lines == ([written] if written else [])


def test_a_hung_turn(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=25))
    kitchen.poll()
    line = judged(kitchen)
    assert (line["value"], line["who"], line["facts"]["thread"]) == ("hung", "user", "hung")
    assert rows(kitchen)["alpha"]["status"] == "left"


def test_a_pull_request_on_a_step_is_that_step_and_a_hung_thread_over_it_is_hung(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(branch=f"alpha   Pull request: {PULL}") + "Reviewer: mcp:r #1\n")
    thread = kitchen.t3.thread("alpha", "completed")
    kitchen.set("open.json", [kitchen.opened("alpha", 9)])
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: {ready.NO_REVIEW}\n")
    kitchen.poll()
    assert said(kitchen) == ("review", True)
    thread.update(status="running", updatedAt=iso(NOW - timedelta(minutes=25)))
    kitchen.t3.at_work.discard(thread["threadId"])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert said(kitchen) == ("hung", True)
    assert rows(kitchen)["alpha"]["status"] == "pr"


def _open_with(kitchen, reason):
    """Open alpha (#9) and beta (#8), each with its Result, and have `jmerge` say `reason` of
    alpha, then run a pass."""
    for slug, number in (("beta", 8), ("alpha", 9)):
        add(kitchen, slug)
        url = f"https://example.test/pull/{number}"
        kitchen.brief(slug, result(branch=f"{slug}   Pull request: {url}"))
        kitchen.t3.thread(slug, "completed")
    kitchen.set("open.json", [kitchen.opened("beta", 8), kitchen.opened("alpha", 9)])
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: {reason}\n")
    kitchen.poll()


def test_a_row_stacked_on_an_open_parent_waits_on_that_row_and_not_on_the_check_runner(kitchen):
    """The 2026-11-07 tree: two stacked rows said `waits the check runner` while jmerge held each
    behind the row it is stacked on."""
    _open_with(kitchen, ready.STACKED_ON.format(branch="beta", slug="beta", default="main"))
    line = judged(kitchen)
    assert line["who"] == "beta"
    assert line["waits"].startswith("beta ")
    assert "check runner" not in line["waits"]
    assert line["why"] == rows(kitchen)["alpha"]["why"]
    assert "it is stacked on beta" in line["why"]


def test_a_row_whose_check_runs_still_waits_on_the_check_runner(kitchen):
    _open_with(kitchen, ready.LIVE_RUN.format(check="check", head="c" * 12, state="in progress"))
    line = judged(kitchen)
    assert (line["value"], line["who"], line["waits"]) == ("check", "ci", "the check runner")
    assert line["why"] == rows(kitchen)["alpha"]["why"]
    assert "is in progress" in line["why"]


def test_a_pass_that_could_not_ask(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "running")
    kitchen.poll()
    assert said(kitchen) == ("working", True)
    kitchen.set("gh-down", "")
    kitchen.poll(NOW + timedelta(minutes=3))
    kept = json.loads((kitchen.state / work.NAME).read_text())
    assert kept["answered"] == "T3 Code only"
    assert said(kitchen) == ("working", False)


def test_a_scout_a_reviewer_and_a_home_out_are_judged_beside_the_rows(kitchen):
    add(kitchen, "alpha")
    review = "\n## Review\nVerdict: clean\nHead: abc\n"
    kitchen.brief("alpha", result(branch=f"alpha   Pull request: {PULL}") + review)
    kitchen.set("open.json", [kitchen.opened("alpha", 9)])
    kitchen.t3.thread("alpha", "completed")
    scout = kitchen.t3.thread("look", "running", title="scout: look")
    reviewer = kitchen.t3.thread("alpha", "completed", title="review: alpha")
    home = kitchen.t3.thread("", "running", title="home: demo")
    lost = kitchen.t3.thread("other", "completed", title="scout: other")
    other = kitchen.t3.thread("", "completed", title="a scratch thread")
    kitchen.poll()
    assert [said(kitchen, one["threadId"]) for one in (scout, reviewer, home, lost, other)] == [
        ("working", True),
        ("done", True),
        ("working", True),
        ("lost", True),
        ("done", True),
    ]
    kept = json.loads((kitchen.state / work.NAME).read_text())
    assert [one["key"] for one in kept["work"] if one["kind"] == "row"] == ["alpha"]
    assert judged(kitchen, home["threadId"])["role"] == "home"


def test_work_json_is_written_whole_with_no_file_left_beside_it(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    assert said(kitchen) == ("unapproved", True)
    assert sorted(path.name for path in kitchen.state.glob("work.json*")) == ["work.json"]
    assert jbus.read_json(kitchen.state / work.NAME, {})["answered"] == "both"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    monkeypatch.setattr(queue, "clock", lambda: NOW)
    yield made
    made.close()


def test_who_holds_a_state_is_its_patterns_holder_but_for_a_leftover_and_a_thread_by_role():
    """A row that ended with something left is never the user's but where a gate of the user's
    holds it: its home closes it, or a thread at work on it, or its review is still to come."""
    holders = {"user", "crew", "rev", "ci", "bus", "dep", "ok", "home", "unknown"}
    roles = {"crew", "rev", "scout", "home", "other"}
    for facts in work.every():
        state = work.judge(facts)
        for closer in work.Closer:
            for unhomed in ("", "it has no home"):
                held = work.holder(state, closer=closer, unhomed=unhomed)
                assert held.who in holders
                if closer == work.Closer.USER:
                    assert held == work.Holder("user", "your answer", "gate")
                elif state.value in ("leftover", "closed"):
                    assert held.who != "user"
                elif closer != work.Closer.REVIEW or state.value != "quiet":
                    assert held == work.Holder(state.who, state.waits, state.pattern.lane)
        for role in ("crew", "reviewer", "scout", "home", "other"):
            held = work.holder(state, role=role)
            assert held.lane == "" and (held.who in roles or held.who == state.who)


def test_an_approved_row_added_while_a_pass_runs_waits_on_its_dependency(kitchen):
    add(kitchen, "alpha", approve=False)

    def added():
        kitchen.t3.on_list = None
        add(kitchen, "beta", depends="alpha")

    kitchen.t3.on_list = added
    kitchen.poll()
    line = judged(kitchen, "beta")
    assert (line["value"], line["facts"]["row"]) == ("behind", "approved and behind")


def test_a_row_whose_thread_is_in_a_status_jbus_does_not_know_says_that_status(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "dreaming")
    kitchen.poll()
    line = judged(kitchen)
    assert (line["value"], line["facts"]["thread"]) == ("asking", "dreaming")
    assert rows(kitchen)["alpha"]["status"] == "gate"
    facts = work.Facts(*(next(iter(facet)) for facet in work.FACETS.values()), seen="dreaming")
    state = work.unforeseen(facts)
    assert (state.value, work.status(state), state.facts.said()["thread"]) == (
        "unknown",
        "stale",
        "dreaming",
    )


def test_a_row_added_while_a_pass_runs_is_judged_with_the_rest(kitchen):
    add(kitchen, "alpha", approve=False)

    def added():
        kitchen.t3.on_list = None
        add(kitchen, "beta", approve=False)

    kitchen.t3.on_list = added
    kitchen.poll()
    assert said(kitchen, "beta") == ("unapproved", True)
    assert rows(kitchen)["beta"]["status"] == "queued"


def test_a_hung_turn_is_said_while_github_does_not_answer(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=25))
    kitchen.set("gh-down", "")
    kitchen.poll()
    line = judged(kitchen)
    assert (line["value"], line["confirmed"], line["facts"]["thread"]) == ("hung", True, "hung")


def test_a_running_thread_whose_liveness_was_not_read_is_not_confirmed(kitchen, monkeypatch):
    from jbus import threads

    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "running")
    monkeypatch.setattr(threads, "out", lambda *_, **__: None)
    kitchen.poll()
    assert said(kitchen) == ("quiet", False)


def test_a_thread_in_a_status_jbus_does_not_know_is_unknown(kitchen):
    other = kitchen.t3.thread("", "dreaming", title="scout: look")
    kitchen.poll()
    line = judged(kitchen, other["threadId"])
    assert (line["value"], line["who"]) == ("unknown", "unknown")


def test_a_row_behind_one_whose_result_is_written_under_a_live_thread_waits_as_dispatch_does(
    kitchen,
):
    add(kitchen, "alpha")
    add(kitchen, "beta", depends="alpha")
    kitchen.brief("alpha", result())
    kitchen.t3.thread("alpha", "running")
    kitchen.t3.thread("beta", "preparing")
    kitchen.t3.threads.pop()
    kitchen.poll()
    assert rows(kitchen)["alpha"]["status"] == "done"
    assert kitchen.t3.launches == []
    line = judged(kitchen, "beta")
    assert (line["value"], line["facts"]["row"]) == ("behind", "approved and behind")
    assert rows(kitchen)["beta"]["why"] == "depends on alpha"


def test_a_home_and_a_scout_at_work_are_held_by_their_role(kitchen):
    home = kitchen.t3.thread("", "running", title="home: demo")
    scout = kitchen.t3.thread("look", "running", title="scout: look")
    kitchen.poll()
    assert [
        (judged(kitchen, one["threadId"])["who"], judged(kitchen, one["threadId"])["waits"])
        for one in (home, scout)
    ] == [
        ("home", "its thread"),
        ("scout", "its thread"),
    ]


def waits(kitchen):
    """Return the keys of `waiting-on-user.json`, as the file has them now."""
    return {one["key"] for one in jbus.read_json(kitchen.state / waiting.NAME, [])}


def test_a_go_shows_before_any_pass_and_the_next_pass_writes_what_it_showed(kitchen):
    add(kitchen, "beta", approve=False)
    add(kitchen, "alpha", depends="beta", approve=False)
    kitchen.poll()
    assert (judged(kitchen)["who"], "approve:alpha" in waits(kitchen)) == ("user", True)
    assert go(kitchen, "alpha")[0] == 0
    shown = judged(kitchen)
    assert (shown["value"], shown["who"], shown["facts"]["row"]) == (
        "behind",
        "dep",
        "approved and behind",
    )
    assert "approve:alpha" not in waits(kitchen) and "approve:beta" in waits(kitchen)
    assert shown["why"] == ""
    kitchen.poll()
    assert judged(kitchen) == shown | {"why": "depends on beta"}
    assert "approve:alpha" not in waits(kitchen)


def while_keep_work_lists(monkeypatch, act):
    """Run `act` inside `states.keep_work`, after the pass judged its rows from the table it read
    and before it writes `work.json`: the moment an act given while a pass runs lands worst."""
    out = states.watch.judged

    def acted(*args):
        act()
        return out(*args)

    monkeypatch.setattr(states.watch, "judged", acted)


def test_a_go_given_while_a_pass_runs_is_not_written_back_as_unapproved(kitchen, monkeypatch):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    while_keep_work_lists(monkeypatch, lambda: go(kitchen, "alpha"))
    kitchen.poll()
    line = judged(kitchen)
    assert (line["value"], line["who"]) == ("ready", "bus")
    assert "approve:alpha" not in waits(kitchen)


def test_a_row_removed_while_a_pass_runs_is_not_written_back(kitchen, monkeypatch):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    kitchen.poll()
    typed = ("--by", "user", "--at", "2026-10-12 10:58 ET")
    while_keep_work_lists(
        monkeypatch, lambda: kitchen.main("--project", "demo", "queue", "remove", "alpha", *typed)
    )
    kitchen.poll()
    kept = json.loads((kitchen.state / work.NAME).read_text())["work"]
    assert [one["key"] for one in kept if one["kind"] == "row"] == ["beta"]


def test_a_queue_that_stops_parsing_while_a_pass_runs_leaves_the_pass_s_lines(kitchen, monkeypatch):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    table = kitchen.state / "queue.json"
    kept = table.read_text()

    def broken():
        table.write_text("not a table")

    while_keep_work_lists(monkeypatch, broken)
    kitchen.poll()
    table.write_text(kept)
    line = judged(kitchen)
    assert (line["value"], line["who"]) == ("unapproved", "user")


def test_a_remove_takes_the_rows_line_and_its_waits_out_before_any_pass(kitchen):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "beta", approve=False)
    kitchen.poll()
    typed = ("--by", "user", "--at", "2026-10-12 10:58 ET")
    assert kitchen.main("--project", "demo", "queue", "remove", "alpha", *typed)[0] == 0
    kept = json.loads((kitchen.state / work.NAME).read_text())["work"]
    assert [one["key"] for one in kept if one["kind"] == "row"] == ["beta"]
    assert waits(kitchen) == {"approve:beta"}


def test_an_answer_takes_its_question_off_the_list_before_any_pass(kitchen):
    add(kitchen, "alpha")
    kitchen.main("gate", "alpha", stdin=ASK)
    kitchen.poll()
    assert "gate:q1" in waits(kitchen)
    kitchen.clock_reads(SAID_AT)
    said = ("--by", "user", "--at", SAID_AT, "--default", "the", "first")
    assert kitchen.main("answer", "1", *said)[0] == 0
    assert "gate:q1" not in waits(kitchen)


def test_a_queue_apply_go_and_remove_show_before_any_pass_and_the_next_pass_keeps_them(
    kitchen,
):
    """`jbus queue apply` (`jbus.asks._queue`) shows each go and remove of its batch at once."""
    add(kitchen, "beta", approve=False)
    add(kitchen, "alpha", depends="beta", approve=False)
    add(kitchen, "gamma", approve=False)
    kitchen.poll()
    assert (judged(kitchen)["who"], "approve:alpha" in waits(kitchen)) == ("user", True)
    kitchen.word()
    text = batch(
        approves("alpha", sha12(brief("alpha", "Builds on: beta\n"))),
        f'remove gamma --by user --at "{TYPED_AT}"\n',
    )
    code, said = kitchen.main("--project", "demo", "queue", "apply", stdin=text)
    assert code == 0, said
    shown = judged(kitchen)
    assert (shown["value"], shown["who"], shown["why"]) == ("behind", "dep", "")
    assert waits(kitchen) == {"approve:beta"}
    kept = json.loads((kitchen.state / work.NAME).read_text())["work"]
    assert "gamma" not in [one["key"] for one in kept]
    kitchen.poll()
    assert judged(kitchen) == shown | {"why": "depends on beta"}
    assert waits(kitchen) == {"approve:beta"}


HOLDS = "Holds: rewrites history\n"
FIX = "Fix of: ci:check\n"


@pytest.mark.parametrize(
    "refused",
    [
        lambda: (
            adds("delta", "--priority 1", brief("delta", HOLDS))
            + approves("delta", sha12(brief("delta", HOLDS)))
        ),
        lambda: adds("delta", "--priority 1", brief("delta", FIX)),
    ],
    ids=["a door", "a fix with no when green"],
)
def test_a_queue_apply_that_is_refused_rewrites_nothing(kitchen, refused):
    add(kitchen, "alpha", approve=False)
    add(kitchen, "gamma", approve=False)
    kitchen.poll()
    kitchen.word()
    before = [(kitchen.state / name).read_text() for name in (work.NAME, waiting.NAME)]
    text = batch(
        approves("alpha", sha12(brief("alpha"))),
        f'remove gamma --by user --at "{TYPED_AT}"\n',
        refused(),
    )
    code, said = kitchen.main("--project", "demo", "queue", "apply", stdin=text)
    assert (code, said.startswith("refused: ")) == (1, True), said
    after = [(kitchen.state / name).read_text() for name in (work.NAME, waiting.NAME)]
    assert after == before


def test_a_hold_and_a_row_added_show_before_any_pass(kitchen):
    """Each write of the queue restates the rows' lines of `work.json` (`queue._changing`)."""
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    assert go(kitchen, "alpha")[0] == 0
    assert said(kitchen) == ("ready", True)
    assert kitchen.main("--project", "demo", "queue", "hold", "alpha")[0] == 0
    assert (judged(kitchen)["value"], judged(kitchen)["who"]) == ("unapproved", "user")
    add(kitchen, "beta", depends="alpha")
    line = judged(kitchen, "beta")
    assert (line["value"], line["who"], line["facts"]["row"]) == (
        "behind",
        "dep",
        "approved and behind",
    )


def on_review(kitchen):
    """Put alpha's pull request #9 on the review step, with a check going, as a pass sees it."""
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(branch=f"alpha   Pull request: {PULL}"))
    kitchen.t3.thread("alpha", "completed")
    kitchen.set("open.json", [kitchen.opened("alpha", 9, None)])
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: {ready.NO_REVIEW}\n")
    kitchen.poll()
    assert said(kitchen) == ("review", True)


def a_tick_says(kitchen, line, run_id=1):
    """Run a merge tick that finds the required check `check` passed at #9's head, its job ending
    at second `run_id`, and whose `jmerge` prints `line`."""
    kitchen.set("jmerge.txt", f"{line}\n")
    head, ended = "c" * 40, f"2026-01-01T00:00:{run_id:02d}Z"
    passed = {"name": "check", "status": "completed", "conclusion": "success"}
    passed |= {"completed_at": ended, "check_suite": {"id": 11}}
    kitchen.set("check-runs.json", {head: [passed]})
    kitchen.set("push-runs.json", {head: [{"id": 100, "name": "check", "check_suite_id": 11}]})
    assert tick.tick(jbus.load(), lambda _: None) == 0


def test_a_ticks_verdict_shows_before_any_pass_and_the_next_pass_keeps_it(kitchen):
    on_review(kitchen)
    a_tick_says(kitchen, f"wait 9 {PULL}: {ready.FRESH_CONFLICT}")
    line = judged(kitchen)
    assert (line["value"], line["who"], line["facts"]["pull"]) == ("rebase", "crew", "rebase")
    a_tick_says(kitchen, "merged 9 alpha abc1234", run_id=2)
    assert said(kitchen) == ("merged", True)


def test_a_check_that_ends_on_github_reaches_its_rows_line_on_the_next_2_s_tick(kitchen):
    """The pass saw #9's check going, and `jmerge` waited on it. GitHub's check then passes: its
    job is among the head's check runs, and `jmerge` moves #9 on to review. The next tick, at
    most 2 s later (`jbus-merge.timer`), restates the row's line, with no pass between."""
    on_review(kitchen)
    going = ready.NOT_PASSED.format(check="check")
    kitchen.set("jmerge.txt", f"wait 9 {PULL}: {going}\n")
    kitchen.poll()
    assert (judged(kitchen)["value"], judged(kitchen)["why"]) == ("check", f"wait: {going}")
    kitchen.set("open.json", [kitchen.opened("alpha", 9, "SUCCESS")])
    a_tick_says(kitchen, f"wait 9 {PULL}: {ready.NO_REVIEW}", run_id=2)
    line = judged(kitchen)
    assert (line["value"], line["why"]) == ("review", f"wait: {ready.NO_REVIEW}")
    timer = configparser.ConfigParser(interpolation=None)
    timer.optionxform = str
    timer.read(REPO / "features" / "jbus" / "units" / "jbus-merge.timer")
    assert timer["Timer"]["OnUnitActiveSec"] == "2s"


def test_a_ticks_stacked_verdict_shows_its_parent_as_the_holder_before_any_pass(kitchen):
    on_review(kitchen)
    stacked = ready.STACKED_ON.format(branch="beta", slug="beta", default="main")
    a_tick_says(kitchen, f"wait 9 {PULL}: {stacked}")
    line = judged(kitchen)
    assert (line["value"], line["who"], line["waits"]) == ("stacked", "beta", "beta to merge")
    assert line["why"] == f"wait: {stacked}"
    a_tick_says(kitchen, f"wait 9 {PULL}: {ready.NO_REVIEW}", run_id=2)
    line = judged(kitchen)
    assert (line["value"], line["who"], line["why"]) == (
        "review",
        "rev",
        f"wait: {ready.NO_REVIEW}",
    )


def test_a_ticks_verdict_given_while_a_pass_runs_is_not_written_back(kitchen, monkeypatch):
    """The pass judged from its own run of `jmerge`, and a tick that ran after it began judged
    later: the pass keeps the tick's facet (`restated.kept`)."""
    on_review(kitchen)

    def later():
        monkeypatch.setattr(verbs, "clock", lambda: NOW + timedelta(seconds=20))
        a_tick_says(kitchen, f"wait 9 {PULL}: {ready.FRESH_CONFLICT}")

    while_keep_work_lists(monkeypatch, later)
    kitchen.poll()
    assert said(kitchen) == ("rebase", True)
    assert kitchen.lines(states.DRIFT) == []


def test_a_tick_that_began_before_a_pass_and_ended_in_it_is_not_written_back(kitchen, monkeypatch):
    """The tick held the run lock, so the pass's own run of `jmerge` found it busy and judged
    nothing; the tick began before the pass and ended after the pass's run, and its verdict is
    the later one (`Said.at`)."""
    on_review(kitchen)
    kitchen.set("jmerge-busy", "")

    def later():
        (kitchen.stub / "jmerge-busy").unlink()
        moments = iter([NOW - timedelta(seconds=5)])
        monkeypatch.setattr(verbs, "clock", lambda: next(moments, NOW + timedelta(seconds=5)))
        a_tick_says(kitchen, f"wait 9 {PULL}: {ready.FRESH_CONFLICT}")

    while_keep_work_lists(monkeypatch, later)
    kitchen.poll()
    assert said(kitchen) == ("rebase", True)
    assert kitchen.lines(states.DRIFT) == []


def test_a_ticks_stacked_verdict_kept_by_a_pass_keeps_its_parent_as_the_holder(
    kitchen, monkeypatch
):
    """The pass keeps a tick's `stacked` verdict (`restated.kept`), and with it the tick's `why`,
    which names the parent that holds the line."""
    on_review(kitchen)
    stacked = ready.STACKED_ON.format(branch="beta", slug="beta", default="main")

    def later():
        monkeypatch.setattr(verbs, "clock", lambda: NOW + timedelta(seconds=20))
        a_tick_says(kitchen, f"wait 9 {PULL}: {stacked}")

    while_keep_work_lists(monkeypatch, later)
    kitchen.poll()
    line = judged(kitchen)
    assert (line["value"], line["who"], line["why"]) == ("stacked", "beta", f"wait: {stacked}")


def test_the_pass_corrects_a_line_broken_by_hand_and_logs_it_as_drift_quietly(kitchen):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    kept = json.loads((kitchen.state / work.NAME).read_text())
    for one in kept["work"]:
        if one["key"] == "alpha":
            one.update(value="ready", who="bus")
    (kitchen.state / work.NAME).write_text(json.dumps(kept))
    kitchen.poll()
    assert (judged(kitchen)["value"], judged(kitchen)["who"]) == ("unapproved", "user")
    drifted = kitchen.events(states.DRIFT)
    assert [(one["line"], one["loud"]) for one in drifted] == [
        ("work-drift alpha: value 'ready' for 'unapproved'", "quiet")
    ]
    kitchen.poll()
    assert len(kitchen.events(states.DRIFT)) == 1


def line_of(key, row=work.Row.FREE, pull=work.Pull.NONE, answered=work.Answered.BOTH, **more):
    facts = work.Facts(
        row,
        work.Thread.NONE,
        work.Launch.NONE,
        work.Written.NONE,
        pull,
        work.Question.NONE,
        answered,
    )
    return work.entry(work.judge(facts), key=key, kind="row", slug=key, **more)


def test_drift_is_what_a_writer_should_have_kept_right_and_not_what_the_pass_alone_sees():
    review, check = work.Pull.REVIEW, work.Pull.CHECK
    pulled = {"pr": "#9", restated.PULLED: "2026-11-07T00:00:00.000000+00:00"}
    before = [
        line_of("gone"),
        line_of("go", row=work.Row.UNAPPROVED),
        line_of("moved", row=work.Row.BEHIND),
        line_of("pushed", pull=review, **pulled),
        line_of("unasked", pull=review, **pulled),
        line_of("opened", pull=work.Pull.NONE),
        {**line_of("valued"), "value": "unapproved"},
    ]
    after = [
        line_of("go"),
        line_of("moved"),
        line_of("pushed", pull=check, pr="#9"),
        line_of("unasked", pull=check, pr="#9", answered=work.Answered.T3),
        line_of("opened", pull=review, pr="#9"),
        line_of("valued"),
        line_of("new"),
    ]
    assert restated.drift(before, after) == [
        ("go", "row 'unapproved' for 'approved and free'"),
        ("gone", "a line for a row the queue does not have"),
        ("new", "no line"),
        ("pushed", "pull 'review' for 'check'"),
        ("valued", "value 'unapproved' for 'ready'"),
    ]


def test_an_act_leaves_a_line_it_cannot_read_as_it_is_and_an_asking_row_still_asking():
    unread = {"key": "alpha", "kind": "row", "value": "unapproved", "facts": "lost"}
    assert work.restate(unread, work.Row.FREE) == unread
    half = {**unread, "facts": {"row": "unapproved", "thread": "none"}}
    assert work.restate(half, work.Row.FREE) == half
    facts = work.Facts(
        work.Row.UNAPPROVED,
        work.Thread.NONE,
        work.Launch.NONE,
        work.Written.NONE,
        work.Pull.NONE,
        work.Question.OPEN,
        work.Answered.BOTH,
    )
    asking = work.entry(work.judge(facts), key="alpha", kind="row", slug="alpha")
    went = work.restate(asking, work.Row.FREE)
    assert (went["value"], went["who"]) == ("asking", asking["who"])
    assert went["facts"]["row"] == "approved and free"


def test_an_act_on_a_question_that_is_gone_or_over_a_queue_that_does_not_parse_writes_no_line(
    kitchen,
):
    add(kitchen, "alpha", approve=False)
    kitchen.poll()
    before = (kitchen.state / work.NAME).read_text()
    config = jbus.load()
    run = passes.Pass(config, config.project("demo"), NOW, lambda _: None)
    waiting.acted(run, "answer", "9")
    (kitchen.state / "queue.json").write_text("not a table")
    waiting.acted(run, "go", "alpha")
    assert (kitchen.state / work.NAME).read_text() == before
    assert "approve:alpha" in waits(kitchen)
