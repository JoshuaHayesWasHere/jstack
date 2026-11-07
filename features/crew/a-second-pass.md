### A second pass

A pull request gets one review round: the reviewer reviews once, you answer each finding once, and a fix you push for them gets no review.
What stands behind the fix is the pull request's own checks, and `jmerge` merges it once they pass and every blocking finding has an answer that counts ("The review").
No pass rules on a decline either: a decline of a blocking finding counts on the reason it cites.

The one later pass is a re-judgement of the brief.
A round whose `Meets the brief:` line says `no`, or that `jmerge` cannot read, or whose count is not the brief's, is owed one scoped review, whatever the fix changed: only a reviewer writes that line, and `jmerge` holds the pull request until a round's own line says `yes`.
That review judges again the lines the `no` named and carries the rest, so it is never a whole second review.
Its findings are a later review's: its `error` findings alone come to this thread, its `warning` ones go to the day's warnings row once the pull request merged, and its `info` ones are dropped ("The review").
A brief that says `Review: cleanup` is the day's warnings row, and it runs this section only for that re-judgement too.

What decides is this, run with the block at the top, in this worktree. Run it once the findings are handled and the fix, if there is one, is pushed, before the `Fixed:` line is written, and on each wake that finds the pull request green after that. It is the only check:

```sh
B="$H/tasks/<slug>.md"
read -r passes saw written << EOF
$(uv run --project "$T/../source" jbriefs --findings "$B" --rounds)
EOF
read -r asked sent stopped ruled ran << EOF
$(awk -v written="$written" -v head="$(git rev-parse HEAD 2> /dev/null)" '
    BEGIN {split(written, heads, ","); for (one in heads) seen[heads[one]]}
    function close_section() {if (section && scope && pass && at == head) ran++; section = scope = pass = 0; at = ""}
    /^## / {close_section(); section = ($(0) == "## Review")}
    section && /^Scope:/ {scope = 1}
    section && /^Verdict: (clean|findings)$/ {pass = 1}
    section && /^Head:/ {at = $(2)}
    /^Scoped review: / {ruled = $(3); sub(/,$/, "", ruled)}
    /^Scoped review: needed since / {asked = $(5); sub(/,$/, "", asked)}
    /^Scoped reviewer:/ && $(NF - 1) == "of" {sent = $(NF); nobody = ($(3) ~ /^none/)}
    function word(value, unset) {return value == "" ? unset : value}
    END {
        close_section()
        print word(asked, "-"), (nobody ? "none:" : "") word(sent, "-"),
            (sent == "" || nobody || (sent in seen)) ? "-" : sent, word(ruled, "no"), ran + 0
    }' "$B")
EOF
scoped() {
    if [ "$ruled" != needed ] || [ "$asked" != "$saw" ] || [ "$ran" -gt 0 ]; then return 0; fi
    head=$(git rev-parse HEAD 2> /dev/null) || return 0
    base=$(git symbolic-ref -q --short refs/remotes/origin/HEAD) && from=$(git merge-base "$base" "$head" 2> /dev/null) || from=
    if [ -z "$from" ]; then
        echo "scoped: this worktree does not know its default branch, so the range of the fix cannot be given"
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
read -r meets met count judged << EOF
$(uv run --project "$T/../source" jbriefs --meets "$B")
EOF
if [ "$meets" = no ] || [ "$meets" = unread ] || [ "$meets" = miscounted ]; then
    if [ "$asked" != "$judged" ]; then
        echo "write Scoped review: needed since $judged, the review's Meets the brief line is $meets"
    else
        said=$(scoped)
        echo "${said:-meets: the review at $judged says $meets of the brief: push the fix, then run this block again}"
    fi
elif [ "$passes" = 0 ]; then
    echo "wait: no review is written in the brief yet"
elif [ "$ruled" = needed ]; then
    said=$(scoped)
    echo "${said:-had: the scoped review the brief was owed is written, and it is the last}"
elif [ "$ruled" != no ]; then
    echo "none: one round, no review of the fix, as the Result says"
else
    echo "write Scoped review: none, one round: the fix merges on its checks"
fi
```

The first branch reads the last round's judgement of the brief, as `jmerge` reads it (`jbriefs --meets`, `jbriefs.meets`).
On `meets: ...`, push the fix for the unmet lines first, with the block of "The review" that pushes a fix, and run the block again: it then gives the launch.
The only other way out is the user's `Waived:` line ("The review").

- `write Scoped review: ...`: add that line to the Result, as printed, and only then the `Fixed:` line.
  `jmerge` merges on the `Fixed:` line, so a Result never has it without the line that says whether a review is owed.
  It is the record: from then on the block reads it and decides nothing again, so a later rebase does not change what was decided.
  Then run the block again and do what it says.
- `none`: no review of the fix.
  Go on to the `Fixed:` line.
- `scoped: launch the scoped reviewer ... with /pr-review run <slug> scoped <old range> <new range>`: launch it once the fixed head's desk proof is on record, as the first review is launched on the desk proof, whether or not the pull request is open yet.
  The desk proof is the brief's last `Checked:` line exiting 0 at the fixed head and its `Proved:` line run there, as "Do the task" writes both after the fix; run no block of "The review": its second block counts the first reviewer and would say to launch none.
  Where both hold at the fixed head, launch one reviewer now, by the launch block of "The review" with `scoped` and the message the line gives, whole.
  Where the check block failed there, fix and push with the block of "The review" that pushes a fix first, then run this block again: it gives the ranges of the head there is then.
  After the launch, add the line `Scoped reviewer: <threadId>, of <the head the message's second range ends at, in full>` to the Result, under the `Scoped review:` line, send the home nothing, and go on as "Stay on the pull request" says.
  Where the line says `in place of the one that stopped at <head>`, a reviewer launched for that head wrote no section, because the head moved under it: put the new line in place of that reviewer's line and do not add under it, also where a message from jbus says to add it, since "A conflict" counts every reviewer line against the sections written and would wait for the stopped one for good.
  If the session has no `t3_thread_launch`, write `Scoped reviewer: none, no launch tool in this session, of <that head>` and send the thread that hears of a pull request ("Telling the home") one line, once: `<slug>: <pull request url> at <full head commit> is fixed, and its scoped review could not be launched (no launch tool in this session): it waits for the user's word`.
  Its `jroles review` runs with `--thread <thread id>`, and on exit 75 this thread makes no launch and ends its turn with the one line "The review" gives for a capped pool, whatever the "Launching" section says: jbus wakes it once the cap has ended.
- `scoped: no scoped reviewer could be launched for this head`: the `Scoped reviewer: none` line is there and the home has been told. Nothing more to do: the pull request waits for the user's word.
- `scoped: the scoped reviewer is launched`: nothing to do.
  Its findings come as a message in this thread, and the message comes after its `## Review` is written.
  One that arrives while this block still prints this line has no section behind it: write no answer and no `Fixed:` line for it, because `jmerge` goes by the section and waits for it, and jbus asks for a replacement reviewer when the section stays unwritten.
  Handle them as a review's: an answer by id for each, and the counting block until it says `write Fixed:`.
  A reviewer whose review could not be done says so in its message and writes a section with `Verdict: not run`.
  That section is not a review, and the block still prints this line for it: add one line to the Result saying why the review was not done, and park a gate ("Do the task"), with the default that the pull request waits.
  A `Scoped reviewer:` line counts for the head it names after `of` and for no other.
  A rebase's scoped reviewer is written the same way, `Scoped reviewer: <threadId>, of <head>`, as the message from jbus says.
- `had`: the scoped review is in the brief, and its findings are handled as above.
  No reviewer is launched again, whatever a fix for its findings changed.
- `scoped: the head the review saw ... is not a commit here`, or `scoped: this worktree does not know its default branch`: no range can be given. Add what it printed to the Result and park a gate ("Do the task"), with the default that the pull request waits.

A brief from before one round may have a `Second pass:` line, or a `Scoped review: needed since` line that a fix wrote.
`jmerge` reads a `Second pass:` line as no line, so it owes nothing.
A `Scoped review: needed since <head>` line, the last such line in the Result, holds the pull request until a review of a later head than `<head>` is written (`its fix is not reviewed`) only while no `Proved:` line of the Result holds at the head (`ready.proves`): a fix whose proof runs there merges on that run and its checks.
A `Meets the brief: no` still waits for the scoped review that says `yes`, as the first branch of the block above says, and on every path the pull request waits until every finding that blocks, of every review, has its answer.
Where that review stays unwritten, jbus says so in a message here that begins `jbus: pull request #<n> waits on you`.

A rebase waits for a review that is running, and for nothing else: the first block of "A conflict" does nothing while a reviewer this thread launched has not written its section, so the head does not move from under it.
A rebase starts a review only as "A conflict" says: a scoped review on the message that the rebase changed the content after its review.
