# Expert refresh

Run by: an expert, for a `refresh` ask: a source's revision moved past its pin in `sources.md`, and only the notes that cite a changed file are rechecked.

Source: this repo

<!-- card: An expert runs it | 4 | A source whose revision moved past its pin. Only the notes that cite a changed file are rechecked, and the pin moves last. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/expert/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the pin and the notes under it.**
A pin in `sources.md` says every note citing that source was checked at that revision, so it moves last.

1. Name the move. Take one checkout from `sources.md`, with every row pinned to it and the revision they name. Read both revisions in full from the checkout, `git -C <checkout> rev-parse <pinned> HEAD` (`principles/principle-prove-it-works.md`). Where its two lines are the same, or the rows name no revision, the ask rests on a move that did not happen (`principles/principle-attack-the-premise.md`): step 6 says so, and steps 2 to 5 are `skip: nothing moved`.
2. List what is left to do. Run this with the block at the top of `skills/expert/SKILL.md`, with the checkout's full path and step 1's second line:

   ```sh
   src='<checkout>'
   new='<now>'
   at=$(git -C "$src" rev-parse -q --verify "$new^{commit}") || { echo "no list: $src has no commit $new"; exit 1; }
   behind() {
       grep -owE '[0-9a-f]{7,40}' | sort -u | while read -r rev; do
           if is=$(git -C "$src" rev-parse -q --verify "$rev^{commit}") && [ "$is" != "$at" ]; then echo "$rev"; fi
       done | paste -sd' ' -
   }
   left=0
   for note in "$E"/notes/*.md; do
       name=${note##*/}
       if [ "$name" = INDEX.md ]; then continue; fi
       row=$(grep -F -- "$name" "$E/notes/INDEX.md")
       revs=$(behind < "$note")
       since=$(sed -n 's/^Stale since \([0-9a-f]*\).*/\1/p' "$note" | head -n 1)
       if [ -n "$since" ] && [ "$(git -C "$src" rev-parse -q --verify "$since^{commit}")" = "$at" ]; then
           case $row in
           *stale*) if grep -qF -- "$name" "$E/unknowns.md"; then echo "stale: $name"; continue; fi ;;
           esac
           echo "write: $name as stale in INDEX.md and unknowns.md"
       elif [ -n "$revs" ]; then
           cited=$(for rev in $revs; do git -C "$src" -c core.quotePath=false diff --name-only --no-renames "$rev" "$at"; done |
               sort -u | while IFS= read -r file; do
                   if grep -qF -- "${file##*/}" "$note"; then echo "$file"; fi
               done | paste -sd' ' -)
           if [ -n "$cited" ]; then echo "recheck: $name at $revs cites $cited"; else echo "restamp: $name at $revs"; fi
       elif [ -n "$(printf '%s\n' "$row" | behind)" ]; then
           echo "write: the line of $name in INDEX.md"
       else
           continue
       fi
       left=$((left + 1))
   done
   if [ "$left" = 0 ]; then echo "move the pin: no note is behind $new"; else echo "not yet: $left behind $new"; fi
   ```

   It finds a note by any revision of the checkout it names, however spelled, and a changed file by its base name.
   On `no list`, fill the two in, or the pin stays.
3. Recheck each `recheck:` note. For each claim citing a file on its line, read `git -C <checkout> diff <the note's revision> <now> -- <file>`, then the file at the new revision: it holds, the source says something else, or what it rested on is gone. More than five notes, or a diff too long to hold, goes to `Explore` subagents: keep one verdict a claim (`principles/principle-guard-the-context-window.md`). A `restamp:` note with a claim that names a directory, or no file, is rechecked too.
4. Give each note its ending, in the note. A claim that holds gets the new revision in place of the old. A claim the source changed is rewritten to point at where the source says it now, at the new revision: it points, and copies nothing in (`principles/principle-laziness-protocol.md`). A claim you cannot settle keeps its revision: the note gets a first line `Stale since <now>: <the claim, and why>`, and `unknowns.md` a line that names the note. Then set the note's line in `notes/INDEX.md` to the new revision, or to `stale`.
5. Run the block of step 2 again. On `not yet`, each line it prints is short of step 4. On `move the pin`, and not before, write the new revision in step 1's rows of `sources.md`. A thread that stops anywhere before this starts again and is given the same lines (`principles/principle-make-operations-idempotent.md`).
6. Answer in the four parts of `templates/expert-answer.md`: read it now. The answer is the pin, from which revision to which, and the count of notes re-stamped, rewritten and stale. "Not checked" names what the block does not read: `reports/`, `cases/`, a note that names no revision, and what the remote has past the checkout.

Never done here, and who does it:

- **A fetch, a pull or a checkout in the source.**
  Its owner does: an expert reads the checkout as it stands.
- **A note the block does not print, opened.**
  Nobody does: it names no revision that is behind.
- **A fix to the source.**
  Its home does, by the gate of `skills/expert/SKILL.md` "What an expert never does".

**Hand over:** in the answer, to whoever asked: the pin as it was and is, each note's ending by name, and what was not checked.
