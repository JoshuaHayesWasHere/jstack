---
name: pr-review
description: Have a finished pull request reviewed in a fresh thread - one review thread per pull request reads its diff itself, judges what it found, and proves the one safety fact by running code (pstack's review, with no reviewer subagents and no fixes), sends the findings to the thread that did the work, and records them in the brief. Use when the user invokes /pr-review or $pr-review in a home or in a crewmate's thread, or asks to review the pull requests that have finished.
tip: has a finished pull request reviewed in a fresh thread | review the pull request | review the pull requests | review the pr | review this pr | review my pr
user-invocable: true
disable-model-invocation: true
card: "Run the pipeline | 4 | Starts one review thread per pull request. It reads the diff itself, judges what it found, and one command proves the fact the change is safe because of. It fixes nothing, and jbus archives it when the pull request merges or closes. | Reach for it when a pull request opens. The crewmate does this by itself. | model: a crewmate; op: the operator | look: rev"
---

# pr-review

A pull request is reviewed by a **reviewer**: a new thread that knows the brief and the pull request and nothing of the conversation that wrote the code. The thread `/pr-review` is typed in never reviews. It launches the reviewer, gives the user the link, and goes back to what it was doing.

There is one pass per pull request: the reviewer reviews once and the crewmate fixes once. A fix that changes files under `tests/` only is not reviewed: what stands behind it is the pull request's own checks. A fix that changes any other file gets one scoped pass, of the fix alone, by another reviewer, and that pass is the last ("A scoped pass"). The crewmate's own check decides which it is (the crew skill, "A second pass"). The reviewer finds, and fixes nothing: what to do with a finding is for the thread that did the work.

```sh
R=$(basename "$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")")
H=~/.local/state/home/$R
T=$(realpath ~/.claude/skills/pr-review/../../templates)
```

`$T` is the `templates/` directory of the repo this skill lives in. Each template there is the one copy of its text: read it when a step names it, not before.

## Which part this thread plays

| The message | Typed in | This thread |
|---|---|---|
| `/pr-review run <slug>` | a thread a launcher made | is the **reviewer** for that brief: go to "The reviewer" |
| `/pr-review <slug>` | anywhere | launches one reviewer, for that brief, whatever its `Review:` line says |
| `/pr-review` | a home (the repo's main checkout) | launches a reviewer for every brief that is ready |
| `/pr-review` | a crewmate's thread (a worktree whose branch has a brief) | launches one reviewer, for that crewmate's pull request |

Only a launcher sends the `run` form. `git rev-parse --git-dir` and `--git-common-dir` give the same path in the main checkout and different paths in a worktree. In a worktree the slug is the brief in `$H/tasks/` whose result names the current branch.

## The brief's `Review:` line

A brief may carry one line that says whether its pull request gets a review. The home writes it, when it writes the brief; nothing here changes it, but for the one case under "A brief the user names". It is a field of its own, like `Thread:`: a line that starts with `Review:`, and its value is the word after that. The same words inside the task's text, a `Done when` line or a result do not count. Read it with this, and no other way:

```sh
awk '/^Review:/ {print $(2); exit}' "$H/tasks/<slug>.md"
```

It prints the value, or nothing for a brief with no such line.

| The brief has | The launcher | The reviewer |
|---|---|---|
| `Review: none` | passes the brief over, unless the user named it | does nothing: it says so and stops |
| anything else, no `Review:` line included | launches a reviewer | reviews, as "The review" says |

The line has two meanings and no more: `none`, and a review. A word a brief from before carries after `review` is read as `review`.

A reviewer runs no test step and no suite, whatever the brief or the repo's `notes.md` says. The tests are CI's `check`, which runs beside the review and has passed before `jmerge` merges, and the crewmate's own runs (the crew skill, "Do the task"). The one thing a reviewer runs is a targeted proof of the fact the change is safe because of ("The review", step 5).

## What a review covers

A review covers the lines the pull request changes, and reads them the way a tech lead would: not only "does this work", but whether it is the right change, whole, and no wider than it had to be.

- A finding is about a changed line, or about something a changed line breaks. In the second case it is written against the changed line that does the breaking, and says what breaks.
- A bug or weakness in code the pull request did not change is not fixed, not sent to the crewmate and not written in `## Review`, however real it is. Those are handled by other paths. Only their count is kept.
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

The first seven are asked at the end of the intent, in the prompt the reviewer reads: the `SCOPE` text in "The review" is the one copy of them. The things to look for under the fourth and fifth are adapted from pstack's reviewer (`THIRD_PARTY.md`), the two under the sixth from the Karpathy guidelines (`THIRD_PARTY.md`), and they widen nothing: each is asked of the changed lines only. The last is the one place a reviewer looks beyond the diff, and only for files shared with other work, never for bugs.

## Launching

The brief's reviewer, if a thread has already launched one and written it in the result:

```sh
awk '/^Reviewer:/ && $(2) !~ /^none/ {print $(2); exit}' "$H/tasks/<slug>.md"
```

It prints that reviewer's thread id, or nothing. A line that says `Reviewer: none`, which a crewmate with no launch tool writes, is no reviewer.

1. Find the briefs that are **ready**. Run this with the block at the top, in a home with no slug with `*` for `<slug>`. It is the only check:

   ```sh
   PASS=first
   checks() {
       view=$(gh pr view ${1:+"${1}"} --json headRefOid,statusCheckRollup) || { echo "wait: could not ask GitHub"; return; }
       never=$(printf '%s\n' "$view" |
           jq -r '.statusCheckRollup[]? | select(.status == "COMPLETED" and (.conclusion | IN("SUCCESS", "NEUTRAL", "SKIPPED") | not)) | .detailsUrl // empty' |
           sed -n 's|^https://[^/]*/\([^/]*/[^/]*\)/actions/runs/[0-9]*/job/\([0-9]*\)$|& \1 \2|p' |
           while read -r url repo job; do
               if gh api "repos/$repo/actions/jobs/$job" | jq -e '.steps | type == "array" and length == 0' > /dev/null; then echo "$url"; fi
           done)
       printf '%s\n' "$view" | jq -r --arg never "$never" '
           ($never | split("\n")) as $never
           | [.statusCheckRollup[]? |
               if .state then (if .state == "SUCCESS" then "passed" elif (.state | IN("PENDING", "EXPECTED")) then "pending" else "failed" end)
               elif .status != "COMPLETED" then "pending"
               elif (.conclusion | IN("SUCCESS", "NEUTRAL")) then "passed"
               elif .conclusion == "SKIPPED" then "skipped"
               elif (.detailsUrl // "" | IN($never[])) then "unstarted"
               else "failed" end] as $each
           | if ($each | length) == 0 then "wait: no check is reported yet"
             elif ($each | index("failed")) then "failed: a check ran and failed"
             elif ($each | index("pending")) then "wait: a check has not finished"
             elif ($each | index("passed") | not) then "unrun: no check ran at \(.headRefOid)"
             elif ($each | index("unstarted")) then "failed: a check never started beside checks that ran"
             else "passed: every check passed at \(.headRefOid)" end'
   }
   for B in "$H"/tasks/<slug>.md; do
       past= why=
       pr=$(awk '/^## Result/ {pr = ""; done = 0; result = 1} result && /^Status: done/ {done = 1} result && $(1) == "Branch:" {pr = $(NF)} END {if (done) print pr}' "$B")
       case $pr in
       http*)
           if [ "$PASS" = first ] && awk '/^## Review$/ || (/^Reviewer:/ && $(2) !~ /^none/) {had = 1} END {exit !had}' "$B"; then
               past="it has a review or a reviewer, and it is one pass per pull request"
           elif state=$(gh pr view "$pr" --json state | jq -r .state) && [ -z "$state" ]; then
               why="GitHub could not be asked for its pull request"
           elif [ "$state" != OPEN ]; then
               past="its pull request is not open: $state"
           fi ;;
       *) past="its last Result does not say Status: done and name a pull request" ;;
       esac
       if [ -n "$past" ]; then
           why=$past
           case "<slug>" in "*") continue ;; esac
       elif [ -n "$why" ]; then
           :
       elif [ "$(awk '/^Review:/ {print $(2); exit}' "$B")" = none ]; then
           why="its brief asks for no review"
       else
           said=$(checks "$pr")
           case $said in
           passed*) head=${said##* } ;;
           "wait: a check has not finished" | "wait: no check is reported yet")
               head=$(gh pr view "$pr" --json headRefOid | jq -r '.headRefOid // empty') ;;
           *) head= ;;
           esac
           if [ -z "$head" ]; then why="its checks, $said"; fi
       fi
       if [ -n "$why" ]; then
           echo "$(basename "$B" .md): not ready, $why"
       else
           echo "$(basename "$B" .md): ready, $pr at $head"
       fi
   done
   ```

   It prints one line for each brief, `<slug>: ready, <url> at <head>` or `<slug>: not ready, <the first thing it is short of>`. With `*` it leaves out the briefs of the past: those with no pull request, with a pull request that is merged or closed, or with a review or a reviewer already. A brief is ready when all of these hold:
   - its last `## Result` says `Status: done` and names a pull request;
   - it has no `## Review` section and no reviewer: no `Reviewer:` line but one that says `none`, which the block above reads the same way;
   - that pull request is open;
   - its `Review:` line, read as above, is not `none`;
   - the pull request's checks are not red. `checks` is the crew skill's function, the same text, and prints its four answers: `passed`, `failed`, `wait`, `unrun` (the crew skill, "The checks"). `passed` and `wait` are ready: a review runs beside the checks, and green is what `jmerge` merges on, not what a review waits for. The `wait` of a GitHub that could not be asked is not ready: no rollup was read. `failed` is never ready: a red pull request is fixed first, and its reviewer is launched on the push. `unrun` means no check ran, every one failed with no step run or was skipped, because the repo's CI starts no job: nothing stands in for a check that did not run, so the brief is not ready, whatever its Result says of a check command that passed in the crewmate's worktree.

   One thing the block cannot see: `t3_thread_list` with `titleContains: "review: <slug>"` finds no thread. Check it for each brief printed as ready.

   In a home with no slug, take every ready brief, oldest first, and at most three. Name the ones left over, and the ones passed over with the reason in a few words each: for a brief with `Review: none`, that its brief asks for no review. In a crewmate's thread with no slug, take that one brief; if it is not ready, say which line fails and stop. With a slug, first do what "A brief the user names" says, then take that one brief the same way.
2. A brief that already has a `## Review` section or a reviewer is refused: say so, and that it is one pass per pull request. A scoped pass is not refused: the crewmate launches one for a fix it pushed for a review's findings, jbus asks it for one after a rebase that changed the content of a reviewed patch, its message is `/pr-review run <slug> scoped <old range> <new range>` with the two ranges as the crew skill's block or jbus gave them, its title is `review: <slug>, scoped`, and it is launched as a second pass is, with `PASS=second` ("A scoped pass"). A second pass is launched in two cases only, and then the message is `/pr-review run <slug> again`: the user asks for another pass in so many words, or this is the crewmate's thread and the block of the crew skill's "A second pass" printed `needed: launch the second reviewer`, which it prints only for a brief from before a fix got a scoped pass. For a second pass send the readiness block with `PASS=second` as its first line: the lines about `## Review` and a reviewer then do not apply, the others do. The title is `review: <slug>, second pass`. A reviewer that ended its turn writing nothing is sent back to work with the same `again` line, whether or not the brief has a `## Review` (`$T/rerun.md`).
3. Find the worktree that has the pull request's branch checked out: `git worktree list --porcelain`. The reviewer runs there (see "Where a run starts"). If no worktree has it, say so and pass that brief over.
4. Start the reviewer with the `t3-code` server's `t3_thread_launch` (if your harness defers it, load it first).

   ```json
   {
     "title": "review: <slug>",
     "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<the pull request's branch>"},
     "message": "/pr-review run <slug>"
   }
   ```

   Before this launch, run `uv run --project "$T/.." jroles review` with the block at the top. When it prints a JSON object, that line is the `<model selection>`, and the `t3_thread_launch` call is this one, which starts the reviewer on the model the role map names. When it prints nothing, the call is the one above. Any other line it prints is on stderr and says why the map gives no model: the call is the one above then too, and the user is told that line. When it exits 75 and prints no JSON, both Claude instances are capped by a usage limit and the line on stderr says until when: make no launch, and say that line. A selection it prints may name `claudeAgent_claude_prime` as its `instanceId`: that is the failover, and the launch is made with it as printed.

   ```json
   {
     "title": "review: <slug>",
     "workspaceStrategy": {"type": "existing_worktree", "worktreePath": "<that worktree>", "branch": "<the pull request's branch>"},
     "message": "/pr-review run <slug>",
     "modelSelection": <model selection>
   }
   ```

   - Leave the project and modes out, and the model unless `jroles` printed one. What is left out, the reviewer inherits from this thread.
   - A launch has no retry key. If the call fails or its reply is lost, look for the thread with `t3_thread_list` (`titleContains: "review: <slug>"`) before launching again.
   - If the session has no such tool, tell the user instead: "Open a new thread in this project, in the worktree of `<branch>`, and type `/pr-review run <slug>`."
5. Give the user the links, one line each: `[review: <slug>](t3-thread://v1/<threadId>)`. Then stop. Do not wait for a reviewer, poll it, or read its thread: its findings go to the crewmate and into the brief.

### A brief the user names

`Review: none` is the home's choice for a task it took to be text only or throwaway. A user who types `/pr-review <slug>` has asked for that brief's review by name, and their word outranks the line. So with a slug, and only then, run this before the readiness check:

```sh
B="$H/tasks/<slug>.md"
if [ "$(awk '/^Review:/ {print $(2); exit}' "$B")" = none ]; then
    awk '/^Review:/ && !seen {seen = 1; print "Review: review (was none: the user asked for this review by name)"; next} {print}' "$B" > "$B.named" &&
        mv "$B.named" "$B" &&
        echo "was none, now review: the user named it"
fi
```

It changes the brief's `Review:` line from `none` to `review` and says so, and prints nothing for any other brief. The user naming the brief is the user's word for a review, so from then on it is a reviewed pull request like any other, and `jmerge` merges (run by jbus, or by the home when there is one) it when it is fixed and green: the line is what the reviewer, the crewmate and the merge check all read. Tell the user in one line that the brief said `none` and is being reviewed on their word.

It runs only on the path the user types, `/pr-review <slug>` in a home or in a crewmate's thread. Never run it for `/pr-review` with no slug or for a crewmate's own launch. And never on `/pr-review run <slug>`, which a thread sends and no user types: a reviewer changes no brief's line, and the first block of its review leaves a `none` brief as it is and exits 78.

## The reviewer

This thread is a **reviewer**. It reads the diff, judges what it found, proves one fact, reports, and ends. It starts no subagent and no other thread: the review is this one thread. It never edits a file, commits, pushes, or changes the pull request, and it never reads the crewmate's thread.

### Start

1. Read `$H/tasks/<slug>.md` and `$H/notes.md`. Nothing else from `$H`, but for what the blocks under "After the review" read by themselves. Then decide whether this message may start a review, with this, putting the message this thread was started with, whole, in place of the words in angle brackets:

   ```sh
   B="$H/tasks/<slug>.md"
   asked='<the message this thread was started with, whole>'
   case $asked in
   "/pr-review run <slug> scoped "*) echo "go: a scoped pass, as \"A scoped pass\" says" ;;
   *)
       if ! grep -qx '## Review' "$B"; then
           echo "go: the brief has no ## Review, so this is the review it is owed"
       elif [ "${asked##* }" = again ]; then
           echo "go: a second pass, the brief has a ## Review and the message ends in again"
       else
           echo "stop: the brief has a ## Review and the message does not end in again"
           echo "the line I accept: /pr-review run <slug> again"
           sed 's|{slug}|<slug>|g' "$T/rerun.md"
       fi ;;
   esac
   ```

   A section is the line `## Review` alone: a `Review:` or `Reviewer:` line, or those words inside another line, is none. On `stop`, say what it printed, the line it would accept included, and end: no review, no section. On `go`, go on. `$T/rerun.md` is the one statement of when a re-run needs `again`: jbus's nudge to a crewmate and the crew skill read the same file, so a re-run line they send always works. The message of a first launch is the plain `/pr-review run <slug>`.
   - Read the brief's `Review:` line as above. If it is `none`, say that its brief asks for no review, and stop: no review, no message to the crewmate, no section.
2. Read the pull request: `gh pr view <url> --json number,title,body,state,headRefName,headRefOid,files,statusCheckRollup`. The diff is read in step 3 of "The review". Open a file only to judge a finding, or to find and prove the safety fact.
3. Check the ground, and stop with the reason if any line fails:
   - `git status -sb`: this checkout is on the pull request's branch and has nothing uncommitted.
   - `git rev-parse HEAD` is the pull request's `headRefOid`. Keep it: this is the head under review.
4. Say in two lines what is about to be reviewed, then start.

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
  play=$(awk '/^Playbook:/ {print $(2); exit}' "$BRIEF")
  P="$T/../playbooks/$play.md"
  case $play in
  "" | none) ;;
  *)
    if [ "${play#*/}" != "$play" ] || [ ! -f "$P" ]; then
      printf '\nPlaybook: %s, which is no playbook here: the crewmate worked with none.\n' "$play"
    elif by=$(sed -n 's/^Run by: //p' "$P" | head -n 1) && [ "${by%%,*}" != "a crewmate" ]; then
      printf '\nPlaybook: %s, which is for %s and not a crewmate: the crewmate worked with none.\n' "$play" "${by%%,*}"
    else
      cited=$(grep -o 'principles/[a-z0-9-]*\.md' "$P" | awk '!seen[$(0)]++' | while read -r file; do
        [ -f "$T/../$file" ] || continue
        name=${file#principles/}
        awk -v name="${name%.md}" '
          /^# / {head = 1; next}
          head && NF {printf "%s%s", (on++ ? " " : "- " name ": "), $(0); next}
          on {exit}
          END {if (on) print ""}' "$T/../$file"
      done)
      printf '\nPlaybook: %s, the steps the crewmate worked by.\n' "$play"
      if [ -n "$cited" ]; then printf 'The principles it cites, and when each applies:\n%s\n' "$cited"; fi
    fi ;;
  esac
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
- First it asks the machine for room. `jgauge room` is the home skill's check before a launch, the one copy of it, in `src/jgauge/room.sh` of the repo this skill lives in: the one-minute load against the core count, the available memory, the memory pressure, the file slots of `/tmp`, and the share of the plan's five-hour and weekly limit already used. Its thresholds are the first lines of that file: change one there. A review asks with `--light`, which skips the load: a review is about 2% of one core, since its time is the model's, and its one heavy step, the proof, runs in the short test lane, which bounds it. Memory, memory pressure, `/tmp` and the plan still hold a review. It prints `go`, or `wait: ` and the first reading with no room. A `note: ` line says a limit is not known, and the review goes on all the same.
- The wait for room is this call, and nothing else. With `--wait 540` the check looks again every 15 seconds until it says `go` or nine minutes have passed. On `go` the block goes on by itself. So send it as a foreground command with a time limit of 10 minutes (600000 ms), and never as a background command. When the nine minutes pass with no room, the block prints the last `wait: ` line, builds nothing and exits 75: start no reviewer, and send the same block again at once, in this same turn. A call that was cut off before it printed anything is sent again the same way. A check that did not run is a `wait` too, and exits 75 at once.
- Never end the turn to wait for room, and never leave a check, a loop or a timer in the background to wait in your place: nothing wakes a reviewer when the machine has room, and the pull request would wait for a review that nobody runs. The block counts its own sends for this slug and head, in a file beside the directories it builds, a send that was cut off included, and forgets them on `go`. The sixth send with no room, about an hour in, prints the last answer and exits 69: give up as "No room" below says, and send the block no more.
- A brief with `Review: none` gets exit code 78 and nothing built: say that its brief asks for no review, and stop.
- Then it does steps 1 and 2 of the interrogate skill with nothing left to ask. The scope is the pull request's diff, `gh pr diff <url>`. The intent is the brief from `Task:` to the end of `Decisions:`, word for word, then, where the brief has a `Skills:` line that is not `none`, that line with what each named skill owes and the artifact the Results hold for each, as `jbriefs --skills-run` prints it with `jmerge`'s own reading, then, where the brief names a playbook run by a crewmate, its name and the "Apply when" paragraph of each principle it cites, read from the playbook's own `principles/<name>.md` citations, and after it the `SCOPE` text. That text is how the scope rule and the seven questions reach the reading of step 3, and it is the one copy of them: the interrogate skill reads questions 4 and 5 out of this block for its own reviewers, which is why the `SCOPE` lines start at the start of a line.
- Last it fills the interrogate skill's `references/reviewer-prompt.md` with the intent, the diff, its `references/rubric.md`, its `references/code-quality-review.md` and questions 4 and 5, and prints the path of the prompt it wrote, a file in a directory of its own under `/tmp`. The diff is in it as GitHub sent it, not retyped by this thread. Keep the path: step 3 reads it, and the proof of step 5 is written beside it.
- Exit code 1 means `gh` gave no diff or the template could not be filled, and the line above it says which. Nothing was reviewed: send the block once more, and if it fails again, write a section with `Verdict: not run` and the reason, tell the crewmate, and stop without settling.

**3. The reading.** Read the file the block printed, from its first line to its last, in parts if it is long, and do what it says, in this thread: it is the adversarial review of this pull request's diff, and it asks for a list of findings. Read whatever the diff calls or is called by, and change nothing. Start no `Agent` call and no thread for it. Write the list down, or "no findings", before step 4: that list is what the lead judges.

**4. Lead judgment.** Read step 5 of `$T/../skills/interrogate/SKILL.md` and its `references/lead-judgment.md` now, and judge the list of step 3 as they say: merge the findings that say the same thing, then put each in one of pstack's four buckets. Judge it against what the reading was not given: the brief's decisions, and the repo to check a claim against.

- **Act on** and **Consider** are the review's findings. Write each as one line, `<severity> <file>:<line> <what is wrong> (principle: <name>)`, in the forms "Outside the diff" gives. The tag names the principle the finding breaks, one the intent lists, or is `(principle: none)`. The severity is `error`, `warning` or `info`: the reading's `critical` is written `error`, the highest, its `warning` stays `warning`, and its `nit` is `info`. A crewmate declines an `info` finding by default and leaves it for a follow-up, so rate a thing `warning` when it must be fixed in this pull request.
- **Noted** and **Dismissed** are counted, not sent. Each count is a line of the section, and each dismissed finding keeps one line there with the reason: it is what lets the user overrule the lead. Neither goes to the crewmate.
- The buckets are the lead's reading. What the crewmate does with a finding is still its own: `Finding: fixed`, or `Finding: not fixed` with a reason (the crew skill, "The review").

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
    setsid sh -c 'uv run --project "${2}" jgauge test-slot --short --thread "${3}" -- sh "${1}/proof.cmd" > "${1}/proof.out" 2>&1; echo $? > "${1}/proof.exit"' proof "$D" "$T/.." '<thread id>' < /dev/null > /dev/null 2>&1 &
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

### No room

A reviewer that gives up says so, to the crewmate and in the brief, so that the pull request never waits for a review nobody is going to run. It gives up only on exit 69 of the block of step 1, which is its sixth send that did not go on.

1. See where the line goes: the block of step 4 of "After the review", with `not run` for the verdict. Send that thread one line with `t3_thread_send`, and on `home` the thread "Telling the home" finds: `<slug>: the review of <url> at <the head kept at the start> was not run. The run block was sent six times and never went on, and its last answer was "<the last line it printed>". This pass reviewed nothing, and the pull request waits for the user's word: park a gate.`
2. Write the section. Run this with the block at the top, with the head kept at the start, the last line the block of step 1 printed, and the thread id the line went to in place of the words in angle brackets. Where the line went to nobody, `sent` is the two words `not sent`:

   ```sh
   B="$H/tasks/<slug>.md"
   kept='<the head kept at the start>'
   why='<the last line the block of step 1 printed>'
   sent='<the thread id the line went to, or the two words "not sent">'
   [ -f "$B" ] || { echo "no section: there is no brief at $B"; exit 1; }
   case $sent in
   "" | "not sent"* | "<"*)
       echo "no section: the line went to nobody, so the brief stays as it is and jbus tells the crewmate that no review came"
       exit 0 ;;
   esac
   if awk -v kept="$kept" '/^## / {last = $(0); verdict = head = ""} /^Verdict:/ {verdict = $(0)} /^Head:/ {head = $(2)} END {exit !(last == "## Review" && verdict == "Verdict: not run" && head == kept)}' "$B"; then
       echo "no section: the brief already ends in a review of $kept that was not run"
       exit 0
   fi
   {
       [ -z "$(tail -c1 "$B")" ] || echo
       printf '\n## Review\nVerdict: not run\n'
       printf 'Why: the run block was sent six times and never went on, and its last answer was "%s"\n' "$why"
       printf 'Head: %s   Unchanged by the review: not checked, no review ran\n' "$kept"
       printf 'Sent to: %s\n' "$sent"
   } >> "$B" && echo "written: ## Review with Verdict: not run, in $B"
   ```

   The section is not a review: `jmerge` reads it as a review with no verdict and merges nothing on it. Its `Head:` line is what lets the crewmate's thread rebase again (the crew skill, "A conflict"). It is written only when the crewmate was told. A section nobody was told of would hide the pull request from jbus, which tells a crewmate of a pull request with no review (`unreviewed`) or with no second pass (`second`) and of nothing else here. Sent a second time for the same head, the block writes no second section.
3. Say the same in this thread in two lines, and stop without settling: a thread that settled would look like a review that was done.

### After the review

1. Check the head again, and name the patch that was reviewed. Run this in this worktree, with the head kept at the start in place of the words in angle brackets:

   ```sh
   kept='<the head kept at the start>'
   if ! view=$(gh pr view <url> --json baseRefName,headRefOid); then
       echo "Head: $kept   Unchanged by the review: not checked, could not ask GitHub"
       echo "Patch-id: not worked out, could not ask GitHub"
       exit 1
   fi
   if [ "$(printf %s "$view" | jq -r .headRefOid)" = "$kept" ] && [ "$(git rev-parse HEAD)" = "$kept" ] && [ -z "$(git status --porcelain)" ]; then
       same=yes
   else
       same=no
   fi
   echo "Head: $kept   Unchanged by the review: $same"
   base=$(printf %s "$view" | jq -r .baseRefName)
   if git fetch -q origin "$base"; then
       echo "Patch-id: $(git diff "$(git merge-base "origin/$base" "$kept")" "$kept" | git patch-id --stable | cut -d' ' -f1)"
   else
       echo "Patch-id: not worked out, could not fetch origin/$base"
       exit 1
   fi
   ```

   It prints the section's `Head:` and `Patch-id:` lines whole. `yes` means the pull request's head and this checkout's are both still the head kept at the start, with nothing uncommitted. On `no`, say that first, in the message and in the section. The crewmate's thread may push or rebase in this worktree while the review is out, and a `no` is how that shows. The review is still of the head the `Head:` line names, and its verdict stands for that head: whatever moved after it is the crewmate's to account for, and its second-pass check compares from that head. The patch-id names the patch that was reviewed, whatever commit carries it: the same command over a rebased head gives the same id when the rebase left the patch as it was, which is how the crew skill's "A conflict" tells. It always prints a `Head:` line, since the head reviewed is known whatever GitHub answers: the crew skill and `jmerge` read it. On exit code 1 the lines say what could not be asked or worked out: write them in the section as printed.
2. Drop what is outside the diff: "Outside the diff". From here on, the findings are the ones that block kept.
3. Add what the reviewer finds itself: "Wider than the brief" and "In flight".
4. See where the findings go, in one call with the block at the top, with this pass's verdict in place of the words in angle brackets:

   ```sh
   B="$H/tasks/<slug>.md"
   verdict='<clean, findings or not run>'
   thread=$(awk '/^Thread:/ {print $(2); exit}' "$B")
   owed() {
       if [ "$verdict" != clean ]; then
           echo "the pass has something to say"
           return
       fi
       before=$(awk '/^## / {review = ($(0) == "## Review")} review && /^Verdict: (clean|findings)$/ {n++} END {print n + 0}' "$B")
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
       scope=
       if [ "$D" != "$H" ]; then scope=${D##*/}; fi
       if [ "$before" = 0 ]; then
           echo "the Fixed: line, which a first review is answered with"
       elif ! grep -q '^Fixed: ' "$B"; then
           echo "the Fixed: line, which the Result does not have yet"
       elif [ -n "$(cat "$H/home-thread" 2> /dev/null | tr -d '[:space:]')" ]; then
           echo "the fixed and green line, which a home that merges hears from the crewmate"
       elif [ -n "$scope" ]; then
           echo "a gate, since jbus merges no pull request of the scoped home $scope"
       elif ! view=$(gh pr view <url> --json mergeable,headRefOid,statusCheckRollup) || [ "$(printf %s "$view" | jq -r .mergeable)" != MERGEABLE ]; then
           echo "a rebase, which waits for this section while GitHub does not say MERGEABLE"
       elif printf %s "$view" | jq -e 'any(.statusCheckRollup[]?; if .state then (.state | IN("SUCCESS", "PENDING", "EXPECTED") | not) else .status == "COMPLETED" and (.conclusion | IN("SUCCESS", "NEUTRAL", "SKIPPED") | not) end)' > /dev/null; then
           echo "a red check, whose rebase or fix waits for this section"
       elif grep -qsF "rebase|<slug>|$(printf %s "$view" | jq -r '.headRefOid // empty' | cut -c1-12)" "${JBUS_STATE_DIR:-$HOME/.local/state/jbus}"/*/sent.json; then
           echo "a rebase, which jbus asked for at this head and which waits for this section"
       fi
   }
   case $verdict in
   clean | findings | "not run") owes=$(owed) ;;
   *) owes="not filled in" ;;
   esac
   if [ "$owes" = "not filled in" ]; then
       echo "not filled in: put clean, findings or not run in place of the placeholder"
   elif [ -z "$owes" ]; then
       echo "nobody: a clean pass after the first leaves the crewmate nothing to do, so no message is sent, and the section says Sent to: not sent, clean"
   elif [ -n "$thread" ]; then
       echo "crewmate $thread: the findings go there, and the home is sent nothing"
   else
       echo "home: the brief has no Thread: line, so the findings go to the home, when there is one"
   fi
   ```

   On `nobody`, send no message, to the crewmate or to anyone, and write `Sent to: not sent, clean` in the section. It is printed only for a second or scoped pass whose verdict is `clean`, on a pull request `jmerge` can merge with no further line from the crewmate: the `Fixed:` line is written and stays as it is, jbus merges, GitHub says `MERGEABLE`, no check is red, and jbus has asked for no rebase at this head. A message there would wake a thread that has nothing to push and nothing to launch. `jmerge` reads the section from the brief, and jbus's relay passes on no section whose verdict is `clean`. The lines for work in flight and a head that moved under the review are then in the section alone. A clean first review is still sent, and so is a clean later pass that leaves the crewmate something to do. On `not filled in`, nothing was decided: fill in the verdict and run it again.

   On `crewmate` and on `home`, nothing is sent yet: step 5 writes the section first, and sends after it.
5. Read `$T/review.md` now. Append it, filled in, to `$H/tasks/<slug>.md`, before anything is sent: the brief is where `jmerge` and jbus read the review, and a message is only the notice of it. A reviewer that sent first and was cut off, or whose append failed, left a verdict in one thread and none in the brief, and the pull request waited for a section nobody was going to write. Where step 4 printed `nobody`, run its block once more now that the section is on disk: the crewmate's thread puts a rebase off while a review's section is not written, and one may have come since step 4. If it no longer prints `nobody`, send the thread it names one line saying the review is clean, and the `Proof:` line. The section stays as it is. Then run this with the block at the top, with the head kept at the start in place of the words in angle brackets. It is the only gate on a send, and on settling:

   ```sh
   B="$H/tasks/<slug>.md"
   kept='<the head kept at the start>'
   if awk -v kept="$kept" '/^## / {review = ($(0) == "## Review")} review && $(1) == "Head:" && $(2) == kept {found = 1} END {exit !found}' "$B"; then
       echo "written: the brief has a ## Review of $kept, so what step 4 named may be sent"
   else
       echo "not yet: the brief has no ## Review of $kept: append the section first, and send nothing before it is there"
   fi
   ```

   On `not yet`, append the section again and run the block again. Send nothing and settle nothing until it prints `written`.

   On `written`, send what step 4 named. On `crewmate`, send them to that thread with `t3_thread_send`: `threadId` is the id it printed, whole. That is so with a home and with none: the findings go to the `Thread:` line. On `home`, send them to the thread "Telling the home" finds. If that finds none, there is no home: do not send, say so, and write `Sent to: not sent, no home` in the section. jbus reads that line, and passes the findings on to the thread a `Thread:` line names by then, or parks them as a gate. A send that failed is written the same way: change the section's `Sent to:` line to `not sent, <why>`, and it is passed on the same way. One message: the pull request, the head reviewed, then each finding on its own line with its severity, its file and line, what is wrong, and its principle tag. Then the `Proof:` line, one line for each overlap with work in flight, and the count dropped, as a number and nothing more. What the lead noted or dismissed is not in it. End with: "One review pass. Fix what you agree with, say why for the rest, and the pull request's checks decide." In a review whose Start 1 printed `go: a second pass`, the message begins "Second pass, and the last full one. On a guarded pull request a fix for these findings still gets its one scoped pass: run the block of the crew skill's 'A second pass' after the push." in place of "One review pass." If there are no findings and no overlap, send one line saying the review is clean, and the `Proof:` line.
6. Send nothing more, to a home or to anyone. The crewmate has the findings, jbus passes them on, or the pass was clean and asked for no message, and the section is on disk. A home hears of this pull request once, from the crewmate, when it is fixed and green, and only while it is the one that merges. While jbus merges, with a home or with none, nobody is sent that: `jmerge` reads the brief, run by jbus.
7. Say the same in this thread in at most five lines. A reviewer does not review the fixes: the scoped pass of a fix is another reviewer's, launched by the crewmate when its fix changed a file outside `tests/`.
8. Last, settle this thread: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle"}` and no `threadId`. It takes effect when the turn ends, so it is the last call, made only once the block of step 5 printed `written` and the findings are sent, where step 4 named a thread. A reviewer that stopped early, for any reason, does not settle: its thread stays where the user can see why.

### Outside the diff

Write the lead's findings, the **Act on** and **Consider** ones of step 4 with what step 5 added, one to a line, each as `<severity> <file>:<line> <what is wrong> (principle: <name>)`, in place of the middle line of this block. A finding about a file as a whole has no `:<line>`. A finding about what the change as a whole lacks (a `Done when` line it does not meet, a test it does not have) has `-` in place of the file and line: that form is for what the pull request leaves out, never for code it did not touch. A finding about something a changed line breaks is written against that changed line before it goes in: if no changed line can be named for it, it goes in as it came, and the block drops it.

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

- It prints the findings to keep, then the count dropped. Send and record the kept ones only. The dropped ones are named nowhere: not to the crewmate, not in the section, not to the home. The count goes in the section's `Dropped:` line.
- A line counts as changed when the pull request added it, or removed a line that sat just before or just after it. Any line of a file the pull request removed counts, and so does a file-level finding on any file in the diff, a renamed or binary one included.
- If it exits with something other than 0, `gh` gave no diff (no network, or a diff too large for GitHub to send). Nothing was kept and nothing dropped: do not send a review as clean. Run it once more, and if it fails again, say so in the section in place of the findings and send that.
- Do not look at what was dropped to see whether it was true. Whether it was true is not the question.

### Wider than the brief

```sh
WHERE=$(sed -n 's/^Where: //p' "$H/tasks/<slug>.md" | grep -o '`[^`]*`' | tr -d '`' | tr '\n' ' ')
PR=$(gh pr view <url> --json files) || exit 1
printf '%s\n' "$PR" | jq -r '.files[].path' | awk -v where="$WHERE" '
  BEGIN { n = split(where, w, " "); for (i = 1; i <= n; i++) sub(/\/$/, "", w[i]) }
  { for (i = 1; i <= n; i++) if ($(0) == w[i] || index($(0), w[i] "/") == 1) next; if (n) print }'
```

It prints each file the pull request changes that is outside the paths the brief's `Where:` line names, or nothing. Each file printed is a finding, a warning with no line: the pull request is wider than its brief. If the reading already raised the same file, keep one. The block reads only the paths in backticks: a printed file that the `Where:` line's own words allow ("and the other skills only where they state a title") is not a finding. A failed `gh` ends the block with exit code 1, and then the width was not checked: say so in the section, not that the pull request is no wider. A brief whose `Where:` names no path in backticks prints nothing: say in the section that the width could not be checked.

A finding can be wider than the brief in a second way: it is about a changed line, and what it asks for is not in the brief's `Where`. That happens with the fifth question's things to look for (a restructuring, a file to split, a branch to move into a module of its own, a wrapper to remove, logic to move to its canonical layer), when the remedy would change a file outside `Where`. The `SCOPE` text asks the reading to say so in the finding. Such a finding is kept, sent and recorded like any other, with these words at the end of its line: `for Noticed, not this pull request`. It asks the crewmate for no fix: the crewmate writes it in the Result under "Noticed", where the home sees it as a possible plan entry. A finding whose remedy stays inside `Where` is an ordinary finding.

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

It prints one line for each open pull request that changes a file this one changes, and one for each brief with no result yet whose `Where:` covers a file this one changes. Those lines go to the crewmate and into the section's `In flight:` line, as they are. They say that two pieces of work touch the same file, so that whoever merges second knows: they are not a fault in this pull request and carry no severity. Do not open the other pull requests or briefs to look further. A failed `gh` ends the block with exit code 1, and then the section's `In flight:` line says "not checked", not "none".

### Telling the home

A repo runs with a home or with none, and a reviewer needs neither. It sends the home of the brief it reviews a message in one case, and in no other: the block in step 4 of "After the review" said `home`, because the brief has no `Thread:` line to send the findings to, and the block below found a home. A question for the user is asked in this thread, and a reviewer that stops early says why here: a thread that has asked shows as `waiting` in T3 Code, and that is what reaches the user.

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

It prints the id in the `home-id` of the brief's home, read now and never kept: `$H/home-id` for the root home, whose briefs have no `Home:` line, and `$H/<scope>/home-id` for a scoped home, whose briefs name the scope, `Home: <scope>`. A brief names no thread, so no home's start or handoff changes it. One written before this rule has a thread id on the line: an id that is in a scoped home's `home-id`, or on the `Was home:` line of its handoff, is that home, and any other id is the root home. A scope is a directory of `$H` whose `home-id` holds an id or whose handoff has a `Was home:` line, and a line that names no such directory is the root home's: it is `jmerge`'s rule, and `whose` in the home skill, so a brief has one home to all three. Between a handoff and the next home's start the file is gone and the block prints nothing. It is the crew skill's block, the same text.

If it prints a thread id, send that thread the message with `t3_thread_send`. If it prints nothing, there is no home: send nothing, and write `Sent to: not sent, no home` in the section, as step 4 says. jbus passes the findings on.

### A scoped pass

A rebase gives a reviewed pull request another head. `jmerge` compares the head the review saw with the rebased one by `git range-diff`. When no line the patch adds or removes changed, the review carries over and no reviewer is launched. When the content changed, which is a conflict someone resolved by hand, the pull request waits for one review of that change alone: jbus asks the crewmate to launch it, and the message that starts this thread is `/pr-review run <slug> scoped <old range> <new range>`. Each range is `<base>..<head>` in full commits: the reviewed patch, then the rebased one.

A scoped pass is also the review of a fix. A fix pushed for a review's findings that changes a file outside `tests/` gets the same pass, of the fix alone, in place of a whole second review, and it is the last: a fix for its findings merges on the checks. The crewmate launches it in the turn that pushes the fix, when the block of the crew skill's "A second pass" prints `scoped: launch the scoped reviewer`, and where it did not, jbus asks it to. The message is the same one. Its ranges are the patch up to the head the last review saw, then the patch up to the fixed head, so the range-diff shows the fix as the commits on the new side alone. On a guarded pull request every fix gets one, a fix under `tests/` and a fix for a scoped pass's findings included: `jmerge` merges a guarded path only on a safety fact proven at the head it merges. There it is the proof run too: what it leaves is a section whose `Head:` is the fixed head, with the `Proof:` line of step 5 at that head.

It is one pass per rebased or fixed head, and never a full review. It is not the second pass either: a brief that already has a `## Review` section is not refused for it, and in "Start" the check for a `## Review` section does not stop it. The rest of "Start" holds: the brief's `Review:` line, the pull request, the ground.

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

   On `stop`, say what it printed and end: no review, no section, and the thread is not settled. A head that moved is a rebase or a push made after jbus asked, and jbus asks again for the new head. Otherwise it prints the section's `Scope:` and `Head:` lines, whole, and under them the range-diff.
2. Review only what the range-diff shows as changed. Under a pair of commits marked `!`, that is each line with two signs, `-+`, `--`, `++` or `+-`: a line the patch adds or removes on one side alone. A commit on one side alone, marked `<` or `>`, is read whole against the commits of the other side. A pair marked `=` is not read, and neither is a line that only moved: a context line, a hunk header, the metadata, the commit message.
3. Give those lines the review of "The review", its six steps in order, with two things changed in the block of its steps 1 and 2. The first line of the `SCOPE` text reads "Review only what this range-diff shows a rebase or a fix changed in a patch that was reviewed before it: the lines with two signs, and a commit on one side alone. The rest of the patch has had its review." And the code the reading is given is the range-diff: `git range-diff --no-color '<old range>' '<new range>'` in place of `gh pr diff <url>` on the line that writes `$D/code`. The reading, the lead's judgment and the verdict are as they are for a first pass. The safety fact of step 5 is the one fact the rebased or fixed patch is still safe because of, proven at this head: it is never left out, since for a guarded pull request the `Proof:` line at this head is what the pass is for. A finding is about one of those lines, or about something it breaks.
4. Rule on the lines the rebase dropped on purpose. Run this in this worktree, with the block at the top. It prints one line for each `Dropped on rebase:` line the brief has at this head, and for each the diff of that file from the head before the rebase, which the crewmate kept under `refs/jstack/pre-rebase/<slug>/<its first 12 characters>`, to this one. The `Rebase:` line, where the brief has one, names that head; the crew's keep step writes the ref and no such line, so with none the block takes the newest ref of the slug, by commit date, which is the head before the last rebase:

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

   On `no drops`, the section gets no `Drops:` line. Otherwise read each diff against the reason on its line. A drop is upheld when the reason is true of the diff and the lines are right to be gone: the task replaces them, or the default branch's change makes them wrong. It is not upheld when the reason does not hold, the diff shows a line the task or the default branch still needs, or the diff could not be read. The section then has, right under `Scope:`, one line `Drops: upheld <file>, <file>` that names every file upheld, and one line `Drops: not upheld <file>: <why>` for each that is not. A drop that is not upheld is also a finding, of severity `error`, at that file. `jmerge` merges a rebase that dropped lines only when every such file is on the `Drops: upheld` line, and holds one that is not upheld for the user.
5. Report as "After the review" says for a first pass: the head checked again, what is outside the pull request's diff dropped, the findings sent where that pass sends them, and `$T/review.md` appended, filled in. The message begins "Scoped pass, of what the rebase changed.", or after a fix "Scoped pass, of the fix pushed after the review.", in place of "One review pass." The section has one line more, right under `Verdict:`, the `Scope:` line the block of step 1 printed, and under it the `Drops:` lines of step 4. Then settle this thread as a first pass does.

`jmerge` merges the rebased head once a `## Review` names it on its `Head:` line, with its findings handled as any review's. A new rebase after that is compared again, from this head. A fixed head is merged the same way. On a guarded pull request it is merged on the `Proof:` line of that section, and a fix pushed for this pass's findings gets a scoped pass of its own.
