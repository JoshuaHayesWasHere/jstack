## Launching

The brief's reviewer, if a thread has already launched one and written it in the result:

```sh
awk '/^Reviewer:/ && $(2) !~ /^none/ {print $(2); exit}' "$H/tasks/<slug>.md"
```

It prints that reviewer's thread id, or nothing.
A line that says `Reviewer: none`, which a crewmate with no launch tool writes, is no reviewer.

1. Find the briefs that are **ready**.
   Run this with the block at the top, in a home with no slug with `*` for `<slug>`.
   It is the only check:

   ```sh
   PASS=first
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
   for B in "$H"/tasks/<slug>.md; do
       past= why=
       pr=$(awk '/^## Result/ {pr = ""; done = 0; result = 1} result && /^Status: done/ {done = 1} result && $(1) == "Branch:" {pr = $(NF)} END {if (done) print pr}' "$B")
       case $pr in
       http*)
           if [ "$PASS" = first ] && awk '/^## Review$/ || (/^Reviewer:/ && $(2) !~ /^none/) {had = 1} END {exit !had}' "$B"; then
               past="it has a review or a reviewer, and it is one pass per pull request"
           elif state=$(gh pr view "$pr" --json state | jq -r .state) && [ -z "$state" ]; then
               why="GitHub could not be asked for its pull request"
           elif [ "$state" != OPEN ]; then
               past="its pull request is not open: $state"
           fi ;;
       *) past="its last Result does not say Status: done and name a pull request" ;;
       esac
       if [ -n "$past" ]; then
           why=$past
           case "<slug>" in "*") continue ;; esac
       elif [ -n "$why" ]; then
           :
       elif [ "$(awk '/^Review:/ {print $(2); exit}' "$B")" = none ]; then
           why="its brief asks for no review"
       else
           said=$(checks "$pr")
           case $said in
           passed*) head=${said##* } ;;
           "wait: a check has not finished" | "wait: no check is reported yet")
               head=$(gh pr view "$pr" --json headRefOid | jq -r '.headRefOid // empty') ;;
           *) head= ;;
           esac
           if [ -z "$head" ]; then why="its checks, $said"; fi
       fi
       if [ -n "$why" ]; then
           echo "$(basename "$B" .md): not ready, $why"
       else
           echo "$(basename "$B" .md): ready, $pr at $head"
       fi
   done
   ```

   It prints one line for each brief, `<slug>: ready, <url> at <head>` or `<slug>: not ready, <the first thing it is short of>`.
   With `*` it leaves out the briefs of the past: those with no pull request, with a pull request that is merged or closed, or with a review or a reviewer already.
   A brief is ready when all of these hold:
   - its last `## Result` says `Status: done` and names a pull request;
   - it has no `## Review` section and no reviewer: no `Reviewer:` line but one that says `none`, which the block above reads the same way;
   - that pull request is open;
   - its `Review:` line, read as above, is not `none`;
   - the pull request's checks are not red.
     `checks` is the crew skill's function, the same text, and prints its four answers: `passed`, `failed`, `wait`, `unrun` (the crew skill, "The checks").
     `passed` and `wait` are ready: a review runs beside the checks, and green is what `jmerge` merges on, not what a review waits for.
     The `wait` of a GitHub that could not be asked is not ready: no rollup was read.
     `failed` is never ready: a red pull request is fixed first, and its reviewer is launched on the push.
     `unrun` means no check ran, every one failed with no step run or was skipped, because the repo's CI starts no job: nothing stands in for a check that did not run, so the brief is not ready,
     whatever its Result says of a check command that passed in the crewmate's worktree.

   One thing the block cannot see: `t3_thread_list` with `titleContains: "review: <slug>"` finds no thread.
   Check it for each brief printed as ready.

   In a home with no slug, take every ready brief, oldest first, and at most three.
   Name the ones left over, and the ones passed over with the reason in a few words each: for a brief with `Review: none`, that its brief asks for no review.
   In a crewmate's thread with no slug, take that one brief; if it is not ready, say which line fails and stop.
   With a slug, first do what "A brief the user names" says, then take that one brief the same way.
2. A brief that already has a `## Review` section or a reviewer is refused: say so, and that it is one pass per pull request.
   A scoped pass is not refused: the crewmate launches one for a fix it pushed for a review's findings, jbus asks it for one after a rebase that changed the content of a reviewed patch,
   its message is `/pr-review run <slug> scoped <old range> <new range>` with the two ranges as the crew skill's block or jbus gave them, its title is `review: <slug>, scoped`, and it is launched as a second pass is,
   with `PASS=second` ("A scoped pass").
   A second pass is launched in two cases only, and then the message is `/pr-review run <slug> again`: the user asks for another pass in so many words,
   or this is the crewmate's thread and the block of the crew skill's "A second pass" printed `needed: launch the second reviewer`, which it prints only for a brief from before a fix got a scoped pass.
   For a second pass send the readiness block with `PASS=second` as its first line: the lines about `## Review` and a reviewer then do not apply, the others do.
   The title is `review: <slug>, second pass`.
   A reviewer that ended its turn writing nothing is sent back to work with the same `again` line, whether or not the brief has a `## Review` (`$T/rerun.md`).
3. Find the worktree that has the pull request's branch checked out: `git worktree list --porcelain`.
   The reviewer runs there (see "Where a run starts").
   If no worktree has it, say so and pass that brief over.
4. Start the reviewer with the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first).

   ```json
   {
     "title": "review: <slug>",
     "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<the pull request's branch>"},
     "message": "/pr-review run <slug>"
   }
   ```

   Before this launch, run `uv run --project "$T/.." jroles review` with the block at the top.
   It prints one JSON object a line, one for each reviewer the role map lists, in order: each line is a `<model selection>`, and each is one `t3_thread_launch` call, this one, which starts that reviewer on the model the line names.
   A pull request gets a review from each.
   With one line, the call is this one as it is.
   With two or more, the call for line `<n>` (1 for the first) has the title `review: <slug>, <n>` and the message `/pr-review run <slug> <n>`: the number is how the reviewer knows which line it is.
   When it prints nothing, there is one call, the one above.
   A scoped pass and a second pass are one reviewer, whatever the map lists: one call, on the first line, with the message and title they are given.
   Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line.
   When it exits 75 and prints no JSON, every instance of a review line's pool is capped by a usage limit and the line on stderr says until when: make no launch, and say that line.
   A selection it prints names the instance of the pool it chose as its `instanceId`, and the launch is made with it as printed.

   ```json
   {
     "title": "review: <slug>",
     "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<the pull request's branch>"},
     "message": "/pr-review run <slug>",
     "modelSelection": <model selection>
   }
   ```

   - Leave the project and modes out, and the model unless `jroles` printed one.
     What is left out, the reviewer inherits from this thread.
   - A crewmate writes one `Reviewer: <threadId>` line in its Result for each reviewer launched, in the order they were launched.
   - A launch has no retry key.
     If the call fails or its reply is lost, look for the thread with `t3_thread_list` (`titleContains: "review: <slug>"`) before launching again.
   - If the session has no such tool, tell the user instead: "Open a new thread in this project, in the worktree of `<branch>`, and type `/pr-review run <slug>`."
5. Give the user the links, one line for each reviewer: `[review: <slug>](t3-thread://v1/<threadId>)`, with its title.
   Then stop.
   Do not wait for a reviewer, poll it, or read its thread: its findings go to the crewmate and into the brief.

### A brief the user names

`Review: none` is the home's choice for a task it took to be text only or throwaway.
A user who types `/pr-review <slug>` has asked for that brief's review by name, and their word outranks the line.
So with a slug, and only then, run this before the readiness check:

```sh
B="$H/tasks/<slug>.md"
if [ "$(awk '/^Review:/ {print $(2); exit}' "$B")" = none ]; then
    awk '/^Review:/ && !seen {seen = 1; print "Review: review (was none: the user asked for this review by name)"; next} {print}' "$B" > "$B.named" &&
        mv "$B.named" "$B" &&
        echo "was none, now review: the user named it"
fi
```

It changes the brief's `Review:` line from `none` to `review` and says so, and prints nothing for any other brief.
The user naming the brief is the user's word for a review, so from then on it is a reviewed pull request like any other, and `jmerge` merges (run by jbus, or by the home when there is one) it when it is fixed and green:
the line is what the reviewer, the crewmate and the merge check all read.
Tell the user in one line that the brief said `none` and is being reviewed on their word.

It runs only on the path the user types, `/pr-review <slug>` in a home or in a crewmate's thread.
Never run it for `/pr-review` with no slug or for a crewmate's own launch.
And never on `/pr-review run <slug>`, which a thread sends and no user types: a reviewer changes no brief's line, and the first block of its review leaves a `none` brief as it is and exits 78.
