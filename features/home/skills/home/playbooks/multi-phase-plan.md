# Multi-phase plan

Run by: the home, for work that is more than one pull request, planned as a batch of entries the user approves once.

Source: pstack, `pstack/skills/poteto-mode/playbooks/multi-phase-plan.md`

<!-- card: Plan a batch | 1 | Work that is more than one pull request, planned as a batch of entries the operator approves once. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

Verify skill: `.claude/skills/verify-*/`, else a `verify-*` item of `skills.json`'s `projectSkills` (jstack: `features/verify-jstack/project-skill/`).

**You own the plan, not the code.** The plan is the deliverable: entries in `$M/plan.md` that a crewmate each works line by line and the user can audit from the evidence. Write nothing in the repo.

1. Size it first (`principles/principle-subtract-before-you-add.md`). Work that is one pull request with an obvious approach is one entry: write it by "Planning" in `skills/home/SKILL.md`, and steps 2 to 7 are `skip: one entry`.
2. List every open question, and settle each before an entry is written (`principles/principle-never-block-on-the-human.md`). One that a run can settle is a brief with `Playbook: prototype`, launched and waited for: its Result goes under the entry's `Decisions:`, with what it proved and what stays unproven. One that reading can settle is a scout's. Only a product or preference call that no run settles goes to the user, as a round of the grilling skill with options, or as a gate with a default once work is out.
3. Have the ground explored by a scout, not by you (`principles/principle-guard-the-context-window.md`): one durable request whose "Deliver" list asks, for each piece of the work, for the files it would hold, the check that proves it, and what it rests on.
   Read its Report, and nothing it read.
   Entries that already have a scout's brief each need none: `skip: the briefs are written`, and `jmerge --claims` prints their files.
4. Write one entry per pull request, in the shape of `templates/plan-entry.md` (`principles/principle-sequence-verifiable-units.md`). Each is one change with its own evidence. Each `Done when` line names what shows it: a command and what it prints, a test by name, a file on disk. Tests alone are not the proof of a change a person can see (`principles/principle-prove-it-works.md`): such an entry has one line that is seen on the real thing. Add to each entry, in brackets on its `Status:` line, its size as a t-shirt size, the files it holds, and what it waits on.
5. Order the batch by the files each entry holds (`principles/principle-separate-before-serializing-shared-state.md`). Two entries that hold one file are a chain: say which goes first. Entries that share none run beside each other. An entry that needs another's change waits for that merge and starts from the default branch: none is stacked. Write the order as one paragraph in the plan's head, above the first entry, and see that every entry is in it once.
6. Name how the batch runs, on a `Playbook:` line in the plan's head. `autopilot-full` for a queue that runs to its end with no word from the user. `orchestrate` for a standing program with a count to reach and a pilot first. `autopilot-stack` (`playbooks/autopilot-stack.md`) for entries that each need the one before and that the user lands, by `playbooks/shipping.md`: the one batch that is stacked. No line for a few entries the home hands out by its skill alone.
7. Show the batch once and take one go for all of it: the plan's path, the entries in order with size and what each waits on, what the prototypes proved, and the open gates. The plan the user approved is the go: every entry in it is approved, a scout's brief for one is launched without showing it, and nothing waits for a second word. Then open the playbook step 6 named, with the block of "A playbook of the home's own".

Never done here, and who does it:

- **Implementing any of it.** A crewmate does, one per entry, from its brief.
- **An entry with no `Done when` a command or a person can run.** Nobody launches one: it is not scoped yet, and goes back to step 2.
- **Ten live lanes and a performance gate on every pull request.** Nobody does until a repo has a verify skill: the review and the repo's checks are the proof.
- **A stack of pull requests.** Nobody does here: step 5 orders by merge.
- **A second plan file with appendices.** Nobody writes one: the alternatives and the evidence are in the scouts' Reports and the prototypes' Results, which the entries name.
- **Asking for a go on each entry.** Nobody does: step 7 is the one go.

**Hand over:** in this thread, to the user: the plan's path, the entries with their order and what each waits on, what the prototypes proved and what stays unproven, the playbook the batch runs by, and the open gates.
