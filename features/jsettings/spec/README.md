# GitHub's API budget, as a TLA+ spec

`GhBudget.tla` models the budget of `gh` calls that every process of jstack shares, at main aa5469d97 (2026-11-11): the six carriers of the st-state-ledger rows D-081 to D-086, one VARIABLE each.

| Row | Carrier | Variable | Written by |
|---|---|---|---|
| D-081 | `gh-rate-limit.json`, the last answer of `gh api rate_limit` | `kept` | `budget._keep`, a temp file then one rename, under the lock |
| D-082 | `.gh-rate-limit.json.lock` | `keepLock` | `budget._locked`, an flock |
| D-083 | the held gate, in each pass's memory | `gate` | `budget.held`, read once by `watch.look` |
| D-084 | `gh-calls.jsonl`, one line per call | `log` | `proc._log`, one append |
| D-085 | `gh-calls.old.jsonl` | `old` | `proc._log`, `os.replace` once the log is past `KEPT`, under the flock of `.gh-calls.jsonl.lock` |
| D-086 | `gh-slots/<0..15>` | `slots` | `proc._slot`, a non-blocking flock |

Each VARIABLE's comment, and each condition of a step, names the file and quotes the code, with no line number.
`features/jsettings/tests/test_gh_budget_spec.py` finds the one place each quote stands, so a move of the lines leaves no cite to renumber.
It also runs TLC on today's code, on today's rotation alone, and on the canary.

## Check the rules

```sh
cd features/jsettings/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config GhBudget.cfg GhBudget.tla
```

TLC writes a `states/` folder where it runs, so run it in a copy of this folder.

- `NoLostGeneration`, "a rotation never drops lines another rotation kept": the old log holds the whole log a rename found past `KEPT`, never a log a second rename moved over it.
- `HeldWhenLow`, "no call starts while the kept budget is under the floor": each call starts with `logged` reading more than `FLOOR` left, or reading nothing.
- `CappedRuns`: each running `gh` holds a slot of its own.

`Fault = "locked-rotate"` is today's code: one flock, `.gh-calls.jsonl.lock`, held over the size check and the rename.
`Fault = "unlocked-rotate"` is the canary, the code before that lock, where the check and the rename are two steps with no lock.

## The findings

The code the model was first drawn from broke both rules, and today's code breaks `HeldWhenLow`; `GhBudget.cfg`'s comment keeps the counts.

1. **A whole log lost** (`NoLostGeneration`, 26 states), fixed; the canary, `Fault = "unlocked-rotate"`, still shows it.
   Two processes log a call each while the log is past its size, and both pass `if path.stat().st_size > KEPT:`.
   The first renames the log to `gh-calls.old.jsonl`, and a line starts a new log.
   The second renames that one-line log over the old log: the whole generation the first kept is in no file.
   The window is small (two `_log` calls at one moment, once per 16 MiB), but nothing ruled it out.
   `proc._log` now checks the size and renames under one flock of `.gh-calls.jsonl.lock`, so the second process checks the size again once the first has renamed, and renames nothing; the rule holds over 225479 distinct states.
   `test_gh_calls.py` runs the two processes and finds the old log whole.
2. **A call at the floor** (`HeldWhenLow`, 18 states, the first TLC stops at).
   A pass reads the budget once, in `watch.look`, and makes every call of the pass on that reading.
   Its own calls and another pass's take the budget to the floor, and the pass goes on calling.
   A per-call gate would not close it either: the reading is the log, and the log has a call's `remaining` only once the call has ended.

The chart's story (`GhBudget-statechart/stories.md`, `bug-1.mmd`) tells the call at the floor in the user's words; the chart is drawn on today's code, so the lost log is in none of its states.

Read off the model, not checked by TLC: `budget._lowest` reads only `gh-calls.jsonl`, so right after a rotation the last minute's lines are in the old log, which `logged` does not read, and for up to `WITHIN` seconds the reading can come from the kept answer, which may be higher.

## Draw the chart

```sh
S=features/skill-library/skills/statechart/scripts
cd features/jsettings/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "../../../$S" \
    statechart from-spec GhBudget.tla --expect-broken HeldWhenLow \
    --title "Does the gh budget hold, and does the call log keep each full log?"
```

It writes `GhBudget-statechart/`, labelled by `GhBudget.map.py`, which reads the floor and `KEPT` from `GhBudget.cfg`.
Its `tlc/` folder holds TLC's output, which is not committed.
The map's header names each join of values the code writes.

## What the model leaves out

- One window stands for `core` and `graphql`, and `held` reads the lower of the two.
  A window's reset, and the second count of one window GitHub keeps, are left out: the count only falls.
- Time is one step, `Tick`: a minute passes, and every line so far and the kept answer are older than `WITHIN`.
- A line holds its `remaining` only; its other fields (`caller`, `endpoint`, `status`, `reset`, `http`, ...) are read by no rule.
- `gh api rate_limit` goes through `proc.run` too, takes a slot and logs a line; the model asks it with neither.
- GitHub refusing a call at 0 and jmerge's backoff gate (`jmerge.backoff`), jmerge's merges, which go under the floor by design, and the threads' own `gh`, which no runner logs.
- A process that dies: the kernel lets its flocks go, and a rename or an append is one step.
- The bound: two processes, one slot (GH_CAP 16), a log renamed past one line (KEPT 16 MiB), a floor of 1 and 4 calls.
