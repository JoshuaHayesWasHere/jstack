"""The frontmatter of a `SKILL.md`: the flat subset of YAML its files use.

Each line between the opening `---` and the closing one is `key: value`. A value is a
double-quoted string (with `\\"` and `\\\\` escaped), a single-quoted one (with `''`), `true`,
`false`, an inline list `[a, "b"]`, or the plain rest of the line. The parser refuses anything
else, such as a nested map, a block scalar or a line with no key. So this parser and a harness
never read a file in two different ways.
"""

from __future__ import annotations

import re

Value = str | bool | list[str]
_KEY = re.compile(r"^(?P<key>[A-Za-z][A-Za-z0-9_-]*):(?: +(?P<value>.*))?$")
_ESCAPES = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "/": "/"}


class Refused(ValueError):
    """A frontmatter outside the subset, with the line that falls outside it."""


def _scalar(text: str) -> str:
    if text.startswith('"'):
        if len(text) < 2 or not text.endswith('"'):
            raise Refused(f"an unclosed string: {text}")
        out, body, at = [], text[1:-1], 0
        while at < len(body):
            char = body[at]
            if char == "\\":
                escaped = body[at + 1 : at + 2]
                if escaped not in _ESCAPES:
                    raise Refused(f"an escape the subset does not have: \\{escaped}")
                out.append(_ESCAPES[escaped])
                at += 2
                continue
            if char == '"':
                raise Refused(f"a quote inside a string that is not escaped: {text}")
            out.append(char)
            at += 1
        return "".join(out)
    if text.startswith("'"):
        if len(text) < 2 or not text.endswith("'"):
            raise Refused(f"an unclosed string: {text}")
        return text[1:-1].replace("''", "'")
    return text


def _value(text: str) -> Value:
    text = text.strip()
    if text in ("true", "false"):
        return text == "true"
    if text.startswith("["):
        if not text.endswith("]"):
            raise Refused(f"an unclosed list: {text}")
        inner = text[1:-1].strip()
        return [_scalar(part.strip()) for part in inner.split(",")] if inner else []
    if text in ("|", ">") or text.startswith(("|-", ">-", "{", "&", "*", "!")):
        raise Refused(f"a value the subset does not have: {text}")
    return _scalar(text)


def split(text: str) -> tuple[str, str] | None:
    """The frontmatter's lines and the body under it, or None for a file with none."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 3)
    if end == -1:
        end = text.find("\n---", 3)
        if end == -1 or text[end + 4 :].strip():
            raise Refused("no closing ---")
    return text[4:end], text[end + 5 :]


def parse(text: str) -> dict[str, Value]:
    """The keys of a file's frontmatter, or none for a file with no frontmatter."""
    found = split(text)
    if found is None:
        return {}
    keys: dict[str, Value] = {}
    for line in found[0].splitlines():
        if not line.strip():
            continue
        pair = _KEY.match(line)
        if not pair:
            raise Refused(f"a line that is not `key: value`: {line}")
        if pair["key"] in keys:
            raise Refused(f"a key given twice: {pair['key']}")
        keys[pair["key"]] = _value(pair["value"] or "")
    return keys
