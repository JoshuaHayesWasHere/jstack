# Opening a pull request

Run by: a crewmate, for opening the pull request as the last step of every other crewmate playbook: never picked for a brief.

Source: pstack, `pstack/skills/poteto-mode/playbooks/opening-a-pr.md`

<!-- card: In every task | 1 | Opening the pull request, as the last step of every other crewmate playbook. It is never picked for a brief. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

Verify skill: `.claude/skills/verify-*/`, else a `verify-*` item of `skills.json`'s `projectSkills` (jstack: `features/verify-jstack/project-skill/`).

**One task, one pull request, from the worktree and branch the home gave you.**
Its base is the default branch, and nothing is stacked on another task's branch, but for a link of a stack, whose brief says so (step 6).
Work that turns out to be more than one pull request goes on the Result's `Left:` line: the home splits it.

1. Run the repo's check command (`$H/fresh-check`) until it passes.
   A heavy suite is run as `skills/crew/SKILL.md` "Do the task" says, by whoever it says.
   Where the repo has a verify skill, run it on what you changed.
   A pass is the real thing run and read, not "it compiles" (`principles/principle-prove-it-works.md`).
2. Read your own diff against the default branch once, as its first reader.
   Take out debug leftovers, anything outside the brief's **Where**, and every comment that narrates the change: a comment stays only for a why the code cannot show.
   The smallest diff that meets "Done when" ships (`principles/principle-laziness-protocol.md`).
3. Order the commits before the first push so they tell the story on the branch and in the pull request: the failing test before the fix, the subtraction before the reshape, the scaffold before the feature (`principles/principle-sequence-verifiable-units.md`). Each commit passes the check, but for a failing test that the next commit turns green. Amend when a fix belongs in the commit just made, a new commit when it is separable. After the first push add commits and rewrite nothing: the only rebase is the one `skills/crew/SKILL.md` "A conflict" runs.
4. Title the pull request and each commit as a Conventional Commit, `type(scope): subject` with no full stop: type one of `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, scope the area, subject short, naming the symbol that carries the change.
   The squash lands the title on the default branch, and a commit body never repeats the subject.
   A commit and a pull request carry no AI co-author trailer, and CI refuses one.
5. Write the body as a one-minute briefing for a reviewer who has the diff, under about 40 lines.
   Copy `features/pr-review/templates/pr-body.md`, which has the headings in order, and fill each `<...>`.
   Drop a heading with nothing to say, but never Scope.
   Write each line of the title and the body as one sentence: step 6 lints both.
6. When the brief asks for a pull request, push and open it as a draft, on the base the block under "Do the task" in `skills/crew/SKILL.md` prints for your brief.
   On `no base`, open none.
   Open it with this, with the block at the top of `skills/crew/SKILL.md`: it lints the text, then locks the conversation.

   ```sh
   if ! { printf '%s\n\n' '<the title>'; cat '<the file the body is in>'; } | python3 -I -S "$T/../source/features/writing/scripts/prose_lint.py" -; then
       echo "not opened: the prose lint refused, as it says above"
       exit 1
   fi
   said=$(gh pr create --draft --base '<that branch>' --title '<the title>' --body-file '<the file the body is in>' 2>&1)
   url=$(printf '%s\n' "$said" | grep -o 'https://[^ ]*/pull/[0-9][0-9]*' | head -n 1)
   if [ -z "$url" ]; then
       echo "not opened: $(printf '%s\n' "$said" | head -n 1)"
   elif locked=$(gh pr lock "$url" 2>&1) || printf '%s\n' "$locked" | grep -q 'already locked'; then
       echo "opened and locked: $url"
   else
       echo "opened: $url"
       echo "Lock: not locked, $(printf '%s\n' "$locked" | head -n 1)"
   fi
   ```

   CI checks no draft: `jmerge` readies it once reviewed and fixed.
   A line `Lock: not locked, <why>` goes into the Result as printed: a stranger can comment there.
   Run `gh pr view` before you say anything about its state.
7. With a pull request open, hand over to `skills/crew/SKILL.md` "Stay on the pull request" and do what it says, in its order: link the pull request, write the Result, tell the home, start the one review beside the checks, end the turn.
   With none, steps 5 and 6 are `skip: the brief asks for no pull request` and the task ends as `skills/crew/SKILL.md` "End" says.

Never done here, and who does it:

- **Merge.** The home merges a pull request that is reviewed, fixed and green. Anything else waits for the user's word.
- **Review**: one reviewer, in a new thread, reviews once, launched as `skills/crew/SKILL.md` "The review" says.
  Fix what you agree with, and push back, with a reason, on the rest.
  A fix that changes a file no finding named gets one last pass ("A second pass").
- **Poll.** jbus wakes this thread when its pull request needs it: no loop, no watcher of your own.

**Hand over:** the open pull request and the Result, to the reviewer and the home, as step 7 says. With no pull request, the Result alone, to the home.
