# skill-cut eval: results

Written by `uv run python features/evals/evals/skill-cut/eval.py`, never by hand.

Base: `e3c4abf11875eb1953cf005cf26899655b758fe1`.
Variant: `e4ca848afec2e85b4c33b17e17716c543d07fa9f`.
Candidate: `claude-opus-5-5` at `medium` effort, no tools.
Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle.
Trials: 3 a case and arm.

Files that differ between the two revisions: `skills/crew/SKILL.md`, `skills/scout/SKILL.md`.
The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.725 | 0.765 | 0.725 | 0.06 / 0.00 / 0.12 |
| `brief-size-and-playbook-checked` | 1.000 | 1.000 | 0.933 | 0.00 / 0.00 / 0.20 |
| `ci-self-hosted` | 0.487 | 0.385 | 0.385 | 0.31 / 0.00 / 0.00 |
| `deeper-home-step` | 0.590 | 0.641 | 0.564 | 0.08 / 0.08 / 0.08 |
| `deeper-proves-it` | 0.769 | 0.744 | 0.692 | 0.15 / 0.15 / 0.00 |
| `deeper-skill` | 0.923 | 0.923 | 0.923 | 0.00 / 0.00 / 0.00 |
| `exec-removal-jstack` | 0.433 | 0.367 | 0.567 | 0.30 / 0.10 / 0.30 |
| `gate-silent-default` | 0.818 | 0.879 | 0.818 | 0.00 / 0.18 / 0.00 |
| `home-on-bus` | 0.788 | 0.818 | 0.788 | 0.09 / 0.18 / 0.09 |
| `jv-shell` | 0.784 | 0.824 | 0.765 | 0.06 / 0.00 / 0.12 |
| `jv-threads` | 0.844 | 0.711 | 0.867 | 0.13 / 0.20 / 0.13 |
| `one-review-thread` | 0.667 | 0.700 | 0.700 | 0.10 / 0.00 / 0.00 |
| `pstack-autopilot-ketchup` | 0.481 | 0.481 | 0.519 | 0.11 / 0.11 / 0.22 |
| `pstack-depth-style` | 0.833 | 0.867 | 0.833 | 0.10 / 0.10 / 0.10 |
| `pstack-rebase-cap` | 0.667 | 0.697 | 0.667 | 0.09 / 0.09 / 0.09 |
| `pstack-trigger-effort` | 0.722 | 0.694 | 0.722 | 0.08 / 0.08 / 0.08 |
| `standing-undo` | 0.722 | 0.750 | 0.722 | 0.08 / 0.00 / 0.08 |

Mean over 17 cases: base 0.721, base again 0.720, variant 0.717.
Noise floor (base against base again): 0.001, so the variant is held to 0.720 or above: it is not.
Variant against base over the cases: 4 higher, 8 tied, 5 lower, sign test p 1.000: no loss under 0.05.
**Regresses.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.658 | 0.921 | 9.31 |
| base-again | 0.644 | 0.907 | 8.71 |
| variant | 0.643 | 0.889 | 8.69 |

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
| `crew-row-number` | 0.000 | 0.000 | 1.000 | 0.00 / 0.00 / 0.00 |
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
| `scout-no-launch` | 0.667 | 0.667 | 1.000 | 1.00 / 1.00 / 0.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-brief` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-budget` | 0.000 | 0.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-fault` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-gate` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-test-slot` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-visual` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-row-wide` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 42 cases: base 0.944, base again 0.944, variant 1.000.
Noise floor (base against base again): 0.000, so the variant is held to 0.944 or above: it is.
Variant against base over the cases: 3 higher, 39 tied, 0 lower, sign test p 0.250: no loss under 0.05.
**Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 6 of 378 answers settled by the judge (base 3, base-again 3, variant 0).

**Verdict of this run: the variant regresses**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
