# The merge flow, as a TLA+ spec

Two pull requests, a main that can go red from a merge or from outside, and a machine that a crew can leave full.
The home wrote it on 2026-10-23 to test the premise behind "nothing moves", and it came in with rejudge-red-prs.

- `FlowToday.tla` models the code as of main 38726c35, and each of its conditions names the file and line that checks it.
- `FlowDesign.tla` models the design: cross-cutting-guard (`Check`), rejudge-red-prs (`Rejudge`) and crew-leftover-procs (`Sweep`).
- `canary/` holds the design with each fix taken out: `NoGuard`, `NoRejudge` and `NoSweep`.
- `flow_canaries.py` runs TLC on all of it, and `FlowToday.map.py` labels the chart in `FlowToday-statechart/`.

## Check the rules

```sh
S=features/skill-library/skills/statechart/scripts
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "$S" \
    python features/jmerge/spec/flow_canaries.py
```

Run it from the repo root.
Today's code breaks all four rules.
The design holds all four.
`NoGuard` breaks `NoMergeTurnsMainRed`, `NoRejudge` breaks `FlowsWhenGreen`, and `NoSweep` breaks `FlowsWhenGreen` and `MachineNotLeftFull`.
`features/jmerge/tests/test_flow_spec.py` runs it, and skips where no Java runs TLC.

## Where `Rejudge` and the code differ

- The model's `ranRed[p]` is a check that ran while main was red, and the code's condition is a base that has moved since the check started (`features/jmerge/src/jmerge/cli.py`, `Repo.again`). The code also judges again a check that failed over a base that was green and moved since, and a change broken on its own then gets its one message, or with no `fresh-check` file fails again at the updated head as its own.
- The model judges again any red pull request, and the code only one whose single shortfall is the failed check: a pull request short of a review, a queue row or anything else keeps `check has not passed` (`Repo.judge`).
- The model's `told[p]` is one flag that the crew's fix clears, and the code asks once for a head and a base tip, in `fresh.json` and `base-merges.json`, while jbus tells a crew once for a head.
- The model has one main, and the code reads each pull request's own base, main or an integration branch.
- The model leaves out guarded paths, which get GitHub's update with no fresh check, and a GitHub that refuses the update.
- The code checks no room before it judges again: the fresh check runs in its own unit under `fresh.lock`, one a run, so the model's `Rejudge` has no `~full`.
