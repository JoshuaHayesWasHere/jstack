# Act once, as a TLA+ spec

`TellOnce.tla` follows jbus's act-once steps as st-fix-tell-once leaves them (2026-11-11): a pass sends a message, posts a body, runs a check again, parks a question, holds a row, appends a line or archives threads once, and keeps the mark that it did in a file of its own, in a step of its own.
A pass can die between any two writes.
Each of the 21 carriers of the st-state-ledger's machine TellOnce is one variable, with the code that writes it quoted beside it.
One behavior follows one act of `Carriers`, since the acts write different files and do not wait on each other, so the states of the 13 acts add up and do not multiply.
The shared shape is three tables: `Code(c)`, the order in which act c's pass writes; `Guard(c)`, the marks it reads at its start; and `Absorbs(c)`, whether its receiver takes a repeat under a key it took as the same act (T3 Code's `clientRequestId`, a question's key, GitHub's state, the relay's id of a body).
An act whose key could move between two tries writes it first, the step `pin`: stall.twice's page, the word's thread, the account question's tip, a skill notice's merges and failover's carry-on, so a try after a pass that died names the key the receiver may have taken already.
The clock's ladder (count, act once, count, log a stall for the home) and owed.json's second writer (failover's carry-on, then `owed.taken`) have actions of their own.
Each quote names its file and no line, and `features/jbus/tests/test_tell_once_spec.py` finds the one place each stands.

## Check the rules of act once

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -continue -config TellOnce.cfg TellOnce.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
The rules:

- `NoTellTwice`: the receiver takes each act once, a repeat after a pass that died being one it takes as the same, and no pass does an act again once its guard read the act's mark.
- `NoTellLost`: between passes, an act still owed whose mark is written was taken, and the stall the clock's `home` says went is in the log.

TLC breaks neither on any act, over 1496 distinct states at depth 24, as `TellOnce.cfg`'s comment says.
Before st-fix-tell-once it broke them on seven, over 1676 distinct states: stall.twice's page and the clock's stall were lost, and failover's ask, the second target's body, a word, the account question and a skill's notice could go twice.
st-model-upkeep-run found an eighth, the finding of a hold only the user lifts (`heldlift`, `clock.held`'s lift branch), lost the same way as the clock's stall, and the same fix of `Box.send` closes it.
`TellOnce.cfg`'s comment names what closed each, and `features/jbus/tests/test_tell_once_crash.py` kills a pass at each of the seven in the code and shows the next pass tells once.
The canary `Fault = "mark-first"` writes the marks before the act and breaks `NoTellLost` on every act; `Fault = "no-mark"` reads no mark and breaks `NoTellTwice` on every act.
In the code the half of `NoTellTwice` that says no act runs after its mark was read holds by the guard's shape; the receiver's count is the half that checks the code.

## Draw the act-once charts

The fourteen acts are three charts, so each chart's overview fits in ten boxes with at most 15 states to a group.
`TellOnce.chart.cfg` draws the six acts that tell a thread through `t3_thread_send`, `TellOnceOther.chart.cfg` the seven that do not, and `TellOnceOwed.chart.cfg` the ask owed after a limit, which alone has as many states as the others; `TellOnce.cfg` still checks all fourteen.
Since one behavior follows one act, the three charts together draw every path.

```sh
S=features/skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "../../../$S" \
    statechart from-spec TellOnce.tla --config TellOnce.chart.cfg \
    --title "Does jbus tell a thread twice, or drop a tell, when a pass dies?"
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "../../../$S" \
    statechart from-spec TellOnce.tla --config TellOnceOther.chart.cfg --out TellOnceOther-statechart \
    --title "Does jbus act twice, or drop an act, outside a thread when a pass dies?"
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "../../../$S" \
    statechart from-spec TellOnce.tla --config TellOnceOwed.chart.cfg --out TellOnceOwed-statechart \
    --title "Does jbus send an ask owed after a limit twice when a pass dies?"
```

They write `TellOnce-statechart/`, `TellOnceOther-statechart/` and `TellOnceOwed-statechart/`, labelled by `TellOnce.map.py`, with one `bug-N` chart for each act that breaks a rule, and none while no act does.
A state's color says where its tell stands: orange not told, green told once, red told twice, each shade a step short of done that its label names, such as a mark written or the outbox holding it; the ask's chart splits by whether owed.json still owes the ask and by its try.

## What the act-once model leaves out

- Time and liveness: the rules are safety rules, so an act a guard keeps from running forever passes them (such as expedite's second tell once its key is marked and expedite.json is not).
- A clock wait whose kind goes back to one it had: its old key is still in sent.json, and the model starts every new wait under a new key.
- `Box.send` keeps a finding's line with its key in `unlogged.json`, one write, for every keyed finding (an ask resent, failover's, expedite's, stall.twice's page): the model has it for the clock's stall, the page as its act, and `clock.held`'s lift.
- The event `item.write` records after its line, and cancelled.py's false "not run again" after a rerun whose finding was lost: each is a fault of its own, not a tell twice or lost.
- The second target's timeout after the target took the body is a pass that dies after the act.
- A word whose thread tried cannot be read (`Client.holds` answers neither) waits for a later pass: a safety rule passes a wait.
- The merges a skill's notice did not name, since a thread was tried with others, go on the next pass under a key of their own: the model has the retry's key, not the next notice.
