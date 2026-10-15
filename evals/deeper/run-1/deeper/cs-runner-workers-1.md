## 1. What a top professional would do
A CI/build performance engineer. They would split `make check` into per-target and per-test wall times and find the critical path before naming a cause. Then they would reproduce the GitHub runner's limits on this machine (its vCPU count, its RAM, cold caches, no network warmup) and predict each step's time on the runner *before* the flip, so the flip tests the explanation instead of only revealing it.

## 2. The rawest material
- `Makefile` and every file it includes, plus `make -n check` and `make --trace check 2>&1 | ts -s`: in place of a remembered sense of "what check runs"
- `gh run list --workflow <ci workflow> -L 20` and `gh run view <id> --log` / `gh run view <id> --json jobs` (step start and end times) for recent CI runs: in place of the badge's single total or a "CI felt slow" note
- `nproc`, `free -g`, `lscpu`, `df -h` on this machine, set against the runner spec GitHub publishes for the label the workflow will use (for example `ubuntu-latest`: 4 vCPU/16 GB for public repos, 2 vCPU/7 GB for private): in place of "the runners are slower"
- The workflow file under `.github/workflows/`, especially its `actions/cache` keys, `setup-*` steps, and any `-j`/`-n` flags: in place of an assumption that CI runs the same command as local
- `pytest --durations=0 -q` output (or the equivalent for the repo's test runner) on a cold and a warm run: in place of a guess at which tests are slow

## 3. The methods and tools
- `hyperfine --runs 10 --prepare 'make clean' 'make check'` (and a warm variant without `--prepare`): a run count and a spread for every number, never one timing
- `make --trace check` piped through `ts -s` (moreutils), or `remake --profile check` if `remake` is installed (`pacman -S remake`): per-target wall time and the critical path
- `pytest --durations=25` and `pytest -n auto` (pytest-xdist) at 2 and 4 workers: which tests dominate, and how they scale with the core count the runner has
- `/usr/bin/time -v make check`, `perf stat -e task-clock,context-switches,cpu-migrations make check`, `pidstat -u -d -r 1`: CPU-bound, IO-bound or waiting, as measured rather than inferred
- `systemd-run --user --scope -p AllowedCPUs=0-3 -p MemoryMax=16G make check` (or `docker run --cpus=4 --memory=16g` on a fresh `ubuntu:24.04` with empty caches, or `act` for the workflow itself): reproduce the runner's limits locally, so a cause is shown and not argued
- `git bisect run` with a timing threshold script, if the slowdown has an onset in history: a bisect over a guess

## 4. What outside the agent shows it is right
- A written prediction, made before the flip, of each CI step's wall time on the GitHub runner, checked against `gh run view <id> --json jobs` for a real run of the same commit: each of the dominant steps within 15% of the prediction. A miss means the explanation is wrong, not the runner.
- `hyperfine` on this machine at the runner's limits (cores, memory, cold cache) gives a median and a spread that put the GitHub run's total inside its range.
- The user's own check: they read the per-step table and the stated cause for each slow step, and agree that it accounts for the time.

## Rewritten prompt
```
"figure out what is slowing down make check and why", and specifically what changes when CI
flips to GitHub's hosted runners.

Start from the raw material, not from summaries: the Makefile and `make -n check`;
`make --trace check | ts -s` for per-target wall time; `pytest --durations=0` cold and warm;
the workflow file in .github/workflows/ (cache keys, setup steps, -j/-n flags); recent runs via
`gh run view <id> --json jobs` for step timings; and this machine's `nproc`, `free -g` and `lscpu`
next to GitHub's published spec for the runner label the workflow will use.

Measure with instruments, never a single timing: `hyperfine --runs 10` (cold with
`--prepare 'make clean'`, and warm), `/usr/bin/time -v`, `perf stat`, and `pidstat -u -d -r 1`
to say whether each slow step is CPU-bound, IO-bound or waiting on the network. Reproduce the
runner here before the flip: `systemd-run --user --scope -p AllowedCPUs=<runner vCPUs>
-p MemoryMax=<runner RAM>` or a fresh `docker run --cpus/--memory` container with empty caches.
Check how the slow steps scale with core count (`pytest -n 2` vs `-n 4`, `make -j`). If the
slowdown has an onset in history, `git bisect run` it with a timing threshold.

Deliver a table of the dominant steps: local warm time, local time at the runner's limits, the
predicted GitHub-runner time, and the cause of each, with the measurement that shows it.

Done when: the predictions are written down before a GitHub run of the same commit, and that
run's step timings (`gh run view --json jobs`) fall within 15% of them for every dominant step;
the hyperfine range at the runner's limits contains the real run's total; and I have read the
table and agree that it accounts for the time. Do not change the Makefile or the workflow as part
of this; ask me before triggering any CI run.
```
