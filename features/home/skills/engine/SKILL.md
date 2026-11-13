---
name: engine
description: "Run one engine pass in a repo's root home: read the queue, what waits on the user and the open pull requests, clear what stalls where a fix is reversible, and end in one verdict, Quiet, Moving or Call. Use for /engine, \"run the engine\", \"engine pass\", /engine schedule and /engine stop."
card: "Run the pipeline | 1 | Runs one engine pass in a root home: it reads the queue, what waits on the operator and the open pull requests, clears what stalls where a fix is reversible, and ends in a verdict, Quiet, Moving or Call. | Reach for it as the root's scheduled task, or to run one pass by hand, and /engine schedule to set the root's schedule. | op: the operator; cmd: /engine"
---

# engine

One pass of the engine, in the repo's root home.
It runs on top of the home skill (`features/home/skills/home/SKILL.md`) and the root's skill (`features/home/skills/root/SKILL.md`): follow both, with their blocks and their gates.
This file holds only what a pass adds to them, and the two places it overrides them: a pass may report a Moving verdict, and a pass asks no go of its own.
`/engine` is the go for one pass.
`/engine schedule` and `/engine stop` run no pass: they run "The schedule".

## Only in a root home

Run this in one call after the home skill's block at the top and the block that finds this home:

```sh
if [ -n "${M:-}" ] && [ "$M" = "${H:-}" ]; then
    echo "root: run the pass"
else
    echo "not a root home: the engine runs only in a repo's root home, so this pass does nothing."
fi
```

On `not a root home:` or `no home:`, say that one line and stop.

## The pass

1. **Read a changed skill again.**
   After a jbus line `jbus: pull request <n> merged and changed these skills: <names>`, read each skill it names again before you follow it.
   The copy in this thread's context is the text from before the merge.
2. **Read where things stand**, each in its own call:
   - `jbus queue show`, the open rows with why each waits.
   - The home skill's "What waits on the user" block, which runs `jbus needs`.
   - `gh pr list --state open --json number,headRefName,mergeable,statusCheckRollup`.
3. **Find what stalls**: each row whose why reads the same as on the last pass, and each pull request that is red, in conflict, or has no check run.
   The last pass is this thread's last `/engine` turn.
   For each, find the cause.
4. **Clear it.**
   - A cause with a reversible fix on the "May" list: make the fix.
   - A failed check: before you rerun it, look for the same test failing on other branches.
     Run `gh run list --status failure --limit 30 --json databaseId,headBranch,name`, then `gh run view <id> --log-failed` on the runs of other branches.
     The same test failed elsewhere: it is a flake, so rerun the job with `gh run rerun <id> --failed`.
     It failed only on this branch: the failure is the branch's own, and a rerun only fails again.
     Its crew fixes it, since jbus tells a crew that its pull request is red.
     Where the crew has stalled, tell its child home.
   - A cause you cannot find from the queue, jbus and `gh`: send a scout by the home skill's "Sending a scout".
     The scout's request is a file under `$H/scouts/`, so it outlives this thread.
   - A stall whose cause you also found on an earlier pass: queue a row in the self-heal child (in jstack `self-heal`, and `uncategorized` in a repo with no such child) by the root's "Queue a row in a child".
     The fix of a stall that repeats is code, not one more rerun.
5. **Pass on a finished scout report** in this pass, not the next: brief its row, or put its finding in the verdict.
6. **Read the line before you tell.**
   Before you tell the user the state of a row, a pull request or a check, read the line that holds it: the brief's last `Status:` line, the queue row, or the check run.
   Never infer a state from a count of words or lines: a count says how much text there is, not which state a line holds.
7. **End in a verdict** ("The verdict").

## May

With no new word from the user, a pass may:

- approve a follow-up row with `jbus queue approve <slug> --follows <approved slug>`;
- give a go again, on the standing word for goes, for a row whose brief changed after its go, once it judged the change: `jbus queue approve <slug> --word <the standing word's id>`;
- waive a `Done when` line it judged by the root's "Judge a waiver" with `jbus waive <slug> <line number>... --as root --from <the root's home-id> --reason <why the line need not hold> --undo <how the merge is undone>`;
- rerun a failed CI job that step 4 found to be a flake;
- tell a child home with `jbus tell`, by the root's "Tell a child";
- remove a dead row, one with nothing left to land, on the user's standing word for such rows, as the home skill's "How a turn ends" does: `jbus queue remove <slug> --message <thread id>/<message id>`;
- stop a row that a later word of the user's superseded, with `jbus queue hold <slug>`.

## Never

A pass never:

- runs `gh pr merge` by hand: `jmerge` merges;
- force-pushes a shared branch;
- deploys;
- deletes data;
- sends a message outside: to a customer, a channel, or an issue tracker;
- fetches several branches at once (`git fetch --all` or a fetch of many refs);
- sends `t3_thread_send` to a child home's crew;
- touches `~/.config/jbus`.

## The verdict

The pass ends in one of three verdicts.
A Moving or a Call report opens with its verdict's word, and has only the lines below.

- **Quiet**: nothing changed since the last pass, and every call is one the user was already told.
  Write nothing: no recap, and no line that says nothing changed.
- **Moving**: something moved, and no call is new.
  In at most five lines: what merged, what started, and what the root fixed, each a line.
  This overrides the home skill's "How a turn ends", which tells only a decision or a stop.
- **Call**: a choice only the user can make, such as a lost go, a new plan entry, or anything a revert does not undo.
  Run each call through the block of the home skill's "How a turn ends" as a `decision` line, so that a call is told once.
  Its `silent` makes the verdict Moving or Quiet, and its `say:` lines are the report, after the word Call.
  A call names its row as `<slug>: line <n>` where it is about a `Done when` line, and never by a pull request's number, since `jbus waive` binds a reply only to a message that named the row and its line.
  Each call has three parts: the pick, its evidence and its risk.
  For example: `alpha: line 4, waive it: the test takes 15.2 s where the line asks for 15, and a revert undoes the merge`.
  A Call can also report what moved, in the Moving lines after the calls.

## The schedule

The root runs the engine from one T3 Code scheduled task, bound to its thread, whose prompt is `/engine` and which runs every 900000 ms.
`/engine schedule` makes that task, and `/engine stop` deletes it.
Neither runs a pass.

1. Run the block in "Only in a root home".
2. Call the `t3-code` server's `list_scheduled_tasks` with no arguments (if your harness defers it, load it first).
   Save its whole reply as a file, or take the file your harness saved it to when the reply was too long to show.
3. Run this with the block at the top and the block that finds this home, with `schedule` or `stop` and the file's path in place of the words in angle brackets:

   ```sh
   DO='<schedule or stop>'
   F='<the reply file>'
   if [ "$DO" != schedule ] && [ "$DO" != stop ]; then
       echo "not read: put schedule or stop in place of <schedule or stop>"
   elif [ -z "$ME" ]; then
       echo "not known: put this thread's id, from t3_thread_configure, in place of <threadId>"
   else
       jq -r --arg me "$ME" --arg do "$DO" '
           if (.tasks | type) == "array" then . else error("no tasks") end
           | [.tasks[] | select(.boundThreadId == $me)
               | select(.prompt == "/engine" or ((.title // "") | endswith("run the engine")))] as $engine
           | [$engine[] | select($do == "schedule" and .prompt == "/engine" and .enabled == true
               and .schedule == {"type": "interval", "everyMs": 900000})][0] as $keep
           | (if $do == "schedule" and $keep == null then ["make: no engine task runs in this thread every 900000 ms"] else [] end)
             + [$engine[] | select(.scheduledTaskId != $keep.scheduledTaskId) | "delete \(.scheduledTaskId): \(.title)"]
             + (if $keep == null then [] else ["keep \($keep.scheduledTaskId): \($keep.title)"] end)
           | if length == 0 then "none: no engine task runs in this thread" else .[] end' "$F" 2> /dev/null ||
           echo "not read: put the path of a file that holds the whole reply of list_scheduled_tasks in place of <the reply file>"
   fi
   ```

4. Do what each line says, in the order printed:
   - `make`: call the `t3-code` server's `schedule_task` with `{"title": "<repo> root: run the engine", "prompt": "/engine", "schedule": {"type": "interval", "everyMs": 900000}, "bindToCurrentThread": true}`, `<repo>` being `$R`.
   - `delete <id>`: call the `t3-code` server's `delete_scheduled_task` with `{"scheduledTaskId": "<scheduledTaskId>"}`.
   - `keep <id>`: that task is the engine's schedule, so call nothing.
   - `not read:` or `not known:`: fill in what the line names, and run the block again.
5. List the tasks again, and run the block again.
   After `schedule` it prints one `keep` line, and after `stop` it prints `none`.
   Where it still prints `make` or `delete`, a call was refused: tell the user the id and what the call answered, and make no second call.
6. Tell the user the line the block printed last, and nothing more.
