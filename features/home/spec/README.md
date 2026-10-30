# The home tree, as a TLA+ spec

A root home and two sibling child homes on one repo, with the rules Josh set for them on 2026-10-23.
Child a is short-lived, does one feature and is archived, and child b is a routine with a declared rhythm.
Each child has a pull request, a crew thread and two calls to Josh, and a call reaches Josh through the root's home thread, which can fail.

- `HomeTree.tla` holds the variables, the start, and the rules, each with its sentence.
- `HomeTreeToday.tla` models today's code, and each of its conditions names the file that checks it and quotes the code, with no line number.
  `test_home_tree_spec.py` finds the one place each quote stands, so a rebase that moves the lines leaves no cite to renumber.
  It is the design too, since the code has each of the design's guards, and its constant `Drop` takes out one of them.
- `canaries.py` runs TLC on all of it, and `HomeTreeToday.map.py` labels the chart.

## Check the rules

```sh
python3 features/home/spec/canaries.py
```

Run it from the repo root.
It checks that each canary, today's code with one guard taken out, breaks the rule that rests on that guard, so no rule holds by construction.
It checks that each rule holds in today's code in each scene, with the merge switch either way.
It prints one line for each run and ends 0 when every run says what it should.
TLC is the statechart skill's pinned `tla2tools.jar`, and Java is `JAVA` or a `java` on `PATH`.
`features/home/tests/test_home_tree_spec.py` runs it, and skips where no Java runs TLC.

Two siblings that both raise calls are too many states for one run of TLC, so each run is a scene.
The scene `a` is child a alone with both its calls and a home thread that can fail, and `b` is child b alone in the same way.
The scene `siblings` is both children, with no calls of their own and a home thread that never fails.
One call never waits on another, and what the siblings share is main, the merge lock and the home thread, so the siblings' scene checks what they share.
In the siblings' scene the rules on calls hold with little to check, since only the root's notices are calls there and the home thread never fails: the scenes `a` and `b` check those rules.
The failed route, `RouteFails` and `RouteMends`, steps only where `MayFail` is `TRUE`, which is the scenes `a` and `b` of `canaries.py` and not `HomeTreeToday.cfg`.
The canary `keep-on-fail` breaks `CallsReachJosh` in scene `a` only after a post to the home thread fails, so it shows the failed route steps there.
The run of every invariant checks `SceneStill` on the whole model: no child, call or notice outside the scene ever leaves its start.
So a run of a property gives TLC the scene alone (`Kids <- Made` in its config), and it finds the same states without a branch and the fairness of each message that never moves.

## Draw the chart

```sh
S=features/skill-library/skills/statechart/scripts
cd features/home/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --project "../../../$S" \
    statechart from-spec HomeTreeToday.tla --png
```

It writes `HomeTreeToday-statechart/`: `chart.mmd` and `chart.png`, `stories.md` and `summary.json`.
Today's code breaks no rule, so it draws no `bug-N` chart and `stories.md` is empty.
Its `tlc/` folder holds TLC's output, which is not committed.
The chart's scene, in `HomeTreeToday.cfg`, is child a alone with one call, a home thread that never fails, K at 1, and no guard dropped.
TLC 2.19 fails in a run of one worker with `-continue` once a rule breaks in some thousands of states, and the statechart command runs one worker, so the chart's scene is small.
The home thread never fails in the chart's scene, and can fail in the scenes `a` and `b` of `canaries.py`.
With it able to fail, the chart's scene has 4002 states and not 1334, and Mermaid's PNG of it comes out mostly blank.
The chart draws only the rules that are invariants.
A ready pull request that never merges (`ReadyMerges`) is a property, and today's code keeps it since pull request 357 let jbus merge a child's pull request, which the chart draws as a step of today's code.
Stranding (`CallsReachJosh`) is a property too, and today's code keeps it: jbus has one route to Josh, the home thread, and a post to it that fails leaves the call in its outbox.
The merge race (`NoBlindMerge`) needs two pull requests, so it is in the siblings' run of `canaries.py` and not in the chart.

## The four rules today's code broke

Until the branch hometree-rules, today's code broke four rules, each along a story of the chart.
Each now holds by the guard the design names for it, and a test in `features/home/tests/test_home_tree_spec.py` drives the real code along that story and fails on the code before it.

1. `RetireHandsOver`, by the hand-over: the handoff skill archives a scope whatever it has out, starts no home after it, and removes its `home-id` and moves its plan out, so what `jbus out --scope <scope>` printed for it is the root home's (`jbriefs/home.py`, `jbus/children.py`).
   The test is `test_retire_hands_over_a_child_archived_with_its_crew_out_leaves_it_to_the_root`, where the handoff archives the scope while a crew jbus launched for it is out, and the crew's brief is the root home's from then on.
2. `StallFlagged`, with `FirstStrike`, `NudgesBounded` and `AsksAfterTwo`, by the root's watch of its children: a jbus pass nudges a child that has been quiet for its patience with work out, tells the user at once, nudges it once more and then asks the user (`jbus/children.py`, `watch`).
   The test is `test_stall_flagged_a_quiet_child_with_its_crew_out_is_flagged`, where real jbus passes nudge the child's home thread an hour after its crew stopped, and the user hears of it.
3. `OneMerger`, by jbus as the only merger: jbus runs `jmerge` whatever `home-thread` holds, and a home's `jmerge --home` merges nothing (`jbus/merge.py`, `jmerge/cli.py`).
   The test is `test_one_merger_no_home_merges_and_jbus_merges_child_a_s_pull_request`, where with an id in `home-thread` neither the root's run nor child a's merges, and jbus's merges child a's pull request.
4. `NoBlindMerge`, by the merge lock: a run of `jmerge` holds `$H/merge.lock` from its read of main's tip to its merge (`jmerge/lock.py`).
   It breaks only in the siblings' scene, so no story of the chart has it.
   The test is `test_no_blind_merge_a_second_run_merges_nothing_while_one_is_merging`, where a second run started in the middle of the first one's merge merges nothing.

## What the model leaves out

- A third child.
- What one home leaves for another: a queued row `--for` that home, the user's word the root carries to a scope by `jbus word --scope`, and `jbus stop`, by which a scoped home reaches the root (#553, #567, #578).
- A pull request that stops being ready a second time, and a push to main by anything but a merge.
- The crew's own stalls, which the crew skill and jbus's waits cover.
