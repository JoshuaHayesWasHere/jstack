---- MODULE GreenMove ----
\* A move of the green copy, as `jbus.green` takes it: `_advance` grows the new tip's tree and
\* writes the step it owes to green.json, `_settle` points the link, installs the tool, removes old
\* trees and relinks the harness layouts, and `_resume` takes up an owed step on the next pass,
\* before `_advance` reads main.json. A pass can die between any two steps (a timeout, a reboot,
\* an OOM kill): the disk keeps what it wrote, and the next pass starts at `move`'s top.
\* Tips are 0..MaxTip, and main's green tip only moves forward (`mainjson`).
\* Fault = "none" is the code; Fault = "no-owed" is the canary: green.json keeps no step, as
\* before st-green-step, so nothing owes the rest of a move a pass did not finish; Fault =
\* "no-back" is the canary of a move that goes back as before st-green-back: it owes a relink and
\* no install of the tree it went back to, and keeps the reload it wrote for the tip it removed.
EXTENDS Naturals
CONSTANTS MaxTip, Fault

Nothing == MaxTip + 1  \* no tool on disk, or no reload owed

VARIABLES
  green,    \* main.json's green tip
  link,     \* the tree the link `green` names (`at(copy)`)
  tool,     \* the tree uv's editable install of the tool names (`_reinstall`), or Nothing
  layouts,  \* the tree the harness layouts were last put from (`relink`)
  trees,    \* the trees green.d/<sha> on disk
  pc,       \* where the pass that runs the move is
  to,       \* green.json's move: `to`
  from,     \* green.json's move: `from`
  owed,     \* green.json's move: `owes`, or "none" where green.json keeps no move
  gone,     \* the tree a move whose install failed removes
  removed,  \* the tips whose move failed and went back, so that never became the copy
  reload,   \* green.json's `at`: the tip whose units systemd owes a reload, or Nothing
  was       \* green.json's move: `was`, the reload owed before the move
vars == <<green, link, tool, layouts, trees, pc, to, from, owed, gone, removed, reload, was>>
rest == <<removed, reload, was>>

Kept(step) == IF Fault = "no-owed" THEN "none" ELSE step

TypeOK ==
  /\ {green, link, layouts, to, from, gone} \subseteq 0..MaxTip
  /\ {tool, reload, was} \subseteq 0..Nothing
  /\ trees \subseteq 0..MaxTip /\ removed \subseteq 0..MaxTip
  /\ pc \in {"idle", "owed", "pointed", "failed", "back", "removing", "installed", "cleaned"}
  /\ owed \in {"none", "install", "relink"}

Init ==
  /\ green = 0 /\ link = 0 /\ tool = 0 /\ layouts = 0 /\ trees = {0}
  /\ pc = "idle" /\ to = 0 /\ from = 0 /\ owed = "none" /\ gone = 0
  /\ removed = {} /\ reload = Nothing /\ was = Nothing

MainGoesGreen ==
  /\ green < MaxTip /\ green' = green + 1
  /\ UNCHANGED <<link, tool, layouts, trees, pc, to, from, owed, gone, removed, reload, was>>

\* `_advance`: `if (owed := in_flight(run.state)) is not None and owed["owes"] == "install":
\* return`, `if not green or not held or green in (held, refused): return`, `_grow`, and
\* `write_json(run.state / FILE, owes)` with `"owes": "install"` and `"was": was`, and with
\* `"at": green` where the tip changed a unit or systemd links one into the tree it leaves,
\* before `_settle` points the link.
Advance ==
  /\ pc = "idle" /\ owed \in {"none", "relink"} /\ green /= link
  /\ trees' = trees \cup {green} /\ to' = green /\ from' = link
  /\ owed' = Kept("install") /\ pc' = "owed"
  /\ was' = reload /\ reload' \in {reload, green} /\ removed' = removed \ {green}
  /\ UNCHANGED <<green, link, tool, layouts, gone>>

\* `_settle`: `_point(copy, tree)`
Point ==
  /\ pc = "owed" /\ link' = to /\ pc' = "pointed"
  /\ UNCHANGED <<green, tool, layouts, trees, to, from, owed, gone>> /\ UNCHANGED rest

\* `if why := _reinstall(copy):` ... else `owed = {**owed, "owes": "relink"}` and its write. uv's
\* install and the write that follows it are one step here (see the README). uv removes the
\* tool before it builds the new one, so an install that fails may leave none. A move back
\* whose install fails stays owed: `if green != held: _back(run, copy, owed)`, `return`.
Install ==
  /\ pc = "pointed"
  /\ \/ /\ tool' = link /\ owed' = Kept("relink") /\ pc' = "installed"
        /\ UNCHANGED <<link, from, to>>
     \/ /\ tool' \in {tool, Nothing} /\ pc' = IF to = from THEN "idle" ELSE "failed"
        /\ UNCHANGED <<link, owed, from, to>>
  /\ UNCHANGED <<green, layouts, trees, gone>> /\ UNCHANGED rest

\* uv could not install it: `_back` writes that the move owes the install of the tree it went
\* back to, `back = {"to": held, "from": held, "owes": "install"}`, with `**was` in place of the
\* reload it wrote for the tip it leaves.
Back ==
  /\ pc = "failed" /\ gone' = to /\ to' = from /\ pc' = "back"
  /\ removed' = removed \cup {to}
  /\ IF Fault = "no-back"
       THEN owed' = "relink" /\ reload' = reload
       ELSE owed' = Kept("install") /\ reload' = was
  /\ UNCHANGED <<green, link, tool, layouts, trees, from, was>>

\* Then `_point(copy, before)`.
PointBack ==
  /\ pc = "back" /\ link' = from /\ pc' = "removing"
  /\ UNCHANGED <<green, tool, layouts, trees, to, from, owed, gone>> /\ UNCHANGED rest

\* Then `shutil.rmtree(trees(copy) / owed["to"], ignore_errors=True)` and `_settle(run, copy,
\* back)`, which points the link at the tree it went back to and installs the tool from it.
Remove ==
  /\ pc = "removing" /\ trees' = trees \ {gone}
  /\ pc' = IF Fault = "no-back" THEN "idle" ELSE "owed"
  /\ UNCHANGED <<green, link, tool, layouts, to, from, owed, gone>> /\ UNCHANGED rest

\* `for old in trees(copy).iterdir(): if ... old.resolve() not in (before.resolve(), tree.resolve())`
Clean ==
  /\ pc = "installed" /\ trees' = trees \cap {from, to} /\ pc' = "cleaned"
  /\ UNCHANGED <<green, link, tool, layouts, to, from, owed, gone>> /\ UNCHANGED rest

\* `faults = relink(copy)`; `if not faults: _drop(run)`: a refused relink keeps the step owed.
Relink ==
  /\ pc = "cleaned"
  /\ \/ /\ layouts' = link /\ owed' = "none"
     \/ /\ UNCHANGED <<layouts, owed>>
  /\ pc' = "idle"
  /\ UNCHANGED <<green, link, tool, trees, to, from, gone>> /\ UNCHANGED rest

\* The pass dies, and the next one starts at `move`'s top.
Die ==
  /\ pc /= "idle" /\ pc' = "idle"
  /\ UNCHANGED <<green, link, tool, layouts, trees, to, from, owed, gone>> /\ UNCHANGED rest

\* `_resume`, before `_advance` reads main.json: an owed install points the link again and
\* installs, an owed relink cleans and relinks again.
Resume ==
  /\ pc = "idle" /\ owed /= "none"
  /\ pc' = IF owed = "install" THEN "owed" ELSE "installed"
  /\ UNCHANGED <<green, link, tool, layouts, trees, to, from, owed, gone>> /\ UNCHANGED rest

\* `reload`, at the end of a pass: `systemctl --user daemon-reload` for the tip green.json keeps,
\* and `write_json` without `at` once systemd took it, or the debt kept where it refused.
Reload ==
  /\ pc = "idle" /\ reload /= Nothing /\ reload' = Nothing
  /\ UNCHANGED <<green, link, tool, layouts, trees, pc, to, from, owed, gone, removed, was>>

Next ==
  \/ MainGoesGreen \/ Advance \/ Point \/ Install \/ PointBack \/ Back
  \/ Remove \/ Clean \/ Relink \/ Die \/ Resume \/ Reload
Spec == Init /\ [][Next]_vars

\* No pass is in a move and green.json owes no step: the tool runs the tree the link names.
ToolRunsCopy == (pc = "idle" /\ owed = "none") => tool = link
\* The tree the tool runs, where uv left one, is on disk.
ToolTreeThere == tool = Nothing \/ tool \in trees
\* No pass is in a move and none is owed: the harness layouts were put from the tree the link
\* names, also after a move whose install failed went back.
LayoutsFollow == (pc = "idle" /\ owed = "none") => layouts = link
\* No reload is owed for a tip whose move went back, so none runs for a tip that never became the
\* copy.
NoReloadForRemoved == reload \notin removed
====
