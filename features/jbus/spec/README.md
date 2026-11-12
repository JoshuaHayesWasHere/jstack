# A row's life, as a TLA+ spec

One row of jbus's queue, from `jbus queue add` to its end, in two regions at the same time.

- The status, which no verb moves: each pass works it out again from the facts (`work.status`), and `queue.derive` writes it, but over a row that is over (`work.over`), whose status it keeps (`work.kept`).
  The spec models the facts `work.status` reads, folded to what it tells apart: the thread (none, starting, at work, hung, waiting, failed, ended, settled, missing), the Result (none, clean, leaving work), the pull request (none, opening, open, merged, closed), a question, and the launch record.
  Each step changes one fact, and the pass derives from them the line's value in `work.json` (`value`, the first of `work.PATTERNS` they match) and the status that value gives, as `work.status` reads it.
  The eight steps of an open pull request are one value, `check`, and `quiet` is `working`; `test_rowlife_spec.py` fails when `work.VALUES` gains a value the spec neither has nor names as joined.
  `Moves` in `RowLife.tla` is `queue.MOVES`, move for move, and `features/jbus/tests/test_rowlife_spec.py` fails when the two differ.
  `removed` is the line the `remove` verb writes, and no pass judges it.
- The go, which verbs and rules of `queue.py` move: an approve or a rule's go (`_grant`), a hold that may keep the go it took (`_hold`), a lift that puts a kept go back (`_lift`), and a go taken back from an unlaunched row (`_void`).
  An approved row whose `depends` are not all over is `behind` until they are (`Ahead`), and jbus launches it stacked all the same.
  jbus launches only an approved row, so `queued` to `launched` waits for the go.

`docs/jbus/row-moves.md` says what each move means and which faults the table leaves out.

## Check the rule

The rule is `FinalStays`: a row that is over stays over, so the queue, `watch.final` and jmerge, which all read `work.over`, never see a row over and then not.
A `done` row may only become `merged`, and a `merged` one stays so.
The facts can still leave a final row: a pull request opens after a `done`, or a question opens on a `merged` row.
The rule holds because `queue.derive` keeps the status (`work.kept`), and so checks the code's derive and not only the table.
The second rule is `MovesKnown`: each move of the status is in `Moves`, so the table is the one `work.status` makes, and a pass marks `"legal": false` only on a fault the model leaves out (a pull request read in neither of GitHub's lists, a row with no launch record, a `Branch:` line that loses the address of a closed pull request), each of which `test_jbus_queue_moves.py` names.
`test_rowlife_spec.py` runs TLC on `RowLife.cfg`, where both rules hold over 2445 distinct states, on a canary that takes `work.kept` out (`Fault = "no-latch"`), where `FinalStays` breaks, and on one that gives a settled thread's row `queued` again (`Fault = "settled-queued"`), where `MovesKnown` breaks.
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
    statechart from-spec RowLife.tla --title "A row's life"
```

It writes `RowLife-statechart/`: `chart.mmd`, `stories.md` and `summary.json`, labelled by `RowLife.map.py`.
No chart's PNG or Excalidraw scene, nor the charts page, is committed: `make charts`, at the repo's root, draws them from each committed `chart.mmd` into a folder git ignores, and prints the page's path.
Each status on the chart says what in `work.py` sets it, and each step that moves the status is labelled by its row of `queue.MOVES`.
The regions draw 64 of their 112 arrows: a step whose next status turns on a fact the chart does not show, such as a pull request that merges from a row at `gate`, is left out, and `tlc/regions-all.mmd` has every one.
Its `tlc/` folder holds TLC's output, which is not committed.

## What the model leaves out

- The facts behind a status, past the folds above (a Result that owes its pull request, each step of an open pull request): `test_jbus_queue_moves.py` walks every combination.
- A restate between passes (`restated.restate`) that the next pass corrects, the `work-drift` event: here a fact's change and the pass that sees it are one step.
  So is a pass that heard from GitHub or T3 Code alone, which keeps the last value unconfirmed.
- The faults the table leaves out, which a pass marks `"legal": false` in `transitions.jsonl` and writes all the same: a pull request that leaves GitHub's open list unmerged and unclosed, a thread, Result or pull request of a row with no launch record, and a `Branch:` line that loses the address of a closed pull request.
  So the model never makes `pr` to `done` either, a move of the table.
- The scout's row, which `work.scouting` reads, and a row's `merge_after`.

## A crew thread, as a TLA+ spec

`ThreadLife.tla` follows one crew thread of one row through jbus's code at main 21112eba8 (2026-11-10).
It starts at the launch record a pass writes (`jbus/dispatch.py`), and goes through the words `jbus/live.py` gives the thread's turn and the carry-ons `jbus/threads.py` `resume` sends.
It ends with the thread put away and its scratch cleared (`jbus/threads.py` `settle`), or with the row its home's: jbus told the home.
Each condition of a step names the file that checks it and quotes the code there, with no line number.
`features/jbus/tests/test_spec_quotes.py` finds the one place each quote stands, in this spec, `RowLife.tla` and `GreenMove.tla`, so a move of the lines leaves no cite to renumber.
`features/jbus/tests/test_thread_life_spec.py` runs TLC on today's code and on each canary.

### Check the rules of the thread

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config ThreadLife.cfg ThreadLife.tla
```

TLC writes a `states/` folder where it runs, so run it in a copy of this folder.
Today's code holds every rule, in 45694 distinct states:

- `ThreadEnds`, "a thread ends archived or with its home told": every thread jbus holds, one its launch record names, is archived in the end, or jbus told its home that the row is the home's, or, with no home thread to tell, `leftover.json` made it yours (`why`).
- `LineFollows`: the brief's `Thread:` line names the crew thread jbus holds, as `crewthread.move` writes it after the record, or the next pass's `crewthread.repair` does when the pass died between the two.
- `ScratchGoes`: a thread put away, settled or archived, has its scratch cleared.
- `CarryOnsBounded`: jbus sends a thread at most two carry-ons.
- `ArchivesFinished`: jbus archives only a finished slug's thread, and only once its turn is over.

A home is told in one of three ways:

- `_stopped`: a turn that failed with no Result, after two carry-ons.
- `leftover.tell`: a Result that leaves something, or a turn that completed or hung with nothing written.
- The stall ladder of `jbus/children.py`: a home with a row out whose crew writes nothing is nudged.

The canary `Drop = "ladder"` takes the stall ladder out, and `ThreadEnds` breaks.
The canary `Drop = "repair"` takes the next pass's repair out, and `LineFollows` breaks: the brief names no crew for good.
The test runs each canary on a cfg with its own rule alone.
In its shortest story the crew asks you something and its request waits.
The ladder also carries a crew that jbus told once to open the pull request its Result owes, if that crew ends again with nothing new written.
`resume` sends that tell once for the thread, `finished` leaves a slug that owes out, and `leftover` counts an owing Result as nothing written while its thread is quiet.

### Draw the chart of the thread

```sh
S=../../skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    statechart from-spec ThreadLife.tla --title "What does jbus do with a thread, launch to archive?"
```

It writes `ThreadLife-statechart/`: `chart.mmd`, `stories.md` and `summary.json`, with labels from `ThreadLife.map.py`.
Its `tlc/` folder holds TLC's output, which is not committed.
The chart has two regions: who has the thread (launching, gated, out, its home's, put away), and where it stands.
No state breaks a rule, so it draws no `bug-N` chart.

### What the thread model leaves out

- The home's thread: the model takes it as there and quiet in the end.
  With no home thread, `_stopped` and `leftover` make the row a gate of yours, and the catch-all's home is started again by `children.keep_alive`.
  A home that keeps writing restarts its stall spell.
- A thread made by a lost launch that the lookup does not find: that is a gate of yours, and jbus holds no thread for it.
- A settled thread that a message wakes (a paused crew's carry-on is modeled only for a thread still out), a row removed from the queue, and the `MERGED` message to a crew whose Result leaves work for after the merge.
- The folds `ThreadLife.tla` names beside each variable: the turns T3 Code reports that act as another (preparing, idle, interrupted, cancelled, unknown), the Results that read as a leftover (malformed, not done, blocked), and `leftover.json`'s `busy`, which the pass rewrites and no rule reads.
- Reviewers, and failover to another instance.
  A scout's launch record is the crew's record with fewer fields (`rec`).

## Main's red, as a TLA+ spec

`MainRed.tla` models what jbus does when main goes red, as the code of main 21112eba8 does it.
Main's push run fails and jbus reruns it once (`watch._check`).
If the rerun fails too, `mainmoved.tell` writes the red tip to `main.json`, and `watch.retro` hands main's tip to `culprits.judge`.
`judge` reverts the tip's one clear culprit (`jbus.reverts`) or files main's fix row (`watch._file`).
A later merge turns main green: the revert, the fix, or a merge that happens to fix it.
After that, `reverts.close` closes a revert that is still open, and `watch._withdraw` takes out a fix row that never launched.
Main's macOS run judges each commit too (`reverts.macos`), earlier in the same pass.
It reverts its own one clear culprit, or leans on the revert jbus opened at the same commits.
Each revert keeps the checks that hold it, its `holders` in `reverts.json`, and `close` closes it only once each of them passed at its red or later.
Each condition of a step names the file of the code that checks it and quotes that code in backticks, with no line number.
`features/jbus/tests/test_main_red_spec.py` finds each quote once in its file and checks that every condition is cited.
It also checks that the spec states each property `features/jbus/tests/main_red_model.py` walks over the real `tell`, and it runs TLC on both configs.

### The rules of main's red

- `NeverRevertedTwice`: jbus never opens a second revert of a commit.
  On 2026-11-09 main's check passed at the red commit itself while the Mac was still red there.
  `close` closed revert #1426 and then dropped its record, and the Mac, still red at that commit, opened #1427.
  Now the Mac leans on the revert and holds it open, and the record goes only once every check jbus judges main by passed at or above its red.
  The canary, `Fault = "opener-only"`, is the code before holders, where a revert is held by the check that opened it alone, and on `MainRed.chart.cfg` `NeverRevertedTwice` breaks.
- `OneRevertOpen`: main's check waits on at most one of jbus's open reverts.
  The Mac may wait on two, as on a revert it leaned on while its run under its red was pending, but a Mac red holds no pull request.
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

It exits 0: every rule holds over 140,012 distinct states (MaxTips 4), in a few seconds.
`MainRed.cfg` leaves the Mac out (`Mac = FALSE`): with it, four commits take TLC far too long.
`MainRed.chart.cfg` has the Mac on up to three commits, where every rule holds over 112,491 distinct states.
The test runs TLC on both configs, and on each rule of `BREAKS` alone, which is empty while the code breaks no rule, and the canary on `MainRed.chart.cfg`.

### Draw the chart of main's red

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
D=$HOME/.cache/jstack/tlc-tmp && mkdir -p "$D"
W=$(TMPDIR=$D mktemp -d) && cp features/jbus/spec/MainRed.* "$W"
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    statechart from-spec MainRed.tla --config MainRed.chart.cfg \
    --title "Main went red: what fixes it?" --out out)
```

Run it from the repo root.
Then copy the files of `$W/out` into `MainRed-statechart/`, all except `tlc/`.
`MainRed.chart.cfg` has the same rules on up to three commits, with the Mac (112,491 states), and it draws 42 chart states and 265 steps.
TLC runs once for each rule, so drawing it takes about two minutes.
The four commits of `MainRed.cfg` draw too many states and steps for Mermaid to render as a PNG.
No state breaks a rule, so it draws no `bug-N` chart.

### What the main-red model leaves out

- A cancelled, batched or job-less run (`watch.BATCHED`, `NO_JOB`, `cancelled`, `refused`): none of them is red.
- Logs `tell` cannot read, a project's first pass, a culprit's row removed from the queue, and a GitHub that does not say what main a culprit's check passed over, which waits as `UNREAD` until `READ_WAIT`.
  TLC's `skew` files the row at once.
- Whether a culprit's slug is over (`over`) before `close` drops its revert's record: the model drops it once every check passed above its red.
- `main-reds.jsonl` keeps only the red tip of each pass, where `tell` writes a line for each failed commit it walks.
- The browser run, and the fix row's crew ending with no pull request.
- Of the Mac (`reverts.macos`): its rerun, folded into its run; a Mac red at a revert, a fix or an outside push, which only files its row; the `macos-red-` rows; and a Mac culprit that `tested`, `covered` or `flaky` keeps from a revert.
  The Mac's one clear culprit is always reverted.
- Time: TLC chooses on each pass whether the red tip is older than `READ_WAIT` (`late`).

## The green move, as a TLA+ spec

`GreenMove.tla` follows one green copy (`jbus/green.py`) as passes move it to main's green tip, with a pass that can die between any two steps.
A move grows the new tip's tree, writes the step it owes to `green.json` (`move`, `owes: install`), points the link, installs the tool again, writes `owes: relink`, removes the trees no command runs, and puts the harness layouts again (`jinstall.green.relink`), and only a relink that is taken drops `move`.
Each pass resumes an owed step (`_resume`) before `_advance` reads main.json.
An install uv refuses, which may have removed the tool first, sends the move back: it owes the install of the tree it came from, with the reload systemd was owed before it, points the link back, removes the new tree, and installs the tool and relinks from the tree it went back to.
An install back that uv refuses too stays owed, and a newer green tip still starts a move that takes it over (`Advance`), so a tree uv never installs again does not hold the copy.
A tip that does not import is refused (`Refuse`), and no move starts to it; at idle, the pass puts the units a move took on to work and stamps `green.json`'s `live` (`Live`).
Each step's comment quotes the code it stands for, and `features/jbus/tests/test_spec_quotes.py` finds each quote once in today's code.

### Check the rules of the green move

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -deadlock -config GreenMove.cfg GreenMove.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
`-deadlock` is there because a copy at main's last tip has no step left to take.
Today's code holds every rule, over 11614 distinct states with MaxTip 3 and tip 2 one that does not import (`Broken = {2}`):

- `ToolRunsCopy`: once no pass is in a move and none is owed, the tool runs the tree the link names, so a unit never starts on a tool the copy no longer holds.
- `ToolTreeThere`: the tree the tool runs, where uv left one, is on disk.
- `LayoutsFollow`: once no pass is in a move and none is owed, the layouts were put from the tree the link names, also after a move whose install failed went back.
- `NoReloadForRemoved`: `green.json` owes systemd no reload for a tip whose move went back, so none runs for a tip that never became the copy.
- `CopyImports`: the link never names a tip that does not import, since `_advance` imports the tip first and refuses it.
- `StampTrue`: `live` names no tip whose units the manager did not take, so the stamp is true or not there.
- `CopyOwned`: the link names a tree on disk, whose `jstack-checkout` marker `owner` reads.

The canary, `Fault = "no-owed"`, keeps no step in `green.json`, as the code did before st-green-step.
`ToolRunsCopy` and `LayoutsFollow` each break in five states: main goes green, the move points the link, and the pass dies, the journal's 203/EXEC on `~/.local/bin/jbus`.
The second canary, `Fault = "no-back"`, goes back as the code did before st-green-back: it owes a relink and no install of the tree it went back to, and keeps the reload it wrote for the tip it removed.
`ToolRunsCopy` breaks when the failed install removed the tool, and `NoReloadForRemoved` breaks once the move goes back.
The canary `Fault = "no-import"` moves to a tip that does not import, and `CopyImports` breaks.
The canary `Fault = "stamp-refused"` stamps `live` over units the manager refused, and `StampTrue` breaks.
`CopyOwned` has no canary: in the model the link always names a tree that is there, and a tree a hand removed takes the fallback.
`features/jbus/tests/test_green_move_spec.py` runs TLC on the config and on each canary for the rules it breaks.

### What the green-move model leaves out

- uv's install and the write of `owes: relink` after it are one step: a pass that dies between them installs again, which is the same install, and the model does not let that second install fail.
- Which units a move puts to work: `took` is the tip whose units the manager took, all or none, and the transient units are left out.
- Of the reload a move owes systemd (`reload`, `at`), only `at` and whether systemd takes it.
- A tree a move went to that is gone on resume, which only a hand can remove: `_resume` goes back (`_back`) as a failed install does.

## Act once, as a TLA+ spec

`TellOnce.tla` follows jbus's act-once steps at main aa5469d97 (2026-11-11): a pass sends a message, posts a body, runs a check again, parks a question, holds a row, appends a line or archives threads once, and keeps the mark that it did in a file of its own, in a step of its own.
A pass can die between any two writes.
Each of the 21 carriers of the st-state-ledger's machine TellOnce is one variable, with the code that writes it quoted beside it.
One behavior follows one act of `Carriers`, since the acts write different files and do not wait on each other, so the states of the 13 acts add up and do not multiply.
The shared shape is three tables: `Code(c)`, the order in which act c's pass writes; `Guard(c)`, the marks it reads at its start; and `Absorbs(c)`, whether its receiver takes a repeat under a key it took as the same act (T3 Code's `clientRequestId`, a question's key, GitHub's state).
The clock's ladder (count, act once, count, log a stall for the home) and owed.json's second writer (failover's carry-on, then `owed.taken`) have actions of their own.
Each quote names its file and no line, and `features/jbus/tests/test_tell_once_spec.py` finds the one place each stands.

### Check the rules of act once

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -continue -config TellOnce.cfg TellOnce.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
The rules:

- `NoTellTwice`: the receiver takes each act once, a repeat after a pass that died being one it takes as the same, and no pass does an act again once its guard read the act's mark.
- `NoTellLost`: between passes, an act still owed whose mark is written was taken, and the stall the clock's `home` says went is in the log.

Today's code breaks them on seven acts, over 1676 distinct states, and `TellOnce.cfg`'s comment keeps each trace: stall.twice's page and the clock's stall are lost, and failover's ask, the second target's body, a word, the account question and a skill's notice can go twice.
The other six (held, items, expedite, cancelled, closed, revert) hold both.
Without `-continue` TLC stops at the first, stall.twice's, at depth 5.
The canary `Fault = "mark-first"` writes the marks before the act and breaks `NoTellLost` on every act; `Fault = "no-mark"` reads no mark and breaks `NoTellTwice` on every act.
In today's code the half of `NoTellTwice` that says no act runs after its mark was read holds by the guard's shape; the receiver's count is the half that checks the code.

### Draw the act-once chart

```sh
S=features/skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "../../../$S" \
    statechart from-spec TellOnce.tla --title "Does jbus tell anyone twice, or drop a tell, when a pass dies?"
```

It writes `TellOnce-statechart/`, labelled by `TellOnce.map.py`, with one `bug-N` chart for each act that breaks a rule.

### What the act-once model leaves out

- Time and liveness: the rules are safety rules, so an act a guard keeps from running forever passes them (such as expedite's second tell once its key is marked and expedite.json is not).
- A clock wait whose kind goes back to one it had: its old key is still in sent.json, and the model starts every new wait under a new key.
- `Box.send` writes a finding's key before its line, which loses the line when a pass dies between them: the model has it for the clock's stall and stall.twice's page, and the other keyed findings (an ask resent, failover's, expedite's) share it.
- The event `item.write` records after its line, cancelled.py's false "not run again" after a rerun whose finding was lost, and the account question the second park leaves open: each is a fault of its own, not a tell twice or lost.
- The second target's timeout after the target took the body is a pass that dies after the act.

## Main's fix and revert, filed step by step, as a TLA+ spec

`MainFix.tla` takes the steps MainRed.tla folds into one, `reverts` and `fixes`, and gives each write its own step, as the code of main aa5469d97 (2026-11-11) makes them.
A pass can die between any two writes, and the disk and GitHub keep what was written.
It has one variable for each carrier of the st-state-ledger's MainFix rows, and each variable's comment quotes the code that writes it:

- B-023, the revert's brief `tasks/revert-<n>-<branch>.md` (`revertBrief`): GitHub opens the revert, then jbus writes its brief, its record in `reverts.json` and its line in `events.jsonl` (`jbus/reverts.py` `revert`).
- B-028, main's fix brief `tasks/main-red-<sha>.md` and its queue row (`fix`): the brief, then `queue.add` (`jbus/watch.py` `_file`).
- B-029, the Mac's fix row `macos-red-<sha>` (`macFix`): the same (`jbus/reverts.py` `_mac_file`).
- B-030, B-031 and B-032, the runs each nightly has seen, `browser-runs.json`, `macos-nightly-runs.json` and `scheduled-<stem>-runs.json` (`browserSeen`, `macosSeen`, `scheduledSeen`): the day's row, then the run kept as seen (`jbus/watch.py` `_nightly_red`).

A pass judges the Mac, then main, then reads each nightly, as steps 9, 12 and 40 run.
`World` names the faults of the world the model lets in past a pass that dies: GitHub refuses or does not answer (`"refuses"`), a hand turns a red green (`"hand"`), or a nightly's red run is more than three days old when a pass first reads it (`"late"`).
`Watched` names the nightlies the model runs.
Each condition the code checks quotes it.
`features/jbus/tests/test_main_fix_spec.py` finds each backticked quote of the spec once, in the file named last before it, and checks that each carrier has its variable.
The conditions with no cite are the world's steps and the pass's own place in its steps, which no code checks.

### Check the rules of main's fix

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config MainFix.cfg MainFix.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
`MainFix.cfg` is today's code with a pass that dies and no other fault, watching all three nightlies, and every rule holds over 1244712 distinct states:

- `FiledWhole`: after any crash, a red tip has a fix row and its brief, or neither, by the next pass: main's red tip, its Mac's, and each red nightly run.
- `RevertKnown`: an open revert on GitHub has its `reverts.json` record by the next pass, since jmerge merges and `reverts.close` closes only a revert on record.
- `RefinesMainRed`: each step is MainRed's `reverts` or `fixes` step, or leaves both as they are, where MainRed's `reverts` is the record and its `fixes` are the red tips whose main fix row the queue holds.
  It also holds with `World = {"refuses"}`, over 12557140 distinct states, which takes about a minute.

The canary, `Fault = "no-reopen-check"`, is `opened` not asking GitHub for the revert's branch, and `RevertKnown` breaks: a pass opens the revert and dies, and the next pass files a fix row in its place.
The comment in `MainFix.cfg` keeps the breaks TLC finds past that config, each with its trace, and the test's `FINDINGS` checks that each still breaks:

- `RevertSaid` (jbus says each revert it opened) breaks on a crash alone: a pass that dies between `reverts.json` and `events.jsonl` leaves the revert with no line, and every later pass reads it as its own.
- `RevertKnown` breaks with `"hand"`: a revert opened by a pass that died, then a green, is never recorded, so it stays open.
  With `"refuses"` it is recorded a pass late.
- `FiledWhole` breaks with `"refuses"`, where a brief written while GitHub did not answer stays when the next pass reverts instead, and with `"late"`, where a nightly's brief stays with no row once its run is stale.

### Draw the chart of main's fix

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
D=$HOME/.cache/jstack/tlc-tmp && mkdir -p "$D"
W=$(TMPDIR=$D mktemp -d) && cp features/jbus/spec/MainFix.* "$W"
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    statechart from-spec MainFix.tla --config MainFix.chart.cfg --expect-broken FiledWhole,RevertKnown,RevertSaid \
    --title "Main went red: what has jbus filed when a pass dies?" --out out)
```

Run it from the repo root, then copy the files of `$W/out` into `MainFix-statechart/`, all except `tlc/`.
`MainFix.chart.cfg` draws main and its Mac with `World = {"refuses", "hand"}` and no nightly, 11175 distinct states, in about a minute.
Even one nightly in that world is 260448 states, too many to draw, so the nightlies are checked by `MainFix.cfg` and not drawn.
Each of its three broken rules draws a `bug-N` chart, and `stories.md` tells each one.

### What the main-fix model leaves out

- A second red, its culprit and its revert, and the revert's holders: MainRed.tla has them.
- `reverts.close` and `_withdraw`, which take a revert or a fix row back once main is green, and the revert MainRed calls stuck.
- `_add_tip`: a red tip that fails as an open fix row does goes into that row's brief, and files no row of its own.
- A queue that refuses a brief (`Refused`): the brief stays with no row, and the home is told of it as a condition.
- A project's first pass, a run whose jobs or logs GitHub has not given yet (`NIGHTLY_GRACE`), a red run whose failures are both shots and more, and a row removed from the queue.
- What `_nightly_red` keeps of a run that files nothing, which it writes at the loop's end: the model writes it at once, since the next pass reads the same runs and keeps the same.

## The one list, as a TLA+ spec

`OneList.tla` models what waits on the user and the marks of what a home has read, at main aa5469d97 (2026-11-11): a gate in gates.md and in questions.json, gates-moved.md, the kinds of waiting-on-user.json, the streaks of streaks.json under streaks.lock, the disk's reading, the sign-in line, budget-hold.json, read-seen, and merge-seen with merge.log.
Each ledger row of the machine OneList (st-state-ledger) is a variable whose comment names the row and quotes the code that writes it.
The parts share only the project's passes and the lock, so Init picks the scene a behavior moves (alerts, gates or marks), and the others stay at their start.
`World` is the set of acts outside the code a run lets happen: a project that closes, a hand that cuts merge.log, and a gate asked by the home.
`OneList.map.py` labels the states and maps each kind of the list to the HomeTree `msg` it refines.

### Check the rules of the one list

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -workers 1 -config OneList.cfg OneList.tla
```

Run it in a copy of this folder.
The rules:

- `ListIsTrue`: an item is listed exactly while its cause holds, once the cause stays, so a cause that flips for ever asks nothing of the list.
  The cause is the model's word: the code lists a closed project's alert for the infra home, and the model says it has no cause.
- `AnsweredLeaves`: once the user's answer, or the default by silence, settles a gate, gates.md gives the list no open gate of it and no question of it stays open.
- `ReadOnce`: the merging block shows each merge line once, and merge-seen counts no line as read that it did not show, also after merge.log is cut.

Today's code, in today's world, breaks `ReadOnce` at 1083 distinct states: a cut of merge.log leaves merge-seen counting a line no block showed.
Each act alone breaks its rule: a closed project leaves its jmerge alert open forever (`ListIsTrue`, as `jmerge case-control` on disk), a cut breaks `ReadOnce`, and a gate asked by the home is asked again by the handoff under the catch-all's key, so answering one of its two questions leaves the other open (`AnsweredLeaves`, `ListIsTrue`).
With no act, every rule holds.
`MarkBy = "line"`, a merge-seen that names the last line it read, which no code writes, holds `ReadOnce` also where merge.log is cut.
The canary `Fault = "stale-streak"`, a pass that leaves the stall alert from before, breaks `ListIsTrue` with no act; `Fault = "mark-count"`, merge-seen as the code's count over that line mark, breaks `ReadOnce` where merge.log is cut.
`features/jbus/tests/test_one_list_spec.py` finds each quote once and runs each of these.

### Draw the chart of a gate

```sh
S=features/skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "../../../$S" \
    statechart from-spec OneList.tla --config OneList.chart.cfg --expect-broken AnsweredLeaves,ListIsTrue \
    --title "Does a gate reach my list, and leave it once I answer?" --png
```

`OneList.chart.cfg` draws the gates scene alone: the other scenes have too many states to draw.
Its rules are about whole behaviors, which the chart does not draw: TLC's traces are in `OneList-statechart/tlc/`, which is not committed.

### What the one-list model leaves out

- The nine kinds of waiting-on-user.json other than `gate` are one item, each rebuilt by a pass from its source; their own lives are RowLife's and the other models'.
- jmerge's streak stands for every key of a project, and the stall key for the keys nothing raises any more; the pass's `pass` and `stale` streaks, `home thread`, `blocking`, `pool-held`, `t3-tool` and `once` keys are not modelled.
- Time: the threshold's span (`LASTING`), a `once` alert's end, the budget hold's ten minutes before `jbus needs` lists it, and the sign-in's week.
- A sign-in whose token file is gone: `remind` returns with the alert as it was.
- `jbus home status` shows the merge lines past the mark without moving it, and is not counted as shown.
- Two Results whose headings read the same: read-seen keys a heading by its text.
  No rule checks read-seen: the model keeps its first mark and the home's marks.
