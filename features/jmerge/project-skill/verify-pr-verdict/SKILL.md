---
name: verify-pr-verdict
description: Check PrVerdict.tla, one pull request through jmerge's verdict; use when changing Repo.judged, a hold or wait, or what --accept lifts.
paths: "features/jmerge/spec/PrVerdict.tla, features/jmerge/src/jmerge/cli.py, features/jmerge/src/jmerge/ready.py, features/jmerge/src/jmerge/rows.py, features/jmerge/src/jmerge/batch.py, features/jmerge/src/jmerge/treeguards.py, features/jbus/src/jbus/rebase.py"
---

# verify-pr-verdict

`features/jmerge/spec/PrVerdict.tla` follows one pull request into main through jmerge's verdict, in the order `Repo.judged` checks it: its review, GitHub's waits, its row's go, a drop or decline, a protected path, a failed check judged again over today's main (`Repo.judge`, `Repo.again`), GitHub's undecided, `Repo.over_main` with the batch and the guards, and merge-off.
Then the run acts on the verdict: it merges, the guards fail on its tree over main's tip, or it joins the batch, and a pull request waiting on GitHub's merge of main stands in its base's line.
Each condition quotes its code with no line number.

- **The rule, `MergesOrWaitsOnYou`:** a ready pull request with a green check and a go merges or waits on your word.
  Its first half, `MergesOnlyOnYourWord`: a merge leaves no hold of yours outstanding but those your accept lifted at its head.
  Its second half is a leads-to under weak fairness of every step that happens by itself.
- **The harm if it breaks:** a pull request merges past a hold of yours, or waits for ever on something you cannot move.

## The record

Model: `features/jmerge/spec/PrVerdict.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/jmerge/src/jmerge/cli.py`: `Repo.judged`, `Repo.judge`, `Repo.again`, `Repo.in_turn`, `Repo.over_main`, `Repo.merge_holding`, `Repo.merge_members`, `Repo.lifted`, `Repo.lift`, `Repo.accept`, `Repo.waits`, `_merging`
- `features/jmerge/src/jmerge/ready.py`: `red_only`, `short_on_github`, `still_to_pass`, `ROW_HELD`, `NO_GO`, `ROW_OVER`, `TOUCHES`
- `features/jmerge/src/jmerge/rows.py`: `short`
- `features/jmerge/src/jmerge/batch.py`: `Batching.takes`, `Batching.chosen`, `kind_of`
- `features/jmerge/src/jmerge/treeguards.py`: `Guards.kept`, `Guards.of`
- `features/jbus/src/jbus/rebase.py`: `tell`

At the sync commit the verdict order in `Repo.judged` was read against the spec (review, GitHub's waits with `beside`, the row, drops and declines, touches, again, undecided, `over_main`, the guards, merge-off) and matches, as does `GuardsFail`'s split on overlap in `merge_holding`.
The batch and one hold do not; see the drift below.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against the model, as `/maintain-formal-verification-skill` says, and never because the check passes.

## Does a change touch it

Rerun it when the diff touches a file of the record, adds or reorders a hold or wait of the verdict, or changes what `--accept` lifts.
`features/jmerge/tests/test_pr_verdict_spec.py` fails when a quote no longer stands once in its file, or a `Drop` the spec reads has no canary.

## Run it

```sh
uv run pytest features/jmerge/tests/test_pr_verdict_spec.py -q
```

It runs TLC on today's code and the nine canaries, in a few minutes, and skips where no Java runs TLC.
A run that ends in seconds took TLC's verdict from the statechart tools' cache (`tools.kept`), keyed by the spec, cfg and jar, and the runner script does the same: the verdict is the one TLC gives, and no change to the code alone can turn it, which is why the record above, and not a pass, says whether the model still describes the code.
`pr_canaries.py` prints one line a run; its command is in `features/jmerge/spec/README.md`, "Why a pull request is not merging".

- **Bounds:** `Moves = 2` (other work moves main at most twice), `Drop = "none"`, 599,971 distinct states; the chart's cfg moves main once (263,292 states).
- **The canaries:** `go`, `touches`, `declines`, `mergeoff` and `head` break the first half (a merge past a hold of yours); `release`, `rejudge`, `again` and `batch-failed` break the second (it waits for ever).
- **Assumptions:** one pull request into main, no stack, no browser run, no migrations, no `merge_after`; `CONFLICTS` stands for both kinds of conflict; each step is atomic; one fix makes the change good, and one review round holds; your word has no fairness.
  The rest is in the README's "What PrVerdict leaves out".

## A real bug or a modeling error

Each condition of a step quotes its code.
Open each quote of a trace at its file and check that `Repo.judged` still reaches it in that order; a verdict the code cannot give at that point is a modeling error, and the model is what gets fixed.
When every step is backed, it is a bug: tell it as what jmerge said of the pull request at each run, in its own words (`hold`, `wait`, the reason), and leave the rule as it is.

## Change the model when the code changes on purpose

- A new hold: add it to `Holds` at the place `Repo.judged` checks it, with a `Drop` and a canary in `pr_canaries.py` that shows a merge past it.
- A new wait: add it where the code checks it, and see the second half still hold.
- Show a changed rule failing on a scratch break first (take the hold out in your own worktree, uncommitted, see the trace, `git restore` the file).

## Drift at the sync commit

`/maintain-formal-verification-skill` fixes these.

- **The batch of one no longer exists (#1642, #1668):** one member has `kind_of(1) == ""`, so `Batching.chosen` sends it alone and it merges on the single path in the same run.
  The model's `JoinBatch`, `BatchProves` and `BatchFails` cannot happen for one pull request, its "ready-batch" verdict forbids the direct merge the code does, and the `batch-failed` canary's loop now needs a failed guards batch or a suspect half.
- **`ROW_OVER` (#1657) is missing:** `rows.short` holds the pull request of a row that is over without merging; it is not in `Holds` and not in the README's "leaves out".
- **Stale prose:** the spec says "as of 21112eba8"; #1644 edited the spec since.
