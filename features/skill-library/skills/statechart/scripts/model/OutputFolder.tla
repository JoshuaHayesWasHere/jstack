---- MODULE OutputFolder ----
EXTENDS Naturals

Runs == {1, 2}
NoRun == 0
NoFolder == [exists |-> FALSE, by |-> NoRun, read |-> {}, notes |-> FALSE]

\* unrendered[r]: --png could not render one of run r's charts, which it finds before it publishes.
VARIABLES pc, inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode, unrendered

vars == <<pc, inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

Init ==
  /\ pc = [r \in Runs |-> "idle"]
  /\ inputOk = [r \in Runs |-> TRUE]
  /\ snap = [r \in Runs |-> 0]
  /\ read = [r \in Runs |-> {}]
  /\ out = NoFolder
  /\ aside = [r \in Runs |-> NoFolder]
  /\ spec = 1
  /\ noted = FALSE
  /\ wrote = [r \in Runs |-> FALSE]
  /\ broke = [r \in Runs |-> FALSE]
  /\ exitCode = [r \in Runs |-> "none"]
  /\ unrendered = [r \in Runs |-> FALSE]

Set(f, r, v) == [f EXCEPT ![r] = v]
Going(r) == pc[r] \notin {"idle", "exited", "stopped", "orphanTlc"}
Go(r, to) == pc' = Set(pc, r, to)
Exit(r, code) == pc' = Set(pc, r, "exited") /\ exitCode' = Set(exitCode, r, code)

Start(r) ==
  /\ pc[r] = "idle"
  /\ r = 2 => pc[1] # "idle"
  /\ \E ok \in BOOLEAN : inputOk' = Set(inputOk, r, ok)
  /\ snap' = Set(snap, r, spec)
  /\ Go(r, "check")
  /\ UNCHANGED <<read, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

Refuse(r) ==
  /\ pc[r] = "check"
  /\ ~inputOk[r] \/ out.notes
  /\ Exit(r, "2")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, unrendered>>

Tlc(r) ==
  /\ \/ pc[r] = "check" /\ inputOk[r] /\ ~out.notes
     \/ pc[r] = "tlc"
  /\ read' = Set(read, r, read[r] \cup {spec})
  /\ Go(r, IF pc[r] = "check" THEN "tlc" ELSE "draw")
  /\ UNCHANGED <<inputOk, snap, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

Draw(r) ==
  /\ pc[r] = "draw"
  /\ Go(r, "publish")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

Stale(r) ==
  /\ pc[r] = "publish" /\ spec # snap[r]
  /\ Exit(r, "2")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, unrendered>>

Foreign(r) ==
  /\ pc[r] = "publish" /\ spec = snap[r] /\ out.notes
  /\ Exit(r, "2")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, unrendered>>

Swap(r) ==
  /\ pc[r] = "publish" /\ spec = snap[r] /\ ~out.notes
  /\ Go(r, "swap")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

MoveIn(r) ==
  /\ pc[r] = "swap" /\ ~out.exists
  /\ out' = [exists |-> TRUE, by |-> r, read |-> read[r], notes |-> FALSE]
  /\ wrote' = Set(wrote, r, TRUE)
  /\ Go(r, "clean")
  /\ UNCHANGED <<inputOk, snap, read, aside, spec, noted, broke, exitCode, unrendered>>

MoveAside(r) ==
  /\ pc[r] = "swap" /\ out.exists /\ ~aside[r].exists
  /\ aside' = Set(aside, r, out)
  /\ out' = NoFolder
  /\ Go(r, "aside")
  /\ UNCHANGED <<inputOk, snap, read, spec, noted, wrote, broke, exitCode, unrendered>>

Checked(r) ==
  /\ pc[r] = "aside" /\ ~aside[r].notes
  /\ Go(r, "swap")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

Supersede(r) ==
  /\ pc[r] = "swap" /\ out.exists /\ aside[r].exists /\ ~out.notes
  /\ aside' = Set(aside, r, NoFolder)
  /\ UNCHANGED <<pc, inputOk, snap, read, out, spec, noted, wrote, broke, exitCode, unrendered>>

Restore(r) ==
  /\ pc[r] = "aside" /\ aside[r].notes /\ ~out.exists
  /\ out' = aside[r]
  /\ aside' = Set(aside, r, NoFolder)
  /\ Exit(r, "2")
  /\ UNCHANGED <<inputOk, snap, read, spec, noted, wrote, broke, unrendered>>

KeepAside(r) ==
  /\ \/ pc[r] = "aside" /\ aside[r].notes /\ out.exists
     \/ pc[r] = "swap" /\ aside[r].exists /\ out.notes
  /\ Exit(r, "2")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, unrendered>>

RenameFails(r) ==
  /\ pc[r] \in {"swap", "aside"}
  /\ \/ /\ aside[r].exists /\ ~out.exists
        /\ out' = aside[r]
        /\ aside' = Set(aside, r, NoFolder)
     \/ UNCHANGED <<out, aside>>
  /\ broke' = Set(broke, r, TRUE)
  /\ Exit(r, "2")
  /\ UNCHANGED <<inputOk, snap, read, spec, noted, wrote, unrendered>>

\* --png renders the charts before the run publishes, and a chart it cannot render is found then.
RenderFails(r) ==
  /\ pc[r] = "publish" /\ ~unrendered[r]
  /\ unrendered' = Set(unrendered, r, TRUE)
  /\ UNCHANGED <<pc, inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode>>

\* A run that published exits 0, or 1 when the rules are not as expected, and 2 when a chart did not
\* render: it keeps what it wrote.
Clean(r) ==
  /\ pc[r] = "clean"
  /\ aside' = Set(aside, r, NoFolder)
  /\ \E code \in IF unrendered[r] THEN {"2"} ELSE {"0", "1"} : Exit(r, code)
  /\ UNCHANGED <<inputOk, snap, read, out, spec, noted, wrote, broke, unrendered>>

Stop(r) ==
  /\ Going(r)
  /\ Go(r, "stopped")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

KillPython(r) ==
  /\ pc[r] = "tlc"
  /\ Go(r, "orphanTlc")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

OrphanEnd(r) ==
  /\ pc[r] = "orphanTlc"
  /\ Go(r, "stopped")
  /\ UNCHANGED <<inputOk, snap, read, out, aside, spec, noted, wrote, broke, exitCode, unrendered>>

Edit ==
  /\ spec = 1
  /\ spec' = 2
  /\ UNCHANGED <<pc, inputOk, snap, read, out, aside, noted, wrote, broke, exitCode, unrendered>>

Note ==
  /\ ~noted
  /\ noted' = TRUE
  /\ out' = [out EXCEPT !.exists = TRUE, !.notes = TRUE]
  /\ UNCHANGED <<pc, inputOk, snap, read, aside, spec, wrote, broke, exitCode, unrendered>>

Next ==
  \/ Edit \/ Note
  \/ \E r \in Runs :
       Start(r) \/ Refuse(r) \/ Tlc(r) \/ Draw(r) \/ Stale(r) \/ Foreign(r) \/ Swap(r)
         \/ MoveIn(r) \/ MoveAside(r) \/ Checked(r) \/ Supersede(r) \/ Restore(r)
         \/ KeepAside(r) \/ RenameFails(r) \/ RenderFails(r) \/ Clean(r) \/ Stop(r) \/ KillPython(r)
         \/ OrphanEnd(r)

Spec == Init /\ [][Next]_vars

\* The folder never holds a chart drawn from two versions of the spec.
ChartsOneSpec == out.read \in {{}, {1}, {2}}

\* A file that you put in the folder is never deleted.
KeepsYourFiles == noted => out.notes \/ \E r \in Runs : aside[r].notes

\* Once a run writes a chart, the folder or a folder that a run moved aside always holds one.
NeverLosesChart ==
  (\E r \in Runs : wrote[r]) => out.by # NoRun \/ \E r \in Runs : aside[r].by # NoRun

\* A run that exits 2 did not write the folder, unless a chart did not render: then it keeps the files
\* it wrote (statechart's --help, "Exit codes").
ExitTwoLeavesFolder == \A r \in Runs : exitCode[r] = "2" => ~wrote[r] \/ unrendered[r]

\* A run exits 2 only for a wrong input, an edited spec, a file that it did not write, a failed
\* rename, or a chart that did not render, never because another run overlaps it.
OverlapNeverRefuses ==
  \A r \in Runs : exitCode[r] = "2" => ~inputOk[r] \/ spec # snap[r] \/ noted \/ broke[r] \/ unrendered[r]
====
