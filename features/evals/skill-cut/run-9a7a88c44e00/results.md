# skill-cut eval: results

Written by `uv run python features/evals/skill-cut/eval.py`. Do not edit by hand.

Base: `6743509c48934b817aaf68dfeeae4818b2fb635b`. Variant: `9a7a88c44e00df085cdfc3f42916907a8144038a`. Candidate: `claude-opus-5-5` at `medium` effort, no tools. Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle. Trials: 3 a case and arm.

Files that differ between the two revisions: `skills/crew/SKILL.md`, `skills/expert/SKILL.md`, `skills/handoff/SKILL.md`, `skills/home/SKILL.md`, `skills/pr-review/SKILL.md`. The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.765 | 0.706 | 0.725 | 0.00 / 0.12 / 0.12 |
| `brief-size-and-playbook-checked` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `ci-self-hosted` | 0.385 | 0.385 | 0.385 | 0.00 / 0.00 / 0.00 |
| `deeper-home-step` | 0.590 | 0.513 | 0.538 | 0.08 / 0.15 / 0.15 |
| `deeper-proves-it` | 0.641 | 0.795 | 0.769 | 0.15 / 0.15 / 0.23 |
| `deeper-skill` | 0.923 | 0.923 | 0.923 | 0.00 / 0.00 / 0.00 |
| `exec-removal-jstack` | 0.533 | 0.433 | 0.533 | 0.20 / 0.30 / 0.10 |
| `gate-silent-default` | 0.879 | 0.848 | 0.879 | 0.18 / 0.09 / 0.09 |
| `home-on-bus` | 0.788 | 0.788 | 0.788 | 0.09 / 0.18 / 0.09 |
| `jv-shell` | 0.784 | 0.765 | 0.745 | 0.06 / 0.00 / 0.18 |
| `jv-threads` | 0.800 | 0.756 | 0.800 | 0.13 / 0.20 / 0.13 |
| `one-review-thread` | 0.700 | 0.700 | 0.667 | 0.00 / 0.00 / 0.10 |
| `pstack-autopilot-ketchup` | 0.444 | 0.444 | 0.481 | 0.00 / 0.00 / 0.11 |
| `pstack-depth-style` | 0.833 | 0.800 | 0.800 | 0.10 / 0.00 / 0.00 |
| `pstack-rebase-cap` | 0.727 | 0.727 | 0.697 | 0.00 / 0.00 / 0.09 |
| `pstack-trigger-effort` | 0.722 | 0.722 | 0.667 | 0.08 / 0.08 / 0.00 |
| `standing-undo` | 0.694 | 0.750 | 0.722 | 0.08 / 0.00 / 0.08 |

Mean over 17 cases: base 0.718, base again 0.709, variant 0.713. Noise floor (base against base again): 0.009, so the variant is held to 0.709 or above: it is. Variant against base over the cases: 3 higher, 7 tied, 7 lower, sign test p 0.344: no loss under 0.05. **Does not regress.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.639 | 0.896 | 8.75 |
| base-again | 0.641 | 0.892 | 8.94 |
| variant | 0.638 | 0.896 | 8.75 |

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
| `scout-no-launch` | 0.667 | 1.000 | 0.333 | 1.00 / 0.00 / 1.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 27 cases: base 0.988, base again 1.000, variant 0.975. Noise floor (base against base again): 0.012, so the variant is held to 0.975 or above: it is. Variant against base over the cases: 0 higher, 26 tied, 1 lower, sign test p 1.000: no loss under 0.05. **Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 3 of 243 answers settled by the judge (base 1, base-again 0, variant 2).

**Verdict of this run: the variant does not regress**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
