"""The kept skill-cut runs the tests read. The runs live out of git (`docs/evals.md`); the few the
tests need are packed in `fixtures/skill-cut.tar.xz`, laid out as the eval's data folder holds
them: `cases/lead/`, `run-1/` and the cases it was answered against in
`fixture/steps-of-run-1.json`, and the `run.json`, `key.json` and `scores.json` of the five runs
the A/B harness rescores."""

import tarfile

import pytest

from testing.paths import REPO

PACKED = REPO / "features" / "evals" / "tests" / "fixtures" / "skill-cut.tar.xz"


@pytest.fixture
def kept_runs(tmp_path):
    """A fresh copy of the packed runs, a folder the eval may write into."""
    data = tmp_path / "skill-cut"
    with tarfile.open(PACKED) as packed:
        packed.extractall(data, filter="data")
    return data
