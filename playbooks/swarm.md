# Swarm

Run by: the home, for a task that splits into slices no one worker has to hold together, or a race of several workers on one brief, where each worker's answer fits in a few lines of a report.

Source: pstack, `pstack/skills/swarm/SKILL.md`

<!-- card: Fan out to threads | 2 | A task that splits into slices no one worker has to hold together, or a race of several workers on one brief. A scout takes each slice that reads, a crewmate each slice that writes, and the home builds the one table. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own.
A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo.
Read a principle in full when a step you are doing names it.

**You own the frame and the one table.** Every worker is a thread of its own with its file under `$H`: a scout, `scouts/<slug>-<n>.md`, for a slice that only reads, and a crewmate, `tasks/<slug>-<n>.md`, for one that writes.
Each is a thread the user can open, and a worker whose answer falls short is asked again in its own thread, where its context still is.
No worker is a subagent.
Each section named below is in `skills/home/SKILL.md`.

1. Frame it before any worker starts.
   Write the done predicate, a check that can fail, and what the swarm returns: a report, or files (`principles/principle-outcome-oriented-execution.md`).
   Then the shape: slices that cover the ground, a race of several workers on one brief, or both.
   For a race, write the rule that picks now, before any result is in: `first pass`, `rank all` or `best of`.
   Slices that must agree with each other as they go are not a swarm: hand the task to one crewmate by "Handing a task to a crewmate", and write `skip: one thread's work` on steps 2 to 6.
2. Set the list, one line per worker, each slice or arm of the race on it once, at most ten in a step.
   With more than ten, widen the slices, or run a second step once the first is drained.
   Mark each line `scout` when its worker only reads and `crew` when it writes.
3. Write one file per worker that stands alone: the goal, the scope, its slice or arm, how to verify, and what to send back.
   A scout's request goes in `scouts/<slug>-<n>.md`, in the shape of `$T/scout-request.md`, with `Out of bounds: read-only.` and no brief to deliver.
   A crewmate's brief goes in `tasks/<slug>-<n>.md`, in the shape of `$T/brief.md`, with `Pull request: none` and `Review: none`, and a **Done when** line that its work is committed and pushed to `origin/<slug>-<n>`.
   Each asks for an answer that opens with `PASS`, `ISSUES` or `BLOCKED`, then gives the evidence and every issue it can prove, not only the first.
   A worker that verifies or measures gets the exact commits by their full ids, and a measurement gets its method: how many samples, what one sample is, the order.
4. Start the step.
   Launch each scout by "Sending a scout", each on its own check of the machine.
   Queue each crewmate's row with `jbus queue add --entry <entry>`, as "Handing a task to a crewmate" says, and approve each on the user's word that asked for the swarm ("The user's word, carried by jbus").
5. Drain and aggregate as the threads end ("When a thread sends a message"), and review nothing in the turn (`principles/principle-guard-the-context-window.md`).
   Read each Report and Result.
   One that lacks the commits or the method its file named gets one message to its own thread asking for them, and after a second miss it is a gap.
   A thread that ended with nothing is a gap too, and a gap is never a pass.
   For coverage, see a result or a gap against every line of step 2.
   For a race, apply the rule of step 1.
   Keep one table (worker, slice or arm, verdict, the evidence in one line), and not what the workers wrote.
6. Keep what holds.
   An issue a worker reports is a claim until a thread has run its evidence or read the line it points at.
   Where crewmates left files to keep, write one more brief, `tasks/<slug>.md`, whose `Rests on:` line is the table: its crewmate checks each claim it keeps, brings the kept files into one branch from the slices' branches, runs the check command, and opens the swarm's one pull request with `Review: review`.
   Queue it with `--depends` on the writing rows, and its Result names their branches to remove once it merges.
   Where every worker only read, the table is the answer, and an issue the user wants fixed is a brief of its own.

Never done here, and who does it:

- **A worker run as a subagent.** Nobody does: every worker is a scout or a crewmate, so its work and its reasons stay on disk.
- **An eleventh thread in one step.** Nobody does: the next ten start when these are drained.
- **A worker that starts workers, or opens a pull request.** Nobody does: the brief of step 6 opens the swarm's one pull request, or none is opened.
- **A suite run by every worker.** Nobody does: the check command runs once, in the crewmate of step 6.
- **Reading the workers' diffs.** The crewmate of step 6 does, and the home reads only the Reports and Results.
- **A wait in a loop, or a stack of pull requests.** Nobody does: each thread's end wakes this one, and the swarm ends in one pull request or none.

**Hand over:** in this thread, to the user, when the last worker of the last step ended: the done predicate, the shape and the rule for a race, the table, each issue on one line with its evidence, every gap or dropout, and the pull request of step 6 if there is one.
