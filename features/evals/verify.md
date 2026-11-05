# The evals

An eval scores a skill's answers against a key, blind, under `features/evals/evals/`: the skill-cut eval, rerunnable on any branch, and the retired eval of the depth questions, kept read-only as a record of its two runs.
The coordinating benchmark, under `features/evals/benchmark/`, measures what jstack's coordinating layer costs from the raw records and from a replay in a sandbox.
The lab, under `features/evals/lab/`, reruns the zero-cost measurements against a pinned copy of the telemetry store and writes one dated result directory.

Paths:
- `features/evals/`
Tests: none

## Sub-features

- `benchmark-records` totals tokens, events, holds, churn and the skills' sh blocks from what is on disk, with no model.
- `benchmark-upkeep` prints each duty's fix share and cost from the same records, and with `--against` each duty's change since an earlier run.
- `benchmark-replay` decides each seeded event with today's `jbus` and `jmerge`, with no model, and runs setup B only with `--spend`.
- `benchmark-home-start` runs `/home` at a commit only with `--spend`.
- `lab` copies the telemetry store, then runs the KPI backtest, the steps' shift tests, the A/B power, the records reader and the replay on that copy, with no model and no `--spend`.
- `ab` compares two revisions on one task set: the `prompt` kind asks `claude -p` in arms A, A-again and B, interleaved and scored blind, and prints a verdict per family with its interval; the `replay` kind runs the replay's today side once per arm, each in its own worktree, and diffs every event's decision; `rescore` reports a kept run, a skill-cut one too, with no model.

The skill-cut eval and the eval of the depth questions are not driven yet.

## How to get to it (user POV)

- Run `uv run --script features/evals/benchmark/records.py --before <commit> --after <commit>`, with `--against features/evals/benchmark/baseline-2026-10-30.json` for the change against the kept baseline.
- Run `features/evals/benchmark/replay.sh "$PWD" <out dir>`.
- Run `features/evals/benchmark/home-start.sh "$PWD" <out dir> <label> <commit>`.
- Run `uv run --script features/evals/lab/lab.py --fit <first day>..<cutoff> --week <Sunday> --end <UTC time> --runs 200`.
  It writes `~/.local/state/home/<repo>/reports/lab/<UTC stamp>-<sha8>/` unless `--out` names a directory: `manifest.json`, a `<stage>.json` and `<stage>.txt` per stage, and `summary.md`, which opens with the KPI table.
  The copy `store.sqlite` is deleted when the run ends, unless `--keep-store`.
- Run `uv run python features/evals/ab/ab.py run --a <rev> --b <rev> --tasks <task file> [--kind replay]`, or `ab.py rescore <run dir>`.

`features/evals/benchmark/README.md` and `features/evals/ab/README.md` say what each prints.

## Driving it with verify-jstack

Needs: `home`, `demo`, `config`, `tasks`, `t3/threads.json`, `gh/open.json`, `gh/commits.json`, `gh/checks.json`, `gh/logs`

The replay makes its own sandbox for each run of each event, so it is run from a shell that has sourced no `env.sh`, and needs none of its own.

### The replay's today side lets a pull request through a red main

- **Run the event.**
  Run `features/evals/benchmark/replay.sh "$PWD" /tmp/replay --runs 1 --events redmain`.
  It prints the limits ledger, then `today: redmain, run 1, <n> ms, expect merged 7 (a red main holds no pull request)`, then `ready 7 <head> beta beta`, then the ledger again.
- **Check that no model ran.**
  `/tmp/replay/today.jsonl` has `"tokens":0`, and there is no `/tmp/replay/b.jsonl`.
- **Proof.**
  Keep `/tmp/replay/redmain.1.today.txt` and `/tmp/replay/redmain.1.today-gh.log`, which has no `pr merge` line, as `jmerge --check` merges nothing.

### The A/B harness's replay kind finds no change between main and main

- **Run the A/A.**
  From a shell with no `claude` on PATH, run `uv run python features/evals/ab/ab.py run --a main --b main --tasks features/evals/ab/tasks/replay.json --kind replay --out /tmp/ab-replay`.
  It prints one line per event, `<event>: same: A <decision> | B <decision>`, then `replay: 0 of 7 events decided differently`.
  Each arm's `/tmp/ab-replay/<arm>/today.jsonl` has `"tokens":0` on every row.
- **Check that each arm had its own worktree and left none.**
  `/tmp/ab-replay/A.log` and `/tmp/ab-replay/B.log` each start with the limits ledger, and `git worktree list` names no `ab-<sha>-A-` or `ab-<sha>-B-` path after.
- **Check that it repeats.**
  The same command with `--out /tmp/ab-replay-2` writes a `results.md` that `cmp` finds the same as `/tmp/ab-replay/results.md`.
- **Proof.**
  Keep `/tmp/ab-replay/results.md` and `/tmp/ab-replay/run.json`, which holds both resolved SHAs and the task file's sha256.

### The upkeep ledger says jbus's share beside the baseline's 0.54

- **Run the reader.**
  Run `uv run --script features/evals/benchmark/records.py --before HEAD --after HEAD --json /tmp/records.json --against features/evals/benchmark/baseline-2026-10-30.json`.
  It ends with `upkeep per duty:` and a row per duty, then `against ...baseline-2026-10-30.json, generated 2026-10-30:` and a row `jbus 0.54 <now> <change> 2425.72 <now> <change>`.
- **Check the JSON.**
  `jq .upkeep.duties.jbus /tmp/records.json` gives the row's totals, and `--against /tmp/records.json` on a second run shows each change as `+0.00` while no commit landed between the runs.
- **Check that no model ran.**
  The reader starts no process but `git`, so the limits ledger does not move for it.
- **Proof.**
  Keep what the first run printed from `upkeep per duty:` on.

### The lab backtests a week on a pinned copy of the store

- **Run the lab.**
  Run `uv run --script features/evals/lab/lab.py --fit 2026-10-11..2026-10-25 --week 2026-10-25 --end 2026-11-03T01:37:48Z --runs 200 --out /tmp/lab-run --keep-store`.
  It prints `store copied from <the live store>`, then each stage as `=== <stage>: exit 0, <s> s` and what the stage printed.
- **Check the copy and the table.**
  `/tmp/lab-run/summary.md` opens with the KPI table: PR open to merge `miss`, blamed on `pairs`, and lead time, change failure rate and merges `hit`.
  The change failure rate's `real` is `sqlite3 /tmp/lab-run/store.sqlite "select 100 * rate from weekly_change_failure where week = '2026-10-25'"`.
- **Check that no model ran.**
  `jq .tokens /tmp/lab-run/replay.json` gives `0`, and `jq .setup_b_ran` gives `false`.
- **Proof.**
  Keep `summary.md` and `manifest.json`.

## Gotchas

- `limit`'s today side is `jbus failover --dry-run` over a recorded failure, which writes nothing, and its `expect` names what setup B should do, so the two can differ: with no instance with headroom in the sandbox's config, it prints `capped ...`.
- `redmain`'s seed must be main's real tip, since jbus reads it from `git ls-remote`: a seed at any other commit gives `ready 7`.
- The lab's days are the machine's local days, as the store's are: run it in the zone the store was built in.
- `records` and `replay` read no store: records reads the transcripts and logs under `--home` from the fit's first day to `--end`, and the replay decides in a sandbox on the wall clock.
  Two runs with the same flags and copy still write the same JSON for every stage: records stops at `--end`, and `replay.json` writes each wall time as `<time>`.
