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

import json
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from repo_standard.adapters import COMMANDS
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
class Table:
    """A spec that runs one test a row of a table: the spec `file`, the name of the array it
    runs, `export`, defined in the spec or in a file it imports, and the title of each row's test,
    `title`, in which `{name}` stands for the row's `name:`."""

    file: str
    export: str
    title: str


@dataclass(frozen=True)
class Mock:
    """The API a stack's browser tests run on: its files (`path`, a file or a folder in the
    stack's roots), the shell command that holds it to the real API (`contract`), and the paths
    of that real API (`producer`), whose change selects no browser test."""

    path: str
    contract: str
    producer: tuple[str, ...] = ()


@dataclass(frozen=True)
class E2E:
    """A node stack's browser tests: the npm `root` whose `script` runs Playwright, the specs any
    change of the app selects (`every`), the URLs a spec opens that its text does not name
    (`routes`), the specs that run a table (`table`), and the API they run on (`mock`). Each path
    is from the repo's root."""

    root: str
    script: str
    every: tuple[str, ...] = ()
    routes: dict[str, tuple[str, ...]] = field(default_factory=dict)
    table: tuple[Table, ...] = ()
    mock: Mock | None = None

    def json(self) -> str:
        """The part as the node-vite adapter's scripts read it, on their command line."""
        return json.dumps(
            {
                "root": self.root,
                "script": self.script,
                "every": list(self.every),
                "routes": {spec: list(urls) for spec, urls in self.routes.items()},
                "table": [vars(one) for one in self.table],
                "mock": None
                if self.mock is None
                else {"path": self.mock.path, "producer": list(self.mock.producer)},
            },
            sort_keys=True,
        )


@dataclass(frozen=True)
class Stack:
    """One stack of a repo of several: the adapter that runs it, the folders it owns and, for a
    node stack, its browser tests. No root of one stack sits in another's, so each path has at
    most one stack."""

    adapter: str
    roots: tuple[str, ...]
    e2e: E2E | None = None


@dataclass(frozen=True)
class Waiver:
    """A rule the repo does not meet yet, and why. `until` is the version by which it means to:
    once the repo pins that version, conform warns that the waiver is due."""

    rule: str
    reason: str
    until: int | None = None


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
    stacks: dict[str, Stack] = field(default_factory=dict)
    local: dict[str, str] = field(default_factory=dict)

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
    known |= {"check", "stacks", "local"}
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
        stacks=_stacks(keys.get("stacks", {})),
        local=_local(keys.get("local")),
    )


def _inside(path: str, root: str) -> bool:
    return f"{path}/".startswith(f"{root}/")


def _stacks(value: Any) -> dict[str, Stack]:
    """Each stack, refused when its adapter is unknown, it has no root, or two roots overlap."""
    if not isinstance(value, dict):
        raise Refused(f"{NAME}: stacks is not a map of a stack's name to its adapter and roots")
    found, owner = {}, {}
    for name, one in value.items():
        if not name or any(char in name for char in " :/"):
            raise Refused(f"{NAME}: stacks.{name} is not a name: it holds a space, : or /")
        part = _closed(one, {"adapter", "roots", "e2e"}, f"stacks.{name}")
        adapter = part.get("adapter")
        if adapter not in COMMANDS:
            known = ", ".join(COMMANDS)
            raise Refused(f"{NAME}: stacks.{name}.adapter is {adapter}, not one of {known}")
        roots = _strings(part.get("roots", []), f"stacks.{name}.roots")
        if not roots:
            raise Refused(f"{NAME}: stacks.{name}.roots names no folder")
        for root in roots:
            clean = posixpath.normpath(root)
            if clean != root.rstrip("/") or root.startswith("/") or clean.startswith(".."):
                raise Refused(f"{NAME}: stacks.{name}.roots has {root}, not a folder of the repo")
            for other, holder in owner.items():
                if "." in (clean, other) or _inside(clean, other) or _inside(other, clean):
                    raise Refused(
                        f"{NAME}: stacks.{name}.roots has {root}, inside or around {other}"
                        f" of {holder}"
                    )
            owner[clean] = name
        clean_roots = tuple(posixpath.normpath(root) for root in roots)
        e2e = part.get("e2e")
        if e2e is not None and adapter != "node-vite":
            raise Refused(f"{NAME}: stacks.{name}.e2e is set, and only a node-vite stack runs one")
        found[name] = Stack(
            adapter, clean_roots, None if e2e is None else _e2e(e2e, clean_roots, f"stacks.{name}")
        )
    return found


def _path(value: Any, roots: tuple[str, ...], where: str) -> str:
    """A path of the repo inside one of the roots, refused when it is not."""
    if not isinstance(value, str) or not value:
        raise Refused(f"{NAME}: {where} is not a path")
    clean = posixpath.normpath(value)
    if (
        value.startswith("/")
        or clean.startswith("..")
        or not any(root == "." or _inside(clean, root) for root in roots)
    ):
        raise Refused(f"{NAME}: {where} is {value}, outside the stack's roots {', '.join(roots)}")
    return clean


def _e2e(value: Any, roots: tuple[str, ...], stack: str) -> E2E:
    """A node stack's `e2e:` part, refused when a path falls outside the stack's roots."""
    where = f"{stack}.e2e"
    part = _closed(value, {"root", "script", "every", "routes", "table", "mock"}, where)
    root = _path(part.get("root"), roots, f"{where}.root")
    script = part.get("script")
    if not isinstance(script, str) or not script.strip():
        raise Refused(f"{NAME}: {where}.script names no npm script of {root}")
    every = tuple(
        _path(one, roots, f"{where}.every")
        for one in _strings(part.get("every", []), f"{where}.every")
    )
    routes = _table(part.get("routes"), f"{where}.routes", list)
    found_routes = {}
    for spec, urls in routes.items():
        urls = _strings(urls, f"{where}.routes.{spec}")
        wrong = [url for url in urls if not url.startswith("/")]
        if wrong:
            raise Refused(f"{NAME}: {where}.routes.{spec} has {wrong[0]}, not a path from /")
        found_routes[_path(spec, roots, f"{where}.routes")] = urls
    table = part.get("table", [])
    if not isinstance(table, list):
        raise Refused(f"{NAME}: {where}.table is not a list of `file`, `export` and `title` maps")
    rows = []
    for at, one in enumerate(table):
        row = _closed(one, {"file", "export", "title"}, f"{where}.table[{at}]")
        export, title = row.get("export"), row.get("title")
        if not isinstance(export, str) or not re.fullmatch(r"[A-Za-z_$][\w$]*", export):
            raise Refused(f"{NAME}: {where}.table[{at}].export is not the name of an array")
        if not isinstance(title, str) or "{name}" not in title:
            raise Refused(f"{NAME}: {where}.table[{at}].title has no {{name}} for a row's name")
        spec = _path(row.get("file"), roots, f"{where}.table[{at}].file")
        rows.append(Table(spec, export, title))
    mock = part.get("mock")
    return E2E(
        root,
        script.strip(),
        every,
        found_routes,
        tuple(rows),
        None if mock is None else _mock(mock, roots, root, where),
    )


def _mock(value: Any, roots: tuple[str, ...], e2e_root: str, stack: str) -> Mock:
    """The `mock:` of an `e2e:` part, refused with no contract, or with a producer path that
    holds the mock or the e2e root, or sits in the mock, since its change selects no browser
    test."""
    where = f"{stack}.mock"
    part = _closed(value, {"path", "contract", "producer"}, where)
    path = _path(part.get("path"), roots, f"{where}.path")
    contract = part.get("contract")
    if not isinstance(contract, str) or not contract.strip():
        raise Refused(f"{NAME}: {where}.contract names no command that holds the mock to the API")
    producer = []
    for one in _strings(part.get("producer", []), f"{where}.producer"):
        clean = posixpath.normpath(one)
        if one.startswith("/") or clean.startswith(".."):
            raise Refused(f"{NAME}: {where}.producer has {one}, not a path of the repo")
        if clean == "." or _inside(clean, path) or _inside(path, clean):
            raise Refused(f"{NAME}: {where}.producer has {one}, inside or around {path}")
        if _inside(e2e_root, clean):
            raise Refused(f"{NAME}: {where}.producer has {one}, around the e2e root {e2e_root}")
        producer.append(clean)
    return Mock(path, contract.strip(), tuple(producer))


def _check(value: Any) -> Check:
    part = _closed(value, {"shards", "nightly"}, "check")
    shards, nightly = part.get("shards", 1), part.get("nightly", False)
    if not isinstance(shards, int) or isinstance(shards, bool) or not 1 <= shards <= 64:
        raise Refused(f"{NAME}: check.shards is not a number of parts from 1 to 64")
    if not isinstance(nightly, bool):
        raise Refused(f"{NAME}: check.nightly is not true or false")
    return Check(shards, nightly)


def _local(value: Any) -> dict[str, str]:
    """Each file a version owns that the repo keeps as its own, with why. A reason left blank
    reads as empty, which the conformance tool fails, as it does a waiver's."""
    if value is None:
        return {}
    if not isinstance(value, dict) or not all(isinstance(one, str) for one in value.values()):
        raise Refused(f"{NAME}: local is not a map of a path to the reason the repo keeps it")
    for path in value:
        clean = posixpath.normpath(path)
        if clean != path or path.startswith("/") or clean.startswith(".."):
            raise Refused(f"{NAME}: local has {path}, not a file of the repo")
    return {path: reason.strip() for path, reason in value.items()}


def _until(value: Any, at: int) -> int | None:
    if value is None:
        return None
    found = re.fullmatch(r"repo-standard-v(\d+)", value) if isinstance(value, str) else None
    if not found:
        raise Refused(f"{NAME}: waivers[{at}].until is not a version's tag, repo-standard-vN")
    return int(found[1])


def _waivers(value: Any) -> tuple[Waiver, ...]:
    """Each waiver as written: a reason left out reads as empty, which the conformance tool fails,
    so the config still loads and the tool can name the waiver."""
    if not isinstance(value, list):
        raise Refused(f"{NAME}: waivers is not a list of `rule:` and `reason:` maps")
    found = []
    for at, one in enumerate(value):
        waiver = _closed(one, {"rule", "reason", "until"}, f"waivers[{at}]")
        if not isinstance(waiver.get("rule"), str) or not waiver["rule"]:
            raise Refused(f"{NAME}: waivers[{at}] names no rule")
        reason = waiver.get("reason", "")
        reason = reason.strip() if isinstance(reason, str) else ""
        found.append(Waiver(waiver["rule"], reason, _until(waiver.get("until"), at)))
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
