"""The one conditional read of GitHub: `ask` sends a GET with the ETag of the answer it had, and
GitHub answers 304, which spends none of the API allowance, until what it would give changes.
`read` keeps each answer in the project's state (`ANSWERS`), so a pass over an unchanged GitHub
costs nothing.

gh exits 1 on a 304, so an answer is read off the status line `gh api -i` prints, never off the
exit code.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jsettings import store

if TYPE_CHECKING:
    from jbus.passes import Pass

ANSWERS = "gh-answers"
"""The kept answers, a file a path: `{path, etag, body, asked}`."""
KEPT = timedelta(days=7)
"""How long a file not asked about is kept: the paths `watch._judged` asks name a commit, so
most are never asked again once main moves on."""


@dataclass(frozen=True)
class Fresh:
    """GitHub's 200: the answer, and the ETag to ask with next time, empty where it gave none."""

    etag: str
    body: Any


@dataclass(frozen=True)
class Same:
    """GitHub's 304: the answer is still the one its ETag was given with."""


def ask(run: Pass, path: str, etag: str = "") -> Fresh | Same | None:
    """Ask GitHub for `path`, with `If-None-Match: etag` where `etag` is given. None where GitHub
    gave no answer: no status line, a status other than 200 or 304, or a 200 that is not JSON."""
    asked = run.run("gh", "api", path, "-i", *(("-H", f"If-None-Match: {etag}") if etag else ()))
    head, _, body = asked.stdout.replace("\r", "").partition("\n\n")
    status, *headers = head.splitlines() or [""]
    code = status.split()[1:2]
    if code == ["304"] and etag:
        return Same()
    if code != ["200"]:
        return None
    tags = [line.split(":", 1)[1].strip() for line in headers if line.lower().startswith("etag:")]
    try:
        return Fresh(tags[0] if tags else "", json.loads(body))
    except ValueError:
        return None


def read(run: Pass, path: str) -> Any:
    """Return what GitHub answers a GET of `path`, asked with the ETag of the answer kept for it,
    so an answer that has not changed is the kept one, at no cost. None where GitHub gave no
    answer, never a kept one. A 200 replaces what was kept: one with no ETag is kept with none, so
    the next ask sends no `If-None-Match` and gets a 200."""
    had = kept(run, path)
    said = ask(run, path, had.etag if had else "")
    answer = said if isinstance(said, Fresh) else had if isinstance(said, Same) else None
    if answer is None:
        return None
    keep(run, path, answer)
    return answer.body


def kept(run: Pass, path: str) -> Fresh | None:
    """The answer kept for `path`, asking GitHub nothing, or None where none is kept."""
    folder = run.state / ANSWERS
    _prune(folder)
    one = store.read_json(_file(folder, path), {})
    if not (isinstance(one, dict) and one.get("path") == path and "body" in one):
        return None
    return Fresh(str(one.get("etag") or ""), one["body"])


def keep(run: Pass, path: str, answer: Fresh) -> None:
    """Keep `answer` as the one for `path`, so the next `read` of it asks with its ETag. A GET of
    another path that gives the same body, as the check runs at a pull request's head do by its
    ref and by its sha, gets the same ETag from GitHub, so its answer may be kept for this one."""
    file = _file(run.state / ANSWERS, path)
    temporary = file.with_name(f"{file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    one = {"path": path, "etag": answer.etag, "body": answer.body, "asked": run.now.isoformat()}
    store.write_json(file, one, indent=None, sort_keys=False, temporary=temporary)


def _file(folder: Path, path: str) -> Path:
    return folder / f"{hashlib.sha256(path.encode()).hexdigest()[:32]}.json"


def _prune(folder: Path) -> None:
    """Remove the kept answers not asked about for `KEPT`, and any temporary file a write that
    died left. Each ask writes its file whole, so a file's mtime is when it was last asked. A file
    another thread removed first is gone already."""
    before = time.time() - KEPT.total_seconds()
    for one in folder.glob("*"):
        with contextlib.suppress(FileNotFoundError):
            if one.stat().st_mtime < before:
                one.unlink()
