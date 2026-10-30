"""`jbus.mirror` reads the briefs, the requests and the gates. Each new section is one event, and a
Result that changes goes out again. What a thread pipes to jbus and also writes in the brief goes
out once. Like `test_jbus_kitchen.py`, the tests run the real pass and the real command against the
fakes.
"""

import json
from datetime import timedelta

from test_jbus_kitchen import GATE, NOW, RESULT, complete


def test_each_new_section_is_one_event_and_a_second_pass_sends_nothing(kitchen):
    brief = kitchen.brief("alpha")
    request = kitchen.brief("look", kind="scouts")
    gates = kitchen.home / "gates.md"
    gates.write_text(GATE.format(n=1, asked="an old one?", status="open", slug="alpha"))
    kitchen.quiet()
    review = "\n## Review\nVerdict: findings\nFindings:\n- high a.py:1 wrong\n"
    follow = "\n## Result, follow-up (2026-10-12, a steer)\nStatus: not done\n"
    gate = "\nalpha: gate\n" + GATE.format(
        n="<n>", asked="in the brief?", status="open", slug="alpha"
    )
    brief.write_text(brief.read_text() + RESULT + review + follow + gate)
    request.write_text(request.read_text() + "\n## Report\nStatus: done\nFindings:\n- one\n")
    gates.write_text(
        GATE.format(n=1, asked="an old one?", status="answered 2026-10-12: yes", slug="alpha")
        + "\n"
        + GATE.format(n=2, asked="a new one?", status="open", slug="beta")
    )
    before = {path: path.read_bytes() for path in (brief, request, gates)}
    kitchen.poll()
    assert sorted((event["event"], event["line"]) for event in kitchen.events()) == [
        ("gate", "gate alpha: in the brief?"),
        ("gate", "gate beta: a new one?"),
        ("gate answered", "gate alpha: gate 1 answered"),
        ("report", "report look: done"),
        ("result", "result alpha: done"),
        ("result", "result alpha: not done"),
        ("review", "review alpha: findings"),
        ("waiting", "waiting demo: 1 wait on user, 1 new (gate 2), 1 gone"),
    ]
    (review_event,) = kitchen.events("review")
    assert review_event["text"] == review.strip()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(kitchen.events()) == 8
    assert {path: path.read_bytes() for path in before} == before
    assert sorted(p.name for p in kitchen.home.iterdir()) == ["gates.md", "scouts", "tasks"]


def test_a_result_that_changes_goes_again_and_one_that_does_not_goes_once(kitchen):
    """The `Fixed:` line a crewmate adds to its last Result reaches a Chef with no home."""
    brief = kitchen.brief("alpha")
    kitchen.quiet()
    brief.write_text(brief.read_text() + RESULT)
    kitchen.poll()
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(kitchen.events("result")) == 1
    brief.write_text(brief.read_text() + "Fixed: none needed, a clean review\n")
    kitchen.poll(NOW + timedelta(minutes=6))
    kitchen.poll(NOW + timedelta(minutes=9))
    first, again = kitchen.events("result")
    assert first["line"] == again["line"] == "result alpha: done"
    assert again["text"].endswith("Fixed: none needed, a clean review")


def test_the_same_result_piped_twice_is_one_event(kitchen):
    lines = "Status: done\nLeft: none\n"
    assert kitchen.main("done", "alpha", stdin=lines) == (0, "queued\n")
    assert kitchen.main("done", "alpha", stdin=lines) == (0, "already sent\n")
    assert kitchen.main("done", "alpha", stdin=lines + "Fixed: abc\n") == (0, "queued\n")
    assert len(kitchen.events("result")) == 2


def test_a_gate_and_a_result_piped_to_jbus_are_queued_at_once(kitchen):
    lines = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")
    assert kitchen.main("gate", "alpha", stdin=lines) == (
        0,
        "asked: queued: question 1\nGate: question 1\n",
    )
    assert kitchen.main("done", "alpha", stdin="Status: done\nLeft: none\n") == (0, "queued\n")
    assert [(e["event"], e["line"], e["text"]) for e in kitchen.events()] == [
        ("gate", "gate alpha: question 1: which way?", lines.strip()),
        ("result", "result alpha: Status: done", "Status: done\nLeft: none"),
    ]


def test_a_gate_inside_a_result_does_not_end_the_result(kitchen):
    brief = kitchen.brief("alpha")
    kitchen.quiet()
    gate = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")
    result = RESULT.replace("Left: none\n", f"alpha: gate\n{gate}Left: none\n")
    brief.write_text(brief.read_text() + result)
    kitchen.set("merged.json", [kitchen.merged("alpha", 7, "a" * 40)])
    kitchen.poll()
    (sent,) = kitchen.events("result")
    (asked,) = kitchen.events("gate")
    (merged,) = kitchen.events("merged")
    assert sent["text"] == result.strip() == merged["text"]
    assert (asked["line"], asked["text"]) == ("gate alpha: which way?", gate.strip())


def test_a_gate_piped_to_jbus_and_written_in_the_brief_goes_once(kitchen):
    brief = kitchen.brief("alpha")
    kitchen.quiet()
    lines = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")
    assert (
        kitchen.main("gate", "alpha", stdin=lines)[1]
        == "asked: queued: question 1\nGate: question 1\n"
    )
    brief.write_text(brief.read_text() + RESULT + "alpha: gate\n" + lines)
    kitchen.poll()
    assert (
        kitchen.main("gate", "alpha", stdin=lines)[1]
        == "asked: already sent: question 1\nGate: question 1\n"
    )
    assert kitchen.lines("gate") == ["gate alpha: question 1: which way?"]


def test_a_scoped_homes_open_gate_is_one_event_that_names_its_home(kitchen):
    root, scoped = kitchen.home / "gates.md", kitchen.home / "quay" / "gates.md"
    scoped.parent.mkdir()
    kitchen.quiet()
    root.write_text(GATE.format(n=1, asked="which cup?", status="open", slug="alpha"))
    scoped.write_text(
        GATE.format(n=1, asked="which berth?", status="open", slug="home")
        + "\n"
        + GATE.format(n=2, asked="which cup?", status="open", slug="alpha")
    )
    kitchen.poll()
    assert sorted((one["slug"], one["line"]) for one in kitchen.events("gate")) == [
        ("alpha", "gate alpha in quay: which cup?"),
        ("alpha", "gate alpha: which cup?"),
        ("home", "gate home in quay: which berth?"),
    ]
    kitchen.poll(NOW + timedelta(minutes=3))
    assert len(kitchen.events("gate")) == 3


def test_a_scoped_gate_answered_later_is_one_event_and_one_answered_before_is_none(kitchen):
    scoped = kitchen.home / "quay" / "gates.md"
    scoped.parent.mkdir()
    old = GATE.format(n=1, asked="an old one?", status="answered 2026-10-01: yes", slug="home")
    scoped.write_text(old)
    kitchen.quiet()
    kitchen.poll()
    assert kitchen.events("gate answered") == []
    scoped.write_text(old + "\n" + GATE.format(n=2, asked="a new one?", status="open", slug="home"))
    kitchen.poll(NOW + timedelta(minutes=3))
    answered = GATE.format(n=2, asked="a new one?", status="answered 2026-10-23: no", slug="home")
    scoped.write_text(old + "\n" + answered)
    kitchen.poll(NOW + timedelta(minutes=6))
    kitchen.poll(NOW + timedelta(minutes=9))
    assert kitchen.lines("gate") == ["gate home in quay: a new one?"]
    assert kitchen.lines("gate answered") == ["gate home in quay: gate 2 answered"]


def test_a_gate_a_scoped_home_piped_to_jbus_and_wrote_in_its_file_goes_once(kitchen):
    scoped = kitchen.home / "quay" / "gates.md"
    scoped.parent.mkdir()
    kitchen.quiet()
    lines = GATE.format(n="<n>", asked="which berth?", status="open", slug="home")
    assert (
        kitchen.main("gate", "home", stdin=lines)[1]
        == "asked: queued: question 1\nGate: question 1\n"
    )
    scoped.write_text(lines.replace("<n>", "1"))
    kitchen.poll()
    assert kitchen.lines("gate") == ["gate home: question 1: which berth?"]


OLD = RESULT + "\n## Review\nVerdict: findings\nFindings:\n- warning a.py:1 off by one\n"
OLD_REPORT = "Thread: mcp:an-old-scout\n\n## Report\nStatus: done\n"


def _restore(kitchen):
    """Put back what a backup would: two briefs and a scout's request that no row of this
    project's queue names. Each of them finished long ago, and the Result of one brief has a gate
    left in it."""
    gate = GATE.format(n="<n>", asked="main fails make check at 198ea14?", status="open", slug="x")
    kitchen.brief("crew-testing", OLD.replace("Left: none\n", f"crew-testing: gate\n{gate}"))
    kitchen.brief("docs-sweep-2", OLD)
    kitchen.brief("check-speed", OLD_REPORT, kind="scouts")


def test_a_restored_tree_is_recorded_and_sends_nothing_old(kitchen):
    """A project that jbus knows is past its first pass. A backup then puts back briefs,
    requests, Results, Reviews, Reports and gates that jbus never saw. None of them is news."""
    kitchen.quiet()
    _restore(kitchen)
    kitchen.poll()
    kinds = ("gate", "result", "review", "report")
    assert [event["line"] for event in kitchen.events() if event["event"] in kinds] == []
    seen = json.loads((kitchen.state / "seen.json").read_text())
    assert "gate main fails make check at 198ea14?" in seen["tasks/crew-testing.md"]
    assert set(seen["scouts/check-speed.md"]) == {"## Report #1"}
    kitchen.poll(NOW + timedelta(minutes=3))
    assert [event["line"] for event in kitchen.events() if event["event"] in kinds] == []


def test_a_gate_a_live_thread_writes_after_a_restore_goes_once(kitchen):
    kitchen.quiet()
    assert kitchen.main("queue", "add", "live", "--priority", "1", stdin=complete("live"))[0] == 0
    _restore(kitchen)
    kitchen.poll()
    gate = GATE.format(n="<n>", asked="which way now?", status="open", slug="live")
    kitchen.brief("live", RESULT + "live: gate\n" + gate)
    kitchen.poll(NOW + timedelta(minutes=3))
    kitchen.poll(NOW + timedelta(minutes=6))
    kinds = ("gate", "result", "review", "report")
    assert [event["line"] for event in kitchen.events() if event["event"] in kinds] == [
        "gate live: which way now?",
        "result live: done",
    ]


def test_a_scout_a_home_launched_has_its_report_sent_though_no_row_names_it(kitchen):
    """A home writes `scouts/<slug>.md`, launches the scout from that file and adds the scout's
    `Thread:` line to it. No queue row names the file. A pass reads the request before the Report
    is in it. That is how jbus tells it apart from a request that a backup put back with its
    Report."""
    kitchen.quiet()
    request = kitchen.brief("look", "Thread: mcp:a-live-scout\n", kind="scouts")
    kitchen.poll()
    request.write_text(request.read_text() + "\n## Report\nStatus: done\n")
    _restore(kitchen)
    kitchen.poll(NOW + timedelta(minutes=3))
    kinds = ("gate", "result", "review", "report")
    assert [event["line"] for event in kitchen.events() if event["event"] in kinds] == [
        "report look: done"
    ]
