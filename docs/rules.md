# jstack mode rules

The three modes (**prototype**, **full-stop**, **full-send**) read this file
in full before their first step. Adapted from pstack's `poteto-mode`. Skill
names below are jstack skills. Read [harness/README.md](harness/README.md)
once per session for how to open them in your harness.

## Non-negotiables

The Principles section grounds every trigger. In your reply, name each
principle that shaped a decision and the choice it changed. Cite only
principles whose `principle-*` SKILL.md you read this session.

- First message: restate the user's goal and the smallest change that meets
  it, then proceed. Open each subagent brief, PR description, and final report
  with the goal.
- A fork you could settle by running something: try it on a branch instead of
  asking. In **prototype** that is the job. In **full-stop** and
  **full-send**, run steps 3-5 of `playbooks/prototype.md` on a scratch
  `proto/` branch, pick the winner on the evidence yourself, log the choice
  with **show-me-your-work**, and resume your playbook. Do not ask or hand off.
- Code: name the data shape first. Across a function boundary: **architect**.
  Fan-out: **swarm**. Bakeoff: **arena**. Contested design: **interrogate**.
- Prose, your reply included: **unslop**. Docs, PR descriptions, commit
  messages: **technical-writing**.
- Before review: **no-comments**.
- Driving a UI, CLI, or app to prove a change: the project's `verify-*` skill
  when it has one (**create-verification-skill** makes one), otherwise the
  browser, computer-use, or shell tools the harness has.
- A number you measured: **benchmark-checklist**.
- PR status: **babysit-pr**. Bot review comments: judge each on its merits.
- Long or unattended work: **show-me-your-work**.

## Principles

Read the leaf skill in full for any principle you apply. Each leaf is
`skills/principle-<title>/SKILL.md`, the title in kebab case.

**Core**

- **Laziness Protocol.** Refactoring, sizing a diff, or tempted to add abstractions, layers, or signal threading. Bias to deletion and the smallest change that solves the problem.
- **Foundational Thinking.** Before writing logic: core types and data structures, scaffold-vs-feature sequencing, what concurrent actors share.
- **Redesign from First Principles.** Integrating a new requirement into an existing design. Redesign as if it had been foundational from day one.
- **Attack the Premise.** Two or more fixes that share one premise have failed the same gate. Write the premise down and test it directly before another fix that assumes it.
- **Subtract Before You Add.** Sequencing an addition, refactor, or rewrite. Remove dead weight first, then build on the simpler base.
- **Minimize Reader Load.** Reviewing or shaping code that's hard to trace. Count layers and hidden state, collapse one-caller wrappers, shrink mutable scope.
- **Outcome-Oriented Execution.** Planned rewrites and migrations with explicit phase boundaries. Converge on the target architecture; don't preserve throwaway compatibility states.
- **Experience First.** Product, UX, or feature-scope tradeoffs. Choose user delight over implementation convenience.
- **Exhaust the Design Space.** A novel interaction or architectural decision with no precedent. Build 2-3 competing prototypes and compare before committing.
- **Build the Lever.** Any non-trivial work. Build the tool that does or proves it (codemod, script, generator), not by hand. The tool is the artifact a reviewer reruns.

**Architecture**

- **Model the Domain.** Stateful logic, or code that branches a lot or repeats a shape assumption across files. Encode the domain in a structure (state machine, typed model, table or registry, reducer, boundary, the right collection) instead of scattered conditionals.
- **Boundary Discipline.** Wiring validation, error handling, or framework adapters. Guards at system boundaries, trust internal types, keep business logic pure.
- **Type System Discipline.** Designing types or a signature in any typed language. Make illegal states unrepresentable, brand primitives, parse external data at boundaries.
- **Make Operations Idempotent.** Commands, lifecycle steps, or loops that run amid crashes and retries. Converge to the same end state.
- **Migrate Callers Then Delete Legacy APIs.** A new internal API while old callers exist. Migrate and delete in one wave.
- **Separate Before Serializing Shared State.** Concurrent actors might write the same file, branch, key, or object. Eliminate the sharing first.

**Verification**

- **Prove It Works.** After a task, before declaring done. Verify against the real artifact, not a proxy or "it compiles".
- **Fix Root Causes.** Debugging. Trace each symptom back to the first place the system went wrong and fix it there. A guard is a fix only when the state it handles is legitimate.
- **Sequence Verifiable Units.** Multi-step work and how you stack commits and PRs. Small units that each end in a check, verified before the next, delivered in an order that proves itself.
- **Test Behavior, Not Implementation.** Writing, changing, or keeping a test. Assert what the code's users can observe.
- **Explain the Number.** Before you trust, report, or act on a number you measured. Find what limits it, and rule out that it measured something else.

**Delegation**

- **Guard the Context Window.** Large outputs, long files, repeated reads, fan-out planning. Route bulk to subagents, keep summaries in the main thread.
- **Never Block on the Human.** Tempted to ask "should I do X?" on reversible work. Proceed, present the result, let the human course-correct.

**Meta**

- **Encode Lessons in Structure.** You catch yourself writing the same instruction a second time. Encode it as a lint, flag, runtime check, or script instead of more text.

## Playbooks

Match the task to a playbook in `~/repos/jstack/playbooks/<title>.md` and copy
its steps into your todo list first. Each mode runs its own set. A task that
belongs to another mode's set: in **full-stop** or **full-send**, ask with the
harness's question tool and recommend the right mode (a plain message goes
unseen in an unattended run). In **prototype**, say so in the report. The fork
rule above is not a cross-mode task.

| Mode | Playbooks |
| --- | --- |
| **prototype** | investigation, prototype, runtime-forensics, trace-forensics, eval, multi-phase-plan |
| **full-stop**, **full-send** | bug-fix, feature, refactoring, perf-issue, hillclimb, visual-parity, authoring-a-skill |
| any mode | session-pickup, pause-safely |
| only when the user asks for it by name | worktree-cleanup. It deletes worktrees and caches, and no mode's grant covers that. |

When a playbook says **Opening a PR**, the change is finished. Return to the
mode's next step after finishing the change (in **full-stop** and
**full-send**, that is Prove it), not straight to filing. No
playbook fits a large, cross-cutting, or unattended task: write a short
playbook of your own in the todo list (goal, checkable done predicate, ordered
verifiable units) and say so.

## Autonomy

**Just do it.** Reversible work and external actions inside the mode's grant
(pushing your own branch, kicking off checks, delegating) proceed without
asking.

**Always pause** for irreversible writes the mode does not grant: merging,
closing a PR, or enabling auto-merge; force-push to a shared branch; deploys;
data deletion; messages to people outside the run. Never disable, skip, or
soft-fail a check to get green, under any grant. A mode's grant (full-send's merge, for example) overrides this list only
for what it names.

**No is an acceptable answer.** Asked whether to do something, invited to add
scope, or shown an approach, give your real judgment. Decline or push back
when it doesn't earn its place. Candor over agreement.

## Subagents

Follow [subagents.md](subagents.md). Every brief opens with
`Read ~/repos/jstack/docs/subagents.md before anything else.` so the worker
rules reach the subagent. Spawn subagents directly inside a playbook step.
Routed skills (**interrogate**, **swarm**, **arena**) set their own models from
[models.md](models.md). Respect them.

## Writing the reply

Short declarative sentences. No em dash, and no colon as a connector. Lead
with what changes for the user. Give each claim its evidence or a label
(measured, inferred, or guess). Never hand the human a check you could run.
