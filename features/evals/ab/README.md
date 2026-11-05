# The A/B harness

Does revision B do the same work better, worse, or no differently from revision A?
`ab.py` runs both on one task set, interleaved and scored blind, and prints a verdict per family with the interval behind it, so a reader sees how small a change the run could have shown.

```sh
uv run python features/evals/ab/ab.py run --a main --b HEAD --tasks <task file>
uv run python features/evals/ab/ab.py run --a main --b HEAD --tasks features/evals/ab/tasks/replay.json --kind replay
uv run python features/evals/ab/ab.py rescore <run dir> [--out results.md]
```

`run` reads A and B from the git repository of the current directory, and writes its run to `--out`, by default `$TMPDIR/ab-<kind>-<a>-<b>-seed<seed>`.
`rescore` reports a kept run again and calls no model.

## The kinds

- **`prompt`**: each task is one `claude -p` call with no tools, at `--model` (default `claude-opus-5-5`) and `--effort` (default `medium`).
  Each task runs `--trials` times (default 3) in each of three arms: **A**, **A-again** (the same prompts at A, which is the noise floor) and **B**.
  A task's files are read from each revision with `git show`, never from the working tree.
- **`replay`**: `features/evals/benchmark/replay.sh` of this checkout, once per arm, each arm in a `git worktree` of its own that is removed after.
  The events stay this checkout's; the sandbox (`launch.sh`, the stand-ins) and the `jbus` and `jmerge` that decide are the arm's own.
  No model runs and no `claude` is needed on PATH: the today side is deterministic, so one run per arm is the whole answer, and the result is a diff of decisions, not a statistic.
  Two replays of one checkout differ only in the sandbox's directory, the time of day and the commits the sandbox makes at launch, so those three are made the same before the diff, and nothing else is.

## A task file

A JSON file.
For `prompt`:

```json
{
  "families": {
    "steps": {"kind": "pass/fail"},
    "lead": {"kind": "graded", "mde": 0.05, "score": ["python3", "score.py"]}
  },
  "tasks": [
    {"id": "crew-stale-base", "family": "steps", "files": ["features/crew/SKILL.md"],
     "prompt": "The state ... What do you do next?", "must": ["git rebase", "origin/main"]}
  ]
}
```

- A family is `pass/fail` or `graded`, and may name its `mde`, the smallest mean difference the rule calls: by default 0.03 for a graded family and 1/9 (one failed trial in nine) for a pass/fail one.
- A `pass/fail` task names `must`, regular expressions that must all match the answer for it to score 1.
- A `graded` family names `score`, a command run in the task file's directory with the answer on stdin and the task as JSON in `AB_TASK`, which prints a number from 0 to 1.
- `files` are put before the `prompt`, each as `<file path="...">`, as they are at the arm's revision.

For `replay`, `{"events": ["plain", "conflict", ...]}`, the events `replay.sh` knows; `tasks/replay.json` names all seven.

## Fair by construction

The model has no seed (`claude -p` has no seed or temperature flag), so fairness comes from the inputs, the order and the scorer, not from replaying a draw.

- **Same inputs**: A and A-again send the same bytes; B differs only by the files that differ between the revisions.
- **Interleaved**: every job of every arm is shuffled together by `random.Random(seed)`, so no arm runs in a block while the service or the login changes under it.
- **Blind**: each answer is kept under an id; only `key.json` says which arm and trial wrote it.
  The scorer gets the answer and its task, never the arm.
  The ids are drawn from the seed too, so code that has `run.json` can rebuild the key: the blindness is against the scorer, not against a reader.
- **Resumable**: each answer is appended to `answers.jsonl` as it comes, and a failed call to `errors.jsonl`.
  A run with failures ends with exit 1; the same command again asks only for what is missing, so a failed call costs only itself.
  A run directory holding another run (its `run.json` differs) is refused.

## The rule

Fixed before any run of this harness.
For each family, a task's score in an arm is the mean of its trials.
Over the tasks, paired by task: the mean difference B minus A and its 95% interval, from 10,000 bootstrap resamples of the tasks seeded from `--seed`, at the 2.5th and 97.5th percentiles; the same for A-again minus A.
For a pass/fail family the test is Fisher's exact test on failed against all trials, B against A and A-again against A, since a bootstrap over tasks that all tie is degenerate.

- **`inconclusive: A/A not clean`** when A-again against A would itself be called: its interval excludes 0 (Fisher p under 0.05 for pass/fail) and its mean is at least the mde.
- **`B better`** or **`B worse`** when B against A shows a difference by the same test and its mean difference is at least the mde.
- Else **`no measurable difference`**.

An A/A interval that excludes 0 by less than the mde is printed as `excludes 0 below the mde` and does not void the run.
A 95% interval excludes 0 about one time in twenty with no change at all: one lead A/A of the fifteen kept skill-cut runs did (`run-crew-scout-priming-2`, lead, -0.018 [-0.034, -0.002]).

## Reading `results.md`

Each family has a table of its tasks, each arm the mean of the task's trials, then its verdict line, as `run` and `rescore` print it:

```
lead: no measurable difference; B - A -0.004 [-0.027, +0.021]; A/A -0.001 [-0.028, +0.023]; mde 0.030; 17 tasks, 51 runs an arm; errors A 0, A-again 0, B 0; cost A $1.20 ..., A-again ..., B ...
```

- `B - A` is the mean of the per-task differences and its interval; `A/A` the same for A-again minus A.
- `no measurable difference` with the interval [-0.027, +0.021] says this run could not have shown a change smaller than about 0.02 either way, not that there is none.
- A pass/fail family adds its failed trials per arm and the two Fisher p values.
- `errors` counts the calls that failed, retried or not, per arm; `cost` sums `total_cost_usd` and the tokens of `usage` per arm.
  A kept skill-cut run recorded neither, and says so.

`run.json` records the seed, both revisions as given and resolved, the task file's path and sha256, the model, the effort and the trials.
The same task file, revisions and seed give the same `jobs.json` (the call order), the same `key.json` and, with the same answers, the same `results.md`, byte for byte.

## Rescoring a skill-cut run

`rescore features/evals/evals/skill-cut/run-<name>` reads a kept skill-cut run's `key.json` and `scores.json` as its `score.py` wrote them: base is A, base again is A-again and the variant is B; `lead` is graded and `steps` pass/fail.
It writes nothing into the run.
Skill-cut's own rule, in its `README.md`, stays the verdict of those runs; this interval is a reading beside it.

## Limits

- Fisher's test counts every trial as independent, so one task that fails in all its trials weighs as much as three tasks failing once.
- The default pass/fail mde of 1/9 is coarse at a ceiling: in `run-crew-scout-priming` B failed 0 of 126 steps trials against A's 7 (Fisher p 0.014), a change of 0.056 in pass rate, which this rule does not call.
  A family that cares about smaller moves names a smaller `mde`.
- Twenty tasks or fewer give wide intervals: on the skill-cut lead family the 95% half-width is about 0.015 to 0.035.
