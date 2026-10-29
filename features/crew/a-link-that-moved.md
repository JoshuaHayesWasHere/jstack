### A link that moved

A link jbus stacked, a brief with a `Stacked on:` line in its head, is moved by jbus and not by the home.
jbus sends it the line, once for each move: when its base's head moves, naming the branch it sits on, and when its base merged, naming the commit its base merged at once its pull request is based on the default branch.
Such a link sends the home nothing for a conflict: on jbus's message that it is in conflict, it runs the block below at once, with the branch its `Stacked on:` line names while that line names no commit, and otherwise with the commit jbus's last line named.

jbus's line is the only reason a link is rebased, and the base is never this thread's to change.
Run this on it, with the branch the line names in place of the words in angle brackets, or the commit when the line gives one.
It moves the link's own commits onto the new base: the ones above the commit this branch started from.
That commit is the tip of the branch it sat on, or, when that branch was itself moved since, the tip it had before, which git's log of the remote branch still has:

```sh
B="$H/tasks/<slug>.md"
G=$(git rev-parse --git-dir)
was='<the branch it sat on>'
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
elif ! view=$(gh pr view --json baseRefName,headRefOid) || ! base=$(printf %s "$view" | jq -er .baseRefName); then
    echo "could not ask GitHub: no rebase"
elif ! git fetch -q origin "$base"; then
    echo "could not fetch origin/$base: no rebase"
else
    git fetch -q origin "$was" 2> /dev/null
    under=
    if git merge-base --is-ancestor "refs/remotes/origin/$was" HEAD 2> /dev/null; then
        under=$(git rev-parse "refs/remotes/origin/$was")
    elif git rev-parse -q --verify "refs/remotes/origin/$was" > /dev/null; then
        under=$(git merge-base --fork-point "refs/remotes/origin/$was" HEAD)
    elif git merge-base --is-ancestor "$was^{commit}" HEAD 2> /dev/null; then
        under=$(git rev-parse "$was^{commit}")
    fi
    if git merge-base --is-ancestor "origin/$base" HEAD; then
        echo "already on origin/$base: no rebase"
    elif [ -z "$under" ]; then
        echo "not found: the commit this branch started from is not $was, which is gone or was rewritten with no record here: no rebase"
    elif ! git update-ref "refs/jstack/pre-rebase/<slug>/$(git rev-parse --short=12 HEAD)" HEAD; then
        echo "could not keep the head under refs/jstack/pre-rebase: no rebase"
    else
        echo "$(git rev-parse HEAD) $base $(printf %s "$view" | jq -r '.headRefOid // empty')" > "$G/crew-before-rebase"
        if said=$(git rebase -q --onto "origin/$base" "$under" 2>&1); then
            echo "moved from $was onto origin/$base"
        elif [ -d "$G/rebase-merge" ] || [ -d "$G/rebase-apply" ]; then
            echo "the rebase stopped: resolve these, then git rebase --continue"
            git diff --name-only --diff-filter=U
        else
            uv run --project "$T/../source" jbus forget "$G/crew-before-rebase" > /dev/null
            echo "the rebase did not start: no rebase"
            echo "$said"
        fi
    fi
fi
```

The block keeps the head before the move under `refs/jstack/pre-rebase/<slug>/<its first 12 characters>` and writes the same record as "A conflict" does.
On `moved`, or once a rebase that stopped is finished (its generated files made again by the block of "A conflict"), go on as "A conflict" does after its rebase: run its block that looks for dropped lines, run the check command, and push with its push block and no other way.
The Result gets no line and its `Fixed:` line stays as it is.
Against the old base the patch held the changes of the links under this one too, and now it does not, so `jmerge` finds the content changed and the move gets its scoped review, on the message "A conflict" names.
On any line that ends `no rebase`, add what it printed to the Result and end your turn; on `not found`, also tell the home, which sends the commit this branch started from.
As a conflict does, the move waits for a review that is running.
