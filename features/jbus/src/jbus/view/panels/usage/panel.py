"""What the threads cost, each as `jgauge session` counts it: for each task, the transcripts of
its worktree, and for each home, the one session it runs as.

Each session's transcript is `<session>.jsonl` in a folder of `KEPT`. The folder's name is the
working directory, with `-` in place of each character that is not a letter or a digit. A task's
crewmate, and the reviewers launched into its worktree, work in
`~/.t3/worktrees/<project>/<slug>`, so that folder holds every thread of the task. A home works
in the project's main checkout, beside other threads. So for a home, the panel takes the session
of that folder that starts within `JOINED` of the home's thread.

The sum is `jgauge.session.of_transcript`, the sum that `jgauge session` prints. The panel reads
a transcript only when the page asks for this panel. It keeps the sum of each transcript, keyed
by the size and the mtime of each of its files. So a second ask reads no file that did not
change. The answer is numbers and times only: the panel copies no text of a transcript into it.
"""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from jbriefs import skills
from jbus.view.state import Read, Source, iso, when
from jgauge import session, transcript

FIRST = False
KEPT = "~/.claude/projects"
PROJECTS = Path(KEPT).expanduser()
WORKTREES = Path.home() / ".t3" / "worktrees"
GAUGE = Path("features") / "home" / "hooks" / "home-gauge.sh"
JOINED = timedelta(minutes=10)
EARLY = timedelta(minutes=1)
SUMMED = (*session.SUMMED, "peak_context")
FIGURES = {key: None for key in (*SUMMED, "first", "last")}
_UNIT = {"known": None, "folder": None, "said": None, "unread": None, **FIGURES}
SHAPE = {
    "usage": {
        "tasks": [_UNIT | {"slug": None, "sessions": [FIGURES]}],
        "homes": [_UNIT | {"title": None, "created": None}],
        "limit": {"limit": None, "ceiling": None, "from": None},
        "newest": None,
    }
}


_kept: dict[Path, tuple[tuple, dict[str, Any] | None]] = {}
_lock = threading.Lock()


def _projects(read: Read) -> dict[str, Any]:
    """The age of what the panel last read: the mtime of the newest transcript it counted. The
    panel takes that mtime from what it kept, so the first screen reads no transcript. It is None
    before the first ask. A folder that is not there counts as read too, and each task and home
    then shows its cost as not known."""
    with _lock:
        stamps = [stamp for key, _ in _kept.values() for _, _, stamp in key]
    newest = iso(datetime.fromtimestamp(max(stamps) / 1e9, UTC)) if stamps else None
    return {"at": newest, "read": True, "path": PROJECTS}


SOURCES = (Source(KEPT, "server", _projects, 160, machine=True),)


def folder(working: Path) -> Path:
    """The folder of `KEPT` that holds the transcripts of a working directory."""
    return PROJECTS / re.sub(r"[^A-Za-z0-9]", "-", str(working))


def _short(path: Path) -> str:
    home = str(Path.home())
    return "~" + str(path)[len(home) :] if str(path).startswith(home + "/") else str(path)


def _files(path: Path) -> tuple:
    """The key the panel keeps a session's sum by: each of its files, with its size and mtime."""
    found = [path, *sorted((path.with_suffix("") / "subagents").rglob("agent-*.jsonl"))]
    stats = []
    for one in found:
        try:
            seen = one.stat()
        except OSError:
            continue
        stats.append((str(one), seen.st_size, seen.st_mtime_ns))
    return tuple(stats)


def _figures(total: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    stamps = sorted(stamp for row in rows for stamp in (row["first_ts"], row["last_ts"]) if stamp)
    return {key: total[key] for key in SUMMED} | {
        "first": when(stamps[0]) if stamps else None,
        "last": when(stamps[-1]) if stamps else None,
    }


def counted(path: Path) -> dict[str, Any] | None:
    """One session's figures, and its own peak as `own`: None where the panel cannot read it."""
    key = _files(path)
    with _lock:
        kept = _kept.get(path)
    if kept and kept[0] == key:
        return kept[1]
    try:
        report = session.of_transcript(path)
    except (OSError, transcript.TranscriptError):
        figures = None
    else:
        figures = _figures(report["total"], report["rows"]) | {
            "own": report["rows"][0]["peak_context"],
            "newest": max((stamp for _, _, stamp in key), default=0),
        }
    with _lock:
        _kept[path] = (key, figures)
    return figures


def _sessions(where: Path) -> list[Path]:
    try:
        return sorted(where.glob("*.jsonl"))
    except OSError:
        return []


def _unit(where: Path, paths: list[Path]) -> dict[str, Any]:
    """The summed figures of the given sessions, with each session's own figures, or the reason
    they are not known."""
    counts = [counted(path) for path in paths]
    read = [one for one in counts if one]
    unit: dict[str, Any] = {"folder": _short(where), "unread": len(counts) - len(read), **FIGURES}
    if not read:
        why = "no transcript" if not counts else "no transcript that could be read"
        return unit | {"known": False, "said": f"not known: {why} under {_short(where)}"}
    stamps = [one[key] for one in read for key in ("first", "last") if one[key]]
    return unit | {
        "known": True,
        "said": "",
        **{key: sum(one[key] for one in read) for key in session.SUMMED},
        "peak_context": max(one["peak_context"] for one in read),
        "first": min(stamps) if stamps else None,
        "last": max(stamps) if stamps else None,
        "sessions": sorted(read, key=lambda one: one["first"] or ""),
        "newest": max(one["newest"] for one in read),
    }


def _task(read: Read, slug: str) -> dict[str, Any]:
    where = folder(WORKTREES / read.name / slug)
    return _unit(where, _sessions(where)) | {"slug": slug}


def checkout(name: str) -> Path | None:
    """The project's main checkout, read from the `.git` file of a worktree that T3 made of the
    project."""
    try:
        made = sorted((WORKTREES / name).iterdir())
    except OSError:
        return None
    for one in made:
        try:
            said = (one / ".git").read_text()
        except OSError:
            continue
        found = re.fullmatch(r"gitdir: (.+)/\.git/worktrees/[^/\n]+\n?", said)
        if found:
            return Path(found[1])
    return None


def started(path: Path) -> datetime | None:
    """When a session started: the time on the first of its opening lines that has a time."""
    try:
        with path.open() as lines:
            for _ in range(20):
                line = lines.readline()
                if not line:
                    break
                try:
                    stamp = when(json.loads(line).get("timestamp"))
                except (ValueError, AttributeError):
                    continue
                if stamp:
                    return datetime.fromisoformat(stamp)
    except OSError:
        return None
    return None


def _homes(read: Read) -> list[dict[str, Any]]:
    """Each home that the last pass listed, with one session of the main checkout. That session
    started between a minute before the home's thread and `JOINED` after it, and of those it is
    the one that started nearest the thread. A session belongs to one home only."""
    homes = sorted(
        (one for one in read.out or [] if one["role"] == "home"),
        key=lambda one: one["created"] or "",
    )
    home = checkout(read.name) if homes else None
    where = folder(home) if home else WORKTREES / read.name
    begun = {path: started(path) for path in _sessions(where)} if home else {}
    found = []
    for one in homes:
        created = datetime.fromisoformat(one["created"]) if one["created"] else None
        near = sorted(
            (abs(at - created), path)
            for path, at in begun.items()
            if created and at and created - EARLY <= at <= created + JOINED
        )
        mine = near[0][1] if near else None
        begun.pop(mine, None)
        unit = _unit(where, [mine] if mine else [])
        if not home:
            unit["said"] = f"not known: no worktree under {_short(where)} names the checkout"
        elif not mine:
            why = "no transcript that starts with its thread"
            unit["said"] = f"not known: {why} under {_short(where)}"
        elif unit["known"]:
            unit["peak_context"] = unit["sessions"][0]["own"]
        found.append(unit | {"title": one["title"], "created": one["created"]})
    return found


def gauge() -> Path:
    """The `home-gauge.sh` that the panel reads: `GAUGE` under the checkout, or else under the
    copy that a release carries."""
    return skills.root() / GAUGE


def limit(read: Read) -> dict[str, Any]:
    """The context a home is held to, read from where `home-gauge.sh` reads it: the two lines of
    the home's `limit` file, or the hook's default for a line that is not a number."""
    try:
        hook = gauge()
        script = hook.read_text()
    except LookupError:
        hook, script = GAUGE, ""
    except OSError:
        script = ""
    named = {
        key: re.search(rf'^"" \| \*\[!0-9\]\*\) {key}=(\d+) ;;$', script, re.M)
        for key in ("limit", "ceiling")
    }
    try:
        lines = (read.home / "limit").read_text().splitlines()
    except OSError:
        lines = []
    given = dict(zip(("limit", "ceiling"), lines, strict=False))
    said = {}
    for key, default in named.items():
        mine = given.get(key, "")
        said[key] = int(mine) if mine.isdigit() else int(default[1]) if default else None
    if said["limit"] is not None and said["ceiling"] is not None:
        said["ceiling"] = max(said["ceiling"], said["limit"])
    mine = given.get("limit", "").isdigit()
    return said | {"from": _short(read.home / "limit") if mine else _short(hook)}


def build(read: Read) -> dict[str, Any]:
    slugs = list(dict.fromkeys(one["slug"] for one in [*read.tasks, *read.ended]))
    tasks = [_task(read, slug) for slug in slugs]
    homes = _homes(read)
    newest = max((one.get("newest", 0) for one in [*tasks, *homes]), default=0)
    return {
        "usage": {
            "tasks": tasks,
            "homes": homes,
            "limit": limit(read),
            "newest": iso(datetime.fromtimestamp(newest / 1e9, UTC)) if newest else None,
        }
    }
