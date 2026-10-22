## 1. What a top professional would do
A test-infrastructure engineer would not just add `-n auto`. First they would find what limits the speedup: the slowest single test or fixture sets a floor that no number of workers gets under. Second, they would prove the tests are isolated, with no shared temp paths, ports, databases, env vars or session-scoped state. Only after that would they call the parallel run as trustworthy as the serial one.

## 2. The rawest material
- `pytest -q --durations=0 -p no:cacheprovider` (serial, full suite): replaces a remembered "the tests take a while"
- `pytest --junitxml=serial.xml`, the per-test outcomes and times: replaces "they all pass"
- `conftest.py` and every `scope="session"`/`scope="module"` fixture, plus `grep -rnE 'tmp|/tmp|port|sqlite|os\.environ|chdir' tests/`: replaces assuming the tests don't share state
- The CI job's own log for the test step (e.g. `.github/workflows/*.yml` and the last run's raw log): replaces the CI duration someone quoted
- `nproc`, `free -h`: replaces guessing how many workers the machine can feed

## 3. The methods and tools
- `pytest-xdist`: `pytest -n auto --dist loadfile` (or `--dist loadscope` / `worksteal`). This is the parallel runner, and the distribution mode is chosen from the durations profile, not by default. Install with `pip install pytest-xdist`.
- `pytest-randomly`: `pytest -p randomly -n auto` with several seeds. A random order exposes hidden ordering and shared-state dependencies before parallelism hides them behind luck. Install with `pip install pytest-randomly`.
- `hyperfine --warmup 1 --runs 5 'pytest -q' 'pytest -q -n auto'`: reports wall time as a mean with its spread instead of one run's number. Install with `pacman -S hyperfine`.
- `for i in {1..20}; do pytest -q -n auto -p randomly || break; done`: a repeat-run stress test for flakiness under contention.
- `/usr/bin/time -v pytest -n auto`: peak RSS, so the worker count fits in `free -h`.
- `diff <(xq serial.xml) <(xq parallel.xml)` (or a short `python -I` script over both junit files): checks that serial and parallel give the same set of passed, failed and skipped tests.

## 4. What outside the agent shows it is right
- The two junit XMLs, serial and parallel, list the identical pass/fail/skip set.
- 20 consecutive parallel runs with random seeds pass with zero failures.
- `hyperfine` shows parallel wall time at or under max(longest single test + fixture setup, serial time ÷ `nproc`) × 1.5. That is ambitious, and it is the standard the field holds a well-isolated suite to. If the target is missed, the durations profile has to name the test or fixture that is the floor.
- The CI job's log shows the test step's duration dropping, with the step green.

## Rewritten prompt
> "run the test in parallel". Start from the raw material, not from impressions: a serial
> `pytest --durations=0 --junitxml=serial.xml` run, `conftest.py` and every session- or
> module-scoped fixture, a grep of `tests/` for shared temp paths, ports, databases, env vars
> and `chdir`, the CI test step's own log, and `nproc` / `free -h`. Use pytest-xdist
> (`-n auto`, with `--dist` chosen from the durations profile), pytest-randomly over several
> seeds to flush out order and shared-state dependencies, `hyperfine --runs 5` to compare serial
> and parallel wall time with its spread, and `/usr/bin/time -v` to size the worker count to
> memory. Fix the isolation bugs you find rather than marking tests serial, unless a test truly
> needs exclusivity. Done when: the serial and parallel junit XMLs show the same pass/fail/skip
> set; 20 consecutive `pytest -n auto -p randomly` runs pass; and hyperfine puts parallel wall
> time at or under 1.5× max(longest single test + its setup, serial time ÷ `nproc`), or the
> durations profile names the test or fixture that sets the floor. The CI test step's log
> must show the shorter, green run.
