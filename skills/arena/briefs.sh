# The four briefs of an arena, written and queued: sourced by step 2 of playbooks/arena.md,
# after the lines that set slug, entry, size, where, priority, scope, prompt, rubric,
# done_when and proves, with H set to the home's state directory.
filled=yes
for said in "$slug" "$entry" "$size" "$where" "$priority" "$prompt" "$rubric" "$done_when" "$proves"; do
    case $said in '' | '<'*'>' | '- <'*'>') filled= ;; esac
done
indent() { printf '%s\n' "${1}" | sed 's/^/  /'; }
home() { if [ -n "$scope" ]; then echo "Home: $scope"; fi; }
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
Task: "Score the two candidates of the arena $slug against the rubric below, and recommend a base, a or b, with its reasons. Commit nothing."
Rubric:
$(indent "$rubric")
Done when:
- the Result marks each criterion held or not held for a and for b, each with the line of the candidate that shows it
- the Result recommends a base, a or b, with its reasons
- nothing is committed or pushed, and no pull request is opened
Proves it: \`git ls-remote --heads origin $slug-judge\` prints nothing, and the graft row $slug sets its own scores beside these
Size: S
Where: $where
Design: none, it reads two candidates and makes none
Pull request: none
Review: none
Playbook: none
Read: \`git fetch origin $slug-a $slug-b\`, then \`git diff origin/HEAD...origin/$slug-a\` and \`git diff origin/HEAD...origin/$slug-b\`; each runner's rationale is in its Result, \`$H/tasks/$slug-a.md\` and \`$H/tasks/$slug-b.md\`
$(home)
EOF
}
graft() {
    cat << EOF
# $slug: the graft of the arena $slug, one artifact from two candidates
Task: "Make one artifact from the two candidates of the arena $slug: score both against the rubric first, then read the judge's verdict, pick a base, and graft the other's best into it by hand."
$(indent "$prompt")
Rubric:
$(indent "$rubric")
Done when:
- the Result's \`Scores:\` lines mark each criterion held or not held for a and for b, written before \`$H/tasks/$slug-judge.md\` is read
- the Result names the base and why, the judge's verdict, and where the two differ
- each graft is folded in by hand and named with the candidate it came from, and two candidates of one shape graft nothing and say so
$done_when
- the Result names the branches \`$slug-a\` and \`$slug-b\` to remove once this merges
Proves it: $proves
Size: $size
Where: $where
Design: none, the two candidates on \`origin/$slug-a\` and \`origin/$slug-b\` are the design
Pull request: open one when done
Review: review
Playbook: none
Read: first \`git fetch origin $slug-a $slug-b\` and each candidate's diff from \`origin/HEAD\`, with its rationale in \`$H/tasks/$slug-a.md\` and \`$H/tasks/$slug-b.md\`; only after the scores are written, the judge's Result in \`$H/tasks/$slug-judge.md\`
$(home)
EOF
}
if [ -z "$filled" ]; then
    echo "not written: put a value in place of each placeholder"
elif [ -e "$H/tasks/$slug.md" ] || [ -e "$H/tasks/$slug-a.md" ] || [ -e "$H/tasks/$slug-b.md" ] || [ -e "$H/tasks/$slug-judge.md" ]; then
    echo "not written: $H/tasks already has a brief of the arena $slug"
else
    runner a b > "$H/tasks/$slug-a.md"
    runner b a > "$H/tasks/$slug-b.md"
    judge > "$H/tasks/$slug-judge.md"
    graft > "$H/tasks/$slug.md"
    echo "written: $slug-a, $slug-b, $slug-judge and $slug in $H/tasks"
    if command -v jbus > /dev/null && jbus plan > /dev/null 2>&1; then
        for row in "$slug-a" "$slug-b" "$slug-judge" "$slug"; do
            case $row in
            "$slug-judge") after="$slug-a,$slug-b" ;;
            "$slug") after="$slug-a,$slug-b,$slug-judge" ;;
            *) after= ;;
            esac
            printf 'add %s --priority %s --entry %s%s\n--- brief %s\n' "$row" "$priority" "$entry" "${after:+ --depends $after}" "$row"
            cat "$H/tasks/$row.md"
            echo "--- end"
        done | jbus queue apply
    else
        echo "no row: jbus has no plan for this repo, so nothing is queued"
    fi
fi
