"""A `Review: after` brief's review hands its findings to one cleanup row: the reviewer runs
`jbus cleanup <brief>` and pipes what it prints into `jbus queue add cleanup-<slug>`, as the
pr-review skill's block does. Run as `tests/test_jbus_queue.py` runs: the real command
against the test kitchen's config and state."""

import pytest

from jbus import cleanup, queue
from test_jbus_kitchen import Kitchen

HEAD, MERGE = "a" * 40, "c" * 40
PULL = "https://example.test/pull/7"
FOUND = (
    "- warning src/a.py:12 the loop reads the list twice (bucket: Act on)\n"
    "- info src/b.py:3 a name says less than it could (bucket: Consider)\n"
    "- info src/c.py:1 not worth it (bucket: Noted)\n"
)


@pytest.fixture
def kitchen(tmp_path, monkeypatch):
    made = Kitchen(tmp_path, monkeypatch)
    yield made
    made.close()


def reviewed(kitchen, mode="after", verdict="findings"):
    """The brief as its reviewer leaves it: a Result naming the pull request, and a section."""
    listed = FOUND if verdict == "findings" else "- none\n"
    text = (
        f'# alpha: a task\nTask: "do it"\nPull request: open one when done\nReview: {mode}\n\n'
        f"## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\nReviewer: mcp:9\n\n"
        f"## Review\nBy: codex\nVerdict: {verdict}\nHead: {HEAD}\nFindings:\n{listed}"
    )
    path = kitchen.home / "tasks" / "alpha.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def handed(kitchen, path):
    """What the skill's block does: `jbus cleanup`, and on a brief, `jbus queue add`."""
    code, said = kitchen.main("--project", "demo", "cleanup", str(path))
    if code == 0:
        argv = ("--project", "demo", "queue", "add", "cleanup-alpha", "--priority", "50")
        added, why = kitchen.main(*argv, stdin=said)
        assert added == 0, why
    return code, said


def rows(kitchen):
    return [row for row in queue.load(kitchen.state) if row["slug"].startswith("cleanup-")]


def test_findings_on_an_after_brief_make_exactly_one_row_that_waits_for_the_go(
    kitchen, monkeypatch
):
    monkeypatch.setattr(cleanup, "_merge_commit", lambda url: MERGE if url == PULL else "")
    path = reviewed(kitchen)
    code, said = handed(kitchen, path)
    assert code == 0
    (row,) = rows(kitchen)
    assert (row["slug"], row["approved"]) == ("cleanup-alpha", "")
    stored = queue.brief_path(kitchen.state, "cleanup-alpha").read_text()
    assert "src/a.py:12" in stored and "src/b.py:3" in stored
    assert "src/c.py" not in stored
    assert f"{PULL}, merged as {MERGE}" in stored
    code, again = handed(kitchen, path)
    assert (code, again.strip()) == (1, cleanup.THERE.format(slug="cleanup-alpha"))
    assert len(rows(kitchen)) == 1


def test_an_open_pull_request_names_the_head_its_review_saw(kitchen, monkeypatch):
    monkeypatch.setattr(cleanup, "_merge_commit", lambda url: "")
    assert handed(kitchen, reviewed(kitchen))[0] == 0
    stored = queue.brief_path(kitchen.state, "cleanup-alpha").read_text()
    assert f"{PULL}, not merged when the review of {HEAD} was written" in stored


@pytest.mark.parametrize(
    ("mode", "verdict", "why"),
    [
        ("after", "clean", cleanup.CLEAN),
        ("review", "findings", cleanup.NOT_AFTER),
        ("none", "findings", cleanup.NOT_AFTER),
        ("after", "not run", cleanup.UNREVIEWED),
    ],
)
def test_a_clean_review_or_another_mode_makes_no_row(kitchen, mode, verdict, why):
    code, said = handed(kitchen, reviewed(kitchen, mode, verdict))
    assert (code, said.strip()) == (1, why)
    assert rows(kitchen) == []
