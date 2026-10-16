1. **First**, per "Stay on the pull request" step 1, link the pull request to this thread with the `t3-code` server's `link_pull_request`, loading it first if deferred: `{"url": "<the url gh pr create printed>"}`.
2. **Step 2**, the three steps of "End": read `$T/result.md` and append it, filled in, to `$H/tasks/<slug>.md`. Its `Branch:` line ends with the pull request url. Then run the awk block that checks whether the home is told. It prints `send nothing: <url> is open…`, so I message no one.
3. Still in step 2, I say the same in this thread in at most five lines.
4. **Step 3**: run the `checks` block of "The checks" (`gh pr view --json headRefOid,statusCheckRollup` …), then the case block of "The review" with its first line in place of the placeholder.
5. On `passed` or `wait`, I run the reviewer-decision block, which prints `review: launch a reviewer`. I launch one now with `t3_thread_launch`, as "Launching" in `$T/../skills/pr-review/SKILL.md` describes, and add `Reviewer: <threadId>` to the Result. On `failed`, I fix and push first, then launch. On `unrun`, I park the gate instead.
6. **Step 4**: end my turn. I arm no watch and don't poll; jbus wakes me.
