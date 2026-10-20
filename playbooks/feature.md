# Feature

Run by: a crewmate, for new or changed behaviour, built from a named data shape.

Source: pstack, `pstack/skills/poteto-mode/playbooks/feature.md`

<!-- card: Build and change | 1 | New or changed behaviour, built from a named data shape. -->

Copy the numbered steps below into your todo list, word for word, before any todo of your own. A step you do not do stays in the list as `skip: <reason>`.

A path such as `principles/<name>.md` or `skills/crew/SKILL.md` is from the root of the repo this file lives in, also when the work is in another repo. Read a principle in full when a step you are doing names it.

**You own the design and the code.**
The brief's "Done when" list is the target and its **Decisions** are settled: build to them.
If you think a decision is wrong, say so in this thread with your reason and carry on with what does not depend on it.

1. Learn the subsystem from what the brief names: its `Read:` and `Rests on:` lines when a scout wrote it, otherwise the files the task needs and no more. The scout's report is the walkthrough. Do not research again what it found.
2. Name the data shape and its organizing structure before you write logic (`principles/principle-model-the-domain.md`, `principles/principle-foundational-thinking.md`): a state machine over scattered booleans, a table or registry over branching, a typed model over a shape assumed in several files. Write the choice down in one or two lines. A new requirement is built in as if it had been there from the first day (`principles/principle-redesign-from-first-principles.md`).
3. Where the shape has more than one sound form and the brief does not choose, write the two or three candidates down with what each costs and pick one yourself (`principles/principle-exhaust-the-design-space.md`). Record the pick and the reason for the pull request's Tradeoffs. Ask only for a product or preference call no experiment can settle (`principles/principle-never-block-on-the-human.md`), in this thread, once.
4. For a task of size M and up, have the design read before you write tests or code. The size is the t-shirt size the brief names, which the home takes from the task's plan entry. A brief that names no size counts as S: write `skip: size S`. Start one read-only subagent (the Agent tool, `subagent_type` `Explore`) with the brief's path and your notes from steps 2 and 3: the plan, the data shape, the candidate shapes and your pick. Ask it what it would change and why. Take what you agree with. Record in the Result what you took and what you left, each with its reason.
5. Write the tests for "Done when" first, where the repo has tests. A test drives the code through its users' interface and asserts what the contract promises, no less and no more, so it fails when that behavior breaks and keeps passing when only the internals change (`principles/principle-test-behavior-not-implementation.md`).
6. Build it in small units, each ending in a check that passes before the next starts (`principles/principle-sequence-verifiable-units.md`). Remove what the new shape makes dead before adding to it (`principles/principle-subtract-before-you-add.md`). Edits are surgical. Guards go at the system's edges (CLI, config, network, external APIs), and the code inside trusts its types and keeps its logic pure (`principles/principle-boundary-discipline.md`). An improvement to a shared primitive goes to every consumer inside the brief's **Where**, each one verified, with the old form deleted in the same change (`principles/principle-migrate-callers-then-delete-legacy-apis.md`). A consumer outside **Where** goes in the Result under "Noticed". Commit as you go.
7. Verify on the surface the user will meet: the repo's verify skill where it has one, and its check command (`principles/principle-prove-it-works.md`). "Inconclusive", or a pass on another surface, is not a pass: say so.
8. Stop when every "Done when" line holds. What else you saw goes under "Noticed", not into the diff.
9. Run `playbooks/opening-a-pr.md`.

Never done here, and who does it:

- **Splitting the work across workers.**
  One crewmate, one worktree, one pull request.
  A feature that is really several pull requests is the home's to split: say so in the Result and build only what "Done when" asks.
- **A second opinion on the design, past step 4's.**
  There is one review, after the pull request is green, by the reviewer.
  A design the user must settle is a question in this thread.
- **Follow-up pull requests.**
  Nothing is stacked.
  A follow-up is a line under "Noticed" for the home to plan.

**Hand over:** in the pull request and the Result, to the reviewer and the home: what you built, what you chose and why, and the decisions still open.
Design alternatives go in a table.
