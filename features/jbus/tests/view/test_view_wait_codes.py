"""`merge.log` keeps each wait with its reason's code, and the view reads a pull request's step
from that code, not from the reason's text. A line logged before the codes has none, and the view
reads its step from the text as before.

The log here is what `jmerge` writes: each line made by `jmerge.lines`, one wait for every reason
`jmerge` gives, and the view reads it as `jbus view` serves it."""

import string

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
    return template.format(**{name: "x1" for name in fields})


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
    placed = {code: step or "unknown" for code, (step, _) in waits.items()}
    assert read == {code: [(step, ""), (step, code)] for code, step in placed.items()}


def test_a_failed_check_and_one_still_running_have_their_own_texts_and_codes():
    """The one reason the scout found the view could not tell apart: `<check> has not passed`,
    once for a red check and for one queued or running alike. Each has its own text now, so a
    line with no code, as `jmerge` prints it, is read as the one it is."""
    pull = dict(
        number=7,
        url=PULL.format(7),
        title="t",
        branch="b",
        head="c" * 40,
        base="main",
        mergeable="MERGEABLE",
        waiting=("check",),
        files=(),
        renamed=False,
        changed=0,
    )
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
