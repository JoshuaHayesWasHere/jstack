"""`jmerge` merges a pull request only once the brief's last `Checked:` line says the desk's
guards passed at its head, and holds it on a missing line, a failed one, a 124 and a line of a
head whose patch changed since, as `jmerge.cli.Repo.judged` asks the rule after the `Proved:` line.
The tests run `jmerge` against the fake `gh` and real origin of `test_home_merge`.
test_jmerge_ready_checked.py drives the rule itself, `ready.short_on_checked`, through each way a
line falls short."""

import pytest

import test_home_merge as merge
from jmerge import ready
from test_jmerge_ready_checked import checked


@pytest.fixture
def merged(tmp_path):
    made = merge.Merged(merge.Home(tmp_path), tmp_path)
    made.home.desk = False
    return made


def briefed(merged, lines):
    text = merge.brief(merge.review("clean", merged.head), lines)
    (merged.home.tasks / "alpha.md").write_text(text)


def test_a_pull_request_whose_guards_passed_at_its_head_merges(merged):
    briefed(merged, checked(head=merged.head))
    (said,) = merged.run()
    assert said.startswith("merged 7 alpha ")


@pytest.mark.parametrize(
    ("line", "why"),
    [
        pytest.param("", lambda m: ready.CHECKED_MISSING.format(head=m.head[:12]), id="missing"),
        pytest.param(
            checked(1, "{head}"),
            lambda m: ready.CHECKED_FAILED.format(exit=1, at=m.head[:12], head=m.head[:12]),
            id="exit 1",
        ),
        pytest.param(
            checked(124, "{head}"),
            lambda m: ready.CHECKED_CUT.format(at=m.head[:12], head=m.head[:12]),
            id="exit 124",
        ),
        pytest.param(
            checked(0, "{start}"),
            lambda m: ready.CHECKED_STALE.format(at=m.start[:12], head=m.head[:12]),
            id="stale",
        ),
    ],
)
def test_a_pull_request_whose_guards_did_not_pass_at_its_head_waits(merged, line, why):
    """The stale line is of main's own commit, whose patch is not the head's, as the line of a
    head before a fix for a review's finding is."""
    briefed(merged, line.format(head=merged.head, start=merged.start))
    (said,) = merged.run()
    assert said == f"wait 7 {merge.URL}: {why(merged)}"
    assert merged.untouched()
