# skill-cut eval: results

Written by `uv run python features/evals/evals/skill-cut/eval.py`, never by hand.

Base: `63ffed6efb8068c5c7ce8c4ea0916a7fd87eedf0`.
Variant: `5d6a312d1c822ef10aa0ee0e22fde61484436489`.
Candidate: `claude-opus-5-5` at `medium` effort, no tools.
Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle.
Trials: 3 a case and arm.

Files that differ between the two revisions: `skills/pr-review/the-review.md`.
The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.608 | 0.706 | 0.706 | 0.06 / 0.00 / 0.12 |
| `brief-size-and-playbook-checked` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `ci-self-hosted` | 0.385 | 0.385 | 0.385 | 0.00 / 0.00 / 0.00 |
| `deeper-home-step` | 0.641 | 0.615 | 0.615 | 0.08 / 0.00 / 0.00 |
| `deeper-proves-it` | 0.846 | 0.795 | 0.641 | 0.00 / 0.15 / 0.15 |
| `deeper-skill` | 0.872 | 0.872 | 0.923 | 0.08 / 0.08 / 0.00 |
| `exec-removal-jstack` | 0.500 | 0.467 | 0.367 | 0.20 / 0.20 / 0.40 |
| `gate-silent-default` | 0.818 | 0.848 | 0.788 | 0.00 / 0.09 / 0.27 |
| `home-on-bus` | 0.758 | 0.697 | 0.758 | 0.09 / 0.09 / 0.09 |
| `jv-shell` | 0.784 | 0.784 | 0.745 | 0.12 / 0.12 / 0.12 |
| `jv-threads` | 0.844 | 0.756 | 0.711 | 0.20 / 0.07 / 0.13 |
| `one-review-thread` | 0.667 | 0.667 | 0.633 | 0.10 / 0.10 / 0.10 |
| `pstack-autopilot-ketchup` | 0.556 | 0.593 | 0.667 | 0.22 / 0.22 / 0.22 |
| `pstack-depth-style` | 0.867 | 0.867 | 0.900 | 0.10 / 0.10 / 0.00 |
| `pstack-rebase-cap` | 0.727 | 0.697 | 0.667 | 0.00 / 0.09 / 0.09 |
| `pstack-trigger-effort` | 0.722 | 0.722 | 0.611 | 0.08 / 0.08 / 0.08 |
| `standing-undo` | 0.722 | 0.667 | 0.750 | 0.08 / 0.17 / 0.00 |

Mean over 17 cases: base 0.725, base again 0.714, variant 0.698.
Noise floor (base against base again): 0.011, so the variant is held to 0.714 or above: it is not.
Variant against base over the cases: 5 higher, 3 tied, 9 lower, sign test p 0.424: no loss under 0.05.
**Regresses.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.646 | 0.907 | 8.86 |
| base-again | 0.643 | 0.903 | 9.10 |
| variant | 0.615 | 0.903 | 8.57 |

## Family `steps`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `crew-info-finding` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `crew-link-first` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-outside-where` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `crew-stale-base` | 0.333 | 0.667 | 0.000 | 1.00 / 1.00 / 0.00 |
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
| `pr-review-severity` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-no-launch` | 0.333 | 1.000 | 0.667 | 1.00 / 0.00 / 1.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 27 cases: base 0.840, base again 0.877, variant 0.840.
Noise floor (base against base again): 0.037, so the variant is held to 0.802 or above: it is.
Variant against base over the cases: 1 higher, 25 tied, 1 lower, sign test p 1.000: no loss under 0.05.
**Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 22 of 243 answers settled by the judge (base 8, base-again 7, variant 7).

**Verdict of this run: the variant regresses**, by the rule in `README.md`: in `lead` its mean is lower than base minus the noise floor, or the sign test against base shows a loss under 0.05.
