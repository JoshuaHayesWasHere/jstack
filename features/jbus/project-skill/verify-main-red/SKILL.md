---
name: verify-main-red
description: Rerun the exhaustive check of main.json's red-main contract, the record `jbus.mainmoved.tell` writes and `jmerge.mainjson` reads for jmerge's red wait ("main is red at <sha12>, its fix merges first"), and read what it finds. Use on any change to mainmoved, mainjson, `jmerge.rows.red`, the pass order in `jbus.cli`, `watch._check`'s answers or the "Main is not red" rule in features/jmerge/docs/jmerge.md, and on any move of the modules it names.
---

# verify-main-red

`main.json` in a jbus project's state is the one record of main's red tip.
`mainmoved.tell` (`features/jbus/src/jbus/mainmoved.py`) is its only writer, once a pass, and builds each record with `jmerge.mainjson.record`; `mainjson.of` (`features/jmerge/src/jmerge/mainjson.py`) reads it; `jmerge.rows.red` (`features/jmerge/src/jmerge/rows.py`) turns it into the wait that holds every pull request but a fix.
A fix is the pull request whose own check proves it (`rows.proves`, of the tests `main.json` keeps as `failed`) or the brief jbus filed for the red (`mainjson.fix_of`).
A test runs the orders someone wrote down.
This check runs every order of merges, check answers, T3 Code answers and passes within its bounds, through the real `tell`, the real `rows.red` and the real `rows.browser_red`, and checks three properties after every pass:

- **S1, no merge onto a known red main.**
  When the newest tip whose check has settled (`green` or `failed`, `mainmoved.SETTLED`) failed, `rows.red` is not empty for a slug that is no fix, nor for the open pull request `fl-fix` at a head whose check does not prove the fix of that tip.
  Broken, jmerge merges onto a red main.
- **S2, no stuck red.**
  When `rows.red` names a tip, no tip that landed after it has a `green` check.
  Broken, jmerge holds every merge after main was fixed.
- **S3, no held fix.**
  When `rows.red` names a tip, `fl-fix` at any head that contains it, whose check ran each test that failed there and passed it, is held neither by `rows.red` nor as main's red by `rows.browser_red`, whatever its slug and whether the filed fix row is open or closed.
  Broken, the fix another row wrote waits behind the red it fixes, as every pull request in jstack did on 2026-10-27 from 17:28.

The model is `features/jbus/tests/main_red_model.py`, standard library only (a `collections.deque` walk, states kept by a `json` key).
Its docstring says what each step is, the code line that backs it, what is stubbed and what is not covered.

## Does a change touch it

Rerun it when the diff touches any of these:

- `features/jbus/src/jbus/mainmoved.py` (`tell`, `main_check`, `failed_at`, `SETTLED`, the `STEPS` slot);
- `features/jmerge/src/jmerge/mainjson.py` (`Record`, `record`, `owed`, `of`, `read`, `FIX`, `failures`);
- `features/jmerge/src/jmerge/rows.py` (`main`, `red`, `Ran`, `proves`, `browser_red`, `main_browser_run`);
- `features/jbus/src/jbus/cli.py` where a pass runs `merge.merge` (`half.said = merge.merge(run)`) before the `after-expedite` slot, or the pass lock (`fcntl.flock`), and `features/jbus/src/jbus/merge.py`;
- `features/jbus/src/jbus/watch.py` `_check` and `_judged`, the answers a tip's check can have;
- `write_json` in `features/jbus/src/jbus/__init__.py`: the model takes a read to see a whole record, which `os.replace` gives;
- the "Main is not red" rule in `features/jmerge/docs/jmerge.md`;
- a move of any of these modules: the model imports them and stubs by module attribute, so a move changes its imports and its stubs, and the check is rerun on the moved code (unit 6 moved `jbus.mainstate` to `jmerge.mainjson` with the same counts).

`scripts/select_tests.py` selects `features/jbus/tests/test_main_red_model.py` for a change to `mainmoved.py`, `mainjson.py`, `rows.py`, `merge.py`, `cli.py` or `features/jmerge/docs/jmerge.md`, through what the model imports and the path it names, so `make check-fast` runs it.
Run it by hand anyway when you change the contract on purpose: what it prints is the point.

## Run it

```sh
uv run pytest features/jbus/tests/test_main_red_model.py -q
```

It takes about a second (3,808 states in the widest world).
On the code as it is today it prints `7 passed`.
The three findings below were strict xfails until `mainjson-red-fix` fixed them.
To print every world:

```sh
uv run python features/jbus/tests/main_red_model.py
```

It prints all four worlds, how many states each walks and how many break each property.

The tests and the world each walks:

| Test | World | Today |
|---|---|---|
| `test_the_walk_reaches_every_event_the_model_has` | every order | passes: each event kind was reached |
| `test_s1_a_failed_tip_seen_by_a_pass_holds_every_merge` | one tip at a time (it lands once the last tip settled and a pass ran since) | passes |
| `test_s1_a_failed_tip_holds_every_merge_whatever_lands_after_it` | every order | passes |
| `test_s2_a_green_tip_seen_by_a_pass_whose_send_goes_ends_the_red` | one tip at a time, T3 Code never loses a send | passes |
| `test_s2_a_green_tip_ends_the_red_when_t3_code_loses_the_send` | one tip at a time | passes |
| `test_s2_a_green_tip_ends_the_red_whatever_lands_after_it` | every order, T3 Code never loses a send | passes |
| `test_s2_a_green_tip_ends_the_red_in_every_order` | every order | passes |
| `test_s3_a_check_that_proves_the_fix_of_a_red_tip_seen_one_at_a_time_is_not_held` | one tip at a time | passes |
| `test_s3_a_check_that_proves_the_fix_is_not_held_in_every_order` | every order | passes |

Each finding's world is cut from a world that passes, so a break there points at that finding's cause.
S1 holds one tip at a time, so S1 breaking over every order needs a tip no pass saw (F2).
S2 holds one tip at a time with every send answered, so S2 breaking one tip at a time needs a lost send (F1), and S2 breaking with every send answered needs a tip no pass saw (F3).
The last test walks S2 over every order, for an order that needs both.
A failure in any test is a new break.

## The findings

All three are fixed: `tell` looks at every tip since its last pass (`landed`), and a pass takes a `fixed` it finds in the record as the end of the red.
The line numbers below are of the code before the fix (`fa810ec`).

- **F1 (S2).**
  After a red tip M1, a green M2 whose send T3 Code loses writes only `fixed` (`mainmoved.py`) and keeps `broken: M1`.
  The next pass, at a tip M3 whose check is pending, writes `broken: M1` again (`check != "green"`) and drops `fixed`: `mainstate.of` (now `mainjson.of`) read `red=M1` with `green=M2`.
- **F2 (S1).**
  A tip that fails and is followed by another before a pass looks at it is never kept as `broken`: `broken` comes from the newest tip's own check.
  With the newest pending, `rows.red` is empty and jmerge merges onto the red main.
- **F3 (S2).**
  The mirror of F2: while main is red jmerge merges only the fix, so a second tip lands by another merge (a second fix, a merge by hand, `--accept`), and a green tip it follows before a pass looks at it is never seen: `broken` stays while the newest tip is pending.
  F2 and F3 have one cause, `tell` reading the newest tip only (`mainmoved.py`), so one fix that reads every tip since `main` may flip both.
  `features/jmerge/docs/jmerge.md` says the wait "ends when jbus sees a green tip", and jbus never sees this one.

## Read a trace

A trace is the shortest order of events to the first state that breaks the property, numbered from `start`.
Tips are `M0` (green, there from the start) to `M3`; a record is printed with its commits as those names and without `at`.
For example F1, on the code before the fix:

```
S2 breaks in 3 of 1006 states (Options(one_at_a_time=True, lost_sends=True)), against "Main is not red" in features/jmerge/docs/jmerge.md
  1. start: M0 is green, no main.json, one red pull request
  2. M1 lands: jmerge merges beta
  3. M1's check settles: failed
  4. pass (no send): tell writes main.json {"broken": "M1", "check": "failed", "main": "M1"}; mainjson reads red=M1 green=-
  5. M2 lands: another merge (the fix, or by hand)
  6. M2's check settles: green
  7. pass (T3 Code loses the send): tell writes main.json {"broken": "M1", "check": "failed", "fixed": "M2", "main": "M1"}; mainjson reads red=- green=M2
  8. M3 lands: jmerge merges beta
  9. pass (no send): tell writes main.json {"broken": "M1", "check": "pending", "green": "M2", "main": "M3"}; mainjson reads red=M1 green=M2
```

The record after a `pass` is what the real `tell` wrote; `red` and `green` are what the real `mainjson.read` gives.
`pass (no send)` is a pass in which no message went, so T3 Code's answer did not matter.

## A real bug or a modeling error

Each step of a trace must be backed by code.
Check every step against this table; a step no line backs is a modeling error, and the model is what gets fixed:

| Step | Backed by |
|---|---|
| `pass (...)` | one `tell` under the pass lock, `features/jbus/src/jbus/cli.py`, in the `after-expedite` slot, `features/jbus/src/jbus/mainmoved.py` |
| `Mn lands: jmerge merges beta` | `rows.red(mainjson.read(state), "beta")` was empty, `features/jmerge/src/jmerge/rows.py`; a merge inside a pass is read before `tell` writes, `features/jbus/src/jbus/cli.py` |
| `Mn lands: another merge` | a merge that asks no `rows.red`, or that `rows.red` lets through as a fix (S3's `fl-fix`), a merge by hand, `jmerge --accept` |
| `jmerge holds fl-fix ...` / `jmerge lets fl-fix merge ...` | the last line of an S3 or S1 trace: `rows.red` and `rows.browser_red` over what `jmerge.cli`'s `Repo.proved` and `Repo.proved_browser` read of the pull request's check, which the model's `proof` stands for |
| `Mn's check settles: <answer>` | an answer `watch._check` gives, `features/jbus/src/jbus/watch.py`; `pending` is a check not ended |
| `T3 Code loses the send` / `refuses the send` | `T3Error` / `T3Refused` from `client.call`, `features/jbus/src/jbus/mainmoved.py` |

The stubs are the other place a model can lie: `mainmoved.main_check`, `mainmoved.failed_at`, `dispatch.launched`, `dispatch.thread_of` and `rebase.held` (`stubbed()` in the model), and `FakePass.run`'s answer to GitHub's list of main's commits, which `landed` asks for.
If one of them is no longer what `tell` calls, the step it stands for is not the code's.
`mock.patch.object` fails on an attribute that is gone, but a name `tell` imports with `from ... import` is not patched by a module attribute: then the real function runs and asks GitHub or T3 Code.

When every step is backed, the trace is a real bug: report it with the trace, in the code's words, and leave the property as it is ("Findings stay findings").

## Change the model when the contract changes on purpose

- **A fix lands for a finding.**
  A finding the walk finds is a strict `xfail` until it is fixed, and its test fails as `XPASS(strict)` once the fix lands: remove that `xfail` mark, and run again to see it pass.
- **`main.json` gets a new key, or `mainjson.of` reads it differently.**
  The model writes and reads the real files and keys its states on the whole record, so nothing in it changes unless a new input reaches `tell`: model that input as a new event in `steps`, with its code line in the docstring.
- **A new input reaches `tell`** (a held message, a second pull request, a conflict): add it to `State`, give it events in `steps`, add its kind to `test_the_walk_reaches_every_event_the_model_has`, and say it in the docstring's scope.
  Raise `TIPS` or `EVENTS` only with the run time measured again.
- **A module moves** (as unit 6 moved `jbus.mainstate` to `jmerge.mainjson`): change the model's imports and the stub targets to the new module, rerun, and expect the same counts.
  Different counts after a pure move mean the move changed behavior.
- **The property changes.**
  Change `s1`, `s2` or `s3` and the sentence in the docstring and here, and show the new property failing on a scratch break before trusting a pass: break the line it guards in your own worktree, uncommitted, run the check, see the trace, `git restore` the file, and see the check back at `7 passed` (or the new count).

Two breaks it was shown to catch on the code before the fix, on 2026-10-20: `if False:` for `if check == "failed":` in `mainmoved.py` breaks S1 in the one-tip-at-a-time world (a failed M1 seen by a pass, then M2 lands pending and the pass drops the red), and `if broken:` in `mainmoved.py` breaks S2 with every send answered (the pass at green M2 keeps `broken: M1`, and the pass at pending M3 reads red again).
On the fixed code, dropping `broken, waiting = tip, []` for `waiting = []` in `mainmoved.py` breaks S1 one tip at a time and over every order.
On 2026-10-27 S3 broke on main's code, which knew a fix only by its slug: M1 lands and fails, a pass writes `broken: M1`, and `jmerge holds fl-fix, its head over M1, its check ran every test: main is red at M1, its fix merges first`.
With the fix, dropping `ran.over == red and` from `rows.proves`, or the path test from `Ran.covers`, breaks S1 one tip at a time and over every order.
Dropping `owed_at or` in `mainmoved.py` passes the walk, since the model's GitHub always lists the tips, and fails `test_a_green_tip_whose_message_was_lost_ends_the_red_though_the_next_tip_is_pending` in `features/jbus/tests/test_jbus_main_moved.py`, where the list is empty.
