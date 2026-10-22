## 1. What a top professional would do
A test-infrastructure / performance engineer. Before adding `-n auto`, they would measure where the suite's wall time actually goes (slow tests, session fixtures, imports, I/O waits), because parallelism only helps CPU-spread work and can make heavy shared setup slower. They would also prove the tests are independent by running them in random order and in isolation, since parallel runs turn hidden shared state (temp files, ports, a shared DB, module globals) into intermittent failures.

## 2. The rawest material
- `pytest --durations=0 -q` on the current serial suite: in place of a remembered sense that "the tests are slow"
- `conftest.py` and every `scope="session"` / `scope="module"` fixture (`grep -rn "scope=" tests/ conftest.py`): in place of an assumption that the tests are independent
- `nproc` and `free -h` on this machine, and the runner spec from the CI config (`.github/workflows/*.yml` or equivalent): in place of a guessed worker count
- The last CI run's own log (`gh run view --log <run-id>`): in place of the reported suite time
- `grep -rnE "tmp|/tmp|port|sqlite|\.db|os\.environ" tests/`: in place of a belief that no tests share files, ports, env or a database

## 3. The methods and tools
- `pytest --durations=0`: a profile before the change, showing whether a few long tests or fixture setup dominate the wall time
- `pytest -p randomly` (`pip install pytest-randomly`) over several seeds: to surface order dependence before parallelism hides it behind flakiness
- `pytest -n auto --dist loadfile` / `--dist loadscope` (`pip install pytest-xdist`): parallel execution, with the distribution mode chosen to fit the fixture scopes
- `hyperfine --warmup 1 --runs 10 'pytest -q' 'pytest -q -n auto'` (`pacman -S hyperfine`): a mean and a spread for the before and after wall time, not a single run
- `pidstat -u 1` or `perf stat -- pytest -q -n auto`: to confirm the workers saturate the cores and are not blocked on I/O or a lock
- `for i in $(seq 20); do pytest -q -n auto -p randomly || break; done`: a repeated run to catch flakes that only appear under parallelism

## 4. What outside the agent shows it is right
- `hyperfine` reports the parallel suite's mean wall time within 1.5× of (serial time ÷ `nproc`), and gives a non-overlapping spread against the serial baseline. That is an aggressive target, and it is the right one when the profile shows CPU-bound tests.
- 20 consecutive `pytest -n auto -p randomly` runs on different seeds all pass, with the same test count as the serial run.
- The next CI run's own log shows the reduced suite time, and its passed test count equals the serial run's.

## Rewritten prompt
```
"run the test in parallel"

Start from the raw data, not impressions: run `pytest --durations=0 -q` serially and keep the output.
Read conftest.py and every session- or module-scoped fixture. Grep tests/ for shared temp paths,
ports, sqlite/.db files and os.environ writes. Record `nproc` here and the CI runner's core count
from its workflow config. Before changing anything, run the suite under `pytest -p randomly` over
several seeds, and fix or isolate any order-dependent test you find (tmp_path, per-worker DB/port
via worker_id).

Then add pytest-xdist and run with `-n auto`, choosing `--dist loadfile` or `--dist loadscope` to fit
the fixture scopes. Use `pidstat -u 1` to confirm the workers saturate the cores.

It is done when:
(a) `hyperfine --warmup 1 --runs 10 'pytest -q' 'pytest -q -n auto'` shows the parallel mean within
1.5× of serial ÷ nproc, with spreads that do not overlap;
(b) 20 consecutive `pytest -q -n auto -p randomly` runs pass with the same test count as the serial run;
(c) the next CI run's log shows the shorter suite time with an unchanged passed count.
Report the before/after hyperfine table and any test you had to isolate, and why.
```
