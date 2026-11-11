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
command that still runs in it.

The move's steps are not one write, so `green.json` keeps the step it owes (`MOVE`): written
before the link moves, as `install`, then `relink` once uv installed the tool, and gone once
the layouts are put. Each pass resumes an owed step (`_resume`) before it reads main.json, so a
pass that dies with the link at the new tree and the tool at the old one, the units' 203/EXEC,
is finished by the next pass, and a relink that is refused is asked again on each pass. Since a
pass resumes first, it starts no new move while one owes its install; one that owes a relink is
done by the newer move. A move whose install fails goes back (`_back`): it owes the install of the
tip it went back to, points the link there and installs the tool again from it, since uv may have
removed ~/.local/bin/jbus before it failed, then relinks. It puts back the reload systemd was owed
before the move, so no reload runs for the tip it removed.
`features/jbus/spec/GreenMove.tla` checks the steps with a death between any two.

After the install, the move puts each harness's layout again from the new tip
(`jinstall.green.relink`), as `install.sh` would: the layouts link the copy's files one by one,
so a file main added would otherwise reach no harness, and one it dropped would leave a link that
dangles, until the next install. With each layout it puts the links under the harness's skills
root and the entries of its hooks file, so a skill or hook main adds is live and one it drops is
gone. Then, on the first pass at a tip, it puts the units to work as the install would
(`jinstall.green.live`), by the install's own list (`jinstall.needs.units`): it links, enables
and starts each unit the install turns on that has no link yet, as when main adds one, services
such as the follower first, and
it restarts each service the install turns on (the follower, and the relay where it runs) that
started before the reinstall changed ~/.local/bin/jbus, with `systemctl --user try-restart` or
`launchctl kickstart -k`. A second move finds each unit linked and each service newer than
the change, and does neither; one the manager refuses raises a condition for the tip. The pass
that moves the copy still runs the jbus it loaded before the move, which may have no such step,
so each pass asks for it, the move's or a later one's, until `green.json` keeps `live` stamped
with the tip the copy holds, which it writes once the manager took each step: a refused step is
asked again on the next pass, and not only on the next move.

The units of `features/*/units/` link through the copy, so a move changes the files systemd
runs, and systemd keeps running the ones it loaded until it is told to read them again. systemd
judges a unit loaded from a link by the file behind it, and a unit owes a reload
(`NeedDaemonReload`, "changed on disk" in `systemctl cat`) while that file is newer than the one
it loaded. Each tip's tree is a checkout of its own, so after any move every unit's file is a
new one, though its content may be the same, and systemd's units name a tree the next move
removes. So a move runs `systemctl --user daemon-reload` where systemd's unit folder links a unit
into the tree it leaves (`linked`), or where the new tip changed, added or dropped a unit file, by
content against that tree (`units`), and then `try-restart` on each timer among the changed ones,
so a timer whose interval changed runs on the new one at once (`reload`). A
timer whose content is the same is not restarted, so its schedule runs on. A service is not
restarted: the pass that moves the copy runs in jbus.service, and a oneshot runs the new file on
its next start. `try-restart` starts no timer that was not running, so a reload run twice ends
the same. Before it points the link, the move writes the reload it owes systemd in `green.json`:
`at`, the tip whose units systemd must read, and `reload`, the unit files whose content changed,
and only a reload that systemd took every call of clears them. A reload systemd refuses raises a
condition for the tip, and each pass asks again, with no new tip, until systemd takes it, so
neither a refusal nor a pass that died before its reload leaves systemd on the old units, nor
any unit owing a reload. A move on a machine that links no unit through the copy and changes
none, and one on launchd, reloads nothing. Nor does one whose user manager does not read this
HOME (`ours`), as a test's or a sandbox's HOME is not the one the account's manager reads: the
move owes it nothing, as `jinstall.machine.Machine.systemctl` asks it nothing.

The links themselves do not move: the install links each unit to its file under the copy's path,
which names whichever tree is green, so a move leaves every link as the install made it. That path
never moves, and yet it spares no reload: systemd judges the file behind it, which each move
makes new.

Each move prints one line, `green <project>: the commands now run from <new 12>, in place of
<old 12>`, which the pass's log keeps, one that added units a second, `green <project>: linked,
enabled and started <units>`, and one that reloaded units another, `green <project>: systemd
reloaded <units>, and restarted <timers>`, whose units are the files that
changed or else `the units of <new 12>`. A crew's worktree is not the copy: `uv run`
there runs that tree's own code, and the copy moves no file of it.
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
"""The project's record of the copy: `refused`, the tip it would not import, `live`, the tip whose
units the manager took every step of `jinstall.green.live` for, `move`, the move that still owes
a step (`MOVE`), and the reload a move owes systemd: `at`, the tip whose units systemd must
read, and `reload`, the unit files whose content changed since systemd read them, whose timers
the reload restarts."""

OWED = ("reload", "at")
"""The keys of `green.json` that keep the reload a move owes systemd."""

MOVE = "move"
"""The key of `green.json` that keeps the move in flight: `to`, the tip it moves to, `from`, the
tip whose tree the link named before it, `owes`, the step it owes next (`STEPS_OWED`), and
`was`, the reload (`OWED`) systemd was owed before it, which a move that goes back puts back."""

STEPS_OWED = ("install", "relink")
"""The steps a move owes, in order: point the link at the new tree and install the tool again
from it, then remove the trees no command runs and put the harness layouts again."""

NO_IMPORT = "the green copy does not import"
MOVE_FAILED = "the green copy could not move"
UNLINKED = "the harness does not link the green copy's files"
UNRELOADED = "systemd did not reload the green copy's units"
UNSTARTED = "the green copy's units did not go live"

UNITS = "features/*/units/*"
"""The unit files a tree holds, which the install links into systemd through the copy."""


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


def units(before: Path, after: Path) -> list[str]:
    """The names of the unit files that differ between the trees, by content: changed, added
    or dropped."""
    old, new = (
        {one.name: one.read_bytes() for one in tree.glob(UNITS) if one.is_file()}
        for tree in (before, after)
    )
    return sorted(name for name in old.keys() | new.keys() if old.get(name) != new.get(name))


def linked(tree: Path, env: Mapping[str, str] | None = None) -> bool:
    """Whether systemd's user unit folder, `${XDG_CONFIG_HOME:-~/.config}/systemd/user`, holds a
    link that resolves into `tree`, so that systemd loaded a unit from it."""
    env = os.environ if env is None else env
    folder = Path(env.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "systemd" / "user"
    if not folder.is_dir():
        return False
    return any(one.is_symlink() and one.resolve().is_relative_to(tree) for one in folder.iterdir())


def ours(env: Mapping[str, str] | None = None) -> bool:
    """Whether the user manager that `systemctl --user` reaches reads this HOME: it answers
    `show-environment` with `HOME=` this HOME. One that does not answer is not ours either."""
    env = os.environ if env is None else env
    said = proc.run("systemctl", "--user", "show-environment", timeout=60)
    home = env.get("HOME") or str(Path.home())
    return said.returncode == 0 and f"HOME={home}" in said.stdout.splitlines()


def reload(run: Pass, copy: Path) -> None:
    """Have systemd read again the units of the tip a move owes it, as `green.json` keeps it, and
    restart each changed unit that is a timer of the tree the copy names. Clear the debt only once
    systemd took every call, so a pass that finds it refused, or never asked, asks again."""
    record = read_json(run.state / FILE, {})
    if not any(record.get(key) for key in OWED):
        return
    owed = record.get("reload") or []
    green = str(record.get("at", ""))
    tree = copy.resolve()
    timers = [one for one in owed if one.endswith(".timer") and any(tree.glob(UNITS[:-1] + one))]
    asks = [["daemon-reload"]] + ([["try-restart", *timers]] if timers else [])
    for asked in asks:
        said = proc.run("systemctl", "--user", *asked, timeout=60)
        if said.returncode != 0:
            why = f"at {green[:12]}: systemctl --user {' '.join(asked)}: {_said(said)}"
            run.condition("green", UNRELOADED, why, key=green[:12])
            return
    write_json(run.state / FILE, {key: value for key, value in record.items() if key not in OWED})
    restarted = f", and restarted {', '.join(timers)}" if timers else ""
    what = ", ".join(owed) if owed else f"the units of {green[:12]}"
    run.say(f"green {run.project.name}: systemd reloaded {what}{restarted}")


def move(run: Pass, copy: Path | None = None) -> None:
    """Resume the step a move of the green copy still owes, then move the copy to main's green
    tip, when there is such a copy and the tip is newer than the one it holds, put the units of
    the tip it holds to work once, then have systemd reload the units any move still owes it. A
    link that names a tree that is gone is still the copy where the tree its move came from
    says so."""
    copy = path() if copy is None else copy
    made_from = owner(copy, run.state)
    if made_from is None or made_from.resolve() != run.project.checkout.resolve():
        return
    _resume(run, copy)
    _advance(run, copy)
    _live(run, copy)
    reload(run, copy)


def _live(run: Pass, copy: Path) -> None:
    """Put the units of the tip the copy holds to work (`jinstall.green.live`), unless
    `green.json` keeps `live` stamped with that tip, and stamp it once the manager took each step.
    The pass that moves the copy still runs the jbus of before the move, so the first pass that
    runs the new one does this, and one the manager refused asks again on the next pass."""
    held = at(copy)
    record = read_json(run.state / FILE, {})
    if not held or record.get("live") == held:
        return
    from jinstall.green import live

    added, why = live(copy)
    if added:
        run.say(f"green {run.project.name}: linked, enabled and started {', '.join(added)}")
    if why:
        run.condition("green", UNSTARTED, f"at {held[:12]}: {why}", key=held[:12])
        return
    write_json(run.state / FILE, {**read_json(run.state / FILE, {}), "live": held})


def in_flight(state: Path) -> dict | None:
    """The move the `green.json` in the project state `state` keeps as owing a step, or None
    where no move owes one."""
    owed = read_json(state / FILE, {}).get(MOVE)
    kept = isinstance(owed, dict) and owed.get("owes") in STEPS_OWED
    return owed if kept and all(isinstance(owed.get(key), str) for key in ("to", "from")) else None


def owner(copy: Path, state: Path) -> Path | None:
    """The checkout `copy` is the green copy of (`of`), or None. A link that names a tree that is
    gone, which a move in flight can leave, is still the copy where the tree that move came from,
    as `green.json` in the project state `state` keeps it, says so."""
    made_from = of(copy)
    if made_from is None and (owed := in_flight(state)) is not None:
        made_from = of(trees(copy) / owed["from"])
    return made_from


def _resume(run: Pass, copy: Path) -> None:
    """Take up the step a move owes, as `green.json` keeps it, before the pass reads main.json: a
    pass that died after it pointed the link, or a relink that was refused, is finished here. A
    tree the move went to that is gone puts the link back on the one it came from."""
    owed = in_flight(run.state)
    if owed is None:
        return
    if not (trees(copy) / owed["to"]).is_dir() and owed["to"] != owed["from"]:
        why = f"to {owed['to'][:12]}: its tree is gone, so it stays at {owed['from'][:12]}"
        run.condition("green", MOVE_FAILED, why, key=owed["to"][:12])
        _back(run, copy, owed)
        return
    _settle(run, copy, owed)


def _settle(run: Pass, copy: Path, owed: Mapping[str, str]) -> None:
    """Take the steps of a move from the one `owed` names: point the link at the new tree and
    install the tool again from it (`install`), then remove the trees no command may run and put
    the harness layouts again (`relink`). Each step writes the next one owed before it starts,
    and the move is dropped from `green.json` only once the relink is taken, so a pass that dies
    or is refused anywhere leaves the next one the step to take."""
    green, held = owed["to"], owed["from"]
    tree, before = trees(copy) / green, trees(copy) / held
    installed = owed["owes"] == "install"
    if installed:
        _point(copy, tree)
        if why := _reinstall(copy):
            run.condition(
                "green", MOVE_FAILED, f"uv tool install at {green[:12]}: {why}", key=green[:12]
            )
            if green != held:
                _back(run, copy, owed)
            return
        owed = {**owed, "owes": "relink"}
        write_json(run.state / FILE, {**read_json(run.state / FILE, {}), MOVE: owed})
    for old in trees(copy).iterdir():
        if old.is_dir() and old.resolve() not in (before.resolve(), tree.resolve()):
            shutil.rmtree(old)
    from jinstall.green import relink

    faults = relink(copy)
    for why in faults:
        run.condition("green", UNLINKED, f"at {green[:12]}: {why}", key=green[:12])
    if not faults:
        _drop(run)
    if installed and green != held:
        line = f"the commands now run from {green[:12]}, in place of {held[:12]}"
        run.say(f"green {run.project.name}: {line}")


def _back(run: Pass, copy: Path, owed: Mapping) -> None:
    """Take the move `owed` back to the tip it came from: keep in `green.json` that it owes the
    install of that tip, with the reload systemd was owed before the move in place of the one it
    wrote for the tip it leaves, then point the link back, remove the tree it leaves, and settle
    the move back: uv may have removed the tool before it failed, and the move it took over may
    have owed a relink that was never taken. An install that fails there too stays owed, and each
    pass asks for it again."""
    held = owed["from"]
    before = trees(copy) / held
    back = {"to": held, "from": held, "owes": "install"}
    was = owed.get("was") if isinstance(owed.get("was"), dict) else {}
    record = read_json(run.state / FILE, {})
    kept = {key: value for key, value in record.items() if key not in OWED}
    write_json(run.state / FILE, {**kept, **was, MOVE: back})
    _point(copy, before)
    shutil.rmtree(trees(copy) / owed["to"], ignore_errors=True)
    _settle(run, copy, back)


def _drop(run: Pass) -> None:
    """Take the move out of `green.json`: it owes no step."""
    record = read_json(run.state / FILE, {})
    write_json(run.state / FILE, {key: value for key, value in record.items() if key != MOVE})


def _advance(run: Pass, copy: Path) -> None:
    """Move the copy to main's green tip, unless a move still owes its install, as one that went
    back and that uv refused again does: that install comes first. A move that owes a relink is
    taken over by this one, which relinks."""
    if (owed := in_flight(run.state)) is not None and owed["owes"] == "install":
        return
    green = mainjson.read(run.state).green
    held = at(copy)
    record = read_json(run.state / FILE, {})
    refused = record.get("refused")
    if not green or not held or green in (held, refused):
        return
    tree = trees(copy) / green
    if why := _grow(run.project.checkout, tree, green):
        run.condition("green", MOVE_FAILED, f"to {green[:12]}: {why}", key=green[:12])
        return
    changed = _built(copy) != _built(tree)
    if broke := imports(tree, fresh=changed):
        shutil.rmtree(tree)
        write_json(run.state / FILE, {**record, "refused": green})
        why = f"at {green[:12]}, so it stays at {held[:12]}: {broke}"
        run.condition("green", NO_IMPORT, why, key=green[:12])
        run.say(f"green {run.project.name}: {green[:12]} does not import, kept {held[:12]}")
        return
    before = copy.resolve()
    changed = units(before, tree)
    was = {key: record[key] for key in OWED if key in record}
    owes = {**record, MOVE: {"to": green, "from": before.name, "owes": "install", "was": was}}
    if (changed or linked(before)) and launchd.manager() == "systemd" and ours():
        owes |= {"reload": sorted({*record.get("reload", []), *changed}), "at": green}
    write_json(run.state / FILE, owes)
    _settle(run, copy, owes[MOVE])


STEPS = (verbs.Step("close", 45, "green.move", lambda half: move(half.run), ()),)
