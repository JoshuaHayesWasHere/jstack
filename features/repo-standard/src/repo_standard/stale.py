"""Generated files kept current: each generator the config's `generators` names runs with `--check`
appended, in the repo's root, and a generator that exits other than 0 is a stale output.

A generator is a command as a list of words, such as `[python3, scripts/generate.py]`, so no shell
reads it. In `--check` mode a generator writes nothing, compares what it would write with the file
on disk, and exits 1 when they differ: that is the contract each generator keeps.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from repo_standard.config import Config
from repo_standard.tree import Fault

SHOWN = 20


def check(root: Path, config: Config) -> list[Fault]:
    faults = []
    for command in config.part("generators"):
        argv = [*command, "--check"]
        named = " ".join(argv)
        try:
            ran = subprocess.run(argv, cwd=root, capture_output=True, text=True)
        except OSError as error:
            faults.append(Fault(command[0], None, f"`{named}` cannot run: {error.strerror}"))
            continue
        if ran.returncode != 0:
            said = (ran.stdout + ran.stderr).strip().splitlines()[-SHOWN:]
            why = f"`{named}` exits {ran.returncode}: its output is stale"
            faults.append(Fault(command[-1], None, "\n".join([why, *said])))
    return faults
