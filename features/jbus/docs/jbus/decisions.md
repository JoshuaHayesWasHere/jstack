# Decisions

No bot outside watches the homes or the queue.
Each home clears its own blockers each time it wakes, with `jbus clear` ("Clearing its own blockers" in the home skill), and raises to you only what you have to decide.
Who pages you is the relay: jbus posts a `decision` to its webhook, the relay sends it on to Sous Chef (the agent behind `GROK_WEBHOOK_URL`, the brief's Chief Keef), and Sous Chef pages you ([The relay](the-relay.md)).

A decision is one `user` event of the kind `decision`, sent once for each blocker, whoever raises it again.
Its line is `decision <slug>: <what to decide>. Reply: "<reply>"`, and the reply is a line you can send as it is: it reaches the home as your word ([Your word to a home](your-word-to-a-home.md)).
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
| `cleared question <n>: took its default, ...` | The question was open `--after` minutes (30 with none) and needs no decision of yours. The thread acted on its default when it asked, so the home takes it: `jbus clear` logs the gate in the home's `gates.md` as answered by the home, and the question closes from there. Nothing is posted, and a later answer of yours still replaces it. |
| `decision question <n>: ...` | You have to decide it, and the pass raises it. |
| `fix <key>: ..., try <n> of <cap>` | The home briefs a fix with `Fix of:` and `When green:`, and queues it. |
| `wait <key>: ...` | A fix of the key is queued and not over. |
| `decision <key>: ... had <n> fixes ...` | The key had its cap, and is raised. |
| `nothing blocks this home` | Nothing to do. |
