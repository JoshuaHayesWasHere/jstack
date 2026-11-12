"""The hot files of a project, and the row a launch waits on for one.

A pull request that conflicts with main gets a `rebase` event in the project's log
(`jbus.rebase`), and each rebase reruns the crew's check and a scoped review. With 20 to 25 pull
requests open, rebases per merge went from 0.21 to 1.11 (2026-11-12), and the conflicts cluster
on a few files. So a pass launches no row while another row that names the same hot file is out:
`holder` names the file and the row, `jbus.dispatch` holds the row for it (`Hot`), and the row
launches on the first pass after that row merged, ended or was removed. Only the launch order
changes: no check, review or merge guard does, and no finished work waits on a lock, since a
pull request that is open already is never held.

A file is hot once it was in `TIMES` or more conflicts in the `WINDOW` before the pass. The
`rebase` event names a head, in the backup ref of its message (`rebase.MESSAGE`), and not the
files: `conflicted` asks git which files the head conflicted in with main as it was when the event
was written (`git merge-tree`), the first commit of main's first-parent line at or before then.
The answer for a head and a moment never changes, so it is kept in `LEDGER`, under `<slug>/<head>`,
the pair the rebase message's key names, and each head is asked about once. A head git cannot
read is kept with no files, so it is not asked about again. The ledger drops what is older than
`WINDOW`, so the log's daily prune (`wake.LOG_KEEP`) takes nothing it still needs.

The log is 50 MB and more on a busy project, so a pass reads only what was added since the last
one: the ledger keeps the log's inode and the offset read to, always the end of a whole line,
since a pass reads with no lock while another may be appending. A new inode, as the prune's
rename makes, or a log shorter than the offset, is read again from the start; the heads already
asked about are not asked again. A pass asks git about `MOST` heads at most, and the next pass
goes on from there.

A row names a file when a path or a glob of its `Where:` line is that file: a folder does not
name the files under it. Most `Where:` lines name a feature's `src/`, and a hold for a folder
would have held 98 of the 158 launches of 2026-11-11 and 12, against 14 for the files named
(scouts/conflict-avoidance.md measured the same of folders).

The hot list is a help to the queue's speed, never a gate: a log or a ledger that cannot be read,
or git that fails, gives fewer hot files, and the rows launch as they did before.
"""

from __future__ import annotations

import contextlib
import itertools
import json
import os
import re
from collections import Counter
from collections.abc import Callable, Iterable, Iterator, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jbriefs import parse, paths
from jbus import read_json, wake, write_json
from jbus.passes import Pass

LEDGER = "hot-files.json"
WINDOW = timedelta(days=7)
TIMES = 3
MOST = 2000
GIT_TIMEOUT = 30
KIND = "rebase"
_BACKUP = re.compile(r"refs/jstack/pre-rebase/(?P<slug>[^/\s]+)/[0-9a-f]+ (?P<head>[0-9a-f]{40})")


def why(file: str, slug: str) -> str:
    """The reason a row waits on `slug` for `file`, as the queue shows it."""
    return (
        f"waits on {slug}: both name {file}, a file in {TIMES} or more conflicts with main in "
        f"{WINDOW.days} days"
    )


def names(where: Iterable[str], file: str) -> bool:
    """Whether a path or glob of a `Where:` line is `file` itself, not a folder above it."""
    parent = file.rpartition("/")[0]
    return any(
        paths.covers((one,), file) and not paths.covers((one,), parent)
        for one in where
        if one != "."
    )


def hot(run: Pass) -> frozenset[str]:
    """The project's hot files at this pass, read once a pass (`Pass.hot`)."""
    if run.hot is None:
        run.hot = _count(run)
    return run.hot


def holder(
    run: Pass, brief: str, out: Callable[[], Mapping[str, str]], skip: Iterable[str] = ()
) -> tuple[str, str] | None:
    """The hot file a brief shares with a row out, and that row, or None. `out` gives each row
    out, by slug, with its brief, in the order the queue launches them, and is asked only for a
    brief that names a hot file; the slugs of `skip`, the row itself and what it depends on, hold
    nothing. The first file by path and the first row that names it are given, so a row's reason
    stays the same from pass to pass."""
    mine = parse.where(brief)
    files = sorted(file for file in hot(run) if names(mine, file))
    if not files:
        return None
    left = set(skip)
    theirs = {slug: parse.where(text) for slug, text in out().items() if slug not in left}
    for file in files:
        for slug, where in theirs.items():
            if names(where, file):
                return file, slug
    return None


def _count(run: Pass) -> frozenset[str]:
    since = run.now - WINDOW
    ledger = read_json(run.state / LEDGER, {})
    mine: dict[str, Any] = ledger if isinstance(ledger, dict) else {}
    kept = mine.get("conflicts")
    known: dict[str, dict[str, Any]] = kept if isinstance(kept, dict) else {}
    place = mine.get("log")
    asked = 0
    for end, record in _lines(run.state / wake.LOG, place):
        if asked >= MOST:
            break
        place = end
        if record is None or record.get("event") != KIND:
            continue
        found = _BACKUP.search(str(record.get("text", "")))
        at = _at(record)
        if found is None or at is None or at < since:
            continue
        key = f"{found['slug']}/{found['head']}"
        if key not in known:
            known[key] = {"at": at.isoformat(), "files": conflicted(run, found["head"], at)}
            asked += 1
    known = {key: one for key, one in known.items() if (_at(one) or since) >= since}
    made = {"log": place, "conflicts": known}
    if made != ledger:
        with contextlib.suppress(OSError):
            write_json(run.state / LEDGER, made, indent=None)
    counted = Counter(file for one in known.values() for file in set(one.get("files", [])))
    return frozenset(file for file, times in counted.items() if times >= TIMES)


def conflicted(run: Pass, head: str, at: datetime) -> list[str]:
    """The files `head` conflicted in with main as it was at `at`, or none where it merged
    cleanly or git could not tell."""
    default = run.run("git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    branch = default.stdout.strip() or "origin/main"
    main = run.run(
        "git",
        "rev-list",
        "-1",
        "--first-parent",
        f"--before={at.isoformat()}",
        branch,
        timeout=GIT_TIMEOUT,
    ).stdout.strip()
    merged = run.run(
        "git",
        "merge-tree",
        "--write-tree",
        "--name-only",
        "--no-messages",
        main,
        head,
        timeout=GIT_TIMEOUT,
    )
    if merged.returncode != 1:
        return []
    return sorted({line for line in merged.stdout.splitlines()[1:] if line})


def _lines(log: Path, kept: Any) -> Iterator[tuple[dict[str, int], dict[str, Any] | None]]:
    """Each whole line of the log after the place the ledger kept, with the place at its end and
    its record, or None for a line that is none. The log is read from the start where it is a new
    file or shorter than that place, and a last line with no newline yet is left for a later
    pass."""
    try:
        handle = os.open(log, os.O_RDONLY)
    except OSError:
        return
    with os.fdopen(handle, "rb") as file:
        stat = os.fstat(file.fileno())
        place = kept if isinstance(kept, dict) else {}
        offset = place.get("offset")
        same = place.get("inode") == stat.st_ino and isinstance(offset, int)
        offset = offset if same and 0 <= offset <= stat.st_size else 0
        file.seek(offset)
        for line in itertools.takewhile(lambda line: line.endswith(b"\n"), file):
            offset += len(line)
            try:
                record = json.loads(line)
            except ValueError:
                record = None
            yield (
                {"inode": stat.st_ino, "offset": offset},
                (record if isinstance(record, dict) else None),
            )


def _at(record: Mapping[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(record["at"]))
    except (KeyError, ValueError):
        return None
