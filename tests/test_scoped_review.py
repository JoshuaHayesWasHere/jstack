"""The reviewer's scoped pass: one review of what a rebase changed in a reviewed patch.

The block of the skill's "A scoped pass" is run as a reviewer runs it, in a real repo, with
the two ranges of the message jbus sends. The section it leads to is then read by `jmerge`,
which merges the rebased head on it."""

import os
import re
import subprocess
import textwrap
from itertools import takewhile

import test_jmerge_guarded as guarded
import test_jmerge_rangediff as rebases
import test_pr_review_skill as reviews
from jbus import rebase
from test_home_merge import FENCED, git, review
from test_home_thread import as_read

SKILL = reviews.SKILL


SECTION = as_read(SKILL).split("\n### A scoped pass\n")[-1].split("\n## ")[0]
MESSAGE = re.compile(r"`(/pr-review run (\S+) scoped (\S+) (\S+))`")


def asked(number, command):
    """The launch message jbus gives the crew for the line `jmerge` prints, and its parts."""
    line = (
        f"wait {number} https://example.test/pull/{number}: the rebase changed the content "
        f"after its review; scoped review of {command}"
    )
    _, _, ask = rebase.content(line)
    return MESSAGE.search(ask.message.format(number=number, slug="alpha"))


def scoped(tree, old, new):
    """Run the section's block in a worktree, with the two ranges of the message."""
    (block,) = [body for body in FENCED.findall(SECTION) if "<old range>" in body]
    script = textwrap.dedent(block).replace("<old range>", old).replace("<new range>", new)
    assert "<" not in script.replace("<<", "")
    ran = subprocess.run(["sh", "-c", script], cwd=tree, capture_output=True, text=True)
    assert (ran.returncode, ran.stderr) == (0, "")
    return ran.stdout.splitlines()


def test_the_message_jbus_sends_is_the_one_the_section_takes():
    old, new = f"{'1' * 40}..{'a' * 40}", f"{'2' * 40}..{'c' * 40}"
    sent = asked(7, f"git range-diff --no-color {old} {new}")
    (taken,) = set(re.findall(r"`(/pr-review run <slug> scoped [^`]+)`", SECTION))
    filled = taken.replace("<slug>", "alpha").replace("<old range>", old)
    assert sent[1] == filled.replace("<new range>", new)


def test_a_brief_with_a_review_is_launched_for_a_scoped_pass_and_refused_for_a_first(tmp_path):
    lines = as_read(SKILL).splitlines()
    (start,) = [n for n, line in enumerate(lines) if "is refused: say so" in line]
    item = [lines[start]] + list(takewhile(lambda line: line.startswith("   "), lines[start + 1 :]))
    (scoped_pass,) = [line.strip() for line in item if line.strip().startswith("A scoped pass")]
    (first_line,) = re.findall(r"`(PASS=\w+)`", scoped_pass)
    launcher = reviews.Launcher(tmp_path)
    launcher.brief.write_text(reviews.BRIEF + reviews.DONE + "\n## Review\nVerdict: clean\n")
    script = reviews.readiness().replace("<slug>", "a-task")
    assert "PASS=first\n" in script

    def says(script):
        env = {
            **os.environ,
            "PATH": f"{launcher.stub}:{os.environ['PATH']}",
            "STUB": str(launcher.stub),
            "H": str(launcher.state),
            "T": str(reviews.REPO / "templates"),
        }
        ran = subprocess.run(["sh", "-c", script], capture_output=True, text=True, env=env)
        return ran.stdout.splitlines()

    assert says(script) == [
        "a-task: not ready, it has a review or a reviewer, and it is one pass per pull request"
    ]
    assert says(script.replace("PASS=first\n", f"{first_line}\n")) == [
        f"a-task: ready, {reviews.URL} at {reviews.HEAD}"
    ]


def test_the_block_prints_the_scope_and_head_lines_and_the_range_diff(tmp_path):
    branch = rebases.Branch(tmp_path)
    branch.theirs({11: "theirs 11"})
    verdict = branch.rebase({11: "the task 11, and theirs"})
    assert not verdict.clean
    git(branch.main, "checkout", "-q", "alpha")
    _, _, old, new = asked(7, verdict.command).groups()
    scope, head, *shown = scoped(branch.main, old, new)
    assert (
        scope == f"Scope: range-diff {branch.base}..{branch.reviewed} {branch.tip}..{branch.head}"
    )
    assert head == f"Head: {branch.head}"
    ran = subprocess.run(verdict.command.split(), cwd=branch.main, capture_output=True, text=True)
    assert shown == ran.stdout.splitlines() != []


def test_a_head_that_moved_since_jbus_asked_stops_the_pass(tmp_path):
    branch = rebases.Branch(tmp_path)
    branch.theirs({11: "theirs 11"})
    verdict = branch.rebase({11: "the task 11, and theirs"})
    git(branch.main, "checkout", "-q", "alpha")
    pushed = rebases.commit(branch.main, "one more", {30: "one more"})
    _, _, old, new = asked(7, verdict.command).groups()
    assert scoped(branch.main, old, new) == [
        f"stop: this worktree is at {pushed}, and the scoped pass is of {branch.head}"
    ]


def test_ranges_git_cannot_compare_stop_the_pass(tmp_path):
    branch = rebases.Branch(tmp_path)
    branch.theirs({8: "theirs 8"})
    branch.rebase()
    git(branch.main, "checkout", "-q", "alpha")
    first, *_ = scoped(branch.main, f"{'9' * 40}..{'8' * 40}", f"{branch.tip}..{branch.head}")
    assert first == "stop: git range-diff could not compare the two ranges"


def test_a_scoped_review_at_the_rebased_head_makes_the_pull_request_ready(proven_merged, rules):
    rebased = rebases.Rebased(proven_merged, {11: "theirs 11"}, rebases.BOTH)
    (waits,) = guarded.jmerge(proven_merged, rules, "--check")
    assert waits == rebased.waits()
    _, slug, old, new = asked(7, waits.split("scoped review of ")[1]).groups()
    scope, head, *_ = scoped(proven_merged.tree, old, new)
    section = (
        f"## Review\nVerdict: clean\n{scope}\n{head}   Unchanged by the run: yes\nFindings:\nnone\n"
    )
    rebased.brief(review("clean", rebased.before) + section)
    assert guarded.jmerge(proven_merged, rules, "--check") == [
        f"ready 7 {rebased.head} {slug} alpha"
    ]


def test_a_scoped_review_with_a_finding_waits_for_it_to_be_handled(proven_merged, rules):
    rebased = rebases.Rebased(proven_merged, {11: "theirs 11"}, rebases.BOTH)
    section = review("findings", rebased.head).replace(
        "Verdict: findings\n", f"Verdict: findings\nScope: range-diff {rebased.command()[28:]}\n"
    )
    rebased.brief(review("clean", rebased.before) + section)
    (said,) = guarded.jmerge(proven_merged, rules, "--check")
    assert said.endswith(": its findings are not handled: the Result has no Fixed line")
