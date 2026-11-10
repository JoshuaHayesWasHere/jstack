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
