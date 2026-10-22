# A thread did not become a home

A new thread becomes a home by itself only when `features/home/hooks/home-start.sh` prints its message.
Check each condition in order:

1. Run `jinstall --check`. The line `ok hard hook <home>/.claude/settings.json SessionStart` must be there.
2. Open the thread in T3 Code. The hook is silent in a terminal session.
3. Open it in the repo's main checkout. The hook is silent in a worktree, a submodule, a bare repo, and T3 Code's scratch folder.
4. Start a new thread. The hook is silent on a resume, a `/clear` and a compaction.
5. Look for `~/.local/state/home/<repo>/off`. While that file is there, the repo has no automatic home. `/nohome on` removes it.

If the thread is already open, type `/home` in it. The thread becomes the home with no hook.
