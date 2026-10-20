---
name: architect
description: "Sketch types, signatures, and module structure before code, then stay in the loop while implementation fills in. Use for /architect, 'architect this', 'design this', or non-trivial work where jumping to code would lock in the wrong shape."
tip: sketches types, signatures and module structure before any code | architect this | design this | sketch the types | module structure
disable-model-invocation: true
card: "Settle the shape before code | 2 | Sketches types, signatures and module structure twice, apart, picks one and grafts the other's best, then lets the code fill in against it. | Reach for it when jumping to code would lock in the wrong shape. Its design is what a brief's `Design:` line names. | op: the operator; model: a crewmate"
---

# Architect

Source: pstack, `pstack/skills/architect/SKILL.md`

Sketch types, function signatures, class shapes, and module boundaries with `not implemented` bodies and pseudocode. Make the sketch twice, apart, pick and graft one, then fill in code against it.

No skill named here loads by itself. To run one, read its file and do what it says. Run this first:

```sh
if [ -n "${ZSH_VERSION:-}" ]; then emulate sh; fi
if R=$(realpath ~/.claude/skills/architect/../.. 2> /dev/null) && [ -f "$R/playbooks/arena.md" ]; then
    echo "$R"
else
    echo "no root: ~/.claude/skills/architect is not a link into the repo this skill lives in"
fi
```

It prints the root of the repo this skill lives in. Every path below that starts with `playbooks/`, `principles/` or `skills/` is from that root, and a path that starts with `references/` is beside this file. On `no root` the skill was loaded from somewhere else: the root is two directories above the real place of this file, not of a link to it.

## Start

Open a todo list with one entry per phase before starting. With no todo tool, write the list in this thread.

1. Ground
2. Sketch
3. Agree
4. Implement
5. Scrap

## Phase A: Ground the problem

Build a real mental model of every system the new code touches. Run the `how` skill (`skills/how/SKILL.md`) over the relevant subsystems. Naming a file isn't grounding. Produce the architectural explanation `how` prescribes. If the design redefines ownership or layering, also run the `why` skill (`skills/why/SKILL.md`) on the existing shape so the rationale becomes a constraint, not a guess.

Skip Phase A only when the work is genuinely greenfield with no surrounding system to integrate.

## Phase B: Sketch

The sketch is made as an arena. Read `playbooks/arena.md` and copy its nine numbered steps into the todo list as this phase's entries, word for word. Step 9 stays in the list as `skip: the code of Phase D is what ships, not the sketch`. That playbook is written for a crewmate. In a thread with no brief, its "Result" is your reply to the user and its "Done when" is what the user asked for. What this skill puts into its steps:

- **Step 1, the prompt.** The design-sketch task, the Phase A grounding, and the text below the line `---` in `references/runner-prompt.md` and in `references/rationale-template.md`, pasted in. A runner knows only its prompt, so a path means nothing to it.
- **Step 1, the rubric.** Interface depth (which candidate hides more complexity behind a smaller, simpler public surface), and the flags in [`references/design-red-flags.md`](references/design-red-flags.md) this task is most likely to raise, up to the playbook's six criteria in all. Screen each candidate against the other flags yourself in step 4. The rubric stays with you and the judge, as the playbook says.
- **Step 2, the place.** A sketch is code: each runner gets a worktree.
- **Step 3, the runners.** Two, as the playbook has them, on this session's model. There is no model per role here and no second model family, so the two differ only by what each chose.
- **Step 6, the pick.** Assume the next contributor is an agent that sees only the files it opened, copies the nearest example, and takes the shortest path that compiles. Prefer the design where a change that looks right from one file is right for the whole repo. A rich interface can keep call chains short by concentrating capability instead of scattering it across layers.
- **Step 7, two candidates of one shape.** The playbook calls that agreement and grafts nothing. Two runners on one model with one prompt agree often, so before you take it, write one whole-shape alternative yourself, not a point fix inside the same shape: its usage and its core types, enough to score (`principles/principle-exhaust-the-design-space.md`). Score it against the rubric as you scored the candidates. If it scores higher, step 1 missed a shape: frame it again with that shape in the task and run the arena once more. Otherwise it goes under "Alternatives considered" with its scores.
- **Step 8, the check.** A sketch passes when the repo's check command still passes with it in the worktree, its types check where the repo has a type checker, and the usage and the type sketch agree. A body that says `not implemented` is not a failure.

What comes out is one design package. The pick and each graft fill the rationale's "Synthesis decision" section.

## Phase C: Agree (opt-in)

Default: proceed directly to implementation with the synthesized design. No human checkpoint.

Opt in to a checkpoint when the invoker explicitly asks: "/architect with checkpoint," "stop and show me before implementing," or similar. Then surface the synthesized design and pause for sign-off.

The synthesis can ship as its own commit either way, the scaffold before the feature (`principles/principle-foundational-thinking.md`). Planned and scoped breakage during fill-in is fine (`principles/principle-outcome-oriented-execution.md`). For adversarial pressure on the design before implementing, run the `interrogate` skill (`skills/interrogate/SKILL.md`) on the synthesized sketch.

If the human pushes back on the shape (in a checkpoint or after the fact), treat that as Phase A evidence. Re-ground and re-run Phase B before writing more code.

## Phase D: Implement against the sketch

Replace `not implemented` bodies with code, pseudocode with logic. The synthesized sketch is the contract. Deviations from it are signal to surface, not friction to absorb silently. If a function needs a parameter the sketch didn't anticipate, ask whether the sketch was wrong, the requirement was missed, or the implementation is overreaching.

## Phase E: Scrap when the architecture is wrong

If implementation keeps producing friction the sketch can't absorb, throw the sketch out. Don't bolt fixes onto a wrong design (`principles/principle-redesign-from-first-principles.md`, `principles/principle-fix-root-causes.md`).

The signal is a *pattern*, not single instances. Tells:

- The same shape of workaround appearing repeatedly across unrelated code.
- Multiple unrelated edge cases that all need special-case branches.
- Types that need escape hatches (`any`, casts, optional fields always set in practice) to compile.
- The "we need a lock" reflex when the sketch said the state wasn't shared.
- Callers having to know the abstraction's internal rules to use it.
- Two or more independent Phase D deviations of the same shape across the implementation.

Use judgment. A few edge cases don't condemn an architecture. Some problems are legitimately complex. Complexity in the data is not complexity in the design.

When you scrap:

1. Re-run the `how` skill over what's been built.
2. Redesign as if the new constraints had been day-one assumptions.
3. Subtract before adding (`principles/principle-subtract-before-you-add.md`). The new sketch should be smaller than the old one before it grows.
4. Return to Phase B and run the arena again.

## Outputs

The caller's usage is written first and the type sketch derived from it. One file with new types and signatures for small changes. Module map plus type definitions for larger work. The rationale ships alongside, shaped per `references/rationale-template.md`, including the usage sketch and the synthesis decision.
