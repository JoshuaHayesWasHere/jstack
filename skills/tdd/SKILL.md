---
name: tdd
description: "Use for /tdd: fix a bug test-first, with a focused regression test that fails before the fix and passes after it. For a bug with a clear, cheap test path. Skip when the test path is unclear, expensive or integration-heavy."
tip: fixes a bug test-first, with a regression test that fails before the fix | fix this bug | fix the bug | regression test | failing test first | test first
disable-model-invocation: true
card: "Distrust the change | 3 | Fixes a bug test-first: a focused regression test that fails before the fix and passes after it. | Reach for it when a bug has a clear, cheap test path. | op: the operator"
---

# TDD Bug Fix

Source: pstack, `pstack/skills/tdd/SKILL.md`

When fixing a bug with a clear, cheap test path, make the broken behavior executable before changing production code.
The goal is a focused regression test that fails before the fix and passes after it.

Run this first:

```sh
if R=$(realpath ~/.claude/skills/tdd/../.. 2> /dev/null) && [ -f "$R/playbooks/bug-fix.md" ]; then
    echo "$R"
else
    echo "no root: ~/.claude/skills/tdd is not a link into the repo this skill lives in"
fi
```

It prints the root of the repo this skill lives in.
Every path below that starts with `playbooks/`, `principles/` or `skills/` is from that root, and a path that starts with `references/` is beside this file.
On `no root` the skill was loaded from somewhere else: the root is two directories above the real place of this file, not of a link to it.

## Workflow

The workflow is written once, in `playbooks/bug-fix.md`: the repro, the failing test seen to fail for the intended reason, the fix at the root cause, the proof, and the commit of the failing test before the fix.
Read it and run its steps 1 to 6 in this thread, in order, as written.
Its step 7 opens a pull request the way a crewmate does: run it in a crewmate's thread.
In any other thread run the repo's check command in its place, and stop.

That playbook is written for a crewmate.
In a thread with no brief, its "Result" is your reply to the user, and the brief's **Where** in its step 4 is the files the user's request names.
Its step 6 commits, and such a thread commits only when the user asked for commits, and never on the default branch: otherwise leave the test and the fix uncommitted and say so.

The rest of this file is what the source says and the playbook does not.

## When no test is written

The playbook names three reasons to write no test: a broad harness, brittle mocks, slow infrastructure.
Three more count: the bug needs production-only state, its reproduction steps are vague, or the test would churn large unrelated fixtures.
Browser automation and a snapshot comparison are checks that can stand in, beside the ones the playbook lists.

A bad test is one that mostly tests mocks, encodes current implementation details, depends on timing or unrelated global state, needs expensive infrastructure for a small fix, or would be deleted immediately after proving the fix.

## Guardrails

- Keep the regression test focused on the bug.
  Avoid broad fixture churn or unrelated coverage expansion.
- If the bug is flaky, make the test deterministic where possible and document the signal being locked down.

## Final Response

Report the evidence, not just the outcome, as the playbook's "Hand over" has it: the failing-before check and the failure it produced, the passing-after run, and any nearby validation performed.
