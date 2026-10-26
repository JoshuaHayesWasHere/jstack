"""Infra's files and T3 Code's port are infra's: only the infra home changes them.

`jleak --infra` reads what Claude Code gives a `PreToolUse` hook and refuses, with exit code 2,
a call of any other thread that would change them. Another home sends the infra home the lines
to change, and the infra home makes the change.

    files   `~/.config/jstack/roles` and `~/.config/jbus/config.toml`, the file a link of them
            points to, T3 Code's host and port (`~/.t3/userdata/server-runtime.json`), and the
            units and script that keep 3773 pointed at T3 Code (`~/.config/systemd/user/t3-port-*`,
            `~/.local/bin/t3-port-follow`)
    port    `tailscale serve` or `funnel` on 3773, or its `reset`; `systemctl` on a `t3-port-*`
            unit, but for a verb that only reads; a listener on 3773 (`socat`, `nc`); `fuser -k`
            on 3773

A `Write`, `Edit`, `MultiEdit` or `NotebookEdit` call is refused when its file is one of the
files. A shell command is cut into simple commands as `jleak.sources` cuts it, and one is refused
when it redirects output into one of the files, or names one as a word and is not a command
that only reads it. `cat`, `grep` or `jq` read; `cp` reads its sources and writes its
destination; `sed`, `perl`, `awk`, `yq` and `tomlq` write only with `-i`; `find` writes with
`-delete` or `-exec` in a folder that holds one of the files; a program this module does not know
is taken to write, `sort` among them. The string that `sh -c`, `bash -c` or `eval` runs is read as
a command of its own. A path is read as the shell would expand `~`, `$HOME` and `${HOME}`, against
the folder the command has moved to with `cd`. A command whose quotes do not close is refused when
its text names one of the files, or `tailscale` and 3773.

The infra home and its crew are let through. The test is the repo of the project the session
started in: Claude Code's `CLAUDE_PROJECT_DIR`, else the hook's `cwd`. When that folder's
checkout, a worktree included, is one of the repo named `infra` (git's common dir is
`.../infra/.git`), the call passes. The project, and not the hook's `cwd`, is read first, so a
thread of another repo that moves its shell into infra's checkout is still refused.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

from jleak import sources

INFRA = "infra"
SEND = "send the infra home the lines to change, and it makes the change"
PORT = f"port 3773 and T3 Code's tailnet setup are infra's, so the command is refused: {SEND}"
EDITS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path"}
EDITS["NotebookEdit"] = "notebook_path"
READERS = {
    *("cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg", "jq", "yq", "bat"),
    *("wc", "diff", "cmp", "ls", "stat", "file", "readlink", "realpath", "test", "[", "echo"),
    *("printf", "sha256sum", "md5sum", "b2sum", "fd", "nl", "od", "hexdump", "strings"),
    *("basename", "dirname", "column", "view"),
}
IN_PLACE = {"sed", "perl", "awk", "gawk", "yq", "tomlq"}
SHELLS = {"sh", "bash", "zsh", "dash"}
FIND_WRITES = {"-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls"}
COPIES = {"cp", "install", "rsync", "ln"}
REDIRECT = re.compile(r"[0-9&]*>[>|]?")
THE_PORT = re.compile(r"(?<![0-9])3773(?![0-9])")
LISTEN = re.compile(r"(?i)listen:3773(?![0-9])")
READ_VERBS = {
    *("status", "show", "cat", "list-units", "list-unit-files", "list-timers"),
    *("is-active", "is-enabled", "is-failed", "help"),
}


class Refused(Exception):
    """The call changes what is infra's. Its message is the line the hook says."""


class Guarded:
    """The files that are infra's, under one home."""

    def __init__(self, home: Path, config: Path):
        self.home = home
        self.units = config / "systemd" / "user"
        self.files = {
            path: self.shown(path)
            for path in (
                config / "jstack" / "roles",
                config / "jbus" / "config.toml",
                home / ".t3" / "userdata" / "server-runtime.json",
                home / ".local" / "bin" / "t3-port-follow",
            )
        }
        self.files |= {Path(os.path.realpath(path)): name for path, name in self.files.items()}

    def shown(self, path: Path) -> str:
        return f"~/{path.relative_to(self.home)}" if path.is_relative_to(self.home) else str(path)

    def named(self, word: str, cwd: Path) -> str | None:
        """The name of the guarded file that a word names, read against `cwd`, or None."""
        path = Path(os.path.normpath(cwd / os.path.expandvars(os.path.expanduser(word))))
        for each in (path, Path(os.path.realpath(path))):
            if each in self.files:
                return self.files[each]
            if each.parent == self.units and each.name.startswith("t3-port-"):
                return self.shown(path)
        return None

    def holds(self, word: str, cwd: Path) -> str | None:
        """The name of a guarded file inside the folder a word names, or None."""
        path = Path(os.path.normpath(cwd / os.path.expandvars(os.path.expanduser(word))))
        inside = [name for each, name in self.files.items() if each.is_relative_to(path)]
        if self.units.is_relative_to(path):
            inside.append(self.shown(self.units / "t3-port-*"))
        return inside[0] if inside else None

    def check(self, word: str, cwd: Path) -> None:
        if name := self.named(word, cwd):
            raise Refused(f"{name} is infra's, so the call is refused: {SEND}")

    def mentioned(self, typed: str) -> None:
        """For a command that cannot be cut into words: refuse one whose text names a file."""
        for path in self.files:
            if path.is_relative_to(self.home) and str(path.relative_to(self.home)) in typed:
                self.check(str(path), self.home)
        if "t3-port-" in typed or ("tailscale" in typed and THE_PORT.search(typed)):
            raise Refused(PORT)


def _verb(argv: list[str]) -> tuple[str, list[str]]:
    """A command's first word that is not a flag, and the words after it."""
    for at, word in enumerate(argv[1:], 1):
        if not word.startswith("-"):
            return word, argv[at + 1 :]
    return "", []


def _port(program: str, argv: list[str]) -> None:
    """Refuse a simple command that changes port 3773 or T3 Code's tailnet setup."""
    verb, rest = _verb(argv)
    words = " ".join(argv[1:])
    if program == "tailscale" and verb in ("serve", "funnel"):
        if THE_PORT.search(words) or "reset" in rest:
            raise Refused(PORT)
    elif program == "systemctl" and any(word.startswith("t3-port-") for word in argv):
        if verb not in READ_VERBS:
            raise Refused(PORT)
    elif program in ("socat", "nc", "ncat", "netcat"):
        listens = LISTEN.search(words) or any(re.fullmatch(r"-\w*l\w*", w) for w in argv)
        if listens and THE_PORT.search(words):
            raise Refused(PORT)
    elif program == "fuser" and any(re.fullmatch(r"-\w*k\w*", w) for w in argv):
        if THE_PORT.search(words):
            raise Refused(PORT)


def _files(guarded: Guarded, program: str, argv: list[str], cwd: Path) -> None:
    """Refuse a simple command that writes one of the files by naming it."""
    words = [word for word in argv[1:] if not word.startswith("-")]
    if program in IN_PLACE:
        if any(re.fullmatch(r"-[A-Za-z]*i.*|--in-place.*|inplace", word) for word in argv):
            for word in words:
                guarded.check(word, cwd)
        return
    if program == "find" and any(w in FIND_WRITES for w in argv):
        for word in argv[1:]:
            if word.startswith(("-", "(", "!")):
                break
            if name := guarded.holds(word, cwd):
                raise Refused(f"{name} is infra's, so the call is refused: {SEND}")
        return
    if program == "dd":
        for word in argv[1:]:
            if word.startswith("of="):
                guarded.check(word[3:], cwd)
        return
    if program in COPIES:
        target = next(
            (argv[at + 1] for at, w in enumerate(argv[:-1]) if w in ("-t", "--target-directory")),
            None,
        )
        target = target or next(
            (w.partition("=")[2] for w in argv if w.startswith("--target-directory=")), None
        )
        given = [word for word in words if word != target] if target else words[:-1]
        target = target or (words[-1] if words else "")
        if not target:
            return
        guarded.check(target, cwd)
        for source in given:
            guarded.check(str(Path(target) / Path(source).name), cwd)
        return
    if program in READERS:
        return
    for word in words:
        guarded.check(word, cwd)
    for word in argv[1:]:
        if word.startswith("-") and "=" in word:
            guarded.check(word.partition("=")[2], cwd)


def _command(guarded: Guarded, typed: str, cwd: Path) -> None:
    try:
        simple = sources._simple(typed)
    except ValueError:
        guarded.mentioned(typed)
        return
    for words, here in simple:
        for part in sources._parts(words) if here else [words]:
            argv, at = [], 0
            while at < len(part):
                if REDIRECT.fullmatch(part[at]) and at + 1 < len(part):
                    if not part[at + 1].startswith("&"):
                        guarded.check(part[at + 1], cwd)
                    at += 2
                    continue
                argv.append(part[at])
                at += 1
            argv = sources._run(argv)
            program = Path(argv[0]).name if argv else ""
            if program == "cd" and len(argv) > 1:
                cwd = cwd / os.path.expandvars(os.path.expanduser(argv[1]))
            elif program == "eval":
                _command(guarded, " ".join(argv[1:]), cwd)
            elif program in SHELLS and "-c" in argv[1:-1]:
                _command(guarded, argv[argv.index("-c") + 1], cwd)
            elif program:
                _port(program, argv)
                _files(guarded, program, argv, cwd)


def infra_home(project: Path) -> bool:
    """Whether the project's checkout is one of the infra repo, a worktree of it included."""
    done = subprocess.run(
        ["git", "-C", str(project), "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.returncode == 0 and Path(done.stdout.strip()).parent.name == INFRA


def refuse(given: str) -> int:
    """`--infra`: 2 with the reason on stderr when the call changes what is infra's, else 0."""
    try:
        value = json.loads(given)
        tool, typed = value["tool_name"], value["tool_input"]
        cwd = Path(value.get("cwd") or ".")
    except (ValueError, KeyError, TypeError):
        print("jleak: the hook's input could not be read, so nothing is checked", file=sys.stderr)
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd)
    home = Path.home()
    config = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    guarded = Guarded(home, config)
    try:
        if tool in EDITS and isinstance(typed.get(EDITS[tool]), str):
            guarded.check(typed[EDITS[tool]], cwd)
        elif tool == "Bash" and isinstance(typed.get("command"), str):
            _command(guarded, typed["command"], cwd)
    except Refused as refused:
        if infra_home(project):
            return 0
        print(f"jleak: {refused}", file=sys.stderr)
        return 2
    return 0
