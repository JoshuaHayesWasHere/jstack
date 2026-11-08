"""`load(root) -> Config`: a repo's `.repo-standard.yml`, read once and checked.

The file is YAML, in the subset this parser reads: block maps and block lists by indent of spaces,
a list item that opens a map (`- files: [...]`), flow lists of scalars (`[a, "b"]`), quoted and
plain scalars, integers, `true` and `false`, and `#` comments. The parser refuses anything else,
such as a tab, an anchor, a flow map or a block scalar, rather than read it in a way another YAML
reader would not. The config is closed too: a key it does not list is refused, so a misspelt key
fails instead of switching a check off.

Each guard reads its own part. A guard whose part is missing is refused, so a repo never passes a
check it never set up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repo_standard.lexers import READERS

NAME = ".repo-standard.yml"
_KEY = re.compile(r"""^("[^"]*"|'[^']*'|[^\s"'#:\[\]{}][^:#]*?):(?:\s+(.*))?$""")
_INT = re.compile(r"^-?\d+$")
_REFUSED = ("{", "&", "*", "!", "|", ">", "%", "@", "`")


class Refused(ValueError):
    """A config the guards cannot read: outside the subset, closed to the key, or missing a part."""


@dataclass(frozen=True)
class Size:
    files: tuple[str, ...]
    exclude: tuple[str, ...]
    cap: int
    over: dict[str, int]


@dataclass(frozen=True)
class Comments:
    files: tuple[str, ...]
    exclude: tuple[str, ...]
    readers: dict[str, str]
    allow: tuple[str, ...]
    links: tuple[str, ...]


@dataclass(frozen=True)
class Docs:
    pages: tuple[str, ...]
    exclude: tuple[str, ...]
    roots: tuple[str, ...]
    elsewhere: dict[str, str]


@dataclass(frozen=True)
class Check:
    """How the shared check workflow runs the repo's tests: in how many parts side by side, and
    whether a nightly run of the whole suite runs."""

    shards: int = 1
    nightly: bool = False


@dataclass(frozen=True)
class Waiver:
    rule: str
    reason: str


@dataclass(frozen=True)
class Config:
    standard: int | None = None
    features: str = "features"
    manifest_schema: str | None = None
    layout: tuple[str, ...] = ()
    owners: dict[str, tuple[str, ...]] = field(default_factory=dict)
    cross_cutting: str = "cross-cutting"
    generators: tuple[tuple[str, ...], ...] | None = None
    docs: Docs | None = None
    size: tuple[Size, ...] | None = None
    comments: Comments | None = None
    waivers: tuple[Waiver, ...] = ()
    enforced_by: dict[str, tuple[str, ...]] = field(default_factory=dict)
    deploy: tuple[str, ...] | None = None
    check: Check = field(default_factory=Check)

    def part(self, name: str) -> Any:
        """The part a guard reads, refused when the config does not set it."""
        value = getattr(self, name.replace("-", "_"))
        if value is None:
            raise Refused(f"{NAME} has no `{name}` part, so this guard has nothing to check")
        return value


def _strip(text: str) -> str:
    """The line with a trailing comment cut: a `#` at its start or after a space, not in quotes."""
    quote = ""
    for at, char in enumerate(text):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "#" and (at == 0 or text[at - 1] == " "):
            return text[:at].rstrip()
    return text.rstrip()


def _lines(text: str) -> list[tuple[int, int, str]]:
    found = []
    for number, raw in enumerate(text.splitlines(), 1):
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise Refused(f"{NAME}:{number}: indents with a tab")
        line = _strip(raw)
        if line.strip() in ("", "---"):
            continue
        found.append((number, len(line) - len(line.lstrip()), line.strip()))
    return found


def _scalar(text: str, number: int) -> Any:
    if text.startswith(("'", '"')):
        if len(text) < 2 or text[-1] != text[0]:
            raise Refused(f"{NAME}:{number}: an unclosed string: {text}")
        body = text[1:-1]
        return body.replace("''", "'") if text[0] == "'" else body
    if text.startswith(_REFUSED):
        raise Refused(f"{NAME}:{number}: a value the subset does not read: {text}")
    if text in ("true", "false"):
        return text == "true"
    if _INT.match(text):
        return int(text)
    if text.startswith("["):
        if not text.endswith("]"):
            raise Refused(f"{NAME}:{number}: an unclosed list: {text}")
        return [_scalar(part, number) for part in _items(text[1:-1], number)]
    return text


def _items(inner: str, number: int) -> list[str]:
    parts, quote, start = [], "", 0
    for at, char in enumerate(inner):
        if quote:
            quote = "" if char == quote else quote
        elif char in "'\"":
            quote = char
        elif char == "[":
            raise Refused(f"{NAME}:{number}: a list inside a flow list")
        elif char == ",":
            parts.append(inner[start:at].strip())
            start = at + 1
    last = inner[start:].strip()
    return [*parts, last] if last or parts else []


def _block(lines: list[tuple[int, int, str]], at: int, indent: int) -> tuple[Any, int]:
    """The value whose lines start at `lines[at]` with `indent`, and the index after it."""
    if lines[at][2] == "-" or lines[at][2].startswith("- "):
        return _list(lines, at, indent)
    return _map(lines, at, indent)


def _list(lines: list[tuple[int, int, str]], at: int, indent: int) -> tuple[list[Any], int]:
    found: list[Any] = []
    while at < len(lines) and lines[at][1] == indent and lines[at][2].startswith("-"):
        number, _, text = lines[at]
        rest = text[1:].strip()
        if not rest:
            raise Refused(f"{NAME}:{number}: a list item with nothing on its line")
        if _KEY.match(rest) and not rest.startswith(("'", '"', "[")):
            inner = [(number, indent + 2, rest), *lines[at + 1 :]]
            value, used = _map(inner, 0, indent + 2)
            found.append(value)
            at += used
        else:
            found.append(_scalar(rest, number))
            at += 1
    return found, at


def _map(lines: list[tuple[int, int, str]], at: int, indent: int) -> tuple[dict[str, Any], int]:
    found: dict[str, Any] = {}
    while at < len(lines) and lines[at][1] == indent:
        number, _, text = lines[at]
        matched = _KEY.match(text)
        if not matched or text.startswith("-"):
            raise Refused(f"{NAME}:{number}: not a `key: value` line: {text}")
        key = str(_scalar(matched[1].strip(), number))
        if key in found:
            raise Refused(f"{NAME}:{number}: {key} is set twice")
        at += 1
        if matched[2]:
            found[key] = _scalar(matched[2].strip(), number)
        elif at < len(lines) and (
            lines[at][1] > indent or (lines[at][1] == indent and lines[at][2].startswith("-"))
        ):
            found[key], at = _block(lines, at, lines[at][1])
        else:
            raise Refused(f"{NAME}:{number}: {key} has no value")
    if at < len(lines) and lines[at][1] > indent:
        raise Refused(f"{NAME}:{lines[at][0]}: indented under a line that holds a value")
    return found, at


def parse(text: str) -> dict[str, Any]:
    """The config's keys, refused when the text falls outside the subset."""
    lines = _lines(text)
    if not lines:
        return {}
    value, at = _block(lines, 0, lines[0][1])
    if at < len(lines) or not isinstance(value, dict):
        raise Refused(f"{NAME}:{lines[min(at, len(lines) - 1)][0]}: not one map at the top")
    return value


def _closed(value: Any, keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Refused(f"{NAME}: {where} is not a map")
    unknown = sorted(set(value) - keys)
    if unknown:
        raise Refused(f"{NAME}: {where} has {', '.join(unknown)}, which the standard does not know")
    return value


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(one, str) and one for one in value):
        raise Refused(f"{NAME}: {where} is not a list of strings")
    return tuple(value)


def _table(value: Any, where: str, kind: type) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(
        isinstance(one, kind) and not isinstance(one, bool) for one in value.values()
    ):
        raise Refused(f"{NAME}: {where} is not a map of {kind.__name__}")
    return value


def _size(value: Any, at: int) -> Size:
    rule = _closed(value, {"files", "exclude", "cap", "over"}, f"size[{at}]")
    cap = rule.get("cap")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1:
        raise Refused(f"{NAME}: size[{at}].cap is not a positive number of lines")
    return Size(
        _strings(rule.get("files"), f"size[{at}].files"),
        _strings(rule.get("exclude", []), f"size[{at}].exclude"),
        cap,
        _table(rule.get("over"), f"size[{at}].over", int),
    )


def _comments(value: Any) -> Comments:
    part = _closed(value, {"files", "exclude", "readers", "allow", "links"}, "comments")
    readers = _table(part.get("readers"), "comments.readers", str)
    wrong = sorted(set(readers.values()) - set(READERS))
    if wrong:
        known = ", ".join(READERS)
        raise Refused(f"{NAME}: comments.readers names {', '.join(wrong)}, not one of {known}")
    return Comments(
        _strings(part.get("files"), "comments.files"),
        _strings(part.get("exclude", []), "comments.exclude"),
        readers,
        _strings(part.get("allow", []), "comments.allow"),
        _strings(part.get("links", []), "comments.links"),
    )


def _docs(value: Any) -> Docs:
    part = _closed(value, {"pages", "exclude", "roots", "elsewhere"}, "docs")
    return Docs(
        _strings(part.get("pages"), "docs.pages"),
        _strings(part.get("exclude", []), "docs.exclude"),
        _strings(part.get("roots"), "docs.roots"),
        _table(part.get("elsewhere"), "docs.elsewhere", str),
    )


def build(keys: dict[str, Any]) -> Config:
    """The typed config from the parsed keys."""
    known = {"standard", "features", "manifest-schema", "layout", "owners", "cross-cutting"}
    known |= {"generators", "docs", "size", "comments", "waivers", "enforced-by", "deploy"}
    known |= {"check"}
    keys = _closed(keys, known, "the top")
    owners = _table(keys.get("owners"), "owners", list)
    enforced = _table(keys.get("enforced-by"), "enforced-by", list)
    standard = keys.get("standard")
    if standard is not None and (not isinstance(standard, int) or isinstance(standard, bool)):
        raise Refused(f"{NAME}: standard is not a whole number, the version the repo pins")
    generators = keys.get("generators")
    size = keys.get("size")
    if size is not None and not isinstance(size, list):
        raise Refused(f"{NAME}: size is not a list of rules")
    return Config(
        standard=standard,
        features=str(keys.get("features", "features")).rstrip("/"),
        manifest_schema=keys.get("manifest-schema"),
        layout=_strings(keys.get("layout", []), "layout"),
        owners={group: _strings(rows, f"owners.{group}") for group, rows in owners.items()},
        cross_cutting=str(keys.get("cross-cutting", "cross-cutting")),
        generators=None if generators is None else _generators(generators),
        docs=None if keys.get("docs") is None else _docs(keys["docs"]),
        size=None if size is None else tuple(_size(one, at) for at, one in enumerate(size)),
        comments=None if keys.get("comments") is None else _comments(keys["comments"]),
        waivers=_waivers(keys.get("waivers", [])),
        enforced_by={
            rule: _strings(rows, f"enforced-by.{rule}") for rule, rows in enforced.items()
        },
        deploy=None if keys.get("deploy") is None else _strings(keys["deploy"], "deploy"),
        check=Check() if keys.get("check") is None else _check(keys["check"]),
    )


def _check(value: Any) -> Check:
    part = _closed(value, {"shards", "nightly"}, "check")
    shards, nightly = part.get("shards", 1), part.get("nightly", False)
    if not isinstance(shards, int) or isinstance(shards, bool) or not 1 <= shards <= 64:
        raise Refused(f"{NAME}: check.shards is not a number of parts from 1 to 64")
    if not isinstance(nightly, bool):
        raise Refused(f"{NAME}: check.nightly is not true or false")
    return Check(shards, nightly)


def _waivers(value: Any) -> tuple[Waiver, ...]:
    """Each waiver as written: a reason left out reads as empty, which the conformance tool fails,
    so the config still loads and the tool can name the waiver."""
    if not isinstance(value, list):
        raise Refused(f"{NAME}: waivers is not a list of `rule:` and `reason:` maps")
    found = []
    for at, one in enumerate(value):
        waiver = _closed(one, {"rule", "reason"}, f"waivers[{at}]")
        if not isinstance(waiver.get("rule"), str) or not waiver["rule"]:
            raise Refused(f"{NAME}: waivers[{at}] names no rule")
        reason = waiver.get("reason", "")
        found.append(Waiver(waiver["rule"], reason.strip() if isinstance(reason, str) else ""))
    return tuple(found)


def _generators(value: Any) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list):
        raise Refused(f"{NAME}: generators is not a list of commands")
    return tuple(_strings(one, f"generators[{at}]") for at, one in enumerate(value))


def load(root: Path, path: Path | None = None) -> Config:
    """The config of the repo at `root`, from `path` or from `root/.repo-standard.yml`."""
    where = path or root / NAME
    try:
        text = where.read_text(encoding="utf-8")
    except OSError as error:
        raise Refused(f"cannot read {where}: {error.strerror}") from error
    return build(parse(text))
