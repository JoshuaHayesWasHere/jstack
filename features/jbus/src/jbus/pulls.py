"""The one read of a project's open pull requests, which `watch.look` and the `jmerge` a pass
starts both take (`read`).

The list is a GraphQL ask, `gh pr list --json FIELDS`, and GraphQL is the API allowance nearest
its wall. REST cannot stand in for it: its list of pull requests has no `statusCheckRollup`, no
`mergeable` and no `files`. So `read` first asks, for nothing, whether anything the list gives
changed (`probe`): REST's list of open pull requests, each open head's check runs and statuses,
asked with the ETag of the answer kept for them (`conditional.read`), which a 304 answers at no
cost, and the remote's default branch and base tips, from `git ls-remote`. The list is asked
again only when what those reads say differs from what they said when it was last asked. A pass
over an unchanged GitHub asks GraphQL nothing and gives the kept answer.

The kept answer is `FILE` in the project's state. It is not reused, and the next read asks again:
- where a probe gave no answer, since nothing then says the list is unchanged;
- where the list names other pull requests or heads than REST's did, as when one of the two
  read GitHub before a change and the other after it;
- where a pull request's `mergeable` is `UNKNOWN`, which GitHub decides a while later with no
  change any probe sees;
- where it was asked just after a base tip moved, since GitHub may give the `mergeable` it had
  before the move once more;
- once it is `FRESH` old, so a change no probe sees (the required checks of a branch's rules,
  which add `EXPECTED` checks) is read within that time.

A read takes two REST calls for each open head and one more, each a 304 while nothing changed,
and one `git ls-remote`. `jbus.merge` hands `jmerge` the kept answer's path and the
pass's stamp (`Open.at`), and `jmerge` takes its list and default branch from it only where the
stamp is this pass's.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from jbus import conditional, read_json, write_json
from jmerge.cli import LIST

if TYPE_CHECKING:
    from jbus.passes import Pass

OPEN = "number,url,title,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,updatedAt"
"""The fields of an open pull request `watch.look` reads."""
FIELDS = ",".join(dict.fromkeys([*OPEN.split(","), *LIST.split(",")]))
"""The fields the one ask gives: what `watch.look` reads and what `jmerge` reads (`LIST`)."""
LIMIT = 100
FILE = "pulls.json"
"""The kept answer: `{fields, seen, tips, settled, asked, at, default, pulls}`."""
FRESH = timedelta(minutes=10)
LISTED = "repos/{owner}/{repo}/pulls?state=open&per_page=100"
RUNS = "repos/{owner}/{repo}/commits/%s/check-runs?per_page=100"
STATUS = "repos/{owner}/{repo}/commits/%s/status"


@dataclass(frozen=True)
class Open:
    """The open pull requests as `gh pr list --json FIELDS` gives them, the default branch where
    git named it, the file they are kept in, and the stamp of the pass that read them."""

    pulls: list[dict[str, Any]]
    default: str
    path: Path
    at: str


@dataclass(frozen=True)
class Probe:
    """What the free reads said: `seen`, a digest of all of it, or None where one gave no
    answer, the default branch, the tip of each base by name, and each open pull request as
    `heads` gives it."""

    seen: str | None
    default: str
    tips: dict[str, str]
    pulls: list[list[Any]]


def read(run: Pass) -> Open:
    """Return the project's open pull requests, asked of GraphQL only where something they give
    changed since the kept answer was asked. Raise `Silent` where GitHub gave no list."""
    path = run.state / FILE
    kept = read_json(path, {})
    kept = kept if isinstance(kept, dict) else {}
    probed = probe(run)
    now = run.now.isoformat()
    if _reusable(run, kept, probed.seen):
        pulls = kept["pulls"]
        kept = {**kept, "at": now}
    else:
        pulls = _ask(run)
        was = kept.get("tips") if isinstance(kept.get("tips"), dict) else {}
        moved = any(was.get(base, tip) != tip for base, tip in probed.tips.items())
        decided = all(pull.get("mergeable") != "UNKNOWN" for pull in pulls)
        agrees = heads(pulls) == probed.pulls
        kept = {
            "fields": FIELDS,
            "seen": probed.seen,
            "tips": probed.tips,
            "settled": probed.seen is not None and agrees and not moved and decided,
            "asked": now,
            "at": now,
            "default": probed.default,
            "pulls": pulls,
        }
    write_json(path, kept, indent=None)
    return Open(pulls, probed.default, path, now)


def _reusable(run: Pass, kept: dict[str, Any], seen: str | None) -> bool:
    """Whether the kept answer stands for this read: the probes said `seen` when it was asked, it
    was kept as settled, and it was asked less than `FRESH` ago."""
    if seen is None or kept.get("seen") != seen or kept.get("fields") != FIELDS:
        return False
    return bool(kept.get("settled")) and isinstance(kept.get("pulls"), list) and _fresh(run, kept)


def _fresh(run: Pass, kept: dict[str, Any]) -> bool:
    """Whether the kept answer was asked less than `FRESH` ago."""
    try:
        return run.now - datetime.fromisoformat(str(kept.get("asked"))) < FRESH
    except (TypeError, ValueError):
        return False


def probe(run: Pass) -> Probe:
    """Read, for nothing while it is unchanged, what tells whether the open list changed: REST's
    open pull requests, each open head's check runs and statuses, and the remote's default
    branch and the tip of each base. `seen` is None where any of them gave no answer."""
    listed = conditional.read(run, LISTED)
    try:
        pulls = sorted(
            (
                one["number"],
                one["html_url"],
                one["title"],
                one["head"]["ref"],
                one["head"]["sha"],
                one["base"]["ref"],
                one.get("draft"),
                one["updated_at"],
            )
            for one in listed
        )
    except (KeyError, TypeError):
        return Probe(None, *_tips(run, ()), [])
    opened = [[number, head, sha, base] for number, _, _, head, sha, base, _, _ in pulls]
    default, tips = _tips(run, sorted({pull[5] for pull in pulls}))
    checks = {}
    for head in sorted({pull[4] for pull in pulls}):
        runs, statuses = conditional.read(run, RUNS % head), conditional.read(run, STATUS % head)
        try:
            checks[head] = [
                sorted(
                    (one["id"], one["name"], one["status"], one["conclusion"])
                    + (one.get("started_at"), one.get("completed_at"), one.get("details_url"))
                    for one in runs["check_runs"]
                ),
                runs.get("total_count"),
                sorted(
                    (one["context"], one["state"], one.get("target_url"), one.get("updated_at"))
                    for one in statuses["statuses"]
                ),
            ]
        except (KeyError, TypeError):
            return Probe(None, default, tips, opened)
    if not default:
        return Probe(None, default, tips, opened)
    said = json.dumps([pulls, default, tips, checks], sort_keys=True, default=str)
    return Probe(hashlib.sha256(said.encode()).hexdigest(), default, tips, opened)


def heads(pulls: list[dict[str, Any]]) -> list[list[Any]]:
    """Each pull request of a GraphQL list as REST's list names it: its number, head branch,
    head and base branch, in order."""
    return sorted(
        [one.get("number"), one.get("headRefName"), one.get("headRefOid"), one.get("baseRefName")]
        for one in pulls
    )


def _tips(run: Pass, bases: list[str] | tuple[str, ...]) -> tuple[str, dict[str, str]]:
    """The remote's default branch, and the tip of it and of each of `bases` by name, from one
    `git ls-remote`, which spends none of the API allowance: ("", {}) where git gave no answer."""
    asked = run.run(
        "git", "ls-remote", "--symref", "origin", "HEAD", *(f"refs/heads/{b}" for b in bases)
    )
    if asked.returncode != 0:
        return "", {}
    default, head, tips = "", "", {}
    for line in asked.stdout.splitlines():
        left, _, ref = line.partition("\t")
        if left.startswith("ref: ") and ref == "HEAD":
            default = left.removeprefix("ref: refs/heads/")
        elif ref.startswith("refs/heads/"):
            tips[ref.removeprefix("refs/heads/")] = left
        elif ref == "HEAD":
            head = left
    if default and head:
        tips[default] = head
    return default, tips


def _ask(run: Pass) -> list[dict[str, Any]]:
    """The one GraphQL ask: the open pull requests with `FIELDS`, through `watch.pulls`, which
    asks every list of pull requests the pass makes. Raise `Silent` where `gh` gave no list."""
    from jbus import watch

    return watch.pulls(run, "open", FIELDS, "--limit", str(LIMIT))
