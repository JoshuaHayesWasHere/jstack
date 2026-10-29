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

   It prints the section's `Head:` and `Patch-id:` lines whole.
   `yes` means the pull request's head and this checkout's are both still the head kept at the start, with nothing uncommitted.
   On `no`, say that first in the section.
   The review is still of the head the `Head:` line names, and its verdict stands for that head: whatever moved after it is the crewmate's to account for, and its second-pass check compares from that head.
   The patch-id names the patch that was reviewed, whatever commit carries it: the same command over a rebased head gives the same id when the rebase left the patch as it was, which is how the crew skill's "A conflict" tells.
   On exit code 1 the lines say what could not be asked or worked out: write them in the section as printed.
2. Drop what is outside the diff: "Outside the diff". From here on, the findings are the ones that block kept.
3. Add what the reviewer finds itself: "Wider than the brief" and "In flight".
4. Send nothing, on any verdict, to the crewmate, to the home or to anyone.
   The section is this pass's one output: jbus reads it on its next pass, asks `jmerge`'s judge what the pull request is short of, and tells the crewmate only when it owes a line for it, findings to answer or a `Fixed:` line.
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

   On `written`, every finding this pass sends goes to the crewmate while the pull request is open, a later review's included, and jbus tells it of them: nothing else is filed.

6. Say the same in this thread in at most five lines.
7. Last, settle this thread: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle"}` and no `threadId`.
   It takes effect when the turn ends, so it is the last call, made only once the block of step 5 printed `written`.
   A reviewer that stopped early, for any reason, does not settle: its thread stays where the user can see why.
