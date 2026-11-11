With no pull request, this thread is finished, and it settles itself when nothing of its work could be lost with it.
Where the brief asks for a pull request (`Pull request: open one`), the last Result names how the row ended on its `Outcome:` line, as `$T/result.md` shows: `carried by <slug>`, `nothing to change, <why>` or `dropped, <why>`.
Without it jbus keeps a `done` row at left, for its home to close.
After step 3, run this in this worktree, with the block at the top.
It is the only check:

```sh
B="$H/tasks/<slug>.md"
said=$(uv run --project "$T/../source" jbriefs line status,pr "$B")
status=$(printf '%s\n' "$said" | cut -f 1)
pr=$(printf '%s\n' "$said" | cut -f 2)
left=$(awk '/^## Result/ {left = 0; result = 1} result && $(1) == "Left:" {left = (NF == 2 && $(2) == "none")} END {print left + 0}' "$B")
why=
if [ "$status" = paused ]; then
    why="the task is paused, the last Result says Status: paused"
elif [ "$status" != done ]; then
    why="the last Result does not say Status: done"
elif [ "$left" != 1 ]; then
    why="the last Result does not say Left: none"
elif [ -z "$pr" ] || [ "$pr" = missing ]; then
    why="the last Result has no Branch line"
elif [ "${pr#http}" != "$pr" ]; then
    why="it has a pull request, and T3 Code settles this thread when that merges or closes"
fi
if [ -n "$why" ]; then
    echo "stay: $why"
elif ! dirty=$(git status --porcelain 2> /dev/null); then
    echo "stay: git status could not be run here"
elif [ -n "$dirty" ]; then
    echo "stay: the worktree has uncommitted work"
elif ! base=$(git symbolic-ref -q --short refs/remotes/origin/HEAD); then
    echo "stay: the remote's default branch is not known here"
elif ! ahead=$(git rev-list -n 1 HEAD --not "$base" 2> /dev/null); then
    echo "stay: the branch could not be compared with $base"
elif [ -n "$ahead" ]; then
    echo "stay: the branch has a commit that is not on $base"
else
    echo "settle"
fi
```

It prints one line. On `settle`, settle this thread: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle"}` and no `threadId`. It takes effect when the turn ends, so it is the last call, made only once the home is told, when there is one. A finished thread that did not settle itself is settled by jbus, once its pull request merged or its last Result says `Status: done` and `Left: none` with no pull request: a `stay` for something left is kept by jbus too. The worktree and the branch stay: removing them is not this thread's. On `stay`, or in a session with no such tool, settle nothing and say the reason here: the thread stays where the user can see what is left. Either way a follow-up is a new message from the user here, or a new brief from the home.
