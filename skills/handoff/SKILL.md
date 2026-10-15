---
name: handoff
description: Close this thread and leave the next one a short start - stop what runs, write a note of ten lines at most, and, for a repo's home, start the next home and settle this thread. The next home reads the rest from jbus. Use when the user invokes /handoff or $handoff, says to wrap up, move on or start fresh, or when the home skill's hand-off conditions are met.
tip: closes this thread and leaves the next one a note of ten lines | wrap up | wrap this up | start fresh | hand off | hand this off
user-invocable: true
card: "Run the pipeline | 6 | Closes a home. It writes a note of ten lines at most and starts the next home, whose start reads the rest from jbus. | Reach for it when the day ends, or the home's context has grown. | op: the operator; model: a home"
---

# handoff

A handoff moves what nothing else holds out of this conversation and onto disk, so that the next thread starts from a note of ten lines and from what jbus holds, and not from this thread's history. After it, this thread is finished.

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
            if [ -f "$f" ] && [ "$(cat "$f")" = "${1}" ]; then
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
    for f in "$H"/handoff.md "$H"/*/handoff.md "${H%/*}"/_*/handoff.md; do
        if [ -n "${1}" ] && [ -f "$f" ] && [ "$(sed -n 's/^Was home:[[:space:]]*\([^[:space:]]*\).*/\1/p' "$f" | head -n 1)" = "${1}" ]; then
            L=$(dirname "$f")
            break
        fi
    done
}
party_home() {
    M=
    P=
    for f in "${H%/*}"/_*/home-id; do
        if [ -n "${1}" ] && [ -f "$f" ] && [ ! -f "${f%/*}/CHARTER.md" ] && [ "$(cat "$f")" = "${1}" ]; then
            M=$(dirname "$f")
            P=${M##*/_}
            break
        fi
    done
    [ -n "$M" ]
}
```

That is **the block at the top**: run it in the same call as each block below. Every block is sh, and the line before `this_home` makes zsh read them so. `$H` is the repo's state directory, which every home of the repo shares. `$T` is the `templates/` directory of the repo this skill lives in. Each template there is the one copy of its text: read it when a step names it, not before.

A handoff is a home's. A repo has one root home, and may have scoped homes beside it (`skills/home/SKILL.md`, "Where a home's state lives"), and each hands off in its own directory, `$M`: `$H` for the root home, `$H/<scope>` for a scoped one. `this_home` sets it as the home skill does, from the one `home-id` that holds this thread's id. `handed_off` sets `$L` to the directory of the home a thread was, from the `Was home:` line step 3 writes, or to nothing. Each block below is run with that id in place of `<threadId>`: the `t3-code` server's `t3_thread_configuration` with no arguments gives it as `threadId` (if your harness defers it, load it first). In a session with no tool that gives the id, put nothing in its place: the handoff is the root's.

A party that is no repo's home hands off too. Its folder is `~/.local/state/home/_<name>`, beside the repos' state directories, and holds its thread id in a `home-id`. `party_home` finds it by that id, and sets `$M` to the folder and `$P` to the name. It finds no expert, whose folder has a `CHARTER.md`: an expert rolls over as `$T/../skills/expert/SKILL.md` "When to roll over" says, and never by this skill. `handed_off` finds a party that handed off as it finds a home.

Before step 1, see which home this is:

```sh
if ! this_home '<threadId>' > /dev/null && party_home '<threadId>'; then
    printf 'party %s\nhandoff: %s\nwrite: %s\n' "$P" "$M/handoff.md" "$M/handoff.next.md"
    exit
fi
if ! this_home '<threadId>' > /dev/null; then
    handed_off '<threadId>'
    case $L in
    "$H" | "$H"/*)
        if [ ! -e "$L/home-id" ]; then
            echo "closed before: $L/handoff.md names this thread and $L/home-id is gone, so step 3 closed already: go to step 3"
            exit
        fi ;;
    esac
fi
this_home '<threadId>' || exit 1
if [ "$M" = "$H" ]; then echo "root"; else echo "scope ${M##*/}"; fi
printf 'write: %s\n' "$M/handoff.next.md"
```

It prints which home this is and where step 2 writes the note. On `party <name>`, this thread is that party's home and no repo's: do none of the steps below, and go by "A party's home". On `closed before`, an earlier turn of this handoff closed and was cut off after it: run step 1, then step 3 and what follows it. On `no home:`, the call stops and nothing is written. This thread is no home now: a crewmate, an ordinary thread, or a home that another took the place of. It writes no note, since that is a home's. Tell the user so in three lines at most, with what this thread leaves undone, and end here.

## Steps

1. **Stop what runs in the background.** A watch, a loop, a `lavish-axi poll` this thread holds: stop each by its process id. This thread is finished and must have nothing left that wakes it. Each one the next home has to start again goes in the note, under `Out, not on the bus:`, with what it watched. Then run `git status --short` and `git log --oneline @{upstream}..` in each worktree this thread used, the main checkout included: each path and commit they print goes under `Uncommitted:` with its branch, and `none` only when both print nothing there.

2. **Write the note**, at the path the block above printed after `write: `, in the shape of `$T/handoff.md`: read it now. It holds only what nothing else holds. The next home's start reads `jbus plan`, the open rows of the queue, the open questions, what merged and what came in since ("When a home starts", step 4, in `$T/../skills/home/SKILL.md`), so none of that is written here: no status, no thread a row of the queue names, no question jbus holds, no `merged` line. A rule of the user's is no line of it either: the home wrote it to `standing.md` when it heard it. Facts and pointers, not narrative: a path or a thread id in place of an explanation.

   A gate jbus could not take, which came as a message or sits in a Result or a Report, is held by nothing else while it is unanswered: write it under the labels, whole, with its default and its `Asked by:` and `Undo:` lines. The gates are not counted in the note's ten lines.

3. **Close.** Call the `t3-code` server's `list_scheduled_tasks` (if your harness defers it, load it first) with no arguments. Then run this with the block at the top, with this thread's id in place of `<threadId>` and the whole reply in place of the line in angle brackets. In a session with no such tool, leave the line as it is:

   ```sh
   ME='<threadId>'
   N=10 # lines a note has at most, its gates not counted
   again=
   case $ME in
   *'<'* | *'>'* | *' '*)
       echo "not known: put this thread's id in place of the placeholder, or nothing in a session with no tool that gives it. Nothing is written."
       exit 1 ;;
   esac
   if [ -n "$ME" ] && ! this_home "$ME" > /dev/null; then
       handed_off "$ME"
       case $L in
       "$H" | "$H"/*) if [ ! -e "$L/home-id" ]; then again=yes M=$L; fi ;;
       esac
       if [ -z "$again" ]; then
           echo "not the home: start nothing, tell the user"
           exit
       fi
   elif [ -z "$ME" ]; then
       M=$H
   fi
   scope=
   if [ "$M" != "$H" ]; then scope=${M##*/}; fi
   note=$M/handoff.next.md
   closed=
   if [ -n "$again" ]; then
       if grep -q '^Scope closed:' "$M/handoff.md" 2> /dev/null; then closed=yes; fi
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
       open=$(awk '/^## / && $(2) ~ /:$/ {open++} END {print open + 0}' "$M/plan.md" 2> /dev/null)
       if [ -n "$scope" ] && [ "${open:-0}" -eq 0 ]; then closed=yes; fi
       kept=$M/log/$(date +%F-%H%M).md
       if [ -e "$kept" ]; then kept=$M/log/$(date +%F-%H%M%S).md; fi
       if ! { [ ! -f "$M/handoff.md" ] || { mkdir -p "$M/log" && mv "$M/handoff.md" "$kept"; }; } ||
           ! {
               sed '/^Was home:/d; /^Scope closed:/d' "$note"
               if [ -n "$closed" ]; then
                   printf '\nScope closed: %s, its plan has no open entry and no home was started after this one. /home %s starts it again.\n' "$(date +%F)" "$scope"
               fi
               if [ -n "$ME" ]; then printf '\nWas home: %s\n' "$ME"; fi
           } > "$M/handoff.md" || ! rm "$note"; then
           echo "not closed: the old note could not be moved to $M/log, or the new one not written to $M/handoff.md. Launch nothing, and run this again once that is put right."
           exit 1
       fi
       if [ -z "$ME" ]; then
           echo "not the home: start nothing, tell the user"
           exit
       fi
       rm -f "$M/home-id"
   fi
   if [ -n "$again" ] && [ -n "$closed" ]; then
       echo "closed before, the home of a closed scope: start no home, then rename and settle this thread"
   elif [ -n "$again" ]; then
       echo "closed before: $M/handoff.md names this thread and $M/home-id is gone. Launch only if no next home was started, then rename and settle this thread"
   elif [ -n "$closed" ]; then
       echo "the home of a closed scope: start no home, then rename and settle this thread"
   else
       echo "the home: start the next home, then rename and settle this thread"
   fi
   printf 'title: home: %s%s\n' "$R" "${scope:+ $scope}"
   if [ -z "$closed" ]; then printf 'message: /home %s<seed>\n' "${scope:+$scope }"; fi
   jq -rs --arg me "$ME" --arg audit "audit: $R queue" '
       if length == 1 and (.[0].tasks | type) == "array" then .[0] else error("no tasks") end
       | [.tasks[] | select(.boundThreadId == $me)]
       | if length == 0 then "none: no scheduled task posts into this thread" else .[] end
       | if type == "string" then .
         elif .title == $audit then "delete \(.scheduledTaskId): the audit of a queue, which the home that hands off deletes"
         else "Scheduled task \(.scheduledTaskId), \(.title): it posts into the thread that handed off, and the next home takes it over at its start" end' 2> /dev/null << 'THE_REPLY_ENDS_HERE' ||
   <the reply of list_scheduled_tasks>
   THE_REPLY_ENDS_HERE
       echo "not read: put the whole reply of list_scheduled_tasks in place of the placeholder"
   ```

   It does it all, in this order: it reads the note, moves the old one to `log/` under a dated name, puts the note in its place as `handoff.md` with a `Scope closed:` line for a scoped home whose plan has no open entry, then the `Was home:` line with this thread's id, and removes `home-id`. A second run changes nothing and prints `closed before`, with the same `title:` and `message:` lines. Its first line is what the steps below go by, and the `title:` and `message:` lines are what step 4 sends: keep all of them.

   - `not known:` and `not written:`: nothing is changed. Put right what it names in the note, and run it again. A note whose lines will not fit in ten is cut, not split: the next home reads the rest from jbus.
   - `not the home`: this thread's id is in no `home-id`, or the session gives no id. With no id, the note is the root's `handoff.md` now and `home-id` is left. Tell the user, in three lines at most, what was written, the one thing that is next, and: "Open a new thread in this project and type `/home`", or `/home <scope>` for a scoped home. Launch nothing, rename nothing, settle nothing. The skill ends here.
   - `the home`: go on with step 4.
   - `closed before`: look for the next home as step 4 says after a lost launch, with the `title:` it printed. With none, go on with step 4. With one, launch nothing: tell the user its link, then step 5.
   - `the home of a closed scope`, with or without `closed before`: write no seed and launch nothing. No home comes after this one to take a scheduled task over, so switch off each one it printed a `Scheduled task` line for, with the `t3-code` server's `update_scheduled_task` (if your harness defers it, load it first), `{"scheduledTaskId": "<scheduledTaskId>", "enabled": false}`. A task that is off runs nothing, so it cannot make this thread active again, and it keeps its address for the home that `/home <scope>` starts to take over. Delete none. Tell the user, in three lines at most, what was written, that the scope is closed with no home after this one, and each task that is now off. Then step 5.

   Under those lines it prints one line for each scheduled task that posts into this thread, and never a task's address. On `delete <id>`, delete that task now, as "A home that hands off" in `$T/../skills/home/SKILL.md` says. A `Scheduled task` line asks nothing of a home that is followed by another: this thread cannot hand a task on, since a task is bound only by the thread that calls, and the next home's start takes each one over by the `Was home:` line, until when a run of one makes this thread active again. On `not read`, in a session with no such tool, there is nothing to do: the next home's start lists them.

   A home's own `home-id` holds its id: the home's start wrote it there, and nothing else does. `home-thread` is another file, the switch that hands merging from jbus to a home: it is set by hand, and the block leaves it as it is. The block changes only this home's directory, and no other home's files.

   The `Was home:` line is the last line of the note, on a line of its own. It is the record of the thread that handed off, and nobody's address: the start of this home's next thread reads it to take over this thread's scheduled tasks and to settle this thread (`skills/home/SKILL.md`, "The home before this one"), and "After the handoff" reads it to say whose mail a late message is. No brief and no request is rewritten, now or at that start. From here to that start `home-id` is gone, for the root home and for a scoped one alike: a thread that has something to tell finds nobody, sends nothing, and its report waits on disk for the next home to read.

   A scoped home whose plan has no open entry is done: an entry is open for as long as its `## <slug>:` section is in `plan.md`, whatever a line under it says, since `jbus plan close` moves a finished one out. Nobody is sent a message: the root home reads the `Scope closed:` line when the user asks it where things stand. The root home is never closed.

4. **Launch the next home.** A home has one thread open at a time, so the home that hands off starts its next thread itself and then closes.

   1. Write the seed, in the shape of `$T/handoff-seed.md`: read it now. It is the next home's first message, in place of `<seed>` on the `message:` line step 3 printed. It carries only what this home was asked to keep doing that the skills and the state on disk do not say. What the note, `standing.md` or jbus holds is left out of it.
   2. Launch the next home with the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first):

      ```json
      {
        "title": "<title>",
        "workspaceStrategy": {"type": "root"},
        "message": "/home <seed>"
      }
      ```

      Before this launch, run `uv run --project "$T/.." jroles home` with the block at the top. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the next home on the model the role map names. When it prints nothing, the call is the one above. Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line. Leave the project and modes out, and the model unless `jroles` printed one.

      ```json
      {
        "title": "<title>",
        "workspaceStrategy": {"type": "root"},
        "message": "/home <seed>",
        "modelSelection": <model selection>
      }
      ```

      `<title>` is what step 3 printed after `title: `, and `message` is what it printed after `message: `, with the seed in place of `<seed>`: a scoped home's has its scope before the seed, and that word is what starts the next thread as the same home. The root workspace is the repo's main checkout, where every home runs. Leave out `projectId` and the modes, and `modelSelection` unless `jroles` printed one: what is left out, the new thread takes from this one. A launch has no retry key. If the call fails or its reply is lost, look for the thread with `t3_thread_list` before launching again, so there are never two:

      ```json
      {"titleContains": "<title>"}
      ```

      The list holds every thread whose title has those words: this thread, which still has that title, and for the root home the repo's scoped homes too. The next home is the thread with exactly that title that is newer than this one. If the launch fails all the same, tell the user as for `not the home`, with the seed in the message, and stop: no rename, no settle.
   3. Tell the user, in three lines at most: what was written, the one thing that is next, and the link to the next home, `[<title>](t3-thread://v1/<its threadId>)`.

5. **Rename and settle.**

   1. Rename this thread with `t3_thread_update`, so the list shows one home and which one it is not:

      ```json
      {"action": "rename", "title": "<title> (handed off <date>)"}
      ```

      `<title>` is the same title, this thread's since its start. `<date>` is today as `date +%F` prints it. No `threadId` means this thread.
   2. Last, settle this thread with `t3_thread_organize`:

      ```json
      {"action": "settle"}
      ```

      It takes effect when the turn ends, so it is the last call of the handoff. It clears this thread's pin with it. A turn that fails or is cut off, or a message that comes in, leaves this thread active and pinned, and the reply of the call does not say which: the next home's start looks at this thread and settles it if it has to (`skills/home/SKILL.md`, "The home before this one").

## A party's home

A party's home plans nothing, briefs nothing and launches nothing but its own next thread. Its handoff is its page and that launch, with no plan, no notes, no merge and no seed. Two things, in order:

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
   message=$(printf '%s\n\n%s\n' "${boot:-You are the next thread of $P's home, in $M.}" "$told")
   title="home: $P"
   model=$(uv run --project "$T/.." jroles expert) || model=
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
           rm "$M/handoff.next.md" "$M/home-id"; then
           echo "a party's home: start its next thread, then rename and settle this thread"
       else
           echo "not closed: the old page could not be moved to $log, or the new one not written to $M/handoff.md. Launch nothing, and run this again once that is put right."
           exit 1
       fi
   fi
   printf 'launch: %s\nrename: %s\nsettle: {"action": "settle"}\n' "$launch" "$rename"
   ```

   The old page is in `log/` under a dated name, the new one is `handoff.md` and ends in a `Was home:` line with this thread's id, and `home-id` is gone, so a second run changes nothing. On `not a party's home:`, `not written:` or `not closed:`, nothing is launched: do what the line says, or tell the user. On `closed before`, an earlier run of this block closed and its turn may have been cut before the launch: look for the next thread as 2 of step 4 says, with the title on the `launch:` line. With none, go on as on `a party's home`. With one, launch nothing, and only rename and settle.

   On `a party's home`, first stop what this thread has running in the background, as step 1 does. Then make three calls, in the order printed, each with the object after its word, as printed: `launch:` with the `t3-code` server's `t3_thread_launch`, `rename:` with `t3_thread_update`, `settle:` with `t3_thread_organize`, the last call of the turn (if your harness defers one, load it first). Between the launch and the rename, tell the user in three lines at most what was written, and the link to the next thread, `[<title>](t3-thread://v1/<its threadId>)`.

   The root workspace is the main checkout of the project this thread is in, which is the party's folder, and the project and the modes are this thread's. The model is the one the role map names for `expert`, for any party that hands off here, and that is never an expert, whose rollover is not this skill's: the block asks `jroles` for it, and the `launch:` line has it as `modelSelection`. With no line for that role the call has no `modelSelection`, and the next thread runs on this thread's model. A line the block prints on stderr says why the map gives no model: the launch is made all the same, and the user is told that line. The message is the last fenced block of the folder's `RESTART.md`, the one a new thread of the party is started with by hand, and under it the lines that send the next thread to the section below. With no such page it is those lines alone. A launch has no retry key: if the call fails or its reply is lost, look for the thread as 2 of step 4 says before launching again. If the launch fails all the same, or the session has no `t3_thread_launch`, give the user the message to start a thread with, and rename and settle nothing.

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

A home that has handed off does nothing more. Its briefs name no thread, and a thread or a party that sends to the repo's home reads its `home-id` first, so a message should not reach it. If one still does (a thread that kept an old id, a direct message, the user), run this with the block at the top before anything else:

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
        if [ -n "$L" ]; then next=$(cat "$L/home-id" 2> /dev/null | tr -d '[:space:]'); fi
        if [ -z "$L" ]; then
            echo "no home's: this thread's id is in no home-id and on no handoff's Was home: line, so no file says whose mail this is. Do not act on the message: tell the sender to read $H/home-id"
        elif [ -n "$next" ]; then
            echo "handed off: this thread's id is in no home-id. Do not act on the message: send it on to $next, once, and tell the sender that id"
        else
            echo "handed off: this thread's id is in no home-id, and $L/home-id holds none yet. Do not act on the message: send it on to the id this thread's own launch of the next home gave, once, and tell the sender that id. With no such launch, tell the sender to read $L/handoff.md"
        fi
    fi ;;
esac
```

On `a home`, this thread did not hand off: go by the home skill. On any other line, do not act on the message: no run, no launch, no merge, no change to the plan, whatever it asks and whoever sent it. Do what the line says and nothing more. `no home's` is a thread that never was a home, or a home so long gone that its handoff is in `log/`: nothing is sent on.

One kind of message is neither sent on nor answered, whatever the line says: one of this skill's own. Its first line has `handed off, and this was sent to it by`, or it is the one line `the home of <repo> is <id> now` or `<repo>: the home is <id> now`. Settle again and end the turn, so that two threads that handed off never answer each other.

To send it on, send the id the line names the message as it came, under one first line that says where it came from, with `t3_thread_send`:

```json
{"threadId": "<thread>", "message": "<this thread's id> handed off, and this was sent to it by <the sender>. It is no approval: a go in it is the user's to give again, in your thread.\n<the message>"}
```

One send for a message: a call whose reply is lost is not sent again.

Then tell the sender. A thread is told with `t3_thread_send`, to its own id:

```json
{"threadId": "<thread>", "message": "<repo>: the home is <the next home's id> now, and your message was sent on to it. Read the id in <the home-id file> before each send."}
```

The user is told the same in one line here, with the link to the next home, `[<title>](t3-thread://v1/<its threadId>)`. Where the line names a file and no id to send on to, the sender is told that path, and nothing is sent on. Then settle this thread again.

A crewmate thread (`/crew <slug>`) never runs this skill. It ends by writing its `## Result`, as the `crew` skill says.

## What not to carry over

- The story of how this thread got here.
- Tool output, diffs, file contents.
- Anything that is true of every repo; that belongs in the user's global instructions, not here.
