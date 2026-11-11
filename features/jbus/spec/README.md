# A row's life, as a TLA+ spec

One row of jbus's queue, from `jbus queue add` to its end, in two regions at the same time.

- The status, which no verb moves: each pass works it out again from the facts (`work.status`), and `queue.derive` writes it, but over a row that is over (`work.over`), whose status it keeps (`work.kept`).
  The spec models the facts `work.status` reads, folded to what it tells apart: the thread (none, starting, at work, waiting, failed, ended), the Result (none, clean, leaving work), the pull request (none, open, merged, closed), a question, and the launch record.
  Each step changes one fact, and the pass derives the status they give.
  `Moves` in `RowLife.tla` is `queue.MOVES`, move for move, and `features/jbus/tests/test_rowlife_spec.py` fails when the two differ.
  `removed` is the line the `remove` verb writes, and no pass judges it.
- The go, which verbs and rules of `queue.py` move: an approve or a rule's go (`_grant`), a hold that may keep the go it took (`_hold`), a lift that puts a kept go back (`_lift`), and a go taken back from an unlaunched row (`_void`).
  jbus launches only an approved row, so `queued` to `launched` waits for the go.

`docs/jbus/row-moves.md` says what each move means and which faults the table leaves out.

## Check the rule

The rule is `FinalStays`: a row that is over stays over, so the queue, `watch.final` and jmerge, which all read `work.over`, never see a row over and then not.
A `done` row may only become `merged`, and a `merged` one stays so.
The facts can still leave a final row: a pull request opens after a `done`, or a question opens on a `merged` row.
The rule holds because `queue.derive` keeps the status (`work.kept`), and so checks the code's derive and not only the table.
`test_rowlife_spec.py` runs TLC on `RowLife.cfg`, where the rule holds over 1076 distinct states, and on a canary that takes `work.kept` out (`Fault = "no-latch"`), where it breaks.
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
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "../../../$S" \
    statechart from-spec RowLife.tla --title "A row's life" --png
```

It writes `RowLife-statechart/`: `chart.mmd` and `chart.png`, `stories.md` and `summary.json`, labelled by `RowLife.map.py`.
Each status on the chart says what in `work.py` sets it, and each step that moves the status is labelled by its row of `queue.MOVES`.
The regions draw 58 of their 85 arrows: a step whose next status turns on a fact the chart does not show, such as a pull request that merges from a row at `gate`, is left out, and `tlc/regions-all.mmd` has every one.
Its `tlc/` folder holds TLC's output, which is not committed.

## What the model leaves out

- The facts behind a status, past the folds above (a hung thread, a missing one, a Result that owes its pull request, each step of an open pull request): `test_jbus_queue_moves.py` walks every combination.
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

## Main's red, as a TLA+ spec

`MainRed.tla` models what jbus does when main goes red, as the code of main 21112eba8 does it.
Main's push run fails and jbus reruns it once (`watch._check`).
If the rerun fails too, `mainmoved.tell` writes the red tip to `main.json`, and `watch.retro` hands main's tip to `culprits.judge`.
`judge` reverts the tip's one clear culprit (`jbus.reverts`) or files main's fix row (`watch._file`).
A later merge turns main green: the revert, the fix, or a merge that happens to fix it.
After that, `reverts.close` closes a revert that is still open, and `watch._withdraw` takes out a fix row that never launched.
Each condition of a step names the file of the code that checks it and quotes that code in backticks, with no line number.
`features/jbus/tests/test_main_red_spec.py` finds each quote once in its file and checks that every condition is cited.
It also checks that the spec states each property `features/jbus/tests/main_red_model.py` walks over the real `tell`, and it runs TLC on both configs.

### The rules of main's red

- `OneRevertOpen`: at most one of jbus's reverts is open at a time.
  Main can go green at a later commit and then red again before a pass sees the green on its own.
  In that pass `culprits.judge` reads only the commits since that green, and may open a revert for the new red.
  `reverts.close` then closes each revert whose red is the green or older, even though main's tip is red (`cleared`), so the first revert never waits for jmerge beside the second.
  The green can come from a fix row's merge, from a red of two flakes that a later merge made green, or from a rerun by hand that turned the red commit itself green.
  The red can come from two merges between passes, where the older failed one is never rerun, or from a rerun that GitHub refused.
- `RedEndsOnlyByAMerge`: a red whose code is broken ends only at a green commit that a later merge made.
  No step of jbus's ends a red.
  Only a run that failed twice by chance turns green at its own commit, through a rerun by hand that `tell` reads again (`again=tip in (main, stands)`).
- The four properties `main_red_model.py` walks, here as the state a pass leaves:
  - `KnownRedReadAsRed` (S1)
  - `NoStuckRed` (S2)
  - `RedTipsOwnTests` (S3)
  - `EachRedJudgedOnce` (S4)

### Check the rules of main's red

The command below is the brief's check.
Run it from this folder, with the pinned jar copied in:

```sh
cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar . && java -cp tla2tools.jar tlc2.TLC -config MainRed.cfg MainRed.tla; rm -rf tla2tools.jar states
```

It exits 0: every rule holds over 113,042 distinct states (MaxTips 4), in about a minute on two workers.
The test runs TLC on both configs, and on each rule of `BREAKS` alone, which is empty while the code breaks no rule.

### Draw the chart of main's red

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
D=$HOME/.cache/jstack/tlc-tmp && mkdir -p "$D"
W=$(TMPDIR=$D mktemp -d) && cp features/jbus/spec/MainRed.* "$W"
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    statechart from-spec MainRed.tla --config MainRed.chart.cfg \
    --title "Main went red: what fixes it?" --out out --png)
```

Run it from the repo root.
Then copy the files of `$W/out` into `MainRed-statechart/`, all except `tlc/`.
`MainRed.chart.cfg` has the same rules on up to three commits (6,145 states), and it draws 10 chart states and 44 steps.
The four commits of `MainRed.cfg` draw too many states and steps for Mermaid to render as a PNG.
No state breaks a rule, so it draws no `bug-N` chart.

### What the main-red model leaves out

- A cancelled, batched or job-less run (`watch.BATCHED`, `NO_JOB`, `cancelled`, `refused`): none of them is red.
- Logs `tell` cannot read, a project's first pass, a culprit's row removed from the queue, and a GitHub that does not say what main a culprit's check passed over, which waits as `UNREAD` until `READ_WAIT`.
  TLC's `skew` files the row at once.
- `close` dropping the record of a revert whose culprit's slug is over (`over`), after which `OPENED` and `TWICE` no longer see it.
- `main-reds.jsonl` keeps only the red tip of each pass, where `tell` writes a line for each failed commit it walks.
- The Mac run (`reverts.macos`), the browser run, and the fix row's crew ending with no pull request.
- Time: TLC chooses on each pass whether the red tip is older than `READ_WAIT` (`late`).

## The green move, as a TLA+ spec

`GreenMove.tla` follows one green copy (`jbus/green.py`) as passes move it to main's green tip, with a pass that can die between any two steps.
A move grows the new tip's tree, writes the step it owes to `green.json` (`move`, `owes: install`), points the link, installs the tool again, writes `owes: relink`, removes the trees no command runs, and puts the harness layouts again (`jinstall.green.relink`), and only a relink that is taken drops `move`.
Each pass resumes an owed step (`_resume`) before `_advance` reads main.json.
An install uv refuses, which may have removed the tool first, sends the move back: it owes the install of the tree it came from, with the reload systemd was owed before it, points the link back, removes the new tree, and installs the tool and relinks from the tree it went back to.
Each step's comment quotes the code it stands for.

### Check the rules of the green move

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -deadlock -config GreenMove.cfg GreenMove.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
`-deadlock` is there because a copy at main's last tip has no step left to take.
Today's code holds every rule, over 10477 distinct states with MaxTip 3:

- `ToolRunsCopy`: once no pass is in a move and none is owed, the tool runs the tree the link names, so a unit never starts on a tool the copy no longer holds.
- `ToolTreeThere`: the tree the tool runs, where uv left one, is on disk.
- `LayoutsFollow`: once no pass is in a move and none is owed, the layouts were put from the tree the link names, also after a move whose install failed went back.
- `NoReloadForRemoved`: `green.json` owes systemd no reload for a tip whose move went back, so none runs for a tip that never became the copy.

The canary, `Fault = "no-owed"`, keeps no step in `green.json`, as the code did before st-green-step.
`ToolRunsCopy` and `LayoutsFollow` each break in five states: main goes green, the move points the link, and the pass dies, the journal's 203/EXEC on `~/.local/bin/jbus`.
The second canary, `Fault = "no-back"`, goes back as the code did before st-green-back: it owes a relink and no install of the tree it went back to, and keeps the reload it wrote for the tip it removed.
`ToolRunsCopy` breaks when the failed install removed the tool, and `NoReloadForRemoved` breaks once the move goes back.
`features/jbus/tests/test_green_move_spec.py` runs TLC on the config and on each canary for the two rules it breaks.

### What the green-move model leaves out

- uv's install and the write of `owes: relink` after it are one step: a pass that dies between them installs again, which is the same install, and the model does not let that second install fail.
- A tip that does not import (`refused`) and the units a move puts to work (`live`): each has its own record, which the move does not change. Of the reload a move owes systemd it keeps only `at`, and whether systemd takes it.
- A tree a move went to that is gone on resume, which only a hand can remove: `_resume` goes back (`_back`) as a failed install does.
