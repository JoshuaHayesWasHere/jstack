"""The brief a crew's launch sends, with the lines jbus puts in its head (`jbus.dispatch`).

`Green main:` names the last commit of main whose check passed, `Stacked on:` the open pull
request a stacked crew starts from, in its place, and `Resume:` what a crew launched again on its
own branch carries on from. A `fixes_main` row launches while main is red.
"""

from __future__ import annotations

import re
from pathlib import Path

from jmerge import mainjson
from jmerge import stacked as stacks

GREEN_MAIN = "Green main:"

_FIXES_MAIN = re.compile(r"\bfix(?:es|ing)?\s+(?:the\s+)?(?:red\s+)?main\b", re.IGNORECASE)


def fixes_main(slug: str, brief: str) -> bool:
    """Whether the row fixes a red main: jbus filed it for one (`mainjson.fix_of`), or the first
    line of its brief, its heading, says it fixes main, as `# x: fix main's red test` does."""
    heading = "".join(brief.splitlines()[:1])
    return mainjson.fix_of(slug) or bool(_FIXES_MAIN.search(heading))


def green_main(brief: str, green: str) -> str:
    """Return the brief with `Green main: <sha>` under its first line, in place of any such
    line its head had. The sha is the last commit of main whose check passed
    (`jmerge.mainjson`). When main is red, a crew rebases onto that commit. When no green
    main is known, the brief gets no such line."""
    kept, head = [], True
    for line in brief.splitlines(keepends=True):
        head = head and not line.startswith("## ")
        if not (head and line.startswith(GREEN_MAIN)):
            kept.append(line)
    plain = "".join(kept)
    if not green:
        return plain
    first, _, rest = plain.partition("\n")
    return f"{first}\n{GREEN_MAIN} {green}\n{rest}"


RESUME = "Resume:"
RESUMED = (
    "Resume: {date}, the thread before this one stopped. Its work is in this worktree and in the "
    "last Result below: redo nothing that is there, and carry on from {says}"
)


def resumed(brief: str, line: str) -> str:
    """Return the brief with `line`, its `Resume:` line, last in its head, above its first `## `,
    in place of any `Resume:` line its head had."""
    top, mark, rest = brief.partition("\n## ")
    kept = "".join(one for one in top.splitlines(keepends=True) if not one.startswith(RESUME))
    put = f"{kept.rstrip()}\n{line}"
    return f"{put}{mark}{rest}" if mark else f"{put}\n"


def resumed_on(home: Path, slug: str) -> stacks.Stacked | None:
    """Return the stack a resume of `slug` launches on: the `Stacked on:` line of its brief in
    `home`'s `tasks/`, the copy its launches wrote, which `jbus.stack` moves when its base
    merges. A resume does not judge its depends again, so a link whose base is still open keeps
    its line, and gets no `Green main:`."""
    path = home / "tasks" / f"{slug}.md"
    return stacks.of(path.read_text(errors="replace")) if path.is_file() else None


def launched_text(brief: str, green: str, on: stacks.Stacked | None) -> str:
    """Return the brief a launch sends: with the `Green main:` line (`green_main`), or for a row
    that launches stacked, with its `Stacked on:` line in that place and no `Green main:`. A
    stacked crew starts from its base's branch, never from main, so the line that tells a crew
    which main to rebase onto has no place in its brief."""
    if on is None:
        return green_main(brief, green)
    return stacked(green_main(brief, ""), on)


def stacked(brief: str, on: stacks.Stacked | None) -> str:
    """Return the brief with `on`'s `Stacked on:` line under its first line, in place of any such
    line its head had, or with no such line where `on` is None."""
    kept, head = [], True
    for line in brief.splitlines(keepends=True):
        head = head and not line.startswith("## ")
        if not (head and line.startswith(stacks.LINE)):
            kept.append(line)
    first, _, rest = "".join(kept).partition("\n")
    return f"{first}\n{stacks.line(on)}\n{rest}" if on else "".join(kept)
