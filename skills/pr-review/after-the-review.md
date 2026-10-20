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
5. Read `$T/review.md` now. Append it, filled in, to `$H/tasks/<slug>.md`, with the `By:` line Start printed under its heading, before anything is sent: the brief is where `jmerge` and jbus read the review, and a message is only the notice of it. A reviewer that sent first and was cut off, or whose append failed, left a verdict in one thread and none in the brief, and the pull request waited for a section nobody was going to write. Where step 4 printed `nobody`, run its block once more now that the section is on disk: the crewmate's thread puts a rebase off while a review's section is not written, and one may have come since step 4. If it no longer prints `nobody`, send the thread it names one line saying the review is clean, and the `Proof:` line. The section stays as it is. Then run this with the block at the top, with the head kept at the start in place of the words in angle brackets. It is the only gate on a send, and on settling:

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
       echo "written: the brief has a ## Review of $kept, so what step 4 named may be sent"
   else
       echo "not yet: the brief has no ## Review of $kept: append the section first, and send nothing before it is there"
   fi
   ```

   On `not yet`, append the section again and run the block again. Send nothing and settle nothing until it prints `written`.

   On `written`, send what step 4 named. On `crewmate`, send them to that thread with `t3_thread_send`: `threadId` is the id it printed, whole. That is so with a home and with none: the findings go to the `Thread:` line. On `home`, send them to the thread "Telling the home" finds. If that finds none, there is no home: do not send, say so, and write `Sent to: not sent, no home` in the section. jbus reads that line, and passes the findings on to the thread a `Thread:` line names by then, or parks them as a gate. A send that failed is written the same way: change the section's `Sent to:` line to `not sent, <why>`, and it is passed on the same way. One message: the pull request, the head reviewed, then each finding on its own line with its severity, its file and line, what is wrong, and its principle tag. Then the `Proof:` line, one line for each overlap with work in flight, and the count dropped, as a number and nothing more. What the lead noted or dismissed is not in it. End with: "One review pass. Fix what you agree with, say why for the rest, and the pull request's checks decide." In a review whose Start 1 printed `go: a second pass`, the message begins "Second pass, and the last full one." in place of "One review pass." If there are no findings and no overlap, send one line saying the review is clean, and the `Proof:` line.
6. Send nothing more, to a home or to anyone. The crewmate has the findings, jbus passes them on, or the pass was clean and asked for no message, and the section is on disk. A home hears of this pull request once, from the crewmate, when it is fixed and green, and only while it is the one that merges. While jbus merges, with a home or with none, nobody is sent that: `jmerge` reads the brief, run by jbus.
7. Say the same in this thread in at most five lines. A reviewer does not review the fixes: the scoped pass of a fix is another reviewer's, launched by the crewmate when its fix changed a file outside `tests/`.
8. Last, settle this thread: the `t3-code` server's `t3_thread_organize` (if your harness defers it, load it first) with `{"action": "settle"}` and no `threadId`. It takes effect when the turn ends, so it is the last call, made only once the block of step 5 printed `written` and the findings are sent, where step 4 named a thread. A reviewer that stopped early, for any reason, does not settle: its thread stays where the user can see why.
