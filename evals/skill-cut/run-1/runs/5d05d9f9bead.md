1. **First, "Before step 1":** call the `t3-code` server's `t3_thread_configuration` with no arguments for `threadId`. Then run the "see which home this is" block, with the block at the top and that id in place of `<threadId>`. I expect `root` or `scope <name>`, plus a `write:` path.
2. **Then step 1, "Stop what runs in the background":** stop the poll by its process id, e.g. `kill <pid of the lavish-axi poll>`, and confirm with `ps -p <pid>` that it is gone. Nothing may be left that wakes this thread.
3. **Record it in the note** (step 2, at the `write:` path) under `Out, not on the bus: lavish-axi poll <page>, waiting on the user's answers; the next home starts it again`.
4. **Check worktrees:** in each one this thread used, run `git status --short` and `git log --oneline @{upstream}..`, and fill `Uncommitted:` from what they print.
5. Then I go on with steps 2 through 5 as written.
