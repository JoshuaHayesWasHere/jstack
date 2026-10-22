# A test of `make check` failed on a bound

| Line | Meaning | Do this |
|---|---|---|
| `Failed: Timeout (>120.0s) from pytest-timeout` | The test named above it waited 120 s on something that never answered: a browser, a server or a subprocess. The run went on to the next test. | Run that test alone with `uv run pytest <its id>`. The stack under the line shows where it waited. |
| `the browser did not finish in 60 s and was stopped` | A browser test's browser never printed the page. It was stopped with every process it started, and its stderr follows the line. | Run the test again. If it stops again, try another build: `JSTACK_TEST_BROWSER=<path> make check-browser`. The browser workflow names Google Chrome on every runner, as a Chromium snapshot does this now and then. |
