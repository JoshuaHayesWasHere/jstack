# A fault outside the task

A fault a thread finds outside its task is a row of the queue, or it is nothing.
It is never a line of the Result, the Review or the Report, and never a change in this diff.
A fault with a known fix is queued, unapproved, as a row of its own.
A fault with no known fix, or one the queue already holds, is nothing: leave it.

Write the row's brief from `$T/brief.md`, as a home writes one, to a new file in `/tmp`.
Its slug is new, and its `Task:` says the fault and its fix.
Its `Decisions:` line begins `noticed in <slug>`, with the slug of the task that found it.
A fault in a scoped home's work has that home's `Home: <scope>` line, and the row is that home's.
Then run this in this worktree, with the block at the top and the new slug and the brief's file in place of the words in angle brackets:

```sh
uv run --project "$T/../source" jbus queue add '<new slug>' --priority 50 < '<the brief file>'
```

The row waits for its go as every row does: a standing rule or the user's go approves it, and its home launches it.
On `refused: <why>`, the brief lacks what the line names: fill it in and run it again.
Nothing else records the fault, and the home hears of it from the queue.
