"""A reviewer that stops before its review writes a `## Review` with `Verdict: not run` and a
`Head:` line (`jbriefs not-run`), so its seat closes: `reviewers.running` stops waiting on it,
and `jbriefs line reviewing` says no, which lets the crew rebase."""

from jbriefs import cli, reviewers

HEAD = "f" * 40
BY = "By: claudeAgent claude-sonnet-5-5 high #1"
REVIEWED = f"""# alpha: the task

## Result
Status: done
Reviewer: mcp:first #1

## Review
{BY}
Verdict: clean
Head: {"a" * 40}   Unchanged by the review: yes
Findings:
- none

## Result, follow-up (2026-11-11, the pull request opened after its review)
Status: done
"""


def written(tmp_path, text, by="", scope=""):
    brief = tmp_path / "alpha.md"
    brief.write_text(text)
    code = cli.main(["not-run", str(brief), HEAD, "it stopped", by, scope])
    return code, brief.read_text()


def reviewing(capsys, brief):
    capsys.readouterr()
    cli.main(["line", "reviewing", str(brief)])
    return capsys.readouterr().out.strip()


def test_a_scoped_reviewer_that_stops_closes_its_seat(tmp_path, capsys):
    text = REVIEWED + f"Scoped reviewer: mcp:scoped, of {HEAD}\n"
    assert reviewers.running(text)
    scope = f"Scope: range-diff {'1' * 40}..{'a' * 40} {'2' * 40}..{HEAD}"
    code, after = written(tmp_path, text, BY, scope)
    assert code == 0
    assert after.endswith(
        f"\n\n## Review\n{BY}\nVerdict: not run\n{scope}\nWhy: it stopped\n"
        f"Head: {HEAD}   Unchanged by the review: not checked, no review ran\n"
        "Sent to: not sent, no review ran\n"
    )
    assert not reviewers.running(after)
    assert reviewing(capsys, tmp_path / "alpha.md") == "no"


def test_a_first_reviewer_that_stops_closes_its_seat(tmp_path, capsys):
    text = "# alpha: the task\n\n## Result\nStatus: done\nReviewer: mcp:first #1"
    assert reviewers.running(text)
    code, after = written(tmp_path, text, BY)
    assert code == 0 and not reviewers.running(after)
    assert "\nReviewer: mcp:first #1\n\n## Review\n" in after
    assert reviewing(capsys, tmp_path / "alpha.md") == "no"


def test_the_same_stop_at_the_same_head_writes_one_section(tmp_path, capsys):
    text = REVIEWED + f"Scoped reviewer: mcp:scoped, of {HEAD}\n"
    _, once = written(tmp_path, text, BY, "Scope: range-diff a b")
    capsys.readouterr()
    code, twice = written(tmp_path, once, BY, "Scope: range-diff a b")
    assert code == 0 and twice == once
    assert capsys.readouterr().out.startswith("no section: the brief already ends")


def test_a_brief_that_is_not_there_gets_no_section(tmp_path, capsys):
    gone = tmp_path / "gone.md"
    assert cli.main(["not-run", str(gone), HEAD, "x", "", ""]) == 1
    assert capsys.readouterr().out.startswith("no section: there is no brief at")
    assert not gone.exists()
