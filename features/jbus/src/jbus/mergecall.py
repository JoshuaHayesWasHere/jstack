"""Whether a thread's own shell command merges a pull request outside `jmerge`, read by
`features/jbus/hooks/merge-command.sh` before an agent's harness runs a `Bash` command.

`jmerge` is the one merger of a repo jbus's config names as a project: its merge reads the
review, the checks at the head over today's base and the line, writes its `merged` line to
`merge.log` and ends it on the command that reverts it. An agent's own `gh pr merge` does none of
that, and from 2026-10-15 to 2026-11-05 homes merged 26 pull requests that way, most on the
user's word, one (#164) on a check run before main moved, which broke main. The user's word to
merge stands, and goes through `jmerge --accept <number> --as user --message <thread>/<message>`,
which reads the message from T3 Code and logs the merge: the refusal prints that line.

A command merges (`merges`) where one of its simple commands is

- `gh pr merge`, with any flags, `--auto` and `--admin` too;
- `gh api` on a pull request's `/merge` endpoint, `repos/<owner>/<repo>/pulls/<number>/merge`,
  with any method;
- `gh api graphql` whose words name `mergePullRequest` or `enablePullRequestAutoMerge`.

The command line is read as the shell reads it, in simple commands cut at `;`, `&`, `|`, `(`, `)`
and newlines (`shlex`), with a quoted string run by `sh -c` or `eval` read as commands of its own,
and a heredoc's body left out but where it feeds a shell (`door._unfold`). A word quoted as an
argument, a commit message naming `gh pr merge`, runs nothing. Before `gh` it skips what only
runs the next word: an assignment, `env`, `command`, `exec`, `time`, `nohup`, `xargs`,
`timeout` and its duration, `sudo`, `nice`, and the shell's `if`, `elif`, `while`, `until`, `do`,
`then`, `else`, `{` and `!`, so a retry loop such as `until gh pr merge 5; do sleep 30; done` is
read too.

The repo a merge is of is the one its `--repo` (or `GH_REPO`, or the endpoint's
`repos/<owner>/<repo>`) names, matched to a project by its `origin` remote, and otherwise the
repo of the directory the command is in there: the call's `cwd`, moved by each `cd` or `pushd`
before it to a path it names literally or through `~`. A `cd` to a path the command cannot know
(`cd "$dir"`) leaves the directory as it was. The merge is refused where that repo is a project
of jbus's config (`port.project`), whoever runs it, and let through elsewhere: in a repo jbus
does not manage, and after the command sources the `env.sh` of a verify-jstack sandbox (a
directory with `.verify-jstack-sandbox`), whose `gh` is the stand-in that merges nothing. A
config that is there and does not load refuses the merge, so a broken config fails closed.

The pull request's number is read from the merge: `gh pr merge 12`, `#12` or its URL, the
endpoint's number, and `$n` of a `for n in 12 13` loop the same command runs, one line for each.
A merge that names it otherwise (a branch, `$1`) gets `<number>`, as a GraphQL one does. The
thread on the line is the one T3 Code's store runs the session in, where it has it.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jbriefs import sends
from jbus import Refused, door, port
from jsettings import paths

SANDBOX = ".verify-jstack-sandbox"
"""The marker file `launch.sh` of the verify-jstack skill writes first in a sandbox."""
NUMBER = "<number>"
_PUNCTUATION = set(";&|()")
_PASS_ON = {
    "do",
    "then",
    "else",
    "if",
    "elif",
    "while",
    "until",
    "{",
    "!",
    "command",
    "exec",
    "time",
    "nohup",
}
_ASSIGN = re.compile(r"[A-Za-z_]\w*=.*", re.S)
_VARIABLE = re.compile(r"\$(?:\{(\w+)\}|(\w+))")
_SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
_ENDPOINT = re.compile(r"^/?repos/([^/\s]+)/([^/\s]+)/pulls/([^/\s]+)/merge/?$")
_MUTATIONS = re.compile(r"\b(?:mergePullRequest|enablePullRequestAutoMerge)\b")
_URL = re.compile(r"github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
_REMOTE = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$")
_MERGE_TAKES_ONE = {
    "-R",
    "--repo",
    "-b",
    "--body",
    "-F",
    "--body-file",
    "-t",
    "--subject",
    "-A",
    "--author-email",
    "--match-head-commit",
}
_API_TAKES_ONE = {
    "-R",
    "--repo",
    "-X",
    "--method",
    "-H",
    "--header",
    "-f",
    "--raw-field",
    "-F",
    "--field",
    "-q",
    "--jq",
    "-t",
    "--template",
    "--hostname",
    "--input",
    "-p",
    "--preview",
    "--cache",
}
_WRAPPERS = {
    "xargs": {"-n", "-I", "-L", "-P", "-d", "-E", "-s", "-a"},
    "timeout": {"-s", "--signal", "-k", "--kill-after"},
    "sudo": {"-u", "--user", "-g", "--group", "-h", "--host", "-C", "-D", "-p", "-r", "-t"},
    "nice": {"-n", "--adjustment"},
}
"""What runs the words after its flags, by name, with its flags whose value is the next word.
`timeout` takes its duration too, before the command."""


@dataclass(frozen=True)
class Merge:
    """One merge a command runs: its words, the pull request's number (`NUMBER` where the command
    does not name it), the `owner/repo` it names, and the directory it runs in, None where a
    `cd` went to a path the command cannot know."""

    words: str
    number: str
    names: str
    at: Path | None


def merges(command: str, cwd: Path) -> list[Merge]:
    """Each merge of a pull request the command line runs, in order, but those after it sources
    a verify-jstack sandbox's `env.sh`."""
    return list(_read(door._unfold(command).replace("\\\n", " "), cwd, {}))


def _commands(text: str) -> list[list[str]]:
    """The simple commands of a shell command line, each as its words with the quotes taken
    off, or none where the shell would not read it either (an unclosed quote)."""
    lexer = shlex.shlex(text.replace("\n", ";"), posix=True, punctuation_chars=";&|()")
    lexer.whitespace_split = True
    found: list[list[str]] = [[]]
    try:
        for word in lexer:
            if set(word) <= _PUNCTUATION:
                found.append([])
            else:
                found[-1].append(word)
    except ValueError:
        return []
    return [one for one in found if one]


def _read(text: str, at: Path | None, loops: dict[str, list[str]]) -> Iterator[Merge]:
    for words in _commands(text):
        words = _bare(words)
        if not words:
            continue
        verb = words[0].rpartition("/")[2]
        if verb == "for" and len(words) > 2 and words[2] == "in":
            loops[words[1]] = words[3:]
            continue
        if verb in ("cd", "pushd"):
            at = _moved(at, words[1:])
            continue
        if verb in (".", "source") and len(words) > 1 and _sandboxed(at, words[1]):
            return
        if verb in _SHELLS:
            ran = next(
                (one for one, flag in zip(words[2:], words[1:], strict=False) if _runs(flag)), None
            )
            if ran is not None:
                yield from _read(ran, at, loops)
            continue
        if verb == "eval":
            yield from _read(" ".join(words[1:]), at, loops)
            continue
        if verb == "gh":
            yield from _gh(words, at, loops)


def _bare(words: list[str]) -> list[str]:
    """The words from the command that runs: with what only runs the next word taken off, and an
    assignment of `GH_REPO` kept in front as `--repo`."""
    repo: list[str] = []
    while words:
        first = words[0]
        if _ASSIGN.fullmatch(first):
            name, _, value = first.partition("=")
            repo = ["--repo", value] if name == "GH_REPO" else repo
            words = words[1:]
        elif first == "env":
            words = _after_env(words[1:])
        elif first in _PASS_ON:
            words = words[1:]
        elif (wrapper := first.rpartition("/")[2]) in _WRAPPERS:
            words = _after(words[1:], _WRAPPERS[wrapper])
            words = words[1:] if wrapper == "timeout" else words
        else:
            break
    if repo and words and words[0].rpartition("/")[2] == "gh":
        return [words[0], *repo, *words[1:]]
    return words


def _after_env(words: list[str]) -> list[str]:
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in ("-u", "--unset", "-C", "--chdir") else words[1:]
    return words


def _after(words: list[str], takes_one: set[str]) -> list[str]:
    while words and words[0].startswith("-"):
        words = words[2:] if words[0] in takes_one else words[1:]
    return words


def _runs(flag: str) -> bool:
    """Whether a shell's flag runs the next word as commands: `-c`, alone or last of a group."""
    return flag.startswith("-") and not flag.startswith("--") and flag.endswith("c")


def _moved(at: Path | None, words: list[str]) -> Path | None:
    words = [one for one in words if not one.startswith("-") or one == "-"]
    target = words[0] if words else "~"
    if target == "~" or target.startswith("~/"):
        target = str(Path.home()) + target[1:]
    if target == "-" or "$" in target or "`" in target:
        return at
    if os.path.isabs(target):
        return Path(os.path.normpath(target))
    return Path(os.path.normpath(at / target)) if at is not None else None


def _sandboxed(at: Path | None, sourced: str) -> bool:
    if sourced == "~" or sourced.startswith("~/"):
        sourced = str(Path.home()) + sourced[1:]
    if "$" in sourced or "`" in sourced or Path(sourced).name != "env.sh":
        return False
    path = Path(sourced) if os.path.isabs(sourced) or at is None else at / sourced
    return (path.parent / SANDBOX).is_file()


def _gh(words: list[str], at: Path | None, loops: dict[str, list[str]]) -> Iterator[Merge]:
    shown = shlex.join(words)
    repo, rest = "", []
    given = iter(words[1:])
    for word in given:
        if word in ("-R", "--repo"):
            repo = next(given, "")
        elif word.startswith("--repo="):
            repo = word.partition("=")[2]
        else:
            rest.append(word)
    if rest[:2] == ["pr", "merge"]:
        named = _after(rest[2:], _MERGE_TAKES_ONE)
        picked = named[0] if named else ""
        if found := _URL.search(picked):
            repo, picked = f"{found.group(1)}/{found.group(2)}", found.group(3)
        for number in _numbers(picked.removeprefix("#"), loops):
            yield Merge(shown, number, repo, at)
    elif rest[:1] == ["api"]:
        endpoint = _after(rest[1:], _API_TAKES_ONE)
        path = endpoint[0] if endpoint else ""
        if found := _ENDPOINT.match(path):
            owner, name, number = found.groups()
            if "{" not in owner:
                repo = f"{owner}/{name}"
            for one in _numbers(number, loops):
                yield Merge(shown, one, repo, at)
        elif path == "graphql" and _MUTATIONS.search(" ".join(rest)):
            yield Merge(shown, NUMBER, repo, at)


def _numbers(word: str, loops: dict[str, list[str]]) -> list[str]:
    """The numbers a pull request's word names: itself where it is one, each number of the loop
    whose variable it is, and `NUMBER` otherwise."""
    if word.isdigit():
        return [word]
    found = _VARIABLE.fullmatch(word)
    looped = loops.get((found.group(1) or found.group(2)) if found else "", [])
    numbers = [one for one in looped if one.isdigit()]
    return numbers if numbers and len(numbers) == len(looped) else [NUMBER]


def _origin(checkout: Path) -> str:
    """The `owner/repo` of the checkout's `origin` on GitHub, in lower case, or nothing."""
    try:
        config = (paths.common_dir(checkout) or checkout / ".git") / "config"
        text = config.read_text(errors="replace")
    except OSError:
        return ""
    url = ""
    within = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            within = stripped == '[remote "origin"]'
        elif within and stripped.replace(" ", "").startswith("url="):
            url = stripped.partition("=")[2].strip()
    found = _REMOTE.search(url)
    return f"{found.group(1)}/{found.group(2)}".lower() if found else ""


def _project(merge: Merge, cwd: Path) -> Path | None:
    """The main checkout of the project of jbus's the merge is of, or None where it is of no
    project. Raise `jbus.Refused` where jbus's config is there and does not load."""
    if merge.names:
        import jbus

        try:
            config = jbus.load()
        except jbus.Refused:
            if (jbus.config_dir() / "config.toml").exists():
                raise
            return None
        wanted = merge.names.lower().removesuffix(".git")
        return next(
            (one.checkout for one in config.projects if _origin(one.checkout) == wanted),
            None,
        )
    checkout = paths.main_checkout(merge.at or cwd)
    if checkout is None:
        return None
    found = port.project(checkout)
    return checkout if found else None


def refusal(command: str, cwd: Path, thread: str) -> str:
    """Why the command may not run, or nothing where it may."""
    lines: list[str] = []
    first = ""
    for merge in merges(command, cwd):
        try:
            checkout = _project(merge, cwd)
        except Refused as error:
            return (
                f"`{merge.words}` merges a pull request, and jbus's config does not load, so "
                f"the hook cannot tell whether jmerge is its repo's merger ({error})"
            )
        if checkout is None:
            continue
        first = first or f"`{merge.words}` merges a pull request of {checkout.name}"
        lines.append(
            f"cd {shlex.quote(str(checkout))} && jmerge --accept {merge.number} --as user "
            f"--message {thread or '<thread id>'}/<message id>"
        )
    if not lines:
        return ""
    run = "\n".join(f"  {one}" for one in dict.fromkeys(lines))
    return (
        f"{first} outside jmerge, its one merger, so no merge.log line, no revert line and "
        "none of jmerge's reads. On the user's own word to merge it, run in its place, with the "
        "id of that message in T3 Code:\n"
        f"{run}\n"
        "jmerge merges it where the accept lifts what holds it, and says why where it does not. "
        "With no such word, the pull request is jmerge's to merge when it is ready."
    )


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
    if not command:
        return 0
    cwd = Path(str(call.get("cwd") or os.getcwd()))
    if not merges(command, cwd):
        return 0
    thread = sends.thread_of_session(str(call.get("session_id") or ""), Path.home() / sends.STORE)
    why = refusal(command, cwd, thread)
    if not why:
        return 0
    print(f"merge-command: refused: {why}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
