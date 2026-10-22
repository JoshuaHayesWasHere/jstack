"""The stale check: which notes cite a file that changed since the commit they were checked at.

A note is stale when a path it cites differs between the citation's commit and the revision the
check reads: `HEAD`, unless `--rev` names another. The check then prints
`stale <note>: <path> changed since <sha>`. The note's stale days count from the first commit
after its pin that changed a path it cites. The count uses that commit's committer date, which
on a squash merge is when the change merged. A note stale for more than `DAYS` days also gets one
`prune <note>` line. The check keeps nothing between runs: rechecking a note moves its pin, and
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
    """The `stale` and `prune` lines of the pack, note by note. This skips a citation
    whose commit is not in the repo, since the verifier names that one."""
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
