# Code Quality Review

Each reviewer applies this code-quality lens in addition to the rubric.
Five more dimensions belong to it and are in your prompt under "The review skill's two questions", as its question 5.
Read that question first where it is there: the structural simplification it asks for is the heart of this lens.

It is a strict standard focused on implementation quality, maintainability, abstraction quality, and codebase health.

## Core Prompt

Start from this baseline:

> Perform a deep code quality audit of the current branch's changes.
> Rethink how to structure / implement the changes to meaningfully improve code quality without impacting behavior.
> Work to improve abstractions, modularity, reduce Spaghetti code, improve succinctness and legibility.
> Be ambitious, if there is a clear path to improving the implementation that involves restructuring some of the codebase, go for it.
> Be extremely thorough and rigorous. Measure twice, cut once.

## Dimensions

Each dimension is stated once.
Apply the ones that are relevant.

1. **Bias toward cleaning the design, not just accepting working code.**
   If behavior can stay the same while the structure becomes meaningfully cleaner, push for the cleaner version.
   Prefer simplifications that remove moving pieces over refactors that spread the same complexity around.

2. **Prefer direct, boring, maintainable code over hacky or magical code.**
   Treat brittle, ad-hoc, or "magic" behavior as a problem.
   Be skeptical of generic mechanisms that hide simple data-shape assumptions.

3. **Push on type and boundary cleanliness when it affects maintainability.**
   Question unnecessary optionality, `unknown`, `any`, or cast-heavy code when a clearer type boundary could exist.
   Prefer explicit typed models over loosely-shaped ad-hoc objects.
   If a branch leans on a silent fallback to paper over an unclear invariant, ask whether the boundary should be made explicit.

4. **Treat unnecessary sequential orchestration and non-atomic updates as design smells when the cleaner structure is obvious.**
   If independent work is serialized for no reason, ask whether it should run in parallel.
   If related updates can leave state half-applied, push for a more atomic structure.
   Do not over-index on micro-optimizations, but do flag avoidable orchestration complexity that makes the code more brittle.

## Output Expectations

Prioritize structural code-quality regressions and missed simplifications first, then spaghetti and branching complexity, then boundary, type, and file-size concerns, then smaller modularity and legibility issues.

## Approval Bar

Do not approve merely because behavior seems correct.
A cast-heavy contract is a presumptive blocker unless the author can justify it, and so is each thing question 5 names.
For each one you find, leave explicit, actionable feedback and push for a cleaner decomposition.

## Review Tone

Be direct, serious, and demanding about quality.
Do not be rude, but do not soften major maintainability issues into mild suggestions.
If the code is making the codebase messier, say so.
If the implementation missed an obvious dramatic simplification, say that too.
Do not be satisfied with "maybe rename this" when the real issue is structural.
