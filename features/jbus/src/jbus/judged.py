"""What `jmerge` judged of each pull request in a pass: the lines it printed (`Said`). The step
each line puts its pull request on is `jmerge.judgement.step`, which both read.

`jbus.merge` runs `jmerge` and keeps its lines, and `jbus.watch` reads them. They are here, below
both, since `jbus.merge` sends through the outbox, and the outbox reads `jbus.watch`.
"""

from __future__ import annotations

from jmerge.lines import one as parse


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
