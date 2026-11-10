"""A crew that paused on rows not yet merged names them on its Result's `Paused on:` line, and jbus
tells it to carry on, once, when the last of them merges (`jbus.pausedon`). No home is woken."""

from datetime import timedelta

import pytest

from test_jbus_kitchen import HOME, NOW, Kitchen, asks, sends
from test_jbus_queue import add

PAUSED = (
    "\n## Result\nStatus: paused, at {head}\nDone when: the table: does not hold\n"
    "Paused on: {rows}\nBranch: three   Pull request: none\nLeft: waits on {rows}\n"
)


@pytest.fixture
def paused(tmp_path, monkeypatch):
    """`one`, `two` and `three` launched side by side, and `three`'s crew paused on `one` and
    `two`, both open as #10 and #11. Each thread's turn has ended."""
    kitchen = Kitchen(tmp_path, monkeypatch)
    kitchen.word()
    kitchen.config(max_running=8)
    for slug in ("one", "two", "three"):
        add(kitchen, slug)
    kitchen.poll(NOW - timedelta(minutes=30))
    launched = sorted(given["title"] for given in kitchen.t3.launches)
    assert launched == ["crew: one", "crew: three", "crew: two"]
    for thread in kitchen.t3.threads:
        thread["status"] = "completed"
    path = kitchen.home / "tasks" / "three.md"
    path.write_text(path.read_text() + PAUSED.format(head="e" * 12, rows="`one`, `two`"))
    kitchen.set("open.json", [kitchen.opened("one", 10), kitchen.opened("two", 11)])
    yield kitchen
    kitchen.close()


def carry_ons(kitchen):
    return [given for given in asks(kitchen) if given["clientRequestId"].startswith("paused-on|")]


def crew_of(kitchen, slug):
    (thread,) = [t for t in kitchen.t3.threads if t["title"] == f"crew: {slug}"]
    return thread["threadId"]


def test_a_paused_crew_is_told_once_when_the_last_row_it_paused_on_merges(paused):
    paused.poll(NOW - timedelta(minutes=20))
    assert carry_ons(paused) == []

    paused.set("open.json", [paused.opened("two", 11)])
    paused.set("merged.json", [paused.merged("one", 10, "a" * 40)])
    paused.poll(NOW - timedelta(minutes=10))
    assert carry_ons(paused) == []

    home_before = [given for given in sends(paused) if given["threadId"] == HOME]
    paused.set("open.json", [])
    paused.set(
        "merged.json",
        [paused.merged("one", 10, "a" * 40), paused.merged("two", 11, "b" * 40)],
    )
    for minute in (0, 3, 6):
        paused.poll(NOW + timedelta(minutes=minute))

    (told,) = carry_ons(paused)
    assert told["threadId"] == crew_of(paused, "three")
    assert "one, two" in told["message"] and "Paused on:" in told["message"]
    assert "tasks/three.md" in told["message"]
    home_after = [given for given in sends(paused) if given["threadId"] == HOME]
    assert home_after == home_before


def test_a_crew_that_is_no_longer_paused_is_told_nothing(paused):
    path = paused.home / "tasks" / "three.md"
    path.write_text(path.read_text() + "\n## Result, follow-up\nStatus: not done\nLeft: none\n")
    paused.set("open.json", [])
    paused.set(
        "merged.json",
        [paused.merged("one", 10, "a" * 40), paused.merged("two", 11, "b" * 40)],
    )
    paused.poll(NOW)
    assert carry_ons(paused) == []
