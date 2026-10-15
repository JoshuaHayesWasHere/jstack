## 1. What a top professional would do
A test-infrastructure / build-performance engineer. Before adding workers, they would measure where the serial time actually goes: per-test durations, collection, and fixture setup. They would also prove the tests are isolated, with no shared temp files, ports, databases or ordering, because parallelism turns hidden coupling into flaky failures. Then they would pick the worker count and distribution mode from the measurement, not set it by default.

## 2. The rawest material
- `pytest --durations=0 -q --junitxml=serial.xml` on the current suite: in place of the impression that "the tests are slow"
- the CI run's own log and its per-step timings (`gh run view --log <run-id>`): in place of a remembered "CI takes ages"
- `nproc`, `lscpu`, `free -h` on this machine and the CI runner's spec: in place of an assumed core count
- `rg -n '/tmp|tmp_path_factory|port|sqlite|session' tests/ conftest.py`, which lists the fixtures and paths the tests share: in place of trusting that the tests are independent

## 3. The methods and tools
- `pytest-xdist` (`pytest -n auto --dist loadscope`, then `--dist loadfile`): parallel execution, with the distribution mode chosen to fit the fixture scopes
- `pytest-randomly` (`pytest -p randomly -n auto`) and `pytest-repeat` (`pytest --count 20 -n auto -x`): catch order dependence and flakiness before calling the change done
- `hyperfine --warmup 1 --runs 5 'pytest -q' 'pytest -q -n auto' 'pytest -q -n 4'`: a wall-time number with a run count and a spread, and a comparison across worker counts
- `pidstat -u 1` or `perf stat -e task-clock pytest -q -n auto`: check whether the cores are saturated or the tests wait on I/O or a single slow test
- Install the missing tools with `pip install pytest-xdist pytest-randomly pytest-repeat` and `pacman -S hyperfine sysstat perf`

## 4. What outside the agent shows it is right
- hyperfine's median wall time for the parallel suite is at most ¼ of the serial median on this machine. That target is reasonable with ≥8 cores unless one test dominates; if one does, name it as the floor.
- The parallel run collects the same test count and the same pass/fail set as the serial run, compared by diffing `serial.xml` against `parallel.xml`.
- 20 consecutive parallel runs in random order all pass, with no new flakes.
- The CI run's own log shows the parallel step passing, along with its new duration.

## Rewritten prompt
```
"run the test in parallel"

Start from the raw numbers, not an impression: run `pytest --durations=0 -q --junitxml=serial.xml`,
read the last CI run's log for its timings, and check `nproc`/`lscpu` here and on the CI runner.
Grep tests/ and conftest.py for shared state (/tmp paths, ports, sqlite files, session fixtures)
and make each one per-worker (tmp_path, worker_id-suffixed names) before parallelising.

Parallelise with pytest-xdist (`-n auto`), choosing --dist loadscope or loadfile to fit the fixture
scopes. Flush out coupling with pytest-randomly and `pytest --count 20 -n auto -x`. Measure with
`hyperfine --warmup 1 --runs 5` serial against parallel at several worker counts, and use pidstat to
see whether the cores are saturated.

Done when: hyperfine's median parallel wall time is ≤ ¼ of serial (or the single slowest test is
named as the floor), the parallel junit xml has the same tests and the same pass/fail set as
serial.xml, 20 random-order parallel runs all pass, and the CI log shows the parallel step green
with its new duration.
```
