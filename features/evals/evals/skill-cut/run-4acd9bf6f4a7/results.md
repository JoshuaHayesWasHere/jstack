# skill-cut eval: results

Written by `uv run python features/evals/evals/skill-cut/eval.py`. Do not edit by hand.

Base: `5a9a4d0401065b73a16dbd3183670901b6cbc80d`. Variant: `4acd9bf6f4a7960209df550cd88568de450f4a46`. Candidate: `claude-opus-5-5` at `medium` effort, no tools. Judge: `claude-sonnet-5-5` at `medium`, only for an answer the key cannot settle. Trials: 3 a case and arm.

Files that differ between the two revisions: `skills/crew/SKILL.md`, `skills/expert/SKILL.md`, `skills/handoff/SKILL.md`, `skills/home/SKILL.md`, `skills/pr-review/SKILL.md`, `skills/scout/SKILL.md`. The diff is `variant.patch`.

## Family `lead`: each case, the mean of its trials, and the spread of trials

| Case | Base | Base again | Variant | Spread of trials, base / again / variant |
|---|---|---|---|---|
| `brief-lint-approval-binding` | 0.667 | 0.745 | 0.765 | 0.18 / 0.06 / 0.00 |
| `brief-size-and-playbook-checked` | 0.933 | 1.000 | 0.967 | 0.20 / 0.00 / 0.10 |
| `ci-self-hosted` | 0.385 | 0.436 | 0.385 | 0.00 / 0.15 / 0.00 |
| `deeper-home-step` | 0.590 | 0.513 | 0.564 | 0.08 / 0.08 / 0.08 |
| `deeper-proves-it` | 0.846 | 0.846 | 0.692 | 0.00 / 0.00 / 0.00 |
| `deeper-skill` | 0.923 | 0.949 | 0.923 | 0.00 / 0.08 / 0.00 |
| `exec-removal-jstack` | 0.467 | 0.400 | 0.467 | 0.10 / 0.20 / 0.30 |
| `gate-silent-default` | 0.879 | 0.848 | 0.879 | 0.09 / 0.09 / 0.09 |
| `home-on-bus` | 0.788 | 0.788 | 0.818 | 0.09 / 0.09 / 0.00 |
| `jv-shell` | 0.824 | 0.804 | 0.765 | 0.00 / 0.06 / 0.12 |
| `jv-threads` | 0.756 | 0.711 | 0.822 | 0.07 / 0.07 / 0.20 |
| `one-review-thread` | 0.700 | 0.700 | 0.700 | 0.00 / 0.00 / 0.00 |
| `pstack-autopilot-ketchup` | 0.519 | 0.444 | 0.481 | 0.22 / 0.00 / 0.11 |
| `pstack-depth-style` | 0.867 | 0.867 | 0.833 | 0.10 / 0.10 / 0.10 |
| `pstack-rebase-cap` | 0.667 | 0.727 | 0.727 | 0.09 / 0.00 / 0.00 |
| `pstack-trigger-effort` | 0.694 | 0.611 | 0.750 | 0.08 / 0.17 / 0.00 |
| `standing-undo` | 0.722 | 0.722 | 0.667 | 0.08 / 0.08 / 0.17 |

Mean over 17 cases: base 0.719, base again 0.712, variant 0.718. Noise floor (base against base again): 0.007, so the variant is held to 0.712 or above: it is. Variant against base over the cases: 6 higher, 5 tied, 6 lower, sign test p 1.000: no loss under 0.05. **Does not regress.**

Readings, not counted by the rule (mean over the cases): agreement on sent, noted and dismissed, three ways; the share of the findings the crewmate fixed that the answer sent; findings sent per answer.

| Arm | Three ways | Fixed ones sent | Sent per answer |
|---|---|---|---|
| base | 0.641 | 0.896 | 8.78 |
| base-again | 0.646 | 0.903 | 8.92 |
| variant | 0.645 | 0.903 | 8.86 |

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
| `scout-no-launch` | 0.333 | 0.667 | 0.000 | 1.00 / 1.00 / 0.00 |
| `scout-no-runs` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `scout-not-the-task` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-exhaustive` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-no-cast` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |
| `types-sum-type` | 1.000 | 1.000 | 1.000 | 0.00 / 0.00 / 0.00 |

Mean over 27 cases: base 0.975, base again 0.988, variant 0.963. Noise floor (base against base again): 0.012, so the variant is held to 0.963 or above: it is. Variant against base over the cases: 0 higher, 26 tied, 1 lower, sign test p 1.000: no loss under 0.05. **Does not regress.**

## The judge

- `lead`: 0 of 153 answers settled by the judge (base 0, base-again 0, variant 0).
- `steps`: 6 of 243 answers settled by the judge (base 2, base-again 1, variant 3).

**Verdict of this run: the variant does not regress**, by the rule in `README.md`: in each family its mean is no lower than base minus the noise floor, and the sign test against base shows no loss under 0.05.
