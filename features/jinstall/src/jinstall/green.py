"""The green copy: where the commands of a checkout's install run from once jbus watches its main.

jbus reverts or fixes a red main, so it must not run from a main that broke (`jbus.green`). When
jbus's config names the checkout `install.sh` runs from as a project, `attach` gives the machine a
green copy at `${XDG_DATA_HOME:-~/.local/share}/jstack/green`, a link to a clone of the checkout
at one tip, and the install points everything that runs at it: uv's tool `jstack` is an editable
install of it, and each layout, its skills, hooks and `source` link, and each unit is assembled
from it (`Machine.source`). The checkout keeps what a developer works on: its project skills,
its generated files, its own git hooks. jbus moves the copy forward to main's green tip on each
pass.

A checkout that jbus does not watch has no green copy: nothing would move it, so its install
runs from the checkout as before. Neither does a run of `jinstall` from a release.
"""

import os
import shutil
from dataclasses import dataclass, replace
from pathlib import Path

import jbus
from jbus import green as copies
from jinstall.harnesses import HARNESSES
from jinstall.kinds import Carried, Found, GoneLink, HookGroup, RetiredHook, State
from jinstall.layout import UNREADABLE, Layout, folder
from jinstall.machine import Dropped, Machine, Moved, Refused
from jmerge import mainjson


def _config_dir(machine: Machine) -> Path:
    named = machine.env.get("JBUS_CONFIG_DIR")
    return Path(named) if named else machine.home / ".config" / "jbus"


def _project(machine: Machine, checkout: Path) -> jbus.Project | None:
    """The project of jbus's config whose checkout is `checkout`, or None."""
    directory = _config_dir(machine)
    if not (directory / "config.toml").is_file():
        return None
    try:
        config = jbus.load(directory)
    except Exception:
        return None
    here = Path(os.path.abspath(checkout)).resolve()
    return next((one for one in config.projects if one.checkout.resolve() == here), None)


def attach(machine: Machine) -> Machine:
    """The machine with its green copy, where jbus's config names its checkout as a project. A
    `jinstall` that runs from the copy itself, as uv's tool does, acts for the checkout the copy
    was made from."""
    if machine.checkout is None:
        return machine
    made_from = copies.of(machine.checkout)
    checkout = made_from if made_from is not None else machine.checkout
    if _project(machine, checkout) is None:
        return replace(machine, checkout=checkout) if made_from is not None else machine
    return replace(machine, checkout=checkout, green=copies.path(machine.env, machine.home))


def tip(machine: Machine) -> str:
    """The commit a new copy starts at: main's last green tip as jbus keeps it for the checkout's
    project, or else the commit the checkout holds, which jbus moves on from once main is green."""
    assert machine.checkout is not None
    project = _project(machine, machine.checkout)
    if project is not None:
        try:
            if kept := mainjson.read(jbus.load(_config_dir(machine)).state(project)).green:
                return kept
        except Exception:
            pass
    head = machine.run(["git", "-C", str(machine.checkout), "rev-parse", "HEAD"])
    return head.out.strip() if head.code == 0 else "HEAD"


def make(machine: Machine) -> str:
    """Make the machine's green copy where it is missing, before the install lists what it puts,
    since the layouts and the tool are made from it. Return "" when the copy is there, or why
    the install made none: the need's own line then says missing."""
    if machine.green is None or GreenCopy(machine.green).probe(machine).state is State.OK:
        return ""
    try:
        GreenCopy(machine.green).put(machine)
    except Refused as why:
        return f"install.sh: green copy {machine.green}: {why}"
    return ""


def relink(copy: Path) -> list[str]:
    """Bring each harness layout that the install assembled from the green copy `copy` up to the
    tip the copy now holds, as the install's own put does: link each file the tip added, remove
    each link to a file it dropped, and write each rewritten copy again. jbus calls it each time
    it moves the copy (`jbus.green.move`), since the layouts link files one by one and would
    otherwise hold only the files of the tip the last install saw. A layout whose `source` names
    anything else, or that is not there, is left as it is.

    For each layout it put, it then puts what points into it, as the install does: the link of
    each skill under the harness's skills root (`skills <harness>`), and the removal of each link
    there to a skill the tip dropped (GoneLink), so a harness lists a new skill with no install
    and no dropped one. The same goes for the hook entries of the harness's hooks file
    (`hooks <file>`, RetiredHook): the layout's `hooks/` now holds the scripts of the new tip, so
    an entry for a dropped script would run a file that is gone on every call. A Claude home
    other than ~/.claude reads its skills through ~/.claude/skills (`HomeSkills`), so it needs
    nothing more. Return why each layout or need it could not put was not put, one line each."""
    from jinstall.needs import needs  # needs imports this module

    machine = replace(Machine.here(copies.of(copy)), green=copy)
    faults, put = [], []
    for harness in HARNESSES:
        source = folder(machine, harness) / "source"
        if not source.is_symlink() or os.readlink(source) != str(copy):
            continue
        try:
            Layout(harness).put(machine)
            put.append(harness)
        except (Refused, *UNREADABLE) as why:
            faults.append(f"layout {harness.name}: {why}")
    if not put:
        return faults
    roots = {machine.home / harness.root for harness in put}
    names = {harness.name for harness in put}
    try:
        listed = needs(machine)
    except (OSError, Refused, *UNREADABLE) as why:
        return [*faults, f"the skills and hooks of {copy}: {why}"]
    for need in listed:
        kind = need.kind
        if not isinstance(kind, Carried) or not (
            need.fold in {f"skills {name}" for name in names}
            or (isinstance(kind, GoneLink) and kind.path.parent in roots)
            or (isinstance(kind, (HookGroup, RetiredHook)) and kind.harness in names)
        ):
            continue
        try:
            found = kind.probe(machine)
            if found.state is not State.OK and found.replaceable:
                kind.put(machine)
        except (OSError, Moved, Refused) as why:
            faults.append(f"{need.name}: {why}")
    return faults


@dataclass(frozen=True)
class GreenCopy:
    """The green copy of the checkout, at `path`.

    due: the machine has a green copy (`attach`).
    ok: `path` is a green copy of this checkout. The detail names the commit it holds.
    missing: nothing is at `path`.
    foreign: `path` is something else, or the green copy of another checkout: the install
      neither writes over it nor removes it.
    put: clone the checkout at `path`, at `tip`.
    drop: remove the copy when it is this checkout's and holds no change of its own."""

    path: Path

    def due(self, machine: Machine) -> bool:
        return machine.green is not None

    def probe(self, machine: Machine) -> Found:
        if not self.path.exists() and not self.path.is_symlink():
            return Found.missing("install.sh makes it at main's last green tip")
        made_from = copies.of(self.path)
        if made_from is None:
            return Found.foreign(f"{self.path} is not a green copy")
        if machine.checkout is None or made_from.resolve() != machine.checkout.resolve():
            return Found.foreign(f"the green copy of {made_from}")
        held = copies.at(self.path)
        return (
            Found.ok(f"at {held[:12]}, which each jbus pass moves to main's green tip")
            if held
            else Found.old("it holds no commit")
        )

    def put(self, machine: Machine) -> None:
        assert machine.checkout is not None
        if why := copies.make(machine.checkout, self.path, tip(machine)):
            raise Refused(why)

    def drop(self, machine: Machine) -> Dropped:
        if self.probe(machine).state is not State.OK:
            return Dropped()
        changed = machine.run(["git", "-C", str(self.path), "status", "--porcelain"])
        if changed.code != 0 or changed.out.strip():
            return Dropped(kept=(f"green copy {self.path} -> it holds changes of its own",))
        self.path.unlink()
        shutil.rmtree(copies.trees(self.path), ignore_errors=True)
        return Dropped(removed=(f"green copy {self.path}",))
