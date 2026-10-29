"""The reviewer of a `Review: after` brief puts the review's findings into one cleanup row. The
tests parse the pr-review skill's block out of `features/pr-review/after-the-review.md` and run
it as the reviewer does: `jbus cleanup <brief>`, piped into `jbus queue add cleanup-<slug>`. `uv
run --project ... jbus` is the real command from this checkout, over a made-up config and state.
`gh` gives the merge commit, or nothing."""

import json
import os
import re
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
    """`Reviewer` is the reviewer's machine. It has the home's brief, jbus's config and state, a
    `uv` that runs this checkout's `jbus`, and a `gh` that says the pull request merged, or is
    open."""

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

    def brief(self, mode="after", verdict="findings", home=""):
        listed = FOUND if verdict == "findings" else "- none\n"
        (self.tasks / "alpha.md").write_text(
            f'# alpha: a task\nTask: "do it"\nPull request: open one when done\n'
            f"Review: {mode}\n{home}\n"
            f"## Result\nStatus: done\nBranch: alpha   Pull request: {PULL}\n"
            "Reviewer: mcp:9\n\n"
            f"## Review\nBy: codex\nVerdict: {verdict}\nHead: {HEAD}\nFindings:\n{listed}"
            "Sent to: not sent, Review: after\n"
        )

    def run(self):
        """Run the skill's block after two lines that set the paths H and T, as the block at the
        top of the skill does, and return what the block prints."""
        (body,) = [one for one in blocks(SKILL.read_text(), "sh") if "jbus cleanup" in one]
        top = f'H="{self.home}/.local/state/home/demo"\nT="{REPO}/features/crew/templates"\n'
        env = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "JBUS_CONFIG_DIR": str(self.config),
            "JBUS_STATE_DIR": str(self.state.parent),
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
    said = reviewer.run()
    (row,) = reviewer.rows()
    assert (row["slug"], row["priority"], row["approved"]) == ("cleanup-alpha", 50, "")
    assert row["depends"] == ["alpha"], "the cleanup starts from a main that has its parent"
    assert "\n| cleanup-alpha | 50 | alpha |" in said, "the line jbus prints names what it waits on"
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    assert "src/a.py:12" in stored and "src/b.py:3" in stored
    assert "src/c.py" not in stored
    assert "- F1 src/a.py:12: the loop reads the list twice (Act on)\n" in stored
    assert f"{PULL}, merged as {MERGE}" in stored
    assert reviewer.run().strip() == cleanup.THERE.format(slug="cleanup-alpha")
    assert len(reviewer.rows()) == 1


@pytest.mark.parametrize("home", ["Home: flow\n", ""])
def test_the_cleanup_row_belongs_to_the_home_of_its_parent(reviewer, home):
    reviewer.merged(MERGE)
    reviewer.brief(home=home)
    reviewer.run()
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    said = [one + "\n" for one in stored.splitlines() if one.startswith("Home:")]
    assert said == ([home] if home else []), "its Result goes to the home that owns the work"


def test_a_parent_row_removed_from_the_queue_still_gets_its_cleanup_row(reviewer):
    reviewer.merged(MERGE)
    reviewer.brief()
    reviewer.state.mkdir(parents=True)
    queue.removed_path(reviewer.state).write_text(
        json.dumps({"alpha": {"at": "2026-10-23 10:00 EDT", "by": "user"}})
    )
    reviewer.run()
    (row,) = reviewer.rows()
    assert (row["slug"], row["depends"]) == ("cleanup-alpha", [])


def test_an_open_pull_request_names_the_head_its_review_saw(reviewer):
    reviewer.brief()
    reviewer.run()
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    assert f"{PULL}, not merged when the review of {HEAD} was written" in stored
    assert_open(stored)


def task_line(stored):
    (line,) = [one for one in stored.splitlines() if one.startswith("Task:")]
    return line


def assert_open(stored):
    """The row's `Task:` sentence of a pull request with no merge commit says it has not merged and
    that the row waits for the merge, and never says it merged."""
    line = task_line(stored)
    assert "has not merged" in line and "launches after it merges" in line
    assert set(re.findall(r"(\w+) merged\b", line)) == {"not"}, line


@pytest.mark.parametrize(
    ("mode", "verdict", "said"),
    [
        ("after", "clean", cleanup.CLEAN),
        ("after", "not run", cleanup.UNREVIEWED),
        ("review", "findings", cleanup.FIRST),
        ("none", "findings", cleanup.NO_REVIEW),
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
    """Write a `twice` brief. The crew answered its first review at the head where it pushed its
    fix. When `second` lists findings, the brief also has the second review of that head."""
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
    assert_open(stored)


def test_a_merged_twice_brief_says_it_merged_with_its_commit(reviewer):
    reviewer.merged(MERGE)
    twice(reviewer, SECOND)
    reviewer.run()
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    assert task_line(stored) == (
        "Task: alpha said `Review: twice`, so it merged once its second review was written, "
        "and that review's warning and error findings come here; its 2 info findings were "
        f"dropped. Pull request: {PULL}, merged as {MERGE}."
    )


def test_a_finding_with_no_repo_path_stays_out_of_where(reviewer):
    reviewer.merged(MERGE)
    twice(
        reviewer,
        SECOND + "- warning - Done when line 1 is met on one screen of three (bucket: Consider)\n",
    )
    reviewer.run()
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    assert "Done when line 1 is met on one screen of three" in stored
    (where,) = [one for one in stored.splitlines() if one.startswith("Where:")]
    assert where == "Where: `src/a.py`, `src/d.py`"


def test_a_second_review_of_info_findings_alone_or_clean_makes_no_row(reviewer):
    twice(reviewer, "".join(line for line in SECOND.splitlines(True) if line.startswith("- info")))
    assert reviewer.run().strip() == cleanup.NO_WARNING.format(kept="warning or error", info=2)
    twice(reviewer, "")
    assert reviewer.run().strip() == cleanup.NO_WARNING.format(kept="warning or error", info=0)
    assert reviewer.rows() == []


def test_the_first_review_of_a_twice_brief_files_nothing_and_goes_to_the_crew(reviewer):
    twice(reviewer)
    assert reviewer.run().strip() == cleanup.FIRST
    assert reviewer.rows() == []


SCOPED = (
    "- error src/a.py:40 the retry never stops (bucket: Consider)\n"
    "- warning src/d.py:7 a test asserts what the code computed (bucket: Act on)\n"
    "- warning src/e.py:2 a write is not undone on a crash (bucket: Act on) (risk: data)\n"
    "- info src/c.py:1 not worth it (bucket: Act on)\n"
)


def scoped(reviewer, second=SCOPED, slug="alpha", mode="review"):
    """Write a `review` brief whose crew answered its first review and pushed its fix, and whose
    fix has its scoped pass, which found `second`."""
    (reviewer.tasks / f"{slug}.md").write_text(
        f'# {slug}: a task\nTask: "do it"\nPull request: open one when done\nReview: {mode}\n\n'
        f"## Result\nStatus: done\nBranch: {slug}   Pull request: {PULL}\n"
        f"Reviewer: mcp:9 #1\nFinding F1: fixed, the loop\nScoped review: needed since {HEAD}, "
        f"the fix changed src/a.py\nFixed: {FIX}\nScoped reviewer: mcp:10, of {FIX}\n\n"
        f"## Review\nBy: codex #1\nVerdict: findings\nHead: {HEAD}\nFindings:\n{FOUND}"
        f"\n## Review\nBy: codex #1\nVerdict: findings\nScope: range-diff x..{HEAD} x..{FIX}\n"
        f"Head: {FIX}\nFindings:\n{second}"
    )


def test_the_second_review_of_a_review_brief_files_its_warnings_alone_as_a_small_row(reviewer):
    scoped(reviewer)
    reviewer.run()
    (row,) = reviewer.rows()
    assert (row["slug"], row["depends"]) == ("cleanup-alpha", ["alpha"])
    stored = queue.brief_path(reviewer.state, "cleanup-alpha").read_text()
    (done,) = [part for part in stored.split("Done when:\n")[1:]]
    listed = [one for one in done.splitlines() if one.startswith("- F")]
    assert listed == [
        "- F5 warning src/d.py:7: a test asserts what the code computed (Act on)",
        "- F6 warning src/e.py:2: a write is not undone on a crash (Act on) (risk: data)",
    ], "the error is its crewmate's, the info is dropped, and the first review's are done"
    assert "\nSize: S\n" in stored and "\nReview: cleanup\n" in stored
    assert "Where: `src/d.py`, `src/e.py`\n" in stored
    assert "its 1 info findings were dropped" in task_line(stored)


def test_a_second_review_of_a_review_brief_with_errors_alone_makes_no_row(reviewer):
    scoped(reviewer, SCOPED.splitlines(True)[0] + SCOPED.splitlines(True)[3])
    assert reviewer.run().strip() == cleanup.NO_WARNING.format(kept="warning", info=1)
    assert reviewer.rows() == []


@pytest.mark.parametrize(
    ("slug", "mode"), [("tidy", "cleanup"), ("cleanup-alpha", "review"), ("cleanup-beta", "twice")]
)
def test_a_cleanup_row_files_no_row_of_its_own_whatever_its_findings(reviewer, slug, mode):
    scoped(reviewer, slug=slug, mode=mode)
    done = subprocess.run(
        [sys.executable, "-m", "jbus", "cleanup", str(reviewer.tasks / f"{slug}.md")],
        env={**os.environ, "JBUS_CONFIG_DIR": str(reviewer.config)},
        capture_output=True,
        text=True,
    )
    assert (done.returncode, done.stdout.strip()) == (1, cleanup.OWN.format(slug=slug))
