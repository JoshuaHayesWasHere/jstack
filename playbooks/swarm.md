# Swarm

Run by: a crewmate, for a task that splits into slices no one worker has to hold together, or a race of several workers on one brief, where each worker's answer fits in a few lines of a report.

Source: pstack, `pstack/skills/swarm/SKILL.md`

<!-- card: Long or wide runs | 3 | A task that splits into slices no one worker has to hold together, or a race of several workers on one brief. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the frame and the one report.** A worker is a subagent: it knows only its brief and is gone when it returns. You keep the frame, the table of results and every file that is kept. Never more than ten subagents in one step.

1. Frame it before any worker starts. Write the done predicate, a check that can fail, and what the swarm returns: a report, or files (`principles/principle-outcome-oriented-execution.md`). Then the shape: slices that cover the ground, a race of several workers on one brief, or both. For a race, write the rule that picks now, before any result is in: `first pass`, `rank all` or `best of`. Slices that must agree with each other as they go are not a swarm: write `skip: one thread's work` on steps 2 to 5 and do it here.
2. Set the number: one worker per slice or per arm of the race, ten at most in a step. With more than ten, widen the slices, or run a second step once the first is drained. Write the list down, one line per worker, and see that every slice is on it once. Every worker runs on this session's model and effort.
3. Give each worker that writes a place of its own before it starts (`principles/principle-separate-before-serializing-shared-state.md`): a directory, `mktemp -d /tmp/<slug>-<n>.XXXXXX`, or for code a worktree you make, `git worktree add --detach <path> HEAD`. No two workers share a path, and none writes in your worktree. Workers that verify or measure get the exact commits by their full ids, and a measurement gets its method: how many samples, what one sample is, the order.
4. Write a brief per worker that stands alone: the goal, the scope, its slice or arm, its place, how to verify, and what to send back. An answer opens with `PASS`, `ISSUES` or `BLOCKED`, then gives the evidence, every issue it can prove and not only the first, and the commits and method it was given. Start all workers of the step in one message with `Agent`: `subagent_type` is `Explore` for a worker that only reads and `general-purpose` for one that writes, `run_in_background` is false, and there is no `model` and no `effort`. Wait for them inside this turn.
5. Drain and aggregate. Read every answer. Drop one that lacks the commits or the method its brief named and start that worker once more; after a second miss write a gap. A worker that returned nothing is a gap too, and a gap is never a pass. For coverage, see a result or a gap against every line of step 2. For a race, apply the rule of step 1. Keep one table (worker, slice or arm, verdict, the evidence in one line) and not what the workers printed (`principles/principle-guard-the-context-window.md`).
6. Check what you keep (`principles/principle-prove-it-works.md`). An issue a worker reports is a claim until you have run its evidence or read the line it points at. Bring the files you keep into your worktree by hand and run the repo's check command once, yourself: no worker runs a suite that starts several processes. Then remove what step 3 made, `git worktree remove --force <path>` and `rm -r <directory>`, and see `git worktree list` without them.
7. Run `playbooks/opening-a-pr.md` when the swarm changed files in your worktree. When it only reported, end as `skills/crew/SKILL.md` "End" says for a task with no pull request. The table goes in the Result either way.

Never done here, and who does it:

- **An eleventh subagent in one step.** Nobody does: the next ten start when these are drained.
- **A worker that has to remember.** A subagent holds nothing after it returns. A piece that must outlast the step (it waits on a review, a pull request or the user) is a thread of its own, and the home launches it: one line per piece under "Noticed".
- **A cloud worker, a worker on a named model, or one at a raised effort.** Nobody does: every worker is a local subagent on this session's model.
- **A worker that starts workers, commits to your branch, pushes or opens a pull request.** You commit what you keep, and the pull request is the one of step 7.
- **A wait in a loop, or a stack of pull requests.** Nobody does: the workers return inside the turn, and the swarm ends in one pull request or none.

**Hand over:** in the pull request and the Result, to the reviewer and the home: the done predicate, the shape and the rule for a race, the table, each issue on one line with its evidence, and every gap or dropout.
