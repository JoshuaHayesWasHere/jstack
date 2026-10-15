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

See `results.md` for the numbers, and the verdict line in it.
