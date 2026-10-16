### Intent
> Add a `Proves it:` line to `templates/brief.md`, right after `Done when:`. The brief parser and jbus's pre-launch checks accept it only when it names something outside the agent: a test, a command, a metric, a dataset, an external judge, or the user. They refuse an empty line, the template text, and any proof by the crew, the crewmate, the reviewer, the agent, "self", "the model", or a review alone, each with a one-line reason. Briefs without the line must be grandfathered or refused, whichever doesn't strand an approved row. The change needs tests for each kind, docs and the home skill updated, and `make check` passing.

### Reviewers
- Reviewer A: 7 findings
- Reviewer B: 6 findings
- Both independently put the same core defect first: the `_OUTSIDE` patterns are too loose and are checked first. They also agreed on the duplicated head-line loop, the test-only `Brief.proof`, the `<` template detection, and the Result-only Done-when items. Only A raised the grandfathering hole and the double gate. Both reviewers answered the review skill's questions.

### Act On

**1. Self-referential lines pass because loose `_OUTSIDE` keywords win before `_SELF` is read, and no test catches it.** (A1, B1, B2)
`proof()` accepts on the first `_OUTSIDE` hit, and those patterns match ordinary prose. That lets these through:
- any backticked span, so `` `the crewmate` checks it`` passes
- `make \w`, so "make sure the reviewer is happy" passes
- `\btests?\b` inside "self-test"
- any `%`, so "the reviewer is 100% sure" passes
- "the model is the judge"
- "his word"
- "eval" and "github"

Refusing these is the feature itself. `_ready` launches whenever `proven()` returns `""`, so this gate is the only enforcement. Both reviewers found it separately and each gave a concrete input that passes. The tests pin only the happy side of the precedence rule.

Fix:
- Make the outside patterns specific: a path (`tests?/\S+`, `test_\w+`), a backticked span only when it starts with a known command (`make <target>`, `uv`, `pytest`, `jbus`, `jgauge`), and `%` only near a metric word.
- Drop "his word/pick/eye", or tie them to "the user".
- Add each example above to `REFUSED`, so a test runs `parse.proof` on it and asserts refusal.

**2. A missing `Proves it:` line is exempt forever, not only for briefs already queued.** (A2)
`proven()` returns `""` whenever the line is absent, and nothing ties that exemption to when the row was approved. Any future brief that leaves the line out launches with no gate, and the requirement survives only as prose in the home skill. A3's evidence shows the Design line is enforced on a missing line, not exempted, and the Done-when says to follow that precedent. Fix: grandfather by something the queue already records, such as rows approved before the cut-off or by `brief_sha`. Gate a missing line on anything approved later. Approved rows stay unstranded, and omitting the line stops being a bypass.

### Consider

- **One brief failing both checks costs the user two gates and two re-approvals.** (A3, with B3's `_ready` part) The fix is small and stays in `dispatch.py`: collect every check's fault, join them, and raise one gate keyed by the brief sha. It also removes the `short, kind` juggling. Worth doing since every approval is the user's, but it is not a correctness bug.
- **Template text is detected by a leading `<`.** (A6, B5) It fails both ways: a real line like `<= 50 ms p95` is refused, and the guide text with its brackets stripped is accepted. Comparing against the actual template line, or `^<[^>]*>$`, is exact and cheap. The Done-when names "the template line" explicitly, so tightening it is reasonable. Fix 1 also shrinks the second half of this risk.
- **`Brief.proof` (and `Proof.said`) are read only by tests.** (A5, B4) This PR adds surface with no consumer. Deleting it is the cheap fix. Keep it only if the jbriefs page is meant to show it.

### Noted
- **Duplicated head-line loop.** (A4, B3) A shared `head_line(text, label)` in `jbriefs.parse` is the right end state. Moving `designed` touches a do-not-touch rule, so leave it for later. `proven` as a thin wrapper is minor.
- **Two Done-when items live in the Result, not the diff.** (A7, B6) These are the grandfather/refuse statement and the real queued brief run through the launch check with its line printed. Check them in the Result. Note that the grandfather statement must change once Act On #2 is fixed.

### Dismissed
- None outright. B3's suggestion of a `(kind, check)` tuple loop in `_ready` is folded into the double-gate item rather than treated as a separate abstraction request. With only two checks, that is the whole justification for it.

### Agreement Map
The reviewers converged hard on the one thing that matters: the outside/self precedence makes the gate easy to pass by accident. B rated it critical, A a warning. Both supplied concrete failing inputs, so it is first. Their nits matched almost one for one, which suggests the rest of the change is sound. A alone traced how the gate behaves over time: the permanent exemption and the double approval. Those are the less obvious, queue-level effects. Fix the two Act On items and their tests, and this ships.

BUCKETS
A1: Act on
A2: Act on
A3: Consider
A4: Noted
A5: Consider
A6: Consider
A7: Noted
B1: Act on
B2: Act on
B3: Noted
B4: Consider
B5: Consider
B6: Noted
