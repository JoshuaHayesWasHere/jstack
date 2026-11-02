# skill-cut eval: results

Written by `uv run python features/evals/evals/skill-cut/eval.py`, never by hand.

Base: `63ffed6efb8068c5c7ce8c4ea0916a7fd87eedf0`.
Variant: `b7aa53c15c1238c9e50850babe2b36ed45c95197`.
Candidate: `claude-opus-5-5` at `medium` effort, no tools.
Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle.
Trials: 3 a case and arm.

Files that differ between the two revisions: `skills/crew/SKILL.md`, `skills/scout/SKILL.md`.
The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.667 | 0.725 | 0.667 | 0.18 / 0.06 / 0.18 |
| `brief-size-and-playbook-checked` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `ci-self-hosted` | 0.385 | 0.564 | 0.385 | 0.00 / 0.54 / 0.00 |
| `deeper-home-step` | 0.615 | 0.641 | 0.615 | 0.00 / 0.08 / 0.15 |
| `deeper-proves-it` | 0.795 | 0.744 | 0.795 | 0.15 / 0.15 / 0.15 |
| `deeper-skill` | 0.949 | 0.923 | 0.923 | 0.08 / 0.00 / 0.00 |
| `exec-removal-jstack` | 0.433 | 0.333 | 0.400 | 0.10 / 0.10 / 0.20 |
| `gate-silent-default` | 0.848 | 0.848 | 0.848 | 0.09 / 0.09 / 0.09 |
| `home-on-bus` | 0.758 | 0.818 | 0.758 | 0.09 / 0.00 / 0.09 |
| `jv-shell` | 0.745 | 0.784 | 0.765 | 0.06 / 0.06 / 0.12 |
| `jv-threads` | 0.867 | 0.800 | 0.822 | 0.13 / 0.27 / 0.07 |
| `one-review-thread` | 0.667 | 0.700 | 0.700 | 0.10 / 0.00 / 0.00 |
| `pstack-autopilot-ketchup` | 0.630 | 0.593 | 0.444 | 0.33 / 0.22 / 0.00 |
| `pstack-depth-style` | 0.800 | 0.867 | 0.833 | 0.00 / 0.20 / 0.10 |
| `pstack-rebase-cap` | 0.697 | 0.697 | 0.667 | 0.09 / 0.09 / 0.09 |
| `pstack-trigger-effort` | 0.694 | 0.722 | 0.722 | 0.08 / 0.08 / 0.08 |
| `standing-undo` | 0.722 | 0.722 | 0.750 | 0.08 / 0.08 / 0.00 |

Mean over 17 cases: base 0.722, base again 0.734, variant 0.711.
Noise floor (base against base again): 0.012, so the variant is held to 0.709 or above: it is.
Variant against base over the cases: 5 higher, 7 tied, 5 lower, sign test p 1.000: no loss under 0.05.
**Does not regress.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.639 | 0.889 | 8.69 |
| base-again | 0.659 | 0.925 | 9.02 |
| variant | 0.641 | 0.900 | 8.78 |

## Family `steps`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `crew-info-finding` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `crew-link-first` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-outside-where` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `crew-stale-base` | 0.000 | 0.667 | 0.000 | 0.00 / 1.00 / 0.00 |
| `expert-correction` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `expert-no-code` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `expert-roll-over` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `handoff-crewmate` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `handoff-not-carried` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `handoff-stop-poll` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `home-grill-first` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `home-hand-off` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `home-message-acts` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `home-not-the-work` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `migrate-delete-old` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `migrate-external` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `migrate-tests` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-already` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-one-thread` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-outside-where` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `pr-review-severity` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `scout-no-launch` | 1.000 | 0.667 | 1.000 | 0.00 / 1.00 / 0.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 27 cases: base 0.815, base again 0.827, variant 0.815.
Noise floor (base against base again): 0.012, so the variant is held to 0.802 or above: it is.
Variant against base over the cases: 0 higher, 27 tied, 0 lower, sign test p 1.000: no loss under 0.05.
**Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 24 of 243 answers settled by the judge (base 8, base-again 9, variant 7).

**Verdict of this run: the variant does not regress**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
