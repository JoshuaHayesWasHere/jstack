---
name: verify-flow-today
description: Rerun TLC on FlowToday.tla, the model of today's merge flow (two rows, their checks, reviews and merges, jmerge's batch and line, main going red and its fix, a machine a crew can leave full), and read what it finds. Use on any change to how jmerge judges, batches, lines up or merges a pull request (`jmerge/cli.py` `Repo`, `batch.py`, `ready.py`, `rows.py`, `rejudge.py`), to jbus's launch room, stray sweep, fix row or revert, or to `scripts/select_tests.py`'s selection.
---

# verify-flow-today

`features/jmerge/spec/FlowToday.tla` models the merge flow as the code runs it: two rows, a main that can go red from a merge or from outside, and a machine a crew can leave full.
Each condition names the file that checks it and quotes the code, with no line number.
How main's red is rerun, judged and reverted is one step here, `JudgeRed`; `verify-main-red` has the detail.
Its design twin is `verify-flow-design`.

The rules, each with its harm:

- **`FlowsWhenGreen`:** once nothing more happens on its own and main is green, work settles merged or waiting on your word.
  Broken, work stops flowing with nothing for you to do about it.
- **`MergeRedsMainOnlyOnAMissedTest`:** a merge turns main red only through a test its check's selection missed, and then jbus reruns main's failed run once and reverts the one clear culprit or files main's fix row.
- **`MachineNotLeftFull`:** once nothing more happens on its own, the machine has room.
  Broken, an idle process a crew left keeps every launch out.
- **`MainFixWaitsOnlyOnYou`:** while main is red and nothing else can happen, its fix waits on nothing of yours but your word.
- The probe `FixAfterARedCheckWaitsOnlyOnYou` checks the `merge_after` case by name.

## The record

Model: `features/jmerge/spec/FlowToday.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/jmerge/src/jmerge/cli.py`: `Repo.judge`, `Repo.judged`, `Repo.again`, `Repo.in_turn`, `Repo.over_main`, `Repo.waits`, `Repo.accept`, `Repo.merge_holding`, `Repo.start_batch`, `Repo.batched`, `Repo.after_batch`, `Repo.build_batch`, `Repo.guards_batch`, `Repo.merge_members`, `in_line`, `IN_LINE`
- `features/jmerge/src/jmerge/batch.py`: `Record`, `Batching`, `narrow`, `kind_of`, `LEAST`, `GUARDS_LEAST`, `GUARDS_MOST`
- `features/jmerge/src/jmerge/ready.py`: `red_only`, `needs_the_user`, `short_on_meets`, `MEETS_NO`, `STACKED_UNMOVED`, `BROWSER_FAILED`, `TOUCHES`
- `features/jmerge/src/jmerge/rows.py`: `short`, `browser_fixing`, `browser_red`
- `features/jmerge/src/jmerge/judgement.py`: `has_go`, `accepted`
- `features/jmerge/src/jmerge/rejudge.py`: `BaseMerge`
- `features/jbus/src/jbus/dispatch.py`: `room`
- `features/jbus/src/jbus/watch.py`: `FIX_GOES`, `_file`
- `features/jbus/src/jbus/culprits.py`: `judge`
- `features/jbus/src/jbus/reverts.py`: `revert`
- `features/jbus/src/jbus/strays.py`: `stop`
- `features/jbus/src/jbus/merge.py`: `start`, `keep`
- `scripts/select_tests.py`: `cross_cutting`, `unowned`, `owns`

At the sync commit every action was read against these; `Launch`, `Check`, `Hear`, `MeetsFix`, `Restack`, `CrewFix`, `BrowserFix`, `Rejudge` and its line, `GiveUpLine` and `KeepsLine`, `Sweep`, `JudgeRed`, `RevertMerges`, `FixMain` and `Unordered`, `Nightly` and `FixBrowser` match.
The batch does not; see the drift below.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, adds a hold or a wait to a pull request's verdict, changes how a batch forms, proves or narrows, or changes what stops a crew's leftover process.
A change to one pull request's verdict alone is `verify-pr-verdict`'s too.

## Run it

```sh
uv run pytest features/jmerge/tests/test_flow_spec.py -q
```

TLC walks some 7M states, so it takes some minutes (about 650 s on a Linux runner, 1800 s timeout), and skips where no Java runs TLC.
A run that ends in seconds took TLC's verdict from the statechart tools' cache (`tools.kept`), keyed by the spec, cfg and jar, and the runner script does the same: the verdict is the one TLC gives, and no change to the code alone can turn it, which is why the record above, and not a pass, says whether the model still describes the code.
`flow_canaries.py` runs the same runs and prints one line each; its command is in `features/jmerge/spec/README.md`, "Check the rules", from the repo root.

- **Bounds:** two pull requests, one outside break, one brief edit, at most one review round that says the brief is not met, `Gap = "turn"`; 7,024,508 distinct states at st-flow's head.
- **The controls:** `Gap = "ended"` (the code from #416 to #427) and `Gap = "busy"` (before #416) each break `FlowsWhenGreen`, `MachineNotLeftFull` and `MainFixWaitsOnlyOnYou`, and hold `MergeRedsMainOnlyOnAMissedTest`.
- **Assumptions:** a crew's turn is one step; the batch of two stands for one of five or more; main's red is judged in one step; jmerge runs one run at a time.
  The rest is in the README's "What the code model leaves out" and "Where `Rejudge` and the code differ".
- **The chart** (`FlowToday.chart.cfg`, 0.97M states) needs more than 14 GB free; the README's "Draw the chart" says how.

## A real bug or a modeling error

Each condition of a step quotes its code.
Open each quote of a trace at its file and check that the code still guards the step as quoted; a step the code cannot take is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as the rows' story (launch, check, review, merge, main's red) in the code's words, and leave the rule as it is.

## Change the model when the code changes on purpose

- A new hold or wait: add it to the verdict where the code checks it, and say in the README which rule reads it.
- A change to the batch: bring `BuildBatch`, `BatchPasses` and `BatchFails` to the code's shape first (see the drift below), and measure the state count again; past some 10M states the test outgrows CI's limit.
- Show a changed rule failing on a scratch break first (take the guard out in your own worktree, uncommitted, see the trace, `git restore` the file).

## Drift at the sync commit

The rules most likely still hold; `/maintain-formal-verification-skill` fixes these.

- **The batch steps no longer match the code (#1642, #1668):** `LEAST = 5`, and a guards batch is 2 to 4 (`GUARDS_LEAST` to `GUARDS_MOST`): with two pull requests the code runs one guards batch inside the same jmerge run (`guards_batch`), where both merge or both go alone in that run.
  The model's `BuildBatch`, `BatchPasses` and `BatchFails` describe a CI batch out across runs and a narrowed batch of one, which can no longer form: a half under five sends every suspect alone (`Batching.chosen`).
  The README's "leaves out" does not say so.
- **`Alone` waits where the code merges (#1670):** when a pending batch is rebuilt, `Repo.batched` first merges the held pull requests, and after a proven batch `Repo.after_batch` merges them in the same run; the model keeps them waiting while a batch is out.
- **`HoldRow` and `HomeEdits` cite a line whose meaning changed (#1657):** `if row and bus.over(row):` now returns `ROW_OVER`, a hold on the pull request; the model's rows end only by merging, so it never reaches it.
- **Older gaps:** a pull request whose guards fail with no overlap with main's change does not go to the line as `InLine` says: it waits on the guards' record for its crew (`judged`, `self.guards.kept`).
  `Repo.again`'s `repeats` (no rejudge after two runs fail the same test) is in neither the model nor the README's "leaves out".
- **Stale prose:** the spec and the README say "as of 21112eba8"; #1644, #1647, #1657, #1668, #1670 and #1681 changed code it cites since.
