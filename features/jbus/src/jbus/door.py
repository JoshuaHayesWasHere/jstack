"""Whether a thread's own shell command may walk through a door, read by
`features/jbus/hooks/door-command.sh` before Claude Code or Codex runs a `Bash` command.

A door is a case of `templates/gates.md`, and the commands that walk through one are the `runs`
of `party.DOORS`, the table a brief's commands are read by (`party.walks`). jbus's go and answer
paths are the main check: a row whose brief walks through a door goes only on the user's own word,
read in T3 Code, that names it. This hook is the second, for what a thread runs itself:

- a home's or a scout's command that walks through a door is refused: the door goes in a row
  whose brief has `Holds: <case>`, and the user's own go in T3 Code opens it for that row's crew;
- a crew's command goes only where its row's go is a `done` act by the party `user` on checked
  evidence, and still holds for the brief stored now;
- any other thread, and a session T3 Code's store does not know, is let through, as
  `jbriefs.sends` lets a send through.

A command is read in pieces: a heredoc's body is left out, since it is text a command reads and
not a command, and the rest is cut at each shell separator, quote, backtick and parenthesis, so a
command quoted for `ssh` or `bash -c` is read as a command of its own, and a commit message's
words are read as words. A command that runs dry walks through nothing (`party.DRY`). A home can
still wrap a door in a script of its own, which is why the go path is the main check.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import home, sends
from jbus import party
from jsettings import paths

_HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1")
_CUT = re.compile(r"[;&|\n'\"`()]")


def pieces(command: str) -> list[str]:
    """The commands of a shell command line, each as one backticked command, a heredoc's body
    left out."""
    kept, ends = [], ""
    for line in command.splitlines():
        if ends:
            if line.strip() == ends:
                ends = ""
            continue
        kept.append(line)
        opened = _HEREDOC.search(line)
        if opened:
            ends = opened.group(2)
    return [f"`{one.strip()}`" for one in _CUT.split("\n".join(kept)) if one.strip()]


def walks(command: str) -> tuple[tuple[str, str], ...]:
    """The doors a shell command line walks through, each with the command that does."""
    return tuple(found for one in pieces(command) for found in party.walks(one))


def _holds(state: Path, slug: str) -> bool:
    """Whether the row's go is the user's own, read in T3 Code: its last `done` go is an act of
    the party `user` on checked evidence, and the row's go holds for the brief stored now."""
    from jbus import acts, queue
    from jmerge import judgement

    gos = [
        one
        for one in acts.read(state)
        if one["action"]["verb"] == "go"
        and one["action"]["subject"] == slug
        and one["outcome"] == "done"
    ]
    if not gos or gos[-1]["party"]["kind"] != "user" or not gos[-1]["evidence"]["checked"]:
        return False
    row, text = queue.current(state, slug)
    return row is not None and judgement.has_go(row, text)


def refusal(homes: Path, buses: Path, thread: str, command: str) -> str:
    """Why the thread may not run the command, or nothing where it may. `homes` is the repo's
    homes' state and `buses` its jbus state."""
    walked = walks(command)
    if not walked:
        return ""
    case, matched = walked[0]
    user = _user()
    door = f"`{matched}` walks through a door ({case})"
    row = (
        f"the door goes in a row whose brief has Holds: {case}, and {user}'s own go in T3 Code, "
        '"go <slug>", opens it for that row\'s crew'
    )
    if any(one.holds(thread) for one in sends.homes(homes)):
        return f"{door}, and a home runs no door itself: {row}"
    for scout in sorted((homes / "scouts").glob("*.md")):
        if _thread(scout) == thread:
            return f"{door}, and a scout runs no door itself: {row}"
    crew = next((one for one in sends.crews(homes) if one.thread == thread), None)
    if crew is None or _holds(buses, crew.slug):
        return ""
    return (
        f"{door}, and the go of {crew.slug} is not {user}'s own word read in T3 Code: {user} "
        f'sends "go {crew.slug}" in T3 Code, and jbus --as user queue approve {crew.slug} '
        "--sha <sha12> --message <thread>/<message> records it"
    )


def _thread(path: Path) -> str:
    from jbriefs import parse

    try:
        return parse.thread_of(path.read_text(errors="replace"))
    except OSError:
        return ""


def _user() -> str:
    try:
        return jsettings.load().user
    except jsettings.Invalid:
        return "the user"


def _command(call: Any) -> str:
    if not isinstance(call, dict) or call.get("tool_name") != "Bash":
        return ""
    given = call.get("tool_input")
    command = given.get("command") if isinstance(given, dict) else None
    return command if isinstance(command, str) else ""


def main() -> int:
    """Read the hook's input on stdin. Print the refusal on stderr and end 2, or end 0."""
    try:
        call = json.load(sys.stdin)
    except ValueError:
        return 0
    command = _command(call)
    if not command or not walks(command):
        return 0
    repo = sends.repo_of(str(call.get("cwd") or ""))
    state = home.homes_dir() / repo
    if not repo or not state.is_dir():
        return 0
    thread = sends.thread_of_session(str(call.get("session_id") or ""), Path.home() / sends.STORE)
    if not thread:
        return 0
    why = refusal(state, paths.jbus_state_dir() / repo, thread, command)
    if not why:
        return 0
    print(f"door-command: refused: {why}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
