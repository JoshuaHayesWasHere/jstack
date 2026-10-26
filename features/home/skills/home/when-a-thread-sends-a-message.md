## When a thread sends a message

The threads this home sent out write what they did to disk: a crewmate its `## Result`, a reviewer its `## Review`, a scout its `## Report`.
Disk is the record.
A message to this thread is an interrupt.
The home plans, assigns and starts, so what it hears is planning: what finishes the work is jbus's to read and whoever the project's webhook is to hear, and reaches this thread only while `$H/home-thread` holds an id, which is the test the crew skill makes in its "Telling the home", though jbus merges either way ("Merging a pull request that is ready").
These are all of them, and the last column says on which state of that file each is sent:

| The message | From | Sent when | Sent on |
|---|---|---|---|
| `<slug>: <pull request url> at <head> is fixed and green` | a crewmate | its pull request is reviewed, the findings are handled, and every check has passed: the merge step reads what jbus did of it | an id in `home-thread` |
| the task ended with no pull request | a crewmate | it wrote a Result that names none | both |
| `<slug>: <pull request url> at <head> is green and has no review` | a crewmate | every check has passed and no reviewer will come: the brief says `Review: none`, or the session could launch none. It is never ready, so end the turn with `decision local <slug>: ` and that it waits for their word ("How a turn ends") | an id in `home-thread`; with none it is a gate |
| the report is written | a scout | at its End, once, and once more only if a page's feedback changed the report | both |
| a review's findings | a reviewer | only when the brief has no `Thread:` line to send them to | both |
| `<slug>: <pull request url> has a conflict, and it is a link of a stack` | a crewmate | GitHub reports a conflict on a link, which its crewmate never rebases by itself: send it the line of "A stack the user lands" | an id in `home-thread`; with none it is a gate |
| `<slug>: gate`, then the gate's lines | a crewmate or a scout | it took a default on a question only the user can answer, carried on, and `jbus gate` could not take the gate: no `jbus`, or no project for the repo | both |
| `jbus: this is <name>'s own word, said <time> and carried to this home by jbus.`, then the words | jbus | the user said it elsewhere and `jbus word` carried it: act on it as said here ("The user's word, carried by jbus") | both |

One more comes from jbus, whatever `home-thread` holds: `jbus: <slug> ended with something left, and it is this home's to close.`, with the pull request and whether it merged, the `Left:` line whole, and each question the slug asked with its answer.
Read the last Result of `$H/tasks/<slug>.md` and those answers, then end it one of two ways.
Where something is still to do, write a brief for what is left and queue it as a follow-up.
Then, or at once where nothing more is wanted or the rest is already somebody's, append `## Result, follow-up (<date>, <the reason>)` to `$H/tasks/<slug>.md`, the brief of the task that ended, with three lines: `Status: done`, `Branch: <its branch>   Pull request: none` and `Left: none`.
Only those three end it.
Send the user nothing about it: a question only they can answer is a gate ("Gates"), and jbus says the row to them once if it is still open 30 minutes after the message.

Nothing is sent when a pull request opens, when a review is written or when its findings are handled.
A reviewer's findings go to the crewmate.
A thread with a question only the user can answer takes a default, carries on and pipes the gate to `jbus gate <slug>`, which keeps it as a numbered question: the home reads the open ones from jbus, shows them, and closes one with the user's answer, which jbus carries back when it differs ("Gates").
With `home-thread` empty no line about a pull request is sent here: jbus reads the brief and the pull request on each pass, and the merge step prints what it found.
Only a thread at one of the four pauses of "Carry on" asks in its own thread and waits: it shows as `waiting` in T3 Code, which is what reaches the user.
The home does not poll for any of it and runs no watch on its state directory or on GitHub, with one exception, in the user's words: "an hourly scheduled run through T3's schedule_task, only while a queue is out, removed when it ends" ("A queue and its hourly audit").
What it has to plan on arrives as a message, and the rest it reads when the user asks for status and at the start of the next home: the gates from jbus ("Gates"), the results from disk.

On each message, do this without waiting for a word from the user.

1. Read what landed: the last result, the review or the report the message is about, from disk. Not the thread that sent it. A gate that came as a message is one jbus could not take: do what the end of "Gates" says for it. A line `Gate: question <number>` in what you just read is a question jbus holds, and asks nothing here. The lines of a gate itself under "Noticed" in a Result or "Findings" in a Report are from a thread that had no home to send them to, or from one that wrote them under the skill as it was: hand them to jbus with the block of "Ask one", under that thread's slug, and only on `not asked` do the same for it as for one that came as a message.
2. Run the merge step of "Merging a pull request that is ready".
   It runs no `jmerge`, and prints what jbus's `jmerge` merged since this home last read the log, then its last line for each open pull request.
   Then clear this home's blockers, as "Clearing its own blockers" says: a start and an audit tick run this step too, so every wake clears them.
3. Run `jbus plan` and close each entry it prints `finished: close it` for ("Planning"). Write no status: the plan holds none. Then launch the next planned task, by "Handing a task to a crewmate" or "Sending a scout", when all of these hold. Any one that fails leaves the task where it is, with the reason kept for step 4:
   - its plan entry's `Stage:` line says `planned`, its own brief is not out (`tasks/<slug>.md` has no `Thread:` line, and its row, where it has one, is still `queued`), and nothing it waits on is unmerged: a task is never stacked on another's branch, but in a plan whose head names `autopilot-stack` ("A stack the user lands");
   - no answer from the user is outstanding for it: an open decision in its entry, or a scout's brief that "Sending a scout" says to show first and the user has not yet seen;
   - its work is in this repo;
   - the launch check, under this list, does not say `wait`;
   - `room` says `go`.

   The launch check names the briefs still out whose `Where:` meets the task's, of any home of this repo. A file another brief names never holds a launch: the overlap is information for the user, and the second pull request to merge rebases. Run it from the main checkout, in one call with the block at the top, with the task's slug in place of the word in angle brackets:

   ```sh
   slug='<slug>'
   if [ -f "$H/scouts/$slug.md" ] && ! [ -f "$H/tasks/$slug.md" ]; then
       echo "go: a scout changes no files, so it overlaps nothing"
   elif ! said=$(uv run --project "$T/../source" jmerge --claims) || [ "${said#wait:}" != "$said" ]; then
       case $said in
       wait:*) printf '%s\n' "$said" ;;
       *) echo "wait: jmerge --claims did not finish, no overlap was read" ;;
       esac
   else
       printf '%s\n' "$said" | awk -v slug="$slug" '
           function paths(where, into,    n, i, part) {
               n = split(where, part, "`")
               for (i = 2; i <= n; i += 2) if (part[i] ~ /[\/.]/) into[part[i]] = 1
           }
           function under(path, directory) {
               sub(/\/+$/, "", directory)
               return index(path, directory "/") == 1
           }
           {
               at = index($(0), " Where: ")
               if (!at) next
               head = substr($(0), 1, at - 1)
               if ($(1) == slug) { paths(substr($(0), at), mine); own = 1; next }
               if (substr(head, length($(1)) + 2, 13) == "not launched ") next
               state = substr(head, length($(1)) + 2)
               sub(/ [^ ]+$/, "", state)
               sub(/^(paused )?pull request /, "#", state)
               out[$(1)] = state
               where[$(1)] = substr($(0), at)
           }
           END {
               if (!own) {
                   print "wait: jmerge --claims has no line for " slug ": write its brief first, then run this again"
                   exit
               }
               for (other in out) {
                   split("", theirs)
                   paths(where[other], theirs)
                   named = ""
                   for (path in mine) for (their in theirs)
                       if (path == their || under(path, their) || under(their, path))
                           named = named (named == "" ? "" : ", ") "`" (length(path) >= length(their) ? path : their) "`"
                   if (named != "") print "overlaps " other " (" out[other] ") on " named ": the second to merge rebases"
               }
               print "go: an overlap holds nothing, name each one in the launch message"
           }'
   fi
   ```

   It prints a line `overlaps <slug> (<#number, out or paused>) on <paths>: the second to merge rebases` for each brief out whose `Where:` names a path of the task's, a file or a directory one is under, and last `go`. A scout's request, in `scouts/` with no brief in `tasks/`, gets `go` alone. On a `wait:` line that says the task has no line, its brief is not on disk yet: write it ("Handing a task to a crewmate" step 1), then run the check again. Name each overlap to the user in the launch message, and launch: it holds nothing. A brief not launched yet is not out, and is left out. On a line that begins `wait:`, nothing was read: launch nothing. Do not read the briefs in `$H/tasks/` for this, and do not ask another home.
4. End the turn by "How a turn ends": what landed, what was merged, what was launched with its link, what was parked, and what waits and why are its lines, and the user hears only a decision or a stop among them.
   When nothing is left planned or out, that is a `handled:` line, told with the open questions when the user asks for status ("Gates").

If a result says the task is not done, the fix is a new message from the user in the crewmate's own thread, or a new brief. The home does not take the task over.

When the user asks for status, run the merge step of "Merging a pull request that is ready" and relay what it printed, and for a brief with no result yet, one `t3_thread_list` call gives the state of the crewmates still out: `running`, `waiting` (it is at one of the four pauses and has asked in its own thread), `failed` or `interrupted`.
Report that state with the thread's link.
No message brought what finished since: run the block of step 4 of "When a home starts" and read the last result of each brief it prints that this thread has not read.
Then run the block of "Show the open ones" ("Gates") and show what it prints.
Then show each `local` decision or stop this home told and nothing has ended yet ("How a turn ends"), with the block at the top and the block that finds this home:

```sh
grep -E '^(decision|stop) local ' "${M:?run the block that finds this home first}/told" 2> /dev/null ||
    echo "no local decision or stop is open"
```

The root home then runs the block of "Scoped homes" that reads the scopes.
Do not read a crewmate's timeline unless the user asks what it is doing.

Once a week the root home's status also says where changes collide. Run this with the block at the top, in the main checkout: when the stamp in `$H` is over 7 days old, or missing, it prints the top 5 files of the last week's three tables (merged pull requests, pairs open at once, rebases that dropped lines or changed the patch) and stamps the run, and otherwise it prints nothing. Show what it prints. A file high in all three is one to split, and never a reason to hold a launch.

```sh
if [ -z "$(find "$H/hot-files.stamp" -mtime -7 2> /dev/null)" ]; then
    J=$(git -C "$T/../source" rev-parse --show-toplevel 2> /dev/null || git -C "$T" rev-parse --show-toplevel) &&
        uv run --project "$J" "$J/scripts/hot_files.py" --since "$(date -d '7 days ago' +%F)" --home "$H" --top 5 &&
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
    route="#/?home=$scope"
fi
if ! link=$(uv run --project "$T/../source" jbus link 2> /dev/null); then
    echo "no jview link: jbus has no page for $R"
else
    view=${link%%#*}
    curl -fsS --max-time 5 "${view%/}/panel/board.json" 2> /dev/null | jq -r '
        (.stages | map({(.key): .name}) | add) as $name
        | "first: Most stuck: "
          + (if .stuck then "\($name[.stuck.stage] // .stuck.stage), \(.stuck.still) of \(.stuck.count)" else "none" end)
          + ". Waiting longest: "
          + (if .longest_wait then "\(.longest_wait.slug), \($name[.longest_wait.stage] // .longest_wait.stage) since \(.longest_wait.since), \(.longest_wait.cause)" else "none" end)
          + "."' 2> /dev/null
    shot=$(uv run --project "$T/../source" jbus view-shot "$route" --out "jview-flow-$R-$scope.png" 2> /dev/null | tail -n 1)
    case $shot in
    /*.png) [ -f "$shot" ] && echo "attach: $shot $(wc -c < "$shot" | tr -d ' ')" ;;
    esac
    echo "$view$route"
fi
```

Make the `first:` line, without its `first: `, the reply's first line, so the words name what the picture shows.
An `attach: <path> <bytes>` line is the picture, sent to this thread, where the user reads the reply, with three calls of the `t3-code` server (if your harness defers them, load them first).
First `t3_attachment_prepare_upload`, with an `upload` of type `image`, the path's file name as its `name`, `image/png` as its `mimeType`, and the bytes as its `sizeBytes`.
Then POST the file's bytes, as they are, to the `relativeUrl` it returns, on that server's HTTP origin.
Last `t3_thread_send_attachments` with that `attachmentId`, the same name, type, MIME type and size, and no `threadId`.
Make the last line the reply's last line.
With no `first:` or no `attach:` line, the reply goes without it and says nothing of it.
On `no jview link`, the reply ends with no link and does not say why.
