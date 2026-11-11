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


def test_a_wait_for_room_on_load_is_a_row_of_cause_load_and_a_wait_on_memory_is_other(machine):
    """`jbus.dispatch` writes the head of what `jgauge room` said after `waiting for room on the
    machine`, so a wait on load is its own cause; another no of `jgauge room`, as memory, stays
    `other` with its reason."""
    load = "waiting for room on the machine: load is at or over 85% of 12 cores"
    memory = "waiting for room on the machine: memory available under 2 GB"
    machine.append(
        "alpha",
        "waits.jsonl",
        wait(minutes(0), "busy", load),
        wait(minutes(4), "busy", memory),
        wait(minutes(7), "busy", ""),
    )
    assert rows(machine) == [
        ("alpha", "busy", "load", None, t(minutes(0)), t(minutes(4)), 4.0),
        ("alpha", "busy", "other", memory, t(minutes(4)), t(minutes(7)), 3.0),
    ]


def test_a_spell_that_ends_after_a_build_is_closed_by_the_next_build(machine):
    machine.append(
        "alpha", "waits.jsonl", wait(minutes(0), "tmp", "waiting: /tmp at 90% of its quota")
    )
    assert rows(machine) == [("alpha", "tmp", "/tmp", None, t(minutes(0)), None, None)]
    machine.append("alpha", "waits.jsonl", wait(minutes(12), "tmp", ""))
    assert rows(machine) == [("alpha", "tmp", "/tmp", None, t(minutes(0)), t(minutes(12)), 12.0)]


def relaunch(failed_thread, cause, launched_at, failed_at, **more):
    """A home's entry in `relaunches.json` as `jbus.children.launch` writes it: the relaunch
    after a failed start, with that start's failure, its thread and when it was launched."""
    failed = {"cause": cause, "at": iso(failed_at), "thread": failed_thread, "times": 1, **more}
    if launched_at is not None:
        failed["launched"] = iso(launched_at)
    return {
        "at": iso(failed_at),
        "why": f"its last launch, thread {failed_thread}, is not at work and wrote no home-id",
        "thread": f"{failed_thread}-again",
        "failed": failed,
        "says": f"start failed: {cause}",
    }


def test_each_failed_home_start_is_a_row_from_its_launch_to_its_failure(machine):
    """`relaunches.json` names each home's last failed start, which jbus drops once the home
    starts: the store keeps a row for each failed start it saw, by its thread, so a start that
    sat with no home-id counts with its minutes after its home has started. The store reads the
    file through `jbus.telemetry.records.home_starts` into the table
    `jbus.telemetry.migrations.v022_home_starts` makes."""
    machine.write(
        "alpha",
        "relaunches.json",
        {
            "uncategorized": relaunch("t-1", "it ended with no home-id", minutes(0), minutes(25)),
            "polish": relaunch("t-2", "its run failed", minutes(5), minutes(6)),
        },
    )
    until = iso(minutes(300))
    machine.write(
        "beta",
        "relaunches.json",
        {
            "uncategorized": relaunch("t-3", "not signed in", minutes(1), minutes(3), on="x"),
            "polish": relaunch("t-4", "5h limit", minutes(2), minutes(4), until=until),
            "docs": relaunch("t-5", "it ended with no home-id", None, minutes(9)),
        },
    )
    held = [
        ("alpha", "uncategorized", "no home-id", None, t(minutes(0)), t(minutes(25)), 25.0),
        ("alpha", "polish", "no home-id", None, t(minutes(5)), t(minutes(6)), 1.0),
        ("beta", "uncategorized", "sign-in", None, t(minutes(1)), t(minutes(3)), 2.0),
        ("beta", "polish", "other", "5h limit", t(minutes(2)), t(minutes(4)), 2.0),
        ("beta", "docs", "no home-id", None, None, t(minutes(9)), None),
    ]
    assert rows(machine) == sorted(held, key=lambda row: (row[0], row[4] or row[5], row[1]))
    machine.write(
        "alpha",
        "relaunches.json",
        {
            "uncategorized": {
                "at": iso(minutes(25)),
                "why": "it has no thread",
                "thread": "t-1-again",
            }
        },
    )
    machine.write(
        "beta",
        "relaunches.json",
        {"uncategorized": relaunch("t-6", "it ended with no home-id", minutes(10), minutes(40))},
    )
    held.append(("beta", "uncategorized", "no home-id", None, t(minutes(10)), t(minutes(40)), 30.0))
    assert rows(machine) == sorted(held, key=lambda row: (row[0], row[4] or row[5], row[1]))


def test_a_relaunches_file_that_is_no_object_or_names_no_failed_start_adds_no_row(machine):
    machine.write("alpha", "relaunches.json", ["uncategorized"])
    machine.write("beta", "relaunches.json", {"uncategorized": {"at": iso(minutes(0))}})
    assert rows(machine) == []


def test_a_wait_on_load_written_with_its_reading_is_still_cause_load(machine):
    """A jbus from before `jbus.roomwait` wrote the load's reading after `load`: that wait is on
    load all the same, and a bare wait for room is `other`."""
    load = "waiting for room on the machine: load 30.00 is at or over 85% of 12 cores"
    bare = "waiting for room on the machine"
    machine.append(
        "alpha",
        "waits.jsonl",
        wait(minutes(0), "busy", load),
        wait(minutes(4), "busy", bare),
        wait(minutes(7), "busy", ""),
    )
    assert rows(machine) == [
        ("alpha", "busy", "load", None, t(minutes(0)), t(minutes(4)), 4.0),
        ("alpha", "busy", "other", bare, t(minutes(4)), t(minutes(7)), 3.0),
    ]
