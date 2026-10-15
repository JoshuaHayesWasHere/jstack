## 1. What a top professional would do
A build and performance engineer would not start from a guess about which test is slow. They would first break the wall time of `make check` into each recipe that runs and its share of the total, separating serial time from parallel time. They would then account for the whole run: every second either belongs to a named target, process or wait, or is marked unexplained. If `make check` was once faster, they would date the slowdown to a commit instead of reasoning about which change caused it.

## 2. The rawest material
- `Makefile` and every file it includes (`grep -n '^include\|^check' Makefile`), plus `make -n check` and `make -p check`: in place of a remembered sense of "what check runs".
- `make --trace check 2>&1 | ts -s '%.s' > /tmp/check-trace.log`, which gives each recipe line with its start time: in place of the total that `time make check` reports.
- A per-recipe timing log from `make check SHELL='/usr/bin/time -f "%e s %U u %S s %C" /bin/sh' 2> /tmp/check-recipes.log`: in place of "the tests are slow".
- The test runner's own timings, for example `pytest --durations=0`, `go test -json`, `cargo test -- -Z unstable-options --report-time` or `ctest --timing`, depending on what the recipes call: in place of a reading of the test names.
- If CI runs `make check`, the step timestamps in its raw log (for example `gh run view <id> --log`): in place of a recollection of how long CI takes.
- `git log --format='%h %ad %s' --date=short -- Makefile '*.mk'`: in place of a recollection of when it got slow.

## 3. The methods and tools
- `hyperfine --warmup 1 --runs 5 'make check'`, plus `-j1` against `-j$(nproc)`: a baseline as a mean and a spread, not one number, and a measure of how much parallelism `make` already gets.
- The `SHELL=/usr/bin/time` wrapper and `make --trace`: attribution of wall time to each recipe, sorted, until the named targets account for at least 90% of it.
- `py-spy record -o /tmp/check.svg -- <slowest recipe>`, or `perf record -g` and then `perf report` for native code: a profile of the slowest recipe before any theory about why it is slow.
- `pidstat -u -d -h 1` and `perf stat -e task-clock,context-switches,page-faults` during the run: whether each slow stretch is bound by CPU, I/O or waiting (sleep, network, lock).
- `strace -f -c -o /tmp/check.strace make check`: syscall and wait time that a profile does not show, such as `fsync`, network calls and re-run subprocesses.
- If any of these is missing: `pacman -S hyperfine perf strace sysstat moreutils` and `pipx install py-spy`.
- `git bisect run sh -c 'timeout 300 make check >/dev/null; t=$(hyperfine -N --runs 3 --export-json /tmp/h.json "make check" >/dev/null && jq ".results[0].mean" /tmp/h.json); [ "$(echo "$t < <threshold>" | bc)" = 1 ]'`, run only if there is a known fast commit: the commit that introduced the slowdown, found by bisecting instead of guessing.

## 4. What outside the agent shows it is right
- The per-recipe times add up to at least 90% of the `hyperfine` mean of `make check`. The remainder is shown as a named gap, not hidden.
- Each "why" makes a prediction, and a measurement confirms it: skipping or stubbing the named culprit, for example with `make check SKIP=...` or by running the target with the cause removed, cuts the `hyperfine` mean by the predicted amount, within its spread.
- If it is a regression, `git bisect` names one commit, and `hyperfine` shows that commit against its parent differing by the slowdown.
- The user can rerun the attribution command and get the same ranking.

## Rewritten prompt
```
"figure out what is slowing down make check and why"

Start from the raw run, not from the test names: read the Makefile and its includes,
`make -n check`, and a timed trace of each recipe
(`make check SHELL='/usr/bin/time -f "%e s %U u %S s %C" /bin/sh'` and `make --trace check | ts -s`),
plus the test runner's own per-test timings (`pytest --durations=0` or the runner's equivalent),
and the CI log's step timestamps if CI runs it.

Measure the baseline with `hyperfine --warmup 1 --runs 5 'make check'`, at -j1 and at -j$(nproc),
and report the mean and the spread. Attribute the wall time to recipes until named targets
account for at least 90% of it. For the top culprits, find out why with a profile
(py-spy or perf record), with pidstat or perf stat to tell CPU from I/O from waiting, and with
strace -c for syscalls and sleeps. If check was faster before, bisect to the commit
with `git bisect run` and a hyperfine threshold.

Done when: a table of recipes by share of wall time covers at least 90% of the hyperfine mean;
each "why" comes with a prediction that a measurement confirms (removing or stubbing
that cause cuts the hyperfine mean by the predicted amount, within its spread);
any regression is pinned to one commit by bisect; and the commands are included so that I
can rerun them and get the same ranking. Diagnose only; don't fix.
```
