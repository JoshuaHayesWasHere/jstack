"""jleak finds what must not leave this machine for a public repo, before it leaves.

The package uses one shape throughout. A `Text` is a named piece of outbound text with its lines
numbered: a file, a branch name, a commit message, the lines a commit adds, a command. A
`Pattern` is a name and a regular expression. `scan` matches every pattern against every line of
every text and gives a `Finding` for each match: where, the line, and the pattern's name. No
finding holds the text that matched, so jleak does not print a key it found a second time.

The patterns come from two places. `BUILT_IN` is in the tree and holds only shapes anyone may
read: the forms of keys. What is private to a machine (a name, a home path, a thread id) is
never in the tree: `load` reads it from the user's own file,

    ${XDG_CONFIG_HOME:-~/.config}/jstack/outbound.toml

    [patterns]
    <name> = '<regular expression>'

The file has one table, `[patterns]`. Each key is a pattern's name, lower case with digits and
`-`, and no built-in pattern's name. Each value is a string, a regular expression of Python's
`re`. jleak matches it against one line at a time, in the case it is written in (`(?i)` at its
start matches any case). The install makes the file with `example`, and never writes it again.
"""

import re
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

FILE = "outbound.toml"
NAME = re.compile(r"[a-z][a-z0-9-]*")


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]


@dataclass(frozen=True)
class Text:
    """Outbound text. `where` is a file or a field, and each line has the number it is
    printed with: its place in a file, or 0 for the file's own name."""

    where: str
    lines: tuple[tuple[int, str], ...]

    @classmethod
    def of(cls, where: str, text: str) -> "Text":
        return cls(where, tuple(enumerate(text.splitlines(), 1)))


@dataclass(frozen=True)
class Finding:
    where: str
    line: int
    pattern: str

    def __str__(self) -> str:
        return f"{self.where}:{self.line}: {self.pattern}"


class Invalid(Exception):
    """The private patterns cannot be used. The error holds the reason as jleak prints
    it, and the reason never holds a pattern's value, since the value is private."""


class Missing(Invalid):
    """There is no private patterns file."""


def _built_in(**shapes: str) -> tuple[Pattern, ...]:
    return tuple(
        Pattern(name.replace("_", "-"), re.compile(shape)) for name, shape in shapes.items()
    )


BUILT_IN = _built_in(
    private_key=r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    github_token=r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{22,})",
    aws_access_key=r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",
    slack_token=r"\bxox[abprs]-(?:[0-9]+-){1,3}[A-Za-z0-9]{10,}",
    anthropic_key=r"\bsk-ant-[A-Za-z0-9_-]{20,}",
)


def scan(texts: Iterable[Text], patterns: Iterable[Pattern]) -> list[Finding]:
    patterns = tuple(patterns)
    return [
        Finding(text.where, number, pattern.name)
        for text in texts
        for number, line in text.lines
        for pattern in patterns
        if pattern.regex.search(line)
    ]


def path(config_home: Path) -> Path:
    """Where the private patterns are, under ${XDG_CONFIG_HOME:-~/.config}."""
    return config_home / "jstack" / FILE


def load(file: Path) -> tuple[Pattern, ...]:
    """The private patterns of `file`. This is the one place that parses them, once.
    Raises Missing when there is no file, and Invalid for one that is not of the shape above."""
    try:
        read = file.read_text()
    except FileNotFoundError:
        raise Missing(f"no private patterns at {file}") from None
    except (OSError, UnicodeDecodeError):
        raise Invalid(f"{file}: it cannot be read") from None
    try:
        value = tomllib.loads(read)
    except tomllib.TOMLDecodeError:
        raise Invalid(f"{file}: it is not TOML") from None
    table = value.get("patterns")
    if not isinstance(table, dict):
        raise Invalid(f"{file}: it has no [patterns] table")
    for key in value:
        if key != "patterns":
            raise Invalid(f"{file}: {key}: only [patterns] is read")
    built_in = {pattern.name for pattern in BUILT_IN}
    found = []
    for name, shape in table.items():
        if not isinstance(shape, str):
            raise Invalid(f"{file}: patterns.{name}: not a string")
        if not NAME.fullmatch(name):
            raise Invalid(f"{file}: patterns.{name}: a name is lower case, with digits and -")
        if name in built_in:
            raise Invalid(f"{file}: patterns.{name}: a built-in pattern has this name")
        try:
            regex = re.compile(shape)
        except re.error:
            raise Invalid(f"{file}: patterns.{name}: not a regular expression") from None
        if regex.search(""):
            raise Invalid(f"{file}: patterns.{name}: it matches an empty line, so every line")
        found.append(Pattern(name, regex))
    return tuple(found)


def example(home: Path) -> str:
    """The file as the install makes it. What the install can know without asking is
    a pattern from the start: the home directory, and the shapes of a thread id and of a
    tailnet's names and addresses. A name it cannot know is an example to fill in, behind a
    `#`."""
    return f"""# What must never leave this machine for a public repo. jleak reads this file,
# and the hooks that call it refuse a push or a pull request that matches. It is yours:
# the install makes it once and never writes it again. Keep it out of every repo.
#
# Each line under [patterns] is  name = 'regular expression'  (Python's re). A pattern is
# held against one line at a time, in the case it is written in: start it with (?i) for
# any case. A finding prints the name, never the text that matched.

[patterns]
home-path = '{re.escape(str(home))}(?![\\w-])'
thread-id = '\\bmcp:[0-9a-f]{{8}}(?:-[0-9a-f]{{4}}){{3}}-[0-9a-f]{{12}}\\b'
tailnet-name = '\\b[a-z0-9-]+\\.ts\\.net\\b'
tailnet-address = '\\b100\\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])(?:\\.[0-9]{{1,3}}){{2}}\\b'

# Fill these in and take the # away:
# user-name = '(?i)\\b(?:alex|alexandra)\\b'
# host-name = '(?i)\\bmy-machine\\b'
# private-repo = '\\b(?:a-private-repo|another-one)\\b'
# state-dir = '\\.local/state/(?:home|jbus)/(?:a-private-repo|another-one)\\b'
"""
