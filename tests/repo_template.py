"""The repo a test copies in place of building its own with git: built once for each worker.

A kitchen's `repo` (`test_jbus_kitchen`), `Home` and `Merged` (`test_home_merge`) each made the
same one-commit checkout and its bare origin with up to seven git processes. Now the first copy
in a worker builds it in `root`, which conftest's `kitchen_template` gives, and every copy after
starts no process. It imports nothing of jstack, so the tests that import it rest on nothing
the test selection reads as a change.
"""

import shutil
import subprocess
from pathlib import Path
from typing import NamedTuple

root = None
template = None


IDENTITY = ("-c", "user.name=t", "-c", "user.email=t@example.com")


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
    """The template, made in `root` by the git processes a kitchen's `repo` started each time.

    The fetch names the origin's path in FETCH_HEAD, which a copy would keep, so the file
    goes: nothing in the kitchen reads it. A build that failed partway leaves its files in
    `root`, so the root is emptied first, and the next try fails on its own cause.
    """
    plain, checkout, origin = root / "plain", root / "checkout", root / "origin.git"
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True)
    for args, cwd in (
        (("init", "-q", "-b", "main", str(plain)), root),
        (("commit", "-q", "--allow-empty", "-m", "start"), plain),
    ):
        subprocess.run(["git", *IDENTITY, *args], cwd=cwd, check=True)
    shutil.copytree(plain, checkout, symlinks=True)
    for args, cwd in (
        (("init", "-q", "--bare", "-b", "main", str(origin)), root),
        (("remote", "add", "origin", str(origin)), checkout),
        (("push", "-q", "origin", "main"), checkout),
        (("fetch", "-q", "origin"), checkout),
        (("remote", "set-head", "origin", "main"), checkout),
    ):
        subprocess.run(["git", *IDENTITY, *args], cwd=cwd, check=True)
    (checkout / ".git" / "FETCH_HEAD").unlink()
    main = subprocess.run(
        ["git", "rev-parse", "main"], cwd=plain, check=True, capture_output=True, text=True
    )
    return Template(plain, checkout, origin, main.stdout.strip())


def copied(template, checkout, origin):
    """The template's checkout and origin, copied to these paths, with no process started.

    The copy's `remote.origin.url` is the one path the template wrote into it, and it is
    pointed at the copy's own origin, so a push or a fetch never reaches the template. The
    template has no worktree, so there is no `gitdir` to point anywhere.
    """
    shutil.copytree(template.checkout, checkout, symlinks=True, dirs_exist_ok=True)
    shutil.copytree(template.origin, origin, symlinks=True, dirs_exist_ok=True)
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
