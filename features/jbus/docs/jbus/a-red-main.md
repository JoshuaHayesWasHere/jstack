# A red main

A pass watches the check of the default branch, `main`, after each merge.
A failed check on main within a day of a merge is `retro <slug>: main check failed at <sha12>, <n> merges since the last green`.
A red main holds every pull request but its fix's, and jbus files the brief for that fix.

## The fix's brief

When `<sha12>` is main's tip as the pass reads it, the pass writes `tasks/main-red-<sha12>.md` in the home's state.
The brief holds the URL of each failed job, the failed test ids its log names, the merges since the last green and the files they changed, `Playbook: bug-fix` and `Size: S`.
The pass queues it with no go (`queue add`) at the top priority of its project, one below the lowest `priority` of its rows (0 where there are none), so it is the next launch there once you approve it.

- A pass files it whenever the queue has no `main-red-<sha12>` row, so a pass that stopped before the row was added files it on the next, and a removed row is not filed again.
- A red commit that a later commit on main superseded is filed by no pass, the first after jbus starts included: only a red tip is a main to fix.
- A project's first pass files none, and neither does a pass for a merged slug that was removed: a red tip the first pass found is filed by the next.
- A `main-red-<sha12>` row that has not launched when main's tip is green again is left as it is, and the pass says once, quietly, `retro main-red-<sha12>: main is green again at <sha12>, and its row is left as it is`.
- A queue that refuses the brief is a `condition` line.

A slug that starts `main-red-` is read as such a fix, so name no brief of your own that way.

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

A run of main that was cancelled is no failed check, whether its check run ended `cancelled` or it was cancelled before it had a job and left the commit with no check run.
jbus asks GitHub to run it again (`gh run rerun <id>`) while GitHub's `run_attempt` for it is 1.
It says `retro <slug>: main check cancelled twice at <sha>` when a later attempt is cancelled too, and `retro <slug>: main check cancelled at <sha>, and GitHub did not run it again` when GitHub refuses.
A job that `timeout-minutes` stops also ends `cancelled`, not `timed_out`, so a suite that hangs on main is run again and then reads `cancelled twice`, never `main check failed`.
