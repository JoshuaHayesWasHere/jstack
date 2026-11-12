"""A row whose required check fails at two heads is held, and the Chef is paged once
(`jbus.stall.twice`). Its crew is then told nothing more, at the second head or a third, until the
row is approved again. A head whose check ran on a red main, the main that GitHub merged the head
into as its failed job's log names it, is not counted, and one whose log GitHub does not give is
judged again on a later pass.

The hold keeps the go it takes (`jbus.queue.hold`), and the pass that sees every required check
passed at the head puts that go back (`jbus.queue.lift`), unless the row was held again since or
its brief changed. A head that failed only at an infra step is not counted either, nor a merge of
main that failed something the head before it did not.

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


FETCH = "2026-11-09T10:00:05.0000000Z curl: (22) The requested URL returned error: 503\n"
LINT = (
    "2026-11-09T10:00:05.0000000Z features/x/README.md:3: more than one sentence, break it at "
    "sentence ends: One. Two.\n"
    "2026-11-09T10:00:05.0100000Z prose_lint.py: 1 new prose lines hold more than one sentence: "
    "one each\n"
)


def infra_at(kitchen, head, job, said="", step="Install zsh", shows=FETCH):
    """The pull request's check fails at `head`, at `step`, by default one that downloads a package
    and fails on a 503: GitHub names the failed step, and its log shows `shows` and names no
    failed test and, unless `said` does, no make target."""
    red_at(kitchen, head, job)
    logs = json.loads((kitchen.stub / "logs.json").read_text())
    log = (
        f"2026-11-09T10:00:00.0000000Z HEAD is now at 10f4a11 Merge {head} into {GREEN}\n"
        f"{shows}{said}"
        "2026-11-09T10:00:05.1000000Z ##[error]Process completed with exit code 1.\n"
    )
    kitchen.set("logs.json", {**logs, job: log})
    path = kitchen.stub / "jobs.json"
    jobs = json.loads(path.read_text()) if path.exists() else {}
    steps = [
        {"name": "Set up job", "conclusion": "success"},
        {"name": step, "conclusion": "failure"},
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


def test_a_failed_check_that_gives_no_job_beside_an_infra_step_counts(launched):
    """Each failed check must show its step: one whose link names no job may have failed at a
    test, so the head is the row's red."""
    status = {**failed(), "detailsUrl": "https://example.test/o/r/status"}
    for head, job, at in ((A, "11", (0,)), (B, "12", (3, 6))):
        infra_at(launched, head, job)
        launched.set("open.json", [pull(launched, [failed(job), status], head=head)])
        passes(launched, *at)
    assert fails(launched).get("infra", []) == []
    assert rows(launched)["alpha"]["held"] is True


def test_a_lint_step_is_no_infra_and_two_heads_that_failed_it_hold_the_row(launched):
    """check.yml's `prose lint` runs no test and no make target, and fails on the row's own
    prose: it is no infra step, since its log shows no download or network failure. Two heads
    that failed it hold the row; a head between them whose `Install zsh` failed on a 503 is kept
    apart and counted for nothing."""
    infra_at(launched, A, "11", step="prose lint", shows=LINT)
    passes(launched, 0)
    infra_at(launched, B, "12")
    passes(launched, 3)
    infra_at(launched, C, "13", step="prose lint", shows=LINT)
    passes(launched, 6, 9)
    kept = fails(launched)
    assert (list(kept["heads"]), kept["infra"]) == ([A, C], [B])
    assert rows(launched)["alpha"]["held"] is True
    assert len(pages(launched)) == 1


def step_run(command, *lines):
    """A step's own part of a job's log: GitHub opens it with the `##[group]Run` line that names
    its command."""
    out = [f"##[group]Run {command}", "##[endgroup]", *lines]
    return "".join(f"2026-11-09T10:00:0{i % 10}.0000000Z {line}\n" for i, line in enumerate(out))


RETRIED = step_run(
    "uv sync --locked",
    "curl: (56) Recv failure: Connection reset by peer",
    "warning: retrying the download of ruff (attempt 2 of 3)",
    "Installed 41 packages in 120ms",
)
QUOTES = step_run(
    "python3 features/writing/scripts/prose_lint.py HEAD^1",
    "features/x/README.md:3: more than one sentence, break it at sentence ends: The step failed "
    "on a connection reset or timed out. It counts for nothing.",
    "prose_lint.py: 1 new prose lines hold more than one sentence: one each",
)


def test_a_lint_step_is_no_infra_where_only_another_part_of_its_log_shows_a_fetch_failure(
    launched,
):
    """A failed step is judged by its own part of the job's log, from its `##[group]Run` line to
    the `##[error]` line that ends it. At each of two heads `prose lint` fails on the row's prose,
    which quotes "connection reset", after a passed `uv sync` retried a `curl: (56)`: neither sign
    is the lint step's fetch failure, so both heads count and hold the row. A head between them
    whose own `zsh` step failed on a `curl: (56)` is kept apart and counted for nothing."""
    infra_at(launched, A, "11", step="prose lint", shows=RETRIED + QUOTES)
    passes(launched, 0)
    zsh = step_run("mkdir -p zsh-debs", "curl: (56) Recv failure: Connection reset by peer")
    infra_at(launched, B, "12", step="zsh", shows=RETRIED + zsh)
    passes(launched, 3)
    infra_at(launched, C, "13", step="prose lint", shows=RETRIED + QUOTES)
    passes(launched, 6, 9)
    kept = fails(launched)
    assert (list(kept["heads"]), kept["infra"]) == ([A, C], [B])
    assert rows(launched)["alpha"]["held"] is True
    assert len(pages(launched)) == 1


TOLERATED = step_run(
    "tests=$(python3 scripts/select_tests.py --failed-on-main 30 "
    "~/.cache/jstack/failed-on-main.json)",
    "curl: (22) The requested URL returned error: 503",
    "##[error]Process completed with exit code 22.",
)
TRAILER = step_run(
    "PYTHONPATH=features/jmerge/src:features/jleak/src python3 scripts/no_ai_trailers.py",
    "##[error]AI co-author trailer: commit 5f16302 carries a Co-Authored-By trailer",
    "Drop each line above: a commit and a pull request carry no AI co-author trailer.",
)


def test_a_trailer_step_is_no_infra_where_a_tolerated_step_before_it_failed_on_a_503(launched):
    """check.yml's `failed on main` runs with `continue-on-error: true` and calls GitHub: its
    `curl: (22)` on a 503 ends with an `##[error]Process completed` line of its own, and the job
    goes on. The step that fails the job is the last one whose part ends in that line, here
    `no AI co-author trailer`, failed on the row's own commits. Two heads that failed it count
    and hold the row."""
    trailer = "no AI co-author trailer"
    infra_at(launched, A, "11", step=trailer, shows=TOLERATED + TRAILER)
    passes(launched, 0)
    infra_at(launched, B, "12", step=trailer, shows=TOLERATED + TRAILER)
    passes(launched, 3, 6)
    kept = fails(launched)
    assert (list(kept["heads"]), kept.get("infra", [])) == ([A, B], [])
    assert rows(launched)["alpha"]["held"] is True
    assert len(pages(launched)) == 1


GREEN_1720 = "03141ec1a67d" + "0" * 28
FIRST_1720, SECOND_1720 = ("c68d82f3425f" + "1" * 28, "580af5ac466e" + "2" * 28)
CAP = (
    "2026-11-12T03:10:00.0000000Z error a-cap-on-size-only-shrinks: features/jbus/src/jbus/"
    "work.py: has 802 lines, over 800: split it\n"
)
OVERVIEW = (
    "2026-11-12T03:40:00.0000000Z FAILED features/statechart/tests/test_statechart_overview.py"
    "::test_statechart_overview - AssertionError\n"
)


def made(kitchen, head, *parents):
    """GitHub's answer for the commit `head`: its parents, the first of them the branch's head
    before it, where `head` is a merge of main."""
    path = kitchen.stub / "commit-made.json"
    kept = json.loads(path.read_text()) if path.exists() else {}
    kitchen.set("commit-made.json", {**kept, head: {"parents": [{"sha": p} for p in parents]}})


def failing(kitchen, head, job, log):
    """The pull request's check fails at `head`, in a job whose log is `log`, on GREEN."""
    red_at(kitchen, head, job)
    logs = json.loads((kitchen.stub / "logs.json").read_text())
    merge = f"2026-11-12T03:00:00.0000000Z HEAD is now at 10f4a11 Merge {head} into {GREEN}\n"
    kitchen.set("logs.json", {**logs, job: merge + log})


def test_twice_holds_no_row_for_the_1720_heads_each_a_merge_of_main_that_brought_a_new_failure(
    launched,
):
    """#1720 (2026-11-11): 03141ec passed. c68d82, a merge of main, failed the size cap on
    work.py, which the pull request's +5 and #1724's +9 crossed together. 580af5, another merge of
    main, failed that cap and #1698's new overview test. Main moved under each, so neither is
    counted: both are kept under `moved`, the crew is told each to fix, and nothing is held."""
    green_at(launched, GREEN_1720)
    passes(launched, 0)
    made(launched, FIRST_1720, GREEN_1720, "e" * 40)
    failing(launched, FIRST_1720, "130937656772", CAP)
    said = launched.poll(NOW + timedelta(minutes=3))
    made(launched, SECOND_1720, FIRST_1720, "f" * 40)
    failing(launched, SECOND_1720, "130941258618", CAP + OVERVIEW)
    said += launched.poll(NOW + timedelta(minutes=6)) + launched.poll(NOW + timedelta(minutes=9))
    kept = fails(launched)
    assert (kept["heads"], kept["moved"]) == ({}, [FIRST_1720, SECOND_1720])
    assert not rows(launched)["alpha"].get("held")
    assert not pages(launched)
    assert {f"failed|alpha|{FIRST_1720[:12]}", f"failed|alpha|{SECOND_1720[:12]}"} <= set(
        told(launched)
    )
    moved = [line for line in said if "main moved under it" in line]
    assert [line.split(" at ")[1][:12] for line in moved] == [FIRST_1720[:12], SECOND_1720[:12]]
    assert "failed a-cap-on-size-only-shrinks features/jbus/src/jbus/work.py, which" in moved[0]
    assert all(line.endswith("main moved under it, not counted") for line in moved)


def test_twice_holds_a_row_whose_own_commits_fail_at_two_heads_beside_a_merge_of_main(launched):
    """A crew commit that fails is counted. A merge of main after it that fails nothing new is
    counted too, and holds the row: main's move brought no failure, so the red is the row's."""
    green_at(launched, GREEN_1720)
    passes(launched, 0)
    made(launched, A, GREEN_1720)
    failing(launched, A, "11", OVERVIEW)
    passes(launched, 3)
    made(launched, B, A, "e" * 40)
    failing(launched, B, "12", OVERVIEW)
    passes(launched, 6, 9)
    kept = fails(launched)
    assert (list(kept["heads"]), kept.get("moved", [])) == ([A, B], [])
    assert rows(launched)["alpha"]["held"] is True
    assert told(launched) == ["failed|alpha|aaaaaaaaaaaa"]
    assert len(pages(launched)) == 1


def test_twice_holds_a_row_whose_crew_commits_fail_at_two_heads(launched):
    """Two heads the crew made, each failing, hold the row, even where the second failure is new."""
    made(launched, A, GREEN_1720)
    failing(launched, A, "11", CAP)
    passes(launched, 0)
    made(launched, B, A)
    failing(launched, B, "12", CAP + OVERVIEW)
    passes(launched, 3, 6)
    assert list(fails(launched)["heads"]) == [A, B]
    assert rows(launched)["alpha"]["held"] is True
    assert len(pages(launched)) == 1


def test_twice_holds_a_row_whose_merges_bring_in_a_branch_that_is_not_on_main(launched):
    """A merge whose second parent is not on the main its check ran on is a merge of another
    branch, not of main: main did not move under it, so each head that fails is counted."""
    green_at(launched, GREEN_1720)
    passes(launched, 0)
    launched.set(
        "compare.json",
        {
            f"{'e' * 40}...{GREEN}": {"status": "diverged"},
            f"{'f' * 40}...{GREEN}": {"status": "behind"},
        },
    )
    made(launched, FIRST_1720, GREEN_1720, "e" * 40)
    failing(launched, FIRST_1720, "130937656772", CAP)
    passes(launched, 3)
    made(launched, SECOND_1720, FIRST_1720, "f" * 40)
    failing(launched, SECOND_1720, "130941258618", CAP + OVERVIEW)
    passes(launched, 6, 9)
    kept = fails(launched)
    assert (set(kept["heads"]), kept.get("moved", [])) == ({FIRST_1720, SECOND_1720}, [])
    assert rows(launched)["alpha"]["held"] is True
    assert len(pages(launched)) == 1
