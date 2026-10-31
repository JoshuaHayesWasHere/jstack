# The evals

An eval scores a skill's answers against a key, blind, under `features/evals/evals/`: the skill-cut eval, rerunnable on any branch, and the retired eval of the depth questions, kept read-only as a record of its two runs.
The coordinating benchmark, under `features/evals/benchmark/`, measures what jstack's coordinating layer costs from the raw records and from a replay in a sandbox.

Paths:
- `features/evals/`
Tests: none

## Sub-features

- `benchmark-records` totals tokens, events, holds, churn and the skills' sh blocks from what is on disk, with no model.
- `benchmark-upkeep` prints each duty's fix share and cost from the same records, and with `--against` each duty's change since an earlier run.
- `benchmark-replay` decides each seeded event with today's `jbus` and `jmerge`, with no model, and runs setup B only with `--spend`.
- `benchmark-home-start` runs `/home` at a commit only with `--spend`.

The skill-cut eval and the eval of the depth questions are not driven yet.

## How to get to it (user POV)

- Run `uv run --script features/evals/benchmark/records.py --before <commit> --after <commit>`, with `--against features/evals/benchmark/baseline-2026-10-30.json` for the change against the kept baseline.
- Run `features/evals/benchmark/replay.sh "$PWD" <out dir>`.
- Run `features/evals/benchmark/home-start.sh "$PWD" <out dir> <label> <commit>`.

`features/evals/benchmark/README.md` says what each prints.

## Driving it with verify-jstack

Needs: `home`, `demo`, `config`, `tasks`, `t3/threads.json`, `gh/open.json`, `gh/commits.json`, `gh/checks.json`, `gh/logs`

The replay makes its own sandbox for each run of each event, so it is run from a shell that has sourced no `env.sh`, and needs none of its own.

### The replay's today side says main is red

- **Run the event.**
  Run `features/evals/benchmark/replay.sh "$PWD" /tmp/replay --runs 1 --events redmain`.
  It prints the limits ledger, then `today: redmain, run 1, <n> ms, expect held 7 (main red)`, then `wait 7 https://example.test/pull/7: main is red at <sha12>, its fix merges first`, then the ledger again.
- **Check that no model ran.**
  `/tmp/replay/today.jsonl` has `"tokens":0`, and there is no `/tmp/replay/b.jsonl`.
- **Proof.**
  Keep `/tmp/replay/redmain.1.today.txt` and `/tmp/replay/redmain.1.today-gh.log`, which has no `pr merge` line.

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

## Gotchas

- `limit`'s today side is `jbus failover --dry-run` over a recorded failure, which writes nothing, and its `expect` names what setup B should do, so the two can differ: with no instance with headroom in the sandbox's config, it prints `capped ...`.
- `redmain`'s seed must be main's real tip, since jbus reads it from `git ls-remote`: a seed at any other commit gives `ready 7`.
