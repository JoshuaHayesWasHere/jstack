First, per **"Stay on the pull request"** step 1, I link the pull request to this thread. I call the `t3-code` server's `link_pull_request` (loading it first if deferred) with `{"url": "<the url gh pr create printed>"}`.

Then I do the three steps of **"End"** (step 2). I append `$T/result.md`, filled in, to `$H/tasks/<slug>.md`, with the PR url on its `Branch:` line. I run the tell-home awk block, which prints `send nothing: <url> is open…`, so I send the home nothing. I say the result here in at most five lines.

Next comes step 3. I run the `checks` block of **"The checks"**. On `passed` or `wait`, I run the **"The review"** decision block, which prints `review: launch a reviewer`. I launch one as `skills/pr-review/SKILL.md` "Launching" says, add `Reviewer: <threadId>` to the Result, and do not wait for it.

Last, I end my turn (step 4): no polling and no watcher, since jbus sends any wake.
