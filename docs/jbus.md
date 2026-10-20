# jbus

`jbus poll` does a home's routine work with no model, so a repo can run with no home thread. A systemd timer runs one pass a minute. The **Chef** is the agent behind a project's webhook, and jbus tells it what each pass found. [The Chef](chef.md) says how to make one.

One pass, under one lock, does this for every project in the config:

1. It runs `jmerge` in the project's main checkout when no home merges, and makes one event for each line `jmerge` prints about a pull request.
2. It reads the briefs, the scout requests and `gates.md` in the home's state directory, and makes one event for each new Result, Review, Report and gate.
3. It asks T3 Code for the project's `crew: <slug>` threads and GitHub, through `gh`, for its pull requests. It makes one event per finding: `merged <slug> #<n> <sha>`, `stale <slug>: ...` for a thread past its `TIMEBOX:` (4 hours with none), one that waited 30 minutes on a request, or one that ended with no Result, and `retro <slug>: ...` for a failed check on main within a day of a merge, or for a revert of a merged pull request. When a pass finds `retro <slug>: main check failed at <sha12>, <n> merges since the last green`, and `<sha12>` is main's tip as the pass reads it, it also writes the brief for its fix, `tasks/main-red-<sha12>.md` in the home's state: the URL of each failed job, the failed test ids its log names, the merges since the last green and the files they changed, `Playbook: bug-fix` and `Size: S`. It queues it with no go (`queue add`, priority 0). A pass files it whenever the queue has no `main-red-<sha12>` row, so a pass that stopped before the row was added files it on the next, and a removed row is not filed again. A red commit that a later commit on main superseded is filed by no pass, the first after jbus starts included: only a red tip is a main to fix. A project's first pass files none, and neither does a pass for a merged slug that was removed: a red tip the first pass found is filed by the next. A `main-red-<sha12>` row that has not launched when main's tip is green again is left as it is, unapproved where it was, and the pass says once, quietly, `retro main-red-<sha12>: main is green again at <sha12>, and its row is left as it is`. A queue that refuses it is a condition. A red main holds no pull request: `jmerge` reads only a pull request's own `check`. A run of main that was cancelled is no failed check, whether its check run ended `cancelled` or it was cancelled before it had a job and left the commit with no check run. jbus asks GitHub to run it again (`gh run rerun <id>`) while GitHub's `run_attempt` for it is 1. It says `retro <slug>: main check cancelled twice at <sha>` when a later attempt is cancelled too, and `retro <slug>: main check cancelled at <sha>, and GitHub did not run it again` when GitHub refuses. A job that `timeout-minutes` stops also ends `cancelled`, not `timed_out`, so a suite that hangs on main is run again and then reads `cancelled twice`, never `main check failed`.
4. It ties each crewmate to its thread, [as the table below says](jbus/tying-a-crewmate-to-its-thread.md).
5. It launches the approved rows of the queue, after every project was asked what is out.
6. It rewrites the queue's derived columns, says what waits on you, and POSTs what it found to the project's webhook.

jbus makes no judgment call. What no rule covers is one line, `gate <slug>: <what>`, and jbus leaves that slug alone for the rest of the pass. On a project's first pass, jbus records the Results, Reviews, Reports, gates and merges that are already there and sends none of them. jbus writes nothing to GitHub and merges nothing itself.

No home merges when `~/.local/state/home/<repo>/home-thread` is missing or empty. With a thread id in that file the home merges, and jbus prints `skipped <project>: the home <id> merges`.

<!-- built: pages -->
- [A thread that left T3 Code's list](jbus/a-thread-that-left-t3-codes-list.md)
- [Add a project](jbus/add-a-project.md)
- [Back up the homes' state](jbus/back-up-the-homes-state.md)
- [Events and the webhook](jbus/events-and-the-webhook.md)
- [Measure the CI](jbus/measure-the-ci.md)
- [Questions](jbus/questions.md)
- [Set up jbus](jbus/set-up-jbus.md)
- [The plan](jbus/the-plan.md)
- [The queue](jbus/the-queue.md)
- [The relay](jbus/the-relay.md)
- [The verbs](jbus/the-verbs.md)
- [The view](jbus/the-view.md)
- [Tying a crewmate to its thread](jbus/tying-a-crewmate-to-its-thread.md)
- [What a pass launches](jbus/what-a-pass-launches.md)
- [What blocks](jbus/what-blocks.md)
- [What the threads noticed](jbus/what-the-threads-noticed.md)
- [What waits on you](jbus/what-waits-on-you.md)
- [When jbus fails](jbus/when-jbus-fails.md)
- [Work items](jbus/work-items.md)
- [Your word to a home](jbus/your-word-to-a-home.md)
<!-- built: end -->
