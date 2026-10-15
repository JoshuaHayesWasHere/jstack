## 1. What a top professional would do
A CI reliability engineer. They would not start by guessing at the fix or raising the 15-minute limit. First they would make the hang name itself: which test, which thread, and which Chrome process were stuck, on the runner itself. Only then would they fix the cause. They would also treat 92% vs 95% as evidence. The two runs stopped at different points, so this looks like a race or a resource limit, not one bad test, and they would want it reproduced more than once before calling it fixed.

## 2. The rawest material
- `gh run list --workflow <ci.yml> --repo <owner>/jstack` then `gh run view <run-id> --log` for both cancelled runs, including the timestamps of the last lines before the stall: in place of "it hung at 92% and 95%"
- `.github/workflows/*.yml` (runner image, Chrome/driver install step, pytest invocation, `timeout-minutes`) and `pytest.ini`/`pyproject.toml` `[tool.pytest.ini_options]`: in place of the memory of how the check is set up
- The test ids at those percentages, from `pytest --collect-only -q | nl` (what sits at about 92% and 95% of the collected count): in place of the dots, which name nothing
- The process tree and Chrome's own stderr at the moment of the hang (`ps -eo pid,ppid,etime,stat,wchan,cmd --forest`, the browser/driver logs), captured on the runner: in place of "Chrome processes were still running"
- The conftest/fixtures that launch and close Chrome (`conftest.py`, any `browser`/`driver`/`page` fixture): in place of an assumption that teardown is fine

## 3. The methods and tools
- `pytest -v -o faulthandler_timeout=120` (built in), or `pip install pytest-timeout` and `pytest --timeout=120 --timeout-method=thread`: make a stuck test dump every thread's stack and fail by name, instead of a silent cancel
- A step after pytest with `if: always()` that runs `ps ... --forest`, `py-spy dump --pid <pytest pid>` (`pip install py-spy`), and `actions/upload-artifact` for Chrome/driver logs. Also set a step-level `timeout-minutes` below the job's 15 so this step still gets time to run: capture the evidence on the machine that hung
- `pytest --durations=0 -p no:cacheprovider`, and `-p no:randomly` versus the random order if pytest-randomly is in use: find out whether the stall follows a test or follows a position in the order
- Local reproduction on the runner's shape: `docker run --cpus=4 --memory=16g -it ubuntu:24.04` (or `act -j <job>`), looped with `for i in $(seq 20); do timeout 600 pytest -q || echo "run $i: $?"; done`: a hang rate, not a single anecdote
- `gh workflow run` / `gh run rerun` repeated after the fix: the same check measured on the real runner

## 4. What outside the agent shows it is right
- GitHub's own `ubuntu-latest` runner: 20 consecutive green runs of the check, each finishing in under 5 minutes, against a 15-minute limit. That is reasonable for a suite that reaches 95% before stalling.
- The local loop: before the fix it shows at least one `timeout` exit 124 (or a named faulthandler dump) in 20 runs, and after the fix it shows 0 in 20.
- The post-run `ps` step lists no `chrome`/`chromedriver` processes after pytest exits on every run.
- The test that hung is named in a failing dump before the fix, and that same test passes after it.

## Rewritten prompt
```
"jstack's first public check never finished: two attempts on `ubuntu-latest` hung after the dots
reached 92% and 95% and were cancelled at the job's 15-minute limit, with Chrome processes still
running." Find out why and fix it, without raising the time limit.

Start from the raw material, not the summary: `gh run view <run-id> --log` for both cancelled runs
(last lines and their timestamps), the workflow file in `.github/workflows/`, the pytest config,
the conftest fixtures that start and stop Chrome, and `pytest --collect-only -q | nl` to name the
tests sitting at ~92% and ~95%.

Make the hang name itself before changing any code. Run pytest with `-v -o faulthandler_timeout=120`
(or pytest-timeout with `--timeout-method=thread`). Give the pytest step a `timeout-minutes` under
15. Add an `if: always()` step that records `ps -eo pid,ppid,etime,stat,wchan,cmd --forest` and
`py-spy dump`, and uploads Chrome/driver logs as artifacts. Reproduce it locally in
`docker run --cpus=4 --memory=16g ubuntu:24.04` in a 20-run loop under `timeout 600`, with
`--durations=0`, and compare a fixed order against a random one. Fix the cause the dumps show,
not a guess.

Done when GitHub's ubuntu-latest runner gives 20 consecutive green runs of the check, each under
5 minutes. The local loop must go from at least one hang in 20 to none in 20. The post-run `ps`
must show no chrome/chromedriver left after pytest exits. The test named in a dump before the fix
must pass after it.
```
