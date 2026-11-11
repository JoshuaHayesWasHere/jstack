### The checks

Whether a pull request's checks have passed is never read off a message or remembered: it is what this prints, run in this worktree with the block at the top. It is the only check:

```sh
uv run --project "$T/../source" jmerge --checks
```

Its first word is one of four answers:

- `passed`: every check passed. The pull request is green.
- `failed`: a check ran and failed.
  Run the check in this worktree with the block of "Do the task" that runs it, in this turn, as that step says: in a repo whose check selects its tests (`scripts/select_tests.py`) it is the touched check, a step to a short slot, and in any other repo the check command.
  On a full lane's `waiting`, stop as "Do the task" says.
  In a repo whose check selects its tests, then run each test file CI's failed parts name, alone in the short lane, with the block of "The failed files" below.
  Never the whole suite and never the first line of `$H/fresh-check` there: CI's check runs the selection, and `jgauge test-slot --thread` refuses a whole suite in such a repo.
  Then run the block of "A failed check" below, with `failed` where the check or a failed file failed here, and do what its first word says.
- `wait`: a check is still running, none is reported yet, or GitHub could not be asked.
  End your turn: jbus sends this thread a message when a check ran and failed at this head, and none when every check passed, since the review came before the pull request.
- `unrun`: no check ran. Every check either failed with no step run or was skipped, which is a repo whose CI starts no job (no runner, a failed payment), and nothing a push repairs. It is not green, and nothing stands in for a check that did not run: the check command passing in this worktree does not, and no line in the Result does. If the Result has no `Unrun:` line for this head, add `Unrun: at <head>, no check ran` and park a gate ("Do the task") that says `no check ran at <head>` and asks what to do, with the default that the pull request waits. Launch no reviewer and send no `fixed and green` line. Then end your turn: the gate's answer wakes this thread, or jbus's message when a check runs and fails.

**Green**, everywhere in this skill, is `passed` and nothing else.
`jmerge --checks` is the one reading of a pull request's checks: the pr-review skill and jbus call the same one.
A failed check whose job GitHub will not give counts as one that ran.
A check run more than once at the head, one cancelled and run again included, counts by its latest run, the one that started last: `jmerge` reads it the same way.
The block of "A failed check" reads each check by its latest run too, so a run that failed and was passed since is never run again, and it runs nothing again while the workflow run of a failed check still has a job going.
The merge goes by the checks the repo names: `jmerge` merges only when each check its `$H/required-checks` file names passed at the head, or the check named `check` where there is no such file (features/jmerge/docs/jmerge.md, "Name the checks a merge waits for").

**The failed files** are the test files that the logs of CI's failed jobs name on a `FAILED` or `ERROR` line, read from the latest run of each failed check.
Run this in this worktree with the block at the top and this thread's id in place of the words in angle brackets:

```sh
if [ ! -f scripts/select_tests.py ]; then
    echo "none: this repo's check selects no tests, so the check command ran them all"
elif ! said=$(uv run --project "$T/../source" jbus budget --wait 540 --calls 10); then
    echo "$said"
elif ! view=$(gh pr view --json statusCheckRollup); then
    echo "wait: could not ask GitHub"
else
    runs=$(printf %s "$view" | jq -r '
        def at: if (. // "") == "" or startswith("0001-") then "~" else . end;
        def run: (.detailsUrl // "") | capture("^https://[^/]*/[^/]*/[^/]*/actions/runs/(?<id>[0-9]+)/job/[0-9]+$").id;
        [.statusCheckRollup[]? | {one: ., key: (.name // .context), when: [(.startedAt | at), (.completedAt | at)]}]
        | group_by(.key) | map((max_by(.when).when) as $last | .[] | select(.when == $last) | .one)
        | [.[] | select(.status == "COMPLETED" and (.conclusion | IN("SUCCESS", "NEUTRAL", "SKIPPED") | not)) | run] | unique | .[]')
    files=$(for run in $runs; do gh run view "$run" --log-failed; done | sed -E -n 's/.* (FAILED|ERROR) ([^ :]*\.py).*/\2/p' | sort -u)
    kept=$(git rev-parse --git-path crew-failed-files)
    if [ -n "$files" ]; then
        { printf '%s\n' "$files"; cat "$kept" 2> /dev/null; } | sort -u > "$kept.new" && mv "$kept.new" "$kept"
    fi
    ran=0
    for file in $files; do
        [ -f "$file" ] || { echo "$file: not in this worktree, so not run"; continue; }
        lane=short
        uv run --project "$T/../source" jgauge test-slot --short --thread '<thread id>' -- make test TESTS="$file"
        said=$?
        if [ "$said" = 124 ]; then
            lane=full
            uv run --project "$T/../source" jgauge test-slot --thread '<thread id>' -- make test TESTS="$file"
            said=$?
        fi
        echo "$file: exit $said, $lane lane"
        [ "$said" = 0 ] || [ "$ran" != 0 ] || ran=$said
        [ "$said" != 76 ] || break
    done
    [ -n "$files" ] || echo "none: CI's failed jobs name no test file"
    echo "failed files: exit $ran"
fi
```

Its last line is `failed files: exit <n>`: 0 where each named file passed here, and the first failure's exit otherwise, which is `failed` for "A failed check".
The block keeps the names in the worktree's `crew-failed-files` (`git rev-parse --git-path crew-failed-files`), and the check block of "Do the task" runs each one in the worktree as a step after the guards, until it passes at a committed head: a fix whose failed file is still red has no `Checked:` line of exit 0, so it is not pushed.
A `76` in the short lane is no slot by the ceiling: run the block again at once.
A `76` in the full lane is a wait for a slot: end the turn as "test slots" says, and on jbus's message run the block again.
A `none` line runs nothing: the check of "Do the task" is the whole of what runs here, and its lint covers a failed lint job.

**A failed check** is the change's own, a base that moved, or a flake, and this says which. Run it in this worktree with the block at the top, after the check command, with what the check command did here in place of the words in angle brackets, `failed` or `passed`:

```sh
B="$H/tasks/<slug>.md"
here='<failed or passed>'
if [ "$here" != failed ] && [ "$here" != passed ]; then
    echo "wait: run the check command in this worktree first, and set here to failed or passed"
elif ! said=$(uv run --project "$T/../source" jbus budget --wait 540 --calls 10); then
    echo "$said"
elif ! view=$(gh pr view --json headRefOid,baseRefName,statusCheckRollup); then
    echo "wait: could not ask GitHub"
else
    head=$(printf %s "$view" | jq -r .headRefOid)
    base=$(printf %s "$view" | jq -r .baseRefName)
    picked=$(printf %s "$view" | jq -r '
        def at: if (. // "") == "" or startswith("0001-") then "~" else . end;
        def run: (.detailsUrl // "") | capture("^https://[^/]*/[^/]*/[^/]*/actions/runs/(?<id>[0-9]+)/job/[0-9]+$").id;
        [.statusCheckRollup[]? | {one: ., key: (.name // .context), when: [(.startedAt | at), (.completedAt | at)]}]
        | group_by(.key) | map((max_by(.when).when) as $last | .[] | select(.when == $last) | .one)
        | ([.[] | select(.status == "COMPLETED" and (.conclusion | IN("SUCCESS", "NEUTRAL", "SKIPPED") | not)) | run] | unique) as $failed
        | ([.[] | select(.status != "COMPLETED") | run | select(IN($failed[]))] | unique) as $going
        | "\($failed | join(" "))|\($going | join(" "))"')
    runs=${picked%%|*}
    going=${picked#*|}
    if [ "$(git rev-parse HEAD)" != "$head" ] && [ -z "$(git status --porcelain)" ] && git fetch -q origin "$head" 2> /dev/null && git merge-base --is-ancestor HEAD "$head"; then
        echo "wait: the pushed head $head is ahead of this worktree, which jmerge's merge of origin/$base on GitHub does: run git merge --ff-only $head, then the check command again"
    elif [ "$(git rev-parse HEAD)" != "$head" ] || [ -n "$(git status --porcelain)" ]; then
        echo "wait: this worktree is not at the pushed head $head with nothing uncommitted, so the check command did not run on what failed: commit and push"
    elif [ "$here" = failed ]; then
        echo "fix: the check command fails here at $head, so the failure is the change's own"
    elif ! git fetch -q origin "$base"; then
        echo "wait: could not fetch origin/$base"
    elif ! git merge-base --is-ancestor "origin/$base" HEAD; then
        echo "stale: the check command passes here at $head, and the branch does not hold the tip of origin/$base: no rerun, no commit, no rebase"
    elif command grep -q "^Rerun: at $head," "$B"; then
        echo "stuck: a fresh run at $head failed again while the check command passes here: not a flake, no second rerun"
    elif [ -n "$going" ]; then
        echo "wait: workflow run $going of a failed check at $head is still running, so it has not ended: no rerun until it has, end your turn"
    elif [ -z "$runs" ]; then
        echo "stuck: the failed check at $head is not a workflow run, so there is nothing to run again"
    else
        started=
        for run in $(printf '%s' "$runs"); do
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

Its first word is one of six answers.
After each but `held`, end your turn.

- `held`: GitHub's API budget, which jbus and every thread share, stayed at its floor (`jbus budget`) for the nine minutes the block waited, and nothing was asked of GitHub.
  Give the block a time limit of 10 minutes (`timeout: 600000` in Claude Code), and run it again, in this turn, until it prints another word.

- `fix`: the failure is in the pull request's own change.
  Only this one gets a commit: fix it, run the check command, push with the block of "The review" that pushes a fix, and add one line to the Result saying what failed and what you did.
  Then go by what has reviewed the pull request.
  Where the block of "The review" prints `launch a reviewer`, launch it now, on the push.
  Where the brief has a `## Review` section, write no line about the push: `jmerge` compares the head the review covers with the one you pushed by `git range-diff`, and the review carries over or one scoped review is asked for ("A conflict").
- `stale`: the change passes here, and its base moved under it.
  CI tests the merge with the base, so no commit of yours and no fresh run repairs it, and a base that moved is by itself no reason to rebase ("A conflict").
  If the Result has no `Stale base:` line for this head, add `Stale base: at <head>, <the check that failed>`, park no gate, and end your turn.
  `jmerge` judges a red pull request again by itself once its base has moved since the check started and is not red: it runs its fresh check on this head over today's base, where the repo has one, and on a pass asks GitHub to merge the base into the branch, so a new check runs and the pull request goes on with its review.
  Nobody sends a rebase for it by hand, the home included.
  No message asks this thread to rebase for it: a check that fails again at the head GitHub's merge made comes as `jbus: <check> failed on your pull request`, and a conflict as "A conflict" says.
  After a merge of the base on GitHub, the branch there is ahead of this worktree: fetch it and run `git merge --ff-only origin/<branch>` before any later commit, so a push is never refused.
- `rerun`: the block ran the whole workflow run again, once, and wrote the `Rerun:` line itself, as the last line of the brief, wherever the last Result is: it is what keeps a second failure at this head from a second run, so leave it where it is. A `wait` that says the brief could not be written asks you to add that line yourself. Never run a job again by itself, and never `gh run rerun --failed`.
- `stuck`: a fresh run failed again at this head, or the failed check is no workflow run. It is not a flake, and the change passes here. If the Result has no `Stuck:` line for this head, add `Stuck: at <head>, <the check that failed>` and park a gate that asks what to do, with the default that the pull request waits.
- `wait`: the block could not judge. Do what the line says, or with nothing to do, end your turn.
