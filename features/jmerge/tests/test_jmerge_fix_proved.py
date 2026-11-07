"""One review round: a fix pushed for a review's findings merges on its checks and its Result's
`Proved:` line, with no scoped review of it. A `Scoped review: needed since <head>` line holds the
pull request for that review only while no `Proved:` line holds at its head (`ready.proves`).
#1175 waited as `its fix is not reviewed` with a `Proved:` line of its head in its Result.

The tests run `jmerge --check` against the fake `gh` of `test_home_merge`, over briefs in the
shape #1175's Result has."""

import pytest

import test_home_merge as merge
from jmerge import ready

REVIEWED, PUSHED = merge.REVIEWED, merge.PUSHED
FINDING = (
    "- error a.py:1 the parts start 54 s after the run is created (principle: "
    "principle-prove-it-works) (bucket: Act on) (proof: `make time`, exit 1, 54 s)\n"
)
OWED = f"Scoped review: needed since {REVIEWED}, the review's Meets the brief line is no\n"


def reviewed(meets=""):
    return (
        "## Review\nBy: claudeAgent claude-sonnet-5-5 high #1\nVerdict: findings\n"
        f"Head: {REVIEWED}   Unchanged by the review: yes\n{meets}Findings:\n{FINDING}Dropped: 0\n"
    )


def proved(head_exit=0, at=PUSHED):
    return f"Proved: a_test.py base exit 1 at {'e' * 40}, head exit {head_exit} at {at}\n"


FIXED = f"Finding F1: fixed, the select step is cached `make time`\n{OWED}Fixed: {PUSHED}\n"


@pytest.fixture
def home(tmp_path):
    return merge.Home(tmp_path)


def judged(home, text, head=PUSHED):
    real = merge.pushed_on(home)
    (home.tasks / "alpha.md").write_text(real(text))
    home.open_pull_request(real(head))
    return home.ready(), real


def test_a_fix_whose_proved_line_holds_at_its_head_merges_with_no_scoped_review(home):
    said, real = judged(home, merge.brief(reviewed(), FIXED + proved()))
    assert said == [f"ready 7 {real(PUSHED)} alpha alpha"]


@pytest.mark.parametrize(
    "proof",
    [
        pytest.param("", id="no Proved line"),
        pytest.param(proved(head_exit=1), id="a Proved line that fails at the head"),
    ],
)
def test_a_fix_with_no_proved_line_that_holds_still_waits_for_its_scoped_review(home, proof):
    said, _ = judged(home, merge.brief(reviewed(), FIXED + proof))
    assert said == [f"wait 7 {merge.URL}: {ready.FIX_UNREVIEWED}"]


DONE = "Done when:\n- the parts start within 25 s\n- each test once\n- the lint runs beside\n"
UNMET = "Meets the brief: no, 2 of 3\n- unmet 1: the parts start within 25 s\n"
DECLINED = (
    "Finding F1: not fixed, the parts start 54 s after creation, because the select step "
    "waits on #1177 (`gh run view 42254151281 --json jobs`)\n"
    f"{OWED}"
    "Fixed: none needed, F1 is declined: its remedy is #1177\n"
)


def test_1175s_result_waits_on_its_unmet_done_when_line_not_on_a_review_of_a_fix(home):
    """#1175 pushed no fix: its `Proved:` line is of the head the review saw, and the review
    says `Done when` 1 is unmet. It waits on that line, and the scoped review the `no` owes is
    the way out (`ready.MEETS_NO`)."""
    text = merge.brief(reviewed(UNMET), DECLINED + proved(at=REVIEWED), DONE)
    said, real = judged(home, text, head=REVIEWED)
    why = ready.MEETS_NO.format(head=real(REVIEWED)[:12], met=2, count=3, lines="1")
    assert said == [f"wait 7 {merge.URL}: {why}"]
