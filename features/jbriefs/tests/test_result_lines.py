"""One reader for each line a crew, a reviewer and jbus write into a brief as it runs: the
pull request on a Result's `Branch:` line, a `## Review` section's seat, the `Reviewer:` lines,
the `Stacked on:` line and the `Checked:` line. jbriefs, jmerge and jbus read them in Python and
the skills' shell blocks read them through `jbriefs line`, so the two give one answer.

Each brief here is a copy of a real one on which the Python and the skills' awk gave different
answers (the st-implicit-pkgs scout, finding 1), with its thread ids and home path replaced and
the private repo's brief cut to its lines (`fixtures/README.md`)."""

import subprocess
import sys
from pathlib import Path

import pytest

from jbriefs import below, checked, findings, parse, stacked

BRIEFS = Path(__file__).parent / "fixtures" / "result_lines"


def brief(name):
    return (BRIEFS / f"{name}.md").read_text()


def line(what, *names):
    """What `jbriefs line` prints for the briefs, as a skill's block runs it."""
    ran = subprocess.run(
        [sys.executable, "-m", "jbriefs", "line", what, *(str(BRIEFS / f"{n}.md") for n in names)],
        capture_output=True,
        text=True,
        check=True,
    )
    return ran.stdout.splitlines()


def test_a_merged_note_after_the_address_still_names_the_pull_request():
    """statechart-tmp-cleanup's follow-up writes `(merged)` after the address: the awk's `$(NF)`
    read that and found no pull request to settle on."""
    text = brief("statechart-tmp-cleanup")
    pull = below.pull(below.last_result(text))
    assert (pull.url, pull.number) == (
        "https://github.com/JoshuaHayesWasHere/jstack/pull/679",
        "679",
    )
    assert line("pr", "statechart-tmp-cleanup") == [pull.url]


def test_the_pull_request_is_the_branch_lines_not_an_earlier_line_that_names_one():
    """done-before-pr-reopen's `Done when:` says `Pull request: none` above its `Branch:` line,
    and jbriefs took that and showed no pull request."""
    text = brief("done-before-pr-reopen")
    result = parse.Result("Result", below.last_result(text))
    assert result.pull_request.url == "https://github.com/JoshuaHayesWasHere/jstack/pull/748"
    assert line("pr", "done-before-pr-reopen") == [result.pull_request.url]


def test_a_result_that_opens_after_its_review_or_has_no_branch_line():
    assert below.pull("## Result\nBranch: b   Pull request: after the review\n").after
    assert below.pull("## Result\nBranch: b   Pull request: none\n").url == ""
    assert below.pull("## Result\nStatus: done\n") is None


def test_a_bare_review_seat_fills_its_seat_and_no_review_is_running():
    """po-scout-model-doc's reviewer dropped the `By: ` label: jbriefs counted its seat, and
    the crew's `^By: .* #[0-9]+$` did not, so its rebase waited for a review that was written."""
    text = brief("po-scout-model-doc")
    assert [one.seat for one in findings.triage(text).sections] == [1]
    assert not findings.running(text)
    assert line("reviewing", "po-scout-model-doc") == ["no"]


def test_a_reviewer_none_line_is_no_reviewer():
    """qw-lock-test-race's crew wrote `Reviewer: none, <why>`: the crew's block read it as the
    review it had had, and the launcher's as none."""
    text = brief("qw-lock-test-race")
    assert findings.launched(text) == 0
    assert not findings.reviewed(text)
    assert line("reviewer,reviewed", "qw-lock-test-race") == ["none\tno"]


def test_a_stacked_on_line_not_in_its_shape_is_no_stack():
    """sb-pin-focus-build's head says `Stacked on: main at <sha>`, three words: jmerge read no
    stack and the crew's `$(4)` read the branch `at`."""
    text = brief("sb-pin-focus-build")
    assert stacked.said(text) == "main at 2ee0b300117f8b090692af1807b46619ea68b386"
    assert stacked.of(text) is None
    assert line("base,stacked", "sb-pin-focus-build") == ["none\tmalformed"]


def test_a_stacked_on_line_moved_onto_main_names_its_commit():
    text = brief("po-scout-model-doc")
    commit = "dc676a4cb82e9820b7a677075873d203b6206121"
    assert stacked.of(text) == stacked.Stacked("po-scout-request-model", "main", commit)
    assert line("base,stacked", "po-scout-model-doc") == [
        f"main\tpo-scout-request-model main at {commit}"
    ]


def test_a_checked_line_with_a_note_after_it_is_not_the_one_that_binds():
    """fl-browser-red-holds's last `Checked:` line has a note after its head: jbus read the
    note's commit and jmerge the line before. Both now read the line before."""
    text = brief("fl-browser-red-holds")
    said = checked.last(text)
    assert said == checked.Checked(
        "make check-fast BASE=origin/main", "0", "530519cd2c0e540fa6c3fb5fee0152def6247ca0"
    )


@pytest.mark.parametrize(
    ("name", "said"),
    [
        ("statechart-tmp-cleanup", "done"),
        ("sb-pin-focus-build", "done"),
        ("qw-lock-test-race", "done"),
    ],
)
def test_the_status_is_the_last_results(name, said):
    assert line("status", name) == [said]


def test_several_briefs_print_one_line_each_with_its_path():
    said = line("status,pr", "sb-pin-focus-build", "qw-lock-test-race")
    assert said == [
        "done\thttps://github.com/JoshuaHayesWasHere/jstack/pull/787\t"
        f"{BRIEFS / 'sb-pin-focus-build.md'}",
        f"done\thttps://github.com/example/private/pull/255\t{BRIEFS / 'qw-lock-test-race.md'}",
    ]


def test_a_branch_line_with_no_pull_request_label_names_the_address_after_its_branch():
    pull = below.pull("Branch: x https://example.test/o/r/pull/986\n")
    assert (pull.url, pull.number) == ("https://example.test/o/r/pull/986", "986")
    assert below.pull("Branch: axe-workers (c42287d), no pull request yet\n").url == ""
