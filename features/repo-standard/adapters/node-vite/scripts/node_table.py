"""A table spec's array, read from the file that holds it, and the rows a change to it selects.

`node_browser` reads a spec of the stack's `e2e.table` with `read_table`: each `{...}` row of the
array's literal and of each `<export>.push({...})`, the row's `name:` and `path:` literals, and
the file's top-level statements. `table_change` gives the ids a change to the file selects from
its hunks, as `git diff -U0` prints them, by the rules of `node_browser`'s docstring.

The scan reads brackets by pattern, not by a parser: it skips comments, strings and templates,
and a quote opens a string only where one can stand, so the apostrophe of JSX text stays text.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

NAME = re.compile(r"\bname\s*:\s*(?:(['\"])((?:\\.|(?!\1).)*)\1|`([^`$]*)`)")
ROW_PATH = re.compile(r"\bpath\s*:\s*(?:\([^)]*\)\s*=>\s*|[\w$]+\s*=>\s*)?(['\"`])([^'\"`\n]*)\1")
DECLARATION = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:declare\s+)?(?:async\s+)?"
    r"(?:const|let|var|function\*?|class|interface|type|enum)\s+([\w$]+)"
)
STRING_BEFORE = re.compile(r"(?:[=(:,\[{}?!&|+;\-*%~^]|=>|\b(?:return|case|of|in|typeof|from))$")
HUNK = re.compile(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@", re.M)

Hunks = list[tuple[int, int]]


def spans(text: str, opening: str = "{") -> list[tuple[int, int]]:
    """The `(start, end)` of each bracketed span of the text, by a scan that skips comments,
    strings and templates. A quote opens a string only where a string can stand, so the
    apostrophe of JSX text, as in `<p>Don't</p>`, stays text."""
    closing = {"{": "}", "[": "]"}[opening]
    found, stack, at, before = [], [], 0, ""
    while at < len(text):
        char = text[at]
        if text.startswith("//", at):
            at = text.find("\n", at)
            at = len(text) if at < 0 else at
            continue
        if text.startswith("/*", at):
            end = text.find("*/", at + 2)
            at = len(text) if end < 0 else end + 2
            continue
        if char in "'\"`" and (not before or STRING_BEFORE.search(before)):
            at += 1
            while at < len(text) and text[at] != char:
                at += 2 if text[at] == "\\" else 1
            at += 1
            before = "a"
            continue
        if char == opening:
            stack.append(at)
        elif char == closing and stack:
            found.append((stack.pop(), at + 1))
        if not char.isspace():
            before = (before + char)[-8:]
        at += 1
    return sorted(found)


def blank(text: str, start: int, inner: Iterable[tuple[int, int]]) -> str:
    """The text with each inner span, offset by `start`, written over with spaces."""
    for first, end in inner:
        a, b = first - start, end - start
        text = text[:a] + " " * (b - a) + text[b:]
    return text


def line_of(text: str, at: int) -> int:
    return text.count("\n", 0, at) + 1


@dataclass(frozen=True)
class Row:
    """One row of a table spec: its literal name, if it has one, the URL it opens, and its lines
    in the file that holds the table."""

    name: str | None
    url: str | None
    first: int
    last: int
    text: str


@dataclass(frozen=True)
class Statement:
    """A top-level statement of the file that holds a table: its lines, and the name it declares,
    or None when it declares none, such as a `for` loop or an import."""

    first: int
    last: int
    name: str | None
    text: str


@dataclass(frozen=True)
class Table:
    """A table spec's array: the file that holds it, its rows, the file's other statements, and
    the lines of the array's literal."""

    spec: str
    file: str
    title: str
    rows: tuple[Row, ...]
    statements: tuple[Statement, ...]
    bounds: tuple[int, int]
    spec_text: str = ""

    def id(self, row: Row) -> str | None:
        if row.name is None:
            return None
        return f"{self.spec} > {self.title.replace('{name}', row.name)}"


def statements(text: str) -> list[Statement]:
    """The top-level statements of a file: each starts at a line that starts at the first column
    with neither a closing bracket nor a comment."""
    lines = text.split("\n")
    starts = [
        at
        for at, line in enumerate(lines, 1)
        if line[:1]
        and not line[:1].isspace()
        and line[:1] not in "}])"
        and not line.startswith(("//", "/*", "*"))
    ]
    found = []
    for at, first in enumerate(starts):
        last = (starts[at + 1] - 1) if at + 1 < len(starts) else len(lines)
        while last > first and (
            not lines[last - 1].strip() or lines[last - 1].lstrip().startswith("//")
        ):
            last -= 1
        body = "\n".join(lines[first - 1 : last])
        declared = DECLARATION.match(body)
        found.append(Statement(first, last, declared[1] if declared else None, body))
    return found


def read_table(
    spec: str, path: str, text: str, start: int, export: str, title: str, spec_text: str = ""
) -> Table:
    """The table of `export`, whose array's `[` is at `start` of the file's text, and the text of
    its spec when another file holds it."""
    end = next((one[1] for one in spans(text, "[") if one[0] == start), len(text))
    objects = spans(text)
    tops = [one for one in objects if start < one[0] and one[1] <= end]
    tops = [one for one in tops if not any(o[0] < one[0] and one[1] <= o[1] for o in tops)]
    for pushed in re.finditer(rf"\b{re.escape(export)}\s*\.\s*push\s*\(\s*", text):
        tops += [one for one in objects if one[0] == pushed.end()]
    rows = []
    for one in sorted(set(tops)):
        nested = [o for o in objects if one[0] < o[0] and o[1] < one[1]]
        outer = blank(text[one[0] : one[1]], one[0], nested)
        name, url = NAME.search(outer), ROW_PATH.search(outer)
        literal = (name[2] if name[1] else name[3]) if name else None
        rows.append(
            Row(
                None if literal is None or "${" in literal else literal,
                re.sub(r"\$\{[^}]*\}", "x", url[2]) if url else None,
                line_of(text, one[0]),
                line_of(text, one[1] - 1),
                text[one[0] : one[1]],
            )
        )
    return Table(
        spec,
        path,
        title,
        tuple(rows),
        tuple(statements(text)),
        (line_of(text, start), line_of(text, end - 1)),
        spec_text,
    )


def users(table: Table, name: str, seen: set[str]) -> set[str] | None:
    """The ids of the rows that name a declaration, directly or through other declarations, or
    None when code outside the rows names it, which runs for the whole spec."""
    if name in seen:
        return set()
    seen.add(name)
    word = re.compile(rf"(?<![\w$]){re.escape(name)}(?![\w$])")
    if word.search(table.spec_text):
        return None
    found: set[str] = set()
    for row in table.rows:
        if word.search(row.text):
            one = table.id(row)
            if one is None:
                return None
            found.add(one)
    for statement in table.statements:
        if statement.name == name or statement.first <= table.bounds[0] <= statement.last:
            continue
        outside = [
            line
            for at, line in enumerate(statement.text.split("\n"), statement.first)
            if not any(row.first <= at <= row.last for row in table.rows)
        ]
        if not word.search("\n".join(outside)):
            continue
        if statement.name is None:
            return None
        more = users(table, statement.name, seen)
        if more is None:
            return None
        found |= more
    return found


def table_change(table: Table, hunks: Hunks) -> set[str]:
    """The ids a change to the file that holds a table selects, given its hunks as git prints
    them: the first line of the new side and its count of lines."""
    whole = {table.spec}
    selected: set[str] = set()
    for first, count in hunks:
        lines = range(first, first + count) if count else [first]
        for line in lines:
            deleted = count == 0
            row = next(
                (one for one in table.rows if one.first <= line and line + deleted <= one.last),
                None,
            )
            if row is not None:
                one = table.id(row)
                if one is None:
                    return whole
                selected.add(one)
                continue
            low, high = table.bounds
            if (low <= line < high) if deleted else (low < line < high):
                continue
            statement = next(
                (
                    one
                    for one in table.statements
                    if one.first <= line and line + deleted <= one.last
                ),
                None,
            )
            if statement is None:
                if deleted:
                    return whole
                continue
            if statement.name is None or statement.first <= table.bounds[0] <= statement.last:
                return whole
            found = users(table, statement.name, set())
            if found is None:
                return whole
            selected |= found
    return selected


def hunks_of(diff: str) -> Hunks:
    """The hunks of a `git diff -U0`, each the first line of its new side and its count."""
    return [(int(first), int(count) if count else 1) for first, count in HUNK.findall(diff)]
