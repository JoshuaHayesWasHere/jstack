"""A row whose required check fails at two heads is held, and the Chef is paged once
(`jbus.stall.twice`). Its crew is then told nothing more, at the second head or a third, until the
row is approved again. A head whose check ran on a red main, the main that GitHub merged the head
into as its failed job's log names it, is not counted, and one whose log GitHub does not give is
judged again on a later pass.

Like `test_jbus_github.py`, the tests run the real pass against the fakes."""

import json

from test_jbus_github import failed, launched, passes, pull, sends
from test_jbus_queue import go, rows

__all__ = ["launched"]

A, B, C, D = ("a" * 40, "b" * 40, "c" * 40, "d" * 40)
RED, GREEN = "9" * 40, "8" * 40


def checked(kitchen, **answers):
    """Keep main's check at each tip, as `jbus.mainmoved.main_check` keeps it in `checks.json`."""
    path = kitchen.state / "checks.json"
    kept = json.loads(path.read_text()) if path.exists() else {}
    path.write_text(json.dumps({**kept, **answers}))


def merged(head, main):
    """The lines of a job's log that say which merge of the head into main its check ran on."""
    return (
        f"2026-11-06T18:08:37.1689626Z HEAD is now at 10f4a11 Merge {head} into {main}\n"
        "2026-11-06T18:12:38.8704685Z FAILED features/x/test_x.py::test_x - AssertionError\n"
    )


def red_at(kitchen, head, job, main=GREEN):
    """The pull request's check fails at `head`, in a job whose log says it ran on GitHub's merge
    of the head into `main`, or names no merge where `main` is None."""
    checked(kitchen, **{GREEN: "green", RED: "failed"})
    path = kitchen.stub / "logs.json"
    logs = json.loads(path.read_text()) if path.exists() else {}
    if main is not None:
        kitchen.set("logs.json", {**logs, job: merged(head, main)})
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
    red_at(launched, A, "11", main=RED)
    passes(launched, 0)
    assert json.loads((launched.state / "fails.json").read_text())["alpha"]["red"] == [A]

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


def test_twice_counts_nothing_a_red_main_failed_though_the_head_s_base_is_before_the_red(launched):
    """The head's branch base is a green tip from before main went red, but GitHub's check runs on
    its merge into main, which was red: neither head is the row's failure, so nothing is held."""
    record = {"main": RED, "at": "2026-10-12T14:00:00+00:00", "check": "failed", "broken": RED}
    (launched.state / "main.json").write_text(json.dumps(record))
    launched.set(
        "compare.json", {f"{RED}...{A}": {"status": "behind"}, f"{RED}...{B}": {"status": "behind"}}
    )
    red_at(launched, A, "11", main=RED)
    passes(launched, 0)
    red_at(launched, B, "12", main=RED)
    passes(launched, 3, 6)
    kept = json.loads((launched.state / "fails.json").read_text())["alpha"]
    assert (kept["heads"], kept["red"]) == ({}, [A, B])
    assert not rows(launched)["alpha"].get("held")
    assert not pages(launched)


def test_twice_holds_no_row_for_the_1177_heads_whose_second_ran_on_main_s_red_tip(launched):
    """#1177 (2026-11-06): 2d578ec46fb1 failed on its merge into 7ada9da3da15, a green main, and
    9d4a47992fd3 on its merge into 90b4d4e8cd61, the red tip #1184 left (`main.json`'s `broken`).
    Both heads' branch base was 2718bff65365, from before the red. Only the first is counted."""
    first, second = (
        "2d578ec46fb10a6e164151c13a9a61f8b3a31417",
        "9d4a47992fd30de67b306adbcc601d425d84065f",
    )
    green, red = (
        "7ada9da3da15d60aec5979e2653b2770798c7af3",
        "90b4d4e8cd61f9da227d772b04f24788ec797515",
    )
    checked(launched, **{green: "green", red: "failed"})
    launched.set("compare.json", {f"{red}...{second}": {"status": "diverged"}})
    record = {
        "main": "743b95420017923af58809f1a8f0f1c6b029fb53",
        "at": "2026-11-06T18:12:42+00:00",
        "check": "pending",
        "broken": red,
        "green": green,
        "pending": ["743b95420017923af58809f1a8f0f1c6b029fb53"],
    }
    launched.set("logs.json", {"128052291743": merged(first, green)})
    launched.set("open.json", [pull(launched, [failed("128052291743")], head=first)])
    passes(launched, 0)
    (launched.state / "main.json").write_text(json.dumps(record))
    launched.set(
        "logs.json", {"128052291743": merged(first, green), "128064773586": merged(second, red)}
    )
    launched.set("open.json", [pull(launched, [failed("128064773586")], head=second)])
    passes(launched, 3, 6)
    kept = json.loads((launched.state / "fails.json").read_text())["alpha"]
    assert (list(kept["heads"]), kept["red"]) == ([first], [second])
    assert not rows(launched)["alpha"].get("held")
    assert not pages(launched)


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


def test_twice_judges_a_head_whose_log_github_does_not_give_again_on_a_later_pass(launched):
    red_at(launched, A, "11", main=None)
    passes(launched, 0)
    kept = json.loads((launched.state / "fails.json").read_text())["alpha"]
    assert (kept["heads"], kept["red"]) == ({}, [])
    assert not rows(launched)["alpha"].get("held")
    assert not pages(launched)

    red_at(launched, A, "11", main=RED)
    passes(launched, 3)
    assert json.loads((launched.state / "fails.json").read_text())["alpha"]["red"] == [A]
