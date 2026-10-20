# Arena

Run by: the home, for one artifact (a design, an interface, a piece of code or of text) where a single attempt would lock in the wrong shape.

Source: pstack, `pstack/skills/arena/SKILL.md`

<!-- card: Fan out to threads | 1 | One artifact where a single attempt would lock in the wrong shape. Two runner crews make it apart, a judge crew scores both, and a graft crew picks a base and grafts the other's best into it. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own.
A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo.
Read a principle in full when a step you are doing names it.

**You own the frame, never the artifact**, and every seat is a crewmate of its own, a T3 thread with its brief in `$H/tasks/`, launched by jbus from its queue row: two runners, one judge and one graft.
Each is a thread the user can open, and its brief and Result outlast it.
No seat is a subagent.

1. Frame it.
   Write the one prompt both runners get, word for word the same: the artifact to make and what it is for.
   The prompt is the contract.
   Then write the rubric, three to six criteria that can be graded on this task, each a line that can be marked held or not held (`principles/principle-exhaust-the-design-space.md`).
   The rubric goes to the judge and the graft, never to a runner.
2. Write the four briefs and queue their rows with the block below, run with the block at the top.
   Put the arena's slug, its plan entry, its size, the paths the artifact is in, a priority, the prompt, the rubric, the entry's own **Done when** lines and its `Proves it:` line in place of the words in angle brackets.
   A scoped home puts its scope on the `scope=` line, and the root home leaves it empty.
3. Approve the four rows, each on the user's word that asked for this arena, as "The user's word, carried by jbus" in `skills/home/SKILL.md` says.
   jbus launches each row when its `--depends` are met: the two runners at once, the judge once both runners ended `done` with no pull request, the graft once all three did.
4. Drain as for any crewmate ("When a thread sends a message").
   A runner that ends with no candidate is a dropout: queue the judge and the graft again with `--depends` on the other runner alone, approve both again, and send the graft's thread nothing, since it has not started.
   Both runners with no candidate mean step 1 was too loose: frame it again under a new slug.
5. Close by the graft's Result.
   It names the base and why, the judge's verdict and where it differed, each graft with its candidate, and the runner branches to remove once it merged.
   Tell the user those in at most five lines when it merges.

```sh
slug='<the arena slug>'
entry='<the plan entry>'
size='<S, M, L or XL>'
where='<the paths the artifact is in, each in backticks>'
priority='<n>'
scope=''
prompt=$(cat << 'THE_PROMPT_ENDS_HERE'
<the one prompt both runners get>
THE_PROMPT_ENDS_HERE
)
rubric=$(cat << 'THE_RUBRIC_ENDS_HERE'
- <a criterion that can be marked held or not held>
THE_RUBRIC_ENDS_HERE
)
done_when=$(cat << 'THE_DONE_ENDS_HERE'
- <a line of the entry's Done when>
THE_DONE_ENDS_HERE
)
proves='<the entry Proves it line>'
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
```

It writes the four briefs, then queues their rows in one batch, all four or none.
On `refused:`, nothing is queued: mend the frame, delete the four briefs, and run it again.
On `no row`, launch the runners by "Handing a task to a crewmate", and each later seat when the ones it depends on ended.

Never done here, and who does it:

- **A seat run as a subagent**: nobody does, since every seat is a crewmate, so its work and its reasons stay on disk.
- **A third runner or a second judge**: nobody does, since there are two runners and one judge.
  A task that needs more directions is two arenas.
- **The rubric shown to a runner**: nobody does, since it is on the judge's and the graft's briefs only.
- **The judge's pick taken unread**: the graft scores both before it reads the judge's Result, as its first **Done when** line says.
- **A pull request from a runner or the judge**: nobody opens one, since the graft's is the arena's one pull request.
- **Writing, reading or landing the artifact**: the crewmates write and read it, and `jmerge` merges the graft's pull request.

**Hand over:** in this thread, to the user, when the graft merges: the rubric, the base and why, the judge's verdict and where it differed, each graft with its candidate, any dropout or agreement, and the runner branches left to remove.
