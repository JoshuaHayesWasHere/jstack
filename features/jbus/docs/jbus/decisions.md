# Decisions

No bot outside watches the homes or the queue.
Each home clears its own blockers each time it wakes, with `jbus clear` ("Clearing its own blockers" in the home skill), and raises to you only what you have to decide.
jbus sends a `decision` to the project's home thread ([Where wakes go](events-and-wakes.md#where-wakes-go)).
Where you run the relay, it also gets what blocks and sends it on to your chat bot (the agent behind `RELAY_WEBHOOK_URL`, Sous Chef, the brief's Chief Keef), which pages you ([What blocks](what-blocks.md), [The relay](the-relay.md)).

A decision is one `user` event of the kind `decision`, sent once for each blocker, whoever raises it again.
Its line is `decision <slug>: <what to decide>. Reply: <hint>`, and the hint says what your reply decides, such as `reply in your own words to merge #9 or say what to do instead`: you answer in your own words, which reach the home as your word ([Your word to a home](your-word-to-a-home.md)), and the home turns them into the verb.
These raise one, and nothing else does:

| What | Raised by | Reply |
|---|---|---|
| A question or a gate that holds (a force-push, a deploy, deleting data, a message to anyone outside, and the rest of the gates table), has no default, or names one of those words | the pass, from the list of what waits | `<project> question <n>: default` |
| A pull request `jmerge` holds for your word | the pass | `<project> #<n>: merge it` |
| A row with no approval of its brief | the pass | `<project> approve <slug>: go` |
| A config item, setup only you can give | the pass | `<project> config: I set it up` |
| A blocker that had its retry cap of fixes and still blocks | `jbus queue add` and `jbus clear` | `<project> <key>: I take it` |
| A scope change, work the plan you approved does not hold | the home, with `jbus decide` | what the home writes |

A project's first pass raises none, as it sends nothing else.
Just before it sends, the pass reads again what each item stands on, as dispatch reads a row again before a launch.
A row whose go now holds for its brief, a gate whose question has closed, and a pull request whose row has merged are not raised.
A row to approve is raised only once it has waited unapproved for `APPROVE_GRACE_SECONDS` (60, one pass), so a row a home queues and approves a moment later never reaches you; a gate that holds is raised at once.

An item that leaves the list of what waits wakes no one: the decision raised for it stays in the log, and no event says it went.

## Fixes and their stop

A fix a home queues by itself is a brief whose head has `Fix of: <key>`, the blocker it clears, and `When green: <the exact check that ends the work>`, such as `check` passing on the fix's pull request at its head.
`jbus queue add` and `jbus queue apply` refuse a fix with no `When green:` line, and queue nothing.
Each fix queued for a key is counted, by its brief's sha, in `blockers.json` in the directory of the brief's home, so the same brief queued again is no new try.
A fix whose own check fails is the same blocker again: `jbus clear` names it by the key its brief fixes.
Once a key has had `retry_cap` fixes (in `~/.config/jstack/config.toml`, 2 with none), the next is refused, and the key is raised as one decision instead.

## jbus clear

`jbus clear` reads only what jbus keeps and asks no service.
It prints one line for each blocker of the home it runs for (`--scope <scope>` for a scoped home):

| Line | What it means |
|---|---|
| `decision question <n>: ...` | You have to decide it, and the pass raises it. |
| `fix <key>: ..., try <n> of <cap>` | The home briefs a fix with `Fix of:` and `When green:`, and queues it. |
| `wait <key>: ...` | A fix of the key is queued and not over. |
| `decision <key>: ... had <n> fixes ...` | The key had its cap, and is raised. |
| `nothing blocks this home` | Nothing to do. |

A key is `question <n>`, `check:<slug>` (its check failed), `row:<slug>` (refused or stuck), `left:<slug>` (its Result left work), or `wait:<slug>`.

### An aged wait

`wait:<slug>` is a backstop, a guard by design, for a wait no step of jbus has a remedy for, such as a run GitHub keeps queued with no job.
Each remedy stays the act of its own step (a rerun of a cancelled check, the fix message of a red check, a nudge to a crew), and the backstop only escalates what none of them moved.
Each code of `jmerge`'s reasons has one row of `clock.BOUNDS`: who clears it and how long a row may wait on it.

| Owner | Bound | Codes |
|---|---|---|
| a jbus act (jbus, `jmerge` or GitHub at work) | 60 minutes | a run in CI, a run with none started (`no-run`), a base merge GitHub was asked for, jmerge's batch and merged-tree guards |
| the crew or reviewer | 120 minutes | a review, findings, a `Proved:` or `Checked:` line, a red check, a conflict |
| the crew of the row ahead | 240 minutes | a row stacked on, carried by or merging after an open row |
| the home | 30 minutes | a queued run jmerge gave up on, a check cancelled twice, a queue jmerge cannot read, a reason no rule names |
| you | none | a code on the `hold` step: it is on what waits on you from its first pass |

A row whose `why` is a `wait` of `jmerge`'s, unchanged past its code's bound since the time `waits.jsonl` keeps for it, prints as `fix wait:<slug>` with the reason and the minutes, also while its crew is busy on other work.
The home's fixes of it count against `retry_cap` like any other key, and once they reach it the key is raised to you as a decision.
The view lists the same row as an `aged` wrong, for its home, and the catch-up takes it as a row that does not move.
`clock.held` reads the same owner: a thread at work keeps a hold from waking its home only where a crew can clear the hold's code.
