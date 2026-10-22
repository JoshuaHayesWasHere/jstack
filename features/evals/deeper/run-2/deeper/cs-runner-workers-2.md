## 1. What a top professional would do
A CI and build performance engineer would not compare two total times. They would run the same commit in both places, split `make check` into its targets and test files, and give each one a time on each machine. Then they would trace every gap to one named cause: core count and `-j`, disk I/O, a cold cache (no ccache, pip or npm cache, or Docker layers), network fetches, or memory pressure. They would also predict the GitHub number from a local emulation of the runner before trusting any single run.

## 2. The rawest material
- `Makefile` and every file it includes (`grep -n 'check' Makefile`), plus `.github/workflows/*.yml`: in place of a remembered idea of what `make check` runs and how the workflow calls it
- The current CI's own job logs with timestamps (`gh run view <id> --log`, or the self-hosted runner's `_diag/` and job logs): in place of the dashboard's total duration
- GitHub's per-step timing for the last runs on its hosted runners: `gh run list --workflow <file> --json databaseId,createdAt,updatedAt,conclusion -L 20`, then `gh api repos/{owner}/{repo}/actions/runs/<id>/jobs`: in place of "it feels slower on GitHub"
- The runner's own hardware, printed inside the job (`nproc; free -m; df -h; lscpu; cat /proc/pressure/io`) and set beside the same output from the current machine: in place of assumed runner specs
- The per-test durations the test runner itself writes (`pytest --durations=0 -q`, `go test -json`, or `ctest --output-junit`): in place of a summary of which tests are slow

## 3. The methods and tools
- `hyperfine --runs 10 --prepare 'make clean' 'make check'`: gives a mean and a spread for every number, never a single run (on Arch, `pacman -S hyperfine` if it is missing)
- `make check --trace` (or `remake --profile`) with `ts '%.s'` from moreutils: gives each target its time, so the gaps can be attributed per target
- `taskset -c 0-3` (or `0-1`, matching the runner's `nproc`), `systemd-run --scope -p MemoryMax=16G`, and a run with every cache emptied: emulate the GitHub runner locally to produce a prediction before checking it on the real thing
- `pidstat -u -d -r 1` and `/usr/bin/time -v` during the run: show whether a slow target is bound by CPU, I/O, memory or waiting on something
- Timestamped `echo` steps or `actions/cache` hit/miss lines added to the workflow on a branch, triggered with `gh workflow run <file> --ref <branch>` (ask the user before pushing): the measurement taken on the real runner

## 4. What outside the agent shows it is right
- A table of the time per target and per slowest test, on the current CI and on GitHub's runner, from at least 5 runs each with spreads, in which named causes account for ≥90% of the wall-clock difference. Explaining 90% is a reasonable target for this field, not a stretch.
- The local emulation's predicted GitHub time for each target, checked against real GitHub runs, landing within 15%. A prediction that misses means a cause is missing.

## Rewritten prompt
> "Figure out what is slowing down make check and why", the part that asks what changes at the flip to
> GitHub's runners. Start from the raw material: the `Makefile` and `.github/workflows/*.yml`, the current
> CI's job logs (`gh run view <id> --log`), GitHub's per-step timings from
> `gh api repos/{owner}/{repo}/actions/runs/<id>/jobs`, `nproc; free -m; lscpu; df -h` printed inside a job
> on each runner, and the test runner's own per-test durations (`pytest --durations=0` or the equivalent).
> Don't start from dashboard totals or remembered numbers. Time `make check` per target with
> `make check --trace | ts '%.s'`, and use `hyperfine --runs 10 --prepare 'make clean'` for every number.
> Emulate the GitHub runner locally with `taskset` set to its core count, `systemd-run -p MemoryMax=`, and
> empty caches. Use `pidstat -u -d -r 1` to say whether each slow target is waiting on CPU, I/O, memory,
> the network, or a cache miss. Write down, per target, the GitHub time this predicts. Then check it on
> real GitHub runners with at least 5 runs from a branch, using `gh workflow run` (ask me before pushing).
> Done when a table of per-target times on both runners, with spreads, attributes ≥90% of the difference
> to named causes, and the local prediction lands within 15% of the measured GitHub times.
