"""The reviewer's scoped pass: one review of what a rebase changed in a reviewed patch.

The tests run the block of the skill's "A scoped pass" as a reviewer runs it, in a real repo,
with the two ranges of the message jbus sends. The reviewer writes the section that the
block's output asks for. `jmerge` then reads that section, and the section lets it merge the
rebased head.
"""

import os
import re
import subprocess
import textwrap
from itertools import takewhile

import test_jmerge_rangediff as rebases
import test_jmerge_run as jrun
import test_pr_review_skill as reviews
from jbus import rebase
from test_home_merge import FENCED, git, review
from test_home_thread import as_read
from test_pr_review_skill import reviewer
from testing.layouts import assembled

SKILL = reviews.SKILL
__all__ = ["reviewer"]


SECTION = as_read(SKILL).split("\n### A scoped pass\n")[-1].split("\n## ")[0]
MESSAGE = re.compile(r"^(/pr-review run (\S+) scoped (\S+) (\S+))$")


def asked(number, command):
    """The message jbus launches the scoped reviewer with for the line `jmerge` prints. The match
    that this returns holds the message's parts as its groups."""
    line = (
        f"wait {number} https://example.test/pull/{number}: the rebase changed the content "
        f"after its review; scoped review of {command}"
    )
    _, _, ask = rebase.content(line)
    return MESSAGE.search(ask.message.format(number=number, slug="alpha"))


def scoped(tree, old, new):
    """Run the section's block in a worktree, with the two ranges of the message."""
    (block,) = [body for body in FENCED.findall(SECTION) if "<new range>" in body]
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
            "T": str(assembled() / "templates"),
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


def test_a_stopped_scoped_pass_is_told_to_write_the_section_a_stop_gives(tmp_path, reviewer):
    """A scoped reviewer that read only step 1, as #1710's and #1708's did, ended on its "no
    section" and left its seat open and the brief `reviewing` for hours. Its stop line sends it
    to "A stop", no line of the skill tells it to write none, and that block writes the section."""
    (said,) = [line for line in SECTION.splitlines() if line.strip().startswith("On `stop`")][:1]
    assert 'write the section "A stop" says' in said
    whole = as_read(SKILL).splitlines()
    assert [
        line
        for line in whole
        if all(word in line for word in ("stop", "scoped pass", "no section"))
    ] == []
    assert "no section" not in said
    (tmp_path / "repo").mkdir()
    branch = rebases.Branch(tmp_path / "repo")
    branch.theirs({11: "theirs 11"})
    verdict = branch.rebase({11: "the task 11, and theirs"})
    git(branch.main, "checkout", "-q", "alpha")
    rebases.commit(branch.main, "one more", {30: "one more"})
    _, _, old, new = asked(7, verdict.command).groups()
    (stop,) = scoped(branch.main, old, new)
    fill = {
        "<the head the review was to be of>": new.split("..")[1],
        "<the stop line the step printed>": stop,
        "<the By: line Start printed>": "By: inherit #1",
        "scope=''": f"scope='Scope: range-diff {old} {new}'",
    }
    assert reviewer.output("### A stop", fill=fill) == [
        f"written: ## Review with Verdict: not run, in {reviewer.brief}"
    ]
    written = reviewer.brief.read_text().split("\n## Review\n")[-1]
    assert f"Scope: range-diff {old} {new}\n" in written
    assert f"Head: {branch.head}   Unchanged by the review: not checked" in written


def test_ranges_git_cannot_compare_stop_the_pass(tmp_path):
    branch = rebases.Branch(tmp_path)
    branch.theirs({8: "theirs 8"})
    branch.rebase()
    git(branch.main, "checkout", "-q", "alpha")
    first, *_ = scoped(branch.main, f"{'9' * 40}..{'8' * 40}", f"{branch.tip}..{branch.head}")
    assert first == "stop: git range-diff could not compare the two ranges"


def test_a_scoped_review_at_the_rebased_head_makes_the_pull_request_ready(proven_merged, rules):
    rebased = rebases.Rebased(proven_merged, {11: "theirs 11"}, rebases.BOTH).push_code()
    (waits,) = jrun.jmerge(proven_merged, rules, "--check")
    assert waits == rebased.waits()
    _, slug, old, new = asked(7, waits.split("scoped review of ")[1]).groups()
    scope, head, *_ = scoped(proven_merged.tree, old, new)
    section = (
        f"## Review\nVerdict: clean\n{scope}\n{head}   Unchanged by the run: yes\nFindings:\nnone\n"
    )
    rebased.brief(review("clean", rebased.before) + section)
    assert jrun.jmerge(proven_merged, rules, "--check") == [f"ready 7 {rebased.head} {slug} alpha"]
