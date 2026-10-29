"""Where jstack's state is, and which repo a directory is of: the one place each command reads them.

- `homes_dir`: the homes' state, one directory per repo, `JBUS_HOME_DIR` or `~/.local/state/home`.
  jbus, `jmerge`, jbriefs and the home hooks all read it here.
- `jbus_config_dir` and `jbus_state_dir`: jbus's config, `JBUS_CONFIG_DIR` or `~/.config/jbus`,
  and its state, `JBUS_STATE_DIR` or `~/.local/state/jbus`. While a test runs, each refuses the
  machine's own directory (`RealDir`).
- `main_checkout` and `repo_name`: the main checkout of the repo a directory is in, a worktree's
  too, from git's common directory, and that checkout's name, which names the repo's home.
"""

from __future__ import annotations

import os
import pwd
from collections.abc import Mapping
from pathlib import Path

from jsettings import proc


def homes_dir(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """The homes' state, one directory per repo: `JBUS_HOME_DIR`, or `~/.local/state/home`.
    `env` and `home` are this process's own environment and home unless a caller names another
    machine's."""
    env = os.environ if env is None else env
    named = env.get("JBUS_HOME_DIR")
    return Path(named) if named else (home or Path.home()) / ".local" / "state" / "home"


class RealDir(RuntimeError):
    """`RealDir` means a test reached the machine's own jbus config or state: one that set
    neither `JBUS_CONFIG_DIR` nor `JBUS_STATE_DIR`, or set one to the real directory."""


def _own(name: str, under: str) -> Path:
    """Return the directory `name` names, else `under` the home, and refuse the machine's own
    while a test runs (pytest sets `PYTEST_CURRENT_TEST`, and a process a test starts inherits
    it). The machine's own is under the account's home in the password database, which a test
    that points `HOME` at a home of its own does not change. Outside a test it is never asked
    for, so a uid with no entry there still gets its directory."""
    path = Path(os.environ.get(name) or Path.home() / under)
    test = os.environ.get("PYTEST_CURRENT_TEST", "").rsplit(" ", 1)[0]
    if not test:
        return path
    real = Path(pwd.getpwuid(os.getuid()).pw_dir) / under
    if path.expanduser().resolve() == real.resolve():
        raise RealDir(
            f"refused: the test {test} reached the real {real}: point {name} at the test's own"
            " directory, as the autouse fixture in testing/jstack_fixtures.py does"
        )
    return path


def jbus_config_dir() -> Path:
    return _own("JBUS_CONFIG_DIR", ".config/jbus")


def jbus_state_dir() -> Path:
    return _own("JBUS_STATE_DIR", ".local/state/jbus")


def common_dir(cwd: Path | str | None = None) -> Path | None:
    """git's common directory of the repo `cwd` is in (this process's own directory by default),
    absolute, or None where `cwd` is in no repo."""
    asked = proc.git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    said = asked.stdout.strip()
    return Path(said) if asked.returncode == 0 and said else None


def main_checkout(cwd: Path | str | None = None) -> Path | None:
    """The main checkout of the repo `cwd` is in, from a worktree too, or None where `cwd` is in
    no repo."""
    common = common_dir(cwd)
    return common.parent if common is not None else None


def repo_name(cwd: Path | str | None = None) -> str:
    """The name of the repo `cwd` is in, its main checkout's, from a worktree too, or an empty
    string where `cwd` is in no repo. It names the repo's home under `homes_dir`."""
    found = main_checkout(cwd)
    return found.name if found is not None else ""
