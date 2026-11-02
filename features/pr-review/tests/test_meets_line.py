"""The review template's `Meets the brief:` line and the parser `jmerge` reads it with
(`jbriefs.meets`) have one shape: a line filled in from the template, each choice and each kind of
item, reads as the template means it, and `jbriefs --meets` prints what `jmerge` will do of it."""

import re
import subprocess
import sys

import pytest

from jbriefs import meets
from testing.paths import REPO

REVIEW = REPO / "features" / "pr-review" / "templates" / "review.md"
SAW = "a" * 40
DONE = ("the rule holds: a test", "the docs say it", "the check command passes")


def template():
    """The template's line and the items under it."""
    lines = REVIEW.read_text().splitlines()
    at = next(n for n, line in enumerate(lines) if line.startswith(meets.LABEL))
    items = []
    for line in lines[at + 1 :]:
        if not line.startswith("- "):
            break
        items.append(line)
    return lines[at], items


def filled(choice, met, items):
    """The template's line with `choice`, the yes or the no side of its `|`, filled with the
    brief's count, and its items filled with each `(kind, k)` of `items`."""
    line, kinds = template()
    sides = line.removeprefix(meets.LABEL).strip().split(" | ")
    side = sides[0 if choice == meets.YES else 1]
    side = side.replace("<m>", str(met)).replace("<n>", str(len(DONE)))
    shapes = {re.match(r"- (\S+) ", one)[1]: one for one in kinds}
    under = [
        re.sub(r"<[^<>]*>$", DONE[k - 1], shapes[kind].replace("<k>", str(k))) for kind, k in items
    ]
    return (f"{meets.LABEL} {side}", *under)


@pytest.mark.parametrize(
    ("choice", "met", "items", "said"),
    [
        (meets.YES, 3, [], meets.Meets(meets.YES, 3, 3)),
        (
            meets.YES,
            3,
            [(meets.WAITING, 3), (meets.AFTER_MERGE, 1)],
            meets.Meets(meets.YES, 3, 3, after_merge=(1,), waiting=(3,)),
        ),
        (
            meets.NO,
            1,
            [(meets.UNMET, 2), (meets.UNMET, 3)],
            meets.Meets(meets.NO, 1, 3, unmet=(2, 3)),
        ),
    ],
    ids=["yes", "yes, with lines that wait", "no"],
)
def test_a_line_filled_in_from_the_template_reads_as_it_means(choice, met, items, said):
    assert meets.parse(filled(choice, met, items)) == said


def test_jbriefs_meets_prints_what_jmerge_reads_of_a_review_from_the_template(tmp_path):
    line = "\n".join(filled(meets.NO, 2, [(meets.UNMET, 2)]))
    listed = "".join(f"- {one}\n" for one in DONE)
    brief = tmp_path / "alpha.md"
    brief.write_text(
        f"# alpha: a task\nDone when:\n{listed}Review: review\n\n## Result\nStatus: done\n"
        f"\n## Review\nBy: inherit #1\nVerdict: clean\nHead: {SAW}\n{line}\nFindings:\n- none\n"
    )
    ran = subprocess.run(
        [sys.executable, "-m", "jbriefs", "--meets", str(brief)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert ran.stdout == f"no 2 3 {SAW}\n"
