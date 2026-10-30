## Sending a scout

Before writing a brief, ask whether it can be written from what `$H` holds and what the user said. If it can, the home writes the brief itself and no scout goes out. If it cannot be written without research, in the code or in the docs, send a scout.

There are two kinds:

| | Light | Durable |
|---|---|---|
| What it is | the `Explore` agent, run inside this thread | `/scout <slug>` in a thread of its own, titled `scout: <slug>` |
| Pick it when | the home can ask it in a sentence or two, and the answer fits in about 30 lines | the research spans several areas, needs outside docs as well as code, needs anything run, or the user wants to watch |
| Who writes the brief | the home, from the answer | the scout, when the request asks for one |

When in doubt between the two, any one of the durable column's conditions decides for durable.

**A light scout.** Ask the `Explore` agent for the conclusion with its paths and lines, not for file contents, and write the brief from what comes back. Or, with no subagent tool, do it in this thread and keep only the conclusion. The brief may carry that answer in its `Read:`, `Change:` and `Rests on:` lines, so the crewmate does not look for it again. If the answer does not fit in about 30 lines, or leaves the brief still unwritable, send a durable scout instead of asking again.

**A durable scout** is a row of the queue, as a crewmate's task is:

1. Write the request, `scouts/<slug>.md`, in the shape of `$T/scout-request.md`: read it first. When the research is for a task to hand out, its "Deliver" list asks for the crewmate's brief. Its `Playbook:` line is a row `a scout` runs whose kind of question this is, from what the block in "Handing a task to a crewmate" that prints a row for each playbook prints, or `none`. Then run the block in "Handing a task to a crewmate" that asks for the deeper version, and write what it says into the request. Its `Home:` line is as "Handing a task to a crewmate" says for a brief's: the scope's name for a scoped home, and `Home: root` for the root home.
   A scout that waits on another row's work has a `Builds on: <slug>: <what it uses>` line for each.
   Its `Out of bounds:` line also says: no loop of more than ten `gh` calls until `uv run --project "$T/../source" jbus budget --calls <n>` says `ok`, and none while it says `held`.
   GitHub's API allowance is one for jbus, `jmerge` and every thread, and a scout's fetch for each job once spent all of it and stalled every merge for an hour.
2. Queue it: `jbus --project <project> queue add <slug> --priority <n> --entry <entry> [--depends <slug>,...] < scouts/<slug>.md`.
   A text with a `Request:` line and no `Task:` line is a request, so the row is a scout's, and `add` refuses one with a crewmate's line (`Size:`, `Pull request:`) or not in the template's shape.
   It is approved as any row is, the entry's go included, and waits on its `--depends` as any row does.
   A pass launches it as `scout: <slug>` with the message `/scout <slug>`, in the project's own checkout and with no branch, writes the request back to `scouts/<slug>.md` with its `Thread:` line, and marks the row done once its Report says `Status: done`.
   `jbus queue show` lists it with `scout` in its `role` column, and the view shows it.
   Once its Report says done, `jbus queue add <slug>` of the brief it delivered at `tasks/<slug>.md` makes the row the crewmate's, with no go.

Anyone who is not this home, an expert bot included, asks for a durable scout the same way.
A durable scout gets the check of the machine before its launch, as a crewmate does: the pass makes it.

A scout that finishes writes its report under `## Report` in its request and sends this thread one message. It never becomes the crewmate: the crewmate starts later, in a fresh thread, from the brief.

**Launch a scout's brief without showing it** when the user approved the plan entry it is for: an entry agreed in planning or answered on a page. Launch from step 2 of "Handing a task to a crewmate": the brief is on disk already, and the home does not rewrite it. Show it first, and wait for the user's word, in two cases only: the brief changes that entry's "Done when", or the task has no entry the user approved. A brief changes the list when it drops a check, weakens one, or adds an outcome the entry does not ask for. Checks that only say how an entry's line is proven change nothing. To show it, give the path, the lines that differ and what the brief rests on, in a few lines.
