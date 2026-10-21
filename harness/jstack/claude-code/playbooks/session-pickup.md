# Session pickup

Run by: the home, for a thread that stopped with its task unfinished (a turn a restart cancelled, a turn that failed, a thread the audit printed as stuck), to be resumed and not started over.

Source: pstack, `pstack/skills/poteto-mode/playbooks/session-pickup.md`

<!-- card: Land and resume | 2 | A thread that stopped with its task unfinished: a cancelled turn, a failed turn, a stuck thread. It is resumed, not started over. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the resume point.** The trail is the brief, its last Result and what the worktree holds. Read the trail and have none of it done again. The thread does the work, not you.

1. Locate the trail, on disk: `$H/tasks/<slug>.md`, its `Thread:` line, its last `## Result` and its `## Review`. Never the thread's timeline (`principles/principle-guard-the-context-window.md`). Write down three things: the thread's id, whether there is a Result and what its `Status:` and `Left:` say, and the pull request if one is named.
2. Reconstruct the state, by commands that print a line and not a diff. From the main checkout: `git worktree list --porcelain` gives the worktree whose branch is the slug; `git -C <that worktree> status --short | wc -l` gives the files not committed; `git -C <that worktree> log --oneline origin/<default branch>..HEAD` gives the commits made. The line `jmerge` prints with `--check` says what a pull request is short of, and the lookup of "Handing a task to a crewmate" in `skills/home/SKILL.md` gives the thread's state. The trail is the record: send no scout to find it out again.
3. Set done against pending. Take the brief's `Done when` lines one by one against the Result's `Proof:` line and the commits of step 2. Name the resume point in one line: the first `Done when` line with no proof, or "open the pull request", "handle the review's findings", "write the Result". Work that has its proof is not redone and not checked again from scratch: a second run of it treats the trail as untrusted.
4. Pick one verdict and write it beside the resume point. `continue`: the work goes on from the resume point, the usual one. `ship`: the work is there and only the pull request or the Result is missing. `override`: the Result says blocked or not done, and an answer has come since: the answer goes in the message. `postmortem`: this is the third time the same thread or its successor stopped at the same point, so no third pickup: park a gate ("Gates") that asks whether to write a new, smaller brief, with the default that you do.
5. Send it, once (`principles/principle-make-operations-idempotent.md`). Look the thread up first: one whose state is `running` is not picked up. Then do what "Picking up a thread that stopped" in `skills/home/SKILL.md` says. A message first, when the thread can still take one: the verdict and the resume point in one line. A new thread on the same worktree when it cannot: the `Resume:` line in the brief, with the resume point, then the launch on the worktree that is there, on `go` from `room`, and the new id on the `Thread:` line.
6. See that it took, by a side effect and not by the thread's reply (`principles/principle-prove-it-works.md`): a new line in the brief or a push to the branch, at the next tick of the audit, or at the next message when no queue is out. A passing report the stopped thread left is a claim: the reviewer and the pull request's checks are its proof, as for any task.

Never done here, and who does it:

- **Reading the thread's timeline, the code or a diff.** Nobody does for a pickup: the brief and the commands of step 2 are the trail.
- **Doing what is left yourself.** The picked-up thread does, in its worktree.
- **A second writer on one worktree.** Nobody does: a thread that is `running` keeps its worktree, and a launch waits until it is not.
- **A new worktree for a task that has one.** Nobody does: the work in the old one would be orphaned. With no worktree left, it is a first launch, by step 2 of "Handing a task to a crewmate".
- **A third pickup at the same point.** The user decides, through the gate of step 4.

**Hand over:** in this thread, to the user: where the thread stopped, what was kept and what is redone (ideally nothing), the resume point and the verdict, which of the two calls was made, and the thread's link.
