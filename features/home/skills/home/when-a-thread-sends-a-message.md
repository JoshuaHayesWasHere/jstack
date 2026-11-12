## When a thread sends a message

The threads this home sent out write what they did to disk: a crewmate its `## Result`, a reviewer its `## Review`, a scout its `## Report`.
Disk is the record.
A message to this thread is an interrupt.
The home plans, assigns and starts, so what it hears is planning: what finishes the work is jbus's to read, and reaches this thread only while `$H/home-thread` holds an id, which is the test the crew skill makes in its "Telling the home", though jbus merges either way ("Merging a pull request that is ready").
These are all of them, and the last column says on which state of that file each is sent:

| The message | From | Sent when | Sent on |
|---|---|---|---|
| `<slug>: <pull request url> at <head> is fixed and green` | a crewmate | its pull request is reviewed, the findings are handled, and every check has passed: the merge step reads what jbus did of it | an id in `home-thread` |
| the task ended with no pull request | a crewmate | it wrote a Result that names none | both |
| `<slug>: <pull request url> at <head> is green and has no review` | a crewmate | every check has passed and no reviewer will come: the brief says `Review: none`, or the session could launch none. It is never ready, so end the turn with `decision local <slug>: ` and that it waits for their word ("How a turn ends") | an id in `home-thread`; with none it is a gate |
| the report is written | a scout | at its End, once | both |
| a review's findings | jbus | only when the brief has no `Thread:` line, so `jbus.reviewed` sends the home the notice a crewmate would get, and only when `jmerge` says a line is owed | both |
| `<slug>: gate`, then the gate's lines | a crewmate or a scout | it took a default on a question only the user can answer, carried on, and `jbus gate` could not take the gate: no `jbus`, or no project for the repo | both |
| `jbus: this is <name>'s own word, said <time> and carried to this home by jbus.`, then the words | jbus | the user said it elsewhere and `jbus word` carried it: act on it as said here ("The user's word, carried by jbus") | both |

One more comes from jbus, whatever `home-thread` holds, for a row with no commits on its branch: `jbus: <slug> ended with something left, and it is this home's to close.`, with the pull request and whether it merged, the `Left:` line whole, and each question the slug asked with its answer.
Read the last Result of `$H/tasks/<slug>.md` and those answers, then end it one of three ways.
Where something is still to do, write a brief for what is left with `Follows: <slug>` in its head, and queue it as a follow-up.
Where the rest is already another row's, add `Follows: <slug>` to the head of that row's brief and queue it again with `jbus queue add`.
The line gives a new row its go by the follow-up rule, on the closed row's go ("A follow-up approved by the follow-up rule"), and a row queued again keeps the go it had.
Then, or at once where nothing more is wanted or the rest is somebody's outside the queue, append `## Result, follow-up (<date>, <the reason>)` to `$H/tasks/<slug>.md`, the brief of the task that ended, with four lines: `Status: done`, `Branch: <its branch>   Pull request: none`, `Outcome: <how it ended>` and `Left: none`.
The outcome is `carried by <slug>` for the follow-up or the row that carries the work on, `nothing to change, <why>` where the task found nothing to do, and `dropped, <why>` where the work is not wanted.
Only those four end a row whose brief asks for a pull request: one with no `Outcome:` line stays left, since how it ended is what the store counts it by (`jbus.outcome`).
Send the user nothing about it: a question only they can answer is a gate ("Gates"), and the row stays this home's while it is open: jbus tells no other home of it.

A row whose branch has commits of its own gets `jbus: <slug> ended with something left on its branch, and it is this home's to see to.` in place of that message, and is not carried on under a new brief.
jbus launches it again on its own slug, branch and worktree, with a `Resume:` line naming the cause, once for each cause that clears: what its last Result's `Waits on:` line names has landed, a review with findings was written after its last Result, or its brief has a new go.
Where it waits on one of those, leave it.
Where it waits on merges its Result does not name, append `## Result, follow-up (<date>, <the reason>)` with `Status: paused`, `Waits on: <each row's slug, or #<n> for a pull request with no row>`, `Branch: <slug>   Pull request: none` and `Left: <what is left>`; where its `Where:` or `Done when:` is too narrow, widen them in `$H/tasks/<slug>.md` and queue it again with `jbus queue add`: its new go launches it.
To steer a crew still out to wait on a merge, at any status, write the line into its last Result with `jbus brief set --result "$H/tasks/<slug>.md" 'Waits on:' <the slug or #<n>>`, never as a `Steers:` line's prose: the brief lint refuses that, and jbus cannot wake the crew on it.
Where nothing more is wanted, close it with the four lines above, `dropped, <why>` or `nothing to change, <why>`.

Nothing is sent when a pull request opens, when a review is written or when its findings are handled.
A reviewer's findings go into the brief, and jbus tells the crewmate of them only when `jmerge` says the crewmate owes a line.
A thread with a question only the user can answer takes a default, carries on and pipes the gate to `jbus gate <slug>`, which keeps it as a numbered question: the home reads the open ones from jbus, shows them, and closes one with the user's answer, which jbus carries back when it differs ("Gates").
With `home-thread` empty no line about a pull request is sent here: jbus reads the brief and the pull request on each pass, and the merge step prints what it found.
Only a thread at one of the four pauses of "Carry on" asks in its own thread and waits: it shows as `waiting` in T3 Code, which is what reaches the user.
The home does not poll for any of it and runs no watch at all, on its state directory, on GitHub or on its threads: jbus watches it, and nudges a home that stays quiet with work out (`jbus.children`).
What it has to plan on arrives as a message, and the rest it reads when the user asks for status and at the start of the next home: the gates from jbus ("Gates"), the results from disk.

On each message, do this without waiting for a word from the user.

First run the block of "What waits on the user": a turn this wake ends with something for the user opens with what it printed.

1. Read what landed: the last result, the review or the report the message is about, from disk.
   Not the thread that sent it.
   A gate that came as a message is one jbus could not take: do what the end of "Gates" says for it.
   A line `Gate: question <number>` in what you just read is a question jbus holds, and asks nothing here.
   The lines of a gate itself in a Result or under "Findings" in a Report are from a thread that had no home to send them to, or from one that wrote them under the skill as it was: hand them to jbus with the block of "Ask one", under that thread's slug, and only on `not asked` do the same for it as for one that came as a message.
2. Run the merge step of "Merging a pull request that is ready".
   It runs no `jmerge`, and prints what jbus's `jmerge` merged since this home last read the log, then its last line for each open pull request.
   Then clear this home's blockers, as "Clearing its own blockers" says: a start runs this step too, so every wake clears them.
3. Run `jbus plan` and close each entry it prints `finished: close it` for ("Planning").
   Write no status: the plan holds none.
   Then queue each approved entry's next row with `jbus queue add --entry <entry>`, with `--depends` for what it waits on.
   Launch nothing by hand: jbus's pass launches a row once it is approved and what it depends on has merged, checks `room` first, and tells the files two briefs out share.
4. End the turn by "How a turn ends": what landed, what was merged, what was launched with its link, what was parked, and what waits and why are its lines, and the user hears only a decision or a stop among them.
   When nothing is left planned or out, that is a `handled:` line, told with the open questions when the user asks for status ("Gates").

If a result says the task is not done, the fix is a new message from the user in the crewmate's own thread, or a new brief. The home does not take the task over.

When the user asks for status, open the reply with what the block of "What waits on the user" prints.
Then run the merge step of "Merging a pull request that is ready" and relay what it printed, and for a brief with no result yet, one `t3_thread_list` call gives the state of the crewmates still out: `running`, `waiting` (it is at one of the four pauses and has asked in its own thread), `failed` or `interrupted`.
Report that state with the thread's link.
No message brought what finished since: run the block of step 4 of "When a home starts" and read the last result of each brief it prints that this thread has not read.
Then run the block of "Show the open ones" ("Gates") and show what it prints.
Then show each `local` decision or stop this home told and nothing has ended yet ("How a turn ends"), with the block at the top and the block that finds this home:

```sh
command grep -E '^(decision|stop) local ' "${M:?run the block that finds this home first}/told" 2> /dev/null ||
    echo "no local decision or stop is open"
```

The root home then runs the block of "Scoped homes" that reads the scopes.
Do not read a crewmate's timeline unless the user asks what it is doing.
To see what a thread last said, after a jbus wake or when the user asks, run `jbus thread <slug>`: it prints the thread's status, its last run, its pull requests and its last message, cut at 2,000 characters, from T3 Code's own store, in place of `t3_thread_read`.

Once a week the root home's status also says where changes collide.
Run this with the block at the top, in the main checkout: when the stamp in `$H` is over 7 days old, or missing, it prints the top 5 files of the last week's three tables (merged pull requests, pairs open at once, rebases that dropped lines) and stamps the run, and otherwise it prints nothing.
Show what it prints.
A file high in all three is one to split, and never a reason to hold a launch.

```sh
if [ -z "$(find "$H/hot-files.stamp" -mtime -7 2> /dev/null)" ]; then
    J=$(git -C "$T/../source" rev-parse --show-toplevel 2> /dev/null || git -C "$T" rev-parse --show-toplevel) &&
        uv run --project "$J" "$J/scripts/hot_files.py" --since "$(perl -MPOSIX -e 'print strftime("%F", localtime(time - 7 * 86400))')" --home "$H" --top 5 &&
        touch "$H/hot-files.stamp"
fi
```

Last, a status reply opens with the board's two headlines and ends with the board itself, its link and its picture, for this home's scope.
A `/ketchup` in this thread ends the same way.
Run this with the block at the top and the block that finds this home:

```sh
route='#/' scope=root
if [ "${M:?run the block that finds this home first}" != "$H" ]; then
    scope=${M##*/}
fi
if ! link=$(uv run --project "$T/../source" jbus link 2> /dev/null); then
    echo "no jview link: jbus has no page for $R"
else
    view=${link%%#*}
    [ "$scope" = root ] || route="#/?home=${link##*#/}/$scope"
    curl -fsS --max-time 5 "${view%/}/panel/pipeline.json" 2> /dev/null | jq -r '
        .data
        | (.stages | map({(.key): .name}) | add) as $name
        | "first: "
          + (if (.stuck.still // 0) > 0 then "Most stuck: \($name[.stuck.stage] // .stuck.stage), \(.stuck.still) of \(.stuck.count)." else "Every row is moving." end)
          + (if .longest_wait then " Waiting longest: \(.longest_wait.slug), \($name[.longest_wait.stage] // .longest_wait.stage) since \(.longest_wait.since), \(.longest_wait.cause)." else " No row waits." end)' 2> /dev/null
    shot=$(uv run --project "$T/../source" jbus view-shot "$route" --out "jview-flow-$R-$scope.png" 2> /dev/null | tail -n 1)
    t3=$(uv run --project "$T/../source" python -c 'import jbus; print(jbus.load().server)' 2> /dev/null)
    case $shot in
    /*.png) [ -f "$shot" ] && [ -n "$t3" ] && echo "attach: $shot $(wc -c < "$shot" | tr -d ' ') $t3" ;;
    esac
    echo "$view$route"
fi
```

Make the `first:` line, without its `first: `, the reply's first line, so the words name what the picture shows.
It names a stage only when a row of it is not moving, and otherwise says what the board's head says then, `Every row is moving`.
An `attach: <path> <bytes> <origin>` line is the picture, sent to this thread, where the user reads the reply, with three calls of the `t3-code` server (if your harness defers them, load them first).
The origin is that server's, the `server` of jbus's config, and with none the block prints no `attach:` line.
First `t3_attachment_prepare_upload`, with an `upload` of type `image`, the path's file name as its `name`, `image/png` as its `mimeType`, and the bytes as its `sizeBytes`.
Then POST the file's bytes, as they are, to the `relativeUrl` it returns on that origin: `curl -fsS -X POST -H 'Content-Type: image/png' --data-binary @<path> '<origin><relativeUrl>'`.
Last `t3_thread_send_attachments` with that `attachmentId`, the same name, type, MIME type and size, and no `threadId`, which sends it to the thread that calls it, this one.
A call of the three that fails sends no picture, and the reply says nothing of it.
Make the last line the reply's last line.
With no `first:` or no `attach:` line, the reply goes without it and says nothing of it.
On `no jview link`, the reply ends with no link and does not say why.
