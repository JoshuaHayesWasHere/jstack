"""The outbox holds a message that needs `act` while its receiver cannot act on it now, by the rules
of `jbus.outbox.RULES`: `busy`, `slot` and `review`. A wake still reaches a waiting thread, and a
message that needs `decide` is held by no rule. The tests send through the real outbox against the
kitchen's fakes, and run the real pass where a sender's next message is what they are about."""

import fcntl
import json
import os

import jbus
from jbus import clock, expedite, outbox, passes, rebase, slotwait, t3, watch, word
from jgauge import slot, waiters
from test_jbus_github import failed, keys, launched, pull
from test_jbus_github import passes as at
from test_jbus_kitchen import NOW

__all__ = ["launched"]

OUT = "\n## Result\nReviewer: mcp:a-reviewer #1\n"
WRITTEN = f"\n## Review\nBy: mcp:a-reviewer #1\nVerdict: clean\nHead: {'c' * 40}\n"


def run_of(kitchen, look=False):
    """Return a pass of the kitchen's project and a client of its T3 Code, with what the pass saw
    where `look` is set."""
    config = jbus.load()
    run = passes.Pass(config, config.projects[0], NOW, lambda _: None)
    client = t3.Client(config.server, config.token_path)
    if look:
        run.world = watch.look(run, client, []).world
    return run, client


def send(run, client, thread, template, needs="act", row="alpha"):
    return outbox.send(
        run,
        client,
        thread=thread,
        row=row,
        key=f"{template}|{row}|{len(run.told)}",
        text="jbus: a line",
        template=template,
        needs=needs,
    )


def held(kitchen):
    """Return each held line of `outbox.jsonl` as its template and its rule."""
    lines = (kitchen.state / outbox.FILE).read_text().splitlines()
    return [
        (one["template"], one["rule"]) for one in map(json.loads, lines) if one["went"] == "held"
    ]


def test_a_conflict_while_the_reviewer_is_out_is_held_and_the_state_after_the_review_is_told(
    launched,
):
    """A crew puts a rebase off while a review it launched is unwritten, so the conflict message
    before the review waits. Once the review is written, the pass sends what the state calls for
    then, the rebase message under its own key, and never the conflict message it held."""
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text() + OUT)
    launched.set("open.json", [pull(launched, mergeable="CONFLICTING")])
    at(launched, 0, 3)
    assert keys(launched) == []
    assert held(launched) == [("conflict", "review"), ("conflict", "review")]
    brief.write_text(brief.read_text() + WRITTEN)
    at(launched, 6, 9)
    assert keys(launched) == ["rebase|alpha|cccccccccccc"]


def test_a_review_out_holds_no_ask_for_that_review_no_clock_line_and_no_decide(launched):
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text() + OUT)
    launched.set("open.json", [pull(launched)])
    crew = launched.t3.threads[0]["threadId"]
    for template, needs, went in [
        ("rebase", "act", False),
        ("rereview", "act", True),
        ("clock", "act", True),
        ("unreviewed", "act", True),
        ("leftover", "decide", True),
    ]:
        run, client = run_of(launched, look=True)
        assert send(run, client, crew, template, needs) is went, template
    assert held(launched) == [("rebase", "review")]


def test_a_review_out_holds_only_the_crew_and_not_a_home_told_of_its_row(launched):
    """The crew is the one that puts work off while its review is out. A home told of the row (a
    stall of the very review that is not written, `jbus.owners`) waits on no review."""
    brief = launched.home / "tasks" / "alpha.md"
    brief.write_text(brief.read_text() + OUT)
    launched.set("open.json", [pull(launched)])
    home = launched.t3.thread("home", "completed")["threadId"]
    run, client = run_of(launched, look=True)
    assert send(run, client, home, "wrong")
    assert held(launched) == []


def waiting(kitchen):
    """Return the thread of alpha's crew, whose turn ended to wait on the short lane."""
    (crew,) = kitchen.t3.threads
    lane = slot.short()
    command = ["uv", "run", "pytest", "tests/test_alpha.py"]
    waiters.register(slot.locks_dir(), crew["threadId"], "short", lane.slots, command, NOW)
    return crew["threadId"]


def test_a_waiter_gets_its_wake_and_the_clock_s_line_and_a_decide_and_nothing_else(launched):
    crew = waiting(launched)
    for template, needs, went in [
        ("rebase", "act", False),
        ("failed", "act", False),
        ("slot-wake", "act", True),
        ("clock", "act", True),
        ("leftover", "decide", True),
        ("word", "act", True),
    ]:
        run, client = run_of(launched)
        assert send(run, client, crew, template, needs) is went, template
    assert held(launched) == [("rebase", "slot"), ("failed", "slot")]
    waiters.woken(slot.locks_dir(), waiters.read(slot.locks_dir())[0].id, NOW)
    run, client = run_of(launched)
    assert send(run, client, crew, "rebase")


def test_a_thread_gets_one_act_message_a_pass_and_a_decide_beside_it(launched):
    """A sender that names the thread without T3 Code's `mcp:` prefix names the same thread."""
    crew = launched.t3.threads[0]["threadId"]
    run, client = run_of(launched)
    assert send(run, client, crew, "rebase")
    assert not send(run, client, crew.removeprefix("mcp:"), "failed")
    assert send(run, client, crew, "leftover", "decide")
    assert held(launched) == [("failed", "busy")]
    run, client = run_of(launched)
    assert send(run, client, crew, "failed")


def test_a_thread_at_work_is_held_but_the_user_s_word_to_it_is_not(launched):
    home = launched.t3.thread("home", "running")["threadId"]
    run, client = run_of(launched)
    assert not send(run, client, home, "answer")
    assert send(run, client, home, "word", row="demo")
    assert send(run, client, home, "item", row="demo")
    assert held(launched) == [("answer", "busy")]


def test_a_spared_template_is_one_its_sender_sends():
    """Each name a rule spares is the template its sender gives the outbox, so a renamed template
    is not held by accident."""
    assert set(slotwait.EVENTS) | {clock.CLOCK} == outbox.WAKES
    assert outbox.USERS == {word.KIND, "item"}
    kinds = {row.kind for row in expedite.TABLE}
    asked = {rebase.unproven("a..b", "c..d").kind, "rereview"}
    assert outbox.ASKS <= kinds | asked and asked <= outbox.ASKS


def test_a_pass_that_finds_a_held_message_due_no_more_sends_nothing_late(launched):
    """A held message is not queued: when the state moves on while it waits, the pass sends
    nothing of it. Here the crew pushed a new head while it waited on a slot, every slot of the
    lane taken, and the failed check of the old head is never told."""
    crew = waiting(launched)
    taken = take(slot.short())
    try:
        launched.set("open.json", [pull(launched, [failed()])])
        at(launched, 0)
        waiters.drop(slot.locks_dir(), crew)
        launched.set("open.json", [pull(launched, head="d" * 40)])
        at(launched, 3, 6)
    finally:
        for fd in taken:
            os.close(fd)
    assert keys(launched) == []
    assert held(launched) == [("failed", "slot")]


def take(lane):
    """Take every slot of the lane, as running tests would, and return the open lock files."""
    locks = slot.locks_dir()
    locks.mkdir(parents=True, exist_ok=True)
    taken = []
    for n in range(1, lane.slots + 1):
        fd = os.open(locks / f"{lane.lock}.{n}.lock", os.O_RDWR | os.O_CREAT)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        taken.append(fd)
    return taken
