---
name: handoff
description: Archive this home - stop what runs, keep a note of ten lines at most in its log, hand what it has out to the root home, close its scope, switch off its scheduled tasks, and rename and settle this thread. It starts no next home. Use when the user invokes /handoff or $handoff, archives a home from the jstack tree, or says to archive or close this home.
tip: archives this home and starts no next one | archive | archive this home | close this home | wrap up
user-invocable: true
disable-model-invocation: true
card: "Run the pipeline | 6 | Archives a home. It keeps a note of ten lines at most in the home's log, hands what the home has out to the root home, closes its scope and starts no next home. | Reach for it when a home's work is over, or from the tree's Archive item. | op: the operator; model: a home"
---

# handoff

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
T=$(realpath ~/.claude/skills/handoff/../../templates)
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
this_home() {
    M=
    case ${1} in
    '') M=$H ;;
    *)
        for f in "$H"/home-id "$H"/*/home-id; do
            if [ -f "$f" ] && [ "$(awk 'NF {print $(1); exit}' "$f")" = "${1}" ]; then
                M=$(dirname "$f")
                break
            fi
        done ;;
    esac
    if [ -z "$M" ]; then
        echo "no home: thread ${1} is no home of $R now, its id is in no home-id under $H. Nothing is written."
        return 1
    fi
}
handed_off() {
    L=
    F=
    for f in "$H"/handoff.md "$H"/*/handoff.md "$H"/log/*.md "$H"/*/log/*.md "${H%/*}"/_*/handoff.md; do
        if [ -n "${1}" ] && [ -f "$f" ] && [ "$(sed -n 's/^Was home:[[:space:]]*\([^[:space:]][^[:space:]]*\).*/\1/p' "$f" | head -n 1)" = "${1}" ]; then
            F=$f
            L=$(dirname "$f")
            case $L in */log) L=${L%/log} ;; esac
            break
        fi
    done
}
party_home() {
    M=
    P=
    for f in "${H%/*}"/_*/home-id; do
        if [ -n "${1}" ] && [ -f "$f" ] && [ ! -f "${f%/*}/CHARTER.md" ] && [ "$(awk 'NF {print $(1); exit}' "$f")" = "${1}" ]; then
            M=$(dirname "$f")
            P=${M##*/_}
            break
        fi
    done
    [ -n "$M" ]
}
```

That is **the block at the top**: run it in the same call as each block below. Every block is sh, and the line before `this_home` makes zsh read them so. `$H` is the repo's state directory, which every home of the repo shares. `$T` is the `templates/` directory of the repo this skill lives in. Each template there is the one copy of its text: read it when a step names it, not before.

A handoff archives a home, and starts no home after it.
A repo has one root home, and may have scoped homes beside it (`skills/home/SKILL.md`, "Where a home's state lives"), and each is archived in its own directory, `$M`: `$H` for the root home, `$H/<scope>` for a scoped one.
`this_home` sets it as the home skill does, from the one `home-id` that holds this thread's id.
`handed_off` sets `$F` to the note that names a thread on its `Was home:` line, which step 3 writes, and `$L` to the directory of the home the thread was, or both to nothing.
Each block below is run with that id in place of `<threadId>`: the `t3-code` server's `t3_thread_configuration` with no arguments gives it as `threadId` (if your harness defers it, load it first).
In a session with no tool that gives the id, put nothing in its place: the blocks then archive nothing.

A party that is no repo's home hands off too, to a next thread of its own.
Its folder is `~/.local/state/home/_<name>`, beside the repos' state directories, and holds its thread id in a `home-id`.
`party_home` finds it by that id, and sets `$M` to the folder and `$P` to the name.
It finds no expert, whose folder has a `CHARTER.md`: an expert rolls over as `$T/../skills/expert/SKILL.md` "When to roll over" says, and never by this skill.
`handed_off` finds a party that handed off as it finds a home.

Before step 1, see which home this is:

```sh
case '<threadId>' in
'')
    echo "not known: the session gives no id for this thread, so no home is archived. Tell the user to run /handoff in the home's own thread in T3 Code."
    exit ;;
esac
if ! this_home '<threadId>' > /dev/null && party_home '<threadId>'; then
    printf 'party %s\nhandoff: %s\nwrite: %s\n' "$P" "$M/handoff.md" "$M/handoff.next.md"
    exit
fi
if ! this_home '<threadId>' > /dev/null; then
    handed_off '<threadId>'
    case $F in
    "$H"/log/* | "$H"/*/log/*)
        echo "archived before: $F names this thread, so an earlier run archived this home: go to step 3"
        exit ;;
    esac
fi
this_home '<threadId>' || exit 1
if [ "$M" = "$H" ]; then echo "root"; else echo "scope ${M##*/}"; fi
printf 'write: %s\n' "$M/handoff.next.md"
```

It prints which home this is and where step 2 writes the note.
On `party <name>`, this thread is that party's home and no repo's: do none of the steps below, and go by "A party's home".
On `archived before`, an earlier turn of this handoff archived the home and was cut off after it: run step 1, then step 3 and what follows it.
On `not known:` or `no home:`, nothing is written.
This thread is no home now: a crewmate, an ordinary thread, or a home that another took the place of.
Tell the user so in three lines at most, with what this thread leaves undone, and end here.

## Steps

1. **Stop what runs in the background.**
   A watch, a loop, a `lavish-axi poll` this thread holds: stop each by its process id.
   This thread is finished and must have nothing left that wakes it.
   Each one goes in the note, under `Out, not on the bus:`, with what it watched.
   Then run `git status --short` and `git log --oneline @{upstream}..` in each worktree this thread used, the main checkout included: each path and commit they print goes under `Uncommitted:` with its branch, and `none` only when both print nothing there.

2. **Write the note**, at the path the block above printed after `write: `, in the shape of `$T/handoff.md`: read it now.
   It is the record of the archived home, kept in its `log/`, and no home starts from it.
   It holds only what nothing else holds: jbus holds the plan, the queue, the questions and what merged, so none of that is written here.
   A rule of the user's is no line of it either: the home wrote it to `standing.md` when it heard it.
   Right after any edit this handoff makes to `$H/standing.md`, run `jbus snapshot --why "<repo> standing rule <n> <added, changed or removed>"`, so the edit is a commit of its own in `~/.local/state/home`, pushed.
   Facts and pointers, not narrative: a path or a thread id in place of an explanation.

   A gate jbus could not take, which came as a message or sits in a Result or a Report, is held by nothing else while it is unanswered: write it under the labels, whole, with its default and its `Asked by:` and `Undo:` lines. The gates are not counted in the note's ten lines.

3. **Archive.**
   Call the `t3-code` server's `list_scheduled_tasks` (if your harness defers it, load it first) with no arguments.
   Then run this with the block at the top, with this thread's id in place of `<threadId>` and the whole reply in place of the line in angle brackets.
   In a session with no such tool, leave the line as it is:

   ```sh
   ME='<threadId>'
   N=10 # lines a note has at most, its gates not counted
   case $ME in
   '' | *'<'* | *'>'* | *' '*)
       echo "not known: put this thread's id in place of the placeholder. With no tool that gives it, nothing is archived: tell the user to run /handoff in the home's own thread in T3 Code."
       exit 1 ;;
   esac
   again=
   if ! this_home "$ME" > /dev/null; then
       handed_off "$ME"
       case $F in
       "$H"/log/* | "$H"/*/log/*) again=yes M=$L ;;
       *)
           echo "not the home: this thread's id is in no home-id under $H and on no archived home's note. Nothing is archived, tell the user."
           exit 1 ;;
       esac
   fi
   scope=
   if [ "$M" != "$H" ]; then scope=${M##*/}; fi
   note=$M/handoff.next.md
   if [ -n "$again" ]; then
       kept=$F
   else
       why=
       if [ ! -s "$note" ]; then
           why="$note is not there"
       elif grep -q '^<' "$note"; then
           why="a line of it is still the template's"
       else
           above=$(awk '/^## Gate/ {exit} NF' "$note")
           lines=$(printf '%s\n' "$above" | grep -c .)
           if [ "$lines" -gt "$N" ]; then why="it has $lines lines above its gates, and a note has at most $N"; fi
       fi
       if [ -z "$why" ]; then
           why=$(sed -n 's/^\([A-Z][^:<]*:\) <.*/\1/p' "$T/handoff.md" | while IFS= read -r label; do
               printf '%s\n' "$above" | grep -q "^$label [^<]" || echo "it has no $label line above its gates that is filled in"
           done | head -n 1)
       fi
       if [ -n "$why" ]; then
           echo "not written: $why. Write the note there in the shape of $T/handoff.md, then run this again."
           exit 1
       fi
       handed_off "$ME"
       kept=
       case $F in "$M"/log/*) kept=$F ;; esac
       if [ -z "$kept" ]; then
           if ! out=$(jbus out --scope "${scope:-.}" 2>&1); then
               out="not known, jbus said: ${out:-nothing}"
           fi
           if [ -n "$scope" ] && [ -f "$M/gates.md" ]; then
               sep=$(printf '\001')
               moved=$(awk -v sep="$sep" '
                   function out() { if (open) printf "%s%s%s%s%s\n", n, sep, by, sep, entry; entry = by = ""; open = 0 }
                   /^## Gate [0-9]+: / { out(); n = $(3); sub(/:$/, "", n) }
                   /^$/ { next }
                   /^Status: open$/ { open = 1 }
                   /^Asked by: / { by = $(0); sub(/^Asked by: /, "", by); sub(/,.*/, "", by) }
                   { entry = entry $(0) "\002" }
                   END { out() }' "$M/gates.md" | while IFS=$sep read -r n by entry; do
                   if [ -z "$by" ] || [ "$by" = home ] || [ "$by" = "home-$scope" ]; then by=home; fi
                   if said=$(printf '%s\n' "$entry" | tr '\002' '\n' | jbus gate "$by" 2>&1); then
                       echo "gate $n of gates.md is the root home's, $said"
                   else
                       echo "not moved: gate $n of gates.md, jbus said: $said"
                   fi
               done)
               if printf '%s\n' "$moved" | grep -q '^not moved: '; then
                   echo "not archived: an open gate of $M/gates.md is not a question jbus holds, and nothing is changed but the gates moved before it. Run this again once jbus takes it:"
                   printf '%s\n' "$moved" | grep '^not moved: '
                   exit 1
               fi
               if ! mv "$M/gates.md" "$M/gates-moved.md"; then
                   echo "not archived: $M/gates.md could not be renamed to gates-moved.md. Run this again once that is put right."
                   exit 1
               fi
               out=$(printf '%s\n%s\n' "$out" "$moved" | grep .)
           fi
           if [ -n "$scope" ]; then label="Moved to the root:"; else label="Left with no home:"; fi
           kept=$M/log/$(date +%F-%H%M).md
           if [ -e "$kept" ]; then kept=$M/log/$(date +%F-%H%M%S).md; fi
           if ! mkdir -p "$M/log" || ! {
               sed '/^Was home:/d; /^Archived:/d; /^Moved to the root:/d; /^Left with no home:/d' "$note"
               printf '\nArchived: %s, and no home was started after this one.\n' "$(date +%F)"
               if [ -z "$out" ]; then
                   printf '%s none\n' "$label"
               else
                   printf '%s\n' "$label"
                   printf '%s\n' "$out" | sed 's/^/- /'
               fi
               printf '\nWas home: %s\n' "$ME"
           } > "$kept"; then
               echo "not archived: the note could not be written to $kept. Run this again once that is put right."
               exit 1
           fi
       fi
       if ! { [ ! -f "$M/handoff.md" ] || mv "$M/handoff.md" "${kept%.md}-before.md"; } ||
           ! { [ -z "$scope" ] || [ ! -f "$M/plan.md" ] || mv "$M/plan.md" "$M/plan-archived.md"; } ||
           ! uv run --project "$T/../source" jbus forget "$M/home-id" > /dev/null; then
           echo "not archived: $M/handoff.md or $M/plan.md could not be moved, or $M/home-id not removed. Run this again once that is put right."
           exit 1
       fi
   fi
   if [ -f "$note" ]; then uv run --project "$T/../source" jbus forget "$note" > /dev/null; fi
   if [ -n "$scope" ]; then
       what="scope $scope is closed, and what it had out is the root home's"
   else
       what="the root home is archived, and $R has no home until someone types /home"
   fi
   if [ -n "$again" ]; then
       echo "archived before: $what. Start no home: switch off its scheduled tasks, tell the user, then rename and settle this thread"
   else
       echo "archived: $what. Start no home: switch off its scheduled tasks, tell the user, then rename and settle this thread"
   fi
   printf 'note: %s\n' "$kept"
   awk '/^(Moved to the root|Left with no home):/ {on = 1; print; next} on && /^- / {print; next} {on = 0}' "$kept"
   printf 'title: home: %s%s\n' "$R" "${scope:+ $scope}"
   jq -rs --arg me "$ME" '
       if length == 1 and (.[0].tasks | type) == "array" then .[0] else error("no tasks") end
       | [.tasks[] | select(.boundThreadId == $me)]
       | if length == 0 then "none: no scheduled task posts into this thread" else .[] end
       | if type == "string" then .
         else "switch off \(.scheduledTaskId): \(.title) posts into this thread, and no home takes it over" end' 2> /dev/null << 'THE_REPLY_ENDS_HERE' ||
   <the reply of list_scheduled_tasks>
   THE_REPLY_ENDS_HERE
       echo "not read: put the whole reply of list_scheduled_tasks in place of the placeholder"
   ```

   It does it all, in this order: it reads the note, asks jbus what this home has out, hands each open gate of a scoped home's `gates.md` to jbus as a question of the root home's and renames the file `gates-moved.md`, keeps the note in `$M/log/` under a dated name with an `Archived:` line, the list of what was out and a `Was home:` line with this thread's id, moves an older `handoff.md` beside it, moves a scoped home's `plan.md` to `plan-archived.md`, and removes `home-id`.
   A second run changes nothing and prints `archived before`, with the same lines under it.
   Its first line is what the steps below go by, and the lines under it are what step 4 tells the user and step 5 renames by: keep all of them.

   - `not known:`, `not written:` and `not archived:`: nothing is archived.
     Put right what it names, and run it again.
     A note whose lines will not fit in ten is cut, not split: jbus holds the rest.
   - `not the home:`: this thread's id is in no `home-id` and on no archived home's note.
     Tell the user so, in three lines at most, and launch, rename and settle nothing.
     The skill ends here.
   - `archived` or `archived before`: go on with step 4.

   What a home has out is what `jbus out` prints for it: each queue row of its briefs that is not over, each entry whose go holds with no live row, each of their crew or reviewer threads that is not settled, each question jbus holds for it and each open gate of its `gates.md`.
   The block writes each under `Moved to the root:` for a scoped home and under `Left with no home:` for the root, and prints them under its first line.
   A scope is a home only while its directory has a `home-id` or a `Was home:` line of a `handoff.md`, so once the block has run, every brief whose `Home:` line names the scope is the root home's by the rule `jbus home` keeps (`features/jbriefs/src/jbriefs/home.py`).
   jbus sends the root home what each of its threads has to tell, `jmerge` merges its pull requests as the root's, and the root home's start lists its rows as its own: nothing is rewritten and nothing is sent.
   With `plan.md` moved, jbus and the jstack tree count the scope as no home, and `/home <scope>` moves it back and starts it again (`skills/home/when-a-home-starts.md`, step 1).
   A root home that is archived leaves the repo with no home: jbus keeps running its queue and merging, a thread with something to tell finds no `home-id` and sends nothing, and its report waits on disk for the home someone starts with `/home`.

   A home's own `home-id` holds its id: the home's start wrote it there, and nothing else does.
   `home-thread` is another file, the switch that has a home run the sweep: it is set by hand, and the block leaves it as it is.
   The block changes only this home's directory, and no other home's files.
   The `Was home:` line is the last line of the note: "After the handoff" reads it to say whose mail a late message is, and the start of a home of the same directory reads it to take over this thread's scheduled tasks and to settle this thread (`skills/home/when-a-home-starts.md`, "The home before this one").

4. **Switch off its scheduled tasks, and tell the user.**
   No home comes after this one to take a scheduled task over, so switch off each one the block printed a `switch off` line for, with the `t3-code` server's `update_scheduled_task` (if your harness defers it, load it first), `{"scheduledTaskId": "<scheduledTaskId>", "enabled": false}`.
   A task that is off runs nothing, so it cannot make this thread active again, and it keeps its address for a home started later in this directory to take over.
   Delete none.
   On `not read`, in a session with no such tool, there is nothing to do: tell the user that a task bound to this thread may still run.
   Then tell the user, in three lines at most: the note's path, what moved to the root home (or, for the root, that the repo has no home until someone types `/home`, with what was out), each task that is now off, and each gate the note carries.

5. **Rename and settle.**

   1. Rename this thread with `t3_thread_update`, so the list shows which home it was and that it is archived:

      ```json
      {"action": "rename", "title": "<title> (archived <date>)"}
      ```

      `<title>` is what step 3 printed after `title: `.
      `<date>` is today as `date +%F` prints it.
      No `threadId` means this thread.
   2. Last, settle this thread with `t3_thread_organize`:

      ```json
      {"action": "settle"}
      ```

      It takes effect when the turn ends, so it is the last call of the handoff.
      It clears this thread's pin with it.
      A turn that fails or is cut off, or a message that comes in, leaves this thread active and pinned, and the reply of the call does not say which: a home started later in this directory looks at this thread and settles it if it has to (`skills/home/when-a-home-starts.md`, "The home before this one").

## A party's home

A party's home plans nothing, briefs nothing and launches nothing but its own next thread.
Its handoff is its page and that launch, with no plan, no merge and no seed.
Two things, in order:

1. **Write the new page**, at the path the first block printed after `write: `, `handoff.next.md` in the party's folder, in the shape its `handoff.md` has: the party's own, and not `$T/handoff.md`. A party with no page yet writes where things stand, what is next and what is open. Facts and pointers, as step 2 says of a home's. Leave `handoff.md` as it is, and write no `Was home:` line: the next block does both.

2. **Close, and start the next thread.** Run this with the block at the top:

   ```sh
   ME='<threadId>'
   again=
   if ! party_home "$ME"; then
       handed_off "$ME"
       case $L in
       "${H%/*}"/_*) if [ ! -e "$L/home-id" ]; then again=yes M=$L P=${L##*/_}; fi ;;
       esac
       if [ -z "$again" ]; then
           echo "not a party's home: the id of thread $ME is in no ${H%/*}/_*/home-id. Nothing is written."
           exit 1
       fi
   fi
   if [ -z "$again" ] && [ ! -s "$M/handoff.next.md" ]; then
       echo "not written: $M/handoff.next.md is not there. Write the new page to it, then run this again."
       exit 1
   fi
   page=$M/RESTART.md
   boot=
   if [ -f "$page" ]; then
       boot=$(awk '/^[ \t]*```/ {if (open) last = text; text = ""; open = !open; next} open {text = text $(0) "\n"} END {printf "%s", last}' "$page")
   fi
   told="Thread $ME, the $P thread before this one, handed off with /handoff and is settled: send it nothing. Before anything else, read \"The thread a party's handoff started\" in $(realpath "$T/../skills/handoff/SKILL.md") and do what it says, with $P in place of <party>. Then start from $M/handoff.md${boot:+ and $page}."
   first="You are the next thread of $P's home, in $M."
   message=$(printf '%s\n\n%s\n' "${boot:-$first}" "$told")
   title="home: $P"
   model=$(uv run --project "$T/../source" jroles expert) || model=
   if ! launch=$(jq -cn --arg title "$title" --arg message "$message" --argjson selection "${model:-null}" '{title: $title, workspaceStrategy: {type: "root"}, message: $message} + if $selection then {modelSelection: $selection} else {} end') ||
       ! rename=$(jq -cn --arg title "$title (handed off $(date +%F))" '{action: "rename", title: $title}'); then
       echo "not closed: jq did not run, and nothing is changed"
       exit 1
   fi
   if [ -n "$again" ]; then
       echo "closed before: $M/handoff.md names this thread and $M/home-id is gone. Launch only if no next thread was started"
   else
       log=$M/log
       kept=$log/$(date +%F-%H%M)-handoff.md
       if [ -e "$kept" ]; then kept=$log/$(date +%F-%H%M%S)-handoff.md; fi
       if { [ ! -f "$M/handoff.md" ] || { mkdir -p "$log" && mv "$M/handoff.md" "$kept"; }; } &&
           sed '/^Was home:/d' "$M/handoff.next.md" > "$M/handoff.md" &&
           printf '\nWas home: %s\n' "$ME" >> "$M/handoff.md" &&
           uv run --project "$T/../source" jbus forget "$M/handoff.next.md" "$M/home-id" > /dev/null; then
           echo "a party's home: start its next thread, then rename and settle this thread"
       else
           echo "not closed: the old page could not be moved to $log, or the new one not written to $M/handoff.md. Launch nothing, and run this again once that is put right."
           exit 1
       fi
   fi
   printf 'launch: %s\nrename: %s\nsettle: {"action": "settle"}\n' "$launch" "$rename"
   ```

   The old page is in `log/` under a dated name, the new one is `handoff.md` and ends in a `Was home:` line with this thread's id, and `home-id` is gone, so a second run changes nothing.
   On `not a party's home:`, `not written:` or `not closed:`, nothing is launched: do what the line says, or tell the user.
   On `closed before`, an earlier run of this block closed and its turn may have been cut before the launch: look for the next thread as "A lost launch" says, with the title on the `launch:` line.
   With none, go on as on `a party's home`.
   With one, launch nothing, and only rename and settle.

   On `a party's home`, first stop what this thread has running in the background, as step 1 does. Then make three calls, in the order printed, each with the object after its word, as printed: `launch:` with the `t3-code` server's `t3_thread_launch`, `rename:` with `t3_thread_update`, `settle:` with `t3_thread_organize`, the last call of the turn (if your harness defers one, load it first). Between the launch and the rename, tell the user in three lines at most what was written, and the link to the next thread, `[<title>](t3-thread://v1/<its threadId>)`.

   The root workspace is the main checkout of the project this thread is in, which is the party's folder, and the project and the modes are this thread's.
   The model is the one the role map names for `expert`, for any party that hands off here, and that is never an expert, whose rollover is not this skill's: the block asks `jroles` for it, and the `launch:` line has it as `modelSelection`.
   With no line for that role the call has no `modelSelection`, and the next thread runs on this thread's model.
   A line the block prints on stderr says why the map gives no model: the launch is made all the same, and the user is told that line.
   The message is the last fenced block of the folder's `RESTART.md`, the one a new thread of the party is started with by hand, and under it the lines that send the next thread to the section below.
   With no such page it is those lines alone.
   A launch has no retry key: if the call fails or its reply is lost, look for the thread as "A lost launch" says before launching again.
   If the launch fails all the same, or the session has no `t3_thread_launch`, give the user the message to start a thread with, and rename and settle nothing.

### A lost launch

A launch has no retry key.
If the call fails or its reply is lost, look for the thread with `t3_thread_list` before launching again, so there are never two:

```json
{"titleContains": "<title>"}
```

The list holds every thread whose title has those words, this thread among them, which still has that title.
The next thread is the one with exactly that title that is newer than this one.

### The thread a party's handoff started

The message that started this thread sent it here. This thread is no home by the home skill, and reads this section of this file and the block at the top, and no other part. Get this thread's id from the `t3-code` server's `t3_thread_configuration` with no arguments, as `threadId`, and call `list_scheduled_tasks` with no arguments (if your harness defers one, load it first). Then run this with the block at the top, with the id, the name the message gives, and the whole reply in place of the words in angle brackets:

```sh
ME='<threadId>'
P='<party>'
M=${H%/*}/_$P
case $ME$P in
'' | *'<'* | *'>'* | *' '* | */*) M= ;;
esac
if [ -z "$ME" ] || [ -z "$M" ] || [ ! -f "$M/handoff.md" ]; then
    echo "not written: this needs the thread's id and the name of a party whose folder under ${H%/*} has a handoff.md"
elif [ "$(cat "$M/home-id" 2> /dev/null)" != "$ME" ] && ! (set -C && printf '%s\n' "$ME" > "$M/home-id") 2> /dev/null; then
    echo "not written: $M/home-id holds $(cat "$M/home-id" 2> /dev/null), another thread, which is the party's now. Take no task over, and tell the user."
else
    echo "written: $M/home-id"
    was=$(sed -n 's/^Was home:[[:space:]]*\([^[:space:]]*\).*/\1/p' "$M/handoff.md" | head -n 1)
    if [ -z "$was" ] || [ "$was" = "$ME" ]; then
        echo "no thread before this one: $M/handoff.md names none, so no task is taken over"
    else
        jq -rs --arg was "$was" '
            if length == 1 and (.[0].tasks | type) == "array" then .[0] else error("no tasks") end
            | [.tasks[] | select(.boundThreadId == $was)]
            | if length == 0 then "none: no scheduled task posts into \($was)" else .[] end
            | if type == "string" then .
              else "take \(.scheduledTaskId): \(.title) posts into \($was), the thread before this one" end' 2> /dev/null << 'THE_REPLY_ENDS_HERE' ||
<the reply of list_scheduled_tasks>
THE_REPLY_ENDS_HERE
            echo "not read: put the whole reply of list_scheduled_tasks in place of the placeholder"
    fi
fi
```

On `written:`, this thread's id is in the party's `home-id`, where whoever sends to the party reads it. It prints one line for each scheduled task that posts into the thread that handed off, and never a task's address. On `take <id>`, take the task over with the `t3-code` server's `update_scheduled_task` (if your harness defers it, load it first), `{"scheduledTaskId": "<scheduledTaskId>", "bindToCurrentThread": true}`, and nothing else in the call: the task keeps its title, its prompt, its schedule and, for a webhook, its address, and one that was switched off stays off. After the calls, list the tasks again and run the block again: it prints `none` when every one is taken. A task it still prints had its call refused: tell the user its id and what the call answered, and make no second call. On `none` and `no thread before this one`, there is nothing to take. On `not written:` or `not read:`, fill in what the line names and run it again. A `not written:` that names another thread is not filled in: that thread started first and is the party's, so this one does nothing more.

Then go on as the message says, from the party's handoff and its restart page.

## After the handoff

A home that is archived does nothing more.
Its briefs name no thread, and a thread or a party that sends to the repo's home reads its `home-id` first, so a message should not reach it.
If one still does (a thread that kept an old id, a direct message, the user), run this with the block at the top before anything else:

```sh
ME='<threadId>'
case $ME in
'' | *'<'* | *'>'*)
    echo "not known: put this thread's id in place of the placeholder. With no tool that gives it, do not act on the message: tell the sender to read $H/home-id" ;;
*)
    if this_home "$ME" > /dev/null; then
        echo "a home: this thread's id is in $M/home-id, so the message is this thread's to act on"
    else
        handed_off "$ME"
        next=
        if [ -n "$L" ]; then next=$(awk 'NF {print $(1); exit}' "$L/home-id" 2> /dev/null); fi
        case $L in
        "$H" | "$H"/*) if [ -z "$next" ]; then next=$(awk 'NF {print $(1); exit}' "$H/home-id" 2> /dev/null); fi ;;
        esac
        if [ -z "$L" ]; then
            echo "no home's: this thread's id is in no home-id and on no archived home's Was home: line, so no file says whose mail this is. Do not act on the message: tell the sender to read $H/home-id"
        elif [ -n "$next" ] && [ "$next" != "$ME" ] && [ "$L" = "${H%/*}/_${L##*/_}" ]; then
            echo "handed off: this thread's id is in no home-id. Do not act on the message and send it on to nobody: tell the sender, once, that $next is the home now"
        elif [ "$L" = "${H%/*}/_${L##*/_}" ]; then
            echo "handed off: this thread's id is in no home-id, and $L/home-id holds none yet. Do not act on the message and send it on to nobody: tell the sender, once, the id this thread's own launch of the next thread gave. With no such launch, tell the sender to read $L/handoff.md"
        elif [ -n "$next" ] && [ "$next" != "$ME" ]; then
            echo "archived: this thread's id is in no home-id. Do not act on the message and send it on to nobody: tell the sender, once, that $next is the home now"
        else
            echo "archived: this thread's id is in no home-id, and $R has no home now. Do not act on the message and send it on to nobody: tell the sender, once, that $R has no home until someone types /home, and that $H/home-id names it then"
        fi
    fi ;;
esac
```

On `a home`, this thread is not archived: go by the home skill.
On any other line, do not act on the message: no run, no launch, no merge, no change to the plan, whatever it asks and whoever sent it.
Do what the line says and nothing more.
`no home's` is a thread that never was a home: nothing is sent on.
The home it names on an `archived` line is the one the archived home's own directory has now, a home started there again, or else the root home.
A `handed off` line is a party's, and names its next thread.

One kind of message is neither sent on nor answered, whatever the line says: one of this skill's own.
Its first line has `handed off, and this was sent to it by`, or it starts `the home of <repo> is <id> now`, `<repo>: the home is <id> now` or `<repo>: there is no home now`.
Settle again and end the turn, so that two archived threads never answer each other.

A message is never sent on: the sender sends it again, to the id it is told.
Between two homes of one repo the send would be refused anyway, since `features/home/hooks/agent-sends.sh` refuses a thread that was a home sending to its repo's home now.
Tell the sender with `t3_thread_send`, to its own id, once: a call whose reply is lost is not sent again.
On a line that names the home now:

```json
{"threadId": "<thread>", "message": "<repo>: the home is <the home's id> now, and your message was not sent on to it. Send it there if it still stands, and read the id in <the home-id file> before each send."}
```

On a line that says the repo has no home, the `t3_thread_send` is this one:

```json
{"threadId": "<thread>", "message": "<repo>: there is no home now, and your message was not sent on. A home starts when someone types /home: read the id in <the home-id file> before each send."}
```

The user is told the same in one line here, with the link to the home now, `[<title>](t3-thread://v1/<its threadId>)`, where there is one.
Where the line names a file and no id, the sender is told that path.
Then settle this thread again.

A crewmate thread (`/crew <slug>`) never runs this skill. It ends by writing its `## Result`, as the `crew` skill says.
