# skill-cut eval: results

Written by `uv run python features/evals/evals/skill-cut/eval.py`, never by hand.

Base: `c03cc3de2e23b0d6d804f6ce789fc53b204088ca`.
Variant: `0275aa91f4727431417c6da5782b0e355c98c96a`.
Candidate: `claude-opus-5-5` at `medium` effort, no tools.
Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle.
Trials: 3 a case and arm.

Files that differ between the two revisions: `skills/pr-review/SKILL.md`, `skills/pr-review/the-review.md`.
The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.745 | 0.725 | 0.353 | 0.06 / 0.06 / 0.00 |
| `brief-size-and-playbook-checked` | 0.800 | 0.867 | 0.200 | 0.00 / 0.20 / 0.00 |
| `ci-self-hosted` | 0.513 | 0.385 | 0.385 | 0.38 / 0.00 / 0.00 |
| `deeper-home-step` | 0.615 | 0.615 | 0.590 | 0.00 / 0.00 / 0.38 |
| `deeper-proves-it` | 0.641 | 0.744 | 0.462 | 0.15 / 0.15 / 0.00 |
| `deeper-skill` | 0.872 | 0.897 | 0.462 | 0.08 / 0.08 / 0.00 |
| `exec-removal-jstack` | 0.400 | 0.333 | 0.500 | 0.20 / 0.10 / 0.00 |
| `gate-silent-default` | 0.879 | 0.848 | 0.273 | 0.09 / 0.09 / 0.00 |
| `home-on-bus` | 0.818 | 0.788 | 0.182 | 0.18 / 0.09 / 0.00 |
| `jv-shell` | 0.824 | 0.706 | 0.176 | 0.00 / 0.24 / 0.00 |
| `jv-threads` | 0.667 | 0.689 | 0.200 | 0.13 / 0.07 / 0.00 |
| `one-review-thread` | 0.633 | 0.600 | 0.367 | 0.10 / 0.00 / 0.20 |
| `pstack-autopilot-ketchup` | 0.556 | 0.593 | 0.556 | 0.22 / 0.22 / 0.00 |
| `pstack-depth-style` | 0.867 | 0.833 | 0.300 | 0.10 / 0.10 / 0.00 |
| `pstack-rebase-cap` | 0.667 | 0.697 | 0.455 | 0.09 / 0.09 / 0.00 |
| `pstack-trigger-effort` | 0.611 | 0.639 | 0.500 | 0.08 / 0.08 / 0.00 |
| `standing-undo` | 0.722 | 0.694 | 0.389 | 0.08 / 0.08 / 0.17 |

Mean over 17 cases: base 0.696, base again 0.686, variant 0.373.
Noise floor (base against base again): 0.010, so the variant is held to 0.686 or above: it is not.
Variant against base over the cases: 1 higher, 1 tied, 15 lower, sign test p 0.001: a loss under 0.05.
**Regresses.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.623 | 0.914 | 9.12 |
| base-again | 0.610 | 0.896 | 8.84 |
| variant | 0.249 | 0.054 | 0.39 |

## Family `steps`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `crew-info-finding` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-link-first` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-outside-where` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-row-budget` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-row-comment` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-row-conflict` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-row-gate` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-row-link` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-row-no-pr` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-row-number` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-row-telling` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-stale-base` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `expert-correction` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `expert-no-code` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `expert-roll-over` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `handoff-crewmate` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `handoff-not-carried` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `handoff-stop-poll` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `home-grill-first` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `home-hand-off` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `home-message-acts` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `home-not-the-work` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `migrate-delete-old` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `migrate-external` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `migrate-tests` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-already` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-one-thread` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-outside-where` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-severity` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-no-launch` | 0.000 | 0.000 | 0.333 | 0.00 / 0.00 / 1.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-brief` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-budget` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-fault` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-gate` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-test-slot` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-visual` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-wide` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 42 cases: base 0.976, base again 0.976, variant 0.984.
Noise floor (base against base again): 0.000, so the variant is held to 0.976 or above: it is.
Variant against base over the cases: 1 higher, 41 tied, 0 lower, sign test p 1.000: no loss under 0.05.
**Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 9 of 378 answers settled by the judge (base 3, base-again 3, variant 3).

**Verdict of this run: the variant regresses**, by the rule in `README.md`: in `lead` its mean is lower than base minus the noise floor, or the sign test against base shows a loss under 0.05.
