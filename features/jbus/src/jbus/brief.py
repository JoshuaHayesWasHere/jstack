"""`jbus brief new|set|append <brief>`: the one writer of a home's brief, `tasks/<slug>.md`, or of a
scout's request, `scouts/<slug>.md`.

- `new` writes the whole brief from stdin. It replaces a brief no thread has taken up (`taken`: no
  `Thread:` line in the head and no `## ` section), and refuses one a thread has taken up.
- `set <Label:> <value>` puts one line in the head, the lines above the first `## `: it replaces the
  head's line of that label, or adds the line after the head's last line that is not blank. With
  `--result` it does the same in the last Result, the last `## Result` or `## Report` section.
- `append` adds the lines on stdin at the end of the last Result, before any section after it.
  Where stdin starts with `## `, or the brief has no Result, they go at the end of the brief.

Each prints the one line it wrote, or `unchanged:` where `new` or `set` found the brief as asked,
and `set` and `append` refuse a brief that is not there.

Every write is `change`: it takes the brief's lock, reads the brief as it is under the lock, makes
one pure edit (`with_line`, `appended`) and replaces the file through a temp file. So no reader sees
half a brief, and no writer drops a line another wrote between its read and its write. The lock is
one file per brief, `<home>/.locks/<kind>-<slug>.lock`, not the brief itself, since `os.replace`
puts a new file in the brief's place and a lock on the old one would guard nothing. Writers of two
briefs share nothing and do not wait on each other. The brief's lock is always the innermost one: a
caller may hold `queue.lock` or `questions.lock` around a write, but nothing takes a lock while it
holds a brief's, and an edit given to `change` must not write a brief itself, since a second
`flock` of the same lock file blocks even in the same process.

The text is split at lines that start with `## `, as every `awk '/^## /'` reader of a brief splits
it, and a code fence does not hide a heading.
"""

from __future__ import annotations

import argparse
import os
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import jbus
from jbus import verbs
from jsettings import store

KINDS = ("tasks", "scouts")
LABEL = re.compile(r"[A-Z][A-Za-z0-9 ]*:")
RESULT = re.compile(r"## (Result|Report)($|[ ,])")


class Missing(jbus.Refused):
    """No brief at the path."""


class Taken(jbus.Refused):
    """`new` over a brief a thread has taken up."""


class NoResult(jbus.Refused):
    """`set --result` on a brief with no Result."""


class Malformed(jbus.Refused):
    """A label, a value or a text the verb cannot place."""


@dataclass(frozen=True)
class Brief:
    """A brief or a scout's request, `<home>/<kind>/<slug>.md`, parsed from a path at the edge."""

    home: Path
    kind: str
    slug: str

    @classmethod
    def at(cls, given: str | Path) -> Brief:
        path = Path(given).expanduser().resolve()
        if path.suffix != ".md" or path.parent.name not in KINDS:
            raise jbus.Refused(
                f"refused: {given} is no brief, which is <home>/tasks/<slug>.md or "
                "<home>/scouts/<slug>.md"
            )
        return cls(path.parent.parent, path.parent.name, path.stem)

    @property
    def path(self) -> Path:
        return self.home / self.kind / f"{self.slug}.md"

    @property
    def named(self) -> str:
        return f"{self.kind}/{self.slug}.md"


@dataclass(frozen=True)
class Wrote:
    """What a write did: whether it changed the brief, and the one line the verb prints."""

    changed: bool
    said: str


# The pure core: each takes a brief's text and returns the new text.


def _head_end(lines: list[str]) -> int:
    return next((at for at, one in enumerate(lines) if one.startswith("## ")), len(lines))


def last_result(lines: list[str]) -> tuple[int, int] | None:
    """The span of the last Result or Report: its heading's line, and the line of the next `## `
    after it or the end."""
    found = [at for at, one in enumerate(lines) if RESULT.match(one)]
    if not found:
        return None
    start = found[-1]
    end = next((at for at in range(start + 1, len(lines)) if lines[at].startswith("## ")), None)
    return start, len(lines) if end is None else end


def _after_text(lines: list[str], start: int, end: int) -> int:
    """The line after the last line of `start..end` that is not blank, or `start`."""
    return next((at + 1 for at in range(end - 1, start - 1, -1) if lines[at].strip()), start)


def _labelled(line: str, label: str) -> bool:
    return line == label or line.startswith(label + " ")


def _text(lines: list[str]) -> str:
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) + "\n"


def taken(text: str) -> bool:
    """Whether a thread has taken the brief up: a `Thread:` line in its head, or a section."""
    lines = text.splitlines()
    end = _head_end(lines)
    return end < len(lines) or any(_labelled(one, "Thread:") for one in lines[:end])


def with_line(text: str, label: str, value: str, *, result: bool = False) -> str:
    """The text with `<label> <value>` in its head, or in its last Result with `result`: in place
    of the line of that label (in the head the first, in the Result the last), or after the
    place's last line that is not blank."""
    lines = text.splitlines()
    if result:
        span = last_result(lines)
        if span is None:
            raise NoResult("refused: the brief has no Result to set a line in")
        start, end = span[0] + 1, span[1]
    else:
        start, end = 0, _head_end(lines)
    found = [at for at in range(start, end) if _labelled(lines[at], label)]
    line = f"{label} {value}"
    if not found:
        lines.insert(_after_text(lines, start, end), line)
        return _text(lines)
    at = found[-1] if result else found[0]
    following = next((one for one in lines[at + 1 : end] if one.strip()), "")
    if lines[at] == label and following.startswith("- "):
        raise Malformed(f"refused: {label} heads a list, and set writes one line")
    lines[at] = line
    return _text(lines)


def _block(text: str) -> list[str]:
    """The lines of an append, with no blank lines before or after them."""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        raise Malformed("refused: stdin holds no lines to append")
    if not lines[0].startswith("## ") and any(one.startswith("## ") for one in lines):
        raise Malformed(
            "refused: stdin starts with lines and then has a section: append the lines and the "
            "section apart"
        )
    return lines


def appended(text: str, block: str) -> str:
    """The text with the lines of `block` at the end of its last Result, before any section after
    it, or at the end of the brief where `block` starts with `## ` or there is no Result."""
    lines, added = text.splitlines(), _block(block)
    span = None if added[0].startswith("## ") else last_result(lines)
    if span is None:
        kept = _text(lines).splitlines()
        gap = [""] if kept and added[0].startswith("## ") else []
        return _text([*kept, *gap, *added])
    at = _after_text(lines, span[0] + 1, span[1])
    after = lines[at:]
    gap = [""] if after and after[0].startswith("## ") else []
    return _text([*lines[:at], *added, *gap, *after])


# The shell: the lock, the read under it, and the write through a temp file.


@contextmanager
def _locked(one: Brief) -> Iterator[None]:
    with store.locked(one.home / ".locks", f"{one.kind}-{one.slug}.lock"):
        yield


def _write(path: Path, text: str) -> None:
    """Write the brief whole, as `jsettings.store.write_json` writes a JSON file: a temp file of
    this process's own beside it, then a rename, keeping the brief's mode."""
    try:
        mode = path.stat().st_mode & 0o7777
    except FileNotFoundError:
        mode = 0o644
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    handle = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    try:
        try:
            os.write(handle, text.encode())
            os.fsync(handle)
        finally:
            os.close(handle)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _change(one: Brief, edit: Callable[[str | None], str | None], *, create: bool = False) -> bool:
    """Run `edit` on the brief as it is under its lock, None where it is not there, and write what
    it returns. Without `create`, a brief that is not there is refused before its lock is made."""
    if not create:
        _there(one, None if not one.path.exists() else "")
    with _locked(one):
        try:
            was: str | None = one.path.read_text()
        except FileNotFoundError:
            was = None
        text = edit(was)
        if text is None or text == was:
            return False
        _write(one.path, text)
        return True


def _there(one: Brief, text: str | None) -> str:
    if text is None:
        raise Missing(f"refused: no brief at {one.path}")
    return text


def change(path: str | Path, edit: Callable[[str], str | None]) -> Wrote:
    """Make one edit to the brief under its lock: `edit` gets the brief as it is under the lock and
    returns the new text, or None for no change. It must be pure: no lock, and no write."""
    one = Brief.at(path)
    changed = _change(one, lambda text: edit(_there(one, text)))
    return Wrote(changed, f"{'changed' if changed else 'unchanged'}: {one.named}")


def new(path: str | Path, text: str) -> Wrote:
    """Write the whole brief, where no thread has taken it up."""
    one = Brief.at(path)
    if not text.strip():
        raise Malformed("refused: stdin holds no brief")
    whole = _text(text.splitlines())

    def edit(was: str | None) -> str:
        if was is not None and was != whole and taken(was):
            raise Taken(f"refused: a thread has taken up {one.path}, and new writes none over it")
        return whole

    changed = _change(one, edit, create=True)
    lines = len(whole.splitlines())
    if not changed:
        return Wrote(False, f"unchanged: {one.named} holds these {lines} lines")
    return Wrote(True, f"wrote: {one.named}, {lines} lines")


def set_line(path: str | Path, label: str, value: str, *, result: bool = False) -> Wrote:
    """Put `<label> <value>` in the brief's head, or with `result` in its last Result."""
    one = Brief.at(path)
    if not LABEL.fullmatch(label):
        raise Malformed(
            f'refused: "{label}" is no label, which is a capital, then letters, digits or spaces, '
            "then a colon, as in Thread: or Scoped reviewer:"
        )
    if not value.strip() or "\n" in value:
        raise Malformed(f"refused: the value of {label} is one line, and not blank")
    where: list[str] = []

    def edit(was: str | None) -> str:
        text = _there(one, was)
        lines = text.splitlines()
        span = last_result(lines) if result else None
        where.append(f"in {lines[span[0]]}" if span else "in the head")
        return with_line(text, label, value, result=result)

    changed = _change(one, edit)
    return Wrote(
        changed,
        f"{'set' if changed else 'unchanged'}: {label} {value}, {where[0]} of {one.named}",
    )


def append(path: str | Path, block: str) -> Wrote:
    """Add the lines of `block` to the brief's last Result, or at its end (`appended`)."""
    one = Brief.at(path)
    added = _block(block)
    where: list[str] = []

    def edit(was: str | None) -> str:
        text = _there(one, was)
        lines = text.splitlines()
        span = None if added[0].startswith("## ") else last_result(lines)
        where.append(f"to {lines[span[0]]}" if span else "at the end")
        return appended(text, block)

    _change(one, edit)
    if added[0].startswith("## "):
        what = ", ".join(one for one in added if one.startswith("## "))
    else:
        what = f"{len(added)} line{'' if len(added) == 1 else 's'}"
    return Wrote(True, f"appended: {what}, {where[0]} of {one.named}")


def remove(path: str | Path) -> None:
    """Remove the brief under its lock, so that no writer that read it before puts it back."""
    one = Brief.at(path)
    with _locked(one):
        one.path.unlink(missing_ok=True)


def _arguments(parser: argparse.ArgumentParser) -> None:
    forms = parser.add_subparsers(dest="form", required=True)
    made = forms.add_parser("new", help="write the whole brief from stdin")
    made.add_argument("brief", help="the brief, <home>/tasks/<slug>.md")
    put = forms.add_parser("set", help="put one line in the head, or with --result the last Result")
    put.add_argument("brief", help="the brief, <home>/tasks/<slug>.md")
    put.add_argument("--result", action="store_true", help="in the last Result, not the head")
    put.add_argument("label", help="the line's label, with its colon, as Thread:")
    put.add_argument("value", nargs="+", help="the line's value; after -- where it starts with -")
    added = forms.add_parser("append", help="add the lines on stdin to the last Result, or the end")
    added.add_argument("brief", help="the brief, <home>/tasks/<slug>.md")


def _run(args: argparse.Namespace, _: None) -> int:
    if args.form == "new":
        wrote = new(args.brief, verbs.piped("brief new", "the whole brief", " <brief>"))
    elif args.form == "set":
        wrote = set_line(args.brief, args.label, " ".join(args.value), result=args.result)
    else:
        wrote = append(args.brief, verbs.piped("brief append", "the lines", " <brief>"))
    print(wrote.said)
    return 0


VERBS = (
    verbs.Verb(
        "brief",
        "write a brief: new from stdin, set one line of its head or last Result, append lines",
        _arguments,
        _run,
        config=False,
    ),
)
