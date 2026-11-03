"""Whether a thread's own shell command may walk through a door, read by
`features/jbus/hooks/door-command.sh` before an agent's harness runs a `Bash` command.

A door is a case of `templates/gates.md`, and the commands that walk through one are the `runs`
of `party.DOORS`, the table a brief's commands are read by (`party.walks`). jbus's go and answer
paths are the main check: a row whose brief walks through a door goes only on the user's own word,
read in T3 Code, that names it. This hook is the second, for what a thread runs itself:

- a home's or a scout's command that walks through a door is refused: the door goes in a row
  whose brief has `Holds: <case>`, and the user's own go in T3 Code opens it for that row's crew;
- a crew's command goes only where its row's go is a `done` act on the user's own words that jbus
  read (`party.opens`), and still holds for the brief stored now;
- any other thread, and a session T3 Code's store does not know, is let through, as
  `jbriefs.sends` lets a send through.

A command is read in pieces (`pieces`): cut at each shell separator, backtick and parenthesis,
with a quoted string read as a command of its own where `ssh`, `bash -c` or `eval` runs it, and
left out where it is an argument such as a commit message or a title. A heredoc's body is left
out, since it is text a command reads, but where it feeds a shell or `ssh`, whose commands it is.
A command that runs dry walks through nothing (`party.DRY`). A home can still wrap a door in a
script of its own, which is why the go path is the main check.

Every refusing hook of jstack (this one, `agent-sends` and jleak's three) judges through
`features/jbus/hooks/judge.sh`. The hook sets `hook` (its name), `input` (what the harness gave it
on stdin) and `source` (jstack's source tree), sources the file, and calls `judge <module>
[<argument>...]`, which ends the hook. The module reads the call on stdin and ends 0 to let it
through, or 2 to refuse it with its reason on stderr. A hook that cannot judge refuses: a module
that ends any other way, one that runs past `JSTACK_HOOK_SECONDS` (25 by default, inside the 30
the harness gives the hook), and a machine with no Python 3.12 or newer each end it 2 too.

Each refusal adds one quiet `hook` event, declared here, to the jbus log of the repo the call ran
in, where jbus keeps one: the hook, the head of the call and the reason. The shell writes it, not
Python, so a refusal for want of Python is logged too, and writes it as plain ASCII, since jbus
reads the log as UTF-8 and a cut could split a character. A machine without the tools the line
needs (`git`, `sed`, `date` and the like) still refuses, and logs nothing.
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

EVENTS = {"hook": "quiet"}

_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1")
_SEPARATOR = set(";&|\n()`")
_SHELL = r"(?:\S*/)?(?:ba|z|da|k)?sh"
_RUNS_TEXT = re.compile(rf"(?:^|\s){_SHELL}(?:\s+-\w+)*\s+-[a-z]*c\s*$|\bssh\s|\beval\s*$")
"""What runs the quoted text after it as a command: `bash -c`, with `-c` alone or last of a group
of flags as in `bash -lc`, `ssh <host>`, `eval`."""
_FEEDS = re.compile(rf"(?:^|[;&|(]\s*|\s){_SHELL}\b[^<]*$|\bssh\s[^<]*$")
"""What runs a heredoc's body as commands: a shell, or `ssh <host>`, before the `<<`."""


def _unfold(command: str) -> str:
    """The command line with each heredoc's body left out, but for one that feeds a shell, whose
    body is commands of its own. A here-string, `<<<`, is no heredoc."""
    kept, ends, runs = [], "", False
    for line in command.splitlines():
        if ends:
            if line.strip() == ends:
                ends = ""
            elif runs:
                kept.append(line)
            continue
        kept.append(line)
        opened = _HEREDOC.search(line)
        if opened:
            ends, runs = opened.group(2), bool(_FEEDS.search(line[: opened.start()]))
    return "\n".join(kept)


def pieces(command: str) -> list[str]:
    """The commands of a shell command line, each as one backticked command. A backslash before a
    newline joins the two lines, as the shell does, and the line is cut at each other
    separator. A quoted string is read as commands of its own after what runs it (`_RUNS_TEXT`),
    as part of its word after `=` or as the command's first word, and otherwise it is an
    argument, a commit message or a title, which runs nothing and is left out."""
    found: list[str] = []
    text, at, now = _unfold(command).replace("\\\n", " "), 0, ""

    def cut() -> None:
        nonlocal now
        if now.strip():
            found.append(f"`{now.strip()}`")
        now = ""

    while at < len(text):
        char = text[at]
        if char in _SEPARATOR:
            cut()
        elif char in "'\"":
            quoted = text[at + 1 :].partition(char)[0]
            at += len(quoted) + 1
            if _RUNS_TEXT.search(now):
                cut()
                found.extend(pieces(quoted))
            elif now.endswith("=") or not now.strip():
                now += quoted
            else:
                now += " _ "
        else:
            now += char
        at += 1
    cut()
    return found


def walks(command: str) -> tuple[tuple[str, str], ...]:
    """The doors a shell command line walks through, each with the command that does."""
    return tuple(found for one in pieces(command) for found in party.walks(one))


def _holds(state: Path, slug: str) -> bool:
    """Whether the row's go is the user's own, read in T3 Code: its last `done` go is an act that
    opens a door (`party.opens`), the user's own words that jbus read, and the row's go holds for
    the brief stored now."""
    from jbus import acts, queue
    from jmerge import judgement

    gos = [
        one
        for one in acts.read(state)
        if one["action"]["verb"] == "go"
        and one["action"]["subject"] == slug
        and one["outcome"] == "done"
    ]
    if not gos:
        return False
    who, said = gos[-1]["party"], gos[-1]["evidence"]
    checked = party.Evidence(said.get("source", ""), "", checked=bool(said.get("checked")))
    if not party.opens(party.Party(who["kind"], who["route"]), checked):
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
        f"the door goes in a row whose brief has Holds: {case}, and jbus queue approve <slug> "
        f"--sha <sha12> --message <thread>/<message>, on {user}'s own message in T3 Code that "
        "names the row, opens it for that row's crew"
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
        f"{door}, and the go of {crew.slug} is not {user}'s own word read in T3 Code: jbus "
        f"queue approve {crew.slug} --sha <sha12> --message <thread>/<message>, on {user}'s own "
        f"message in T3 Code that names {crew.slug}, records it"
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
