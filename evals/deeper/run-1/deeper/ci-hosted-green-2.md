## 1. What a top professional would do
A CI/test-infrastructure engineer would not raise the 15-minute limit or add retries. They would first make the hang report itself: name the exact test that was running when it stopped, and capture a stack dump of every thread and child process at that moment. They would also check whether the two attempts stopped on the same test, which means it is deterministic, or on different tests, which points to an ordering, resource or leaked-Chrome problem. Only then would they change any code.

## 2. The rawest material
- `gh run list --workflow <ci.yml> --limit 5` then `gh run view <run-id> --log` for both attempts: in place of "hung at 92% and 95%".
- The last `[ 92%]` and `[ 95%]` lines in each raw log, and the test IDs around them from `pytest --collect-only -q` in the same order: in place of a percentage.
- `.github/workflows/*.yml`, plus the fixtures that start and quit Chrome (`conftest.py`, any `webdriver` or `playwright` launch code): in place of the assumption that teardown works.
- A process snapshot taken inside the job when it hangs (`ps -ef --forest`, `pgrep -a chrome`, and Chrome's own stderr or `--enable-logging=stderr` output): in place of the job summary's "Chrome processes still running".
- The runner's own facts in the log header (image version, Chrome and chromedriver versions, CPU and memory): in place of "ubuntu-latest".

## 3. The methods and tools
- `pytest -v -p no:randomly --timeout=120 --timeout-method=thread` (from `pytest-timeout`, installed with `pip install pytest-timeout`): this turns the silent hang into a failure that names the test and dumps every thread's stack.
- `faulthandler_timeout = 100` in `pytest.ini`: a second stack dump in case the timeout plugin's own thread is blocked.
- A workflow step guarded by `if: failure() || cancelled()`, run under `timeout-minutes` below the job limit, that runs `ps -ef --forest`, `pgrep -a chrome`, and `py-spy dump --pid $(pgrep -f pytest)` (`pip install py-spy`, which needs `sudo`): a profile of the hang, captured before any fix.
- Reproducing locally in the same image, with `act -j <job>` or `docker run -it ubuntu:24.04` plus the workflow's install steps, then running the suspect test alone and with its neighbours (`pytest <id> -v`, then `pytest -k` widened step by step): a bisect over the test order instead of a guess.
- `pytest --count 20` on the suspect test (`pip install pytest-repeat`), and a loop of `workflow_dispatch` runs (`gh workflow run` ×N): a run count, so that both the failure rate and the fix are measured rather than seen once.

## 4. What outside the agent shows it is right
- GitHub Actions itself: 20 out of 20 consecutive `ubuntu-latest` runs finish green, each in under 5 minutes against the 15-minute limit. In this field that is a reasonable bar for a suite that should never hang.
- A final step `! pgrep -a chrome` that passes in every run, meaning no Chrome process outlives the tests.
- A test or `--timeout` run that hangs or fails before the fix and passes after it, on the CI runner and not only locally.

## Rewritten prompt
```
"jstack's first public check never finished: two attempts on `ubuntu-latest` hung after the dots
reached 92% and 95% and were cancelled at the job's 15-minute limit, with Chrome processes still
running." Find out why and fix it. Do not fix it by raising the limit or adding retries.

Start from the raw runs, not the summary: `gh run view <run-id> --log` for both attempts. Map each
last `[ 92%]`/`[ 95%]` line to a test ID using `pytest --collect-only -q` in the same order, and say
whether both attempts stopped on the same test. Read `.github/workflows/*.yml` and the fixtures that
launch and quit Chrome. Record the runner image, the Chrome and chromedriver versions, and the
CPU and memory from the log header.

Make the hang report itself before changing any code. Run CI with
`pytest -v -p no:randomly --timeout=120 --timeout-method=thread` and set
`faulthandler_timeout` in pytest.ini. Add a step guarded by `if: failure() || cancelled()` that
dumps `ps -ef --forest`, `pgrep -a chrome`, and `py-spy dump` of the pytest process. Reproduce in the
same image (`act` or `docker run ubuntu:24.04`), then bisect the test order down to the smallest set
that hangs, and measure how often it hangs with `pytest --count 20`.

It is done when a run that hung before the fix passes after it on the CI runner, and 20 out of 20
consecutive `ubuntu-latest` runs finish green, each under 5 minutes. Every run must end with a step
`! pgrep -a chrome` that passes, so no Chrome process outlives the tests. Report the cause with the
stack dump that shows it, and the 20 run IDs with their durations.
```
