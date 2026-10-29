"""After a pull request's first review, its errors and warnings are fixed in it. A `Review: review`
brief answers its first review as before, and pushes its fix. The review after that, the scoped
pass of the fix, routes each finding by the severity it wrote, whatever its bucket or tag: an
error or a warning waits on its answer by id and a push, and an info is dropped. No finding goes
to another row. A brief that still says `after` is read as `review`. The tests drive it through
`ready.short_of`, the function `jmerge` calls before a merge, and through `jbriefs --findings
--left`, the crew's count."""

import subprocess
import sys

import pytest

import jsettings
from jbriefs import findings
from jmerge import ready

HEAD, FIX, AGAIN = "a" * 40, "b" * 40, "c" * 40
PULL = "https://example.test/pull/7"
FIRST = "warning a.py:3 the loop reads the list twice (principle: none) (bucket: Act on)"
ERROR = "error a.py:40 the retry never stops (principle: none) (bucket: Consider)"
WARNING = "warning c.py:7 a test asserts what the code computed (principle: none) (bucket: Act on)"
RISKY = WARNING.replace("c.py:7", "d.py:2") + " (risk: data)"
INFO = "info b.py:9 a name says less than it could (principle: none) (bucket: Act on)"


def brief(result="", mode="review"):
    return (
        f'# alpha: a task\nTask: "do it"\nPull request: open one when done\nReview: {mode}\n\n'
        f"## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n"
        f"Reviewer: mcp:9 #1\n{result}"
    )


def review(head, found, scope=""):
    verdict = "findings" if found else "clean"
    listed = "".join(f"- {one}\n" for one in found) or "- none\n"
    scoped = f"Scope: range-diff {scope}\n" if scope else ""
    return (
        f"\n## Review\nBy: claudeAgent claude-sonnet-5-5 high #1\nVerdict: {verdict}\n{scoped}"
        f"Head: {head}\nFindings:\n{listed}"
    )


def fixed(second, answers=""):
    """A `review` brief whose first review the crew answered and fixed at FIX, and whose fix has
    its scoped pass, which found `second`. `answers` is what the crew wrote after that pass."""
    result = (
        f"Finding F1: fixed, the loop\nScoped review: needed since {HEAD}, the fix changed a.py\n"
        f"Fixed: {FIX}\nScoped reviewer: mcp:10, of {FIX}\n{answers}"
    )
    return brief(result) + review(HEAD, (FIRST,)) + review(FIX, second, f"x..{HEAD} x..{FIX}")


def left(tmp_path, text):
    path = tmp_path / "alpha.md"
    path.write_text(text)
    ran = subprocess.run(
        [sys.executable, "-m", "jbriefs", "--findings", str(path), "--left"],
        capture_output=True,
        text=True,
        check=True,
    )
    return ran.stdout.strip()


def test_a_second_review_with_errors_and_warnings_waits_on_both(tmp_path):
    text = fixed((ERROR, WARNING, INFO))
    assert ready.short_of(text, FIX) == ready.NOT_PUSHED
    assert left(tmp_path, text) == "not yet: 2 of 3 findings have no Finding: line: F2, F3"
    pushed = fixed((ERROR, WARNING, INFO), f"Fixed: {AGAIN}\n")
    assert ready.short_of(pushed, AGAIN) == ready.UNANSWERED.format(ids="F2, F3")
    one = fixed((ERROR, WARNING, INFO), f"Finding F2: fixed, the retry\nFixed: {AGAIN}\n")
    assert ready.short_of(one, AGAIN) == ready.UNANSWERED.format(ids="F3")
    answered = one.replace("Fixed: ", "Finding F3: fixed, the test\nFixed: ")
    assert ready.short_of(answered, AGAIN) == ""
    assert ready.declines(answered, user=jsettings.DEFAULTS) == ("", "")
    routes = {one.id: one.route for one in findings.triage(answered).findings}
    assert routes == {
        "F1": findings.HOLDS,
        "F2": findings.HOLDS,
        "F3": findings.HOLDS,
        "F4": findings.DROPPED,
    }


def test_a_second_review_of_infos_alone_owes_no_fix_push_and_merges(tmp_path):
    text = fixed((INFO,))
    assert ready.short_of(text, FIX) == ""
    assert left(tmp_path, text).startswith("write nothing:")
    assert ready.short_of(fixed(()), FIX) == ""


@pytest.mark.parametrize("found", [WARNING, RISKY])
def test_a_second_reviews_warning_holds_the_merge_whatever_its_bucket_or_tag(found):
    text = fixed((found,))
    assert ready.short_of(text, FIX) == ready.NOT_PUSHED
    (one,) = [one for one in findings.triage(text).findings if one.lead.head == FIX]
    assert (one.bucket, one.route) == ("Act on", findings.HOLDS)


def test_the_first_review_still_goes_to_the_crew_whatever_its_severity():
    text = brief() + review(HEAD, (FIRST, INFO))
    assert ready.short_of(text, HEAD) == ready.NO_FIXED
    held = brief(f"Fixed: {FIX}\n") + review(HEAD, (FIRST, INFO))
    assert ready.short_of(held, FIX) == ready.UNANSWERED.format(ids="F1, F2")


def test_a_seat_that_writes_its_first_review_late_is_still_a_first_review():
    late = review(FIX, (WARNING,)).replace("#1", "#2")
    text = brief(f"Reviewer: mcp:11 #2\nFinding F1: fixed, the loop\nFixed: {FIX}\n")
    text += review(HEAD, (FIRST,)) + late
    assert ready.short_of(text, FIX) == ready.NOT_PUSHED
    assert [one.route for one in findings.triage(text).findings] == [findings.HOLDS] * 2


@pytest.mark.parametrize("mode", ["after", "cleanup"])
def test_a_brief_that_still_says_an_old_mode_is_read_as_review(mode):
    assert ready.short_of(brief(mode=mode), HEAD) == ready.NO_REVIEW
    assert ready.short_of(brief(mode=mode) + review(HEAD, (FIRST,)), HEAD) == ready.NO_FIXED
    assert not ready.asks_no_ruling(brief(mode=mode))


@pytest.mark.parametrize(
    "text",
    [
        brief() + review(HEAD, (FIRST, INFO)),
        brief("Finding F1: fixed, the loop\nFinding F2: not fixed, the name, because b.py:9\n")
        + review(HEAD, (FIRST, INFO)),
        brief("Finding F1: not fixed, the loop, because a.py:4\n") + review(HEAD, (FIRST,)),
        brief() + review(HEAD, ()),
        fixed((WARNING, INFO)),
        fixed((ERROR,), "Finding F2: fixed, the retry\n"),
        fixed((ERROR,), "Finding F2: not fixed, the retry, because a.py:41 stops it\n"),
        fixed((INFO,)),
        fixed((WARNING,), "Finding F2: fixed, the test\n"),
    ],
)
def test_the_fixed_line_the_crew_is_asked_for_is_the_one_jmerge_writes(text):
    said = findings.triage(text)
    shape = findings.fixed_shape(said)
    line = findings.left(said)
    if shape is None:
        assert line.split(":")[0] in ("wait", "not yet", "write nothing")
    else:
        pushed, why = shape
        assert why, "a Fixed: line always says why"
        named = "<the head you pushed>, " if pushed else "none needed, <reason>: "
        assert line == f"write Fixed: {named}{why}"


def test_a_clean_late_first_review_beside_an_infos_only_pass_owes_nothing(tmp_path):
    late = review(FIX, ()).replace("#1", "#2")
    text = fixed((INFO,)).replace(
        "Reviewer: mcp:9 #1\n", "Reviewer: mcp:9 #1\nReviewer: mcp:11 #2\n"
    )
    text += late
    assert ready.short_of(text, FIX) == ""
    assert left(tmp_path, text).startswith("write nothing:")
