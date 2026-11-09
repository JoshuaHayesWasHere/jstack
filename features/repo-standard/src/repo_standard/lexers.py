"""The comments of a file, read the way its language reads them, as `(line, comment)` pairs.

`READERS` names each reader, and `BY_EXTENSION` picks one for the extensions it knows. A repo maps
any other extension to one of them in its config (`.go: script`).

- `python` reads the file with `tokenize`, so a `#` in a string is no comment.
- `shell` reads it character by character, so a `#` in quotes or inside a word is no comment.
- `config` reads YAML and TOML as `shell` does, but opens a quote only where a value or a key
  starts, so the apostrophe of a plain scalar such as `name: don't` opens none, and a triple
  quote only after TOML's `=`.
- `script` finds `//` and `/* */`, skipping strings, template strings, regular expressions and a
  `://`, as JavaScript, TypeScript, Go, C and CSS write them.
- `page` reads the `<script>` and `<style>` of an HTML page as `script`.
- `unit` takes a line that starts with `#` or `;`, as a systemd unit or an INI file writes them.
- `hash` takes a line that starts with `#`, as a list of patterns writes them.
"""

from __future__ import annotations

import io
import re
import tokenize
from collections.abc import Callable

Found = list[tuple[int, str]]
EMBEDDED = re.compile(r"<(script|style)\b[^>]*>(.*?)</\1>", re.S | re.I)
WORD = re.compile(r"[\w$]+")
AFTER_A_WORD_A_REGEX = {"return", "typeof", "case", "do", "else", "in", "of", "new", "delete"}
AFTER_A_MARK_A_REGEX = {"", *"([{,;:=!&|?+-*%<>~^"}


def python(text: str) -> Found:
    tokens = tokenize.generate_tokens(io.StringIO(text).readline)
    return [(token.start[0], token.string) for token in tokens if token.type == tokenize.COMMENT]


def shell(text: str) -> Found:
    found, quote, at = [], "", 0
    while at < len(text):
        char = text[at]
        if char == "\\" and quote != "'":
            at += 1
        elif quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and text[at - 1 : at].strip() == "":
            end = text.find("\n", at) % (len(text) + 1)
            found.append((text.count("\n", 0, at) + 1, text[at:end]))
            at = end
        at += 1
    return found


def _starts_a_value(text: str, at: int) -> bool:
    before = text[text.rfind("\n", 0, at) + 1 : at]
    mark = before.rstrip(" \t")[-1:]
    return mark in ("", "[", "{", ",", "=") or (mark in (":", "-") and before[-1] in " \t")


def _config_quoted_end(text: str, at: int) -> int:
    """The end of the quoted value at `at`. Only TOML has a triple-quoted string, and only TOML
    writes a value after `=`, so a triple quote opens one only there: YAML's `'''x'` is `'x`."""
    quote = text[at]
    toml = text[text.rfind("\n", 0, at) + 1 : at].rstrip(" \t").endswith("=")
    end = text.find(quote * 3, at + 3) if toml and text.startswith(quote * 3, at) else -1
    if end >= 0:
        return end + 3
    at += 1
    while at < len(text):
        escaped = text[at] == "\\" if quote == '"' else text[at : at + 2] == "''"
        if text[at] == quote and not escaped:
            return at + 1
        at += 2 if escaped else 1
    return at


def config(text: str) -> Found:
    found, at = [], 0
    while at < len(text):
        char = text[at]
        if char in "'\"" and _starts_a_value(text, at):
            at = _config_quoted_end(text, at)
            continue
        if char == "#" and text[at - 1 : at].strip() == "":
            end = text.find("\n", at) % (len(text) + 1)
            found.append((text.count("\n", 0, at) + 1, text[at:end]))
            at = end
        at += 1
    return found


def _quoted_end(text: str, at: int) -> int:
    quote, at = text[at], at + 1
    while at < len(text) and text[at] != quote and (quote == "`" or text[at] != "\n"):
        at += 2 if text[at] == "\\" else 1
    return at + 1


def _regex_end(text: str, at: int) -> int:
    within, at = False, at + 1
    while at < len(text) and text[at] != "\n":
        if text[at] == "\\":
            at += 1
        elif text[at] in "[]":
            within = text[at] == "["
        elif text[at] == "/" and not within:
            return at + 1
        at += 1
    return at


def _comment_end(text: str, at: int) -> int:
    closing = "*/" if text[at + 1] == "*" else "\n"
    end = text.find(closing, at + 2)
    return len(text) if end < 0 else end + len(closing.strip())


def script(text: str) -> Found:
    found, before, at = [], "", 0
    while at < len(text):
        char, two, word = text[at], text[at : at + 2], WORD.match(text, at)
        if char in "'\"`":
            before, at = char, _quoted_end(text, at)
        elif two == "/*" or (two == "//" and text[at - 1 : at] != ":"):
            end = _comment_end(text, at)
            found.append((text.count("\n", 0, at) + 1, text[at:end]))
            at = end
        elif char == "/" and (before in AFTER_A_WORD_A_REGEX or before in AFTER_A_MARK_A_REGEX):
            before, at = "/", _regex_end(text, at)
        elif word:
            before, at = word[0], word.end()
        else:
            before, at = before if char.isspace() else char, at + 1
    return found


def page(text: str) -> Found:
    return [
        (text.count("\n", 0, embedded.start(2)) + at, comment)
        for embedded in EMBEDDED.finditer(text)
        for at, comment in script(embedded[2])
    ]


def _lines(text: str, marks: tuple[str, ...]) -> Found:
    lines = enumerate(text.splitlines(), 1)
    return [(at, line.strip()) for at, line in lines if line.lstrip().startswith(marks)]


def unit(text: str) -> Found:
    return _lines(text, ("#", ";"))


def hash_lines(text: str) -> Found:
    return _lines(text, ("#",))


READERS: dict[str, Callable[[str], Found]] = {
    "python": python,
    "shell": shell,
    "config": config,
    "script": script,
    "page": page,
    "unit": unit,
    "hash": hash_lines,
}
BY_EXTENSION = {
    ".py": "python",
    ".sh": "shell",
    ".bash": "shell",
    ".yml": "config",
    ".yaml": "config",
    ".toml": "config",
    ".js": "script",
    ".mjs": "script",
    ".ts": "script",
    ".css": "script",
    ".html": "page",
    ".service": "unit",
    ".timer": "unit",
}
