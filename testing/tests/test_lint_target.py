"""`make lint` runs every command CI's lint job runs after it, so a desk check that passed
`make lint` (as `make check-fast PART=touched` runs it) does not fail CI's lint on a rule only
CI ran: #1346 passed at the desk and failed CI on the repo standard's size cap. The standard's
conform runs in CI's lint job only through `make lint`, so `make lint` must run it."""

import subprocess

from test_workflows import CHECK, steps
from testing.paths import REPO


def test_make_lint_runs_each_command_that_cis_lint_job_runs_after_it():
    found, _ = steps(CHECK.read_text(), "lint")
    runs = [step["run"] for step in found if "run" in step]
    after = runs[next(i for i, run in enumerate(runs) if run.startswith("make lint")) + 1 :]
    planned = subprocess.run(
        ["make", "-n", "--no-print-directory", "lint"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert "uv run repo-standard conform" in planned
    assert [run for run in after if run not in planned] == []
