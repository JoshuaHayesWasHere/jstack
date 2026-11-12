"""One reader for each line a crew, a reviewer and jbus write into a brief as it runs: the
pull request on a Result's `Branch:` line, a `## Review` section's seat, the `Reviewer:` lines,
the `Stacked on:` line and the `Checked:` line. jbriefs, jmerge and jbus read them in Python and
the skills' shell blocks read them through `jbriefs line`, so the two give one answer.

Each brief here is a copy of a real one on which the Python and the skills' awk gave different
answers (the st-implicit-pkgs scout, finding 1), with its thread ids and home path replaced and
the private repo's brief cut to its lines (`fixtures/README.md`)."""

import contextlib
import io
from pathlib import Path

import pytest

from jbriefs import below, checked, cli, findings, parse, reviewers, stacked

BRIEFS = Path(__file__).parent / "fixtures" / "result_lines"


def brief(name):
    return (BRIEFS / f"{name}.md").read_text()


def line(what, *names):
    """What `jbriefs line` prints for the briefs, as a skill's block runs it."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert cli.main(["line", what, *(str(BRIEFS / f"{n}.md") for n in names)]) == 0
    return out.getvalue().splitlines()


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
    assert not reviewers.running(text)
    assert line("reviewing", "po-scout-model-doc") == ["no"]


def test_a_reviewer_none_line_is_no_reviewer():
    """qw-lock-test-race's crew wrote `Reviewer: none, <why>`: the crew's block read it as the
    review it had had, and the launcher's as none."""
    text = brief("qw-lock-test-race")
    assert reviewers.launched(text) == 0
    assert not reviewers.reviewed(text)
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


def test_several_briefs_print_one_line_each_and_with_path_its_path():
    assert line("status", "sb-pin-focus-build", "qw-lock-test-race") == ["done", "done"]
    said = line("status,pr,path", "sb-pin-focus-build", "qw-lock-test-race")
    assert said == [
        "done\thttps://github.com/JoshuaHayesWasHere/jstack/pull/787\t"
        f"{BRIEFS / 'sb-pin-focus-build.md'}",
        f"done\thttps://github.com/example/private/pull/255\t{BRIEFS / 'qw-lock-test-race.md'}",
    ]


def test_a_branch_line_with_no_pull_request_label_names_the_address_after_its_branch():
    pull = below.pull("Branch: x https://example.test/o/r/pull/986\n")
    assert (pull.url, pull.number) == ("https://example.test/o/r/pull/986", "986")
    assert below.pull("Branch: axe-workers (c42287d), no pull request yet\n").url == ""


def test_a_line_jbriefs_line_does_not_know_and_a_brief_it_cannot_read(tmp_path, capsys):
    with pytest.raises(SystemExit):
        cli.main(["line", "status,colour", str(BRIEFS / "qw-lock-test-race.md")])
    assert "no such line: colour" in capsys.readouterr().err
    gone = tmp_path / "gone.md"
    assert cli.main(["line", "pr", str(gone), str(BRIEFS / "qw-lock-test-race.md")]) == 1
    said = capsys.readouterr()
    assert said.out.splitlines() == ["https://github.com/example/private/pull/255"]
    assert f"{gone} cannot be read" in said.err


def test_a_brief_with_no_result_has_none_to_read():
    assert below.last_result("# alpha: a task\nTask: do it\n") == ""
    assert line("status,pr,reviewer,stacked", "qw-lock-test-race") == [
        "done\thttps://github.com/example/private/pull/255\tnone\tnone"
    ]


def test_a_two_step_checked_line_reads_as_its_guards():
    base, head = "b" * 40, "c" * 40
    two = (
        f"Checked: make check-fast BASE={base} PART=guards exit {{}} (took 9 s), then the "
        "import-reached remainder, where exit 124 is the short lane's time limit and passes: "
        f"make check-fast BASE={base} PART=rest exit {{}} at {head}"
    )
    guards = f"make check-fast BASE={base} PART=guards"
    assert checked.read(two.format(0, 124)) == checked.Checked(guards, "0", head)
    assert checked.read(two.format(0, 2)) == checked.Checked(guards, "2", head)
    assert checked.read(two.format(1, 0)) == checked.Checked(guards, "1", head)


SAW = "a" * 40
RESULT = "# alpha\n\n## Result\nStatus: done\n"


def section(by, scoped=False):
    scope = "Scope: range-diff a..b c..d\n" if scoped else ""
    return f"\n## Review\nBy: {by}\nVerdict: clean\n{scope}Head: {SAW}\n"


SONNET = "claudeAgent claude-sonnet-5-5 high"
SEATS = "Reviewer: mcp:a #1\nReviewer: mcp:b #2\n"


@pytest.mark.parametrize(
    ("brief", "running"),
    [
        (RESULT + "Reviewer: mcp:1\n", True),
        (RESULT + "Reviewer: mcp:1\nScoped reviewer: mcp:3\n" + section("x") + section("y"), False),
        (RESULT + "Reviewer: mcp:1\nSecond reviewer: mcp:2\n" + section("x"), True),
        (RESULT + SEATS + section(f"{SONNET} #1"), True),
        (RESULT + SEATS + section(f"{SONNET} #1") + section(f"{SONNET} #1"), True),
        (RESULT + SEATS + section(f"{SONNET} #1") + section(f"{SONNET} #2"), False),
        (
            RESULT
            + "Reviewer: mcp:x\n"
            + SEATS
            + section(f"{SONNET} #1")
            + section(f"{SONNET} #2"),
            False,
        ),
        (
            RESULT
            + SEATS
            + section(f"{SONNET} #1")
            + section(f"{SONNET} #2")
            + f"Scoped reviewer: mcp:s, of {SAW}\n"
            + section(f"{SONNET} #1"),
            True,
        ),
        (
            RESULT
            + SEATS
            + section(f"{SONNET} #1")
            + section(f"{SONNET} #2")
            + f"Scoped reviewer: mcp:s, of {SAW}\n"
            + section(f"{SONNET} #1", scoped=True),
            False,
        ),
        (
            RESULT
            + SEATS
            + section(f"{SONNET} #1")
            + section(f"{SONNET} #2")
            + "Reviewer: mcp:c #1\n",
            True,
        ),
        (
            RESULT
            + "Reviewer: mcp:1 #1\nSecond reviewer: mcp:2\n"
            + section(f"{SONNET} #1")
            + section("y"),
            False,
        ),
    ],
    ids=[
        "launched and unwritten",
        "a legacy scoped line waits for any section",
        "two legacy lines and one section",
        "a seat unwritten",
        "a seat that wrote twice stands for no other",
        "each seat wrote",
        "an unnumbered launch the seats replaced waits for nothing",
        "a scoped reviewer waits for a scoped section",
        "a scoped section answers it",
        "a seat launched again after its section waits for a new one",
        "an unnumbered second reviewer takes a section of no seat",
    ],
)
def test_a_review_runs_while_a_line_has_no_section_after_it(brief, running):
    assert reviewers.running(brief) is running
