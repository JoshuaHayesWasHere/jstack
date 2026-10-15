# /deeper eval: results

Written by `uv run python evals/deeper/eval.py`. Do not edit by hand.

Writer: `claude-opus-5-5` at `medium` effort, no tools. Trials: 2 a case and arm. Template: `templates/brief.md` at sha256 `e2d7213b0af3`. Skill: `skills/deeper/SKILL.md` at sha256 `c00c53750a25`.

## Each case, the mean of its trials (plain / deeper)

| Case | Kind | Raw sources | Instruments | Beyond the skill's examples | Proof outside | Words |
|---|---|---|---|---|---|---|
| `tests-parallel` | perf | 0.5 / 4 | 1 / 4.5 | 1 / 2 | 0.6 / 1 | 194.5 / 298.5 |
| `cs-stubs-in-process` | perf | 2 / 5.5 | 1 / 7.5 | 0 / 1.5 | 0.675 / 0.8665 | 216.5 / 377.5 |
| `check-workers-share` | perf | 0 / 3.5 | 0.5 / 9 | 0.5 / 5 | 0.9 / 0.762 | 304 / 418 |
| `cs-runner-workers` | analysis | 1.5 / 5.5 | 0 / 6 | 0 / 3 | 0.625 / 0.9285 | 217 / 411 |
| `rs-parallel-reviews` | research | 0 / 4.5 | 0 / 5.5 | 0 / 3 | 0.2665 / 0.443 | 228.5 / 474.5 |
| `rs-load-limit` | perf | 1 / 4.5 | 0 / 5.5 | 0 / 4.5 | 0.2665 / 0.5225 | 324 / 477.5 |
| `hj-home-gauge` | outcome | 0 / 4 | 0 / 3.5 | 0 / 2 | 0.5335 / 0.714 | 169.5 / 542.5 |
| `jv-usage` | outcome | 0.5 / 2 | 0 / 2 | 0 / 1 | 0.225 / 0.625 | 176.5 / 245.5 |
| `jstack-leak-zero` | outcome | 1 / 2.5 | 0 / 1 | 0 / 1 | 0.618 / 0.755 | 397.5 / 482.5 |
| `ci-hosted-green` | analysis | 0 / 3 | 0 / 3 | 0 / 2.5 | 1 / 0.875 | 223.5 / 426.5 |

## Each measure over the cases

| Measure | Plain, mean | Deeper, mean | Deeper wins | Ties | Deeper loses | Sign test p | Spread of trials, plain / deeper |
|---|---|---|---|---|---|---|---|
| raw | 0.65 | 3.90 | 10 | 0 | 0 | 0.002 | 0.30 / 1.40 |
| instruments | 0.25 | 4.75 | 10 | 0 | 0 | 0.002 | 0.10 / 0.90 |
| outside | 0.57 | 0.75 | 8 | 0 | 2 | 0.109 | 0.21 / 0.19 |
| beyond | 0.15 | 2.55 | 10 | 0 | 0 | 0.002 | 0.10 / 0.50 |

**Verdict: /deeper won**, by the rule in `README.md`: it wins a measure when it scores higher on more cases than it scores lower, with a sign test under 0.05, and it wins the eval with two of the three measures and a loss on none. Won: raw, instruments. Lost: none.

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
