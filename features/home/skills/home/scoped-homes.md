## Scoped homes

A scoped home is a home like any other, for one goal: it plans, launches and, on `home merges`, merges its own tasks by this skill, from its own directory.
On `jbus merges` jbus merges a scoped home's pull requests as it merges the root home's ("Merging a pull request that is ready").
The homes of a repo do not plan each other's work, and they are quiet towards each other:

- A home sends another home one kind of message: a decision that crosses scopes, one that changes what that home may plan or touch. Send it with `t3_thread_send` to the id in that home's `home-id`, in the user's words. A home with no `home-id` is not running: write the decision as a dated line in `$H/standing.md`, which its next start reads whole, and snapshot it as the next point says.
- Nothing else is sent: not a launch, a merge, a status, or that a scope has ended. The root home is sent nothing while a scope works, and reads the scope's files when the user asks for status. A scope that ends says so in its own `handoff.md`.
- A standing rule from the user is one dated line in `$H/standing.md`, written by the home that heard it, or a change to a skill, which is a task. Right after any edit to it, run `jbus snapshot --why "<repo> standing rule <n> <added, changed or removed>"`, so the edit is a commit of its own in `~/.local/state/home`, pushed, and can be undone ("Undo an edit to standing.md" in `docs/state.md`). It is relayed to no home: every home reads `standing.md` whole at its start.
- No home asks another what it has out. The launch check of "When a thread sends a message" prints it.
- A user's word about another home's work, a page that home opened, a row with its `Home:` line or a slug of its prefix, is that home's alone: forward it with the one `jbus word --from "$ME"` line of "A word this home records", which carries it there, and brief nothing of it.

A scoped home gives each brief and request a slug that starts with its prefix, the one its section of `$H/notes.md` names.

**Making a scope** is the root home's, and only on the user's word. In one call with the block at the top and the block that finds this home, with the scope's name in place of `<scope>`, the prefix its slugs and branches will start with, such as `rs-`, in place of `<prefix>`, and what the scope owns, in the user's words, in place of `<what the scope owns>`:

```sh
scope='<scope>'
prefix='<prefix>'
what_it_owns() {
    cat << 'WHAT_IT_OWNS_ENDS_HERE'
<what the scope owns>
WHAT_IT_OWNS_ENDS_HERE
}
owns=$(what_it_owns | paste -sd ' ' -)
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
    *[!abcdefghijklmnopqrstuvwxyz0123456789-]* | -* | *[!-]) why="the slug prefix $prefix is not lower-case letters and digits that end in a dash, as rs- is" ;;
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
        rm -f "$H/$scope/plan.md"
        rmdir "$H/$scope" 2> /dev/null
        echo "not made: $H/$scope/plan.md or the section in $H/notes.md could not be written, and what was made is taken back. Nothing is written."
    fi
fi
```

On `made:`, the scope has its plan, with the goal as its first line, and a dated section in the shared notes that says what it owns and its prefix. Start its home with `t3_thread_launch`, on `go` from `room`: send what the block printed after `launch: `, as it is. It starts in the main checkout, as every home does. A lost reply is looked for by that title, as "Handing a task to a crewmate" says. Give the user the link. With no such tool, tell the user to open a new thread in this project and type `/home <scope>`.

On `not made:` nothing is written: tell the user what the line says. A name or a prefix that is taken needs another from them.

**Reading the scopes** is the root home's too, when the user asks for status. In one call with the block at the top and the block that finds this home:

```sh
if [ "${M:?run the block that finds this home first}" = "$H" ]; then
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
    done
fi
```

It prints nothing in a repo with no scope, and nothing for a scoped home. For each scope it prints the scope's handoff, whole, then each entry of its plan that is not done, as its heading and its `Status:` line. A scope with a `home-id` has a home running, and that id makes its link. Tell the user each scope in a line or two: what is out, what is next, and that it is closed when its handoff says so. The rest of an entry is in `$H/<scope>/plan.md`: read it only when the user asks about that task. Send the scope's home nothing.
