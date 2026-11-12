### A conflict

A default branch that moved is a reason to rebase in one case only, a conflict, never staleness and never a failure by itself.
GitHub says the pull request is `CONFLICTING`, or jbus's message says it is in conflict with its base.
A failed check after GitHub merged the base into the branch comes as any failure does, `jbus: <check> failed on your pull request`, and "The checks" handles it.
A check that failed while the base was red is no reason either: once the base has moved since that check started, `jmerge` judges the pull request again over today's base by itself, and asks GitHub to merge the base into the branch, so no crew waits on it and no home sends a rebase for it by hand.
A default branch that moved, on this pull request's files or on any other, is no reason by itself: when the head merges cleanly over today's main, `jmerge` has GitHub merge main into the branch, and the check at the new head decides.
The rebase is told once for a pull request: a failure after it is not rebased for again, and jbus parks a gate with the default that the pull request waits.

Run this with the block at the top: as it is on jbus's message that the pull request is in conflict, and with `stale` in place of the words in angle brackets on jbus's rebase message, `jbus: <default> moved under your pull request #<n> (<reason>)`, whose reason is no conflict.
Only a wait line of an older `jmerge`, that main changed after the check started, still brings that one (`jmerge.ready.MAIN_CHANGED`, `jbus.rebase.STALE`).
It rebases onto the pull request's base, the default branch.
On a conflict it does so when GitHub reports `CONFLICTING`, and does nothing on any other answer.
On `stale` it does so whatever GitHub reports, `MERGEABLE` included.
It never rebases a link jbus stacked, a brief with a `Stacked on:` line in its head, `stale` or not, until its line says the commit its base merged as and the head holds it: until then its branch holds its base's commits too, and this rebase would replay them ("A link that moved").

Every rebase goes on, a third after fixed and green and any after it included: a rebase gets no scoped review, since its checks verify it, as the end of this section says.

It never rebases under a review that is running either.
A reviewer launched from this thread has a line in the Result, `Reviewer:`, `Second reviewer:` or `Scoped reviewer:` with a thread id, and writes one `## Review` section with a `Head:` line.
While one of those lines has no such section written after it, of its seat (`#<n>`) where the line has one, the block prints `a review of <head> is running: rebase after its section is written` and does nothing: a rebase would move the head from under the reviewer, whose findings would then name lines of a head that is gone.
`jbriefs line reviewing` reads it, by the rule jbus waits on before it moves a head (`jbriefs.reviewers.running`).
Run the block again on the message that brings that review's findings.

Before it rebases, the block keeps the head under `refs/jstack/pre-rebase/<slug>/<the head's first 12 characters>`. A worktree shares its refs with the main checkout, so `jmerge` always finds the commit before the rebase there, and `jmerge --sweep` deletes only branches and the gate's refs, so the ref outlives the branch. These refs are never pushed, and they are removed only by hand.

```sh
B="$H/tasks/<slug>.md"
G=$(git rev-parse --git-dir)
why='<conflict or stale>'
reviewing() {
    [ "$(uv run --project "$T/../source" jbriefs line reviewing "$B" 2> /dev/null)" = yes ]
}
if [ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ]; then
    echo "the rebase is not finished: resolve these, then git rebase --continue"
    git diff --name-only --diff-filter=U
elif reviewing; then
    echo "a review of $(git rev-parse HEAD) is running: rebase after its section is written"
elif stacked=$(uv run --project "$T/../source" jbriefs line stacked "$B" 2> /dev/null) && [ "$stacked" != none ] && { [ "${stacked% at *}" = "$stacked" ] || ! git merge-base --is-ancestor "${stacked##* }" HEAD 2> /dev/null; }; then
    echo "a link of a stack: no rebase here, jbus stacked it and says when it moves"
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
                uv run --project "$T/../source" jbus forget "$G/crew-before-rebase" > /dev/null
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

If it stops, resolve the files it names and run `git rebase --continue` until the rebase is finished.
A file that a command writes is never resolved by hand.
The repo's `[[project]]` table in jbus's config names each one in its key `generated`, as `generated = ["uv.lock -> uv lock"]`, and where it names none `uv.lock` is made by `uv lock`.
Run this each time the rebase stops, with the block at the top.
It names the files to resolve by hand first.
Once those are resolved and added it takes the base's version of each generated file (during a rebase, `--ours` is the base being rebased onto) and runs its command, so the file is made from what both sides now ask for:

```sh
uv run --project "$T/../source" jmerge --remake
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

Then check the rebased head with the guard tests and the lint, and push it: the check block of "Do the task" is no condition of this push.
CI runs the whole check at the pushed head, as it does for any push, and a failure there comes as `jbus: <check> failed on your pull request`, which "The checks" handles.
#1729 merged main five times and pushed none of them: each run of the whole block took 30 minutes, main moved meanwhile, and the pull request was in conflict again by its end.
A conflict repaired in a push that CI then checks costs one CI run; one repaired after the whole block at the desk costs the block, and a busy main outruns it.
In a repo whose check selects its tests (`scripts/select_tests.py`), run this in this worktree with the block at the top and this thread's id and the brief's slug in place of the words in angle brackets.
It runs `make check-fast BASE=<the fork> PART=guards`, the lint and the guard tests, in a full test slot, and writes its `Checked:` line:

```sh
B="$H/tasks/<slug>.md"
G=$(git rev-parse --git-dir)
head=$(git rev-parse HEAD)
if [ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ]; then
    echo "the rebase is not finished: resolve, git rebase --continue, then run this again"
elif [ -n "$(git status --porcelain)" ]; then
    echo "no check: commit the resolution first"
elif [ ! -f scripts/select_tests.py ]; then
    echo "no light check: this repo's check selects no tests, so run the check block of \"Do the task\""
else
    on=$(uv run --project "$T/../source" jbriefs line base "$B" 2> /dev/null)
    [ "$on" != none ] || on=
    on=origin/${on:-main}
    git rev-parse -q --verify "$on^{commit}" > /dev/null || on=origin/main
    if ! base=$(git merge-base "$on" HEAD); then
        echo "no check: the branch shares no commit with $on"
    else
        uv run --project "$T/../source" jgauge test-slot --thread '<thread id>' -- make check-fast BASE="$base" PART=guards
        ran=$?
        if [ "$ran" = 76 ]; then
            echo "waiting: every full test slot is taken"
        elif [ -n "$(git status --porcelain)" ] || [ "$(git rev-parse HEAD)" != "$head" ]; then
            echo "no line: the worktree moved off $head while the check ran: run this again"
        else
            printf 'Checked: make check-fast BASE=%s PART=guards exit %s at %s\n' "$base" "$ran" "$head" >> "$B"
            if [ "$ran" = 0 ]; then
                echo "checked: the guards and the lint passed at $head"
            else
                echo "failed: the guards and the lint exited $ran at $head"
            fi
        fi
    fi
fi
```

Give the call a time limit of 10 minutes (`timeout: 600000` in Claude Code), and never send it to the background.
On `checked`, push with the block below.
On `waiting`, end the turn as "test slots" says for a full slot, and on jbus's message run this block again.
On `failed`, the rebase or the change broke a guard or the lint: fix it and commit, run the check block of "Do the task" at the new head, since a commit of your own is more than the base, and then push with the block below.
On `no light check`, run the check block of "Do the task", and push once it passes.
jleak's `pre-push` hook takes the `PART=guards` line for this head and no other: the head's one change over the head of the brief's last line of the whole check must be the base it now sits on, the same commits of its own over a later fork, whether a rebase or a merge of the base made it (`jleak.crewpush.only_the_base`).
A head with a commit more, a fix pushed with the rebase included, is refused with `crew-push: refused: its last Checked: line, the guards and the lint at <head12>, binds only a merge of <base> over <head12> ...`, and wants the check block of "Do the task".

Push with this. It is the only way a rebased head is pushed, never a bare `git push --force` and never `--force-with-lease` with no commit named. The lease names the head the pull request had at GitHub before the rebase started, read from the record, so a fetch since then cannot widen it:

```sh
G=$(git rev-parse --git-dir)
branch=$(git symbolic-ref -q --short HEAD)
pushed=
if [ -f "$G/crew-before-rebase" ]; then read -r before base pushed < "$G/crew-before-rebase"; fi
if [ -z "$branch" ] || [ -z "$pushed" ]; then
    echo "no push: the head the pull request had before the rebase is not on record here, so there is no lease to push with"
elif git push -q --force-with-lease="refs/heads/$branch:$pushed" --force-if-includes origin "HEAD:refs/heads/$branch"; then
    uv run --project "$T/../source" jbus forget "$G/crew-before-rebase" > /dev/null
    echo "pushed $(git rev-parse HEAD) over $pushed"
else
    echo "the push was refused: origin's $branch is no longer at $pushed, or origin did not answer"
fi
```

On `pushed`, the record is removed. On `the push was refused` or `no push`, nothing was pushed and nothing is forced: somebody else pushed to this branch, or the record is gone. Add what it printed to the Result, park a gate ("Do the task") that asks what to do with the commits on the origin's branch, with the default that the pull request waits, and end your turn.

A rebase adds no line to the Result and changes none.
A `Fixed:` line that names a commit keeps naming the commit it named before the rebase: that commit, or with no such line the head the last review saw, is the one the review covers, and `jmerge` compares the head it finds with it.
A commit made before the push, for a failed guard or for a line put back, is read with the rebase.

The review stands after a rebase: `jmerge` works out the `git range-diff` between the commit the review covers and the rebased head, and where that is clean it carries the review over.
Where the rebase changed the content, the review is kept all the same, since the pull request's checks verify a rebase: no review is started and nothing is asked of this thread.
The pull request still waits on its `Proved:` and `Checked:` lines at the rebased head, and on a `Dropped on rebase` line for a line the rebase lost.
A rebase is a head that does not descend from the one the review covers, has as many commits of its own and changes every file the reviewed patch changes ("After a rebase" in `features/jmerge/docs/jmerge.md`).
A commit pushed with the rebase makes it a push, and a push, on the reviewed head or over a merge of main, keeps the review only where its patch differs in tests, docs or config alone.
Any other push, and a head whose patches git cannot compare, waits on one scoped review of the changed hunks only.
jbus launches that reviewer itself, in this worktree, with `/pr-review run <slug> scoped <old range> <new range>`, and adds its `Scoped reviewer:` line, of the rebased head, to the Result: launch nothing, and write no such line for it, unless a later message from jbus asks you to, as it does where it could not launch one.
This thread hears of it once its `## Review` is written, in a message that lists its findings by id, and hears nothing of one that is clean; handle the findings as a review's.
Until its `## Review` section is written, the first block above does not rebase.
A head gets one scoped review: a later push that changes code gets its own, and its `Scoped reviewer:` line goes under the earlier one, which stays: the first block counts every reviewer that was launched.
A push for a failed check made after a review saw an older head is ruled on the same way, with no line in the Result ("The checks"): `jmerge` compares the two heads, a clean range-diff or a patch that differs in tests, docs or config alone keeps the review, and any other gets the same one scoped review from jbus.
A failing push before any review starts nothing more than the reviewer the pull request was still owed.

A task is stacked on another task's branch in one case only, and a crewmate sees it as a line in the head of its brief.
A row that builds on another row's code launches once that row opened its pull request, on its branch: jbus writes its `Stacked on:` line, and only once its base merged moves it, or tells it once to rebase with "A link that moved".
