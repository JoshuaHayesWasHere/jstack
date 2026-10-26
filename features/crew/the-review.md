## The review

A pull request gets one review, and the crewmate that opened it starts it: nobody types `/pr-review`. The review itself is done by a reviewer, in a new thread. This thread only launches it. A fix that changes a file outside `tests/` gets one scoped review, of the fix alone, and that is the last: see "A second pass".

The time to launch is when the pull request is open, straight after the Result names it, and not when it is green: the review runs beside CI. It goes by the first word the block of "The checks" prints then. On `passed` or `wait`, launch at once, in the turn that opened the pull request: the launch never waits for green. On `failed`, a red pull request is fixed first, and the reviewer is launched on the push that fixes it, without waiting for that push to turn green. On `unrun` no check ran, and no reviewer is launched: "The checks" parks it as a gate. Green is still what `jmerge` merges on, and what a pull request with no reviewer waits for: where the block below prints `none`, or the session has no launch tool, the `Reviewer: none` line and its message to the home are written on `passed` and not before.

Which of these it is, is what this prints, run with the first line of what the block of "The checks" printed in place of the words in angle brackets:

```sh
checked='<the line the block of "The checks" printed>'
case ${checked%%:*} in
passed) echo "launch: run the block below and do what it prints" ;;
wait) echo "launch beside the checks: run the block below, and launch now if it says to; any other answer waits for passed" ;;
failed) echo "fix first: do what \"The checks\" says, and launch on the push" ;;
unrun) echo "no launch: no check ran, park the gate" ;;
*) echo "not known: run the block of \"The checks\" first" ;;
esac
```

What decides whether there is a reviewer to launch is this, run with the block at the top. It is the only check: do not go by what you remember of earlier messages.

```sh
B="$H/tasks/<slug>.md"
mode=$(awk '/^Review:/ {print $(2); exit}' "$B")
case $mode in
none | after | twice) ;;
*) mode=review ;;
esac
if [ "$mode" = none ]; then
    echo "none: launch no reviewer, the brief asks for no review"
elif grep -qE '^(## Review$|Reviewer:)' "$B"; then
    echo "$mode: launch no reviewer, this pull request has had its one"
else
    echo "$mode: launch a reviewer"
fi
```

It prints the brief's mode, then what to do.
The mode is the brief's `Review:` line, the first line that starts with it: `none`, `after`, `twice`, or `review` for anything else.
A brief with no such line is `review`, and so is one whose line says more than `review`, as briefs from before the reviewer stopped running tests do.
The same words inside the task's text or a result do not count.

- `none: launch no reviewer`: the home wrote that the task gets no review. Add the line `Reviewer: none, the brief says Review: none` to the Result, once, and tell the home, as "With no reviewer" below says: on a later message the line is already there. Then go on as "Stay on the pull request" says. There will be no findings and no `Fixed:` line, and `jmerge` does not merge it, whoever runs it: the pull request waits for the user's word.
- `review`, and `launch no reviewer`: a review has been written (`## Review`), or the Result has a `Reviewer:` line because this thread launched one before. A reviewer of such a line that ended its turn writing nothing is sent back to work with `/pr-review run <slug> again`, never the plain line: `$T/rerun.md` is the one statement of why, and jbus's nudge for it reads the same file. Write what you sent in the Result as `Woke: jbus, sent <that line>`.
- `after`: launch the reviewer as for `review`, and do not wait for it.
  The pull request merges once its check passes, and the reviewer turns its findings into a cleanup row, `cleanup-<slug>`, a follow-up that `jbus queue add` approves by the home's follow-up rule, so no findings come to this thread and the Result gets no `Finding` lines and no `Fixed:` line.
  While a home merges, jbus wakes this thread when every check has passed, and on `passed` it sends the thread that hears of a pull request ("Telling the home") one line, once for a head: `<slug>: <pull request url> at <full head commit> is green, and its brief says Review: after`.
- `twice`: launch the reviewer as for `review`, and handle its findings in one fix round as below, with no block of "A second pass" and no `Second pass:` or `Scoped review:` line.
  Once the `Fixed:` line names the head you pushed, launch the second review of that head as a second pass is launched, `/pr-review run <slug> again`, and add `Second reviewer: <threadId> #1` to the Result; after `Fixed: none needed` nothing changed, and no second review is owed.
  Fix nothing for the second review: its reviewer files its `warning` and `error` findings as a cleanup row, `cleanup-<slug>`, drops its `info` ones, and sends you one line, which you add to the Result as `Second review: <k> warning or error findings filed as cleanup-<slug>, <m> info dropped`, or `Second review: none filed, <m> info dropped` where it filed nothing.
  `jmerge` merges once the second review is written, whatever it found, and the `fixed and green` line below is sent once it is.
- `review`, and `launch a reviewer`: launch one for each line of the role map's review list, `jroles review`, or one where it lists none. The mode is not passed on: the reviewer reads the same line. It runs no test step and no suite, whatever the line says: what it does is under "The review" of the pr-review skill.

To launch them, do it the way `$T/../skills/pr-review/SKILL.md` "Launching" says for `/pr-review` typed in a crewmate's thread: each line `jroles review` prints is one reviewer, told its number.
Then add one line `Reviewer: <threadId> #<n>` to the Result for each, in the order they were launched, `<n>` the number its message gave it, and go on as "Stay on the pull request" says.
Do not wait for the reviewer or read its thread.

Each launch this section or "A second pass" makes runs `jroles review` as `uv run --project "$T/../source" jroles review --thread <thread id>`, with this thread's own id, which the `t3-code` server's `t3_thread_configuration` gives as `threadId`.
When it exits 75 and prints no JSON, every instance of the review pool is capped, and it has registered this thread as a waiter until the cap's end, in the line it prints.
Then make no launch and add no `Reviewer:` line, and end your turn at once with one line: `Waiting on the review pool: jbus will wake this thread when its cap ends.`
Never poll for the reset, never wait in a background job, and never count on a nudge from jbus's other messages: `jbus poll` sends this thread one message once the cap's end has passed, and that message is the wake.
On it, make the same launch again.
If the pool is capped again by then, the run registers this thread again and you stop again: each wait is woken once.

If the session has no `t3_thread_launch`, write `Reviewer: none, no launch tool in this session` in its place, tell the home as below, and go on the same way.

A pull request with no reviewer never turns ready and sends no `fixed and green` line, and this thread is idle, not `waiting`: nobody would know it is open. So it tells the home, once. Run this before adding the `Reviewer: none` line, with the block at the top:

```sh
B="$H/tasks/<slug>.md"
if grep -q '^Reviewer: none' "$B"; then
    echo "send nothing: the home was told of this pull request when that line was written"
else
    echo "tell the home: it is green and has no review"
fi
```

On `tell the home`, add the line, then send the thread that hears of a pull request ("Telling the home") one line: `<slug>: <pull request url> at <full head commit> is green and has no review (<the brief says Review: none, or no launch tool in this session>): it waits for the user's word`. The pull request is green by now, since that is when this section is reached. On `send nothing`, the line is there and the home has been told, or jbus merges and it was not to be: one message, not one per wake.

The findings come back as a message in this thread, one from each reviewer. With more than one reviewer, push nothing for the findings until each has written its section: the block below prints `wait` until then, and on it end your turn, since the last reviewer's message wakes this thread. Then the findings of all of them are handled together, and pushed once. The reviewer sends it to the thread on the brief's `Thread:` line, home or no home. When the reviewer could not send it, jbus does, once, and that message begins `jbus: the reviewer could not deliver these findings.` and holds the `## Review` section whole: it is the same wake. Fix what you agree with and say here why for the rest, each by its severity as below. Then run the check command, push, add one line to the Result saying what woke you and what you did, and end your turn again. Handling the findings sends the home nothing. A finding that needs the user's word is settled on a default and parked as a gate ("Do the task"): it is fixed or not fixed by that default, and does not hold up the `Fixed:` line.
After that push, run the block of "Do the task" that asks `jmerge --scope` again, and give each `outside:` file it prints a `Wider:` line in the last Result, or take the file back out and push again.

Every finding ends one of two ways, and none is left unanswered. The findings have ids, `F1`, `F2`, ..., which no reviewer writes: two reviewers' findings of one place are one id, and this lists them, merged and triaged, each with its bucket, its reviewers and the answer it has so far. Run it with the block at the top:

```sh
uv run --project "$T/../source" jbriefs --findings "$H/tasks/<slug>.md"
```

Add one line to the Result for each finding it lists as `[Act on]` or `[Consider]`, by its id, in one of these two shapes:

- `Finding F<n>: fixed, <the finding in a few words>`;
- `Finding F<n>: not fixed, <the finding in a few words>, because <the reason, in one line>`.

A finding listed `[Dismissed]` or `[Noted]` was not sent and asks for no line. One listed as `contradicts: F<n>` is another reviewer's dismissal of that finding, printed beside it: weigh it when you answer that one. A review written before the ids, whose findings have no bucket, is answered as before, `Finding: fixed, ...` or `Finding: not fixed, ..., because ...`, in order: those lines go to its findings by count. An answer with no id answers no finding that has a bucket.

A reason says why the pull request is right as it is, or where the finding went: "I disagree" is not one. For an `Act on` finding, the one bucket that holds the merge, a decline counts only where its reason cites a `path:line`, a command in backticks, or the gate it is parked on as `question <n>` with the Result's `Gate: question <n>` line, and only where no other finding was declined for the same reason: `jmerge` waits on each one that does not, by id. A finding the reviewer marked `for Noticed, not this pull request` asks for no fix here: write it in the Result under "Noticed", and end it `not fixed`, with the reason that its remedy is outside the brief's `Where`, naming the `Where:` line's file it falls outside. A finding parked as a gate ends by its default: `fixed`, or `not fixed` with the reason that the default leaves the pull request as it is and `question <n>` holds it.

A finding tagged `(risk: <area>)`, on security, auth, billing, data, migrations or concurrency, holds the merge whatever its bucket, a `Consider` one too, and is not declined by this thread alone: the `Consider` default below does not apply to it. Where you would decline it, park it as a gate ("Do the task") whose default, the one you take, is "fix it": fix it and end it `fixed`. Where the user answers that it stays, end it `Finding F<n>: not fixed, ..., because question <n>: <the answer>`. `jmerge` waits on a risky decline that names no such gate. No other finding asks the user anything.

A finding's bucket is the lead's reading, and it sets the default; its severity is a field and decides nothing. An `Act on` finding is handled as above: fixed, or not fixed with a reason of its own. A `Consider` finding is declined by default: end it `Finding F<n>: not fixed, <the finding in a few words>, because consider: left for a follow-up`, and add it to the Result under "Noticed", one line for each, as `follow-up: <the finding as the reviewer wrote it>`. Fix one only when the fix is inside the lines the finding names, adds no test and touches no other file. A review from before the buckets is read by severity the same way: an `info` finding there is declined by default, `Finding: not fixed, <the finding in a few words>, because info: left for a follow-up`. A review whose findings are all declined pushes nothing, and the block below says `write Fixed: none needed`. The findings of a second pass and of a scoped review are handled the same way.

Then run this, with the block at the top. It reads the same list, and says what is left:

```sh
uv run --project "$T/../source" jbriefs --findings "$H/tasks/<slug>.md" --left
```

On `wait`, the reviewer has sent its message and not yet written its section: handle the findings, and run it again before the `Fixed:` line. On `wait: <k> of <n> reviewers`, a reviewer has not written yet: push nothing and end your turn, as above. On `not yet`, a finding has no answer that counts: the ids after its colon are the ones, each with why its answer is refused where it has one, and a review from before the ids names none. Give each its line. Otherwise it says which `Fixed:` line to write. After a second pass or a scoped review the findings of every review are listed, and the earlier answers stay: add the new ones under them. The sections of one head are one review, one from each reviewer. Where the last review has findings and none of them is fixed, it says `none needed` whatever an earlier pass fixed. The answers say what became of each finding, and the `Fixed:` line says once, for the whole review, that all of them are handled and at which head. `jmerge` reads both: it merges on the `Fixed:` line, and waits, on every path, until each `Act on` finding has an answer that counts.

When the findings are handled, which is when the block says `write Fixed:`, and not before, first run the block of "A second pass" and add the `Second pass:` line it prints. Then add one line to the Result in one of these two shapes. It is what tells "fixed" from "findings sent, not fixed yet", and `jmerge` merges on it (run by jbus, or by a home while `home-thread` holds an id):
Before it, run the check command at that head (in jstack `make check-fast BASE=origin/main`), add `Checked: <the command> exit <its exit> at <the full head>` to the Result, and write `Fixed:` only after exit 0 there, since `jmerge` marks the draft ready on the `Fixed:` line and CI's run must not be the first check that head gets.

- `Fixed: <full commit>`: the head you pushed, from `git rev-parse HEAD` after the push;
- `Fixed: none needed, <reason>`: after a clean review, or when you decline every finding. Nothing was pushed.

The Result has one `Fixed:` line. If you push again for a failed check after writing it with a commit, set it to the new head. A rebase leaves it as it is: `jmerge` compares the rebased head with the commit that line names ("A conflict").

While the home merges, nothing else brings it back to the pull request, so tell it when the pull request is fixed and green. Send the thread that hears of a pull request ("Telling the home") one line: `<slug>: <pull request url> at <full head commit> is fixed and green`. With no home, or while jbus merges, send nothing: `jmerge`, run by jbus, reads the `Fixed:` line from the brief on its next pass. It is sent only when the block of "A second pass" prints `none`, or prints `had` with the second pass's findings handled: on `needed`, on `scoped` and on `write Scoped review:` the pull request is not ready, and the home would be woken to a `wait`. The time to send it:

- after `Fixed: <full commit>`: on jbus's message that every check passed at that head. It comes again for each later head that turns green, since the head has moved;
- after `Fixed: none needed`: the same, on jbus's message that every check passed at the head, whether or not it was green when the line was written.

Where no check ran, the head is not green and the line is not sent: "The checks" parks it as a gate.
