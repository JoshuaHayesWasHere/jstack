**Move the ones a file still has** at the start, before the open ones are shown. A home started before jbus kept the questions wrote them in `$M/gates.md`. This block pipes each open one to jbus and then takes the file out of jbus's sight, so that a gate is listed once, as its question:

```sh
: "${SEP:?run the block that reads jbus first}"
G="$M/gates.md"
if [ ! -s "$G" ]; then
    echo "nothing to move: this home has no gates.md"
else
    awk -v sep="$SEP" '
        function out() { if (open) printf "%s%s%s%s%s\n", n, sep, by, sep, entry; entry = by = ""; open = 0 }
        /^## Gate [0-9]+: / { out(); n = $(3); sub(/:$/, "", n) }
        /^$/ { next }
        /^Status: open$/ { open = 1 }
        /^Asked by: / { by = $(0); sub(/^Asked by: /, "", by); sub(/,.*/, "", by) }
        { entry = entry $(0) "\002" }
        END { out() }' "$G" | {
        kept=0
        while IFS=$SEP read -r n by entry; do
            if [ -z "$by" ] || [ "$by" = home ]; then by=$own; fi
            if [ -n "$WHY" ]; then
                said=$WHY
            elif said=$(printf '%s\n' "$entry" | tr '\002' '\n' | jbus gate "$by" 2>&1); then
                echo "moved: gate $n of $G, $said"
                continue
            else
                said="jbus said: $said"
            fi
            kept=$((kept + 1))
            echo "not moved: gate $n of $G, $said:"
            printf '%s\n' "$entry" | tr '\002' '\n'
        done
        if [ "$kept" != 0 ]; then
            echo "kept: $G, with $kept open that jbus does not hold"
        elif mv "$G" "$M/gates-moved.md"; then
            echo "retired: $G is now $M/gates-moved.md, and jbus reads it no more"
        else
            echo "kept: $G could not be renamed, so jbus still lists its open gates beside their questions"
        fi
    }
fi
```

On `moved: gate <n> of <file>, queued: question <number>`, jbus holds the gate as that question. `already sent` is one jbus held before. On `retired`, every open gate of the file is a question now, and the file has another name: nothing reads it again, and no block writes it. On `not moved`, the gate's own lines are under the line, and the file stays: jbus could not take that one, so it is one of those the end of this section speaks of, shown to the user as text and carried in the handoff's note, whole, under a `## Gate` line.
