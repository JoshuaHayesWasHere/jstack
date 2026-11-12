# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""A retro's dataset: every record of a past window, built from the raw stores, read-only.

    retro_data.py build --start <day> [--days 7] [--base-start <day>] [--tz <zone>] --out <dir>
    retro_data.py freeze <codebook>    hash it into <codebook>.sha256, and make it read-only
    retro_data.py check <codebook>     whether it is still the frozen one

`build` reads jbus's state of every project (`JBUS_STATE_DIR`, `~/.local/state/jbus` with none)
and T3 Code's database with mode=ro (`T3_DB`, `~/.t3/userdata/statev2.sqlite` with none). It
writes one JSONL table per kind of record, `completeness.jsonl` (records of each source on each
day), and `summary.json`, then prints the count of each table. A record belongs to the week its own
time falls in, `window` or `base`, days in `--tz`; a row belongs to the week of its first
transition. Nothing after the window's end is read, so a window that has ended prints the same
counts on every run, and the build refuses one that has not.

The typed-message filter keeps a T3 message its user wrote (`createdBy` user) and drops machine
text by its first words (`DROP`). Every candidate is in `filter_decisions.jsonl` with its reason.
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import sys
from collections import Counter
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CLIP = 500
DROP = (
    ("<task-notification>", "task notification"),
    ("<system-reminder>", "system reminder"),
    ("this session is being continued from a previous conversation", "compaction continuation"),
    ("<local-command-", "local command output"),
    ("base directory for this skill", "skill text"),
    ("[request interrupted", "interrupt marker"),
    ("caveat: the messages below were generated", "local command caveat"),
)
JBUS_TABLES = {
    "transitions.jsonl": "transitions.jsonl",
    "events.jsonl": "events.jsonl",
    "acts.jsonl": "acts.jsonl",
    "items.jsonl": "items.jsonl",
}


def when(text):
    if not text:
        return None
    try:
        found = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


def iso(moment):
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z") if moment else None


def lines(path):
    try:
        with path.open() as file:
            for line in file:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return


class Window:
    """The window and its base, each `days` long from a first day, in `zone`."""

    def __init__(self, start, days, base_start, zone):
        self.zone, self.days = ZoneInfo(zone), days
        self.starts = {"window": start} | ({"base": base_start} if base_start else {})

    def bounds(self, week):
        first = datetime.combine(self.starts[week], time(), self.zone)
        return first, first + timedelta(days=self.days)

    def week(self, moment):
        for week in self.starts:
            low, high = self.bounds(week)
            if moment and low <= moment < high:
                return week
        return None

    def day(self, moment):
        return moment.astimezone(self.zone).date().isoformat()

    @property
    def end(self):
        return self.bounds("window")[1]

    def each_day(self):
        for week, first in self.starts.items():
            for n in range(self.days):
                yield week, (first + timedelta(days=n)).isoformat()


def stamped(record, moment, window):
    return record | {"day": window.day(moment), "week": window.week(moment)}


def jbus(state, window):
    """Each project's records in the window, by table, and its rows from their transitions."""
    tables = {name: [] for name in (*JBUS_TABLES, "gates.jsonl", "rows.jsonl")}
    moves = {}
    for folder in sorted(p for p in state.iterdir() if (p / "queue.json").is_file()):
        project = folder.name
        for table, source in JBUS_TABLES.items():
            for one in lines(folder / source):
                moment = when(one.get("at"))
                # A line with `go` and no `to` moves a row's go (`queue._go`), not its status.
                if table == "transitions.jsonl" and "to" in one and moment and moment < window.end:
                    moves.setdefault((project, one.get("slug") or ""), []).append(one)
                if not window.week(moment):
                    continue
                if "line" in one:
                    one["line"] = str(one["line"])[:CLIP]
                tables[table].append(stamped({"project": project} | one, moment, window))
        try:
            asked = json.loads((folder / "questions.json").read_text()).get("records") or []
        except (FileNotFoundError, json.JSONDecodeError):
            asked = []
        for one in asked:
            moment = when(one.get("asked_at"))
            if window.week(moment):
                answer = one.get("answer") or {}
                answered = when(answer.get("at"))
                kept = {
                    "project": project,
                    "number": one.get("number"),
                    "slug": one.get("slug"),
                    "at": iso(moment),
                    "question": one.get("question"),
                    "default": one.get("default"),
                    "holds": one.get("holds") or "",
                    "closed_by": answer.get("closed_by")
                    if answered and answered < window.end
                    else None,
                    "answered_at": iso(answered) if answered and answered < window.end else None,
                }
                tables["gates.jsonl"].append(stamped(kept, moment, window))
    for (project, slug), each in sorted(moves.items()):
        each.sort(key=lambda one: when(one["at"]))
        first = when(each[0]["at"])
        if not window.week(first):
            continue
        row = {"project": project, "slug": slug, "t_first": iso(first)}
        for one in each:
            row.setdefault(f"t_{one.get('to')}", one["at"])
        row |= {f"n_{to}": n for to, n in sorted(Counter(one.get("to") for one in each).items())}
        row["last_status"] = each[-1].get("to")
        tables["rows.jsonl"].append(stamped(row, first, window))
    return tables


def classify(text, message_id, created_by):
    """(decision, reason, kind) of one T3 user-role message."""
    plain = re.sub(r"\s+", " ", text or "").strip().lower()
    kind = "text"
    if plain.rstrip(".") == "continue where you left off":
        kind = "resume"
    elif re.match(r"^[/$][a-z][\w:-]*", plain):
        kind = "command"
    if created_by != "user":
        return "drop", f"createdBy {created_by}", kind
    if message_id.startswith("limit-resume:"):
        return "drop", "limit-resume (resumed after a usage limit)", kind
    if not plain:
        return "drop", "empty", kind
    for prefix, why in DROP:
        if plain.startswith(prefix):
            return "drop", why, kind
    return "keep", "typed", kind


def t3(database, window):
    """Every T3 user-role message in the window, with the filter's decision."""
    decisions = []
    if not database.is_file():
        return decisions
    low = min(window.bounds(week)[0] for week in window.starts)
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        roots = dict(
            connection.execute("select project_id, workspace_root from projection_projects")
        )
        threads = {
            thread: (os.path.basename((roots.get(project) or "").rstrip("/")), title)
            for thread, project, title in connection.execute(
                "select thread_id, project_id, title from orchestration_v2_projection_threads"
            )
        }
        found = connection.execute(
            "select message_id, thread_id, created_at, payload_json"
            " from orchestration_v2_projection_messages"
            " where role = 'user' and created_at >= ? and created_at < ?"
            " order by created_at, message_id",
            (iso(low), iso(window.end)),
        )
        for message_id, thread, created, payload in found:
            moment = when(created)
            if not window.week(moment):
                continue
            said = json.loads(payload)
            text = said.get("text") or ""
            decision, reason, kind = classify(text, message_id, said.get("createdBy"))
            project, title = threads.get(thread, ("", ""))
            record = {
                "store": "t3",
                "id": message_id,
                "thread": thread,
                "thread_title": title,
                "project": project,
                "at": iso(moment),
                "decision": decision,
                "reason": reason,
                "kind": kind,
                "n_chars": len(text),
                "text": text[:4000],
            }
            decisions.append(stamped(record, moment, window))
    return decisions


def write(out, name, records):
    with (out / name).open("w") as file:
        for one in records:
            file.write(json.dumps(one, ensure_ascii=False, sort_keys=True) + "\n")


def build(args):
    start = date.fromisoformat(args.start)
    base = date.fromisoformat(args.base_start) if args.base_start else None
    window = Window(start, args.days, base, args.tz)
    if window.end > datetime.now(UTC):
        sys.exit(f"refused: the window ends {iso(window.end)}, still to come: its counts move")
    state = Path(os.environ.get("JBUS_STATE_DIR") or Path.home() / ".local/state/jbus")
    database = Path(os.environ.get("T3_DB") or Path.home() / ".t3/userdata/statev2.sqlite")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tables = jbus(state, window) if state.is_dir() else {}
    decisions = t3(database, window)
    tables["filter_decisions.jsonl"] = decisions
    tables["messages.jsonl"] = [
        {k: v for k, v in one.items() if k not in ("decision", "reason")}
        for one in decisions
        if one["decision"] == "keep"
    ]
    per_day = Counter()
    for name in ("messages.jsonl", *JBUS_TABLES):
        for one in tables.get(name, []):
            per_day[(name.removesuffix(".jsonl"), one.get("project") or "", one["day"])] += 1
    sources = sorted({(source, project) for source, project, _ in per_day})
    tables["completeness.jsonl"] = [
        {
            "source": source,
            "project": project,
            "week": week,
            "day": day,
            "records": per_day[(source, project, day)],
        }
        for source, project in sources
        for week, day in window.each_day()
    ]
    for name, records in tables.items():
        write(out, name, records)
    counts = {name: len(records) for name, records in sorted(tables.items())}
    tally = Counter(
        f"{one['week']} | {one['decision']} | {one['reason']}" for one in decisions
    ) + Counter(f"{one['week']} | typed | {one['kind']}" for one in tables["messages.jsonl"])
    empty = sorted(
        f"{one['source']} {one['project']} {one['day']}".strip()
        for one in tables["completeness.jsonl"]
        if not one["records"]
    )
    summary = {
        "window": {week: first.isoformat() for week, first in window.starts.items()},
        "days": args.days,
        "tz": args.tz,
        "sources": {"jbus": str(state), "t3": str(database) if database.is_file() else None},
        "counts": counts,
        "filter": dict(sorted(tally.items())),
        "empty_days": len(empty),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True) + "\n")
    for name, count in counts.items():
        print(f"{count:>8} {name}")
    for key, count in sorted(tally.items()):
        print(f"{count:>8} {key}")
    print(f"{len(empty):>8} source-days with no record (completeness.jsonl)")


def sealed(book):
    return book.with_name(book.name + ".sha256")


def digest(book):
    return hashlib.sha256(book.read_bytes()).hexdigest()


def freeze(args):
    book = Path(args.codebook)
    if not book.is_file():
        sys.exit(f"refused: no codebook at {book}: write it from the question alone first")
    sha, seal = digest(book), sealed(book)
    if seal.is_file():
        kept = seal.read_text().split()[0]
        if kept != sha:
            sys.exit(f"refused: {book.name} changed since it was frozen at {kept}")
        print(f"frozen already: {sha}")
        return
    seal.write_text(f"{sha}  {book.name}\n")
    book.chmod(book.stat().st_mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    print(f"frozen: {sha}")


def check(args):
    book = Path(args.codebook)
    if not sealed(book).is_file():
        sys.exit(f"not frozen: {sealed(book)} does not exist")
    kept, sha = sealed(book).read_text().split()[0], digest(book)
    if kept != sha:
        sys.exit(f"changed: {book.name} is {sha}, frozen at {kept}")
    print(f"frozen: {sha}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    verbs = parser.add_subparsers(dest="verb", required=True)
    made = verbs.add_parser("build")
    made.add_argument("--start", required=True, help="the window's first day, YYYY-MM-DD")
    made.add_argument("--days", type=int, default=7)
    made.add_argument("--base-start", help="the base window's first day, as long as the window")
    made.add_argument("--tz", default="America/New_York")
    made.add_argument("--out", required=True)
    for verb in ("freeze", "check"):
        verbs.add_parser(verb).add_argument("codebook")
    args = parser.parse_args(argv)
    {"build": build, "freeze": freeze, "check": check}[args.verb](args)


if __name__ == "__main__":
    main()
