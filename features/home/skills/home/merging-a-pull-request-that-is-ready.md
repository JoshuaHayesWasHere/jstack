## Merging a pull request that is ready

A pull request that is reviewed, fixed and green is merged, and the user is told. Nobody has to give the word for that one. A pull request that is anything short of ready is never merged without the user's word. Neither is one that changes a protected path (a secret, or one of the two lists of paths), nor any pull request of a repo whose merge is switched off: those are the user's to merge, ready or not. One that changes a guarded path is merged by the same command, under a stricter gate (below).

The home merges nothing itself. One command does all of it, with no model: `jmerge`, from the repo this skill lives in. One runner runs it for a repo, jbus or a home, never both: two runs at once would race, and no lock keeps them apart.

**Who merges** is what `$H/home-thread` says, and this block is the one the three blocks below go by.
It is the test jbus makes (`features/jbus/src/jbus/merge.py`), and the one the start of a home makes for its warning:

```sh
if [ -n "$(cat "$H/home-thread" 2> /dev/null | tr -d '[:space:]')" ]; then merges=home; else merges=jbus; fi
echo "$merges merges"
```

It prints `home merges` when the file holds an id, and `jbus merges` when it is empty or missing. Run it in the same call as each of the three blocks below, before the block: the merge step, the landing of a stack, which is the merge step with a flag, and the sweep. Each stops with `run the block of "Who merges" first` when it was not run, and `jmerge` is run on `home merges` alone. A home runs `jmerge` to merge, land or sweep nowhere else. `jmerge --claims` changes nothing, and is run whoever merges.

**The merge step** is run on a crewmate's `fixed and green` line, which is sent for it to be run while the home merges, when the user asks for status, and once at the start of a home. On any other message it is step 2 of "When a thread sends a message", so nothing that turned ready is left waiting. Run it from the main checkout, in one call with the block at the top, the block that finds this home and the block of "Who merges", with this thread's id in place of `<threadId>`. On `home merges` it is the only check: do not go by what a report said, or by what you remember.

```sh
: "${merges:?run the block of "Who merges" first}"
flags=''
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
case $merges in
home)
    own=$(
        uv run --project "$T/.." jmerge --home '<threadId>' $flags
    )
    ran=$?
    if [ -n "$own" ]; then printf '%s\n' "$own"; fi
    end=$(grep -c '' "$L" 2> /dev/null)
    end=${end:-0}
    if [ "$end" -gt "$lines" ]; then news "$lines" "$end" | grep -vxF -e "$own"; fi
    echo "$end" > "$S"
    (exit "$ran")
    ;;
*)
    case " $flags " in
    *" --land "*) echo "not landed: jbus merges here and lands no stack, until $H/home-thread holds an id" ;;
    esac
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
    ;;
esac
```

On `jbus merges` it runs no `jmerge`: jbus runs it on each pass, and this home's part is to read what jbus did.
The block prints what a run of `jmerge` would, from what jbus's runs left on disk.
First the `merged` lines jbus's `jmerge` appended to `$H/merge.log` since this home last read it, without their date: how far it read is kept in `$M/merge-seen`, a home with no mark starts at the end of the log, so an old merge is never news, and a log shorter than the mark is read from its start.
Then, for each pull request GitHub lists as open, the last `wait` or `hold` line `jmerge` said of it (`$H/merge.log.last`): that is read anew on every run and no mark is kept for it, so a `hold` is never lost between this block and the one that tells it, a pull request that has waited for long still has its line when the user asks for status, and one that is merged or closed has none.
An open pull request `jmerge` has no line for yet is `wait <number> <url>: jbus has said nothing of it yet`.
They are the lines of the table below, and are relayed as a run's own are.
On `wait: could not ask GitHub` no pull request's line was read.

A line is as of jbus's last pass, not of now: `jmerge` writes one only when it changes, and nothing here says how old it is. No `fixed and green` line is sent while jbus merges, so a pull request that just turned ready often still has the `wait` from before its `Fixed:` line: jbus's next pass judges it, and its `merged` line comes on a later run of this step. If jbus is stopped the lines stay as they were: `systemctl --user status jbus.timer` says whether it runs.

jbus runs `jmerge` for the whole repo, and the block prints this home's lines alone: a `merged` line whose slug is a brief of this home's, and the line of an open pull request that one's `Branch:` line ends on, the first such brief by name in codepoint order, as `jmerge` finds it.
A brief is the home's that its `Home:` line names: by its thread id, by the id on the `Was home:` line of its handoff, or by its scope, which is a directory of `$H` with a `home-id` or such a handoff.
A brief is the root's when it has no such line, when its line names no such home, or when the pull request has no brief.
That is `jmerge`'s one rule (`home_of` in `features/jmerge/src/jmerge/claims.py`, over `homes` in `features/jmerge/src/jmerge/cli.py`): `jmerge --claims` prints a brief's home by it, and on `home merges` `jmerge --home` leaves the others' out by it.
The block first prints the `merged` lines this home has not read, as on `jbus merges`, and sets the mark past them before `jmerge` runs, so a run cut short tells none of them twice.
After the run it prints what `jmerge` printed, then any `merged` line of this home's that another writer logged meanwhile, and sets the mark to the end of the log: what this home's own run printed is not news after the switch is emptied.
It ends with what `jmerge` ended with and does not end the call, so a sweep joined after it runs.

jbus runs `jmerge` with no `--home`, as the root home would, and while `$H/home-thread` is empty it merges for every home of the repo.
So the pull request of a brief whose `Home:` line names a scoped home is merged, held or left waiting by the same rules as the root home's, and its `merged` line is in `$H/merge.log` like any other.
A pull request is `wait <number> <url>: another home's` only while an id is in `$H/home-thread`, where each home runs `jmerge --home` and merges its own: never tell the user that a scoped home's pull request is theirs to merge for that reason.

On `home merges` it runs `jmerge`. For each open pull request of this repo that is ready, it squash-merges it at the exact head it checked (`gh pr merge <number> --squash --match-head-commit <head>`), runs `git pull --ff-only` in the main checkout, and removes the crewmate's worktree and its local and remote branch. It writes no plan: `jbus plan` counts an entry's status from its queue rows. The skills in `~/.claude/skills` may be symlinks into the main checkout, and stay on the old text until that pull. It prints one line per open pull request, and appends the same lines, dated, to `$H/merge.log`:

| The line | Means |
|---|---|
| `merged <number> <slug> <commit> "<title>", revert: <command>` | it is merged as that commit, the main checkout is pulled, and the worktree and both branches are gone. The line ends in the command that undoes it |
| `merged <number> <slug> <commit> "<title>", the rebase changed the patch in <files>, revert: <command>` | it is merged, and a rebase changed its patch in those files after the last head a review saw: the review stands, and no review saw that change. Name the files on the line's `merged:` line |
| `merged <number> <slug> <commit> "<title>", kept: <what and why>, revert: <command>` | it is merged, and something was left: a worktree with uncommitted work, a branch that is not at the merged head, a worktree or a branch git would not remove. Do nothing more about it. The same line says so if the pull failed |
| `merged <number> <slug> <commit> "<title>", guarded: <path>, revert: <command>` | it is merged under the stricter gate of a guarded path, the first one it changes |
| `wait <number> <url>: <reason>` | it is not merged. The reason is the first thing it is short of |
| `wait <number> <url>: guarded (touches <path>), <reason>` | it is not merged yet: it is short of nothing else, it changes a guarded path, and that part of the stricter gate does not hold. It is not the user's to merge: a later run merges it once the reason is gone |
| `hold <number> <url>: needs <the user's name>, touches <path>` | it is not merged and `jmerge` never merges it: it is short of nothing else, and it changes a protected path: a secret, or one of `jmerge`'s two lists. The path is the first one that matches. Tell the user, once: it is theirs to merge |
| `wait <number> <url>: auto-merge is off for this repo` | it is not merged: it is short of nothing else, and the repo has a `merge-off` file. It is the user's to merge |
| `wait <number> <url>: another home's` | its brief's `Home:` line names another home of this repo, and while `$H/home-thread` holds an id a home merges its own. `--all` merges those too: add it only on the user's word |
| `wait: could not ask GitHub` | nothing was looked at |

Ready means all of these hold.
The rules are in `features/jmerge/src/jmerge/ready.py`, and nowhere else:

- its base is the default branch. A pull request based on another branch would be merged into that branch, and nothing of it would reach the default one: the line is `wait <number> <url>: its base is <branch>, not <default branch>`, and no flag lifts it;
- its brief has no `Stack:` line in its head, or the user said to land that stack. A stack is landed by the user: the line is `wait <number> <url>: it is in the stack <name>, which the user lands`, and `--land <name>` lifts it, for that stack alone. A `Stack:` line with no name is held, and no `--land` lifts it;
- the brief has a `## Review` section, so a review was written. A brief with `Review: none` gets no review, so it is never ready: it needs the user's word;
- the review is clean, or the crewmate's Result has its `Fixed:` line;
- the head is the commit the `Fixed:` line names, and after findings that is not the head the review saw: a fix is a push. A crewmate that declines every finding writes `Fixed: none needed`. With `Fixed: none needed`, or a clean review and no `Fixed:` line, it is the head the review saw, or the commit the Result's `Rebase:` line ends on. A `Rebase:` line with no commit, as older briefs have, is not ready: a push the command cannot account for reads as not ready;
- a `Rebase:` line that says `patch unchanged, before <commit>, head <commit>` is true: `jmerge` works out the patch-id of the base-to-head diff at both commits, in the main checkout, and waits when the two differ or when it cannot work one out (a commit that is not in the checkout). A line that says `patch changed in <files>` does not hold the merge, since a review stands after a rebase: the `ready` or `merged` line says `the rebase changed the patch in <files>`, unless a review was written of the head the rebase ended on or of the head it is merged at. A line in the older shape, `range-diff empty` or `changed <files>`, is read for its last word alone;
- the fix is reviewed where it must be: a fix that changes a file outside `tests/` gets one scoped review. A Result with the line `Scoped review: needed since <head>` is not ready until the brief has a review of a later head and every finding of every review has its `Finding:` line. That review counts as the review in the lines above. A fix under `tests/` only is not reviewed. A brief from before the scoped review has `Second pass: needed since <head>` and is read the same way;
- the check named `check` passed at its head, whatever the other checks say. It is the job the repo's workflow runs the check command in. A `check` that failed, has not finished, was skipped or is not among the checks has not passed, and the line is `wait <number> <url>: check has not passed`. Nothing stands in for it: a pull request whose checks did not run is not green, whatever its Result says of a check command that passed in the crewmate's worktree, an older `CI: did not run` line included;
- GitHub says `MERGEABLE`.

Two more things keep a ready pull request from the command, and only the user lifts them. They are looked at last, so each is said of a pull request that is short of nothing else:

- it changes no protected path.
  The patterns are in `features/jmerge/src/jmerge/protected.txt`, one per line, `#` for a comment: `secrets/`, `.env`, `.env.*`, `*.pem`, `*.key`, the two lists themselves, `/features/jmerge/src/jmerge/protected.txt` and `/features/jmerge/src/jmerge/guarded.txt`, and `/policy/` and `/dns/` at the root of a repo, where a change applies to the live tailnet policy or DNS records.
  A pattern that ends in `/` is a directory and covers everything under it, from the root of the repo when it has another `/` in it and at any depth when it has none.
  Any other pattern is a file: a name at any depth, or with a `/` in it the whole path from the root, as `features/jbus/src/jbus/merge.py`.
  A `*` matches within one part of a path.
  `jmerge` refuses to run, and merges nothing, while that file, `guarded.txt` or `ci-paths.txt` is missing or has a pattern it cannot read (`**`, a leading `!`): no line there is taken and ignored.
  The line is `hold <number> <url>: needs <the user's name>, touches <first matching path>`, with the name `jmerge` reads from `~/.config/jstack/config.toml` (`user` where that file names none), and no flag lifts it, `--all` and `--land` included.
  A rename changes both its paths: one into or out of a protected path is held as an edit there is, and one between two paths that are not protected is not.
  GitHub lists a rename under its new path alone, so `jmerge` asks for the paths the renames left, of a pull request that has one and is short of nothing else.
  GitHub must have said every path the pull request changes: one whose file list it cut short is held, and so is one whose renames it would not give the old paths of.
  To protect or guard another path, a pull request adds a line to `protected.txt` or `guarded.txt`, and since it changes one of the two lists the user merges it;
- the repo's merge is on. Every repo is on until `$H/merge-off` is there: `/nohome merge` makes the file and `/nohome merge on` removes it. With it, the line is `wait <number> <url>: auto-merge is off for this repo`, whoever runs the command, a home or `jbus`.

A pull request that changes a path listed in `features/jmerge/src/jmerge/guarded.txt`, and no protected one, is merged by `jmerge` itself, under the stricter gate that `features/jmerge/docs/jmerge.md` gives under "Protected and guarded paths".

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

To see what is ready and merge nothing, run the merge step with `flags='--check'` in place of its `flags=''` line, on `home merges`: on `jbus merges` the `jmerge` line is not reached, and the merge step's own lines say what waits. It prints `ready <number> <head> <branch> <slug>` in place of merging. A pull request that is held, or whose repo's merge is off, is printed as it is without the flag: it is not `ready`.

To land a stack, run the merge step with `flags='--land <name>'` in place of its `flags=''` line, the stack's name in place of the words in angle brackets: one run, which reads the log and sets the mark as every merge step does. To see what would land and merge nothing, it is `flags='--check --land <name>'`. It is run on the user's word only: "land <name>", said in this thread. No `fixed and green` line, no tick and no start of a home runs it.

On `jbus merges` the merge step then prints `not landed` before its other lines, and nothing was run: jbus never adds `--land`.
End the turn with `stop local <name>: landing the stack needs an id in $H/home-thread, which only the user writes` ("How a turn ends"), and do nothing more.
On `home merges`, `--land` lifts the second wait for the pull requests whose `Stack:` line names that stack, and nothing else: each is merged as any other, when it is ready and its base is the default branch.
So one run lands the bottom link and prints `its base is <branch>, not <default branch>` for every link above it.
The merged link's remote branch stays while a pull request is based on it, and its line says so under `kept:`.
`jmerge` changes no base, and prints nothing that says a new base is the next step: "A stack the user lands" has it, and the playbook `shipping` has the steps in order.

A merge clears up after itself only when all is clean at that moment. What is left then, and what never had a merge by this command, is the sweep's: a `kept:` of a merge, a pull request merged by hand, a crewmate that ended with no pull request, a scout's worktree, the gate's ref. The same command does it, with no model. Run it once at the start of a home, after the merge step, from the main checkout, in one call with the block at the top and the block of "Who merges":

```sh
case ${merges:?run the block of "Who merges" first} in
home) uv run --project "$T/.." jmerge --sweep ;;
*) echo "no sweep: jbus merges here, and this home runs no jmerge" ;;
esac
```

On `no sweep`, nothing was run and there are no lists to act on. On `home merges`, it looks at each branch a brief in `$H/tasks` or a request in `$H/scouts` names, a crewmate's `<slug>` and a scout's `scout-<slug>`, with its worktree under `~/.t3/worktrees/<repo>`, and at every other worktree there. It prints two lists, the first one removed, and appends the same lines, dated, to `$H/merge.log`:

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
