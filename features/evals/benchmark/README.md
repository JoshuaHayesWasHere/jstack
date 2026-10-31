# The coordinating benchmark

What does jstack's coordinating layer cost, and does a deterministic jbus and jmerge save anything against a home agent doing the same work by hand?
This folder holds three parts: the records reader, the replay, and the home start run.

The verdict rules are the request's, fixed before any number was read, and they do not change to fit a result.
This folder measures, and the verdicts are read from what it prints.

## The records reader

It reads what is on disk and calls no model, so it costs nothing to run.
Run it from the root of the repo:

```sh
uv run --script features/evals/benchmark/records.py --before 4d6fd232e --after f5d5a84d2 --json /tmp/records.json
```

`--before` and `--after` are the two commits whose skills it compares, here main just before and just after the first skill cuts.
It prints, over `--days` (default 7) and `--churn-days` (default 90):

- Tokens and API-price dollars by session role, and the share per merged task that is coordinating and not doing.
- jbus's events, and launch to merge at p50 and p90.
- The pull requests each kind of hold stopped at least once, from `merge.log`.
- Each module's fix share, flagged `OVER-BUILT` above 0.5.
- The size of the skills' sh blocks at each commit.

Every path comes from `--home` (default `$HOME`), `--project` (default `jstack`) and `--repo` (default this checkout).
A record that is not on disk counts as empty, and stderr names it, as it does a model the prices do not have, which counts as $0.

## The replay

It seeds each event into a verify-jstack sandbox, then runs today's `jbus` and `jmerge` on it and prints what they decide:

```sh
features/evals/benchmark/replay.sh "$PWD" /tmp/replay --runs 1 --events redmain
```

The events are `plain`, `conflict`, `redmain`, `findings`, `limit`, `launch` and `batch`, and all of them run by default.
On `redmain` it prints `wait 7 ...: main is red at <sha12>, its fix merges first`.
On `limit` it prints jbus's own dry run over a recorded usage-limit failure, which writes nothing and moves no thread: today's move is decided, and not made.

Add `--spend` to also run setup B, a home agent with no jbus, on each event.
That spends model usage, and it is the only way this command does.
B's tokens, dollars, turns, wall-clock and what it said go to `b.jsonl` in the out directory.

## The home start run

It runs one `/home` with the skills at a commit, in a sandbox, so two commits can be compared:

```sh
features/evals/benchmark/home-start.sh "$PWD" /tmp/home-start before 4d6fd232e --spend
features/evals/benchmark/home-start.sh "$PWD" /tmp/home-start after f5d5a84d2 --spend
```

With no `--spend` it lays out the commit, prints what it would run, and runs no model.
With `--spend`, each run appends a row to `c.jsonl` in the out directory, and a run that gives no answer appends `"error":true` and exits 1.

## What the two scripts share

- Each prints the limits ledger before and after, from `LIMITS` or `~/.local/state/claude/limits`.
- `--spend` caps each model run at $3, which a run of every event does 14 times by default.
- `--claude-home` names the sign-in a `--spend` run uses, by default `$HOME/.claude`, and `--model` its model.
- Run each from a shell that has sourced no sandbox `env.sh`.

## Limits

- Setup A, T3 Code's features alone, is not replayed: the stand-in serves no watch, schedule, delegate or queue tool.
- A home start here has no T3 Code tools, on either side.
- The events are seeded kinds, not specific past pull requests, and B is handed its rules.
