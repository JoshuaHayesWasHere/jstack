"""The one conditional read of GitHub: `ask` sends a GET with the ETag of the answer it had, and
GitHub answers 304, which spends none of the API allowance, until what it would give changes.
`read` keeps each answer in the project's state (`ANSWERS`), so a pass over an unchanged GitHub
costs nothing.

gh exits 1 on a 304, so an answer is read off the status line `gh api -i` prints, never off the
exit code.
"""

from __future__ import annotations

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
    answer, never a kept one. A 200 replaces what was kept, and one with no ETag keeps nothing."""
    folder = run.state / ANSWERS
    _prune(folder)
    file = folder / f"{hashlib.sha256(path.encode()).hexdigest()[:32]}.json"
    kept = store.read_json(file, {})
    had = isinstance(kept, dict) and kept.get("path") == path and "body" in kept
    said = ask(run, path, str(kept.get("etag") or "") if had else "")
    if said is None:
        return None
    if isinstance(said, Same):
        etag, body = kept["etag"], kept["body"]
    elif said.etag:
        etag, body = said.etag, said.body
    else:
        file.unlink(missing_ok=True)
        return said.body
    temporary = file.with_name(f"{file.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    answer = {"path": path, "etag": etag, "body": body, "asked": run.now.isoformat()}
    store.write_json(file, answer, indent=None, sort_keys=False, temporary=temporary)
    return body


_pruned: set[Path] = set()


def _prune(folder: Path) -> None:
    """Remove the kept answers not asked about for `KEPT`, once a process. Each ask writes its file
    whole, so a file's mtime is when it was last asked."""
    if folder in _pruned:
        return
    _pruned.add(folder)
    if not folder.is_dir():
        return
    before = time.time() - KEPT.total_seconds()
    for one in folder.iterdir():
        try:
            if one.stat().st_mtime < before:
                one.unlink(missing_ok=True)
        except FileNotFoundError:
            continue
