"""One command, `jmerge`, merges a pull request that is reviewed, fixed and green, and the home
skill tells a home to run it. The test takes the line from the skill and runs it against a fake `gh`
and a temporary repo."""

import functools
import json
import os
import re
import shlex
import shutil
import subprocess
import textwrap
from datetime import date, datetime

import pytest

import repo_template
from jmerge import lines, ready
from test_home_thread import as_read
from testing.layouts import assembled
from testing.paths import skills

SKILL = skills()["home"] / "SKILL.md"
FENCED = re.compile(r"^[ \t]*```sh\n(.*?)^[ \t]*```$", re.M | re.S)
NAME = "a demo repo"
URL = "https://example.test/pull/7"
REVIEWED = "a" * 40
PUSHED = "b" * 40
TITLE = "feat: the task, done"


@functools.cache
def uv_cache():
    """The uv cache of the user the tests run as. This helper asks `uv` for it once, when a
    test first needs it, and `functools.cache` keeps the answer."""
    ran = subprocess.run(["uv", "cache", "dir"], check=True, capture_output=True, text=True)
    return ran.stdout.strip()


def run(conclusion, name="check", status="COMPLETED"):
    """A check run as GitHub lists it: the job named `check` unless the test names another."""
    return {"__typename": "CheckRun", "name": name, "status": status, "conclusion": conclusion}


PASSED = run("SUCCESS")
FAILED = run("FAILURE")
RUNNING = run("", status="IN_PROGRESS")
SKIPPED = run("SKIPPED")
OTHER_PASSED = run("SUCCESS", "lint")
OTHER_FAILED = run("FAILURE", "lint")
UNSTARTED = {**FAILED, "detailsUrl": "https://github.com/someone/repo/actions/runs/5/job/1"}
BORDERS = run("SUCCESS", "borders")


def rollup(checks):
    """A pull request's checks as GitHub lists them: `checks`, plus a passed `borders` where
    `checks` has no run of it. `borders` is the other check jmerge requires."""
    listed = list(checks)
    named = {one.get("name") or one.get("context") for one in listed}
    return listed if "borders" in named else [*listed, BORDERS]


def timed(conclusion, started, completed, name="check"):
    """A check run that ran on 2026-10-18 from `started` to `completed`, as GitHub lists it."""
    day = "2026-10-18T{}Z"
    return {
        **run(conclusion, name),
        "startedAt": day.format(started),
        "completedAt": day.format(completed),
    }


CANCELLED_EARLY = timed("CANCELLED", "00:28:37", "00:43:52")
PASSED_LATER = timed("SUCCESS", "01:11:04", "01:23:33")
ROLLUP_OF_D2FDB509 = (
    CANCELLED_EARLY,
    PASSED_LATER,
    timed("SKIPPED", "00:26:17", "00:26:16", "full"),
    timed("SKIPPED", "00:56:59", "00:56:59", "full"),
)

LIST = (
    "number,url,title,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,"
    "files,changedFiles,isDraft"
)
ME = "mcp:this-home"
OTHER = "mcp:another-home"

NOHOME = skills()["nohome"] / "SKILL.md"

GH = """\
#!/bin/sh
echo "$*" >> "$STUB/calls"
export GIT_AUTHOR_NAME=t GIT_AUTHOR_EMAIL=t@example.com
export GIT_COMMITTER_NAME=t GIT_COMMITTER_EMAIL=t@example.com
case "$1 $2" in
    "pr list")
        if [ "$3" = "--base" ]; then
            [ "$5 $6 $7 $8" = "--state open --json number" ] || exit 64
            cat "$STUB/based-on-$4.json" 2> /dev/null || echo "[]"
        else
            cat "$STUB/list.json" 2> /dev/null
        fi ;;
    "repo view")
        case "$*" in
            *"--json defaultBranchRef --jq .defaultBranchRef.name") ;;
            *) exit 64 ;;
        esac
        cat "$STUB/default" 2> /dev/null || echo main ;;
    "api --paginate")
        [ "$3 $4" = "repos/{owner}/{repo}/pulls/7/files --jq" ] || exit 64
        echo "$GH_REPO" > "$STUB/asked-about"
        case "$5" in
            ".[] | .previous_filename // empty") cat "$STUB/left" ;;
            ".[] | {filename, status}") cat "$STUB/every" ;;
            *) exit 64 ;;
        esac ;;
    "api repos/"*"/check-runs")
        cat "$STUB/main-check-runs.json" ;;
    "api rate_limit")
        cat "$STUB/rate-limit.json" ;;
    "pr merge")
        [ "$4 $5" = "--squash --match-head-commit" ] || exit 64
        cp "$LOG" "$STUB/log-at-merge" 2> /dev/null
        if [ "$6" != "$(cat "$STUB/head")" ]; then
            echo "X Pull request #$3 is not mergeable: the head moved" >&2
            echo "GraphQL: Head branch was modified. Review and try the merge again." >&2
            exit 1
        fi
        commit=$(git -C "$ORIGIN" commit-tree "$6^{tree}" -p refs/heads/main -m "the task (#$3)")
        git -C "$ORIGIN" update-ref refs/heads/main "$commit"
        echo "$commit" > "$STUB/merged" ;;
    "pr view")
        if [ "$4 $5" = "--json state,headRefOid,baseRefName" ]; then
            cat "$STUB/pull-${3##*/}.json"
            exit
        fi
        [ "$4 $5 $6 $7" = "--json mergeCommit --jq .mergeCommit.oid" ] || exit 64
        cat "$STUB/merged" ;;
    "pr ready")
        [ -n "$3" ] || exit 64
        if [ -e "$STUB/ready-refused" ]; then
            echo "could not mark #$3 ready" >&2
            exit 1
        fi ;;
    "pr revert")
        [ "$#" = 3 ] || exit 64
        main=$(git -C "$ORIGIN" rev-parse refs/heads/main)
        commit=$(git -C "$ORIGIN" commit-tree "$main~1^{tree}" -p "$main" -m "Revert the task")
        git -C "$ORIGIN" update-ref "refs/heads/revert-${3##*/}" "$commit"
        echo "${3%/*}/8" ;;
    *) exit 64 ;;
esac
"""


def block(about):
    """The one `sh` block of the skill that has the text `about` in it, as an agent reads it."""
    (found,) = [text for text in FENCED.findall(as_read(SKILL)) if about in text]
    return textwrap.dedent(found)


def paths():
    """The block at the top of the skill, which sets `$H`."""
    (found,) = [text for text in FENCED.findall(as_read(SKILL)) if re.search(r"^H=", text, re.M)]
    return textwrap.dedent(found)


def git(cwd, *args):
    identity = ["-c", "user.name=t", "-c", "user.email=t@example.com"]
    ran = subprocess.run(
        ["git", *identity, *args], cwd=cwd, check=True, capture_output=True, text=True
    )
    return ran.stdout.strip()


def file(path, renamed=False):
    """A changed file as GitHub lists it. For a rename, GitHub lists only the path the file has
    now."""
    kind = "RENAMED" if renamed else "MODIFIED"
    return {"path": path, "additions": 1, "deletions": 0, "changeType": kind}


def brief(review="", result="", field=""):
    """A crewmate's brief with its Result, then whatever a reviewer and the crewmate added."""
    return (
        "# alpha: a task\n"
        'Task: "do it"\n'
        "Decisions:\n"
        "- A brief that only talks about `Review: none` or a `Fixed:` line has neither.\n"
        f"{field}"
        "Pull request: open one when done\n"
        "\n"
        "## Result\n"
        "Status: done\n"
        f"Branch: alpha   Pull request: {URL}\n"
        f"{result}"
        f"{review}"
    )


def review(verdict, head=REVIEWED):
    findings = "- error a.py:1 it is wrong\n" if verdict == "findings" else "none\n"
    return (
        "## Review\n"
        f"Verdict: {verdict}\n"
        f"Head: {head}   Unchanged by the run: yes\n"
        f"Findings:\n{findings}"
    )


class Home:
    """A user's home directory, a repo's main checkout, that repo's state, and a fake `gh`.

    The main checkout is a copy of the worker's template: one empty commit on `main`, no remote.
    """

    def __init__(self, tmp_path):
        self.user = tmp_path / "user"
        (self.user / ".claude").mkdir(parents=True)
        (self.user / ".claude" / "skills").symlink_to(assembled() / "skills")
        self.tasks = self.user / ".local" / "state" / "home" / NAME / "tasks"
        self.tasks.mkdir(parents=True)
        self.state = self.tasks.parent
        (self.state / "home-thread").write_text(f"{ME}\n")
        self.origin = tmp_path / "origin.git"
        self.stub = tmp_path / "stub"
        self.stub.mkdir()
        (self.stub / "gh").write_text(GH)
        (self.stub / "gh").chmod(0o755)
        self.main = tmp_path / "code" / NAME
        self.main.mkdir(parents=True)
        shutil.copytree(
            repo_template.templated().plain,
            self.main,
            symlinks=True,
            dirs_exist_ok=True,
            ignore=repo_template.LOCKS,
        )
        self.code = None

    def open_pull_request(
        self,
        head,
        checks=(PASSED,),
        mergeable="MERGEABLE",
        base="main",
        files=("a.txt",),
        changed=None,
        renamed=False,
        draft=False,
    ):
        """What GitHub lists of the one open pull request. `changed` is the number of files
        GitHub says the pull request changes, when that number is more than the files it lists.
        `renamed` makes the last file a rename. `draft` marks a pull request its author has not
        marked ready."""
        listed = {
            "number": 7,
            "url": URL,
            "title": TITLE,
            "headRefName": "alpha",
            "headRefOid": head,
            "baseRefName": base,
            "mergeable": mergeable,
            "statusCheckRollup": rollup(checks),
            "files": [file(path, renamed and path == files[-1]) for path in files],
            "changedFiles": len(files) if changed is None else changed,
            "isDraft": draft,
        }
        (self.stub / "list.json").write_text(json.dumps([listed]))
        (self.stub / "head").write_text(f"{head}\n")

    def run(self, *flags, cwd=None, path=None, about=None):
        """Run the command as jbus's pass does: `jmerge` from the main checkout, with no `--home`,
        whatever the switch holds. With `about`, run the skill's block that holds that text, in
        one call with the block at the top, with the flags added to its `jmerge` line."""
        if about is None:
            script = f'{paths()}\nuv run --project "$T/../source" jmerge {" ".join(flags)}'
            return self.sh(script, cwd, path)
        text = block(about)
        (line,) = [line for line in text.splitlines() if "jmerge --" in line]
        asked = f"{line} {' '.join(flags)}".rstrip()
        return self.sh(f'{paths()}\nM="$H"\n{text.replace(line, asked)}', cwd, path)

    def sh(self, script, cwd=None, path=None):
        """Run a script as a thread of this user would, with the fake `gh` first on PATH."""
        ran = subprocess.run(
            ["sh", "-c", script],
            capture_output=True,
            text=True,
            cwd=cwd or self.main,
            env={
                **os.environ,
                "HOME": str(self.user),
                "JBUS_CONFIG_DIR": str(self.user / ".config" / "jbus"),
                "JBUS_STATE_DIR": str(self.user / ".local" / "state" / "jbus"),
                "JBUS_HOME_DIR": str(self.user / ".local" / "state" / "home"),
                "PATH": path or f"{self.stub}:{os.environ['PATH']}",
                "STUB": str(self.stub),
                "ORIGIN": str(self.origin),
                "LOG": str(self.state / "merge.log"),
                "UV_CACHE_DIR": uv_cache(),
                "UV_OFFLINE": "1",
            },
        )
        self.code = ran.returncode
        self.stderr = ran.stderr
        return ran.stdout.splitlines()

    def nohome(self, typed):
        """Run the block the nohome skill gives under the heading for what the user typed,
        after the block at its top."""
        text = NOHOME.read_text()
        top, *_ = FENCED.findall(text)
        section = text.split(f"## `{typed}`:")[1].split("\n## ")[0]
        (found,) = FENCED.findall(section)
        said = self.sh(f"{textwrap.dedent(top)}\n{textwrap.dedent(found)}")
        assert (self.code, self.stderr, said) == (0, "", [])

    def ready(self, *flags):
        """What is ready and what waits, with nothing merged."""
        said = self.run("--check", *flags)
        assert self.stderr == ""
        return said


def pushed_on(home):
    """Make three commits on a branch from the commit where it forks from main, each on top of
    the one before. Return a function that puts their real ids in a text in place of
    `REVIEWED`, `PUSHED` and `LATER`. A fix is the commit on top of the reviewed head."""
    git(home.main, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(home.main, "checkout", "-q", "-b", "alpha")
    real = {}
    for stands_for in (REVIEWED, PUSHED, "c" * 40):
        git(home.main, "commit", "-q", "--allow-empty", "-m", "a push")
        real[stands_for] = git(home.main, "rev-parse", "HEAD")
    git(home.main, "checkout", "-q", "main")
    return lambda text: re.sub("|".join(real), lambda found: real[found[0]], text)


def test_a_pull_request_fixed_after_its_findings_is_ready_at_the_fixed_head(home):
    real = pushed_on(home)
    text = brief(review("findings"), f"{ENDED}Fixed: {PUSHED}\n")
    (home.tasks / "alpha.md").write_text(real(text))
    home.open_pull_request(real(PUSHED))
    assert home.ready() == [f"ready 7 {real(PUSHED)} alpha alpha"]


def test_a_pull_request_with_a_clean_review_is_ready_at_the_reviewed_head(home):
    (home.tasks / "alpha.md").write_text(brief(review("clean")))
    home.open_pull_request(REVIEWED)
    assert home.ready() == [f"ready 7 {REVIEWED} alpha alpha"]


@pytest.mark.parametrize(
    "result",
    [
        f"Rebase: range-diff empty, head {PUSHED}\n",
        f"Rebase: changed a.py b.py, head {PUSHED}\nFixed: none needed, the review was clean\n",
        pytest.param(
            f"Rebase: range-diff empty, head {'c' * 40}\nRebase: range-diff empty, head {PUSHED}\n",
            id="of two Rebase lines the last one counts",
        ),
    ],
)
def test_a_clean_review_stands_after_a_rebase_the_result_records(home, result):
    (home.tasks / "alpha.md").write_text(brief(review("clean"), result))
    home.open_pull_request(PUSHED)
    assert home.ready() == [f"ready 7 {PUSHED} alpha alpha"]


def test_a_rebase_hold_an_older_crew_wrote_holds_nothing(home):
    """The crew no longer holds a third rebase after fixed and green, so a `Rebase hold:` line
    from before that is no reason to wait, at the head it names or any other."""
    held = f"Rebase hold: at {REVIEWED}, a third rebase, onto main\n"
    (home.tasks / "alpha.md").write_text(brief(review("clean"), held))
    home.open_pull_request(REVIEWED)
    assert home.ready() == [f"ready 7 {REVIEWED} alpha alpha"]


def test_findings_all_declined_are_ready_at_the_reviewed_head(home):
    result = (
        "Finding: not fixed, it is wrong, because the task does not own it\n"
        "Fixed: none needed, the finding is about code the task does not own\n"
    )
    (home.tasks / "alpha.md").write_text(brief(review("findings"), result))
    home.open_pull_request(REVIEWED)
    assert home.ready() == [f"ready 7 {REVIEWED} alpha alpha"]


STOOD_IN = f"CI: did not run at {PUSHED}, `make check` passed in this worktree at that head\n"
NOT_PASSED = "check has not passed"
NO_RUN = f"check has no run at {PUSHED[:12]}"


@pytest.mark.parametrize(
    "checks",
    [
        (PASSED,),
        (PASSED, OTHER_FAILED),
        (PASSED, run("", "lint", status="IN_PROGRESS")),
        (PASSED, run("SKIPPED", "deploy")),
        ({"__typename": "StatusContext", "context": "check", "state": "SUCCESS"},),
    ],
)
def test_a_pull_request_is_green_when_the_check_named_check_passed(home, checks):
    (home.tasks / "alpha.md").write_text(brief(review("clean", PUSHED)))
    home.open_pull_request(PUSHED, checks=checks)
    assert home.ready() == [f"ready 7 {PUSHED} alpha alpha"]


def test_a_red_main_holds_no_pull_request_whose_check_passed(home):
    failed = {"name": "full", "status": "completed", "conclusion": "failure"}
    (home.stub / "main-check-runs.json").write_text(json.dumps({"check_runs": [failed]}))
    (home.tasks / "alpha.md").write_text(brief(review("clean", PUSHED)))
    home.open_pull_request(PUSHED, checks=(PASSED,))
    assert home.ready() == [f"ready 7 {PUSHED} alpha alpha"]


WIDER = f"Second pass: needed since {REVIEWED}, the fix also changed b.py\n"
SECOND = review("findings") + review("findings", PUSHED)
ENDED = "Finding: fixed, it is wrong\n"
LATER = "c" * 40

SECOND_PASS = {
    "a fix inside the files the findings named": (
        f"{ENDED}Fixed: {PUSHED}\n"
        "Second pass: none, the fix stayed inside the files the findings named\n",
        review("findings"),
        PUSHED,
    ),
    "a wider fix with a clean second pass": (
        f"{ENDED}Fixed: {PUSHED}\n{WIDER}",
        review("findings") + review("clean", PUSHED),
        PUSHED,
    ),
    "a wider fix, and a fix pushed for the second pass": (
        f"{ENDED}{ENDED}Fixed: {LATER}\n{WIDER}",
        SECOND,
        LATER,
    ),
    "a wider fix, and the second pass's findings all declined": (
        f"{ENDED}Finding: not fixed, it is wrong, because it is not this task's\n"
        f"Fixed: none needed, the second pass's findings are not this task's\n{WIDER}",
        SECOND,
        PUSHED,
    ),
}


@pytest.mark.parametrize("case", SECOND_PASS)
def test_a_fix_gets_a_second_pass_only_when_it_went_wider(home, case):
    result, reviews, head = SECOND_PASS[case]
    real = pushed_on(home)
    (home.tasks / "alpha.md").write_text(real(brief(reviews, result)))
    home.open_pull_request(real(head))
    assert home.ready() == [f"ready 7 {real(head)} alpha alpha"]


OWED = f"Scoped review: needed since {REVIEWED}, the fix changed a.py\n"
NO_FIX_REVIEW = "its fix is not reviewed: the scoped review of it is not written"

FIX_REVIEW = {
    "a fix under tests only": (
        f"{ENDED}Fixed: {PUSHED}\nScoped review: none, the fix changed files under tests/ only\n",
        review("findings"),
        PUSHED,
    ),
    "a fix with a clean review of it": (
        f"{ENDED}Fixed: {PUSHED}\n{OWED}",
        review("findings") + review("clean", PUSHED),
        PUSHED,
    ),
    "a fix pushed for the findings of its review": (
        f"{ENDED}{ENDED}Fixed: {LATER}\n{OWED}",
        SECOND,
        LATER,
    ),
}


@pytest.mark.parametrize("case", FIX_REVIEW)
def test_a_fix_is_ready_with_no_review_owed_or_with_its_one_review_handled(home, case):
    result, reviews, head = FIX_REVIEW[case]
    real = pushed_on(home)
    (home.tasks / "alpha.md").write_text(real(brief(reviews, result)))
    home.open_pull_request(real(head))
    assert home.ready() == [f"ready 7 {real(head)} alpha alpha"]


def test_a_fix_whose_review_is_owed_waits_for_it_and_then_for_each_of_its_findings():
    from jmerge import ready

    fixed = f"{ENDED}Fixed: {PUSHED}\n{OWED}"
    assert ready.short_of(brief(review("findings"), fixed), PUSHED) == NO_FIX_REVIEW
    same_head = review("findings") + review("clean")
    assert ready.short_of(brief(same_head, fixed), PUSHED) == NO_FIX_REVIEW
    written = review("findings") + review("clean", PUSHED)
    assert ready.short_of(brief(written, fixed), PUSHED) == ""
    unanswered = brief(SECOND, f"{ENDED}Fixed: {LATER}\n{OWED}")
    assert ready.short_of(unanswered, LATER) == (
        "its findings are not handled: 1 of 2 have no Finding line"
    )
    assert ready.short_of(brief(SECOND, f"{ENDED}{ENDED}Fixed: {LATER}\n{OWED}"), LATER) == ""
    again = f"{ENDED}{ENDED}Fixed: {LATER}\n{OWED}Scoped review: needed since {PUSHED}, it too\n"
    assert ready.short_of(brief(SECOND, again), LATER) == NO_FIX_REVIEW
    guarded = again.replace("it too", "guarded")
    assert ready.short_of(brief(SECOND, guarded), LATER) == ""
    no_head = f"{ENDED}Fixed: {PUSHED}\nScoped review: needed since -, it could not be compared\n"
    unnamed = review("findings").replace(f"Head: {REVIEWED}", "Run: 1")
    assert ready.short_of(brief(unnamed, no_head), PUSHED) == NO_FIX_REVIEW


FIXED = brief(review("findings"), f"{ENDED}Fixed: {PUSHED}\n")
NO_ORIGIN = "main could not be fetched to see what its rebase kept"
CHECKED_ALONE = brief(review("clean", PUSHED))

SHORT = {
    "findings with no fixed line": (
        brief(review("findings")),
        {"head": PUSHED},
        "its findings are not handled: the Result has no Fixed line",
    ),
    "a head that moved after the fixed line, and a finding with no ending": (
        brief(review("findings"), f"Fixed: {PUSHED}\n"),
        {"head": "c" * 40},
        "its findings are not handled: 1 of 1 have no Finding line",
    ),
    "a head that moved after the fixed line": (
        brief(review("findings"), f"Finding: fixed, it is wrong\nFixed: {PUSHED}\n"),
        {"head": "c" * 40},
        NO_ORIGIN,
    ),
    "a head that moved after a clean review": (
        brief(review("clean")),
        {"head": PUSHED},
        NO_ORIGIN,
    ),
    "a rebase line with no commit": (
        brief(review("clean"), "Rebase: range-diff empty\n"),
        {"head": PUSHED},
        NO_ORIGIN,
    ),
    "a rebase line with a short commit": (
        brief(review("clean"), f"Rebase: changed a.py, head {PUSHED[:7]}\n"),
        {"head": PUSHED},
        NO_ORIGIN,
    ),
    "a head that moved after the rebase": (
        brief(review("clean"), f"Rebase: range-diff empty, head {PUSHED}\n"),
        {"head": "c" * 40},
        NO_ORIGIN,
    ),
    "findings declined, then a push after the rebase": (
        brief(
            review("findings"),
            f"Rebase: changed a.py, head {PUSHED}\n"
            "Finding: not fixed, it is wrong, because a.py:1 is not this task's code\n"
            "Fixed: none needed, not this task's code\n",
        ),
        {"head": "c" * 40},
        NO_ORIGIN,
    ),
    "a fixed line that names the head the findings were written on": (
        brief(review("findings"), f"Fixed: {REVIEWED}\n"),
        {"head": REVIEWED},
        "its findings are not handled: nothing was pushed after them",
    ),
    "a second review with findings on the head the first fix pushed": (
        brief(
            review("findings") + review("findings").replace(REVIEWED, PUSHED), f"Fixed: {PUSHED}\n"
        ),
        {"head": PUSHED},
        "its findings are not handled: nothing was pushed after them",
    ),
    "a fix with no review of it": (
        brief(review("findings"), f"{ENDED}Fixed: {PUSHED}\n{OWED}"),
        {"head": PUSHED},
        NO_FIX_REVIEW,
    ),
    "a wider fix with no second pass": (
        brief(review("findings"), f"Fixed: {PUSHED}\n{WIDER}"),
        {"head": PUSHED},
        "its fix changed more than the findings named: the second pass is not written",
    ),
    "a wider fix, and a second review of the head the first one saw": (
        brief(review("findings") + review("clean"), f"Fixed: {PUSHED}\n{WIDER}"),
        {"head": PUSHED},
        "its fix changed more than the findings named: the second pass is not written",
    ),
    "a wider fix, and a line that does not say since which head": (
        brief(review("findings"), f"Fixed: {PUSHED}\nSecond pass: needed\n"),
        {"head": PUSHED},
        "its fix changed more than the findings named: the second pass is not written",
    ),
    "a wider fix, and a rebase moved the Fixed line before the second pass's findings came": (
        brief(SECOND, f"{ENDED}Fixed: {LATER}\n{WIDER}Rebase: range-diff empty, head {LATER}\n"),
        {"head": LATER},
        "its findings are not handled: 1 of 2 have no Finding line",
    ),
    "a wider fix, and a review that names no head": (
        brief(
            review("findings").replace(f"Head: {REVIEWED}", "Run: 1"),
            f"{ENDED}Fixed: {PUSHED}\nSecond pass: needed since -, the fix could not be compared\n",
        ),
        {"head": PUSHED},
        "its fix changed more than the findings named: the second pass is not written",
    ),
    "a wider fix, and a second reviewer whose run did not start": (
        brief(
            review("findings") + review("not run", PUSHED),
            f"{ENDED}Fixed: {PUSHED}\n{WIDER}",
        ),
        {"head": PUSHED},
        "its review has no verdict",
    ),
    "a wider fix whose second pass has findings, and no Fixed line after them": (
        brief(SECOND, f"Fixed: {PUSHED}\n{WIDER}"),
        {"head": PUSHED},
        "its findings are not handled: nothing was pushed after them",
    ),
    "check failed": (
        CHECKED_ALONE,
        {"head": PUSHED, "checks": (FAILED, OTHER_PASSED)},
        NOT_PASSED,
    ),
    "check has not finished": (
        FIXED,
        {"head": PUSHED, "checks": (RUNNING, OTHER_PASSED)},
        NOT_PASSED,
    ),
    "check is missing beside other checks that passed": (
        CHECKED_ALONE,
        {"head": PUSHED, "checks": (OTHER_PASSED, run("SUCCESS", "checks"))},
        NO_RUN,
    ),
    "check was skipped": (
        FIXED,
        {"head": PUSHED, "checks": (SKIPPED, OTHER_PASSED)},
        NOT_PASSED,
    ),
    "check ended neutral": (
        FIXED,
        {"head": PUSHED, "checks": (run("NEUTRAL"), OTHER_PASSED)},
        NOT_PASSED,
    ),
    "check passed once and failed in a later run": (
        FIXED,
        {"head": PUSHED, "checks": (PASSED, FAILED)},
        NOT_PASSED,
    ),
    "check passed, and a run that started later was cancelled": (
        FIXED,
        {"head": PUSHED, "checks": (PASSED_LATER, timed("CANCELLED", "01:30:00", "01:31:00"))},
        NOT_PASSED,
    ),
    "check passed, and a run that started later failed": (
        CHECKED_ALONE,
        {"head": PUSHED, "checks": (timed("FAILURE", "01:30:00", "01:41:00"), PASSED_LATER)},
        NOT_PASSED,
    ),
    "check's one run was cancelled": (
        FIXED,
        {"head": PUSHED, "checks": (CANCELLED_EARLY, OTHER_PASSED)},
        NOT_PASSED,
    ),
    "a commit status named check that failed": (
        CHECKED_ALONE,
        {
            "head": PUSHED,
            "checks": ({"__typename": "StatusContext", "context": "check", "state": "FAILURE"},),
        },
        NOT_PASSED,
    ),
    "no check ran, and an old Result says the check command stood in": (
        brief(review("clean", PUSHED), STOOD_IN),
        {"head": PUSHED, "checks": (UNSTARTED, run("SKIPPED", "deploy"))},
        NOT_PASSED,
    ),
    "every check skipped, and an old Result says the check command stood in": (
        brief(review("clean", PUSHED), STOOD_IN),
        {"head": PUSHED, "checks": (SKIPPED, SKIPPED)},
        NOT_PASSED,
    ),
    "no checks reported": (
        CHECKED_ALONE,
        {"head": PUSHED, "checks": ()},
        NO_RUN,
    ),
    "CONFLICTING": (
        FIXED,
        {"head": PUSHED, "mergeable": "CONFLICTING"},
        "it conflicts with its base",
    ),
    "UNKNOWN": (
        FIXED,
        {"head": PUSHED, "mergeable": "UNKNOWN"},
        "GitHub has not decided whether it merges",
    ),
    "Review: none": (
        brief(result=f"Fixed: {PUSHED}\n", field="Review: none\n"),
        {"head": PUSHED},
        "its brief says Review: none, so it needs the user's word",
    ),
    "Review: none, and reviewed anyway": (
        brief(review("clean"), field="Review: none\n"),
        {"head": REVIEWED},
        "its brief says Review: none, so it needs the user's word",
    ),
    "not reviewed yet": (
        brief(result="Reviewer: mcp:1111-aaaa\n"),
        {"head": REVIEWED},
        "it has no review yet",
    ),
    "no brief": (
        None,
        {"head": REVIEWED},
        "no brief has a Result that names it",
    ),
}


@pytest.mark.parametrize("case", SHORT)
def test_a_pull_request_short_of_ready_is_printed_with_the_first_reason(home, case):
    text, listed, reason = SHORT[case]
    if text:
        (home.tasks / "alpha.md").write_text(text)
    home.open_pull_request(**listed)
    assert home.ready() == [f"wait 7 {URL}: {reason}"]


@pytest.mark.parametrize("case", [case for case in SHORT if SHORT[case][2] == NO_ORIGIN])
def test_a_head_no_line_names_is_compared_with_the_commit_its_review_covers(case):
    """The commit the cases above fetch is the `Fixed:` commit, or the reviewed head when the
    brief has no `Fixed:` line."""
    from jmerge import ready

    text, listed, _ = SHORT[case]
    head = listed["head"]
    covered = PUSHED if f"Fixed: {PUSHED}" in text else REVIEWED
    assert ready.short_of(text, head) == ""
    assert ready.rebase_of(text, head) is None
    assert ready.to_range_diff(None, text, head) == covered


def test_a_gh_that_fails_prints_nothing_as_ready(home):
    (home.tasks / "alpha.md").write_text(FIXED)
    assert home.ready() == ["wait: could not ask GitHub: gh exited 1: it said nothing"]


def test_with_no_open_pull_request_it_prints_nothing(home):
    (home.stub / "list.json").write_text("[]")
    assert home.ready() == []


def test_a_gh_that_fails_is_a_job_not_done(home):
    home.ready()
    assert home.code != 0


def test_a_pull_request_that_waits_is_not_a_failure(home):
    (home.tasks / "alpha.md").write_text(brief(review("findings")))
    home.open_pull_request(PUSHED)
    home.ready()
    assert home.code == 0


def test_outside_a_repo_it_fails_and_prints_no_line(home, tmp_path):
    """Outside a repo, `$H` names no repo, and the command reads the switch from the directory
    above `$H`."""
    (home.state.parent / "home-thread").write_text(f"{ME}\n")
    assert home.run(cwd=tmp_path) == []
    assert home.code != 0
    assert "not in a git repository" in home.stderr


def test_with_no_gh_it_fails_and_prints_no_line(home, tmp_path):
    tools = tmp_path / "tools"
    tools.mkdir()
    for tool in ("uv", "git", "sh", "basename", "dirname", "realpath", "cat", "tr"):
        (tools / tool).symlink_to(shutil.which(tool))
    assert home.run(path=str(tools)) == []
    assert home.code != 0
    assert "gh is not installed" in home.stderr


WHOSE = {
    "a brief that names this home": (f"Home: {ME}\n", OTHER, "", (), True),
    "a brief that names another home": (f"Home: {OTHER} (a second home)\n", ME, "", (), False),
    "no line, and this home is the listed one": ("", ME, "", (), True),
    "no line, and another home is the listed one": ("", OTHER, "", (), False),
    "a brief that names this home by its directory": (
        "Home: second (a second home)\n",
        OTHER,
        "",
        (),
        True,
    ),
    "a brief that names another home by its directory": (
        "Home: third (a home)\n",
        ME,
        "",
        (),
        False,
    ),
    "no line and no home listed, asked by a scoped home": ("", "", "", (), False),
    "a brief that names no home, which is the root's": ("Home: mcp:nobody\n", ME, "", (), True),
    "a brief that names a directory that is no scope": ("Home: tasks\n", ME, "", (), True),
    "a brief that names no home, and another is the root": (
        "Home: mcp:nobody\n",
        OTHER,
        "",
        (),
        False,
    ),
    "a home that handed off to this one": (f"Home: {OTHER}\n", ME, OTHER, (), True),
    "a home that handed off to another": ("Home: mcp:old\n", OTHER, "mcp:old", (), False),
}


@pytest.mark.parametrize("case", WHOSE)
def test_a_home_that_asks_sees_its_own_pull_requests(home, case):
    line, listed, was, flags, mine = WHOSE[case]
    (home.tasks / "alpha.md").write_text(brief(review("clean"), field=line))
    if listed:
        (home.state / "home-id").write_text(f"{listed}\n")
    (home.state / "second").mkdir()
    (home.state / "second" / "home-id").write_text(f"{ME}\n")
    (home.state / "third").mkdir()
    (home.state / "third" / "home-id").write_text(f"{OTHER}\n")
    if was:
        (home.state / "handoff.md").write_text(f"# a handoff\n\nWas home: {was}\n")
    home.open_pull_request(REVIEWED)
    wanted = f"ready 7 {REVIEWED} alpha alpha" if mine else f"wait 7 {URL}: another home's"
    assert home.ready("--home", ME, *flags) == [wanted]


PLAN = """\
# a demo repo: plan

## alpha: a task
Status: with crewmate (thread mcp:1111-aaaa)
Done when:
- it is done

## beta: another task
Status: planned
"""


REVERT = f"revert: gh pr revert {URL}"


def merged_as(commit):
    """The start of a `merged` line: its first four words, which jbus reads, and the title."""
    return f'merged 7 alpha {commit} "{TITLE}"'


def merged_line(commit, *notes):
    return ", ".join([merged_as(commit), *notes, REVERT])


TRACKED = """\
[remote "origin"]
\turl = {origin}
\tfetch = +refs/heads/*:refs/remotes/origin/*
[branch "main"]
\tremote = origin
\tmerge = refs/heads/main
"""


class Merged:
    """A main checkout with a crewmate's worktree. The crewmate pushed its branch, and the pull
    request has a clean review at the head it pushed, so the pull request is ready unless the test
    says otherwise.

    The origin is a copy of the template's origin, whose `main` has the commit that `Home` copied.
    The checkout gets what `git push -u origin main` would write: the remote, `main`'s upstream
    and the ref of `origin/main`. So `Merged` starts from a `Home` that no test has changed yet.
    """

    def __init__(self, home, tmp_path):
        self.home = home
        self.origin = home.origin
        template, git_dir = repo_template.templated(), home.main / ".git"
        if (git_dir / "refs" / "heads" / "main").read_text().strip() != template.main:
            raise AssertionError("Merged is built on a Home whose main has moved")
        shutil.copytree(template.origin, self.origin, symlinks=True, ignore=repo_template.LOCKS)
        with (git_dir / "config").open("a") as config:
            config.write(TRACKED.format(origin=self.origin))
        (git_dir / "refs" / "remotes" / "origin").mkdir(parents=True)
        (git_dir / "refs" / "remotes" / "origin" / "main").write_text(f"{template.main}\n")
        self.start = template.main
        self.tree = tmp_path / "trees" / "alpha"
        git(home.main, "worktree", "add", "-q", "-b", "alpha", str(self.tree))
        (self.tree / "a.txt").write_text("the task\n")
        git(self.tree, "add", "a.txt")
        git(self.tree, "commit", "-q", "-m", "the task")
        git(self.tree, "push", "-q", "-u", "origin", "alpha")
        self.head = git(self.tree, "rev-parse", "HEAD")
        self.plan = home.state / "plan.md"
        self.plan.write_text(PLAN)
        (home.tasks / "alpha.md").write_text(brief(review("clean", self.head)))
        home.open_pull_request(self.head)

    def run(self, *flags):
        said = self.home.run(*flags)
        assert self.home.stderr == ""
        assert self.home.code == 0
        return said

    def on_main(self):
        return git(self.origin, "rev-parse", "main"), git(self.home.main, "rev-parse", "HEAD")

    def branches(self):
        local = git(self.home.main, "branch", "--format=%(refname:short)").split()
        remote = git(self.origin, "branch", "--format=%(refname:short)").split()
        return sorted(local), sorted(remote)

    def log(self):
        log = self.home.state / "merge.log"
        return log.read_text().splitlines() if log.exists() else []

    def untouched(self):
        return (
            self.on_main() == (self.start, self.start)
            and self.tree.exists()
            and self.branches() == (["alpha", "main"], ["alpha", "main"])
            and self.plan.read_text() == PLAN
        )


def test_a_ready_pull_request_is_merged_pulled_and_cleared_up_and_the_plan_is_left(merged):
    said = merged.run()
    commit, pulled = merged.on_main()
    assert said == [merged_line(commit)]
    assert commit != merged.start and pulled == commit
    assert (merged.home.main / "a.txt").read_text() == "the task\n"
    assert not merged.tree.exists()
    assert merged.branches() == (["main"], ["main"])
    today = date.today().isoformat()
    assert merged.plan.read_text() == PLAN
    (logged,) = merged.log()
    assert re.fullmatch(rf"{today} \d\d:\d\d ", logged[:17])
    assert logged[17:] == said[0]


def test_a_pull_request_that_waits_is_left_and_logged(merged):
    merged.home.open_pull_request(merged.head, checks=(PASSED, FAILED))
    line = f"wait 7 {URL}: {NOT_PASSED}"
    assert merged.run() == [line]
    assert merged.untouched()
    assert [logged.split(" ", 2)[2] for logged in merged.log()] == [f"{line} [not-passed]"]


def test_a_check_cancelled_and_then_run_again_to_a_pass_is_green(merged):
    merged.home.open_pull_request(merged.head, checks=ROLLUP_OF_D2FDB509)
    assert merged.run("--check") == [f"ready 7 {merged.head} alpha alpha"]
    assert merged.untouched()


def test_a_look_at_what_is_ready_merges_and_logs_nothing(merged):
    assert merged.run("--check") == [f"ready 7 {merged.head} alpha alpha"]
    assert merged.untouched()
    assert merged.log() == []


def test_a_head_that_moved_after_the_check_is_not_merged(merged):
    (merged.home.stub / "head").write_text("c" * 40 + "\n")
    said = merged.run()
    assert said == [
        f"wait 7 {URL}: the merge failed: "
        "GraphQL: Head branch was modified. Review and try the merge again."
    ]
    assert merged.untouched()


def test_another_homes_pull_request_is_left_by_a_home_and_merged_by_jbus(merged):
    (merged.home.state / "home-id").write_text(f"{ME}\n")
    (merged.home.tasks / "alpha.md").write_text(
        brief(review("clean", merged.head), field=f"Home: {OTHER}\n")
    )
    theirs = merged.home.state / "second" / "plan.md"
    theirs.parent.mkdir()
    theirs.write_text(PLAN)
    (theirs.parent / "home-id").write_text(f"{OTHER}\n")
    merged.plan.write_text("# a demo repo: plan\n")
    assert merged.run("--home", ME) == [f"wait 7 {URL}: another home's"]
    assert merged.on_main() == (merged.start, merged.start)
    said = merged.run()
    commit, _ = merged.on_main()
    assert said == [merged_line(commit)]
    assert theirs.read_text() == PLAN


def test_a_merge_writes_no_plan_and_notes_none(merged):
    plan = "# a demo repo: plan\n\n## beta: another task\nStage: planned\n"
    merged.plan.write_text(plan)
    said = merged.run()
    commit, _ = merged.on_main()
    assert said == [merged_line(commit)]
    assert merged.plan.read_text() == plan
    assert [logged[17:] for logged in merged.log()] == [merged_line(commit)]


def test_a_main_checkout_that_cannot_be_pulled_is_said(merged):
    git(merged.home.main, "commit", "-q", "--allow-empty", "-m", "not pushed")
    (said,) = merged.run()
    commit, pulled = merged.on_main()
    unfollowed = lines.unfollowed(said)
    assert unfollowed.startswith("the main checkout was not pulled after the merge (fatal: ")
    assert said.startswith(f"{merged_as(commit)}, {unfollowed}, ")
    assert pulled != commit
    assert not merged.tree.exists()


def test_a_worktree_with_uncommitted_work_is_kept_with_its_branches(merged):
    (merged.tree / "notes.txt").write_text("not committed\n")
    said = merged.run()
    commit, pulled = merged.on_main()
    assert said == [merged_line(commit, f"kept: {merged.tree} has uncommitted work")]
    assert pulled == commit
    assert merged.tree.exists()
    assert merged.branches() == (["alpha", "main"], ["alpha", "main"])


def test_a_branch_with_a_commit_the_merge_did_not_take_is_kept(merged):
    git(merged.tree, "commit", "-q", "--allow-empty", "-m", "after the push")
    said = merged.run()
    commit, _ = merged.on_main()
    assert said == [merged_line(commit, "kept: alpha is not at the merged head")]
    assert merged.tree.exists()
    assert merged.branches() == (["alpha", "main"], ["alpha", "main"])


def test_a_worktree_that_cannot_be_removed_keeps_both_branches(merged):
    git(merged.home.main, "worktree", "lock", str(merged.tree))
    (said,) = merged.run()
    commit, _ = merged.on_main()
    kept = f"kept: {merged.tree} could not be removed, and both branches are left ("
    assert said.startswith(f"{merged_as(commit)}, {kept}")
    assert merged.tree.exists()
    assert merged.branches() == (["alpha", "main"], ["alpha", "main"])


def test_a_remote_branch_that_cannot_be_deleted_is_said_as_kept(merged):
    git(merged.origin, "branch", "-D", "alpha")
    (said,) = merged.run()
    commit, _ = merged.on_main()
    kept = "kept: the remote branch alpha, the worktree and the local branch are removed ("
    assert said.startswith(f"{merged_as(commit)}, {kept}")
    assert not merged.tree.exists()
    assert merged.branches() == (["main"], ["main"])


def test_a_worktree_whose_directory_is_gone_does_not_stop_the_command(merged):
    shutil.rmtree(merged.tree)
    (said,) = merged.run()
    commit, pulled = merged.on_main()
    assert said.startswith(merged_as(commit))
    assert pulled == commit
    assert merged.branches() == (["main"], ["main"])
    assert [logged.split(" ", 2)[2] for logged in merged.log()] == [said]


def test_each_line_is_logged_as_it_is_printed_not_at_the_end(merged):
    listed = json.loads((merged.home.stub / "list.json").read_text())
    other = {**listed[0], "number": 6, "url": URL[:-1] + "6"}
    (merged.home.stub / "list.json").write_text(json.dumps([other, *listed]))
    said = merged.run()
    assert said[0] == f"wait 6 {URL[:-1]}6: no brief has a Result that names it"
    assert said[1].startswith("merged 7 alpha ")
    at_the_merge = (merged.home.stub / "log-at-merge").read_text().splitlines()
    waited = f"{said[0]} [no-brief]"
    assert [logged.split(" ", 2)[2] for logged in at_the_merge] == [waited]
    assert [logged.split(" ", 2)[2] for logged in merged.log()] == [waited, said[1]]


OFF = f"wait 7 {URL}: auto-merge is off for this repo"


def test_a_repo_with_no_merge_off_file_is_merged_as_ever(merged):
    assert not (merged.home.state / "merge-off").exists()
    assert merged.run() == [merged_line(merged.on_main()[0])]


@pytest.mark.parametrize("flags", [(), ("--land", "demo"), ("--home", OTHER)])
def test_a_merge_off_file_merges_nothing_whoever_runs_it(merged, flags):
    merged.home.nohome("/nohome merge")
    assert (merged.home.state / "merge-off").is_file()
    assert merged.run(*flags) == [OFF]
    assert merged.untouched()
    assert merged.run("--check") == [OFF]


def test_merge_off_is_said_only_of_what_would_have_been_merged(merged):
    merged.home.nohome("/nohome merge")
    merged.home.open_pull_request(merged.head, checks=(FAILED,))
    assert merged.run() == [f"wait 7 {URL}: {NOT_PASSED}"]


def test_switched_back_on_the_repo_is_merged_again(merged):
    merged.home.nohome("/nohome merge")
    assert merged.run() == [OFF]
    merged.home.nohome("/nohome merge on")
    assert not (merged.home.state / "merge-off").exists()
    assert merged.run() == [merged_line(merged.on_main()[0])]


DRAFT = f"wait 7 {URL}: draft"
READIED = f"wait 7 {URL}: reviewed and fixed, so marked ready, and CI runs its check at "


def readied(merged):
    """The calls of this run that marked the pull request ready."""
    asked = (merged.home.stub / "calls").read_text().splitlines()
    return [call for call in asked if call.startswith("pr ready")]


@pytest.mark.parametrize("flags", [(), ("--land", "demo")])
def test_a_draft_that_is_otherwise_ready_is_never_merged(merged, flags):
    merged.home.open_pull_request(merged.head, draft=True)
    assert merged.run("--check", *flags) == [DRAFT]
    assert readied(merged) == []
    assert merged.run(*flags) == [READIED + merged.head]
    assert merged.untouched()
    asked = (merged.home.stub / "calls").read_text().splitlines()
    assert not [call for call in asked if call.startswith("pr merge")]
    merged.home.open_pull_request(merged.head)
    assert merged.run(*flags) == [merged_line(merged.on_main()[0])]


PLACED_AS_A_DRAFT = {
    "no review yet": (brief(), ready.NO_REVIEW),
    "findings that are not handled": (brief(review("findings")), ready.NO_FIXED),
    "no brief names it": (None, ready.DRAFT),
}


@pytest.mark.parametrize("case", PLACED_AS_A_DRAFT)
def test_a_draft_waits_on_the_step_it_is_at_and_its_skipped_check_is_not_one(merged, case):
    """A crew opens its pull request as a draft, so CI runs no check on it while the review and
    the fix go on: a draft is placed on the step its brief is at, and a check that never ran is
    not that step."""
    written, why = PLACED_AS_A_DRAFT[case]
    (merged.home.state / "home-id").write_text(f"{ME}\n")
    if written is None:
        (merged.home.tasks / "alpha.md").unlink()
    else:
        (merged.home.tasks / "alpha.md").write_text(written)
    merged.home.open_pull_request(merged.head, checks=(SKIPPED,), draft=True)
    assert merged.run() == [f"wait 7 {URL}: {why}"]
    assert merged.untouched()


@pytest.mark.parametrize("field", ["", f"Home: {OTHER}\n"])
def test_a_reviewed_and_fixed_draft_is_marked_ready_so_its_one_check_runs(merged, field):
    """The one step left to a draft whose review and fix are done is the mark that it is ready,
    which starts its check. jmerge makes it on the run that finds nothing else holds it, so no
    turn a crew might not end on leaves it a draft; another home's is marked too, as jbus judges
    every home. With `--check` nothing is marked, and the draft waits on `draft`, never on the
    check."""
    (merged.home.tasks / "alpha.md").write_text(brief(review("clean", merged.head), field=field))
    merged.home.open_pull_request(merged.head, checks=(SKIPPED,), draft=True)
    assert merged.run("--check") == [DRAFT] and readied(merged) == []
    assert merged.run() == [READIED + merged.head]
    assert [call.split()[:3] for call in readied(merged)] == [["pr", "ready", "7"]]
    assert merged.untouched()
    merged.home.open_pull_request(merged.head, checks=(SKIPPED,))
    assert merged.run() == [f"wait 7 {URL}: {ready.NOT_PASSED.format(check='check')}"]


def test_a_mark_github_refuses_leaves_the_draft_waiting_on_it_with_githubs_reason(merged):
    (merged.home.stub / "ready-refused").write_text("")
    merged.home.open_pull_request(merged.head, checks=(SKIPPED,), draft=True)
    said = ready.UNREADIED.format(said="could not mark #7 ready")
    assert merged.run() == [f"wait 7 {URL}: {said}"]
    assert merged.untouched()


def test_a_draft_whose_brief_says_review_none_is_marked_ready_and_still_holds(merged):
    """`Review: none` waits for the user's word: the draft is marked ready, so that word has a
    check to go by, and the line still says it waits for the word."""
    (merged.home.tasks / "alpha.md").write_text(brief(field="Review: none\n"))
    merged.home.open_pull_request(merged.head, checks=(SKIPPED,), draft=True)
    (said,) = merged.run()
    assert said.endswith(f"7 {URL}: {ready.REVIEW_NONE}")
    assert [call.split()[:3] for call in readied(merged)] == [["pr", "ready", "7"]]


def test_a_repo_no_home_ever_started_in_can_be_switched_off(home):
    shutil.rmtree(home.state)
    home.nohome("/nohome merge")
    assert (home.state / "merge-off").is_file()


def test_the_logged_line_of_a_merge_can_be_read_back_and_its_revert_run(merged):
    (said,) = merged.run()
    commit, _ = merged.on_main()
    (logged,) = merged.log()
    at, line = logged[:16], logged[17:]
    assert datetime.strptime(at, "%Y-%m-%d %H:%M").date() == date.today()
    assert line == said
    assert line.split()[:4] == ["merged", "7", "alpha", commit]
    assert line.split(", ")[0] == f'merged 7 alpha {commit} "feat: the task'
    carried, command = line.rsplit(", revert: ", 1)
    assert carried == f'merged 7 alpha {commit} "{TITLE}"'

    opened = merged.home.sh(command)
    assert (merged.home.code, merged.home.stderr) == (0, "")
    assert opened == [URL[:-1] + "8"]
    assert calls(merged.home)[-1] == f"pr revert {URL}"
    assert git(merged.origin, "rev-parse", "revert-7^") == commit
    assert git(merged.origin, "rev-parse", "revert-7^{tree}") == git(
        merged.origin, "rev-parse", f"{merged.start}^{{tree}}"
    )
    assert merged.on_main() == (commit, commit)
    assert git(merged.home.main, "status", "--porcelain", "--branch") == "## main...origin/main"


def test_the_notes_of_a_merge_come_before_its_revert_command(merged):
    (merged.tree / "notes.txt").write_text("not committed\n")
    (said,) = merged.run()
    kept = f"kept: {merged.tree} has uncommitted work"
    assert said == f"{merged_as(merged.on_main()[0])}, {kept}, {REVERT}"
    assert merged.log()[0].endswith(said)


def test_a_url_the_shell_would_read_is_quoted_in_the_revert_command(merged):
    listed = json.loads((merged.home.stub / "list.json").read_text())
    listed[0]["url"] = odd = "https://example.test/a&b/pull/7"
    (merged.home.stub / "list.json").write_text(json.dumps(listed))
    text = brief(review("clean", merged.head)).replace(URL, odd)
    (merged.home.tasks / "alpha.md").write_text(text)
    (said,) = merged.run()
    assert shlex.split(said.rsplit(", revert: ", 1)[1]) == ["gh", "pr", "revert", odd]


def calls(home):
    """Each call of `gh` that the command made, as the line of arguments the stub recorded."""
    return (home.stub / "calls").read_text().splitlines()


def test_github_is_asked_about_the_repo_of_origin(merged):
    merged.run()
    about = f"--repo {merged.origin}"
    assert calls(merged.home) == [
        f"pr list --state open --json {LIST} {about}",
        f"repo view {merged.origin} --json defaultBranchRef --jq .defaultBranchRef.name",
        f"pr merge 7 --squash --match-head-commit {merged.head} --subject {TITLE} (#7)"
        f" --body-file - {about}",
        f"pr view 7 --json mergeCommit --jq .mergeCommit.oid {about}",
        f"pr list --base alpha --state open --json number {about}",
    ]


def test_a_checkout_with_no_origin_leaves_the_repo_to_gh(home):
    home.open_pull_request(REVIEWED)
    home.ready()
    assert calls(home) == [
        f"pr list --state open --json {LIST}",
        "repo view --json defaultBranchRef --jq .defaultBranchRef.name",
    ]


def test_a_gh_that_fails_is_logged(home):
    assert home.run() == ["wait: could not ask GitHub: gh exited 1: it said nothing"]
    assert (
        (home.state / "merge.log")
        .read_text()
        .endswith(" wait: could not ask GitHub: gh exited 1: it said nothing\n")
    )


STACK = "Stack: demo (link 2 of 3)\n"
IN_A_STACK = f"wait 7 {URL}: it is in the stack demo, which the user lands"
ON_A_BRANCH = f"wait 7 {URL}: its base is beta, not main"


def test_a_pull_request_based_on_another_branch_is_never_merged(merged):
    merged.home.open_pull_request(merged.head, base="beta")
    assert merged.run("--check") == [ON_A_BRANCH]
    assert merged.run() == [ON_A_BRANCH]
    assert merged.untouched()


def test_the_base_is_compared_with_the_default_branch_github_names(merged):
    (merged.home.stub / "default").write_text("trunk\n")
    assert merged.run() == [f"wait 7 {URL}: its base is main, not trunk"]
    assert merged.untouched()


def test_a_default_branch_github_does_not_give_merges_nothing(merged):
    (merged.home.stub / "default").write_text("")
    assert merged.home.run() == [
        "wait: could not ask GitHub: gh exited 0: it named no default branch"
    ]
    assert merged.home.code == 1
    assert merged.untouched()


def test_a_pull_request_in_a_stack_waits_for_the_user_to_land_it(merged):
    (merged.home.tasks / "alpha.md").write_text(brief(review("clean", merged.head), field=STACK))
    assert merged.run("--check") == [IN_A_STACK]
    assert merged.run() == [IN_A_STACK]
    assert merged.run("--land", "another") == [IN_A_STACK]
    assert merged.untouched()


def test_a_stack_the_user_lands_merges_its_link_on_the_default_branch(merged):
    (merged.home.tasks / "alpha.md").write_text(brief(review("clean", merged.head), field=STACK))
    assert merged.run("--check", "--land", "demo") == [f"ready 7 {merged.head} alpha alpha"]
    said = merged.run("--land", "demo")
    commit, pulled = merged.on_main()
    assert said == [merged_line(commit)]
    assert commit != merged.start and pulled == commit


def test_a_link_of_a_landed_stack_still_waits_on_its_base(merged):
    (merged.home.tasks / "alpha.md").write_text(brief(review("clean", merged.head), field=STACK))
    merged.home.open_pull_request(merged.head, base="beta")
    assert merged.run("--land", "demo") == [ON_A_BRANCH]
    assert merged.untouched()


def test_a_stack_line_with_no_name_is_held_and_no_word_lands_it(merged):
    (merged.home.tasks / "alpha.md").write_text(
        brief(review("clean", merged.head), field="Stack:\n")
    )
    line = f"wait 7 {URL}: it is in a stack its brief does not name, which the user lands"
    assert merged.run() == [line]
    assert merged.run("--land", "''") == [line]
    assert merged.untouched()


def test_only_a_stack_line_in_the_head_of_the_brief_counts(home):
    said = "Noticed: this could be one link of a stack\nStack: demo\n"
    (home.tasks / "alpha.md").write_text(brief(review("clean"), said))
    home.open_pull_request(REVIEWED)
    assert home.ready() == [f"ready 7 {REVIEWED} alpha alpha"]


BASED_ON = "the open pull request 8 is based on it"


def test_a_merged_branch_an_open_pull_request_is_based_on_is_kept(merged):
    (merged.home.stub / "based-on-alpha.json").write_text(json.dumps([{"number": 8}]))
    said = merged.run()
    commit, _ = merged.on_main()
    kept = (
        f"kept: the remote branch alpha, the worktree and the local branch are removed ({BASED_ON})"
    )
    assert said == [merged_line(commit, kept)]
    assert not merged.tree.exists()
    assert merged.branches() == (["main"], ["alpha", "main"])
    assert git(merged.origin, "rev-parse", "alpha") == merged.head


def test_a_merged_branch_is_kept_when_github_does_not_say_what_is_based_on_it(merged):
    (merged.home.stub / "based-on-alpha.json").write_text("not json\n")
    (said,) = merged.run()
    ask = "could not ask GitHub whether a pull request is based on it: gh exited 0: its output"
    assert f"({ask} was not JSON), revert: " in said
    assert merged.branches() == (["main"], ["alpha", "main"])


def test_the_sweep_keeps_that_branch_until_no_pull_request_is_based_on_it(merged):
    (merged.home.tasks / "alpha.md").write_text(brief(review("clean", merged.head), "Left: none\n"))
    based = merged.home.stub / "based-on-alpha.json"
    based.write_text(json.dumps([{"number": 8}]))
    merged.run()
    pull = {"state": "MERGED", "headRefOid": merged.head, "baseRefName": "main"}
    (merged.home.stub / "pull-7.json").write_text(json.dumps(pull))
    sweep = "jmerge --sweep"
    assert merged.home.run(about=sweep) == [f"kept alpha: {BASED_ON}"]
    assert merged.branches() == (["main"], ["alpha", "main"])
    based.unlink()
    assert merged.home.run(about=sweep) == ["removed alpha no-thread: the remote branch"]
    assert merged.branches() == (["main"], ["main"])


class Rebased:
    """A ready pull request whose default branch got new commits, and whose crewmate rebased
    the branch onto the new tip and pushed. The main checkout has the branch from before and after
    the rebase."""

    def __init__(self, merged, theirs):
        self.merged = merged
        self.before = merged.head
        main, tree = merged.home.main, merged.tree
        (main / theirs).write_text("theirs\n")
        git(main, "add", theirs)
        git(main, "commit", "-q", "-m", "theirs")
        git(main, "push", "-q", "origin", "main")
        git(tree, "fetch", "-q", "origin")
        rebase = ["-c", "core.editor=true", "rebase"]
        try:
            git(tree, *rebase, "origin/main")
        except subprocess.CalledProcessError:
            (tree / theirs).write_text("theirs\nthe task\n")
            git(tree, "add", theirs)
            git(tree, *rebase, "--continue")
        git(tree, "push", "-q", "--force-with-lease", "origin", "alpha")
        self.head = git(tree, "rev-parse", "HEAD")
        merged.home.open_pull_request(self.head)

    def says(self, line, *flags, reviewed="clean", more="", saw=None):
        """What `jmerge` prints for a Result with this `Rebase:` line. The brief has a review
        of the head before the rebase, unless the test says which head the review saw."""
        result = f"Rebase: {line}\n{more}".format(before=self.before, head=self.head)
        text = brief(review(reviewed, saw or self.before), result)
        (self.merged.home.tasks / "alpha.md").write_text(text)
        (said,) = self.merged.run(*flags)
        return said


UNCHANGED = "patch unchanged, before {before}, head {head}"
CHANGED = "patch changed in a.txt, before {before}, head {head}"


def scoped(merged, rebased):
    """The line of a pull request whose rebase changed what its patch says. The pull request
    waits for one review of the range-diff. The range-diff compares the commits of each head,
    counted after the commit where that head forks from main."""
    tip = git(merged.home.main, "rev-parse", "origin/main")
    return (
        f"wait 7 {URL}: the rebase changed the content after its review; scoped review of "
        f"git range-diff --no-color {merged.start}..{rebased.before} {tip}..{rebased.head}"
    )


def test_a_rebase_that_left_the_patch_as_it_was_is_ready(merged):
    rebased = Rebased(merged, "b.txt")
    assert rebased.says(UNCHANGED, "--check") == f"ready 7 {rebased.head} alpha alpha"
    said = rebased.says(UNCHANGED)
    assert said == merged_line(merged.on_main()[0])


def test_a_rebase_that_changed_the_content_and_says_so_waits_for_a_scoped_review(merged):
    rebased = Rebased(merged, "a.txt")
    assert rebased.says(CHANGED, "--check") == scoped(merged, rebased)
    assert rebased.says(CHANGED) == scoped(merged, rebased)
    assert merged.tree.exists() and (merged.home.main / "a.txt").read_text() == "theirs\n"


def test_a_review_of_the_rebased_head_saw_what_the_rebase_changed(merged):
    rebased = Rebased(merged, "a.txt")
    said = rebased.says(CHANGED, "--check", saw=rebased.head)
    assert said == f"ready 7 {rebased.head} alpha alpha"


def test_a_rebase_that_changed_the_patch_and_says_it_did_not_waits(merged):
    rebased = Rebased(merged, "a.txt")
    why = "its Rebase line says the patch is unchanged, and the rebase changed it"
    assert rebased.says(UNCHANGED) == f"wait 7 {URL}: {why}"
    fixed = f"{ENDED}Fixed: {rebased.head}\n"
    assert rebased.says(UNCHANGED, reviewed="findings", more=fixed) == f"wait 7 {URL}: {why}"
    assert rebased.says(CHANGED, "--check", reviewed="findings", more=fixed) == (
        scoped(merged, rebased)
    )


@pytest.mark.parametrize("gone", ["before", "head"])
def test_a_rebase_between_commits_the_main_checkout_does_not_have_waits(merged, gone):
    rebased = Rebased(merged, "b.txt")
    missing = "c" * 40
    line = UNCHANGED.replace(f"{{{gone}}}", missing)
    more = f"{ENDED}Fixed: {rebased.head}\n" if gone == "head" else ""
    assert rebased.says(line, more=more, reviewed="findings" if more else "clean") == (
        f"wait 7 {URL}: its Rebase line cannot be checked: "
        f"the patch of {missing} cannot be worked out in the main checkout"
    )


@pytest.mark.parametrize(
    "line",
    [
        "patch unchanged, head {head}",
        "patch changed, before {before}, head {head}",
        "patch unchanged, before 0123abc, head {head}",
    ],
)
def test_a_new_rebase_line_that_does_not_say_what_the_rebase_did_waits(merged, line):
    rebased = Rebased(merged, "a.txt")
    why = "its Rebase line does not say what the rebase did to the patch"
    assert rebased.says(line) == f"wait 7 {URL}: {why}"


@pytest.mark.parametrize("line", ["range-diff empty, head {head}", "changed a.txt, head {head}"])
def test_a_rebase_line_in_the_older_shape_is_read_for_its_head_alone(merged, line):
    rebased = Rebased(merged, "a.txt")
    assert rebased.says(line, "--check") == f"ready 7 {rebased.head} alpha alpha"
