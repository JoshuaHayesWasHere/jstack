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

Each brief is saved as `runs/<random id>.md`, and which arm wrote it is only in `key.json`. `score.py` scores the files in `runs/` from their text alone: it never sees the key or the file name, and it is a script, not a model, so it is neither the writing agent nor another model judging it. Its lexicons were committed before the first brief was written. It scores three things:

- **raw**: how many kinds of raw material the brief names (logs, transcripts, traces, a profile, a database, the machine's counters, per-test timings, the event log, CI runs, git history, raw data, samples);
- **instruments**: how many named instruments it asks for (`py-spy`, `perf stat`, `hyperfine`, `pytest --durations`, `pidstat`, `gh run`, `git bisect`, `sqlite3`, and the rest of `INSTRUMENTS`). The report also gives **beyond**: the same count without the seven instruments the skill names as its own examples, so a brief that only copies them is seen doing it;
- **outside**: the share of its proof lines (`Done when:` items, and `Proves it:` where there is one) that name a judge outside the agent (a command, a test, a measured number, CI, a dataset, the user's check) and do not rest on a review or a self-report.

`report` joins the scores to the key. Then, for each case, the brief as it shipped is scored the same way, beside how its pull request turned out: merged or not, the findings of its review, follow-up Results, reruns of a check, and Done when lines that did not hold.

## The rule for a win

Fixed before the first run, and not changed after it. For each of the three measures, a case's score is the mean of its trials. `/deeper` wins a measure when it scores higher than plain on more cases than it scores lower, with a two-sided sign test (ties left out) under 0.05. It wins the eval when it wins two of the three measures and scores lower on none. Losing a measure is scoring lower on more cases than higher. If it does not win, that is the finding: the eval is not tuned until it does.

## Run it

From the root of the repo:

```sh
uv run python evals/deeper/eval.py
```

It runs `cases`, `write`, `score` and `report` in order. `write` calls `claude -p` 60 times (ten cases, two trials, one call for plain and two for deeper), four at a time. `cases` reads the home's `tasks/` on this machine and asks GitHub how each pull request ended. On a machine without them, `uv run python evals/deeper/eval.py score report` rescores the committed briefs.

## Limits

- One writer model, two trials a case: the spread across trials is in `results.md`, and a gap smaller than it is noise.
- A lexicon counts words, not whether a source or a tool is the right one for the task. A brief that names more is not proven to be a better one; `beyond` and the word counts in `results.md` show how much of a gap is the skill's examples and length.
- The writer has no tools, in both arms: the briefs are written from the request alone, as the first draft of a home is.

## Result

Two runs, both of 2026-10-15, scored by the same script under the same rule. **Run 2, on the skill as it merges, won. Run 1, on an earlier form of the skill, did not.** Only what the two runs agree on is a finding.

| Measure | Run 1: mean plain to deeper, cases up / down, p | Run 2: the same |
|---|---|---|
| Raw sources | 0.80 to 3.95, 10 / 0, 0.002 | 0.65 to 3.90, 10 / 0, 0.002 |
| Instruments | 0.20 to 4.80, 10 / 0, 0.002 | 0.25 to 4.75, 10 / 0, 0.002 |
| Instruments beyond the skill's examples | 0.20 to 2.45, 9 / 0, 0.004 | 0.15 to 2.55, 10 / 0, 0.002 |
| Proof outside the agent | 0.61 to 0.62, 4 / 6, 0.754 | 0.57 to 0.75, 8 / 2, 0.109 |
| Verdict | did not win: proof outside lost | won: raw and instruments, no measure lost |

- Run 1 is in `run-1/`. Its `/deeper` printed the rewritten prompt in a nested fence, which the repo's fence finder skips, so the skill was changed to print it as a block quote and the eval was run again on that text. Nothing in the scorer, the cases or the rule changed between the runs: they are in the commit before run 1.
- **What holds:** `/deeper` makes a brief name its raw material and an expert's instruments, on every case of both runs, and not only by copying the skill's own examples.
- **What does not hold:** whether it moves the share of the proof that sits outside the agent. It went down in run 1 and up in run 2, and neither sign test is under 0.05. Read it as no effect shown. A brief through `/deeper` is about 1.5 to 2 times as long, with more `Done when:` items, and not every extra item is a check a script reads as an outside judge. The planned `Proves it:` line in the template (the deeper-proves-it brief) is aimed at that gap.
- **How the shipped briefs turned out:** all ten pull requests merged. The shipped briefs scored like the plain arm (raw 0.9 and instruments 0.8 on the mean), and their reviews raised 30 errors and warnings over the ten. Seven of the ten had a `Done when` line their Result said did not hold at first. Ten cases are too few, and those outcomes too unlike the three measures, to tie a finding to a missing source or instrument.
