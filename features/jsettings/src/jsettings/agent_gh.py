"""The `gh` an agent runs in its own shell, logged in `proc.CALLS` with the caller `agent`.

An agent's Bash shell finds the crew's `gh` (`features/crew/bin/gh`) first on PATH: the crew's
SessionStart hook (`features/crew/hooks/gh-logged.sh`) puts it there through the file Claude Code
sources before each Bash command (`CLAUDE_ENV_FILE`). That script takes its own directory off
PATH, so the `gh` this module starts is the real one, and calls `main`. gh runs as the agent
asked: its input and output are the agent's own, and what it says on stderr reaches the agent
once it ends, without the debug log (`GH_DEBUG=api`) this module asks for to read the call's
`X-Ratelimit-*` headers. The line is written as `proc.run` writes its own, so
`jbus budget --callers` and the store's `gh_hours` count the agent's spend beside jbus's.

The script runs the real `gh` alone, with no line, where the rest of PATH has no `gh` or no
`python3`, where this module cannot be loaded, and for a `gh` that `proc.run` started, which
jbus's own commands do from an agent's shell too: that one carries `proc.LOGGED`, and `proc.run`
writes its line. A `gh` that asked GitHub nothing, such as `gh --version`, writes no line, since
it spent nothing. A line that cannot be written, as under a test that names no `JBUS_STATE_DIR`
(`paths.RealDir`), costs the call nothing: the agent still gets what gh did.

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
    done = subprocess.run(command, stderr=subprocess.PIPE, env={**os.environ, "GH_DEBUG": "api"})
    said = proc.Debug.parse(done.stderr.decode(errors="replace"))
    sys.stderr.write(said.stderr)
    sys.stderr.flush()
    if said.requests:
        with contextlib.suppress(Exception):
            proc._log(paths.jbus_state_dir(), command, CALLER, done.returncode, said)
    return done.returncode if done.returncode >= 0 else 128 - done.returncode
