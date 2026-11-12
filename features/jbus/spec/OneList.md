# The one list, as a TLA+ spec

`OneList.tla` models what waits on the user and the marks of what a home has read, at main aa5469d97 (2026-11-11): a gate in gates.md and in questions.json, gates-moved.md, the kinds of waiting-on-user.json, the streaks of streaks.json under streaks.lock, the disk's reading, the sign-in line, budget-hold.json, read-seen, and merge-seen with merge.log.
Each ledger row of the machine OneList (st-state-ledger) is a variable whose comment names the row and quotes the code that writes it.
The parts share only the project's passes and the lock, so Init picks the scene a behavior moves (alerts, gates or marks), and the others stay at their start.
`World` is the set of acts outside the code a run lets happen: a project that closes, a hand that cuts merge.log, and a gate asked by the home.
`OneList.map.py` labels the states and maps each kind of the list to the HomeTree `msg` it refines.

## Check the rules of the one list

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -workers 1 -config OneList.cfg OneList.tla
```

Run it in a copy of this folder.
The rules:

- `ListIsTrue`: an item is listed exactly while its cause holds, once the cause stays, so a cause that flips for ever asks nothing of the list.
  A project that runs no jmerge owes no jmerge alert, so the list leaves out each alert about a closed project (`jbus.alert.open_items`).
- `AnsweredLeaves`: once the user's answer, or the default by silence, settles a gate, gates.md gives the list no open gate of it and no question of it stays open.
- `ReadOnce`: the merging block shows each merge line once, and merge-seen counts no line as read that it did not show, also after merge.log is cut.

Today's code, in today's world, holds every rule.
A closed project's jmerge alert stays open in streaks.json, as `jmerge case-control` on disk, but the list leaves it out, so a close holds `ListIsTrue`.
Since st-one-list-home-marks, merge-seen names the last line of merge.log the merging block read, so a cut moves no line from unread to read (`ReadOnce`), and the handoff pipes a gate the home asked under the key it was asked under, so jbus asks it nothing again (`AnsweredLeaves`, `ListIsTrue`).
The canary `Fault = "stale-streak"`, a pass that leaves the stall alert from before, breaks `ListIsTrue` with no act; `Fault = "closed-listed"`, a list that keeps a closed project's alerts, as the code did before, breaks `ListIsTrue` where a project closes; `Fault = "mark-count"`, merge-seen as a count of lines, as it was, breaks `ReadOnce` where merge.log is cut; and `Fault = "ask-again"`, the handoff that piped the home's gate under the catch-all's key, as it did, breaks `AnsweredLeaves` and `ListIsTrue` where a gate is the home's.
`features/jbus/tests/test_one_list_spec.py` finds each quote once and runs each of these.

## Draw the chart of a gate

```sh
S=features/skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "../../../$S" \
    statechart from-spec OneList.tla --config OneList.chart.cfg \
    --title "Does a gate reach my list, and leave it once I answer?"
```

`OneList.chart.cfg` draws the gates scene alone: the other scenes have too many states to draw.
Its rules are about whole behaviors, which the chart does not draw: TLC's traces are in `OneList-statechart/tlc/`, which is not committed.

## What the one-list model leaves out

- The nine kinds of waiting-on-user.json other than `gate` are one item, each rebuilt by a pass from its source; their own lives are RowLife's and the other models'.
- jmerge's streak stands for every key of a project, and the stall key for the keys nothing raises any more; the pass's `pass` and `stale` streaks, `home thread`, `blocking`, `pool-held`, `t3-tool` and `once` keys are not modelled.
- Time: the threshold's span (`LASTING`), a `once` alert's end, the budget hold's ten minutes before `jbus needs` lists it, and the sign-in's week.
- A sign-in whose token file is gone: `remind` returns with the alert as it was.
- `jbus home status` shows the merge lines past the mark without moving it, and is not counted as shown.
- Two Results whose headings read the same: read-seen keys a heading by its text.
  No rule checks read-seen: the model keeps its first mark and the home's marks.
