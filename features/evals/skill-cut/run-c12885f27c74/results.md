# skill-cut eval: results

Written by `uv run python features/evals/skill-cut/eval.py`. Do not edit by hand.

Base: `5a9a4d0401065b73a16dbd3183670901b6cbc80d`. Variant: `c12885f27c74286e18afc86a50054568842c9f2d`. Candidate: `claude-opus-5-5` at `medium` effort, no tools. Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle. Trials: 3 a case and arm.

Files that differ between the two revisions: `principles/migrate-callers-then-delete-legacy-apis.md`, `principles/type-system-discipline.md`. The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.745 | 0.745 | 0.706 | 0.06 / 0.06 / 0.00 |
| `brief-size-and-playbook-checked` | 0.933 | 0.967 | 1.000 | 0.20 / 0.10 / 0.00 |
| `ci-self-hosted` | 0.538 | 0.538 | 0.385 | 0.46 / 0.46 / 0.00 |
| `deeper-home-step` | 0.564 | 0.538 | 0.641 | 0.08 / 0.00 / 0.08 |
| `deeper-proves-it` | 0.846 | 0.769 | 0.795 | 0.00 / 0.15 / 0.15 |
| `deeper-skill` | 0.949 | 0.897 | 0.923 | 0.08 / 0.08 / 0.00 |
| `exec-removal-jstack` | 0.333 | 0.433 | 0.533 | 0.10 / 0.30 / 0.10 |
| `gate-silent-default` | 0.848 | 0.818 | 0.848 | 0.09 / 0.00 / 0.09 |
| `home-on-bus` | 0.818 | 0.788 | 0.788 | 0.00 / 0.09 / 0.09 |
| `jv-shell` | 0.784 | 0.784 | 0.784 | 0.12 / 0.06 / 0.12 |
| `jv-threads` | 0.800 | 0.756 | 0.844 | 0.20 / 0.07 / 0.20 |
| `one-review-thread` | 0.700 | 0.667 | 0.633 | 0.00 / 0.10 / 0.10 |
| `pstack-autopilot-ketchup` | 0.519 | 0.519 | 0.519 | 0.11 / 0.11 / 0.11 |
| `pstack-depth-style` | 0.800 | 0.833 | 0.833 | 0.00 / 0.10 / 0.10 |
| `pstack-rebase-cap` | 0.697 | 0.697 | 0.727 | 0.09 / 0.09 / 0.00 |
| `pstack-trigger-effort` | 0.694 | 0.639 | 0.722 | 0.08 / 0.25 / 0.08 |
| `standing-undo` | 0.722 | 0.722 | 0.694 | 0.08 / 0.08 / 0.08 |

Mean over 17 cases: base 0.723, base again 0.712, variant 0.728. Noise floor (base against base again): 0.011, so the variant is held to 0.712 or above: it is. Variant against base over the cases: 7 higher, 3 tied, 7 lower, sign test p 1.000: no loss under 0.05. **Does not regress.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.653 | 0.921 | 9.08 |
| base-again | 0.636 | 0.914 | 9.08 |
| variant | 0.647 | 0.907 | 8.86 |

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
| `scout-no-launch` | 1.000 | 1.000 | 0.333 | 0.00 / 0.00 / 1.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 27 cases: base 1.000, base again 1.000, variant 0.975. Noise floor (base against base again): 0.000, so the variant is held to 1.000 or above: it is not. Variant against base over the cases: 0 higher, 26 tied, 1 lower, sign test p 1.000: no loss under 0.05. **Regresses.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 2 of 243 answers settled by the judge (base 0, base-again 0, variant 2).

**Verdict of this run: the variant regresses**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
