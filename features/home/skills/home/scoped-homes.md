## Scoped homes

A scoped home is a home like any other, for one goal: it plans and launches its own tasks by this skill, from its own directory.
jbus merges a scoped home's pull requests as it merges the root home's, and no home merges its own ("Merging a pull request that is ready").
The homes of a repo do not plan each other's work, and they are quiet towards each other:

- A home sends another home one kind of message: a decision that crosses scopes, one that changes what that home may plan or touch. Send it with `t3_thread_send` to the id in that home's `home-id`, in the user's words. A home with no `home-id` is not running: write the decision as a dated line in `$H/standing.md`, which its next start reads whole, and snapshot it as the next point says.
- A scoped home sends the root only what it cannot resolve on its own and that needs the big picture: a decision or a stop, by the block of "Sending the root" below.
- Nothing else is sent: not a launch, a merge, a pull request opened, a score, a status, or that a scope has ended.
  The root home reads the scope's files, its plan and its queue rows, when the user asks for status ("Reading the scopes").
  A scope that ends says so in its own `handoff.md`.
- A standing rule from the user is one dated line in `$H/standing.md`, written by the home that heard it, or a change to a skill, which is a task. Right after any edit to it, run `jbus snapshot --why "<repo> standing rule <n> <added, changed or removed>"`, so the edit is a commit of its own in `~/.local/state/home`, pushed, and can be undone ("Undo an edit to standing.md" in `docs/state.md`). It is relayed to no home: every home reads `standing.md` whole at its start.
- No home asks another what it has out. The launch check of "When a thread sends a message" prints it.
- A user's word about another home's work, a page that home opened, a row with its `Home:` line or a slug of its prefix, is that home's alone: forward it with the one `jbus word --from "$ME"` line of "A word this home records", which carries it there, and brief nothing of it.

A scoped home gives each brief and request a slug that starts with its prefix, the one its section of `$H/notes.md` names.

**Sending the root** is a scoped home's, and only for one of two kinds.
A `decision` is one the scope cannot make on its own, since it needs the big picture: it crosses scopes, or changes what another home may plan or touch.
A `stop` is a blocker the scope cannot clear by itself, nor by a gate to the user.
In one call with the block at the top and the block that finds this home, with the kind in place of `<decision or stop>` and what the root must decide or clear, in a line or two, in place of the other words in angle brackets:

```sh
kind='<decision or stop>'
what=$(paste -sd ' ' - << 'THE_SEND_ENDS_HERE'
<what the root must decide or clear>
THE_SEND_ENDS_HERE
)
root=$(awk 'NF {print $(1); exit}' "$H/home-id" 2> /dev/null)
if [ "${M:?run the block that finds this home first}" = "$H" ]; then
    echo "not sent: this is the root home, and only a scoped home sends the root"
else
    case $kind in
    decision | stop)
        case $what in
        '' | '<what the root '*) echo "not sent: what the root must decide or clear is not filled in" ;;
        *)
            if [ -z "$root" ]; then
                echo "not sent: no root home is running, $H/home-id holds no thread: park the $kind as a gate (\"Gates\"), which jbus takes to the user"
            else
                printf '%s\n' "$root" "${M##*/} home, a $kind: $what" | jq -R . | jq -sc '{threadId: .[0], message: .[1]}' | sed 's/^/send: /'
            fi ;;
        esac ;;
    '' | *'<'* | *'>'*) echo "not sent: the kind is not filled in, decision or stop" ;;
    *) echo "not sent: a $kind is not sent to the root, only a decision or a stop: the root reads this scope's plan, $M/plan.md, and its queue rows when the user asks for status" ;;
    esac
fi
```

On `send:`, send what the block printed after `send: `, as it is, with `t3_thread_send`.
On `not sent:` nothing is sent: do what the line says.

**Making a scope** is the root home's, and only on the user's word. In one call with the block at the top and the block that finds this home, with the scope's name in place of `<scope>`, the prefix its slugs and branches will start with, such as `rs-`, in place of `<prefix>`, and what the scope owns, in the user's words, in place of `<what the scope owns>`:

```sh
scope='<scope>'
prefix='<prefix>'
owns=$(paste -sd ' ' - << 'WHAT_IT_OWNS_ENDS_HERE'
<what the scope owns>
WHAT_IT_OWNS_ENDS_HERE
)
why=
if [ "${M:?run the block that finds this home first}" != "$H" ]; then
    why="this is the home of the scope $(basename "$M"), and only the root home makes a scope: the user asks the root home for it"
fi
if [ -z "$why" ]; then
    case $scope in
    '' | *'<'* | *'>'*) why="the scope's name is not filled in" ;;
    .* | *[!A-Za-z0-9._-]*) why="$scope is not a name a scope can have: letters, digits, dots and dashes, and no dot first" ;;
    tasks | scouts | reports | log) why="$scope is a directory every home of $R shares" ;;
    off | merge.log) why="$scope is a file of $R's own directory, there or not" ;;
    *)
        if [ -f "$H/$scope/plan.md" ]; then
            why="$scope is already a scope of $R: its home starts with /home $scope"
        elif [ -e "$H/$scope" ]; then
            why="$scope is there already, as $H/$scope, and is no scope"
        fi ;;
    esac
fi
if [ -z "$why" ]; then
    case $prefix in
    '' | *'<'* | *'>'*) why="the slug prefix is not filled in" ;;
    *[!a-z0-9-]* | -* | *[!-]) why="the slug prefix $prefix is not lower-case letters and digits that end in a dash, as rs- is" ;;
    *)
        for sent in "$H"/tasks/"$prefix"*.md "$H"/scouts/"$prefix"*.md; do
            if [ -f "$sent" ]; then why="a brief or a request already starts with $prefix: $sent"; fi
        done
        for given in $(grep -o '[a-z0-9-]*-\*\.md' "$H/notes.md" 2> /dev/null | sed 's/\*\.md$//'); do
            case $given in
            "$prefix") why="the slug prefix $prefix is another home's, as $H/notes.md says" ;;
            "$prefix"*) why="the slug prefix $prefix is the start of $given, which $H/notes.md gives to another home" ;;
            *) case $prefix in "$given"*) why="the slug prefix $prefix starts with $given, which $H/notes.md gives to another home" ;; esac ;;
            esac
        done ;;
    esac
fi
if [ -z "$why" ]; then
    case $owns in
    '' | '<what the scope '*) why="what the scope owns is not filled in" ;;
    esac
fi
if [ -n "$why" ]; then
    echo "not made: $why. Nothing is written."
else
    day=$(date +%F)
    if mkdir "$H/$scope" 2> /dev/null &&
        printf '# %s, %s: plan\n\nGoal (%s, the user): %s\n' "$R" "$scope" "$day" "$owns" 2> /dev/null > "$H/$scope/plan.md" &&
        {
            if [ -s "$H/notes.md" ]; then echo; fi
            printf '## Scoped home: %s, %s\n' "$scope" "$day"
            printf -- '- A scoped home (`home: %s %s`), made by the root home on the user'"'"'s word. It owns: %s\n' "$R" "$scope" "$owns"
            printf -- '- Its handoff, plan and log are in `%s/`. Its briefs and scout requests are `%s*.md` in the shared `tasks/` and `scouts/`, and its branches start with `%s`. This file stays shared. Start it with `/home %s`. The root home plans no `%s` task, and that home plans nothing else.\n' "$scope" "$prefix" "$prefix" "$scope" "$prefix"
        } 2> /dev/null >> "$H/notes.md"; then
        echo "made: scope $scope, with $H/$scope/plan.md and its section in $H/notes.md"
        printf 'launch: {"title": "home: %s %s", "workspaceStrategy": {"type": "root"}, "message": "/home %s"}\n' "$(printf '%s' "$R" | sed 's/[\\"]/\\&/g')" "$scope" "$scope"
    else
        uv run --project "$T/../source" jbus forget --dir "$H/$scope/plan.md" "$H/$scope" > /dev/null 2>&1
        echo "not made: $H/$scope/plan.md or the section in $H/notes.md could not be written, and what was made is taken back. Nothing is written."
    fi
fi
```

On `made:`, the scope has its plan, with the goal as its first line, and a dated section in the shared notes that says what it owns and its prefix. Start its home with `t3_thread_launch`, on `go` from `room`: send what the block printed after `launch: `, as it is. It starts in the main checkout, as every home does. A lost reply is looked for by that title, as "Handing a task to a crewmate" says. Give the user the link. With no such tool, tell the user to open a new thread in this project and type `/home <scope>`.

On `not made:` nothing is written: tell the user what the line says. A name or a prefix that is taken needs another from them.

**Reading the scopes** is the root home's too, when the user asks for status. In one call with the block at the top and the block that finds this home:

```sh
if [ "${M:?run the block that finds this home first}" = "$H" ]; then
    why=
    rows=
    if ! command -v jbus > /dev/null; then
        why="no jbus: jbus is not installed here, so it holds no row"
    elif ! shown=$(jbus queue show 2>&1); then
        why=$(printf '%s\n' "$shown" | head -n 1)
    else
        rows=$(printf '%s\n' "$shown" | awk '
            function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }
            /^\|/ {
                line = $(0); gsub(/\\\|/, "\001", line)
                n = split(line, cell, "|")
                for (i = 1; i <= n; i++) gsub(/\001/, "|", cell[i])
                if (!head) { for (i = 2; i < n; i++) at[trim(cell[i])] = i; head = 1; next }
                if (trim(cell[2]) ~ /^-+$/) next
                print trim(cell[at["slug"]]) "\t" trim(cell[at["slug"]]) " | " trim(cell[at["status"]]) " | " trim(cell[at["pr"]]) " | " trim(cell[at["why"]])
            }' | while IFS="$(printf '\t')" read -r slug line; do
            if [ -f "$H/tasks/$slug.md" ]; then printf '%s\t%s\n' "$(whose "$H/tasks/$slug.md")" "$line"; fi
        done)
    fi
    for plan in "$H"/*/plan.md; do
        [ -f "$plan" ] || continue
        scope=$(basename "$(dirname "$plan")")
        case $scope in
        tasks | scouts | reports | log) continue ;;
        esac
        if [ -s "$H/$scope/home-id" ]; then
            echo "=== scope $scope: home thread $(cat "$H/$scope/home-id")"
        else
            echo "=== scope $scope: no home thread"
        fi
        if [ -s "$H/$scope/handoff.md" ]; then cat "$H/$scope/handoff.md"; else echo "no handoff yet"; fi
        echo "=== scope $scope: open plan entries"
        awk '
            function entry() {
                if (title != "" && !done) { print title; if (status != "") print status; shown++ }
                title = status = ""; done = 0
            }
            /^## / { entry(); title = substr($(0), 4); next }
            /^Status:/ && title != "" && status == "" { status = $(0); if ($(2) ~ /^done([^a-z]|$)/) done = 1 }
            END { entry(); if (!shown) print "none" }' "$plan"
        echo "=== scope $scope: queue rows"
        if [ -n "$why" ]; then
            echo "$why"
        else
            printf '%s\n' "$rows" | awk -F '\t' -v dir="$H/$scope" '$(1) == dir { print $(2); shown++ } END { if (!shown) print "none" }'
        fi
    done
fi
```

It prints nothing in a repo with no scope, and nothing for a scoped home.
For each scope it prints the scope's handoff, whole, then each entry of its plan that is not done, as its heading and its `Status:` line.
Last it prints the scope's rows in jbus's queue, each as its slug, status, pull request and why: what a scope no longer sends the root, its launches, pull requests and merges, is there.
A scope with a `home-id` has a home running, and that id makes its link.
Tell the user each scope in a line or two: what is out, what is next, and that it is closed when its handoff says so.
The rest of an entry is in `$H/<scope>/plan.md`: read it only when the user asks about that task.
Send the scope's home nothing.
