---
name: pr-review
description: Have a finished pull request reviewed in a fresh thread - one review thread per pull request reads its diff itself, judges what it found, and proves the one safety fact by running code (pstack's review, with no reviewer subagents and no fixes), sends the findings to the thread that did the work, and records them in the brief. Use when the user invokes /pr-review or $pr-review in a home or in a crewmate's thread, or asks to review the pull requests that have finished.
tip: has a finished pull request reviewed in a fresh thread | review the pull request | review the pull requests | review the pr | review this pr | review my pr
user-invocable: true
disable-model-invocation: true
card: "Run the pipeline | 4 | Starts one review thread per pull request. It reads the diff itself, judges what it found, and one command proves the fact the change is safe because of. It fixes nothing, and jbus archives it when the pull request merges or closes. | Reach for it when a pull request opens. The crewmate does this by itself. | model: a crewmate; op: the operator | look: rev"
---

# pr-review

A pull request is reviewed by a **reviewer**: a new thread that knows the brief and the pull request and nothing of the conversation that wrote the code.
The thread `/pr-review` is typed in never reviews.
It launches the reviewer, gives the user the link, and goes back to what it was doing.

There is one pass per pull request: the reviewer reviews once and the crewmate fixes once.
A fix that changes files under `tests/` only is not reviewed: what stands behind it is the pull request's own checks.
A fix that changes any other file gets one scoped pass, of the fix alone, by another reviewer, and that pass is the last ("A scoped pass").
The crewmate's own check decides which it is (the crew skill, "A second pass").
The reviewer finds, and fixes nothing: what to do with a finding is for the thread that did the work.

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
T=$(realpath ~/.claude/skills/pr-review/../../templates)
```

`$T` is the `templates/` directory of the repo this skill lives in.
Each template there is the one copy of its text: read it when a step names it, not before.

## Which part this thread plays

| The message | Typed in | This thread |
|---|---|---|
| `/pr-review run <slug>` | a thread a launcher made | is the **reviewer** for that brief: go to "The reviewer" |
| `/pr-review <slug>` | anywhere | launches one reviewer, for that brief, whatever its `Review:` line says |
| `/pr-review` | a home (the repo's main checkout) | launches a reviewer for every brief that is ready |
| `/pr-review` | a crewmate's thread (a worktree whose branch has a brief) | launches one reviewer, for that crewmate's pull request |

Only a launcher sends the `run` form.
`git rev-parse --git-dir` and `--git-common-dir` give the same path in the main checkout and different paths in a worktree.
In a worktree the slug is the brief in `$H/tasks/` whose result names the current branch.

## The brief's `Review:` line

A brief may carry one line that says whether its pull request gets a review.
The home writes it, when it writes the brief; nothing here changes it, but for the one case under "A brief the user names".
It is a field of its own, like `Thread:`: a line that starts with `Review:`, and its value is the word after that.
The same words inside the task's text, a `Done when` line or a result do not count.
Read it with this, and no other way:

```sh
awk '/^Review:/ {print $(2); exit}' "$H/tasks/<slug>.md"
```

It prints the value, or nothing for a brief with no such line.

| The brief has | The launcher | The reviewer |
|---|---|---|
| `Review: none` | passes the brief over, unless the user named it | does nothing: it says so and stops |
| anything else, no `Review:` line included | launches a reviewer | reviews, as "The review" says |

The line has two meanings and no more: `none`, and a review.
A word a brief from before carries after `review` is read as `review`.

A reviewer runs no test step and no suite, whatever the brief or the repo's `notes.md` says.
The tests are CI's `check`, which runs beside the review and has passed before `jmerge` merges, and the crewmate's own runs (the crew skill, "Do the task").
The one thing a reviewer runs is a targeted proof of the fact the change is safe because of ("The review", step 5).

## What a review covers

A review covers the lines the pull request changes, and reads them the way a tech lead would: not only "does this work", but whether it is the right change, whole, and no wider than it had to be.

- A finding is about a changed line, or about something a changed line breaks.
  In the second case it is written against the changed line that does the breaking, and says what breaks.
- A bug or weakness in code the pull request did not change is not fixed, not sent to the crewmate and not written in `## Review`, however real it is.
  Those are handled by other paths.
  Only their count is kept.
- The review asks for nothing beyond what the brief needed.

The questions a review answers, each about the changed code only:

| The question | Answered by |
|---|---|
| Does it meet the brief, the `Done when` lines above all? | the reviewer |
| Is it tested properly? A test must execute something: a new or changed test that only matches wording is a warning, and the remedy to name is a test that executes, not deleting it. | the reviewer |
| Does it do what the user wanted, not only what the brief's words say? | the reviewer |
| Is it correct? Six things to look for go with it: a change that is run twice or crashes halfway, shared state kept in step by structure or only by convention, a rule in prose that should be a check, an old path kept beside a new one, a check that reads a proxy and not the thing, a bug fix with no test. | the reviewer |
| Could it be done more simply or cheaply? Five things to look for go with it: a restructuring that makes whole branches or layers disappear, a file pushed past 1,000 lines, ad-hoc branches in an existing flow, thin wrappers, logic outside its canonical layer. | the reviewer, and "Wider than the brief" for one whose remedy is outside `Where` |
| Does it leave everything it did not mean to change unaffected? Two things to look for go with it: a changed line that does not trace to the task, and a removal of code the change did not orphan. | the reviewer |
| Is the diff wider than the brief's `Where`? A file outside it is a finding. | the reviewer, and "Wider than the brief" |
| Does it collide with work in flight? | the reviewer, by "In flight" |

The first seven are asked at the end of the intent, in the prompt the reviewer reads: the `SCOPE` text in "The review" is the one copy of them.
The things to look for under the fourth and fifth are adapted from pstack's reviewer (`THIRD_PARTY.md`), the two under the sixth from the Karpathy guidelines (`THIRD_PARTY.md`), and they widen nothing: each is asked of the changed lines only.
The last is the one place a reviewer looks beyond the diff, and only for files shared with other work, never for bugs.

## Launching

When this thread launches a reviewer, for `/pr-review` in a home or a crewmate's thread, `/pr-review <slug>`, or the crew skill's launch, and when a step names "A brief the user names": read `$T/../skills/pr-review/launching.md` now.

## The reviewer

This thread is a **reviewer**.
It reads the diff, judges what it found, proves one fact, reports, and ends.
It starts no subagent and no other thread: the review is this one thread.
It never edits a file, commits, pushes, or changes the pull request, and it never reads the crewmate's thread.

### Start

1. Read `$H/tasks/<slug>.md` and `$H/notes.md`.
   Nothing else from `$H`, but for what the blocks under "After the review" read by themselves.
   Then work out who this reviewer is, and then whether this message may start a review.

   Who this reviewer is goes on the section's `By:` line, under its heading: the provider, the model and the effort this thread runs on.
   Ask the thread itself: the `t3-code` server's `t3_thread_configuration` with no `threadId` (if your harness defers it, load it first).
   Run this with the block at the top, with what it printed, whole, and the message this thread was started with in place of the words in angle brackets.
   Keep what it prints, the `By:` line:

   ```sh
   asked='<the message this thread was started with, whole>'
   config='<what t3_thread_configuration printed, or nothing where this session has no such tool>'
   case $config in "<"*) config= ;; esac
   by=$(printf '%s' "$config" | jq -r '.modelSelection | [(.provider // .instanceId), .model, (.options[]? | select(.id | test("effort$"; "i")) | .value)] | join(" ")' 2> /dev/null)
   if [ -z "$by" ]; then
       n=$(printf '%s\n' "$asked" | awk '$(4) ~ /^[0-9]+$/ {print $(4); exit} {print 1}')
       by=$(uv run --project "$T/.." jroles review 2> /dev/null | sed -n "${n}p" |
           jq -r '[.provider, .model, (.options[]? | select(.id | test("effort$"; "i")) | .value)] | join(" ")' 2> /dev/null)
   fi
   echo "By: ${by:-inherit}"
   ```

   Each provider's effort is its own option, `effort`, `reasoningEffort` or `reasoning_effort`, and the line gives its value, so two reviewers of one pull request have two `By:` lines: `By: codex gpt-6-sol xhigh` and `By: cursor grok-4.7 xhigh`.
   Only a session with no `t3_thread_configuration` falls back on the line of the role map's review list the message's number names, as `jroles review` prints it now, and on `By: inherit` where it prints none.
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

   A section is the line `## Review` alone: a `Review:` or `Reviewer:` line, or those words inside another line, is none.
   A message that ends in a number is one reviewer of several, launched on that line of the role map's review list: it writes its own section beside the others', at the same head,
   and it is refused only where a section with its own `By:` line is there.
   On `stop`, say what it printed, the line it would accept included, and end: no review, no section.
   On `go`, go on.
   `$T/rerun.md` is the one statement of when a re-run needs `again`: jbus's nudge to a crewmate and the crew skill read the same file, so a re-run line they send always works.
   The message of a first launch is the plain `/pr-review run <slug>`.
   - Read the brief's `Review:` line as above.
     If it is `none`, say that its brief asks for no review, and stop: no review, no message to the crewmate, no section.
2. Read the pull request: `gh pr view <url> --json number,title,body,state,headRefName,headRefOid,files,statusCheckRollup`.
   The diff is read in step 3 of "The review".
   Open a file only to judge a finding, or to find and prove the safety fact.
3. Check the ground, and stop with the reason if any line fails:
   - `git status -sb`: this checkout is on the pull request's branch and has nothing uncommitted.
   - `git rev-parse HEAD` is the pull request's `headRefOid`.
     Keep it: this is the head under review.
4. Say in two lines what is about to be reviewed, then start.

### The review

When "Start" is done, and whenever a step names "The review" or one of its steps: read `$T/../skills/pr-review/the-review.md` now.

### No room

A reviewer that gives up says so, to the crewmate and in the brief, so that the pull request never waits for a review nobody is going to run.
It gives up only on exit 69 of the block of step 1, which is its sixth send that did not go on.

1. See where the line goes: the block of step 4 of "After the review", with `not run` for the verdict.
   Send that thread one line with `t3_thread_send`, and on `home` the thread "Telling the home" finds:
   `<slug>: the review of <url> at <the head kept at the start> was not run. The run block was sent six times and never went on, and its last answer was "<the last line it printed>". This pass reviewed nothing, and the pull request waits for the user's word: park a gate.`
2. Write the section.
   Run this with the block at the top, with the head kept at the start, the last line the block of step 1 printed, the `By:` line Start printed, and the thread id the line went to in place of the words in angle brackets.
   Where the line went to nobody, `sent` is the two words `not sent`:

   ```sh
   B="$H/tasks/<slug>.md"
   kept='<the head kept at the start>'
   why='<the last line the block of step 1 printed>'
   sent='<the thread id the line went to, or the two words "not sent">'
   by='<the By: line Start printed>'
   case $by in "<"*) by= ;; esac
   [ -f "$B" ] || { echo "no section: there is no brief at $B"; exit 1; }
   case $sent in
   "" | "not sent"* | "<"*)
       echo "no section: the line went to nobody, so the brief stays as it is and jbus tells the crewmate that no review came"
       exit 0 ;;
   esac
   if awk -v kept="$kept" -v by="$by" '/^## / {last = $(0); verdict = head = mine = ""} /^Verdict:/ {verdict = $(0)} /^Head:/ {head = $(2)} /^By: / {mine = $(0)} END {exit !(last == "## Review" && verdict == "Verdict: not run" && head == kept && mine == by)}' "$B"; then
       echo "no section: the brief already ends in a review of $kept that was not run"
       exit 0
   fi
   {
       [ -z "$(tail -c1 "$B")" ] || echo
       printf '\n## Review\n'
       if [ -n "$by" ]; then printf '%s\n' "$by"; fi
       printf 'Verdict: not run\n'
       printf 'Why: the run block was sent six times and never went on, and its last answer was "%s"\n' "$why"
       printf 'Head: %s   Unchanged by the review: not checked, no review ran\n' "$kept"
       printf 'Sent to: %s\n' "$sent"
   } >> "$B" && echo "written: ## Review with Verdict: not run, in $B"
   ```

   The section is not a review: `jmerge` reads it as a review with no verdict and merges nothing on it.
   Its `By:` line says whose it is, so that this reviewer's section at the same head, once it runs again, takes its place, and another reviewer's does not.
   Its `Head:` line is what lets the crewmate's thread rebase again (the crew skill, "A conflict").
   It is written only when the crewmate was told.
   A section nobody was told of would hide the pull request from jbus, which tells a crewmate of a pull request with no review (`unreviewed`) or with no second pass (`second`) and of nothing else here.
   Sent a second time for the same head, the block writes no second section.
3. Say the same in this thread in two lines, and stop without settling: a thread that settled would look like a review that was done.

### After the review

When the review has its verdict, and whenever a step names "After the review" or one of its steps, as "No room", "Outside the diff", "Telling the home" and "A scoped pass" do: read `$T/../skills/pr-review/after-the-review.md` now.

### Outside the diff

Write the lead's findings, the **Act on** and **Consider** ones of step 4 with what step 5 added, one to a line, each as `<severity> <file>:<line> <what is wrong> (principle: <name>) (bucket: <Act on or Consider>)`,
with its `(risk: <area>)` tag where it has one, in place of the middle line of this block.
A finding about a file as a whole has no `:<line>`.
A finding about what the change as a whole lacks (a `Done when` line it does not meet, a test it does not have) has `-` in place of the file and line: that form is for what the pull request leaves out, never for code it did not touch.
A finding about something a changed line breaks is written against that changed line before it goes in: if no changed line can be named for it, it goes in as it came, and the block drops it.

```sh
gh pr diff <url> | awk '
  pass == 2 {
    file = $(2)
    sub(/:[0-9]+$/, "", file)
    if ($(2) == "-" || $(2) in changed || file in removed) print
    else if (NF) dropped++
    next
  }
  old > 0 || new > 0 {
    mark = substr($(0), 1, 1)
    if (mark == "+") { changed[file ":" at++]; new-- }
    else if (mark == "-") { changed[file ":" at - 1]; changed[file ":" at]; old-- }
    else if (mark != "\\") { at++; old--; new-- }
    next
  }
  /^diff --git / { file = $NF; sub(/^b\//, "", file); changed[file]; seen = 1 }
  /^--- / { was = substr($(0), 5); sub(/^a\//, "", was) }
  /^\+\+\+ / {
    file = substr($(0), 5)
    sub(/^b\//, "", file)
    if (file == "/dev/null") removed[was]
    else changed[file]
  }
  /^@@ / {
    split($(2), o, ",")
    split($(3), n, ",")
    old = (2 in o) ? o[2] : 1
    new = (2 in n) ? n[2] : 1
    at = substr(n[1], 2) + 0
  }
  END {
    if (!seen) { print "no diff was read: nothing kept, nothing dropped" > "/dev/stderr"; exit 1 }
    print "Dropped: " dropped + 0
  }
' - pass=2 /dev/fd/3 3<<'FINDINGS'
<the findings, one to a line>
FINDINGS
```

- It prints the findings to keep, then the count dropped.
  Send and record the kept ones only.
  The dropped ones are named nowhere: not to the crewmate, not in the section, not to the home.
  The count goes in the section's `Dropped:` line.
- A line counts as changed when the pull request added it, or removed a line that sat just before or just after it.
  Any line of a file the pull request removed counts, and so does a file-level finding on any file in the diff, a renamed or binary one included.
- If it exits with something other than 0, `gh` gave no diff (no network, or a diff too large for GitHub to send).
  Nothing was kept and nothing dropped: do not send a review as clean.
  Run it once more, and if it fails again, say so in the section in place of the findings and send that.
- Do not look at what was dropped to see whether it was true.
  Whether it was true is not the question.

### Wider than the brief

```sh
WHERE=$(sed -n 's/^Where: //p' "$H/tasks/<slug>.md" | grep -o '`[^`]*`' | tr -d '`' | tr '\n' ' ')
PR=$(gh pr view <url> --json files) || exit 1
printf '%s\n' "$PR" | jq -r '.files[].path' | awk -v where="$WHERE" '
  BEGIN { n = split(where, w, " "); for (i = 1; i <= n; i++) sub(/\/$/, "", w[i]) }
  { for (i = 1; i <= n; i++) if ($(0) == w[i] || index($(0), w[i] "/") == 1) next; if (n) print }'
```

It prints each file the pull request changes that is outside the paths the brief's `Where:` line names, or nothing.
Each file printed is a finding, a warning with no line: the pull request is wider than its brief.
If the reading already raised the same file, keep one.
The block reads only the paths in backticks: a printed file that the `Where:` line's own words allow ("and the other skills only where they state a title") is not a finding.
A failed `gh` ends the block with exit code 1, and then the width was not checked: say so in the section, not that the pull request is no wider.
A brief whose `Where:` names no path in backticks prints nothing: say in the section that the width could not be checked.

A finding can be wider than the brief in a second way: it is about a changed line, and what it asks for is not in the brief's `Where`.
That happens with the fifth question's things to look for (a restructuring, a file to split, a branch to move into a module of its own, a wrapper to remove, logic to move to its canonical layer), when the remedy would change a file outside `Where`.
The `SCOPE` text asks the reading to say so in the finding.
Such a finding is kept, sent and recorded like any other, with these words at the end of its line: `for Noticed, not this pull request`.
It asks the crewmate for no fix: the crewmate writes it in the Result under "Noticed", where the home sees it as a possible plan entry.
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
Those lines go to the crewmate and into the section's `In flight:` line, as they are.
They say that two pieces of work touch the same file, so that whoever merges second knows: they are not a fault in this pull request and carry no severity.
Do not open the other pull requests or briefs to look further.
A failed `gh` ends the block with exit code 1, and then the section's `In flight:` line says "not checked", not "none".

### Telling the home

A repo runs with a home or with none, and a reviewer needs neither.
It sends the home of the brief it reviews a message in one case, and in no other: the block in step 4 of "After the review" said `home`, because the brief has no `Thread:` line to send the findings to, and the block below found a home.
A question for the user is asked in this thread, and a reviewer that stops early says why here: a thread that has asked shows as `waiting` in T3 Code, and that is what reaches the user.

Whom to send it to, in one call with the block at the top and `B` set to that brief, `$H/tasks/<slug>.md`:

```sh
named=$(sed -n 's/^Home:[[:space:]]*\([^[:space:]]*\).*/\1/p' "$B" 2> /dev/null | head -n 1)
first() { awk 'NF {print $(1); exit}' "${1}" 2> /dev/null; }
was() { sed -n 's/^Was home:[[:space:]]*\([^[:space:]][^[:space:]]*\).*/\1/p' "${1}" 2> /dev/null | head -n 1; }
D=
if [ -n "$named" ] && [ "$named" != "$(first "$H/home-id")" ] && [ "$named" != "$(was "$H/handoff.md")" ]; then
    D=$(find "$H/" -mindepth 1 -maxdepth 1 -type d 2> /dev/null | sort | while IFS= read -r d; do
        id=$(first "$d/home-id")
        old=$(was "$d/handoff.md")
        if [ -z "$id$old" ]; then continue; fi
        if [ "${d##*/}" = "$named" ] || [ "$id" = "$named" ] || [ "$old" = "$named" ]; then echo "$H/${d##*/}"; fi
    done | tail -n 1)
fi
D=${D:-$H}
if [ -s "$D/home-id" ]; then first "$D/home-id"; fi
```

It prints the id in the `home-id` of the brief's home, read now and never kept: `$H/home-id` for the root home, whose briefs have no `Home:` line, and `$H/<scope>/home-id` for a scoped home, whose briefs name the scope, `Home: <scope>`.
A brief names no thread, so no home's start or handoff changes it.
One written before this rule has a thread id on the line: an id that is in a scoped home's `home-id`, or on the `Was home:` line of its handoff, is that home, and any other id is the root home.
A scope is a directory of `$H` whose `home-id` holds an id or whose handoff has a `Was home:` line, and a line that names no such directory is the root home's: it is `jmerge`'s rule, and `whose` in the home skill,
so a brief has one home to all three.
Between a handoff and the next home's start the file is gone and the block prints nothing.
It is the crew skill's block, the same text.

If it prints a thread id, send that thread the message with `t3_thread_send`.
If it prints nothing, there is no home: send nothing, and write `Sent to: not sent, no home` in the section, as step 4 says. jbus passes the findings on.

### A scoped pass

A rebase gives a reviewed pull request another head.
`jmerge` compares the head the review saw with the rebased one by `git range-diff`.
When no line the patch adds or removes changed, the review carries over and no reviewer is launched.
When the content changed, which is a conflict someone resolved by hand, the pull request waits for one review of that change alone: jbus asks the crewmate to launch it,
and the message that starts this thread is `/pr-review run <slug> scoped <old range> <new range>`.
Each range is `<base>..<head>` in full commits: the reviewed patch, then the rebased one.

A scoped pass is also the review of a fix.
A fix pushed for a review's findings that changes a file outside `tests/` gets the same pass, of the fix alone, in place of a whole second review, and it is the last: a fix for its findings merges on the checks.
The crewmate launches it in the turn that pushes the fix, when the block of the crew skill's "A second pass" prints `scoped: launch the scoped reviewer`, and where it did not, jbus asks it to.
The message is the same one.
Its ranges are the patch up to the head the last review saw, then the patch up to the fixed head, so the range-diff shows the fix as the commits on the new side alone.
A path listed in `src/jmerge/guarded.txt` gets the stricter gate that `docs/jmerge.md` gives under "Protected and guarded paths".

It is one pass per rebased or fixed head, and never a full review.
It is not the second pass either: a brief that already has a `## Review` section is not refused for it, and in "Start" the check for a `## Review` section does not stop it.
The rest of "Start" holds: the brief's `Review:` line, the pull request, the ground.

1. Run this in this worktree, with the two ranges of the message in place of the words in angle brackets:

   ```sh
   old='<old range>'
   new='<new range>'
   head=$(git rev-parse HEAD)
   if [ "${new##*..}" != "$head" ]; then
       echo "stop: this worktree is at $head, and the scoped pass is of ${new##*..}"
   elif ! said=$(git range-diff --no-color "$old" "$new" 2>&1); then
       echo "stop: git range-diff could not compare the two ranges"
       printf '%s\n' "$said"
   else
       echo "Scope: range-diff $old $new"
       echo "Head: $head"
       printf '%s\n' "$said"
   fi
   ```

   On `stop`, say what it printed and end: no review, no section, and the thread is not settled.
   A head that moved is a rebase or a push made after jbus asked, and jbus asks again for the new head.
   Otherwise it prints the section's `Scope:` and `Head:` lines, whole, and under them the range-diff.
2. Review only what the range-diff shows as changed.
   Under a pair of commits marked `!`, that is each line with two signs, `-+`, `--`, `++` or `+-`: a line the patch adds or removes on one side alone.
   A commit on one side alone, marked `<` or `>`, is read whole against the commits of the other side.
   A pair marked `=` is not read, and neither is a line that only moved: a context line, a hunk header, the metadata, the commit message.
3. Give those lines the review of "The review", its six steps in order, with two things changed in the block of its steps 1 and 2.
   The first line of the `SCOPE` text reads "Review only what this range-diff shows a rebase or a fix changed in a patch that was reviewed before it: the lines with two signs, and a commit on one side alone. The rest of the patch has had its review."
   And the code the reading is given is the range-diff:
   `git range-diff --no-color '<old range>' '<new range>'` in place of `gh pr diff <url>` on the line that writes `$D/code`.
   The reading, the lead's judgment and the verdict are as they are for a first pass.
   The safety fact of step 5 is the one fact the rebased or fixed patch is still safe because of, proven at this head: it is never left out.
   A finding is about one of those lines, or about something it breaks.
4. Rule on the lines the rebase dropped on purpose.
   Run this in this worktree, with the block at the top.
   It prints one line for each `Dropped on rebase:` line the brief has at this head, and for each the diff of that file from the head before the rebase, which the crewmate kept under `refs/jstack/pre-rebase/<slug>/<its first 12 characters>`,
   to this one.
   The `Rebase:` line, where the brief has one, names that head; the crew's keep step writes the ref and no such line, so with none the block takes the newest ref of the slug, by commit date, which is the head before the last rebase:

   ```sh
   B="$H/tasks/<slug>.md"
   head=$(git rev-parse HEAD)
   short=$(printf %s "$head" | cut -c1-12)
   before=$(sed -n 's/^Rebase: patch .*, before \([0-9a-f]\{12\}\)[0-9a-f]\{28\}, head [0-9a-f]\{40\}$/\1/p' "$B" | tail -n 1)
   kept="refs/jstack/pre-rebase/<slug>/$before"
   if [ -z "$before" ]; then
       kept=$(git for-each-ref --sort=-committerdate --count=1 --format='%(refname)' "refs/jstack/pre-rebase/<slug>/")
   fi
   said=$(sed -n "s/^Dropped on rebase: \(.*\), [0-9]* of main's, [0-9]* of its own, at $short: ..*/\1/p" "$B" | sort -u)
   if [ -z "$said" ]; then
       echo "no drops: the brief has no Dropped on rebase line at $head"
   elif [ -z "$kept" ] || ! git rev-parse -q --verify "$kept^{commit}" > /dev/null; then
       echo "not upheld: the head before the rebase is not kept under refs/jstack/pre-rebase/<slug>, so no drop can be read"
       printf '%s\n' "$said" | sed 's/^/drop: /'
   else
       printf '%s\n' "$said" | while IFS= read -r file; do
           echo "drop: $file"
           grep -F "Dropped on rebase: $file, " "$B" | grep -F ", at $short: " | tail -n 1
           git diff "$kept" HEAD -- "$file"
       done
   fi
   ```

   On `no drops`, the section gets no `Drops:` line.
   Otherwise read each diff against the reason on its line.
   A drop is upheld when the reason is true of the diff and the lines are right to be gone: the task replaces them, or the default branch's change makes them wrong.
   It is not upheld when the reason does not hold, the diff shows a line the task or the default branch still needs, or the diff could not be read.
   The section then has, right under `Scope:`, one line `Drops: upheld <file>, <file>` that names every file upheld, and one line `Drops: not upheld <file>: <why>` for each that is not.
   A drop that is not upheld is also a finding, of severity `error`, at that file.
   `jmerge` merges a rebase that dropped lines only when every such file is on the `Drops: upheld` line, and holds one that is not upheld for the user.
5. Report as "After the review" says for a first pass: the head checked again, what is outside the pull request's diff dropped, the findings sent where that pass sends them, and `$T/review.md` appended, filled in.
   The message begins "Scoped pass, of what the rebase changed.", or after a fix "Scoped pass, of the fix pushed after the review.", in place of "One review pass." The section has one line more, right under `Verdict:`,
   the `Scope:` line the block of step 1 printed, and under it the `Drops:` lines of step 4.
   Then settle this thread as a first pass does.

`jmerge` merges the rebased head once a `## Review` names it on its `Head:` line, with its findings handled as any review's.
A new rebase after that is compared again, from this head.
A fixed head is merged the same way.
