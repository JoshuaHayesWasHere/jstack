---
name: verify-merge-run
description: Check MergeRun.tla, a run of jmerge the pass starts with a death at each step; use when changing jbus.merge's records, the run lock, a restart, the batch record or the wait log.
paths: "features/jmerge/spec/MergeRun.tla, features/jbus/src/jbus/merge.py, features/jmerge/src/jmerge/cli.py, features/jmerge/src/jmerge/lock.py, features/jmerge/src/jmerge/rejudge.py, features/jmerge/src/jmerge/batch.py, features/jmerge/src/jmerge/waits.py"
---

# verify-merge-run

`features/jmerge/spec/MergeRun.tla` follows one run of `jmerge` that jbus's pass starts: the start stamp, the detached `keep` that holds `going.lock` and writes `ran-<at>.json`, the next pass's replace and `_judged`, and, inside jmerge under its run lock, `Repo.open_only`, `Repo.start_batch`, a restart of a queued run (`Repo.unstuck`), a merge with its wait spell, and `Repo.batched`.
Any actor can die between two of its writes.
`Inside` picks the parts a cfg follows, and `Fault` changes one thing of today's code (`replace-first`).

The rules, each with its harm, and today's verdict:

- **`RunHeard`** (breaks): every run's lines are judged once.
  Broken, what jmerge said never reaches you.
- **`StreakOnce`** (holds): the jmerge streak counts each run once.
- **`NoFalseNoRecord`** (holds): "ended with no record" only of a run with none.
  A record that names the stamp is no death, and a run slower than STARTING finds its stamp moved aside and runs nothing.
- **`DeathTold`** (holds): a run that died with no record is told.
  The pass moves the stamp to `died` before it tells and removes `died` after, and a run removes only its own stamp.
- **`OneRunAtATime`** (holds): no two runs hold the repo.
- **`RestartReopens`** (breaks): a pull request jmerge closed to restart is reopened or the user is told.
  Broken, a pull request stays closed.
- **`WaitLoggedOnce`** (holds) and **`WaitKept`** (breaks): a merged pull request's wait is logged, once.
- **`BatchMergedOnce`** (holds).

## The record

Model: `features/jmerge/spec/MergeRun.tla`
Sync: `f9f788d969e4c17b96f4e5bca43d7878bb77d810`
Covers:
- `features/jbus/src/jbus/merge.py`: `merge`, `start`, `keep`, `_stamped`, `_stamp`, `_unstamp`, `_kept`, `_told`, `_records`, `_judged`, `_sent`, `_starting`, `GOING`, `STARTED`, `DIED`, `READ`
- `features/jmerge/src/jmerge/cli.py`: `Repo.open_only`, `Repo.start_batch`, `Repo.unstuck`, `Repo.rerun_batch`, `Repo.batched`, `Repo.build_batch`, `Repo.merge_batch`
- `features/jmerge/src/jmerge/lock.py`: `running`
- `features/jmerge/src/jmerge/rejudge.py`: `BaseMerge.restart`, `BaseMerge.reopen`, `BaseMerge.reopened`, `BaseMerge.open_only`
- `features/jmerge/src/jmerge/batch.py`: `state_of`, `kind_of`, `push`, `Record.fail`, `Record.late`, `Record.prove`, `Batching.chosen`
- `features/jmerge/src/jmerge/waits.py`: `Spells.saw`, `Spells.merged`, `Spells.open_only`

At the sync commit, main's tip when this branch last took main in, the model was read against these.
`_stamped` takes `going.lock` without waiting, leaves a stamp younger than STARTING, unstamps a stale stamp a record names (`_kept`), moves any other to `died` with one `os.replace`, tells of the run once for its stamp (`_told`), removes `died`, and only then writes the new stamp, as `PassStarts`, `PassTells`, `PassUnmarks`, `PassUnstamps` and `PassStamps` say.
`keep` takes `going.lock`, runs nothing where the stamp is not its own, and writes the record, which names the stamp, before `_unstamp`.
`merge` unstamps under `going.lock` before `_unrun` when `start` fails.
`_records` replaces `ran-<at>.json` with `read.json` before `_judged` (`RunHeard`'s trace), `keep` writes the record and then unlinks the stamp whichever pass wrote it, `Repo.open_only` reopens before it drops records, `BaseMerge.restart` keeps the try, closes, keeps `closed`, then reopens and keeps `took`, and `Spells.merged` appends the log line before it writes the spells without the merged one.
#1748 (1e8535dc7) changed `merge.py` and the model together, and no other covered file changed from the first sync, 8f4c21b6f, to this one; `features/jmerge/tests/test_merge_run_spec.py` passed there (23 passed).
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, a new writer of the pass's run directory, `base-merges.json`'s restarts, the batch record or the wait log, or a cfg or the spec.
The test also fails when a quote of the spec no longer stands once in its file: move the quote with the code, then rerun.

## Run it

```sh
uv run pytest features/jmerge/tests/test_merge_run_spec.py -q
```

It runs TLC on each cfg and each rule alone in under half a minute, and skips where no Java runs TLC.
The bare TLC command and the table of rules, cfgs and verdicts are in `features/jmerge/spec/README.md`, "The rules of the run, and today's verdicts"; run TLC in a copy of the folder, since it writes `states/` where it runs.

- **Bounds:** `MaxRuns = 2`, `MaxTicks = 2`, `ReplyLost = TRUE`; `MergeRun.cfg` follows no part (`Inside = {}`), its comment's 101,832 distinct states a count from before #1748, and `MergeRun.restart.cfg`, `.batch.cfg` and `.waits.cfg` each follow one part.
- **The faults:** `judge-first` holds `RunHeard` and breaks `StreakOnce`; `unlink-first`, the stamp code before #1748, is the canary that breaks `NoFalseNoRecord` and `DeathTold`; `fresh-list` holds `RestartReopens`; `no-run-lock` is the canary that breaks `OneRunAtATime`; `log-on-sweep` breaks `WaitLoggedOnce`.
- **Assumptions:** no time past STARTING, RESTART_MINUTES and PENDING_MINUTES, which TLC chooses; two pull requests stand for every other; the rest is in the README's "What MergeRun leaves out".

## A real bug or a modeling error

Each step of a trace quotes the code that takes it.
Open each quote at its file and check the write order still is the step's; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the run's story (pass, keep, jmerge, death), and leave the rule as it is.

## Change the model when the code changes on purpose

- A fix that reorders writes: change the step, rerun every cfg, and move the README's verdict table and the cfg's comment with what TLC prints.
- A new carrier of the ledger's MergeRun rows: give it a variable whose comment quotes its writer.

## Drift at the sync commit

None found in the steps.
`MergeRun.cfg`'s comment still gives 101,832 distinct states for the whole space, a count from before #1748 added the pass's lock and three pass steps; it was not run again here.
The README and spec say "main aa5469d97"; the one covered change from there to the first sync, 23f42940f, moved the import of `stacked` in `cli.py` and changed no step.
