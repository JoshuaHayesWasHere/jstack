"""The store's `launch_failures`: one row for each launch that failed or waited, by its cause, built
from the records jbus writes as it writes them: a `failover` line of `events.jsonl` that says an
instance could not sign in, with the row's launch before it in `transitions.jsonl`, and the spells
of a row's reason to wait in `waits.jsonl` that keep a launch from starting. The causes are
`jbus.telemetry.launch_failures`'s, and the table is the one
`jbus.telemetry.migrations.v021_launch_failures` makes."""

import contextlib
from datetime import timedelta

from test_jbus_telemetry import NOW, iso, machine

__all__ = ["machine"]


def failover(at, slug, said):
    line = f"failover {slug}: {said}, carry-on on claudeAgent to claudeAgent_claude_prime"
    return {"at": iso(at), "event": "failover", "slug": slug, "loud": "quiet", "line": line}


def launched(at, slug):
    return {"at": iso(at), "slug": slug, "from": "queued", "to": "launched", "by": "jbus"}


def wait(at, slug, why):
    return {"slug": slug, "why": why, "at": iso(at)}


def minutes(n):
    return NOW + timedelta(minutes=n)


def t(moment):
    """A time as the store keeps it (`jbus.telemetry.values.STAMP`)."""
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def rows(machine):
    machine.build()
    with contextlib.closing(machine.store()) as store:
        return store.execute(
            'SELECT project, slug, cause, reason, start, "end", minutes FROM launch_failures '
            'ORDER BY project, coalesce(start, "end"), slug'
        ).fetchall()


def test_each_cause_jbus_records_is_a_row_with_its_start_end_and_minutes(machine):
    machine.append(
        "alpha",
        "transitions.jsonl",
        launched(minutes(0), "signs"),
        launched(minutes(30), "signs"),
    )
    machine.append(
        "alpha",
        "events.jsonl",
        failover(minutes(33), "signs", "claudeAgent could not sign in"),
        failover(minutes(34), "scout far", "claudeAgent could not sign in"),
        failover(minutes(35), "capped", "claudeAgent is at its 5h limit"),
    )
    machine.append(
        "alpha",
        "waits.jsonl",
        wait(minutes(40), "tmp", "waiting: /tmp at 81% of its quota"),
        wait(minutes(41), "tmp", "waiting: /tmp at 83% of its quota"),
        wait(minutes(50), "tmp", ""),
        wait(minutes(40), "slot", "max_per_home is 12 in the polish home"),
        wait(minutes(46), "slot", "waiting for room on the machine"),
        wait(minutes(52), "slot", "depends on tmp"),
        wait(minutes(60), "out", "no launch: claudeAgent cannot sign in (Not logged in)"),
        wait(
            minutes(61), "out", "no launch: claudeAgent is capped until 2026-10-28T17:00:00+00:00"
        ),
        wait(minutes(40), "held", "depends on tmp"),
        wait(minutes(45), "held", ""),
    )
    machine.append(
        "beta",
        "waits.jsonl",
        wait(minutes(70), "open", "max_running is 8"),
    )
    capped = "no launch: claudeAgent is capped until 2026-10-28T17:00:00+00:00"
    assert rows(machine) == [
        ("alpha", "signs", "sign-in", None, t(minutes(30)), t(minutes(33)), 3.0),
        ("alpha", "scout far", "sign-in", None, None, t(minutes(34)), None),
        ("alpha", "slot", "no slot", None, t(minutes(40)), t(minutes(46)), 6.0),
        ("alpha", "tmp", "/tmp", None, t(minutes(40)), t(minutes(50)), 10.0),
        (
            "alpha",
            "slot",
            "other",
            "waiting for room on the machine",
            t(minutes(46)),
            t(minutes(52)),
            6.0,
        ),
        ("alpha", "out", "sign-in", None, t(minutes(60)), t(minutes(61)), 1.0),
        ("alpha", "out", "other", capped, t(minutes(61)), None, None),
        ("beta", "open", "no slot", None, t(minutes(70)), None, None),
    ]


def test_a_spell_that_ends_after_a_build_is_closed_by_the_next_build(machine):
    machine.append(
        "alpha", "waits.jsonl", wait(minutes(0), "tmp", "waiting: /tmp at 90% of its quota")
    )
    assert rows(machine) == [("alpha", "tmp", "/tmp", None, t(minutes(0)), None, None)]
    machine.append("alpha", "waits.jsonl", wait(minutes(12), "tmp", ""))
    assert rows(machine) == [("alpha", "tmp", "/tmp", None, t(minutes(0)), t(minutes(12)), 12.0)]
