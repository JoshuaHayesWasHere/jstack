First, per **"Stay on the pull request"**, step 1: link the pull request to this thread with the `t3-code` server's `link_pull_request` tool, `{"url": "<the url gh pr create printed>"}`, loading it first if deferred.

Next, step 2 runs the three steps of **"End"**:
- Append `$T/result.md`, filled in, to `$H/tasks/<slug>.md`, with `Branch: <pr url>`.
- Run the awk check. It prints `send nothing: <url> is open…`, so the home gets no message.
- Say the same here in at most five lines.

Then step 3 runs the `checks` block of **"The checks"**. On `passed` or `wait`, the review block of **"The review"** prints `review: launch a reviewer`. I launch one as pr-review's "Launching" says, add `Reviewer: <threadId>` to the Result, and end my turn (step 4) without arming a watch or polling.
