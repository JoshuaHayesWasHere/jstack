## Making a scope

The root makes a scope only on the user's word.
In one call with the block at the top and the block that finds this home, with the scope's name in place of `<scope>`, the prefix its slugs and branches will start with, such as `rs-`, in place of `<prefix>`, and what the scope owns, in the user's words, in place of `<what the scope owns>`:

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
    asked | tasks | scouts | reports | log) why="$scope is a directory every home of $R shares" ;;
    off | merge.log) why="$scope is a file of $R's own directory, there or not" ;;
    *)
        if [ -f "$H/$scope/plan.md" ]; then
            why="$scope is already a scope of $R: its home starts with /home $scope"
        elif [ -f "$H/$scope/plan-archived.md" ]; then
            why="$scope is an archived scope of $R: /home $scope starts its home again"
        elif [ "$scope" != uncategorized ] && [ -e "$H/$scope" ]; then
            why="$scope is there already, as $H/$scope, and is no scope"
        fi ;;
    esac
fi
if [ -z "$why" ] && [ "$scope" = uncategorized ]; then
    if [ -n "$prefix" ]; then
        why="uncategorized takes no prefix: it owns every slug no other scope's prefix claims, so put nothing in place of the prefix"
    fi
    if [ -z "$owns" ]; then owns="every row no other scope of $R claims"; fi
elif [ -z "$why" ]; then
    case $prefix in
    '' | *'<'* | *'>'*) why="the slug prefix is not filled in" ;;
    *[!abcdefghijklmnopqrstuvwxyz0123456789-]* | -* | *[!-]) why="the slug prefix $prefix is not lower-case letters and digits that end in a dash, as rs- is" ;;
    *)
        for sent in "$H"/tasks/"$prefix"*.md "$H"/scouts/"$prefix"*.md; do
            if [ -f "$sent" ]; then why="a brief or a request already starts with $prefix: $sent"; fi
        done
        for kept in "$H"/*/prefix; do
            [ -f "$kept" ] || continue
            given=$(awk 'NF {print $(1); exit}' "$kept")
            case $given in
            '') ;;
            "$prefix") why="the slug prefix $prefix is another home's, as $kept says" ;;
            "$prefix"*) why="the slug prefix $prefix is the start of $given, which $kept gives to another home" ;;
            *) case $prefix in "$given"*) why="the slug prefix $prefix starts with $given, which $kept gives to another home" ;; esac ;;
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
    if [ -d "$H/$scope" ]; then had=yes; else had=; fi
    if { [ -n "$had" ] || mkdir "$H/$scope" 2> /dev/null; } &&
        printf '# %s, %s: plan\n\nGoal (%s, the user): %s\n' "$R" "$scope" "$day" "$owns" 2> /dev/null > "$H/$scope/plan.md" &&
        { [ -z "$prefix" ] || printf '%s\n' "$prefix" 2> /dev/null > "$H/$scope/prefix"; }; then
        if [ -n "$prefix" ]; then
            echo "made: scope $scope, with $H/$scope/plan.md and its prefix $prefix in $H/$scope/prefix"
        else
            echo "made: scope $scope, with $H/$scope/plan.md and no prefix: it owns every slug no other scope's prefix claims"
        fi
        printf 'launch: {"title": "home: %s %s", "workspaceStrategy": {"type": "root"}, "message": "/home %s"}\n' "$(printf '%s' "$R" | sed 's/[\\"]/\\&/g')" "$scope" "$scope"
    else
        if [ -n "$had" ]; then
            uv run --project "$T/../source" jbus forget "$H/$scope/plan.md" > /dev/null 2>&1
        else
            uv run --project "$T/../source" jbus forget --dir "$H/$scope/plan.md" "$H/$scope/prefix" "$H/$scope" > /dev/null 2>&1
        fi
        echo "not made: $H/$scope/plan.md or $H/$scope/prefix could not be written, and what was made is taken back. Nothing is written."
    fi
fi
```

On `made:`, the scope has its plan, with the goal as its first line, and its prefix in `$H/<scope>/prefix`: the root home plans no task of that prefix, and that home plans nothing else.
Start its home with `t3_thread_launch`, on `go` from `room`: send what the block printed after `launch: `, as it is.
It starts in the main checkout, as every home does.
A lost reply is looked for by that title, as "Handing a task to a crewmate" says.
Give the user the link.
With no such tool, tell the user to open a new thread in this project and type `/home <scope>`.

On `not made:` nothing is written: tell the user what the line says. A name or a prefix that is taken needs another from them.
For `uncategorized`, put nothing in place of `<prefix>`, and nothing in place of `<what the scope owns>` to have the plan say it owns every row no other scope claims; its directory may be there already, with jbus's files for its rows, and the block keeps them.
