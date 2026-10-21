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

**A durable scout** is launched like a crewmate:

1. Write the request, `scouts/<slug>.md`, in the shape of `$T/scout-request.md`: read it first. When the research is for a task to hand out, its "Deliver" list asks for the crewmate's brief. Its `Playbook:` line is a row `a scout` runs whose kind of question this is, from what the block in "Handing a task to a crewmate" that prints a row for each playbook prints, or `none`. Then run the block in "Handing a task to a crewmate" that asks for the deeper version, and write what it says into the request. Its `Home:` line is as "Handing a task to a crewmate" says for a brief's: the scope's name for a scoped home, and no line for the root home.

2. Start the scout thread with `t3_thread_launch`. The request must be on disk before this call.

   ```json
   {
     "title": "scout: <slug>",
     "workspaceStrategy": {"type": "worktree", "baseRef": "<default branch>", "branch": "scout-<slug>", "startFromOrigin": true},
     "message": "/scout <slug>"
   }
   ```

   Before this launch, run `uv run --project "$T/.." jroles scout` with the block at the top. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the scout on the model the role map names. When it prints nothing, the call is the one above. Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line. When it exits 75 and prints no JSON, every instance of the role's pool is capped by a usage limit and the line on stderr says until when: make no launch, and say that line. A selection it prints names the instance of the pool it chose as its `instanceId`, and the launch is made with it as printed. Leave the project and modes out, and the model unless `jroles` printed one.

   ```json
   {
     "title": "scout: <slug>",
     "workspaceStrategy": {"type": "worktree", "baseRef": "<default branch>", "branch": "scout-<slug>", "startFromOrigin": true},
     "message": "/scout <slug>",
     "modelSelection": <model selection>
   }
   ```

   The branch is `scout-<slug>`, not the slug: the crewmate that follows takes the slug for its own branch and worktree. Everything else is as "Handing a task to a crewmate" says for its launch: the default branch, what is left out, a lost reply (look for `scout: <slug>`), and a session with no such tool (the user types `/scout <slug>`).
3. Add the line `Thread: <threadId>` to the request, with the block in step 3 of "Handing a task to a crewmate", and give the user the link: `[scout: <slug>](t3-thread://v1/<threadId>)`.

A durable scout gets the check of the machine before its launch, as a crewmate does.

A scout that finishes writes its report under `## Report` in its request and sends this thread one message. It never becomes the crewmate: the crewmate starts later, in a fresh thread, from the brief.

**Launch a scout's brief without showing it** when the user approved the plan entry it is for: an entry agreed in planning or answered on a page. Launch from step 2 of "Handing a task to a crewmate": the brief is on disk already, and the home does not rewrite it. Show it first, and wait for the user's word, in two cases only: the brief changes that entry's "Done when", or the task has no entry the user approved. A brief changes the list when it drops a check, weakens one, or adds an outcome the entry does not ask for. Checks that only say how an entry's line is proven change nothing. To show it, give the path, the lines that differ and what the brief rests on, in a few lines.
