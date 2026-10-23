### The review

The review is pstack's, in two parts. One is its interrogate: a reading of the diff against the intent, and a lead's judgment of what it found. The other is its blast radius: the one fact the change is safe because of, proven by running real code. jstack's copies are `$T/../skills/interrogate/SKILL.md` and `$T/../skills/blast-radius/SKILL.md`. This section says which of their steps a reviewer does and what becomes of the answer, and repeats none of their text: read each where a step names it.

pstack's two reviewers are one reading here, so that a pull request has one review thread and nothing under it. It is in the crewmate's own worktree, on the pull request's branch at the head under review, which is why the launcher put it there: it reads the code around the diff there, and the proof runs the real code there. Nothing in the worktree changes, and nothing goes to `origin`.

**1. Room, and 2. Scope and intent.** One block does both, so that nothing is built on a machine with no room:

```sh
BRIEF="$H/tasks/<slug>.md"
[ "$(awk '/^Review:/ {print $(2); exit}' "$BRIEF")" = none ] && exit 78
W="${TMPDIR:-/tmp}/pr-review-<slug>.$(git rev-parse HEAD 2> /dev/null).sends"
echo sent >> "$W"
said=$(uv run --project "$T/.." jgauge room --light --wait 540) || [ "$?" = 75 ] || said="wait: jgauge room did not run"
if [ "$said" != go ]; then
  printf '%s\n' "$said"
  [ "$(grep -c . "$W")" -lt 6 ] && exit 75
  rm -f "$W"
  exit 69
fi
rm -f "$W"
SCOPE=$(cat <<'SCOPE'
Scope of this review. It overrides anything above that reads wider.
Review only the lines this pull request changes: its diff against its base branch.
Report a finding only when it is about a changed line, or about something a changed line breaks. Give every finding the file and line of the changed line, and when the damage is elsewhere, say where in the text.
For a finding about a removed line, give the line that now sits just before or just after where it was. For a finding about what the change as a whole lacks (a "Done when" line it does not meet, a test it does not have), give no file and say so.
End every finding with the principle it breaks, `(principle: <name>)`, a name from the principles listed above, or `(principle: none)` when it breaks none of them or none is listed.
Do not report and do not fix a bug or weakness in code this pull request did not change, however real: those are handled elsewhere.
Do not ask for work beyond what the task above needed.
Read the changed code the way a tech lead would, and answer these about it:
1. Does it meet the task and every "Done when" line above? Name each line it does not meet.
2. Is it tested properly? A test must execute something. A new or changed test that only matches wording and executes nothing is a warning, and the remedy to name is a test that executes (one that runs the shell, parses the block and checks it, or runs the script), not deleting the test.
3. Does it do what the user wanted, not only what the words of the task say?
4. Is it correct? Look for these too, in the changed lines:
   - Run twice, or after a run that crashed halfway: if what happens depends on the state left behind, a reconciliation step is missing.
   - Shared state: where several actors can touch the same files, branches or data, is access kept in step by structure (a lock, sequential phases, one owner), or only by a convention that will not hold?
   - A rule in prose: a comment or convention someone has to remember, where a type, a lint rule or a runtime check would make the wrong thing impossible.
   - An old path kept beside a new one: with no outside consumer, the callers move and the old path goes in the same change.
   - A proxy: a check that reads a file's age, a cached value or a self-report, and not the real value or the output itself.
   - A bug fix with no test for the bug.
5. Could it be done more simply or cheaply? Look for these too, in the changed lines:
   - Be ambitious about structural simplification. Do not stop at "this could be a bit cleaner." Look for reframings that make whole branches, helpers, modes, conditionals or layers disappear. Assume a "code judo" move is often available: one that uses the existing architecture more effectively and makes the change dramatically simpler. If you can delete complexity rather than rearrange it, push hard for that.
   - A file the change pushes from under 1,000 lines to over 1,000: should it be split first?
   - Ad-hoc conditionals, special cases or one-off branches put into an existing flow, where a helper or a module of its own would hold the logic.
   - A thin abstraction, identity wrapper or pass-through helper that adds indirection and no clarity.
   - Logic outside its canonical layer: feature logic in a shared path, or a one-off where an existing helper would do.
   When the remedy for one of these would change a file outside the "Where" line above, say so in the finding: it is noted for later, not asked for in this pull request.
6. Does it leave everything it did not mean to change unaffected? Look for these too, in the changed lines:
   - A changed line that does not trace to the task: adjacent code, comments or formatting "improved" in passing, or a refactor of something that was not broken. Every changed line should trace directly to the task above.
   - A removal the change did not earn: an import, variable or function that was already unused before this change is named in the finding, not deleted. What the change itself made unused goes in the same change, and one left behind is a finding too.
7. Does it change a file outside the "Where" line above? Each such file is a finding.
SCOPE
)
INTENT=$(
  sed -n '/^Task:/,/^Pull request:/{/^Pull request:/!{/^Skills:/!p}}' "$BRIEF"
  run=$(uv run --project "$T/.." jbriefs --skills-run "$BRIEF")
  if [ -n "$run" ]; then
    skills=$(awk '/^## / {exit} /^Skills:/ {sub(/^Skills:[ \t]*/, ""); print; exit}' "$BRIEF")
    printf '\nSkills: %s. The crewmate loaded each in full and ran it, and its Result owes one artifact for each under Skills run:, the one templates/skill-artifacts.md names. jmerge waits on one that is missing, empty or a placeholder. Judge whether each is the real one: an artifact that restates the brief, or that running the skill plainly did not produce, is a finding about the change as a whole.\n' "$skills"
    printf 'What the Results hold under Skills run:, as jmerge reads it:\n%s\n' "$run"
  fi
  play=$(uv run --project "$T/.." jbus playbook reviewer "$BRIEF")
  if [ -n "$play" ]; then printf '\n%s\n' "$play"; fi
  printf '\n%s\n' "$SCOPE"
)
I="$T/../skills/interrogate/references"
D=$(mktemp -d "${TMPDIR:-/tmp}/pr-review-<slug>.XXXXXX") || exit 1
printf '%s\n' "$INTENT" > "$D/intent"
printf '%s\n' "$SCOPE" | awk '/^4\. / {on = 1} /^   When the remedy/ || /^6\. / {on = 0} on' > "$D/questions"
{ echo '~~~~~~diff' && gh pr diff <url> && echo '~~~~~~'; } > "$D/code" && [ "$(wc -l < "$D/code")" -gt 2 ] ||
  { echo "no diff was read: nothing to review" >&2; exit 1; }
awk -v dir="$D" -v refs="$I" '
  BEGIN {
    from["INTENT"] = dir "/intent"
    from["DIFF_OR_FILES"] = dir "/code"
    from["RUBRIC_CONTENTS"] = refs "/rubric.md"
    from["CODE_QUALITY_CONTENTS"] = refs "/code-quality-review.md"
    from["REVIEW_SKILL_QUESTIONS"] = dir "/questions"
  }
  !body { body = ($(0) == "---"); next }
  {
    lead = index($(0), "> ") == 1 ? "> " : ""
    name = substr($(0), length(lead) + 1)
    if (name !~ /^\{[A-Z_]+\}$/) { print; next }
    name = substr(name, 2, length(name) - 2)
    if (!(name in from)) { print "the template asks for " name ", which this block does not fill" > "/dev/stderr"; bad = 1; next }
    lines = 0
    while ((getline line < from[name]) > 0) { print lead line; lines++ }
    close(from[name])
    if (!lines) { print "nothing to fill " name " with: " from[name] " is empty or missing" > "/dev/stderr"; bad = 1 }
    filled++
  }
  END {
    if (filled != 5) { print "the template has " filled + 0 " places to fill, not 5" > "/dev/stderr"; bad = 1 }
    exit bad
  }' "$I/reviewer-prompt.md" > "$D/prompt.md" || exit 1
echo "$D/prompt.md"
```

- Send the block whole, as it is, with only the slug and the pull request's url filled in, and with the block at the top, which sets `H` and `T`.
- First it asks the machine for room.
  `jgauge room` is the home skill's check before a launch, the one copy of it, in `features/jgauge/src/jgauge/room.sh` of the repo this skill lives in: the one-minute load against the core count, the available memory, the memory pressure, the file slots of `/tmp`, and the share of the plan's five-hour and weekly limit already used.
  Its thresholds are the first lines of that file: change one there.
  A review asks with `--light`, which skips the load: a review is about 2% of one core, since its time is the model's, and its one heavy step, the proof, runs in the short test lane, which bounds it.
  Memory, memory pressure, `/tmp` and the plan still hold a review.
  It prints `go`, or `wait: ` and the first reading with no room.
  A `note: ` line says a limit is not known, and the review goes on all the same.
- The wait for room is this call, and nothing else. With `--wait 540` the check looks again every 15 seconds until it says `go` or nine minutes have passed. On `go` the block goes on by itself. So send it as a foreground command with a time limit of 10 minutes (600000 ms), and never as a background command. When the nine minutes pass with no room, the block prints the last `wait: ` line, builds nothing and exits 75: start no reviewer, and send the same block again at once, in this same turn. A call that was cut off before it printed anything is sent again the same way. A check that did not run is a `wait` too, and exits 75 at once.
- Never end the turn to wait for room, and never leave a check, a loop or a timer in the background to wait in your place: nothing wakes a reviewer when the machine has room, and the pull request would wait for a review that nobody runs. The block counts its own sends for this slug and head, in a file beside the directories it builds, a send that was cut off included, and forgets them on `go`. The sixth send with no room, about an hour in, prints the last answer and exits 69: give up as "No room" below says, and send the block no more.
- A brief with `Review: none` gets exit code 78 and nothing built: say that its brief asks for no review, and stop.
- Then it does steps 1 and 2 of the interrogate skill with nothing left to ask.
  The scope is the pull request's diff, `gh pr diff <url>`.
  The intent is the brief from `Task:` to the end of `Decisions:`, word for word, then, where the brief has a `Skills:` line that is not `none`, that line with what each named skill owes and the artifact the Results hold for each, as `jbriefs --skills-run` prints it with `jmerge`'s own reading, then, where the brief names a playbook run by a crewmate, its name and the "Apply when" paragraph of each principle it cites, read from the playbook's own `principles/<name>.md` citations, and after it the `SCOPE` text.
  A scoped pass puts the earlier findings and the crew's answers, as `jbriefs --findings` prints them, right above the `SCOPE` text ("A scoped pass", step 3).
  That text is how the scope rule and the seven questions reach the reading of step 3, and it is the one copy of them: the interrogate skill reads questions 4 and 5 out of this block for its own reviewers, which is why the `SCOPE` lines start at the start of a line.
- Last it fills the interrogate skill's `references/reviewer-prompt.md` with the intent, the diff, its `references/rubric.md`, its `references/code-quality-review.md` and questions 4 and 5, and prints the path of the prompt it wrote, a file in a directory of its own under `/tmp`. The diff is in it as GitHub sent it, not retyped by this thread. Keep the path: step 3 reads it, and the proof of step 5 is written beside it.
- Exit code 1 means `gh` gave no diff or the template could not be filled, and the line above it says which. Nothing was reviewed: send the block once more, and if it fails again, write a section with `Verdict: not run` and the reason, tell the crewmate, and stop without settling.

**3. The reading.** Read the file the block printed, from its first line to its last, in parts if it is long, and do what it says, in this thread: it is the adversarial review of this pull request's diff, and it asks for a list of findings. Read whatever the diff calls or is called by, and change nothing. Start no `Agent` call and no thread for it. Write the list down, or "no findings", before step 4: that list is what the lead judges.

**4. Lead judgment.** Read step 5 of `$T/../skills/interrogate/SKILL.md` and its `references/lead-judgment.md` now, and judge the list of step 3 as they say: merge the findings that say the same thing, then put each in one of pstack's four buckets. Judge it against what the reading was not given: the brief's decisions, and the repo to check a claim against.

- **Act on** and **Consider** are the review's findings. Write each as one line, `<severity> <file>:<line> <what is wrong> (principle: <name>) (bucket: Act on)` or `(bucket: Consider)`, in the forms "Outside the diff" gives. The bucket tag is what `jmerge` reads: an **Act on** finding holds the merge until the crewmate answers it by id, a **Consider** one does not. A finding on security, auth, billing, data, migrations or concurrency ends with one more tag, `(risk: <that area>)`: the crewmate may not decline it without a gate that asks the user. Write no id: `jbriefs --findings` gives each finding its id, and merges this reviewer's with another's of the same place. The tag names the principle the finding breaks, one the intent lists, or is `(principle: none)`. The severity is `error`, `warning` or `info`: the reading's `critical` is written `error`, the highest, its `warning` stays `warning`, and its `nit` is `info`. A crewmate declines an `info` finding by default and leaves it for a follow-up, so rate a thing `warning` when it must be fixed in this pull request.
- **Noted** and **Dismissed** are counted, not sent. Each count is a line of the section, and each dismissed finding keeps one line there, `<severity> <file>:<line> <what is wrong> (principle: <name>) (dismissed: <the reason>)`: it is what lets the user overrule the lead, and where another reviewer raised the same finding, `jbriefs --findings` prints the dismissal beside it. Neither goes to the crewmate.
- The buckets are the lead's reading. What the crewmate does with a finding is still its own: `Finding F<n>: fixed`, or `Finding F<n>: not fixed` with a reason (the crew skill, "The review").

**5. The one safety fact.** Read `$T/../skills/blast-radius/SKILL.md` now, its "How sure are you" list and its steps 2 and 5: find the one fact this change is safe because of, and prove it by running real code at this head. Then run this with the block at the top, which sets `T`, and with the directory of the prompt file, the head kept at the start and the one command that proves the fact in place of the words in angle brackets:

```sh
D='<the directory of the prompt file>'
kept='<the head kept at the start>'
: "${T:?is not set: send this with the block at the top}"
limit=540
G=$(git rev-parse --git-dir)
at() { [ "$(git rev-parse HEAD)" = "$kept" ] && [ ! -d "$G/rebase-merge" ] && [ ! -d "$G/rebase-apply" ]; }
at || { echo "unproven: this checkout is not at $kept, or a rebase is going on in it, so the proof did not run"; exit 1; }
export D
cmd=$(cat << 'THE_PROOF_ENDS_HERE'
<the proof>
THE_PROOF_ENDS_HERE
)
key=$({ printf '%s\n' "$cmd"; cat "$D/proof.sh" 2> /dev/null; } | cksum)
running() { [ -f "$D/proof.pid" ] && ! [ -f "$D/proof.exit" ] && kill -0 "$(cat "$D/proof.pid")" 2> /dev/null; }
if running; then
    echo "joined: the proof an earlier call started still runs, so it is waited on and not started again"
elif [ -f "$D/proof.exit" ] && ! [ -f "$D/proof.told" ] && [ "$(cat "$D/proof.key" 2> /dev/null)" = "$key" ]; then
    echo "checked: the proof ended after the last call, and this is what it said"
else
    rm -f "$D/proof.pid" "$D/proof.exit" "$D/proof.told" "$D/proof.out"
    printf '%s\n' "$cmd" > "$D/proof.cmd"
    echo "$key" > "$D/proof.key"
    perl -MPOSIX -e 'POSIX::setsid(); exec @ARGV or die' sh -c 'uv run --project "${2}" jgauge test-slot --short --thread "${3}" -- sh "${1}/proof.cmd" > "${1}/proof.out" 2>&1; echo $? > "${1}/proof.exit"' proof "$D" "$T/.." '<thread id>' < /dev/null > /dev/null 2>&1 &
    echo $! > "$D/proof.pid"
    echo "started: the proof runs at this head, and this call waits on it"
fi
waited=0
while ! [ -f "$D/proof.exit" ] && running && [ "$waited" -lt "$limit" ]; do
    sleep 1
    waited=$((waited + 1))
done
if [ "$(cat "$D/proof.exit" 2> /dev/null)" = 76 ] && grep -q "is registered as a waiter" "$D/proof.out"; then
    touch "$D/proof.told"
    cat "$D/proof.out"
    echo "waiting: no short test slot is free and nothing ran: end your turn now with the one line, and send this block again when jbus wakes this thread"
    exit 76
elif [ -f "$D/proof.exit" ] && [ "$(cat "$D/proof.key")" != "$key" ]; then
    touch "$D/proof.told"
    echo "stale: the proof exited $(cat "$D/proof.exit") but it was started for a command that has changed since: send this block again, and it runs the proof as it is now"
    exit 75
elif [ -f "$D/proof.exit" ]; then
    touch "$D/proof.told"
    echo "exit $(cat "$D/proof.exit")"
    tail -n 5 "$D/proof.out"
    at || echo "unproven: the head moved under the proof"
    git status --porcelain
elif running; then
    echo "running: $(tail -n 1 "$D/proof.out" 2> /dev/null). Send this block again now, in this turn, and again until it prints exit: never end your turn while it runs"
else
    echo "lost: the proof stopped with no exit code: send this block again, and it starts the proof afresh"
fi
```

- The proof is one targeted run that fails loud when the fact is false: a test file or a single test of the repo that executes it, or a script you write as `$D/proof.sh` that calls the real code, run as `sh "$D/proof.sh"`. It is never the repo's whole suite and never its check command: CI's `check` ran those, and passed before this thread was launched.
- The block starts the proof on its own, under `jgauge test-slot --short`, which holds one of the slots of the short lane: no full suite takes those, so it waits only behind other short runs. `<thread id>` is this review thread's own id: the `t3-code` server's `t3_thread_configuration` with no arguments gives it as `threadId` (if your harness defers it, load it first). Send the block as a foreground command with a time limit of 10 minutes (600000 ms), and never as a background command. The call waits on the proof for up to 9 minutes, and a proof holds the short lane for 2 minutes at most, so one call usually has its `exit` line. On `running`, send the block again, in this turn, as many times as it takes, until it prints `exit`.
- **Never end your turn while your own proof waits or runs, and never say you will go on once it finishes**: nothing wakes a reviewer when a command ends, only a message does, and the Review would never be written. A proof an earlier call or an earlier turn started is joined (`joined`), not started again, and one that ended after the last call gives what it said (`checked`). A proof sent again after it gave its answer runs afresh, so fix `$D/proof.sh` and send the block again. On `stale`, the proof ran for a command that has changed since and is no proof: send the block again.
- The one time the turn ends is when the block prints `waiting` and ends 76: with `--thread` the proof waits for no slot, so with every slot of the lane taken it registers this thread as a waiter, writes one line saying so into `$D/proof.out`, and nothing runs. End your turn with one line, `Waiting on a test slot: jbus will wake this thread when one is free.`, and send the block again when jbus wakes you with its one message. Never poll for a slot, and never end the turn with nothing said. On a machine with no jbus nothing wakes a waiter: leave `--thread <thread id>` off, and the proof waits for its slot in place, on `running`. A proof still running at the short lane's time limit (`jgauge test-slot --help` gives it) is stopped, exit 124, and `$D/proof.out` says so: it proved nothing, so make it smaller, a single test, and send the block again. Never take the `--short` off to get past the limit. An `exit 76` or `waiting` proved nothing either.
- The crewmate's thread may rebase or push in this worktree while the review is out. The block runs the proof only at the head kept at the start with no rebase going on, and looks again after it. On a line that starts `unproven:`, whatever else it printed is not a proof of that head: the `Proof:` line is `unproven, the head moved under the proof`, with the finding below.
- The proof command enters the reviewed repo's own environment by itself: in a `uv` repo it is `uv run pytest <the test>` from this worktree, never a bare `pytest`. The block's own `uv run --project "$T/.."` leaves the environment of the repo this skill lives in first on `PATH`, and a bare command would run there.
- The reviewer changes no file in the worktree. The script and what it printed are under `/tmp`, beside the prompt, and the last line of the block shows the worktree: it prints nothing. If it prints a file, the proof wrote there: say so in the section, and its `Unchanged by the review:` is `no`.
- What ran and its last lines go on the section's `Proof:` line, in the one form `$T/review.md` shows, with a comma between its parts: the command, `exit <code>`, and the last line or two it printed. A passed proof names no failed exit code in its command or its fact, since any `exit <n>` with n not 0 refuses the line: write `the hook ended with status 1`, not `the hook said exit 1`, and put a command that holds one in `$D/proof.sh`, so that the line names the script.
- Read `$D/proof.out` before judging a proof that did not exit 0. One that ran the real code and failed has found the fact false: that is a finding, an `error` against the changed line that breaks it. One that never reached the real code (a command not found, an import that failed, a usage error) proved nothing either way: fix the proof and run it again, and if it still cannot run, the fact is unproven. A fact that could not be proven by running code is written `Proof: unproven, <the fact>`, and that is itself a finding: `warning - the one fact the change is safe because of is unproven: <the fact>`.

**6. Verdict.** The section's `Verdict:` is one of two words, and CI is neither:

| pstack's verdict | `Verdict:` | When |
|---|---|---|
| `PASS` | `clean` | no finding is left once "After the review" has dropped and added its own |
| `PASS+NOTES` or `FAIL` | `findings` | the section's `Findings:` has at least one line |

- A review that could not be done is neither: its section says `Verdict: not run` and why.
- `Head:` is the head reviewed, and `Patch-id:` is `git patch-id --stable` of the diff from the base to that head. The block of step 1 of "After the review" prints both lines whole.
- CI's `check` is not the verdict, and not the precondition either: a reviewer is launched when the pull request opens, beside its checks, and never on one whose check failed. A green pull request can still have findings, and `jmerge` merges only one that is green.
