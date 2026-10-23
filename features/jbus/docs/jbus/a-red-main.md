# A red main

A pass watches the check of the default branch, `main`, after each merge.
When main's check fails within a day of a merge, the pass reports `retro <slug>: main check failed at <sha12>, <n> merges since the last green`.
While main is red, every pull request waits except the one that fixes main, and jbus files the brief for that fix.

## The fix's brief

If `<sha12>` is still main's tip when the pass reads main, the pass writes `tasks/main-red-<sha12>.md` in the home's state.
The brief holds:

- the URL of each failed job;
- the failed test ids that its log names;
- the merges since the last green, with the files they changed;
- `Playbook: bug-fix` and `Size: S`.

The pass queues it with no go (`queue add`), at the top of its project.
Its `priority` is one less than the lowest `priority` among the project's rows, or 0 when there are none.
So once you approve it, it is the next launch in that project.

- A pass files it whenever the queue has no `main-red-<sha12>` row.
  So if a pass stopped before it added the row, the next pass files it, and a removed row is not filed again.
- No pass files a red commit that a later commit on main superseded, not even the first pass after jbus starts.
  Only a red tip is a main to fix.
- A project's first pass files no brief, and neither does a pass for a merged slug that was removed.
  The next pass files a red tip that the first pass found.
- When main's tip is green again and a `main-red-<sha12>` row has not launched, the pass leaves the row as it is.
  It says so once, in a quiet line: `retro main-red-<sha12>: main is green again at <sha12>, and its row is left as it is`.
- If the queue refuses the brief, the pass reports a `condition` line.

jbus reads a slug that starts `main-red-` as the fix of a red main, so do not give a brief of your own such a slug.

## `main.json`

The one record of a red main is `main.json` beside the queue.
The pass that tells a red pull request that main is green again writes it (`features/jbus/src/jbus/mainmoved.py`), whether or not a pull request merged lately.

| Field | Holds |
|---|---|
| `broken` | The tip whose check failed, kept until a green tip follows. While main's tip is not green, it is the red main. |
| `green` | The last tip whose check passed. |
| `fixed` | The green tip, written by a pass that still owes a crew its message and keeps the old commit to look at again. Main reads as green from that pass on. |

A tip whose check has not ended or was cancelled changes neither field, so a main stays red until a later tip is green.
`jmerge` reads the file ("Main is not red, or it is the fix of a red main" in [jmerge](../../../jmerge/docs/jmerge.md)).

## A cancelled run

A cancelled run of main is not a failed check.
That holds when its check run ended `cancelled`, and also when the run was cancelled before it had a job, so the commit has no check run.
jbus asks GitHub to run it again (`gh run rerun <id>`) while GitHub's `run_attempt` for it is 1.
It says `retro <slug>: main check cancelled twice at <sha>` when a later attempt is cancelled too, and `retro <slug>: main check cancelled at <sha>, and GitHub did not run it again` when GitHub refuses.
A job that `timeout-minutes` stops also ends `cancelled`, not `timed_out`.
So jbus runs a suite that hangs on main again, and then reports `cancelled twice`, never `main check failed`.
