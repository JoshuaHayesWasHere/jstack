Principles are short rules that the modes apply and cite. Each one is a skill at `skills/principle-<title>/SKILL.md`. A mode names each principle that shaped a decision in its reply.

The index below comes from `docs/rules.md`. To count the principle skills, run `ls -d ~/repos/jstack/skills/principle-* | wc -l`. The count at this commit is 24.

## Core

| Principle | Applies when, and the rule |
| --- | --- |
| [`principle-laziness-protocol`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-laziness-protocol/SKILL.md) | Refactoring, sizing a diff, or tempted to add abstractions, layers, or signal threading. Bias to deletion and the smallest change that solves the problem. |
| [`principle-foundational-thinking`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-foundational-thinking/SKILL.md) | Before writing logic: core types and data structures, scaffold-vs-feature sequencing, what concurrent actors share. |
| [`principle-redesign-from-first-principles`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-redesign-from-first-principles/SKILL.md) | Integrating a new requirement into an existing design. Redesign as if it had been foundational from day one. |
| [`principle-attack-the-premise`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-attack-the-premise/SKILL.md) | Two or more fixes that share one premise have failed the same gate. Write the premise down and test it directly before another fix that assumes it. |
| [`principle-subtract-before-you-add`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-subtract-before-you-add/SKILL.md) | Sequencing an addition, refactor, or rewrite. Remove dead weight first, then build on the simpler base. |
| [`principle-minimize-reader-load`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-minimize-reader-load/SKILL.md) | Reviewing or shaping code that's hard to trace. Count layers and hidden state, collapse one-caller wrappers, shrink mutable scope. |
| [`principle-outcome-oriented-execution`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-outcome-oriented-execution/SKILL.md) | Planned rewrites and migrations with explicit phase boundaries. Converge on the target architecture. Don't preserve throwaway compatibility states. |
| [`principle-experience-first`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-experience-first/SKILL.md) | Product, UX, or feature-scope tradeoffs. Choose user delight over implementation convenience. |
| [`principle-exhaust-the-design-space`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-exhaust-the-design-space/SKILL.md) | A novel interaction or architectural decision with no precedent. Build 2-3 competing prototypes and compare before committing. |
| [`principle-build-the-lever`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-build-the-lever/SKILL.md) | Any non-trivial work. Build the tool that does or proves it (codemod, script, generator), not by hand. The tool is the artifact a reviewer reruns. |

## Architecture

| Principle | Applies when, and the rule |
| --- | --- |
| [`principle-model-the-domain`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-model-the-domain/SKILL.md) | Stateful logic, or code that branches a lot or repeats a shape assumption across files. Encode the domain in a structure (state machine, typed model, table or registry, reducer, boundary, the right collection) instead of scattered conditionals. |
| [`principle-boundary-discipline`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-boundary-discipline/SKILL.md) | Wiring validation, error handling, or framework adapters. Guards at system boundaries, trust internal types, keep business logic pure. |
| [`principle-type-system-discipline`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-type-system-discipline/SKILL.md) | Designing types or a signature in any typed language. Make illegal states unrepresentable, brand primitives, parse external data at boundaries. |
| [`principle-make-operations-idempotent`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-make-operations-idempotent/SKILL.md) | Commands, lifecycle steps, or loops that run amid crashes and retries. Converge to the same end state. |
| [`principle-migrate-callers-then-delete-legacy-apis`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-migrate-callers-then-delete-legacy-apis/SKILL.md) | A new internal API while old callers exist. Migrate and delete in one wave. |
| [`principle-separate-before-serializing-shared-state`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-separate-before-serializing-shared-state/SKILL.md) | Concurrent actors might write the same file, branch, key, or object. Eliminate the sharing first. |

## Verification

| Principle | Applies when, and the rule |
| --- | --- |
| [`principle-prove-it-works`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-prove-it-works/SKILL.md) | After a task, before declaring done. Verify against the real artifact, not a proxy or "it compiles". |
| [`principle-fix-root-causes`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-fix-root-causes/SKILL.md) | Debugging. Trace each symptom back to the first place the system went wrong and fix it there. A guard is a fix only when the state it handles is legitimate. |
| [`principle-sequence-verifiable-units`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-sequence-verifiable-units/SKILL.md) | Multi-step work and how you stack commits and PRs. Small units that each end in a check, verified before the next, delivered in an order that proves itself. |
| [`principle-test-behavior-not-implementation`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-test-behavior-not-implementation/SKILL.md) | Writing, changing, or keeping a test. Assert what the code's users can observe. |
| [`principle-explain-the-number`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-explain-the-number/SKILL.md) | Before you trust, report, or act on a number you measured. Find what limits it, and rule out that it measured something else. |

## Delegation

| Principle | Applies when, and the rule |
| --- | --- |
| [`principle-guard-the-context-window`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-guard-the-context-window/SKILL.md) | Large outputs, long files, repeated reads, fan-out planning. Route bulk to subagents, keep summaries in the main thread. |
| [`principle-never-block-on-the-human`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-never-block-on-the-human/SKILL.md) | Tempted to ask "should I do X?" on reversible work. Proceed, present the result, let the human course-correct. |

## Meta

| Principle | Applies when, and the rule |
| --- | --- |
| [`principle-encode-lessons-in-structure`](https://github.com/JoshuaHayesWasHere/jstack/blob/main/skills/principle-encode-lessons-in-structure/SKILL.md) | You catch yourself writing the same instruction a second time. Encode it as a lint, flag, runtime check, or script instead of more text. |
