## 1. What a top professional would do
A test-infrastructure / performance engineer would measure first: a serial baseline with per-test durations, so they know the long pole and the floor that parallelism can't beat. They would also prove the tests are independent before trusting them in parallel, by running them in random order, repeated, and comparing results with the serial run. (This assumes a pytest suite; for another runner, use its equivalents.)

## 2. The rawest material
- `pytest -p no:randomly --durations=0 -q 2>&1 | tee /tmp/serial-durations.txt`: in place of a remembered "the suite takes a few minutes"
- `pytest --junitxml=/tmp/serial.xml`: in place of "it all passes", a per-test pass/fail record to diff against
- The CI run's own log for the test job (`gh run view <run-id> --log`): in place of the CI badge or the summary line
- `nproc` and `free -h` on this machine and on the CI runner: in place of an assumed core count
- `grep -rnE 'tmp_path|/tmp/|port|sqlite|\.db|os\.environ|scope="session"|scope="module"' tests/ conftest.py`: in place of an assumption that the tests share no files, ports, databases, env or session fixtures

## 3. The methods and tools
- `pip install pytest-xdist` then `pytest -n auto --dist loadscope` (try `--dist loadfile` and `worksteal` too): the parallel run itself, with the distribution mode chosen by measurement
- `hyperfine --warmup 1 --runs 5 'pytest -q' 'pytest -q -n auto' 'pytest -q -n auto --dist worksteal'`: wall-clock medians with spread, not a single timing
- `pip install pytest-randomly pytest-repeat` then `pytest -n auto -p randomly --count 3`: flushes out order and shared-state dependence
- `pidstat -u 1` (from `sysstat`, `pacman -S sysstat`) during a parallel run: confirms every core is busy and shows when the tail is a single straggler
- `pytest --durations=0` under `-n auto`: shows how much time the slowest tests and per-worker fixture setup cost

## 4. What outside the agent shows it is right
- A junit diff: the set of passing and failing tests from `pytest -n auto --junitxml=/tmp/par.xml` matches `/tmp/serial.xml` exactly, on 5 consecutive runs with different `-p randomly` seeds, and none of them is flaky
- hyperfine's median wall time for the parallel run is at most max(serial ÷ `nproc` × 1.3, longest single test + 5 s), with a spread under 10%. That target is the reasonable one for an embarrassingly parallel suite
- The CI test job passes with `-n auto`, and its logged duration drops by the same ratio

## Rewritten prompt
> "Run the test in parallel." Start from a serial baseline: `pytest --durations=0` saved to
> `/tmp/serial-durations.txt`, a `--junitxml=/tmp/serial.xml` record, `nproc` here and on the
> CI runner, the CI test job's own log, and a grep of `tests/` and `conftest.py` for shared tmp
> files, ports, databases, env vars and session/module fixtures. Make the suite run under
> pytest-xdist (`-n auto`). Choose `--dist` (loadscope, loadfile or worksteal) by `hyperfine
> --runs 5`, not by guess. Isolate any shared state that `pytest-randomly` with `--count 3`
> exposes, and watch `pidstat -u 1` so the tail is not a single straggler. It is done when the
> parallel run's junit results match the serial ones exactly across 5 randomly seeded runs with
> no flakes, hyperfine's median is at most max(serial ÷ cores × 1.3, longest test + 5 s) with
> under 10% spread, and the CI job passes with `-n auto` at a correspondingly shorter logged
> time.
