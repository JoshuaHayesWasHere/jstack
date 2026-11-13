"""The `gh` an agent runs in its own shell, logged in `proc.CALLS` with the caller `agent`.

An agent's Bash shell finds the crew's `gh` (`features/crew/bin/gh`) first on PATH, which the
crew's SessionStart hook puts there, and that script runs this module with the rest of PATH, so
the `gh` this module starts is the real one. gh runs as the agent asked: its input and output are
the agent's own, and what it says on stderr reaches the agent once it ends, without the debug log
(`GH_DEBUG=api`) this module asks for to read the call's `X-Ratelimit-*` headers. The line is
written as `proc.run` writes its own, so `jbus budget --callers` and the store's `gh_hours` count
the agent's spend beside jbus's.

Two cases write no line. A `gh` that `proc.run` started, which jbus's own commands do from an
agent's shell too, carries `proc.LOGGED` and has its line from `proc.run` already. A `gh` that
asked GitHub nothing, such as `gh --version` or `gh auth git-credential`, spent nothing. A line
that cannot be written, as under a test that names no `JBUS_STATE_DIR` (`paths.RealDir`), costs
the call nothing: the agent still gets what gh did.

An agent's `gh` takes no slot of `proc.GH_CAP`: a `gh run watch` can run for many minutes, and
would hold a slot jbus's own calls wait on for all of them.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys

from jsettings import paths, proc

CALLER = "agent"


def main(argv: list[str]) -> int:
    """Run the real `gh` with `argv`, pass on what it did, and log its line."""
    command = ("gh", *argv)
    if os.environ.get(proc.LOGGED):
        os.execvp("gh", command)
    try:
        done = subprocess.run(
            command, stderr=subprocess.PIPE, env={**os.environ, "GH_DEBUG": "api"}
        )
    except OSError as error:
        print(f"gh: {error}", file=sys.stderr)
        return 127
    said = proc.Debug.parse(done.stderr.decode(errors="replace"))
    sys.stderr.write(said.stderr)
    sys.stderr.flush()
    if said.requests:
        with contextlib.suppress(Exception):
            proc.log(paths.jbus_state_dir(), command, CALLER, done.returncode, said)
    return done.returncode if done.returncode >= 0 else 128 - done.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
