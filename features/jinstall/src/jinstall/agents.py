"""The Units need on macOS: the launchd agents that `jinstall.launchd` makes from the unit
templates, in `~/Library/LaunchAgents`, loaded into the gui domain."""

import time
from dataclasses import dataclass
from pathlib import Path

from jinstall import launchd
from jinstall.kinds import Found, Kind, split
from jinstall.machine import Dropped, Machine, Refused

PLIST_MODE = 0o644
"""launchd refuses a plist that its group or anyone else may write."""
GONE_WAIT = 5.0
"""How long the install waits for launchd to finish a bootout before it bootstraps the agent
again: a bootstrap while the bootout still runs fails with 5."""


@dataclass(frozen=True)
class Agents:
    """The jbus, jgauge and jroles agents. `agents` is each agent, by the unit that systemd
    would enable in its place. The agents that are on are each of `timers`, and each opted unit
    whose need is ok, as for `Units` (`kinds.split`). An agent that is on has its plist
    `<directory>/<label>.plist` and is loaded. An agent that is not on has no plist: launchd
    loads every plist of the folder at login, so a plist there is an agent that runs. The view,
    which systemd links and does not enable, gets none.

    A plist belongs to this install when its comment names this install's source
    (`launchd.made_from`).

    due: jbus is set up (its config is there), or a plist of this install's is there.
    ok: each agent that is on has the plist its templates make, and ~/.local/bin/jbus is
      there, since the agents run it. When launchctl answers, each of them is also loaded
      (`launchctl print` finds it), and no plist of an opted agent whose need is missing is
      there.
    old: the detail names the first piece that is not so: `lacks jstack.jbus.plist`,
      `jstack.jbus.plist is not as its templates make it`, `jstack.jbus is not loaded`,
      `jstack.jbus-ci.plist is there, and nothing asks for it`.
    foreign: a plist that no install made, `jstack.jbus.plist -> not jstack's, differs`; no
      ~/.local/bin/jbus; and, under the account's own HOME, a launchctl that did not answer.
    put: refuse when there is no ~/.local/bin/jbus. Otherwise boot out and remove the plist of
      each opted agent whose need is missing, write each plist that differs (booting its agent
      out first when it is loaded), and bootstrap each agent that is not loaded. A run that
      finds everything as it should be writes nothing and runs no bootstrap.
    drop: boot out each agent whose plist is this install's, and remove the plist.
    Each launchctl step goes through `machine.launchctl`, so in a sandbox with no stand-in the
    need only writes, checks and removes the plists."""

    directory: Path
    agents: dict[str, launchd.Agent]
    timers: tuple[str, ...]
    config: Path
    opted: tuple[tuple[str, Kind], ...] = ()

    def _path(self, agent: launchd.Agent) -> Path:
        return self.directory / f"{agent.label}.plist"

    def _text(self, machine: Machine, agent: launchd.Agent) -> str:
        return launchd.text(agent, machine.home, machine.source)

    def _read(self, agent: launchd.Agent) -> str | None:
        try:
            return self._path(agent).read_text()
        except OSError:
            return None

    def _ours(self, machine: Machine) -> list[launchd.Agent]:
        return [
            agent
            for agent in self.agents.values()
            if launchd.made_from(self._read(agent) or "") == str(machine.source)
        ]

    def _split(self, machine: Machine) -> tuple[list[launchd.Agent], list[launchd.Agent]]:
        on, off = split(machine, self.timers, self.opted)
        return [self.agents[name] for name in on], [self.agents[name] for name in off]

    def _service(self, machine: Machine, agent: launchd.Agent) -> str:
        return f"{machine.gui()}/{agent.label}"

    def _loaded(self, machine: Machine, agent: launchd.Agent) -> bool | str | None:
        """True when launchd has the agent and False when it has not. None where launchctl
        does not run here, and what launchctl said where its answer is neither, such as a
        domain with no one logged in to it."""
        ran = machine.launchctl("print", self._service(machine, agent))
        if ran is None or ran.code is None:
            return None
        if ran.code == 0 or ran.code in launchd.NOT_LOADED:
            return ran.code == 0
        said = ran.out.strip().splitlines()
        return f"launchctl print {self._service(machine, agent)}: {said[-1] if said else ran.code}"

    def due(self, machine: Machine) -> bool:
        return self.config.is_file() or bool(self._ours(machine))

    def probe(self, machine: Machine) -> Found:
        on, off = self._split(machine)
        lacking, stale = [], []
        for agent in on:
            said = self._read(agent)
            if said is None:
                lacking.append(self._path(agent).name)
            elif launchd.made_from(said) is None:
                return Found.foreign(f"{self._path(agent).name} -> not jstack's, differs")
            elif said != self._text(machine, agent):
                stale.append(self._path(agent).name)
        if len(lacking) == len(on):
            return Found.missing()
        if lacking:
            return Found.old(f"lacks {' '.join(lacking)}")
        if stale:
            return Found.old(f"{stale[0]} is not as its templates make it")
        if not (machine.home / ".local" / "bin" / "jbus").exists():
            return Found.foreign("no ~/.local/bin/jbus")
        for agent in on:
            loaded = self._loaded(machine, agent)
            if loaded is None and machine.home == machine.account:
                return Found.foreign(f"launchctl did not answer, so {agent.label} is not loaded")
            if loaded is None:
                return Found.ok()
            if isinstance(loaded, str):
                return Found.foreign(loaded)
            if not loaded:
                return Found.old(f"{agent.label} is not loaded")
        for agent in off:
            if launchd.made_from(self._read(agent) or "") is not None:
                return Found.old(f"{self._path(agent).name} is there, and nothing asks for it")
        return Found.ok()

    def _launchctl(self, machine: Machine, *args: str) -> None:
        ran = machine.launchctl(*args)
        if ran is not None and ran.code != 0:
            said = ran.out.strip().splitlines()
            raise Refused(f"launchctl {' '.join(args)}: {said[-1] if said else ran.code}")

    def _bootout(self, machine: Machine, agent: launchd.Agent) -> None:
        """Boot the agent out when launchd has it, and wait until launchd says it is gone."""
        if self._loaded(machine, agent) is not True:
            return
        self._launchctl(machine, "bootout", self._service(machine, agent))
        until = time.monotonic() + GONE_WAIT
        while self._loaded(machine, agent) is True and time.monotonic() < until:
            time.sleep(0.1)

    def _remove(self, machine: Machine, agent: launchd.Agent) -> None:
        self._bootout(machine, agent)
        machine.unlink(self._path(agent))

    def put(self, machine: Machine) -> None:
        if not (machine.home / ".local" / "bin" / "jbus").exists():
            raise Refused("no ~/.local/bin/jbus for the agents to run, so none is written")
        on, off = self._split(machine)
        for agent in off:
            if launchd.made_from(self._read(agent) or "") is not None:
                self._remove(machine, agent)
        for agent in on:
            said, wanted = self._read(agent), self._text(machine, agent)
            if said is not None and launchd.made_from(said) is None:
                raise Refused(f"{self._path(agent)} is not jstack's")
            if said != wanted:
                self._bootout(machine, agent)
                machine.make_dirs(launchd.log(machine.home, agent.label).parent)
                machine.write_text(self._path(agent), wanted, PLIST_MODE)
            if self._loaded(machine, agent) is False:
                self._launchctl(machine, "bootstrap", machine.gui(), str(self._path(agent)))

    def drop(self, machine: Machine) -> Dropped:
        ours = self._ours(machine)
        for agent in ours:
            self._remove(machine, agent)
        return Dropped(removed=tuple(f"agent {self._path(agent)}" for agent in ours))
