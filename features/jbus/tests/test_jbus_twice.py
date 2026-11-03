"""A row whose required check fails at two heads is held, and the Chef is paged once
(`jbus.stall.twice`). Its crew is then told nothing more, at the second head or a third, until the
row is approved again. A head whose check ran on main's red tip is not counted.

Like `test_jbus_github.py`, the tests run the real pass against the fakes."""

import json

from test_jbus_github import failed, launched, passes, pull, sends
from test_jbus_queue import go, rows

__all__ = ["launched"]

A, B, C, D = ("a" * 40, "b" * 40, "c" * 40, "d" * 40)
RED = "9" * 40


def red_at(kitchen, head, job):
    kitchen.set("open.json", [pull(kitchen, [failed(job)], head=head)])


def told(kitchen):
    return [given["clientRequestId"] for given in sends(kitchen)]


def pages(kitchen):
    return [event for event in kitchen.events("condition") if "check failed twice" in event["line"]]


def test_two_failed_heads_hold_the_row_and_page_the_chef_once_and_a_third_head_sends_nothing(
    launched,
):
    red_at(launched, A, "11")
    passes(launched, 0)
    assert told(launched) == ["failed|alpha|aaaaaaaaaaaa"]
    assert not rows(launched)["alpha"].get("held")

    red_at(launched, B, "12")
    passes(launched, 3, 6)
    assert told(launched) == ["failed|alpha|aaaaaaaaaaaa"]
    assert rows(launched)["alpha"]["held"] is True
    assert rows(launched)["alpha"]["why"] == "check failed twice"
    (page,) = pages(launched)
    assert page["line"] == "condition alpha: check failed twice"
    for named in (
        "alpha",
        "#7",
        "aaaaaaaaaaaa: check failed (o/r job 11)",
        "bbbbbbbbbbbb: check failed (o/r job 12)",
    ):
        assert named in page["text"]

    red_at(launched, C, "13")
    passes(launched, 9, 12)
    assert told(launched) == ["failed|alpha|aaaaaaaaaaaa"]
    assert len(pages(launched)) == 1


def test_a_failure_on_main_s_red_tip_is_not_counted(launched):
    record = {"main": RED, "at": "2026-10-12T14:00:00+00:00", "check": "failed", "broken": RED}
    (launched.state / "main.json").write_text(json.dumps(record))
    red_at(launched, A, "11")
    passes(launched, 0)
    assert json.loads((launched.state / "fails.json").read_text())["alpha"]["red"] == [A]

    (launched.state / "main.json").unlink()
    red_at(launched, B, "12")
    passes(launched, 3)
    assert not rows(launched)["alpha"].get("held")
    assert not pages(launched)

    red_at(launched, C, "13")
    passes(launched, 6)
    assert rows(launched)["alpha"]["held"] is True
    (page,) = pages(launched)
    assert "bbbbbbbbbbbb" in page["text"] and "cccccccccccc" in page["text"]
    assert "aaaaaaaaaaaa" not in page["text"]


def test_an_approve_lifts_the_hold_and_the_count_starts_again(launched):
    red_at(launched, A, "11")
    passes(launched, 0)
    red_at(launched, B, "12")
    passes(launched, 3)
    assert rows(launched)["alpha"]["held"] is True

    assert go(launched, "alpha")[0] == 0
    passes(launched, 6)
    assert not rows(launched)["alpha"].get("held")
    assert "failed|alpha|bbbbbbbbbbbb" in told(launched)

    red_at(launched, C, "13")
    passes(launched, 9)
    assert "failed|alpha|cccccccccccc" not in told(launched)
    assert rows(launched)["alpha"]["held"] is True
    assert len(pages(launched)) == 2
    red_at(launched, D, "14")
    passes(launched, 12)
    assert "failed|alpha|dddddddddddd" not in told(launched)
