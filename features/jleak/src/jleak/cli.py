"""The `jleak` command has six forms.

    jleak [--strict] [--patterns FILE] --all
    jleak [--strict] [--patterns FILE] [--as FIELD] FILE...
    jleak [--strict] [--patterns FILE] --push URL
    jleak [--strict] [--patterns FILE] --command
    jleak --trailers
    jleak --commit-msg FILE

`--all` checks every tracked file of the repo it runs in. jleak checks a FILE as it is. It
reads `-` as what is piped in, and a finding names that text by the FIELD that `--as` gives.
`--push` reads what git gives a `pre-push` hook. Its URL is the second argument that git passes
the hook. `--command` reads what Claude Code gives a `PreToolUse` hook. It reads the private
patterns only for a command that writes to a pull request, since no other command needs them.

The last two forms read no private pattern: they look for the AI trailers of `jleak.trailers`.
`--trailers` reads what Claude Code or Codex gives a `PreToolUse` hook, and refuses a commit or a
pull request whose text has such a line, with exit code 2. `--commit-msg` reads what git gives a
`commit-msg` hook, takes each such line out of the message file and prints one line that names
them. It exits 0 whatever it finds, since the hook cleans a message and never stops a commit.

It prints one line for each finding, `<file or field>:<line>: <pattern's name>`, then
`<n> findings`. The two hook forms print to stderr, where git and the agent read a refusal.

    0  no finding
    1  a finding
    2  jleak could check nothing, and stderr gives the reason. With `--command`, a finding
       also exits 2, since 2 is the code on which Claude Code refuses the command.

With no private patterns file, jleak checks the built-in patterns and says so on stderr.
Both hooks pass `--strict`. With `--strict`, jleak exits 2 when the private patterns file is
missing. Without that, a hook that checked no private pattern would let every private name
through.
"""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path

import jleak
from jleak import sources, trailers


def parser() -> argparse.ArgumentParser:
    made = argparse.ArgumentParser(
        prog="jleak", description="Find what must not leave this machine, before it leaves."
    )
    made.add_argument("--strict", action="store_true", help="refuse with no private patterns")
    made.add_argument("--patterns", type=Path, help="the private patterns, in place of the file")
    made.add_argument("--as", dest="field", default="stdin", help="what to call the piped text")
    way = made.add_mutually_exclusive_group()
    way.add_argument("--all", action="store_true", help="every tracked file of this repo")
    way.add_argument("--push", metavar="URL", help="what a pre-push hook is given")
    way.add_argument("--command", action="store_true", help="what a PreToolUse hook is given")
    way.add_argument(
        "--trailers", action="store_true", help="what a PreToolUse hook is given, for AI trailers"
    )
    way.add_argument(
        "--commit-msg", metavar="FILE", type=Path, help="what a commit-msg hook is given"
    )
    made.add_argument("files", nargs="*", metavar="FILE", help="a file, or - for the piped text")
    return made


def patterns(args: argparse.Namespace) -> tuple[jleak.Pattern, ...]:
    """The built-in patterns and the private ones. Raises Invalid when jleak cannot use the private
    ones. With `--strict`, a private patterns file that is `Missing` also raises Invalid.
    Without `--strict`, the function says so on stderr and gives the built-in patterns alone."""
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    try:
        private = jleak.load(args.patterns or jleak.path(config))
    except jleak.Missing as missing:
        if args.strict:
            why = "sh install.sh makes the file, and nothing is checked without it"
            raise jleak.Invalid(f"{missing}: {why}") from None
        print(f"jleak: {missing}, so only the built-in ones are checked", file=sys.stderr)
        private = ()
    return (*jleak.BUILT_IN, *private)


def typed(given: str) -> tuple[str, Path]:
    """The command and the directory it runs in, from a PreToolUse hook's input. A tool that
    is not the shell has no command."""
    try:
        value = json.loads(given)
        if value["tool_name"] != "Bash":
            return "", Path()
        command = value["tool_input"]["command"]
        cwd = value.get("cwd") or "."
    except (ValueError, KeyError, TypeError):
        raise sources.Unreadable("the hook's input could not be read") from None
    if not isinstance(command, str) or not isinstance(cwd, str):
        raise sources.Unreadable("the hook's input could not be read")
    return command, Path(cwd)


def count(found: Sequence[jleak.Finding]) -> str:
    return f"{len(found)} finding{'' if len(found) == 1 else 's'}"


def refuse_trailers(given: str) -> int:
    """`--trailers`: 2 with each finding on stderr when the command writes an AI trailer, else
    0."""
    try:
        command, cwd = typed(given)
    except sources.Unreadable as error:
        print(f"jleak: {error}, so nothing is checked", file=sys.stderr)
        return 0
    found = jleak.scan(sources.messages(command, cwd), trailers.PATTERNS)
    for finding in found:
        print(finding, file=sys.stderr)
    if not found:
        return 0
    many = "" if len(found) == 1 else "s"
    again = "drop the line and commit again"
    print(
        f"jleak: {len(found)} AI trailer{many}, so the command is refused: {again}", file=sys.stderr
    )
    return 2


def clean_message(file: Path) -> int:
    """`--commit-msg`: take the AI trailers out of the message file, and name them."""
    try:
        message = file.read_text()
        cleaned, taken = trailers.strip(message)
        if taken:
            file.write_text(cleaned)
    except (OSError, UnicodeError) as error:
        print(f"jleak: the commit message could not be cleaned: {error}", file=sys.stderr)
        return 0
    if taken:
        print(f"jleak: took out of the commit message: {' | '.join(taken)}", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.trailers:
        return refuse_trailers(sys.stdin.read())
    if args.commit_msg:
        return clean_message(args.commit_msg)
    if not (args.all or args.push or args.command or args.files):
        parser().print_usage(sys.stderr)
        return 2
    try:
        if args.command:
            command, cwd = typed(sys.stdin.read())
            found, sent = sources.command(command, cwd)
            found += jleak.scan(sent, patterns(args)) if sent else []
        elif args.push:
            found = jleak.scan(sources.pushed(sys.stdin, args.push), patterns(args))
        elif args.all:
            found = jleak.scan(sources.tree(Path.cwd()), patterns(args))
        else:
            piped = sys.stdin.read() if "-" in args.files else ""
            found = jleak.scan(sources.files(args.files, piped, args.field), patterns(args))
    except jleak.Invalid as error:
        print(f"jleak: {error}", file=sys.stderr)
        return 2
    except sources.Unreadable as error:
        print(f"jleak: {error}, so nothing is checked", file=sys.stderr)
        return 2
    hook = bool(args.push or args.command)
    for finding in found:
        print(finding, file=sys.stderr if hook else sys.stdout)
    if not hook:
        print(count(found))
    elif found and args.push:
        print(f"jleak: {count(found)}, so the push is refused", file=sys.stderr)
    elif found:
        again = "take the text out and run it again"
        print(f"jleak: {count(found)}, so the command is refused: {again}", file=sys.stderr)
    return (2 if args.command else 1) if found else 0
