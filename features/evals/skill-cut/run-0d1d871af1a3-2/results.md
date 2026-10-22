# skill-cut eval: results

Written by `uv run python features/evals/skill-cut/eval.py`. Do not edit by hand.

Base: `5a9a4d0401065b73a16dbd3183670901b6cbc80d`. Variant: `0d1d871af1a35a48b7d5727cd67cecabc63cf162`. Candidate: `claude-opus-5-5` at `medium` effort, no tools. Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle. Trials: 3 a case and arm.

Files that differ between the two revisions: `principles/migrate-callers-then-delete-legacy-apis.md`, `principles/type-system-discipline.md`, `skills/interrogate/references/lead-judgment.md`. The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.706 | 0.745 | 0.745 | 0.12 / 0.06 / 0.06 |
| `brief-size-and-playbook-checked` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `ci-self-hosted` | 0.385 | 0.385 | 0.385 | 0.00 / 0.00 / 0.00 |
| `deeper-home-step` | 0.590 | 0.615 | 0.590 | 0.08 / 0.15 / 0.08 |
| `deeper-proves-it` | 0.795 | 0.795 | 0.538 | 0.15 / 0.15 / 0.00 |
| `deeper-skill` | 0.923 | 0.897 | 0.923 | 0.00 / 0.08 / 0.00 |
| `exec-removal-jstack` | 0.567 | 0.500 | 0.433 | 0.20 / 0.30 / 0.30 |
| `gate-silent-default` | 0.848 | 0.818 | 0.818 | 0.09 / 0.00 / 0.00 |
| `home-on-bus` | 0.788 | 0.667 | 0.697 | 0.09 / 0.09 / 0.09 |
| `jv-shell` | 0.824 | 0.784 | 0.824 | 0.00 / 0.06 / 0.00 |
| `jv-threads` | 0.778 | 0.711 | 0.822 | 0.13 / 0.07 / 0.07 |
| `one-review-thread` | 0.667 | 0.700 | 0.667 | 0.10 / 0.00 / 0.10 |
| `pstack-autopilot-ketchup` | 0.519 | 0.481 | 0.444 | 0.11 / 0.11 / 0.00 |
| `pstack-depth-style` | 0.800 | 0.867 | 0.800 | 0.00 / 0.10 / 0.00 |
| `pstack-rebase-cap` | 0.727 | 0.697 | 0.667 | 0.00 / 0.09 / 0.09 |
| `pstack-trigger-effort` | 0.750 | 0.694 | 0.667 | 0.00 / 0.08 / 0.17 |
| `standing-undo` | 0.750 | 0.750 | 0.750 | 0.00 / 0.00 / 0.00 |

Mean over 17 cases: base 0.730, base again 0.712, variant 0.692. Noise floor (base against base again): 0.018, so the variant is held to 0.712 or above: it is not. Variant against base over the cases: 2 higher, 8 tied, 7 lower, sign test p 0.180: no loss under 0.05. **Regresses.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.651 | 0.910 | 8.88 |
| base-again | 0.633 | 0.889 | 8.86 |
| variant | 0.629 | 0.900 | 9.06 |

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
