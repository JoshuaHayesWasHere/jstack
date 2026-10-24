### A conflict

A default branch that moved is a reason to rebase in two cases only, a conflict or a failure, never staleness.
GitHub says the pull request is `CONFLICTING`.
Or a message from jbus or `jmerge` says its check no longer passes there, `<command> fails on <head> over today's main`.
A check that failed while the base was red is no reason either: once the base has moved since that check started, `jmerge` judges the pull request again over today's base by itself, with its fresh check where the repo has one, and asks GitHub to merge the base into the branch, so no crew waits on it and no home sends a rebase for it by hand.
A default branch that moved on this pull request's files or on any other is no reason by itself: where the repo asks for a fresh check, `jmerge` tests the head over today's main and merges on a pass, and one that ran out of time is queued again, not failed.
Only where `jmerge` can run no fresh check (a guarded pull request, `it needs a rebase`, or a repo with no `fresh-check`) does a message say `main changed <files> after its check started`, because a new check at the rebased head is then the only test of the combined tree.
The rebase is told once for a pull request: a failure after it is not rebased for again, and jbus parks a gate with the default that the pull request waits.

Run this with the block at the top: as it is on jbus's message that the pull request is in conflict, and with `stale` in place of the words in angle brackets on that message. It rebases onto the pull request's base, the default branch. On a conflict it does so when GitHub reports `CONFLICTING`, and does nothing on any other answer. On `stale` it does so whatever GitHub reports, `MERGEABLE` included. It never rebases a link of a stack, a brief with a `Stack:` line in its head, `stale` or not: such a branch holds the commits of the links under it, and this rebase would replay them ("A link that moved").

Every rebase goes on, a third after fixed and green and any after it included: where it changed the reviewed content, `jmerge` waits on a scoped review of the changed range, as the end of this section says.

It never rebases under a review that is running either. A reviewer launched from this thread has a line in the Result, `Reviewer:`, `Second reviewer:` or `Scoped reviewer:` with a thread id, and writes one `## Review` section with a `Head:` line. While the brief has more of those lines than of those sections, the block prints `a review of <head> is running: rebase after its section is written` and does nothing: a rebase would move the head from under the reviewer, whose findings would then name lines of a head that is gone. Run the block again on the message that brings that review's findings.

Before it rebases, the block keeps the head under `refs/jstack/pre-rebase/<slug>/<the head's first 12 characters>`. A worktree shares its refs with the main checkout, so `jmerge` always finds the commit before the rebase there, and `jmerge --sweep` deletes only branches and the gate's refs, so the ref outlives the branch. These refs are never pushed, and they are removed only by hand.

```sh
B="$H/tasks/<slug>.md"
G=$(git rev-parse --git-dir)
why='<conflict or stale>'
reviewing() {
    awk '
        /^## / {result = 1; review = ($(0) == "## Review"); seat = ""; scope = 0}
        review && /^By: .* #[0-9]+$/ {seat = $(NF)}
        review && /^Scope:/ {scope = 1}
        review && /^Head:/ {
            written++
            if (seat != "" && scope) scoped++
            else if (seat != "") {numbered++; wrote[seat] = 1}
            review = 0
        }
        result && /^(Reviewer|Second reviewer|Scoped reviewer): / && !/^[A-Za-z ]+: none/ {
            if ($(1) == "Reviewer:" && $(NF) ~ /^#[0-9]+$/) seats[$(NF)] = 1
            else if ($(1) == "Reviewer:") old++
            else if ($(1) == "Scoped") asked++
            else more++
        }
        END {
            n = filled = 0
            for (one in seats) {n++; if (one in wrote) filled++}
            if (n) exit !(filled < n || asked > scoped || more > numbered - filled)
            exit !(old + asked + more > written)
        }' "$B" 2> /dev/null
}
if [ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ]; then
    echo "the rebase is not finished: resolve these, then git rebase --continue"
    git diff --name-only --diff-filter=U
elif reviewing; then
    echo "a review of $(git rev-parse HEAD) is running: rebase after its section is written"
elif awk '/^## / {exit} /^Stack:/ {found = 1} END {exit !found}' "$B" 2> /dev/null; then
    echo "a link of a stack: no rebase here, the home says when and from which branch"
elif ! view=$(gh pr view --json mergeable,baseRefName,headRefOid); then
    echo "could not ask GitHub: no rebase"
else
    base=$(printf %s "$view" | jq -r .baseRefName)
    pushed=$(printf %s "$view" | jq -r '.headRefOid // empty')
    state=$(printf %s "$view" | jq -r .mergeable)
    if [ "$why" = stale ]; then state=STALE; fi
    case $state in
    MERGEABLE) echo "no conflict: no rebase" ;;
    CONFLICTING | STALE)
        if ! git fetch -q origin "$base"; then
            echo "could not fetch origin/$base: no rebase"
        elif git merge-base --is-ancestor "origin/$base" HEAD; then
            echo "already on origin/$base: no rebase"
        elif ! git update-ref "refs/jstack/pre-rebase/<slug>/$(git rev-parse --short=12 HEAD)" HEAD; then
            echo "could not keep the head under refs/jstack/pre-rebase: no rebase"
        else
            before=$(git rev-parse HEAD)
            echo "$before $base $pushed" > "$G/crew-before-rebase"
            if said=$(git rebase -q "origin/$base" 2>&1); then
                echo "rebased onto origin/$base"
            elif [ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ]; then
                echo "the rebase stopped: resolve these, then git rebase --continue"
                git diff --name-only --diff-filter=U
            else
                rm "$G/crew-before-rebase"
                echo "the rebase did not start: no rebase"
                echo "$said"
            fi
        fi ;;
    *) echo "GitHub has not decided yet: no rebase" ;;
    esac
fi
```

When it says GitHub has not decided, or that it could not ask, fetch, keep the head or start, there is no rebase: say what it printed in the Result and end your turn.
`already on` is a branch that holds the tip of its base: there is nothing to rebase onto.
On `a link of a stack`, do what "A link that moved" says for a conflict.
jbus tells this thread once for each head in conflict, so do not ask again.

The file `crew-before-rebase` in the git directory is the record of a rebase from its start to its push. Its first line is the head before the rebase, the base, and the head the pull request had at GitHub when the rebase started. The push removes the file.

If it stops, resolve the files it names and run `git rebase --continue` until the rebase is finished. A file that a command writes is never resolved by hand. The repo's `notes.md` names each one on a line `Generated: <file> -> <command>`, as jstack's does with `Generated: uv.lock -> uv lock`, and where it has no such line `uv.lock` is made by `uv lock`. Run this each time the rebase stops, with the block at the top. It names the files to resolve by hand first. Once those are resolved and added it takes the base's version of each generated file (during a rebase, `--ours` is the base being rebased onto) and runs its command, so the file is made from what both sides now ask for:

```sh
G=$(git rev-parse --git-dir)
table=$(sed -n 's/^[-* ]*Generated:[[:space:]]*//p' "$H/notes.md" 2> /dev/null | tr -d '`')
if [ -z "$table" ]; then table='uv.lock -> uv lock'; fi
made_by() {
    printf '%s\n' "$table" | awk -v file="${1}" '
        {at = index($(0), " -> ")}
        at && substr($(0), 1, at - 1) == file {print substr($(0), at + 4); found = 1; exit}
        END {exit !found}'
}
if ! [ -d "$G/rebase-merge" ] && ! [ -d "$G/rebase-apply" ]; then
    echo "no rebase is stopped here: nothing to make again"
elif ! cd "$(git rev-parse --show-toplevel)"; then
    echo "could not go to the top of the worktree: nothing made again"
else
    stopped=$(git -c core.quotePath=false diff --name-only --diff-filter=U)
    by_hand=$(printf '%s\n' "$stopped" | while IFS= read -r file; do
        if [ -n "$file" ] && ! made_by "$file" > /dev/null; then echo "$file"; fi
    done)
    if [ -z "$stopped" ]; then
        echo "nothing is left to resolve: git rebase --continue"
    elif [ -n "$by_hand" ]; then
        echo "resolve these by hand and git add them, then run this again:"
        echo "$by_hand"
    else
        printf '%s\n' "$stopped" | while IFS= read -r file; do
            command=$(made_by "$file")
            if git checkout -q --ours -- "$file" && sh -c "$command" > /dev/null 2>&1 && git add -- "$file"; then
                echo "made again: $file, by $command over the base's version"
            else
                echo "not made: $command did not write $file over the base's version, so it is still to resolve"
            fi
        done
    fi
fi
```

On `not made`, run the command yourself and read what it says: the file is still never edited by hand.

Once the rebase is finished, prove that it lost no line, before the check command. Run this. For each file the patch changes, before the rebase or after it, it looks in the head for two sets of lines. The default branch's are the ones it added between where the branch left it before the rebase and where it leaves it now. Its own are the ones the patch added before the rebase. Each must be in the file at the head, unless the other side's diff removes that same line, which is a deletion that was meant. Lines are compared as text with the white space at their end left off, they are counted, so a line that is there once does not stand for two, and blank lines are skipped. It is the rule `jmerge` holds a rebased pull request to:

```sh
G=$(git rev-parse --git-dir)
if [ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ]; then
    echo "the rebase is not finished: resolve, git rebase --continue, then run this again"
elif ! [ -f "$G/crew-before-rebase" ]; then
    echo "no rebase to look through"
else
    read -r before base pushed < "$G/crew-before-rebase"
    old=$(git merge-base "origin/$base" "$before")
    new=$(git merge-base "origin/$base" HEAD)
    lines() { git -c core.quotePath=false diff --no-ext-diff --no-renames -U0 "$@"; }
    files=
    if [ -n "$old" ] && [ -n "$new" ]; then
        files=$({ lines --name-only "$old" "$before" && lines --name-only "$new" HEAD; } | sort -u)
    fi
    lost=$(printf '%s\n' "$files" | while IFS= read -r file; do
        if [ -z "$file" ]; then continue; fi
        {
            lines "$old" "$new" -- "$file"
            printf '\001\n'
            lines "$old" "$before" -- "$file"
            printf '\001\n'
            git show "HEAD:$file" 2> /dev/null
        } | awk -v file="$file" '
            BEGIN {part = 0}
            $(0) == "\001" && part < 2 {part++; hunks = 0; next}
            part < 2 && /^@@/ {hunks = 1; next}
            part < 2 {
                sign = substr($(0), 1, 1)
                line = substr($(0), 2)
                sub(/[ \t\r]+$/, "", line)
                if (!hunks || line == "") next
                if (sign == "+") added[part, line]++
                else if (sign == "-") removed[part, line]++
                next
            }
            {line = $(0); sub(/[ \t\r]+$/, "", line); if (line != "") there[line]++}
            END {
                for (key in added) {
                    split(key, at, SUBSEP)
                    left = added[key] - removed[1 - at[1], at[2]]
                    if (left > there[at[2]]) short[at[1]] += left - there[at[2]]
                }
                if (short[0]) print short[0] " of main\047s lines in " file
                if (short[1]) print short[1] " of its own in " file
            }'
    done | awk '{printf "%s%s", (NR > 1 ? ", " : ""), $(0)} END {if (NR) print ""}')
    if [ -z "$files" ]; then
        echo "could not look: git gave no file the patch changes between origin/$base, $before and the head"
    elif [ -n "$lost" ]; then
        echo "Dropped: $lost"
    else
        echo "Kept: every line, in $(printf '%s\n' "$files" | paste -sd' ' -)"
    fi
fi
```

On `Kept: every line, in <files>`, go on. On `could not look`, nothing is proved: find out why git gave no file (a base that is not fetched, a record that names a commit that is gone), and do not push until the block prints one of the other two. On `Dropped: <k> of main's lines in <file>, <j> of its own in <file>`, the rebase took a line out that neither side meant to. Put the lines back, commit, and run the block again. Where a line is gone on purpose (the task replaces it, or the default branch's change makes it wrong), add one line to the Result for each such file, `Dropped on rebase: <file>, <k> of main's, <j> of its own, at <head12>: <why>`, with the two counts the block printed for that file, `0` for one it did not print, and the first 12 characters of the head you push: the scoped review rules on it. `jmerge` reads the line for the head the pull request is at and no other, so a commit after it (a fix, another rebase) asks for the line again at the new head, and jbus says so in a message here that begins `jbus: the rebase dropped`. A drop with no such line keeps the pull request waiting, one the review upholds merges, and only one it does not uphold goes to the user. Then run the block again, and go on only when every `Dropped` it still prints has its line in the Result. The head before the rebase is `refs/jstack/pre-rebase/<slug>/<its first 12 characters>`, and `git diff <that ref> HEAD -- <file>` shows what the resolution did.

Then run the check command, and push with this. It is the only way a rebased head is pushed, never a bare `git push --force` and never `--force-with-lease` with no commit named. The lease names the head the pull request had at GitHub before the rebase started, read from the record, so a fetch since then cannot widen it:

```sh
G=$(git rev-parse --git-dir)
branch=$(git symbolic-ref -q --short HEAD)
pushed=
if [ -f "$G/crew-before-rebase" ]; then read -r before base pushed < "$G/crew-before-rebase"; fi
if [ -z "$branch" ] || [ -z "$pushed" ]; then
    echo "no push: the head the pull request had before the rebase is not on record here, so there is no lease to push with"
elif git push -q --force-with-lease="refs/heads/$branch:$pushed" --force-if-includes origin "HEAD:refs/heads/$branch"; then
    rm "$G/crew-before-rebase"
    echo "pushed $(git rev-parse HEAD) over $pushed"
else
    echo "the push was refused: origin's $branch is no longer at $pushed, or origin did not answer"
fi
```

On `pushed`, the record is removed. On `the push was refused` or `no push`, nothing was pushed and nothing is forced: somebody else pushed to this branch, or the record is gone. Add what it printed to the Result, park a gate ("Do the task") that asks what to do with the commits on the origin's branch, with the default that the pull request waits, and end your turn.

A rebase adds no line to the Result and changes none.
A `Fixed:` line that names a commit keeps naming the commit it named before the rebase: that commit, or with no such line the head the last review saw, is the one the review covers, and `jmerge` compares the head it finds with it.
A commit made before the push, for the check command or for a line put back, is read with the rebase.

The review stands after a rebase when the rebase left the reviewed content as it was: `jmerge` works out the `git range-diff` between the commit the review covers and the rebased head, and where that is clean no review is started and nothing is asked of this thread. Where it is not, the rebase changed what was reviewed, and jbus says so in a message here: `the rebase changed the content after its review`, with the two ranges of that range-diff. That message, and nothing else, starts one scoped review, of the changed hunks only. Launch one reviewer the way "The review" launches one, with the message `/pr-review run <slug> scoped <old range> <new range>`, add the line `Scoped reviewer: <threadId>` to the Result, and handle its findings as a review's. Until its `## Review` section is written, the first block above does not rebase. A head gets one scoped review: a later rebase gets its own only on its own message, and its `Scoped reviewer:` line is added under the earlier one, which stays: the first block counts every reviewer that was launched. A push for a failed check made after a review saw an older head is ruled on the same way: its `CI fix:` line ("The checks") has `jmerge` compare the two heads, a clean range-diff carries the review over, and one that is not brings the same message here, which starts the one scoped review. A failing push before any review starts nothing more than the reviewer the pull request was still owed.

A task is not stacked on another task's branch. One that needs another task's change waits for that pull request to merge and starts from the default branch: a stacked branch conflicts as soon as its base is squash-merged, and that is a rebase nobody needed. There is one exception, in the user's words: "take it as written, and allow a stack for this one playbook". It is the home's playbook `autopilot-stack`, and a crewmate sees it only as a `Stack:` line in the head of its brief.
