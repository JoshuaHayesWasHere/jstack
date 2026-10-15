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

Run of 2026-10-15, numbers in `results.md`. **By the rule above, `/deeper` did not win.**

- **Raw sources: won.** Higher on 10 cases of 10 (mean 0.80 to 3.95, sign test p 0.002).
- **Instruments: won.** Higher on 10 of 10 (0.20 to 4.80, p 0.002). Without the skill's seven examples it is still higher on 9 of 10 and tied on 1 (0.20 to 2.45, p 0.004), so the gain is not only copied examples.
- **Proof outside the agent: lost.** Lower on 6 cases of 10 and higher on 4 (0.61 to 0.62 on the mean, p 0.75). A brief through `/deeper` is about 1.5 times as long and has more `Done when:` items, and the extra items (a baseline table, a census, a reproduction) are not all checks a script reads as outside judges. The rule counts a measure scored lower on more cases as lost, so the eval is lost, however small that gap.

The finding: `/deeper` makes a brief name its raw material and its instruments, by a wide margin on every case, and does not move the share of its proof that sits outside the agent. That is the gap the planned `Proves it:` line in the template (the deeper-proves-it brief) is for. The eval is left as it was run: no lexicon, rule or case was changed after the first brief was written (the scorer and this rule are in the commit before the runs).

How the shipped briefs turned out: all ten pull requests merged. The shipped briefs scored like the plain arm (raw 0.9, instruments 0.8 on the mean) and their reviews raised 30 errors and warnings over the ten. Seven of the ten had a `Done when` line the Result said did not hold at first. Ten cases are too few, and the outcome is too unlike the three measures, to tie a review finding to a missing source or instrument.
