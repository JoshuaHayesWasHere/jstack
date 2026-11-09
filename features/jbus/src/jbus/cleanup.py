"""Once `jbus.threads.settle` puts a crew's thread away, `clear_scratch` removes what the crew
left on disk: its scratch folder (`jbus.dispatch.scratch`), and the worktrees of the repo it made
in the Claude scratchpad of its own worktree (`scratchpad`), then prunes their registrations.

The scratchpad is in /tmp whatever the crew's `TMPDIR` says, and a crew makes a "before" worktree
there for A/B timing that the door hook will not let it remove, so these stayed registered and
helped fill the tmpfs quota. Only the crew's own scratchpad is searched, so another crew's
worktrees and T3 Code's own under `~/.t3/worktrees` are out of reach, and a worktree that holds
some process's working directory stays (`in_use`).
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from jbus.dispatch import scratch
from jbus.passes import Pass


def scratchpad(worktree: str) -> Path:
    """Return the folder Claude Code keeps the scratchpads of a session in `worktree` under:
    `claude-<uid>` in `CLAUDE_CODE_TMPDIR` or /tmp, then the worktree's path with each character
    that is not a letter or a digit made `-`."""
    root = Path(os.environ.get("CLAUDE_CODE_TMPDIR") or "/tmp") / f"claude-{os.getuid()}"
    return root / re.sub("[^A-Za-z0-9]", "-", worktree)


def in_use() -> set[Path]:
    """Return the working directory of each process this user can read."""
    found: set[Path] = set()
    for proc in Path("/proc").glob("[0-9]*"):
        try:
            found.add(Path(os.readlink(proc / "cwd")))
        except OSError:
            continue
    return found


def clear_scratch(run: Pass, slug: str, worktree: str = "") -> None:
    """Remove the slug's scratch folder and the worktrees its crew made in the scratchpad of its
    `worktree`, save one in use, then prune their registrations."""
    folder = scratch(run, slug)
    cleared = []
    if folder.exists():
        shutil.rmtree(folder, ignore_errors=True)
        cleared.append(f"its scratch folder {folder}")
    if worktree:
        pad, busy = scratchpad(worktree), in_use()
        listed = run.run("git", "worktree", "list", "--porcelain").stdout.splitlines()
        for line in listed:
            tree = Path(line.removeprefix("worktree "))
            if not line.startswith("worktree ") or not tree.is_relative_to(pad):
                continue
            if any(cwd.is_relative_to(tree) for cwd in busy):
                continue
            if run.run("git", "worktree", "remove", "--force", str(tree)).returncode == 0:
                cleared.append(f"the worktree {tree}")
    if cleared:
        run.run("git", "worktree", "prune")
        run.say(f"cleared {slug}: {', '.join(cleared)}")
