# What the Chef is sent and may run

The Chef is the T3 Code thread behind a webhook of jbus ([The Chef](../chef.md) says how to make one).
This page is its contract: the body jbus POSTs to it, and the commands it may run.

## What it is sent

`jbus` POSTs JSON to the project's `webhook_url`, at most once in five minutes, and only when an event for you waits.
The Chef behind the top-level `webhook_url` is the monitor of every project.
It gets every project's events for you, each with its `project` field.
That includes the events of a project that has a Chef of its own.
A project with no `webhook_url` and `webhook_key` of its own has only the top-level Chef:

```json
{
  "kind": "events",
  "say": ["demo: gate alpha: question 3: tea or coffee?"],
  "events": [
    {
      "project": "demo",
      "slug": "alpha",
      "event": "gate",
      "line": "gate alpha: question 3: tea or coffee?",
      "text": "## Gate 3: tea or coffee?\nStatus: open\n...",
      "loud": "user",
      "say": "demo: gate alpha: question 3: tea or coffee?"
    }
  ]
}
```

| Field | Holds |
|---|---|
| `kind` | `events`. |
| `say` | The lines for you, in order, each beginning with its project's name. The Chef passes each one on. |
| `events[].project`, `events[].slug` | The project in the config, and the task. |
| `events[].event` | The kind: `alert`, `gate`, `sign-in`, `stall` or `waiting`. |
| `events[].line` | The event in one line. |
| `events[].text` | The whole text when there is one, such as the lines of a question. |
| `events[].loud` | `user` or `quiet`. An event with `user` also has its own `say`. |

[Events and the webhook](events-and-the-webhook.md) has the kinds at each level.
jbus posts a project's webhook its `user` events, and no quiet events.

Each POST carries the project's `webhook_key` in two headers, `Authorization: Bearer <key>` and `X-Automation-Key: <key>`. Its `User-Agent` is `jbus`.

## What it may run

The Chef runs `jbus queue` and nothing else that changes state.

| Command | What the Chef does with it |
|---|---|
| `jbus queue show` | Reads the table, and what waits on you above it. |
| `jbus queue add <slug> --priority <n> [--depends <slugs>]` | Adds a row, with the brief on stdin. |
| `jbus queue approve <slug> --sha <sha12> --message <thread id>/<message id>` | Records your go for the brief you were shown. The Chef runs it only after you said yes to that brief, and names the message you said it in. |
| `jbus queue hold <slug>` | Takes a row's approval back. |
| `jbus queue apply` | Runs a batch of those three verbs from stdin, all or none. |

The Chef never approves by itself.
The `approve` command above takes no name and no time.
Instead it names your own message, which jbus reads from T3 Code, or a word or an answer that jbus keeps.
jbus writes who ran the command and when.
`--sha` ties the go to one text of the brief.
One more basis, `--rule <n> --follows <parent slug>`, is not your word for the row.
A home uses it for a follow-up to a row you approved, and `jbus queue add` uses it itself for a row that its follow-up rule names a follow-up ([the queue](the-queue.md)).
jbus does not check who runs the command, and it records who did.
So only the Chef's own rule keeps the Chef from using this basis.
The row then records that you did not give your word for it, and the digest's `by_rule` counts those rows so the Chef can tell you.
[The queue](the-queue.md) has the format of a batch.

The Chef does not merge, does not run `jmerge --accept`, and does not edit a brief after your go.
A pull request that `jmerge` holds is yours.
The `waiting-on-user` line holds the command, and you run it.
