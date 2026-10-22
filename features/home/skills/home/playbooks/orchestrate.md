# Orchestrate

Run by: the home, for a standing program: many entries toward one goal that outlives a single home, worked to a predicate that can be counted, with the user checking in now and then.

Source: pstack, `pstack/skills/poteto-mode/playbooks/orchestrate.md`

<!-- card: Work a queue unattended | 3 | A standing program: many entries toward one goal that outlives a single home, worked to a predicate that can be counted. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the program, never the code.** You write briefs, drain what the threads send, keep the count and decide. A brief is your only product: a crewmate cannot ask you a question, so a vague one fails quietly. Each section named below is in `skills/home/SKILL.md`.

1. Frame it as a count (`principles/principle-outcome-oriented-execution.md`). Write the done predicate in the plan's head as something a command can count, such as "all 14 entries merged, each with a review", and the number of entries beside it. Work a single crewmate could finish is no program: write its one entry, and steps 2 to 7 are `skip: one task`. A split that is contested is settled first, by a round of the grilling skill or a brief with `Playbook: arena`.
2. Write the standing orders before any launch. Every constraint the user gave is one dated line of `$H/notes.md`, in their words: every thread reads that file at its start, so nothing is pasted into a brief. When you catch yourself writing the same instruction into a second brief, write the line first (`principles/principle-encode-lessons-in-structure.md`).
3. Run a pilot: launch one entry, and take it to its merge before any other is launched (`principles/principle-sequence-verifiable-units.md`). It is there to prove wrong the brief, the check command and the size of an entry while that costs one thread. Read its Result's "Noticed" and its Review, and change the remaining entries and `notes.md` from them. Where the entries are near copies of each other, the first is the pilot and the rest launch when it merges.
4. Scale. Put `Playbook: orchestrate` in the head of `$M/plan.md`, and schedule the audit as "A queue and its hourly audit" says: the same block and the same two calls as for `playbooks/autopilot-full.md`. Launch what the launch check and `room` let start, and launch again on every message: a rolling window, never a batch that waits for its slowest. A dependency is context, not only order: an entry that rests on another's result gets the lines of that Result in its brief's `Rests on:`, since a crewmate sees no sibling.
5. Drain. A message is a queue event, not an interrupt: work it as "When a thread sends a message" says, a tick as "One tick" says, and review nothing in the turn (`principles/principle-guard-the-context-window.md`). A result that needs judging is a scout's request or a new brief. End each drain with one line of count against the predicate: merged, out, planned, open gates.
6. Handle a failure by its kind (`principles/principle-fix-root-causes.md`), and clear the home's own blockers on every wake ("Clearing its own blockers"). A thread that stopped is picked up with the playbook `session-pickup`, twice at most, and then its entry is written again, smaller. When more launches would only make more of the same failure (a pilot that was wrong, a check command that is broken, CI that starts no job), put a dated stop line at the top of the plan, launch nothing, let what is out finish, make the cause a task, and take the line out when it merges.
7. Close by account, not by memory (`principles/principle-prove-it-works.md`). Every brief this plan launched ends one of three ways: merged, ended with no pull request, or abandoned with its reason in the plan. The sweep prints no `kept` line that is unexplained. The predicate is counted from the plan and `$H/merge.log`. Then delete the audit, take the `Playbook:` line out, put what kept coming back into `notes.md`, and hand off.

Never done here, and who does it:

- **Writing or landing code.** A crewmate writes it and `jmerge` merges it. A conflict is its crewmate's, a restack nobody's.
- **A layer of coordinators under you.** A scoped home is that layer, and only the root home makes one, on the user's word: ask for it in a gate.
- **A store, a ledger or an inbox of your own.** Nobody keeps one: `$H` is the store, a brief's Result and Review the ledger, `$M/gates.md` the gates.
- **A verifier on another model, a cloud worker, a raised effort.** Nobody does: one reviewer, this session's model, medium effort.
- **Stopping at a share of a wall clock.** `room` decides each launch, by its `CUSHION` line.
- **Resuming a thread to see how it is.** Nobody does: read its brief and its branch, as the tick does.
- **A stack.** Nobody does here.

**Hand over:** in this thread, to the user, at the close and when asked: the predicate and the count against it, what merged with its pull requests, what was abandoned and why, the open gates, which are the only asks, and where the record is.
