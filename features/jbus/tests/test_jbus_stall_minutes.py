"""Each spell a running row's thread is quiet or hung is one record of `stalls.jsonl`: a line when a
pass first sees it, and a line with its minutes when a pass sees it end.

The tests run the real pass against the faked T3 Code server of `test_jbus_kitchen`, and read the
file the pass appends to. The first pass begins the file with the moment the record began, so a
week the passes watched with no stall has 0 stall minutes per merged row, and a row merged before
it is a gap. A spell is counted once however many passes see it, and a thread that waits on the
user's answer, or a home's thread, is never in a spell.
"""

import contextlib
import io
import json
from datetime import timedelta

from jbus import cli
from test_jbus_kitchen import NOW, iso
from test_jbus_kpi_page import Cells, run
from test_jbus_live import MIN, hanging, written


def lines(kitchen):
    path = kitchen.state / "stalls.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def stalls(kitchen):
    return [one for one in lines(kitchen) if "began" not in one]


def ended(kitchen):
    return [one for one in stalls(kitchen) if "minutes" in one]


def test_a_thread_quiet_over_three_passes_gives_its_minutes_once(kitchen):
    thread = hanging(kitchen, minutes=12, queued=0)
    for minute in range(3):
        kitchen.poll(NOW + minute * MIN)
        assert written(kitchen)[0]["live"] == "quiet"
    assert stalls(kitchen) == [
        {
            "at": iso(NOW),
            "thread": thread["threadId"],
            "role": "crew",
            "slug": "alpha",
            "since": iso(NOW - 12 * MIN),
        }
    ]
    wrote = NOW + 2 * MIN + timedelta(seconds=30)
    thread |= {"updatedAt": iso(wrote), "itemCount": 41}
    kitchen.poll(NOW + 3 * MIN)
    kitchen.poll(NOW + 4 * MIN)

    assert written(kitchen)[0]["live"] == "moving"
    assert ended(kitchen) == [
        {
            "at": iso(NOW + 3 * MIN),
            "thread": thread["threadId"],
            "role": "crew",
            "slug": "alpha",
            "since": iso(NOW - 12 * MIN),
            "until": iso(wrote),
            "minutes": 14.5,
            "became": "moving",
        }
    ]


def test_a_quiet_spell_that_turns_hung_is_one_spell_until_the_thread_is_gone(kitchen):
    thread = hanging(kitchen, minutes=15, queued=0)
    kitchen.poll()
    kitchen.poll(NOW + 6 * MIN)
    assert written(kitchen)[0]["live"] == "hung"
    kitchen.t3.threads.remove(thread)
    kitchen.poll(NOW + 7 * MIN)
    kitchen.poll(NOW + 8 * MIN)

    assert [(one["minutes"], one["became"]) for one in ended(kitchen)] == [(22.0, "gone")]
    assert len(stalls(kitchen)) == 2


def test_a_thread_that_waits_on_the_users_answer_is_in_no_spell(kitchen):
    hanging(kitchen, minutes=25, queued=0, pendingRequestCount=1)
    for minute in range(3):
        kitchen.poll(NOW + minute * MIN)
    assert written(kitchen)[0]["live"] == "waiting"
    assert stalls(kitchen) == []


def test_a_quiet_spell_ends_when_its_thread_starts_to_wait_on_the_user(kitchen):
    thread = hanging(kitchen, minutes=11, queued=0)
    kitchen.poll()
    thread["pendingRequestCount"] = 1
    for minute in range(1, 4):
        kitchen.poll(NOW + minute * MIN)

    assert [(one["minutes"], one["became"]) for one in ended(kitchen)] == [(12.0, "waiting")]


def test_a_home_thread_quiet_is_no_rows_spell(kitchen):
    hanging(kitchen, "demo", minutes=12, queued=0, title="home: demo")
    kitchen.poll()
    kitchen.poll(NOW + MIN)
    assert written(kitchen)[0]["live"] == "quiet"
    assert stalls(kitchen) == []


def test_a_thread_that_writes_between_two_passes_and_is_quiet_again_is_two_spells(kitchen):
    thread = hanging(kitchen, minutes=12, queued=0)
    kitchen.poll()
    again = NOW + 1 * MIN
    thread |= {"updatedAt": iso(again), "itemCount": 41}
    kitchen.poll(NOW + 15 * MIN)
    kitchen.poll(NOW + 16 * MIN)

    assert [(one["since"], one["until"], one["minutes"]) for one in ended(kitchen)] == [
        (iso(NOW - 12 * MIN), iso(again), 13.0)
    ]
    assert [one["since"] for one in stalls(kitchen) if "minutes" not in one] == [
        iso(NOW - 12 * MIN),
        iso(again),
    ]


def test_a_gap_with_no_pass_before_the_spell_adds_none_of_its_minutes(kitchen):
    thread = hanging(kitchen, minutes=2, queued=0)
    kitchen.poll()
    assert written(kitchen)[0]["live"] == "moving"
    after = NOW + 5 * 60 * MIN
    kitchen.poll(after)
    assert written(kitchen)[0]["live"] == "hung"
    thread |= {"updatedAt": iso(after + MIN), "itemCount": 41}
    kitchen.poll(after + 2 * MIN)

    assert [(one["since"], one["until"], one["minutes"]) for one in ended(kitchen)] == [
        (iso(NOW - 2 * MIN), iso(after + MIN), 3.0)
    ]


def test_a_gap_with_no_pass_inside_a_spell_adds_none_of_its_minutes(kitchen):
    thread = hanging(kitchen, minutes=12, queued=0)
    kitchen.poll()
    kitchen.poll(NOW + MIN)
    after = NOW + MIN + 5 * 60 * MIN
    kitchen.poll(after)
    thread |= {"updatedAt": iso(after + MIN), "itemCount": 41}
    kitchen.poll(after + 2 * MIN)
    kitchen.poll(after + 3 * MIN)

    assert [(one["since"], one["until"], one["minutes"]) for one in ended(kitchen)] == [
        (iso(NOW - 12 * MIN), iso(after + MIN), 14.0)
    ]


def test_a_week_the_passes_watched_with_no_stall_shows_no_stall_minute_per_merged_row(kitchen):
    hanging(kitchen, minutes=2, queued=0)
    for minute in range(3):
        kitchen.poll(NOW + minute * MIN)
        assert written(kitchen)[0]["live"] == "moving"
    with open(kitchen.state / "transitions.jsonl", "a") as log:
        for slug, at in (("before", NOW - timedelta(days=7)), ("beta", NOW + 60 * MIN)):
            log.write(json.dumps({"slug": slug, "from": "pr", "to": "merged", "at": iso(at)}))
            log.write("\n")
    with contextlib.redirect_stdout(io.StringIO()):
        assert cli.main(["telemetry"]) == 0
    out = kitchen.state_dir / "kpis.html"

    code, said = run("--week", iso(NOW)[:10], "--out", str(out))

    assert code == 0, said
    cells = Cells()
    cells.feed(out.read_text())
    assert lines(kitchen) == [{"at": iso(NOW), "began": True}]
    stall = cells.rows["Stall minutes per merged row"]
    assert stall[5] == "0 min n 1 tracked: covers demo"
    assert stall[4] == (
        "n/a n 0 no data: covers demo; no stall record kept for 1 merged row, on 2026-10-05"
    )
