1. **Before step 1** ("see which home this is"): call `t3_thread_configuration` with no arguments for `threadId`, then run the block at the top together with the identify block, `<threadId>` filled in. Expect `root` or `scope <name>`, plus the `write:` path.
2. **Step 1, stop what runs in the background:** find the poll's pid (`pgrep -af 'lavish-axi poll'`) and stop it with `kill <pid>`. This thread must have nothing left that wakes it.
3. Still step 1: since the user's answers are not yet in, the next home has to restart that poll. I note it for the note's `Out, not on the bus:` line, e.g. `lavish-axi poll on <page>, waiting on the user's answers; start it again`.
4. Still step 1: run `git status --short` and `git log --oneline @{upstream}..` in each worktree I used, for the `Uncommitted:` line.
5. Then **step 2**: read `$T/handoff.md` and write the note at the printed `write:` path, ten lines at most.
