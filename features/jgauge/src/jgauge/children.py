"""A watchdog that ends a test slot's command once the `jgauge test-slot` that holds the slot dies.

The slot is the holder's flock, so the kernel lets it go when the holder dies, SIGKILL too, and
the next call takes it. A command that lived on would then share its slot, and its temporary
directory, with the next one, whose start empties that directory. So the holder starts a
watchdog before its command, in a session of its own that no signal to the holder's group
reaches. The watchdog reads a pipe whose write end only the holder keeps: the command, once
forked, writes its pid there before it runs (`announce`), and the holder writes `DONE` once the
command has ended. The pipe ends when the holder does, however it ends. With `DONE` the watchdog
does nothing. Without it, the holder died while its command ran, and the watchdog kills the
command, every process under it, and in the short lane its process group.

`python -m jgauge.children <group>` is the watchdog, with `group` 1 where the command leads a
process group of its own.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
from pathlib import Path

DONE = b"done\n"
PROC = Path("/proc")


class Watch:
    """The holder's end of the watchdog's pipe."""

    def __init__(self, group: bool) -> None:
        read, self.fd = os.pipe()
        with open(os.devnull, "rb+") as null:
            self.dog = subprocess.Popen(
                [sys.executable, "-m", "jgauge.children", "1" if group else "0"],
                stdin=read,
                stdout=null,
                stderr=null,
                start_new_session=True,
            )
        os.close(read)

    def announce(self) -> None:
        """In the command's process, after the fork and before it runs: its pid goes to the
        watchdog, so a holder that dies at once still leaves the watchdog its command. The
        command does not keep the pipe, since `subprocess` closes it on the exec."""
        os.write(self.fd, f"{os.getpid()}\n".encode())

    def done(self) -> None:
        """The command has ended: the watchdog has nothing to end."""
        with contextlib.suppress(OSError):
            os.write(self.fd, DONE)
        os.close(self.fd)

    def reap(self) -> None:
        """Wait for the watchdog, which ends once it reads `DONE`. The holder reaps it after the
        slot log has its release row, whose CPU seconds are the command's and not the
        watchdog's."""
        self.dog.wait()


def _parents() -> dict[int, int]:
    """Each live process's parent."""
    found: dict[int, int] = {}
    if PROC.is_dir():
        for stat in PROC.glob("[0-9]*/stat"):
            with contextlib.suppress(OSError, IndexError, ValueError):
                found[int(stat.parent.name)] = int(stat.read_text().rsplit(")", 1)[1].split()[1])
        return found
    listed = subprocess.run(["ps", "-A", "-o", "pid=,ppid="], capture_output=True, text=True)
    for line in listed.stdout.splitlines():
        with contextlib.suppress(ValueError):
            pid, parent = map(int, line.split())
            found[pid] = parent
    return found


def stop(roots: set[int], group: int | None) -> set[int]:
    """Stop each live one of `roots`, every process under them, and with `group` that process
    group, until no new one turns up, so none starts another or leaves the tree while it is
    looked at, and give back the processes stopped. A process stays under its parent while it is
    stopped, also one in a session of its own, which no signal to the group reaches."""
    seen: set[int] = set()
    while True:
        parents = _parents()
        tree = roots & parents.keys()
        grew = True
        while grew:
            under = {child for child, parent in parents.items() if parent in tree}
            grew = not under <= tree
            tree |= under
        new = tree - seen
        if group is not None:
            with contextlib.suppress(OSError):
                os.killpg(group, signal.SIGSTOP)
        if not new:
            return seen
        for one in new:
            with contextlib.suppress(OSError):
                os.kill(one, signal.SIGSTOP)
        seen |= new


def tell(stopped: set[int], group: int | None, number: int) -> None:
    """Send signal `number` to each of `stopped` and with `group` to that process group."""
    if group is not None:
        with contextlib.suppress(OSError):
            os.killpg(group, number)
    for one in stopped:
        with contextlib.suppress(OSError):
            os.kill(one, number)


def end(pid: int, group: bool) -> None:
    """Kill `pid` and every process under it, and with `group` its process group."""
    leader = pid if group else None
    tell(stop({pid}, leader), leader, signal.SIGKILL)


def main() -> None:
    for told in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(told, signal.SIG_IGN)
    said = sys.stdin.buffer.read()
    if said.endswith(DONE) or not said:
        return
    end(int(said.split()[0]), sys.argv[1] == "1")


if __name__ == "__main__":
    main()
