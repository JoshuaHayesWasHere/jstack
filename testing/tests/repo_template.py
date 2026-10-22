"""The repo a test copies in place of building its own with git. The first test in each worker that
copies it builds it.

A kitchen's `repo` (`test_jbus_kitchen`), `Home` and `Merged` (`test_home_merge`) each made the same
one-commit checkout and its bare origin with up to seven git processes. Now the first test in a
worker that copies the repo builds it in `root`, which conftest's `kitchen_template` gives, and
every copy after starts no process. This module imports nothing of jstack, so
`scripts/select_tests.py` never selects this module's importers for a change to jstack's code.
"""

import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

root = None
template = None


IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.com")
QUIET = ("-c", "maintenance.auto=false", "-c", "gc.auto=0")
LOCKS = shutil.ignore_patterns("*.lock")


class Template(NamedTuple):
    """The repos a test copies in place of building its own, all at one commit of `main`.

    `plain` is a checkout with that one commit and no remote, as `test_home_merge`'s `Home`
    makes. `checkout` is the same with `origin`, a bare repo that has `main` as its default.
    """

    plain: Path
    checkout: Path
    origin: Path
    main: str


def built(root):
    """Build the template in `root` and return it. Before the template, each kitchen's `repo` ran
    these same git processes for every test.

    The fetch writes the origin's path into FETCH_HEAD, and a copy would keep it. Nothing in the
    kitchen reads the file, so the build deletes it. A build that failed partway leaves its files in
    `root`, so the build empties the root first. Then, if the next try fails, it fails for its own
    reason and not because of the leftover files. A commit or a push starts git's auto maintenance
    in a detached process. That process writes and removes a lock file while a test copies the
    checkout, so the build turns auto maintenance off (`QUIET`). The push's receive-pack reads only
    the origin's own config, so the build turns auto maintenance off in that config too
    (`receive.autogc`).

    """
    plain, checkout, origin = root / "plain", root / "checkout", root / "origin.git"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    for args, cwd in (
        (("init", "-q", "-b", "main", str(plain)), root),
        (("commit", "-q", "--allow-empty", "-m", "start"), plain),
    ):
        subprocess.run(["git", *IDENTITY, *QUIET, *args], cwd=cwd, check=True)
    shutil.copytree(plain, checkout, symlinks=True, ignore=LOCKS)
    for args, cwd in (
        (("init", "-q", "--bare", "-b", "main", str(origin)), root),
        (("config", "receive.autogc", "false"), origin),
        (("remote", "add", "origin", str(origin)), checkout),
        (("push", "-q", "origin", "main"), checkout),
        (("fetch", "-q", "origin"), checkout),
        (("remote", "set-head", "origin", "main"), checkout),
    ):
        subprocess.run(["git", *IDENTITY, *QUIET, *args], cwd=cwd, check=True)
    (checkout / ".git" / "FETCH_HEAD").unlink()
    main = subprocess.run(
        ["git", "rev-parse", "main"], cwd=plain, check=True, capture_output=True, text=True
    )
    return Template(plain, checkout, origin, main.stdout.strip())


def copied(template, checkout, origin):
    """Copy the template's checkout and origin to these paths, and start no process.

    The build wrote the template's path in one place only, the checkout's `remote.origin.url`, and
    the copy keeps it there. This points that URL at the copy's own origin, so a push or a fetch
    never reaches the template. The template has no worktree, so there is no `gitdir` to point
    anywhere. The copy leaves out any lock file: the lock belongs to a git process in the template,
    and in a copy it would make git refuse to run.

    """
    shutil.copytree(template.checkout, checkout, symlinks=True, dirs_exist_ok=True, ignore=LOCKS)
    shutil.copytree(template.origin, origin, symlinks=True, dirs_exist_ok=True, ignore=LOCKS)
    config = checkout / ".git" / "config"
    text, was = config.read_text(), f"\turl = {template.origin}\n"
    if text.count(was) != 1:
        raise AssertionError(f"the template's config names its origin {text.count(was)} times")
    config.write_text(text.replace(was, f"\turl = {origin}\n"))


def templated():
    """The worker's template, built on the first call."""
    global template
    if template is None:
        if root is None:
            raise RuntimeError("no template root: conftest's kitchen_template gives it")
        template = built(root)
    return template
