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
  A tip with more than one merge since the last green, a culprit whose head lacks the green under the tip (a skew, #899), or a red from outside gets main's fix row instead, and jbus closes a revert still open once main is green without it (#899).
  jbus's pass approves both fix rows it files, main's and the browser run's, by rule and not by your word (#547).
  A stacked link is marked ready and checked while it sits on its base's open branch, and its move onto main may keep that pass (`jmerge.reuse`, #868).
  jbus takes a link off its stack once its brief's `Builds on:` line no longer names its open base (#846, #877), which in the model takes an edit of the brief, since every depends names its base.
  A pull request whose last review round says the brief is not met is held (`MEETS_NO`, #843), and jbus tells its crew, which meets it (#850).
  Since #575 and #577 it has each pull request's browser run, which holds it when it failed, and main's browser red.
  Since cut 11 of the simplify pass it has a row's go, which jbus asks at launch and jmerge at merge (`rows.py` `ROW_HELD`, `NO_GO`), and a hold for your word, as a change that touches a protected path has (`ready.py` `TOUCHES`).
  A crew opens its pull request as a draft, and the draft's check waits on its review: jmerge marks it ready only once the draft is all it waits on.
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
Today's code breaks three rules, `FlowsWhenGreen`, `NoMergeTurnsMainRed` and `MainFixWaitsOnlyOnYou`, and holds `MachineNotLeftFull`.
At main 035d4e297 it prints, for today's code:

```text
ok    today: FlowsWhenGreen breaks (4909 distinct states found, 0.7 s)
ok    today: NoMergeTurnsMainRed breaks (106934 distinct states found, 1.1 s)
ok    today: MachineNotLeftFull holds (2573438 distinct states found, 19.0 s)
ok    today: MainFixWaitsOnlyOnYou breaks (290878 distinct states found, 2.2 s)
```

The four verdicts are those of the spec before fl-flowtoday-1102, which modeled main 859203e0.
`FlowsWhenGreen` says work settles merged or waiting on your word: your approval of a row, or `jmerge --accept` of a hold.
It breaks on a draft that touches a protected path.
`Repo.judged` returns the hold before it reaches `if one.draft:`, and jmerge marks a draft ready only when its reason is the draft (`READY_ON`), so the draft stays one.
`jmerge --accept` lifts the hold, finds the draft's wait under it, and refuses, so your word cannot move it either.
A control sets `FlowToday.tla`'s constant `Draft` to `readied`, which marks such a draft ready, and `FlowToday.cfg` sets it to `held`, the code.
The control holds `FlowsWhenGreen`, so that draft is its only break, and breaks the probe `NoLift`, so your word lifts a hold there.
It breaks `NoMergeTurnsMainRed` because a check can still miss a test that reads the changed path.
`scripts/select_tests.py` runs every test no rule owns (#397), and each test whose `READ_SET` matches the changed path (#426).
`testing/tests/test_cross_cutting.py` makes a test that globs or walks the tree declare a read set, but it sees only the reads it knows.
A test that reads the path another way, or past its read set, is selected by chance, so the model keeps that chance.
It breaks `MainFixWaitsOnlyOnYou` on the same draft: main is red from outside, its rerun fails, jbus files the fix row and approves it by rule, and the pull request its crew puts the fix in is that draft, so nothing but your word could move it, and your word cannot.
Since #547 no fix row waits on your approval, so of the rule's waits only your word is yours: the go of a row you held or whose brief changed, and the lift of a pull request's hold.
The control that marks such a draft ready still breaks it, on a fix in the merge_after follow-up of a pull request whose check failed over the red main: jmerge judges that pull request again only once main is green, and the follow-up with the fix merges only after it.
Until fl-flowtoday-1102 the control's shortest break was a fix stacked on that pull request; with #868 the shortest is the merge_after one, and the stacked one still waits for its base.
Until red-main-no-hold it broke the rule another way as well: while main was red only a fix whose own check proved it merged, so a fix row closed with its fix in an open pull request whose check ran other tests left nothing to merge and nothing for you to approve, as on 2026-10-27.
The design holds all four, in the words they had before the holds: its check runs every test that reads the tree, and the crew of a fix reads a failure over the red it fixes as its own.
`NoGuard` breaks `NoMergeTurnsMainRed`, `NoRejudge` breaks `FlowsWhenGreen`, and `NoSweep` breaks `FlowsWhenGreen` and `MachineNotLeftFull`.
Two controls run the model with an earlier `Gap`, `FlowToday.tla`'s constant, which `FlowToday.cfg` sets to `turn`, the code since #427.
With `ended`, the code from #416 to #427, which stops an idle process a crew left only once its row ended, it breaks all four rules.
With `busy`, the code before #416, which stops only a process that uses CPU, it breaks all four too.
In both an idle process a crew left at its pull request, a `sleep` or a headless browser waiting, keeps the machine full.
Then a follow-up that merges after its row launches first and its row never launches, and main's fix cannot launch either.
`features/jmerge/tests/test_flow_spec.py` runs it, and skips where no Java runs TLC.

## Draw the chart

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
W=$(mktemp -d) && cp features/jmerge/spec/FlowToday.* features/jmerge/spec/FlowDesign.* "$W"
(cd "$W" && UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    statechart from-spec FlowToday.tla --config FlowToday.chart.cfg --against FlowDesign.tla --label "the design" \
    --title "Does work keep flowing?" --out out --png \
    --expect-broken FlowsWhenGreen --expect-broken NoMergeTurnsMainRed --expect-broken MainFixWaitsOnlyOnYou)
```

Run it from the repo root, and copy the files of `$W/out`, but its `tlc/`, into `FlowToday-statechart/`.
`FlowToday.chart.cfg` checks the four rules on the model cut by `ChartCut`: no change breaks a browser test of its own, and no brief is edited, so the chart has no unstack.
The chart command holds TLC's whole state graph in memory, and the whole model, 2.6M states, took more than 27 GB before earlyoom stopped it.
With an edit and an outside break both in the cut, TLC 2.19 throws while its `-continue` run prints a path of `NoMergeTurnsMainRed`.
`flow_canaries.py` checks every rule on the whole model.
The chart draws no revert: the command stops each path at the first state that breaks a rule, and jbus reverts only a merge that turned main red, which breaks `NoMergeTurnsMainRed`.
The design starts with both pull requests open, so each story says the design starts on another screen.

## What the code model leaves out

`FlowToday.tla` has only the variables the four rules read, and the scout's `FlowNow.tla` has the rest.

- The queue before a row's go: the home's brief and which home a word goes to (#402); each row starts with your go, and a brief edited after it (#399) is a hold you lift by approving it again.
- The review as more than one step: its findings, its clock and your nudge, a conflict and its rebase, and what reaches you.
- Holds for your word other than a protected path (a dropped line, a decline, a gate), each one `needs`, and a merge gate, which only a passing gate lifts.
- A brief that says `Review: none`, whose draft jmerge marks ready at once and which waits on your word.
- A crew at work: a crew's turn is one step, so `Gap = "turn"` stops every idle process.
- A process that holds a test slot, which jbus.strays leaves running since #427: the model takes it to end with its check.
- A row that ends other than by merging: done, left, or its worktree gone.
- The account caps, GitHub's API budget, cancelled checks, and the nightlies other than browser.yml's.
- A draft's browser run, which is waived as its failed checks are: a draft in the model has run no check.
- A pull request whose own browser run proves the fix of main's browser red: the browser-red row is main's only fix there.
- A fix row that ends with no fix anywhere, which leaves main red with nothing to merge until you queue another.
- A fix row that launched and is left to its crew once main is green: the model's fix row is queued until jbus's pass approves it by rule and it launches, and that launch is the whole of its work.
- A revert whose check fails (`reverts.stuck`), and a second revert of one row: the model keeps one revert open at a time, and its revert merges only while its culprit is still the red tip's, so once another merge landed on the red tip main's fix row ends the red, and jbus closes the revert.
- What a reverted row does next: it stays merged.
- What a culprit's head holds: TLC takes it to hold the green under the red tip or not (a skew), either way.
- Which stacked moves are a clean replay of the trees their check passed: TLC takes either, a pass kept or the check run again.
- A stacked link's check over its base's change: in the model it fails only on its own change and on main's red.
- jbus.stack's test of whether a link's own change needs its base's: a link whose brief no longer names its base comes off its stack.
- A `Waived:` line, your other way past a review round that says the brief is not met, and a round that says so after the draft's first.
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
