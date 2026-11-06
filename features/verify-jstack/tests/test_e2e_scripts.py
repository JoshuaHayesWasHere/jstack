"""The two deterministic end-to-end scripts of `features/verify-jstack/e2e/`. Each is run as its
README says, `bash <script>`, twice, and the two transcripts must end `e2e: ok` and be the same
bytes: a script that drifts from the harness fails here, and so does one that starts printing a
path, a pid or a time it does not mask. Both source features/verify-jstack/e2e/lib.sh."""

import os
import subprocess

import pytest

from testing.paths import REPO

SCRIPTS = [
    "features/verify-jstack/e2e/two-sandboxes.sh",
    "features/verify-jstack/e2e/refusals.sh",
]


@pytest.mark.parametrize("script", SCRIPTS)
def test_an_e2e_script_passes_and_prints_the_same_lines_on_a_rerun(script, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("VERIFY_JSTACK_")}
    runs = [
        subprocess.run(
            ["bash", REPO / script],
            env={**env, "TMPDIR": str(tmp_path)},
            capture_output=True,
            text=True,
            timeout=120,
        )
        for _ in range(2)
    ]

    for ran in runs:
        assert ran.returncode == 0, ran.stdout + ran.stderr
        assert ran.stdout.splitlines()[-1] == "e2e: ok"
    assert runs[0].stdout == runs[1].stdout
