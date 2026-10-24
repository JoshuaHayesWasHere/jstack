## When a home starts

A home starts in one of two ways.
The user types `/home`.
Or the session-start hook (`hooks/home-start.sh` in the layout that holds this skill) adds a `[home]` line to a new T3 Code thread opened in the main checkout of any repo, one that never had a home included, and the thread invokes this skill before its first reply.
In the second case the user's first message is their opening request, unless it starts with `/home`, which is the first case: do the five steps below, keep step 5 to the lines that matter for that request, and then take the request as the start of planning.

The first word after `/home` may name a scope: step 1 says. Text after `/home`, or after the scope, that says the previous home wrote it is a seed: that home's handoff launched this thread with it. It is not the user's opening request. Do the five steps, do what the seed says to keep doing, and do not wait for the user: step 5 merges, launches and gives the status by itself.

Escalations reach the user through jbus's webhook, to Sous Chef. A home sends no other thread a status and keeps no registry of homes: jbus is it.

The user opts out with `/nohome` (the `nohome` skill), for one thread or for the repo.

1. Work out which home this is, and make `$H` if this is the repo's first home. `plan.md` is what says a home has started: `$H/plan.md` the root home, for this step and for the hook alike, and `$H/<scope>/plan.md` a scoped one. Run this with the block at the top, with everything typed after `/home` in place of `<the text after /home>`, or nothing when nothing was typed after it or nobody typed `/home`:

   ```sh
   here=$(pwd -P)/
   root=$(cd "${H%/*}" 2> /dev/null && pwd -P || echo /dev/null)
   case $here in
   "$root"/_?*/*)
       party=${here#"$root"/_}
       echo "a party's home: ${party%%/*}'s, in $root/_${party%%/*}, and not a repo's, so /home starts nothing here. Nothing is written."
       exit ;;
   esac
   the_text() {
       cat << 'THE_TEXT_ENDS_HERE'
   <the text after /home>
   THE_TEXT_ENDS_HERE
   }
   typed=$(the_text)
   word=$(printf '%s\n' "$typed" | awk 'NF {print $(1); exit}')
   case $word in
   '' | .* | *[!A-Za-z0-9._-]* | tasks | scouts | reports | log) scope= ;;
   *) scope=$word ;;
   esac
   case $typed in
   '<the text after '*)
       echo "not filled in: put what was typed after /home in place of the placeholder, or nothing" ;;
   *)
       if [ -n "$scope" ] && [ -f "$H/$scope/plan.md" ]; then
           printf 'scope %s\ntitle: home: %s %s\n' "$scope" "$R" "$scope"
       elif [ "$(printf '%s\n' "$typed" | wc -w)" -eq 1 ]; then
           echo "no scope: $R has no scope $word, there is no $H/$word/plan.md. Only the root home makes a scope, when the user asks for one. Nothing is written."
       else
           printf 'root\ntitle: home: %s\n' "$R"
           if [ ! -f "$H/plan.md" ]; then
               mkdir -p "$H" && touch "$H/plan.md" "$H/notes.md" && echo "first home: made $H"
           fi
       fi ;;
   esac
   ```

   On `a party's home:`, the thread is in the folder of a party that is no repo's home, such as an expert's: this thread is no home, and none of the steps below is done. A thread that a message started goes on with that message, and one the user typed `/home` in tells the user that line and stops. How such a thread is replaced is not this skill's to say: `$T/../skills/handoff/SKILL.md` "A party's home", or for an expert, whose folder has a `CHARTER.md`, `$T/../skills/expert/SKILL.md` "When to roll over". Otherwise its first line says which home this is. `root`: the repo's root home, and the text, if there is any, is a seed or the user's opening request. `scope <word>`: that scope's home, and what follows the word is its seed. On `no scope:`, one word was typed and it names no scope: tell the user what the line says and stop, this thread is no home. When it prints `first home`, say this is the repo's first home. What was in `$H` before stays: a home in another repo may have kept briefs and notes there.
2. Name this thread for what it is, with the `t3-code` server's `t3_thread_update` (if your harness defers it, load it first):

   ```json
   {"action": "rename", "title": "<title>"}
   ```

   `<title>` is what step 1 printed after `title: `. No `threadId` means this thread. T3 Code cannot nest a crewmate's thread under its home, so the title says what each thread is. If the session truly has no such tool, deferred or not, do nothing.

   Then pin this thread, with `t3_thread_organize`:

   ```json
   {"action": "pin"}
   ```

   A home is pinned for as long as it is the home. A thread that is pinned already keeps its place, so a second start changes nothing, and the settle of its handoff clears the pin.
3. Put this thread's id on disk, so the threads this home sends out can report back to it and the block that finds this home can find it. The `t3-code` server's `t3_thread_configuration` with no arguments gives the id as `threadId` (if your harness defers it, load it first). Shell variables do not last from one call to the next, so run this in one call with the block at the top, with the id in place of `<threadId>` and the first line step 1 printed, `root` or `scope <word>`, in place of `<which home>`:

   ```sh
   ME='<threadId>'
   home='<which home>'
   M=
   case $home in
   root) M=$H ;;
   'scope '.* | 'scope '*[!A-Za-z0-9._-]* | 'scope tasks' | 'scope scouts' | 'scope reports' | 'scope log') ;;
   'scope '?*) M=$H/${home#scope } ;;
   esac
   case $ME in
   '' | *'<'* | *'>'*) M= ;;
   esac
   if [ -z "$M" ] || [ ! -f "$M/plan.md" ]; then
       echo "not written: this needs the thread's id, and root or scope and its name as step 1 printed it"
   else
       printf '%s\n' "$ME" > "$M/home-id"
       switch=$(cat "$H/home-thread" 2> /dev/null | tr -d '[:space:]')
       if [ -n "$switch" ]; then
           echo "jbus does not merge here: $H/home-thread holds $switch. Nothing empties it but the user, by hand."
       fi
   fi
   ```

   The file is that one line and nothing else, in this home's own directory, and it replaces whatever an earlier home left there. The `handoff` skill removes it. On `jbus does not merge here`, tell the user that line as it is, at once: `$H/home-thread` is the merge switch, an id in it keeps jbus from running `jmerge` for this repo, and a home that started before the id moved to `home-id` left its own there. The block reads the switch and never writes it.

   Writing the file is all it takes for the threads this home's last thread left out to report here. A brief or a request names its home by its scope, or names none for the root home, and never a thread: each thread reads this file when it sends, so the block rewrites no brief and no request, and an approval of a queued one stands. Until this runs, those threads report to nobody, and what they wrote waits on disk. On `not written:`, nothing is: fill in what it names and run it again. With no tool that gives the id, skip this step as the root home. A scoped home cannot go on without its id: tell the user and stop.

   Then do what "Its scheduled tasks" says, under "The home before this one" below these steps, before step 4.
4. See where things stand.
   Read `$H/standing.md` and `$M/handoff.md` whole, the user's standing rules and the note the last home left: the block below prints the path of each that is there.
   Where the repo has a context pack, `<checkout>/docs/context/`, the block prints the path of its `INDEX.md` after those two: read it whole as well.
   It is the light layer, one line a note with what the note answers and the commit it was checked at: open a note under `<checkout>/docs/context/notes/` only when a step needs it.
   When what you know disagrees, the first in this order wins: the user's word and `standing.md`, then `$H/notes.md`, then the source at its current revision, then the pack, then the model's memory, always labelled "from memory, not checked".
   A pack line that a layer above it contradicts is reported, not acted on: say it to the user, and brief the note's fix as a pull request to `<checkout>/docs/context/`.
   A repo with no pack gets one by a brief that starts from the skeleton in `$T/context/`, which `$T/context/README.md` explains, and [features/jpack/docs/context.md](../../../jpack/docs/context.md) of the jstack checkout says how a pack is checked and pruned.
   Then run it in one call with the block at the top, the block that finds this home and the block that reads jbus ("Gates"), in the main checkout:

   ```sh
   : "${SEP:?run the block that reads jbus first}"
   W=110 # characters a line is cut at
   clip() { awk -v w="${1:-$W}" '{ if (length($(0)) > w) print substr($(0), 1, w - 3) "..."; else print }'; }
   atmost() { awk -v n="${1}" -v more="${2}" 'NR <= n {print} END {if (NR > n) print "... and " NR - n " more: " more}'; }
   scope=
   if [ "$M" != "$H" ]; then scope=${M##*/}; fi
   for f in "$H/standing.md" "$M/handoff.md" "$M/handoff.next.md"; do
       if [ -f "$f" ]; then echo "read whole: $f"; fi
   done
   if top=$(git rev-parse --show-toplevel 2> /dev/null) && [ -f "$top/docs/context/INDEX.md" ]; then
       echo "read whole: $top/docs/context/INDEX.md"
   fi
   echo "## plan"
   if ! command -v jbus > /dev/null || ! plan=$(jbus plan ${scope:+--scope "$scope"}); then
       echo "no jbus plan: read $M/plan.md whole"
   else
       printf '%s\n' "$plan" | clip 150 | atmost 12 "jbus plan${scope:+ --scope $scope}"
   fi
   echo "## queue"
   if [ -n "$WHY" ]; then
       echo "$WHY"
   elif ! shown=$(jbus --project "$P" queue show 2>&1); then
       printf '%s\n' "$shown" | head -n 1 | clip
   else
       rows=$(printf '%s\n' "$shown" | awk '
           function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
           /^\|/ {
               line = $(0); gsub(/\\\|/, "\001", line)
               n = split(line, cell, "|")
               for (i = 1; i <= n; i++) gsub(/\001/, "|", cell[i])
               if (!head) { for (i = 2; i < n; i++) at[trim(cell[i])] = i; head = 1; next }
               if (trim(cell[2]) ~ /^-+$/) next
               print "row\t" trim(cell[at["slug"]]) "\t" trim(cell[at["slug"]]) " | " trim(cell[at["status"]]) " | " trim(cell[at["pr"]]) " | " trim(cell[at["why"]])
               next
           }
           NF { print (head ? "end" : "waits") "\t" $(0) }')
       printf '%s\n' "$rows" | awk -F '\t' '$(1) == "waits" && n++ == 0 {print $(2)}'
       printf '%s\n' "$rows" | awk -F '\t' '$(1) == "waits" && n++ > 0 {print $(2)}' | clip | atmost 3 "jbus --project $P queue show"
       printf '%s\n' "$rows" | awk -F '\t' '$(1) == "row" {print $(2) "\t" $(3)}' | while IFS="$(printf '\t')" read -r slug line; do
           if [ "$(whose "$H/tasks/$slug.md")" = "$M" ]; then printf '%s\n' "$line"; fi
       done | clip | atmost 10 "jbus --project $P queue show"
       printf '%s\n' "$rows" | awk -F '\t' '$(1) == "end" {print $(2)}' | clip | atmost 2 "jbus --project $P queue show"
   fi
   echo "## questions"
   if [ -f "$M/gates.md" ]; then echo "a gates file: run the block of \"Move the ones a file still has\" (\"Gates\"), then this block again"; fi
   if [ -n "$WHY" ]; then
       echo "$WHY"
   elif [ -z "$OPEN$LINKS" ]; then
       echo "none is open"
   else
       printf '%s\n' "$OPEN" | while IFS=$SEP read -r n slug asked took rest; do
           if [ -n "$n" ]; then printf 'question %s, from %s: %s (default: %s)\n' "$n" "$slug" "$asked" "$took"; fi
       done | clip | atmost 5 "the block of \"Show the open ones\""
       printf '%s\n' "$LINKS" | grep -c . | awk '$(1) > 0 {print $(1) " for this home, a link with a conflict: the block of \"Show the open ones\""}'
   fi
   echo "## noticed"
   if ! command -v jbus > /dev/null || [ -z "$P" ]; then
       echo "no jbus project: no Noticed line is kept for this repo"
   elif ! shown=$(jbus --project "$P" noticed 2>&1); then
       printf '%s\n' "$shown" | head -n 1 | clip
   else
       printf '%s\n' "$shown" | while IFS= read -r line; do
           case $line in
           'none is new' | 'none: '*) printf '%s\n' "$line" ;;
           *) if mine "${line%%:*}"; then printf '%s\n' "$line"; fi ;;
           esac
       done | clip | atmost 5 "jbus --project $P noticed"
   fi
   echo "## merged"
   L="$H/merge.log"
   lines=$(grep -c '' "$L" 2> /dev/null)
   lines=${lines:-0}
   seen=$(cat "$M/merge-seen" 2> /dev/null)
   case $seen in
   '' | *[!0-9]*) seen=$lines ;;
   esac
   if [ "$seen" -gt "$lines" ]; then seen=0; fi
   tail -n "+$((seen + 1))" "$L" 2> /dev/null | while IFS= read -r line; do
       said=$(printf '%s\n' "$line" | cut -c18-)
       case $said in
       'merged '*)
           slug=${said#merged * }
           if [ "$(whose "$H/tasks/${slug%% *}.md")" = "$M" ]; then printf '%s\n' "$line"; fi ;;
       esac
   done | clip | atmost 5 "$L"
   echo "## to read"
   S="$M/read-seen"
   unread=$(for f in "$H"/tasks/*.md "$H"/scouts/*.md; do
       [ -f "$f" ] || continue
       heading=$(grep -E '^## (Result|Report)' "$f" | tail -n 1)
       said="${f#"$H"/}: $heading"
       if [ -n "$heading" ] && ! grep -qxF -e "$said" "$S" 2> /dev/null && [ "$(whose "$f")" = "$M" ]; then
           printf '%s\n' "$said"
       fi
   done)
   if [ ! -e "$S" ]; then
       printf '%s\n' "$unread" | grep . > "$S"
       echo "no mark yet: $(grep -c '' "$S") headings of this home's are marked read in $S, and none is shown"
   else
       printf '%s\n' "$unread" | grep . | atmost 8 "mark these read, then run this block again"
   fi
   ```

   It prints this home's part of what jbus and the files hold, each line cut at 110 characters, a line of the plan at 150 and one under `## to read` not at all, and each part at a few lines, with the command that prints the rest. Under `## plan`, one line for each entry of this home's plan: the slug, its one line, and its status. No status is written by hand, in the plan or anywhere else: `jbus plan` counts it from the entry's queue rows each time it is read, as `4 of 7 merged, #383 at pr, 1 queued not approved`. An entry with no row shows its `Stage:` line, and one from before shows its old line as `(typed) Status: ...`, which nobody checked. The plan is not read whole: read an entry's own section of `$M/plan.md` when you take that entry up, its "Done when" list and the user's words under `Decisions:`. On `no jbus plan`, read the file whole. Under `## queue`, what waits on the user, then each open row of this home's as its slug, status, pull request and why it waits. Under `## questions`, each open question of this home's, by its number. Under `## noticed`, each `Noticed` line of this home's briefs and requests that jbus keeps as new, by its key: mark each one once, with `jbus --project "$P" noticed take <key> --row <the queue row or plan entry it went to>` or `drop <key> --why <words>`, both with `--by` and `--at` as `queue remove` takes them. Under `## merged`, each `merged` line `jmerge` logged since this home's mark in `merge-seen`, which the merge step of step 5 moves, and not this block.

   Under `## to read`, the last `## Result` or `## Report` heading of each brief and request that is this home's and that no home has marked read, at most eight: what came in that no home has read. A `## Review` or a `Finding:` line added under a heading that is marked shows nothing again. A home with no `$M/read-seen` yet marks every heading there is now, shows none, and says so: what came before the mark is the last homes'. Read each section it printed, then mark them read with the block below, and only then: a start cut off before the mark shows them to the next home again. A path under `read whole:` that ends in `handoff.next.md` is a note the last home wrote and was cut off before it put in place: read it too, for a gate only it holds. A brief or a request is this home's by what `whose` prints for it: a scoped home's when its `Home:` line names the scope, and the root home's when it has no such line or one that names no home. One written before, with a thread id on the line, is the home's whose `home-id` or whose handoff's `Was home:` line has that id. Read nothing else yet: not the log, not `plan.md`, not `$H/notes.md`. A step that needs a fact of the repo, its check command or a trap the notes name, reads `notes.md` then. The code is never the home's to read.

   **Mark what was read**, with the block at the top and the block that finds this home, with the lines step 4 printed under its last part that you read, as printed, in place of the line in angle brackets:

   ```sh
   S="${M:?run the block that finds this home first}/read-seen"
   grep -E '^(tasks|scouts)/[^/: ]+\.md: ## (Result|Report)' << 'READ' | while IFS= read -r line; do
   <the lines step 4 printed that you read>
   READ
       if ! grep -qxF -e "$line" "$S" 2> /dev/null; then printf '%s\n' "$line" >> "$S"; fi
   done
   echo "marked read: $(grep -c '' "$S" 2> /dev/null || echo 0) headings in $S"
   ```

   It keeps each line once. The lines under `## to read` are never cut, so each is the heading as it is. The status of "When a thread sends a message" runs step 4's block too, and marks in the same way.
5. First, where step 4 printed `no project:` under `## questions`, do what "On the bus" says, below these steps: a repo with a home is a jbus project. Then do steps 2 and 3 of "When a thread sends a message", once, without waiting for a word: run the merge step, which merges what is ready or, while jbus merges, prints what jbus merged since the last home read the log and what each open pull request waits for, update the plan, and launch what can start. Then run the sweep, the last block of "Merging a pull request that is ready", and do what that section says for each of its two lists: a start is the one time it is run. Both go by the block of "Who merges", and run no `jmerge` on `jbus merges`. A message sent between the last home's handoff and this start reached nobody, a `fixed and green` line among them, and step 4 has already read what landed. Then tell the user where things stand in at most six lines: what crewmates and scouts finished since the last home, what this start merged, swept and launched, what is still out, what is next in the plan and the note, any open decision, and the open questions step 4 printed. A gate is piped to jbus and no message brings it: where step 4 printed a question, give it to the user as "Show the open ones" ("Gates") says, by its block. Before that summary, run the first block of "A queue and its hourly audit" and do what it prints: an audit is its home's own, so this home schedules one for a queue that is out and deletes the one the last home left. Last before the summary, do what "Its thread" says, under "The home before this one".

### On the bus

Every repo with a home is a project of jbus's config: jbus launches, merges, keeps the questions and carries the user's word only for a project it has. `/new-home` adds the repo, and a home started by `/home` in a repo, or before that step was there, did not. So a home that finds its repo missing adds it, before step 5 merges or launches anything. Run this in the main checkout, in one call with the block at the top, the block that finds this home and the block that reads jbus ("Gates"):

```sh
: "${SEP:?run the block that reads jbus first}"
C=$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")
if [ -n "$P" ]; then
    echo "on the bus: $R is jbus project $P"
elif ! command -v jbus > /dev/null; then
    echo "not on the bus: jbus is not installed here, so nothing is added: sh install.sh in $(realpath "$T/../source" 2> /dev/null || realpath "$T/..")"
else
    echo "not on the bus: $R has no project in jbus's config: add it with the block of step 3 of $T/../skills/new-home/SKILL.md, checkout $C"
fi
```

On `on the bus`, there is nothing to do. On `jbus is not installed`, tell the user the line and go on. On `has no project`, add it, with the one block that adds a repo, so this start and `/new-home` cannot drift:

1. Find the repo's T3 Code project id as step 2 of `/new-home` does: `t3_project_list` with `{"limit": 100}`, the entry whose `workspaceRoot` is the checkout the line names, asking again with each `nextCursor` until it is found or the list ends. Make no project here: with none found, or no such tool, tell the user `needs you: add <the checkout> as a project in T3 Code, then start a home again`, and go on to step 5.
2. Read step 3 of `$T/../skills/new-home/SKILL.md` now, and run its block in the main checkout, with the checkout and the project id filled in.
3. Read its lines as `/new-home` does: `done`, `already`, or `needs you:` and what the user runs. Tell the user the `jbus project` line.

The block runs `jbus project add`, the only writer of jbus's config. Never open, print or edit that file. It never writes `home-thread`, whatever the home's rules say: a repo it adds is one jbus merges for, unless the user has put an id in that switch by hand. A home that cannot add its repo goes on with step 5: the pass names it among the homes not on the bus, in `jbus status` and on the view's machine row, until somebody adds it.

### The home before this one

A handoff leaves two things that only the next home can see to. Both go by the `Was home:` line of `$M/handoff.md`, so a second run, and the start of a home whose last thread was cut off in its handoff, end in the same state: this thread pinned, no scheduled task that posts into the last one, and the last one settled.

**Its scheduled tasks.** Step 3 sends the start here. A scheduled task posts into the thread that made it until another thread takes it, and each run of it makes that thread active again, settled or not. Call the `t3-code` server's `list_scheduled_tasks` (if your harness defers it, load it first) with no arguments. Then run this in one call with the block at the top and the block that finds this home, with the whole reply in place of the line in angle brackets, and nothing in place of `<the ids a call was refused for>`:

```sh
refused='<the ids a call was refused for>'
the_reply() {
    cat << 'THE_REPLY_ENDS_HERE'
<the reply of list_scheduled_tasks>
THE_REPLY_ENDS_HERE
}
case $refused in
*'<'* | *'>'*) refused= ;;
esac
was=$(sed -n 's/^Was home:[[:space:]]*\([^[:space:]]*\).*/\1/p' "$M/handoff.md" 2> /dev/null | head -n 1)
if [ -z "$was" ] || [ "$was" = "$ME" ]; then
    echo "no home before this one: $M/handoff.md names none, so no task is taken over"
else
    said=$(the_reply | jq -rs --arg was "$was" --arg audit "audit: $R queue" --arg refused " $refused " '
        if length == 1 and (.[0].tasks | type) == "array" then .[0] else error("no tasks") end
        | [.tasks[] | select(.boundThreadId == $was)]
        | if length == 0 then "none: no scheduled task posts into \($was)" else .[] end
        | if type == "string" then .
          elif (.scheduledTaskId as $id | $refused | index(" \($id) ")) then "left \(.scheduledTaskId): \(.title) still posts into \($was), the call for it was refused"
          elif .title == $audit then "delete \(.scheduledTaskId): the audit of the home before this one"
          else "take \(.scheduledTaskId): \(.title) posts into \($was), the home before this one" end' 2> /dev/null) || said="not read: put the whole reply of list_scheduled_tasks in place of the placeholder"
    printf '%s\n' "$said"
    kept=
    if [ -s "$M/audit" ]; then read -r kept by < "$M/audit"; fi
    case $said in
    *"delete ${kept:-no audit is kept}: "*) rm -f "$M/audit" "$M/audit-seen" ;;
    esac
fi
```

It prints one line for each task that posts into the last home, and never a task's address. It names no task of another home: that home's own start takes those.

- `take <id>`: take the task over with the `t3-code` server's `update_scheduled_task` (if your harness defers it, load it first), the id in place of `<scheduledTaskId>`:

  ```json
  {"scheduledTaskId": "<scheduledTaskId>", "bindToCurrentThread": true}
  ```

  Nothing else in the call: the task keeps its title, its prompt, its schedule and, for a webhook, its address, so whoever posts to it is told nothing. One that was switched off stays off: tell the user its title. A task can only be bound by the thread that calls, which is why this is done here and not by the home that handed off.
- `delete <id>`: delete it, as "Delete it" under "A queue and its hourly audit" says. An audit is its home's own, and step 5 schedules this home's: the block has dropped `$M/audit` where it kept that id. A delete that answers that there is no such task is done all the same.
- `none` and `no home before this one`: nothing to do.

After the calls, list the tasks again and run the block again, with the id of each task a call was refused for, a space between two, in place of `<the ids a call was refused for>`. It prints `none` when every one is taken. On `left <id>`, the task still posts into the last home: tell the user its id and what the call answered, make no second call for it, and go on.

**Its thread.** Step 5 sends the start here, as its last look. A home that hands off settles itself, which takes effect only when its turn ends well, and a settle is what clears its pin. So the reply of that call says nothing: look, once the last home has had the time of this start to end its turn. Call `t3_thread_list`, with this thread's title, which the last home's begins with:

```json
{"titleContains": "<title>"}
```

Then run this in one call with the same two blocks, with the whole reply in place of the line in angle brackets:

```sh
was=$(sed -n 's/^Was home:[[:space:]]*\([^[:space:]]*\).*/\1/p' "$M/handoff.md" 2> /dev/null | head -n 1)
if [ -z "$was" ] || [ "$was" = "$ME" ]; then
    echo "no home before this one: $M/handoff.md names none, so no thread is looked for"
else
    jq -rs --arg was "$was" '
        if length == 1 and (.[0].threads | type) == "array" then .[0] else error("no threads") end
        | [.threads[] | select(.threadId == $was)][0] as $it
        | if $it == null and .nextCursor != null then "more: \($was) is not on this page, call again with cursor \(.nextCursor)"
          elif $it == null then "not found: no thread with this title has the id \($was), so nothing is settled"
          elif $it.settled == true then "settled: \($was) is settled, and a settle clears its pin"
          else "settle \($was): the home before this one is still active, and may still be pinned" end' 2> /dev/null << 'THE_REPLY_ENDS_HERE' ||
<the reply of t3_thread_list>
THE_REPLY_ENDS_HERE
        echo "not read: put the whole reply of t3_thread_list in place of the placeholder"
fi
```

On `settle <id>`, settle that thread with `t3_thread_organize`, the id in place of `<thread>`, and tell the user in one line that the last home had not settled and now is:

```json
{"action": "settle", "threadId": "<thread>"}
```

On `more`, make the same call with `cursor` set to the number it names, and run the block on that reply. On `not found`, tell the user that line. On `settled`, nothing. T3 Code's list does not say whether a thread is pinned: a pin is known to be gone only because the thread is settled.
