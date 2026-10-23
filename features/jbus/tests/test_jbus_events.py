"""jbus keeps every event it sends. `events.jsonl` holds each event with its text, the time jbus
sent it and the time jbus posted it. `jbus events` prints the file and writes nothing.

The tests run the real pass and the real command against the faked T3 Code server and webhook of
`test_jbus_kitchen`, or the real `wake.Box` against the webhook of `test_jbus_wake`. The log uses
the test's clock, which the test sets with `clock.at`. Nothing reaches the network.

jbus builds the table of kinds from what each module of jbus declares in its `EVENTS`. The tests of
the table import the real `jbus.wake` in a fresh Python, with made-up modules beside jbus's own.
"""

import json
import stat
import subprocess
import sys
from datetime import timedelta

import pytest

import jbus
from jbus import Project, wake
from test_jbus_kitchen import GATE, KEY, NOW
from test_jbus_wake import KEY as HOOK_KEY
from test_jbus_wake import Webhook

ASKED = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")


@pytest.fixture
def webhook():
    fake = Webhook()
    yield fake
    fake.close()


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


def box(tmp_path, webhook):
    project = Project("demo", tmp_path / "checkout", "demo", "project-1", webhook.url, HOOK_KEY)
    return wake.Box(tmp_path / "state", project)


def at(moment):
    return moment.isoformat(timespec="seconds")


def logged(kitchen):
    """Return the file's own lines that are events, as jbus wrote them."""
    lines = (kitchen.state / "events.jsonl").read_text().splitlines()
    return [one for one in map(json.loads, lines) if "posted" not in one]


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


def test_a_gate_sent_in_a_pass_is_read_back_from_the_log_and_from_jbus_events_unposted(kitchen):
    assert kitchen.main("gate", "alpha", stdin=ASKED) == (0, "queued: question 1\n")
    kitchen.poll()
    (gate,) = [one for one in logged(kitchen) if one["event"] == "gate"]
    assert gate["text"] == ASKED.strip()
    assert printed(kitchen, "--slug", "alpha") == [
        {
            "at": at(NOW),
            "event": "gate",
            "slug": "alpha",
            "loud": "quiet",
            "line": "gate alpha: question 1: which way?",
            "text": ASKED.strip(),
            "posted": None,
        }
    ]


def test_a_decision_queued_while_a_pass_runs_is_posted_after_it_was_sent(kitchen, clock):
    """The pass began before the decision, and the event's queued time and posted time both come
    from the clock, not from the start of the pass."""
    queued, posting = NOW + timedelta(seconds=30), NOW + timedelta(seconds=40)
    clock.at(queued)
    config = jbus.load()
    made = wake.Box(kitchen.state, config.project("demo"), config.webhook)
    assert made.send("alpha", "decision", "decision alpha: which way?")
    clock.at(posting)
    kitchen.poll(NOW)
    assert [(one["at"], one["posted"]) for one in printed(kitchen)] == [(at(queued), at(posting))]


def test_an_event_a_pass_sends_is_logged_with_its_slug_loudness_and_line(kitchen):
    stray(kitchen, "beta")
    kitchen.poll()
    (gate,) = printed(kitchen)
    assert (gate["at"], gate["slug"], gate["loud"]) == (at(NOW), "beta", "quiet")
    assert gate["line"] == "condition beta: pull request #10 has no brief"


def test_the_log_is_private_and_holds_no_webhook_url_and_no_key(kitchen):
    kitchen.webhook.status = 500
    assert kitchen.main("gate", "alpha", stdin=ASKED) == (0, "queued: question 1\n")
    kitchen.poll()
    path = kitchen.state / "events.jsonl"
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert kitchen.webhook.url not in path.read_text()
    assert KEY not in path.read_text()


def test_jbus_events_writes_nothing(kitchen):
    assert kitchen.main("gate", "alpha", stdin=ASKED) == (0, "queued: question 1\n")
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
    assert kitchen.main("gate", "alpha", stdin=ASKED) == (0, "queued: question 1\n")
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


def test_a_quiet_event_is_never_posted_and_one_for_the_user_is_at_the_next_post(
    tmp_path, webhook, clock
):
    made = box(tmp_path, webhook)
    made.send("", "note", "note: a quiet one")
    assert made.flush(NOW, lambda _: None) == 0
    assert [(one["line"], one["posted"]) for one in made.log()] == [("note: a quiet one", None)]
    later = clock.at(NOW + timedelta(minutes=10))
    made.send("alpha", "decision", "decision alpha: which?")
    assert made.flush(later, lambda _: None) == 1
    assert [(one["at"], one["line"], one["posted"]) for one in made.log()] == [
        (at(NOW), "note: a quiet one", None),
        (at(later), "decision alpha: which?", at(later)),
    ]


def test_a_post_the_webhook_refuses_leaves_the_event_not_posted(tmp_path, webhook):
    webhook.fail = {1}
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "decision alpha: which?")
    assert made.flush(NOW, lambda _: None) == 0
    assert [one["posted"] for one in made.log()] == [None]


def test_the_same_event_sent_again_after_its_post_is_not_posted(tmp_path, webhook, clock):
    made = box(tmp_path, webhook)
    made.send("alpha", "decision", "decision alpha: which?")
    assert made.flush(NOW, lambda _: None) == 1
    later = clock.at(NOW + timedelta(minutes=1))
    made.send("alpha", "decision", "decision alpha: which?")
    assert [(one["at"], one["posted"]) for one in made.log()] == [
        (at(NOW), at(NOW)),
        (at(later), None),
    ]


def test_an_event_a_key_keeps_out_is_not_logged(tmp_path, webhook):
    made = box(tmp_path, webhook)
    assert made.send("alpha", "result", "result alpha: done", key="once")
    assert not made.send("alpha", "result", "result alpha: done", key="once")
    assert len(made.log()) == 1


def test_a_log_that_cannot_be_written_stops_no_event_and_no_post(tmp_path, webhook):
    """The test puts a directory where the log goes, so every append fails, and the webhook still
    gets both lists."""
    made = box(tmp_path, webhook)
    (made.state / "events.jsonl").mkdir(parents=True)
    assert made.send("alpha", "decision", "decision alpha: which?", "a" * 70_000, cap=70_000)
    assert made.send("beta", "decision", "decision beta: which?", "b" * 70_000, cap=70_000)
    said, went = [], []
    assert made.flush(NOW, said.append, went=went.append) == 2
    assert [[one["slug"] for one in post["events"]] for post in webhook.posts] == [
        ["alpha"],
        ["beta"],
    ]
    assert (said, went, made.waiting(), made.marks()["last_error"]) == ([], [""], 0, "")
    assert made.log() == []


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
    kept = [(one["event"], one["slug"], one["at"], one["posted"]) for one in printed(kitchen)]
    assert kept == [
        ("condition", "gamma", at(recent), None),
        ("snapshot", "", at(evening), None),
    ]
    assert stat.S_IMODE((kitchen.state / "events.jsonl").stat().st_mode) == 0o600


TABLE = {
    "gate": "quiet",
    "waiting": "quiet",
    "alert": "user",
    "stall": "quiet",
    "decision": "user",
    "failover": "quiet",
    "sign-in": "user",
    "waiting-on-user": "quiet",
    "condition": "quiet",
    "merged": "quiet",
    "gate answered": "quiet",
    "result": "quiet",
    "review": "quiet",
    "report": "quiet",
    "stale": "quiet",
    "rebase": "quiet",
    "rereview": "quiet",
    "drops": "quiet",
    "proof": "quiet",
    "failed": "quiet",
    "conflict": "quiet",
    "refailed": "quiet",
    "green": "quiet",
    "mainmoved": "quiet",
    "resume": "quiet",
    "slot-wake": "quiet",
    "pool-wake": "quiet",
    "retro": "quiet",
    "snapshot": "quiet",
    "jmerge": "quiet",
    "expedite": "quiet",
    "heartbeat": "quiet",
    "queue": "quiet",
    "sweep": "quiet",
    "relayed": "quiet",
    "overlap": "quiet",
    "note": "quiet",
    "leftover": "quiet",
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
    "item.steered": "quiet",
    "item.sent": "quiet",
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
