# skill-cut eval: results

Written by `uv run python features/evals/skill-cut/eval.py`. Do not edit by hand.

Base: `c228ac614900a72bfcb56f3397c72ca570da17f4`. Variant: `4003f32e2b1e3c3dfd1b4625c1923dbb8b2208ee`. Candidate: `claude-opus-5-5` at `medium` effort, no tools. Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle. Trials: 3 a case and arm.

Files that differ between the two revisions: `principles/migrate-callers-then-delete-legacy-apis.md`, `principles/type-system-discipline.md`, `skills/interrogate/references/lead-judgment.md`. The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.667 | 0.765 | 0.765 | 0.24 / 0.00 / 0.00 |
| `brief-size-and-playbook-checked` | 1.000 | 0.933 | 1.000 | 0.00 / 0.20 / 0.00 |
| `ci-self-hosted` | 0.538 | 0.385 | 0.692 | 0.46 / 0.00 / 0.62 |
| `deeper-home-step` | 0.564 | 0.564 | 0.590 | 0.08 / 0.08 / 0.08 |
| `deeper-proves-it` | 0.795 | 0.846 | 0.692 | 0.15 / 0.00 / 0.31 |
| `deeper-skill` | 0.923 | 0.923 | 0.949 | 0.00 / 0.00 / 0.08 |
| `exec-removal-jstack` | 0.500 | 0.400 | 0.467 | 0.20 / 0.20 / 0.30 |
| `gate-silent-default` | 0.848 | 0.818 | 0.818 | 0.09 / 0.00 / 0.00 |
| `home-on-bus` | 0.788 | 0.788 | 0.758 | 0.09 / 0.09 / 0.09 |
| `jv-shell` | 0.804 | 0.804 | 0.824 | 0.06 / 0.06 / 0.00 |
| `jv-threads` | 0.822 | 0.733 | 0.844 | 0.20 / 0.00 / 0.07 |
| `one-review-thread` | 0.700 | 0.667 | 0.700 | 0.00 / 0.10 / 0.00 |
| `pstack-autopilot-ketchup` | 0.556 | 0.444 | 0.519 | 0.22 / 0.00 / 0.11 |
| `pstack-depth-style` | 0.833 | 0.800 | 0.833 | 0.10 / 0.00 / 0.10 |
| `pstack-rebase-cap` | 0.667 | 0.727 | 0.667 | 0.09 / 0.00 / 0.09 |
| `pstack-trigger-effort` | 0.667 | 0.722 | 0.694 | 0.25 / 0.08 / 0.08 |
| `standing-undo` | 0.722 | 0.750 | 0.750 | 0.08 / 0.00 / 0.00 |

Mean over 17 cases: base 0.729, base again 0.710, variant 0.739. Noise floor (base against base again): 0.019, so the variant is held to 0.710 or above: it is. Variant against base over the cases: 8 higher, 4 tied, 5 lower, sign test p 0.581: no loss under 0.05. **Does not regress.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.648 | 0.918 | 9.14 |
| base-again | 0.631 | 0.889 | 8.76 |
| variant | 0.655 | 0.946 | 9.39 |

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
| `scout-no-launch` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 27 cases: base 0.963, base again 0.963, variant 0.963. Noise floor (base against base again): 0.000, so the variant is held to 0.963 or above: it is. Variant against base over the cases: 0 higher, 27 tied, 0 lower, sign test p 1.000: no loss under 0.05. **Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 9 of 243 answers settled by the judge (base 3, base-again 3, variant 3).

**Verdict of this run: the variant does not regress**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
