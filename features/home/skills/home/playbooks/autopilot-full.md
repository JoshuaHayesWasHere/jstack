# Autopilot, full

Run by: the home, for a queue of approved plan entries worked to its end with no word from the user, each pull request owned by one crewmate from its first commit to green.

Source: pstack, `pstack/skills/poteto-mode/playbooks/autopilot-full.md`

<!-- card: Work a queue unattended | 1 | A queue of approved plan entries worked to its end with no word from the operator, each pull request owned by one crewmate from first commit to green. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the queue, never a pull request.**
One crewmate owns each pull request, the reviewer owns its verdict, and `jmerge` merges what is ready.
You keep the order, the launches and the account at the end.
Each section named below is in `skills/home/SKILL.md`.

1. Mark what is the user's, then start. An entry the user said they will merge or decide themselves is not in the queue: leave it `planned`, with their words under `Decisions:`, and launch it on their word. Say the queue in at most six lines, the entries in order and what each waits on, and go on: the plan the user approved is the go, and nothing waits for a second one (`principles/principle-never-block-on-the-human.md`).
2. Start the queue.
   Put `Playbook: autopilot-full` in the head of `$M/plan.md`, above the first entry.
   Schedule nothing: the queue moves on messages, and jbus's pass is its cadence (`principles/principle-encode-lessons-in-structure.md`).
3. Queue each entry's first row, by step 3 of "When a thread sends a message", and jbus launches each one that `room` lets start.
   Entries that hold no file in common run at once, and one whose code changes, calls or imports another's change is queued with `--depends` on it (`principles/principle-separate-before-serializing-shared-state.md`).
   Entries of one plan layer are siblings: they queue unstacked, with `--merge-after` only where the order of the merges matters.
   Each brief carries the whole of its pull request: build, the pull request, its checks, its review, its fixes.
4. Work each message as "When a thread sends a message" says, and nothing more. The verdict on a pull request is its reviewer's and the merge is `jmerge`'s: you read no diff and judge no change. When a pull request merges, the next entry that can start gets a fresh crewmate, never the thread that just finished.
5. Clear this home's blockers each wake ("Clearing its own blockers").
   A thread is judged by its side effects (a line in its brief, a push to its branch), not by its state or what it says of itself (`principles/principle-prove-it-works.md`).
   On jbus's nudge, pick up each thread that stopped with the playbook `session-pickup` when it is neither `running` nor `waiting`.
   A stall drops nothing: its entry stays in the queue.
6. On the user's stop, stop at once.
   Send every thread out one line with `t3_thread_send`: write nothing more, push nothing, and wait for a word.
   Launch nothing, and tell the user which threads were told.
   The threads keep their briefs and their worktrees until the user releases them.
7. Close when every entry of the plan is done.
   Run `jmerge` and the sweep once more.
   Then account for every entry by its line in `$H/merge.log`, not from memory (`principles/principle-outcome-oriented-execution.md`): merged, with its pull request and commit, or left, with the reason.
   Its lines are told on status.
   Take the `Playbook:` line out of the plan's head.

Never done here, and who does it:

- **Merging by hand, or having a crewmate merge its own pull request.** `jmerge` does, on review, fix and green. What is short of that waits for the user's word.
- **A swarm of verifiers, live lanes, or a second reviewer on another model.** Nobody does: one review a pull request, and a second pass only where the crew skill's block asks for one.
- **Raising a limit or a budget a check enforces.** The user does: park it as a gate, with the default that the limit stays.
- **A rebase, a fix or a push from the home.** The crewmate that owns the pull request does, on its own wakes.
- **A watch loop, or a schedule.**
  Nobody does: jbus's pass watches every home.
- **A stack.**
  Nobody does here: a dependent entry waits for the merge, or jbus stacks it on its `Builds on:` row's open pull request.

**Hand over:** in this thread, to the user, only when asked: catch the user up per `skills/ketchup/SKILL.md`, then this account, uncut: each entry with its crewmate's link, its state and its pull request; what merged, with the commit; each stuck thread and what was done; and the open gates.
