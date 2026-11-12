"""A test that main's ledger of reds calls a flake twice in seven days gets one row.

`mainmoved.tell` writes a line to `main-reds.jsonl` for each red tip, with the tests that failed
there, and one when the spell ends, with its cause. Where one test failed in two spells that went
green with no fix, no more than seven days apart, the pass writes `tasks/flake-<name>.md` and
queues it as jbus's own row, which the follow-up rule approves. A test gets one row, ever: a third
flake, a pass run again and a row that was removed file no other. The real pass runs against the
kitchen's fakes."""

import json
from datetime import timedelta

import pytest

import jbus
from jbus import flakerow, mainmoved, queue
from test_jbus_kitchen import NOW, Kitchen
from test_jbus_queue import rows

TESTS = "features/jbus/tests/test_jbus_{}.py::test_{}"
TEST = TESTS.format("digest", "jbus_digest_writes_nothing")
OTHER = TESTS.format("view", "the_view_reads_the_queue")
SLUG = "flake-test-jbus-digest-writes-nothing"
DAY = timedelta(days=1)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    (made.home / "follow-rule").write_text("9\n")
    yield made
    made.close()


def write(kitchen, line):
    kitchen.state.mkdir(parents=True, exist_ok=True)
    with open(kitchen.state / mainmoved.REDS, "a") as handle:
        handle.write(json.dumps(line) + "\n")


def red(kitchen, sha, ago, failed, cause=mainmoved.NO_FIX, after=None, verdict="change"):
    """Add the line `mainmoved.tell` writes for a red tip `sha`, judged `ago` before NOW, of the
    spell since the green tip `after` (one of its own where none is given), and with a `cause`,
    the line that closed the spell at `sha` an hour later."""
    write(
        kitchen,
        {
            "at": (NOW - ago).isoformat(),
            "sha": sha * 40,
            "after": (after or f"g{sha}") * 40,
            "prs": [],
            "step": "check / make check: test",
            "failed": failed,
            "verdict": verdict,
        },
    )
    if cause:
        closed(kitchen, sha, ago - timedelta(hours=1), cause)


def closed(kitchen, sha, ago, cause=mainmoved.NO_FIX):
    """Add the line that closes the spell whose first red tip is `sha`, `ago` before NOW."""
    at = (NOW - ago).isoformat()
    write(kitchen, {"at": at, "sha": sha * 40, "green": "f" * 40, "prs": [], "cause": cause})


def filed(kitchen):
    if not (kitchen.state / "queue.json").exists():
        return []
    return sorted(slug for slug in rows(kitchen) if slug.startswith(flakerow.PREFIX))


def test_a_test_that_flaked_twice_in_seven_days_gets_one_row(kitchen):
    red(kitchen, "1", 6 * DAY, [TEST, OTHER])
    red(kitchen, "2", 3 * DAY, [OTHER], cause="fix: #9", verdict="flake")
    red(kitchen, "3", DAY, [TEST])
    kitchen.poll()
    assert filed(kitchen) == [SLUG]
    brief = (kitchen.home / "tasks" / f"{SLUG}.md").read_text()
    assert brief == (kitchen.state / "briefs" / f"{SLUG}.md").read_text()
    task = next(line for line in brief.splitlines() if line.startswith("Task: "))
    assert f"`{TEST}`" in task
    assert f"{'1' * 12} ({(NOW - 6 * DAY).isoformat()})" in task
    assert f"{'3' * 12} ({(NOW - DAY).isoformat()})" in task
    assert "\nSize: S\n" in brief
    assert "\nReview: review\n" in brief
    assert "\nWhere: `features/jbus/tests/test_jbus_digest.py`\n" in brief
    assert f"\nDecisions: {queue.RED_DECIDED}" in brief
    made = rows(kitchen)[SLUG]["approval"]
    assert (made["basis"], made["ref"]) == (queue.RULE, queue.FOLLOW_REF)


def test_two_flaked_tips_of_one_spell_are_one_flake(kitchen):
    """The tips of a spell are one red main, not two, and a spell is a flake only once it went
    green with no fix: one still red counts for nothing."""
    red(kitchen, "1", 3 * DAY, [TEST], cause=None, after="0")
    red(kitchen, "2", 3 * DAY - timedelta(minutes=15), [TEST], cause=None, after="0")
    closed(kitchen, "1", 3 * DAY - timedelta(minutes=30))
    kitchen.poll()
    assert filed(kitchen) == []
    red(kitchen, "4", DAY, [TEST], cause=None, after="3")
    kitchen.poll()
    assert filed(kitchen) == []
    closed(kitchen, "4", DAY - timedelta(minutes=30))
    kitchen.poll()
    assert filed(kitchen) == [SLUG]


def test_a_third_flake_files_no_second_row(kitchen):
    """The row stays the test's one row: a pass run again, and a third flake once its row went
    from the queue, file no other. A test whose row was removed, one that flaked once, and one
    whose two flakes are more than seven days apart file none."""
    once, apart = TESTS.format("a", "once"), TESTS.format("b", "apart")
    gone = "flake-test-the-view-reads-the-queue"
    jbus.write_json(kitchen.state / "removed.json", {gone: {"at": NOW.isoformat(), "by": "user"}})
    red(kitchen, "1", 9 * DAY, [apart])
    red(kitchen, "2", 2 * DAY, [TEST, OTHER, once])
    red(kitchen, "3", DAY, [TEST, OTHER, apart])
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=5))
    assert filed(kitchen) == [SLUG]
    assert sorted(path.name for path in (kitchen.home / "tasks").glob("flake-*")) == [f"{SLUG}.md"]
    (kitchen.state / "queue.json").write_text("[]\n")
    red(kitchen, "4", -DAY, [TEST])
    kitchen.poll(NOW + DAY)
    assert filed(kitchen) == []


def test_a_row_the_queue_refused_is_filed_on_a_later_pass(kitchen):
    """Nothing is kept of a row the queue refused, so the pass that finds the queue whole again
    files it."""
    red(kitchen, "1", 2 * DAY, [TEST])
    red(kitchen, "2", DAY, [TEST])
    (kitchen.state / "queue.json").write_text("not a table\n")
    kitchen.poll()
    assert any(SLUG in line for line in kitchen.lines("condition"))
    (kitchen.state / "queue.json").write_text("[]\n")
    kitchen.poll(NOW + timedelta(minutes=5))
    assert filed(kitchen) == [SLUG]
