# How a task flows

![A home plans and writes a brief, a scout researches when needed, a crewmate does the one task and opens the pull request, a reviewer sends findings back, and jbus runs jmerge, which merges to main. Every thread reads and writes the state directory.](flow.svg)

A thread is an agent with a model, and a command has no model.
The state directory is the only thing the threads share.
A message wakes a thread, and the records are files in that directory.
[State](state.md) lists its files.

## The ten steps

| Step | Who | What happens |
|---|---|---|
| 1. Plan entry | You, with the home | You say what you want. The home writes one entry per pull request in `plan.md`, with a "Done when" list. |
| 2. Brief | The home | It writes `tasks/<slug>.md`: the task, where it may work, and its `Proves it:`, `Design:`, `Review:` and `Playbook:` lines. |
| 3. The queue and the approval | You | The brief waits as a row of the queue. You approve that exact brief, named by its sha. |
| 4. Launch | `jbus` | It launches an approved row once the rows its `depends` names are merged and `jgauge room` prints `go`. |
| 5. The worktree | The crewmate | A new thread in its own worktree, on a branch named for the slug, works the brief by its playbook. |
| 6. The check | The check command | The repo's check command runs once, under a test slot. CI runs the repo's checks on the pull request the crewmate opens, and `jmerge` waits for the check named `check`, or for the checks the repo lists in `required-checks`. |
| 7. The review | The reviewer | One fresh thread reviews each pull request, with no reviewer subagents. It reads the diff itself, judges what it found, and proves one safety fact by running code. It fixes nothing, and jbus archives it once the pull request merges or closes. |
| 8. The findings | The crewmate | It ends every finding with a `Finding:` line, fixed or not fixed and why, then writes one `Fixed:` line. |
| 9. `jmerge` | A command | It merges what is reviewed, fixed and green, at the head that was checked. For the rest it prints `wait` or `hold` and the reason. `jbus` runs it on each pass, and no home runs it to merge. |
| 10. The sweep | A command | `jmerge --sweep` removes the worktree and the branches a finished thread left, and prints what it kept and why. |

A **scout** goes first, before step 2, when the home cannot write the brief from what it knows. It reads the code and the docs and writes down what it found. The home itself never reads the code.

A repo can run with a home thread, with `jbus` and its queue, or with both.
With a home thread alone, steps 3 and 4 happen in the thread.
You say yes to the plan entry there, and the home launches the crewmate itself after `jgauge room` prints `go`.
With `jbus` alone, `jbus` launches only the approved rows of the queue.
A release install writes a `jbus` config with `dispatch = false`, so `jbus` launches nothing until you [set it up](../../jbus/docs/jbus/set-up-jbus.md).

The `jbus` timer runs `jmerge` on each pass, and no home runs it to merge.
A home writes its own id into `home-id` when it starts, and only you write `home-thread`.
Until you choose, run `jmerge` in the repo's main checkout.
[Configuration](../../jinstall/docs/configuration.md#switches-for-one-repo) has both switches.

## What you are asked for

Three things come to you.
Without asking you, the threads do everything else that is reversible.

- **An approval.** You give a yes to that exact brief.
- **A gate.** A thread met a question only you can answer, took a default and carried on. You keep the default, or change it.
- **A held pull request.**
  `jmerge` printed `hold`.
  You give `jmerge --accept <number> --by <user> --at "<date and time>"`, where `<user>` is the `user` of your [configuration](../../jinstall/docs/configuration.md#jstack).
  Add `--check` to see what it would do.
  `jmerge` refuses `--accept` unless the review proved the fact that makes the change safe.
  [jmerge](../../jmerge/docs/jmerge.md) has the rest.

| Asked for | When | If you are away |
|---|---|---|
| An approval | Before a task launches | That task does not launch. Other tasks go on. |
| A gate | At any step of any thread | Nothing waits. The default stands until you change it. |
| A held pull request | At the merge | The pull request stays open. Nothing else is held up unless it depends on it. |
| One of the four pauses | Before a force-push to a shared branch, a deploy, deleting data, or a message to anyone outside | The thread asks in its own thread and waits for your answer. These are the only things a thread asks first. |
| A pull request with no review | Its brief says `Review: none` | It never merges by itself. It waits for your word. |

A brief that says `Review: after` merges once its check passes, and its review's findings become a cleanup row, `cleanup-<slug>`.
Where the reviewed row's go still holds, jbus approves that row by the follow-up rule when it is queued, or on the next pass; otherwise it waits for your go.
A brief that says `Review: twice`, the home's default, gets one review and one fix round.
Then a second review reads the head the fix round pushed, unless that round changed nothing and wrote `Fixed: none needed`.
The pull request merges once the second review is written.
The second review's `warning` and `error` findings come to you as the same kind of cleanup row, and its `info` findings are dropped.
A brief that says `Review: review` has every finding answered before the merge.
There, a fix that changes a file outside `tests/` gets one more review, of the fix alone, and that review is the last.
A fix that changes only files under `tests/` gets no second review, and the pull request's checks stand behind it.
A blocking finding that the crewmate declines gets that review all the same, even when nothing was pushed.

## Who clears a blocker, and who pages you

No bot outside watches the homes or the queue.
Each home clears its own blockers each time it wakes, with `jbus clear`: it takes the default of a gate left open, and briefs a fix of a failed check, a refused or stuck row, or a leftover.
Every such fix has a `When green:` line, the exact check that ends it, and each blocker gets at most `retry_cap` fixes (2 with none), after which it comes to you as a decision.
What reaches you is a `decision`, a `sign-in` or an `alert` that stands, each with a reply you can send as it is: jbus posts it to the relay, the relay sends it to your chat bot (Sous Chef, the brief's Chief Keef), and the bot pages you.
The rest, a merge, a stale thread, a retro, is in the digest.
[Decisions](../../jbus/docs/jbus/decisions.md) has the rest.

A `wait` from `jmerge` is not a failure and asks nothing of you.
`jmerge` prints the first thing it is short of, such as a check that has not passed, and a later run merges it once the reason is gone.

## Two pages to open in a browser

Two HTML pages in this directory draw the same flow in more detail.
github.com shows an HTML file as its source, so open them from the files on your machine.
A release install puts them in `share/jstack/features/home/docs/` of the `jstack` tool's environment, and `uv tool dir` prints the folder that holds that environment:

```sh
xdg-open "$(uv tool dir)/jstack/share/jstack/features/home/docs/flow.html"
xdg-open "$(uv tool dir)/jstack/share/jstack/features/home/docs/jstack-explained.html"
```

In a checkout of jstack, open the same two files in `features/home/docs/`.

| Page | Shows |
|---|---|
| [`flow.html`](flow.html) | One task from a home to a merge, column by column: every file a step reads or writes, and every message a thread sends. |
| [`jstack-explained.html`](jstack-explained.html) | The ten steps as a drawing, a first day, one card for each skill, playbook and principle, and the commands. |

Both pages load nothing from the network.
