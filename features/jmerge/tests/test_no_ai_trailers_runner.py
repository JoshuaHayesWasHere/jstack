"""The check's no-AI-trailer step (`scripts/no_ai_trailers.py`) reads a pull request's commits in
the checkout the runner gives it: `actions/checkout` with `fetch-depth: 2` and no filter, of
GitHub's merge of the head into main, then the step's own read of base to head from `origin`.

GitHub builds that merge on the main it saw then, and the event's base can be a later main: the
merge's first parent, which the checkout holds with its tree, is then an ancestor of the event's
base. On 2026-11-10 that read, a `git fetch --filter=tree:0 --unshallow` into the checkout, made
git 2.56.0 crash (`BUG: builtin/pack-objects.c:5098: should_include_obj should only be called on
existing objects`) on three pull requests: index-pack repacked the checkout's commits that the
fetched commits link to into the new promisor pack, walked past them into the fetched history,
and met a tree the filter left out. Each pull request went red for a fault not its own.

The tests build that checkout over a real `origin` and run the script as the step runs it."""

import json
import os
import subprocess
import sys
from pathlib import Path

from jbus import stall

REPO = Path(__file__).resolve().parents[3]
SCRIPT = REPO / "scripts" / "no_ai_trailers.py"
CLAUDE = "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
RUN = {"check": True, "capture_output": True, "text": True}


def git(where, *args):
    who = ["-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
    return subprocess.run(["git", *who, *args], cwd=where, **RUN).stdout.strip()


def commit(where, path, text, message):
    (where / path).write_text(text)
    git(where, "add", path)
    git(where, "commit", "-q", "-m", message)
    return git(where, "rev-parse", "HEAD")


def runner_checkout(tmp_path, messages):
    """An `origin` where the pull request's branch has these commits, GitHub's merge of it into
    main as main was, and main moved on since. Return the checkout the runner makes of that merge,
    and the event's base (main now) and head."""
    origin, work = tmp_path / "origin", tmp_path / "work"
    origin.mkdir()
    git(origin, "init", "-q")
    for at in range(3):
        commit(origin, f"main{at}", f"{at}\n", f"chore: main {at}")
    git(origin, "checkout", "-q", "-b", "pr")
    for at, message in enumerate(messages):
        head = commit(origin, f"pr{at}", f"{at}\n", message)
    git(origin, "checkout", "-q", "--detach", "main")
    git(origin, "merge", "-q", "--no-ff", "-m", "Merge pr into main", "pr")
    git(origin, "update-ref", "refs/pull/1/merge", "HEAD")
    git(origin, "checkout", "-q", "main")
    base = commit(origin, "later", "later\n", "chore: main moves after the merge was built")
    git(origin, "config", "uploadpack.allowFilter", "true")
    git(origin, "config", "uploadpack.allowAnySHA1InWant", "true")
    work.mkdir()
    git(work, "init", "-q")
    git(work, "remote", "add", "origin", f"file://{origin}")
    merge = "+refs/pull/1/merge:refs/remotes/pull/1/merge"
    git(
        work,
        "fetch",
        "-q",
        "--no-tags",
        "--prune",
        "--no-recurse-submodules",
        "--depth=2",
        "origin",
        merge,
    )
    git(work, "checkout", "-q", "--force", "refs/remotes/pull/1/merge")
    return work, base, head


def step(work, base, head, title="feat: a change"):
    """Run the script as the step does, on a pull request from base to head."""
    event = work.parent / "event.json"
    pull = {"title": title, "body": "Why.", "base": {"sha": base}, "head": {"sha": head}}
    event.write_text(json.dumps({"pull_request": pull}))
    env = {
        **os.environ,
        "PYTHONPATH": f"{REPO}/features/jmerge/src:{REPO}/features/jleak/src",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_TOKEN": "t0ken",
    }
    ran = subprocess.run(
        [sys.executable, str(SCRIPT)], cwd=work, capture_output=True, text=True, env=env
    )
    return ran.returncode, ran.stdout.splitlines()


def test_the_commits_are_read_over_the_runners_checkout_of_a_merge_on_an_older_main(tmp_path):
    work, base, head = runner_checkout(tmp_path, ["feat: one", "fix: two"])
    assert step(work, base, head) == (
        0,
        ["no-ai-trailers: the title, the body and 2 commits carry none"],
    )


def test_an_ai_trailer_is_still_refused_over_the_runners_checkout(tmp_path):
    work, base, head = runner_checkout(tmp_path, ["feat: one", f"fix: two\n\nWhy.\n\n{CLAUDE}"])
    code, printed = step(work, base, head)
    assert (code, printed[0]) == (
        1,
        f"::error title=AI co-author trailer::commit {head[:12]} line 5: {CLAUDE}",
    )


def test_a_git_that_cannot_read_the_commits_is_named_a_runner_fault_jbus_counts_for_nothing(
    tmp_path,
):
    """An `origin` that serves nothing leaves the range unread: the step still fails, as an
    unread range is not a clean one, and says it in the words jbus reads as a fetch failure of
    the runner's (`jbus.stall.FETCH`), not as the pull request's own red."""
    work, base, head = runner_checkout(tmp_path, ["feat: one"])
    git(work, "remote", "set-url", "origin", f"file://{tmp_path}/gone")
    code, printed = step(work, base, head)
    assert code == 2
    assert printed[0].startswith("::error::no-ai-trailers: the commits could not be read")
    assert "a runner fault, not this pull request's" in printed[0]
    assert stall.FETCH.search(printed[0])
