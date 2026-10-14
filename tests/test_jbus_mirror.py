"""`jbus.mirror` reads the briefs, the requests and the gates: each new section is one event,
a Result that changes goes again, and what is piped to jbus and written in the brief goes
once. Run as `tests/test_jbus_kitchen.py` runs: the real pass and the real command, against
the fakes.
"""

from datetime import timedelta

from test_jbus_kitchen import GATE, NOW, RESULT


def test_each_new_section_is_one_event_and_a_second_pass_sends_nothing(kitchen):
    brief = kitchen.brief("alpha")
    request = kitchen.brief("look", kind="scouts")
    gates = kitchen.home / "gates.md"
    gates.write_text(GATE.format(n=1, asked="an old one?", status="open", slug="alpha"))
    kitchen.quiet()
    review = "\n## Review\nVerdict: findings\nFindings:\n- high a.py:1 wrong\n"
    follow = "\n## Result, follow-up (2026-10-12, a steer)\nStatus: not done\n"
    noticed = "\nalpha: gate\n" + GATE.format(
        n="<n>", asked="in the brief?", status="open", slug="alpha"
    )
    brief.write_text(brief.read_text() + RESULT + review + follow + noticed)
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
    lines = "alpha: gate\n" + GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")
    assert kitchen.main("gate", "alpha", stdin=lines) == (0, "queued: question 1\n")
    assert kitchen.main("done", "alpha", stdin="Status: done\nLeft: none\n") == (0, "queued\n")
    assert [(e["event"], e["line"], e["text"]) for e in kitchen.events()] == [
        ("gate", "gate alpha: question 1: which way?", lines.strip()),
        ("result", "result alpha: Status: done", "Status: done\nLeft: none"),
    ]


def test_a_gate_inside_a_result_does_not_end_the_result(kitchen):
    brief = kitchen.brief("alpha")
    kitchen.quiet()
    gate = GATE.format(n="<n>", asked="which way?", status="open", slug="alpha")
    result = RESULT.replace("Left: none\n", f"Noticed:\nalpha: gate\n{gate}Left: none\n")
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
    assert kitchen.main("gate", "alpha", stdin=lines)[1] == "queued: question 1\n"
    brief.write_text(brief.read_text() + RESULT + "Noticed:\nalpha: gate\n" + lines)
    kitchen.poll()
    assert kitchen.main("gate", "alpha", stdin=lines)[1] == "already sent: question 1\n"
    assert kitchen.lines("gate") == ["gate alpha: question 1: which way?"]
