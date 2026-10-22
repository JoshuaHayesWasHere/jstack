# skill-cut eval: results

Written by `uv run python features/evals/evals/skill-cut/eval.py`, never by hand.

Base: `3ab67eb47ac97dc407a4687631301cc255990256`. Variant: `0d1d871af1a35a48b7d5727cd67cecabc63cf162`. Candidate: `claude-opus-5-5` at `medium` effort, no tools. Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle. Trials: 3 a case and arm.

Files that differ between the two revisions: `principles/migrate-callers-then-delete-legacy-apis.md`, `principles/type-system-discipline.md`, `skills/interrogate/references/lead-judgment.md`. The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.765 | 0.725 | 0.745 | 0.00 / 0.06 / 0.06 |
| `brief-size-and-playbook-checked` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `ci-self-hosted` | 0.385 | 0.513 | 0.564 | 0.00 / 0.38 / 0.54 |
| `deeper-home-step` | 0.538 | 0.564 | 0.538 | 0.15 / 0.08 / 0.15 |
| `deeper-proves-it` | 0.846 | 0.718 | 0.795 | 0.00 / 0.08 / 0.15 |
| `deeper-skill` | 0.923 | 0.923 | 0.923 | 0.15 / 0.00 / 0.00 |
| `exec-removal-jstack` | 0.500 | 0.433 | 0.333 | 0.20 / 0.20 / 0.10 |
| `gate-silent-default` | 0.848 | 0.879 | 0.848 | 0.09 / 0.09 / 0.09 |
| `home-on-bus` | 0.758 | 0.697 | 0.788 | 0.09 / 0.09 / 0.09 |
| `jv-shell` | 0.784 | 0.745 | 0.804 | 0.06 / 0.18 / 0.06 |
| `jv-threads` | 0.778 | 0.756 | 0.889 | 0.13 / 0.20 / 0.07 |
| `one-review-thread` | 0.700 | 0.633 | 0.700 | 0.00 / 0.10 / 0.00 |
| `pstack-autopilot-ketchup` | 0.519 | 0.519 | 0.556 | 0.11 / 0.22 / 0.22 |
| `pstack-depth-style` | 0.833 | 0.800 | 0.833 | 0.10 / 0.00 / 0.10 |
| `pstack-rebase-cap` | 0.727 | 0.697 | 0.667 | 0.00 / 0.09 / 0.09 |
| `pstack-trigger-effort` | 0.750 | 0.667 | 0.639 | 0.00 / 0.25 / 0.25 |
| `standing-undo` | 0.750 | 0.722 | 0.750 | 0.00 / 0.08 / 0.00 |

Mean over 17 cases: base 0.730, base again 0.705, variant 0.728. Noise floor (base against base again): 0.024, so the variant is held to 0.705 or above: it is. Variant against base over the cases: 5 higher, 7 tied, 5 lower, sign test p 1.000: no loss under 0.05. **Does not regress.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.654 | 0.896 | 8.84 |
| base-again | 0.636 | 0.900 | 9.06 |
| variant | 0.653 | 0.921 | 9.25 |

## Family `steps`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `crew-info-finding` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-link-first` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-outside-where` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
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
| `pr-review-noticed` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-one-thread` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-severity` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-no-launch` | 1.000 | 1.000 | 0.667 | 0.00 / 0.00 / 1.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 27 cases: base 1.000, base again 1.000, variant 0.988. Noise floor (base against base again): 0.000, so the variant is held to 1.000 or above: it is not. Variant against base over the cases: 0 higher, 26 tied, 1 lower, sign test p 1.000: no loss under 0.05. **Regresses.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 1 of 243 answers settled by the judge (base 0, base-again 0, variant 1).

**Verdict of this run: the variant regresses**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
