---
name: verify-main-red
description: Check main's red: the walk of main.json's contract and MainRed.tla; use when changing mainmoved, mainjson, jbus.reverts, culprits, watch's red steps or Repo.again.
---

# verify-main-red

`main.json` in a jbus project's state is the one record of main's red tip.
`mainmoved.tell` (`features/jbus/src/jbus/mainmoved.py`) is its only writer, once a pass, and builds each record with `jmerge.mainjson.record`; `mainjson.of` (`features/jmerge/src/jmerge/mainjson.py`) reads it.
A red main holds no pull request, so the record stops no merge.
`jmerge.cli.Repo.again` reads it to ask GitHub for no merge of a red main into a red pull request, and `jbus.culprits` reads its `failed` to tell a flake from a culprit's own red (`jbus.reverts`).
A test runs the orders someone wrote down.
This check runs every order of merges, check answers, reruns and passes within its bounds, through the real `tell` and the real `mainjson.read`, and checks four properties after every pass:

- **S1, a known red is read as red.**
  When the newest tip whose check has settled (`green` or `failed`, `mainjson.SETTLED`) failed, `read` names a red tip.
  Broken, jmerge merges a red main into each red pull request, and each one goes red again.
- **S2, no stuck red.**
  When `read` names a tip, no tip that landed after it has a `green` check.
  Broken, a pull request red over the old red is never judged again after main was fixed.
- **S3, the red tip's own tests.**
  When the record keeps `failed` beside `broken`, those are the tests that failed at that tip.
  Broken, `jbus.reverts` judges a red tip by another tip's tests, so a revert is a wrong one or a culprit escapes.
- **S4, each red judged once.**
  `main-reds.jsonl` (`mainmoved.REDS`), the ledger of reds `tell` writes, has a line for the red tip the record names, with that tip's own tests, and no tip has two lines.
  Broken, a spell of main's red reads `unjudged` and counts as a change failure whatever caused it, or two lines give one red two causes.

The model is `features/jbus/tests/main_red_model.py`, standard library only (a `collections.deque` walk, states kept by a `json` key).
Its docstring says what each step is, the code line that backs it, what is stubbed and what is not covered.
`tell` reads no pull request and sends no message, so the model has neither.

## The record

Two checks share this record, and one sha confirms both: `main_red_model.py` walks the real `tell` and `mainjson.read`, and `features/jbus/spec/MainRed.tla` models the wider red, from the rerun through the revert or the fix row to the close.

Model: `features/jbus/spec/MainRed.tla`
Sync: `228c1436cc6fe94de479d333c7aab7b007460462`
Covers:
- `features/jbus/src/jbus/mainmoved.py`: `tell`, `main_check`, `failed_at`, `failed_steps`, `red_line`, `REDS`, `landed`, `close`, `closing_line`
- `features/jmerge/src/jmerge/mainjson.py`: `record`, `read`, `fix_of`, `FIX`
- `features/jbus/src/jbus/watch.py`: `_check`, `_rerun_failed`, `RERUN_WAIT`, `mac_check`, `retro`, `RedTip`, `_withdraw`, `_file`, `_same_red`, `_open_reds`, `FIX_GOES`
- `features/jbus/src/jbus/culprits.py`: `judge`, `kept_why`
- `features/jbus/src/jbus/reverts.py`: `culprit`, `Keep`, `tested`, `covered`, `revert`, `lean`, `holders`, `_keep`, `stuck`, `close`, `cleared`, `over`, `macos`, `_mac_red`, `MAC_WALK`, `READ_WAIT`
- `features/jmerge/src/jmerge/reverts.py`: `read`
- `features/jmerge/src/jmerge/cli.py`: `Repo.again`
- `features/jbus/src/jbus/poll.py`: `steps`, `first_half`, `second_half`

At the sync commit `MainRed.tla` was read against these: `culprit`'s order of checks, then `tested` and `covered`; `OPENED` taking the newest revert and `stuck`; `lean` adding to the newest revert only; `close` skipping a revert not yet open, closing once all holders passed even while main is red, and dropping the record only with main green and every check in `greens`; the pass order 9, 10, 11, 12, 13; `retro` handing over the tip only at `main.red`; `_rerun_failed` asking for a rerun only at the tip; `_withdraw` and `_file`.
The walk of `main_red_model.py` was rerun there and passes as below.
`features/repo-guards/tests/test_model_sync.py` fails when a file or name above is gone.
Move `Sync:` forward only after you read every change to these files since it against both models, as `/maintain-formal-verification-skill` says, and never because a check passes.

### MainRed.tla

The rules beyond S1 to S4, each with its harm:

- **`NeverRevertedTwice`:** jbus never opens a second revert of a commit.
  Broken, as on 2026-11-09 (#1426 closed, then #1427 opened by the Mac at the same commit), one culprit is reverted twice.
- **`OneRevertOpen`:** main's check waits on at most one of jbus's open reverts.
- **`RedEndsOnlyByAMerge`:** a red whose code is broken ends only at a green commit a later merge made.
- `KnownRedReadAsRed`, `NoStuckRed`, `RedTipsOwnTests` and `EachRedJudgedOnce` are S1 to S4 below, as the state a pass leaves; `test_main_red_spec.py` checks the spec states each one the walk checks.

```sh
uv run pytest features/jbus/tests/test_main_red_spec.py -q
```

It prints `6 passed` in seconds, and skips where no Java runs TLC; TLC's verdict may come from the statechart tools' cache (`tools.kept`), so to see TLC run, use the bare command in `features/jbus/spec/README.md`, "Check the rules of main's red", in a copy of the folder.

- **Bounds:** `MainRed.cfg` is `MaxTips = 4` with no Mac (`Mac = FALSE`), 140,012 distinct states; `MainRed.chart.cfg` is `MaxTips = 3` with the Mac, 112,491 states.
- **The canary:** `Fault = "opener-only"` on `MainRed.chart.cfg` is a revert held by the check that opened it alone, and `NeverRevertedTwice` breaks.
  `BREAKS`, the rules today's code breaks, is empty.
- **Assumptions:** two rows and an outside push; no cancelled, batched or job-less run; logs always readable; skew or no answer files the row at once; whether a culprit's slug is `over` is folded; `main-reds.jsonl` keeps only each pass's red tip; no browser run; the Mac's rerun is folded into its run, and its `tested`, `covered` and `flaky` checks are left out.
  The rest is in the README's "What the main-red model leaves out".
- **A trace:** each condition of a step quotes its code; open each quote, and a step the code cannot take is a modeling error.
  When every step is backed, tell it as the merges, runs, reruns and passes in the code's words.

### Drift at the sync commit

`/maintain-formal-verification-skill` fixes it; the walk of `main_red_model.py` holds.

- **`MainRed.tla` has no closing lines:** since 46210ec44 and db90d454e, `mainmoved.tell` appends a closing line (`close`, `closing_line`) with its `cause` to `main-reds.jsonl` when main goes green, keyed by the spell's first red tip.
  The model's `reds` has no such line and the README's "leaves out" does not name it, so `EachRedJudgedOnce` ("names no tip twice") is false of the real file, where the first tip has its red line and its closing line.
  `main_red_model.py`'s S4 counts only the lines that carry a verdict and checks for at most one closing line a spell, so the TLA+ S4 is weaker than the S4 it claims to match.
- **The base commit in the spec's prose is stale:** the README and the spec say "main 21112eba8", and the spec already has holders and `lean` from f82908cda (#1689), which came later.
- A pending Mac commit inside the Mac's red range is `UNREAD` (quiet) in the code and "file" in the model; neither reverts, and the model keeps no Mac row.

## Does a change touch it

Rerun it when the diff touches any of these:

- `features/jbus/src/jbus/mainmoved.py` (`tell`, `main_check`, `failed_at`, `failed_steps`, `red_line`, `REDS`, `landed`, the `STEPS` slot);
- `features/jmerge/src/jmerge/mainjson.py` (`Record`, `record`, `SETTLED`, `of`, `read`, `typed`, `FIX`, `failures`);
- `features/jmerge/src/jmerge/cli.py` (`Repo.again`, which reads `main_state`) and `features/jmerge/src/jmerge/rows.py` (`main`);
- `features/jbus/src/jbus/culprits.py` (`kept_why`) where it reads `failed` for `jbus.reverts`;
- `features/jbus/src/jbus/poll.py` where a pass runs `tell` in the `after-expedite` slot, or the pass lock (`store.locked`, whose `fcntl.flock` is in `features/jsettings/src/jsettings/store.py`), and `features/jbus/src/jbus/merge.py`, where `merge.start` starts a pass's run of `jmerge` off the pass and `merge.keep` runs it, so a merge it makes lands at any point between and within passes;
- `features/jbus/src/jbus/watch.py` `_check` and `_judged`, the answers a tip's check can have;
- `write_json` in `features/jsettings/src/jsettings/store.py`: the model takes a read to see a whole record, which `os.replace` gives;
- the "Main is not red" rule in `features/jmerge/docs/jmerge.md`;
- for `MainRed.tla`, every file of the record above: `jbus.reverts` (a culprit, its revert, its holders, `lean`, `close`, `macos`), `culprits.judge`, `watch._check`, `retro`, `_file` and `_withdraw`, and `jmerge.reverts.read`; a change to how a revert or a fix row is filed write by write is `verify-main-fix`'s too;
- a move of any of these modules: the model imports them and stubs by module attribute, so a move changes its imports and its stubs, and the check is rerun on the moved code (unit 6 moved `jbus.mainstate` to `jmerge.mainjson` with the same counts).

`scripts/select_tests.py` selects `features/jbus/tests/test_main_red_model.py` for a change to `mainmoved.py`, `mainjson.py` or `features/jmerge/docs/jmerge.md`, through what the model imports and the path it names, so `make check-fast` runs it.
Run it by hand anyway when you change the contract on purpose: what it prints is the point.

## Run it

```sh
uv run pytest features/jbus/tests/test_main_red_model.py -q
```

It takes a few seconds (6,183 states in the widest world).
On the code as it is today it prints `9 passed`.
To print every world:

```sh
uv run python features/jbus/tests/main_red_model.py
```

It prints both worlds, how many states each walks, and for each property `holds` or the number of states that break it with a trace.
On the code as it is today, every order walks 6,183 states and one tip at a time walks 1,154, and S1 to S4 hold in both.

The model has two worlds:

- **every order** (`Options()`): any merge, check answer, rerun or pass may come at any point, so a tip may land before a pass looked at the one under it.
- **one tip at a time** (`Options(one_at_a_time=True)`): a tip lands only once the newest tip's check has settled and a pass has run since.

The tests and the world each walks:

| Test | World | Today |
|---|---|---|
| `test_the_walk_reaches_every_event_the_model_has` | every order | passes: each event kind was reached |
| `test_s1_a_failed_tip_seen_by_a_pass_is_read_as_red` | one tip at a time | passes |
| `test_s1_a_failed_tip_is_read_as_red_whatever_lands_after_it` | every order | passes |
| `test_s2_a_green_tip_seen_by_a_pass_ends_the_red` | one tip at a time | passes |
| `test_s2_a_green_tip_ends_the_red_in_every_order` | every order | passes |
| `test_s3_the_tests_kept_are_the_red_tip_s_own_one_at_a_time` | one tip at a time | passes |
| `test_s3_the_tests_kept_are_the_red_tip_s_own_in_every_order` | every order | passes |
| `test_s4_each_red_tip_has_one_line_in_the_ledger_one_at_a_time` | one tip at a time | passes |
| `test_s4_each_red_tip_has_one_line_in_the_ledger_in_every_order` | every order | passes |

Each finding's world is cut from a world that passes, so a break there points at that finding's cause.
S1 holds one tip at a time, so S1 breaking over every order needs a tip no pass saw (F2).
S2 holds one tip at a time, so S2 breaking over every order needs a tip no pass saw (F3).
`tell` sends no message since it stopped telling crews, so the model has no T3 Code and no lost send, and F1 has no path left.
A failure in any test is a new break.

## The findings

All three are fixed: `tell` looks at every tip since its last pass (`landed`), and a pass takes a `fixed` it finds in the record as the end of the red.
F1's cause, a send T3 Code lost, is gone with the message: `tell` writes no `fixed` now, and reads one only in a record written before.
The line numbers below are of the code before the fix (`fa810ec`).

- **F1 (S2), retired.**
  A green tip whose message T3 Code lost wrote only `fixed`, and the next pass, at a pending tip, wrote the old `broken` back.
- **F2 (S1).**
  A tip that fails and is followed by another before a pass looks at it was never kept as `broken`: `broken` came from the newest tip's own check.
  With the newest pending, `read` named no red tip.
- **F3 (S2).**
  The mirror of F2: a green tip followed by another before a pass looks at it was never seen, so `broken` stayed while the newest tip was pending.
  F2 and F3 had one cause, `tell` reading the newest tip only.

## Read a trace

A trace is the shortest order of events to the first state that breaks the property, numbered from `start`.
Tips are `M0` (green, there from the start) to `M3`; a record is printed with its commits as those names and without `at`.
For example, with the scratch break `green, waiting, unrun = tip, [], ""` for `green, broken, waiting, unrun = tip, "", [], ""` in `tell`'s `check == "green"` branch, every order prints:

```
S2 breaks in 56 of 3831 states (Options(one_at_a_time=False)), against "Main is not red" in features/jmerge/docs/jmerge.md
  1. start: M0 is green, no main.json
  2. M1 lands: a merge
  3. M1's check settles: failed
  4. pass: tell writes main.json {"broken": "M1", "check": "failed", "failed": ["features/m/tests/test_m.py::test_M1"], "main": "M1"}; mainjson reads red=M1 green=-
  5. M1's check is rerun and passes
  6. M2 lands: a merge
  7. pass: tell writes main.json {"broken": "M1", "check": "pending", "failed": ["features/m/tests/test_m.py::test_M1"], "green": "M1", "main": "M2", "pending": ["M2"]}; mainjson reads red=M1 green=M1
```

The record after a `pass` is what the real `tell` wrote; `red` and `green` are what the real `mainjson.read` gives.
One tip at a time, the same break holds, since a pass at a green newest tip clears `broken` before the loop.

## A real bug or a modeling error

Each step of a trace must be backed by code.
Check every step against this table; a step no line backs is a modeling error, and the model is what gets fixed:

| Step | Backed by |
|---|---|
| `pass` | one `tell` under the pass lock, `features/jbus/src/jbus/poll.py`, in the `after-expedite` slot, `features/jbus/src/jbus/mainmoved.py` |
| `Mn lands: a merge` | a merge by `jmerge`: by hand, by `--accept`, by the merge tick, or by a pass's run, which `merge.start` starts off the pass and `merge.keep` runs. No read of the record stops one, and none waits for a pass, so a merge lands at any point between and within passes, `features/jbus/src/jbus/merge.py` |
| `Mn's check settles: <answer>` | an answer `watch._check` gives, `features/jbus/src/jbus/watch.py`; `pending` is a check not ended |
| `Mn's check is rerun and passes` | a rerun of a failed check on the same tip, which `main_check` asks again about (`again=tip in (main, stands)`), `features/jbus/src/jbus/mainmoved.py` |

The stubs are the other place a model can lie: `mainmoved.main_check`, `mainmoved.failed_at`, `mainmoved.failed_steps` and `mainmoved.account` (`stubbed()` in the model), and `FakePass.run`'s answer to GitHub's list of main's commits, which `landed` asks for.
If one of them is no longer what `tell` calls, the step it stands for is not the code's.
`mock.patch.object` fails on an attribute that is gone, but a name `tell` imports with `from ... import` is not patched by a module attribute: then the real function runs and asks GitHub.

When every step is backed, the trace is a real bug: report it with the trace, in the code's words, and leave the property as it is ("Findings stay findings").

## Change the model when the contract changes on purpose

- **A fix lands for a finding.**
  A finding the walk finds is a strict `xfail` until it is fixed, and its test fails as `XPASS(strict)` once the fix lands: remove that `xfail` mark, and run again to see it pass.
- **`main.json` gets a new key, or `mainjson.of` reads it differently.**
  The model writes and reads the real files and keys its states on the whole record, so nothing in it changes unless a new input reaches `tell`: model that input as a new event in `steps`, with its code line in the docstring.
- **A new input reaches `tell`**: add it to `State`, give it events in `steps`, add its kind to `test_the_walk_reaches_every_event_the_model_has`, and say it in the docstring's scope.
  Raise `TIPS` or `EVENTS` only with the run time measured again.
- **A module moves** (as unit 6 moved `jbus.mainstate` to `jmerge.mainjson`): change the model's imports and the stub targets to the new module, rerun, and expect the same counts.
  Different counts after a pure move mean the move changed behavior.
- **The property changes.**
  Change `s1`, `s2`, `s3` or `s4` and the sentence in the docstring and here, and show the new property failing on a scratch break before trusting a pass: break the line it guards in your own worktree, uncommitted, run the check, see the trace, `git restore` the file, and see the check back at `9 passed` (or the new count).

Two breaks it was shown to catch on the code before the fix, on 2026-10-20: `if False:` for `if check == "failed":` in `mainmoved.py` breaks S1 in the one-tip-at-a-time world (a failed M1 seen by a pass, then M2 lands pending and the pass drops the red), and `if broken:` in `mainmoved.py` breaks S2 (the pass at green M2 keeps `broken: M1`, and the pass at pending M3 reads red again).
On the fixed code, dropping `broken, waiting, unrun = tip, [], ""` for `waiting, unrun = [], ""` in `mainmoved.py` breaks S1 one tip at a time and over every order.
Dropping `was.get("fixed") or` in `mainmoved.py` passes the walk, since the model writes no `fixed`, and fails `test_a_record_left_owing_a_message_ends_the_red_at_its_fixed_tip` in `features/jbus/tests/test_jbus_main_moved.py`, an older record with `fixed` where GitHub lists no tips.
A break it was shown to catch on the code as it is today, on 2026-11-03: dropping `broken` from `green, broken, waiting, unrun = tip, "", [], ""` in `mainmoved.py` breaks S2 over every order (the trace above).
A break S4 was shown to catch, on 2026-11-10: dropping `tip not in judged and` from `if tip not in judged and (read := failed_at(run, tip)) is not None:` in `mainmoved.tell` breaks S4 one tip at a time and over every order, since a second pass at a failed M1 writes M1's line to `main-reds.jsonl` again.
