## 1. What a top professional would do
A CI/build performance engineer would not stop at "what is slow"; they would break `make check` wall time into per-target time on each runner kind and attribute each difference to a named machine property: core count against `-j`, disk, cold caches, network fetches, or a missing toolchain. Before arguing about causes, they would also predict the GitHub-runner time from the self-hosted profile and then check that prediction.

## 2. The rawest material
- `gh run list --workflow <ci workflow> --json databaseId,createdAt,updatedAt,headSha,conclusion --limit 50`, then `gh run view <id> --log` for runs on both the current runners and `ubuntu-latest`: in place of a remembered "CI got slower" or a dashboard average.
- The per-step timestamps inside those logs, and any junit XML the test step writes (e.g. `build/test-results/*.xml`): in place of the job's single total duration.
- `Makefile` and every file it includes (the `check:` target's prerequisites and recipes), and `.github/workflows/*.yml` (`runs-on`, `actions/cache` keys, setup steps): in place of a description of what `make check` does.
- The runner's own counters, captured in a debug step: `nproc`, `lscpu`, `free -m`, `df -h .`, `cat /proc/pressure/{cpu,io}`: in place of the published spec of "a GitHub runner".

## 3. The methods and tools
- `make --trace check 2>&1 | ts -s '%.s'` (`ts` from moreutils), on each runner and locally: a per-recipe timeline, which is a profile before any fix.
- `pytest --durations=0 --junitxml=…` (or the suite's own equivalent) inside the check target: per-test time, so the slow targets can be split down to the slow tests.
- `hyperfine --runs 5 --prepare 'make clean' 'make -j1 check' 'make -j2 check' 'make -j$(nproc) check'` locally: how wall time scales with cores. Since a GitHub runner has fewer cores, this predicts how much of the change is CPU alone.
- `pidstat -u -d 1` or `/usr/bin/time -v make check` in a `workflow_dispatch` job on both runner kinds: whether each phase is bound by CPU, I/O or waiting. That separates disk and network from compute.
- A comparison of cold and warm cache (one run with `actions/cache` disabled, one with it restored): how much of the time is setup the self-hosted runner kept between runs.
- `git bisect run` over the CI history, only if (1) shows a step that grew at one commit rather than at the flip.

## 4. What outside the agent shows it is right
- A table of per-target times on both runner kinds, at least 5 runs each, with median and spread, in which the attributed causes account for at least 90% of the wall-time difference.
- A prediction written down before the GitHub-runner runs (from the `-j` scaling curve and the cache/setup deltas) that the measured median matches within 10%.
- A target the field would call reasonable: `make check` on `ubuntu-latest`, warm cache, at or under the current self-hosted median, with each remaining gap named by its cause and its cost in seconds.

## Rewritten prompt
> "Figure out what is slowing down make check and why", specifically what changes at the flip to
> GitHub's runners. Start from the raw runs, not memory: `gh run list --json …` and
> `gh run view <id> --log` for runs on both the self-hosted runners and `ubuntu-latest`, their
> per-step timestamps and junit XML, the `check:` target in `Makefile` with its includes, and
> `.github/workflows/*.yml`. Capture each runner's `nproc`, `lscpu`, `free -m`, `df -h` and
> `/proc/pressure` in a debug step. Profile before explaining: time each recipe with
> `make --trace check | ts -s`, each test with `pytest --durations=0`, and each phase as CPU, I/O
> or wait with `pidstat -u -d 1`. Measure core scaling locally with
> `hyperfine --runs 5 'make -jN check'` for N = 1, 2, nproc, and compare cold and warm cache in a
> `workflow_dispatch` job on both runner kinds. From the scaling curve and the cache deltas,
> predict the `ubuntu-latest` median before measuring it. You are done when there is a table of
> per-target times, at least 5 runs per runner with median and spread, in which the named causes
> account for at least 90% of the difference, the prediction lands within 10% of the measured
> median, and every second by which `make check` on `ubuntu-latest` (warm cache) exceeds the
> current self-hosted median is attributed to a cause.
