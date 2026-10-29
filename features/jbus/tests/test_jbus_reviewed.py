"""A reviewer writes its section and sends nothing. jbus reads the section on its next pass, asks
jmerge's judge what the pull request is short of, and tells the crew through the outbox only when
the crew owes a line: findings to answer, or a `Fixed:` line. Like `test_jbus_kitchen.py`, the
tests run the real pass against the fakes, and check who is sent what.
"""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import reviewed
from jmerge import ready
from test_jbus_kitchen import FOUND, NOW, review, sends

HEAD = "c" * 40
KEY = f"review|alpha|{HEAD[:12]}"
BY = "By: claudeAgent claude-sonnet-5-5 high #1"


def section(verdict="findings", findings=FOUND, head=HEAD):
    """A section as the reviewer writes it now: its `By:` line, and a `Sent to:` line that names
    no thread, since the reviewer sends nothing."""
    text = review(verdict, "not sent, jbus tells the crew when it owes a line", findings)
    return text.replace("## Review\n", f"## Review\n{BY}\n").replace("c" * 40, head)


def outboxed(kitchen):
    path = kitchen.state / "outbox.jsonl"
    lines = path.read_text().splitlines() if path.exists() else []
    return [json.loads(line) for line in lines]


def noticed(kitchen):
    """The lines of `outbox.jsonl` about a review notice."""
    return [line for line in outboxed(kitchen) if line["key"].startswith("review|")]


def test_a_clean_first_review_sends_nobody_anything(kitchen):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + section("clean", "- none"))
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    for minutes in (0, 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert sends(kitchen) == [] and noticed(kitchen) == []
    assert kitchen.lines("reviewed") == []


def test_a_findings_review_tells_the_crew_once_by_the_outbox_naming_the_section_and_its_ids(
    kitchen,
):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + section())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    for minutes in (0, 3, 6):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    (given,) = sends(kitchen)
    assert (given["threadId"], given["clientRequestId"]) == ("mcp:crew", KEY)
    message = given["message"]
    assert message.startswith(f"jbus: alpha's pull request #7 at {HEAD[:12]} has its review")
    assert BY in message and "the Result has no Fixed line" in message
    assert "F1 [Act on] warning src/alpha/a.py:3 the sum is off by one" in message
    assert message.endswith(jbus.END_TURN)
    ((line),) = noticed(kitchen)
    assert (line["thread"], line["template"], line["needs"], line["went"]) == (
        "mcp:crew",
        "reviewed",
        "act",
        "sent",
    )
    assert kitchen.lines("reviewed") == [f"reviewed alpha: told mcp:crew of #7 at {HEAD[:12]}"]


def test_a_twice_brief_s_second_review_goes_to_its_own_crew(kitchen):
    """The crew answered the first review and pushed its fix. The second review's warning goes to
    the same crew, which owes it an answer and a push before the merge."""
    first = section(head="d" * 40)
    answered = "\n## Result\nFinding F1: fixed, the sum\nFixed: " + HEAD + "\n"
    second = section(findings="- warning src/alpha/b.py:9 a second thing")
    kitchen.brief("alpha", "Review: twice\nThread: mcp:crew\n" + first + answered + second)
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    for minutes in (0, 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    (given,) = sends(kitchen)
    assert given["threadId"] == "mcp:crew"
    assert "nothing was pushed after them" in given["message"]
    assert "F2 [Act on] warning src/alpha/b.py:9 a second thing" in given["message"]


def test_a_findings_review_of_a_brief_with_no_thread_line_goes_to_its_home(kitchen):
    (kitchen.home / "home-id").write_text("mcp:a-home\n")
    kitchen.brief("alpha", section())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    (given,) = sends(kitchen)
    assert (given["threadId"], given["clientRequestId"]) == ("mcp:a-home", KEY)
    assert "F1 [Act on]" in given["message"]


def test_a_findings_review_with_no_thread_line_and_no_home_is_a_gate_once(kitchen):
    kitchen.brief("alpha", section())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    for minutes in (0, 3):
        kitchen.poll(NOW + timedelta(minutes=minutes))
    assert kitchen.lines("condition") == [
        "condition alpha: review findings with no thread to send them to"
    ]
    assert sends(kitchen) == [] and noticed(kitchen) == []


def test_the_notice_waits_while_the_crew_is_at_work_and_goes_after(kitchen):
    crew = kitchen.t3.thread("alpha", "running")
    kitchen.brief("alpha", f"Thread: {crew['threadId']}\n" + section())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    assert sends(kitchen) == []
    assert [(one["went"], one["rule"]) for one in noticed(kitchen)] == [("held", "busy")]
    crew["status"] = "completed"
    kitchen.t3.at_work.discard(crew["threadId"])
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [one["clientRequestId"] for one in sends(kitchen)] == [KEY]


def test_a_review_of_two_seats_is_told_once_both_are_written(kitchen):
    seats = "Reviewer: mcp:r1 #1\nReviewer: mcp:r2 #2\n"
    other = section(findings="- error src/alpha/b.py:9 a second thing").replace("#1", "#2")
    brief = kitchen.brief("alpha", "Thread: mcp:crew\n" + seats + section())
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    assert sends(kitchen) == []
    brief.write_text(brief.read_text() + other)
    kitchen.poll(NOW + timedelta(minutes=3))
    (given,) = sends(kitchen)
    assert "F1 [Act on]" in given["message"] and "F2 [Act on]" in given["message"]


@pytest.mark.parametrize("sent", ["mcp:crew", "1c2d3e4f-0000-4000-8000-000000000000"])
def test_a_section_its_reviewer_sent_itself_is_not_told_again(kitchen, sent):
    """A reviewer launched before this rule still runs the skill text it loaded, and sends the
    findings itself. Its `Sent to:` line names the thread, and jbus sends no second copy."""
    text = section().replace("not sent, jbus tells the crew when it owes a line", sent)
    kitchen.brief("alpha", "Thread: mcp:crew\n" + text)
    kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    kitchen.poll()
    assert sends(kitchen) == []


@pytest.mark.parametrize(
    ("brief", "pull"),
    [
        (section("not run"), "open"),
        (section(), "merged"),
        ("", "open"),
    ],
    ids=["not run", "merged", "no review"],
)
def test_nothing_is_told_where_jmerge_says_the_crew_owes_no_line(kitchen, brief, pull):
    kitchen.brief("alpha", "Thread: mcp:crew\n" + brief)
    if pull == "open":
        kitchen.set("open.json", [kitchen.opened("alpha", 7)])
    else:
        kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll()
    assert noticed(kitchen) == []


@pytest.mark.parametrize("mode", ["", "Review: twice\n"])
def test_a_clean_review_is_judged_the_same_with_or_without_a_fixed_none_needed_line(mode):
    """The crew no longer writes `Fixed: none needed` after a clean review: jmerge's judge gives
    the same answer on the brief with the line and without it, and neither owes the crew a line."""
    brief = f"# alpha: a task\n{mode}Thread: mcp:crew\n" + section("clean", "- none")
    fixed = brief + "\n## Result\nFixed: none needed, the review is clean\n"
    assert ready.short_of(brief, HEAD) == ready.short_of(fixed, HEAD) == ""
    assert reviewed.due(brief, HEAD) is None and reviewed.due(fixed, HEAD) is None
