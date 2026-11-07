### A scoped pass

A rebase gives a reviewed pull request another head. `jmerge` compares the head the review saw with the rebased one by `git range-diff`. When no line the patch adds or removes changed, the review carries over and no reviewer is launched. When the content changed, which is a conflict someone resolved by hand, the pull request waits for one review of that change alone: jbus asks the crewmate to launch it, and the message that starts this thread is `/pr-review run <slug> scoped <old range> <new range>`. Each range is `<base>..<head>` in full commits: the reviewed patch, then the rebased one.

A scoped pass is also the re-judgement a review's `Meets the brief: no` owes.
One round gives a fix pushed for a review's findings no pass, and a decline no ruling: this pass judges again the `Done when` lines the `no` named, and it is the last, so a fix for its findings merges on the checks.
A fix is never held for this pass as a review of the fix: `jmerge` waits for it as `its fix is not reviewed` only while the Result has no `Proved:` line that holds at the fixed head, and once one holds, only the `no` it re-judges holds the pull request.
Like any review after the first, it routes each finding by the severity it writes, whatever its bucket or tag: an `error` goes to the crewmate, a `warning` goes to the day's warnings row once the pull request merged, and an `info` is dropped.
The crewmate launches it once the fixed head's checks have passed, when the block of the crew skill's "A second pass" prints `scoped: launch the scoped reviewer`, and where it did not, jbus asks it to.
The message is the same one.
Its ranges are the patch up to the head the last review saw, then the patch up to the fixed head, so the range-diff shows the fix as the commits on the new side alone.

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
3. Give those lines the review of "The review", its six steps in order, with three things changed in the block of its steps 1 and 2.
   The first line of the `SCOPE` text reads "Review only what this range-diff shows a rebase or a fix changed in a patch that was reviewed before it: the lines with two signs, and a commit on one side alone.
   The rest of the patch has had its review."
   And the code the reading is given is the range-diff: `git range-diff --no-color '<old range>' '<new range>'` in place of `git diff --no-color '<the base>' '<the head>'` on the line that writes `$D/code`.
   And the `INTENT` has the earlier findings and the crew's answers to them: right above its last line, `printf '\n%s\n' "$SCOPE"`, goes the line `printf '\nThe findings of the reviews before this pass, and the answers of the crew to them, as jbriefs --findings prints them.\n%s\n' "$(uv run --project "$T/../source" jbriefs --findings "$BRIEF")"`.
   The reading, the lead's judgment and the verdict are as they are for a first pass.
   The safety fact of step 5 is the one fact the rebased or fixed patch is still safe because of, proven at this head: it is never left out.
   A finding is about one of those lines, or about something it breaks.
4. Rule on the lines the rebase dropped on purpose.
   Run this in this worktree, with the block at the top and the old range of the message in place of the words in angle brackets.
   It prints one line for each `Dropped on rebase:` line the brief has at this head, and for each the diff of that file from the head before the rebase to this one.
   That head is the one the old range ends on, which `jmerge` named in its `scoped review of git range-diff` line, when it is a commit here; otherwise it is the newest head the crewmate kept under `refs/jstack/pre-rebase/<slug>/`, by commit date, which is the head before the last rebase.
   No line of the brief names it:

   ```sh
   B="$H/tasks/<slug>.md"
   old='<old range>'
   head=$(git rev-parse HEAD)
   short=$(printf %s "$head" | cut -c1-12)
   kept=${old##*..}
   if ! git rev-parse -q --verify "$kept^{commit}" > /dev/null; then
       kept=$(git for-each-ref --sort=-committerdate --count=1 --format='%(refname)' "refs/jstack/pre-rebase/<slug>/")
   fi
   said=$(sed -n "s/^Dropped on rebase: \(.*\), [0-9]* of main's, [0-9]* of its own, at $short: ..*/\1/p" "$B" | sort -u)
   if [ -z "$said" ]; then
       echo "no drops: the brief has no Dropped on rebase line at $head"
   elif [ -z "$kept" ] || ! git rev-parse -q --verify "$kept^{commit}" > /dev/null; then
       echo "not upheld: the head before the rebase is not a commit here, nor kept under refs/jstack/pre-rebase/<slug>, so no drop can be read"
       printf '%s\n' "$said" | sed 's/^/drop: /'
   else
       printf '%s\n' "$said" | while IFS= read -r file; do
           echo "drop: $file"
           command grep -F "Dropped on rebase: $file, " "$B" | command grep -F ", at $short: " | tail -n 1
           git diff "$kept" HEAD -- "$file"
       done
   fi
   ```

   On `no drops`, the section gets no `Drops:` line. Otherwise read each diff against the reason on its line. A drop is upheld when the reason is true of the diff and the lines are right to be gone: the task replaces them, or the default branch's change makes them wrong. It is not upheld when the reason does not hold, the diff shows a line the task or the default branch still needs, or the diff could not be read. The section then has, right under `Scope:`, one line `Drops: upheld <file>, <file>` that names every file upheld, and one line `Drops: not upheld <file>: <why>` for each that is not. A drop that is not upheld is also a finding, of severity `error`, at that file. `jmerge` merges a rebase that dropped lines only when every such file is on the `Drops: upheld` line, and holds one that is not upheld for the user.
5. Rule on no decline: one round counts a decline of a blocking finding on the reason it cites (the crew skill, "The review"), and no pass rules on it, so the section gets no `Declines:` line.
6. Report as "After the review" says for a first pass: the head checked again, what is outside the pull request's diff dropped, and `$T/review.md` appended, filled in, with nothing sent.
   The section has one line more, right under `Verdict:`, the `Scope:` line the block of step 1 printed, and under it the `Drops:` lines of step 4.
   Its `Meets the brief:` line is written as a first pass writes it, with the brief's whole count, since `jmerge` reads the last round's line and no earlier one.
   It re-judges only the lines the round before it named `unmet`, against the fix or the rebase, and carries every line that round met: a scoped pass is never a whole second review, and its `yes` is what clears the earlier `no`.
   A pass over a rebase whose content changed carries the earlier round's line as it was, but for a line the changed content breaks.
   Then settle this thread as a first pass does.

`jmerge` merges the rebased head once a `## Review` names it on its `Head:` line, with its findings handled as any review's. A new rebase after that is compared again, from this head. A fixed head is merged the same way.
