"""The root `conftest.py` loads what every test shares as pytest plugins: the isolation of
`testing/jstack_fixtures.py`, and the test modules other tests import. So a test in a feature's
own folder, `features/<name>/tests`, gets the same autouse fixtures as one in `tests/`, and
imports a helper of `tests/` by its bare name. Here a test is copied into such a folder of a
copy of the checkout and run there, by a pytest of its own started as a command, so the folder
it starts in is not on its path."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

from testing.paths import REPO

PROBE = """\
import os
import shutil
from pathlib import Path

from test_jbus_kitchen import NOW


def test_it_runs_isolated_like_any_test_of_tests(tmp_path_factory):
    base = tmp_path_factory.getbasetemp()
    config = Path(os.environ["XDG_CONFIG_HOME"]) / "jstack" / "config.toml"
    assert config.is_relative_to(base)
    assert 'timezone = "America/New_York"' in config.read_text()
    assert Path(shutil.which("systemd-run")).is_relative_to(base)
    assert Path(os.environ["LIMITS"]).is_relative_to(base)
    assert NOW
"""


def test_a_test_in_a_features_own_folder_gets_the_isolation_and_the_shared_helpers(tmp_path):
    copy = tmp_path / "jstack"
    copy.mkdir()
    for name in ("conftest.py", "pyproject.toml"):
        shutil.copy2(REPO / name, copy / name)
    for name in ("src", "testing"):
        (copy / name).symlink_to(REPO / name)
    (copy / "features").mkdir()
    for feature in (REPO / "features").iterdir():
        (copy / "features" / feature.name).symlink_to(feature)
    probe = copy / "features" / "x" / "tests" / "test_probe.py"
    probe.parent.mkdir(parents=True)
    probe.write_text(PROBE)
    env = {name: value for name, value in os.environ.items() if not name.startswith("PYTEST_")}
    ran = subprocess.run(
        [Path(sys.executable).parent / "pytest", "-q", "-p", "no:cacheprovider", "-p", "no:xdist"]
        + ["--basetemp", str(tmp_path / "base"), str(probe)],
        cwd=copy,
        env=env | {"XDG_CONFIG_HOME": "/nonexistent", "LIMITS": "/nonexistent"},
        capture_output=True,
        text=True,
    )
    assert ran.returncode == 0 and "1 passed" in ran.stdout, ran.stdout + ran.stderr
