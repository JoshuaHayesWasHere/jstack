"""The stale check: which notes cite a file that changed since the commit they were checked at.

A cited path that differs between a citation's commit and the revision read, `HEAD` unless
told, makes its note stale: `stale <note>: <path> changed since <sha>`. A note is stale since
the first commit after its pin that changed a path it cites, by that commit's committer date,
which on a squash merge is when the change landed. One stale for more than `DAYS` days is
also `prune <note>`, once. Nothing is kept between runs: rechecking a note moves its pin, and
its days start again from the next change. The check edits no pack.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from jpack import citations, notes
from jpack.verify import git

DAYS = 14


def since(repo: Path, sha: str, rev: str, path: str, now: datetime) -> datetime | None:
    """When `path` first changed after `sha` on the way to `rev`, or None where it did not."""
    if not git(repo, "diff", "--quiet", sha, rev, "--", path).returncode:
        return None
    logged = git(repo, "log", "--format=%ct", "--reverse", f"{sha}..{rev}", "--", path)
    first = logged.stdout.split()
    return datetime.fromtimestamp(int(first[0]), UTC) if first else now


def lines(
    pack: Path, repo: Path, now: datetime, *, rev: str = "HEAD", days: int = DAYS
) -> list[str]:
    """The `stale` and `prune` lines of the pack, note by note. A citation whose commit is not
    in the repo is the verifier's to name, and is passed over here."""
    found = []
    for name, text in notes(pack).items():
        oldest = None
        seen = set()
        for cited in citations(name, text):
            if (cited.path, cited.sha) in seen:
                continue
            seen.add((cited.path, cited.sha))
            if git(repo, "cat-file", "-e", f"{cited.sha}^{{commit}}").returncode:
                continue
            changed = since(repo, cited.sha, rev, cited.path, now)
            if changed is None:
                continue
            found.append(f"stale {name}: {cited.path} changed since {cited.sha}")
            oldest = changed if oldest is None else min(oldest, changed)
        if oldest is not None and now - oldest > timedelta(days=days):
            found.append(f"prune {name}")
    return found
