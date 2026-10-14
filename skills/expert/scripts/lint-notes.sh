#!/bin/sh
# Check an expert's notes, with no model: every note has a line in notes/INDEX.md, lists at
# least one source, and each source names the revision it was read at.
# Usage: lint-notes.sh <the expert's folder>
# A note is a `.md` file in the folder's `notes/`, but for `INDEX.md`. Its sources are the
# list items (`- ` or `* `) under its `Sources` heading, each with the lines that carry it on,
# up to the next blank line, item or heading. Any other line under that heading is named: a
# source is a list item.
# A revision is a date written YYYY-MM-DD, or a commit id: 7 to 40 of 0-9 and a-f, a digit
# among them, inside backticks or as the word right after `at`. It is a word of its own,
# outside double quotes, so a date or a number inside a path or a link is none, and neither is
# a bare number. A source has a revision when it names one, or when the note names one for all
# its sources, on a line between its title and the first of its four parts.
# It prints one line for each thing wrong, `<note>: <what>`, and exits 1. A folder in order
# prints nothing and exits 0. A folder with no `notes/` exits 2.
set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: lint-notes.sh <the expert's folder>" >&2
    exit 2
fi
notes=${1}/notes
if [ ! -d "$notes" ]; then
    echo "lint-notes.sh: ${1} has no notes folder" >&2
    exit 2
fi

# The note's name reaches awk by the environment: a `-v` value is read for escape sequences.
wrong=$(for note in "$notes"/*.md; do
    name=${note##*/}
    if [ ! -f "$note" ] || [ "$name" = INDEX.md ]; then continue; fi
    if ! NAME=$name awk '
        {line = $(0); sub(/^[-* ]*/, "", line)}
        index(line, "`" ENVIRON["NAME"] "`: ") == 1 {found = 1}
        END {exit !found}' "$notes/INDEX.md" 2> /dev/null; then
        echo "$name: no line in notes/INDEX.md"
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
