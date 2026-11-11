---- MODULE GreenMove ----
\* A move of the green copy, as `jbus.green` takes it: `_advance` grows the new tip's tree and
\* writes the step it owes to green.json, `_settle` points the link, installs the tool, removes old
\* trees and relinks the harness layouts, and `_resume` takes up an owed step on the next pass,
\* before `_advance` reads main.json. A pass can die between any two steps (a timeout, a reboot,
\* an OOM kill): the disk keeps what it wrote, and the next pass starts at `move`'s top.
\* Tips are 0..MaxTip, and main's green tip only moves forward (`mainjson`).
\* Fault = "none" is the code; Fault = "no-owed" is the canary: green.json keeps no step, as
\* before st-green-step, so nothing owes the rest of a move a pass did not finish.
EXTENDS Naturals
CONSTANTS MaxTip, Fault

VARIABLES
  green,    \* main.json's green tip
  link,     \* the tree the link `green` names (`at(copy)`)
  tool,     \* the tree uv's editable install of the tool names (`_reinstall`)
  layouts,  \* the tree the harness layouts were last put from (`relink`)
  trees,    \* the trees green.d/<sha> on disk
  pc,       \* where the pass that runs the move is
  to,       \* green.json's move: `to`
  from,     \* green.json's move: `from`
  owed,     \* green.json's move: `owes`, or "none" where green.json keeps no move
  gone      \* the tree a move whose install failed removes
vars == <<green, link, tool, layouts, trees, pc, to, from, owed, gone>>

Kept(step) == IF Fault = "none" THEN step ELSE "none"

TypeOK ==
  /\ {green, link, tool, layouts, to, from, gone} \subseteq 0..MaxTip
  /\ trees \subseteq 0..MaxTip
  /\ pc \in {"idle", "owed", "pointed", "failed", "back", "removing", "installed", "cleaned"}
  /\ owed \in {"none", "install", "relink"}

Init ==
  /\ green = 0 /\ link = 0 /\ tool = 0 /\ layouts = 0 /\ trees = {0}
  /\ pc = "idle" /\ to = 0 /\ from = 0 /\ owed = "none" /\ gone = 0

MainGoesGreen ==
  /\ green < MaxTip /\ green' = green + 1
  /\ UNCHANGED <<link, tool, layouts, trees, pc, to, from, owed, gone>>

\* `_advance`: `if owed is not None and owed["owes"] != "relink": return`, then
\* `if not green or not held or green in (held, refused): return`, `_grow`, and
\* `write_json(run.state / FILE, owes)` with `"owes": "install"`, before `_settle` points the link.
Advance ==
  /\ pc = "idle" /\ owed \in {"none", "relink"} /\ green /= link
  /\ trees' = trees \cup {green} /\ to' = green /\ from' = link
  /\ owed' = Kept("install") /\ pc' = "owed"
  /\ UNCHANGED <<green, link, tool, layouts, gone>>

\* `_settle`: `_point(copy, tree)`
Point ==
  /\ pc = "owed" /\ link' = to /\ pc' = "pointed"
  /\ UNCHANGED <<green, tool, layouts, trees, to, from, owed, gone>>

\* `if why := _reinstall(copy):` ... else `owed = {**owed, "owes": "relink"}` and its write. uv's
\* install and the write that follows it are one step here (see the README).
Install ==
  /\ pc = "pointed"
  /\ \/ /\ tool' = link /\ owed' = Kept("relink") /\ pc' = "installed"
        /\ UNCHANGED <<link, from, to>>
     \/ /\ pc' = "failed" /\ UNCHANGED <<link, tool, owed, from, to>>
  /\ UNCHANGED <<green, layouts, trees, gone>>

\* uv could not install it: `_point(copy, before)`.
PointBack ==
  /\ pc = "failed" /\ link' = from /\ pc' = "back"
  /\ UNCHANGED <<green, tool, layouts, trees, to, from, owed, gone>>

\* Then `_back(run, held)` writes that the move owes a relink of the tree it went back to, which
\* the move it took over may have owed.
Back ==
  /\ pc = "back" /\ gone' = to /\ to' = from /\ owed' = Kept("relink") /\ pc' = "removing"
  /\ UNCHANGED <<green, link, tool, layouts, trees, from>>

\* Then `shutil.rmtree(tree)`.
Remove ==
  /\ pc = "removing" /\ trees' = trees \ {gone} /\ pc' = "idle"
  /\ UNCHANGED <<green, link, tool, layouts, to, from, owed, gone>>

\* `for old in trees(copy).iterdir(): if ... old.resolve() not in (before.resolve(), tree.resolve())`
Clean ==
  /\ pc = "installed" /\ trees' = trees \cap {from, to} /\ pc' = "cleaned"
  /\ UNCHANGED <<green, link, tool, layouts, to, from, owed, gone>>

\* `faults = relink(copy)`; `if not faults: _drop(run)`: a refused relink keeps the step owed.
Relink ==
  /\ pc = "cleaned"
  /\ \/ /\ layouts' = link /\ owed' = "none"
     \/ /\ UNCHANGED <<layouts, owed>>
  /\ pc' = "idle"
  /\ UNCHANGED <<green, link, tool, trees, to, from, gone>>

\* The pass dies, and the next one starts at `move`'s top.
Die ==
  /\ pc /= "idle" /\ pc' = "idle"
  /\ UNCHANGED <<green, link, tool, layouts, trees, to, from, owed, gone>>

\* `_resume`, before `_advance` reads main.json: an owed install points the link again and
\* installs, an owed relink cleans and relinks again.
Resume ==
  /\ pc = "idle" /\ owed /= "none"
  /\ pc' = IF owed = "install" THEN "owed" ELSE "installed"
  /\ UNCHANGED <<green, link, tool, layouts, trees, to, from, owed, gone>>

Next ==
  \/ MainGoesGreen \/ Advance \/ Point \/ Install \/ PointBack \/ Back
  \/ Remove \/ Clean \/ Relink \/ Die \/ Resume
Spec == Init /\ [][Next]_vars

\* No pass is in a move and green.json owes no step: the tool runs the tree the link names.
ToolRunsCopy == (pc = "idle" /\ owed = "none") => tool = link
\* The tree the tool runs is on disk.
ToolTreeThere == tool \in trees
\* No pass is in a move and none is owed: the harness layouts were put from the tree the link
\* names, also after a move whose install failed went back.
LayoutsFollow == (pc = "idle" /\ owed = "none") => layouts = link
====
