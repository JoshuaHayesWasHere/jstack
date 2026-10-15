## 1. What a top professional would do
A CI reliability engineer would not tune the timeout or retry. They would first find out which test or tests never reported. The dots stopped between 92% and 95%, so the answer is in the last few percent. They would then make the hang self-reporting: a per-test timeout, and a dump of the process tree when it fires. That way the next hang names its culprit and leaves evidence about which Chrome is still alive and why, without anyone having to re-run and guess.

## 2. The rawest material
- `gh run list --workflow <check>.yml --limit 5` and then `gh run view <run-id> --log` for both cancelled runs: in place of "hung at 92% and 95%". The raw log has a timestamp on every line, which shows when the last dot was printed and how long the job sat silent before the 15-minute cancel.
- The test files listed in the order the runner schedules them (for example the runner's `--list`/`--listTests` output), lined up against the number of dots in each log: in place of the percentage. This narrows the candidates to the tests that never emitted a dot.
- `.github/workflows/*.yml` for the check, plus the runner config and the browser-launch helper (where Chrome is started and closed): in place of what we assume the job does on `ubuntu-latest`. That means the image version, the Chrome flags such as `--no-sandbox`/`--headless`, and any teardown.
- The Chrome processes that were "still running": captured as `ps -eo pid,ppid,etime,stat,cmd --forest` at the moment of the hang, in place of the cancel message's summary.

## 3. The methods and tools
- **Per-test reporter instead of dots** (the runner's `spec`/`verbose` reporter), with a per-test timeout well under the job limit. The method is to locate the hang by name rather than by percentage.
- **A hang watchdog in the workflow.** Wrap the test command in `timeout --signal=TERM --kill-after=30 600 <test command>`. Add an `if: always()` step that runs `ps -eo pid,ppid,etime,stat,cmd --forest` and `pgrep -a chrome`. If the runner is Node, also run `npx why-is-node-running` (or log `process._getActiveHandles()`). The method is to dump state at the hang instead of losing it to the cancel.
- **Local reproduction on the same image.** Run `docker run --rm -it -v "$PWD":/w -w /w ubuntu:24.04` with the job's install steps, or `act -j <job>` (install with `pacman -S act`). Then run the suspect test alone in a loop: `for i in $(seq 20); do <test command> <suspect>; done`. The method is to reproduce before fixing, and to keep a run count rather than rely on a single pass.
- **`strace -f -p <pid>` / `gdb -p <pid> -batch -ex 'thread apply all bt'`** on the stuck process in the reproduction. The method is to see what it is blocked on (a pipe, a websocket to a dead target, a child wait) before changing any code.

## 4. What outside the agent shows it is right
- **The GitHub Actions check itself.** It must finish green on `ubuntu-latest` in 5 of 5 consecutive runs (re-run with `gh run rerun`), each in under 5 minutes. That target is reasonable for a check that reached 95% well inside 15.
- **A post-test step that fails the job if `pgrep chrome` finds anything.** It must pass, which shows that no Chrome outlives the suite.
- **A test that fails before and passes after.** A deliberately hanging test, or the hang reproduced in the `ubuntu:24.04` container, must make the job fail fast. It should fail within the per-test timeout, name the test, and print the process tree, instead of sitting silent until the 15-minute cancel.

## Rewritten prompt
> "jstack's first public check never finished: two attempts on `ubuntu-latest` hung after the dots
> reached 92% and 95% and were cancelled at the job's 15-minute limit, with Chrome processes still
> running." Start from the raw logs of both cancelled runs (`gh run view <run-id> --log`). Use their
> line timestamps and the dot counts, set against the runner's ordered test list, to name the test or
> tests that never reported. Then read the workflow in `.github/workflows/` and the code that launches
> and closes Chrome. Make the hang self-reporting: switch to a per-test reporter, give each test a
> timeout, wrap the run in `timeout --kill-after`, and add an `if: always()` step that prints
> `ps -eo pid,ppid,etime,stat,cmd --forest` and `pgrep -a chrome`. Reproduce the hang in a
> `ubuntu:24.04` container (or with `act`), running the suspect test alone in a loop. Use `strace -f`
> or a backtrace to see what the stuck process waits on before you change anything. Fix the cause,
> not the timeout. It is done when a hang fails the job fast and by name, when a post-test
> `pgrep chrome` step finds nothing, and when the check passes on `ubuntu-latest` 5 runs out of 5,
> each in under 5 minutes.
