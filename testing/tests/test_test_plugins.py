"""The root `conftest.py` loads what every test shares, and it loads it as pytest plugins: the
isolating fixtures of `testing/jstack_fixtures.py`, and the test modules other tests import. So a
test in a feature's own folder, `features/<name>/tests`, gets the same autouse fixtures as one in
`tests/`, and imports a helper of `tests/` by its bare name. Here the test copies a test into such a
folder in a copy of the checkout. A separate pytest, started as a command, runs the copied test
there. In that run, the folder pytest starts in is not on its path."""

import os
import shutil
import subprocess
import sys
import time
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


def test_the_fake_systemd_run_starts_its_command_in_a_session_of_its_own_with_no_setsid(
    no_user_units, tmp_path
):
    """A Mac has no `setsid`, and the fake starts its command there too. A fake that started
    nothing and said nothing left each fresh check of `jmerge` unrun on macOS."""
    out = tmp_path / "session"
    write = "import os, sys; open(sys.argv[1] + '.part', 'w').write(str(os.getsid(0))); "
    write += "os.rename(sys.argv[1] + '.part', sys.argv[1])"
    empty = tmp_path / "empty"
    empty.mkdir()
    ran = subprocess.run(
        [no_user_units / "systemd-run", "--user", "--quiet", "--"]
        + [sys.executable, "-c", write, str(out)],
        env=os.environ | {"PATH": str(empty)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    end = time.monotonic() + 10
    while not out.exists():
        assert time.monotonic() < end, f"the fake started nothing with no setsid: {ran}"
        time.sleep(0.05)
    assert ran.returncode == 0
    assert int(out.read_text()) != os.getsid(0)
