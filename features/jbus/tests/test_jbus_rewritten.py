"""`jbus.watch.rewritten` tells a crew once when its brief lost lines it had on the pass before: a
later round appends a `## Result, follow-up` and never rewrites a section. Like
`test_jbus_kitchen.py`, the tests run the real pass against the fakes.
"""

import json
from datetime import timedelta

import pytest

from jbus import watch
from test_jbus_kitchen import NOW, RESULT, sends
from test_jbus_queue import add, gates

PROVED = "Proved: proved.sh passed at cccccccccccc"


def told_rewritten(kitchen):
    return [s for s in sends(kitchen) if s["clientRequestId"].startswith("rewritten|")]


@pytest.fixture
def written(kitchen):
    """Launch alpha, whose crew has opened pull request 7 and ended its turn on a Result with a
    `Proved:` line. A row that is over, merged or done, is no crew's at work, and goes unread."""
    add(kitchen, "alpha")
    assert "launched alpha: mcp:thread-1" in kitchen.poll(NOW - timedelta(minutes=30))
    kitchen.t3.threads[0]["status"] = "completed"
    kitchen.set("open.json", [kitchen.opened("alpha", 7, state=None)])
    path = kitchen.home / "tasks" / "alpha.md"
    url = "https://example.test/pull/7"
    result = RESULT.replace("Pull request: none", f"Pull request: {url}")
    path.write_text(path.read_text() + f"\n{result}{PROVED}\n")
    kitchen.poll(NOW - timedelta(minutes=20))
    return path


def test_a_brief_that_only_grows_tells_its_crew_nothing(written, kitchen):
    """The head above the first `## ` is the home's and jbus's, which write lines into it in
    place (`watch._add_tip`, `dispatch.write_thread`), and the crew skill sets a `Fixed:` line to
    its new head in place, so only the rest of the sections must grow."""
    written.write_text(written.read_text() + "Fixed: " + "a" * 40 + "\n")
    kitchen.poll(NOW - timedelta(minutes=15))
    head = written.read_text().replace("Where:", "Read: main is red again\nWhere:", 1)
    head = head.replace("Fixed: " + "a" * 40, "Fixed: " + "b" * 40)
    written.write_text(head + "\n## Result, follow-up (2026-11-08, rebased)\n")
    kitchen.poll(NOW - timedelta(minutes=10))
    assert told_rewritten(kitchen) == []
    assert "alpha" in json.loads((kitchen.state / watch.BRIEFS_SEEN).read_text())


def test_a_cut_proved_line_is_told_to_the_crew_once_word_for_word(written, kitchen):
    written.write_text(written.read_text().replace(f"{PROVED}\n", ""))
    said = kitchen.poll(NOW - timedelta(minutes=10))
    kitchen.poll(NOW)
    told = told_rewritten(kitchen)
    assert [one["threadId"] for one in told] == ["mcp:thread-1"]
    assert f"```\n{PROVED}\n```" in told[0]["message"]
    assert "a new `## Result, follow-up (<date>, <why>)` section" in told[0]["message"]
    assert "rewritten alpha: told its crew the brief lost 1 line" in said


def test_a_cut_line_t3_code_refuses_to_send_is_told_on_a_later_pass(written, kitchen):
    written.write_text(written.read_text().replace(f"{PROVED}\n", ""))
    kitchen.t3.refuse_send = True
    said = kitchen.poll(NOW - timedelta(minutes=10))
    assert any(line.startswith("wait alpha: its crew could not be told") for line in said)
    assert not [line for line in said if line.startswith("rewritten alpha")]
    kitchen.t3.refuse_send = False
    said = kitchen.poll(NOW)
    assert "rewritten alpha: told its crew the brief lost 1 line" in said
    assert f"```\n{PROVED}\n```" in told_rewritten(kitchen)[-1]["message"]


FINDING = "- warning src/alpha/a.py:3 the sum is off by one"


def reviewed(kitchen, written, seat=1):
    """A reviewer thread on seat `#1` of alpha, named by the Result's `Reviewer:` line, and the
    `## Review` section it wrote with `seat` on its `By:` line, seen by a pass."""
    made = kitchen.t3.thread("alpha", "completed", title="review: alpha")["threadId"]
    section = (
        f"\n## Review\nBy: claude opus high #{seat}\nVerdict: findings\n"
        f"Head: {'c' * 40}   Unchanged by the run: yes\nFindings:\n{FINDING}\n"
    )
    written.write_text(written.read_text() + f"Reviewer: {made} #1\n" + section)
    kitchen.poll(NOW - timedelta(minutes=15))
    return made


def asked_of_reviewer(kitchen):
    return [s for s in sends(kitchen) if s["clientRequestId"].startswith("rewritten-review|")]


def test_a_line_a_reviewer_took_out_of_its_own_review_is_not_told_to_the_crew(written, kitchen):
    """In #1586 a reviewer corrected its own `## Review`, jbus told the crew to put the lines
    back, and the restored lines left the verdict unread. Only a reviewer writes that section, so
    the crew is never the one to restore it, while a cut from a Result is still the crew's."""
    reviewed(kitchen, written)
    written.write_text(written.read_text().replace(f"{FINDING}\n", ""))
    kitchen.poll(NOW - timedelta(minutes=10))
    assert told_rewritten(kitchen) == []
    written.write_text(written.read_text().replace(f"{PROVED}\n", ""))
    kitchen.poll(NOW)
    told = told_rewritten(kitchen)
    assert len(told) == 1
    assert f"```\n{PROVED}\n```" in told[0]["message"]
    assert FINDING not in told[0]["message"]


def test_a_line_cut_from_a_review_is_asked_of_its_reviewer_once(written, kitchen):
    made = reviewed(kitchen, written)
    written.write_text(written.read_text().replace(f"{FINDING}\n", ""))
    kitchen.poll(NOW - timedelta(minutes=10))
    kitchen.poll(NOW)
    asked = asked_of_reviewer(kitchen)
    assert [one["threadId"] for one in asked] == [made]
    assert f"```\n{FINDING}\n```" in asked[0]["message"]
    assert "your own correction" in asked[0]["message"]
    assert gates(kitchen) == []


def test_a_line_cut_from_a_review_no_reviewer_line_names_is_a_condition(written, kitchen):
    reviewed(kitchen, written, seat=2)
    written.write_text(written.read_text().replace(f"{FINDING}\n", ""))
    kitchen.poll(NOW - timedelta(minutes=10))
    kitchen.poll(NOW)
    assert asked_of_reviewer(kitchen) == told_rewritten(kitchen) == []
    named = [one for one in gates(kitchen) if "lost lines of its review" in one]
    assert named == ["condition alpha: its brief lost lines of its review by seat #2"]
