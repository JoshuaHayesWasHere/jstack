# A row's life, as a TLA+ spec

One row of jbus's queue, from `jbus queue add` to its end, in two regions at the same time.

- The status, which a pass moves: each pass works it out again from the facts (`work.status`), and `queue.derive` writes it, but over a row that is over (`work.over`), whose status it keeps (`work.kept`).
  Three writes move it too, each with a line of its own: `remove`, the add of a crewmate's brief over a scout's done row (`HandOver`), which makes the row a crewmate's, queued again with no go and none of the scout's facts, and the merge of the revert jbus opened of a merged row's merge (`Reland`, `reverts.reland`), which moves the row to `left` once per merge taken back and makes that merge no merge of the row's (`reverted`), so its redo goes the normal path.
  The row's role, scout or crew, is fixed when it is added, and only the hand-over changes it.
  The spec models the facts `work.status` reads, folded to what it tells apart: the thread (none, starting, at work, hung, waiting, failed, ended, settled, missing), the Result (none, clean, leaving work), the pull request (none, opening, open, merged, closed), a question, and the launch record.
  Each step changes one fact, and the pass derives from them the line's value in `work.json` (`value`, the first of `work.PATTERNS` they match) and the status that value gives, as `work.status` reads it.
  The eight steps of an open pull request are one value, `check`, and `quiet` is `working`; `test_rowlife_spec.py` fails when `work.VALUES` gains a value the spec neither has nor names as joined.
  `queue.MOVES` is each change of status one step of TLC's graph of the spec makes but the hand-over's, and `features/jbus/tests/test_rowlife_spec.py` fails when the two differ.
  A thread T3 Code settles with nothing written makes a launched row `stale`, as one that completed or was archived does (`work._THREAD`), so a launched row never goes back to `queued`.
  A pull request in neither of GitHub's lists reads as closed only while the Result's `Branch:` line names its address, and as none otherwise (`watch.pull`), so a row whose pull request closed may be `done`.
  `removed` is the line the `remove` verb writes, from any status but `merged` and `done`, which `remove` refuses (`Remove`).
- The go, which verbs and rules of `queue.py` move: an approve or a rule's go (`_grant`), a hold that may keep the go it took (`_hold`), a lift that puts a kept go back (`_lift`), and a go taken back from an unlaunched row (`_void`).
  An approved row whose `depends` are not all over is `behind` until they are (`Ahead`), and jbus launches it stacked all the same.
  An `add` that changes an approved row's depends moves it between free and behind (`Depends`), and its line keeps its value until the next pass (`Pass`), since `restated.restate` keeps an approved facet beside another.
  jbus launches only an approved row, so `queued` to `launched` waits for the go.

`docs/jbus/row-moves.md` says what each move means and which faults the table leaves out.

## Replay a real log

`statechart replay` walks each line of a project's `transitions.jsonl` over TLC's graph of the spec, read by `RowLife.trace.py`, and names each line no step of the model makes:

```sh
S=features/skill-library/skills/statechart/scripts L=~/.local/state/jbus/<project>/transitions.jsonl
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "../../../$S" \
    statechart replay RowLife.tla --trace RowLife.trace.py --log "$L"
```

A pass's line matches a path of steps that are no verb's, a hand-over's line (`handed`) one `HandOver` step, a reland's line (`reverted`) one `Reland` step, a removal one `Remove` step, and a line that moves the go (`queue._go`) one step of `Grant`, `Hold`, `Lift` or `Void`.
`features/jbus/tests/test_rowlife_replay.py` replays a fixture of 138 of jstack's own lines, and skips where no Java runs TLC.

## Check the rule

The rule is `FinalStays`: a crewmate's row that is over stays over, so the queue, `watch.final` and jmerge, which all read `work.over`, never see it over and then not.
A `done` row may only become `merged`, and a `merged` one stays so but for one `Reland` for each merge a revert took back, so a redo whose own merge is reverted opens the row again.
The facts can still leave a final row: a pull request opens after a `done`, or a question opens on a `merged` row.
The rule holds because `queue.derive` keeps the status (`work.kept`), and so checks the code's derive and not only the table.
`test_rowlife_spec.py` runs TLC on `RowLife.cfg`, where the rule holds over 12716 distinct states, on two canaries where it breaks, one that takes `work.kept` out (`Fault = "no-latch"`) and one that lets the hand-over take a crewmate's done row too (`Fault = "any-hand-over"`), and on one that gives a settled thread's row `queued` again (`Fault = "settled-queued"`), whose graph has status edges `queue.MOVES` lacks.
A scout's done row leaves `done` only by the hand-over, which makes it a crewmate's, and a crewmate's row never leaves.
Its TLC runs skip where no Java runs TLC.
By hand, in a copy of this folder:

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config RowLife.cfg RowLife.tla
```

## Draw the chart

```sh
S=features/skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "../../../$S" \
    statechart from-spec RowLife.tla --title "A row's life"
```

It writes `RowLife-statechart/`: `chart.mmd`, `stories.md` and `summary.json`, labelled by `RowLife.map.py`.
No chart's PNG or Excalidraw scenes, nor the charts page, is committed: `make charts`, at the repo's root, draws them from each committed `chart.mmd` into a folder git ignores, and prints the page's path.
Each status on the chart says what in `work.py` sets it, and each step that moves the status is labelled by its row of `queue.MOVES`.
The regions draw 87 of their 119 arrows: a step whose next status turns on a fact the chart does not show, such as a pull request that merges from a row at `gate`, is left out, and `tlc/regions-all.mmd` has every one.
Its `tlc/` folder holds TLC's output, which is not committed.

## What the model leaves out

- The facts behind a status, past the folds above (a Result that owes its pull request, each step of an open pull request): `test_jbus_queue_moves.py` walks every combination.
- A restate between passes (`restated.restate`) that the next pass corrects, the `work-drift` event: here a fact's change and the pass that sees it are one step, but for the depends an `add` changes (`Depends`).
  So is a pass that heard from GitHub or T3 Code alone, which keeps the last value unconfirmed.
- The faults the table leaves out: a pull request read in neither of GitHub's lists while the row has one, and a thread, Result or pull request of a row with no launch record.
  A pass marks each one `"legal": false` in `transitions.jsonl` and writes it all the same, and `statechart replay` names it.
- The live guards of `remove`: a thread at work, an open or merged pull request, a launch with no answer yet, which read T3 Code and GitHub at that moment.
- What of a scout's row `scouted.scouting` reads, past its role and the hand-over, and a row's `merge_after`.
