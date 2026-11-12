"""A scoped reviewer reads the crew's worktree and stops when it is not at the pull request's head
with nothing uncommitted (pr-review's "A scoped pass", step 1). So `rebase.scope` launches none
into such a tree, and says so on a wait line; and a reviewer that stops all the same writes a
`## Review` with `Verdict: not run`, which ends its row's reviewing (`jbriefs not-run`).

#1710 and #1708 sat at `reviewing: yes` for hours: each crew's worktree held an unpushed commit,
their scoped reviewers stopped in about 30 s with no section, and the crews refused to rebase while
reviewing."""

import subprocess
from datetime import timedelta

from jbriefs import cli as jbriefs
from test_jbus_kitchen import NOW
from test_jbus_queue import gates
from test_jbus_rereview import keys, launched, out, scoped  # noqa: F401

SCOPED = "mcp:scoped-1710"
HEAD = "fd80988fd1935d2274cac06a0cdb51a9b840843a"
OLD = f"{'1' * 40}..50e43f4e9ea65317b5e752d87750df2f5e85470c {'2' * 40}..{HEAD}"

ST_MODEL_TEST_SLOT = f"""# st-model-test-slot: TestSlot.tla models the test slot

## Result
Status: done
Branch: st-model-test-slot   Pull request: after the review
Reviewer: mcp:review-1710 #1

## Review
By: claudeAgent_claude_prime claude-sonnet-5-5 high #1
Verdict: clean
Head: 50e43f4e9ea65317b5e752d87750df2f5e85470c   Unchanged by the review: yes
Meets the brief: yes, 7 of 7
Findings:
- none
Sent to: not sent, jbus tells the crew when it owes a line

## Result, follow-up (2026-11-11, the pull request opened after its review)
Status: done
Branch: st-model-test-slot   Pull request: https://github.com/o/r/pull/1710
Scoped reviewer: {SCOPED}, of {HEAD}
"""


def reviewing(capsys, brief):
    capsys.readouterr()
    jbriefs.main(["line", "reviewing", str(brief)])
    return capsys.readouterr().out.strip()


def test_1710s_scoped_reviewer_that_stopped_ends_its_reviewing_once_it_writes_its_section(
    tmp_path, capsys
):
    brief = tmp_path / "st-model-test-slot.md"
    brief.write_text(ST_MODEL_TEST_SLOT)
    assert reviewing(capsys, brief) == "yes"
    why = "the reviewer stopped: this worktree is at 27df01214, and the scoped pass is of fd80988"
    stop = ["not-run", str(brief), "--head", HEAD, "--why", why]
    stop += ["--by", "By: claudeAgent claude-sonnet-5-5 high #1", "--scope", f"Scope: {OLD}"]
    assert jbriefs.main(stop) == 0
    assert reviewing(capsys, brief) == "no"


def tree(kitchen):
    """A worktree of alpha with two commits, at the second: the pull request's head is the first,
    so the tree is one commit ahead of it, as #1710's crew was with its unpushed commit."""
    path = kitchen.root / "trees" / "alpha"
    path.mkdir(parents=True)
    kitchen.git("init", "-q", "-b", "alpha", cwd=path)
    for name in ("pushed", "unpushed"):
        (path / name).write_text(f"{name}\n")
        kitchen.git("add", name, cwd=path)
        kitchen.git("commit", "-q", "-m", name, cwd=path)
    kitchen.t3.threads[0].update(worktreePath=str(path))
    pushed = subprocess.run(
        ["git", "rev-parse", "HEAD~1"], cwd=path, capture_output=True, text=True, check=True
    )
    return path, pushed.stdout.strip()


def test_a_worktree_one_commit_ahead_of_the_head_gets_no_scoped_reviewer_till_it_is_at_it(
    launched,  # noqa: F811
):
    path, head = tree(launched)
    out(launched, head=head)
    said = launched.poll()
    assert scoped(launched) == [] and keys(launched) == [] and gates(launched) == []
    assert [line for line in said if line.startswith("wait alpha: ")] == [
        f"wait alpha: #7's scoped review waits, the crew's worktree {path} is at "
        f"{_head(path)[:12]}, not {head[:12]}, or has changes not committed"
    ]
    launched.git("reset", "-q", "--hard", head, cwd=path)
    launched.poll(NOW + timedelta(minutes=3))
    assert len(scoped(launched)) == 1 and keys(launched) == [head[:12]]


def test_a_worktree_at_the_head_with_a_change_not_committed_gets_no_scoped_reviewer(
    launched,  # noqa: F811
):
    path, head = tree(launched)
    launched.git("reset", "-q", "--hard", head, cwd=path)
    (path / "scratch").write_text("not committed\n")
    out(launched, head=head)
    said = launched.poll()
    assert scoped(launched) == [] and keys(launched) == []
    assert any(line.startswith("wait alpha: #7's scoped review waits") for line in said)
    (path / "scratch").unlink()
    launched.poll(NOW + timedelta(minutes=3))
    assert len(scoped(launched)) == 1


def _head(path):
    said = subprocess.run(["git", "rev-parse", "HEAD"], cwd=path, capture_output=True, text=True)
    return said.stdout.strip()
