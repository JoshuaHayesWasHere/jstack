### A scoped pass

A rebase gives a reviewed pull request another head. `jmerge` compares the head the review saw with the rebased one by `git range-diff`. When no line the patch adds or removes changed, the review carries over and no reviewer is launched. When the content changed, which is a conflict someone resolved by hand, the pull request waits for one review of that change alone: jbus asks the crewmate to launch it, and the message that starts this thread is `/pr-review run <slug> scoped <old range> <new range>`. Each range is `<base>..<head>` in full commits: the reviewed patch, then the rebased one.

A scoped pass is also the review of a fix.
A fix pushed for a review's findings that changes a file outside `tests/` gets the same pass, of the fix alone, in place of a whole second review, and it is the last: a fix for its findings merges on the checks.
Like any review after the first, it routes each finding by the severity it writes, whatever its bucket or tag: only an `error` goes to the crewmate, a `warning` goes to the cleanup row that step 6 files, and an `info` is dropped.
The crewmate launches it in the turn that pushes the fix, when the block of the crew skill's "A second pass" prints `scoped: launch the scoped reviewer`, and where it did not, jbus asks it to.
The message is the same one.
Its ranges are the patch up to the head the last review saw, then the patch up to the fixed head, so the range-diff shows the fix as the commits on the new side alone.
A blocking decline is owed the same pass, also when nothing was pushed: a declined finding changes no line, so the range-diff alone would never show it again.
Then both ranges end at the head the review saw, the range-diff shows no change, and the pass is its ruling on the declines (step 5).

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
   And the code the reading is given is the range-diff: `git range-diff --no-color '<old range>' '<new range>'` in place of `gh pr diff <url>` on the line that writes `$D/code`.
   And the `INTENT` has the earlier findings and the crew's answers to them: right above its last line, `printf '\n%s\n' "$SCOPE"`, goes the line `printf '\nThe findings of the reviews before this pass, and the answers of the crew to them, as jbriefs --findings prints them. This pass rules on each blocking decline.\n%s\n' "$(uv run --project "$T/../source" jbriefs --findings "$BRIEF")"`.
   The reading, the lead's judgment and the verdict are as they are for a first pass.
   The safety fact of step 5 is the one fact the rebased or fixed patch is still safe because of, proven at this head: it is never left out.
   A finding is about one of those lines, or about something it breaks.
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
5. Rule on each blocking decline.
   Run this in this worktree, with the block at the top:

   ```sh
   B="$H/tasks/<slug>.md"
   listed=$(uv run --project "$T/../source" jbriefs --findings "$B")
   declined=$(printf '%s\n' "$listed" | awk '/^F[0-9]+ / {id = $(1)} /^  ruling: / {printf "%s%s", (n++ ? " " : ""), id}')
   if [ -z "$declined" ]; then
       echo "no declines: no blocking finding is declined by id"
   else
       echo "rule on: $declined"
       printf '%s\n' "$listed"
   fi
   ```

   On `no declines`, the section gets no `Declines:` line.
   Otherwise it names each blocking finding the crew declined by id, the ones an earlier scoped pass ruled on too, and under it the list with each finding, its answer, the reason the decline gives and the ruling it has so far.
   Rule on every one it names, an earlier ruling included: a scoped section you write at the head of an earlier one by the same `By:` takes its place, and its rulings with it, so a decline it leaves out has no ruling.
   A finding of the bucket Consider, Noted or Dismissed is not ruled on, and neither is one answered `fixed`.
   Check each reason at this head: read the `path:line` it cites, run the command it gives, read the gate it names.
   A decline is upheld when its reason is true at this head and answers the finding: the case cannot happen, the brief decides it, or the user's answer to the gate does.
   It is not upheld when the reason does not hold, or holds and leaves the finding standing; the disproof is what shows it, a `path:line` or a command and what it printed.
   The section then has, right under `Scope:` and its `Drops:` lines, one line `Declines: upheld F2, F4` that names every finding upheld, and one line `Declines: not upheld F3: <the disproof>` for each that is not.
   A decline not upheld is not written again as a finding: the ruling is its record, and it stands until the crew answers the finding `fixed`.
   `jmerge` waits on a ruling that is missing, and on a decline not upheld: that one is the crew's to fix, then its home's, and it is the user's only for a finding on one of review-triage's categories, `(risk: <area>)`, which `jmerge` holds for the user.
6. Report as "After the review" says for a first pass: the head checked again, what is outside the pull request's diff dropped, and `$T/review.md` appended, filled in, with nothing sent.
   The section has one line more, right under `Verdict:`, the `Scope:` line the block of step 1 printed, and under it the `Drops:` lines of step 4 and the `Declines:` lines of step 5.
   Then settle this thread as a first pass does.

`jmerge` merges the rebased head once a `## Review` names it on its `Head:` line, with its findings handled as any review's. A new rebase after that is compared again, from this head. A fixed head is merged the same way.
