# Autopilot, stack

Run by: the home, for a queue of approved plan entries that each need the one before, built as one linear stack of pull requests that the user reviews and lands.

Source: pstack, `pstack/skills/poteto-mode/playbooks/autopilot-stack.md`

<!-- card: Work a queue unattended | 2 | A queue of approved entries that each need the one before, built as one linear stack of pull requests that the operator reviews and lands. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/home/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the stack's order, never a pull request and never the landing.** One crewmate owns each link, its reviewer the verdict, and the user lands the stack. You alone write the order: the `Stack:` line in each link's brief, and the base of its pull request. This is the one exception to "no stacking", in the user's words: "take it as written, and allow a stack for this one playbook". Each section named below is in `skills/home/SKILL.md`.

1. Choose it, or leave it (`principles/subtract-before-you-add.md`). A stack is for entries where each needs the change of the one before, and the user wants to review all of it before any lands. Entries that hold no file in common and may merge by themselves are `playbooks/autopilot-full.md`: say so, take that one, and the steps below are `skip: not a stack`. Say the stack in at most six lines, bottom first, and go on: the approved plan is the go (`principles/never-block-on-the-human.md`).
2. Write the order down before any launch. Put `Playbook: autopilot-stack` in the head of `$M/plan.md`, above the first entry: the exception holds for a plan with that line, and for no other. Name the stack with one word. Write the `Stack:` line into every link's brief, as "A stack the user lands" has it. Run the command there that reads the order back, and see every link once, in its place (`principles/encode-lessons-in-structure.md`).
3. Run the first block of "A queue and its hourly audit". On `schedule`, schedule the audit and keep its id. On `no queue`, that section does not count this playbook as a queue: say so once, and the stack moves on messages alone.
4. Launch link 1 as any crewmate, by "Handing a task to a crewmate": its base is the default branch. Its brief has the `Stack:` line, so `jmerge` prints `wait` for it whatever its review says: no link merges on a `fixed and green` line.
5. Add the next link only on a verified one (`principles/sequence-verifiable-units.md`). When a link's `fixed and green` line arrives, read its brief: a `## Review`, and a clean verdict or a `Fixed:` line. Then launch the link above it with the call of "A stack the user lands", from its parent's branch, after `room` says `go`. One link at a time, and never one on a parent that is not fixed and green.
6. Work each message as "When a thread sends a message" says, and each tick as "One tick" says. You read no diff and judge no change (`principles/prove-it-works.md`). A link that stopped is picked up with `playbooks/session-pickup.md`, and nothing above it launches meanwhile. A link's crewmate never rebases for a conflict by itself: on its line that it has one, send it the line of "A link with a conflict" there, then the links above it, bottom up.
7. On the user's stop, stop at once. Launch nothing, send every thread out one line to write and push nothing more, delete the audit if one is kept, and tell the user which threads were told.
8. Deliver the stack when its top link is fixed and green. Run the merge step of "Merging a pull request that is ready" with `flags='--check --land <name>'`: the bottom link prints `ready`, and each one above it waits on its base. Tell the user the name, each link from the bottom up with its pull request and its verdict, what is parked or left out and why, and that it lands on their word, "land <name>". Then stop: the landing is `playbooks/shipping.md`, and it starts with that word.

Never done here, and who does it:

- **Merging or landing a link.** The user lands the stack, by their word to this thread or with their own clicks. `jmerge` holds every link until then.
- **A rebase, a fix or a push from the home.** The link's own crewmate does, on its own wakes.
- **A crewmate choosing or changing its base.** Nobody does: the base is what its brief's `Stack:` line gives, and only the home writes that line.
- **A new order once a link is out.** The user decides: park it as a gate, with the default that the order stays.
- **A stack under any other playbook.** Nobody does: there a dependent entry waits for the merge.
- **GitHub's auto-merge, or Graphite.** Nobody does: `jmerge` merges at an exact head.

**Hand over:** in this thread, to the user, when the top link is fixed and green and when asked: the stack's name, the bottom and the top pull request, one line a link with its verdict, what is parked or left out and why, and the open gates.
