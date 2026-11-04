## The review

A pull request gets one review, and the crewmate that opened it starts it: nobody types `/pr-review`.
The review itself is done by a reviewer, in a new thread.
This thread only launches it.
A fix pushed for its findings gets no review: one round, and the pull request merges on its checks once each blocking finding has its answer.
The one later pass is the one a `Meets the brief: no` owes: see "A second pass".

The time to launch is when `check` has passed at the pull request's head: the deterministic checks prove or fail the work first, and the reviewer reads only a head they passed.
It goes by the first word the block of "The checks" prints.
On `passed`, launch at once, in that turn.
On `wait`, the checks still run: launch nothing, and end the turn, since jbus says when every check has passed.
On `failed`, a red pull request is fixed first, and the reviewer is launched once the push that fixes it has passed.
On `unrun` no check ran, and no reviewer is launched: "The checks" parks it as a gate.
Where the block below prints `none`, or the session has no launch tool, the `Reviewer: none` line and its message to the home are written on `passed` too.

Which of these it is, is what this prints, run with the first line of what the block of "The checks" printed in place of the words in angle brackets:

```sh
checked='<the line the block of "The checks" printed>'
case ${checked%%:*} in
passed) echo "launch: run the block below and do what it prints" ;;
wait) echo "no launch yet: the checks still run, and the reviewer is launched once they have passed" ;;
failed) echo "fix first: do what \"The checks\" says, and launch once the push has passed" ;;
unrun) echo "no launch: no check ran, park the gate" ;;
*) echo "not known: run the block of \"The checks\" first" ;;
esac
```

What decides whether there is a reviewer to launch is this, run with the block at the top. It is the only check: do not go by what you remember of earlier messages.

```sh
B="$H/tasks/<slug>.md"
mode=$(awk '/^Review:/ {print $(2); exit}' "$B")
case $mode in
none | cleanup) ;;
*) mode=review ;;
esac
if [ "$mode" = none ]; then
    echo "none: launch no reviewer, the brief asks for no review"
elif awk '/^## Result/ {result = 1} result && /^(## Review$|Reviewer:)/ {had = 1} END {exit !had}' "$B"; then
    echo "$mode: launch no reviewer, this pull request has had its one"
else
    echo "$mode: launch a reviewer"
fi
```

It prints the brief's mode, then what to do.
The mode is the brief's `Review:` line, the first line that starts with it: `none`, `cleanup`, or `review` for anything else, an old `after` or `twice` included.
A brief with no such line is `review`, and so is one whose line says more than `review`, as briefs from before the reviewer stopped running tests do.
The same words inside the task's text or a result do not count.
A `## Review` or `Reviewer:` line counts only at or after the first `## Result`: a `Reviewer:` line in the brief's head is the home's guidance for the reviewer, not a reviewer.

- `none: launch no reviewer`: the home wrote that the task gets no review. Add the line `Reviewer: none, the brief says Review: none` to the Result, once, and tell the home, as "With no reviewer" below says: on a later message the line is already there. Then go on as "Stay on the pull request" says. There will be no findings and no `Fixed:` line, and `jmerge` does not merge it, whoever runs it: the pull request waits for the user's word.
- `review`, and `launch no reviewer`: a review has been written (`## Review`), or the Result has a `Reviewer:` line because this thread launched one before. A reviewer of such a line that ended its turn writing nothing is sent back to work with `/pr-review run <slug> again`, never the plain line: `$T/rerun.md` is the one statement of why, and jbus's nudge for it reads the same file. Write what you sent in the Result as `Woke: jbus, sent <that line>`.
- `cleanup`: the brief is the day's warnings row, `warnings-<day>`, which jbus filed, and it gets one review, of its own diff alone.
  Launch the reviewer as for `review`, and handle its findings in one fix round as below, with no block of "A second pass" and no `Second pass:` or `Scoped review:` line: a fix for them gets no review.
  Only an `error` of that review comes to this thread, whatever its bucket or tag, and every other finding is dropped, so a review with no error asks no line of you and `jmerge` merges it on its checks.
  No finding of it goes to another day's row, so no follow-up of a follow-up is queued.
  The `fixed and green` line below is sent once the `Fixed:` line is written, with no block of "A second pass" run for it.
- `review`, and `launch a reviewer`: launch one for each line of the role map's review list, `jroles review`, or one where it lists none. The mode is not passed on: the reviewer reads the same line. It runs no test step and no suite, whatever the line says: what it does is under "The review" of the pr-review skill.

To launch them, run the block below, and make one `t3_thread_launch` call for each `launch:` line it prints, with the JSON after `launch: ` as the call's arguments, as printed: `$T/../skills/pr-review/launching.md` says what a reviewer does with its number.
Never write a launch's arguments by hand: with no `workspaceStrategy` the reviewer opens in the project's main checkout and refuses to run there, and the block gives each call this worktree and its branch.
Then add one line `Reviewer: <threadId> #<n>` to the Result for each, in the order they were launched, `<n>` the number its message gave it, and go on as "Stay on the pull request" says.
Do not wait for the reviewer or read its thread.

Each launch this section or "A second pass" makes runs `jroles review` as `uv run --project "$T/../source" jroles review --thread <thread id>`, with this thread's own id, which the `t3-code` server's `t3_thread_configure` with no arguments gives as `threadId`.
The block runs it, in this worktree, with that id in place of `<thread id>`, `first` or `scoped` in place of `<pass>`, and for a scoped pass the message "A second pass" gives, whole, in place of `<message>`:

```sh
thread='<thread id>'
pass='<pass>'
message='<message>'
top=$(git rev-parse --show-toplevel 2> /dev/null)
branch=$(git branch --show-current 2> /dev/null)
case $pass in
first) title='review: <slug>, $n' said='/pr-review run <slug> $n' ;;
scoped)
    title='review: <slug>, scoped' said=$message
    case $message in '' | '<'*) title= ;; esac
    ;;
*) title= ;;
esac
case $thread in '' | '<'*) title= ;; esac
if [ -z "$title" ]; then
    echo "not filled in: put this thread's id in place of <thread id>, first or scoped in place of <pass>, and for scoped the message in place of <message>"
elif [ -z "$top" ] || [ -z "$branch" ]; then
    echo "no launch: this thread is in no worktree on a branch, and a reviewer runs in the crew's worktree"
else
    selections=$(uv run --project "$T/../source" jroles review --thread "$thread")
    code=$?
    if [ "$code" -eq 75 ]; then
        echo "capped: launch nothing and add no Reviewer: line"
    elif [ "$code" -ne 0 ]; then
        echo "no launch: jroles review ended $code"
    else
        printf '%s\n' "$selections" | grep -q '^{' || selections=null
        [ "$pass" = first ] || selections=$(printf '%s\n' "$selections" | grep -m 1 .)
        printf '%s\n' "$selections" | grep . | jq -cn --arg top "$top" --arg branch "$branch" \
            --arg title "$title" --arg said "$said" '
            [inputs] | to_entries[] | (.key + 1 | tostring) as $n
            | {title: ($title | sub("\\$n"; $n)),
               workspaceStrategy: {type: "existing_worktree", worktreePath: $top, branch: $branch},
               message: ($said | sub("\\$n"; $n))}
              + (if .value == null then {} else {modelSelection: .value} end)' |
            sed 's/^/launch: /'
    fi
fi
```

On `capped`, every instance of the review pool is capped, and `jroles` has registered this thread as a waiter until the cap's end, in the line it printed.
End your turn at once with one line: `Waiting on the review pool: jbus will wake this thread when its cap ends.`
Never poll for the reset, never wait in a background job, and never count on a nudge from jbus's other messages: `jbus poll` sends this thread one message once the cap's end has passed, and that message is the wake.
On it, run the block again.
If the pool is capped again by then, the run registers this thread again and you stop again: each wait is woken once.
On `no launch`, make none, and add what it printed to the Result.

If the session has no `t3_thread_launch`, write `Reviewer: none, no launch tool in this session` in its place, tell the home as below, and go on the same way.

A pull request with no reviewer is never merged and sends no `fixed and green` line, and this thread is idle, not `waiting`: nobody would know it is open.
So it tells the home, once.
Run this before adding the `Reviewer: none` line, with the block at the top:

```sh
B="$H/tasks/<slug>.md"
if awk '/^## Result/ {result = 1} result && /^Reviewer: none/ {had = 1} END {exit !had}' "$B"; then
    echo "send nothing: the home was told of this pull request when that line was written"
else
    echo "tell the home: it is green and has no review"
fi
```

On `tell the home`, add the line, then send the thread that hears of a pull request ("Telling the home") one line: `<slug>: <pull request url> at <full head commit> is green and has no review (<the brief says Review: none, or no launch tool in this session>): it waits for the user's word`. The pull request is green by now, since that is when this section is reached. On `send nothing`, the line is there and the home has been told, or jbus merges and it was not to be: one message, not one per wake.
A pull request whose brief says `Review: none` is parked as no gate: `jmerge` holds it for the user's word and jbus lists it under Needs you, so `jbus gate` refuses that line as `settled`.

The findings come as one message in this thread, from jbus and not from the reviewer, which writes its section in the brief and sends nothing.
The message comes once every reviewer of the head has written its section and `jmerge` says the pull request waits on your answers, so the findings of all of them are handled together, and pushed once.
It begins `jbus: <slug>'s pull request #<n> at <head12> has its review`, names the sections by their `By:` lines, and lists the findings by id.
A clean review brings no message and asks no line of you: `jmerge` merges it once it is green.
Fix what you agree with and say here why for the rest, each by its severity as below.
Then run the check command, push with the block below that pushes a fix, add one line to the Result saying what woke you and what you did, and end your turn again.
Handling the findings sends the home nothing.
A finding that needs the user's word is settled on a default and parked as a gate ("Do the task"): it is fixed or not fixed by that default, and does not hold up the `Fixed:` line.

Every finding ends one of two ways, and none is left unanswered. The findings have ids, `F1`, `F2`, ..., which no reviewer writes: two reviewers' findings of one place are one id, and this lists them, merged and triaged, each with its bucket, its reviewers and the answer it has so far. Run it with the block at the top:

```sh
uv run --project "$T/../source" jbriefs --findings "$H/tasks/<slug>.md"
```

Add one line to the Result for each finding it lists as `[Act on]` or `[Consider]`, by its id, in one of these two shapes:

- `Finding F<n>: fixed, <the finding in a few words>`;
- `Finding F<n>: not fixed, <the finding in a few words>, because <the reason, in one line>`.

A finding listed `[Dismissed]` or `[Noted]` was not sent and asks for no line. One listed as `contradicts: F<n>` is another reviewer's dismissal of that finding, printed beside it: weigh it when you answer that one. A review written before the ids, whose findings have no bucket, is answered as before, `Finding: fixed, ...` or `Finding: not fixed, ..., because ...`, in order: those lines go to its findings by count. An answer with no id answers no finding that has a bucket.

A reason says why the pull request is right as it is, or where the finding went: "I disagree" is not one.
For an `Act on` finding, the one bucket that holds the merge, a decline counts only where its reason cites a `path:line`, a command in backticks, or the gate it is parked on as `question <n>` with the Result's `Gate: question <n>` line, and only where no other finding was declined for the same reason: `jmerge` waits on each one that does not, by id.
A blocking finding carries its evidence in a `(proof: ...)` tag: a command that exited non-zero at the head, a check that failed, a doc line the pull request made wrong, or an unmet `Done when` line.
One that `jbriefs --findings` lists with `proof: none` shows nothing a run, a check or a doc can show: it still waits for its answer by id, and a decline of it counts with any reason, a risky one still on its gate.
The section's `Outside Where:` line is no finding and asks for no line: it is what `jmerge --scope` printed, which anyone can run again.
A finding the reviewer marked `outside Where, not this pull request` asks for no fix here: queue it as `$T/a-fault-outside.md` says, or leave it when its fix is not known, and end it `not fixed`, with the reason that its remedy is outside the brief's `Where`, naming the `Where:` line's file it falls outside.
A finding parked as a gate ends by its default: `fixed`, or `not fixed` with the reason that the default leaves the pull request as it is and `question <n>` holds it.

A finding tagged `(risk: <area>)`, on security, auth, billing, data, migrations or concurrency, holds the merge whatever its bucket, a `Consider` one too, and is not declined by this thread alone: the `Consider` default below does not apply to it. Where you would decline it, park it as a gate ("Do the task") whose default, the one you take, is "fix it": fix it and end it `fixed`. Where the user answers that it stays, end it `Finding F<n>: not fixed, ..., because question <n>: <the answer>`. `jmerge` waits on a risky decline that names no such gate. No other finding asks the user anything.

In a first review, a finding's bucket is the lead's reading, and it sets the default; its severity is a field and decides nothing.
After the first review, the severity alone decides, as the reviewer wrote it: the scoped review a `Meets the brief: no` owes, or a rebase's, sends this thread its `error` findings, whatever their bucket or tag, and each is answered and fixed as an `Act on` one is.
Its `warning` findings go to the day's warnings row, `warnings-<day>`, which jbus files from the briefs once the pull request merged (`jbus.daywarnings`), and its `info` findings are dropped.
No bucket, `Act on` included, and no `(risk: <area>)` tag brings a warning or an info back into this pull request, and no fix push is owed for one.
An `Act on` finding is handled as above: fixed, or not fixed with a reason of its own.
A `Consider` finding is declined by default: end it `Finding F<n>: not fixed, <the finding in a few words>, because consider: left for a follow-up`.
One worth doing later is a row, queued as `$T/a-fault-outside.md` says, and any other is nothing.
Fix one only when the fix is inside the lines the finding names, adds no test and touches no other file.
A review from before the buckets is read by severity the same way: an `info` finding there is declined by default, `Finding: not fixed, <the finding in a few words>, because info: left for a follow-up`.
A review whose findings are all declined pushes nothing, and the block below says `write Fixed: none needed`.
The errors of a scoped review are handled the same way.

Then run this, with the block at the top. It reads the same list, and says what is left:

```sh
uv run --project "$T/../source" jbriefs --findings "$H/tasks/<slug>.md" --left
```

On `wait`, no review is written yet: end your turn, since jbus's message is the wake.
On `wait: <k> of <n> reviewers`, a reviewer has not written yet: push nothing and end your turn, as above.
On `write nothing`, the last review is a later one that sent this thread no finding: write no answer and leave the `Fixed:` line as it is.
On `not yet`, a finding has no answer that counts: the ids after its colon are the ones, each with why its answer is refused where it has one, and a review from before the ids names none.
Give each its line.
Otherwise it says which `Fixed:` line to write.
After a scoped review the findings of every review are listed, and the earlier answers stay: add the new ones under them.
The sections of one head are one review, one from each reviewer.
Where the last review has findings and none of them is fixed, it says `none needed` whatever an earlier pass fixed.
The answers say what became of each finding, and the `Fixed:` line says once, for the whole review, that all of them are handled and at which head.
`jmerge` reads both: it merges on the `Fixed:` line, and waits, on every path, until each `Act on` finding has an answer that counts.

`jmerge` also reads each review's `Meets the brief:` line, the reviewer's typed judgement of the brief, and the one rule is this.
The pull request does not merge while the last round's line says `no`, or a section of that round has no line of the template's shape, or a count that is not the brief's (`jbriefs --meets <brief>` prints what `jmerge` reads).
A `no` owes you a fix for each unmet line and a scoped review whose own line says `yes`: the block of "A second pass" gives that review, whatever the fix changed, also after a scoped pass, until a round says `yes`.
Never write a review's line yourself, and never rewrite one: the judgement is the reviewer's.
The only other way out is a line `Waived: <the Done when line>, <thread>/<message>` in the brief that rests on the user's own message, or the bot's word, that names this row, says it waives and quotes that line, which jbus checks: your own message, the home's, or the user's go waives nothing.

A fix is one or more new commits on the head GitHub has, never an amend, a squash or a rebase: a rewritten head is a force-push, which costs a new run and a new look at what the review saw, and a default branch that moved is no reason for one ("A conflict").
Push it with this, the one way a fix, a failed check's included, is pushed:

```sh
G=$(git rev-parse --git-dir)
branch=$(git symbolic-ref -q --short HEAD)
if [ -z "$branch" ] || ! git fetch -q origin "$branch"; then
    echo "no push: could not fetch origin's $branch"
elif ! git merge-base --is-ancestor FETCH_HEAD HEAD; then
    if [ -f "$G/crew-before-rebase" ]; then
        echo "no push: a rebase is not pushed yet, push it with the block of A conflict"
    else
        echo "no push: this head does not hold origin's $branch at $(git rev-parse FETCH_HEAD)"
    fi
elif git push -q origin "HEAD:refs/heads/$branch"; then
    echo "pushed $(git rev-parse HEAD)"
else
    echo "the push was refused: origin did not take a plain push of $branch"
fi
```

On `no push: this head does not hold`, nothing was pushed and nothing is forced, and there are three ways out by what made the head differ.
An amend or a squash goes back with `git reset --soft FETCH_HEAD`, then one `git commit`.
A rebase that no conflict asked for goes back with `git rebase --onto FETCH_HEAD <the last commit under the fix>`.
A commit GitHub added by merging the base comes in with `git merge --no-edit FETCH_HEAD`.
Where origin's head is such a merge, this is the only way out, whatever else made the head differ, since the other two would drop what the merge brought.
Then run the block again.
A rebase for a conflict is pushed by the block of "A conflict", and a fix pushed after it starts from the head that block pushed.

When the findings are handled, which is when the block says `write Fixed:`, and not before, first run the block of "A second pass" and add the `Scoped review:` line it prints.
Then add one line to the Result in one of these two shapes.
It is what tells "fixed" from "findings sent, not fixed yet", and `jmerge`, run by jbus, the only merger, merges on it:

- `Fixed: <full commit>`: the head you pushed, from `git rev-parse HEAD` after the push;
- `Fixed: none needed, <reason>`: when you decline every finding.
  Nothing was pushed.

Where that line is missing, `jmerge` reads it from git and the `Checked:` line (features/jmerge/docs/jmerge.md, "The review is done"), but write it all the same, since the blocks of this skill read it.

The Result has one `Fixed:` line. If you push again for a failed check after writing it with a commit, set it to the new head. A rebase leaves it as it is: `jmerge` compares the rebased head with the commit that line names ("A conflict").

jbus is the only merger, so no home waits to hear that the pull request is fixed and green: "Telling the home" sends the `fixed and green` line to nobody, and `jmerge`, run by jbus, reads the `Fixed:` line from the brief on its next pass, once the head is green.
Wait for no message that every check passed after a `Fixed:` line: jbus sends that message only for a brief with no reviewer launched, no `Reviewer: none` line and no `## Review` yet (`rebase.owed`, `features/jbus/src/jbus/rebase.py`).
The line is due only when the block of "A second pass" prints `none`, or prints `had` with the scoped review's findings handled: on `scoped` and on `write Scoped review:` the pull request is not ready.

Where no check ran, the head is not green and the line is not sent: "The checks" parks it as a gate.
