"""A pull request that still conflicts with its base at a head its crew was told of is told
again once for each tip of main it was not told at (`jbus.rebase.github`): a crew that refused
the first message, or held on a home's word, keeps its head, and nothing else would tell it
when the merge it waited for lands (#1710, 2026-11-11)."""

from datetime import timedelta

import pytest

import jbus
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import add

SLUG = "st-model-test-slot"
HEAD = "8ce761cc69e2" + "0" * 28
TIP, NEXT = "1" * 40, "2" * 40
SPENT = f"rebase|{SLUG}|{HEAD[:12]}"
REVIEW = f"\n## Review\nVerdict: clean\nHead: {'b' * 40}\n"


@pytest.fixture
def crew(tmp_path, monkeypatch):
    """#1710's crew: launched, its turn ended, its brief reviewed, its pull request in conflict
    with main at the head it was told to rebase, under the key that telling spent."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    add(kitchen, SLUG)
    kitchen.poll(NOW - timedelta(minutes=30))
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    result(kitchen, "Reviewer: mcp:reviewer\n" + REVIEW)
    pull = {**kitchen.opened(SLUG, 1710), "mergeable": "CONFLICTING", "headRefOid": HEAD}
    kitchen.set("open.json", [pull])
    kitchen.set("jmerge.txt", "")
    tip(kitchen, TIP)
    yield kitchen
    kitchen.close()


def result(kitchen, lines):
    brief = kitchen.home / "tasks" / f"{SLUG}.md"
    brief.write_text(brief.read_text() + "\n## Result\nStatus: done\n" + lines)


def tip(kitchen, sha):
    kitchen.set("commits.json", [kitchen.commit(sha)])


def keys(kitchen):
    return [
        given["clientRequestId"]
        for tool, given in kitchen.t3.calls
        if tool == "t3_thread_send" and given["clientRequestId"].startswith("rebase|")
    ]


def passes(kitchen, *minutes):
    for minute in minutes:
        kitchen.poll(NOW + timedelta(minutes=minute))


def spend(kitchen, *spent):
    path = kitchen.state / "sent.json"
    jbus.write_json(path, [*jbus.read_json(path, []), *spent])


def test_1710_spent_key_is_told_once_at_a_new_tip_and_not_again_at_that_tip(crew):
    spend(crew, SPENT)
    passes(crew, 0, 3, 6)
    assert keys(crew) == [f"{SPENT}|{TIP[:12]}"]
    tip(crew, NEXT)
    passes(crew, 9, 12)
    assert keys(crew) == [f"{SPENT}|{TIP[:12]}", f"{SPENT}|{NEXT[:12]}"]


def test_a_conflict_first_told_at_a_tip_is_not_told_again_until_main_moves(crew):
    passes(crew, 0, 3, 6)
    assert keys(crew) == [SPENT]
    tip(crew, NEXT)
    passes(crew, 9, 12)
    assert keys(crew) == [SPENT, f"{SPENT}|{NEXT[:12]}"]


def test_a_crew_whose_reviewer_has_not_written_is_not_told_again_until_it_has(crew):
    spend(crew, SPENT)
    result(crew, f"Scoped reviewer: mcp:scoped, of {HEAD}\n")
    passes(crew, 0, 3)
    assert keys(crew) == []
    result(crew, f"\n## Review\nVerdict: clean\nScope: range-diff\nHead: {HEAD}\n")
    passes(crew, 6)
    assert keys(crew) == [f"{SPENT}|{TIP[:12]}"]


def test_a_crew_at_work_is_not_told_again_until_its_turn_ends(crew):
    spend(crew, SPENT)
    for thread in crew.t3.threads:
        thread["status"] = "running"
    passes(crew, 0, 3)
    assert keys(crew) == []
    for thread in crew.t3.threads:
        thread["status"] = "completed"
    passes(crew, 6)
    assert keys(crew) == [f"{SPENT}|{TIP[:12]}"]
