"""Propose a check for each `Done when:` item of a brief that runs nothing (`runnable.runs`), and
count how many items of the queue's live rows run something (`share`).

A proposal is the item with a check put after it, one of five kinds, the first of `RULES` that
fits:

- `test`: the item promises a test. The check is a `uv run pytest -q` path under the tests
  directory the brief's `Where:` line names, which the crew writes or renames.
- `run`: the item names a verb of `jbus`, `jmerge` or `jgauge` that only reads (`READS`). The
  check is the verb in backticks.
- `drive`: the item names any other verb of theirs, one that writes. The check is a drive with
  the verify-jstack skill, in a sandbox, and the verb is never put in backticks: a reader who
  runs the backticked words of a brief runs no verb that writes against the machine's state.
- `grep`: the item names a symbol. The check is an `rg` of it in the file the item names, or
  else in the brief's `Where:` paths. A grep shows that text is there, not what it does.
- `judged`: none of the above. The check is `judged: <why>`, for what a person reads.

Each proposal is one for which `runs` is true. The proposer only prints: it writes no brief, and
`jbriefs --propose` refuses a row whose go holds, since a new `Done when:` voids a go
(`jbus.queue`).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from jbriefs.meets import done_when
from jbriefs.runnable import runs
from jsettings.brief import head

Kind = Literal["test", "run", "drive", "grep", "judged"]

LAUNCH = "features/verify-jstack/project-skill/scripts/launch.sh"
"""The script that makes a verify-jstack sandbox, which a `drive` proposal starts from."""

VERBS = {
    "jbus": (
        "poll alarm status events digest view word queue plan gate answer done project t3 bot "
        "budget ci decide failover flow health home item kpis link needs out "
        "playbook relay rules snapshot steps stop telemetry tick tidy told view-shot wakes"
    ).split(),
    "jgauge": "session context room limits sample spend test-slot check proof sizes".split(),
    "jmerge": ("--check --sweep --claims --scope --checks --range-diff --remake --accept".split()),
}
"""Every verb of each tool, as its parser has them. A `jbus queue` verb is two words."""

READS = {
    "jbus": {"status", "events", "digest", "playbook", "queue show", "queue verify"},
    "jgauge": {"session", "context", "room", "spend"},
    "jmerge": {"--check", "--checks", "--claims", "--range-diff"},
}
"""The verbs that only read. Every other verb counts as one that writes, a new one too, and so
does `jmerge` with no verb, which merges."""

_QUEUE = "show add approve hold remove withdraw rename apply verify check".split()
_TOOL = re.compile(r"(?<![\w./-])(jbus|jmerge|jgauge)(?=\s|$)")
_TEST = re.compile(r"\btests?\b", re.I)
_FILE = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)*[\w.-]+\.(?:py|md|yml|yaml|toml|json|jsonl|sh))\b")
_SPAN = re.compile(r"`([^`]+)`")
_NAME = re.compile(r"\b(?:[a-z_]\w*\.)+[A-Za-z_]\w*\b|\b[A-Z][A-Z0-9]*_[A-Z0-9_]*\b")
_SAFE = re.compile(r"[\w .:=\[\]()-]+")
_PATH = re.compile(r"(?<![\w/.-])((?:[\w.-]+/)+[\w./-]*)")
_WORD = re.compile(r"[a-z0-9]+")
_HUMAN = re.compile(r"\b(?:Josh|the user|by hand|decide)\b", re.I)
_REPORT = re.compile(r"\b(?:the Result|pull request|pasted|printout)\b", re.I)
_MEASURE = re.compile(r"\b(?:p50|p90|per (?:merge|day|week)|for a day|minutes|share)\b|%", re.I)


@dataclass(frozen=True)
class Brief:
    """What a proposal reads of a brief: its slug and the paths its `Where:` line names."""

    slug: str
    where: tuple[str, ...]

    @classmethod
    def of(cls, text: str, stem: str = "brief") -> Brief:
        first = next((line for line in text.splitlines() if line.startswith("# ")), "")
        slug = first[2:].split(":", 1)[0].strip() if ":" in first else stem
        line = head(text, "Where:") or ""
        where = tuple(path.rstrip(".,;") for path in _PATH.findall(line))
        return cls(slug or stem, where)

    def tests(self) -> str:
        """The tests directory of the brief's `Where:` line: a path with a `tests` part, else
        the tests of the first feature it names, else `tests`."""
        for path in self.where:
            parts = path.strip("/").split("/")
            if "tests" in parts:
                return "/".join(parts[: parts.index("tests") + 1])
        for path in self.where:
            parts = path.strip("/").split("/")
            if parts[0] == "features" and len(parts) > 1:
                return f"features/{parts[1]}/tests"
        return "tests"


@dataclass(frozen=True)
class Proposal:
    """The item numbered `number` in the brief's `Done when:` list, as `item` with its
    `check` put after it."""

    number: int
    kind: Kind
    item: str
    check: str

    def line(self) -> str:
        return f"{self.number}. {self.kind}: {self.item}"


def _test(item: str, brief: Brief) -> tuple[Kind, str] | None:
    if not _TEST.search(item):
        return None
    words = "_".join(_WORD.findall(_SPAN.sub(" ", item).lower())[:6]) or "it"
    module = re.sub(r"\W", "_", brief.slug)
    return "test", f"`uv run pytest -q {brief.tests()}/test_{module}.py::test_{words}`"


def verb(item: str) -> tuple[str, str] | None:
    """The first verb of `jbus`, `jmerge` or `jgauge` the item names, as the tool and the verb,
    or None for an item that names none. `jmerge` with no flag after it is the verb `""`."""
    for found in _TOOL.finditer(item):
        tool = found[1]
        words = item[found.end() :].split()
        first = words[0].strip(",.;:`") if words else ""
        if tool == "jmerge":
            return tool, first if first in VERBS[tool] else ""
        if first not in VERBS[tool]:
            continue
        if tool == "jbus" and first == "queue" and len(words) > 1:
            second = words[1].strip(",.;:`")
            if second in _QUEUE:
                return tool, f"queue {second}"
        return tool, first
    return None


def writes(tool: str, name: str) -> bool:
    """Whether the verb `name` of `tool` writes: every verb that `READS` does not name."""
    return name not in READS[tool]


def _command(item: str, brief: Brief) -> tuple[Kind, str] | None:
    named = verb(item)
    if named is None:
        return None
    tool, name = named
    words = f"{tool} {name}".strip()
    if writes(tool, name):
        return "drive", (
            f"drive it with verify-jstack: `bash {LAUNCH}`, then, with that sandbox's env.sh "
            f"sourced, run {words} there"
        )
    return "run", f"`{words}`"


def _grep(item: str, brief: Brief) -> tuple[Kind, str] | None:
    files = [path for path in _FILE.findall(item) if "/" in path or path.count(".") == 1]
    spans = [span for span in _SPAN.findall(item) if not _FILE.fullmatch(span.strip())]
    names = [
        *(span.strip().rstrip("*") for span in spans),
        *(name.rsplit(".", 1)[-1] for name in _NAME.findall(_FILE.sub(" ", _SPAN.sub(" ", item)))),
    ]
    symbol = next((name for name in names if len(name) > 2 and _SAFE.fullmatch(name)), None)
    if symbol is None:
        return None
    within = " ".join(files[:1] or brief.where[:3] or ["."])
    return "grep", f"`rg -nF -e '{symbol}' {within}`"


def _judged(item: str, brief: Brief) -> tuple[Kind, str]:
    if _HUMAN.search(item):
        why = "only the user can say"
    elif _MEASURE.search(item):
        why = "a measure of the live system, read where the pull request pastes it"
    elif _REPORT.search(item):
        why = "the reviewer reads it in the Result or the pull request"
    else:
        why = "the reviewer reads the diff for it"
    return "judged", f"judged: {why}"


RULES: tuple[Callable[[str, Brief], tuple[Kind, str] | None], ...] = (
    _test,
    _command,
    _grep,
    _judged,
)
"""The kinds of check, in the order they are tried. The last always fits."""


def proposal(number: int, item: str, brief: Brief) -> Proposal | None:
    """The proposal for one item, or None where the item runs something already or no check
    makes it one that does."""
    if runs(item):
        return None
    for rule in RULES:
        made = rule(item, brief)
        if made is None:
            continue
        kind, check = made
        said = f"{item.rstrip('.')} ({check})"
        return Proposal(number, kind, said, check) if runs(said) else None
    return None


def propose(text: str, stem: str = "brief") -> tuple[Proposal, ...]:
    """A proposal for each item of the brief's `Done when:` list that runs nothing."""
    brief = Brief.of(text, stem)
    made = (
        proposal(number, item, brief) for number, item in enumerate(done_when(text.splitlines()), 1)
    )
    return tuple(one for one in made if one)


@dataclass(frozen=True)
class Share:
    """How many of the `Done when:` items on `rows` rows run something (`runs`)."""

    running: int
    items: int
    rows: int
    statuses: tuple[str, ...]

    def line(self) -> str:
        percent = f"{100 * self.running / self.items:.0f}%" if self.items else "-"
        return (
            f"{self.running} of {self.items} Done when items run something ({percent}), on "
            f"{self.rows} rows {', '.join(self.statuses)}"
        )


def share(state: Path, statuses: Iterable[str]) -> Share:
    """Count the items of the stored brief of each row of the queue in `state` whose status is
    one of `statuses`. A row whose brief is gone counts no item."""
    wanted = tuple(statuses)
    rows = json.loads((state / "queue.json").read_text())
    running = items = counted = 0
    for row in rows:
        if row.get("status") not in wanted:
            continue
        counted += 1
        try:
            text = (state / "briefs" / f"{row['slug']}.md").read_text(errors="replace")
        except OSError:
            continue
        listed = done_when(text.splitlines())
        items += len(listed)
        running += sum(runs(item) for item in listed)
    return Share(running, items, counted, wanted)
