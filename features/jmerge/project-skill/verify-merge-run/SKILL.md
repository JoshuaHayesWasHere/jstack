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

- **`RunHeard`** (breaks): every run's lines are judged once. Broken, what jmerge said never reaches you.
- **`StreakOnce`** (holds): the jmerge streak counts each run once.
- **`NoFalseNoRecord`** (breaks): "ended with no record" only of a run with none.
- **`DeathTold`** (breaks): a run that died with no record is told.
- **`OneRunAtATime`** (holds): no two runs hold the repo.
- **`RestartReopens`** (breaks): a pull request jmerge closed to restart is reopened or the user is told. Broken, a pull request stays closed.
- **`WaitLoggedOnce`** (holds) and **`WaitKept`** (breaks): a merged pull request's wait is logged, once.
- **`BatchMergedOnce`** (holds).

## The record

Model: `features/jmerge/spec/MergeRun.tla`
Sync: `8f4c21b6f59fc1bfbccace831d3a916bae72fb5d`
Covers:
- `features/jbus/src/jbus/merge.py`: `merge`, `start`, `keep`, `_records`, `_judged`, `_sent`, `_starting`, `STARTED`, `READ`
- `features/jmerge/src/jmerge/cli.py`: `Repo.open_only`, `Repo.start_batch`, `Repo.unstuck`, `Repo.rerun_batch`, `Repo.batched`, `Repo.build_batch`, `Repo.merge_batch`
- `features/jmerge/src/jmerge/lock.py`: `running`
- `features/jmerge/src/jmerge/rejudge.py`: `BaseMerge.restart`, `BaseMerge.reopen`, `BaseMerge.reopened`, `BaseMerge.open_only`
- `features/jmerge/src/jmerge/batch.py`: `state_of`, `kind_of`, `push`, `Record.fail`, `Record.late`, `Record.prove`, `Batching.chosen`
- `features/jmerge/src/jmerge/waits.py`: `Spells.saw`, `Spells.merged`, `Spells.open_only`

At the sync commit, main's tip when this branch took main in, the model was read against these: `merge` unlinks a stale stamp before `_unrun` and then writes the new one, `_records` replaces `ran-<at>.json` with `read.json` before `_judged` (`RunHeard`'s trace), `keep` writes the record and then unlinks the stamp whichever pass wrote it, `Repo.open_only` reopens before it drops records, `BaseMerge.restart` keeps the try, closes, keeps `closed`, then reopens and keeps `took`, and `Spells.merged` appends the log line before it writes the spells without the merged one.
No covered file changed between the model's commit (1e09951f9, #1713) and the sync, and `features/jmerge/tests/test_merge_run_spec.py` passed there.
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

- **Bounds:** `MaxRuns = 2`, `MaxTicks = 2`, `ReplyLost = TRUE`; `MergeRun.cfg` with `Inside = {}` has 101,832 distinct states, and `MergeRun.restart.cfg`, `.batch.cfg` and `.waits.cfg` each follow one part.
- **The faults:** `judge-first` holds `RunHeard` and breaks `StreakOnce`; `fresh-list` holds `RestartReopens`; `no-run-lock` is the canary that breaks `OneRunAtATime`; `log-on-sweep` breaks `WaitLoggedOnce`.
- **Assumptions:** no time past STARTING, RESTART_MINUTES and PENDING_MINUTES, which TLC chooses; two pull requests stand for every other; the rest is in the README's "What MergeRun leaves out".

## A real bug or a modeling error

Each step of a trace quotes the code that takes it.
Open each quote at its file and check the write order still is the step's; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the run's story (pass, keep, jmerge, death), and leave the rule as it is.

## Change the model when the code changes on purpose

- A fix that reorders writes: change the step, rerun every cfg, and move the README's verdict table and the cfg's comment with what TLC prints.
- A new carrier of the ledger's MergeRun rows: give it a variable whose comment quotes its writer.

## Drift at the sync commit

None found in the steps. The README and spec say "main aa5469d97"; the one covered change from there to the sync, 23f42940f, moved the import of `stacked` in `cli.py` and changed no step.
