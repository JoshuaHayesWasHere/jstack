# The merge flow, as a TLA+ spec

Two rows, a main that can go red from a merge or from outside, and a machine that a crew can leave full.
The home wrote it on 2026-10-23 to test the premise behind "nothing moves", and it came in with rejudge-red-prs.

- `FlowToday.tla` models the code as of main 21112eba8, and each of its conditions names the file that checks it and quotes the code, with no line number, so a rebase that moves the lines leaves no cite to renumber.
  `statechart.lib.located` finds the one place a quote stands.
  It is the flow-statechart scout's `FlowNow.tla` of main 6485914, kept with the scout's report and not in the repo, with #416, #426 and #427 since and cut down to what the four rules read.
  Since #583 and #584 it has main's fix: the `main-red-` row, or a pull request that carries the fix, and the row's crew may end with no pull request, its fix in an open one.
  Since red-main-no-hold a red main holds no pull request, so a merged fix ends the red whether or not its own check proved it.
  Since fl-flowtoday-1102 it follows the scout fl-statechart-1102's `FlowNow.tla` of main a978b7ba9 in six places.
  jbus reruns main's failed push run once before it judges the red tip (#672), and a red from outside may be a flake that the rerun passes.
  jbus then reverts the red tip's one clear culprit (`jbus.reverts`, #862), and jmerge merges the revert; two reds that overlap, a skew (#899), or a red from outside gets main's fix row instead.
  Since st-flow that is one step, `JudgeRed`, over `mend` (judging, a revert open, or the fix row filed) and `redBy` (a flake, outside, one merge, or many): how jbus reruns, judges the oldest red since the last green (#992), reverts, and closes a stale revert is `features/jbus/spec/MainRed.tla`'s.
  jbus's pass approves both fix rows it files, main's and the browser run's, by rule and not by your word (#547).
  A stacked link is checked while it sits on its base's open branch, and its move onto main may keep that pass (`jmerge.reuse`, #868).
  Since fl-stack-by-depends-only it has no unstack: a stacked link stays on its stack until its base merged.
  A pull request whose last review round says the brief is not met is held (`MEETS_NO`, #843), and jbus tells its crew, which meets it (#850).
  Since #575 and #577 it has each pull request's browser run, which holds it when it failed, and main's browser red.
  Since cut 11 of the simplify pass it has a row's go, which jbus asks at launch and jmerge at merge (`rows.py` `ROW_HELD`, `NO_GO`), and a hold for your word, as a change that touches a protected path has (`ready.py` `TOUCHES`).
  Since fl-no-draft a crew opens its pull request ready, and jmerge marks no draft ready: the model has no draft, no `Ready` step and no lift that `jmerge --accept` keeps, and its `Accept` merges a held pull request whose check passed, as `Repo.accept` does.
  Since review-after-green-one-round one round gives a fix no review, and since vision-review-before-pr that round comes before the pull request: jbus launches the reviewer once the crew's desk proof binds its pushed head, and the crew opens the pull request after the review, so its check runs once, after the round.
  `Launch` cites jbus's launch on the desk proof, and `Merges` the review rule on its `ci[p] = "pass"` condition.
  The round is no variable, since no rule reads it: a history bit for it took the model of fl-no-draft from 7.9M to 12.9M states, and a step of its own to 21.0M.
  Since st-flow it has jmerge's batch, its line and its run off jbus's pass.
  A ready pull request main moved past is a member of jmerge's batch (#1564), which CI checks on one draft pull request: a pass merges every member, a failed batch of two makes both suspects and the next batch the first half of them, and a failed batch of one sends its member alone, at that head, to the merged-tree guards or the line.
  While a batch is out on a green main, a pull request that would merge alone waits for it (`batch-first`), and any merge into main makes it stale, so the next run builds it again.
  A pull request that goes alone and whose guards fail, or a red one main moved past (#1012), has GitHub merge main into its branch only in its turn in main's line (#1009): the holder gives the line up once it waits on anything but jmerge, GitHub and its check (`cli.IN_LINE`).
  jbus's pass starts jmerge's run and returns (#1616), so what jmerge said of a failed check, a browser run or a review round reaches the crew a pass late: the model's `Hear` step.
  The batch's rerun of a failed check, its timeout and the most it takes (#1613) are left out: with two pull requests and no flake in a member's check, none of them changes what merges.
- `FlowDesign.tla` models the design: cross-cutting-guard (`Check`), rejudge-red-prs (`Rejudge`) and crew-leftover-procs (`Sweep`), with today's fix path.
- `canary/` holds the design with each fix taken out: `NoGuard`, `NoRejudge` and `NoSweep`.
  `NoProof`, the red hold as it was before #583, went with the hold.
- `flow_canaries.py` runs TLC on all of it, and `FlowToday.map.py` labels the chart in `FlowToday-statechart/`.

## Check the rules

```sh
S=features/skill-library/skills/statechart/scripts
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    python features/jmerge/spec/flow_canaries.py
```

Run it from the repo root.
Today's code holds all four rules: `FlowsWhenGreen`, `MergeRedsMainOnlyOnAMissedTest`, `MachineNotLeftFull` and `MainFixWaitsOnlyOnYou`.
The probe `FixAfterARedCheckWaitsOnlyOnYou` holds too.
At st-flow's head it prints:

```text
ok    design: every rule holds (425 distinct states found, 0.6 s)
ok    canary NoGuard: NoMergeTurnsMainRed breaks (47 distinct states found, 0.6 s)
ok    canary NoRejudge: FlowsWhenGreen breaks (177 distinct states found, 0.7 s)
ok    canary NoSweep: FlowsWhenGreen breaks (310 distinct states found, 0.6 s)
ok    canary NoSweep: MachineNotLeftFull breaks (287 distinct states found, 0.6 s)
ok    today: FlowsWhenGreen holds (7024508 distinct states found, 83.9 s)
ok    today: MergeRedsMainOnlyOnAMissedTest holds (7024508 distinct states found, 83.9 s)
ok    today: MachineNotLeftFull holds (7024508 distinct states found, 83.9 s)
ok    today: MainFixWaitsOnlyOnYou holds (7024508 distinct states found, 83.9 s)
ok    today: FixAfterARedCheckWaitsOnlyOnYou holds (7024508 distinct states found, 83.9 s)
ok    today, before #427 (idle swept once its row ended): MergeRedsMainOnlyOnAMissedTest holds (7024508 distinct states found, 60.7 s)
ok    today, before #427 (idle swept once its row ended): FlowsWhenGreen breaks (6284 distinct states found, 0.9 s)
ok    today, before #427 (idle swept once its row ended): MachineNotLeftFull breaks (4552 distinct states found, 0.8 s)
ok    today, before #427 (idle swept once its row ended): MainFixWaitsOnlyOnYou breaks (97834 distinct states found, 1.5 s)
ok    today, before #416 (busy leftovers only): MergeRedsMainOnlyOnAMissedTest holds (7024508 distinct states found, 59.0 s)
ok    today, before #416 (busy leftovers only): FlowsWhenGreen breaks (6307 distinct states found, 0.9 s)
ok    today, before #416 (busy leftovers only): MachineNotLeftFull breaks (4560 distinct states found, 0.9 s)
ok    today, before #416 (busy leftovers only): MainFixWaitsOnlyOnYou breaks (98086 distinct states found, 1.6 s)
every run says what it should
```

The rules of a model that must hold share one TLC run, so their lines share its count and time, and each rule that must break has a run of its own.
TLC runs on two workers, so the count of a run that breaks a rule varies a little from run to run.
Today's model has 7.0M states, where it had 7.9M at fl-no-draft, 10.5M at #946 and 2.6M before fl-rules-1103: st-flow's batch, line and pass read cost less than the main-red detail it moved out to `MainRed.tla`.
With no draft a pull request's check runs beside its review rather than after it, so the two interleave in more ways, as the scout fl-simplify-1103 also found of its chart-sized model, and that took the model to 14.7M before #946.
fl-no-draft then took out `named` and `proved`, which no step and no rule read since red-main-no-hold took out the red hold, with every rule's verdict the same: the run of `test_flow_spec.py` had passed CI's 1200 s limit at 14.7M.
On 2026-11-03 the home kept the code and rewrote two rules in the words of the flow the merged pull requests chose; their intent stays, and `FlowsWhenGreen` keeps its words.

- `FlowsWhenGreen`: "Work never stops flowing: once nothing more happens on its own and main is green, it settles merged or waiting on your word."
  Its words are unchanged.
  It broke on a draft held on a protected path while the spec's `Accept` refused a draft; fl-rules-1103 made `Accept` mark the draft ready, as #709 did, and since fl-no-draft there is no draft: a pull request held for your word is open and checked, and your word merges it.
- `MergeRedsMainOnlyOnAMissedTest`, which was `NoMergeTurnsMainRed`: "A merge turns main red only through a test its check's selection missed, and then jbus reruns main's failed push run once and reverts the one clear culprit or files main's fix row."
  The flow is that of #849, #862 and #899.
  A check can still miss a test that reads the changed path: `scripts/select_tests.py` runs every test no rule owns (#397), and each test whose `READ_SET` matches the changed path (#426), and `testing/tests/test_cross_cutting.py` sees only the reads it knows, so the model keeps that chance and records it as `missed`.
  Until it is judged, the red is in its one rerun (#672) or due its judgement; once judged, jbus's revert is open, or main's fix row is filed, or that row's crew put the fix in an open pull request.
- `MachineNotLeftFull`: "Once nothing more happens on its own, the machine has room."
  Its words are unchanged.
- `MainFixWaitsOnlyOnYou`: "While main is red and nothing else can happen, its fix waits on nothing of yours but your word: the lift of a pull request you hold, or your approval of a row whose brief you must approve."
  Since #547 jbus approves every fix row it files, main's and the browser run's, by rule, so no approval of a fix row is yours.

Until #946 today's code broke `MainFixWaitsOnlyOnYou`, and the rule was not rewritten to hold: the break was a fault in the code, and #946 fixed the code.
Its shortest story, 9 states, was the merge_after case: something outside breaks main; its rerun fails, and jbus files main's fix row and approves it by rule; the row's crew puts the fix in b; a's check fails over the red main.
jmerge judges a again only once main is green (`features/jmerge/src/jmerge/cli.py` `or (one.base == self.trunk and bool(self.main_state.red))`, `Repo.again`), and merges b only after a (`features/jmerge/src/jmerge/rows.py` `for other in row.get("merge_after", []):`), so the fix waited on nothing your word can move.
Since #946 main's fix brief lets its crew leave the fix only in an open pull request that waits on no other (`features/jbus/src/jbus/watch.py` `FIX_GOES`), which `FlowToday.tla` models as `Unordered`, so the fix never goes in b there.
The same pull request made the model's crew read a break of its own as its own whatever the base, as `features/crew/the-checks.md` does, which ended the case of a fix whose own break its crew read as main's red.
The probe `FixAfterARedCheckWaitsOnlyOnYou` checks the merge_after case by name, where main is red, b holds its fix, and a's check failed over the red main, and it holds.
The design holds all four rules in the words they had before: its check runs every test that reads the tree, and the crew of a fix reads a failure over the red it fixes as its own.
`NoGuard` breaks `NoMergeTurnsMainRed`, `NoRejudge` breaks `FlowsWhenGreen`, and `NoSweep` breaks `FlowsWhenGreen` and `MachineNotLeftFull`.
Two controls run the model with an earlier `Gap`, `FlowToday.tla`'s constant, which `FlowToday.cfg` sets to `turn`, the code since #427.
With `ended`, the code from #416 to #427, which stops an idle process a crew left only once its row ended, it breaks `FlowsWhenGreen`, `MachineNotLeftFull` and `MainFixWaitsOnlyOnYou`.
With `busy`, the code before #416, which stops only a process that uses CPU, it breaks the same three.
In both an idle process a crew left at its pull request, a `sleep` or a headless browser waiting, keeps the machine full.
Then a follow-up that merges after its row launches first and its row never launches, and main's fix cannot launch either.
A full machine stops no judgement of main's red, so both hold `MergeRedsMainOnlyOnAMissedTest`.
`features/jmerge/tests/test_flow_spec.py` runs it, and skips where no Java runs TLC.

## Draw the chart

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
D=$HOME/.cache/jstack/tlc-tmp && mkdir -p "$D"
W=$(TMPDIR=$D mktemp -d) && cp features/jmerge/spec/FlowToday.* features/jmerge/spec/FlowDesign.* "$W"
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec FlowToday.tla --config FlowToday.chart.cfg --against FlowDesign.tla --label "the design" \
    --title "Does work keep flowing?" --out out --png)
```

Run it from the repo root, and copy the files of `$W/out`, but its `tlc/`, into `FlowToday-statechart/`.
`FlowToday.chart.cfg` checks the four rules on the model cut by `ChartCut`: no change breaks a browser test of its own, and no brief is edited.
The chart command holds TLC's whole state graph in memory: the whole model, 2.6M states before fl-rules-1103, took more than 27 GB before earlyoom stopped it.
The cut, 1.19M states at #946, 1.04M since fl-no-draft and 0.97M since st-flow, needed more than 14 GB at fl-spec-readme-docs's head, and earlyoom stopped it once, so run it with that much memory free.
TLC also keeps a disk queue of states under `TMPDIR`, and the cut's queue outgrew a `/tmp` tmpfs the machine's other work had filled, so the block puts `TMPDIR` on a disk with room (`$HOME/.cache` here).
With an edit and an outside break both in the cut, TLC 2.19 threw while its `-continue` run printed a path of the rule then named `NoMergeTurnsMainRed`.
`flow_canaries.py` checks every rule on the whole model.
The chart has no red path: since #946 no state of the cut breaks a rule, and at st-flow's head its 69 states all work.
The design starts with both pull requests open, so a story, when the chart has one, says the design starts on another screen.

## What the code model leaves out

`FlowToday.tla` has only the variables the four rules read, and the scout's `FlowNow.tla` has the rest.

- The queue before a row's go: the home's brief and which home a word goes to (#402); each row starts with your go, and a brief edited after it (#399) is a hold you lift by approving it again.
- The review as more than one step: its findings, its clock and your nudge, a conflict and its rebase, and what reaches you.
- Holds for your word other than a protected path (a dropped line, a decline, a gate), each one `needs`, and a merge gate, which only a passing gate lifts.
- A brief that says `Review: none`, which waits on your word.
- A crew at work: a crew's turn is one step, so `Gap = "turn"` stops every idle process.
- A process that holds a test slot, which jbus.strays leaves running since #427: the model takes it to end with its check.
- A row that ends other than by merging: done, left, or its worktree gone.
- The account caps, GitHub's API budget, cancelled checks, and the nightlies other than browser.yml's.
- A draft someone opened by hand, which jmerge never merges or marks ready.
- A pull request whose own browser run proves the fix of main's browser red: the browser-red row is main's only fix there.
- A fix row that ends with no fix anywhere, which leaves main red with nothing to merge until you queue another.
- A fix row that launched and is left to its crew once main is green: the model's fix row is queued until jbus's pass approves it by rule and it launches, and that launch is the whole of its work.
- A revert whose check fails (`reverts.stuck`), and a second revert of one row: the model keeps one revert open at a time, and where another merge broke more on the red tip, the revert's merge leaves main red and its tip is judged again, which files main's fix row.
- What a reverted row does next: it stays merged.
- What a culprit's head holds: TLC takes it to hold the green under the red tip or not (a skew), either way.
- Which stacked moves are a clean replay of the trees their check passed: TLC takes either, a pass kept or the check run again.
- A stacked link's check over its base's change: in the model it fails only on its own change and on main's red.
- A `Waived:` line, your other way past a review round that says the brief is not met, and a round that says so after the first.
- The red that ends at a fixing merge: the code ends it once jbus sees main's new tip green.
- How main's red is rerun, judged, reverted and closed: `features/jbus/spec/MainRed.tla` has it, and this model judges it in one step.
- A hand merge that moves main's tip, and a revert's turn in main's line (#1044): its merge is one step.
- The batch's rerun of a failed check, its timeout, the most it takes (#1613), a member that conflicts with one before it, a batch that cannot be made, and a proven batch whose merge stops at a member that no longer stands: the model builds it again.
- An accepted pull request whose guards failed over a moved main, which goes through the line, and an accept that takes the line: the model's accept merges at once.
- A pull request that conflicts with main's tip and waits for its rebase, a stacked base's own line, and the line's restarts of a queued run.
- jmerge's run lock and the merge tick: the model's jmerge is one run at a time, and only what its run said waits for a pass to read it.

`FlowDesign.tla`'s `Sweep` clears every leftover, idle or busy, as soon as a turn ends, which the code did not until #427: from #416 it stopped a busy one, and an idle one only once its row ended.
The design also has both pull requests open from the start, so it has no launch and no row order, and it has no browser run.

## Where `Rejudge` and the code differ

- Since st-flow the model's condition is the code's, a base that has moved since the check started (`moved[p]`, `Repo.again`), and the update waits its turn in main's line (#1012).
  A change broken on its own then fails again at the updated head as its own.
- The model judges again any red pull request, and the code only one whose single shortfall is the failed check: a pull request short of a review, a queue row or anything else keeps `check has failed` (`Repo.judge`).
- The code asks once for a head and a base tip, in `base-merges.json`, while jbus tells a crew once for a head: the model has no record of either.
- The model has one main, and the code reads each pull request's own base (`baseRefName`).
- The model leaves out a GitHub that refuses the update.
- The code checks no room before it judges again: GitHub runs the check at the updated head and nothing runs on this machine, so the model's `Rejudge` has no `~full`.

# Why a pull request is not merging: PrVerdict.tla

`PrVerdict.tla` follows one pull request into main through jmerge's verdict, in the order `Repo.judged` (`features/jmerge/src/jmerge/cli.py`) checks it: its review, GitHub's waits, its row's go, a drop or decline, a protected path, a failed check judged again over today's main (`Repo.judge`, `Repo.again`), GitHub's undecided, `Repo.over_main` with the batch and the guards, and merge-off.
Then the run acts on the verdict: it merges, the guards fail on its tree over main's tip, or it joins the batch, and a pull request whose turn GitHub's merge of main waits on stands in its base's line (`IN_LINE`) behind the one ahead.
A crew's fix may fail its check again, and jbus counts each head at which the check failed on a change of its own: at the second it holds the row and pages you (`jbus.stall.twice`, `check failed twice`), and the outbox tells a held row's crew nothing until your approve, or a check that passes at a head, lifts the hold.
Each condition quotes its code with no line number, and `features/jmerge/tests/test_pr_verdict_spec.py` finds each quote once in its file.
It models the verdict as of main 21112eba8 and jbus's hold as of main 8644c5324, and came in with st-pr, the pull request chart of the scout st-map; st-verdict-live widened its rule to every open pull request.

The rule, `MergesOrWaitsOnYou`: "every open pull request merges or waits on the user's word".
It has two halves: a merge leaves no hold of yours outstanding but those your accept lifted at its head (`MergesOnlyOnYourWord`), and every open pull request, from its first state, goes on to merge or to wait on your word, so no path waits for ever on its crew, its reviewer, GitHub, a check or jmerge.
It waits on your word where jmerge holds it for you, or where jbus held its row and paged you, which your approve lifts whatever jmerge says of it.
The second half is a leads-to under weak fairness of every step that happens by itself, and not an invariant on settled states, since one canary's break is a loop with no settled state: a batch of one that fails, and takes the pull request again at the same head.
Your word has no fairness, and other work moves main at most `Moves` times, once in `PrVerdict.cfg`: with two moves, today's run took over 600 s on CI, past the spec test's timeout, and every canary breaks with one.

`pr_canaries.py` runs TLC on today's code and on ten canaries, each the code with one hold taken out (`Drop`):

```sh
S=features/skill-library/skills/statechart/scripts
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    python features/jmerge/spec/pr_canaries.py
```

At st-verdict-live's head it prints:

```text
ok    today: MergesOrWaitsOnYou holds (655106 distinct states found, 27.1 s)
ok    canary go: MergesOrWaitsOnYou breaks (58795 distinct states found, 2.2 s)
ok    canary touches: MergesOrWaitsOnYou breaks (58784 distinct states found, 2.1 s)
ok    canary declines: MergesOrWaitsOnYou breaks (58788 distinct states found, 2.1 s)
ok    canary mergeoff: MergesOrWaitsOnYou breaks (58787 distinct states found, 2.1 s)
ok    canary head: MergesOrWaitsOnYou breaks (577682 distinct states found, 17.4 s)
ok    canary release: MergesOrWaitsOnYou breaks (655098 distinct states found, 21.1 s)
ok    canary rejudge: MergesOrWaitsOnYou breaks (780300 distinct states found, 30.8 s)
ok    canary again: MergesOrWaitsOnYou breaks (650098 distinct states found, 27.8 s)
ok    canary batch-failed: MergesOrWaitsOnYou breaks (654332 distinct states found, 28.2 s)
ok    canary twice: MergesOrWaitsOnYou breaks (687466 distinct states found, 27.4 s)
every run says what it should
```

`go`, `touches`, `declines`, `mergeoff` and `head` break the first half: the pull request merges past a hold of yours, and with `head` past one your accept gave at an earlier head.
`release`, `rejudge`, `again`, `batch-failed` and `twice` break the second: it waits for ever behind a line's holder that waits on its user, on a check that failed only over main's red, in a batch of one that fails again and again, or, with no limit on failed heads, on a crew whose every fix fails its check again.
`rejudge` and `again` break on the same story, since with no unrun check modelled both rest on one path; they are two lines of code, so each keeps its canary.

The first run found a story the code does not have: a check that failed over a red main, then a conflict with main, said `check has failed` for ever, as GitHub's failed check outranks its conflict.
jbus tells the crew of a conflict from GitHub's `CONFLICTING` whatever jmerge says (`features/jbus/src/jbus/rebase.py`), so the model's crew rebases on a conflict it is told of alone, and the rule holds.

The first run of the widened rule found a pull request that merged past jbus's hold: the crew's fix went out before the hold, a third head passed and joined the batch, and the hold landed while the batch's check ran.
The code has no such order: a pass runs its tellers, `stall.twice` among them, before the steps after expedite, where `rebase.github` tells the crew of the failed check, so the row is held in the pass that counts its second failed head before its crew hears of it, and the model's crew gets no fix while a count at the limit waits for its hold.
jbus's hold is the one wait on you that jmerge words as its crew's: with the check failed, jmerge says `check has failed`, as GitHub's waits come before the row's go, while the outbox holds the crew's fix until your approve or a head whose check passes.
The row says `check failed twice` and jbus pages you once; the chart draws the state in "Waits on your word" as `held: its check failed twice`, whatever jmerge last said, with your approve as its way out.

## Draw the chart

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
W=$(mktemp -d) && cp features/jmerge/spec/PrVerdict.* "$W"
(cd "$W" && UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec PrVerdict.tla --config PrVerdict.chart.cfg \
    --title "Why isn't my pull request merging?" --out out --png)
```

Run it from the repo root, and copy the files of `$W/out`, but its `tlc/`, into `PrVerdict-statechart/`.
`PrVerdict.chart.cfg` moves main once (655,106 model states, about two minutes), and `PrVerdict.map.py` labels each state by main and what jmerge last said, and a row jbus held for its failed checks as held.
The chart has 20 states and draws 54 of its 142 steps, at least one way out of each state but merged, and no state breaks the rule.
Then draw its Excalidraw file and the charts page again, from the repo root:

```sh
statechart excalidraw features/jmerge/spec/PrVerdict-statechart/chart.mmd --out features/home/docs/charts/PrVerdict.excalidraw
statechart site --out features/home/docs/charts/index.html
```

each with `UV_PROJECT_ENVIRONMENT` and `uv run --frozen --project "$S"` in front, as `from-spec` has above.

## What PrVerdict leaves out

- A stacked link, a base other than main, another home's pull request, one no brief names, and a draft opened by hand.
- The browser run, migrations, `merge_after`, and `row_first`'s order among GitHub's waits.
- A required check with no run at its head (`NO_RUN`), the restart of a queued run, and `repeats`, which only saves a CI round.
- GitHub's merge state and `merge-tree` disagreeing (`FRESH_CONFLICT`): `CONFLICTS` stands for both.
- Main moving between the verdict and the merge (`merge_holding`'s judge again): each step is atomic.
- A batch of two or more: its timeout, its rerun, its narrowing to suspects, and `BATCH_FIRST`.
  The model's batch is of one, and proves or fails on the tree merged over main.
- A review round that says the brief is not met: one round holds.
- A head jbus counts for nothing besides one over main's red: a flake shared with two other branches and an infra step's failure (`jbus.stall.shared`, `infra`).
- Your own hold of a row (`jbus queue hold`): `nogo` stands for it and for a row with no go, whose crew the outbox still tells, so the model's crew is told of both, and with no hold of yours `queue.lift`'s refusal of a row held again since is left out too.
- Whose your accept is: the bus's doors and `--message` (`Repo.accept`).

# A run of jmerge the pass started: MergeRun.tla

`MergeRun.tla` follows one run of `jmerge` that jbus's pass starts, as the code of main aa5469d97 takes it, with a death at each step.
The pass (`jbus.merge.merge`) writes a start stamp and starts a detached process (`keep`), which holds `going.lock`, runs `jmerge --if-free` and writes what it printed to `ran-<at>.json`.
The next pass reads each record: it replaces `ran-<at>.json` with `read.json`, then sends its lines (`_judged`).
Inside, `jmerge` holds the repo's run lock and goes in the order of `jmerge.cli`: `Repo.open_only` settles the restarts a run left owed, `Repo.start_batch` reads where the batch stands, the judge loop restarts a pull request whose run GitHub left queued (`Repo.unstuck`) or merges one and closes its wait spell, and `Repo.batched` merges a proven batch or builds the next.
The merge tick runs `jmerge --if-free` too.
Each carrier of the st-state-ledger ledger's MergeRun rows (B-059 to B-063, C-023, C-029, C-031, C-033, C-043, C-044) has its variable, whose comment quotes the code that writes it.
The batch's state is `batch.state_of`'s six values, with the three PrVerdict.batch lacks: proven, late and rerun.
`features/jmerge/tests/test_merge_run_spec.py` finds each quote once in its file, checks each carrier has its variable, and runs TLC on each config and on each rule alone.

The constant `Inside` names the parts of jmerge's run a config follows (restart, batch, waits).
The parts share nothing but the run lock and a death, and all of them together with two pass runs is past 58M states, so each config follows the parts its rules read.
`Fault = "replace-first"` is today's code; each other value changes one thing of it: `judge-first` sends the lines before the replace, `fresh-list` reads whether a pull request is open from GitHub in the run, `no-run-lock` is the canary of `OneRunAtATime`, and `unlink-first` is the start stamp as it was before the stamp named its run, the canary of `NoFalseNoRecord` and `DeathTold`.
`ReplyLost` is the world: GitHub took a close whose reply gh lost.

## The rules of the run, and today's verdicts

| Rule | Config | Today | Notes |
|---|---|---|---|
| `RunHeard`: every run's lines are judged once | `MergeRun.cfg` | breaks | the pass replaces the record, then dies before `_judged`; `judge-first` holds it |
| `StreakOnce`: the jmerge streak counts each run once | `MergeRun.cfg` | holds | `judge-first` breaks it: a pass that dies after `_judged` and before the replace counts the run twice, since `_sent` keys each line but nothing keys the streak |
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
    --title "jbus's pass starts a run of jmerge: does what it said reach you?" --out out --png)
```

Run it from the repo root, and copy the files of `$W/out`, but its `tlc/`, into `MergeRun-statechart/`.
`MergeRun.chart.cfg` has one pass run and no tick (191 model states), labelled by `MergeRun.map.py`: 32 chart states and 50 of its 67 steps, and one bug path, for RunHeard; NoFalseNoRecord and DeathTold hold on it.
The two-run stories are `MergeRun.cfg`'s, which the test checks.

## What MergeRun leaves out

- The run's own lines and what jbus does with them: a record is heard or not, and `Said.failed` is not modelled.
- A start that fails (`start` returns why), `child.log`, the systemd unit against a session of its own past whether jmerge outlives its process, and a stamp that does not parse.
- Time, past STARTING, RESTART_MINUTES and PENDING_MINUTES: TLC chooses when each has gone by.
- Of the restart: the queued run itself, `gave_up`, the line it holds, and a user who reopens by hand.
- Of the batch: its members one by one, a guards batch's run, the merge lock another run holds, the main-red and switch-off skips, a failed job with no run to rerun, and `failed` heads; `most` is three levels, 5, 12 and 48, which keep what `_full` reads.
- Two pull requests stand for every other: P, restarted, and W, merged alone.
