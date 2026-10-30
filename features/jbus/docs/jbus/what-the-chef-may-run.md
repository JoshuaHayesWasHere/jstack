# What the Chef may run

The Chef is an agent of yours, outside a home, that keeps the queue for you ([The Chef](../chef.md)).
This page is its contract: the commands it may run.

The Chef runs `jbus queue` and nothing else that changes state.

| Command | What the Chef does with it |
|---|---|
| `jbus queue show` | Reads the table, and what waits on you above it. |
| `jbus queue check [<slug>]` | Checks a brief on stdin as `add` would, and writes nothing. |
| `jbus queue add <slug> --priority <n> [--depends <slugs>]` | Adds a row, with the brief on stdin. |
| `jbus queue approve <slug> --sha <sha12> --message <thread id>/<message id>` | Records your go for the brief you were shown. The Chef runs it only after you said yes to that brief, and names the message you said it in. For a brief whose `Holds:` line names a door, it parks a gate for you instead, unless it runs as `jbus --as user queue approve ... --message ...` on your own message. |
| `jbus queue hold <slug>` | Takes a row's approval back. |
| `jbus queue apply` | Runs a batch of `add`, `approve`, `hold` and `remove` lines from stdin, all or none; the Chef uses only the first three. |

The Chef never approves by itself.
The `approve` command above takes no name and no time.
Instead it names your own message, which jbus reads from T3 Code, or a word or an answer that jbus keeps.
jbus writes who ran the command and when.
`--sha` ties the go to one text of the brief.
One more basis, `--follows <parent slug>`, is not your word for the row: a follow-up of approved work needs no new approval, and its ground is the parent's go.
A home uses it for a follow-up to a row with a go, and jbus uses it itself, in `jbus queue add` and on each pass, for a row that its follow-up rule names a follow-up ([the queue](the-queue.md)).
jbus does not check who runs the command, and it records who did.
So only the Chef's own rule keeps the Chef from using this basis.
The row then records that you did not give your word for it, and the digest's `by_rule` counts those rows so the Chef can tell you.
[The queue](the-queue.md) has the format of a batch.

The Chef does not merge, does not run `jmerge --accept`, and does not edit a brief after your go.
A pull request that `jmerge` holds is yours.
The `waiting-on-user` line holds the command, and you run it.
