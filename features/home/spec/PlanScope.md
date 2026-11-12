# A plan entry and a scope's retire, as a TLA+ spec

`PlanScope.tla` follows three things of one scope, s, as the files keep them, with a process that can die between any two writes:

- one entry of its plan, from its `Stage:`, `Status:` and `Builds on:` lines to `jbus plan close`, which appends the section to `plan-done.md` and then rewrites `plan.md` (`jbus/plan.py`);
- the scope's retire by `/handoff`, step by step: the note in `handoff.next.md`, its gate asked of the catch-all and `gates.md` moved aside, the note kept in `log/` with its `Was home:` line, the older `handoff.md` moved to `log/`, `jbus retire`, which under both homes' `blockers.lock` counts s's fixes in the catch-all's ledger, moves `plan.md` to `plan-archived.md` and empties s's ledger, `home-id` removed, and the note cleared (`skills/handoff/SKILL.md`);
- a blocker's fixes counted in `blockers.json`, and one fix moved from s to the catch-all, `uncategorized`, by `jbus queue move`, which rewrites the brief's `Home:` line and then carries the try under both homes' `blockers.lock` (`jbus/blockers.py`, `rehome`).

It has one variable for each row of the state ledger whose machine is PlanScope (A-168, C-065 to C-068, C-073, C-074, C-081, C-082, C-095, C-099), and each one's comment quotes the code that writes it, or says no code does and quotes the code that reads it.
Each condition of a step quotes its code with no line number, and `features/home/tests/test_plan_scope_spec.py` finds the one place each quote stands.
`Life` maps the retire onto HomeTree's `life`: s is working until its plan is archived, then retired, or handed to the catch-all where it had work out, and the map labels them in HomeTreeToday's words.

## Check the rules

```sh
cd features/home/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config PlanScope.cfg PlanScope.tla
```

Run it in a copy of this folder.
TLC stops at the first rule that breaks, so the test checks each rule of `PlanScope.cfg` in a run of its own, as `statechart from-spec` does, over 850500 distinct states.

- `RetireWhole`, a retired scope's work has a home, holds: the archive asks the gate of the catch-all and moves `gates.md` aside before it moves `plan.md`, and once `plan.md` is gone every brief that named s, by name or by its thread's id, is the catch-all's (`jbriefs/home.py`).
- `FixCountedOnce`, a fix is counted once across a move, holds: a move holds both locks from its read to its second write, and so does a retire to its last, and run again each carries each try once, by its sha.
- `EntryOnce`, an entry is in `plan.md` or `plan-done.md` and in both only between the two writes of one close, holds: a close that dies between its two writes leaves the section in both, and the home closes it again, since `jbus plan` says `close it`, and `plan.close` finds the section already at the end of `plan-done.md`, appends nothing and rewrites the plan.
- `FixCountedWhereRead`, a counted fix is in the ledger admit reads for it, a rule this model adds, breaks: a move that dies after it rewrote the `Home:` line and before `rehome` leaves the try where admit no longer reads it until someone runs the move again.
- `FixCountedWhereReadOrMoveAgain` holds: that cut move is the only way `FixCountedWhereRead` breaks, since `jbus retire` carries s's tries to the catch-all's ledger before `plan.md` moves, and admit reads its brief's home again under that home's lock.

The canaries break their rule: `Fault = "close-twice"` (a close run again after one cut short appends again, as the close did before it skipped the append) breaks `EntryOnce` along CloseAppend, CloseDies, CloseAppend, and `Fault = "move-one-lock"` (the move takes only the lock of the ledger it carries to, so a fix counted meanwhile in the other is lost) breaks `FixCountedOnce`; `Fault = "retire-no-carry"` (the archive before `jbus retire`) and `Fault = "carry-then-unlock"` (a fix counted in s between the carry and the archive) break `FixCountedWhereReadOrMoveAgain`.

## Draw the chart

```sh
S=features/skill-library/skills/statechart/scripts
cd features/home/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "../../../$S" \
    statechart from-spec PlanScope.tla --config PlanScope.chart.cfg --count-config PlanScope.cfg \
    --expect-broken FixCountedWhereRead --title "A plan entry and a scope's retire: is any work lost?" --png
```

It writes `PlanScope-statechart/`, labelled by `PlanScope.map.py`, in two regions: the scope, and its entry and fix.
`PlanScope.chart.cfg` is the chart's scene: one start (each line of the entry as the template writes it), one fix with both head lines, no fix that fails and no run of `jbus clear`, 1443 states where the whole model's are too many to draw.
`states.tsv` and `arrows.tsv` list its 428 states and 1,441 arrows between them, each with its action and its count of model steps.
They leave out the rest of `PlanScope.cfg`'s 850,500 states: labelling its 1,178,100 before #1791 reached 29.5 GB, more than this machine has free, so `--count-config PlanScope.cfg` has TLC count them, with no graph kept, for the chart's tab, which says the tables leave them out.
Its one bug story is the one broken rule: the move cut before its carry.

## What the model leaves out

- A gate `jbus gate` refuses, which the archive keeps whole in the note in `log/`, which no home reads.
- `forgo`, which gives back the try of a fix removed before it launched, the cap's `pending` wait, and `decision question <n>` lines.
- Two closes, or a close and a retire, run at once: `plan.close` takes no lock, and one home thread runs both.
- A party's handoff, which writes `handoff.md` from `handoff.next.md` with its `Was home:` line: no scope runs it.
- `/home <scope>`, which moves `plan-archived.md` back.
