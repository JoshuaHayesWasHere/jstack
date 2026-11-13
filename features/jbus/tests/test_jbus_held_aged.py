"""A wait whose reason has not changed past its code's bound is a blocker its home clears
(aged-wait, self-heal-gaps E2).

On 2026-11-11 st-mainred-fast's pull request #1695 waited from 20:20:28Z on `check has no run at
912dad95c383` (waits.jsonl:1517), a run GitHub kept queued with no job, which no crew can start.
`clock.held` woke its home at 20:52Z, then dropped the hold as soon as the row's crew was at work
on something else, and `jbus tidy blockers` listed nothing: no `check:`, `row:` or `left:` key is a
wait. The block reached the user only through a catch-up, hours later.

The tests replay that row through the real pass against the kitchen's fakes, at the times of the
day: the hold stays while the crew is busy, since no crew clears a run GitHub keeps queued;
`jbus tidy blockers` prints `fix wait:st-mainred-fast` once the wait is past its code's bound
(`aged.BOUNDS`), at 21:20Z; and, once the home's fixes reach `retry_cap`, a decision for the
user. The view lists it as an `aged` wrong."""

import json
from datetime import UTC, datetime, timedelta

import pytest

import jbus
from jbus import aged, blockers, clock, passes, verbs, wakes
from jbus.view import state
from jmerge import ready
from test_jbus_blocker_retries import fix, paged, seen
from test_jbus_kitchen import sends
from test_jbus_leftover import home
from test_jbus_queue import add

SLUG, NUMBER, HEAD = "st-mainred-fast", 1695, "912dad95c383"
REASON = ready.NO_RUN.format(check="check", head=HEAD)
LINE_1517 = {"slug": SLUG, "why": f"wait: {REASON}", "at": "2026-11-11T20:20:28+00:00"}
"""The line of waits.jsonl the day kept when #1695 started to wait, as the pass wrote it."""
KEY = f"wait:{SLUG}"


def at(hour, minute, second=0):
    return datetime(2026, 11, 11, hour, minute, second, tzinfo=UTC)


class Day:
    """st-mainred-fast's row, its crew idle, its pull request #1695 open, and `jmerge` saying it
    waits on a check with no run at its head, from 20:20:28Z on."""

    def __init__(self, kitchen):
        self.kitchen = kitchen
        self.desk = home(kitchen)
        add(kitchen, SLUG)
        self.crew = kitchen.t3.thread(SLUG, "completed", idle=timedelta(hours=2))
        kitchen.set("open.json", [kitchen.opened(SLUG, NUMBER)])
        kitchen.quiet()
        kitchen.set("jmerge.txt", f"wait {NUMBER} https://example.test/pull/{NUMBER}: {REASON}\n")
        self.poll(at(20, 20, 28))
        last = (kitchen.state / "waits.jsonl").read_text().splitlines()[-1]
        assert json.loads(last) == LINE_1517

    def poll(self, moment):
        self.kitchen.poll(moment)

    def busy(self):
        """The crew starts its run 4, on work of its own: it is at work from here on."""
        self.crew["status"] = "running"
        self.kitchen.t3.at_work.add(self.crew["threadId"])

    def holds(self):
        return list(jbus.read_json(self.kitchen.state / clock.HELD_FILE, {}).values())

    def woke(self):
        """Each time `clock.held` woke the home about a hold."""
        sent = sends(self.kitchen)
        return [one for one in sent if one["clientRequestId"].startswith(f"{clock.HELD}|")]

    def clear(self, moment):
        self.kitchen.monkeypatch.setattr(verbs, "clock", lambda: moment)
        code, said = self.kitchen.main("--project", "demo", "tidy", "blockers")
        assert code == 0, said
        return said.splitlines()


def test_held_2026_11_11_hold_of_1695_stays_while_its_crew_is_busy_on_other_work(kitchen):
    """The home is woken once at 20:52Z, and the hold stays in `held.json`, woken, through 22:31Z
    while st-mainred-fast's crew is at work: no crew starts a run GitHub keeps queued, so a busy
    crew is not at work on the cause."""
    day = Day(kitchen)
    day.poll(at(20, 52, 22))
    (hold,) = day.holds()
    assert (hold["rows"], hold["woke"], hold["since"]) == ([SLUG], True, LINE_1517["at"])
    assert len(day.woke()) == 1
    day.busy()
    for moment in (at(21, 0), at(21, 20, 30), at(22, 0), at(22, 31)):
        day.poll(moment)
        (kept,) = day.holds()
        assert (kept["woke"], kept["since"]) == (True, LINE_1517["at"]), moment
    assert len(day.woke()) == 1


def test_blockers_jbus_clear_prints_fix_wait_st_mainred_fast_at_21_20(kitchen):
    """`no-run` is a jbus act's, bounded at `aged.BOUNDS`' minutes: unchanged since 20:20:28Z,
    it is no blocker at 21:19Z and the home's `fix` at 21:20Z, also with the crew busy. A line a
    pass cut short as it died ends `waits.jsonl` then, and `jbus.blockers` reads past it."""
    assert blockers.waits(kitchen.state) == []
    day = Day(kitchen)
    day.busy()
    day.poll(at(21, 19, 30))
    assert not [line for line in day.clear(at(21, 19, 30)) if KEY in line]
    day.poll(at(21, 20, 30))
    with (kitchen.state / "waits.jsonl").open("a") as log:
        log.write('{"slug": "st-mainred-fast", "why": "wa')
    (line,) = [line for line in day.clear(at(21, 20, 30)) if KEY in line]
    assert line.startswith(f"fix {KEY}: ") and REASON in line and "try 1 of 2" in line


def test_blockers_an_aged_wait_whose_fixes_reach_retry_cap_is_a_decision(kitchen):
    """The home briefed two fixes of the key, and both merged; at 22:31Z #1695 still waits on the
    same reason, so `jbus tidy blockers` raises it to the user, once."""
    day = Day(kitchen)
    for n in (1, 2):
        slug = f"{SLUG}-fix-{n}"
        code, said = kitchen.main(
            "--project", "demo", "queue", "add", slug, "--priority", "1", stdin=fix(slug, KEY)
        )
        assert code == 0, said
        seen(kitchen, slug, timedelta(minutes=30), status="merged", pr=f"#{1700 + n}")
    day.poll(at(22, 31))
    (line,) = [line for line in day.clear(at(22, 31)) if KEY in line]
    assert line.startswith(f"decision {KEY}: ") and "the retry cap" in line
    day.clear(at(22, 32))
    assert len([one for one in paged(kitchen) if KEY in one["line"]]) == 1


def test_wrongs_list_an_aged_wait_for_its_home(kitchen):
    """The view lists the wait as an `aged` wrong from its bound, with its `since` from
    waits.jsonl, for the row's home to fix, and the catch-up takes it as a row that does not
    move."""
    from jbus.view.panels.since import panel as since

    day = Day(kitchen)
    day.poll(at(21, 20, 30))
    run = passes.Pass(jbus.load(), jbus.load().projects[0], at(21, 20, 30))
    (aged,) = [one for one in wakes.read(run).once(state.wrongs) if one["kind"] == "aged"]
    assert (aged["row"], aged["since"]) == (SLUG, LINE_1517["at"])
    assert REASON in aged["cause"] and aged["owner"].startswith("home")
    assert "aged" in since.STUCK


@pytest.mark.parametrize("code", sorted(ready.codes()))
def test_blockers_each_reason_code_has_a_bound_and_an_owner(code):
    """A code `jmerge` gains with no row of `aged.BOUNDS` fails here, so no wait is left with
    nobody to age it."""
    bound = aged.BOUNDS[code]
    assert bound.owner in aged.OWNERS
    assert (bound.minutes is None) == (bound.owner == aged.USER)
