# Main's fix and revert, filed step by step, as a TLA+ spec

`MainFix.tla` takes the steps MainRed.tla folds into one, `reverts` and `fixes`, and gives each write its own step, as the code makes them, last read against it at 43b12ce51 (2026-11-12), with st-main-fix-crash-gaps (#1728) in it.
A pass can die between any two writes, and the disk and GitHub keep what was written.
Each fix below makes the last write of a step its commit point: every write before it can be done again by the next pass, and a write-ahead name marks the one call to GitHub that cannot.
It has one variable for each carrier of the st-state-ledger's MainFix rows, and each variable's comment quotes the code that writes it:

- B-023, the revert's brief `tasks/revert-<n>-<branch>.md` (`revertBrief`): jbus names the revert in `reverts-opening.json` (`opening`), GitHub opens it, then jbus writes its brief, its line in `events.jsonl` (`said`), its record in `reverts.json` (`record`), and drops its name (`jbus/reverts.py` `revert` and `_own`).
- B-028, main's fix row `main-red-<sha>` (`fix`): `queue.add`, then its brief's copy in `tasks/` (`jbus/watch.py` `_file` and `copy_brief`).
- B-029, the Mac's fix row `macos-red-<sha>` (`macFix`): the same (`jbus/reverts.py` `_mac_file`).
- B-030, B-031 and B-032, the runs each nightly has seen, `browser-runs.json`, `macos-nightly-runs.json` and `scheduled-<stem>-runs.json` (`browserSeen`, `macosSeen`, `scheduledSeen`): the day's row, then its brief's copy, then the run kept as seen (`jbus/watch.py` `_nightly_red`).

A pass runs `reverts.known` (tellers 36), then reads each nightly (tellers 40), then judges the Mac (after-expedite 9), then main (12), as `poll.first_half` runs its slots.
`reverts.known` asks GitHub for the branch `reverts-opening.json` names, among the pass's open pull requests or by `gh pr list`, and keeps a revert it finds open, whether main is red or green and whether compare answers.
It drops a name GitHub has no revert for once `READ_WAIT` has passed, and one whose revert is on record.
The shot tests of any nightly's red file the day's shots row (`drawn_apart`), the Mac's after a run that passed.
`World` names the faults of the world the model lets in past a pass that dies: GitHub refuses or does not answer (`"refuses"`), a hand turns a red green (`"hand"`), a nightly's red run is more than three days old when a pass first reads it (`"late"`), or a pass has no world (`"blind"`: no T3 Code token, T3 Code or GitHub silent, or the API budget under its floor), so it skips `reverts.known`, the nightlies and the Mac, which need one, and judges main alone.
`Watched` names the nightlies the model runs.
Each condition the code checks quotes it.
`features/jbus/tests/test_main_fix_spec.py` finds each backticked quote of the spec once, in the file named last before it, and checks that each carrier has its variable.
The conditions with no cite are the world's steps and the pass's own place in its steps, which no code checks.

## Check the rules of main's fix

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config MainFix.cfg MainFix.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
`MainFix.cfg` is the code with a pass that dies and no other fault, watching all three nightlies, and every rule holds over 329948 distinct states:

- `FiledWhole`: no brief ever stands with no row, between passes after one that ran every step: main's fix and its Mac's, at every tip, and each nightly's rows.
  A blind pass is not such a pass: it launches nothing, and the next pass with a world queues the row.
- `RevertKnown`: an open revert on GitHub has its `reverts.json` record by the next pass, since jmerge merges and `reverts.close` closes only a revert on record.
- `RevertSaid`: each revert on record has its line in `events.jsonl`.
- `RefinesMainRed`: each step is MainRed's `reverts` or `fixes` step, or leaves both as they are, where MainRed's `reverts` is the record and its `fixes` are the red tips whose main fix row the queue holds.

They hold too in each world TLC broke them in on the code of aa5469d97: `World = {"hand"}` (669004 distinct states), `{"refuses"}` (1339244) and `{"late"}` (1006483).
They hold with `World = {"blind"}` too, over 586960 distinct states.
Those counts are of `MainFix.cfg`'s `VIEW View`, which tells each variable apart only by what a later step or a rule can still read of it: a nightly run kept in its seen file is "passed" or seen, a pull request's run is as good as seen, a red run that aged unseen is late whatever its kind, the tip and `clear` stop counting once main and its Mac are green again, and so do `sight` between passes and `before` after a pass that died.
A pass also goes past a nightly's last run straight to its next step, since dying between the two writes nothing.
So the rules are checked as before, over a quarter to a tenth as many states, and each TLC test ends in well under a minute.
`test_main_fix_spec.py` runs each of those rules alone in its world, and each canary below.
Each canary is the code with one fix taken back, and TLC breaks the rule it keeps; the comment in `MainFix.cfg` keeps each trace:

- `Fault = "keep-first"`, the record before the line, breaks `RevertSaid`: a pass that dies between them leaves a revert every later pass reads as its own, with no line.
- `Fault = "no-known"`, no `reverts.known`, breaks `RevertKnown` with `"hand"`: a revert opened by a pass that died, then a green, is never recorded, so it stays open.
- `Fault = "brief-first"`, the brief before its row, breaks `FiledWhole` with `"refuses"`, where the next pass reverts instead, and with `"late"`, where the run is stale by the next pass.

`features/jbus/tests/test_main_fix_crashes.py` stops the real pass at each write those traces name and runs the next one.

## Draw the chart of main's fix

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
D=$HOME/.cache/jstack/tlc-tmp && mkdir -p "$D"
W=$(TMPDIR=$D mktemp -d) && cp features/jbus/spec/MainFix.* "$W"
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec MainFix.tla --config MainFix.chart.cfg --also-config MainFix.cfg \
    --title "Main went red: what has jbus filed when a pass dies?" --out out)
```

Run it from the repo root, then copy the files of `$W/out` into `MainFix-statechart/`, all except `tlc/`.
`MainFix.chart.cfg` draws main and its Mac with `World = {}` and no nightly, 329 distinct states.
With no broken rule the chart draws the shortest way to each state between passes, and the worlds `"refuses"` and `"hand"` give too many of them to read, so they and the nightlies are checked by `MainFix.cfg` and not drawn.
`--also-config MainFix.cfg` runs it once more for the tables alone: its 329,948 states add 910 states and 2,506 arrows to the chart cfg's, and `states.tsv` and `arrows.tsv` list all 975 states and 2,647 arrows between them, each with its action and its count of model steps in each run.

## What the main-fix model leaves out

- A second red, its culprit and its revert, and the revert's holders: MainRed.tla has them.
- `reverts.close` and `_withdraw`, which take a revert or a fix row back once main is green, and the revert MainRed calls stuck.
- `_add_tip`: a red tip that fails as an open fix row does goes into that row's brief, and files no row of its own.
- A queue that refuses a brief (`Refused`): its copy is written to `tasks/` with no row, and the home is told of it as a condition.
- A revert opened by hand on a branch jbus would name: `reverts.known` keeps only the one `reverts-opening.json` names.
- That `reverts.known` reads the pass's open pull requests, 100 at most, before it asks `gh pr list`: the model asks GitHub once.
- The retrospective line `_filed` sends once a fix row is queued: a pass that dies between the row and `run.find` sends none, and nothing reads that line back.
- A project's first pass, a run whose jobs or logs GitHub has not given yet (`NIGHTLY_GRACE`), a red run whose failures are both shots and more, and a row removed from the queue.
- What `_nightly_red` keeps of a run that files nothing, which it writes at the loop's end: the model writes it at once, since the next pass reads the same runs and keeps the same.
