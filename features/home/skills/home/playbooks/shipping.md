# Shipping

Run by: the home, for landing a stack that `autopilot-stack` built, on the user's word, bottom link first and one link at a time.

Source: pstack, `pstack/skills/poteto-mode/playbooks/shipping.md`

<!-- card: Land and resume | 1 | Landing a stack that `autopilot-stack` built, on the operator's word, bottom link first and one link at a time. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the order of landing, never a branch.** `jmerge` merges, at the exact head it checked. Each link's crewmate moves its own branch. You change one thing by hand: the base of the next link's pull request, one link at a time. Each section named below is in `skills/home/SKILL.md`. This is the half after `playbooks/autopilot-stack.md`.

1. Have the word. A stack lands on the user's word and on nothing else: "land <name>", said in this thread. Write it, dated and in their words, under `Decisions:` in the plan entry of every link, so the next home has it too. With no such word, say that the stack waits for it and stop: every later step is `skip: the user has not said to land it`.
2. Read the order from disk, not from memory (`principles/principle-encode-lessons-in-structure.md`): the command of "A stack the user lands" prints each link's `Stack:` line. The bottom link is the one with the lowest place whose plan entry is not done.
3. See what would land: `uv run --project "$T/../source" jmerge --home '<threadId>' --land <name>` from the main checkout, which merges nothing.
   The bottom link prints `ready`, or `wait` and the first thing it is short of.
   Every link above it prints `its base is <branch>, not <default branch>`: that is the order holding, not a fault.
   Ready is what that command says of a reviewed head, never green checks alone and never what a message said (`principles/principle-prove-it-works.md`).
4. Stop at the first link that is not ready. On `wait` for the bottom link, nothing above it lands, however ready it is: tell the user which link, its pull request, the reason as printed, and what has landed so far. The home fixes nothing: its crewmate does, and its next `fixed and green` line brings you back to step 3.
5. The user lands the bottom link, and only it, with `jmerge --land <name>` from the main checkout: end the turn with `stop local <name>:` and that command.
   Then read its `merged` line in `$H/merge.log`.
   `kept: the remote branch` is wanted here: the link above is still based on that branch.
   A `wait` that says the merge failed is a head that moved: go back to step 3 (`principles/principle-make-operations-idempotent.md`).
6. Move the next link, and no other, as "A stack the user lands" says under "A link moves": the base of its pull request, its `Stack:` line, and one line to its crewmate.
   Run no sweep now.
   End the turn: its crewmate rebases its own branch onto the default branch and pushes, and its `fixed and green` line at the new head is what wakes you (`principles/principle-sequence-verifiable-units.md`).
7. On that line, go to step 2. The order is read again after every merge, and the link that moved is judged again at its new head: its review stands, its checks ran again, and its `merged` line says which files the rebase changed.
8. Close when the top link is merged, or at a stop the user leaves standing.
   Run the sweep of "Merging a pull request that is ready": it removes the branches that were kept.
   Account for every link by its line in `$H/merge.log` (`principles/principle-outcome-oriented-execution.md`): merged, with its pull request and commit, or not landed, with the reason.
   When all are merged, take the `Playbook:` line out of the plan's head.
   Show the open gates.

Never done here, and who does it:

- **Landing with no word from the user, or on a `fixed and green` line.** Nobody does: the word is "land <name>", and it covers that stack until its top link is merged or the user takes it back.
- **Landing a ready link above one that is not.** Nobody does: it would merge into a branch, not into the default one. Step 4 stops and says which.
- **A rebase or a push of a link from the home.** The link's own crewmate does, on the home's one line.
- **Moving two links at once, or a link whose parent is not merged.** Nobody does: one base changes after each merge.
- **GitHub's auto-merge or merge-when-ready on a link.** Nobody does: `jmerge` merges at the head it checked.
- **A watch on the pull request being landed.**
  Nobody does: jbus's pass merges it, and nudges this home when it stays quiet with work out.
- **Verifying a link again after its move.** Nobody does: `jmerge` compares the moved head with the reviewed one by `git range-diff`, and asks for a scoped review only where the content changed.

**Hand over:** in this thread, to the user, after each merge and at the close: what landed, with pull request and commit; the link that stopped the landing and why; what the next link needs; and the open gates.
