"""Whether a thread's own shell command may walk through a door, read by
`features/jbus/hooks/door-command.sh` before an agent's harness runs a `Bash` command.

A door is a case of `templates/gates.md`, and the commands that walk through one are the `runs`
of `party.DOORS`, the table a brief's commands are read by (`party.walks`). jbus's go and answer
paths are the main check: a row whose brief walks through a door goes only on the user's own word,
read in T3 Code, in reply to an ask about that row alone. This hook is the second, for what a
thread runs itself:

- a home's or a scout's command that walks through a door is refused: the door goes in a row
  whose brief has `Holds: <case>`, and the user's own plain reply in T3 Code, to the home's ask
  about that row, opens it for that row's crew;
- a crew's command goes only where its row's go is a `done` act on the user's own words that jbus
  read (`party.opens`), and still holds for the brief stored now;
- any other thread, and a session T3 Code's store does not know, is let through, as
  `jbriefs.sends` lets a send through.

A thread may remove a worktree it added itself, such as a bisect's or a proof's copy in `/tmp`,
with no door (`_own_removes`). The hook keeps each `git worktree add` it reads, with its path and
its thread, in `OWN` in the repo's jbus state, where a path is the thread's that added it last.
A path counts only where the command names it: literally, or through a variable the same command
sets to one. One added through `$(mktemp -d)`, or named through a variable an earlier command set,
is no thread's, and its remove keeps the door. A path that is already something when it is added,
such as another thread's worktree, is not taken.

A command is read in pieces (`pieces`): cut at each shell separator, backtick and parenthesis,
with a quoted string read as a command of its own where `ssh`, `bash -c` or `eval` runs it, and
left out where it is an argument such as a commit message or a title, but for one word that is
a flag or a refspec (`"--force"`, `'+main'`), which is read as that word, so that `party.walks`
reads a quoted flag or refspec as it reads a bare one. A heredoc's body is left out, since it
is text a command reads, but where it feeds a shell or `ssh`, whose commands it is. A command
that runs dry walks through nothing (`party.DRY`). A home can still wrap a door in a script of
its own, which is why the go path is the main check.

Every refusing hook of jstack (this one, `agent-sends`, `merge-command` and jleak's three) judges
through `features/jbus/hooks/judge.sh`. The hook sets `hook` (its name), `input` (what the harness
gave it on stdin) and `source` (jstack's source tree), sources the file, and calls `judge <module>
[<argument>...]`, which ends the hook. The module reads the call on stdin and ends 0 to let it
through, or 2 to refuse it with its reason on stderr. A hook that cannot judge refuses: a module
that ends any other way, one that runs past `JSTACK_HOOK_SECONDS` (25 by default, inside the 30 the
harness gives the hook), and a machine with no Python 3.12 or newer each end it 2 too. The time is
kept by the module's own Python, with `signal.alarm`, so it holds where no `timeout` command is, as
on macOS.

Each refusal adds one quiet `hook` event, declared here, to the jbus log of the repo the call ran
in, where jbus keeps one: the hook, the head of the call and the reason. A hook that sets
`withheld`, as jleak's do, logs the tool's name in place of the call, since the call it refused
may hold a private pattern, which jleak's own reasons never repeat. The shell writes it, not
Python, so a refusal for want of Python is logged too, and writes it as plain ASCII, since jbus
reads the log as UTF-8 and a cut could split a character. A machine without the tools the line
needs (`git`, `sed`, `date` and the like) still refuses, and logs nothing.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

import jsettings
from jbriefs import home, sends
from jbus import party
from jsettings import paths

EVENTS = {"hook": "quiet"}
OWN = "own-worktrees.jsonl"
"""Each `git worktree add` the hook read, one JSON line `{"thread", "path"}`, in the repo's jbus
state."""

_HEREDOC = re.compile(r"(?<!<)<<(?!<)-?\s*(['\"]?)(\w+)\1")
_SEPARATOR = set(";&|\n()`")
_SHELL = r"(?:\S*/)?(?:ba|z|da|k)?sh"
_RUNS_TEXT = re.compile(rf"(?:^|\s){_SHELL}(?:\s+-\w+)*\s+-[a-z]*c\s*$|\bssh\s|\beval\s*$")
"""What runs the quoted text after it as a command: `bash -c`, with `-c` alone or last of a group
of flags as in `bash -lc`, `ssh <host>`, `eval`."""
_FEEDS = re.compile(rf"(?:^|[;&|(]\s*|\s){_SHELL}\b[^<]*$|\bssh\s[^<]*$")
"""What runs a heredoc's body as commands: a shell, or `ssh <host>`, before the `<<`."""
_FLAG = re.compile(r"[-+:][^\s'\"]+")
"""A quoted word the command reads as a flag or a refspec: `"--force"`, `'-D'`, `'+main'`."""


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
            elif now.endswith("=") or not now.strip() or _FLAG.fullmatch(quoted):
                now += quoted
            else:
                now += " _ "
        else:
            now += char
        at += 1
    cut()
    return found


_REMOVE = re.compile(r"\bworktree\s+remove\b")
_VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")
_ASSIGN = re.compile(r"([A-Za-z_]\w*)=(.*)", re.S)
_TAKES_ONE = {"-b", "-B", "--reason"}
"""The flags of `git worktree add` whose value is the next word."""
_GIT_TAKES_ONE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def worktrees(command: str) -> list[tuple[str, Path | None]]:
    """Each `git worktree add` and `git worktree remove` of the command line, in order, as `add`
    or `remove` with the absolute path it names, or None where the path is relative or names a
    variable the command does not set to a plain value. A command quoted inside another, as in
    `bash -c`, is not read here."""
    text = _unfold(command).replace("\\\n", " ").replace("\n", ";")
    lexer = shlex.shlex(text, posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    try:
        words = list(lexer)
    except ValueError:
        return []
    found: list[tuple[str, Path | None]] = []
    known: dict[str, str | None] = {}
    one: list[str] = []
    for word in [*words, ";"]:
        if set(word) <= set(";&|()"):
            _read(one, known, found)
            one = []
        else:
            one.append(word)
    return found


def _read(
    words: list[str], known: dict[str, str | None], found: list[tuple[str, Path | None]]
) -> None:
    """Read one simple command: a bare assignment sets a variable, a worktree add or remove is
    found."""
    sets = [match for word in words if (match := _ASSIGN.fullmatch(word))]
    if words and len(sets) == len(words):
        for match in sets:
            known[match.group(1)] = _expand(match.group(2), known)
        return
    while words and _ASSIGN.fullmatch(words[0]):
        words = words[1:]
    if not words or words[0].rpartition("/")[2] != "git":
        return
    at = 1
    while at < len(words) and words[at].startswith("-"):
        at += 2 if words[at] in _GIT_TAKES_ONE else 1
    verb = words[at + 1] if words[at : at + 1] == ["worktree"] and at + 1 < len(words) else ""
    if verb not in ("add", "remove"):
        return
    rest = iter(words[at + 2 :])
    for word in rest:
        if word in _TAKES_ONE:
            next(rest, "")
            continue
        if word.startswith("-"):
            continue
        path = _expand(word, known)
        absolute = path is not None and os.path.isabs(path)
        found.append((verb, Path(os.path.normpath(path)) if absolute and path else None))
        return


def _expand(word: str, known: dict[str, str | None]) -> str | None:
    """The word with `~` and the variables the command set put in, or None where it names
    another or runs a command."""
    if word == "~" or word.startswith("~/"):
        word = str(Path.home()) + word[1:]
    missing = False

    def put(match: re.Match[str]) -> str:
        nonlocal missing
        value = known.get(match.group(1) or match.group(2))
        missing = missing or value is None
        return value or ""

    word = _VARIABLE.sub(put, word)
    return None if missing or "$" in word or "`" in word else word


def _made(buses: Path, thread: str) -> set[Path]:
    """The paths whose last add the hook read was the thread's."""
    last: dict[Path, str] = {}
    try:
        lines = (buses / OWN).read_text(errors="replace").splitlines()
    except OSError:
        return set()
    for line in lines:
        try:
            one = json.loads(line)
            last[Path(one["path"])] = one["thread"]
        except (ValueError, KeyError, TypeError):
            continue
    return {path for path, who in last.items() if who == thread}


def _keep(buses: Path, thread: str, command: str) -> None:
    """Keep each path the command adds a worktree at as the thread's, where it is nothing yet
    or an empty directory, such as one `mktemp -d` made."""
    added = [
        path
        for verb, path in worktrees(command)
        if verb == "add" and path and not (path.exists() and any(_entries(path)))
    ]
    if not added:
        return
    buses.mkdir(parents=True, exist_ok=True)
    with (buses / OWN).open("a") as kept:
        kept.write("".join(json.dumps({"thread": thread, "path": str(p)}) + "\n" for p in added))


def _entries(path: Path) -> list[Path]:
    """What is in the directory, or the path itself where it is no directory."""
    return list(path.iterdir()) if path.is_dir() else [path]


def _own_removes(
    buses: Path, thread: str, command: str, walked: tuple[tuple[str, str], ...]
) -> tuple[tuple[str, str], ...]:
    """The doors walked, but for the worktree removes where each one the command runs removes a
    worktree the thread added itself."""
    removes = [path for verb, path in worktrees(command) if verb == "remove"]
    counted = sum(1 for _, matched in walked if _REMOVE.search(matched))
    if not removes or len(removes) < counted or not set(removes) <= _made(buses, thread):
        return walked
    return tuple(one for one in walked if not _REMOVE.search(one[1]))


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
    walked = _own_removes(buses, thread, command, walks(command))
    if not walked:
        return ""
    case, matched = walked[0]
    user = _user()
    door = f"`{matched}` walks through a door ({case})"
    if _REMOVE.search(matched):
        door += (
            ", as a worktree this thread did not add: one it added at a path its command named, "
            "literally or through a variable that command set, it may remove"
        )
    row = (
        f"the door goes in a row whose brief has Holds: {case}; ask {user} about that row alone, "
        "in plain words, and pass their reply: jbus queue approve <slug> --sha <sha12> --message "
        f"<thread>/<message>, on {user}'s own reply in T3 Code, opens it for that row's crew"
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
        f"{door}, and the go of {crew.slug} is not {user}'s own word read in T3 Code: ask "
        f"{user} about {crew.slug} alone, in plain words, and pass their reply: jbus queue "
        f"approve {crew.slug} --sha <sha12> --message <thread>/<message>, on {user}'s own reply "
        "in T3 Code, records it"
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
    adds = any(verb == "add" for verb, _ in worktrees(command)) if command else False
    if not command or not (adds or walks(command)):
        return 0
    repo = sends.repo_of(str(call.get("cwd") or ""))
    state = home.homes_dir() / repo
    if not repo or not state.is_dir():
        return 0
    thread = sends.thread_of_session(str(call.get("session_id") or ""), Path.home() / sends.STORE)
    if not thread:
        return 0
    buses = paths.jbus_state_dir() / repo
    _keep(buses, thread, command)
    why = refusal(state, buses, thread, command)
    if not why:
        return 0
    print(f"door-command: refused: {why}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
