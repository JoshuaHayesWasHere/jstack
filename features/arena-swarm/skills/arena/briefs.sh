# The briefs of an arena, written and queued: run with sh by step 2 of the arena playbook,
# features/arena-swarm/skills/arena/playbooks/arena.md, which exports slug, entry, size,
# where, priority, scope, have, prompt, rubric, done_when and proves, and H, the home's state
# directory. `have` names the runners the judge and the graft read: `a b`, or after a
# dropout the one runner left.
filled=yes
for said in "$slug" "$entry" "$size" "$where" "$priority" "$have" "$prompt" "$rubric" "$done_when" "$proves"; do
    case $said in '' | '<'*'>' | '- <'*'>') filled= ;; esac
done
indent() { printf '%s\n' "${1}" | sed 's/^/  /'; }
home() { if [ -n "$scope" ]; then echo "Home: $scope"; fi; }
words() {
    sep=
    for r in $have; do
        printf '%s`origin/%s`' "$sep" "$slug-$r"
        sep=' and '
    done
}
reads() {
    printf '`git fetch origin'
    for r in $have; do printf ' %s' "$slug-$r"; done
    printf '`, then each candidate'"'"'s diff from `origin/HEAD`, with its rationale in its Result:'
    for r in $have; do printf ' `%s`' "$H/tasks/$slug-$r.md"; done
}
# The `Builds on:` line of a seat that starts from the runners' work, and the judge's too
# when it is given `judge`: jbus queues a `--depends` only on a row that line names.
builds() {
    printf 'Builds on:'
    sep=' '
    for r in $have; do
        printf '%s%s' "$sep" "$slug-$r"
        sep=', '
    done
    if [ -n "${1}" ]; then printf ', %s-judge' "$slug"; fi
    printf ': the candidates on their branches, with the rationale in their Results'
    if [ -n "${1}" ]; then printf ", and the judge's verdict in its Result"; fi
    printf '\n'
}
runner() {
    cat << EOF
# $slug-${1}: runner ${1} of the arena $slug, made apart from runner ${2}
Task: "Make the artifact below on this branch, apart: another thread makes the same thing, and neither sees the other."
$(indent "$prompt")
Done when:
- the artifact is committed on this branch and pushed to \`origin/$slug-${1}\`, and no pull request is opened
- the check command (\`notes.md\`) passes on it
- the Result names the alternatives it weighed and why each was set aside
Proves it: \`git log origin/$slug-${1} --not origin/HEAD\` lists the candidate's commits, and the check command (\`notes.md\`) passes on them
Size: $size
Where: $where
Design: none, each runner makes the design itself, and the graft row $slug picks between the two
Pull request: none
Review: none
Playbook: none
$(home)
EOF
}
judge() {
    cat << EOF
# $slug-judge: the judge of the arena $slug, read only
Task: "Score the candidates of the arena $slug, $(words), against the rubric below, and recommend a base with its reasons. Commit nothing."
Rubric:
$(indent "$rubric")
Done when:
- the Result marks each criterion held or not held for each candidate, $(words), each with the line of the candidate that shows it
- the Result recommends a base with its reasons
- nothing is committed or pushed, and no pull request is opened
Proves it: \`git ls-remote --heads origin $slug-judge\` prints nothing, and the graft row $slug sets its own scores beside these
Size: S
Where: $where
Design: none, it reads the candidates and makes none
Pull request: none
Review: none
Playbook: none
Read: $(reads)
$(builds)
$(home)
EOF
}
graft() {
    cat << EOF
# $slug: the graft of the arena $slug, one artifact from its candidates
Task: "Make one artifact from the candidates of the arena $slug, $(words): score each against the rubric first, then read the judge's verdict, pick a base, and graft the other's best into it by hand."
$(indent "$prompt")
Rubric:
$(indent "$rubric")
Done when:
- the Result's \`Scores:\` lines mark each criterion held or not held for each candidate, $(words), written before \`$H/tasks/$slug-judge.md\` is read
- the Result names the base and why, the judge's verdict, and where the two differ
- each graft is folded in by hand and named with the candidate it came from, and two candidates of one shape, or one alone, graft nothing and say so
$done_when
- the Result names the runner branches \`$slug-a\` and \`$slug-b\` to remove once this merges
Proves it: $proves
Size: $size
Where: $where
Design: none, the candidates $(words) are the design
Pull request: open one when done
Review: review
Playbook: none
Read: first $(reads); only after the scores are written, the judge's Result in \`$H/tasks/$slug-judge.md\`
$(builds judge)
$(home)
EOF
}
# The head of a brief, and the head as jbus reads it for a brief's sha (`body` in
# features/jbus/src/jbus/queue.py): with no `Home:`, `Thread:` or `Green main:` line, which a home and a
# launch write in.
headof() { awk '/^## / {exit} {print}' "${1}"; }
bare() { grep -v '^Home:\|^Thread:\|^Green main:'; }
# A brief is written when it is not there, kept as it was when its head is the same, and
# written again for a new `have` only while its seat has not started: no Thread: line and
# no Result yet.
put() {
    if [ ! -e "${2}" ]; then
        printf '%s\n' "${1}" > "${2}" && echo "written: ${2##*/}"
    elif [ "$(headof "${2}" | bare)" = "$(printf '%s\n' "${1}" | bare)" ]; then
        echo "as it was: ${2##*/}"
    elif [ "${3}" = again ] && ! grep -q '^Thread:\|^## Result' "${2}"; then
        printf '%s\n' "${1}" > "${2}" && echo "written again: ${2##*/}"
    else
        echo "differs: ${2##*/}"
        return 1
    fi
}
case " $have " in
" a b " | " a " | " b ") picked=yes ;;
*) picked= ;;
esac
if [ -z "$filled" ] || [ -z "$picked" ]; then
    echo "not written: put a value in place of each placeholder, with have as a b, a or b"
elif ! said=$(put "$(runner a b)" "$H/tasks/$slug-a.md" && put "$(runner b a)" "$H/tasks/$slug-b.md" &&
    put "$(judge)" "$H/tasks/$slug-judge.md" again && put "$(graft)" "$H/tasks/$slug.md" again); then
    printf '%s\n' "$said"
    echo "not written: a brief of the arena $slug differs from this frame, or its seat has started"
else
    printf '%s\n' "$said"
    if command -v jbus > /dev/null && jbus plan > /dev/null 2>&1; then
        firsts=
        for r in $have; do firsts="$firsts$slug-$r,"; done
        for row in $(for r in $have; do echo "$slug-$r"; done) "$slug-judge" "$slug"; do
            case $row in
            "$slug-judge") after=${firsts%,} ;;
            "$slug") after="$firsts$slug-judge" ;;
            *) after= ;;
            esac
            printf 'add %s --priority %s --entry %s%s\n--- brief %s\n' "$row" "$priority" "$entry" "${after:+ --depends $after}" "$row"
            headof "$H/tasks/$row.md"
            echo "--- end"
        done | jbus queue apply
    else
        echo "no row: jbus has no plan for this repo, so nothing is queued"
    fi
fi
