## 1. Scope s working: the entry in plan-done.md twice; no fix

Rule broken: An entry is in its plan or in plan-done.md, once, and in both only between the two writes of one close: no line is lost, and no close leaves a second copy. A close cut short is still between its two writes, as the disk shows it, until a close finishes it.
Why: jbus plan close died between its append to plan-done.md and its rewrite of the plan, and the close run again appended the section a second time: plan.close reads plan-done.md only for the blank line before the section.
There are 144 ways to get here in the model. This is the shortest.

0. Start: Scope s working: the entry proposed or planned; no fix
1. The home closes the entry: plan close appends it to plan-done.md. Now: Scope s working: the entry in its plan and in plan-done.md, the close at work; no fix
2. The close dies between its two writes. Now: Scope s working: the entry in its plan and in plan-done.md, its close cut short; no fix
3. The home closes it again: plan close appends it a second time. Now: Scope s working: the entry in plan-done.md twice; no fix

## 2. Scope s working: the entry proposed or planned; the fix counted in s, not where its home reads it

Rule broken: A counted fix is in the ledger admit reads for it, the one of its brief's home, once no move runs. (A rule this model adds to the brief's three: today's code breaks it.)
Why: jbus queue move rewrote the fix's Home: line and died before blockers.rehome carried its try, which only a move run again carries.
There are 126 ways to get here in the model. This is the shortest.

0. Start: Scope s working: the entry proposed or planned; no fix
1. The home queues the fix, and jbus counts it. Now: Scope s working: the entry proposed or planned; the fix counted in s
2. The home moves the fix to the catch-all: queue move rewrites its Home: line. Now: Scope s working: the entry proposed or planned; the fix counted in s, not where its home reads it, the move at work
3. The move dies. Now: Scope s working: the entry proposed or planned; the fix counted in s, not where its home reads it

## 3. Scope s's plan archived, its home-id still there: the entry proposed or planned (in plan-archived.md); the fix counted in s, not where its home reads it

Rule broken: A counted fix is in the ledger admit reads for it, the one of its brief's home, once no move runs. (A rule this model adds to the brief's three: today's code breaks it.)
Why: the archive moved plan.md aside, so the fix's brief is the catch-all's, but no step moves blockers.json: the try stays in s's ledger, which admit no longer reads.
There are 60 ways to get here in the model. This is the shortest.

0. Start: Scope s working: the entry proposed or planned; no fix
1. You run /handoff: the home writes its note. Now: Scope s archiving, its note written: the entry proposed or planned; no fix
2. The archive asks the scope's gate of the catch-all. Now: Scope s archiving, its gate asked of the catch-all, gates.md still there: the entry proposed or planned; no fix
3. The archive moves gates.md aside. Now: Scope s archiving, its gates asked of the catch-all, gates.md moved aside: the entry proposed or planned; no fix
4. The archive keeps the note in log/, with its Was home line. Now: Scope s archiving, its note kept in log/: the entry proposed or planned; no fix
5. The archive moves the older handoff.md to log/. Now: Scope s archiving, its note and the older one in log/: the entry proposed or planned; no fix
6. The home queues the fix, and jbus counts it. Now: Scope s archiving, its note and the older one in log/: the entry proposed or planned; the fix counted in s
7. The archive moves plan.md to plan-archived.md. Now: Scope s's plan archived, its home-id still there: the entry proposed or planned (in plan-archived.md); the fix counted in s, not where its home reads it
