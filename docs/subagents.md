# Subagents

Shared rules for every subagent a jstack skill spawns. Adapted from the
Subagents section of pstack's `poteto-mode`.

## Defaults for every spawn

- Run it in the background, in agent mode (read-only strips tools), with file
  pointers instead of inlined context.
- Give every role an explicit model from [models.md](models.md). Code
  playbooks read their own line (`feature, refactoring`, `bug-fix`,
  `perf-issue`, or `hillclimb`). Prose and judgment read `judgment and prose`.
  Trivial mechanical edits read `swarm workers`.
- Open every brief with the goal. Point the subagent at
  `~/repos/jstack/docs/harness/README.md` and this file before the task.

## Match the model to the job

Start from the role's line, keep its model, and set the effort the job needs.
Raise one step, up to `xhigh`, for the hardest or subtlest work. Lower one
step for judgment, and two or more for routine work. No role runs above
`xhigh`. Verification always runs on the `swarm workers` model.

Fable 5.2 runs outside a panel only when the user named it for this task, or
when two Opus 5.5 `xhigh` runs of the same brief failed their check. Say which.
Difficulty alone never qualifies.

If a tool rejects a model or effort, never pass it again. Fall back to the
role's line, then the calling skill's fallback, then the closest valid model
of the same family, then omit `model`. Say so.

## Ownership

You own every subagent's work. Review the diff and write your own summary. A
second opinion is the same prompt on another vendor's model.

Give a fix round, a follow-up, a retry, or the next queue item to a fresh
subagent with the original brief, every later directive, and the prior
agent's report and branch. Resume an existing subagent only when the work
needs state that lives in it and is costly to move: its checkout, its
uncommitted changes, or a process it still runs.
