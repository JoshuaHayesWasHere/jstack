"""`merge.log` keeps each wait with its reason's code, and the view reads a pull request's step
from that code, not from the reason's text. A line logged before the codes has none, and the view
reads its step from the text as before.

The log here is what `jmerge` writes: each line made by `jmerge.lines`, one wait for every reason
`jmerge` gives, and the view reads it as `jbus view` serves it."""

import string

import pytest

from jbus import cancelled
from jbus.view import state
from jmerge import lines, ready
from view.scene import PULL, ago, et, row, tasks

PLAIN = {
    "fresh-check": ("check", "a fresh check is queued"),
    "unfetched": ("check", "main could not be fetched to see what its rebase kept"),
    "unknown": ("", "a reason nobody has printed before"),
}
"""The reasons `jmerge` writes as plain text, from outside `ready.Reason`, or wrote in the last
week of a log, each with its code, its step and a text of it."""


def _filled(template):
    fields = {name for _, name, _, _ in string.Formatter().parse(template) if name}
    return template.format(**dict.fromkeys(fields, "x1"))


def _waits():
    """Each code with the step it puts a pull request on and a reason that has it: every
    `Reason` of `ready` under the code its name gives, and every plain-text reason."""
    named = {
        name.lower().replace("_", "-"): (reason.step, _filled(reason))
        for name, reason in ready.reasons().items()
    }
    return named | PLAIN


def _logged(minutes, line):
    return f"{et(ago(minutes=minutes)).removesuffix(' ET')} {line}"


def test_each_wait_in_merge_log_has_its_code_and_the_view_reads_its_step_from_it(scene, served):
    """One pull request for each reason. Its first line is as a `merge.log` from before the codes
    has it, and its second as `jmerge` logs it now. The two are on the same step, and only the
    second has a code."""
    waits = _waits()
    numbers = {code: 100 + at for at, code in enumerate(waits)}
    log = []
    for code, (_, reason) in waits.items():
        said = lines.waits("wait", numbers[code], PULL.format(numbers[code]), reason)
        log += [_logged(30, said), _logged(20, lines.logged(said))]
    scene.merge_log(*log)
    scene.queue(
        [
            row(f"r-{code}", "pr", pr=f"#{numbers[code]}", why=f"wait: {reason}")
            for code, (_, reason) in waits.items()
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    read = {
        code: [(one["step"], one["code"]) for one in found[f"r-{code}"]["history"]]
        for code in waits
    }
    placed = {code: state.LANE.get(step, step) or "unknown" for code, (step, _) in waits.items()}
    assert read == {code: [(step, ""), (step, code)] for code, step in placed.items()}


def test_a_failed_check_and_one_still_running_have_their_own_texts_and_codes():
    """The one reason the scout found the view could not tell apart: `<check> has not passed`,
    once for a red check and for one queued or running alike. Each has its own text now, so a
    line with no code, as `jmerge` prints it, is read as the one it is."""
    pull = {
        "number": 7,
        "url": PULL.format(7),
        "title": "t",
        "branch": "b",
        "head": "c" * 40,
        "base": "main",
        "mergeable": "MERGEABLE",
        "waiting": ("check",),
        "files": (),
        "renamed": False,
        "changed": 0,
    }
    red = ready.short_on_github(ready.PullRequest(**pull, failed=("check",)))
    running = ready.short_on_github(ready.PullRequest(**pull))
    assert (red, running) == ("check has failed", "check has not passed")
    said = [lines.waits("wait", 7, PULL.format(7), why) for why in (red, running)]
    assert [lines.logged(line) for line in said] == [
        f"wait 7 {PULL.format(7)}: {red} [check-failed]",
        f"wait 7 {PULL.format(7)}: {running} [not-passed]",
    ]
    assert [lines.one(lines.logged(line)).code for line in said] == ["check-failed", "not-passed"]
    assert [ready.code_of(str(why)) for why in (red, running)] == ["check-failed", "not-passed"]
    assert lines.one(said[0]) == lines.Line("wait", 7, PULL.format(7), red)


def test_a_reason_whose_free_text_names_a_red_check_is_read_as_its_own_not_the_check():
    """A reason that starts with a field matches the start of any text, so it is tried last: a
    refused merge carries GitHub's error, which may say a check has failed, and is the refusal's."""
    said = ready.BASE_MERGE_REFUSED.format(
        base="main", tip="a" * 12, why=ready.CHECK_FAILED.format(check="the required check")
    )
    assert str(said).endswith("into it: the required check has failed")
    assert ready.code_of(str(said)) == ready.BASE_MERGE_REFUSED.code


RATE_LIMIT = "failed to get run: HTTP 403: API rate limit exceeded for installation ID 1"


@pytest.mark.parametrize("name", ["check", "macos"])
@pytest.mark.parametrize("minutes", [None, 30])
@pytest.mark.parametrize("error", ["", f": {RATE_LIMIT}"])
def test_a_check_github_did_not_run_again_is_on_the_check_step_with_its_reason(
    scene, served, name, minutes, error
):
    """The row's `why` that `cancelled` writes for a check GitHub would not run again, with or
    without GitHub's refusal after it, as the home hears it, is on the check step under its own
    code. The `why` itself leaves the refusal out, so the view does not show a rate limit as the
    reason it waits."""
    why = f"#11: {cancelled.unrun(name, minutes)}"
    reason = why.removeprefix("#11: ")
    assert RATE_LIMIT not in why
    assert ready.code_of(reason + error) == ready.CANCELLED_UNRUN.code
    scene.queue([row("oat-bowl", "pr", pr="#11", checks="failed", why=why + error)])
    found = tasks(served.json("/state.json?project=demo"))["oat-bowl"]
    assert found["step"] == "check"
    scene.queue([row("oat-bowl", "pr", pr="#11", checks="failed", why=why)])
    found = tasks(served.json("/state.json?project=demo"))["oat-bowl"]
    assert (found["step"], found["reason"]) == ("check", reason)


@pytest.mark.parametrize("name", ["check", "macos"])
@pytest.mark.parametrize("minutes", [[None, None], [30, 30], [12, 31]])
@pytest.mark.parametrize("cause", ["", "its timeout of 30 min"])
def test_a_check_cancelled_twice_is_on_the_check_step_with_its_reason(
    scene, served, name, minutes, cause
):
    """The row's `why` that `cancelled` writes for a check cancelled at two attempts, with or
    without how long each ran and what stopped it, is on the check step under its own code."""
    why = f"#11: {cancelled.twice(name, minutes, cause)}"
    reason = why.removeprefix("#11: ")
    assert ready.code_of(reason) == ready.CANCELLED_TWICE.code
    scene.queue([row("oat-bowl", "pr", pr="#11", checks="failed", why=why)])
    found = tasks(served.json("/state.json?project=demo"))["oat-bowl"]
    assert (found["step"], found["reason"]) == ("check", reason)


def test_a_pull_request_in_jmerges_batch_is_in_the_check_lane_not_unknown(scene, served):
    """#1574's row, as the pass wrote it from what `jmerge` printed of it on 2026-11-10: a member
    of jmerge's batch waits on CI's check of the batch, so it is in the lane of a pull request
    whose own check runs."""
    why = "wait: it is in jmerge's batch over main at eca6f811b913, whose check decides its merge"
    scene.queue([row("po-crew-owes-ends", "pr", pr="#1574", checks="passed", why=why)])
    found = tasks(served.json("/state.json?project=demo"))["po-crew-owes-ends"]
    assert found["step"] == "check"


def test_a_checked_wait_in_the_desk_checks_words_from_before_1715_is_in_the_result_lane(
    scene, served
):
    """#1718's row, as jbus's view read it on 2026-11-11: a stale Checked: wait `jmerge` wrote
    before #1715 reworded the desk check's words, beside the same wait in today's words. Both
    are in the result lane, not Unknown."""
    before = (
        "its last Checked: line is of 2340e1f7de54, and its patch changed after it: the crew's "
        "check block (features/crew/do-the-task.md), which runs `make check-fast PART=touched`, "
        "the lint, the touched tests and the repo-guards tests, and writes its line (a "
        "`PART=guards` line of an earlier head binds too), runs again at ba66f41642f6"
    )
    today = ready.CHECKED_STALE.format(at="2340e1f7de54", head="ba66f41642f6")
    scene.queue(
        [
            row("st-code-conforms", "pr", pr="#1718", why=f"wait: {before}"),
            row("st-code-today", "pr", pr="#1719", why=f"wait: {today}"),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    assert [found[slug]["step"] for slug in ("st-code-conforms", "st-code-today")] == [
        "result",
        "result",
    ]
