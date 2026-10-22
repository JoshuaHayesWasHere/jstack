## 1. What a top professional would do
A build and performance engineer would not stop at the slowest step. They would account for the whole wall-clock time of `make check` across its recipes, tests and idle waits, and show that the parts add up to the total within a stated margin. Then they would prove each "why" with a profile of that step and a controlled experiment, not an explanation. If `make check` got slower over time, they would bisect to the commit that did it instead of guessing.

## 2. The rawest material
- `Makefile` and every file it includes (`grep -n '^include\|^check' Makefile`), plus `make -n check` and `make -p check | less`: in place of a remembered idea of what `check` runs.
- A per-recipe trace from `make --trace check 2>&1 | ts -s '%.s' > /tmp/check-trace.log` (`ts` is in `moreutils`): in place of "it feels like the tests are slow".
- The test runner's own timing, e.g. `pytest --durations=0 -p no:cacheprovider` or `ctest --output-on-failure -T Test` with its `Testing/Temporary/LastTest.log`: in place of a summary of which tests are slow.
- The machine's counters during the run: `pidstat -u -d -r 1 > /tmp/check-pidstat.log` and `/usr/bin/time -v make check`: in place of the assumption that it is CPU-bound.
- `git log --format='%h %ad %s' --date=short -- Makefile tests/` and CI run logs with timestamps, if CI keeps them: in place of "it used to be faster".

## 3. The methods and tools
- `hyperfine --warmup 1 --runs 10 'make check'` (pacman `hyperfine`), with a clean tree and a warm tree measured separately: a baseline with a run count and a spread before any claim.
- `make --trace` with `ts`, or `remake --profile check` (AUR `remake`): attributing wall time to each recipe, and finding the serial steps that `-j$(nproc)` would not help.
- `pytest --durations=0`, `pytest --setup-show` and `python -X importtime`: separating test bodies, fixture setup and import cost.
- `py-spy record -o /tmp/check.svg --subprocesses -- make check` for Python, or `perf record -g -- make check` with `perf report` for native code: a profile of the dominant step before naming a cause.
- `pidstat -u -d -r 1`, `perf stat -e task-clock,context-switches,page-faults make check`, `strace -f -c -o /tmp/check.strace make check`: deciding whether the run is limited by CPU, I/O, sleeps or process spawning.
- `git bisect run sh -c 'timeout 120 make check'` with a time threshold: finding the commit behind a regression, if there is one.

## 4. What outside the agent shows it is right
- The breakdown adds up: the attributed times of the named steps sum to `hyperfine`'s mean wall time of `make check`, within 10%.
- Each named cause is shown by an experiment. Stubbing, skipping or caching that one step on a scratch branch drops `hyperfine`'s mean by the amount attributed to it, outside the spread of 10 runs. That branch is thrown away afterward, not merged.
- If the cause is a regression, `git bisect` names a single commit, and reverting just that commit on a scratch branch restores the old time under `hyperfine`.
- The target to aim the explanation at: show what `make check` would take if every named cause were removed, and say how far that is from 10 seconds. Ask for 10 seconds even if it is minutes today, because a performance engineer would treat that as the reasonable floor.

## Rewritten prompt
> "Figure out what is slowing down make check and why." Do not fix anything. Start from the
> source data, not from impressions: read `Makefile`, its includes and `make -n check` to get
> what `check` actually runs. Record a timed trace with `make --trace check | ts -s`, get the
> test runner's own per-test timings (`pytest --durations=0 --setup-show` or the ctest log), and
> capture `pidstat -u -d -r 1` and `/usr/bin/time -v` during a run. First measure a baseline with
> `hyperfine --warmup 1 --runs 10 'make check'`, separately for a clean tree and a warm tree.
> Attribute the wall time to recipes and tests until the named parts add up to the total within
> 10%. For each part that matters, profile it before explaining it: `py-spy record --subprocesses`
> or `perf record -g`, `python -X importtime`, and `strace -f -c`. Say whether it is bound by CPU,
> I/O, sleeps, process spawning or serial steps. If it has gotten slower over time, use
> `git bisect run` with a time threshold instead of guessing. Prove each cause with an
> experiment on a scratch branch that is discarded afterward: stubbing or skipping that one cause
> must drop `hyperfine`'s mean by the attributed amount, outside the spread. Report the baseline
> with its spread, the breakdown table, each cause with its profile and its experiment, and the
> time `make check` would take with all of them removed, compared to a target of 10 seconds.
