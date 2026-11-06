# The merge flow, as a TLA+ spec

Two rows, a main that can go red from a merge or from outside, and a machine that a crew can leave full.
The home wrote it on 2026-10-23 to test the premise behind "nothing moves", and it came in with rejudge-red-prs.

- `FlowToday.tla` models the code as of main a978b7ba9, and each of its conditions names the file that checks it and quotes the code, with no line number.
  `test_flow_spec.py` finds the one place each quote stands, so a rebase that moves the lines leaves no cite to renumber.
  It is the flow-statechart scout's `FlowNow.tla` of main 6485914, kept with the scout's report and not in the repo, with #416, #426 and #427 since and cut down to what the four rules read.
  Since #583 and #584 it has main's fix: the `main-red-` row, or a pull request that carries the fix, and the row's crew may end with no pull request, its fix in an open one.
  Since red-main-no-hold a red main holds no pull request, so a merged fix ends the red whether or not its own check proved it.
  Since fl-flowtoday-1102 it follows the scout fl-statechart-1102's `FlowNow.tla` of main a978b7ba9 in six places.
  jbus reruns main's failed push run once before it judges the red tip (#672), and a red from outside may be a flake that the rerun passes.
  jbus then reverts the red tip's one clear culprit (`jbus.reverts`, #862), and jmerge merges the revert.
  Since #992 jbus judges the oldest red tip since the last green, and reverts its one clear culprit there while no later tip of the run fails a test that did not fail at it.
  Two reds that overlap (a later tip fails another test), a culprit whose head lacks the green under the tip (a skew, #899), or a red from outside gets main's fix row instead, a commit whose check has not ended is judged again on the next pass until the tip is an hour old, and jbus closes a revert still open once main is green without it (#899).
  jbus's pass approves both fix rows it files, main's and the browser run's, by rule and not by your word (#547).
  A stacked link is checked while it sits on its base's open branch, and its move onto main may keep that pass (`jmerge.reuse`, #868).
  Since fl-stack-by-depends-only it has no unstack: a stacked link stays on its stack until its base merged.
  A pull request whose last review round says the brief is not met is held (`MEETS_NO`, #843), and jbus tells its crew, which meets it (#850).
  Since #575 and #577 it has each pull request's browser run, which holds it when it failed, and main's browser red.
  Since cut 11 of the simplify pass it has a row's go, which jbus asks at launch and jmerge at merge (`rows.py` `ROW_HELD`, `NO_GO`), and a hold for your word, as a change that touches a protected path has (`ready.py` `TOUCHES`).
  Since fl-no-draft a crew opens its pull request ready, and jmerge marks no draft ready: the model has no draft, no `Ready` step and no lift that `jmerge --accept` keeps, and its `Accept` merges a held pull request whose check passed, as `Repo.accept` does.
  Since review-after-green-one-round one round gives a fix no review, and since vision-review-before-pr that round comes before the pull request: jbus launches the reviewer once the crew's desk proof binds its pushed head, and the crew opens the pull request after the review, so its check runs once, after the round.
  `Launch` cites jbus's launch on the desk proof, and `Merges` the review rule on its `ci[p] = "pass"` condition.
  The round is no variable, since no rule reads it: a history bit for it took today's model from 7.9M to 12.9M states, and a step of its own to 21.0M.
- `FlowDesign.tla` models the design: cross-cutting-guard (`Check`), rejudge-red-prs (`Rejudge`) and crew-leftover-procs (`Sweep`), with today's fix path.
- `canary/` holds the design with each fix taken out: `NoGuard`, `NoRejudge` and `NoSweep`.
  `NoProof`, the red hold as it was before #583, went with the hold.
- `flow_canaries.py` runs TLC on all of it, and `FlowToday.map.py` labels the chart in `FlowToday-statechart/`.

## Check the rules

```sh
S=features/skill-library/skills/statechart/scripts
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    python features/jmerge/spec/flow_canaries.py
```

Run it from the repo root.
Today's code holds all four rules: `FlowsWhenGreen`, `MergeRedsMainOnlyOnAMissedTest`, `MachineNotLeftFull` and `MainFixWaitsOnlyOnYou`.
The probe `FixAfterARedCheckWaitsOnlyOnYou` holds too.
At fl-no-draft's head it prints:

```text
ok    design: every rule holds (425 distinct states found, 0.6 s)
ok    canary NoGuard: NoMergeTurnsMainRed breaks (47 distinct states found, 0.6 s)
ok    canary NoRejudge: FlowsWhenGreen breaks (178 distinct states found, 0.6 s)
ok    canary NoSweep: FlowsWhenGreen breaks (294 distinct states found, 0.6 s)
ok    canary NoSweep: MachineNotLeftFull breaks (293 distinct states found, 0.6 s)
ok    today: FlowsWhenGreen holds (7851776 distinct states found, 85.5 s)
ok    today: MergeRedsMainOnlyOnAMissedTest holds (7851776 distinct states found, 85.5 s)
ok    today: MachineNotLeftFull holds (7851776 distinct states found, 85.5 s)
ok    today: MainFixWaitsOnlyOnYou holds (7851776 distinct states found, 85.5 s)
ok    today: FixAfterARedCheckWaitsOnlyOnYou holds (7851776 distinct states found, 85.5 s)
ok    today, before #427 (idle swept once its row ended): MergeRedsMainOnlyOnAMissedTest holds (7851776 distinct states found, 59.7 s)
ok    today, before #427 (idle swept once its row ended): FlowsWhenGreen breaks (5573 distinct states found, 0.7 s)
ok    today, before #427 (idle swept once its row ended): MachineNotLeftFull breaks (4110 distinct states found, 0.7 s)
ok    today, before #427 (idle swept once its row ended): MainFixWaitsOnlyOnYou breaks (71345 distinct states found, 0.9 s)
ok    today, before #416 (busy leftovers only): MergeRedsMainOnlyOnAMissedTest holds (7851776 distinct states found, 57.4 s)
ok    today, before #416 (busy leftovers only): FlowsWhenGreen breaks (5560 distinct states found, 0.7 s)
ok    today, before #416 (busy leftovers only): MachineNotLeftFull breaks (4103 distinct states found, 0.6 s)
ok    today, before #416 (busy leftovers only): MainFixWaitsOnlyOnYou breaks (71471 distinct states found, 1.0 s)
every run says what it should
```

The rules of a model that must hold share one TLC run, so their lines share its count and time, and each rule that must break has a run of its own.
TLC runs on two workers, so the count of a run that breaks a rule varies a little from run to run.
Today's model has 7.9M states, where it had 10.5M at #946 and 2.6M before fl-rules-1103.
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
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    statechart from-spec FlowToday.tla --config FlowToday.chart.cfg --against FlowDesign.tla --label "the design" \
    --title "Does work keep flowing?" --out out --png)
```

Run it from the repo root, and copy the files of `$W/out`, but its `tlc/`, into `FlowToday-statechart/`.
`FlowToday.chart.cfg` checks the four rules on the model cut by `ChartCut`: no change breaks a browser test of its own, and no brief is edited.
The chart command holds TLC's whole state graph in memory: the whole model, 2.6M states before fl-rules-1103, took more than 27 GB before earlyoom stopped it.
The cut, 1.19M states at #946 and 1.04M since fl-no-draft, needed more than 14 GB at fl-spec-readme-docs's head, and earlyoom stopped it once, so run it with that much memory free.
TLC also keeps a disk queue of states under `TMPDIR`, and the cut's queue outgrew a `/tmp` tmpfs the machine's other work had filled, so the block puts `TMPDIR` on a disk with room (`$HOME/.cache` here).
With an edit and an outside break both in the cut, TLC 2.19 threw while its `-continue` run printed a path of the rule then named `NoMergeTurnsMainRed`.
`flow_canaries.py` checks every rule on the whole model.
The chart has no red path: since #946 no state of the cut breaks a rule, and at fl-no-draft's head its 65 states all work.
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
- A revert whose check fails (`reverts.stuck`), and a second revert of one row: the model keeps one revert open at a time, and its revert merges only while its culprit is still the red tip's, so once another merge landed on the red tip main's fix row ends the red, and jbus closes the revert.
- What a reverted row does next: it stays merged.
- What a culprit's head holds: TLC takes it to hold the green under the red tip or not (a skew), either way.
- Which stacked moves are a clean replay of the trees their check passed: TLC takes either, a pass kept or the check run again.
- A stacked link's check over its base's change: in the model it fails only on its own change and on main's red.
- A `Waived:` line, your other way past a review round that says the brief is not met, and a round that says so after the first.
- The red that ends at a fixing merge: the code ends it once jbus sees main's new tip green.

`FlowDesign.tla`'s `Sweep` clears every leftover, idle or busy, as soon as a turn ends, which the code did not until #427: from #416 it stopped a busy one, and an idle one only once its row ended.
The design also has both pull requests open from the start, so it has no launch and no row order, and it has no browser run.

## Where `Rejudge` and the code differ

- The model's `ranRed[p]` is a check that ran while main was red, and the code's condition is a base that has moved since the check started (`features/jmerge/src/jmerge/cli.py`, `Repo.again`).
  The code also judges again a check that failed over a base that was green and moved since, and a change broken on its own then fails again at the updated head as its own.
- The model judges again any red pull request, and the code only one whose single shortfall is the failed check: a pull request short of a review, a queue row or anything else keeps `check has failed` (`Repo.judge`).
- The model's `told[p]` is one flag that the crew's fix clears, and the code asks once for a head and a base tip, in `base-merges.json`, while jbus tells a crew once for a head.
- The model has one main, and the code reads each pull request's own base (`baseRefName`).
- The model leaves out a GitHub that refuses the update.
- The code checks no room before it judges again: GitHub runs the check at the updated head and nothing runs on this machine, so the model's `Rejudge` has no `~full`.
