# A row's life, as a TLA+ spec

One row of jbus's queue, from `jbus queue add` to its end, in two regions at the same time.

- The status, which no verb moves: each pass works it out again from the facts (`work.status`), and `queue.derive` writes it.
  `Moves` in `RowLife.tla` is `queue.MOVES`, move for move, and `features/jbus/tests/test_rowlife_spec.py` fails when the two differ.
  `removed` is the line the `remove` verb writes, and no pass judges it.
- The go, which verbs and rules of `queue.py` move: an approve or a rule's go (`_grant`), a hold that may keep the go it took (`_hold`), a lift that puts a kept go back (`_lift`), and a go taken back from an unlaunched row (`_void`).
  jbus launches only an approved row, so `queued` to `launched` waits for the go.

`docs/jbus/row-moves.md` says what each move means and which faults the table leaves out.

## Check the rule

The rule is `FinalStays`: a row that merged or is done stays so, since jmerge and `watch.final` read a row that leaves as not final.
The spec models the table each pass judges a move by, so the rule says the table holds no move out of `merged` or `done`.
`test_rowlife_spec.py` runs TLC on `RowLife.cfg`, where the rule holds, and on a canary that adds the fault `done` to `pr` (`Fault = "done-pr"`), where it breaks.
Its TLC runs skip where no Java runs TLC.

## Draw the chart

```sh
S=features/skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "../../../$S" \
    statechart from-spec RowLife.tla --title "A row's life" --png
```

It writes `RowLife-statechart/`: `chart.mmd` and `chart.png`, `stories.md` and `summary.json`, labelled by `RowLife.map.py`.
Each status on the chart names the line of `work.py` that sets it.
Each step has a label of its own, so the regions draw every one of TLC's 46 arrows.
Its `tlc/` folder holds TLC's output, which is not committed.

## What the model leaves out

- The facts behind a status (thread, launch, Result, pull request, question): `test_jbus_queue_moves.py` walks them.
- The moves a pass saw that the table leaves out: a pass marks each one `"legal": false` in `transitions.jsonl` and writes it all the same.
- The scout's row, which `work.scouting` reads, and a row's `depends` and `merge_after`.

## A crew thread, as a TLA+ spec

`ThreadLife.tla` follows one crew thread of one row through jbus's code at main 21112eba8 (2026-11-10).
It starts at the launch record a pass writes (`jbus/dispatch.py`), and goes through the words `jbus/live.py` gives the thread's turn and the carry-ons `jbus/threads.py` `resume` sends.
It ends with the thread put away and its scratch cleared (`jbus/threads.py` `settle`), or with the row its home's: jbus told the home.
Each condition of a step names the file that checks it and quotes the code there, with no line number.
`features/jbus/tests/test_thread_life_spec.py` finds the one place each quote stands, so a move of the lines leaves no cite to renumber.
It also runs TLC on today's code and on the canary.

### Check the rules of the thread

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config ThreadLife.cfg ThreadLife.tla
```

TLC writes a `states/` folder where it runs, so run it in a copy of this folder.
Today's code holds every rule, in 2974 states:

- `ThreadEnds`, "a thread ends archived or with its home told": every thread jbus holds, one its launch record names, is archived in the end, or jbus told its home that the row is the home's.
- `ScratchGoes`: a thread put away, settled or archived, has its scratch cleared.
- `CarryOnsBounded`: jbus sends a thread at most two carry-ons.
- `ArchivesFinished`: jbus archives only a finished slug's thread, and only once its turn is over.

A home is told in one of three ways:

- `_stopped`: a turn that failed with no Result, after two carry-ons.
- `leftover.tell`: a Result that leaves something, or a turn that completed or hung with nothing written.
- The stall ladder of `jbus/children.py`: a home with a row out whose crew writes nothing is nudged.

The canary, `Drop = "ladder"`, takes the stall ladder out, and `ThreadEnds` breaks.
In its shortest story the crew asks you something and its request waits.
The ladder also carries a crew that jbus told once to open the pull request its Result owes, if that crew ends again with nothing new written.
`resume` sends that tell once for the thread, `finished` leaves a slug that owes out, and `leftover` counts an owing Result as nothing written while its thread is quiet.

### Draw the chart of the thread

```sh
S=../../skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    statechart from-spec ThreadLife.tla --title "What does jbus do with a thread, launch to archive?" --png
```

It writes `ThreadLife-statechart/`: `chart.mmd` and `chart.png`, `stories.md` and `summary.json`, with labels from `ThreadLife.map.py`.
Its `tlc/` folder holds TLC's output, which is not committed.
The chart has two regions: who has the thread (launching, gated, out, its home's, put away), and where it stands.
No state breaks a rule, so it draws no `bug-N` chart.

### What the thread model leaves out

- The home's thread: the model takes it as there and quiet in the end.
  With no home thread, `_stopped` and `leftover` make the row a gate of yours, and the catch-all's home is started again by `children.keep_alive`.
  A home that keeps writing restarts its stall spell.
- A thread made by a lost launch that the lookup does not find: that is a gate of yours, and jbus holds no thread for it.
- A settled thread that a message wakes, a turn that waits on a test slot (`World.awaits`), a row removed from the queue, and the `MERGED` message to a crew whose Result leaves work for after the merge.
- Scouts, reviewers, and failover to another instance.
