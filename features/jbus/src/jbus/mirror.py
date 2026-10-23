"""Read what the threads wrote down, and never write it: briefs, scout requests and the gates.

Each pass reads `tasks/*.md`, `scouts/*.md` and each `gates.md` of the home and of its scoped homes
(`gate_files`), in the home's state directory. It sends one event for each new section: a Result
(a follow-up included), a Review, a Report, an open gate, an answered gate, and a gate that a thread
with no home wrote into its own Result or Report. A gate of a scoped home names that home. A gate
that a thread piped to `jbus gate` is a question jbus keeps (`questions`). `gate_key` gives such a
question the same key as the gate in the file, so the two are one event, and jbus sends no event for
its answer. `seen.json` keeps the file, heading and hash of every section jbus sent. So jbus sends
each section once, and sends a Result, Review or Report again when its text changes. On a project's
first pass jbus sends nothing: it only records what is already there. jbus also sends nothing for a
file that no pass read before and whose slug was never a row of the queue. Restoring a tree from a
backup puts such a file back (`scan`).
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections.abc import Iterator
from pathlib import Path

from jbus import noticed, queue, read_json, verbs, write_json
from jbus.wake import Pass

EVENTS = {
    "gate": "quiet",
    "gate answered": "quiet",
    "result": "quiet",
    "review": "quiet",
    "report": "quiet",
}
_GATE = re.compile(r"^## Gate (\S+?):\s*(.*)$")


_THREAD = re.compile(r"mcp:\S+|[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
_GATE_LINES = ("Status:", "Asked by:", "Default:", "Built on it:", "Undo:", "Context:", "Option:")
DEFAULT, RECOMMENDED = "default", "recommended"
_MARK = f"(?:{DEFAULT}|{RECOMMENDED})"
_OPTION = re.compile(
    rf"Option:\s*(?P<name>[^<\s].*?)\s*(?:\((?P<marks>{_MARK}(?:,\s*{_MARK})*)\))?"
    r":\s+(?P<follows>[^<\s].*)"
)


def sections(text: str, *, gates_inside: bool = False) -> list[tuple[str, str]]:
    """Return each `## ` heading with the lines under it, in order.

    With `gates_inside`, a `## Gate` line belongs to the section it is in and does not end
    that section. A thread with no home puts its gate in its own Result or Report.
    """
    found: list[tuple[str, list[str]]] = []
    for line in text.splitlines():
        if line.startswith("## ") and not (gates_inside and found and _GATE.match(line)):
            found.append((line.strip(), []))
        elif found:
            found[-1][1].append(line)
    return [(heading, "\n".join(lines).strip()) for heading, lines in found]


def field(body: str, name: str) -> str:
    for line in body.splitlines():
        if line.startswith(f"{name}:"):
            return line[len(name) + 1 :].strip()
    return ""


def gates_in(text: str) -> list[tuple[str, str]]:
    found, lines = [], text.splitlines()
    for at, line in enumerate(lines):
        match = _GATE.match(line.strip())
        if match:
            own = itertools.takewhile(lambda one: one.startswith(_GATE_LINES), lines[at + 1 :])
            found.append((match[2].strip(), "\n".join([line.strip(), *own])))
    return found


def last_result(text: str) -> str:
    whole = sections(text, gates_inside=True)
    results = [f"{h}\n{b}" for h, b in whole if h.startswith("## Result")]
    return results[-1] if results else ""


def page(report: str) -> str:
    """Return what a scout's Report says after its last `Page:`, or nothing when the Report names
    no page.

    `Page: none` names no page, and neither does `Page: none, <why>`. `jmerge --sweep` and the
    scout skill's own settle block read the line the same way.
    """
    named = [
        line.split("Page:", 1)[1].strip(" \t") for line in report.splitlines() if "Page:" in line
    ]
    return "" if not named or re.match(r"none(,|$)", named[-1]) else named[-1]


def undelivered(text: str) -> str:
    """Return a brief's last Review, whole, when it has findings and its `Sent to:` names no
    thread.

    On that line the reviewer writes the thread id it sent the findings to, or `not sent` and
    why, in its own words. So only a line that starts with a thread id counts as delivered.
    """
    reviews = [f"{h}\n{b}" for h, b in sections(text, gates_inside=True) if h == "## Review"]
    if not reviews or field(reviews[-1], "Verdict") != "findings":
        return ""
    sent = [line for line in reviews[-1].splitlines() if line.startswith("Sent to:")]
    if not sent:
        return ""
    to = sent[-1][len("Sent to:") :].split()
    delivered = to and _THREAD.fullmatch(to[0].rstrip(",.;"))
    return "" if delivered else reviews[-1]


def question(lines: str) -> str:
    """Return a gate's question, from the lines a thread sent: its `## Gate <n>:` line."""
    for line in lines.splitlines():
        match = _GATE.match(line.strip())
        if match:
            return match[2].strip()
    for line in lines.splitlines():
        if line.strip() and not re.fullmatch(r"\S+: gate", line.strip()):
            return line.strip()
    return ""


def options(lines: str) -> tuple[list[tuple[str, str, frozenset[str]]], list[str]]:
    """Return the options a gate proposes, from its `Option:` lines in order: each one's short
    name, what follows from it, and its marks. Also return the `Option:` lines that are not an
    option.

    A line is `Option: <short name>: <what follows from it>`, and the name ends at the first
    colon. `(default)`, `(recommended)` or `(default, recommended)` between the name and that
    colon marks the option. A line that still has its angle brackets is a placeholder
    that nobody filled in, and is not an option.
    """
    found, unread = [], []
    for line in map(str.strip, lines.splitlines()):
        if not line.startswith("Option:"):
            continue
        match = _OPTION.fullmatch(line)
        if match:
            marks = frozenset(re.findall(_MARK, match["marks"] or ""))
            found.append((match["name"], match["follows"].strip(), marks))
        else:
            unread.append(line)
    return found, unread


def context(lines: str) -> str:
    """Return what a gate's `Context:` line says, or nothing for a line that nobody filled in."""
    said = field(lines, "Context")
    return "" if said.startswith("<") else said


def gate_key(slug: str, asked: str) -> str:
    """Return one key for a gate however it arrived: read from a file, or piped to `jbus gate`."""
    return "asked " + hashlib.sha256(f"{slug}\n{asked}".encode()).hexdigest()[:16]


def _found(kind: str, slug: str, heading: str, body: str) -> tuple[str, str, str] | None:
    if kind == "tasks" and heading.startswith("## Result"):
        return "result", f"result {slug}: {field(body, 'Status') or heading[3:]}", ""
    if kind == "tasks" and heading == "## Review":
        return "review", f"review {slug}: {field(body, 'Verdict') or 'written'}", ""
    if kind == "scouts" and heading == "## Report":
        return "report", f"report {slug}: {field(body, 'Status') or 'written'}", ""
    return None


def gates(text: str) -> list[tuple[str, str, str, str]]:
    """Return each gate of a `gates.md`, in order: its number, what it asks, its heading, and
    the lines under it."""
    found = ((_GATE.match(heading), heading, body) for heading, body in sections(text))
    return [(match[1], match[2].strip(), heading, body) for match, heading, body in found if match]


def gate_files(home: Path) -> tuple[Path, ...]:
    """Return the home's `gates.md`, then each scoped home's, whether or not it exists."""
    return (home / "gates.md", *sorted(home.glob("*/gates.md")))


def home_gates(home: Path) -> Iterator[tuple[Path, str, str, str, str]]:
    """Return each gate of the home's `gates.md`, then of each scoped home's: its file, its
    number, what it asks, the lines under it, and its `gate_key`. It returns no gate for a file
    it cannot read."""
    for file in gate_files(home):
        for number, asked, _, body in gates(_read(file)):
            yield file, number, asked, body, gate_key(asker(body), asked)


def asker(body: str) -> str:
    """Return the slug on a gate's `Asked by:` line, or `home`."""
    return field(body, "Asked by").split(",")[0].strip() or "home"


def _gates(
    text: str, held: frozenset[str] | None = frozenset(), where: str = ""
) -> list[tuple[str, str, str, str, str]]:
    """Return the events of a `gates.md`. `where` is the scoped home the file is of, or nothing
    for the root's. A gate jbus holds as a question gets no `gate answered` event: its record is
    closed, and jbus reports a closed record nowhere. With no `held`, jbus could not read the
    questions, so this function reports no answered gate until jbus can read them.

    A scoped gate's line and key name its home, so two homes' gates are two events, and a root
    gate keeps the key it always had. A scoped gate that jbus holds as a question went out when
    it was piped, under the question's key, so it gets no event here."""
    found = []
    for number, asked, heading, body in gates(text):
        slug = asker(body)
        status = field(body, "Status")
        whole = f"{heading}\n{body}"
        key, tag = gate_key(slug, asked), f"{slug} in {where}" if where else slug
        if status.startswith("open"):
            if where and (held is None or key in held):
                continue
            found.append((slug, "gate", f"gate {tag}: {asked}", whole, f"{where} {key}".lstrip()))
        elif held is None:
            continue
        elif status.startswith("answered") and key not in held:
            line, done = f"gate {tag}: gate {number} answered", f"{where}#{number}".lstrip("#")
            found.append((slug, "gate answered", line, whole, f"answered {done}"))
    return found


def scan(
    run: Pass, held: frozenset[str] | None = frozenset(), rows: list[queue.Row] | None = None
) -> int:
    """Send what is new. `held` is the keys of the questions jbus holds (`questions.keys`).
    `rows` is the rows of the queue as the pass loaded them, or None where the pass could not
    load them. With None, the pass treats no file as restored, as it does on a
    project's first pass, which records everything there is.

    `seen.json` keeps each file the pass reads. While a file has nothing to send, its entry has
    no heading. So a later pass can tell that a pass read the file. Suppose no pass ever read a
    file, and no row of the queue has or had its slug. Then the file arrived with all its
    sections at once, as a file in a tree restored from a backup does. The pass records it and
    sends nothing for it, and `noticed.keep` adds its `Noticed` lines as lines from before. A
    brief jbus launched has a row. A home writes a scout's request before the launch, so a
    pass reads the request before the scout's Report is in it.

    It reads the `gates.md` of each scoped home too. A gate that such a file holds as answered
    the first time a pass reads it was answered before, and the pass sends nothing for it.
    """
    seen_path = run.state / "seen.json"
    seen: dict[str, dict[str, str]] = read_json(seen_path, {})
    named = None
    if rows is not None and not run.first:
        named = frozenset(row["slug"] for row in rows) | queue.removed_slugs(run.state)
    restored: set[str] = set()
    sent = 0

    def new(file: str, heading: str, whole: str, *, again: bool) -> str:
        digest = hashlib.sha256(whole.encode()).hexdigest()[:16]
        was = seen.setdefault(file, {}).get(heading)
        if was == digest or (was is not None and not again):
            return ""
        seen[file][heading] = digest
        return digest

    for kind in ("tasks", "scouts"):
        for path in sorted((run.home / kind).glob("*.md")):
            slug, counts, text = path.stem, {}, _read(path)
            file = f"{kind}/{path.name}"
            if file not in seen and named is not None and slug not in named:
                restored.add(file)
            seen.setdefault(file, {})
            for asked, lines in gates_in(text):
                if new(file, f"gate {asked}", lines, again=False) and file not in restored:
                    key = gate_key(slug, asked)
                    sent += run.find(
                        slug, "gate", f"gate {slug}: {asked}", lines, key=key, past=True
                    )
            for heading, body in sections(text, gates_inside=True):
                counts[heading] = counts.get(heading, 0) + 1
                made = _found(kind, slug, heading, body)
                name = f"{heading} #{counts[heading]}"
                digest = made and new(file, name, body, again=True)
                if made and digest and file not in restored:
                    what, line, _ = made
                    whole = f"{heading}\n{body}"
                    key = f"{kind} {name} {digest}"
                    sent += run.find(slug, what, line, whole, key=key, past=True)
    for path in gate_files(run.home):
        where = "" if path.parent == run.home else path.parent.name
        file = f"{where}/gates.md" if where else "gates.md"
        first = bool(where) and file not in seen
        if path.exists():
            seen.setdefault(file, {})
        for slug, what, line, whole, key in _gates(_read(path), held, where):
            fresh = new(file, f"{what} {key}", whole, again=False)
            if fresh and not (first and what == "gate answered"):
                sent += run.find(slug, what, line, whole, key=key, past=True)
    if restored:
        try:
            noticed.keep(run.state, run.home, run.now, before=frozenset(restored))
        except noticed.Unparsable:
            pass
    write_json(seen_path, seen)
    return sent


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


STEPS = (
    verbs.Step(
        "tellers", 10, "mirror.scan", lambda half: scan(half.run, half.held, half.rows), ("sight",)
    ),
)
