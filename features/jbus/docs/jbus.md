# jbus

jbus does a home's routine work with no model.
The work you approve then goes through launch, review and merge while no thread is open.
A timer runs one pass a minute, `jbus poll`, over every repo in its config.
On Linux and WSL2 the timer is the systemd user unit `jbus.timer`, and on macOS it is the launchd agent `jstack.jbus`.
A pass launches the rows of the queue you approved as crewmate threads in T3 Code, tells each thread what its pull request is short of, runs `jmerge` to merge what is ready, and tells you what waits on you.

jbus needs T3 Code running on the machine, `gh` signed in to GitHub, and a service manager for its timer.
That is a systemd user manager on Linux, the same on WSL2 once systemd is turned on in the distro, and launchd on macOS.
[Set up jbus](jbus/set-up-jbus.md) has the five steps from a release install to a jbus that launches work.

## What a pass does

One pass, under one lock, does this for every project in the config:

1. It runs `jmerge` in the project's main checkout, and makes one event for each line `jmerge` prints about a pull request.
2. It reads the briefs and the scout requests in the home's state directory, and makes one event for each new Result, Review, Report and question.
3. It asks T3 Code for the project's threads, and asks GitHub, through `gh`, for its pull requests and main's checks.
   It makes one event for each finding, such as `merged <slug> #<n> <sha>`, `stale <slug>: ...` or `retro <slug>: ...` ([A red main](jbus/a-red-main.md)).
4. It tells each crewmate's thread what it must act on: a failed check, a conflict, a review it is owed.
   A required check of a row's pull request that ran and was cancelled or timed out at its head is no crewmate's: at its run's first attempt jbus runs it again once (`gh run rerun <run> --failed`) and logs `cancelled <slug>: ran #<n>'s check again, run <run> at <head>`.
   A check cancelled again at a later attempt, or one GitHub will not run again, is one stall, once for the head, that the one list takes to the brief's home, and its line is the row's why.
   A run on a head the pull request has left, one a newer push displaced, is neither run again nor told.
   It stops a process that a crew or reviewer left running once its turn ended, busy or idle, and a busy one a scout left, one whose parent is 1, that runs in the task's worktree or a temporary folder its session made (under /tmp, /var/tmp or a test slot's own folder), and that holds no test slot, and adds a `Left running:` line under the task's last Result or Report.
5. It launches the approved rows of the queue, after it has asked every project for its open threads and pull requests ([What a pass launches](jbus/what-a-pass-launches.md)).
6. It rewrites the queue's derived columns, says what waits on you, and sends the events meant for you to the project's home thread ([Where wakes go](jbus/events-and-wakes.md#where-wakes-go)).

jbus makes no judgment call.
When no rule covers a case, jbus logs one line, `condition <slug>: <what>`, without posting it, and leaves that slug alone for the rest of the pass.
On a project's first pass, jbus records the Results, Reviews, Reports, questions and merges that are already there and sends none of them.
jbus writes three things to GitHub: a rerun of a cancelled check, a new base for a stacked pull request whose base merged, and a push of that link's commits moved onto the new base, under a lease.
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
- [Measure the CI](jbus/measure-the-ci.md)
- [Questions](jbus/questions.md)
- [Set up jbus](jbus/set-up-jbus.md)
- [The health check](jbus/the-health-check.md)
- [The plan](jbus/the-plan.md)
- [The queue](jbus/the-queue.md)
- [The relay](jbus/the-relay.md)
- [The sign-in](jbus/the-sign-in.md)
- [The units](jbus/the-units.md)
- [The verbs](jbus/the-verbs.md)
- [The view](jbus/the-view.md)
- [What a pass launches](jbus/what-a-pass-launches.md)
- [What blocks](jbus/what-blocks.md)
- [What the Chef may run](jbus/what-the-chef-may-run.md)
- [What the threads noticed](jbus/what-the-threads-noticed.md)
- [What waits on you](jbus/what-waits-on-you.md)
- [When jbus fails](jbus/when-jbus-fails.md)
- [Work items](jbus/work-items.md)
- [Your word to a home](jbus/your-word-to-a-home.md)
<!-- generated: end -->

[Working on jbus](working-on-jbus.md) has the pages for changing jbus itself, which an install does not need.
