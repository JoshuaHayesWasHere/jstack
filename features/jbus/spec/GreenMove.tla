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
\* no install of the tree it went back to, and keeps the reload it wrote for the tip it removed;
\* Fault = "no-import" moves to a tip without importing its commands first; Fault =
\* "stamp-refused" stamps `live` where the manager refused a step of the units.
\* Each cite of jbus/green.py quotes the code in backticks with no line number, and
\* features/jbus/tests/test_spec_quotes.py finds each such quote once in today's code.
EXTENDS Naturals
CONSTANTS MaxTip, Fault
\* The tips of main that do not import (`IMPORTS`) in their own tree: their check passed, and the
\* copy's commands fail to load there.
CONSTANT Broken

Nothing == MaxTip + 1  \* no tool on disk, or no reload owed

VARIABLES
  green,    \* main.json's green tip. main.json's other fields (main, at, check, broken, pending,
            \* failed) are MainRed's; this model reads only `green`
            \* (jbus/green.py `green = mainjson.read(run.state).green`).
  link,     \* the tree the link `green` names (`at(copy)`)
  tool,     \* the tree uv's editable install of the tool names (`_reinstall`), or Nothing
  layouts,  \* the tree the harness layouts were last put from (`relink`)
  trees,    \* the trees green.d/<sha> on disk, each with its jstack-checkout marker, the checkout
            \* it was made from, which jbus/green.py `(copy / ".git" / MARK).write_text(f"{checkout}\n")`
            \* writes as the first file of a new tree, and which `owner` reads through the link
            \* (jbus/green.py `named = (copy / ".git" / MARK).read_text().strip()`), or through the
            \* tree the move in flight came from where the link names a tree that is gone
            \* (jbus/green.py `made_from = of(trees(copy) / owed["from"])`). A tree whose fill
            \* failed after git init and before the marker is removed in the same step
            \* (`_grow`), so every tree here holds its marker.
  pc,       \* where the pass that runs the move is
  to,       \* green.json's move: `to`
  from,     \* green.json's move: `from`
  owed,     \* green.json's move: `owes`, or "none" where green.json keeps no move
  gone,     \* the tree a move whose install failed removes
  removed,  \* the tips whose move failed and went back, so that never became the copy
  reload,   \* green.json's `at`: the tip whose units systemd owes a reload, or Nothing. Its
            \* `reload` list, the unit files whose content changed, only names which timers the
            \* reload restarts, so it is not modeled: it is written and cleared with `at`.
  was,      \* green.json's move: `was`, the reload owed before the move
  refused,  \* green.json's `refused`: the tip that did not import, which no later pass tries
            \* again (jbus/green.py `write_json(run.state / FILE, {**record, "refused": green})`),
            \* or Nothing
  live,     \* green.json's `live`: the tip whose units the manager took every step for, stamped
            \* after them (jbus/green.py `write_json(run.state / FILE, {**read_json(run.state / FILE, {}), "live": held})`),
            \* or Nothing
  took      \* the systemd user units: the tip whose units the manager last linked, enabled,
            \* started and restarted with no step refused (jinstall.green.live). The transient
            \* units jbus starts (jbus-jmerge-*, jbus-scorecard-*) are the merge run's and the
            \* scorecard's, not the copy's, and are not modeled.
vars == <<green, link, tool, layouts, trees, pc, to, from, owed, gone, removed, reload, was,
          refused, live, took>>
rest == <<removed, reload, was>>
marks == <<refused, live, took>>

Kept(step) == IF Fault = "no-owed" THEN "none" ELSE step

TypeOK ==
  /\ {green, link, layouts, to, from, gone} \subseteq 0..MaxTip
  /\ {tool, reload, was, refused, live, took} \subseteq 0..Nothing
  /\ Broken \subseteq 1..MaxTip
  /\ trees \subseteq 0..MaxTip /\ removed \subseteq 0..MaxTip
  /\ pc \in {"idle", "owed", "pointed", "failed", "back", "removing", "installed", "cleaned"}
  /\ owed \in {"none", "install", "relink"}

Init ==
  /\ green = 0 /\ link = 0 /\ tool = 0 /\ layouts = 0 /\ trees = {0}
  /\ pc = "idle" /\ to = 0 /\ from = 0 /\ owed = "none" /\ gone = 0
  /\ removed = {} /\ reload = Nothing /\ was = Nothing
  \* install.sh put tip 0's units to work and stamped nothing, so the first pass puts them again.
  /\ refused = Nothing /\ live = Nothing /\ took = 0

MainGoesGreen ==
  /\ green < MaxTip /\ green' = green + 1
  /\ UNCHANGED <<link, tool, layouts, trees, pc, to, from, owed, gone, removed, reload, was>>
  /\ UNCHANGED marks

\* `_advance` skips the tip the copy holds and the one it refused (jbus/green.py
\* `if not green or not held or green in (held, refused):`).
Fresh ==
  /\ pc = "idle" /\ (owed \in {"none", "relink"} \/ (owed = "install" /\ to = from))
  /\ green /= link /\ green /= refused

\* A tip whose commands do not import is removed and kept as `refused`, and the copy stays
\* (jbus/green.py `if broke := imports(tree, fresh=changed):`). Its tree is grown and removed in
\* the one step: a pass that dies between them leaves a tree the next move's clean removes.
Refuse ==
  /\ Fresh /\ green \in Broken /\ Fault /= "no-import"
  /\ refused' = green
  /\ UNCHANGED <<green, link, tool, layouts, trees, pc, to, from, owed, gone, live, took>>
  /\ UNCHANGED rest

\* `_advance`, after `_resume`, which settles an owed install to a new tip or sends it back, so
\* the install it may still owe is one back (to = from), which it takes over: `if not green or not
\* held or green in (held, refused): return`, `_grow`, and `write_json(run.state / FILE, owes)`
\* with `"owes": "install"` and `"was": was`, and with `"at": green` where the tip changed a unit
\* or systemd links one into the tree it leaves, before `_settle` points the link.
Advance ==
  /\ Fresh /\ (green \notin Broken \/ Fault = "no-import")
  /\ trees' = trees \cup {green} /\ to' = green /\ from' = link
  /\ owed' = Kept("install") /\ pc' = "owed"
  /\ was' = reload /\ reload' \in {reload, green} /\ removed' = removed \ {green}
  /\ UNCHANGED <<green, link, tool, layouts, gone>> /\ UNCHANGED marks

\* `_settle`: `_point(copy, tree)`
Point ==
  /\ pc = "owed" /\ link' = to /\ pc' = "pointed"
  /\ UNCHANGED <<green, tool, layouts, trees, to, from, owed, gone>> /\ UNCHANGED rest /\ UNCHANGED marks

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
  /\ UNCHANGED <<green, layouts, trees, gone>> /\ UNCHANGED rest /\ UNCHANGED marks

\* uv could not install it: `_back` writes that the move owes the install of the tree it went
\* back to, `back = {"to": held, "from": held, "owes": "install"}`, with `**was` in place of the
\* reload it wrote for the tip it leaves.
Back ==
  /\ pc = "failed" /\ gone' = to /\ to' = from /\ pc' = "back"
  /\ removed' = removed \cup {to}
  /\ IF Fault = "no-back"
       THEN owed' = "relink" /\ reload' = reload
       ELSE owed' = Kept("install") /\ reload' = was
  /\ UNCHANGED <<green, link, tool, layouts, trees, from, was>> /\ UNCHANGED marks

\* Then `_point(copy, before)`.
PointBack ==
  /\ pc = "back" /\ link' = from /\ pc' = "removing"
  /\ UNCHANGED <<green, tool, layouts, trees, to, from, owed, gone>> /\ UNCHANGED rest /\ UNCHANGED marks

\* Then `shutil.rmtree(trees(copy) / owed["to"], ignore_errors=True)` and `_settle(run, copy,
\* back)`, which points the link at the tree it went back to and installs the tool from it.
Remove ==
  /\ pc = "removing" /\ trees' = trees \ {gone}
  /\ pc' = IF Fault = "no-back" THEN "idle" ELSE "owed"
  /\ UNCHANGED <<green, link, tool, layouts, to, from, owed, gone>> /\ UNCHANGED rest /\ UNCHANGED marks

\* `for old in trees(copy).iterdir(): if ... old.resolve() not in (before.resolve(), tree.resolve())`
Clean ==
  /\ pc = "installed" /\ trees' = trees \cap {from, to} /\ pc' = "cleaned"
  /\ UNCHANGED <<green, link, tool, layouts, to, from, owed, gone>> /\ UNCHANGED rest /\ UNCHANGED marks

\* `faults = relink(copy)`; `if not faults: _drop(run)`: a refused relink keeps the step owed.
Relink ==
  /\ pc = "cleaned"
  /\ \/ /\ layouts' = link /\ owed' = "none"
     \/ /\ UNCHANGED <<layouts, owed>>
  /\ pc' = "idle"
  /\ UNCHANGED <<green, link, tool, trees, to, from, gone>> /\ UNCHANGED rest /\ UNCHANGED marks

\* The pass dies, and the next one starts at `move`'s top.
Die ==
  /\ pc /= "idle" /\ pc' = "idle"
  /\ UNCHANGED <<green, link, tool, layouts, trees, to, from, owed, gone>> /\ UNCHANGED rest /\ UNCHANGED marks

\* `_resume`, before `_advance` reads main.json: an owed install points the link again and
\* installs, an owed relink cleans and relinks again.
Resume ==
  /\ pc = "idle" /\ owed /= "none"
  /\ pc' = IF owed = "install" THEN "owed" ELSE "installed"
  /\ UNCHANGED <<green, link, tool, layouts, trees, to, from, owed, gone>> /\ UNCHANGED rest /\ UNCHANGED marks

\* `reload`, at the end of a pass: `systemctl --user daemon-reload` for the tip green.json keeps,
\* and `write_json` without `at` once systemd took it, or the debt kept where it refused.
Reload ==
  /\ pc = "idle" /\ reload /= Nothing /\ reload' = Nothing
  /\ UNCHANGED <<green, link, tool, layouts, trees, pc, to, from, owed, gone, removed, was>>
  /\ UNCHANGED marks

\* `_live`, after `_advance` in each pass: put the units of the tip the link names to work
\* unless `live` is stamped with it (jbus/green.py `if not held or record.get("live") == held:`).
\* The manager takes every step and `live` is stamped, or it refuses one, which raises a
\* condition and stamps nothing (jbus/green.py
\* `run.condition("green", UNSTARTED, f"at {held[:12]}: {why}", key=held[:12])`), so the next
\* pass asks again. The units it added before the refusal stay, which `took` does not tell
\* apart from none, since the next call adds what is missing. A pass that dies after the
\* manager took them and before the stamp calls `live` again, which finds each unit there.
Live ==
  /\ pc = "idle" /\ live /= link
  /\ \/ took' = link /\ live' = link
     \/ took' = took /\ live' = IF Fault = "stamp-refused" THEN link ELSE live
  /\ UNCHANGED <<green, link, tool, layouts, trees, pc, to, from, owed, gone, refused>>
  /\ UNCHANGED rest

Next ==
  \/ MainGoesGreen \/ Refuse \/ Advance \/ Point \/ Install \/ PointBack \/ Back
  \/ Remove \/ Clean \/ Relink \/ Die \/ Resume \/ Reload \/ Live
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
\* The copy never runs a tip whose commands do not import: a main whose check passed and that
\* breaks jbus here does not reach the commands that revert or fix it.
CopyImports == link \notin Broken
\* `live` names only a tip whose units the manager took every step for, so a refused step is
\* asked again on the next pass and not left for good.
StampTrue == live \in {Nothing, took}
\* The link names a tree on disk, whose marker names the checkout, so `owner` finds the project
\* that moves the copy at each pass's start.
CopyOwned == link \in trees
====
