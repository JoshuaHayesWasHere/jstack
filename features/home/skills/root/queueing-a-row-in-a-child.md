## Queueing a row in a child

The root queues every row in a child, and none of its own.
A brief or a request goes to the child whose goal it serves, or to `uncategorized`, and its `Home:` line names that child.
The entry's go approves the row as it is queued, the root's own on the user's standing word or the user's ("Give an entry its go").
Where the user's own message asks for this row, `--message` binds it too, as `jbus queue approve --message` does.
Where no message of the user's asks for it, put `none` in place of the message.
In one call with the block at the top and the block that finds this home, in the main checkout, with `tasks` for a brief or `scouts` for a request, its slug, the child, a priority, the plan entry and the user's message or `none` in place of the words in angle brackets, and the row's order added as `--depends <slugs>` or `--merge-after <slugs>` ("Handing a task to a crewmate", step 1):

```sh
kind='<tasks or scouts>'
slug='<slug>'
child='<child>'
priority='<n>'
entry='<entry>'
message='<thread id>/last'
case $kind in
tasks) B="$H/tasks/$slug.md" ;;
scouts) B="$H/scouts/$slug.md" ;;
*) B= ;;
esac
why=
if [ "${M:?run the block that finds this home first}" != "$H" ]; then
    why="this is the home of the scope $(basename "$M"): a child queues its own rows by \"Handing a task to a crewmate\""
fi
if [ -z "$why" ]; then
    case $kind/$slug/$child/$priority/$entry/$message in
    *'<'* | *'>'*) why="the kind, the slug, the child, the priority, the entry or the user's message is not filled in" ;;
    esac
fi
if [ -z "$why" ]; then
    case $kind in tasks | scouts) ;; *) why="$kind is neither tasks nor scouts" ;; esac
    case $child in
    '' | root) why="the root queues no row of its own: name the child whose goal the row serves, or uncategorized" ;;
    *) [ -f "$H/$child/plan.md" ] || why="$child is no child home of $R: there is no $H/$child/plan.md" ;;
    esac
    case $message in
    none | ?*/?*) ;;
    *) why="$message is not the user's message as <thread id>/last or <thread id>/<message id>, or none" ;;
    esac
fi
if [ -z "$why" ]; then
    named=$(awk '/^Home:/ {print $(2); exit}' "$B" 2> /dev/null)
    if [ ! -f "$B" ]; then
        why="there is no $B"
    elif [ "$named" != "$child" ]; then
        why="$B has Home: ${named:-nothing}, not $child: write Home: $child in it"
    fi
fi
if [ -n "$why" ]; then
    echo "not queued: $why. Nothing is queued."
elif ! command -v jbus > /dev/null || ! jbus plan > /dev/null 2>&1; then
    echo "no plan: jbus holds no plan of this repo, so nothing is queued"
elif [ "$message" = none ] && said=$(jbus queue add "$slug" --priority "$priority" --entry "$entry" --from "$ME" --for "$child" < "$B" 2>&1); then
    echo "queued: the row $slug, in $child, on the go of the entry $entry"
elif [ "$message" != none ] && said=$(jbus queue add "$slug" --priority "$priority" --entry "$entry" --from "$ME" --for "$child" --message "$message" < "$B" 2>&1); then
    echo "queued: the row $slug, in $child, approved on $message"
else
    printf '%s\n' "$said"
fi
```

On `queued:`, the row is the child's: jbus's pass launches it once its go holds, and the root sends the child nothing.
A row whose entry has no go waits: give the entry its go, or ask the user where only they can give it.
On `not queued:` nothing is queued: mend what the line names and run it again.
On `no plan:` the repo is not on jbus: "On the bus" ("When a home starts") adds it.
On `refused:`, mend the brief as the lines under it say, and run it again.
`<entry>` is an entry of the child's plan, or of the root's plan for `uncategorized`, the plan whose go approves the row: `add` refuses an entry that plan does not have, and the line lists its open entries.
