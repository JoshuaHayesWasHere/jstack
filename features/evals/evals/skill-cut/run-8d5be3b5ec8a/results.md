# skill-cut eval: results

Written by `uv run python features/evals/evals/skill-cut/eval.py`, never by hand.

Base: `63ffed6efb8068c5c7ce8c4ea0916a7fd87eedf0`.
Variant: `8d5be3b5ec8a0ae2506aeb75f9c2d2b691eb0818`.
Candidate: `claude-opus-5-5` at `medium` effort, no tools.
Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle.
Trials: 3 a case and arm.

Files that differ between the two revisions: `skills/crew/SKILL.md`, `skills/home/SKILL.md`, `skills/pr-review/SKILL.md`, `skills/pr-review/the-review.md`, `skills/scout/SKILL.md`.
The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.706 | 0.765 | 0.725 | 0.18 / 0.00 / 0.12 |
| `brief-size-and-playbook-checked` | 0.900 | 1.000 | 1.000 | 0.20 / 0.00 / 0.00 |
| `ci-self-hosted` | 0.385 | 0.385 | 0.385 | 0.00 / 0.00 / 0.00 |
| `deeper-home-step` | 0.692 | 0.718 | 0.615 | 0.15 / 0.08 / 0.00 |
| `deeper-proves-it` | 0.641 | 0.641 | 0.744 | 0.31 / 0.15 / 0.15 |
| `deeper-skill` | 0.872 | 0.897 | 0.872 | 0.08 / 0.08 / 0.08 |
| `exec-removal-jstack` | 0.433 | 0.433 | 0.533 | 0.10 / 0.30 / 0.10 |
| `gate-silent-default` | 0.818 | 0.818 | 0.848 | 0.00 / 0.00 / 0.09 |
| `home-on-bus` | 0.788 | 0.758 | 0.758 | 0.09 / 0.09 / 0.09 |
| `jv-shell` | 0.824 | 0.824 | 0.745 | 0.00 / 0.00 / 0.12 |
| `jv-threads` | 0.733 | 0.800 | 0.800 | 0.13 / 0.13 / 0.13 |
| `one-review-thread` | 0.700 | 0.667 | 0.667 | 0.00 / 0.10 / 0.10 |
| `pstack-autopilot-ketchup` | 0.444 | 0.667 | 0.556 | 0.00 / 0.00 / 0.33 |
| `pstack-depth-style` | 0.800 | 0.833 | 0.833 | 0.00 / 0.10 / 0.10 |
| `pstack-rebase-cap` | 0.636 | 0.697 | 0.697 | 0.00 / 0.09 / 0.09 |
| `pstack-trigger-effort` | 0.694 | 0.750 | 0.667 | 0.08 / 0.00 / 0.00 |
| `standing-undo` | 0.778 | 0.667 | 0.694 | 0.08 / 0.17 / 0.08 |

Mean over 17 cases: base 0.697, base again 0.725, variant 0.714.
Noise floor (base against base again): 0.028, so the variant is held to 0.669 or above: it is.
Variant against base over the cases: 9 higher, 2 tied, 6 lower, sign test p 0.607: no loss under 0.05.
**Does not regress.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.625 | 0.907 | 9.10 |
| base-again | 0.646 | 0.907 | 8.86 |
| variant | 0.644 | 0.907 | 8.90 |

## Family `steps`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `crew-info-finding` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `crew-link-first` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `crew-outside-where` | 0.000 | 0.000 | 0.000 | 0.00 / 0.00 / 0.00 |
| `crew-stale-base` | 0.333 | 0.000 | 0.667 | 1.00 / 0.00 / 1.00 |
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
| `scout-no-launch` | 1.000 | 0.667 | 0.667 | 0.00 / 1.00 / 1.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 27 cases: base 0.864, base again 0.840, variant 0.864.
Noise floor (base against base again): 0.025, so the variant is held to 0.840 or above: it is.
Variant against base over the cases: 1 higher, 25 tied, 1 lower, sign test p 1.000: no loss under 0.05.
**Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 21 of 243 answers settled by the judge (base 6, base-again 7, variant 8).

**Verdict of this run: the variant does not regress**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
