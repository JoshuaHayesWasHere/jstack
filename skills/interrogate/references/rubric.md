# Review Rubric

Review through whichever lenses are relevant.
Not every lens applies to every change.

Six more checks belong to this rubric and are in your prompt under "The review skill's two questions", as its question 4: apply them with the same weight.

## Correctness

Does the code actually do what the intent says it should?

- Edge cases: empty inputs, nil/undefined, boundary values, concurrent access
- Error handling: are errors caught, propagated, or silently swallowed?
- Off-by-one, type coercion, integer overflow, string encoding
- State management: race conditions, stale closures, dangling references
- Do both the happy path and the sad path work?

When you find a potential bug, trace the execution path.
Don't just flag "this could be nil".
Show the call chain that makes it nil.

## Root Causes vs. Symptoms

Is the code fixing the actual problem or papering over a symptom?

Answering this often requires looking beyond the changed files.
Read the surrounding code (callers, callees, type definitions, sibling modules) and understand the architecture the change lives in.
Use the tools available to you (Read, Grep, Glob, and read-only `git` in Bash) to follow the call chain, read the types, and understand why the code exists before judging whether the change addresses the right layer.

- Guard clauses that mask a deeper invariant violation
- Retry logic that hides a broken contract
- Type casts that silence a modeling error
- A workaround: why is it needed?
  What would a proper fix look like?
- A fix in module A that should really be a fix in module B's contract

## Structural Integrity

Does the code fit well into the system it's part of?

- Boundary discipline: is validation at system boundaries, or scattered through business logic?
  Validate data once where it enters the system, then trust it internally.
- Abstraction level: is the code mixing high-level orchestration with low-level detail?
- Coupling: does this change introduce dependencies that will make future changes harder?
- Data model fit: do the data structures match the actual access patterns?
- Bolted-on vs. integrated: if the new requirement had been known from the start, would the code look like this, or does the change feel patched onto the existing design?

Don't penalize simple code for lacking abstraction.
Premature abstraction is worse than duplication.

## Verification

Can you tell that this code works from reading it?

- Are there tests?
  Do they test behavior or implementation details?
- Are there assertions/invariants that would catch regressions?
- If this touches an integration boundary: is the full path tested?

## Complexity Budget

Is the complexity justified by what the code accomplishes?

- Code that could be simpler without losing correctness or clarity
- Abstractions that serve only one call site
- Configuration or parameterization for cases that don't exist yet
- Dead code, unused imports, vestigial parameters
- Over-engineering: "just in case" code paths with no current callers
- Does the user experience justify the complexity?
  Every feature, control, and option should earn its place.
  Half-finished features are worse than missing ones.

Simpler is better unless simpler is wrong.

## Security

For each security finding, trace the input path through the code and show it.

- User input flowing to dangerous sinks (SQL, shell, eval, innerHTML) without sanitization
- Authentication/authorization gaps in new endpoints
- Secrets in code, logs, or error messages
- TOCTOU (time-of-check-time-of-use) in security-critical paths
