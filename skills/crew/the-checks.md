### The checks

Whether a pull request's checks have passed is never read off a message or remembered: it is what this prints, run in this worktree with the block at the top. It is the only check:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
checks() {
    view=$(gh pr view ${1:+"${1}"} --json headRefOid,statusCheckRollup) || { echo "wait: could not ask GitHub"; return; }
    never=$(printf '%s\n' "$view" |
        jq -r '.statusCheckRollup[]? | select(.status == "COMPLETED" and (.conclusion | IN("SUCCESS", "NEUTRAL", "SKIPPED") | not)) | .detailsUrl // empty' |
        sed -n 's|^https://[^/]*/\([^/]*/[^/]*\)/actions/runs/[0-9]*/job/\([0-9]*\)$|& \1 \2|p' |
        while read -r url repo job; do
            if gh api "repos/$repo/actions/jobs/$job" | jq -e '.steps | type == "array" and length == 0' > /dev/null; then echo "$url"; fi
        done)
    printf '%s\n' "$view" | jq -r --arg never "$never" '
        def when: [.startedAt, .completedAt] | map(if (. // "") == "" or startswith("0001-") then "~" else . end);
        ($never | split("\n")) as $never
        | [.statusCheckRollup // [] | group_by(.name // .context)[] | (map(when) | max) as $last | .[] | select(when == $last) |
            if .state then (if .state == "SUCCESS" then "passed" elif (.state | IN("PENDING", "EXPECTED")) then "pending" else "failed" end)
            elif .status != "COMPLETED" then "pending"
            elif (.conclusion | IN("SUCCESS", "NEUTRAL")) then "passed"
            elif .conclusion == "SKIPPED" then "skipped"
            elif (.detailsUrl // "" | IN($never[])) then "unstarted"
            else "failed" end] as $each
        | if ($each | length) == 0 then "wait: no check is reported yet"
          elif ($each | index("failed")) then "failed: a check ran and failed"
          elif ($each | index("pending")) then "wait: a check has not finished"
          elif ($each | index("passed") | not) then "unrun: no check ran at \(.headRefOid)"
          elif ($each | index("unstarted")) then "failed: a check never started beside checks that ran"
          else "passed: every check passed at \(.headRefOid)" end'
}
checks
```

Its first word is one of four answers:

- `passed`: every check passed. The pull request is green.
- `failed`: a check ran and failed. Run the check command in this worktree (`notes.md` names it) with the block of "Do the task" that runs it, until it prints `done`, in this turn. On `waiting`, stop as "Do the task" says. Then run the block of "A failed check" below, and do what its first word says.
- `wait`: a check is still running, none is reported yet, or GitHub could not be asked. End your turn: jbus sends this thread a message when a check ran and failed at this head, or, where the home is owed a line on green, when every check passed.
- `unrun`: no check ran. Every check either failed with no step run or was skipped, which is a repo whose CI starts no job (no runner, a failed payment), and nothing a push repairs. It is not green, and nothing stands in for a check that did not run: the check command passing in this worktree does not, and no line in the Result does. If the Result has no `Unrun:` line for this head, add `Unrun: at <head>, no check ran` and park a gate ("Do the task") that says `no check ran at <head>` and asks what to do, with the default that the pull request waits. Launch no reviewer and send no `fixed and green` line. Then end your turn: the gate's answer wakes this thread, or jbus's message when a check runs and fails.

**Green**, everywhere in this skill, is `passed` and nothing else. `checks` is the pr-review skill's function too: change it in both, and the tests run each copy over the same rollups. A failed check whose job GitHub will not give counts as one that ran. A check run more than once at the head, one cancelled and run again included, counts by its latest run, the one that started last: `jmerge` reads it the same way. The merge is stricter still, and goes by one check: `jmerge` merges only when the check named `check` passed at the head, whatever the other checks say.

**A failed check** is the change's own, a base that moved, or a flake, and this says which. Run it in this worktree with the block at the top, after the check command, with what the check command did here in place of the words in angle brackets, `failed` or `passed`:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
B="$H/tasks/<slug>.md"
here='<failed or passed>'
if [ "$here" != failed ] && [ "$here" != passed ]; then
    echo "wait: run the check command in this worktree first, and set here to failed or passed"
elif ! view=$(gh pr view --json headRefOid,baseRefName,statusCheckRollup); then
    echo "wait: could not ask GitHub"
else
    head=$(printf %s "$view" | jq -r .headRefOid)
    base=$(printf %s "$view" | jq -r .baseRefName)
    runs=$(printf %s "$view" |
        jq -r '.statusCheckRollup[]? | select(.status == "COMPLETED" and (.conclusion | IN("SUCCESS", "NEUTRAL", "SKIPPED") | not)) | .detailsUrl // empty' |
        sed -n 's|^https://[^/]*/[^/]*/[^/]*/actions/runs/\([0-9]*\)/job/[0-9]*$|\1|p' | sort -u | paste -sd' ' -)
    if [ "$(git rev-parse HEAD)" != "$head" ] || [ -n "$(git status --porcelain)" ]; then
        echo "wait: this worktree is not at the pushed head $head with nothing uncommitted, so the check command did not run on what failed: commit and push"
    elif [ "$here" = failed ]; then
        echo "fix: the check command fails here at $head, so the failure is the change's own"
    elif ! git fetch -q origin "$base"; then
        echo "wait: could not fetch origin/$base"
    elif ! git merge-base --is-ancestor "origin/$base" HEAD; then
        echo "stale: the check command passes here at $head, and the branch does not hold the tip of origin/$base: no rerun, no commit, no rebase"
    elif grep -q "^Rerun: at $head," "$B"; then
        echo "stuck: a fresh run at $head failed again while the check command passes here: not a flake, no second rerun"
    elif [ -z "$runs" ]; then
        echo "stuck: the failed check at $head is not a workflow run, so there is nothing to run again"
    else
        started=
        for run in $runs; do
            if gh run rerun "$run" > /dev/null 2>&1; then started="${started:+$started }$run"; fi
        done
        if [ -n "$started" ]; then
            line="Rerun: at $head, workflow run $started was run again whole"
            if { { [ -z "$(tail -c1 "$B")" ] || echo >> "$B"; } && echo "$line" >> "$B"; } 2> /dev/null; then
                echo "rerun: workflow run $started is started again, whole, and the brief has the line $line"
            else
                echo "wait: workflow run $started is started again, and the brief could not be written: add the line $line"
            fi
        else
            echo "wait: gh run rerun did not start workflow run $runs again"
        fi
    fi
fi
```

Its first word is one of five answers. After each, end your turn.

- `fix`: the failure is in the pull request's own change. Only this one gets a commit: fix it, run the check command, push, and add one line to the Result saying what failed and what you did. Then go by what has reviewed the pull request. Where the block of "The review" prints `launch a reviewer`, launch it now, on the push. Where the brief has a `## Review` section and the Result no `Fixed:` line that names a commit, add `CI fix: <the head you pushed>, after the review of <the Head: of the last ## Review section>`, both commits in full, one line for each such push: `jmerge` compares the two heads by `git range-diff`, and the review carries over or one scoped review is asked for ("A conflict"). Where a reviewer is launched and its section is not written yet, the line is owed once the section is, if its `Head:` is not the head you pushed: add it on the message that brings the findings when nothing is pushed for them.
- `stale`: the change passes here, and the default branch moved under it. CI tests the merge with the base, so no commit of yours and no fresh run repairs it, and a base that moved is by itself no reason to rebase ("A conflict"). If the Result has no `Stale base:` line for this head, add `Stale base: at <head>, <the check that failed>`, and park no gate. What turns the pull request green is the message "A conflict" names, which jbus or `jmerge` sends when its check fails over today's default branch, or, where `jmerge` cannot run a fresh check, when the default branch changed this pull request's files. When that message has come for this head, run the first block of "A conflict" with `stale` now. When it has not, it wakes this thread.
- `rerun`: the block ran the whole workflow run again, once, and wrote the `Rerun:` line itself, as the last line of the brief, wherever the last Result is: it is what keeps a second failure at this head from a second run, so leave it where it is. A `wait` that says the brief could not be written asks you to add that line yourself. Never run a job again by itself, and never `gh run rerun --failed`.
- `stuck`: a fresh run failed again at this head, or the failed check is no workflow run. It is not a flake, and the change passes here. If the Result has no `Stuck:` line for this head, add `Stuck: at <head>, <the check that failed>` and park a gate that asks what to do, with the default that the pull request waits.
- `wait`: the block could not judge. Do what the line says, or with nothing to do, end your turn.
