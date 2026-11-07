"""`move` keeps the copy of jstack that this machine's commands run from at main's last green tip.

jbus, jmerge and jgauge are what revert or fix a red main ("Main is not red" in
`features/jmerge/docs/jmerge.md`), so a main that breaks must not break them. They do not
run from the live checkout, where any branch or any red tip of main may be checked out. They
run from the green copy at `${XDG_DATA_HOME:-~/.local/share}/jstack/green` (`path`), which
`install.sh` makes (`make`) once jbus's config names the checkout as a project. The copy is a link
to a tree of its own for each tip, a clone of the checkout at `green.d/<sha>` beside it (`trees`).
uv's tool `jstack`, whose commands the units run, is an editable install of the copy, and each
harness's layout links its `source` to it, so `uv run --project "$T/../source" jbus` in a home
or a wake runs it too.

The copy keeps the checkout it was made from in `.git/jstack-checkout` (`of`), and fetches from
the checkout's own origin. Each pass of that checkout's project moves it (`move`) to `green`,
the last tip of main whose required check passed, which `jbus.mainmoved.tell` keeps in
`main.json` (`jmerge.mainjson`), which only ever names a later tip of main. The move makes the
new tip's tree beside the one the link names and imports its commands (`IMPORTS`) with the pass's
own Python, or, where the tip changed `pyproject.toml` or `uv.lock`, in an environment uv makes as
the tool's install will. Only then does it point the link at the new tree, in one rename, so a
command that starts runs one tip or the other and never a tree half way between them. A tree that
does not import is removed, the pass raises a condition for that tip, and `green.json` in the
project's state keeps it as `refused`, so no later pass tries it again. So a main whose check
failed never reaches the copy, nor does a tip whose check passed but which fails to import
here. Then it installs the tool again, as `install.sh` does: the editable install's paths name
the tree itself and not the link, so the tool runs the new tip only once it is installed from
it. Where uv cannot install it, the link goes back to the tree the tool runs, the new tree goes,
and the next pass tries again. The tree the link named before stays until the next move, for a
command that still runs in it. Last, it puts each harness's layout again from the new tip
(`jinstall.green.relink`), as `install.sh` would: the layouts link the copy's files one by one,
so a file main added would otherwise reach no harness, and one it dropped would leave a link that
dangles, until the next install. With each layout it puts the links under the harness's skills
root and the entries of its hooks file, so a skill or hook main adds is live and one it drops is
gone. Where the move changed a systemd unit the install linked through the copy, it has the user
manager read the units again (`_reload`), since systemd reads a unit's file only on a reload.

Each move prints one line, `green <project>: the commands now run from <new 12>, in place of
<old 12>`, which the pass's log keeps. A crew's worktree is not the copy: `uv run` there runs that
tree's own code, and the copy moves no file of it.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from jbus import launchd, read_json, verbs, write_json
from jbus.passes import Pass
from jmerge import mainjson
from jsettings import proc

MARK = "jstack-checkout"
"""The file in the copy's `.git` that names the checkout it was made from."""

IMPORTS = (
    "import jbus, jbus.cli, jbus.poll, jbus.verbs; jbus.verbs.ranked(jbus.__path__); "
    "import jmerge.cli, jgauge.cli"
)
"""What the copy must import before a move counts as done: each command the units run, and every
module of jbus that declares a step of a pass, as `jbus steps` imports them."""

BUILT = ("pyproject.toml", "uv.lock")
"""The files whose change makes `move` import the new tip in an environment uv makes for it."""

FILE = "green.json"
"""The project's record of the tip the copy would not import, `{"refused": <sha>}`."""

NO_IMPORT = "the green copy does not import"
MOVE_FAILED = "the green copy could not move"
UNLINKED = "the harness does not link the green copy's files"


def path(env: Mapping[str, str] | None = None, home: Path | None = None) -> Path:
    """Where the green copy is: `${XDG_DATA_HOME:-~/.local/share}/jstack/green`."""
    env = os.environ if env is None else env
    data = env.get("XDG_DATA_HOME") or (home or Path.home()) / ".local" / "share"
    return Path(data) / "jstack" / "green"


def _git(where: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return proc.run("git", "-C", str(where), *args, timeout=600)


def of(copy: Path) -> Path | None:
    """The checkout that `copy` is the green copy of, or None where `copy` is no green copy."""
    try:
        named = (copy / ".git" / MARK).read_text().strip()
    except OSError:
        return None
    return Path(named) if named else None


def at(copy: Path) -> str:
    """The commit the copy holds, or "" where git cannot say."""
    said = _git(copy, "rev-parse", "--verify", "-q", "HEAD^{commit}")
    return said.stdout.strip() if said.returncode == 0 else ""


def sources(copy: Path) -> list[Path]:
    """The copy's package roots, as `install.sh` puts them on PYTHONPATH."""
    return [one for one in (copy / "src", *sorted(copy.glob("features/*/src"))) if one.is_dir()]


def imports(copy: Path, fresh: bool = False) -> str:
    """Import the copy's commands with this Python and its packages, the copy's roots first.
    With `fresh`, import them in a new environment that uv makes from the copy's
    `pyproject.toml`, as `uv tool install --editable` does, and not with this Python's packages.
    Return "" when they import, or the last line the import printed."""
    python = [sys.executable]
    if fresh:
        python = ["uv", "run", "--isolated", "--no-project", "--with-editable", str(copy), "python"]
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(str(one) for one in sources(copy)),
        "PYTHONSAFEPATH": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    said = proc.run(*python, "-c", IMPORTS, cwd=copy, env=env, timeout=600)
    return "" if said.returncode == 0 else _said(said)


def _said(done: subprocess.CompletedProcess[str]) -> str:
    lines = (done.stderr or done.stdout).strip().splitlines()
    return lines[-1] if lines else f"exit {done.returncode}"


def fetch(copy: Path, sha: str, source: str = "origin") -> bool:
    """Fetch the one commit `sha` into the copy, with no history behind it, and say whether
    the copy has it then."""
    if not _has(copy, sha):
        _git(copy, "fetch", "-q", "--depth", "1", source, sha)
    return _has(copy, sha)


def trees(copy: Path) -> Path:
    """Where the copy's trees are, one for each tip it was at: `<copy>.d`, beside it."""
    return copy.with_name(f"{copy.name}.d")


def make(checkout: Path, copy: Path, sha: str) -> str:
    """Make `copy` a green copy of `checkout` at `sha`. Return "" when it is made, or why it is
    not.

    Each tree is a repo of its own and not a worktree, which the checkout would list, and a test
    or a sandbox that installs from the checkout would add one there. It holds no history, only
    its one commit, which it fetches from the checkout, or else from the checkout's origin, which
    its own `origin` names."""
    if copy.exists() or copy.is_symlink():
        return f"{copy} is there already"
    tree = trees(copy) / sha
    if why := _grow(checkout, tree, sha):
        return why
    _point(copy, tree)
    return ""


def _grow(checkout: Path, tree: Path, sha: str) -> str:
    """Make `tree` a clone of `checkout` at `sha`. Return "" when it is made, or why not, with no
    tree left then."""
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    why = _fill(checkout, tree, sha)
    if why:
        shutil.rmtree(tree)
        with contextlib.suppress(OSError):
            tree.parent.rmdir()
    return why


def _point(copy: Path, tree: Path) -> None:
    """Point the link `copy` at `tree` in one rename."""
    new = copy.with_name(f".{copy.name}.new")
    new.unlink(missing_ok=True)
    new.symlink_to(os.path.relpath(tree, copy.parent))
    os.replace(new, copy)


def _built(tree: Path) -> list[bytes | None]:
    return [(tree / one).read_bytes() if (tree / one).is_file() else None for one in BUILT]


def _fill(checkout: Path, copy: Path, sha: str) -> str:
    origin = _git(checkout, "remote", "get-url", "origin").stdout.strip()
    made = _git(copy, "init", "-q")
    if made.returncode != 0:
        return f"git init: {_said(made)}"
    (copy / ".git" / MARK).write_text(f"{checkout}\n")
    if origin:
        _git(copy, "remote", "add", "origin", origin)
    if not fetch(copy, sha, f"file://{checkout.resolve()}") and not fetch(copy, sha):
        return f"git fetch: {sha[:12]} is in neither {checkout} nor its origin"
    moved = _checkout(copy, sha)
    return f"git checkout: {_said(moved)}" if moved.returncode != 0 else ""


def _has(copy: Path, sha: str) -> bool:
    return _git(copy, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def _checkout(copy: Path, sha: str) -> subprocess.CompletedProcess[str]:
    return _git(copy, "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", sha)


def _reinstall(copy: Path) -> str:
    """Install uv's tool `jstack` again from the copy. Return "" when uv did, or why not."""
    said = proc.run("uv", "tool", "install", "--editable", str(copy), "--reinstall", timeout=600)
    return "" if said.returncode == 0 else _said(said)


def _reload(copy: Path, before: Path, after: Path) -> str:
    """Have systemd read again each unit the install linked through the copy whose file the move
    changed, since systemd reads a unit's file only on a reload: a timer main changed runs as
    main has it from this pass on, and not from the next install. Return "" where there was
    nothing to reload or it reloaded, or what went wrong."""
    if launchd.manager() != "systemd":
        return ""
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    units, through = Path(config) / "systemd" / "user", str(copy) + os.sep
    changed = []
    for link in sorted(units.glob("*")) if units.is_dir() else ():
        target = os.readlink(link) if link.is_symlink() else ""
        if not target.startswith(through):
            continue
        inside = target.removeprefix(through)
        old, new = before / inside, after / inside
        if not (old.is_file() and new.is_file() and old.read_bytes() == new.read_bytes()):
            changed.append(link.name)
    if not changed:
        return ""
    said = proc.run("systemctl", "--user", "daemon-reload", timeout=60)
    if said.returncode != 0:
        return f"systemctl --user daemon-reload, for {' '.join(changed)}: {_said(said)}"
    return f"systemd read {' '.join(changed)} again"


def move(run: Pass, copy: Path | None = None) -> None:
    """Move the green copy of the project's checkout to main's green tip, when there is such a
    copy and the tip is newer than the one it holds."""
    copy = path() if copy is None else copy
    made_from = of(copy)
    if made_from is None or made_from.resolve() != run.project.checkout.resolve():
        return
    green = mainjson.read(run.state).green
    held = at(copy)
    refused = read_json(run.state / FILE, {}).get("refused")
    if not green or not held or green in (held, refused):
        return
    tree = trees(copy) / green
    if why := _grow(run.project.checkout, tree, green):
        run.condition("green", MOVE_FAILED, f"to {green[:12]}: {why}", key=green[:12])
        return
    changed = _built(copy) != _built(tree)
    if broke := imports(tree, fresh=changed):
        shutil.rmtree(tree)
        write_json(run.state / FILE, {"refused": green})
        why = f"at {green[:12]}, so it stays at {held[:12]}: {broke}"
        run.condition("green", NO_IMPORT, why, key=green[:12])
        run.say(f"green {run.project.name}: {green[:12]} does not import, kept {held[:12]}")
        return
    before = copy.resolve()
    _point(copy, tree)
    if why := _reinstall(copy):
        _point(copy, before)
        shutil.rmtree(tree)
        why = f"uv tool install at {green[:12]}: {why}"
        run.condition("green", MOVE_FAILED, why, key=green[:12])
        return
    for old in trees(copy).iterdir():
        if old.is_dir() and old.resolve() not in (before, tree.resolve()):
            shutil.rmtree(old)
    from jinstall.green import relink

    for why in relink(copy):
        run.condition("green", UNLINKED, f"at {green[:12]}: {why}", key=green[:12])
    if why := _reload(copy, before, tree):
        run.say(f"green {run.project.name}: {why}")
    run.say(
        f"green {run.project.name}: the commands now run from {green[:12]}, in place of {held[:12]}"
    )


STEPS = (verbs.Step("close", 45, "green.move", lambda half: move(half.run), ()),)
