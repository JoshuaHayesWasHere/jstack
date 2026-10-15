# The /deeper eval

Does a brief written through `/deeper` (`skills/deeper/SKILL.md`) ask for deeper work than one written without it? This eval is the merge gate of the skill: it ran before the skill merged, and its results are committed here.

## What it does

Ten briefs the jstack home wrote and shipped, each for research, perf, analysis or outcome work, and each with a pull request:

| Case | Kind |
|---|---|
| `tests-parallel` | perf |
| `cs-stubs-in-process` | perf |
| `check-workers-share` | perf |
| `cs-runner-workers` | analysis |
| `rs-parallel-reviews` | research |
| `rs-load-limit` | perf |
| `hj-home-gauge` | outcome |
| `jv-usage` | outcome |
| `jstack-leak-zero` | outcome |
| `ci-hosted-green` | analysis |

For each, the request is the brief's `Task:` line, with the private patterns of `jleak` taken out (`cases/<slug>.md`). Each request goes through brief writing twice, the same number of times each way:

- **plain**: the writer gets the brief template and the request.
- **deeper**: `/deeper` is run on the request first, and the writer gets the same template and the prompt `/deeper` rewrote (`deeper/<slug>-<trial>.md` keeps what it said).

The writer is the same model, effort and prompt in both arms, with no tools, so the only difference is the prompt it writes from.

## Blind scoring

Each run is its own directory, `run-<n>/`. Each brief is saved as `run-<n>/runs/<random id>.md`, and which arm wrote it is only in `run-<n>/key.json`. `score.py` scores the files in `runs/` from their text alone: it never sees the key or the file name, and it is a script, not a model, so it is neither the writing agent nor another model judging it. Its lexicons were committed before the first brief was written. It scores three things:

- **raw**: how many kinds of raw material the brief names (logs, transcripts, traces, a profile, a database, the machine's counters, per-test timings, the event log, CI runs, git history, raw data, samples);
- **instruments**: how many named instruments it asks for (`py-spy`, `perf stat`, `hyperfine`, `pytest --durations`, `pidstat`, `gh run`, `git bisect`, `sqlite3`, and the rest of `INSTRUMENTS`). The report also gives **beyond**: the same count without the seven instruments the skill names as its own examples, so a brief that only copies them is seen doing it;
- **outside**: the share of its proof lines (`Done when:` items, and `Proves it:` where there is one) that name a judge outside the agent (a command, a test, a measured number, CI, a dataset, the user's check) and do not rest on a review or a self-report.

Beside the three measures, each run's `results.md` gives three readings of them that the rule does not count, added after the first two runs: **raw_beyond**, the raw count without the seven kinds the skill lists as its examples (logs, transcripts, traces, a profile, the database, CI runs, the machine's counters); **beyond**, the same for instruments; and **outside_no_code**, the outside share without its first branch, which takes any span in backticks as a judge, so a line that only names a path counts. They rescore the committed briefs, with no model call: `uv run python evals/deeper/eval.py --run run-1` and `--run run-2`.

`report` joins the scores to the key. Then, for each case, the brief as it shipped is scored the same way, beside how its pull request turned out: merged or not, the findings of its review, follow-up Results, reruns of a check, and Done when lines that did not hold.

## The rule for a win

Fixed before the first run, and not changed after it. For each of the three measures, a case's score is the mean of its trials. `/deeper` wins a measure when it scores higher than plain on more cases than it scores lower, with a two-sided sign test (ties left out) under 0.05. It wins the eval when it wins two of the three measures and scores lower on none. Losing a measure is scoring lower on more cases than higher. If it does not win, that is the finding: the eval is not tuned until it does.

## Run it

From the root of the repo:

```sh
uv run python evals/deeper/eval.py
```

It runs `cases`, `write`, `score` and `report` in order. `write` calls `claude -p` 60 times (ten cases, two trials, one call for plain and two for deeper), four at a time, and adds the next run, `run-<n>/`, in one rename once every brief and the key are written: a failed call leaves nothing, and no kept run is touched. It stops first when there is no `claude` or no private patterns for `jleak`. `cases` reads the home's `tasks/` on this machine and asks GitHub how each pull request ended. On a machine without them, `uv run python evals/deeper/eval.py --run run-2` rescores and reports a kept run, and refuses to write one.

## Limits

- One writer model, two trials a case: the spread across trials is in each run's `results.md`, and a gap smaller than it is noise.
- A lexicon counts words, not whether a source or a tool is the right one for the task. A brief that names more is not proven to be a better one; `beyond` and the word counts in each run's `results.md` show how much of a gap is the skill's examples and length.
- The writer has no tools, in both arms: the briefs are written from the request alone, as the first draft of a home is.

## Result

Two runs, both of 2026-10-15, scored by the same script under the same rule. Each run's numbers are in `run-1/results.md` and `run-2/results.md`. They differ in two places of the skill text that `/deeper` reads (`git diff fbb2892 7a0815c -- skills/deeper/SKILL.md`): the form it is told to print its rewritten prompt in (a nested fence in run 1, which the repo's fence finder skips, and a block quote in run 2), and the shell block of "Run by a home", which now says when jbus cannot take the gate. Neither touches the four questions, so they are two runs of the same questions. **On raw sources and instruments, `/deeper` won in both runs. Proof outside the agent is not shown either way. The rule's no-loss condition held in one run of the two, so the eval as a whole does not show a win on all it set out to.**

| Measure | Run 1: mean plain to deeper, cases up / down, p | Run 2: the same |
|---|---|---|
| Raw sources | 0.80 to 3.95, 10 / 0, 0.002 | 0.65 to 3.90, 10 / 0, 0.002 |
| Instruments | 0.20 to 4.80, 10 / 0, 0.002 | 0.25 to 4.75, 10 / 0, 0.002 |
| Proof outside the agent | 0.61 to 0.62, 4 / 6, 0.754 | 0.57 to 0.75, 8 / 2, 0.109 |
| Verdict of the run, by the rule | did not win: proof outside lost | won: no measure lost |
| Reading: raw beyond the skill's examples | 0.20 to 1.50, 8 / 0, 0.008 | 0.20 to 1.40, 9 / 0, 0.004 |
| Reading: instruments beyond the skill's examples | 0.20 to 2.45, 9 / 0, 0.004 | 0.15 to 2.55, 10 / 0, 0.002 |
| Reading: proof outside, no inline code | 0.39 to 0.33, 3 / 7, 0.344 | 0.36 to 0.38, 6 / 4, 0.754 |

- **What holds:** `/deeper` makes a brief name its raw material and an expert's instruments, on every case of both runs. The gain stands when the skill's own examples are taken out, for raw material as well as for instruments.
- **What does not hold:** that it moves the proof outside the agent. That measure went down in run 1 and up in run 2, neither under 0.05. Without inline code the rise of run 2 is gone (0.36 to 0.38): what rose was lines naming a path or a command in backticks, which the measure, fixed before the run, counts as a judge. So the measure is weaker than its name, and nothing here ties a change in it to a `Proves it:` line.
- **How the shipped briefs turned out:** all ten pull requests merged. The shipped briefs scored like the plain arm (raw 0.9 and instruments 0.8 on the mean), and their reviews raised 30 errors and warnings over the ten. Seven of the ten have a Result that says at least once that a line does or did not hold. Ten cases are too few, and those outcomes too unlike the three measures, to tie a review finding to a missing source or instrument.
