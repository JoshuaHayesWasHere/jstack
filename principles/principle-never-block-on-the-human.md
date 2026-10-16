# Never Block on the Human

Apply when tempted to ask 'should I do X?' on reversible work.

The human supervises asynchronously. Agents must stay unblocked. Make reasonable decisions, proceed, and let the human course-correct after the fact. Since code changes are reversible and reviewable, a wrong decision usually costs less than blocking.

- Proceed, then present. Do the work, show the result. Don't ask "should I do X?" Do X, explain why.
- Make the system self-healing. When you notice a problem, log it and fix it in the next round.
- Irreversible actions (force-push, delete production data, send external messages) still require confirmation.
- Reversible actions (write code, edit notes, split tasks) should proceed without blocking.
- Product direction comes from the human. Execution should not block.

<!-- card: Keep moving with nobody watching | 1 | On reversible work, proceed and then present. A wrong decision costs less than waiting. | `autopilot-full`; `autonomous-run`; `multi-phase-plan` -->
