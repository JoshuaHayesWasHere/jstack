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
| `brief-lint-approval-binding` | 0.765 | 0.686 | 0.725 | 0.00 / 0.24 / 0.06 |
| `brief-size-and-playbook-checked` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `ci-self-hosted` | 0.385 | 0.385 | 0.385 | 0.00 / 0.00 / 0.00 |
| `deeper-home-step` | 0.590 | 0.590 | 0.538 | 0.08 / 0.15 / 0.00 |
| `deeper-proves-it` | 0.744 | 0.744 | 0.692 | 0.15 / 0.15 / 0.31 |
| `deeper-skill` | 0.923 | 0.923 | 0.923 | 0.00 / 0.00 / 0.00 |
| `exec-removal-jstack` | 0.367 | 0.300 | 0.400 | 0.20 / 0.20 / 0.20 |
| `gate-silent-default` | 0.848 | 0.818 | 0.848 | 0.09 / 0.00 / 0.09 |
| `home-on-bus` | 0.788 | 0.758 | 0.788 | 0.09 / 0.09 / 0.09 |
| `jv-shell` | 0.745 | 0.686 | 0.765 | 0.06 / 0.24 / 0.00 |
| `jv-threads` | 0.778 | 0.800 | 0.778 | 0.27 / 0.27 / 0.27 |
| `one-review-thread` | 0.700 | 0.667 | 0.700 | 0.00 / 0.10 / 0.00 |
| `pstack-autopilot-ketchup` | 0.444 | 0.444 | 0.519 | 0.00 / 0.00 / 0.11 |
| `pstack-depth-style` | 0.867 | 0.800 | 0.867 | 0.10 / 0.00 / 0.10 |
| `pstack-rebase-cap` | 0.667 | 0.697 | 0.667 | 0.09 / 0.09 / 0.09 |
| `pstack-trigger-effort` | 0.722 | 0.750 | 0.750 | 0.08 / 0.00 / 0.00 |
| `standing-undo` | 0.750 | 0.722 | 0.722 | 0.00 / 0.08 / 0.08 |

Mean over 17 cases: base 0.711, base again 0.692, variant 0.710.
Noise floor (base against base again): 0.018, so the variant is held to 0.692 or above: it is.
Variant against base over the cases: 4 higher, 9 tied, 4 lower, sign test p 1.000: no loss under 0.05.
**Does not regress.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.639 | 0.900 | 8.75 |
| base-again | 0.624 | 0.885 | 8.75 |
| variant | 0.642 | 0.889 | 8.78 |

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
| `scout-no-launch` | 0.667 | 1.000 | 1.000 | 1.00 / 0.00 / 0.00 |
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

Mean over 42 cases: base 0.944, base again 0.952, variant 1.000.
Noise floor (base against base again): 0.008, so the variant is held to 0.937 or above: it is.
Variant against base over the cases: 3 higher, 39 tied, 0 lower, sign test p 0.250: no loss under 0.05.
**Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 4 of 378 answers settled by the judge (base 3, base-again 1, variant 0).

**Verdict of this run: the variant does not regress**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
