# A crew thread, as a TLA+ spec

`ThreadLife.tla` follows one crew thread of one row through jbus's code, last read against it at 228c1436c (2026-11-11).
It starts at the launch record a pass writes (`jbus/dispatch.py`), and goes through the words `jbus/live.py` gives the thread's turn and the carry-ons `jbus/threads.py` `resume` sends.
It ends with the thread put away and its scratch cleared (`jbus/threads.py` `settle`), or with the row its home's: jbus told the home.
Each condition of a step names the file that checks it and quotes the code there, with no line number.
`features/jbus/tests/test_spec_quotes.py` finds the one place each quote stands, in this spec, `RowLife.tla` and `GreenMove.tla`, so a move of the lines leaves no cite to renumber.
`features/jbus/tests/test_thread_life_spec.py` runs TLC on today's code and on each canary.

## Check the rules of the thread

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -config ThreadLife.cfg ThreadLife.tla
```

TLC writes a `states/` folder where it runs, so run it in a copy of this folder.
Today's code holds every rule, in 45694 distinct states:

- `ThreadEnds`, "a thread ends archived or with its home told": every thread jbus holds, one its launch record names, is archived in the end, or jbus told its home that the row is the home's, or, with no home thread to tell, `leftover.json` made it yours (`why`).
- `LineFollows`: the brief's `Thread:` line names the crew thread jbus holds, as `crewthread.move` writes it after the record, or the next pass's `crewthread.repair` does when the pass died between the two.
- `ScratchGoes`: a thread put away, settled or archived, has its scratch cleared.
- `CarryOnsBounded`: jbus sends a thread at most two carry-ons.
- `ArchivesFinished`: jbus archives only a finished slug's thread, and only once its turn is over.

A home is told in one of three ways:

- `_stopped`: a turn that failed with no Result, after two carry-ons.
- `leftover.tell`: a Result that leaves something, or a turn that completed or hung with nothing written.
- The stall ladder of `jbus/children.py`: a home with a row out whose crew writes nothing is nudged.

The canary `Drop = "ladder"` takes the stall ladder out, and `ThreadEnds` breaks.
The canary `Drop = "repair"` takes the next pass's repair out, and `LineFollows` breaks: the brief names no crew for good.
The test runs each canary on a cfg with its own rule alone.
In its shortest story the crew asks you something and its request waits.
The ladder also carries a crew that jbus told once to open the pull request its Result owes, if that crew ends again with nothing new written.
`resume` sends that tell once for the thread, `finished` leaves a slug that owes out, and `leftover` counts an owing Result as nothing written while its thread is quiet.

## Draw the chart of the thread

```sh
S=../../skill-library/skills/statechart/scripts
cd features/jbus/spec
UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec ThreadLife.tla --title "What does jbus do with a thread, launch to archive?"
```

It writes `ThreadLife-statechart/`: `chart.mmd`, `stories.md` and `summary.json`, with labels from `ThreadLife.map.py`.
Its `tlc/` folder holds TLC's output, which is not committed.
The chart has two regions: who has the thread (launching, gated, out, its home's, put away), and where it stands.
No state breaks a rule, so it draws no `bug-N` chart.

## What the thread model leaves out

- The home's thread: the model takes it as there and quiet in the end.
  With no home thread, `_stopped` and `leftover` make the row a gate of yours, and the catch-all's home is started again by `children.keep_alive`.
  A home that keeps writing restarts its stall spell.
- A thread made by a lost launch that the lookup does not find: that is a gate of yours, and jbus holds no thread for it.
- A settled thread that a message wakes (a paused crew's carry-on is modeled only for a thread still out), a row removed from the queue, and the `MERGED` message to a crew whose Result leaves work for after the merge.
- The folds `ThreadLife.tla` names beside each variable: the turns T3 Code reports that act as another (preparing, idle, interrupted, cancelled, unknown), the Results that read as a leftover (malformed, not done, blocked), and `leftover.json`'s `busy`, which the pass rewrites and no rule reads.
- Reviewers, and failover to another instance.
  A scout's launch record is the crew's record with fewer fields (`rec`).
