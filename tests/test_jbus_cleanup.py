"""A `Review: after` brief's review hands its findings to one cleanup row. The pr-review
skill's block is run as the reviewer runs it, parsed out of
`features/pr-review/after-the-review.md`: `jbus cleanup <brief>`, piped into
`jbus queue add cleanup-<slug>`. `uv run --project ... jbus` is the real command from this
checkout, over a made-up config and state, and `gh` gives the merge commit, or nothing."""

import os
import subprocess
import sys

import pytest

from jbus import cleanup, queue
from skill_blocks import blocks
from testing.paths import REPO

SKILL = REPO / "features" / "pr-review" / "after-the-review.md"
HEAD, MERGE = "a" * 40, "c" * 40
PULL = "https://example.test/pull/7"
FOUND = (
    "- warning src/a.py:12 the loop reads the list twice (bucket: Act on)\n"
    "- info src/b.py:3 a name says less than it could (bucket: Consider)\n"
    "- info src/c.py:1 not worth it (bucket: Noted)\n"
)
CONFIG = (
    'server = "http://127.0.0.1:1"\n\n[[project]]\nname = "demo"\n'
    'checkout = "/somewhere/demo"\nprojectId = "p-demo"\n'
)


class Reviewer:
    """The reviewer's machine: the home's brief, jbus's config and state, a `uv` that runs
    this checkout's `jbus`, and a `gh` that says the pull request merged, or is open."""

    def __init__(self, tmp_path):
        self.home = tmp_path / "home"
        self.tasks = self.home / ".local/state/home/demo/tasks"
        self.config = tmp_path / "config"
        self.state = tmp_path / "state" / "demo"
        self.bin = tmp_path / "bin"
        for made in (self.tasks, self.config, self.bin):
            made.mkdir(parents=True)
        (self.config / "config.toml").write_text(CONFIG)
        (self.config / "config.toml").chmod(0o600)
        uv = self.bin / "uv"
        uv.write_text(
            '#!/bin/sh\nwhile [ "$1" != jbus ]; do shift; done\nshift\n'
            f'exec {sys.executable} -m jbus "$@"\n'
        )
        uv.chmod(0o755)
        self.merged("")

    def merged(self, commit):
        gh = self.bin / "gh"
        said = f'echo \'{{"mergeCommit": {{"oid": "{commit}"}}}}\'' if commit else "exit 1"
        gh.write_text(f"#!/bin/sh\n{said}\n")
        gh.chmod(0o755)

    def brief(self, mode="after", verdict="findings"):
        listed = FOUND if verdict == "findings" else "- none\n"
        (self.tasks / "alpha.md").write_text(
            f'# alpha: a task\nTask: "do it"\nPull request: open one when done\n'
            f"Review: {mode}\n\n"
            f"## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n"
            "Reviewer: mcp:9\n\n"
            f"## Review\nBy: codex\nVerdict: {verdict}\nHead: {HEAD}\nFindings:\n{listed}"
            "Sent to: not sent, Review: after\n"
        )

    def run(self):
        """The skill's block, with the block at the top that gives H and T."""
        (body,) = [one for one in blocks(SKILL.read_text(), "sh") if "jbus cleanup" in one]
        top = f'H="{self.home}/.local/state/home/demo"\nT="{REPO}/templates"\n'
        env = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "JBUS_CONFIG_DIR": str(self.config),
            "JBUS_STATE_DIR": str(self.state.parent),
            "PYTHONPATH": str(REPO / "src"),
        }
        done = subprocess.run(
            ["sh", "-c", top + body.replace("<slug>", "alpha")],
            cwd=self.home,
            env=env,
            capture_output=True,
            text=True,
        )
        assert done.returncode == 0, done.stderr
        return done.stdout

    def rows(self):
        if not self.state.is_dir():
            return []
        return [row for row in queue.load(self.state) if row["slug"].startswith("cleanup-")]


@pytest.fixture
def reviewer(tmp_path):
    return Reviewer(tmp_path)


def test_findings_on_an_after_brief_make_exactly_one_row_that_waits_for_the_go(reviewer):
    reviewer.merged(MERGE)
    reviewer.brief()
    reviewer.run()
    (row,) = reviewer.rows()
    assert (row["slug"], row["priority"], row["approved"]) == ("cleanup-alpha", 50, "")
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    assert "src/a.py:12" in stored and "src/b.py:3" in stored
    assert "src/c.py" not in stored
    assert "- F1 src/a.py:12: the loop reads the list twice (Act on)\n" in stored
    assert f"{PULL}, merged as {MERGE}" in stored
    assert reviewer.run().strip() == cleanup.THERE.format(slug="cleanup-alpha")
    assert len(reviewer.rows()) == 1


def test_an_open_pull_request_names_the_head_its_review_saw(reviewer):
    reviewer.brief()
    reviewer.run()
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    assert f"{PULL}, not merged when the review of {HEAD} was written" in stored


@pytest.mark.parametrize(
    ("mode", "verdict", "said"),
    [
        ("after", "clean", cleanup.CLEAN),
        ("after", "not run", cleanup.UNREVIEWED),
        ("review", "findings", "not after:"),
        ("none", "findings", "not after:"),
    ],
)
def test_a_clean_review_or_another_mode_makes_no_row(reviewer, mode, verdict, said):
    reviewer.brief(mode, verdict)
    assert reviewer.run().startswith(said)
    assert reviewer.rows() == []


FIX = "b" * 40
SECOND = (
    "- error src/a.py:40 the retry never stops (bucket: Act on)\n"
    "- warning src/d.py:7 a test asserts what the code computed (bucket: Noted)\n"
    "- info src/b.py:3 a name says less than it could (bucket: Consider)\n"
    "- info src/c.py:1 not worth it (bucket: Act on)\n"
)


def twice(reviewer, second=None):
    """A `twice` brief: its first review answered at the head the fix pushed, and the second
    review of that head, when `second` lists its findings."""
    text = (
        '# alpha: a task\nTask: "do it"\nPull request: open one when done\nReview: twice\n\n'
        f"## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n"
        "Reviewer: mcp:9 #1\nFinding F1: fixed, the loop\n"
        f"Fixed: {FIX}\nSecond reviewer: mcp:10 #1\n\n"
        f"## Review\nBy: codex #1\nVerdict: findings\nHead: {HEAD}\nFindings:\n{FOUND}"
        "Sent to: mcp:crew\n"
    )
    if second is not None:
        verdict = "findings" if second else "clean"
        text += (
            f"\n## Review\nBy: codex #1\nVerdict: {verdict}\nHead: {FIX}\nFindings:\n"
            f"{second or '- none'}\n"
        )
    (reviewer.tasks / "alpha.md").write_text(text)


def test_the_second_review_of_a_twice_brief_files_its_warnings_and_errors_as_one_row(reviewer):
    twice(reviewer, SECOND)
    reviewer.run()
    (row,) = reviewer.rows()
    assert (row["slug"], row["approved"]) == ("cleanup-alpha", "")
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    assert "src/a.py:40" in stored and "src/d.py:7" in stored
    assert "src/b.py" not in stored and "src/c.py" not in stored
    assert "src/a.py:12" not in stored, "the first review's findings were the crew's to fix"
    assert "- F4 error src/a.py:40: the retry never stops (Act on)\n" in stored
    assert "2 info findings" in stored
    assert f"{PULL}, not merged when the review of {FIX} was written" in stored


def test_a_second_review_of_info_findings_alone_or_clean_makes_no_row(reviewer):
    twice(reviewer, "".join(line for line in SECOND.splitlines(True) if line.startswith("- info")))
    assert reviewer.run().strip() == cleanup.NO_WARNING.format(info=2)
    twice(reviewer, "")
    assert reviewer.run().strip() == cleanup.NO_WARNING.format(info=0)
    assert reviewer.rows() == []


def test_the_first_review_of_a_twice_brief_files_nothing_and_goes_to_the_crew(reviewer):
    twice(reviewer)
    assert reviewer.run().strip() == cleanup.FIRST
    assert reviewer.rows() == []
