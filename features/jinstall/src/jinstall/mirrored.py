"""The doctor's look at each mirror home: `jroles mirror --check`, read in place.

A mirror is an extra Claude home that providers.json declares, and `jroles-mirror.timer` keeps
it as a mirror of `~/.claude` (`jroles.mirror`). The probe reads it through the same `plan` that
the command uses, so the doctor and `jroles mirror --check` cannot disagree. The doctor only
probes a mirror. The timer, or `jroles mirror` run by hand, repairs it.

    ok       every entry is as `jroles mirror` makes it
    missing  the home is not there: the instance has no login yet
    old      an entry differs: the detail names how many and the first
"""

from dataclasses import dataclass
from pathlib import Path

from jinstall.kinds import Found
from jinstall.machine import Machine
from jroles import Refused, mirror


def declared(inventory: Path, home: Path) -> tuple[mirror.Mirror, ...]:
    """The mirrors the inventory declares, or none when the inventory cannot be read. The
    inventory's own line says why."""
    try:
        return mirror.mirrors(inventory.read_text(), home)
    except (OSError, UnicodeDecodeError, Refused):
        return ()


@dataclass(frozen=True)
class Mirrored:
    """One mirror home, compared with `~/.claude`."""

    mirror: mirror.Mirror

    def ask(self, machine: Machine) -> str:
        return "jroles mirror"

    def probe(self, machine: Machine) -> Found:
        if not self.mirror.home.is_dir():
            return Found.missing(f"{self.mirror.instance} has no home yet")
        try:
            said = mirror.check(mirror.Main.of(machine.home), self.mirror)
        except (OSError, Refused) as error:
            return Found.old(str(error))
        if not said:
            return Found.ok()
        more = f", and {len(said) - 1} more" if len(said) > 1 else ""
        return Found.old(f"{said[0]}{more}: run jroles mirror")
