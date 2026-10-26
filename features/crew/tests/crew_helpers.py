"""What the tests of the crew skill share: its sections, the `sh` block under a heading, and
the pull requests and briefs that the tests run the blocks over."""

import json
import os
import re
import shlex
import subprocess
import textwrap
from pathlib import Path

from jmerge import rangediff, ready
from test_home_thread import as_read
from testing.paths import REPO

SKILL = REPO / "features" / "crew" / "SKILL.md"


FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)


def sections():
    found, name = {}, None
    for line in as_read(SKILL).splitlines():
        if line.startswith("## "):
            name = line[3:]
            found[name] = []
        elif name:
            found[name].append(line)
    return {name: "\n".join(lines) for name, lines in found.items()}


def block(heading, about):
    """The one `sh` block under `heading` that contains `about`, as an agent reads it."""
    (found,) = [text for text in FENCED.findall(sections()[heading]) if about in text]
    return textwrap.dedent(found)


BRIEF = """\
# alpha: a task
Task: "do it"
Decisions:
- A brief that only talks about `Review: none` or a `## Review` section still gets a review.
Pull request: open one when done

## Result
Status: done
Branch: alpha   Pull request: https://example.test/pull/1
"""


def said(tmp_path, heading, about, brief, notes=None, cwd=None):
    """What one of the skill's blocks prints for a brief, and for the repo's notes if there are
    any."""
    (tmp_path / "tasks").mkdir(exist_ok=True)
    (tmp_path / "tasks" / "alpha.md").write_text(brief)
    if notes is not None:
        (tmp_path / "notes.md").write_text(notes)
    ran = subprocess.run(
        ["sh", "-c", block(heading, about).replace("<slug>", "alpha")],
        capture_output=True,
        text=True,
        env={**os.environ, "H": str(tmp_path), "T": str(REPO / "features" / "crew" / "templates")},
        cwd=cwd,
        check=True,
    )
    return ran.stdout.splitlines()


def with_field(line):
    """The brief with a `Review:` line of its own, where the home writes it."""
    return BRIEF.replace("\n## Result", f"{line}\n\n## Result")


def reviewed(findings, endings=""):
    """The brief once a reviewer has written its section and the crewmate has written its
    `Finding:` lines."""
    listed = "".join(f"- {finding}\n" for finding in findings) or "none\n"
    review = f"\n## Review\nVerdict: findings\nFindings:\n{listed}Dropped: 0\nSent to: mcp:1\n"
    return BRIEF + endings + review


TWO = ["warning a.py:3 it runs twice", "info b.py the file as a whole"]


class Fix:
    """A crewmate's worktree at the head that a review saw, then at the head that the crewmate
    pushed with its fix."""

    def __init__(
        self,
        tmp_path,
        fix,
        findings=("warning a.py:3 it runs twice",),
        task=("a.py", "b.py"),
        opened=False,
    ):
        self.state = tmp_path / "state"
        self.work = tmp_path / "work"
        (self.state / "tasks").mkdir(parents=True)
        self.work.mkdir()
        git(self.work, "init", "-q", "-b", "a-task")
        self.start = ""
        if opened:
            self.start = self.commit("start")
            git(self.work, "update-ref", "refs/remotes/origin/main", self.start)
            git(self.work, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        for name in task:
            (self.work / name).parent.mkdir(parents=True, exist_ok=True)
            (self.work / name).write_text("the task\n")
        self.saw = self.commit("the task")
        for name in fix:
            (self.work / name).parent.mkdir(parents=True, exist_ok=True)
            (self.work / name).write_text("the fix\n")
        self.fixed = self.commit("the fix") if fix else self.saw
        self.findings = findings
        self.review = self.reviewed(self.saw)

    def reviewed(self, head):
        listed = "".join(f"- {finding}\n" for finding in self.findings)
        return (
            f"\n## Review\nVerdict: findings\nHead: {head}   Unchanged by the review: yes\n"
            f"Findings:\n{listed}Dropped: 0\nSent to: mcp:1\n"
        )

    def commit(self, message):
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "--allow-empty", "-m", message)
        return git(self.work, "rev-parse", "HEAD")

    def says(self, result, reviews=None, shell="sh"):
        """What the block prints for a Result's lines and the reviews written after it."""
        brief = BRIEF + result + (self.review if reviews is None else reviews)
        (self.state / "tasks" / "alpha.md").write_text(brief)
        told = {"H": str(self.state), "T": str(REPO / "features" / "crew" / "templates")}
        ran = subprocess.run(
            [shell, "-c", block("The review", "Second pass:").replace("<slug>", "alpha")],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={**os.environ, **told},
            check=True,
        )
        return ran.stdout.splitlines()


HAD = "had: the review of the fix is written, and this head is owed none"


def opened(tmp_path, path, fix=None):
    """A pull request that changes `path` and b.py, with one finding in `path`, and a fix."""
    fix = [path] if fix is None else fix
    return Fix(tmp_path, fix, [f"warning {path}:3 it"], (path, "b.py"), opened=True)


GUARDED = "skills/crew/SKILL.md"


def held_open(go):
    """A check that runs until the test touches `go`, for a minute at most, so a test that
    fails before the touch leaves no detached check behind it."""
    return f"n=0; while ! [ -f {go} ] && [ $n -lt 600 ]; do sleep 0.1; n=$((n + 1)); done"


GH = """\
#!/bin/sh
case "$1 $2" in
    "pr view") cat "$STUB/view.json" 2> /dev/null ;;
    "api rate_limit")
        cat "$STUB/rate-limit.json" 2> /dev/null && exit
        full='{"limit": 5000, "used": 0, "remaining": 5000, "reset": 1791824400}'
        printf '{"resources": {"core": %s, "graphql": %s}}\n' "$full" "$full" ;;
    "run rerun")
        echo "$*" >> "$STUB/calls"
        [ ! -e "$STUB/no-rerun" ] ;;
    "api repos/someone/repo/actions/jobs/"*)
        cat "$STUB/job-${2##*/}.json" 2> /dev/null && exit
        echo '{"message":"Not Found","status":"404"}'
        exit 1 ;;
    *) exit 64 ;;
esac
"""


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    ran = subprocess.run(
        ["git", *identity, *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return ran.stdout.strip()


class PullRequest:
    """A crewmate's worktree with its branch pushed, and a default branch that has moved since."""

    def __init__(self, tmp_path, mergeable, main_edits):
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "gh").write_text(GH)
        (self.stub / "gh").chmod(0o755)
        if mergeable:
            view = f'{{"baseRefName": "main", "mergeable": "{mergeable}"}}'
            (self.stub / "view.json").write_text(view)

        origin, other, main = tmp_path / "origin.git", tmp_path / "other", tmp_path / "main"
        self.work = tmp_path / "trees" / "a-task"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(other))
        self.commit(other, "shared.txt", "one\n", "start")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(tmp_path, "clone", "-q", str(origin), str(main))
        git(main, "worktree", "add", "-q", "-b", "a-task", str(self.work))
        self.git_dir = Path(git(self.work, "rev-parse", "--absolute-git-dir"))
        self.commit(self.work, "shared.txt", "one\nthe task\n", "the task")
        git(self.work, "push", "-q", "-u", "origin", "a-task")
        self.commit(other, main_edits, "theirs\n", "theirs")
        git(other, "push", "-q", "origin", "HEAD:main")
        self.landed = git(other, "rev-parse", "HEAD")

    @staticmethod
    def commit(repo, name, text, message):
        (repo / name).write_text(text)
        git(repo, "add", name)
        git(repo, "commit", "-q", "-m", message)

    def head(self):
        return git(self.work, "rev-parse", "HEAD")

    def rebasing(self):
        states = ("rebase-merge", "rebase-apply")
        return any((self.git_dir / name).exists() for name in states)

    def run(self, about, home=None):
        script = block("Stay on the pull request", about)
        if home:
            script = script.replace("<slug>", "alpha")
        return subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.com",
                "GIT_EDITOR": "true",
                "T": str(REPO / "features" / "crew" / "templates"),
                **({"H": str(home)} if home else {}),
            },
        ).stdout


def covers(main, brief, head):
    """How `jmerge` judges a head that the brief does not mention: which commit its review
    covers, and whether that review carries over to the head. `jmerge` decides with a
    range-diff, which it runs in the main checkout after the checkout has fetched."""
    assert ready.short_of(brief, head) == ""
    covered = ready.to_range_diff(ready.rebase_of(brief, head), brief, head)
    git(main, "fetch", "-q", "origin")
    return covered, rangediff.verdict(main, covered, head, "main").clean


def run(conclusion, job=None):
    """One run of a check, as `gh pr view --json statusCheckRollup` lists the run, with its job
    if the run has one."""
    one = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": conclusion}
    if job:
        one["detailsUrl"] = f"https://github.com/someone/repo/actions/runs/5/job/{job}"
    return one


def ran(conclusion, started, completed, name="check", job=None):
    """A run of the check `name` that ran on 2026-10-18 from `started` to `completed`."""
    day = "2026-10-18T{}Z"
    return {
        **run(conclusion, job),
        "name": name,
        "startedAt": day.format(started),
        "completedAt": day.format(completed),
    }


STEPS = {"1": [], "2": [{"name": "Run make check", "conclusion": "failure"}]}


RUNNING = {"__typename": "CheckRun", "status": "IN_PROGRESS", "conclusion": ""}


ROLLUPS = {
    "all passed": ([run("SUCCESS"), run("SUCCESS", 2), run("SKIPPED")], "passed"),
    "a commit status that passed": (
        [{"__typename": "StatusContext", "state": "SUCCESS"}],
        "passed",
    ),
    "one ran and failed": ([run("SUCCESS"), run("FAILURE", 2)], "failed"),
    "one failed, and GitHub gives no job for it": ([run("FAILURE"), run("SKIPPED")], "failed"),
    "one failed, and its job cannot be asked for": ([run("FAILURE", 3), run("SKIPPED")], "failed"),
    "one timed out after it ran": ([run("TIMED_OUT", 2), run("SKIPPED")], "failed"),
    "a commit status that failed": (
        [{"__typename": "StatusContext", "state": "FAILURE"}],
        "failed",
    ),
    "one never started beside one that passed": ([run("SUCCESS"), run("FAILURE", 1)], "failed"),
    "none ran": ([run("FAILURE", 1), *[run("SKIPPED", 9)] * 3], "unrun"),
    "all skipped": ([run("SKIPPED"), run("SKIPPED")], "unrun"),
    "one still running": ([run("SUCCESS"), RUNNING], "wait"),
    "one still running beside one that never started": ([run("FAILURE", 1), RUNNING], "wait"),
    "none reported yet": ([], "wait"),
    "check cancelled, then run again to a pass, as #72's head was": (
        [
            ran("CANCELLED", "00:28:37", "00:43:52", job=2),
            ran("SUCCESS", "01:11:04", "01:23:33"),
            ran("SKIPPED", "00:26:17", "00:26:16", "full"),
            ran("SKIPPED", "00:56:59", "00:56:59", "full"),
        ],
        "passed",
    ),
    "check passed, then a later run was cancelled": (
        [ran("SUCCESS", "01:11:04", "01:23:33"), ran("CANCELLED", "01:30:00", "01:31:00", job=2)],
        "failed",
    ),
    "check passed, then a later run failed": (
        [ran("FAILURE", "01:30:00", "01:41:00", job=2), ran("SUCCESS", "01:11:04", "01:23:33")],
        "failed",
    ),
    "check's one run was cancelled": ([ran("CANCELLED", "00:28:37", "00:43:52", job=2)], "failed"),
    "GitHub cannot be asked": (None, "wait"),
}


def spent(stub, left=0):
    """GitHub's API budget, as the stub `gh` gives it, has `left` calls in each window."""
    window = {"limit": 5000, "used": 5000 - left, "remaining": left, "reset": 1791824400}
    (stub / "rate-limit.json").write_text(json.dumps({"resources": dict.fromkeys(WINDOWS, window)}))


WINDOWS = ("core", "graphql")


def stub_gh(stub, head, rollup, state="OPEN"):
    """A stub `gh` that prints this rollup for the pull request, or fails when there is no
    rollup."""
    stub.mkdir()
    (stub / "gh").write_text(GH)
    (stub / "gh").chmod(0o755)
    for job, steps in STEPS.items():
        (stub / f"job-{job}.json").write_text(json.dumps({"id": int(job), "steps": steps}))
    if rollup is not None:
        view = {"state": state, "headRefOid": head, "statusCheckRollup": rollup}
        (stub / "view.json").write_text(json.dumps(view))


class Failed(PullRequest):
    """A pull request with a check that ran and failed at the pushed head, and its brief."""

    def __init__(self, tmp_path, holds_base=True):
        super().__init__(tmp_path, None, "other.txt")
        self.state = tmp_path / "state"
        (self.state / "tasks").mkdir(parents=True)
        self.brief = self.state / "tasks" / "alpha.md"
        self.brief.write_text(BRIEF)
        if holds_base:
            git(self.work, "fetch", "-q", "origin")
            git(self.work, "merge", "-q", "--no-edit", "origin/main")
        self.push()

    def push(self, checks=None):
        """GitHub has the head that this worktree is at, and the pull request's failed check is
        job 2 of run 5."""
        view = {
            "headRefOid": self.head(),
            "baseRefName": "main",
            "statusCheckRollup": checks or [run("SUCCESS"), run("FAILURE", 2)],
        }
        (self.stub / "view.json").write_text(json.dumps(view))

    def says(self, here, wait=None):
        """What the block prints when the test tells it what the check command did in this
        worktree. With `wait`, the block waits that long for GitHub's budget, not nine minutes."""
        text = block("Stay on the pull request", "run rerun").replace("<slug>", "alpha")
        if wait is not None:
            text = text.replace("--wait 540", f"--wait {wait}")
        text, filled = re.subn(
            r"^here='<[^>]*>'$", f"here='{here}'" if here else r"\g<0>", text, flags=re.M
        )
        assert filled == 1
        ran = subprocess.run(
            ["sh", "-c", text],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "H": str(self.state),
                "T": str(REPO / "features" / "crew" / "templates"),
            },
            check=True,
        )
        (line,) = ran.stdout.splitlines()
        return line

    def reruns(self):
        calls = self.stub / "calls"
        return calls.read_text().splitlines() if calls.exists() else []


class Link(PullRequest):
    """The second link of a stack. Its worktree started from the branch of the link under it.
    That link's branch has since been squash-merged, and the remote still keeps the branch."""

    def __init__(self, tmp_path, base, edits="mine.txt", under_moved=False):
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "gh").write_text(GH)
        (self.stub / "gh").chmod(0o755)
        if base:
            (self.stub / "view.json").write_text(f'{{"baseRefName": "{base}"}}')

        origin, other, main = tmp_path / "origin.git", tmp_path / "other", tmp_path / "main"
        self.work = tmp_path / "trees" / "a-link"
        git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
        git(tmp_path, "clone", "-q", str(origin), str(other))
        self.commit(other, "shared.txt", "one\n", "start")
        git(other, "push", "-q", "origin", "HEAD:main")
        git(tmp_path, "clone", "-q", str(origin), str(main))
        git(main, "checkout", "-q", "-b", "under")
        if under_moved:
            self.commit(main, "bottom.txt", "one\n", "bottom, one")
            self.commit(main, "bottom.txt", "one\ntwo\n", "bottom, two")
        bottom = git(main, "rev-parse", "HEAD")
        self.commit(main, "under.txt", "one\n", "under, one")
        self.commit(main, "under.txt", "one\ntwo\n", "under, two")
        git(main, "push", "-q", "-u", "origin", "under")
        git(main, "worktree", "add", "-q", "-b", "a-link", str(self.work), "under")
        git(main, "checkout", "-q", "main")
        self.git_dir = Path(git(self.work, "rev-parse", "--absolute-git-dir"))
        self.commit(self.work, edits, "one\ntwo\nthe link\n", "the link")
        git(self.work, "push", "-q", "-u", "origin", "a-link")
        self.started_from = git(main, "rev-parse", "under")
        self.commit(other, "other.txt", "theirs\n", "theirs")
        git(other, "push", "-q", "origin", "HEAD:main")
        if under_moved:
            self.commit(other, "bottom.txt", "one\ntwo\n", "bottom (#1)")
            git(other, "push", "-q", "origin", "HEAD:main")
            git(main, "fetch", "-q", "origin")
            git(main, "checkout", "-q", "under")
            git(main, "rebase", "-q", "--onto", "origin/main", bottom)
            git(main, "push", "-q", "--force-with-lease", "origin", "under")
            git(main, "checkout", "-q", "main")
        self.commit(other, "under.txt", "one\ntwo\n", "under (#2)")
        git(other, "push", "-q", "origin", "HEAD:main")
        self.landed = git(other, "rev-parse", "HEAD")

    def move(self, was="under"):
        about = block("Stay on the pull request", "--onto")
        (placeholder,) = re.findall(r"^was='(<[^>]+>)'$", about, re.M)
        return self.run_text(about.replace(placeholder, was)).splitlines()

    def run_text(self, text, **env):
        return subprocess.run(
            ["sh", "-c", text],
            capture_output=True,
            text=True,
            cwd=self.work,
            env={
                **os.environ,
                "T": str(REPO / "features" / "crew" / "templates"),
                **env,
                "PATH": f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "GIT_AUTHOR_NAME": "t",
                "GIT_AUTHOR_EMAIL": "t@example.com",
                "GIT_COMMITTER_NAME": "t",
                "GIT_COMMITTER_EMAIL": "t@example.com",
                "GIT_EDITOR": "true",
            },
        ).stdout


STOPPED = "the rebase stopped: resolve these, then git rebase --continue"


def stays(pr, about, brief=None, why=None, slug="a-task", state=None, shell="sh", **env):
    """What a block of "Stay on the pull request" prints in a crewmate's worktree. The test
    fills in the slug, puts the home's state beside the worktree, and passes `stale` where
    the test gives it, and the variables in `env`."""
    state = state or pr.stub.parent / "home"
    (state / "tasks").mkdir(parents=True, exist_ok=True)
    if brief is not None:
        (state / "tasks" / f"{slug}.md").write_text(brief)
    text = block("Stay on the pull request", about).replace("<slug>", slug)
    if why:
        text, filled = re.subn(r"^why='<[^>]*>'$", f"why='{why}'", text, flags=re.M)
        assert filled == 1
    if shell != "sh":
        text = f"exec {shell} -c {shlex.quote(text)}"
    return Link.run_text(pr, text, H=str(state), **env).splitlines()


def asked(pr, mergeable):
    """GitHub's answer about the pull request, with the head that GitHub has for it."""
    view = {"baseRefName": "main", "mergeable": mergeable, "headRefOid": pr.head()}
    (pr.stub / "view.json").write_text(json.dumps(view))
