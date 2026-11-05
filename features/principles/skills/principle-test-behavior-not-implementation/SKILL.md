---
name: principle-test-behavior-not-implementation
description: "Apply when you write, change, or keep a test. Assert what the code's users can observe, so that the test fails when that behavior breaks and keeps passing when only the internals change."
---

# Test Behavior, Not Implementation

Apply when you write, change, or keep a test. Assert what the code's users can observe, so that the test fails when that behavior breaks and keeps passing when only the internals change.

A test is a claim about what the code does for its users: a caller, an end user, or another service. Behavior is what those users can observe through the interface they use. That includes return values, errors, state they can read back, and effects on systems outside the code, such as a request sent, a row written, or a message emitted. Implementation is what they cannot observe: private helpers, internal call order, intermediate data, and which internal collaborator did the work.

Judge each test against two imagined edits:

- **Break the behavior.** Make the code return a wrong value, skip an effect, or do the effect twice. If the test still passes, it proves nothing. The usual causes are an assertion looser than the contract, an expected value computed by the code under test, a restated constant or prompt string that never runs the code that reads it, and an assertion on data that the test built itself.
- **Change the internals.** Keep every observable result the same and restructure the code underneath. If the test now fails, it is pinned to the implementation. It will need a rewrite on every refactor and still catches no bug.

Keep a test that catches the first edit and survives the second. Rewrite or delete the rest. To write a test that does both, drive the code through its users' interface with a concrete input. Derive the expected value from the requirement, not from a run of the code. Assert what the contract promises, no less and no more.

The contract decides, not the shape of the assertion. When "an empty cart never charges" is the promise, an assertion that the payment client got no call is behavior. Pair it with a case where the charge happens, so that the test shows it can see a call. The payload that a mocked external service receives is behavior, because that service observes it. A call to an internal helper is implementation, because no user can see it. An empty list is the exact answer when no record matches, and a hollow check when the test only needs some result. An exact error message pins wording that no caller reads. The error type that callers branch on is the contract.

A test can pin an invariant instead of a call, such as a key that must exist in two tables or a compile-time type check. The invariant is the behavior.

## In an agent-first repo, tests are not the primary guard

In an agent-first repo, agents write most of the code and most of its tests.
A test that an agent writes beside its own code tends to restate that code, so it passes for the same reason the code was written and catches little.
There, four guards come before any unit test, in this order:

1. CI: the check that every pull request must pass before it merges.
2. Lint: a rule that fails the build on the wrong shape, so that nobody has to remember the rule.
3. Deterministic scripts: a script that drives the real command, request, or page end to end and prints the same verdict on every run, such as the repo's verify skill.
4. Validation pipelines: the evals and checks that run the product on real inputs and judge what comes out.

A unit test is still worth writing, or keeping, when it is a keeper: a test pinned to a real bug or a real invariant that must never regress.
Name the bug or the invariant it pins.
A test that catches nothing a CI job, a lint rule, a script, or a validation pipeline would not catch is noise.
So is a test written to match the code rather than the requirement.
Put what such a test checks in the first guard that can own it.
A keeper still has to pass the two edits above.

<!-- card: Prove it | 2 | A test fails when the behavior its users can observe breaks, and keeps passing when only the internals change. | `bug-fix`; `feature`; `authoring-a-skill` -->
