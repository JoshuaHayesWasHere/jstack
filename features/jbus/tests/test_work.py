"""Each piece of work has one state. The tests run `work.judge` over every set of facts there is,
and run each ending that a pass can meet as `features/jbus/tests/test_jbus_queue.py` runs,
against a faked T3 Code, `gh` and `jmerge`, with `work.json` read back."""

import json
import time
from dataclasses import replace
from datetime import timedelta

import pytest

import jbus
from jbus import queue, work
from jmerge import ready
from test_jbus_kitchen import NOW, Kitchen, iso
from test_jbus_queue import add, rows

PULL = "https://example.test/pull/9"
AT = "2026-10-12 10:00 ET"


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


def test_each_value_but_unknown_is_one_pattern_and_the_values_are_the_closed_set():
    assert work.VALUES == (
        "removed",
        "asking",
        "hung",
        "waiting",
        "merged",
        "leftover",
        "done",
        "closed",
        "result",
        "review",
        "findings",
        "second",
        "check",
        "proof",
        "rebase",
        "hold",
        "launching",
        "working",
        "quiet",
        "lost",
        "unapproved",
        "behind",
        "ready",
        "unknown",
    )
    assert [one.value for one in work.PATTERNS] == list(work.VALUES[:-1])


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
        "user",
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
    remove = ("--project", "demo", "queue", "remove", "alpha", "--by", "user", "--at", AT)
    assert kitchen.main(*remove)[0] == 0
    thread = kitchen.t3.thread("alpha", "running")
    kitchen.poll()
    line = judged(kitchen, thread["threadId"])
    assert (line["kind"], line["slug"], line["value"]) == ("thread", "alpha", "removed")
    assert "alpha" not in rows(kitchen)


def test_a_hung_turn(kitchen):
    add(kitchen, "alpha")
    kitchen.t3.thread("alpha", "running", idle=timedelta(minutes=25))
    kitchen.poll()
    line = judged(kitchen)
    assert (line["value"], line["who"], line["facts"]["thread"]) == ("hung", "user", "hung")
    assert rows(kitchen)["alpha"]["status"] == "left"


def test_a_pull_request_on_a_step_is_that_step_and_a_hung_thread_over_it_is_hung(kitchen):
    add(kitchen, "alpha")
    kitchen.brief("alpha", result(branch=f"alpha   Pull request: {PULL}"))
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
    holders = {"user", "crew", "rev", "ci", "bus", "dep", "ok", "home", "unknown"}
    roles = {"crew", "rev", "scout", "home", "other"}
    for facts in work.every():
        state = work.judge(facts)
        for home in (False, True):
            for after in (False, True):
                held = work.holder(state, home=home, after=after)
                assert held.who in holders
                if state.value not in ("leftover", "closed"):
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
