---
name: verify-main-red
description: Rerun the exhaustive check of main.json's red-main contract, the record `jbus.mainmoved.tell` writes and `jbus.mainstate` reads for jmerge's red wait ("main is red at <sha12>, its fix merges first"), and read what it finds. Use on any change to mainmoved, mainstate, `jmerge.rows.red`, the pass order in `jbus.cli`, `watch._check`'s answers or the "Main is not red" rule in docs/jmerge.md, and on unit 6's move of `jbus.mainstate` to `jmerge.mainjson`.
---

# verify-main-red

`main.json` in a jbus project's state is the one record of main's red tip.
`mainmoved.tell` (`src/jbus/mainmoved.py:77-173`) is its only writer, once a pass; `mainstate.of` (`src/jbus/mainstate.py:41-53`) reads it; `jmerge.rows.red` (`src/jmerge/rows.py:84-87`) turns it into the wait that holds every pull request but the fix's.
A test runs the orders someone wrote down.
This check runs every order of merges, check answers, T3 Code answers and passes within its bounds, through the real `tell` and the real `rows.red`, and checks two properties after every pass:

- **S1, no merge onto a known red main.**
  When the newest tip whose check has settled (`green` or `failed`, `mainmoved.SETTLED`) failed, `rows.red` is not empty for a slug that is no fix.
  Broken, jmerge merges onto a red main.
- **S2, no stuck red.**
  When `rows.red` names a tip, no tip that landed after it has a `green` check.
  Broken, jmerge holds every merge after main was fixed.

The model is `tests/main_red_model.py`, standard library only (a `collections.deque` walk, states kept by a `json` key).
Its docstring says what each step is, the code line that backs it, what is stubbed and what is not covered.

## Does a change touch it

Rerun it when the diff touches any of these:

- `src/jbus/mainmoved.py` (`tell`, `main_check`, `SETTLED`, the `STEPS` slot);
- `src/jbus/mainstate.py` (`of`, `read`, `GREEN`, `FIXED`, `FIX`);
- `src/jmerge/rows.py` (`main`, `red`);
- `src/jbus/cli.py` where a pass runs `merge.merge` (line 146) before the `after-expedite` slot, or the pass lock (215-219), and `src/jbus/merge.py`;
- `src/jbus/watch.py` `_check` (797-828), the answers a tip's check can have;
- `write_json` in `src/jbus/__init__.py` (434-444): the model takes a read to see a whole record, which `os.replace` gives;
- the "Main is not red" rule in `docs/jmerge.md`;
- unit 6 of the plan, which moves `jbus.mainstate` to `jmerge.mainjson`: the model imports `mainstate` and stubs by module attribute, so the move changes its imports and its stubs, and the check is rerun on the moved code.

`scripts/select_tests.py` selects `tests/test_main_red_model.py` for a change to `mainmoved.py`, `mainstate.py`, `rows.py`, `merge.py`, `cli.py` or `docs/jmerge.md`, through what the model imports and the path it names, so `make check-fast` runs it.
Run it by hand anyway when you change the contract on purpose: what it prints is the point.

## Run it

```sh
uv run pytest tests/test_main_red_model.py -q
```

It takes about a second (4,402 states in the widest world).
On the code as it is today it prints `3 passed, 4 xfailed`.
The four xfails are the three findings below, each `xfail(strict=True)`: the run stays green while the finding stands, and its test fails as `XPASS(strict)` once a fix lands.
To read their traces:

```sh
uv run pytest tests/test_main_red_model.py -q --runxfail
uv run python tests/main_red_model.py
```

The second prints all four worlds, how many states each walks and how many break each property.

The tests and the world each walks:

| Test | World | Today |
|---|---|---|
| `test_the_walk_reaches_every_event_the_model_has` | every order | passes: each event kind was reached |
| `test_s1_a_failed_tip_seen_by_a_pass_holds_every_merge` | one tip at a time (it lands once the last tip settled and a pass ran since) | passes |
| `test_s1_a_failed_tip_holds_every_merge_whatever_lands_after_it` | every order | xfail F2 |
| `test_s2_a_green_tip_seen_by_a_pass_whose_send_goes_ends_the_red` | one tip at a time, T3 Code never loses a send | passes |
| `test_s2_a_green_tip_ends_the_red_when_t3_code_loses_the_send` | one tip at a time | xfail F1 |
| `test_s2_a_green_tip_ends_the_red_whatever_lands_after_it` | every order, T3 Code never loses a send | xfail F3 |
| `test_s2_a_green_tip_ends_the_red_in_every_order` | every order | xfail F1 and F3 |

Each finding's world is cut from a world that passes, so its mark flips once that finding is fixed, whatever the others do.
S1 holds one tip at a time, so S1 breaking over every order needs a tip no pass saw (F2).
S2 holds one tip at a time with every send answered, so S2 breaking one tip at a time needs a lost send (F1), and S2 breaking with every send answered needs a tip no pass saw (F3).
The last test walks S2 over every order, for an order that needs both, and flips once F1 and F3 are both fixed.
A failure in a test that passes today is a new break.

## The findings

- **F1 (S2).**
  After a red tip M1, a green M2 whose send T3 Code loses writes only `fixed` (`mainmoved.py:173`) and keeps `broken: M1`.
  The next pass, at a tip M3 whose check is pending, writes `broken: M1` again (164-165, `check != "green"`) and drops `fixed`: `mainstate.of` reads `red=M1` with `green=M2`.
- **F2 (S1).**
  A tip that fails and is followed by another before a pass looks at it is never kept as `broken`: `broken` comes from the newest tip's own check (97-99).
  With the newest pending, `rows.red` is empty and jmerge merges onto the red main.
- **F3 (S2).**
  The mirror of F2: while main is red jmerge merges only the fix, so a second tip lands by another merge (a second fix, a merge by hand, `--accept`), and a green tip it follows before a pass looks at it is never seen: `broken` stays while the newest tip is pending.
  F2 and F3 have one cause, `tell` reading the newest tip only (`mainmoved.py:87-100`), so one fix that reads every tip since `main` may flip both.
  `docs/jmerge.md` says the wait "ends when jbus sees a green tip", and jbus never sees this one.

## Read a trace

A trace is the shortest order of events to the first state that breaks the property, numbered from `start`.
Tips are `M0` (green, there from the start) to `M3`; a record is printed with its commits as those names and without `at`.
For example F1:

```
S2 breaks in 3 of 1006 states (Options(one_at_a_time=True, lost_sends=True)), against "Main is not red" in docs/jmerge.md
  1. start: M0 is green, no main.json, one red pull request
  2. M1 lands: jmerge merges beta
  3. M1's check settles: failed
  4. pass (no send): tell writes main.json {"broken": "M1", "check": "failed", "main": "M1"}; mainstate reads red=M1 green=-
  5. M2 lands: another merge (the fix, or by hand)
  6. M2's check settles: green
  7. pass (T3 Code loses the send): tell writes main.json {"broken": "M1", "check": "failed", "fixed": "M2", "main": "M1"}; mainstate reads red=- green=M2
  8. M3 lands: jmerge merges beta
  9. pass (no send): tell writes main.json {"broken": "M1", "check": "pending", "green": "M2", "main": "M3"}; mainstate reads red=M1 green=M2
```

The record after a `pass` is what the real `tell` wrote; `red` and `green` are what the real `mainstate.read` gives.
`pass (no send)` is a pass in which no message went, so T3 Code's answer did not matter.

## A real bug or a modeling error

Each step of a trace must be backed by code.
Check every step against this table; a step no line backs is a modeling error, and the model is what gets fixed:

| Step | Backed by |
|---|---|
| `pass (...)` | one `tell` under the pass lock, `src/jbus/cli.py:215-219`, in the `after-expedite` slot, `src/jbus/mainmoved.py:176-183` |
| `Mn lands: jmerge merges beta` | `rows.red(mainstate.read(state), "beta")` was empty, `src/jmerge/rows.py:84-87`; a merge inside a pass is read before `tell` writes, `src/jbus/cli.py:146` |
| `Mn lands: another merge` | a merge that asks no `rows.red`: the `main-red-<sha12>` fix (`mainstate.fix_of`), a merge by hand, `jmerge --accept` |
| `Mn's check settles: <answer>` | an answer `watch._check` gives, `src/jbus/watch.py:797-828`; `pending` is a check not ended |
| `T3 Code loses the send` / `refuses the send` | `T3Error` / `T3Refused` from `client.call`, `src/jbus/mainmoved.py:143-153` |

The stubs are the other place a model can lie: `mainmoved.main_check`, `dispatch.launched`, `dispatch.thread_of` and `rebase.held` (`stubbed()` in the model).
If one of them is no longer what `tell` calls, the step it stands for is not the code's.
`mock.patch.object` fails on an attribute that is gone, but a name `tell` imports with `from ... import` is not patched by a module attribute: then the real function runs and asks GitHub or T3 Code.

When every step is backed, the trace is a real bug: report it with the trace, in the code's words, and leave the property as it is ("Findings stay findings").

## Change the model when the contract changes on purpose

- **A fix lands for a finding.**
  Its test fails as `XPASS(strict)`: remove that `xfail` mark, and run again to see it pass.
  A fix for F2 or F3 that looks at the tips between two passes is a new step for `tell` to make; the model's events need not change.
- **`main.json` gets a new key, or `mainstate.of` reads it differently.**
  The model writes and reads the real files and keys its states on the whole record, so nothing in it changes unless a new input reaches `tell`: model that input as a new event in `steps`, with its code line in the docstring.
- **A new input reaches `tell`** (a held message, a second pull request, a conflict): add it to `State`, give it events in `steps`, add its kind to `test_the_walk_reaches_every_event_the_model_has`, and say it in the docstring's scope.
  Raise `TIPS` or `EVENTS` only with the run time measured again.
- **A module moves** (unit 6, `jbus.mainstate` to `jmerge.mainjson`): change the model's imports and the stub targets to the new module, rerun, and expect the same counts.
  Different counts after a pure move mean the move changed behavior.
- **The property changes.**
  Change `s1` or `s2` and the sentence in the docstring and here, and show the new property failing on a scratch break before trusting a pass: break the line it guards in your own worktree, uncommitted, run the check, see the trace, `git restore` the file, and see the check back at `3 passed, 4 xfailed` (or the new count).

Two breaks it was shown to catch, on 2026-10-20: `if False:` for `if check == "failed":` at `mainmoved.py:98` breaks S1 in the one-tip-at-a-time world (a failed M1 seen by a pass, then M2 lands pending and the pass drops the red), and `if broken:` at `mainmoved.py:164` breaks S2 with every send answered (the pass at green M2 keeps `broken: M1`, and the pass at pending M3 reads red again).
