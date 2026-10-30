"""jbus keeps every event it sends. `events.jsonl` holds each event with its text and the time jbus
sent it. `jbus events` prints the file and writes nothing.

The tests run the real pass and the real command against the faked T3 Code server of
`test_jbus_kitchen`, or the real `wake.Box`. The log uses the test's clock, which the test sets
with `clock.at`. Nothing reaches the network.

jbus builds the table of kinds from what each module of jbus declares in its `EVENTS`. The tests of
the table import the real `jbus.wake` in a fresh Python, with made-up modules beside jbus's own.
"""

import json
import stat
import subprocess
import sys
from datetime import timedelta

import pytest

from jbus import Project, wake
from test_jbus_kitchen import GATE, KEY, NOW, REFUSED

ASKED = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")


class Clock:
    def __init__(self):
        self.now = NOW

    def at(self, moment):
        self.now = moment
        return moment


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    made = Clock()
    monkeypatch.setattr(wake.Box, "clock", staticmethod(lambda: made.now))
    return made


def box(tmp_path):
    project = Project("demo", tmp_path / "checkout", "demo", "project-1")
    return wake.Box(tmp_path / "state", project)


def at(moment):
    return moment.isoformat(timespec="seconds")


def logged(kitchen):
    """Return the file's own lines that are events, as jbus wrote them."""
    lines = (kitchen.state / "events.jsonl").read_text().splitlines()
    return list(map(json.loads, lines))


def printed(kitchen, *argv):
    code, out = kitchen.main("events", *argv)
    assert code == 0
    return [json.loads(line) for line in out.splitlines()]


def stray(kitchen, *slugs):
    """Make pull requests that are open and have no brief. The next pass records one condition
    for each new one."""
    pulls = [kitchen.opened(slug, 10 + place) for place, slug in enumerate(slugs)]
    kitchen.set("open.json", pulls)


def poll(kitchen, clock, now):
    """Run a pass that starts now, on a clock that reads now."""
    return kitchen.poll(clock.at(now))


def tree(root):
    return {
        str(path): (path.stat().st_mtime_ns, path.read_bytes() if path.is_file() else None)
        for path in sorted(root.rglob("*"))
    }


def test_a_gate_sent_in_a_pass_is_read_back_from_the_log_and_from_jbus_events(kitchen):
    assert kitchen.main("gate", "alpha", stdin=ASKED) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    kitchen.poll()
    (gate,) = [one for one in logged(kitchen) if one["event"] == "gate"]
    assert gate["text"] == ASKED.strip()
    (named,) = [one["id"] for one in wake.entries(kitchen.state) if one["event"] == "gate"]
    assert printed(kitchen, "--slug", "alpha") == [
        {
            "at": at(NOW),
            "event": "gate",
            "slug": "alpha",
            "loud": "quiet",
            "line": "gate alpha: question 1: which way?",
            "text": ASKED.strip(),
            "id": named,
        }
    ]


def test_an_event_a_pass_sends_is_logged_with_its_slug_loudness_and_line(kitchen):
    stray(kitchen, "beta")
    kitchen.poll()
    (gate,) = printed(kitchen)
    assert (gate["at"], gate["slug"], gate["loud"]) == (at(NOW), "beta", "quiet")
    assert gate["line"] == "condition beta: pull request #10 has no brief"


def test_the_log_is_private_and_holds_no_key(kitchen):
    kitchen.wakes.refused = REFUSED
    assert kitchen.main("gate", "alpha", stdin=ASKED) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    kitchen.poll()
    path = kitchen.state / "events.jsonl"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert KEY not in path.read_text()


def test_jbus_events_writes_nothing(kitchen):
    assert kitchen.main("gate", "alpha", stdin=ASKED) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    kitchen.poll()
    before = tree(kitchen.root)
    assert printed(kitchen)
    assert printed(kitchen, "--slug", "alpha", "--since", "2026-10-12")
    assert tree(kitchen.root) == before


def test_jbus_events_before_any_event_prints_nothing_and_makes_no_state(kitchen):
    assert kitchen.main("events") == (0, "")
    assert not kitchen.state.exists()


def test_since_leaves_out_what_was_sent_before_it(kitchen, clock):
    later = NOW + timedelta(hours=1)
    stray(kitchen, "beta")
    poll(kitchen, clock, NOW)
    stray(kitchen, "beta", "gamma")
    poll(kitchen, clock, later)
    both = [("beta", at(NOW)), ("gamma", at(later))]
    assert [(one["slug"], one["at"]) for one in printed(kitchen)] == both
    for since in ("2026-10-12T15:30:00+00:00", "2026-10-12 11:30"):
        assert [(one["slug"], one["at"]) for one in printed(kitchen, "--since", since)] == both[1:]


def test_slug_and_since_together_leave_only_what_passes_both(kitchen, clock):
    later = NOW + timedelta(hours=1)
    assert kitchen.main("gate", "alpha", stdin=ASKED) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    clock.at(later)
    assert kitchen.main("done", "alpha", stdin="Status: done\n") == (0, "queued\n")
    assert kitchen.main("done", "beta", stdin="Status: done\n") == (0, "queued\n")
    shown = printed(kitchen, "--slug", "alpha", "--since", "2026-10-12T15:30:00+00:00")
    assert [(one["line"], one["at"]) for one in shown] == [
        ("result alpha: Status: done", at(later))
    ]


def test_a_since_that_is_no_time_is_refused(kitchen):
    code, out = kitchen.main("events", "--since", "teatime")
    assert (code, out) == (1, "refused: --since teatime is not a time, as 2026-10-12T15:00 is\n")


def test_an_event_a_key_keeps_out_is_not_logged(tmp_path):
    made = box(tmp_path)
    assert made.send("alpha", "result", "result alpha: done", key="once")
    assert not made.send("alpha", "result", "result alpha: done", key="once")
    assert len(made.log()) == 1


def test_the_daily_prune_drops_what_is_older_than_two_weeks(kitchen, clock):
    old, recent, evening = (
        NOW - timedelta(days=15),
        NOW - timedelta(days=13),
        NOW + timedelta(hours=7),
    )
    stray(kitchen, "beta")
    poll(kitchen, clock, old)
    stray(kitchen, "beta", "gamma")
    poll(kitchen, clock, recent)
    assert [(one["slug"], one["at"]) for one in printed(kitchen)] == [
        ("beta", at(old)),
        ("gamma", at(recent)),
    ]
    poll(kitchen, clock, evening)
    kept = [(one["event"], one["slug"], one["at"]) for one in printed(kitchen)]
    assert kept == [("condition", "gamma", at(recent)), ("snapshot", "", at(evening))]
    assert stat.S_IMODE((kitchen.state / "events.jsonl").stat().st_mode) == 0o600


TABLE = {
    "act": "quiet",
    "gate": "quiet",
    "waiting": "quiet",
    "alert": "quiet",
    "recovered": "quiet",
    "stall": "quiet",
    "decision": "user",
    "failover": "quiet",
    "waiting-on-user": "quiet",
    "condition": "quiet",
    "clock": "quiet",
    "hold-stall": "quiet",
    "home-stall": "quiet",
    "merged": "quiet",
    "gate answered": "quiet",
    "result": "quiet",
    "review": "quiet",
    "report": "quiet",
    "stale": "quiet",
    "rebase": "quiet",
    "rereview": "quiet",
    "restack": "quiet",
    "drops": "quiet",
    "failed": "quiet",
    "conflict": "quiet",
    "refailed": "quiet",
    "green": "quiet",
    "mainmoved": "quiet",
    "resume": "quiet",
    "slot-wake": "quiet",
    "slot-end": "quiet",
    "pool-wake": "quiet",
    "retro": "quiet",
    "cancelled": "quiet",
    "snapshot": "quiet",
    "jmerge": "quiet",
    "expedite": "quiet",
    "heartbeat": "quiet",
    "queue": "quiet",
    "sweep": "quiet",
    "reviewed": "quiet",
    "note": "quiet",
    "unplaced": "quiet",
    "item.proposed": "quiet",
    "item.linked": "quiet",
    "item.approved": "quiet",
    "item.queued": "quiet",
    "item.launched": "quiet",
    "item.waiting": "quiet",
    "item.resumed": "quiet",
    "item.held": "quiet",
    "item.done": "quiet",
    "item.dropped": "quiet",
    "pack": "quiet",
}


def test_the_table_of_kinds_is_the_one_written_out_here_kind_for_kind():
    assert wake.LOUDNESS == TABLE
    sent = {kind: wake.event("demo", "alpha", kind, "a line")["loud"] for kind in TABLE}
    assert sent == TABLE


def fresh(tmp_path, run, **modules):
    """Run a fresh Python that imports jbus with `modules` beside its own, then runs `run`."""
    for name, source in modules.items():
        (tmp_path / f"{name}.py").write_text(source)
    code = f"import jbus\njbus.__path__.append({str(tmp_path)!r})\n{run}\n"
    return subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)


def test_a_new_module_s_kind_is_sent_at_its_level_with_no_line_in_wake(tmp_path):
    shouting = (
        "from jbus import wake\n"
        'EVENTS = {"shouting": "user"}\n'
        "def tell():\n"
        '    return wake.event("demo", "alpha", "shouting", "a line")\n'
    )
    run = "from jbus import shouting, wake\nprint(shouting.tell()['loud'], len(wake.LOUDNESS))"
    ran = fresh(tmp_path, run, shouting=shouting)
    assert (ran.returncode, ran.stdout.split()) == (0, ["user", str(len(TABLE) + 1)]), ran.stderr


def test_a_kind_two_modules_declare_fails_at_import_and_names_both(tmp_path):
    ran = fresh(
        tmp_path,
        "import jbus.wake",
        first='EVENTS = {"shouting": "user"}\n',
        second='EVENTS = {"whisper": "quiet", "shouting": "quiet"}\n',
    )
    assert ran.returncode != 0
    last = ran.stderr.splitlines()[-1]
    assert last.startswith("ValueError") and "shouting" in last
    assert "jbus.first" in last and "jbus.second" in last and "whisper" not in last


def test_a_module_in_a_folder_declares_its_kinds_as_one_at_the_top_does(tmp_path):
    (tmp_path / "feature" / "deep").mkdir(parents=True)
    (tmp_path / "feature" / "__init__.py").write_text('EVENTS = {"shouting": "user"}\n')
    (tmp_path / "feature" / "deep" / "__init__.py").write_text("")
    (tmp_path / "feature" / "deep" / "tell.py").write_text(
        'from jbus import Loud\nEVENTS: dict[str, Loud] = {"whisper": "quiet"}\n'
    )
    run = "from jbus import wake\nprint(wake.LOUDNESS['shouting'], wake.LOUDNESS['whisper'])"
    ran = fresh(tmp_path, run)
    assert (ran.returncode, ran.stdout.split()) == (0, ["user", "quiet"]), ran.stderr


@pytest.mark.parametrize(
    "written",
    [
        'EVENTS = {"shouting": "usr"}',
        'KIND = "shouting"\nEVENTS = {KIND: "user"}',
        'EVENTS = dict(shouting="user")',
        'EVENTS = ("shouting", "user")',
        "EVENTS: dict[str, str]",
        'EVENTS = OTHER = {"shouting": ["user"]}',
    ],
)
def test_an_events_that_is_not_kinds_at_levels_written_out_fails_at_import(tmp_path, written):
    ran = fresh(tmp_path, "import jbus.wake", odd=written + "\n")
    assert ran.returncode != 0
    last = ran.stderr.splitlines()[-1]
    assert last.startswith("ValueError: jbus.odd: EVENTS is not a dict written out")
