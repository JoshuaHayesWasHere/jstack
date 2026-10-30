# A fault outside the task

A fault a thread finds outside its task is a row of the queue, or it is nothing.
It is never a line of the Result, the Review or the Report, and never a change in this diff.
A fault with a known fix is queued, unapproved, as a row of its own.
A fault with no known fix, or one the queue already holds, is nothing: leave it.

Write the row's brief from `$T/brief.md`, as a home writes one, to a new file in `/tmp`.
Its slug is new, and its `Task:` says the fault and its fix.
Its `Decisions:` line begins `noticed in <slug>`, with the slug of the task that found it.
Its `Home:` line names the home whose work has the fault, `Home: <scope>` for a scoped home's and `Home: root` for work that stands apart from the task and no scope owns, and the row is that home's.
A fault the filing task's own change caused, one that exists only because of that change, is instead a follow-up of it: its `Home:` line is the one in the filing task's brief, the filing task's home, and its slug starts with that home's prefix, as the filing task's slug does, so the row is never the root home's to re-file.
Then run this in this worktree, with the block at the top and the new slug and the brief's file in place of the words in angle brackets:

```sh
uv run --project "$T/../source" jbus queue add '<new slug>' --priority 50 < '<the brief file>'
```

The row waits for its go as every row does: a standing rule or the user's go approves it, and its home launches it.
On `refused: <why>`, the brief lacks what the line names: fill it in and run it again.
Nothing else records the fault, and the home hears of it from the queue.
