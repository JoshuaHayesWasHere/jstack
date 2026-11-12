# A run of jmerge the pass started: MergeRun.tla

`MergeRun.tla` follows one run of `jmerge` that jbus's pass starts, as the code of main aa5469d97 takes it, with a death at each step.
The pass (`jbus.merge.merge`) writes a start stamp and starts a detached process (`keep`), which holds `going.lock`, runs `jmerge --if-free` and writes what it printed to `ran-<at>.json`.
The next pass reads each record: it sends its lines (`_judged`), counting the run on the jmerge streak once for the record's `at`, then replaces `ran-<at>.json` with `read.json`.
Inside, `jmerge` holds the repo's run lock and goes in the order of `jmerge.cli`: `Repo.open_only` settles the restarts a run left owed, `Repo.start_batch` reads where the batch stands, the judge loop restarts a pull request whose run GitHub left queued (`Repo.unstuck`) or merges one and closes its wait spell, and `Repo.batched` merges a proven batch or builds the next.
The merge tick runs `jmerge --if-free` too.
Each carrier of the st-state-ledger ledger's MergeRun rows (B-059 to B-063, C-023, C-029, C-031, C-033, C-043, C-044) has its variable, whose comment quotes the code that writes it.
The batch's state is `batch.state_of`'s six values, with the three PrVerdict.batch lacks: proven, late and rerun.
`features/jmerge/tests/test_merge_run_spec.py` finds each quote once in its file, checks each carrier has its variable, and runs TLC on each config and on each rule alone.

The constant `Inside` names the parts of jmerge's run a config follows (restart, batch, waits).
The parts share nothing but the run lock and a death, and all of them together with two pass runs is past 58M states, so each config follows the parts its rules read.
`Fault = "judge-first"` is today's code; each other value changes one thing of it: `replace-first` replaces the record before it sends the lines, `unkeyed` sends them first with no key on the streak, `tell-clears` keys the streak but clears the key on a count with no key (`_unrun` of a run with no record), `fresh-list` reads whether a pull request is open from GitHub in the run, `no-run-lock` is the canary of `OneRunAtATime`, and `unlink-first` is the start stamp as it was before the stamp named its run, the canary of `NoFalseNoRecord` and `DeathTold`.
`ReplyLost` is the world: GitHub took a close whose reply gh lost.

## The rules of the run, and today's verdicts

| Rule | Config | Today | Notes |
|---|---|---|---|
| `RunHeard`: every run's lines are judged once | `MergeRun.cfg` | holds | the lines are sent before the replace; `replace-first` breaks it: the pass replaces the record, then dies before `_judged` |
| `StreakOnce`: the jmerge streak counts each run once | `MergeRun.cfg` | holds | the streak counts a run once for its record's `at`; `unkeyed` breaks it: a pass that dies after `_judged` and before the replace counts the run twice; so does `tell-clears`, where the pass that reads the record again first tells of a run with no record |
| `NoFalseNoRecord`: "ended with no record" only of a run with none | `MergeRun.cfg` | holds | a record that names the stamp is no death, and a run slower than STARTING finds its stamp moved aside and runs nothing; `unlink-first` breaks it |
| `DeathTold`: a run that died with no record is told | `MergeRun.cfg` | holds | the pass moves the stamp to `died` before it tells, and removes `died` after, and a run removes only its own stamp; `unlink-first` breaks it |
| `OneRunAtATime`: no two runs hold the repo | `MergeRun.cfg` | holds | `no-run-lock` breaks it: `going.lock` alone lets a run outlive its process |
| `RestartReopens`: a pull request jmerge closed to restart is reopened or the user is told | `MergeRun.restart.cfg` | breaks | a close whose reply gh lost keeps a refusal that owes no reopen; and with no reply lost, a pass's list read before the tick closed it marks its reopen `took`; `fresh-list` holds it |
| `WaitLoggedOnce`: a merged pull request's wait is logged once | `MergeRun.waits.cfg` | holds | `Spells.merged` runs only at the merge; `log-on-sweep` breaks it: a run that died between the append and the drop leaves a spell the sweep logs again |
| `WaitKept`: a merged pull request's wait is logged | `MergeRun.waits.cfg` | breaks | jmerge dies between the squash and `Spells.merged`; a batch squashes every member before any is said |
| `BatchMergedOnce` | `MergeRun.batch.cfg` | holds | a crash after the squashes leaves `state_of` none, since main moved |

```sh
cd features/jmerge/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config MergeRun.cfg MergeRun.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
Each config's comment keeps TLC's verdict and the trace it prints.

## Draw the chart of the run

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
W=$(mktemp -d) && cp features/jmerge/spec/MergeRun.* "$W"
(cd "$W" && UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec MergeRun.tla --config MergeRun.chart.cfg \
    --title "jbus's pass starts a run of jmerge: does what it said reach you?" --out out)
```

Run it from the repo root, and copy the files of `$W/out`, but its `tlc/`, into `MergeRun-statechart/`.
`MergeRun.chart.cfg` has one pass run and no tick (191 model states), labelled by `MergeRun.map.py`: 21 chart states and 30 of its 41 steps, and no bug path: RunHeard, NoFalseNoRecord and DeathTold hold on it.
The two-run stories are `MergeRun.cfg`'s, which the test checks.

## What MergeRun leaves out

- The run's own lines and what jbus does with them: a record is heard or not, and `Said.failed` is not modelled.
- A start that fails (`start` returns why), `child.log`, the systemd unit against a session of its own past whether jmerge outlives its process, and a stamp that does not parse.
- Time, past STARTING, RESTART_MINUTES and PENDING_MINUTES: TLC chooses when each has gone by.
- Of the restart: the queued run itself, `gave_up`, the line it holds, and a user who reopens by hand.
- Of the batch: its members one by one, a guards batch's run, the merge lock another run holds, the main-red and switch-off skips, a failed job with no run to rerun, and `failed` heads; `most` is three levels, 5, 12 and 48, which keep what `_full` reads.
- Two pull requests stand for every other: P, restarted, and W, merged alone.
