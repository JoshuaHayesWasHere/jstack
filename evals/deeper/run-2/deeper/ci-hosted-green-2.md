## 1. What a top professional would do
A CI reliability engineer would not guess why it hangs. They would capture a stack dump of the hung process, plus the process tree with Chrome in it, at the moment it stops, and work from that.
They would map "92%" and "95%" to the exact test IDs that were running, then reproduce the hang under `ubuntu-latest` conditions (headless, 4 cores, no display) before changing any code.

## 2. The rawest material
- `gh run list --workflow <ci.yml> --limit 5` and `gh run view <run-id> --log` for both cancelled attempts: in place of "the dots reached 92% and 95%"
- `pytest --collect-only -q` run in the same order and with the same plugins as the CI step, to turn 92% and 95% into the test that was running: in place of a percentage
- `.github/workflows/*.yml` (the job's `runs-on`, `timeout-minutes`, Chrome/chromedriver setup) and the `conftest.py` fixture that launches and quits Chrome: in place of the memory of how the suite starts the browser
- `ps -eo pid,ppid,etime,stat,cmd --forest` and `py-spy dump --pid <pytest-pid>` taken inside the CI job while it hangs: in place of "Chrome processes still running" from the cancellation notice
- Chrome/chromedriver's own logs (`--enable-logging --v=1`, `chromedriver --log-path`), uploaded with `actions/upload-artifact` under `if: always()`: in place of nothing, since none is kept today

## 3. The methods and tools
- `gh run view --log` / `gh run download`: reading the run's raw log before forming a hypothesis
- pytest's `faulthandler_timeout = 120` in `pytest.ini`/`pyproject.toml`, or `pytest-timeout` with `--timeout=120 --timeout-method=thread`: dumping every thread's stack from the hung test instead of waiting out the 15-minute kill
- a background watchdog step (`sleep 600; ps ... --forest; py-spy dump --pid $(pgrep -f pytest)`), with `pip install py-spy` and `sudo` on the runner: a profile of the hang before the fix
- `act -j <job>` or `docker run --cpus 4 -m 16g ubuntu:24.04` with the workflow's install steps: reproducing on `ubuntu-latest`'s shape locally before calling it fixed
- `pytest <tail of the suite from the test at 92%>` and `pytest --deselect`/`-k` halving: a bisect over the test set rather than a guess at the culprit
- `pgrep -a chrome` in a final `if: always()` step: counting orphaned browsers instead of inferring them

## 4. What outside the agent shows it is right
- Before the fix, the identified test, run alone or in the reproduction container, hangs or trips the timeout. After the fix it passes.
- The GitHub Actions check on `ubuntu-latest` goes green on 20 consecutive runs (`gh workflow run` repeated, or a matrix of 20). Each job finishes in under 4 minutes, well inside the 15-minute limit. The field would call that reasonable for a suite that only hangs at its tail.
- The final `pgrep -a chrome` step prints nothing on every one of those runs.

## Rewritten prompt
> "jstack's first public check never finished: two attempts on `ubuntu-latest` hung after the
> dots reached 92% and 95% and were cancelled at the job's 15-minute limit, with Chrome
> processes still running." Find and fix the cause of that hang, and nothing beyond it.
> Start from the raw runs, not the summary. Read both cancelled attempts with
> `gh run view <run-id> --log`. Map 92% and 95% to test IDs with `pytest --collect-only -q`,
> in CI's order and with CI's plugins. Read `.github/workflows/*.yml` and the `conftest.py`
> fixture that starts and quits Chrome.
> Capture the hang before changing code. Set `faulthandler_timeout` (or `pytest-timeout
> --timeout-method=thread`) so the hung test dumps every stack. Add a watchdog step that
> records `ps -eo pid,ppid,etime,stat,cmd --forest` and `py-spy dump` of pytest. Keep
> Chrome's and chromedriver's logs as an artifact under `if: always()`. Reproduce on the
> runner's shape with `act` or an `ubuntu:24.04` container, and halve the suite's tail with
> `-k`/`--deselect` until one test hangs alone.
> It is done when three things hold. That test hangs before the fix and passes after it. The
> check on `ubuntu-latest` is green on 20 consecutive runs, each under 4 minutes. A final
> `pgrep -a chrome` step finds no Chrome left on any of them. Report the run IDs and the
> stack dump that named the cause.
