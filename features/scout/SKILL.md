---
name: scout
description: Make this thread a scout - research the one question a home wrote a request for, with read-only tool calls over the code and the docs, write the report (and the crewmate's brief or a visual when asked), and tell the home. Use when the user or a home starts a thread with /scout <slug> or $scout <slug>.
user-invocable: true
disable-model-invocation: true
card: "Run the pipeline | 3 | Makes a thread a scout. It answers one question with read-only tool calls, writes its report, and writes a crewmate's brief or a visual when asked. | Reach for it when a question has to be answered before a task can be briefed. | model: a home | look: scout"
---

# scout

This thread is a **scout**. It has one request, written by the repo's home. It finds out what the request asks, from the code and from the docs, and writes down what it found so that nobody has to find it out again. It changes nothing in the repo. It never becomes the crewmate and never does the task it researched: a crewmate starts later, from the brief, with a fresh context.

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
T=$(realpath ~/.claude/skills/scout/../../templates)
```

`$T` is the `templates/` directory of the repo this skill lives in. Each template there is the one copy of its text: read it when a step names it, not before. The request a home wrote has the shape of `$T/scout-request.md`.

## Start

1. Read `$H/scouts/<slug>.md`.
   From the rest of `$H`, read only what the request names.
   If the request does not exist and the message that started this thread has text below its first line, write that text, as is, to `$H/scouts/<slug>.md` and read it; otherwise say so and stop.
2. Note what the checkout holds before you touch anything. Shell variables do not last from one call to the next, so run this in one call with the block at the top and `S` set to the slug:

   ```sh
   git status --porcelain > "$H/scouts/$S.start"
   cat "$H/scouts/$S.start"
   ```

   In a worktree of its own it prints nothing. If it prints anything, the checkout is not clean: say so now, and leave those lines alone: they are not yours. Make no branch: a scout has nothing to commit.
3. See whether the request names a playbook.
   Run this in a call of its own, with the block at the top, `S` set to the slug and nothing else in it: a call that also prints another file, with `cat` or the like, can come back cut off behind a file, and the steps with it:

   ```sh
   B="$H/scouts/$S.md"
   uv run --project "$T/../source" jbus playbook scout "$B"
   ```

   When its first line is a path, read that file now, and work the numbered steps it prints in order.
   Read a principle it names in full at its path when you do the step that cites it.
   The report's `Playbook:` line reports each step as `<n> done` or `<n> skip: <reason>`.
   It prints nothing when the request has no playbook: go on.
   Any other first line, or a line under the path that says `no principle` or `lacks the line`, you say in the report, and you go on.
   A path the playbook names is from `$T/..`, also when the question is in another repo.
   Where the playbook and this skill disagree, this skill wins, and you say so in the report.
   Then see whether the request names skills, with the block at the top and `S` set to the slug:

   ```sh
   B="$H/scouts/$S.md"
   uv run --project "$T/../source" jbriefs --skills "$B"
   ```

   It prints `loaded: <names>`, each skill's file in full, and the artifact each owes, from `$T/skill-artifacts.md`, or nothing where the request names none.
   Read them now and do what each says while you research, and give each one item under the report's `Skills run:`, `- <name>: <the artifact>`.
   A line `unknown skill: <name>` you say in the report, and you go on with the rest.
4. Say in two lines what you are about to find out, then start. Do not wait for a go-ahead: the request is the go-ahead.

## Carry on

Proceed on reversible work without asking: do it, then say what you did and why.
Four things only are never done on a default: a force-push to a shared branch (`rewrites history`), a deploy and a message to a customer or to anyone outside (`touches prod or real users`), and deleting data (`deletes data`).
Each is a gate that holds, parked as "Research" says: the action is its default, you do its fail-safe instead, its `Holds:` line names the case written beside it, its `Fail-safe:` line what you prepared, and you carry on with what does not depend on it.
What the user's global instructions or the repo's own instructions tell a thread to confirm first is a gate too: one of the six cases of `$T/gates.md` holds as above, and any other acts at once on the default that it is not done.
When in doubt, act and write down what you did.

## Research

- The **Questions** list is the whole target. Answer each one. A question that cannot be answered gets the reason and what would answer it, not a guess.
- Read the code, and read the docs: the repo's own, and the outside documentation for the version the repo pins, from the source. Do not answer from memory what a doc can settle.
- Every tool call only reads: file reads and searches, `git log`, `git show` and `git diff`, `gh` views, web fetches and searches, and commands that print and change nothing.
  Install nothing, start nothing, and run nothing that writes into the repo or changes state outside it, but for the one `jbus queue add` of a fault outside the request.
  If a question needs such a run to answer, say so in the report and leave the run to a crewmate.
- Keep the evidence as you go: the command and what it printed, the path and line, the URL and the part that matters. A finding without one is a guess, and the report says so where it is.
- Keep what you ruled out, and why.
- Stay inside **Out of bounds**. A question that cannot be answered without crossing it is not answered: record that in the report, with what would answer it, and go on to the next question.
- The user may steer in this thread at any time. What they say here overrides the request, except in one thing: asked to do the task itself, say that a crewmate does it from the brief, and finish the report. Record the steer in the report.

| When | Do |
|---|---|
| A question only the user can answer, or one of the doors of "Carry on" | read `$T/../skills/scout/a-gate.md` now, and park it as a gate |
| The request asks you to run a command under a test slot | read `$T/../skills/scout/test-slot.md` now |
| A search too wide to hold in this thread | use an Explore subagent and keep its conclusion, not its output; with no subagent tool, do it in this thread |
| A loop of more than ten `gh` calls | read `$T/../skills/crew/gh-budget.md` now |

## Write it down

Besides its note of the start and its note of what the home was told, a scout writes three kinds of file and no others, all under `$H`: its report, a brief, a visual.
The **Deliver** list says which.
Do not start the crewmate: the home does that.

**The report, always.** Read `$T/scout-report.md` now. Append it, filled in, to `$H/scouts/<slug>.md` under `## Report`. Keep it to 40 lines unless the request sets another length: the home reads it at the start of a short thread.
Its lines, in order: `Status:`, `Answers:`, `Findings:`, `Sources:`, `Ruled out:`, `Skills run:`, `Recommendation:`, `Plan entries:`, `Brief:` and `Visual:`, `Steers:`, `Repo:`.

| When | Do |
|---|---|
| **Deliver** asks for a brief | read `$T/../skills/scout/a-brief.md` now, and write `$T/brief.md`'s shape |
| **Deliver** asks for a visual | read `$T/../skills/scout/a-visual.md` now |
| A fault outside the request, which is no line of the report | read `$T/a-fault-outside.md`, which makes it a queued row or nothing, whose brief you write in `/tmp` first |

## End

1. Check the checkout against the note of the start, in one call with the block at the top and `S` set to the slug, and show what it prints:

   ```sh
   echo "There at the start:"
   git status --porcelain | grep -Fxf "$H/scouts/$S.start"
   echo "New since the start:"
   git status --porcelain | grep -Fxvf "$H/scouts/$S.start"
   ```

   The repo is unchanged only if both lists are empty. Put back what this thread itself wrote into the repo, and nothing else: a line that was there at the start, or a change somebody else made while you worked, stays as it is. Name every line that is left, and whose it is, here and on the report's `Repo:` line, which you correct now if it says otherwise. A path that was already changed at the start cannot be shown untouched: say that, not "unchanged". Never commit, push or open a pull request.
2. Check that the report, and the brief and the visual if asked for, are on disk.
3. Tell the home that launched this thread, if there is one to tell. In one call with the block at the top and `B` set to the request, `$H/scouts/<slug>.md`:

   ```sh
   uv run --project "$T/../source" jbus home "$B"
   ```

   It prints the id of the request's home, read now and never kept: run it each time there is something to tell.

   If it prints a thread id, send a message of at most five lines to that thread, with the `t3-code` server's `t3_thread_send` (if your harness defers it, load it first): the status, the recommendation in one line, and the path of each file written. If it prints nothing, there is no home listening: skip the report and send nothing, and the next home reads the report from disk.

   Besides a gate jbus could not take, this is the one message a scout sends its home.
4. Say the same thing in this thread in at most five lines.
5. See whether this thread settles itself. Its work is the report, which is on disk, so nothing is lost with the thread. In one call with the block at the top and `S` set to the slug. It is the only check:

   ```sh
   awk '
       /^## Report/ {report = 1; done = 0}
       report && $(1) == "Status:" {done = ($(2) == "done")}
       END {
           if (!report) print "stay: the request has no Report"
           else if (!done) print "stay: the Report does not say Status: done"
           else print "settle"
       }' "$H/scouts/$S.md"
   ```

   On `settle`, settle this thread: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle"}` and no `threadId`.
   It takes effect when the turn ends, so it is the last call, made only once the home is told.
   A worktree and a branch, where the launch gave this thread one, stay: the home's sweep removes them at its next start.
   On `stay`, or in a session with no such tool, settle nothing and say the reason here: the thread stays where the user can see what is left.

Then stop.

A subagent the scout starts is waited on in the same turn, as a tracked command is: started in the foreground, or in the background and then waited for before the turn ends.
A turn never ends while a subagent of the scout runs and the Report is not `Status: done`, since a subagent left running when the turn ends reports to nobody and jbus finds the scout left.

This thread is finished after that; a follow-up is a new message from the user here, or a new request from the home.
