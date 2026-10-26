"""The run of a repo's merge gate, which `jmerge` makes before a merge (`cli.Gate`) and a reviewer
makes on the head it reviews (`jmerge --gate <head>`).

The gate is the command on the first line of the `merge-gate` file in the repo's state. It runs as
`sh -c '<command> "$@"' merge-gate <base> <head>`, with `BASE` and `HEAD` in its environment too,
and stdin closed. A gate that runs over its limit is stopped with its process group.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from jmerge import ready

NAME = "merge-gate"
REVIEW_LIMIT = 540


def command(state: Path) -> str:
    """The gate's command, or an empty string for a repo with no gate."""
    try:
        return ready.fresh_command((state / NAME).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return ""


def outside_venv() -> dict[str, str]:
    """This environment as a shell outside the venv `jmerge` runs in has it: `uv run --project`
    sets `VIRTUAL_ENV` and puts that venv's bin first on PATH, and both are taken out, so a bare
    `python3` or `ruff` is the one the repo's own shell finds."""
    env = dict(os.environ)
    venv = env.pop("VIRTUAL_ENV", "")
    if venv:
        bin_dir = os.path.join(venv, "bin")
        env["PATH"] = os.pathsep.join(
            one for one in env.get("PATH", "").split(os.pathsep) if one != bin_dir
        )
    return env


def run(
    gate: str, cwd: Path, base: str, head: str, limit: float, pass_fds: tuple[int, ...] = ()
) -> tuple[int | None, str]:
    """Run the gate and return its exit code, None where it ran over `limit`, and its output.
    An `OSError` is raised where it could not start."""
    env = outside_venv() | {"BASE": base, "HEAD": head}
    with tempfile.TemporaryFile() as log:
        ran = subprocess.Popen(
            ["sh", "-c", f'{gate} "$@"', NAME, base, head],
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            pass_fds=pass_fds,
            start_new_session=True,
        )
        try:
            code = ran.wait(limit)
        except subprocess.TimeoutExpired:
            os.killpg(ran.pid, signal.SIGKILL)
            ran.wait()
            code = None
        log.seek(0)
        return code, log.read().decode(errors="replace")


def over(limit: float) -> str:
    """A limit as a line says it: in minutes where it is whole minutes."""
    return f"{limit // 60:g} minutes" if limit % 60 == 0 else f"{limit:g} s"


def review(state: Path, head: str, pull: str, limit: float = REVIEW_LIMIT) -> int:
    """The reviewer's run of the gate, in this worktree, on the head it reviews. It prints nothing
    for a repo with no gate or a gate that passes, and one finding for a gate that fails or runs
    over. Exit 1 says the gate was not run, with why on stderr."""
    gate = command(state)
    if not gate:
        return 0
    try:
        view = subprocess.run(
            ["gh", "pr", "view", *([pull] if pull else []), "--json", "baseRefName"],
            capture_output=True,
            text=True,
        )
        base = json.loads(view.stdout)["baseRefName"] if view.returncode == 0 else ""
    except (OSError, ValueError, TypeError, KeyError):
        base = ""
    fork = None
    if base and not subprocess.run(["git", "fetch", "-q", "origin", base]).returncode:
        fork = subprocess.run(
            ["git", "merge-base", f"origin/{base}", head], capture_output=True, text=True
        )
    if fork is None or fork.returncode:
        print(
            "not run: where the pull request left its base could not be worked out", file=sys.stderr
        )
        return 1
    try:
        code, said = run(gate, Path.cwd(), fork.stdout.strip(), head, limit)
    except OSError as error:
        code, said = 127, str(error)
    at = head[:12]
    if code is None:
        why = f"it ran over {over(limit)} and was stopped"
    elif code != 0:
        why = ready.first_line(said, code)
    else:
        return 0
    print(f"error - the merge gate fails at {at}: {why} (principle: none) (bucket: Act on)")
    return 0
