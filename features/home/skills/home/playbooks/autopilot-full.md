# Autopilot, full

Run by: the home, for a queue of approved plan entries worked to its end with no word from the user, each pull request owned by one crewmate from its first commit to green.

Source: pstack, `pstack/skills/poteto-mode/playbooks/autopilot-full.md`

<!-- card: Work a queue unattended | 1 | A queue of approved plan entries worked to its end with no word from the operator, each pull request owned by one crewmate from first commit to green. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the queue, never a pull request.** One crewmate owns each pull request, the reviewer owns its verdict, and `jmerge` merges what is ready. You keep the order, the launches, the hourly audit and the account at the end. Each section named below is in `skills/home/SKILL.md`.

1. Mark what is the user's, then start. An entry the user said they will merge or decide themselves is not in the queue: leave it `planned`, with their words under `Decisions:`, and launch it on their word. Say the queue in at most six lines, the entries in order and what each waits on, and go on: the plan the user approved is the go, and nothing waits for a second one (`principles/principle-never-block-on-the-human.md`).
2. Start the queue. Put `Playbook: autopilot-full` in the head of `$M/plan.md`, above the first entry. Run the first block of "A queue and its hourly audit": on `schedule`, schedule the audit and keep its id, then run the block again and see `keep`. The cadence is a schedule, never something to remember (`principles/principle-encode-lessons-in-structure.md`). With no schedule tool, say so once and go on: the queue then moves on messages alone.
3. Launch one crewmate for each entry that can start, by step 3 of "When a thread sends a message": the launch check and `room` before each. Entries that hold no file in common run at once, and one that needs another's change waits for that merge and starts from the default branch (`principles/principle-separate-before-serializing-shared-state.md`). Each brief carries the whole of its pull request: build, the pull request, its checks, its review, its fixes.
4. Work each message as "When a thread sends a message" says, and nothing more. The verdict on a pull request is its reviewer's and the merge is `jmerge`'s: you read no diff and judge no change. When a pull request merges, the next entry that can start gets a fresh crewmate, never the thread that just finished.
5. Work each tick as "One tick" says, and clear the home's own blockers on every wake ("Clearing its own blockers"). A thread is judged by its side effects (a line in its brief, a push to its branch), not by its state or what it says of itself (`principles/principle-prove-it-works.md`). One printed as `stuck` is picked up with the playbook `session-pickup` when it is neither `running` nor `waiting`. A stall proves nothing and drops nothing: its entry stays in the queue. A tick that changed something ends by catching the user up on that alone, per `skills/ketchup/SKILL.md`. A tick that changed nothing ends with no reply.
6. On the user's stop, stop at once. Send every thread out one line with `t3_thread_send`: write nothing more, push nothing, and wait for a word. Launch nothing, delete the audit as "A home that hands off" does, and tell the user which threads were told. The threads keep their briefs and their worktrees until the user releases them.
7. Close when the first block of "A queue and its hourly audit" prints `delete`: every entry is done. Delete the audit and run the keep block with nothing. Run `jmerge` and the sweep once more. Then account for every entry by its line in `$H/merge.log`, not from memory (`principles/principle-outcome-oriented-execution.md`): merged, with its pull request and commit, or left, with the reason. Take the `Playbook:` line out of the plan's head, and show the open gates.

Never done here, and who does it:

- **Merging by hand, or having a crewmate merge its own pull request.** `jmerge` does, on review, fix and green. What is short of that waits for the user's word.
- **A swarm of verifiers, live lanes, or a second reviewer on another model.** Nobody does: one review a pull request, and a second pass only where the crew skill asks.
- **Raising a limit or a budget a check enforces.** The user does: park it as a gate, with the default that the limit stays.
- **A rebase, a fix or a push from the home.** The crewmate that owns the pull request does, on its own wakes.
- **A watch loop, or a second schedule.** Nobody does: the audit is the one exception, and it ends with the queue.
- **A stack.** Nobody does here: a dependent entry waits for the merge. Entries the user wants to review as one chain and land themselves are `playbooks/autopilot-stack.md`, landed by `playbooks/shipping.md`.

**Hand over:** in this thread, to the user, at the close and when asked: catch the user up per `skills/ketchup/SKILL.md`, then this account, uncut: each entry with its crewmate's link, its state and its pull request; what merged, with the commit; each stuck thread and what was done; the open gates; and that the audit is deleted.
