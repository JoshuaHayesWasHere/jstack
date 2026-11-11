"""A row's crew thread has one answer, `jbus.crewthread().crew`: the thread on its brief's `Thread:`
line, which a resume moves, whether jbus or a home made it. The clock's checks, the rebase and
expedite all read it, so a crew a home resumed by hand on a new thread gets its restarts and its
messages there, and not on the thread it left. A resume writes the line and the queue's column
together (`crewthread().move`), and `jbus crew-threads` names each row whose carriers disagree."""

import json
import re
from datetime import UTC, datetime, timedelta

import jbus
from test_jbus_clock import restarts
from test_jbus_github import launched  # noqa: F401  (fixture)
from test_jbus_github import passes as run_at
from test_jbus_kitchen import NOW, sends
from test_jbus_queue import add
from test_jbus_resume import crew_of, landed, left, relaunches  # noqa: F401  (fixture)
from test_jbus_twice import A, red_at

ALPHA = "mcp:thread-1"


def resumed_by_hand(kitchen, slug="alpha"):
    """A home resumes the crew on a new thread and writes the new id on the brief's `Thread:` line,
    as the home skill's pickup does, and archives the old thread."""
    (old,) = [one for one in kitchen.t3.threads if one["title"] == f"crew: {slug}"]
    old["archived"], old["status"] = True, "completed"
    new = kitchen.t3.thread(slug, "completed", idle=timedelta(minutes=30))
    brief = kitchen.home / "tasks" / f"{slug}.md"
    text = re.sub(r"^Thread: .*$", f"Thread: {new['threadId']}", brief.read_text(), flags=re.M)
    brief.write_text(text)
    return old["threadId"], new["threadId"]


def works(kitchen, thread_id, minute):
    """The thread works for a pass at `minute`, then its turn ends."""
    (crew,) = [one for one in kitchen.t3.threads if one["threadId"] == thread_id]
    crew["status"] = "running"
    kitchen.t3.at_work.add(thread_id)
    run_at(kitchen, minute)
    crew["status"] = "completed"
    kitchen.t3.at_work.discard(thread_id)


def test_a_crew_resumed_by_hand_is_restarted_on_its_new_thread_when_a_check_turns_red(launched):  # noqa: F811
    old, new = resumed_by_hand(launched)
    red_at(launched, A, "11")
    run_at(launched, 0)
    works(launched, new, 1)
    run_at(launched, 2, 3, 4, 5)
    assert [one["threadId"] for one in restarts(launched)] == [new]
    assert old not in {one["threadId"] for one in sends(launched)}


def test_a_crew_that_was_not_resumed_is_restarted_on_its_launched_thread(launched):  # noqa: F811
    red_at(launched, A, "11")
    run_at(launched, 0)
    works(launched, ALPHA, 1)
    run_at(launched, 2, 3)
    assert [one["threadId"] for one in restarts(launched)] == [ALPHA]


def crewthread():
    """The module under test, imported where a test uses it, so the restart tests run without it."""
    from jbus import crewthread as module

    return module


def a_pass(kitchen):
    config = jbus.load()
    return jbus.passes.Pass(config, config.project("demo"), datetime.now(UTC))


def column(kitchen, slug):
    rows = json.loads((kitchen.state / "queue.json").read_text())
    return next(row.get("thread", "") for row in rows if row["slug"] == slug)


def line(kitchen, slug):
    brief = (kitchen.home / "tasks" / f"{slug}.md").read_text()
    return re.findall(r"^Thread: (.*)$", brief, flags=re.M)


def test_a_move_writes_the_brief_s_thread_line_and_the_queue_s_column_in_one_call(launched):  # noqa: F811
    crewthread().move(a_pass(launched), "alpha", "mcp:thread-9")
    assert line(launched, "alpha") == ["mcp:thread-9"]
    assert column(launched, "alpha") == "mcp:thread-9"
    assert crewthread().crew(a_pass(launched), "alpha") == "mcp:thread-9"


def test_jbus_s_resume_of_a_left_row_names_its_new_thread_in_the_brief_and_the_queue(left):  # noqa: F811
    left.poll(NOW - timedelta(minutes=20))
    landed(left)
    left.poll(NOW)
    (again,) = relaunches(left)
    new = crew_of(left, "three")["threadId"]
    assert line(left, "three") == [new]
    assert column(left, "three") == new
    assert crewthread().crew(a_pass(left), "three") == new


def test_the_check_names_the_row_whose_carriers_disagree_and_not_the_clean_one(launched):  # noqa: F811
    add(launched, "beta")
    launched.poll(NOW - timedelta(minutes=20))
    assert column(launched, "beta") and line(launched, "beta") == [column(launched, "beta")]
    old, new = resumed_by_hand(launched, "beta")
    found = crewthread().disagreements(a_pass(launched))
    assert [one.slug for one in found] == ["beta"]
    (beta,) = found
    assert (beta.brief, beta.launched, beta.queue) == (new, old, old)
    assert launched.main("crew-threads")[1].splitlines() == [beta.line()]


def test_a_pass_after_a_hand_resume_moves_the_queue_s_column_to_the_brief_s_thread(launched):  # noqa: F811
    _, new = resumed_by_hand(launched)
    run_at(launched, 0)
    assert column(launched, "alpha") == new
    assert crewthread().disagreements(a_pass(launched)) == []
    assert launched.main("crew-threads") == (0, "none: every row's carriers name one crew thread\n")


def test_a_brief_left_behind_by_a_pass_that_died_after_a_launch_takes_the_newest_launch(launched):  # noqa: F811
    """A pass that died between a resume's launch record and the brief's line left the line on an
    older launch's thread: the newest launch is the crew, and the next pass moves the line."""
    directory = launched.state_dir / "launches" / "demo" / "alpha"
    (first,) = directory.glob("*.json")
    record = json.loads(first.read_text())
    later = {**record, "thread": "mcp:thread-7", "at": (NOW + timedelta(minutes=1)).isoformat()}
    (directory / "resumed.json").write_text(json.dumps(later))
    assert crewthread().crew(a_pass(launched), "alpha") == "mcp:thread-7"
    run_at(launched, 2)
    assert line(launched, "alpha") == ["mcp:thread-7"]
    assert column(launched, "alpha") == "mcp:thread-7"
