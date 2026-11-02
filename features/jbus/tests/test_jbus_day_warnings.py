"""A later review's warnings collect in one follow-up row a day, and none is dropped.

A review after the first sends its crew only its errors: a warning holds nothing and is kept, and
an info is dropped (`jbriefs.findings.KEPT`). Once a day has ended, the pass files the day's
warnings row, `warnings-<day>`, of every warning kept from a pull request that merged, each with
its path:line and the pull request it came from, `Size: S` and `Review: cleanup`, and approves
it by the follow-up rule as it queues it, so nothing of it reaches the user. A day with no warning
files nothing, and a day's warnings under `BAR` carry to the next day's row. The row's own review keeps
nothing, so no follow-up of a follow-up is queued. The real pass runs against the kitchen's fakes,
with `SINCE`, the merge of #833, set before the kitchen's clock."""

import json
from datetime import timedelta

import pytest

from jbus import daywarnings, queue
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import rows

HEAD, FIX = "a" * 40, "b" * 40
FIRST = "warning a.py:3 the loop reads the list twice (principle: none) (bucket: Act on)"
WARNING = "warning src/{slug}/c.py:7 a test asserts what the code computed (bucket: Act on)"
CONSIDERED = "warning src/{slug}/d.py:2 a name hides its unit (bucket: Consider) (risk: data)"
ERROR = "error src/{slug}/e.py:40 the retry never stops (bucket: Consider)"
INFO = "info src/{slug}/b.py:9 a name says less than it could (bucket: Act on)"
DAY = timedelta(days=1)
TODAY = "2026-10-12"


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "follow-rule").write_text("9\n")
    monkeypatch.setattr(daywarnings, "SINCE", NOW - 30 * DAY)
    yield made
    made.close()


def review(head, found, scope=""):
    listed = "".join(f"- {one}\n" for one in found) or "- none\n"
    scoped = f"Scope: range-diff x..{HEAD} x..{FIX}\n" if scope else ""
    verdict = "findings" if found else "clean"
    return (
        f"\n## Review\nBy: claudeAgent claude-sonnet-5-5 high #1\nVerdict: {verdict}\n{scoped}"
        f"Head: {head}\nFindings:\n{listed}"
    )


def reviewed(kitchen, slug, number, second, answers="", mode="review"):
    """Write the brief of `slug` as its crew leaves it: its first review answered and fixed at
    FIX, then the scoped pass of the fix, which found `second`, and `answers` after it."""
    pull = f"https://example.test/pull/{number}"
    found = [one.format(slug=slug) for one in second]
    (kitchen.home / "tasks" / f"{slug}.md").write_text(
        f'# {slug}: a task\nTask: "do it"\nPull request: open one when done\nReview: {mode}\n\n'
        f"## Result\nStatus: done\nBranch: {slug}   Pull request: {pull}\nReviewer: mcp:9 #1\n"
        f"Finding F1: fixed, the loop\nFixed: {FIX}\nScoped reviewer: mcp:10, of {FIX}\n{answers}"
        + review(HEAD, (FIRST,))
        + review(FIX, found, scope=True)
    )


def merged(kitchen, *pulls):
    """Say that GitHub lists `pulls`, each a slug and its number, as merged ten minutes before
    the kitchen's clock."""
    made = [kitchen.merged(slug, number, f"{number:040d}") for slug, number in pulls]
    (kitchen.stub / "merged.json").write_text(json.dumps(made))


def filed(kitchen):
    if not (kitchen.state / "queue.json").exists():
        return []
    return sorted(slug for slug in rows(kitchen) if slug.startswith(daywarnings.PREFIX))


def text(kitchen, slug):
    return (kitchen.state / "briefs" / f"{slug}.md").read_text()


def test_a_days_warnings_are_one_row_filed_once_the_day_ends_and_approved_by_rule(kitchen):
    reviewed(kitchen, "alpha", 7, (ERROR, WARNING, INFO), "Finding F2: fixed, the retry\n")
    reviewed(kitchen, "beta", 8, (WARNING, CONSIDERED))
    merged(kitchen, ("alpha", 7), ("beta", 8))
    kitchen.poll()
    assert filed(kitchen) == []
    kitchen.poll(NOW + DAY)
    assert filed(kitchen) == [f"warnings-{TODAY}"]
    brief = text(kitchen, f"warnings-{TODAY}")
    done = brief.split("Done when:\n")[1].split("\n- Each warning")[0].splitlines()
    assert done == [
        "- alpha F3 warning src/alpha/c.py:7: a test asserts what the code computed "
        "(https://example.test/pull/7)",
        "- beta F2 warning src/beta/c.py:7: a test asserts what the code computed "
        "(https://example.test/pull/8)",
        "- beta F3 warning src/beta/d.py:2: a name hides its unit (https://example.test/pull/8)",
    ]
    assert "\nSize: S\n" in brief
    assert "\nReview: cleanup\n" in brief
    assert "e.py" not in brief and "b.py" not in brief
    made = rows(kitchen)[f"warnings-{TODAY}"]["approval"]
    assert (made["basis"], made["ref"]) == (queue.RULE, queue.FOLLOW_REF)
    assert made["words"].startswith(queue.FOLLOW_RULE)
    assert "follows" not in made or not made["follows"]
    kitchen.poll(NOW + 2 * DAY)
    kitchen.poll(NOW + 3 * DAY)
    assert filed(kitchen) == [f"warnings-{TODAY}"]


def test_a_day_with_no_warning_files_no_row(kitchen):
    reviewed(kitchen, "alpha", 7, (INFO,))
    reviewed(kitchen, "beta", 8, (ERROR,), "Finding F2: fixed, the retry\n")
    merged(kitchen, ("alpha", 7), ("beta", 8))
    for days in range(3):
        kitchen.poll(NOW + days * DAY)
    assert filed(kitchen) == []


def test_a_days_warnings_under_the_bar_carry_to_the_next_days_row(kitchen):
    reviewed(kitchen, "alpha", 7, (WARNING, CONSIDERED))
    merged(kitchen, ("alpha", 7))
    kitchen.poll()
    kitchen.poll(NOW + DAY)
    assert filed(kitchen) == []
    reviewed(kitchen, "beta", 8, (WARNING,))
    merged(kitchen, ("alpha", 7), ("beta", 8))
    kitchen.poll(NOW + DAY + timedelta(hours=1))
    assert filed(kitchen) == []
    kitchen.poll(NOW + 2 * DAY)
    assert filed(kitchen) == ["warnings-2026-10-13"]
    brief = text(kitchen, "warnings-2026-10-13")
    assert "kept 2026-10-12 to 2026-10-13" in brief
    for line in ("alpha F2", "alpha F3", "beta F2"):
        assert f"\n- {line} warning " in brief


def test_the_days_rows_own_review_an_open_pull_request_and_one_before_since_keep_nothing(
    kitchen, monkeypatch
):
    """The day's row says `Review: cleanup`: its one review sends its crew an error alone and
    keeps nothing, so no follow-up of a follow-up is queued. A pull request still open keeps
    nothing yet, and one that merged before #833 had its warnings answered then."""
    reviewed(kitchen, "warnings-2026-10-11", 6, (WARNING, WARNING, WARNING), mode="cleanup")
    reviewed(kitchen, "early", 5, (WARNING, WARNING, WARNING))
    reviewed(kitchen, "alpha", 7, (WARNING, WARNING, WARNING))
    pulls = [
        kitchen.merged("warnings-2026-10-11", 6, "6" * 40),
        kitchen.merged("early", 5, "5" * 40),
    ]
    pulls[1]["mergedAt"] = "2026-09-01T12:00:00Z"
    (kitchen.stub / "merged.json").write_text(json.dumps(pulls))
    (kitchen.stub / "open.json").write_text(json.dumps([kitchen.opened("alpha", 7)]))
    for days in range(3):
        kitchen.poll(NOW + days * DAY)
    assert filed(kitchen) == []
