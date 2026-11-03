"""`jmerge` keeps, for each pull request it merges, how long it waited once it was ready: from
the second its required checks passed at its head to the second its merge began, and the codes
that held it in between, one line each in `merge-waits.jsonl` (`jmerge.waits`).

The run tests drive the command against the fake `gh` and real origin of `test_home_merge`."""

import json
from datetime import UTC, datetime, timedelta

import pytest

import test_home_merge as merge
from jmerge import ready, waits
from jsettings import store


def passed(name, ago):
    """A check run of `name` that passed `ago` before now, as GitHub lists it."""
    ended = (datetime.now(UTC) - ago).replace(microsecond=0)
    return {
        **merge.run("SUCCESS", name),
        "startedAt": (ended - timedelta(minutes=5)).isoformat().replace("+00:00", "Z"),
        "completedAt": ended.isoformat().replace("+00:00", "Z"),
    }


def at(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def logged(merged):
    log = merged.home.state / waits.LOG
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def green(merged, check_ago, borders_ago):
    """GitHub lists the pull request with `check` and `borders` passed so long ago each."""
    check = passed("check", check_ago)
    merged.home.open_pull_request(merged.head, checks=(check, passed("borders", borders_ago)))
    return check


def test_a_pull_request_merged_on_the_run_that_first_sees_it_ready_waits_with_no_blocker(merged):
    check = green(merged, timedelta(seconds=4), timedelta(minutes=2))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")
    (line,) = logged(merged)
    assert line["number"] == 7 and line["head"] == merged.head
    assert at(line["ready"]) == at(check["completedAt"])
    assert line["ready_by"] == "check"
    assert line["blockers"] == {}
    assert line["at"] == line["began"]
    waited = (at(line["began"]) - at(line["ready"])).total_seconds()
    assert line["seconds"] == pytest.approx(waited, abs=0.002)
    assert 4 <= line["seconds"] < 60
    assert not store.read_dict(merged.home.state / waits.SPELLS)


def test_a_pull_request_that_waits_for_its_review_counts_from_ready_and_names_the_review(merged):
    """It opened long before it was ready: its wait starts when its last check passed."""
    check = green(merged, timedelta(seconds=2), timedelta(hours=3))
    (merged.home.tasks / "alpha.md").write_text(merge.brief())
    assert merged.run() == [f"wait 7 {merge.URL}: it has no review yet"]
    assert merged.run() == [f"wait 7 {merge.URL}: it has no review yet"]
    assert logged(merged) == []
    (merged.home.tasks / "alpha.md").write_text(merge.brief(merge.review("clean", merged.head)))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")
    (line,) = logged(merged)
    assert at(line["ready"]) == at(check["completedAt"])
    assert set(line["blockers"]) == {"no-review"}
    assert 0 < line["blockers"]["no-review"] <= line["seconds"] < 120
    assert [one[17:].endswith("[no-review]") for one in merged.log()] == [True, False]


def test_a_check_run_writes_no_wait(merged):
    green(merged, timedelta(seconds=2), timedelta(seconds=2))
    merged.run("--check")
    assert not (merged.home.state / waits.LOG).exists()
    assert not (merged.home.state / waits.SPELLS).exists()


T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def pull(head="a" * 40, ready_at=T0, waiting=()):
    return ready.PullRequest(
        7,
        merge.URL,
        "t",
        "alpha",
        head,
        "main",
        "MERGEABLE",
        waiting,
        (),
        False,
        1,
        passed_at=None if waiting else ready_at,
    )


def seconds(n):
    return T0 + timedelta(seconds=n)


def test_a_blocker_that_clears_and_comes_back_counts_only_the_seconds_it_held(tmp_path):
    spells = waits.Spells(tmp_path, run=True)
    spells.saw(pull(), "no-review", seconds(10))
    spells.saw(pull(), "main-red", seconds(30))
    spells.saw(pull(), "no-review", seconds(45))
    spells.saw(pull(), "no-review", seconds(50))
    wait = spells.merged(pull(), seconds(70))
    assert wait.seconds == 70
    assert wait.blockers == {"no-review": 20 + 25, "main-red": 15}
    assert sum(wait.blockers.values()) == 60


def test_a_new_head_or_a_check_run_again_starts_the_wait_over(tmp_path):
    spells = waits.Spells(tmp_path, run=True)
    spells.saw(pull(), "no-review", seconds(10))
    spells.saw(pull(waiting=("check",)), "not-passed", seconds(20))
    spells.saw(pull(ready_at=seconds(40)), "no-fixed", seconds(50))
    spells.saw(pull("b" * 40, ready_at=seconds(90)), "no-review", seconds(100))
    wait = spells.merged(pull("b" * 40, ready_at=seconds(90)), seconds(130))
    assert (wait.head, wait.ready, wait.seconds) == ("b" * 40, waits.stamp(seconds(90)), 40)
    assert wait.blockers == {"no-review": 30}


def test_a_ready_with_no_end_from_github_is_the_first_run_that_saw_it(tmp_path):
    spells = waits.Spells(tmp_path, run=True)
    unended = pull(ready_at=None)
    spells.saw(unended, "no-review", seconds(10))
    wait = spells.merged(unended, seconds(25))
    assert (wait.ready_by, wait.ready, wait.seconds) == ("run", waits.stamp(seconds(10)), 15)


def test_the_spells_of_closed_pull_requests_are_dropped(tmp_path):
    spells = waits.Spells(tmp_path, run=True)
    spells.saw(pull(), "no-review", seconds(10))
    spells.open_only({8})
    assert json.loads((tmp_path / waits.SPELLS).read_text()) == {}
