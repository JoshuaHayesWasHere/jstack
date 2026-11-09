"""A row whose required check fails at two heads is held, and the Chef is paged once
(`jbus.stall.twice`). Its crew is then told nothing more, at the second head or a third, until the
row is approved again. A head whose check ran on a red main, the main that GitHub merged the head
into as its failed job's log names it, is not counted, and one whose log GitHub does not give is
judged again on a later pass.

Like `test_jbus_github.py`, the tests run the real pass against the fakes."""

import json
from datetime import timedelta

import pytest

from test_jbus_github import failed, launched, passes, pull, sends
from test_jbus_kitchen import NOW
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


TEST = "features/x/test_x.py::test_x"


def red_elsewhere(kitchen, branches):
    """`jbus ci`'s ledger: `TEST` failed an hour ago on each of `branches`, with no runner fault in
    the log and no red main to blame."""
    at = (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    job = {
        "event": "pull_request",
        "kind": "local",
        "conclusion": "failure",
        "steps": 3,
        "created": at,
        "started": at,
        "completed": at,
        "sha": "e" * 40,
        "tests": [TEST],
        "signs": [],
        "attempt": 1,
        "name": "check",
    }
    jobs = [{**job, "run": at, "job": 900 + at, "branch": one} for at, one in enumerate(branches)]
    kitchen.state.mkdir(parents=True, exist_ok=True)
    (kitchen.state / "ci.jsonl").write_text("".join(json.dumps(one) + "\n" for one in jobs))


@pytest.mark.parametrize(
    ("branches", "held"),
    [(("beta", "gamma"), False), (("beta",), True), (("alpha", "beta"), True)],
    ids=["shared-with-two-branches", "one-other-branch", "its-own-branch"],
)
def test_twice_counts_a_red_only_where_its_failed_tests_are_not_a_flake_of_two_other_branches(
    launched, branches, held
):
    """2026-11-07: #1219 and #1220 were held for a clock-bound test that failed the same way on
    #1218, #1219 and #1220. A head whose failed tests all failed on two other branches in the
    window is a flake by `jbus ci`'s rule and is not counted; a test that failed on one other
    branch alone, or on the row's own, is the pull request's red, and two of them hold it."""
    red_elsewhere(launched, branches)
    red_at(launched, A, "11")
    passes(launched, 0)
    red_at(launched, B, "12")
    passes(launched, 3, 6)
    assert bool(rows(launched)["alpha"].get("held")) is held
    assert len(pages(launched)) == int(held)


def test_twice_counts_a_shared_red_whose_log_also_counts_an_error_it_names_no_test_of(launched):
    """The head's log names only `TEST`, a flake of two other branches, but its summary counts an
    error no test id names, as a collection error is: what failed is not all shared, so two such
    heads hold the row."""
    red_elsewhere(launched, ("beta", "gamma"))
    error = "ERROR features/x/test_y.py - ImportError\n= 1 failed, 1 error in 2.0s =\n"
    for head, job, at in ((A, "11", (0,)), (B, "12", (3, 6))):
        red_at(launched, head, job)
        logs = json.loads((launched.stub / "logs.json").read_text())
        launched.set("logs.json", {**logs, job: logs[job] + error})
        passes(launched, *at)
    assert rows(launched)["alpha"]["held"] is True
    assert len(pages(launched)) == 1


GO = ("approved", "approval", "brief_sha")


def green_at(kitchen, head, job="21"):
    """The pull request's required check passes at `head`."""
    passed = {**failed(job), "conclusion": "SUCCESS"}
    kitchen.set("open.json", [pull(kitchen, [passed], head=head)])


def held_twice(kitchen):
    """Fail the row's check at two heads, so that `twice` holds it, and return the go it had."""
    had = {column: rows(kitchen)["alpha"][column] for column in GO}
    red_at(kitchen, A, "11")
    passes(kitchen, 0)
    red_at(kitchen, B, "12")
    passes(kitchen, 3)
    assert rows(kitchen)["alpha"]["held"] is True
    assert not rows(kitchen)["alpha"]["approved"]
    return had


def fails(kitchen):
    return json.loads((kitchen.state / "fails.json").read_text())["alpha"]


def test_a_held_row_lifts_itself_once_its_required_check_passes_and_its_count_starts_again(
    launched,
):
    """2026-11-09: each hold waited for an approve, 23.9 row-hours of it after the check was
    green again. The pass that sees every required check passed at the head puts back the go the
    hold took, with no approve from anyone, and the count starts from none: one more red head is
    told to the crew and holds nothing."""
    had = held_twice(launched)
    green_at(launched, C)
    passes(launched, 6)
    row = rows(launched)["alpha"]
    assert not row.get("held") and "hold" not in row
    assert {column: row[column] for column in GO} == had
    assert (fails(launched).get("heads") or {}) == {}
    assert not fails(launched).get("held_at")

    red_at(launched, D, "14")
    passes(launched, 9)
    assert "failed|alpha|dddddddddddd" in told(launched)
    assert not rows(launched)["alpha"].get("held")
    assert len(pages(launched)) == 1


def test_a_row_somebody_else_held_since_stays_held_on_a_green_head(launched):
    held_twice(launched)
    assert launched.main("queue", "hold", "alpha")[0] == 0
    green_at(launched, C)
    passes(launched, 6)
    assert rows(launched)["alpha"]["held"] is True
    assert not rows(launched)["alpha"]["approved"]


def test_a_row_whose_brief_changed_since_its_go_stays_held_on_a_green_head(launched):
    held_twice(launched)
    stored = launched.state / "briefs" / "alpha.md"
    stored.write_text(stored.read_text() + "\nAlso: one more thing to do.\n")
    green_at(launched, C)
    passes(launched, 6)
    assert rows(launched)["alpha"]["held"] is True
    assert not rows(launched)["alpha"]["approved"]


def infra_at(kitchen, head, job, said=""):
    """The pull request's check fails at `head`, at a step that downloads a package: GitHub names
    the failed step, and its log names no failed test and, unless `said` does, no make target."""
    red_at(kitchen, head, job)
    logs = json.loads((kitchen.stub / "logs.json").read_text())
    log = (
        f"2026-11-09T10:00:00.0000000Z HEAD is now at 10f4a11 Merge {head} into {GREEN}\n"
        "2026-11-09T10:00:05.0000000Z curl: (22) The requested URL returned error: 503\n"
        f"{said}"
        "2026-11-09T10:00:05.1000000Z ##[error]Process completed with exit code 22.\n"
    )
    kitchen.set("logs.json", {**logs, job: log})
    path = kitchen.stub / "jobs.json"
    jobs = json.loads(path.read_text()) if path.exists() else {}
    steps = [
        {"name": "Set up job", "conclusion": "success"},
        {"name": "Install zsh", "conclusion": "failure"},
        {"name": "make check", "conclusion": "skipped"},
    ]
    kitchen.set(
        "jobs.json", {**jobs, job: {"status": "completed", "run_attempt": 1, "steps": steps}}
    )


def job_reads(kitchen, job):
    return [line for line in kitchen.log("gh") if line.endswith(f"/actions/jobs/{job}")]


def test_a_head_that_failed_only_an_infra_step_is_kept_apart_and_counted_for_nothing(launched):
    """13 of the 50 heads counted by 2026-11-09 failed only a shared test or an infra step. A
    head whose failed job failed at a step whose log names no failed test and no make target is
    kept apart, as a red main's is, and two of them hold nothing. GitHub is asked for each job's
    step once, however many passes judge the head."""
    infra_at(launched, A, "11")
    passes(launched, 0)
    infra_at(launched, B, "12")
    passes(launched, 3, 6)
    kept = fails(launched)
    assert (kept["heads"], kept["infra"]) == ({}, [A, B])
    assert not rows(launched)["alpha"].get("held")
    assert not pages(launched)
    assert len(job_reads(launched, "11")) == len(job_reads(launched, "12")) == 1

    red_at(launched, C, "13")
    passes(launched, 9)
    assert list(fails(launched)["heads"]) == [C]
    assert not rows(launched)["alpha"].get("held")


def test_a_failed_step_whose_log_names_a_make_target_is_no_infra_and_counts(launched):
    target = "2026-11-09T10:00:05.0500000Z make: *** [check-fast] Error 2\n"
    infra_at(launched, A, "11", target)
    passes(launched, 0)
    infra_at(launched, B, "12", target)
    passes(launched, 3, 6)
    assert fails(launched).get("infra", []) == []
    assert rows(launched)["alpha"]["held"] is True
