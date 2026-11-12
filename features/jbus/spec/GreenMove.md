# The green move, as a TLA+ spec

`GreenMove.tla` follows one green copy (`jbus/green.py`) as passes move it to main's green tip, with a pass that can die between any two steps.
A move grows the new tip's tree, writes the step it owes to `green.json` (`move`, `owes: install`), points the link, installs the tool again, writes `owes: relink`, removes the trees no command runs, and puts the harness layouts again (`jinstall.green.relink`), and only a relink that is taken drops `move`.
Each pass resumes an owed step (`_resume`) before `_advance` reads main.json.
An install uv refuses, which may have removed the tool first, sends the move back: it owes the install of the tree it came from, with the reload systemd was owed before it, points the link back, removes the new tree, and installs the tool and relinks from the tree it went back to.
An install back that uv refuses too stays owed, and a newer green tip still starts a move that takes it over (`Advance`), so a tree uv never installs again does not hold the copy.
A tip that does not import is refused (`Refuse`), and no move starts to it; at idle, the pass puts the units a move took on to work and stamps `green.json`'s `live` (`Live`).
Each step's comment quotes the code it stands for, and `features/jbus/tests/test_spec_quotes.py` finds each quote once in today's code.

## Check the rules of the green move

```sh
cd features/jbus/spec
java -cp ~/.cache/jstack/tla2tools/1.7.4/tla2tools.jar tlc2.TLC -deadlock -config GreenMove.cfg GreenMove.tla
```

Run it in a copy of this folder, since TLC writes `states/` where it runs.
`-deadlock` is there because a copy at main's last tip has no step left to take.
Today's code holds every rule, over 11614 distinct states with MaxTip 3 and tip 2 one that does not import (`Broken = {2}`):

- `ToolRunsCopy`: once no pass is in a move and none is owed, the tool runs the tree the link names, so a unit never starts on a tool the copy no longer holds.
- `ToolTreeThere`: the tree the tool runs, where uv left one, is on disk.
- `LayoutsFollow`: once no pass is in a move and none is owed, the layouts were put from the tree the link names, also after a move whose install failed went back.
- `NoReloadForRemoved`: `green.json` owes systemd no reload for a tip whose move went back, so none runs for a tip that never became the copy.
- `CopyImports`: the link never names a tip that does not import, since `_advance` imports the tip first and refuses it.
- `StampTrue`: `live` names no tip whose units the manager did not take, so the stamp is true or not there.
- `CopyOwned`: the link names a tree on disk, whose `jstack-checkout` marker `owner` reads.

The canary, `Fault = "no-owed"`, keeps no step in `green.json`, as the code did before st-green-step.
`ToolRunsCopy` and `LayoutsFollow` each break in five states: main goes green, the move points the link, and the pass dies, the journal's 203/EXEC on `~/.local/bin/jbus`.
The second canary, `Fault = "no-back"`, goes back as the code did before st-green-back: it owes a relink and no install of the tree it went back to, and keeps the reload it wrote for the tip it removed.
`ToolRunsCopy` breaks when the failed install removed the tool, and `NoReloadForRemoved` breaks once the move goes back.
The canary `Fault = "no-import"` moves to a tip that does not import, and `CopyImports` breaks.
The canary `Fault = "stamp-refused"` stamps `live` over units the manager refused, and `StampTrue` breaks.
`CopyOwned` has no canary: in the model the link always names a tree that is there, and a tree a hand removed takes the fallback.
`features/jbus/tests/test_green_move_spec.py` runs TLC on the config and on each canary for the rules it breaks.

## Draw the chart of the green move

```sh
S=$PWD/features/skill-library/skills/statechart/scripts
D=$HOME/.cache/jstack/tlc-tmp && mkdir -p "$D"
W=$(TMPDIR=$D mktemp -d) && cp features/jbus/spec/GreenMove.* "$W"
(cd "$W" && TMPDIR=$D UV_PROJECT_ENVIRONMENT="$HOME/.cache/jstack/statechart-venv" uv run --frozen --exact --project "$S" \
    statechart from-spec GreenMove.tla --title "Does the green copy reach main's green tip?" --out out)
```

Run it from the repo root, then copy the files of `$W/out` into `GreenMove-statechart/`, all except `tlc/`.
`GreenMove.cfg` turns off TLC's deadlock check, as `-deadlock` does above, since a copy at main's last tip has no step left.
`GreenMove.map.py` labels each state with the step of the move the pass is at and what a command you run meets: the tool the link names, another tree, or none.
It draws 26 chart states and 60 steps from 11,614 model states, every step between two of them, in a few seconds.

## What the green-move model leaves out

- uv's install and the write of `owes: relink` after it are one step: a pass that dies between them installs again, which is the same install, and the model does not let that second install fail.
- Which units a move puts to work: `took` is the tip whose units the manager took, all or none, and the transient units are left out.
- Of the reload a move owes systemd (`reload`, `at`), only `at` and whether systemd takes it.
- A tree a move went to that is gone on resume, which only a hand can remove: `_resume` goes back (`_back`) as a failed install does.
