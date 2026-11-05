---
name: pr-review
description: Have a finished pull request reviewed in a fresh thread - one review thread per pull request reads its diff itself, judges what it found, and proves the one safety fact by running code (pstack's review, with no reviewer subagents and no fixes), and records the findings in the brief, where jbus reads them and tells the thread that did the work when it owes a line. Use when the user invokes /pr-review or $pr-review in a home or in a crewmate's thread, or asks to review the pull requests that have finished.
tip: has a finished pull request reviewed in a fresh thread | review the pull request | review the pull requests | review the pr | review this pr | review my pr
user-invocable: true
disable-model-invocation: true
card: "Run the pipeline | 4 | Starts one review thread per pull request. It reads the diff itself, judges what it found, and one command proves the fact the change is safe because of. It fixes nothing, and jbus archives it when the pull request merges or closes. | Reach for it when a pull request opens. The crewmate does this by itself. | model: a crewmate; op: the operator | look: rev"
---

# pr-review

This is the reviewer's text: a thread started with `/pr-review run <slug>`, which only a launcher sends, reviews that brief's pull request, as "The reviewer" says.
Any other message makes this thread a launcher.

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
T=$(realpath ~/.claude/skills/pr-review/../../templates)
```

`$T` is the `templates/` directory of the repo this skill lives in. Each template there is the one copy of its text: read it when a step names it, not before.

## Launching

When this thread launches a reviewer, for `/pr-review` in a home or a crewmate's thread, `/pr-review <slug>`, or the crew skill's launch: read `$T/../skills/pr-review/launching.md` now.

## The reviewer

This thread is a **reviewer**. It reads the diff, judges what it found, proves one fact, reports, and ends. It starts no subagent and no other thread: the review is this one thread. It never edits a file, commits, pushes, or changes the pull request, and it never reads the crewmate's thread.

A reviewer runs no test step and no suite, whatever the brief says.
The tests are CI's `check`, which has passed at the head before a reviewer is launched, and the crewmate's own runs (the crew skill, "Do the task").
The one thing a reviewer runs is a targeted proof of the fact the change is safe because of ("The review", step 5).
New prose is one sentence per line, and an old line the pull request did not touch is no finding for how many sentences it holds.

### Start

1. Read `$H/tasks/<slug>.md`.
   Nothing else from `$H`, but for what the blocks under "After the review" read by themselves.
   Then work out who this reviewer is, and then whether this message may start a review.

   Who this reviewer is goes on the section's `By:` line, under its heading: the provider, the model and the effort this thread runs on, and its number, `#<n>`.
   Ask the thread itself: the `t3-code` server's `t3_thread_configure` with no arguments (if your harness defers it, load it first).
   Run this with the block at the top, with what it printed, whole, and the message this thread was started with in place of the words in angle brackets.
   Keep what it prints, the `By:` line:

   ```sh
   asked='<the message this thread was started with, whole>'
   config='<what t3_thread_configure printed, or nothing where this session has no such tool>'
   case $config in "<"*) config= ;; esac
   n=$(printf '%s\n' "$asked" | awk 'NR == 1 {print ($(4) ~ /^[0-9]+$/ ? $(4) : 1)}')
   by=$(printf '%s' "$config" | jq -r '.modelSelection | [(.provider // .instanceId), .model, (.options[]? | select(.id | test("effort$"; "i")) | .value)] | join(" ")' 2> /dev/null)
   if [ -z "$by" ]; then
       by=$(uv run --project "$T/../source" jroles review 2> /dev/null | sed -n "${n}p" |
           jq -r '[.provider, .model, (.options[]? | select(.id | test("effort$"; "i")) | .value)] | join(" ")' 2> /dev/null)
   fi
   echo "By: ${by:-inherit} #$n"
   ```

   The number is the message's, the line of the role map's review list this reviewer was launched for, and 1 for a message with none: a scoped pass and a second pass are the first line's.
   So the two reviewers of one pull request have two `By:` lines, also on one model: `By: claudeAgent claude-sonnet-5-5 high #1` and `By: claudeAgent claude-sonnet-5-5 high #2`, and `jmerge` counts them by the number.
   Then decide whether this message may start a review, with this, with the same message and that `By:` line in place of the words in angle brackets:

   ```sh
   B="$H/tasks/<slug>.md"
   asked='<the message this thread was started with, whole>'
   by='<the By: line the block above printed>'
   case $asked in
   "/pr-review run <slug> scoped "*) echo "go: a scoped pass, as \"A scoped pass\" says" ;;
   *" again") echo "go: a second pass, or the review the brief is still owed, the message ends in again" ;;
   "/pr-review run <slug> "[0-9]*)
       if awk -v by="$by" '/^## / {review = ($(0) == "## Review")} review && $(0) == by {found = 1} END {exit !found}' "$B"; then
           echo "stop: the brief has a ## Review with $by, and a reviewer writes one section for its line"
           echo "the line I accept: /pr-review run <slug> again"
           sed 's|{slug}|<slug>|g' "$T/rerun.md"
       else
           echo "go: the brief has no ## Review with $by, so this is that line's review"
       fi ;;
   *)
       if ! grep -qx '## Review' "$B"; then
           echo "go: the brief has no ## Review, so this is the review it is owed"
       else
           echo "stop: the brief has a ## Review and the message does not end in again"
           echo "the line I accept: /pr-review run <slug> again"
           sed 's|{slug}|<slug>|g' "$T/rerun.md"
       fi ;;
   esac
   ```

   On `stop`, say what it printed, the line it would accept included, and end: no review, no section.
   On `go`, go on.
2. Read the pull request: `gh pr view <url> --json number,title,body,state,headRefName,headRefOid,files,statusCheckRollup`. The diff is read in step 3 of "The review". Open a file only to judge a finding, or to find and prove the safety fact.
3. Check the ground, and stop with the reason if any line fails:
   - `git status -sb`: this checkout is on the pull request's branch and has nothing uncommitted.
   - `git rev-parse HEAD` is the pull request's `headRefOid`. Keep it: this is the head under review.
4. Say in two lines what is about to be reviewed, then start.

### The review

When "Start" is done, and whenever a step names "The review" or one of its steps: read `$T/../skills/pr-review/the-review.md` now.

### No room

A reviewer that gives up says so in the brief, so that the pull request never waits for a review nobody is going to run.
It gives up only on exit 69 of the block of step 1, which is its sixth send that did not go on.
It sends nobody anything.

1. Write the section.
   Run this with the block at the top, with the head kept at the start, the last line the block of step 1 printed and the `By:` line Start printed in place of the words in angle brackets.
   For a scoped pass, `scope` is the `Scope:` line step 1 of "A scoped pass" printed, and for any other pass it is left empty:

   ```sh
   B="$H/tasks/<slug>.md"
   kept='<the head kept at the start>'
   why='<the last line the block of step 1 printed>'
   by='<the By: line Start printed>'
   scope=''
   case $by in "<"*) by= ;; esac
   case $scope in "<"*) scope= ;; esac
   [ -f "$B" ] || { echo "no section: there is no brief at $B"; exit 1; }
   if awk -v kept="$kept" -v by="$by" '/^## / {last = $(0); verdict = head = mine = ""} /^Verdict:/ {verdict = $(0)} /^Head:/ {head = $(2)} /^By: / {mine = $(0)} END {exit !(last == "## Review" && verdict == "Verdict: not run" && head == kept && mine == by)}' "$B"; then
       echo "no section: the brief already ends in a review of $kept that was not run"
       exit 0
   fi
   {
       [ -z "$(tail -c1 "$B")" ] || echo
       printf '\n## Review\n'
       if [ -n "$by" ]; then printf '%s\n' "$by"; fi
       printf 'Verdict: not run\n'
       if [ -n "$scope" ]; then printf '%s\n' "$scope"; fi
       printf 'Why: the run block was sent six times and never went on, and its last answer was "%s"\n' "$why"
       printf 'Head: %s   Unchanged by the review: not checked, no review ran\n' "$kept"
       printf 'Sent to: not sent, no review ran\n'
   } >> "$B" && echo "written: ## Review with Verdict: not run, in $B"
   ```

   The section is not a review: `jmerge` reads it as a review with no verdict and merges nothing on it.
   Its `By:` line says whose it is, so that this reviewer's section at the same head, once it runs again, takes its place, and another reviewer's does not.
   Its `Scope:` line, on a scoped pass, keeps it a scoped pass: a scoped section takes the place of no section but a scoped one, so the first review of the same head keeps its findings.
   Its `Head:` line is what lets the crewmate's thread rebase again (the crew skill, "A conflict").
   jbus's stall clock (`jbus.clock`) reads a review with no verdict as a wait on the review: it carries the crewmate on, and then tells the home.
   Sent a second time for the same head, the block writes no second section.
2. Say the same in this thread in two lines, and stop without settling: a thread that settled would look like a review that was done.

### After the review

When the review has its verdict, and whenever a step names "After the review" or one of its steps, as "No room", "Outside the diff" and "A scoped pass" do: read `$T/../skills/pr-review/after-the-review.md` now.

### Outside the diff

When step 2 of "After the review" drops what is outside the diff, and whenever a step names "Outside the diff": read `$T/../skills/pr-review/outside-the-diff.md` now.

### Wider than the brief

```sh
uv run --project "$T/../source" jmerge --scope <slug>
```

It compares the diff with the brief's `Where:`: it asks `jmerge` which changed files that line does not cover, with the one parser of that line (`jbriefs.parse.where`), and prints nothing when all are inside.
What it prints goes on the section's `Outside Where:` line, each `outside: <path>` as its path, joined with `, `, or `none` when it printed nothing.
That line is no finding: it carries no severity, asks the crewmate for no line, and holds no merge, since the command, not the reader, is the check, and anyone can run it again.
So no finding restates it, and a finding of the reading that says only that a file is outside `Where` is dismissed (the lead judgment of "The review").
Do not judge the width by reading the diff: the command's answer is the answer.
A command that exits with something other than 0 (the brief's `Where:` names no path, or neither the branch nor the pull request can be read) printed why on stderr: the line is then `Outside Where: not checked, <why>`, not `none`.

A finding can be wider than the brief in a second way: it is about a changed line, and what it asks for is not in the brief's `Where`.
That happens with the fifth question's things to look for (a restructuring, a file to split, a branch to move into a module of its own, a wrapper to remove, logic to move to its canonical layer), when the remedy would change a file outside `Where`.
The `SCOPE` text asks the reading to say so in the finding.
Such a finding is kept, sent and recorded like any other, with these words at the end of its line: `outside Where, not this pull request`.
It asks the crewmate for no fix: the crewmate queues it as a row of its own, as `templates/a-fault-outside.md` says, or leaves it.
A finding whose remedy stays inside `Where` is an ordinary finding.

### In flight

```sh
BRIEF="$H/tasks/<slug>.md"
PR=$(gh pr view <url> --json number,files) || exit 1
OPEN=$(gh pr list --state open --json number,title,files) || exit 1
printf '%s\n' "$OPEN" | jq -r --argjson pr "$PR" '
  ($pr.files | map(.path)) as $mine
  | .[] | select(.number != $pr.number)
  | (.files | map(.path) | map(select(IN($mine[])))) as $both
  | select($both | length > 0)
  | "pull request \(.number) (\(.title)): \($both | join(", "))"'
for other in "$H"/tasks/*.md; do
  [ "$other" = "$BRIEF" ] && continue
  grep -q '^## Result' "$other" && continue
  where=$(sed -n 's/^Where: //p' "$other" | grep -o '`[^`]*`' | tr -d '`' | tr '\n' ' ')
  both=$(printf '%s\n' "$PR" | jq -r '.files[].path' | awk -v where="$where" '
    BEGIN { n = split(where, w, " "); for (i = 1; i <= n; i++) sub(/\/$/, "", w[i]) }
    { for (i = 1; i <= n; i++) if ($(0) == w[i] || index($(0), w[i] "/") == 1) { print; next } }' |
    paste -sd, - | sed 's/,/, /g')
  if [ -n "$both" ]; then echo "brief $(basename "$other" .md): $both"; fi
done
```

It prints one line for each open pull request that changes a file this one changes, and one for each brief with no result yet whose `Where:` covers a file this one changes.
Those lines go into the section's `In flight:` line, as they are.
They say that two pieces of work touch the same file, so that whoever merges second knows: they are not a fault in this pull request and carry no severity.
Do not open the other pull requests or briefs to look further.
A failed `gh` ends the block with exit code 1, and then the section's `In flight:` line says "not checked", not "none".

### A scoped pass

When this thread was started with `/pr-review run <slug> scoped <old range> <new range>`, and whenever a step names "A scoped pass": read `$T/../skills/pr-review/a-scoped-pass.md` now.
