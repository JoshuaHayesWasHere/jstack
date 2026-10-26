# The home tree, as a TLA+ spec

A root home and two sibling child homes on one repo, with the rules Josh set for them on 2026-10-23.
Child a is short-lived and does one feature, and child b is a routine with a declared rhythm.
Each child has a pull request, a crew thread and two calls to Josh, and a call reaches Josh through a route that can change and fail.

- `HomeTree.tla` holds what both models share: the variables, the start, and the rules, each with its sentence.
- `HomeTreeToday.tla` models today's code, and each of its conditions names the file and line that checks it.
- `HomeTreeDesign.tla` models the design, and its constant `Drop` takes out one of its guards.
- `canaries.py` runs TLC on all of it, and `HomeTreeToday.map.py` labels the chart.

## Check the rules

```sh
python3 features/home/spec/canaries.py
```

Run it from the repo root.
It checks that each rule holds in the design in each scene.
It checks that each canary, the design with one guard taken out, breaks the rule that rests on that guard, so no rule holds by construction.
It checks that each rule holds in today's code in each scene, with the merge switch either way.
It prints one line for each run and ends 0 when every run says what it should.
TLC is the statechart skill's pinned `tla2tools.jar`, and Java is `JAVA` or a `java` on `PATH`.
`features/home/tests/test_home_tree_spec.py` runs it, and skips where no Java runs TLC.

Two siblings that both raise calls are too many states for one run of TLC, so each run is a scene.
The scene `a` is child a alone with both its calls and routes that change and fail, and `b` is child b alone in the same way.
The scene `siblings` is both children, with no calls of their own and routes that stay.
One call never waits on another, and what the siblings share is main, the merge lock and the routes, so the siblings' scene checks what they share.
In the siblings' scene the rules on calls hold with little to check, since only the root's notices are calls there and the routes stay: the scenes `a` and `b` check those rules.

## Draw the chart

```sh
S=features/skill-library/skills/statechart/scripts
cd features/home/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "../../../$S" \
    statechart from-spec HomeTreeToday.tla --against HomeTreeDesign.tla --label "the design" --png
```

It writes `HomeTreeToday-statechart/`: `chart.mmd` and `chart.png`, `stories.md` and `summary.json`.
Today's code breaks no rule, so it draws no `bug-N` chart and `stories.md` is empty.
Its `tlc/` folder holds TLC's output, which is not committed.
The chart's scene, in `HomeTreeToday.cfg` and `HomeTreeDesign.cfg`, is child a alone with one call, routes that stay, and K at 1.
TLC 2.19 fails in a run of one worker with `-continue` once a rule breaks in some thousands of states, and the statechart command runs one worker, so the chart's scene is small.
The routes stay in the chart's scene and move in the scenes `a` and `b` of `canaries.py`.
The chart draws only the rules that are invariants.
A ready pull request that never merges (`ReadyMerges`) is a property, and today's code keeps it since pull request 357 let jbus merge a child's pull request, which the chart draws as a step of today's code.
Stranding (`CallsReachJosh`) is a property too, and today's code keeps it since pull request 332 moved what waits for a route the setting dropped.
The merge race (`NoBlindMerge`) needs two pull requests, so it is in the siblings' run of `canaries.py` and not in the chart.

## The four rules today's code broke

Until the branch hometree-rules, today's code broke four rules, each along a story of the chart.
Each now holds by the guard the design names for it, and a test in `features/home/tests/test_home_tree_spec.py` drives the real code along that story and fails on the code before it.

1. `NoRetireWithOpen`, by the retire guard: the handoff skill closes a scope only when `jbus out --scope <scope>` says it has nothing out (`jbus/children.py`).
   The test is `test_no_retire_with_open_a_child_with_its_crew_out_is_not_retired`, where the handoff keeps the scope open while a crew jbus launched for it is out, and closes it once the crew's row is done.
2. `StallFlagged`, with `FirstStrike`, `NudgesBounded` and `AsksAfterTwo`, by the root's watch of its children: a jbus pass nudges a child that has been quiet for its patience with work out, tells the user at once, nudges it once more and then asks the user (`jbus/children.py`, `watch`).
   The test is `test_stall_flagged_a_quiet_child_with_its_crew_out_is_flagged`, where real jbus passes nudge the child's home thread an hour after its crew stopped, and the user hears of it.
3. `OneMerger`, by jbus as the only merger: jbus runs `jmerge` whatever `home-thread` holds, and a home's `jmerge --home` merges nothing (`jbus/merge.py`, `jmerge/cli.py`).
   The test is `test_one_merger_no_home_merges_and_jbus_merges_child_a_s_pull_request`, where with an id in `home-thread` neither the root's run nor child a's merges, and jbus's merges child a's pull request.
4. `NoBlindMerge`, by the merge lock: a run of `jmerge` holds `$H/merge.lock` from its read of main's tip to its merge (`jmerge/lock.py`).
   It breaks only in the siblings' scene, so no story of the chart has it.
   The test is `test_no_blind_merge_a_second_run_merges_nothing_while_one_is_merging`, where a second run started in the middle of the first one's merge merges nothing.

## What the model leaves out

- The wake setting `both`, which posts to the home thread and the webhook at once.
- A third child, and a sibling's message to another, which goes through the root.
- A pull request that stops being ready a second time, and a push to main by anything but a merge.
- The crew's own stalls, which the crew skill and jbus's waits cover.
