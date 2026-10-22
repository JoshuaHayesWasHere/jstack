## 1. What a top professional would do
A CI/build performance engineer. They would not compare one slow run to a remembered fast one. They would run the same commit on both runner types several times and break `make check` into its per-target and per-test times on each. Then they would tie every gap to a named resource of the runner: core count against `make -j`, disk and tmpfs, network fetches, cold caches, or the CPU model. Only after that would they say what the flip changes.

## 2. The rawest material
- `gh run list --workflow <check workflow> --json databaseId,headSha,createdAt,updatedAt,conclusion`, then `gh run view <id> --log` for runs of one SHA on the current runner and on `ubuntu-latest`: in place of "CI got slower" or a remembered number.
- The `Makefile` and `.github/workflows/*.yml` themselves (the `check` target's prerequisites, the `-j` it runs with, the `runs-on:`, any `actions/cache` steps): in place of a summary of what `make check` does.
- The runner's own counters from a diagnostic step on each runner type (`nproc; free -h; df -h /tmp .; lscpu | grep -E 'Model name|^CPU\(s\)'; mount | grep -E 'tmpfs| / '`): in place of GitHub's advertised runner spec.
- The per-test durations from the test runner's own output (for example `pytest --durations=0` or the equivalent): in place of a guess at which tests are slow.

## 3. The methods and tools
- `hyperfine --runs 5 --prepare 'make clean' 'make check'` locally and on the current runner: gives a median and a spread rather than one number.
- `make --trace check 2>&1 | ts -s` (from moreutils), or `remake --profile check`: per-target wall time, which shows the critical path.
- `pytest --durations=0` (or the suite's own timer): per-test cost, which separates slow tests from slow setup.
- `/usr/bin/time -v make check` and `pidstat -u -d 1` running alongside it: CPU-bound against I/O-bound against idle-waiting (network or serial targets).
- `gh run view --log` timestamps diffed step by step across the two runner types: per-step attribution of the flip, on the same SHA.
- `act -j <job>` (from `pacman -S act` or the AUR) where a hosted run is too slow to iterate on. It is a rehearsal only and does not stand in for the hosted runner's numbers.

## 4. What outside the agent shows it is right
- GitHub's own run timings for one SHA, at least 5 runs on each runner type, reported per step as median and spread. They must show where the time goes on each.
- A prediction tested on the hosted runner. The attribution names the cause (for example "`-j` is hard-coded to 8 against 4 cores", or "the cache misses on X"), predicts the saving from fixing it, and a hosted run measures that saving. The prediction must land within the spread.
- Target: `make check` on GitHub's runners no slower than on the current runner, median over 5 runs. That is reasonable for a build engineer, not a stretch.

## Rewritten prompt
```
"figure out what is slowing down make check and why", the part that asks what changes at the flip
to GitHub's runners.

Start from the raw runs, not memory: pick one SHA, get at least 5 runs of the check workflow on the
current runner and on ubuntu-latest (gh run list --json …, gh run view <id> --log), and read the
Makefile's check target and .github/workflows/*.yml (runs-on, -j, cache steps). Add a diagnostic
step on each runner type that prints nproc, free -h, df -h, lscpu and mounts.

Measure, don't guess: per-step times from the run logs, per-target times from make --trace | ts -s
(or remake --profile), per-test times from the test runner's --durations, and CPU/IO/idle from
/usr/bin/time -v and pidstat -u -d 1. Report every number as a median with its spread.

Attribute each gap between the runners to a named resource (cores vs -j, disk/tmpfs, network
fetches, cold caches, CPU model). Done when: the per-step table for both runner types is in hand,
the top cause comes with a predicted saving, and a hosted run measures that saving within the
spread. Target: make check on GitHub's runners no slower than on the current runner.
```
