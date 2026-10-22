"""The checkout's own skills: each skill of this repo's own that a feature declares
(`projectSkills`, which the generator lists in skills.json), linked into the checkout's
`.claude/skills/<name>` and `.cursor/skills/<name>`, where Claude Code and Cursor read a repo's
skills (`Harness.project`). git tracks neither folder: the install makes them.

Listed only with a checkout, a release has none, and due only when HOME is the account's own or
holds the checkout, as a git hook is: a run under a sandbox's or a test's HOME leaves a
checkout outside it as it is.
"""

import os
from dataclasses import dataclass
from pathlib import Path

from jinstall.kinds import Found, Link
from jinstall.machine import Dropped, Machine


def ours(machine: Machine) -> bool:
    """Whether this run may write in the checkout it installs from."""
    checkout = machine.checkout
    if checkout is None:
        return False
    return machine.home == machine.account or checkout.is_relative_to(machine.home)


@dataclass(frozen=True)
class ProjectLink:
    """A link from `<checkout>/<root>/<name>` to the folder of a declared project skill.
    ok, old, foreign and drop as `Link`'s."""

    path: Path
    target: Path

    def _link(self) -> Link:
        return Link(self.path, self.target)

    def probe(self, machine: Machine) -> Found:
        return self._link().probe(machine)

    def due(self, machine: Machine) -> bool:
        return ours(machine)

    def put(self, machine: Machine) -> None:
        self._link().put(machine)

    def drop(self, machine: Machine) -> Dropped:
        return self._link().drop(machine)


def stray(path: Path, checkout: Path, declared: frozenset[str]) -> bool:
    """Whether `path`, under a project root of `checkout`, is a link into the checkout by a
    name no feature declares: what the install made for a skill whose declaration is gone."""
    return (
        path.is_symlink()
        and path.name not in declared
        and os.readlink(path).startswith(f"{checkout}{os.sep}")
    )


@dataclass(frozen=True)
class StrayProjectLink:
    """A link under the checkout's project roots into the checkout, for a skill no feature
    declares. Listed only when found, old until it is unlinked. put and drop unlink it."""

    path: Path
    declared: frozenset[str]

    def _stray(self, machine: Machine) -> bool:
        return machine.checkout is not None and stray(self.path, machine.checkout, self.declared)

    def probe(self, machine: Machine) -> Found:
        if self._stray(machine):
            return Found.old(f"{os.readlink(self.path)}, a skill no feature declares")
        return Found.ok("unlinked")

    def due(self, machine: Machine) -> bool:
        return ours(machine)

    def put(self, machine: Machine) -> None:
        if self._stray(machine):
            machine.unlink(self.path)

    def drop(self, machine: Machine) -> Dropped:
        if not self._stray(machine):
            return Dropped()
        machine.unlink(self.path)
        return Dropped(removed=(str(self.path),))
