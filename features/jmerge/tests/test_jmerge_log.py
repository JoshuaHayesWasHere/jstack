"""`jmerge` logs each line it prints in `merge.log`. On every pass it prints a line for each
pull request that waits or that it holds, so it logs such a line only when the line differs from
the last line logged for that pull request. It still prints every line, as before. The log keeps
a wait with its reason's code at its end, which the printed line does not have.

The tests run the command against the fake `gh` and real origin of `test_home_merge`."""

import json

import test_home_merge as merge


def test_a_wait_is_logged_once_and_again_when_its_reason_changes(merged):
    waits = f"wait 7 {merge.URL}: {merge.NOT_PASSED}"
    merged.home.open_pull_request(merged.head, checks=(merge.PASSED, merge.FAILED))
    assert merged.run() == [waits] and merged.run() == [waits]
    assert [line[17:] for line in merged.log()] == [f"{waits} [not-passed]"]
    last = merged.home.state / "merge.log.last"
    assert json.loads(last.read_text()) == {"7": f"{waits} [not-passed]"}
    merged.home.open_pull_request(merged.head)
    (merged.home.tasks / "alpha.md").write_text(merge.brief())
    unreviewed = f"wait 7 {merge.URL}: it has no review yet"
    assert merged.run() == [unreviewed] and merged.run() == [unreviewed]
    logged = [f"{waits} [not-passed]", f"{unreviewed} [no-review]"]
    assert [line[17:] for line in merged.log()] == logged
    (merged.home.tasks / "alpha.md").write_text(merge.brief(merge.review("clean", merged.head)))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")
    assert [line[17:] for line in merged.log()] == [*logged, said]


def test_a_red_check_and_a_running_one_print_apart_and_are_logged_with_their_own_codes(merged):
    """A check that failed and one still running print lines of their own, and the log keeps
    their codes: `check-failed` for the one whose latest run failed, `not-passed` for the other."""
    red = f"wait 7 {merge.URL}: {merge.CHECK_FAILED}"
    waits = f"wait 7 {merge.URL}: {merge.NOT_PASSED}"
    merged.home.open_pull_request(merged.head, checks=(merge.FAILED, merge.OTHER_PASSED))
    assert merged.run() == [red]
    merged.home.open_pull_request(merged.head, checks=(merge.RUNNING, merge.OTHER_PASSED))
    assert merged.run() == [waits]
    logged = [f"{red} [check-failed]", f"{waits} [not-passed]"]
    assert [line[17:] for line in merged.log()] == logged
