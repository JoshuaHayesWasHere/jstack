### A second pass

A brief that says `Review: twice` runs none of this section: its second review is the one "The review" launches after its one fix round, and on a wake that finds it green, the `fixed and green` line is sent once that review is written.

The reviewer reviews once and you fix once.
Whether anybody reviews the fix depends on what it changed, whichever files the findings named.
A fix that changes a file outside `tests/` gets one scoped review: a reviewer that reads the fix alone.
A fix that changes files under `tests/` only, or nothing, gets none: what stands behind it is the pull request's own checks.
A blocking finding you declined by id gets that scoped review all the same, also when nothing was pushed: a decline changes no line, so nothing else would look at it again, and the scoped reviewer rules on it.
That review is the last: a fix pushed for its findings gets no further review, and merges on its checks.
No fix gets a whole second review.

A path listed in `features/jmerge/src/jmerge/guarded.txt` gets the stricter gate that `features/jmerge/docs/jmerge.md` gives under "Protected and guarded paths", and jbus's message says what its fix is owed.

What decides is this, run with the block at the top, in this worktree. Run it once the findings are handled and the fix, if there is one, is pushed, before the `Fixed:` line is written, and on each wake that finds the pull request green after that. It is the only check:

```sh
B="$H/tasks/<slug>.md"
read -r passes saw written declined << EOF
$(uv run --project "$T/.." jbriefs --findings "$B" --rounds)
EOF
declined=${declined:--}
read -r decided since launched asked sent stopped ruled here ran << EOF
$(awk -v written="$written" -v head="$(git rev-parse HEAD 2> /dev/null)" '
    BEGIN {split(written, heads, ","); for (one in heads) seen[heads[one]]}
    function close_section() {if (section && scope && pass && at == head) ran++; section = scope = pass = 0; at = ""}
    /^## / {close_section(); section = ($(0) == "## Review")}
    section && /^Scope:/ {scope = 1}
    section && /^Verdict: (clean|findings)$/ {pass = 1}
    section && /^Head:/ {at = $(2)}
    /^Second pass:/ {decided = $(3); sub(/,$/, "", decided); since = $(5); sub(/,$/, "", since)}
    /^Second reviewer:/ {launched = "yes"}
    /^Scoped review: / {ruled = $(3); sub(/,$/, "", ruled)}
    /^Scoped review: needed since / {asked = $(5); sub(/,$/, "", asked)}
    /^Scoped reviewer:/ && $(NF - 1) == "of" {sent = $(NF); nobody = ($(3) ~ /^none/)}
    /^Scoped reviewer:/ && $(NF - 1) == "of" && $(NF) == head && $(3) !~ /^none/ {here++}
    function word(value, unset) {return value == "" ? unset : value}
    END {
        close_section()
        print word(decided, "-"), word(since, "-"), word(launched, "no"),
            word(asked, "-"), (nobody ? "none:" : "") word(sent, "-"),
            (sent == "" || nobody || (sent in seen)) ? "-" : sent, word(ruled, "no"),
            here + 0, ran + 0
    }' "$B")
EOF
scoped() {
    if [ "$ruled" != needed ]; then return 0; fi
    had=no
    if [ "$asked" != "$saw" ] || [ "$ran" -gt 0 ]; then had=yes; fi
    if [ "$had" = yes ] && [ "$declined" = - ]; then return 0; fi
    head=$(git rev-parse HEAD 2> /dev/null) || return 0
    base=$(git symbolic-ref -q --short refs/remotes/origin/HEAD) && from=$(git merge-base "$base" "$head" 2> /dev/null) || from=
    if [ -z "$from" ]; then
        echo "scoped: this worktree does not know its default branch, so the range of the fix cannot be given"
    elif [ "$had" = yes ] && [ "$here" -gt "$ran" ]; then
        echo "scoped: the scoped reviewer is launched, and its findings come to this thread"
    elif [ "$had" = yes ] && ! old=$(git merge-base "$base" "$saw" 2> /dev/null); then
        echo "scoped: the head the review saw, $saw, is not a commit here, so its range cannot be given"
    elif [ "$had" = yes ]; then
        echo "scoped: launch the scoped reviewer again, to rule on the declines of $(printf %s "$declined" | sed 's/,/, /g'), with /pr-review run <slug> scoped $old..$saw $from..$head"
    elif [ "$sent" = "none:$head" ]; then
        echo "scoped: no scoped reviewer could be launched for this head, and the home was told"
    elif [ "$sent" = "$head" ]; then
        echo "scoped: the scoped reviewer is launched, and its findings come to this thread"
    elif ! old=$(git merge-base "$base" "$saw" 2> /dev/null); then
        echo "scoped: the head the review saw, $saw, is not a commit here, so its range cannot be given"
    else
        again=
        if [ "$stopped" != - ]; then again=" in place of the one that stopped at $stopped"; fi
        echo "scoped: launch the scoped reviewer$again, with /pr-review run <slug> scoped $old..$saw $from..$head"
    fi
}
if [ "$decided" = needed ] && [ "$saw" != "$since" ]; then
    said=$(scoped)
    echo "${said:-had: the second pass is written, and it is the last}"
elif [ "$decided" = needed ] && [ "$launched" = yes ]; then
    echo "needed: the second reviewer is launched, and its findings come to this thread"
elif [ "$decided" = needed ]; then
    echo "needed: launch the second reviewer"
elif [ "$decided" != - ]; then
    said=$(scoped)
    echo "${said:-none: no second pass, as the Result says}"
elif [ "$passes" = 0 ]; then
    echo "wait: no review is written in the brief yet"
elif [ "$ruled" = needed ]; then
    said=$(scoped)
    echo "${said:-had: the review of the fix is written, and this head is owed none}"
elif [ "$ruled" != no ] && [ "$declined" = - ]; then
    echo "none: no review of the fix, as the Result says"
elif ! changed=$(git -c core.quotePath=false diff --name-only "$saw" HEAD 2> /dev/null); then
    echo "write Scoped review: needed since $saw, the fix could not be compared with that head"
else
    outside=$(printf '%s\n' "$changed" | awk '
        NF && !/^tests\// {n++; if (n <= 5) list = list (n > 1 ? " " : "") $(0)}
        END {if (n > 5) list = list " and " n - 5 " more"; print list}')
    if [ -n "$outside" ]; then
        echo "write Scoped review: needed since $saw, the fix changed $outside"
    elif [ "$declined" != - ]; then
        echo "write Scoped review: needed since $saw, to rule on the declines of $(printf %s "$declined" | sed 's/,/, /g')"
    elif [ -z "$changed" ]; then
        echo "write Scoped review: none, nothing was pushed for the findings"
    else
        echo "write Scoped review: none, the fix changed files under tests/ only"
    fi
fi
```

The last branches decide, once: the files that differ between the head the review saw (its `Head:` line) and the head checked out here, which is the one you pushed.
With no difference, nothing was pushed.
One file outside `tests/` is enough, and the line names the first five.
A blocking decline with no ruling is enough too, pushed or not: `jbriefs --findings --rounds` names those findings in its fourth field, and the line names them.
The scoped reviewer it launches reads the earlier findings and your answers, and rules on each decline in its section, `Declines: upheld F2` or `Declines: not upheld F3: <the disproof>`.
With nothing pushed its two ranges both end at the head the review saw, and the review of the fix is had once a scoped section that ran names the head checked out here, or a review of a later head than the `Scoped review:` line names is written.
A blocking decline still with no ruling after that, one the scoped pass's own findings brought or one it left out, launches the scoped reviewer again, with `again` in the line: add its `Scoped reviewer:` line under the others, as for the first.
The block counts, at the head checked out here, the `Scoped reviewer:` lines that name it and the scoped sections that ran with it as their `Head:`, wherever in the brief each stands: while there are more of the first, the reviewer is at work and nothing is launched.
A fix that cannot be compared with the head the review saw is owed a review.
So is a fix pushed after a rebase, since the default branch's files then differ too: that is one review too many, never one too few.
A pull request with more than one review and no `Scoped review:` line, the later one asked for after a rebase or by the user, is decided the same way, from the head the last review saw.

`scoped` gives the launch where the last `Scoped review:` line says a review is owed since the head the last review saw, and nothing anywhere else. Where a crewmate did not run this block, jbus asks in its place, once for a head, with a message that begins `jbus: the fix you pushed to pull request`, or `jbus: pull request #<n> waits on you`: do what that message says. Where jbus can give no range for an owed review, that message says to run this block, and jbus's stall ends the wait.

- `write Scoped review: ...`: add that line to the Result, as printed, and only then the `Fixed:` line. `jmerge` merges on the `Fixed:` line, so a Result never has it without the line that says whether the fix is owed a review. It is the record: from then on the block reads it and compares nothing again, so a later rebase does not change what was decided. Then run the block again and do what it says.
- `none`: no review of the fix. Go on to the `fixed and green` line.
- `scoped: launch the scoped reviewer ... with /pr-review run <slug> scoped <old range> <new range>`: launch it in the turn that pushed the fix, beside the checks, as the first review is launched: it does not wait for green. Go by the first word the block of "The checks" prints for the fixed head, and run no block of "The review": its second block counts the first reviewer and would say to launch none. On `passed` or `wait`, launch one reviewer now, the way the first was launched, as the same "Launching" section says for a scoped pass, with the message the line gives, whole. On `failed`, fix and push first, then run this block again: it gives the ranges of the head there is then. On `unrun`, launch none: "The checks" parks the gate. After the launch, add the line `Scoped reviewer: <threadId>, of <the head the message's second range ends at, in full>` to the Result, under the `Scoped review:` line, send the home nothing, and go on as "Stay on the pull request" says. Where the line says `in place of the one that stopped at <head>`, a reviewer launched for that head wrote no section, because the head moved under it: put the new line in place of that reviewer's line and do not add under it, also where a message from jbus says to add it, since "A conflict" counts every reviewer line against the sections written and would wait for the stopped one for good. If the session has no `t3_thread_launch`, write `Scoped reviewer: none, no launch tool in this session, of <that head>` and send the thread that hears of a pull request ("Telling the home") one line, once: `<slug>: <pull request url> at <full head commit> is fixed, and its scoped review could not be launched (no launch tool in this session): it waits for the user's word`.
  Its `jroles review` runs with `--thread <thread id>`, and on exit 75 this thread makes no launch and ends its turn with the one line "The review" gives for a capped pool, whatever the "Launching" section says: jbus wakes it once the cap has ended.
- `scoped: no scoped reviewer could be launched for this head`: the `Scoped reviewer: none` line is there and the home has been told. Nothing more to do: the pull request waits for the user's word.
- `scoped: the scoped reviewer is launched`: nothing to do. Its findings come as a message in this thread, and the message comes after its `## Review` is written. One that arrives while this block still prints this line has no section behind it: write no answer and no `Fixed:` line for it, because `jmerge` goes by the section and waits for it, and jbus asks for a replacement reviewer when the section stays unwritten. Handle them as a review's: an answer by id for each, and the counting block until it says `write Fixed:`. Then the `Fixed:` line is one of three: the new head, if you pushed for these findings; left as it is, after a clean scoped pass; `Fixed: none needed, <reason>`, if it had findings and you declined them all. A reviewer whose review could not be done says so in its message and writes a section with `Verdict: not run`. That section is not a review, and the block still prints this line for it: add one line to the Result saying why the review was not done, and park a gate ("Do the task"), with the default that the pull request waits. A `Scoped reviewer:` line counts for the head it names after `of` and for no other, and one that names no head counts for none. A rebase's scoped reviewer is written the same way, `Scoped reviewer: <threadId>, of <head>`, as the message from jbus says. Once the head has moved the block prints the launch line again, for the head there is now.
- `had`: the review of the fix is in the brief, as a `## Review` section of a later head than the one the `Scoped review:` line names, and its findings are handled as above. No reviewer is launched again, whatever a fix for its findings changed: the `fixed and green` line follows.
- A decline the scoped pass did not uphold, its `Declines: not upheld F<n>: <the disproof>` line, is yours to fix: fix it, push, answer it `Finding F<n>: fixed, ...`, and write `Fixed: <the head you pushed>` again.
  Declining it again does not lift the ruling, and the fix gets no further review: the scoped pass is the last.
  Where you still hold the decline, send the thread that hears of a pull request ("Telling the home") one line, `<slug>: <pull request url>, the decline of F<n> is not upheld and I hold it: <why>`, and end your turn: the home settles it with you.
  Only a finding on one of review-triage's categories, tagged `(risk: <area>)`, is the user's: `jmerge` holds it for the user, and you send nothing for it.
- `scoped: the head the review saw ... is not a commit here`, or `scoped: this worktree does not know its default branch`: no range can be given. Add what it printed to the Result and park a gate ("Do the task"), with the default that the pull request waits.

A brief from before this rule has a `Second pass:` line in its Result. The block reads it and writes none like it, and decides nothing again for such a brief:

- `none: no second pass, as the Result says`: go on to the `fixed and green` line.
- `needed: launch the second reviewer`: the line says `Second pass: needed since <head>`, and no second reviewer was launched. When the fixed head is green ("The checks"), launch one the way the first reviewer was launched, as the same "Launching" section says for a second pass, with the message `/pr-review run <slug> again`, and add the line `Second reviewer: <threadId>` to the Result. If the session has no `t3_thread_launch`, write `Second reviewer: none, no launch tool in this session` and send the thread that hears of a pull request ("Telling the home") one line, once: `<slug>: <pull request url> at <full head commit> is fixed and green, and its second pass could not be launched (no launch tool in this session): it waits for the user's word`.
  Its `jroles review` runs with `--thread <thread id>` too, and a capped pool ends the turn the same way.
- `needed: the second reviewer is launched`: nothing to do. Its findings come as a message in this thread, and a section with `Verdict: not run` is handled as a scoped reviewer's is.
- `had: the second pass is written, and it is the last`: handle its findings as a scoped review's, and launch nobody.
- a `scoped:` line: the Result also says `Scoped review: needed since` the head the last review saw. Do what the list above says.

`jmerge` reads the same lines: with `Scoped review: needed since <head>` as the last such line in the Result, a pull request is not ready until a review of a later head is written, and on every path, until every finding that blocks, of every review, has its answer. It reads `Second pass: needed since <head>` the same way. The `Fixed:` line cannot say that by itself here: it was written before the review of the fix, and a rebase moves it. Where the review stays unwritten, jbus says so in a message here that begins `jbus: pull request #<n> waits on you`.

A rebase waits for a review that is running, and for nothing else: the first block of "A conflict" does nothing while a reviewer this thread launched has not written its section, so the head does not move from under it. A review of a fix that is owed and not yet launched is no such review, and never waits for a rebase. When a wake brings a conflict, or the message that the default branch changed this pull request's files, while the block above prints `scoped: launch the scoped reviewer`, do what "A conflict" says, as on any other wake, and run the block again after the push: its ranges are then of the rebased head. The section's `Head:` is that later head, which is all the block and `jmerge` ask of it.

A push for a failed check starts no review: the `Reviewer:` line is already there, and the block above decides once. A rebase starts one only as "A conflict" says, a scoped review on the message that the rebase changed the content after its review. What stands behind a fix that got no review is the pull request's own checks.
