## Scoped homes

A scoped home is a home like any other, for one goal: it plans and launches its own tasks by this skill, from its own directory.
jbus merges a scoped home's pull requests as it merges the root home's, and no home merges its own ("Merging a pull request that is ready").
The homes of a repo do not plan each other's work, and they are quiet towards each other:

- The root home sends a scoped home one kind of message: a decision that crosses scopes, one that changes what that home may plan or touch.
  It is the user's word, carried with `jbus word --to "$P" --message '<thread id>/<message id>' --scope <scope>`, given again for each scope or once as `--scope every`, and never with `t3_thread_send`.
  jbus checks that the message is the user's own, keeps one record for each scope, says `held` for a scope that has it already, and wakes each home once on its next pass.
  The root writes no words of its own into it.
  A home with no `home-id` is not running: write the decision as a dated line in `$H/standing.md`, which its next start reads whole, and snapshot it as the next point says.
- A scoped home reaches the root only when it is stuck and needs steering: a stop on its own open row, which jbus takes only when another home's row or something no home owns holds it ("Stopping on the root" below), and a decision only the user can make is a gate.
- Nothing else is sent: not a launch, a merge, a pull request opened, a score, a status, or that a scope has ended.
  The root home reads the scope's files, its plan and its queue rows, when the user asks for status ("Reading the scopes").
  A scope that ends says so in its own `handoff.md`.
- A standing rule from the user is one dated line in `$H/standing.md`, written by the home that heard it, or a change to a skill, which is a task. Right after any edit to it, run `jbus snapshot --why "<repo> standing rule <n> <added, changed or removed>"`, so the edit is a commit of its own in `~/.local/state/home`, pushed, and can be undone ("Undo an edit to standing.md" in `docs/state.md`). It is relayed to no home: every home reads `standing.md` whole at its start.
- A finding one home has for another, something it found that is that home's to act on, is a record and never a send: `jbus --project "$P" noticed add --for <scope or root> --from "$ME" "<the finding>"`.
  jbus keeps it for that home and wakes that home once, and the home marks it with `noticed take` or `drop`.
  jbus refuses a record for no home of the project, and one a home keeps for itself.
- No home asks another what it has out. The launch check of "When a thread sends a message" prints it.
- A user's word about another home's work, a page that home opened, a row with its `Home:` line or a slug of its prefix, is that home's alone: forward it with the one `jbus word --from "$ME"` line of "A word this home records", which carries it there, and brief nothing of it.

A scoped home gives each brief and request a slug that starts with its prefix, the one its section of `$H/notes.md` names.

**Stopping on the root** is a scoped home's, and the only way it reaches the root.
A stop is a fact of the queue that jbus checks: one of this home's own open rows is held by another home's open row, or by something no home owns, and this home cannot clear it.
jbus refuses any other stop: one on this home's own rows only, one on a row that merged, is done or was removed, and the same stop again while it is open.
In one call with the block at the top, the block that finds this home and the block that reads jbus, with this home's held row in place of `<own row>`, the other home's row or its pull request's `#<n>` in place of `<row or #pr>`, and what the root must clear, in a line, in place of the last words in angle brackets:

```sh
: "${ME:?run the block that finds this home first}" "${P:?run the block that reads jbus first}"
jbus --project "$P" stop '<own row>' --on '<row or #pr>' --from "$ME" '<what the root must clear>'
```

When what holds the row is no home's (the machine, the install, Claude Code), put `--outside '<what holds it>'` in place of `--on '<row or #pr>'`.
jbus takes that stop too, and counts it per scope in the digest, since no row backs it.
On `stopped:` jbus has sent the stop to the root home's thread, read as it sends, or keeps it until a root home runs, and sends nothing more for it.
On `refused:` nothing is sent: the home clears what the line names itself, or it is no stop.
A stop whose own row merges or is removed closes itself, with no message.

A `decision` the scope cannot make alone, one the user must make, is no stop: park it as a gate (`jbus gate`, "Gates"), which jbus takes to the user.
Nothing else reaches the root, and never by a `t3_thread_send` of this home's own or a line in `$H/standing.md`.
`features/home/hooks/agent-sends.sh` refuses a home's own `t3_thread_send` to any home of this repo, or to a crew of another home's brief, and its line names the jbus verb that carries the message instead.

**Answering a stop** is the root home's.
jbus's message names the scope and the row; answer it once, in the same call as the block that finds this home and the block that reads jbus:

```sh
: "${ME:?run the block that finds this home first}" "${P:?run the block that reads jbus first}"
jbus --project "$P" stop answer '<scope>' '<own row>' '<the answer>' --from "$ME"
```

`--from` comes last.
jbus closes the stop and carries the answer to the scope's home, once.

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
