---
name: home
description: Make this thread the home for the repo it runs in - read the repo's short handoff, plan work with the user, hand each task to a crewmate thread, and hand off to a fresh home before the context grows. Use when the user invokes /home or $home, opens a new thread to continue work in a repo, or asks to pick up where the last thread left off.
user-invocable: true
disable-model-invocation: true
card: "Run the pipeline | 1 | Makes this thread the repo's home. It reads the last home's note and what jbus holds, plans with the operator, writes each brief and launches its crewmate. It does none of the work. | Reach for it when you start or continue work in a repo. | op: the operator; cmd: the start hook"
---

# home

There are no subagents doing the work. Each task is one ordinary thread, and its pull request gets one review, by a reviewer in a new thread that the crewmate launches (`pr-review`). A fix outside `tests/` gets one scoped review, and that is the last: nothing loops. The repo's own checks and its CI decide whether the work is good.

## Where a home's state lives

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
T=$(realpath ~/.claude/skills/home/../../templates)
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
word() { awk 'NF {print $(1); exit}' "${1}" 2> /dev/null; }
was() { sed -n 's/^Was home:[[:space:]]*\([^[:space:]][^[:space:]]*\).*/\1/p' "${1}" 2> /dev/null | head -n 1; }
whose() {
    named=$(sed -n 's/^Home:[[:space:]]*\([^[:space:]]*\).*/\1/p' "${1}" 2> /dev/null | head -n 1)
    found=$H
    if [ -n "$named" ] && [ "$named" != "$(word "$H/home-id")" ] && [ "$named" != "$(was "$H/handoff.md")" ]; then
        for d in "$H"/*/; do
            d=${d%/}
            id=$(word "$d/home-id")
            old=$(was "$d/handoff.md")
            if [ -z "$id$old" ]; then continue; fi
            if [ "${d##*/}" = "$named" ] || [ "$id" = "$named" ] || [ "$old" = "$named" ]; then found=$d; fi
        done
    fi
    echo "$found"
}
```

That is **the block at the top**. Every block below is sh, and its last line makes zsh read them so: without it zsh stops a call at a pattern that matches no file. `$R` is the repo's name, the same from the main checkout and from any worktree of it. `$H` is the repo's state directory, which every home of the repo shares. `whose` prints the directory of the home a brief or a request is, by `jmerge`'s rule ("Merging a pull request that is ready"): a block below asks it whether one is this home's.

`$T` is the `templates/` directory of the repo this skill lives in. Each template there is the one copy of its text: read it when a step names it, not before.

A repo has one root home, and may have scoped homes beside it, each for one goal. A scope is a directory under `$H` that holds a `plan.md`, and never `tasks`, `scouts`, `reports` or `log`. `$M` is this home's own directory: `$H` for the root home, `$H/<scope>` for a scoped one. **The block that finds this home** sets it, from the one `home-id` that holds this thread's id:

```sh
ME='<threadId>'
M=
case $ME in
'') M=$H ;;
*'<'* | *'>'*) ;;
*)
    for f in "$H"/home-id "$H"/*/home-id; do
        if [ -f "$f" ] && [ "$(cat "$f")" = "$ME" ]; then
            M=$(dirname "$f")
            break
        fi
    done ;;
esac
if [ -z "$M" ]; then
    echo "no home: thread $ME is no home of $R now, its id is in no home-id under $H. Nothing is written."
    exit 1
fi
```

Run it after the block at the top, in the same call as each block below that names `$M`, with this thread's id in place of `<threadId>`: the id step 3 of "When a home starts" put on disk. In a session with no tool that gives the id, put nothing in its place: that home is the root's. On `no home:` the call stops there. This thread handed off, or another home took its place: write nothing, and tell the user. A message that reaches such a thread is not its to act on, whoever sent it: run the block under "After the handoff" in `$T/../skills/handoff/SKILL.md` and do what it prints.

| File | Holds | Size |
|---|---|---|
| `$M/handoff.md` | The note the last home left: what is next, what it has out that jbus does not hold, what not to redo, what is uncommitted, and each gate jbus could not take. Rewritten at every handoff, from `handoff.next.md` beside it. | Ten lines, and its gates |
| `$M/plan.md` | The work this home has planned: one entry per task, each with a "Done when" list. | Open tasks only |
| `$M/home-id` | This home's thread id. A scout, a crewmate or a reviewer reads it each time it sends: the root home's for a brief or a request with no `Home:` line, a scoped home's for one that names its scope. | One line |
| `$H/home-thread` | The merge switch, and not this home's id. Empty or missing, jbus runs `jmerge` on each pass, also while a home runs, and the home runs none: it tells the user what jbus logged. An id in it stops jbus's run for the project, and only the home merges. One of the two merges, never both: the block of "Who merges" reads it before every run ("Merging a pull request that is ready"). Set by hand only: no skill and no script writes it. | Empty, or one line |
| `$M/read-seen` | The Result and Report headings step 4 of a start has shown this home, one a line, so each is shown once. | One line per heading |
| `$M/merge-seen` | How many lines of `$H/merge.log` this home has read, so that while jbus merges each `merged` line is relayed once ("Merging a pull request that is ready"). | One number |
| `$M/log/` | Old handoffs, dated. Nobody reads these at start. | Unbounded |
| `$H/notes.md` | Facts about this repo that a new thread would otherwise relearn the hard way. Read when a step needs one of them, not whole at a start. | At most 60 lines |
| `$H/standing.md` | The user's standing rules for this repo's homes, carried from home to home. Read whole at every start. Right after any edit to it, run `jbus snapshot --why "<repo> standing rule <n> <added, changed or removed>"`, so the edit is a commit of its own in `~/.local/state/home`, pushed, and can be undone ("Undo an edit to standing.md" in `docs/state.md`). | Short |
| `$H/tasks/<slug>.md` | A crewmate's brief, and its result, whichever home wrote it. | One page |
| `$H/scouts/<slug>.md` | A scout's request, and its report, whichever home wrote it. | One page |
| `$H/reports/` | The pages a scout or a home makes for the user. | Unbounded |
| `$H/merge.log` | Every line `jmerge` printed, dated: what it merged, each with the command that opens its revert, what waits and is held, and what it swept. | Unbounded |
| `$H/merge-off` | Present when the automatic merge is switched off for the repo: `jmerge` merges nothing here. `/nohome merge` makes it and `/nohome merge on` removes it. | Empty |

## Carry on

Proceed on reversible work without asking: do it, then say what you did and why. Pause for the user's word before four things only: a force-push to a shared branch, a deploy, deleting data, and a message to a customer or to anyone outside. What the user's global instructions or the repo's own instructions tell a thread to confirm first is still confirmed first. When in doubt, act and write down what you did.

For a home, reversible work is the plan, the briefs, the launches and the merge of what is ready. A question only the user can answer does not hold any of it up: "Gates". Planning with the user is not such a question: what the work is for comes from them.

## When a home starts

A home starts in one of two ways. The user types `/home`. Or the session-start hook (`hooks/home-start.sh` in the checkout that holds this skill) adds a `[home]` line to a new T3 Code thread opened in the main checkout of any repo, one that never had a home included, and the thread invokes this skill before its first reply. In the second case the user's first message is their opening request, unless it starts with `/home`, which is the first case: do the five steps below, keep step 5 to the lines that matter for that request, and then take the request as the start of planning.

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
   typed=$(cat << 'THE_TEXT_ENDS_HERE'
   <the text after /home>
   THE_TEXT_ENDS_HERE
   )
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
4. See where things stand. Read `$H/standing.md` and `$M/handoff.md` whole, the user's standing rules and the note the last home left: the block below prints the path of each that is there. Then run it in one call with the block at the top, the block that finds this home and the block that reads jbus ("Gates"), in the main checkout:

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
    echo "not on the bus: jbus is not installed here, so nothing is added: sh install.sh in $T/.."
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
case $refused in
*'<'* | *'>'*) refused= ;;
esac
was=$(sed -n 's/^Was home:[[:space:]]*\([^[:space:]]*\).*/\1/p' "$M/handoff.md" 2> /dev/null | head -n 1)
if [ -z "$was" ] || [ "$was" = "$ME" ]; then
    echo "no home before this one: $M/handoff.md names none, so no task is taken over"
else
    said=$(jq -rs --arg was "$was" --arg audit "audit: $R queue" --arg refused " $refused " '
        if length == 1 and (.[0].tasks | type) == "array" then .[0] else error("no tasks") end
        | [.tasks[] | select(.boundThreadId == $was)]
        | if length == 0 then "none: no scheduled task posts into \($was)" else .[] end
        | if type == "string" then .
          elif (.scheduledTaskId as $id | $refused | index(" \($id) ")) then "left \(.scheduledTaskId): \(.title) still posts into \($was), the call for it was refused"
          elif .title == $audit then "delete \(.scheduledTaskId): the audit of the home before this one"
          else "take \(.scheduledTaskId): \(.title) posts into \($was), the home before this one" end' 2> /dev/null << 'THE_REPLY_ENDS_HERE'
<the reply of list_scheduled_tasks>
THE_REPLY_ENDS_HERE
    ) || said="not read: put the whole reply of list_scheduled_tasks in place of the placeholder"
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

## Planning

Planning is a conversation with the user. Its result goes in `plan.md`, not in this thread's memory.

When the shape of the work is not settled (more than one task, or a design choice the user has not made), plan by the grilling skill: read `$T/../skills/grilling/SKILL.md` and work its rounds before writing an entry. A single task the user has already described in full needs no round.

- One entry per task. A task is one pull request's worth of work. If it is larger, split it before anything starts.
- Every entry has a **Done when** list: checks a person or a command can run. It is the stopping rule. Without one, do not start.
- Record a decision the user makes in the entry it belongs to, in their words.
- Write no status in an entry, and change none by hand. An entry has a `Stage:` line, which says where the planning is: `proposed`, `planned`, `parked` or `scouting`. Once a brief of the entry is queued, its status is counted from its queue rows by `jbus plan`, and the `Stage:` line is not read.
- Queue each brief of an entry with `jbus queue add --entry <entry>`, in a repo `jbus plan` answers for and in no other, where the brief's slug is not the entry's own: an entry is often several briefs, and the column is how a row is counted for its entry.

An entry has the shape of `$T/plan-entry.md`: read it before writing the first one.

When `jbus plan` prints `finished: close it` for an entry, run `jbus plan close <entry>` (a scoped home adds `--scope <scope>`). It moves the entry's section, as it is, from `plan.md` to `plan-done.md` beside it, and is refused while a row of the entry is not over. An entry leaves `plan.md` this way and no other: none is deleted by hand, and `plan-done.md` is never read at a start.

A plan of several entries that the user approves in one go runs as a queue: "A queue and its hourly audit" says when it starts and ends, and what the home schedules for it.

## The home does not do the work

A home plans, hands out, and keeps the record. Every task is done by a **crewmate**: a separate thread, in its own worktree, that the user can open, watch and steer. The home does not edit the repo, run its checks, or read a crewmate's diff.

The home does no research of its own: it reads only its state directory, `$H`. Not the code, not the docs, not a diff. What it needs to know from those, a scout finds out.

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

   Before this launch, run `uv run --project "$T/.." jroles scout` with the block at the top. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the scout on the model the role map names. When it prints nothing, the call is the one above. Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line. Leave the project and modes out, and the model unless `jroles` printed one.

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

## A playbook of the home's own

A row `the home` runs, in what the block in "Handing a task to a crewmate" that prints a row for each playbook prints, is steps for this thread: how to run a queue of tasks, not how to do one. Its name is kept on a `Playbook:` line in the head of `$M/plan.md`, above the first `## ` heading, so the next home works by it too. Open it when a home starts with that line in its plan, and when you take one up. Run this after the block at the top and the block that finds this home, with the playbook's name in place of `<name>`, or with nothing in its place to take the name the plan has:

```sh
name='<name>'
if [ -z "$name" ]; then
    name=$(awk '/^## / {exit} /^Playbook:/ {print $(2); exit}' "$M/plan.md" 2> /dev/null)
fi
case $name in
"" | none) ;;
*)
    f="$T/../playbooks/$name.md"
    if [ "${name#*/}" != "$name" ] || [ ! -f "$f" ]; then
        echo "no playbook: playbooks/ has no $name.md"
    else
        by=$(sed -n 's/^Run by: //p' "$f" | head -n 1)
        case ${by%%,*} in
        "the home")
            realpath "$f"
            printf '%s\n' "$by" | sed -n 's/.* in a brief with //p' | grep -o '`[^`]*`' | tr -d '`' |
                sed 's/^/asks of its brief: /' ;;
        *) echo "not the home's: playbooks/$name.md is for ${by%%,*}" ;;
        esac
    fi ;;
esac
```

It prints nothing when the name is `none`, or when none is given and the plan's head has no `Playbook:` line: go on with no playbook. On `no playbook`, do the same, and tell the user what it printed. On `not the home's`, the file is for a crewmate or a scout: do the same again, and put its name on a brief or a request instead. When its first line is a path, read that file now. Copy its numbered steps into your todo list, word for word, before any todo of your own (with no todo tool, write the list in this thread), and work them in order. A step you do not do stays in the list as `skip: <reason>`. A path the playbook names is from `$T/..`, the repo this skill lives in, also when the work is in another repo. A line under the path, `asks of its brief:`, is a line to write in each brief the playbook has you hand out. The playbook adds to this skill and does not replace it: where the two disagree, this skill wins, and you say so to the user.

## Handing a task to a crewmate

1. Write the brief, `tasks/<slug>.md`, from the plan entry, in the shape of `$T/brief.md`: read it first. Its `Home:` line names this home and never a thread. A scoped home writes `Home: <scope>`, the word step 1 of "When a home starts" printed after `scope`, and the root home writes no such line. The crewmate, and its reviewer when it must, read the id in that home's `home-id` each time they send, so the brief is not changed when the home hands off. A brief a scout wrote is already there: check that its `Home:` line is as this says and that its `Size:` line is its plan entry's size, set each if not, and go to step 2.

   Its `Proves it:` line, under the "Done when" list, names what outside the agent shows the task is done: a test or a command, a metric, a dataset, an external judge or the user. `jbus queue add` queues no brief whose line names only the crew, the crewmate, the reviewer, the agent, the model or a review, or is empty, and a launch checks it again.

   Its `Size:` line is the task's t-shirt size, `S`, `M`, `L` or `XL`, as its plan entry's `Size:` line has it: the feature playbook's step 4 reads it to decide on a design read. `jbus queue add` queues no brief with no such line, or with any other word on it.

   Its `Review:` line says how much review the pull request gets. It is fixed now, when the brief is written, and the crewmate and the reviewer both go by it:

   | Write | When |
   |---|---|
   | `Review: review` | always, unless the one below holds or the user says otherwise |
   | `Review: none` | the task is text only (wording, a note, a doc with nothing that runs) or throwaway (a spike nobody merges) |

   A brief with no line counts as `review`. With `none` the crewmate launches no reviewer and the home never merges the pull request by itself: it waits for the user's word. No reviewer runs a test step or a suite: the one full run is the crewmate's.

   A brief is checked when it is queued, not when it launches. `jbus queue add` refuses a brief that is short of anything a launch asks: a `Task:`, `Done when:`, `Proves it:`, `Size:`, `Where:`, `Pull request:`, `Review:` and `Playbook:` line, each filled in; a `Proves it:` line that names something outside the agent; a t-shirt size; a crewmate's playbook or `none`; a `Design:` line; and a `Skills:` line, where the brief has one, whose every name is a skill of `skills/` or a principle of `principles/`. It prints `refused: <slug>'s brief has <n> faults, and nothing is queued` and one line under it for each fault: mend the brief and add it again. Nothing is queued, so the user is never asked to approve a brief that cannot launch. A launch checks the same again.

   Its `Skills:` line names what the crewmate runs besides the playbook, or says `none`, and a brief with no line names nothing. Write each name in its canonical form, pstack's, so it reads the same in Grok Bot and in T3: a skill as its directory, `architect`, and a principle as its file without `.md`, `principle-model-the-domain`. `docs/jbriefs.md` "Skills a brief names" says which aliases resolve. The crewmate loads each file in full at its start, and its Result owes one artifact for each, the one `templates/skill-artifacts.md` names: `jmerge` merges no pull request whose Result leaves one out.

   Its `Playbook:` line names the steps the crewmate works through: one file in `$T/../playbooks/`, without its `.md`. Run this with the block at the top. It prints a row for each playbook, its name and then who runs it and for what kind of task, and a last row for `none`:

   ```sh
   for f in "$T"/../playbooks/*.md; do
       if [ -f "$f" ]; then
           printf '%s | %s\n' "$(basename "$f" .md)" "$(sed -n 's/^Run by: //p' "$f" | head -n 1)"
       fi
   done
   echo "none | nothing above fits"
   ```

   Pick from what it prints, by who runs the row. A brief takes a row `a crewmate` runs whose kind of task this is, or `none`. A scout's request takes a row `a scout` runs, or `none`. A row `the home` runs goes on no brief and no request: "A playbook of the home's own" opens it. A brief with no line counts as `none`, and the crewmate works by the crew skill alone. jbus launches no brief whose line names a playbook that is no file there, such as `fix` or `feature.`: it is a gate that says why. A row that ends `in a brief with` some lines asks for those lines in the brief: write them. Do not read the playbook to pick it: its row is enough.

   Then ask for the deeper version of the task, not a bigger one (`$T/../principles/principle-depth-over-breadth.md`). Run this, for a brief or a scout's request alike, with the playbook you picked in place of the words in angle brackets. Put the kind of work there instead, `research`, `perf`, `analysis`, `outcome` or `other`, where you picked `none`, and where the playbook hides the kind: an outcome under `feature` or `autonomous-run` is `outcome`, and a bug whose cause is not proven is `analysis`, whatever the playbook:

   ```sh
   picked='<the playbook picked, or for none the kind of work>'
   case $picked in
   *'<'* | *'>'* | '') echo "not filled in: put the playbook or the kind of work in place of the placeholder" ;;
   investigation | trace-forensics | runtime-forensics | perf-issue | hillclimb | eval | research | perf | analysis | outcome)
       echo "deeper: answer these four for this task, in this repo, on this machine, and write each where it says"
       echo "1. What would a top professional in this field do here that is not asked? Name the field: the answer shapes 2, 3 and 4, and adds no line and no deliverable"
       echo "2. What is the rawest material they would start from, in place of what is already digested? A brief's Read: line, or each of a request's questions, where to start looking"
       echo "3. What specific methods and tools would they use, each with the command that runs it here? A brief's Instruments: line, for the crew"
       echo "4. What, other than the agent or the user's trust in it, would show the result is right? A brief's Proves it: line"
       ;;
   bug-fix) echo "skip: a bug fix with a known cause goes by the direct path; where the cause is not proven, run this again with analysis" ;;
   feature | autonomous-run) echo "skip: a $picked task that builds a named change goes by the direct path; where it is an outcome to reach, run this again with outcome" ;;
   *) echo "skip: $picked is not research, perf, analysis or outcome work: a mechanical fix, a docs change and a bug fix with a known cause go by the direct path" ;;
   esac
   ```

   On `deeper`, answer the four from `$H` and what the user said, as for the rest of the brief: an answer that needs the code or the docs is a question for the scout. A brief the step ran on has a `Read:` line with answer 2 and an `Instruments:` line with answer 3, though the home wrote it. A request has no brief to hold 3 and 4: where its "Deliver" list asks for the crewmate's brief, name them on that line, so the scout's brief carries them on `Instruments:` and `Proves it:`. Do not run `/deeper`: it is the user's to type. On `skip`, write the brief as it is. Skip it too for a task whose "Done when" already names its data, its instruments and its outside judge.

2. Start the crewmate thread with the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first). The brief must be on disk before this call.

   ```json
   {
     "title": "crew: <slug>",
     "workspaceStrategy": {"type": "worktree", "baseRef": "<default branch>", "branch": "<slug>", "startFromOrigin": true},
     "message": "/crew <slug>"
   }
   ```

   Before this launch, run `uv run --project "$T/.." jroles crew` with the block at the top. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the crewmate on the model the role map names. When it prints nothing, the call is the one above. Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line.

   ```json
   {
     "title": "crew: <slug>",
     "workspaceStrategy": {"type": "worktree", "baseRef": "<default branch>", "branch": "<slug>", "startFromOrigin": true},
     "message": "/crew <slug>",
     "modelSelection": <model selection>
   }
   ```

   - The default branch is `git symbolic-ref --short refs/remotes/origin/HEAD` without the `origin/` prefix.
   - Use a branch prefix such as `feat/` only if `notes.md` names one for this repo.
   - The title is `crew: ` and the slug, so the left bar shows which threads are crewmates.
   - Leave the project and modes out, and the model unless `jroles` printed one. What is left out, the crewmate inherits from this thread.
   - A launch has no retry key. If the call fails or its reply is lost, look for the thread with `t3_thread_list` before launching again:

     ```json
     {"titleContains": "crew: <slug>"}
     ```
   - If the session has no such tool, tell the user instead: "Open a new thread in this project, in a new worktree, and type `/crew <slug>`."
3. Add the line `Thread: <threadId>` to the brief. Run this with the block at the top, with `tasks` or, for a scout's request, `scouts` in place of `<tasks or scouts>`, and the id the launch returned in place of `<the launched thread>`:

   ```sh
   B="$H/<tasks or scouts>/<slug>.md"
   line='Thread: <the launched thread>'
   case $line in
   *'<'* | *'>'* | 'Thread: ') echo "not written: put the id the launch returned in place of the placeholder" ;;
   *)
       if [ ! -f "$B" ]; then
           echo "not written: there is no $B"
       elif grep -qxF -e "$line" "$B"; then
           echo "not written: $B has $line"
       elif grep -q '^Thread:' "$B"; then
           was=$(grep -m 1 '^Thread:' "$B")
           awk -v line="$line" '/^Thread:/ && !put { print line; put = 1; next } { print }' "$B" > "$B.thread" && mv "$B.thread" "$B"
           echo "written: $line, in place of $was, in $B"
       else
           awk -v line="$line" '
               /^## / && !put { print line; put = 1 }
               { print }
               END { if (!put) print line }' "$B" > "$B.thread" && mv "$B.thread" "$B"
           echo "written: $line, in $B"
       fi ;;
   esac
   ```

   The line goes above the Result, when a fast crewmate has written one by then, and takes the place of the line of an earlier launch from the same brief: a review's findings go to the thread it names. Briefs and requests are in the repo's directory, whichever home launches from them. Write no status in the plan. A launch by this section adds no row to the queue, and `jbus plan` counts an entry from its rows, so where the brief has no row yet, add one for its entry. Run this in the main checkout with the block at the top, with the brief's slug, a priority and the entry's slug in place of the words in angle brackets:

   ```sh
   if command -v jbus > /dev/null && jbus plan > /dev/null 2>&1; then
       if said=$(jbus queue add '<slug>' --priority '<n>' --entry '<entry>' < "$H/tasks/<slug>.md" 2>&1); then
           echo "added: the row <slug>, of the entry <entry>"
       else
           printf '%s\n' "$said"
       fi
   else
       echo "no row: jbus has no plan for this repo, so nothing is added to its queue"
   fi
   ```

   `jbus plan` answers only for the repo it is run in, and `jbus queue add` with no project takes the config's only project whatever the repo: so the row is added only where `jbus plan` answered, and on `no row` none is, since it would be another repo's row. On `refused:`, nothing is queued: mend the brief as the lines under it say, and run it again. A row with no approval is never launched again. Then give the user the link: `[<slug>](t3-thread://v1/<threadId>)`.

No fixed count limits the threads out, crewmates and durable scouts together. Two things do: only tasks that do not touch the same files are out together, and the machine has to have room.

The machine is shared with the homes of other repos, so check it before every launch:

```sh
uv run --project "$T/.." jgauge room || echo "wait: jgauge room did not run"
```

It prints `go`, or `wait: ` and the first reading that has no room. There are four readings: the one-minute load against the core count, the available memory, the memory pressure, which is the share of the last minute that something on the machine stood waiting for memory, and the plan's limits, which is the share of the account's five-hour and weekly limit already used. A reading of the machine it cannot take is a `wait` too. The limits are the one reading that never stops a launch unread: they come from the file on the `LIMITS` line, which the user's status line script writes, and for a window that file does not give, `room` prints `go` and under it a `note: ` line saying that limit is not known. A window past its reset counts as empty, and a `wait` on a limit says when the window resets. The check is one file, `src/jgauge/room.sh` in the repo this skill lives in, and `jgauge room` runs it: the pr-review skill's run block and `jbus` ask the same file, and no skill holds a copy. The four thresholds are the first four lines of its `room`: change one there. `PROC` points the readings at another directory and `LIMITS` at another file, for a test. Run it with the block at the top, which sets `T`: `uv run --project` needs nothing on `PATH` but `uv`. A check that did not run is a `wait` as well.

Launch on `go`. On `wait`, do not launch: tell the user the task is written and waiting, and why, and launch it when they next ask or the check says `go`. That holds whatever the user asks for in one message: every launch gets its own check, and the ones with no room wait their turn.

A review is a task like any other. Do not run several review subagents that each install and test their own checkout: that is the same load as that many crewmates, with nobody able to watch it. Each review runs in its own reviewer thread, as many at a time as the machine has room for (the pr-review skill's run block makes the same check before a run starts), and their heavy suites run under the machine-wide lock in the user's global instructions.

## When a thread sends a message

The threads this home sent out write what they did to disk: a crewmate its `## Result`, a reviewer its `## Review`, a scout its `## Report`. Disk is the record. A message to this thread is an interrupt. The home plans, assigns and starts, so what it hears is planning: what finishes the work is jbus's to read and whoever the project's webhook is to hear, and reaches this thread only while it is the one that merges ("Who merges", under "Merging a pull request that is ready"). These are all of them, and the last column says on which answer of that block each is sent:

| The message | From | Sent when | Sent on |
|---|---|---|---|
| `<slug>: <pull request url> at <head> is fixed and green` | a crewmate | its pull request is reviewed, the findings are handled, and every check has passed | `home merges` |
| the task ended with no pull request | a crewmate | it wrote a Result that names none | both |
| `<slug>: <pull request url> at <head> is green and has no review` | a crewmate | every check has passed and no reviewer will come: the brief says `Review: none`, or the session could launch none. It is never ready, so tell the user it waits for their word | `home merges`; on `jbus merges` it is a gate |
| the report is written | a scout | at its End, once, and once more only if a page's feedback changed the report | both |
| a review's findings | a reviewer | only when the brief has no `Thread:` line to send them to | both |
| `<slug>: <pull request url> has a conflict, and it is a link of a stack` | a crewmate | GitHub reports a conflict on a link, which its crewmate never rebases by itself: send it the line of "A stack the user lands" | `home merges`; on `jbus merges` it is a gate |
| `<slug>: gate`, then the gate's lines | a crewmate or a scout | it took a default on a question only the user can answer, carried on, and `jbus gate` could not take the gate: no `jbus`, or no project for the repo | both |
| `jbus: this is <name>'s own word, said <time> and carried to this home by jbus.`, then the words | jbus | the user said it elsewhere and `jbus word` carried it: act on it as said here ("The user's word, carried by jbus") | both |

One more comes from jbus, whoever merges: `jbus: <slug> ended with something left, and it is this home's to close.`, with the pull request and whether it merged, the `Left:` line whole, and each question the slug asked with its answer. Read the last Result of `$H/tasks/<slug>.md` and those answers, then end it one of two ways. Where something is still to do, write a brief for what is left and queue it as a follow-up. Then, or at once where nothing more is wanted or the rest is already somebody's, append `## Result, follow-up (<date>, <the reason>)` to `$H/tasks/<slug>.md`, the brief of the task that ended, with three lines: `Status: done`, `Branch: <its branch>   Pull request: none` and `Left: none`. Only those three end it. Send the user nothing about it: a question only they can answer is a gate ("Gates"), and jbus says the row to them once if it is still open 30 minutes after the message.

Nothing is sent when a pull request opens, when a review is written or when its findings are handled. A reviewer's findings go to the crewmate. A thread with a question only the user can answer takes a default, carries on and pipes the gate to `jbus gate <slug>`, which keeps it as a numbered question: the home reads the open ones from jbus, shows them, and closes one with the user's answer, which jbus carries back when it differs ("Gates"). On `jbus merges` no line about a pull request is sent here: jbus reads the brief and the pull request on each pass, and the merge step prints what it found. Only a thread at one of the four pauses of "Carry on" asks in its own thread and waits: it shows as `waiting` in T3 Code, which is what reaches the user. The home does not poll for any of it and runs no watch on its state directory or on GitHub, with one exception, in the user's words: "an hourly scheduled run through T3's schedule_task, only while a queue is out, removed when it ends" ("A queue and its hourly audit"). What it has to plan on arrives as a message, and the rest it reads when the user asks for status and at the start of the next home: the gates from jbus ("Gates"), the results from disk.

On each message, do this without waiting for a word from the user.

1. Read what landed: the last result, the review or the report the message is about, from disk. Not the thread that sent it. A gate that came as a message is one jbus could not take: do what the end of "Gates" says for it. A line `Gate: question <number>` in what you just read is a question jbus holds, and asks nothing here. The lines of a gate itself under "Noticed" in a Result or "Findings" in a Report are from a thread that had no home to send them to, or from one that wrote them under the skill as it was: hand them to jbus with the block of "Ask one", under that thread's slug, and only on `not asked` do the same for it as for one that came as a message.
2. Run the merge step of "Merging a pull request that is ready", after its block "Who merges". On `home merges` it runs `jmerge`, which merges what is ready and writes no plan. On `jbus merges` it runs none, and prints what jbus's `jmerge` merged since this home last read the log, then its last line for each open pull request.
3. Run `jbus plan` and close each entry it prints `finished: close it` for ("Planning"). Write no status: the plan holds none. Then launch the next planned task, by "Handing a task to a crewmate" or "Sending a scout", when all of these hold. Any one that fails leaves the task where it is, with the reason kept for step 4:
   - its plan entry's `Stage:` line says `planned`, its own brief is not out (`tasks/<slug>.md` has no `Thread:` line, and its row, where it has one, is still `queued`), and nothing it waits on is unmerged: a task is never stacked on another's branch, but in a plan whose head names `autopilot-stack` ("A stack the user lands");
   - no answer from the user is outstanding for it: an open decision in its entry, or a scout's brief that "Sending a scout" says to show first and the user has not yet seen;
   - its work is in this repo;
   - none of the files in its `Where:` is held by another brief still out, of any home of this repo: the launch check, under this list, prints them;
   - `room` says `go`.

   The launch check is one command, with no model. Run it from the main checkout, in one call with the block at the top:

   ```sh
   uv run --project "$T/.." jmerge --claims
   ```

   It prints one line for each brief that still holds files, whichever home of this repo wrote it: `<slug> <not launched | out | pull request <number>> <home> Where: <the brief's Where: line>`. The home is `root` or the scope's name. A brief whose pull request is merged or closed, or whose task ended with none, prints nothing. The task's own brief is one of the lines: leave it out. A file or a directory of the task's `Where:` that another line names holds the task back until that slug's line is gone. On `wait: could not ask GitHub` nothing was read: launch nothing. Do not read the briefs in `$H/tasks/` for this, and do not ask another home.
4. Tell the user in a few lines, here: what landed, what was merged, what was launched with its link, what was parked, and what waits and why. When nothing is left planned or out, say that the planned work is done and show the open questions ("Gates").

If a result says the task is not done, the fix is a new message from the user in the crewmate's own thread, or a new brief. The home does not take the task over.

When the user asks for status, run the merge step of "Merging a pull request that is ready" and relay what it printed, and for a brief with no result yet, one `t3_thread_list` call gives the state of the crewmates still out: `running`, `waiting` (it is at one of the four pauses and has asked in its own thread), `failed` or `interrupted`. Report that state with the thread's link. No message brought what finished since: run the block of step 4 of "When a home starts" and read the last result of each brief it prints that this thread has not read. Then run the block of "Show the open ones" ("Gates") and show what it prints. The root home then runs the block of "Scoped homes" that reads the scopes. Do not read a crewmate's timeline unless the user asks what it is doing.

## Gates

A gate is a question only the user can answer, asked with the default that was taken so the work did not wait for it. jbus keeps each one as a numbered question: `jbus gate` writes it, and `jbus answer` closes it, once. This home keeps no file of them and no copy: it reads the open ones from jbus, and runs the one command that closes one.

**Every gate acts unless stopped.** The asking thread, this home included, acts on its default at once and carries on. No question parks work while it waits, and the user sees each one as already acted on. Every gate carries a default, and the default is the option the thread recommends, marked `(default, recommended)`. `jbus gate` refuses a gate with no filled `Default:` line, and one whose recommended option is not the default. If the user has not answered in 2 hours, a jbus pass closes the question with its default, by silence. The record says it was not the user's word (`by jbus`, the time, `no answer in 2 hours`). A later answer from the user still replaces that close, and one that differs goes back to the thread as any other.

The one exception is a default that is **irreversible or slow to revert**: undoing it needs the user, or takes more than one ordinary pull request or command, or cannot restore what was there, or has already reached someone outside this machine. Such a gate does not act. Its thread does the fail-safe and adds two lines under `Undo:`: `Holds: <the case>`, word for word from the table, and `Fail-safe: <what was prepared, with its path or link>`. The action then waits for the user's answer, and silence never closes it. `jbus gate` refuses a `Holds:` line with no filled `Fail-safe:` line, a case that is not in the table, and a `Fail-safe:` line with no `Holds:` line.

| Case | Examples | Fail-safe |
|---|---|---|
| deletes data | removing files, folders, branches, a repo, a T3 project or thread, a database, a bucket, a cloud resource | dry-run: list exactly what goes; a backup or bundle first where one can be made; then hold for the user |
| rewrites history | force-push to a shared branch, filter-repo, deleting tags | safety bundle of the old history, verify script, then hold for the user |
| spends money | creating paid cloud resources, raising a plan or a limit, a purchase | the cost estimate or plan, then hold for the user |
| touches prod or real users | a prod deploy, a prod data or schema change, a message to a customer or anyone outside | the plan or diff (`terraform plan`, `cdk diff`, the message text), then hold for the user |
| changes access or secrets | rotating or granting a key or token, tailnet policy or DNS | the diff of the change, then hold for the user (jmerge's protected paths already hold the code side) |
| publishes | a public release, a tag, a package, a public repo or post | the exact artifact and where it goes, then hold for the user |

Everything else acts at once on its default: a merge (reverted by `gh pr revert`), a branch, a brief, a config edit with its backup, a launch. `$T/gates.md` has the same rule under the gate's lines, for every thread that gates.

**The block that reads jbus** is run in the same call as every block of this section but the last two, after the block at the top and the block that finds this home, from the main checkout:

```sh
: "${M:?run the block that finds this home first}"
SEP=$(printf '\001')
own=home
if [ "$M" != "$H" ]; then own=home-$(basename "$M"); fi
mine() {
    if [ "${1}" = "$own" ]; then return 0; fi
    case ${1} in
    home) return 1 ;;
    home-*) if [ -f "$H/${1#home-}/plan.md" ]; then return 1; fi ;;
    esac
    for f in "$H/tasks/${1}.md" "$H/scouts/${1}.md"; do
        if [ -f "$f" ]; then
            [ "$(whose "$f")" = "$M" ]
            return
        fi
    done
    [ "$M" = "$H" ]
}
P=$(awk -v repo="$R" '
    function said(line) { sub(/^[^=]*=[ \t]*"/, "", line); sub(/"[ \t]*(#.*)?$/, "", line); return line }
    function table() { if (inside && !found && name != "" && (state == "" ? name : state) == repo) { print name; found = 1 } name = state = "" }
    /^[ \t]*\[/ { table(); inside = ($(0) ~ /^[ \t]*\[\[project\]\][ \t]*$/); next }
    inside && /^[ \t]*name[ \t]*=/ { name = said($(0)) }
    inside && /^[ \t]*state[ \t]*=/ { state = said($(0)) }
    END { table() }' "${JBUS_CONFIG_DIR:-$HOME/.config/jbus}/config.toml" 2> /dev/null)
OPEN=
LINKS=
Q="${JBUS_STATE_DIR:-$HOME/.local/state/jbus}/$P/questions.json"
if ! command -v jbus > /dev/null; then
    WHY="no jbus: jbus is not installed here, so it holds no question"
elif [ -z "$P" ]; then
    WHY="no project: jbus's config names no project for $R, so it holds no question of this repo"
elif [ ! -e "$Q" ]; then
    WHY=
elif ! found=$(jq -r '.records[] | select(.answer == null) | [.number, .slug, .question, .default, .built_on, .undo, (.holds // ""), (.fail_safe // "")] | map(tostring) | join("\u0001")' "$Q" 2> /dev/null); then
    WHY="jbus could not be read: $Q is not the record jbus writes"
else
    WHY=
    found=$(printf '%s\n' "$found" | while IFS=$SEP read -r n slug rest; do
        if [ -n "$n" ] && mine "$slug"; then printf '%s\n' "$n$SEP$slug$SEP$rest"; fi
    done)
    OPEN=$(printf '%s\n' "$found" | grep -v "has a conflict, and it is a link of a stack$SEP")
    LINKS=$(printf '%s\n' "$found" | grep "has a conflict, and it is a link of a stack$SEP" | cut -d "$SEP" -f 1-3)
fi
```

It prints nothing. `$P` is this repo's project in jbus's config, and `$OPEN` the open questions that are this home's, read from the record jbus keeps of them, `questions.json` in the project's state directory: it is as it is now, with no pass between. This block only reads it: `jbus gate` and `jbus answer` are the two that write it. `$LINKS` holds the ones that ask this home and not the user, a link's conflict, apart from `$OPEN`: no round has them. A question is this home's by the brief or the request of the slug that asked, as step 4 of "When a home starts" tells, or by this home's own slug, whatever brief has that name: `home` for the root home, `home-<scope>` for a scoped one. One that no brief, no request and no home asked, as an expert's finding is, is the root home's. `$WHY` says why nothing could be read.

**Ask one** when the question is this home's own. Take the default you would recommend and act on it at once, or, for a default the table above holds, do its fail-safe and act on it only once the user answers. Fill in the lines of `$T/gates.md` (read it first), its `<n>` left as it is, with the `Holds:` and `Fail-safe:` lines under `Undo:` for a gate that holds, and carry on. Under the gate go one `Context:` line and one `Option:` line for every option you weighed, the default you took among them, which is the one you recommend, marked `(default, recommended)`, and the rest with no mark. With the entry in place of the line in angle brackets, and `own` left as it is:

```sh
: "${SEP:?run the block that reads jbus first}"
slug='own'
gate=$(cat << 'THE_GATE_ENDS_HERE'
<the gate, filled in>
Context: <what the user needs to know to answer it, in one line, with the links to it>
Option: <an option's short name> (default, recommended): <what follows from it>
THE_GATE_ENDS_HERE
)
if [ "$slug" = own ]; then
    slug=$own
    gate=$(printf '%s\n' "$gate" | sed "s/^Asked by: [^,]*/Asked by: $own/")
fi
case $(printf '%s\n' "$gate" | head -n 1) in
'## Gate <n>: '[!\<]* | '## Gate '[0-9]*': '?*) why= ;;
*) why="the first line is not '## Gate <n>: ' and the question" ;;
esac
if [ -n "$why" ]; then
    echo "not asked: $why"
elif ! command -v jbus > /dev/null; then
    echo "not asked: jbus is not installed here"
elif said=$(printf '%s\n' "$gate" | jbus gate "$slug" 2>&1); then
    echo "asked: $said"
else
    echo "not asked: jbus said: $said"
fi
```

On `asked: queued: question <number>`, jbus has it under this home's own slug, and nothing is written here. `asked: already sent:` is the same question still open. On `asked: already answered: question <number>:` nothing was asked: an earlier question of this home had the same words, and the line gives its answer. If that answer does not settle this one, word the question so that it says what is new, and run it again. On `not asked: the first line`, fill it in and run it again. On `not asked: jbus said: not sent:` or `jbus said: refused:`, jbus names what the gate lacks: a `Default:` line, a default that is not the recommended option, a `Holds:` line with no fail-safe or a case not in the table. Mend that line and run it again. On any other `not asked`, jbus holds nothing: put the question to the user in this thread, in two lines, with the default taken.

The same block hands jbus a gate another thread wrote out in full, the lines of a gate under "Noticed" in a Result or "Findings" in a Report: run it with that thread's slug in place of `own` and those lines as the entry. On `asked:`, jbus holds it, or held it already, and it asks nothing more here. On `not asked`, it is one jbus could not take: the end of this section says what to do with it.

**Move the ones a file still has** at the start, before the open ones are shown, when `$M/gates.md` exists: read `$T/../skills/home/move-the-ones-a-file-still-has.md` now, and run its block in the same call as the block that reads jbus. Its "the end of this section" is the end of "Gates".

**Show the open ones** in the start's summary, when the user asks for status, and when nothing is left planned or out:

```sh
: "${SEP:?run the block that reads jbus first}"
if [ -n "$WHY" ]; then
    echo "$WHY"
elif [ -z "$OPEN$LINKS" ]; then
    echo "no open questions"
else
    printf '%s\n' "$OPEN" | while IFS=$SEP read -r n slug asked took built undo holds safe; do
        if [ -n "$n" ]; then
            printf 'question %s, from %s: %s\ndefault: %s\nbuilt on it: %s\nundo: %s\n' "$n" "$slug" "$asked" "$took" "$built" "$undo"
            if [ -n "$holds" ]; then
                printf 'holds (%s) for the answer, fail-safe: %s\n' "$holds" "$safe"
            else
                printf 'acted on already: the default stands unless the user stops it\n'
            fi
        fi
    done
    printf '%s\n' "$LINKS" | while IFS=$SEP read -r n slug asked; do
        if [ -z "$n" ]; then continue; fi
        url=$(printf '%s\n' "$asked" | sed -n 's/^[^ ]*: \(http[^ ]*\) has a conflict, and it is a link of a stack$/\1/p')
        state=$(gh pr view "$url" --json state,mergeable --jq '"\(.state) \(.mergeable)"' 2> /dev/null)
        case $state in
        "OPEN CONFLICTING") echo "for this home, question $n, from $slug: send its line, $url has a conflict" ;;
        "") echo "for this home, question $n, from $slug: could not ask GitHub about $url" ;;
        *) echo "for this home, question $n, from $slug: handled, $url is $state, and the question is the user's to close as default" ;;
        esac
    done
fi
```

On `no open questions`, say nothing about gates. On `no jbus`, `no project` and `jbus could not be`, say that line: no question could be read. One open question is text: give it to the user by its number: the question and the default taken, then what was built on it and how to undo it. For one whose last line is `holds (<case>) for the answer`, say instead that its default waits for their answer, with the case and the fail-safe. Ask for nothing more than the answer. A line `for this home, question <number>` is a link's conflict, which asks this home and not the user, and GitHub says which it is now. On `send its line`, do what "A link with a conflict" says for the crewmate's line. On `handled`, tell the user in one line that question <number> is theirs to close, as `default`: silence never closes a link's question, and only their name does. On `could not ask GitHub`, do neither, and say so.

Two or more open questions are one round of the grill page, wherever the grilling skill's "On a page" (`$T/../skills/grilling/SKILL.md`, read it now) puts a round on a page. Each set of open questions has a page of its own: do its step 1 with `gates-<n>` as the `<slug>`, `<n>` being the highest number among them, and for a scoped home `gates-<scope>-<n>`. Then run this in place of its step 2:

```sh
: "${SEP:?run the block that reads jbus first}"
open=$(printf '%s\n' "$OPEN" | grep -c .)
last=$(printf '%s\n' "$OPEN" | cut -d "$SEP" -f 1 | sort -n | tail -n 1)
slug=gates-$last
if [ "$M" != "$H" ]; then slug=gates-$(basename "$M")-$last; fi
F="$H/reports/grill-$slug.html"
if [ -n "$WHY" ]; then
    echo "no page: $WHY"
elif [ "$open" -lt 2 ]; then
    echo "no page: $open open, and fewer than two are text"
elif [ ! -f "$F" ]; then
    echo "no page: $F is not there, make it first with $slug as the slug"
else
    ROUND=$(printf '%s\n' "$OPEN" | jq -R --arg slug "$slug" '
        split("\u0001") | {
            id: "gate-\(.[0])", title: .[2],
            body: (if (.[6] // "") != "" then "Asked by \(.[1]). It holds (\(.[6])) for your answer, with its fail-safe: \(.[7])" else "Asked by \(.[1]). Its default is acted on already" end),
            built_on: .[4], undo: .[5],
            options: [
                {id: "default", label: "Yes: \(.[3])", recommended: true},
                {id: "other", label: "Something else: say what in the note"}
            ]
        }' | jq -s --arg slug "$slug" '{
            slug: $slug, round: 1, title: "Open questions",
            lead: "Each default was taken so the work did not wait, but for one that holds. A question left alone is answered by its default after 2 hours, but for one that holds.",
            settled: [], questions: .
        }')
    export ROUND
    if awk '
        /<script type="application\/json" id="round-data">/ { print; print ENVIRON["ROUND"]; inside = 1; seen = 1; next }
        inside && /<\/script>/ { inside = 0 }
        !inside { print }
        END { exit !seen }' "$F" > "$F.new" && mv "$F.new" "$F"; then
        echo "round written: $open questions, in $F"
    else
        rm -f "$F.new"
        echo "no page: $F has no round-data block to write the round into"
    fi
fi
```

On `round written:`, each open question is a question `gate-<n>` on the page, its default the recommended option, with what was built on it and how to undo it. Go on with steps 3 to 5 of "On a page": open the session, hold the one poll, end your turn. If a poll for this page is already out, hold no second one. On `no page:`, or where "On a page" keeps a round as text, give each question as text, as for one.

When the poll returns answers, put what it printed, all of it, in place of `<what the poll printed>`:

```sh
awk '
    function plain(s,    out, i, c) {
        out = ""
        for (i = 1; i <= length(s); i++) {
            c = substr(s, i, 1)
            if (c == "\\") { i++; c = substr(s, i, 1); if (c == "n") c = "\n" }
            out = out c
        }
        return out
    }
    function answer(line,    word, n, same, mark, at, note) {
        if (line !~ /^- gate-[0-9]+: (default|other) /) return
        split(line, word, " ")
        n = word[2]; gsub(/[^0-9]/, "", n)
        same = (word[3] == "default")
        mark = same ? "), left as recommended" : "), changed from the recommended"
        at = index(line, mark)
        note = at ? substr(line, at + length(mark)) : ""
        sub(/^\. Note: /, "", note)
        if (same && note == "") print "question " n ": default: the default, picked on the page"
        else if (same) print "question " n ": noted: " note
        else if (note != "") print "question " n ": differs: " note
        else print "question " n ": open: something else was picked, with no note"
        seen++
    }
    /^- gate-/ { answer($(0)); next }
    /\\n- gate-/ { count = split(plain($(0)), line, "\n"); for (i = 1; i <= count; i++) answer(line[i]) }
    END { if (!seen) print "no answers: no line says \"- gate-<n>: \"" }' << 'THE_POLL_ENDS_HERE'
<what the poll printed>
THE_POLL_ENDS_HERE
```

Run "Close one" for each `default`, `noted` and `differs` line, with the words after that word as the answer. A `noted` line is the default left checked, with a note: read the note, and it is `differs` if it disagrees with the default and `default` if not. An `open` line closes nothing: ask for that question's answer here. Then end the session, as step 7 of "On a page" does. If the poll says the user ended the session instead, these questions stay open and are text from then on.

**Close one** when the user answers it, here or on a page. Put the question's number, the user's name, the time they answered, `default` or `differs`, and their words, as they said them, in place of the five placeholders:

```sh
n='<number>'
by="<the user's name>"
at='<YYYY-MM-DD HH:MM ZONE>'
which='<default or differs>'
ANSWER=$(paste -sd ' ' - << 'THE_ANSWER_ENDS_HERE'
<the user's answer, in their words>
THE_ANSWER_ENDS_HERE
)
case $which in
default | differs)
    if ! command -v jbus > /dev/null; then
        echo "not answered: jbus is not installed here"
    elif said=$(jbus answer "$n" --by "$by" --at "$at" "--$which" -- "$ANSWER" 2>&1); then
        printf '%s\n' "$said"
    else
        printf 'not answered: jbus said: %s\n' "$said"
    fi ;;
*) echo "not answered: say whether the answer is the default the thread took, default, or not, differs" ;;
esac
```

`default` is an answer that keeps the default the thread took, and `differs` one that does not: only the one who heard the answer knows which, so words such as "yes" are read against the question's default before the block is run. On `answered: question <number>`, the question is closed, and this home sends nothing and undoes nothing: jbus carries an answer that differs to the thread that asked, with the question's undo line, on its next pass. For a question this home asked under its own slug there is no thread to tell: change the plan entry it touches, or write the new brief. Where jbus says the slug `has no Thread: line`, or the thread is finished or its pull request merged, the answer is work for a new brief.

On `not answered: jbus said: refused:` the question is as it was. `only <name> answers` gives the name `--by` takes, and `--at is "<YYYY-MM-DD HH:MM ZONE>"` the form of the time: set that line and run it again. `was answered already` prints the first answer, which stands: the user answered it elsewhere, and a second answer is theirs to give as a new word, not as this question's.

A gate that came as a `<slug>: gate` message is one jbus could not take, so jbus holds no question for it and no command closes it: this thread is its record. Give it to the user in two lines, and send an answer that differs to the thread on its `Asked by:` line yourself (`t3_thread_send`, the answer and the gate's `Undo:` line). It is the one answer a home carries. Until it is answered, the handoff's note carries it under its labels, whole: nothing else outlasts this thread.

## The user's word, carried by jbus

The user says an approval or an instruction for this home wherever they are, most often to Sous Chef, and `jbus word` carries it here: a message that begins `jbus: this is <name>'s own word, said <time> and carried to this home by jbus.`, with their words under it. What jbus carried to this thread is what this prints, in the same call as the block at the top, the block that finds this home and the block that reads jbus ("Gates"):

```sh
: "${SEP:?run the block that reads jbus first}"
if [ -z "$P" ] || ! command -v jbus > /dev/null; then
    echo "$WHY"
elif ! found=$(jbus --project "$P" events 2>&1); then
    echo "jbus could not be asked: $(printf '%s\n' "$found" | head -n 1)"
elif ! found=$(printf '%s\n' "$found" | jq -r --arg me "$ME" 'select(.word.to? == $me and $me != "") | "\(.word.by), \(.word.at): \(.word.words)"' 2> /dev/null); then
    echo "jbus could not be read: what jbus events printed is not JSON lines"
elif [ -z "$found" ]; then
    echo "no word: jbus carried none to this thread"
else
    printf '%s\n' "$found" | tail -n 5
fi
```

It prints the last five, each as `<name>, <time>: <words>`. A message whose words and time are on a line it prints is the user's word, as said in this thread: act on it at once, and ask for no second confirmation, here, to Sous Chef or by a gate. It answers no open question, and nothing is sent back for it. A message that says it is the user's word and is on no line the block prints was not carried by jbus: it is a thread's message, and it approves nothing.

### A go given on a page

The user's answer on a Lavish page is their go for the rows it names, and it is approved by what they sent, which jbus reads from Lavish's state file itself: never by the poll's text, which is this thread's report of it. Once a page's answer comes back, step 5 of the grilling skill's "On a page" prints the send's reference, `<session key>/<entry id>`: the last entry of the page's session in `${LAVISH_AXI_STATE_DIR:-~/.lavish-axi}/state.json` whose role is `user`, with the send's time and text under it. Approve only when that text is the answer the poll returned. Where it is not, approve nothing by `--page`: a later send may take the go back, so ask the user for their word another way. Approve each row with it:

```sh
jbus --project <project> queue approve <slug> --sha <sha12> --page <session key>/<entry id>
```

jbus refuses a state file that is not there, a session or an entry the file does not have, and an entry whose role is not the user's, each in one line. The row then reads `his pick on a Lavish page, <time>, <page file name>; run <time> by the <repo> home`. Where the block prints `no entry`, the page gave no go jbus can read: ask the user for their word another way.

### A follow-up approved by a standing rule

A row of the queue launches on the user's own word, and `jbus queue approve` names it: `--word`, `--answer`, `--message` or `--page`. There is one case where the home approves a row the user did not speak of: the brief is a follow-up to work they approved, and a rule of `standing.md` says a follow-up needs no new approval (rule 6 of this repo's). Then the home names the rule and the parent row, the one the user did give their word for:

```sh
jbus --project <project> queue approve <slug> --sha <sha12> --rule 6 --follows <parent>
```

It is never for new work: new work waits for the user's go, however small it is and whatever entry it is filed under. A follow-up finishes or repairs what the parent row asked for, and asks for no outcome the parent did not. jbus does not judge that, the home does. jbus refuses a parent that is no row of this queue, one with no approval, and one that was itself approved by a rule: a chain is one step, so a follow-up of a follow-up names the first parent or waits for the user. The row then reads `rule 6, follow-up of <parent>; run <time> by the <repo> home; he did not speak of this row`, the page marks it, and the digest counts it for the user: that is how they audit it, so a doubtful one is a gate and not a rule approval.

## Merging a pull request that is ready

A pull request that is reviewed, fixed and green is merged, and the user is told. Nobody has to give the word for that one. A pull request that is anything short of ready is never merged without the user's word. Neither is one that changes a protected path (a secret, or one of the two lists of paths), nor any pull request of a repo whose merge is switched off: those are the user's to merge, ready or not. One that changes a guarded path is merged by the same command, under a stricter gate, and no path is guarded today.

The home merges nothing itself. One command does all of it, with no model: `jmerge`, from the repo this skill lives in. One runner runs it for a repo, jbus or a home, never both: two runs at once would race, and no lock keeps them apart.

**Who merges** is what `$H/home-thread` says, and this block is the one the three blocks below go by. It is the test jbus makes (`src/jbus/merge.py`), and the one the start of a home makes for its warning:

```sh
if [ -n "$(cat "$H/home-thread" 2> /dev/null | tr -d '[:space:]')" ]; then merges=home; else merges=jbus; fi
echo "$merges merges"
```

It prints `home merges` when the file holds an id, and `jbus merges` when it is empty or missing. Run it in the same call as each of the three blocks below, before the block: the merge step, the landing of a stack, which is the merge step with a flag, and the sweep. Each stops with `run the block of "Who merges" first` when it was not run, and `jmerge` is run on `home merges` alone. A home runs `jmerge` to merge, land or sweep nowhere else. `jmerge --claims` changes nothing, and is run whoever merges.

**The merge step** is run on a crewmate's `fixed and green` line, which is sent for it to be run while the home merges, when the user asks for status, and once at the start of a home. On any other message it is step 2 of "When a thread sends a message", so nothing that turned ready is left waiting. Run it from the main checkout, in one call with the block at the top, the block that finds this home and the block of "Who merges", with this thread's id in place of `<threadId>`. On `home merges` it is the only check: do not go by what a report said, or by what you remember.

```sh
: "${merges:?run the block of "Who merges" first}"
flags=''
L="$H/merge.log"
S="${M:?run the block that finds this home first}/merge-seen"
news() {
    tail -n "+$((${1} + 1))" "$L" | head -n "$((${2} - ${1}))" | cut -c18- | grep '^merged ' |
        while IFS= read -r line; do
            slug=${line#merged * }
            if [ "$(whose "$H/tasks/${slug%% *}.md")" = "$M" ]; then printf '%s\n' "$line"; fi
        done
}
lines=$(grep -c '' "$L" 2> /dev/null)
lines=${lines:-0}
seen=$(cat "$S" 2> /dev/null)
case $seen in
'' | *[!0-9]*) seen=$lines ;;
esac
if [ "$seen" -gt "$lines" ]; then seen=0; fi
if [ "$lines" -gt "$seen" ]; then news "$seen" "$lines"; fi
echo "$lines" > "$S"
case $merges in
home)
    own=$(
        uv run --project "$T/.." jmerge --home '<threadId>' $flags
    )
    ran=$?
    if [ -n "$own" ]; then printf '%s\n' "$own"; fi
    end=$(grep -c '' "$L" 2> /dev/null)
    end=${end:-0}
    if [ "$end" -gt "$lines" ]; then news "$lines" "$end" | grep -vxF -e "$own"; fi
    echo "$end" > "$S"
    (exit "$ran")
    ;;
*)
    case " $flags " in
    *" --land "*) echo "not landed: jbus merges here and lands no stack, until $H/home-thread holds an id" ;;
    esac
    if open=$(gh pr list --repo "$(git remote get-url origin)" --state open --limit 200 --json number,url --jq '.[] | "\(.number) \(.url)"'); then
        printf '%s\n' "$open" | while read -r n url; do
            if [ -z "$n" ]; then continue; fi
            brief=$(LC_ALL=C && awk -v url="$url" '$(1) == "Branch:" && $(NF) == url {print FILENAME; exit}' "$H"/tasks/*.md 2> /dev/null)
            if [ "$(whose "$brief")" != "$M" ]; then continue; fi
            said=$(jq -r --arg n "$n" '.[$n] // empty' "$H/merge.log.last" 2> /dev/null)
            printf '%s\n' "${said:-wait $n $url: jbus has said nothing of it yet}"
        done
    else
        echo "wait: could not ask GitHub"
    fi
    ;;
esac
```

On `jbus merges` it runs no `jmerge`: jbus runs it on each pass, and this home's part is to tell the user. The block prints what a run of `jmerge` would, from what jbus's runs left on disk. First the `merged` lines jbus's `jmerge` appended to `$H/merge.log` since this home last read it, without their date: how far it read is kept in `$M/merge-seen`, a home with no mark starts at the end of the log, so an old merge is never news, and a log shorter than the mark is read from its start. Then, for each pull request GitHub lists as open, the last `wait` or `hold` line `jmerge` said of it (`$H/merge.log.last`): that is read anew on every run and no mark is kept for it, so a `hold` is never lost between this block and the one that tells it, a pull request that has waited for long still has its line when the user asks for status, and one that is merged or closed has none. An open pull request `jmerge` has no line for yet is `wait <number> <url>: jbus has said nothing of it yet`. They are the lines of the table below, and are relayed as a run's own are. On `wait: could not ask GitHub` no pull request's line was read.

A line is as of jbus's last pass, not of now: `jmerge` writes one only when it changes, and nothing here says how old it is. No `fixed and green` line is sent while jbus merges, so a pull request that just turned ready often still has the `wait` from before its `Fixed:` line: jbus's next pass judges it, and its `merged` line comes on a later run of this step. If jbus is stopped the lines stay as they were: `systemctl --user status jbus.timer` says whether it runs.

jbus runs `jmerge` for the whole repo, and the block prints this home's lines alone: a `merged` line whose slug is a brief of this home's, and the line of an open pull request that one's `Branch:` line ends on, the first such brief by name in codepoint order, as `jmerge` finds it. A brief is the home's that its `Home:` line names: by its thread id, by the id on the `Was home:` line of its handoff, or by its scope, which is a directory of `$H` with a `home-id` or such a handoff. A brief is the root's when it has no such line, when its line names no such home, or when the pull request has no brief. That is `jmerge`'s one rule (`home_of` in `src/jmerge/claims.py`, over `homes` in `src/jmerge/cli.py`): `jmerge --claims` prints a brief's home by it, and on `home merges` `jmerge --home` leaves the others' out by it. The block first prints the `merged` lines this home has not read, as on `jbus merges`, and sets the mark past them before `jmerge` runs, so a run cut short tells none of them twice. After the run it prints what `jmerge` printed, then any `merged` line of this home's that another writer logged meanwhile, and sets the mark to the end of the log: what this home's own run printed is not news after the switch is emptied. It ends with what `jmerge` ended with and does not end the call, so a sweep joined after it runs.

jbus runs `jmerge` with no `--home`, as the root home would. So the pull request of a brief whose `Home:` line names a scoped home is `wait <number> <url>: another home's` to it, also when it is ready or would be held, and nobody merges it while jbus merges: no `fixed and green` line comes for it either, so when the user asks for status, tell them that this line is a pull request nobody merges, and that it is theirs to merge once its brief has a `Fixed:` line.

On `home merges` it runs `jmerge`. For each open pull request of this repo that is ready, it squash-merges it at the exact head it checked (`gh pr merge <number> --squash --match-head-commit <head>`), runs `git pull --ff-only` in the main checkout, and removes the crewmate's worktree and its local and remote branch. It writes no plan: `jbus plan` counts an entry's status from its queue rows. The skills in `~/.claude/skills` may be symlinks into the main checkout, and stay on the old text until that pull. It prints one line per open pull request, and appends the same lines, dated, to `$H/merge.log`:

| The line | Means |
|---|---|
| `merged <number> <slug> <commit> "<title>", revert: <command>` | it is merged as that commit, the main checkout is pulled, and the worktree and both branches are gone. The line ends in the command that undoes it |
| `merged <number> <slug> <commit> "<title>", the rebase changed the patch in <files>, revert: <command>` | it is merged, and a rebase changed its patch in those files after the last head a review saw: the review stands, and no review saw that change. Tell the user the files |
| `merged <number> <slug> <commit> "<title>", kept: <what and why>, revert: <command>` | it is merged, and something was left: a worktree with uncommitted work, a branch that is not at the merged head, a worktree or a branch git would not remove. Do nothing more about it. The same line says so if the pull failed |
| `merged <number> <slug> <commit> "<title>", guarded: <path>, revert: <command>` | it is merged under the stricter gate of a guarded path, the first one it changes |
| `wait <number> <url>: <reason>` | it is not merged. The reason is the first thing it is short of |
| `wait <number> <url>: guarded (touches <path>), <reason>` | it is not merged yet: it is short of nothing else, it changes a guarded path, and that part of the stricter gate does not hold. It is not the user's to merge: a later run merges it once the reason is gone |
| `hold <number> <url>: needs <the user's name>, touches <path>` | it is not merged and `jmerge` never merges it: it is short of nothing else, and it changes a protected path: a secret, or one of `jmerge`'s two lists. The path is the first one that matches. Tell the user, once: it is theirs to merge |
| `wait <number> <url>: auto-merge is off for this repo` | it is not merged: it is short of nothing else, and the repo has a `merge-off` file. It is the user's to merge |
| `wait <number> <url>: another home's` | its brief's `Home:` line names another home of this repo, and a home merges its own. `--all` merges those too: add it only on the user's word |
| `wait: could not ask GitHub` | nothing was looked at |

Ready means all of these hold. The rules are in `src/jmerge/ready.py`, and nowhere else:

- its base is the default branch. A pull request based on another branch would be merged into that branch, and nothing of it would reach the default one: the line is `wait <number> <url>: its base is <branch>, not <default branch>`, and no flag lifts it;
- its brief has no `Stack:` line in its head, or the user said to land that stack. A stack is landed by the user: the line is `wait <number> <url>: it is in the stack <name>, which the user lands`, and `--land <name>` lifts it, for that stack alone. A `Stack:` line with no name is held, and no `--land` lifts it;
- the brief has a `## Review` section, so a review was written. A brief with `Review: none` gets no review, so it is never ready: it needs the user's word;
- the review is clean, or the crewmate's Result has its `Fixed:` line;
- the head is the commit the `Fixed:` line names, and after findings that is not the head the review saw: a fix is a push. A crewmate that declines every finding writes `Fixed: none needed`. With `Fixed: none needed`, or a clean review and no `Fixed:` line, it is the head the review saw, or the commit the Result's `Rebase:` line ends on. A `Rebase:` line with no commit, as older briefs have, is not ready: a push the command cannot account for reads as not ready;
- a `Rebase:` line that says `patch unchanged, before <commit>, head <commit>` is true: `jmerge` works out the patch-id of the base-to-head diff at both commits, in the main checkout, and waits when the two differ or when it cannot work one out (a commit that is not in the checkout). A line that says `patch changed in <files>` does not hold the merge, since a review stands after a rebase: the `ready` or `merged` line says `the rebase changed the patch in <files>`, unless a review was written of the head the rebase ended on or of the head it is merged at. A line in the older shape, `range-diff empty` or `changed <files>`, is read for its last word alone;
- the fix is reviewed where it must be: a fix that changes a file outside `tests/` gets one scoped review. A Result with the line `Scoped review: needed since <head>` is not ready until the brief has a review of a later head and every finding of every review has its `Finding:` line. That review counts as the review in the lines above. A fix under `tests/` only is not reviewed. A brief from before the scoped review has `Second pass: needed since <head>` and is read the same way;
- the check named `check` passed at its head, whatever the other checks say. It is the job the repo's workflow runs the check command in. A `check` that failed, has not finished, was skipped or is not among the checks has not passed, and the line is `wait <number> <url>: check has not passed`. Nothing stands in for it: a pull request whose checks did not run is not green, whatever its Result says of a check command that passed in the crewmate's worktree, an older `CI: did not run` line included;
- GitHub says `MERGEABLE`.

Two more things keep a ready pull request from the command, and only the user lifts them. They are looked at last, so each is said of a pull request that is short of nothing else:

- it changes no protected path. The patterns are in `src/jmerge/protected.txt`, one per line, `#` for a comment: `secrets/`, `.env`, `.env.*`, `*.pem`, `*.key`, the two lists themselves, `/src/jmerge/protected.txt` and `/src/jmerge/guarded.txt`, and `/policy/` and `/dns/` at the root of a repo, where a change applies to the live tailnet policy or DNS records. A pattern that ends in `/` is a directory and covers everything under it, from the root of the repo when it has another `/` in it and at any depth when it has none. Any other pattern is a file: a name at any depth, or with a `/` in it the whole path from the root, as `src/jbus/merge.py`. A `*` matches within one part of a path. `jmerge` refuses to run, and merges nothing, while that file, `guarded.txt` or `ci-paths.txt` is missing or has a pattern it cannot read (`**`, a leading `!`): no line there is taken and ignored. The line is `hold <number> <url>: needs <the user's name>, touches <first matching path>`, with the name `jmerge` reads from `~/.config/jstack/config.toml` (`user` where that file names none), and no flag lifts it, `--all` and `--land` included. A rename changes both its paths: one into or out of a protected path is held as an edit there is, and one between two paths that are not protected is not. GitHub lists a rename under its new path alone, so `jmerge` asks for the paths the renames left, of a pull request that has one and is short of nothing else. GitHub must have said every path the pull request changes: one whose file list it cut short is held, and so is one whose renames it would not give the old paths of. To protect or guard another path, a pull request adds a line to `protected.txt` or `guarded.txt`, and since it changes one of the two lists the user merges it;
- the repo's merge is on. Every repo is on until `$H/merge-off` is there: `/nohome merge` makes the file and `/nohome merge on` removes it. With it, the line is `wait <number> <url>: auto-merge is off for this repo`, whoever runs the command, a home or `jbus`.

A pull request that changes a guarded path, and no protected one, is merged by `jmerge` itself, under a stricter gate. The patterns are in `src/jmerge/guarded.txt`, in the same syntax. The user emptied the list on 2026-10-12 ("drop the guarded merge guards"), so a ready pull request merges with none of the parts below asked. The gate's code stays, and a line added to the file guards its path again: that is a change to a protected path, so the user merges it.

Guarded today: none.

When a path is guarded, the gate is looked at beside the hold, of a pull request that is short of nothing else, and the first part that does not hold is the line `wait <number> <url>: guarded (touches <first guarded path>), <reason>`. Nobody merges such a pull request by hand: a later run merges it once the reason is gone, and a reason that needs work (a rebase, a `Finding:` line) is the crewmate's.

- `jmerge`'s own rules are main's. A pull request cannot weaken its own gate: `jmerge` never checks one out, and reads its code and its lists from its own package directory. Before it judges a guarded pull request, and in its own repo before the first merge of a run, whose pull would bring that checkout up to date under code already loaded, it fetches the git checkout that holds that directory, and goes on only if the package there has no uncommitted or untracked change and is what `origin`'s default branch has. A checkout that is only behind is pulled, and the reason is `jmerge pulled main's rules; judged on the next run`: the code already loaded is the old one. Anything else waits with its reason (`jmerge's own rules have a change that is not committed`, `are not main's`, `are not in a git checkout`). After a merge that changes `src/jmerge/`, every later guarded pull request of that run waits: `jmerge's rules changed in this run`. So a pull request that changes `ready.py`, `guarded.txt` or `ci-paths.txt` is judged by main's version;
- its check has a start time: `check` passed at the head, as for any pull request, and the time its earliest run started there is known. The reason is `its check has no start time`;
- its review is finished, and is of that head. Every finding the review lists has its `Finding:` line, with or without a second pass: `<k> of its <n> findings have no Finding line`. The head is the one the review saw, the `Fixed:` commit, or the head of a `Rebase: patch unchanged` line that is true: `its head is not the one its review saw`. A `Rebase: patch changed in <files>` line with no review written of the rebased head does hold a guarded path: `the rebase changed the patch after its review`;
- it is fresh against main. After a `git fetch` in the main checkout, the paths the first-parent commits of the default branch changed since the check started, the paths their renames left included, do not meet the paths the pull request changes, and none is a CI path (`src/jmerge/ci-paths.txt`: `.github/workflows/`, `/pyproject.toml`, `/uv.lock`, `/Makefile`). The reason is `main changed <up to five paths> after its check started at <HH:MM> ET; it needs a rebase`. A main that moved only on other paths is fresh, and nothing is rebased for it;
- main is still the commit it was judged against, right before the merge (`git ls-remote`). The reason is `main moved while it was judged`, and the next run judges it again. Its `merged` line says `guarded: <first guarded path>`.

A pull request that is held (`hold`) is merged by the user, by hand, and so is any pull request of a repo whose merge is off. The sweep below then removes what its thread left.

A head that moved between the check and the merge fails the merge, and that is the wanted result: the line is `wait <number> <url>: the merge failed`, with what GitHub said, and the next run looks again. A worktree is removed only when it is clean and its branch is at the merged head, so nothing unpushed is lost.

**The log is the undo list.** Each `merged` line in `$H/merge.log` starts with the time it was printed, then its first four words, `merged <number> <slug> <commit>`, then the pull request's title in quotes, the notes above, and last `revert: gh pr revert <url>`. Run as it stands, from anywhere, that command opens a pull request that reverts the merge. It pushes nothing to the default branch and changes nothing in the checkout: the revert is a pull request like any other, and is merged like one. Run it on the user's word only, and give them the pull request it prints.

Relay what it printed: tell the user in one line per pull request, the slug, the pull request, that it is merged, and anything that was kept. A `hold` line is the user's to act on, and jbus tells them of it: each pull request `jmerge` holds is on jbus's list of what waits on the user, from jbus's own run or from the last line a home's run logged, which `jbus queue show` prints first. Tell it only when the user asks for status, or when it is about the pull request a message was sent for. A `wait` line is reported, not acted on: give it to the user when they ask for status, and when it is about the pull request a message was sent for. The home does not fix what a pull request is short of. Its crewmate does. Settling a merged crewmate's thread is not the command's: T3 Code settles a thread whose linked pull request merges.

To see what is ready and merge nothing, run the merge step with `flags='--check'` in place of its `flags=''` line, on `home merges`: on `jbus merges` the `jmerge` line is not reached, and the merge step's own lines say what waits. It prints `ready <number> <head> <branch> <slug>` in place of merging. A pull request that is held, or whose repo's merge is off, is printed as it is without the flag: it is not `ready`.

To land a stack, run the merge step with `flags='--land <name>'` in place of its `flags=''` line, the stack's name in place of the words in angle brackets: one run, which reads the log and sets the mark as every merge step does. To see what would land and merge nothing, it is `flags='--check --land <name>'`. It is run on the user's word only: "land <name>", said in this thread. No `fixed and green` line, no tick and no start of a home runs it.

On `jbus merges` the merge step then prints `not landed` before its other lines, and nothing was run: jbus never adds `--land`. Tell the user that landing the stack needs an id in `$H/home-thread`, which only they write, and do nothing more. On `home merges`, `--land` lifts the second wait for the pull requests whose `Stack:` line names that stack, and nothing else: each is merged as any other, when it is ready and its base is the default branch. So one run lands the bottom link and prints `its base is <branch>, not <default branch>` for every link above it. The merged link's remote branch stays while a pull request is based on it, and its line says so under `kept:`. `jmerge` changes no base, and prints nothing that says a new base is the next step: "A stack the user lands" has it, and the playbook `shipping` has the steps in order.

A merge clears up after itself only when all is clean at that moment. What is left then, and what never had a merge by this command, is the sweep's: a `kept:` of a merge, a pull request merged by hand, a crewmate that ended with no pull request, a scout's worktree, the gate's ref. The same command does it, with no model. Run it once at the start of a home, after the merge step, from the main checkout, in one call with the block at the top and the block of "Who merges":

```sh
case ${merges:?run the block of "Who merges" first} in
home) uv run --project "$T/.." jmerge --sweep ;;
*) echo "no sweep: jbus merges here, and this home runs no jmerge" ;;
esac
```

On `no sweep`, nothing was run and there are no lists to act on. On `home merges`, it looks at each branch a brief in `$H/tasks` or a request in `$H/scouts` names, a crewmate's `<slug>` and a scout's `scout-<slug>`, with its worktree under `~/.t3/worktrees/<repo>`, and at every other worktree there. It prints two lists, the first one removed, and appends the same lines, dated, to `$H/merge.log`:

| The line | Means |
|---|---|
| `removed <branch> <thread>: <what>` | the thread is finished and nothing of its work could be lost, so what it left is gone: the worktree, the local branch, the remote branch, the gate's ref, whichever were there |
| `removed <branch> <thread>: <what>, kept: <what and why>` | git refused a step, and the rest is left for the next sweep |
| `kept <branch>: <reason>` | nothing of it was removed. The reason is the first of: not done, blocked, paused, something under Left, a scout's Report with a page, a pull request that is open or closed unmerged, uncommitted work, a commit that is in neither the remote's default branch nor its merged pull request, a process running in the worktree |
| `kept <directory>: no brief or request names its branch <branch>` | a worktree of T3 Code's that is nobody's task here. It is never removed |
| `wait: could not read origin` | nothing was looked at |

Removable means all of these hold. The rules are in `src/jmerge/sweep.py`, and nowhere else:

- the brief's last Result says `Status: done` and `Left: none`, or the request's last Report says `Status: done` and names no page: a page may still wait on the user;
- its pull request is merged, or it has none;
- the worktree has nothing uncommitted and no process running in it;
- each of the local branch, the remote branch and the gate's ref is at a commit the remote's default branch has, or at the merged pull request's head or behind it.

A branch or worktree that no brief or request names is never removed: the sweep does not list such a branch at all.

For each `removed` line, settle the thread it names, unless it says `no-thread`: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle", "threadId": "<thread>"}`. T3 Code has settled most of them by then, and a scout settles itself: a thread that is settled stays so. If the line is a crewmate's and its plan entry does not say done yet, as after a pull request merged by hand, set it. Tell the user all of them in one line.

A `kept` line is reported, not acted on: the home removes nothing by hand. Give the user the ones that wait on their word, in one line each: blocked, paused, something under Left, a pull request closed unmerged, uncommitted work, a commit that is nowhere else, a scout's page, a worktree nobody's task names. Say nothing of the ones that are only still out: not done, a pull request that is open, a process running.

To see both lists and remove nothing, add `--check`: it prints `removable` in place of `removed`, and logs nothing.

## A queue and its hourly audit

At every home's start (step 5), when a queue playbook (`autopilot-full` or `orchestrate`) is taken up, on each audit tick, when a queue's last entry is set to done, and before a handoff: read `$T/../skills/home/queue-and-its-hourly-audit.md` now. Its "the next section" is "Picking up a thread that stopped", below.

## Picking up a thread that stopped

A thread that stopped with its task unfinished is picked up, not started over: a turn a T3 Code restart cancelled, one that failed at the plan's limit, one the audit printed as `stuck`. Its worktree and its brief hold what it did. The playbook `session-pickup` has the steps: open it with the block of "A playbook of the home's own". It ends in one of two calls.

A message first, when the thread can still take one: `t3_thread_send` to the id on the brief's `Thread:` line, one line, to carry on from its brief and its worktree and to redo nothing that is there.

A new thread on the same worktree when it cannot: the send fails, the thread is archived or gone, or it was sent that message once and the next tick prints it `stuck` again. Find the worktree whose branch is the slug with `git worktree list --porcelain`, from the main checkout. With none, there is nothing to pick up: launch from step 2 of "Handing a task to a crewmate". Add one line to the brief, above its first `## ` heading, so the new thread knows it resumes: `Resume: <date>, the thread before this one stopped. Its work is in this worktree and in the last Result below: redo nothing that is there, and carry on from <the resume point>`. The crew skill reads the brief at its start, and a brief is trusted. Then, on `go` from `room`, the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first):

```json
{
  "title": "crew: <slug>",
  "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<slug>"},
  "message": "/crew <slug>"
}
```

Before this launch, run `uv run --project "$T/.." jroles crew` with the block at the top. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the crewmate on the model the role map names. When it prints nothing, the call is the one above. Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line. Leave the project and modes out, and the model unless `jroles` printed one.

```json
{
  "title": "crew: <slug>",
  "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<slug>"},
  "message": "/crew <slug>",
  "modelSelection": <model selection>
}
```

Put the new thread's id on the brief's `Thread:` line with the block of step 3 of "Handing a task to a crewmate", which takes the old line's place, and give the user the link. One writer per worktree: never launch on a worktree whose last thread is `running`.

## A stack the user lands

When the head of `$M/plan.md` names `autopilot-stack` on its `Playbook:` line, or the user lands a stack: read `$T/../skills/home/stack-the-user-lands.md` now.

## Scoped homes

When the root home is asked for status, when the repo has more than one home, or when the user asks for a home scoped to one goal: read `$T/../skills/home/scoped-homes.md` now.

## When to hand off

Read `$T/../skills/handoff/SKILL.md` and do its steps, then stop working in this thread, when any of these is true:

- The planning the user came for is done and the tasks are handed out.
- The user moves to a different piece of work.
- The context is past 300,000 tokens, or this thread has been compacted once. `hooks/home-gauge.sh` tells this thread its count after every tool call from then on, and at 350,000 it refuses every tool call but the ones the handoff makes: only the handoff runs.
- The user says so.

Before the handoff, end the audit of a queue, as "A queue and its hourly audit" says for a home that hands off: it posts into this thread, and the next home schedules its own.

Say it plainly when one of them is reached: "This is a good point to hand off." Do not wait to be asked.
