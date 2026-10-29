## Merging a pull request that is ready

A pull request that is reviewed, fixed and green is merged, and the user is told of it when they ask for status, as "How a turn ends" says.
Nobody has to give the word for that one.
A pull request that is anything short of ready is never merged without the user's word.
Neither is one that changes a protected path (a secret, or the list of protected paths itself), nor any pull request of a repo whose merge is switched off: those are the user's to merge, ready or not.

The home merges nothing itself, and runs no command that merges.
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
    tail -n "+$((${1} + 1))" "$L" | head -n "$((${2} - ${1}))" | cut -c18- | grep '^merged ' |
        while IFS= read -r line; do
            slug=${line#merged * }
            if [ "$(whose "$H/tasks/${slug%% *}.md")" = "$M" ]; then printf '%s\n' "$line"; fi
        done
}
lines=$(grep -c '' "$L" 2> /dev/null)
lines=${lines:-0}
seen=$(cat "$S" 2> /dev/null)
case $seen in
'' | *[!0-9]*) seen=$lines ;;
esac
if [ "$seen" -gt "$lines" ]; then seen=0; fi
if [ "$lines" -gt "$seen" ]; then news "$seen" "$lines"; fi
echo "$lines" > "$S"
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

It runs no `jmerge`: jbus runs it on each pass, and this home's part is to read what jbus did.
The block prints what a run of `jmerge` would, from what jbus's runs left on disk.
First the `merged` lines jbus's `jmerge` appended to `$H/merge.log` since this home last read it, without their date: how far it read is kept in `$M/merge-seen`, a home with no mark starts at the end of the log, so an old merge is never news, and a log shorter than the mark is read from its start.
Then, for each pull request GitHub lists as open, the last `wait` or `hold` line `jmerge` said of it (`$H/merge.log.last`): that is read anew on every run and no mark is kept for it, so a `hold` is never lost between this block and the one that tells it, a pull request that has waited for long still has its line when the user asks for status, and one that is merged or closed has none.
An open pull request `jmerge` has no line for yet is `wait <number> <url>: jbus has said nothing of it yet`.
They are the lines of the table below, and are relayed as a run's own are.
On `wait: could not ask GitHub` no pull request's line was read.

A line is as of jbus's last pass, not of now: `jmerge` writes one only when it changes, and nothing here says how old it is.
A pull request that just turned ready often still has the `wait` from before its `Fixed:` line: jbus's next pass judges it, and its `merged` line comes on a later run of this step.
If jbus is stopped the lines stay as they were: `systemctl --user status jbus.timer` says whether it runs.

jbus runs `jmerge` for the whole repo, and the block prints this home's lines alone: a `merged` line whose slug is a brief of this home's, and the line of an open pull request that one's `Branch:` line ends on, the first such brief by name in codepoint order, as `jmerge` finds it.
A brief is the home's that its `Home:` line names: by its thread id, by the id on the `Was home:` line of its handoff, or by its scope, which is a directory of `$H` with a `home-id` or such a handoff.
A brief is the root's when it has no such line, when its line names no such home, or when the pull request has no brief.
That is `jmerge`'s one rule (`home_of` in `features/jmerge/src/jmerge/claims.py`, over `homes` in `features/jmerge/src/jmerge/cli.py`): `jmerge --claims` prints a brief's home by it, and `jmerge --home` leaves the others' out by it.

jbus runs `jmerge` with no `--home`, and it merges for every home of the repo, whatever `$H/home-thread` holds.
So the pull request of a brief whose `Home:` line names a scoped home is merged, held or left waiting by the same rules as the root home's, and its `merged` line is in `$H/merge.log` like any other.
A pull request is `wait <number> <url>: another home's` only to a run of `jmerge --home`, which merges nothing: jbus never says it, and never tell the user that a scoped home's pull request is theirs to merge for that reason.

jbus's run of `jmerge`, for each open pull request of this repo that is ready, it squash-merges it at the exact head it checked (`gh pr merge <number> --squash --match-head-commit <head>`), runs `git pull --ff-only` in the main checkout, and removes the crewmate's worktree and its local and remote branch.
It writes no plan: `jbus plan` counts an entry's status from its queue rows.
The skills in `~/.claude/skills` may be symlinks into the main checkout, and stay on the old text until that pull.
It prints one line per open pull request, and appends the same lines, dated, to `$H/merge.log`:

| The line | Means |
|---|---|
| `merged <number> <slug> <commit> "<title>", revert: <command>` | it is merged as that commit, the main checkout is pulled, and the worktree and both branches are gone. The line ends in the command that undoes it |
| `merged <number> <slug> <commit> "<title>", the rebase changed the patch in <files>, revert: <command>` | it is merged, and a rebase changed its patch in those files after the last head a review saw: the review stands, and no review saw that change. Name the files on the line's `merged:` line |
| `merged <number> <slug> <commit> "<title>", kept: <what and why>, revert: <command>` | it is merged, and something was left: a worktree with uncommitted work, a branch that is not at the merged head, a worktree or a branch git would not remove. Do nothing more about it. The same line says so if the pull failed |
| `wait <number> <url>: <reason>` | it is not merged. The reason is the first thing it is short of |
| `hold <number> <url>: needs <the user's name>, touches <path>` | it is not merged and `jmerge` never merges it: it is short of nothing else, and it changes a protected path: a secret, or `jmerge`'s list of them. The path is the first one that matches. Tell the user, once: it is theirs to merge |
| `wait <number> <url>: auto-merge is off for this repo` | it is not merged: it is short of nothing else, and the repo has a `merge-off` file. It is the user's to merge |
| `wait <number> <url>: another home's` | to a run of `jmerge --home` alone: its brief's `Home:` line names another home of this repo. jbus's own run judges every home's |
| `wait: could not ask GitHub` | nothing was looked at |

Ready means all of these hold.
The rules are in `features/jmerge/src/jmerge/ready.py`, and nowhere else:

- its base is the default branch. A pull request based on another branch would be merged into that branch, and nothing of it would reach the default one: the line is `wait <number> <url>: its base is <branch>, not <default branch>`, and no flag lifts it;
- its brief has no `Stack:` line in its head, or the user said to land that stack. A stack is landed by the user: the line is `wait <number> <url>: it is in the stack <name>, which the user lands`, and `--land <name>` lifts it, for that stack alone. A `Stack:` line with no name is held, and no `--land` lifts it;
- the brief has a `## Review` section, so a review was written. A brief with `Review: none` gets no review, so it is never ready: it needs the user's word;
- the review is clean, or the crewmate's Result has its `Fixed:` line;
- the head is the commit the `Fixed:` line names, and after findings that is not the head the review saw: a fix is a push.
  A crewmate that declines every finding writes `Fixed: none needed`.
  With `Fixed: none needed`, or a clean review and no `Fixed:` line, it is the head the review saw, or a head `jmerge` compares with it after a rebase, as the next item says;
- a rebase since the review is worked out from git, the commit the review covers to the head, and a `Rebase:` line in the brief is read as no line: `jmerge` looks for the lines the rebase dropped and runs `git range-diff`, which carries the review over or waits for a scoped review of the change (features/jmerge/docs/jmerge.md, "After a rebase");
- the fix is reviewed where it must be: a fix that changes a file outside `tests/` gets one scoped review. A Result with the line `Scoped review: needed since <head>` is not ready until the brief has a review of a later head and every finding of every review has its `Finding:` line. That review counts as the review in the lines above. A fix under `tests/` only is not reviewed. A brief from before the scoped review has `Second pass: needed since <head>` and is read the same way;
- the check named `check` passed at its head, whatever the other checks say. It is the job the repo's workflow runs the check command in. A `check` that failed, has not finished, was skipped or is not among the checks has not passed, and the line is `wait <number> <url>: check has not passed`. Nothing stands in for it: a pull request whose checks did not run is not green, whatever its Result says of a check command that passed in the crewmate's worktree, an older `CI: did not run` line included;
- GitHub says `MERGEABLE`.

Two more things keep a ready pull request from the command, and only the user lifts them. They are looked at last, so each is said of a pull request that is short of nothing else:

- it changes no protected path.
  The patterns are in `features/jmerge/src/jmerge/protected.txt`, one per line, `#` for a comment: `secrets/`, `.env`, `.env.*`, `*.pem`, `*.key`, the list itself, `/features/jmerge/src/jmerge/protected.txt`, and `/policy/` and `/dns/` at the root of a repo, where a change applies to the live tailnet policy or DNS records.
  A pattern that ends in `/` is a directory and covers everything under it, from the root of the repo when it has another `/` in it and at any depth when it has none.
  Any other pattern is a file: a name at any depth, or with a `/` in it the whole path from the root, as `features/jbus/src/jbus/merge.py`.
  A `*` matches within one part of a path.
  `jmerge` refuses to run, and merges nothing, while that file or `ci-paths.txt` is missing or has a pattern it cannot read (`**`, a leading `!`): no line there is taken and ignored.
  The line is `hold <number> <url>: needs <the user's name>, touches <first matching path>`, with the name `jmerge` reads from `~/.config/jstack/config.toml` (`user` where that file names none), and no flag lifts it, `--land` included.
  A rename changes both its paths: one into or out of a protected path is held as an edit there is, and one between two paths that are not protected is not.
  GitHub lists a rename under its new path alone, so `jmerge` asks for the paths the renames left, of a pull request that has one and is short of nothing else.
  GitHub must have said every path the pull request changes: one whose file list it cut short is held, and so is one whose renames it would not give the old paths of.
  To protect another path, a pull request adds a line to `protected.txt`, and since it changes the list the user merges it;
- the repo's merge is on. Every repo is on until `$H/merge-off` is there: `/nohome merge` makes the file and `/nohome merge on` removes it. With it, the line is `wait <number> <url>: auto-merge is off for this repo`, whoever runs the command, a home or `jbus`.

A pull request that is held (`hold`) is merged by the user, by hand, and so is any pull request of a repo whose merge is off. The sweep below then removes what its thread left.

A head that moved between the check and the merge fails the merge, and that is the wanted result: the line is `wait <number> <url>: the merge failed`, with what GitHub said, and the next run looks again. A worktree is removed only when it is clean and its branch is at the merged head, so nothing unpushed is lost.

**The log is the undo list.** Each `merged` line in `$H/merge.log` starts with the time it was printed, then its first four words, `merged <number> <slug> <commit>`, then the pull request's title in quotes, the notes above, and last `revert: gh pr revert <url>`. Run as it stands, from anywhere, that command opens a pull request that reverts the merge. It pushes nothing to the default branch and changes nothing in the checkout: the revert is a pull request like any other, and is merged like one. Run it on the user's word only, and give them the pull request it prints.

Write what it printed as lines of the turn's end ("How a turn ends"): one `merged:` line per pull request, the slug, the pull request and anything that was kept, which the user is told when they ask for status.
A `hold` line is the user's to act on, and jbus tells them of it: each pull request `jmerge` holds is on jbus's list of what waits on the user, from jbus's own run or from the last line a home's run logged, which `jbus queue show` prints first.
Tell it only when the user asks for status.
A `wait` line is reported, not acted on: give it to the user when they ask for status.
The home does not fix what a pull request is short of.
Its crewmate does.
Settling a merged crewmate's thread is not the command's: T3 Code settles a thread whose linked pull request merges.

To see what is ready and merge nothing, run `uv run --project "$T/../source" jmerge --home '<threadId>'` from the main checkout, in one call with the block at the top, with this thread's id in place of `<threadId>`.
It merges nothing whatever the switch says, and prints `ready <number> <head> <branch> <slug>` for each of this home's pull requests that is ready.
A pull request that is held, or whose repo's merge is off, is printed as it is without the flag: it is not `ready`.

A stack is landed by the user's word only, "land <name>", said in this thread, and by the user's own run: the home runs no `jmerge --land`, since jbus is the only merger, and jbus never adds `--land`.
End the turn with `stop local <name>: landing the stack is the user's own run of jmerge --land <name> from the main checkout` ("How a turn ends"), and do nothing more.
That run lifts the second wait for the pull requests whose `Stack:` line names that stack, and nothing else: each is merged as any other, when it is ready and its base is the default branch.
So one run lands the bottom link and prints `its base is <branch>, not <default branch>` for every link above it.
The merged link's remote branch stays while a pull request is based on it, and its line says so under `kept:`.
`jmerge` changes no base, and prints nothing that says a new base is the next step: "A stack the user lands" has it, and the playbook `shipping` has the steps in order.

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
    echo "no sweep: $H/home-thread is empty, and this home sweeps nothing"
fi
```

On `no sweep`, nothing was run and there are no lists to act on.
Otherwise it looks at each branch a brief in `$H/tasks` or a request in `$H/scouts` names, a crewmate's `<slug>` and a scout's `scout-<slug>`, with its worktree under `~/.t3/worktrees/<repo>`, and at every other worktree there.
It prints two lists, the first one removed, and appends the same lines, dated, to `$H/merge.log`:

| The line | Means |
|---|---|
| `removed <branch> <thread>: <what>` | the thread is finished and nothing of its work could be lost, so what it left is gone: the worktree, the local branch, the remote branch, the gate's ref, whichever were there |
| `removed <branch> <thread>: <what>, kept: <what and why>` | git refused a step, and the rest is left for the next sweep |
| `kept <branch>: <reason>` | nothing of it was removed. The reason is the first of: not done, blocked, paused, something under Left, a scout's Report with a page, a pull request that is open or closed unmerged, uncommitted work, a commit that is in neither the remote's default branch nor its merged pull request, a process running in the worktree |
| `kept <directory>: no brief or request names its branch <branch>` | a worktree of T3 Code's that is nobody's task here. It is never removed |
| `wait: could not read origin` | nothing was looked at |

Removable means all of these hold.
The rules are in `features/jmerge/src/jmerge/sweep.py`, and nowhere else:

- the brief's last Result says `Status: done` and `Left: none`, or the request's last Report says `Status: done` and names no page: a page may still wait on the user;
- its pull request is merged, or it has none;
- the worktree has nothing uncommitted and no process running in it;
- each of the local branch, the remote branch and the gate's ref is at a commit the remote's default branch has, or at the merged pull request's head or behind it.

A branch or worktree that no brief or request names is never removed: the sweep does not list such a branch at all.

For each `removed` line, settle the thread it names, unless it says `no-thread`: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle", "threadId": "<thread>"}`. T3 Code has settled most of them by then, and a scout settles itself: a thread that is settled stays so. If the line is a crewmate's and its plan entry does not say done yet, as after a pull request merged by hand, set it. Tell the user all of them in one line.

A `kept` line is reported, not acted on: the home removes nothing by hand. Give the user the ones that wait on their word, in one line each: blocked, paused, something under Left, a pull request closed unmerged, uncommitted work, a commit that is nowhere else, a scout's page, a worktree nobody's task names. Say nothing of the ones that are only still out: not done, a pull request that is open, a process running.

To see both lists and remove nothing, add `--check`: it prints `removable` in place of `removed`, and logs nothing.
