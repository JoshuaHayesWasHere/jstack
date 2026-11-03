"""`move` keeps the copy of jstack that this machine's commands run from at main's last green tip.

jbus, jmerge and jgauge are what revert or fix a red main ("Main is not red" in
`features/jmerge/docs/jmerge.md`), so a main that breaks must not break them. They do not run
from the live checkout, where any branch or any red tip of main may be checked out. They run
from the green copy: a clone of the checkout at `${XDG_DATA_HOME:-~/.local/share}/jstack/green`
(`path`), which `install.sh` makes (`make`) once jbus's config names the checkout as a project.
uv's tool `jstack`, whose commands the units run, is an editable install of the copy, and each
harness's layout links its `source` to it, so `uv run --project "$T/../source" jbus` in a home
or a wake runs it too.

The copy keeps the checkout it was made from in `.git/jstack-checkout` (`of`), and fetches from
the checkout's own origin. Each pass of that checkout's project moves it (`move`) to `green`,
the last tip of main whose required check passed, which `jbus.mainmoved.tell` keeps in
`main.json` (`jmerge.mainjson`), which only ever names a later tip of main. Before it says the
move is done, it imports the copy's commands (`IMPORTS`) with the pass's own Python. A copy that
does not import goes back to the tip it was at, the pass raises a condition for that tip, and
`green.json` in the project's state keeps it as `refused`, so no later pass tries it again. So a
main whose check failed never reaches the copy, and neither does a tip whose check passed but
which does not import here. When the move changed `pyproject.toml` or `uv.lock`, it installs the
tool again, as `install.sh` does, so a new command or package root is on the tool's path.

Each move prints one line, `green <project>: the commands now run from <new 12>, in place of
<old 12>`, which the pass's log keeps. A crew's worktree is not the copy: `uv run` there runs that
tree's own code, and the copy moves no file of it.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

from jbus import read_json, verbs, write_json
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
"""The files whose change makes `move` install the tool again."""

FILE = "green.json"
"""The project's record of the tip the copy would not import, `{"refused": <sha>}`."""

NO_IMPORT = "the green copy does not import"
MOVE_FAILED = "the green copy could not move"


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


def imports(copy: Path) -> str:
    """Import the copy's commands with this Python and its packages, the copy's roots first.
    Return "" when they import, or the last line the import printed."""
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join(str(one) for one in sources(copy)),
        "PYTHONSAFEPATH": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    said = proc.run(sys.executable, "-c", IMPORTS, cwd=copy, env=env, timeout=120)
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


def make(checkout: Path, copy: Path, sha: str) -> str:
    """Make `copy` a green copy of `checkout` at `sha`. Return "" when it is made, or why it is
    not.

    It is a repo of its own and not a worktree, which the checkout would list, and a test or
    a sandbox that installs from the checkout would add one there. It holds no history, only
    each commit it was at: it fetches `sha` from the checkout, and every later tip from the
    checkout's origin, which its own `origin` names."""
    if copy.exists():
        return f"{copy} is there already"
    copy.mkdir(parents=True)
    if why := _fill(checkout, copy, sha):
        shutil.rmtree(copy)
    return why


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
    if not fetch(copy, green):
        run.condition("green", MOVE_FAILED, f"{green[:12]} is not in the copy's origin")
        return
    moved = _checkout(copy, green)
    if moved.returncode != 0:
        why = f"to {green[:12]}: {_said(moved)}"
        run.condition("green", MOVE_FAILED, why, key=green[:12])
        return
    if broke := imports(copy):
        _checkout(copy, held)
        write_json(run.state / FILE, {"refused": green})
        why = f"at {green[:12]}, so it stays at {held[:12]}: {broke}"
        run.condition("green", NO_IMPORT, why, key=green[:12])
        run.say(f"green {run.project.name}: {green[:12]} does not import, kept {held[:12]}")
        return
    changed = _git(copy, "diff", "--quiet", held, green, "--", *BUILT).returncode != 0
    if changed and (why := _reinstall(copy)):
        run.condition("green", MOVE_FAILED, f"uv tool install at {green[:12]}: {why}")
    run.say(
        f"green {run.project.name}: the commands now run from {green[:12]}, in place of {held[:12]}"
    )


STEPS = (verbs.Step("close", 45, "green.move", lambda half: move(half.run), ()),)
