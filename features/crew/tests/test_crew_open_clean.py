"""The crew skill's block that a crewmate runs right before it opens its pull request, in "Do the
task": it says `open it` only on a head that merges cleanly into a fresh `origin/<base>`, and on
a conflict it rebases first, so no pull request is in conflict the moment it opens.

The replay is #1725's: its branch left main at 23f42940, main reached 9eabd172 (#1698) three hours
before it opened, and it opened in conflict on TellOnce's chart and the charts page. CI's checkout
is shallow and #1725's head is on no branch of main, so the replay rebuilds that shape: the same
files, the same two kinds of conflict, and a clone whose `origin/main` is still at the old base."""

import os
import subprocess
from pathlib import Path

from crew_helpers import PullRequest, block, git
from testing.layouts import assembled

CHART = "features/jbus/spec/TellOnce-statechart/chart.mmd"
PAGE = "features/home/docs/charts/index.html"
OTHER = "features/jbus/src/jbus/outbox.py"
RESOLVED = "stateDiagram-v2\n  state Told {\n    Once\n  }\n"
IDENTITY = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
}


class Replay:
    """A crewmate's worktree whose branch is pushed, and a main that moved under it since its
    clone last fetched."""

    def __init__(self, tmp_path, conflicts=True):
        self.tmp_path = tmp_path
        origin, self.main = tmp_path / "origin.git", tmp_path / "main"
        self.work = tmp_path / "trees" / "st-fix-tell-once"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(self.main))
        for path, text in (
            (CHART, "stateDiagram-v2\n  Told --> Sent\n"),
            (PAGE, "<p>charts</p>\n"),
        ):
            (self.main / path).parent.mkdir(parents=True, exist_ok=True)
            (self.main / path).write_text(text)
        (self.main / OTHER).parent.mkdir(parents=True, exist_ok=True)
        (self.main / OTHER).write_text("held = []\n")
        git(self.main, "add", ".")
        git(self.main, "commit", "-q", "-m", "23f42940")
        git(self.main, "push", "-q", "origin", "HEAD:main")
        git(self.main, "remote", "set-head", "origin", "main")
        self.base = git(self.main, "rev-parse", "HEAD")

        git(self.main, "worktree", "add", "-q", "-b", "st-fix-tell-once", str(self.work))
        self.git_dir = git(self.work, "rev-parse", "--absolute-git-dir")
        if conflicts:
            PullRequest.commit(self.work, CHART, "stateDiagram-v2\n  Told --> Once\n", "the fix")
            PullRequest.commit(self.work, PAGE, "<p>charts, TellOnce redrawn</p>\n", "the page")
        else:
            PullRequest.commit(self.work, OTHER, "held = []\nsent = set()\n", "the fix")
        git(self.work, "push", "-q", "-u", "origin", "st-fix-tell-once")
        self.pushed = git(self.work, "rev-parse", "HEAD")

        other = tmp_path / "other"
        git(tmp_path, "clone", "-q", str(origin), str(other))
        PullRequest.commit(other, CHART, "stateDiagram-v2\n  state Told {\n  }\n", "9eabd172")
        git(other, "rm", "-q", PAGE)
        git(other, "commit", "-q", "-m", "9eabd172, the page")
        git(other, "push", "-q", "origin", "HEAD:main")
        self.landed = git(other, "rev-parse", "HEAD")

    def run(self, heading, about, brief="# st-fix-tell-once\n"):
        script = block(heading, about).replace("<slug>", "st-fix-tell-once")
        script = script.replace("'<branch>'", "'main'")
        (self.tmp_path / "tasks").mkdir(exist_ok=True)
        (self.tmp_path / "tasks" / "st-fix-tell-once.md").write_text(brief)
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                "H": str(self.tmp_path),
                "T": str(assembled() / "templates"),
                **IDENTITY,
                "GIT_EDITOR": "true",
            },
        )
        return ran.stdout.splitlines()

    def before_it_opens(self, brief="# st-fix-tell-once\n"):
        return self.run("Do the task", "merge-tree", brief)

    def mergeable(self):
        """What GitHub's `mergeable` would say of the head on origin against origin's main."""
        head = git(self.main, "ls-remote", "origin", "refs/heads/st-fix-tell-once").split()[0]
        git(self.main, "fetch", "-q", "origin")
        merged = subprocess.run(
            ["git", "merge-tree", "--write-tree", "origin/main", head],
            cwd=self.main,
            capture_output=True,
        )
        return "MERGEABLE" if merged.returncode == 0 else "CONFLICTING"

    def resolve(self):
        """Resolve each stop as the crewmate would: the fix's state drawn into main's redrawn
        chart, and main's deletion of the page, then continue."""
        while self.rebasing():
            for path in git(self.work, "diff", "--name-only", "--diff-filter=U").splitlines():
                if path == PAGE:
                    git(self.work, "rm", "-q", path)
                else:
                    (self.work / path).write_text(RESOLVED)
                    git(self.work, "add", path)
            empty = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=self.work)
            go_on = "--skip" if empty.returncode == 0 else "--continue"
            subprocess.run(
                ["git", "-c", "core.editor=true", "rebase", go_on],
                cwd=self.work,
                capture_output=True,
                env={**os.environ, **IDENTITY},
            )

    def rebasing(self):
        return any(
            os.path.exists(os.path.join(self.git_dir, name))
            for name in ("rebase-merge", "rebase-apply")
        )


def test_1725_rebases_onto_todays_main_before_it_opens_and_then_opens_mergeable(tmp_path):
    replay = Replay(tmp_path)
    assert git(replay.work, "rev-parse", "origin/main") == replay.base
    assert replay.mergeable() == "CONFLICTING"

    said = replay.before_it_opens()
    assert said[0].startswith(
        f"not opened: the head conflicts with origin/main at {replay.landed[:12]}"
    )
    assert CHART in said[0] and PAGE in said[0]
    assert (
        said[1]
        == "the rebase stopped: resolve these as A conflict says, then git rebase --continue"
    )
    record = Path(replay.git_dir, "crew-before-rebase").read_text().split()
    assert record == [replay.pushed, "main", replay.pushed]
    kept = git(
        replay.work, "rev-parse", f"refs/jstack/pre-rebase/st-fix-tell-once/{replay.pushed[:12]}"
    )
    assert kept == replay.pushed

    replay.resolve()
    assert not replay.rebasing()
    assert git(replay.work, "merge-base", "--is-ancestor", replay.landed, "HEAD") == ""
    assert git(replay.work, "log", "--format=%s", "origin/main..HEAD") == "the fix"
    assert replay.before_it_opens() == [
        "a rebase is not pushed yet: prove it and push it as A conflict says, then run this again"
    ]
    pushed = replay.run("Stay on the pull request", "--force-with-lease")
    assert pushed[0].startswith(
        f"pushed {git(replay.work, 'rev-parse', 'HEAD')} over {replay.pushed}"
    )

    head = git(replay.work, "rev-parse", "HEAD")
    assert replay.before_it_opens() == [
        f"open it: {head[:12]} merges cleanly into origin/main at {replay.landed[:12]}"
    ]
    assert replay.mergeable() == "MERGEABLE"
    assert (replay.work / CHART).read_text() == RESOLVED


def test_a_head_that_merges_cleanly_over_a_moved_main_opens_with_no_rebase(tmp_path):
    replay = Replay(tmp_path, conflicts=False)
    assert replay.before_it_opens() == [
        f"open it: {replay.pushed[:12]} merges cleanly into origin/main at {replay.landed[:12]}"
    ]
    assert git(replay.work, "rev-parse", "HEAD") == replay.pushed
    assert not os.path.exists(os.path.join(replay.git_dir, "crew-before-rebase"))
    assert replay.mergeable() == "MERGEABLE"


def test_a_link_jbus_moved_onto_main_opens_with_no_rebase_until_its_head_holds_the_merge(tmp_path):
    """A link whose `Stacked on:` line says its base merged, as jbus writes it once it moved the
    link onto main, still holds its base's commits until jbus carries the merge into its head: a
    rebase onto main here would replay them, which "A conflict" refuses a link for."""
    replay = Replay(tmp_path)
    brief = f"# st-fix-tell-once\nStacked on: under under at {replay.landed}\n"
    assert replay.before_it_opens(brief) == [
        "open it: a link of a stack, jbus moves it onto its base's merge"
    ]
    assert git(replay.work, "rev-parse", "HEAD") == replay.pushed
    assert not os.path.exists(os.path.join(replay.git_dir, "crew-before-rebase"))
    assert git(replay.work, "for-each-ref", "refs/jstack") == ""
