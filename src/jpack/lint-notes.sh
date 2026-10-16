#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: lint-notes.sh <the expert's folder, or a context pack>" >&2
    exit 2
fi
notes=${1}/notes
if [ ! -d "$notes" ]; then
    echo "lint-notes.sh: ${1} has no notes folder" >&2
    exit 2
fi
index=notes/INDEX.md
if [ ! -f "${1}/$index" ] && [ -f "${1}/INDEX.md" ]; then index=INDEX.md; fi

wrong=$(if [ "$index" = INDEX.md ] && [ "$(grep -c . "${1}/INDEX.md")" -gt 40 ]; then
    echo "INDEX.md: $(grep -c . "${1}/INDEX.md") lines that are not blank, a pack's index is at most 40"
fi
for note in "$notes"/*.md; do
    name=${note##*/}
    if [ ! -f "$note" ] || [ "$name" = INDEX.md ]; then continue; fi
    if ! NAME=$name awk '
        {line = $(0); sub(/^[-* ]*/, "", line)}
        index(line, "`" ENVIRON["NAME"] "`: ") == 1 {found = 1}
        END {exit !found}' "${1}/$index" 2> /dev/null; then
        echo "$name: no line in $index"
    fi
    NAME=$name awk '
        function revised(text,    words, word, i, bare, lead, ticks, ticked, after) {
            gsub(/"[^"]*"/, " ", text)
            words = split(text, word, /[ \t]+/)
            for (i = 1; i <= words; i++) {
                bare = word[i]
                gsub(/^[^0-9A-Za-z]+|[^0-9A-Za-z]+$/, "", bare)
                if (bare ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]$/) return 1
                lead = word[i]
                sub(/[0-9A-Za-z].*$/, "", lead)
                ticked = (ticks + gsub(/`/, "", lead)) % 2
                ticks += gsub(/`/, "", word[i])
                if ((ticked || after) && length(bare) >= 7 && length(bare) <= 40 && bare ~ /^[0-9a-f]+$/ && bare ~ /[0-9]/) return 1
                after = (bare == "at")
            }
            return 0
        }
        function close_item() {
            if (item != "" && !stated && !revised(item)) print ENVIRON["NAME"] ": a source with no revision, in it or above the four parts (a commit id in backticks or after at, or a date as YYYY-MM-DD): " first
            item = ""
        }
        /^```/ {fenced = !fenced; next}
        fenced {next}
        {part = $(0); sub(/^#* */, "", part); sub(/[ \t\r]+$/, "", part)}
        part ~ /^(Answer|Sources|Confidence|Not checked)$/ {close_item(); parts = 1; inside = (part == "Sources"); next}
        /^#/ {close_item(); inside = 0; next}
        !parts && revised($(0)) {stated = 1}
        !inside {next}
        /^[-*] / {close_item(); sources++; item = first = $(0); next}
        !NF {close_item(); next}
        item != "" {item = item " " $(0); next}
        {print ENVIRON["NAME"] ": a line under Sources that is no list item (- or *): " $(0)}
        END {
            close_item()
            if (!sources) print ENVIRON["NAME"] ": no source, no list item (- or *) is under a Sources heading"
        }' "$note"
done)

if [ -n "$wrong" ]; then
    printf '%s\n' "$wrong"
    exit 1
fi
