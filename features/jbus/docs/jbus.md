# jbus

jbus does a home's routine work with no model.
The work you approve then goes through launch, review and merge while no thread is open.
A timer runs one pass, `jbus poll`, over every repo in its config, 10 seconds after the last one ended.
On Linux and WSL2 the timer is the systemd user unit `jbus.timer`, and on macOS it is the launchd agent `jstack.jbus`.
A pass launches the rows of the queue you approved as crewmate threads in T3 Code, tells each thread what its pull request is short of, runs `jmerge` to merge what is ready, and tells you what waits on you.

jbus needs T3 Code running on the machine, `gh` signed in to GitHub, and a service manager for its timer.
That is a systemd user manager on Linux, the same on WSL2 once systemd is turned on in the distro, and launchd on macOS.
[Set up jbus](jbus/set-up-jbus.md) has the five steps from a release install to a jbus that launches work.

## What a pass does

One pass, under one lock, works on every project in the config side by side, each project in a thread of its own with its own T3 Code client (`jbus.poll`).
Each project's steps run in this order:

1. It runs `jmerge` in the project's main checkout, and makes one event for each line `jmerge` prints about a pull request.
2. It reads the briefs and the scout requests in the home's state directory, and makes one event for each new Result, Review, Report and question.
3. It asks T3 Code for the project's threads, and asks GitHub, through `gh`, for its pull requests and main's checks.
   It makes one event for each finding, such as `merged <slug> #<n> <sha>`, `stale <slug>: ...` or `retro <slug>: ...` ([A red main](jbus/a-red-main.md)).
4. It tells each crewmate's thread what it must act on: a failed check, a conflict, a review it is owed.
   A required check of a row's pull request that ran and was cancelled or timed out at its head is no crewmate's: at its run's first attempt jbus runs it again once (`gh run rerun <run> --failed`) and logs `cancelled <slug>: ran #<n>'s check again, run <run> at <head>`.
   A check cancelled again at a later attempt, or one GitHub will not run again, is one stall, once for the head, that the one list takes to the brief's home, and its line is the row's why.
   A run on a head the pull request has left, one a newer push displaced, is neither run again nor told.
   A required run GitHub queued at a row's head and started nothing of for 30 minutes (`ready.QUEUED_MINUTES`) is no crewmate's either, on every open row's pull request (`cancelled.unqueue`): a run with no jobs, which the roll-up does not list, or a run whose `check` job sits queued.
   Where the roll-up lists no run of a required check, or one queued that long, jbus reads the head's workflow runs and their jobs, cancels each such run that has not ended (`gh run cancel <run>`), runs it again (`gh run rerun <run>`), and logs `queued <slug>: GitHub queued #<n>'s <check> run at <head> <m> minutes ago and started no job: cancelled it and ran it again`.
   That is once for the head, marked `queued|<slug>|<head12>`: a rerun GitHub refuses while its cancel ends is asked again on each pass for 10 minutes (`ready.RESTART_MINUTES`) and then given up with GitHub's refusal on the line, and a run GitHub queues again at that head is logged once and not restarted, so its wait is the home's.
   When the last review's `Meets the brief:` line says `no`, has no shape `jmerge` reads, or counts other lines than the brief has, jbus sends the crew to the crew skill's "A second pass" (`jbus.expedite`).
   When `jmerge` waits on the Result's `Proved:` line, jbus sends the crew to the proof block of the crew skill's do-the-task.md, the step "Once the check passed, prove the change with the tests it changes", and tells it to push nothing for it; when the Result's `Skills run:` leaves out a skill the brief names, jbus tells the crew the item each such skill owes.
   Every reason `jmerge.ready` gives, of every step, is told to its crew this way (`expedite.TABLE`), or named with why it is not: no crew can fix it (`expedite.UNTOLD`), or another part of jbus tells the crew of it (`expedite.ELSEWHERE`).
   A test holds the three to `jmerge.ready`, so a new reason with none of them fails it.
   It stops a process that a crew or reviewer left running once its turn ended, busy or idle, and a busy one a scout left, one whose parent is 1, that runs in the task's worktree or a temporary folder its session made (under /tmp, /var/tmp or a test slot's own folder), and that holds no test slot, and adds a `Left running:` line under the task's last Result or Report.
5. It launches the approved rows of the queue, after it has asked every project for its open threads and pull requests ([What a pass launches](jbus/what-a-pass-launches.md)).
6. It rewrites the queue's derived columns, says what waits on you, and sends the events meant for you to the project's home thread ([Where wakes go](jbus/events-and-wakes.md#where-wakes-go)).

jbus makes no judgment call.
When no rule covers a case, jbus logs one line, `condition <slug>: <what>`, without posting it, and leaves that slug alone for the rest of the pass.
On a project's first pass, jbus records the Results, Reviews, Reports, questions and merges that are already there and sends none of them.
jbus writes these things to GitHub, and no others:

- a rerun of a check that was cancelled, and of main's red check at its first attempt;
- a cancel and a rerun of a required run GitHub kept queued at a row's head, once for the head;
- a new base for a stacked pull request, when its base merged ([What a pass launches](jbus/what-a-pass-launches.md));
- a push of a stacked link's own commits moved onto its new base, under a lease;
- a revert of the one clear culprit of a red main, a pull request `gh pr revert` opens, and the close of that revert, with a comment, once main is green without it ([A red main](jbus/a-red-main.md)).

jbus merges nothing itself.
`jmerge` does the merging.

jbus is the only merger, whatever `~/.local/state/home/<repo>/home-thread` holds, and no home runs `jmerge` to merge.
A run of `jmerge` holds the repo's merge lock from its read of main's tip to its merge, so a run of yours never merges between them.

## The pages

<!-- generated: pages by scripts/generate-jstack-trees.py from the headings of features/jbus/docs/jbus/; do not edit, rerun it -->
- [A red main](jbus/a-red-main.md)
- [A scratch home](jbus/a-scratch-home.md)
- [Add a project](jbus/add-a-project.md)
- [Back up the homes' state](jbus/back-up-the-homes-state.md)
- [Decisions](jbus/decisions.md)
- [Events and wakes](jbus/events-and-wakes.md)
- [Gate labels](jbus/gate-labels.md)
- [Measure the CI](jbus/measure-the-ci.md)
- [Questions](jbus/questions.md)
- [Row moves](jbus/row-moves.md)
- [Set up jbus](jbus/set-up-jbus.md)
- [The health check](jbus/the-health-check.md)
- [The plan](jbus/the-plan.md)
- [The queue](jbus/the-queue.md)
- [The relay](jbus/the-relay.md)
- [The sign-in](jbus/the-sign-in.md)
- [The telemetry store](jbus/the-telemetry-store.md)
- [The units](jbus/the-units.md)
- [The verbs](jbus/the-verbs.md)
- [The view](jbus/the-view.md)
- [What a pass launches](jbus/what-a-pass-launches.md)
- [What blocks](jbus/what-blocks.md)
- [What the Chef may run](jbus/what-the-chef-may-run.md)
- [What waits on you](jbus/what-waits-on-you.md)
- [When jbus fails](jbus/when-jbus-fails.md)
- [Work items](jbus/work-items.md)
- [Your word to a home](jbus/your-word-to-a-home.md)
<!-- generated: end -->

[Working on jbus](working-on-jbus.md) has the pages for changing jbus itself, which an install does not need.
