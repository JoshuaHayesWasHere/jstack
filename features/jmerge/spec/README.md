# The merge flow, as a TLA+ spec

Two rows, a main that can go red from a merge or from outside, and a machine that a crew can leave full.
The home wrote it on 2026-10-23 to test the premise behind "nothing moves", and it came in with rejudge-red-prs.

- `FlowToday.tla` models the code as of main 859203e0, and each of its conditions names the file that checks it and quotes the code, with no line number.
  `test_flow_spec.py` finds the one place each quote stands, so a rebase that moves the lines leaves no cite to renumber.
  It is the flow-statechart scout's `FlowNow.tla` of main 6485914, kept with the scout's report and not in the repo, with #416, #426 and #427 since and cut down to what the four rules read.
  Since #583 and #584 it has main's fix as `jmerge.rows.red` takes it: the `main-red-` row, or a pull request whose own check proved the fix, and the row's crew may end with no pull request, its fix in an open one.
  Since #575 and #577 it has each pull request's browser run, which holds it when it failed, and main's browser red, which holds it as main's red while the fix jbus filed for that run is open.
- `FlowDesign.tla` models the design: cross-cutting-guard (`Check`), rejudge-red-prs (`Rejudge`) and crew-leftover-procs (`Sweep`), with today's fix path.
- `canary/` holds the design with each fix taken out: `NoGuard`, `NoRejudge`, `NoSweep` and `NoProof`, which has `rows.red` as it was before #583.
- `flow_canaries.py` runs TLC on all of it, and `FlowToday.map.py` labels the chart in `FlowToday-statechart/`.

## Check the rules

```sh
S=features/skill-library/skills/statechart/scripts
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    python features/jmerge/spec/flow_canaries.py
```

Run it from the repo root.
Today's code breaks two rules, `NoMergeTurnsMainRed` and `MainFixWaitsOnlyOnYou`, and holds the other two.
It breaks `NoMergeTurnsMainRed` because a check can still miss a test that reads the changed path.
`scripts/select_tests.py` runs every test no rule owns (#397), and each test whose `READ_SET` matches the changed path (#426).
`testing/tests/test_cross_cutting.py` makes a test that globs or walks the tree declare a read set, but it sees only the reads it knows.
A test that reads the path another way, or past its read set, is selected by chance, so the model keeps that chance.
It breaks `MainFixWaitsOnlyOnYou` once main's fix row has closed with its fix in an open pull request, whose check proves the fix only when it ran each test main failed.
`scripts/select_tests.py` selects by the diff and not by `main.json`'s `failed`, so a fix's check runs those tests by the same chance, and a red whose logs name no failed test is proved by nothing.
Then nothing can merge, and no row is left for you to approve, as on 2026-10-27.
It breaks the same rule when the pull request that carries the fix also breaks a test of its own: its check fails over the red main, its crew reads the failure as main's, and jmerge judges it again only once main is green.
The design holds all four: its check runs every test that reads the tree, and the crew of a fix reads a failure over the red it fixes as its own.
`NoGuard` breaks `NoMergeTurnsMainRed`, `NoRejudge` breaks `FlowsWhenGreen`, and `NoSweep` breaks `FlowsWhenGreen` and `MachineNotLeftFull`.
`NoProof` breaks `MainFixWaitsOnlyOnYou`: the main-red row ends with its fix in an open pull request, whose check proves the fix, and `rows.red` before #583 holds it all the same.
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
    statechart from-spec FlowToday.tla --against FlowDesign.tla --label "the design" \
    --title "Does work keep flowing?" --out out --png \
    --expect-broken NoMergeTurnsMainRed --expect-broken MainFixWaitsOnlyOnYou)
```

Run it from the repo root, and copy the files of `$W/out`, but its `tlc/`, into `FlowToday-statechart/`.
The design starts with both pull requests open, so each story says the design starts on another screen.

## What the code model leaves out

`FlowToday.tla` has only the variables the four rules read, and the scout's `FlowNow.tla` has the rest.

- The queue before a row's go: the home's brief, your approval, a brief edited after it (#399), and which home a word goes to (#402).
- The review, its clock and your nudge, a conflict and its rebase, and what reaches you.
- A crew at work: a crew's turn is one step, so `Gap = "turn"` stops every idle process.
- A process that holds a test slot, which jbus.strays leaves running since #427: the model takes it to end with its check.
- A row that ends other than by merging: done, left, or its worktree gone.
- The account caps, GitHub's API budget, cancelled checks, the nightlies other than browser.yml's, and those of integration branches.
- A draft, whose browser run is waived as its failed checks are: the model's pull requests are past their review.
- A pull request whose own browser run proves the fix of main's browser red: the browser-red row is main's only fix there.
- A fix row that ends with no fix anywhere, which leaves main red with nothing to merge until you queue another.
- A fix row that launched and is left to its crew once main is green: the model's fix row is queued until you approve it, and the approval is the whole of its work.
- The red that ends at a fixing merge: the code ends it once jbus sees main's new tip green.

`FlowDesign.tla`'s `Sweep` clears every leftover, idle or busy, as soon as a turn ends, which the code did not until #427: from #416 it stopped a busy one, and an idle one only once its row ended.
The design also has both pull requests open from the start, so it has no launch and no row order, and it has no browser run.

## Where `Rejudge` and the code differ

- The model's `ranRed[p]` is a check that ran while main was red, and the code's condition is a base that has moved since the check started (`features/jmerge/src/jmerge/cli.py`, `Repo.again`).
  The code also judges again a check that failed over a base that was green and moved since, and a change broken on its own then fails again at the updated head as its own.
- The model judges again any red pull request, and the code only one whose single shortfall is the failed check: a pull request short of a review, a queue row or anything else keeps `check has failed` (`Repo.judge`).
- The model's `told[p]` is one flag that the crew's fix clears, and the code asks once for a head and a base tip, in `base-merges.json`, while jbus tells a crew once for a head.
- The model has one main, and the code reads each pull request's own base, main or an integration branch.
- The model leaves out a GitHub that refuses the update.
- The code checks no room before it judges again: GitHub runs the check at the updated head and nothing runs on this machine, so the model's `Rejudge` has no `~full`.
