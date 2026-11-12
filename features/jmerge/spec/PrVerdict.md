# Why a pull request is not merging: PrVerdict.tla

`PrVerdict.tla` follows one pull request into main through jmerge's verdict, in the order `Repo.judged` (`features/jmerge/src/jmerge/cli.py`) checks it: its review, GitHub's waits, its row (over, held, or without its go), a drop or decline, a protected path, a failed check judged again over today's main (`Repo.judge`, `Repo.again`), GitHub's undecided, `Repo.over_main` with the batch and the guards, and merge-off.
Then the run acts on the verdict: it merges, the guards fail on its tree over main's tip, or, where the batch takes it, it goes the single path when the run judged no other member and joins a batch with the others when it did, and a pull request whose turn GitHub's merge of main waits on stands in its base's line (`IN_LINE`) behind the one ahead.
A crew's fix may fail its check again, and jbus counts each head at which the check failed on a change of its own: at the third it holds the row and pages you (`jbus.stall.twice`, `check failed twice`), and the outbox tells a held row's crew nothing until your approve, or a check that passes at a head, lifts the hold.
At the second it holds the row too where the failed jobs' logs name no failed test; where they name some, the crew is told of them and fixes once more, so the model's count jumps from one to the limit, or steps to two, as the second head's logs name no test or some (st-stall-acts).
Each condition quotes its code with no line number, and `features/jmerge/tests/test_pr_verdict_spec.py` finds each quote once in its file.
It models the verdict as of main 21112eba8 and jbus's hold as of main 8644c5324 and st-stall-acts, and came in with st-pr, the pull request chart of the scout st-map; st-verdict-live widened its rule to every open pull request.

The rule, `MergesOrWaitsOnYou`: "every open pull request merges or waits on the user's word".
It has two halves: a merge leaves no hold of yours outstanding but those your accept lifted at its head (`MergesOnlyOnYourWord`), and every open pull request, from its first state, goes on to merge or to wait on your word, so no path waits for ever on its crew, its reviewer, GitHub, a check or jmerge.
It waits on your word where jmerge holds it for you, or where jbus held its row and paged you, which your approve lifts whatever jmerge says of it.
The second half is a leads-to under weak fairness of every step that happens by itself, and not an invariant on settled states, since one canary's break is a loop with no settled state: a batch that fails, and takes the pull request again at the same head.
Your word has no fairness, and other work moves main at most `Moves` times, once in `PrVerdict.cfg`: with two moves, today's run took over 600 s on CI, past the spec test's timeout, and every canary breaks with one.

`pr_canaries.py` runs TLC on today's code and on eleven canaries, each the code with one hold taken out (`Drop`):

```sh
S=features/skill-library/skills/statechart/scripts
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    python features/jmerge/spec/pr_canaries.py
```

At st-model-upkeep-run's head it prints, with each run's time left out:

```text
ok    today: MergesOrWaitsOnYou holds (1518172 distinct states found)
ok    canary over: MergesOrWaitsOnYou breaks (115953 distinct states found)
ok    canary go: MergesOrWaitsOnYou breaks (117384 distinct states found)
ok    canary touches: MergesOrWaitsOnYou breaks (115887 distinct states found)
ok    canary declines: MergesOrWaitsOnYou breaks (115949 distinct states found)
ok    canary mergeoff: MergesOrWaitsOnYou breaks (115951 distinct states found)
ok    canary head: MergesOrWaitsOnYou breaks (1255043 distinct states found)
ok    canary release: MergesOrWaitsOnYou breaks (1501914 distinct states found)
ok    canary rejudge: MergesOrWaitsOnYou breaks (1474055 distinct states found)
ok    canary again: MergesOrWaitsOnYou breaks (1492365 distinct states found)
ok    canary batch-failed: MergesOrWaitsOnYou breaks (1422595 distinct states found)
ok    canary twice: MergesOrWaitsOnYou breaks (1469094 distinct states found)
every run says what it should
```

`over`, `go`, `touches`, `declines`, `mergeoff` and `head` break the first half: the pull request merges past a hold of yours, and with `head` past one your accept gave at an earlier head.
`release`, `rejudge`, `again`, `batch-failed` and `twice` break the second: it waits for ever behind a line's holder that waits on its user, on a check that failed only over main's red, in a batch that fails again and again at one head, or, with no limit on failed heads, on a crew whose every fix fails its check again.
`rejudge` and `again` break on the same story, since with no unrun check modelled both rest on one path; they are two lines of code, so each keeps its canary.

The first run found a story the code does not have: a check that failed over a red main, then a conflict with main, said `check has failed` for ever, as GitHub's failed check outranks its conflict.
jbus tells the crew of a conflict from GitHub's `CONFLICTING` whatever jmerge says (`features/jbus/src/jbus/rebase.py`), so the model's crew rebases on a conflict it is told of alone, and the rule holds.

The first run of the widened rule found a pull request that merged past jbus's hold: the crew's fix went out before the hold, a third head passed and joined the batch, and the hold landed while the batch's check ran.
The code has no such order: a pass runs its tellers, `stall.twice` among them, before the steps after expedite, where `rebase.github` tells the crew of the failed check, so the row is held in the pass that counts its last failed head before its crew hears of it, and the model's crew gets no fix while a count at the limit waits for its hold.
jbus's hold is the one wait on you that jmerge words as its crew's: with the check failed, jmerge says `check has failed`, as GitHub's waits come before the row's go, while the outbox holds the crew's fix until your approve or a head whose check passes.
The row says `check failed twice` and jbus pages you once; the chart draws the state in "Waits on your word" as `held: its check failed twice`, whatever jmerge last said, with your approve as its way out.

The hold of a row that is over (`ROW_OVER`, #1657) says "accept it to merge it".
st-model-upkeep-run found that no accept lifted it, since `Repo.judged` passed `rows.short`'s wait through no `Repo.lift`, so a rule that each hold you are asked about has a word that moves it broke in four states, the row over from the start.
#1796 fixed it: your accept at the head lifts `ROW_OVER` and no other wait of the queue (`Repo.queue_of` reads the row as an open pull request's), so its go and its hold still hold it, and `over` is one of `Accepted`.

## Draw the chart

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
W=$(mktemp -d) && cp features/jmerge/spec/PrVerdict.* "$W"
(cd "$W" && UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec PrVerdict.tla --config PrVerdict.chart.cfg \
    --title "Why isn't my pull request merging?" --out out)
```

Run it from the repo root, and copy the files of `$W/out`, but its `tlc/`, into `PrVerdict-statechart/`.
`PrVerdict.chart.cfg` moves main once (1,518,172 model states), and `PrVerdict.map.py` labels each state by main and what jmerge last said, and a row jbus held for its failed checks as held.
The chart has 21 states and draws 56 of its 175 steps, at least one way out of each state but merged, and no state breaks the rule.
Then draw its Excalidraw file and the charts page again, from the repo root:

```sh
statechart excalidraw features/jmerge/spec/PrVerdict-statechart/chart.mmd --out features/home/docs/charts/PrVerdict.excalidraw
statechart site --out features/home/docs/charts/index.html
```

each with `UV_PROJECT_ENVIRONMENT` and `uv run --frozen --project "$S"` in front, as `from-spec` has above.

## What PrVerdict leaves out

- A stacked link, a base other than main, another home's pull request, one no brief names, and a draft opened by hand.
- The rule preflight (#1768): a pull request that adds or tightens a test waits until those tests have run on every other open pull request merged with it (`RULE_UNRUN`), and on its crew where one fails (`RULE_BREAKS`); the model has one pull request, so no other for a rule to break.
- The browser run, migrations, `merge_after`, and `row_first`'s order among GitHub's waits.
- A required check with no run at its head (`NO_RUN`) apart from a conflicting one's, the restart of a queued run, and `repeats`, which only saves a CI round.
  GitHub runs no check on a pull request that conflicts with its base, so a check not ended at a decided clash is one with no run, said as the conflict (#1721); the model has no run started before the clash.
- GitHub's merge state and `merge-tree` disagreeing (`FRESH_CONFLICT`): `CONFLICTS` stands for both.
- Main moving between the verdict and the merge (`merge_holding`'s judge again): each step is atomic.
- The other members of a batch: whether a run judges any is the world's (`Alone` has no fairness), and a batch with them is one step out and one back, its kind (guards or CI's), its timeout, its rerun, its narrowing to suspects and `BATCH_FIRST` left out.
  It proves or fails on the pull request's tree merged over main.
- A review round that says the brief is not met: one round holds.
- A head jbus counts for nothing besides one over main's red: a flake shared with two other branches and an infra step's failure (`jbus.redhead.shared`, `infra`).
- Your own hold of a row (`jbus queue hold`): `nogo` stands for it and for a row with no go, whose crew the outbox still tells, so the model's crew is told of both, and with no hold of yours `queue.lift`'s refusal of a row held again since is left out too.
- Whose your accept is: the bus's doors and `--message` (`Repo.accept`).
