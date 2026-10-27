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

   It prints the section's `Head:` and `Patch-id:` lines whole. `yes` means the pull request's head and this checkout's are both still the head kept at the start, with nothing uncommitted. On `no`, say that first in the section. The crewmate's thread may push or rebase in this worktree while the review is out, and a `no` is how that shows. The review is still of the head the `Head:` line names, and its verdict stands for that head: whatever moved after it is the crewmate's to account for, and its second-pass check compares from that head. The patch-id names the patch that was reviewed, whatever commit carries it: the same command over a rebased head gives the same id when the rebase left the patch as it was, which is how the crew skill's "A conflict" tells. It always prints a `Head:` line, since the head reviewed is known whatever GitHub answers: the crew skill and `jmerge` read it. On exit code 1 the lines say what could not be asked or worked out: write them in the section as printed.
2. Drop what is outside the diff: "Outside the diff". From here on, the findings are the ones that block kept.
3. Add what the reviewer finds itself: "Wider than the brief", "The merge gate" and "In flight".
4. Send nothing, on any verdict, to the crewmate, to the home or to anyone.
   The section is this pass's one output: jbus reads it on its next pass, asks `jmerge`'s judge what the pull request is short of, and tells the crewmate only when it owes a line for it, findings to answer or a `Fixed:` line.
   A clean pass, a second review filed as a cleanup row and a pass whose other reviewers have not written yet owe the crewmate no line, so nobody is woken for them.
   With no `Thread:` line in the brief, jbus tells the home in its place, and with no home it parks the findings as a gate.
5. Read `$T/review.md` now.
   Append it, filled in, to `$H/tasks/<slug>.md`, with the `By:` line Start printed under its heading, and `Sent to: not sent, jbus tells the crew when it owes a line` as its last line.
   The brief is where `jmerge` and jbus read the review, so a pass whose append failed has written no review at all.
   Then run this with the block at the top, with the head kept at the start in place of the words in angle brackets.
   It is the only gate on settling:

   ```sh
   B="$H/tasks/<slug>.md"
   kept='<the head kept at the start>'
   by='<the By: line Start printed>'
   case $by in "<"*) by= ;; esac
   if awk -v kept="$kept" -v by="$by" '
       /^## / {if (head && (by == "" || mine)) found = 1; review = ($(0) == "## Review"); head = mine = 0}
       review && $(1) == "Head:" && $(2) == kept {head = 1}
       review && $(0) == by {mine = 1}
       END {if (head && (by == "" || mine)) found = 1; exit !found}' "$B"; then
       echo "written: the brief has a ## Review of $kept"
   else
       echo "not yet: the brief has no ## Review of $kept: append the section first"
   fi
   ```

   On `not yet`, append the section again and run the block again.
   Settle nothing until it prints `written`.

   On `written`, first run this with the block at the top.
   A brief whose first `Review:` line says `after` has merged, or will, on its check alone, so its findings go to a cleanup row and not to the crewmate.
   So do the findings of the second review of a brief that says `twice`:

   ```sh
   B="$H/tasks/<slug>.md"
   if awk '/^Review:/ {after = ($(2) == "after" || $(2) == "twice"); exit} END {exit !after}' "$B"; then
       if text=$(uv run --project "$T/../source" jbus cleanup "$B"); then
           if ! said=$(printf '%s\n' "$text" | uv run --project "$T/../source" jbus queue add "cleanup-<slug>" --priority 50 --depends "<slug>" 2>&1); then
               case $said in
               "refused: cleanup-<slug> cannot depend on <slug>: <slug> was removed"*)
                   printf '%s\n' "$text" | uv run --project "$T/../source" jbus queue add "cleanup-<slug>" --priority 50 ;;
               *) echo "$said" && false ;;
               esac
           else
               echo "$said"
           fi
       else
           echo "$text"
       fi
   else
       echo "not after: the brief says Review: review or none, so its crewmate answers the findings"
   fi
   ```

   On `not after` and on `first review`, the crewmate answers the findings, and jbus tells it of them.
   On any other line, the findings go to the cleanup row and not to the crewmate, and the crewmate is told nothing: `jmerge` merges an `after` brief on its check and a `twice` brief once its second review is written.
   It queues one row, `cleanup-<slug>`, that lists each finding with its path:line, the pull request and its merge commit.
   The row is a follow-up of `<slug>`, so jbus approves it by the follow-up rule when it is queued, or on the next pass, where `<slug>`'s go holds; otherwise it waits for the user's go.
   The row depends on `<slug>`, so it launches only once that pull request has merged, and its crew starts from a main that has it.
   A `<slug>` row already removed from the queue has nothing left to wait on, so the block queues the row with no such dependency.
   On any other `no cleanup row`, of an `after` brief, or of a `twice` brief whose row is already in the queue, the review was clean or the row is already queued, and nothing more is done.

6. Send nothing more, to a home or to anyone: jbus tells the crewmate of the section, and `jmerge`, run by jbus, reads it from the brief.
7. Say the same in this thread in at most five lines. A reviewer does not review the fixes: the scoped pass of a fix is another reviewer's, launched by the crewmate when its fix changed a file outside `tests/`.
8. Last, settle this thread: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle"}` and no `threadId`. It takes effect when the turn ends, so it is the last call, made only once the block of step 5 printed `written`. A reviewer that stopped early, for any reason, does not settle: its thread stays where the user can see why.
