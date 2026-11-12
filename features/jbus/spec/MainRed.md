# Main's red, as a TLA+ spec

`MainRed.tla` models what jbus does when main goes red, as the code does it, last read against it at 228c1436c (2026-11-11).
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

## The rules of main's red

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
  - `EachRedJudgedOnce` (S4): `main-reds.jsonl`'s verdict lines name no tip twice and name the red tip, and its closing lines (`mainmoved.close`) close no spell twice.

## Check the rules of main's red

The command below is the brief's check.
Run it in a copy of the folder, since TLC writes `states/` where it runs:

```sh
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config MainRed.cfg MainRed.tla
```

It exits 0: every rule holds over 147,834 distinct states (MaxTips 4), in a few seconds.
`MainRed.cfg` leaves the Mac out (`Mac = FALSE`): with it, four commits take TLC far too long.
`MainRed.chart.cfg` has the Mac on up to three commits, where every rule holds over 116,957 distinct states.
The test runs TLC on both configs, and on each rule of `BREAKS` alone, which is empty while the code breaks no rule, and the canary on `MainRed.chart.cfg`.

## Draw the chart of main's red

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
D=$HOME/.cache/jstack/tlc-tmp && mkdir -p "$D"
W=$(TMPDIR=$D mktemp -d) && cp features/jbus/spec/MainRed.* "$W"
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec MainRed.tla --config MainRed.chart.cfg --also-config MainRed.cfg \
    --title "Main went red: what fixes it?" --out out)
```

Run it from the repo root.
Then copy the files of `$W/out` into `MainRed-statechart/`, all except `tlc/`.
`MainRed.chart.cfg` has the same rules on up to three commits, with the Mac (116,957 states), and it draws 42 chart states and 265 steps.
TLC runs once for each rule, so drawing it takes about two minutes.
The four commits of `MainRed.cfg` draw too many states and steps for Mermaid to render as a PNG, so `--also-config MainRed.cfg` runs it once more for the tables alone.
`states.tsv` and `arrows.tsv` list all 42 chart states and all 377 arrows between them, each with its action and its count of model steps in each run.
`MainRed.cfg` (147,834 states) reaches no state the chart's cfg misses, and 8 arrows that it does, which the tables list and the tab names.
No state breaks a rule, so it draws no `bug-N` chart.

## What the main-red model leaves out

- A cancelled, batched or job-less run (`watch.BATCHED`, `NO_JOB`, `cancelled`, `refused`): none of them is red.
- Logs `tell` cannot read, a project's first pass, a culprit's row removed from the queue, and a GitHub that does not say what main a culprit's check passed over, which waits as `UNREAD` until `READ_WAIT`.
  TLC's `skew` files the row at once.
- Whether a culprit's slug is over (`over`) before `close` drops its revert's record: the model drops it once every check passed above its red.
- `main-reds.jsonl` keeps only the red tip of each pass, where `tell` writes a line for each failed commit it walks.
  A pass is one step, so its closing line and `main.json` are written together: `close`'s guard against a second closing line, for a pass that dies between the two, is never needed here.
- The browser run, and the fix row's crew ending with no pull request.
- Of the Mac (`reverts.macos`): its rerun, folded into its run; a commit of its range still pending, which is `UNREAD` and later `OVERLAP`, both quiet here since no Mac row is kept; a Mac red at a revert, a fix or an outside push, which only files its row; the `macos-red-` rows; and a Mac culprit that `tested`, `covered` or `flaky` keeps from a revert.
  The Mac's one clear culprit is always reverted.
- Time: TLC chooses on each pass whether the red tip is older than `READ_WAIT` (`late`).
