## Reading the scopes

The root reads every child on each wake: at its start, on each message jbus or a thread sends it, and when the user asks for status or about a child.
It reads the children's files and rows, and no child is asked or woken for it.
In one call with the block at the top and the block that finds this home:

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
        asked | tasks | scouts | reports | log) continue ;;
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
            /^Status:/ && title != "" && status == "" { status = $(0); if ($(2) == "done" || $(2) == "done.") done = 1 }
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
For each scope it prints a note an older handoff left there, whole, or `no handoff yet`, then each entry of its plan that is not done, as its heading and its `Status:` line.
Last it prints the scope's rows in jbus's queue, each as its slug, status, pull request and why: what a scope no longer sends the root, its launches, pull requests and merges, is there.
A scope with a `home-id` has a home running, and that id makes its link.
On status and at a start the user began, tell the user each scope in a line or two: what is out and what is next.
On any other wake, act on what the read shows, such as a child with no row to work on or an entry whose go is owed, and the turn ends by "How a turn ends" with nothing said for the read.
The rest of an entry is in `$H/<scope>/plan.md`: read it only when the user asks about that task.
Send the scope's home nothing for the read: a steer it needs goes by `jbus tell` ("Tell a child").
