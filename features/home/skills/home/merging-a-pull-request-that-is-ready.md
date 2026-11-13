## Merging a pull request that is ready

A pull request that is reviewed, fixed and green is merged, and the user is told of it when they ask for status, as "How a turn ends" says.
Nobody has to give the word for that one.
A pull request that is anything short of ready is never merged without the user's word.
On that word, the one way a home merges it is `jmerge --accept <number> --as user --message <thread id>/last`, run from the main checkout on the user's own message in T3 Code, `last` their newest there: it lifts the hold, merges, and writes the `merged` line with that message to `$H/merge.log`.
A home's own `gh pr merge`, `gh api .../pulls/<number>/merge` or GraphQL `mergePullRequest` is refused by the `merge-command` hook, which prints that line in its place ([The merge hook](../../docs/hooks.md#the-merge-hook)).
Where the accept refuses, its line says why and what to do; relay it to the user, and merge nothing by hand.
A pull request whose last review round says `Meets the brief: no`, has no such typed line, or has a count that is not its brief's is short of ready: `jmerge` holds it by its own reason (`meets-no`, `meets-unread`, `meets-miscounted`) on every path that merges, a follow-up row's included.
Its way out is its crew's fix and a scoped review whose own line says `yes`, or a `Waived:` line in the brief.
The root writes its own, `Waived: <the Done when line>, root/<act id>`, with `jbus waive --as root` and its reason and undo ("Judge a waiver" in its skill), and a scoped home sends it the waiver as a `decision` stop.
Any other is the user's `Waived: <the Done when line>, <thread>/<message>` line, which jbus checks rests on the user's own message, or the bot's word: a message that names the row, says it waives and quotes that line, from which a home writes the line, or the plain reply to a home's ask, recorded as "How a turn ends" says.
A home never has the user quote a line or type exact words, and its own word waives nothing.
A pull request that changes a protected path (a secret, or the list of protected paths itself), and any pull request of a repo whose merge is switched off, is the user's to merge, ready or not.

The home merges nothing itself, and runs no command that merges but `jmerge --accept` on the user's word.
One command does all of it, with no model: `jmerge`, from the repo this skill lives in, and jbus alone runs it to merge, on each pass, for every home of the repo, whatever `$H/home-thread` says.
That is the user's rule that jbus is the only merger, and child homes never merge their own pull requests (`features/home/spec/HomeTree.tla`, `OneMerger`).
A run of `jmerge` that names a home, `jmerge --home <id>`, merges nothing: it says what it would do of that home's pull requests, as `--check` does.
A run that merges holds the repo's merge lock, `$H/merge.lock`, from its read of main's tip to its merge, so a hand run of the user's never lands a merge between them (`NoBlindMerge`).

**The merge step** is run on a crewmate's `fixed and green` line, when the user asks for status, and once at the start of a home.
On any other message it is step 2 of "When a thread sends a message", so nothing that turned ready is left waiting.
Run it from the main checkout, in one call with the block at the top and the block that finds this home.
It is the only check: do not go by what a report said, or by what you remember.

```sh
L="$H/merge.log"
S="${M:?run the block that finds this home first}/merge-seen"
news() {
    tail -n "+$((${1} + 1))" "$L" | head -n "$((${2} - ${1}))" | cut -c18- | command grep '^merged ' |
        while IFS= read -r line; do
            slug=${line#merged * }
            if [ "$(whose "$H/tasks/${slug%% *}.md")" = "$M" ]; then printf '%s\n' "$line"; fi
        done
}
lines=$(command grep -c '' "$L" 2> /dev/null)
lines=${lines:-0}
seen=$(cat "$S" 2> /dev/null) || seen=$lines
case $seen in
*[!0-9]*) seen=$(command grep -snxF "$seen" "$L" | tail -n 1 | cut -d: -f1) ;;
esac
seen=${seen:-0}
if [ "$lines" -gt "$seen" ]; then news "$seen" "$lines"; fi
head -n "$lines" "$L" 2> /dev/null | tail -n 1 > "$S"
if open=$(gh pr list --repo "$(git remote get-url origin)" --state open --limit 200 --json number,url --jq '.[] | "\(.number) \(.url)"'); then
    printf '%s\n' "$open" | while read -r n url; do
        if [ -z "$n" ]; then continue; fi
        brief=$(LC_ALL=C && awk -v url="$url" '$(1) == "Branch:" && $(NF) == url {print FILENAME; exit}' "$H"/tasks/*.md 2> /dev/null)
        if [ "$(whose "$brief")" != "$M" ]; then continue; fi
        said=$(jq -r --arg n "$n" '.[$n] // empty' "$H/merge.log.last" 2> /dev/null)
        printf '%s\n' "${said:-wait $n $url: jbus has said nothing of it yet}"
    done
else
    echo "wait: could not ask GitHub"
fi
```

It runs no `jmerge`: jbus runs it on each pass, and this block reads what jbus's runs left on disk, for this home's briefs alone, by `whose` (`home_of` in `features/jmerge/src/jmerge/claims.py`, which `jmerge --claims` prints by); a pull request with no brief is the root's.
First the `merged` lines appended to `$H/merge.log` since this home last read it, without their date: `$M/merge-seen` keeps the last line read, so a cut loses none, and a home with no mark starts at the log's end.
Then, for each pull request GitHub lists as open, the last `wait` or `hold` line `jmerge` said of it (`$H/merge.log.last`), read anew on every run with no mark, so a `hold` is never lost and one merged or closed has none; one with no line yet is `wait <number> <url>: jbus has said nothing of it yet`.
They are the lines of the table below, and are relayed as a run's own are.

A line is as of jbus's last pass: `jmerge` writes one only when it changes.
A pull request that just turned ready often still has the `wait` from before its `Fixed:` line, and its `merged` line comes on a later run of this step.
If jbus is stopped the lines stay as they were: `systemctl --user status jbus.timer` says whether it runs.

A scoped home's pull request is merged, held or left waiting by the same rules as the root's.
It is `wait <number> <url>: another home's` only to a run of `jmerge --home`, which merges nothing: never tell the user it is theirs to merge for that reason.

[What a merge does](../../../jmerge/docs/jmerge.md#what-a-merge-does) lists the steps of jbus's run of `jmerge` for each ready pull request: the merge, the pull of the main checkout, and the removal of the crewmate's worktree and branches.
The skills in `~/.claude/skills` may be symlinks into the main checkout, and stay on the old text until that pull.
`jmerge` prints one line per open pull request, and appends the same lines, dated, to `$H/merge.log`:

| The line | Means |
|---|---|
| `merged <number> <slug> <commit> "<title>", revert: <command>` | it is merged as that commit, the main checkout is pulled, and the worktree and both branches are gone. The line ends in the command that undoes it |
| `merged <number> <slug> <commit> "<title>", the rebase changed the patch in <files>, revert: <command>` | it is merged, and a rebase changed its patch in those files after the last head a review saw: the review stands, and no review saw that change. Name the files on the line's `merged:` line |
| `merged <number> <slug> <commit> "<title>", kept: <what and why>, revert: <command>` | it is merged, and something was left: a worktree with uncommitted work, a branch that is not at the merged head, a worktree or a branch git would not remove. Do nothing more about it. The same line says so if the pull failed |
| `wait <number> <url>: <reason>` | it is not merged. The reason is the first thing it is short of |
| `hold <number> <url>: needs <the user's name>, touches <path>` | it is not merged and `jmerge` never merges it: it is short of nothing else, and it changes a protected path: a secret, or `jmerge`'s list of them. The path is the first one that matches. Tell the user, once: it is theirs to merge, and on their word `jmerge --accept` merges it |
| `wait <number> <url>: auto-merge is off for this repo` | it is not merged: it is short of nothing else, and the repo has a `merge-off` file. It is the user's to merge |
| `wait <number> <url>: another home's` | to a run of `jmerge --home` alone: its brief's `Home:` line names another home of this repo. jbus's own run judges every home's |
| `wait: could not ask GitHub` | nothing was looked at |

[What ready means](../../../jmerge/docs/jmerge.md#what-ready-means) lists each reason a pull request waits, and the rules are in `features/jmerge/src/jmerge/ready.py`.

Two more things keep a ready pull request from the command, and only the user lifts them. They are looked at last, so each is said of a pull request that is short of nothing else:

- it changes no protected path, a pattern of `features/jmerge/src/jmerge/protected.txt` ([Protected paths](../../../jmerge/docs/jmerge.md#protected-paths) has the list and its grammar).
  A rename into or out of a protected path is held as an edit there is, and `jmerge` asks GitHub for the old path, which it lists a rename without.
  The line is `hold <number> <url>: needs <the user's name>, touches <first matching path>`, and no flag lifts it.
  To protect another path, a pull request adds a line to `protected.txt`, and since it changes the list the user merges it;
- the repo's merge is on: every repo is, until `$H/merge-off` is there (`/nohome merge` makes it, `/nohome merge on` removes it).
  With it, the line is `wait <number> <url>: auto-merge is off for this repo`, and the accept waits on it too: the user merges such a pull request themselves.

The sweep below removes what a merged pull request's thread left.

A head that moved between the check and the merge fails the merge, and that is the wanted result: the line is `wait <number> <url>: the merge failed`, with what GitHub said, and the next run looks again. A worktree is removed only when it is clean and its branch is at the merged head, so nothing unpushed is lost.

**The log is the undo list.** Each `merged` line in `$H/merge.log` starts with the time it was printed, then its first four words, `merged <number> <slug> <commit>`, then the pull request's title in quotes, the notes above, and last `revert: gh pr revert <url>`. Run as it stands, from anywhere, that command opens a pull request that reverts the merge. It pushes nothing to the default branch and changes nothing in the checkout: the revert is a pull request like any other, and is merged like one. Run it on the user's word only, and give them the pull request it prints.

Write what it printed as lines of the turn's end ("How a turn ends"): one `merged:` line per pull request, the slug, the pull request and anything that was kept.
A `hold` line is on jbus's list of what waits on the user (`jbus queue show` prints it first), and a `wait` line is reported, not acted on: tell either only when the user asks for status.
The home does not fix what a pull request is short of: its crewmate does.
Settling a merged crewmate's thread is not the command's: T3 Code settles a thread whose linked pull request merges.

To see what is ready and merge nothing, run `uv run --project "$T/../source" jmerge --home '<threadId>'` from the main checkout, in one call with the block at the top, with this thread's id in place of `<threadId>`.
It merges nothing whatever the switch says, and prints `ready <number> <head> <branch> <slug>` for each of this home's pull requests that is ready.
A pull request that is held, or whose repo's merge is off, is printed as it is without the flag: it is not `ready`.

A merged branch stays on the remote while an open pull request is based on it, and its line says so under `kept:`.

A merge clears up after itself only when all is clean at that moment.
What is left then, and what never had a merge by this command, is the sweep's: a `kept:` of a merge, a pull request merged by hand, a crewmate that ended with no pull request, a scout's worktree, the gate's ref.
The same command does it, with no model.
**Who sweeps** is what `$H/home-thread` says: the home sweeps while the file holds an id, set by the user by hand, and nobody sweeps while it is empty or missing.
The switch decides nothing of the merge, which is jbus's whatever it holds.
Run the sweep once at the start of a home, after the merge step, from the main checkout, in one call with the block at the top:

```sh
if [ -n "$(cat "$H/home-thread" 2> /dev/null | tr -d '[:space:]')" ]; then
    uv run --project "$T/../source" jmerge --sweep
else
    echo "sweep off: home-thread is empty, so no home runs jmerge --sweep"
fi
```

On `sweep off`, nothing was run and there are no lists to act on.
Otherwise it looks at each branch a brief in `$H/tasks` or a request in `$H/scouts` names, a crewmate's `<slug>` and a scout's `scout-<slug>`, with its worktree under `~/.t3/worktrees/<repo>`, and at every other worktree there.
It prints two lists, the first one removed, and appends the same lines, dated, to `$H/merge.log`:

| The line | Means |
|---|---|
| `removed <branch> <thread>: <what>` | the thread is finished and nothing of its work could be lost, so what it left is gone: the worktree, the local branch, the remote branch, the gate's ref, whichever were there |
| `removed <branch> <thread>: <what>, kept: <what and why>` | git refused a step, and the rest is left for the next sweep |
| `kept <branch>: <reason>` | nothing of it was removed. The reason is the first of: not done, blocked, paused, something under Left, a pull request that is open or closed unmerged, uncommitted work, a commit that is in neither the remote's default branch nor its merged pull request, a process running in the worktree |
| `kept <directory>: no brief or request names its branch <branch>` | a worktree of T3 Code's that is nobody's task here. It is never removed |
| `wait: could not read origin` | nothing was looked at |

Removable means all of these hold.
The rules are in `features/jmerge/src/jmerge/sweep.py`, and nowhere else:

- the brief's last Result says `Status: done` and `Left: none`, or the request's last Report says `Status: done`;
- its pull request is merged, or it has none;
- the worktree has nothing uncommitted and no process running in it;
- each of the local branch, the remote branch and the gate's ref is at a commit the remote's default branch has, or at the merged pull request's head or behind it.

A branch or worktree that no brief or request names is never removed: the sweep does not list such a branch at all.

For each `removed` line, settle the thread it names, unless it says `no-thread`: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle", "threadId": "<thread>"}`. T3 Code has settled most of them by then, and a scout settles itself: a thread that is settled stays so. If the line is a crewmate's and its plan entry does not say done yet, as after a pull request merged by hand, set it. Tell the user all of them in one line.

A `kept` line is reported, not acted on: the home removes nothing by hand. Give the user the ones that wait on their word, in one line each: blocked, paused, something under Left, a pull request closed unmerged, uncommitted work, a commit that is nowhere else, a scout's page, a worktree nobody's task names. Say nothing of the ones that are only still out: not done, a pull request that is open, a process running.

To see both lists and remove nothing, add `--check`: it prints `removable` in place of `removed`, and logs nothing.
