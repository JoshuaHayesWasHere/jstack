---
name: show-me-your-work
description: Keep a decision log for long or unattended work, one TSV row per decision (what, why, evidence, result), so the user can review it after stepping away. Use for /show-me-your-work, or when a playbook step names this skill.
tip: keeps a decision log you can review after stepping away | decision log | while i'm away | i'm stepping away | unattended | overnight
disable-model-invocation: true
card: "Catch up and keep track | 4 | Keeps a decision log for long or unattended work, one row per decision: what, why, the evidence and the result. | Reach for it when a run goes on with nobody watching and will be reviewed later. | op: the operator; plain: a step of `autonomous-run`, `hillclimb`"
---

# Show me your work

Keep one log for the task. Other skills and playbooks send their trail here and do not make up a format of their own.

## The format

One TSV file, one row per decision, six columns. A cell stays on one line.

- **ts.** The time, ISO 8601, in UTC. The script stamps it.
- **phase.** The phase or workstream. In a loop, the attempt: `a1`, `a2`.
- **decision.** What was chosen or done, in one line.
- **why.** The reason, in plain words.
- **evidence.** A pointer that proves it: a commit, a pull request number, `file:line`, the path of an output. Never a paragraph.
- **result.** The outcome, or the state of the predicate: `kept`, `reverted`, `check passes`, `inconclusive`, `open`.

An example, as a reviewer would read it:

```text
ts	phase	decision	why	evidence	result
2026-05-24T09:40:00Z	harness	froze the harness at 7 runs a side	one run moved by more than the change we look for	commit 3a9f1c2	baseline 41 ms, range 40 to 43
2026-05-24T11:15:00Z	a1	parse the header once, not per row	the profile had 60% of the time in the header parse	commit 7c21e0a	kept, 41 ms to 33 ms
2026-05-24T12:30:00Z	a2	cache the lookup table	the profile's next entry	reverted, no commit	reverted, 33 ms to 33 ms
```

## Logging a row

Run this, with the five cells filled in. It prints the log's path and how many rows it holds:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
S=$(realpath -q ~/.claude/skills/crew/../show-me-your-work || true)
L=${L:-$(git rev-parse --absolute-git-dir 2> /dev/null || pwd)/decisions.tsv}
if [ ! -f "$S/scripts/log.sh" ]; then
    echo "no row: scripts/log.sh of this skill was not found by way of ~/.claude/skills/crew"
elif sh "$S/scripts/log.sh" "$L" "<phase>" "<decision>" "<why>" "<evidence>" "<result>"; then
    echo "$L: $(($(wc -l < "$L") - 1)) rows"
fi
```

`scripts/log.sh` is beside this file. It stamps `ts`, writes the header on first use, turns a tab or a newline inside a cell into a space, and puts a single quote before a cell that starts with `=`, `+`, `-` or `@`, so that evidence somebody else wrote is not run as a formula when the log is opened in a spreadsheet. Write no row by hand.

Write each row the way you would tell a teammate what you did: plain words, concrete actions. `skills/unslop/SKILL.md`, from the root of the repo this skill lives in, applies to log text too.

Log decisions and checkpoints, not every action: a fork chosen, a unit finished with what its check printed, a pivot or a revert with what set it off, a blocker, a gate parked. In a loop, one row per attempt, kept or reverted. Skip what is trivial.

A thread that adds to a log another thread wrote makes its first row one with phase `start`: the decision says which earlier rows are not its own, and the evidence names this thread. Use `start` for nothing else.

## Where it lives

The log is a working file, not part of the change. Its default place is `decisions.tsv` in the worktree's git directory, which is what the block above uses: it is out of the tree, so nothing has to ignore it, and each worktree has its own. Put `L=<path>` on a line before the block for another place. The log goes when the worktree is removed, so the Result carries what a later reader needs: the number of rows, and each kept change on one line.

Commit it into the tree only when the brief says so.

## Rules

- Append only. A wrong call gets a new row that says what replaced it. Never edit or delete a row.
- Prefer evidence that a committed script prints over a one-off made by hand.

## Check the log before handing over

At the end of the task, before the Result is written, read the log top to bottom (`column -s "$(printf '\t')" -t <the log>` prints it as a table) and walk your own rows against what happened:

- Every row is a real decision or action.
- Each row's evidence resolves and shows what the row says: `git cat-file -e <commit>` for a commit, the file read for a path.
- A fork, a pivot or an approach given up that shaped the work and has no row is a gap. Add the row.

Correct the log, not the story: a wrong row gets a new row after it with what happened and a pointer that resolves. Rows another thread wrote are not yours to check, but one your own work shows to be wrong gets a row the same way.

Then write in the Result: the log's path and its number of rows on the `Proof:` line, and under "Noticed" each row whose evidence is weak or missing, each check claimed and not run, and each choice that looks risky now. "No flags" is an answer. The pull request's reviewer is the second reader, in a new thread: no subagent reviews the trail.
