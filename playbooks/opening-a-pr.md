# Opening a pull request

Run by: a crewmate, for opening the pull request as the last step of every other crewmate playbook: never picked for a brief.

Source: pstack, `pstack/skills/poteto-mode/playbooks/opening-a-pr.md`

<!-- card: In every task | 1 | Opening the pull request, as the last step of every other crewmate playbook. It is never picked for a brief. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**One task, one pull request, from the worktree and branch the home gave you.**
Its base is the default branch, and nothing is stacked on another task's branch, but for a link of a stack, whose brief says so (step 6).
Work that turns out to be more than one pull request goes in the Result under "Noticed": the home splits it.

1. Run the repo's check command (`notes.md` names it) until it passes. A heavy suite is run as `skills/crew/SKILL.md` "Do the task" says, by whoever it says. Where the repo has a verify skill, run it on what you changed. A pass is the real thing run and read, not "it compiles" (`principles/principle-prove-it-works.md`).
2. Read your own diff against the default branch once, as its first reader. Take out debug leftovers, anything outside the brief's **Where**, and every comment that narrates the change: a comment stays only for a why the code cannot show. The smallest diff that meets "Done when" ships (`principles/principle-laziness-protocol.md`). This is not the review: the reviewer does that, in a new thread.
3. Order the commits before the first push so they tell the story on the branch and in the pull request: the failing test before the fix, the subtraction before the reshape, the scaffold before the feature (`principles/principle-sequence-verifiable-units.md`). Each commit passes the check, but for a failing test that the next commit turns green. Amend when a fix belongs in the commit just made, a new commit when it is separable. After the first push add commits and rewrite nothing: the only rebase is the one `skills/crew/SKILL.md` "A conflict" runs.
4. Title the pull request, and each commit, as a Conventional Commit: `type(scope): subject`, no full stop at the end. Type is one of `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`. Scope is the area. Subject is short and names a real symbol when one carries the change. The home squash-merges, so the title is the line that lands on the default branch. A commit body does not say the subject again.
5. Write the body as a one-minute briefing for a reviewer who has the diff, under about 40 lines. Copy `templates/pr-body.md` and fill each `<...>`: it has the headings, their order and what goes under each. Drop a heading with nothing to say, but never Scope. Write it as `skills/technical-writing/SKILL.md` says (every layer but the mode), then run `skills/unslop/SKILL.md` over it: read each in full when you reach this step.
6. When the brief asks for a pull request, push and open it ready, on the base that the block under "Do the task" in `skills/crew/SKILL.md` prints for your brief: the default branch, or for a link of a stack the branch its `Stack:` line names. On `no base`, open none. Open it with this, which locks its conversation right after:

   ```sh
   said=$(gh pr create --base '<that branch>' --title '<the title>' --body-file '<the file the body is in>' 2>&1)
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

   Never `--draft`.
   A line `Lock: not locked, <why>` goes into the Result as printed: a stranger can comment there.
   Run `gh pr view` before you say anything about its state.
7. With a pull request open, hand over to `skills/crew/SKILL.md` "Stay on the pull request" and do what it says, in its order: link the pull request, write the Result, tell the home, start the one review when the checks have passed, watch, end the turn. With none, steps 5 and 6 are `skip: the brief asks for no pull request` and the task ends as `skills/crew/SKILL.md` "End" says.

Never done here, and who does it:

- **Merge.**
  The home merges a pull request that is reviewed, fixed and green.
  Anything else waits for the user's word.
- **Review.**
  One reviewer, in a new thread, reviews once.
  You launch it as `skills/crew/SKILL.md` "The review" says, fix what you agree with, and say why for the rest: push back when a finding drifts from what the brief asks.
  A fix that changes a file no finding named gets one more pass, the last, as `skills/crew/SKILL.md` "A second pass" says.
- **Poll.**
  `watch_pull_request` wakes this thread on a failed check, passing checks, a comment or a conflict.
  No loop, no watcher of your own.

**Hand over:** the open pull request and the Result, to the reviewer and the home, as step 7 says.
With no pull request, the Result alone, to the home.
