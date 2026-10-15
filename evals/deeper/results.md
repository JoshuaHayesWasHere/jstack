# /deeper eval: results

Written by `uv run python evals/deeper/eval.py`. Do not edit by hand.

Writer: `claude-opus-5-5` at `medium` effort, no tools. Trials: 2 a case and arm. Template: `templates/brief.md` at sha256 `e2d7213b0af3`. Skill: `skills/deeper/SKILL.md` at sha256 `0293aac0d8ea`.

## Each case, the mean of its trials (plain / deeper)

| Case | Kind | Raw sources | Instruments | Beyond the skill's examples | Proof outside | Words |
|---|---|---|---|---|---|---|
| `tests-parallel` | perf | 0 / 3.5 | 1 / 4 | 1 / 1 | 0.775 / 1 | 186 / 305 |
| `cs-stubs-in-process` | perf | 2.5 / 6 | 0 / 8.5 | 0 / 2.5 | 0.625 / 0.55 | 179 / 319 |
| `check-workers-share` | perf | 0 / 4.5 | 1 / 8 | 1 / 4.5 | 1 / 0.8825 | 303 / 457.5 |
| `cs-runner-workers` | analysis | 1 / 5 | 0 / 7 | 0 / 3.5 | 0.625 / 0.5625 | 240 / 346 |
| `rs-parallel-reviews` | research | 0 / 4.5 | 0 / 5.5 | 0 / 2.5 | 0.343 / 0.45 | 250 / 403 |
| `rs-load-limit` | perf | 1.5 / 3.5 | 0 / 6 | 0 / 5 | 0.4165 / 0.569 | 340 / 514 |
| `hj-home-gauge` | outcome | 0 / 4.5 | 0 / 2.5 | 0 / 1.5 | 0.5835 / 0.47 | 131.5 / 311.5 |
| `jv-usage` | outcome | 0.5 / 3 | 0 / 2 | 0 / 1 | 0.2 / 0.25 | 223.5 / 410.5 |
| `jstack-leak-zero` | outcome | 0.5 / 2.5 | 0 / 1 | 0 / 1 | 0.6785 / 0.5635 | 376 / 379.5 |
| `ci-hosted-green` | analysis | 2 / 2.5 | 0 / 3.5 | 0 / 2 | 0.9 / 0.875 | 265.5 / 487.5 |

## Each measure over the cases

| Measure | Plain, mean | Deeper, mean | Deeper wins | Ties | Deeper loses | Sign test p | Spread of trials, plain / deeper |
|---|---|---|---|---|---|---|---|
| raw | 0.80 | 3.95 | 10 | 0 | 0 | 0.002 | 0.80 / 1.10 |
| instruments | 0.20 | 4.80 | 10 | 0 | 0 | 0.002 | 0.00 / 1.00 |
| outside | 0.61 | 0.62 | 4 | 0 | 6 | 0.754 | 0.16 / 0.17 |
| beyond | 0.20 | 2.45 | 9 | 1 | 0 | 0.004 | 0.00 / 0.50 |

**Verdict: /deeper did not win**, by the rule in `README.md`: it wins a measure when it scores higher on more cases than it scores lower, with a sign test under 0.05, and it wins the eval with two of the three measures and a loss on none. Won: raw, instruments. Lost: outside.

## How the shipped briefs turned out

The brief the home actually wrote, scored the same way, and what became of its pull request: findings of its review (errors and warnings, then info), follow-up Results, reruns of a check, and Done when lines its Result said did not hold.

| Case | Merged | Shipped: raw / instruments / outside | Findings | Follow-ups | Reruns | Not held |
|---|---|---|---|---|---|---|
| `tests-parallel` | yes | 0 / 1 / 1 | 2, 6 | 0 | 0 | 1 |
| `cs-stubs-in-process` | yes | 3 / 3 / 1 | 1, 5 | 0 | 0 | 1 |
| `check-workers-share` | yes | 0 / 0 / 1 | 1, 2 | 0 | 0 | 0 |
| `cs-runner-workers` | yes | 0 / 1 / 1 | 0, 4 | 0 | 0 | 2 |
| `rs-parallel-reviews` | yes | 0 / 0 / 0.143 | 2, 2 | 0 | 0 | 1 |
| `rs-load-limit` | yes | 2 / 2 / 0.286 | 2, 3 | 0 | 0 | 0 |
| `hj-home-gauge` | yes | 1 / 0 / 1 | 3, 4 | 0 | 0 | 1 |
| `jv-usage` | yes | 1 / 0 / 0.833 | 5, 10 | 0 | 0 | 0 |
| `jstack-leak-zero` | yes | 0 / 0 / 0.833 | 7, 1 | 0 | 0 | 3 |
| `ci-hosted-green` | yes | 2 / 1 / 1 | 7, 2 | 1 | 1 | 3 |
