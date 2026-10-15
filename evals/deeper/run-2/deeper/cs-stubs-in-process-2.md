## 1. What a top professional would do
A performance engineer would not accept "the tests are slow" as an answer. They would:
- Measure the whole of `make check` first, with a run count and a spread, before naming any cause.
- Break the wall time down by target, then by process, until the named parts add up to the total.
- Prove each "why" with a controlled experiment that removes the suspected cause and shows the time drop by the predicted amount.

## 2. The rawest material
- `make -n check` and the `Makefile` itself (plus any included `*.mk`): in place of a remembered idea of what `check` runs.
- `make --trace check 2>&1 | ts -s '%.s'` (from `moreutils`), which gives each recipe line with a timestamp: in place of a feeling about which step is slow.
- `pytest --durations=0 -q` output, or the equivalent per-test timing of whatever runner `check` calls: in place of a guess at "the slow tests".
- `strace -f -c -o /tmp/check.strace make check`, which gives process spawns, `execve` counts and syscall time: in place of an assumption that the time is CPU time in our code.
- The CI run's own log for `make check` with its step timings, and `git log` on `Makefile` and the test config: in place of "it used to be faster".

## 3. The methods and tools
- `hyperfine --warmup 1 --runs 10 'make check'`: a baseline mean and spread, cold and warm (`--prepare 'make clean'`), before anything is changed.
- `make --trace` with `ts`, or `remake --profile check` (`pacman -S remake` / AUR): per-target wall time, and whether targets run serially that could run under `-j`.
- `pytest --durations=0`, and `python -X importtime` on the test entry point: per-test time and collection or import cost.
- `py-spy record -o /tmp/check.svg --subprocesses -- make check` (`pipx install py-spy`): a flame graph of where the Python time goes.
- `perf stat -e task-clock,context-switches make check` and `pidstat -u -d 1` alongside it: CPU-bound vs I/O-bound vs idle. If wall time is much greater than CPU time, the cause is waiting.
- `strace -f -c` / `strace -f -e trace=execve`: spawn storms such as repeated interpreter startups, `npx`, or network calls.
- `git bisect run sh -c 'hyperfine -N --runs 3 --export-json /tmp/b.json "make check" && jq ".results[0].mean < T" /tmp/b.json'`: if it got slower, find the commit instead of guessing.

## 4. What outside the agent shows it is right
- A `hyperfine` baseline of `make check`, with mean ± σ over 10 runs, cold and warm.
- An attribution table whose parts sum to at least 95% of that measured wall time, with no unexplained remainder.
- For each named cause, a controlled `hyperfine` run with that cause removed (target skipped, test deselected, `-j` added, cache warmed, import stubbed). Its measured drop must match the predicted saving within the noise.
- The stated, deliberately ambitious target: identify changes predicted to bring warm `make check` under half its current time. The field would call that reasonable for an unprofiled suite.

## Rewritten prompt
> "figure out what is slowing down make check and why"
>
> Start from the raw material, not from impressions:
> - Read `make -n check` and the `Makefile` with its includes.
> - Run `make --trace check 2>&1 | ts -s '%.s'` for per-recipe timestamps.
> - Run `pytest --durations=0` (or the runner `check` uses) for per-test times.
> - Run `strace -f -c make check` for spawns and syscalls.
> - Read the CI log's step timings for `make check`.
>
> Instruments and method:
> - First take a baseline with `hyperfine --warmup 1 --runs 10 'make check'`, both warm and cold (`--prepare 'make clean'`), and report mean ± σ.
> - Then break the time down by target (`make --trace` or `remake --profile`).
> - Then break it down by test and import (`pytest --durations=0`, `python -X importtime`).
> - Then find where CPU time goes (`py-spy record --subprocesses`) and whether the run is CPU-bound or waiting (`perf stat`, `pidstat -u -d 1`).
> - If it regressed, find the commit with `git bisect run` and a hyperfine threshold instead of guessing.
> - Do not fix anything; this is diagnosis.
>
> Proof:
> - The attribution must account for at least 95% of the measured wall time.
> - Each named cause must be confirmed by a controlled hyperfine run with that cause removed, and its measured saving must match the prediction within noise.
> - Aim to identify changes that would bring warm `make check` under half its current time, and say which measurements show it.
