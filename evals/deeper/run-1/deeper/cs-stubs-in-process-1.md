## 1. What a top professional would do
A build/performance engineer would not guess which part of `make check` is slow. They would first split its wall time per target and per test, then profile the slowest one, and only then say "why".
They would check whether the slowness is CPU, I/O, waiting or serialization. They would also look for a regression point in history, so the "why" names a commit or a cause rather than a suspect.

## 2. The rawest material
- `Makefile` (and any `*.mk` it includes), read as text: in place of a remembered idea of what `check` runs.
- `make -n check` and `make --trace check 2>&1 | tee /tmp/check-trace.log`: in place of an assumed list and order of steps.
- A timed run log, `ts -s '%.s' < <(make check 2>&1) > /tmp/check-timed.log` (from `moreutils`): in place of "it feels slow" and a single wall-clock number.
- The test runner's own per-test timings, `pytest --durations=0 -q` (or the equivalent for the repo's runner): in place of a guess at which tests are heavy.
- `git log --oneline -- Makefile tests/ pyproject.toml` and the CI run logs for `make check` over recent weeks (`gh run list --workflow <ci> --json databaseId,createdAt,conclusion` then `gh run view <id> --log`): in place of a recollection of when it got slow.

## 3. The methods and tools
- `hyperfine --warmup 1 --runs 5 'make check'`: a baseline wall time with a mean and spread before any claim.
- `hyperfine --runs 5 'make <each sub-target>'` (e.g. `lint`, `typecheck`, `test`): to break the total down per target.
- `pytest --durations=0` and `pytest -p no:cacheprovider --collect-only -q` timed separately: to tell collection and import cost apart from test cost.
- `python -X importtime -c 'import <pkg>' 2> /tmp/import.log` plus `tuna /tmp/import.log`: for import-time cost, if collection is heavy.
- `py-spy record -o /tmp/check.svg -- make check` (or `perf record -g -- make check` with `perf report` for non-Python steps): a profile of the slowest target before naming a cause.
- `/usr/bin/time -v make check` and `pidstat -u -d 1` during the run: to decide whether it is CPU-bound, I/O-bound or idle (waiting, sleeping, network).
- `make -j$(nproc) check` against `make check`: to find serialization the targets do not need.
- `git bisect run sh -c 'timeout 600 make check >/dev/null; [ $(...) -lt <threshold> ]'` with a timing script: to find the commit where it slowed, if the history shows a regression.
- Install missing tools with `pacman -S hyperfine moreutils perf` and `pipx install py-spy tuna`.

## 4. What outside the agent shows it is right
- `hyperfine` numbers (mean ± σ, at least 5 runs) for `make check` and for each sub-target. They must account for at least 90% of the total wall time, so that no time is left unattributed.
- A profile or `--durations` output that shows the named cause taking the time it is claimed to take.
- A falsifiable check of the "why": disabling or stubbing the named cause (skip that target, mark those tests, mock that import) must remove roughly that much time in a fresh `hyperfine` run.
- If a regression is claimed, `git bisect` names the first slow commit, and timing that commit against its parent reproduces the difference.
- The user re-runs the reported `hyperfine` command on their machine and sees the same breakdown.

## Rewritten prompt
```
"figure out what is slowing down make check and why"

Start from the raw material, not from impressions: read the Makefile and anything it includes,
get the real step list with `make -n check` and `make --trace check`, and time each output line
with `ts -s` from moreutils. Pull the test runner's own per-test timings (`pytest --durations=0`),
and look at `git log` for Makefile/tests/config along with recent CI logs for `make check`
(`gh run view <id> --log`) to see whether and when it got slower.

Measure before explaining. Baseline `make check` with `hyperfine --warmup 1 --runs 5`, then each
sub-target the same way. Separate test collection/import time (`--collect-only`,
`python -X importtime`) from test run time. Profile the slowest target with `py-spy record` (or
`perf record -g` for non-Python steps). Use `/usr/bin/time -v` and `pidstat` to tell CPU-bound,
I/O-bound and idle time apart, and compare `make -j$(nproc) check` to see whether serialization
plays a part. If history shows a regression, `git bisect run` it with a timing threshold.
Install anything missing with pacman or pipx.

Done when: a hyperfine breakdown attributes at least 90% of `make check`'s wall time to named
targets, tests or imports; each named cause is backed by a profile or --durations output; and
removing or stubbing each cause cuts roughly the claimed time in a fresh hyperfine run. If it is a
regression, bisect names the commit and the parent-vs-commit timing reproduces it. Report the
exact commands so I can re-run them and get the same numbers. Do not fix anything; diagnose only.
```
