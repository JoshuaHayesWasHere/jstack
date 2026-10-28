"""What `jmerge` judged of each pull request in a pass: the lines it printed (`Said`), and the
step each line puts its pull request on (`step`).

`jbus.merge` runs `jmerge` and keeps its lines, and `jbus.watch` reads them. They are here, below
both, since `jbus.merge` sends through the outbox, and the outbox reads `jbus.watch`.
"""

from __future__ import annotations

from jmerge import ready
from jmerge.lines import one as parse

GONE = ("proof",)
"""The steps of reasons only an older `jmerge` wrote, which the view no longer draws: the Proof of
a guarded path, whose gate `jmerge` dropped."""


def step(said: str, code: str = "") -> str:
    """Return the step a pull request waits on, read from the last line `jmerge` printed about it
    (`<word>: <reason>`) and the reason's code where `merge.log` wrote one. A `hold` is on the
    `hold` step, and a `wait` is on the step of its code (`ready.step_of`). A line with no code,
    as `jmerge` prints it or as an older `merge.log` has it, takes the code its reason's text
    gives (`ready.code_of`). Return nothing for a line with no reason, for a reason no rule
    names, or for one on a step of `GONE`."""
    word, _, reason = said.partition(": ")
    if not reason:
        return ""
    if word == "hold":
        return "hold"
    found = ready.step_of(code or ready.code_of(reason))
    return "" if found in GONE else found


class Said(list[str]):
    """`Said` is the list of lines `jmerge` printed about pull requests in this pass, as it
    printed them.

    `failed` is true when `jmerge` did not run to its end. In that case, a pull request with no line
    is one that `jmerge` did not reach. It is not one that `jmerge` read and had nothing to say
    about.
    """

    failed = False

    def crews(self, numbers: set[int]) -> Said:
        """Return the lines as the user is to hear them. A hold of one of these pull requests
        is its crew's to lift for now, so its line becomes a `wait`. The line stays in the
        list. A pull request with no line counts as one that `jmerge` did not reach, and such
        a pull request keeps the hold it had."""
        mine = {text for text in self if (line := parse(text)) and line.number in numbers}
        kept = Said(
            "wait" + text[4:] if text in mine and text[:5] == "hold " else text for text in self
        )
        kept.failed = self.failed
        return kept
