"""The batch: the pull requests main moved past, proven together by CI's check of one tree.

Where the state has a `merge-batch` file (`SWITCH`), a pull request into the default branch that
is ready by every rule but "main moved" and the guards on its merged tree is a member
(`cli.Repo.over_main`). `jmerge` builds main's tip with each member merged in, in merge order,
force-pushes that commit to its own branch `BRANCH`, under one standing draft pull request, and
keeps the tip, the tree, the commit and the members in `KEPT`. CI's check of that pull request
runs on GitHub's merge of its head over main, whose tree is the batch's, since the head holds the
tip, and leaves the artifact of the two trees (`green.checked`). On it, with the tip unmoved,
`jmerge` squash-merges each member at its own head, in order, with no guards run
(`cli.Repo.merge_batch`). A batch of two or more that went `PENDING_MINUTES` with no artifact
found is built again whole over today's tip, once (`again`): a timeout is no evidence against a
member. One whose check failed has the failed jobs of its workflow run started again, once
(`Rerun`), for a flake or a runner fault is no evidence against a member either. One whose check
failed after its rerun, whose rerun GitHub refused, or that timed out twice in a row, keeps its
members as `suspects`, and the next batch is the first half of them (`narrow`), so CI's checks
of halves find the member that failed it. Where a half proved and one suspect is left, that one
failed it. A failed batch of one, or that last suspect, goes down the single path of today at
its head (`failed`), whose guards name the failing test for its crew.

The batch pull request is jmerge's own: it is never judged as a row's, and never merged.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path

from jmerge import ready
from jsettings import store

BRANCH = "jmerge/batch"
KEPT = "batch.json"
SWITCH = "merge-batch"
MOST = 12
"""The most members a batch takes: the scout's cap, above which a failed batch costs too many
members a round of their own (scouts/po-batched-merge-scout.md)."""
PENDING_MINUTES = 30
"""How long a batch may go from its push with no artifact found before it counts as failed: above
the p90 of 387 s of the pull request check, so a run GitHub left queued or never started, or a
pass whose artifact is never found, does not hold its members for ever."""
SHA = 12
_IDENTITY = ("-c", "user.name=jmerge", "-c", "user.email=jmerge@localhost")

UNMADE = "batch: not made over {base} at {tip} ({why}), so its members go alone"
"""The line of a batch that could not be built, pushed or opened: each member goes the single
path of today in the same run. It is about no pull request, so jbus reads nothing of it."""
PASSED = "CI's check passed jmerge's batch over {base} at {tip} in {run}, so no guards ran"
TITLE = "jmerge: batch over {base}"
BODY = (
    "jmerge's batch: {base}'s tip with each ready pull request main moved past merged in, for "
    "CI's check of that tree. jmerge force-pushes it and never merges it: each member merges "
    "on its own once the check passed (features/jmerge/docs/jmerge.md#batches)."
)

NONE = "none"
PENDING = "pending"
PROVEN = "proven"
FAILED = "failed"
LATE = "late"
RERUN = "rerun"

_RUN = re.compile(r"/actions/runs/(\d+)/")


@dataclass(frozen=True)
class Member:
    number: int
    head: str


@dataclass(frozen=True)
class Rerun:
    """The one rerun of a failed batch's check: the links of the failed jobs it was started for,
    each in the workflow run it reran, and when it was started."""

    jobs: tuple[str, ...]
    at: datetime

    @property
    def runs(self) -> tuple[str, ...]:
        """The workflow runs of `jobs`, by id, each once, in order."""
        return tuple(dict.fromkeys(m[1] for job in self.jobs if (m := _RUN.search(job))))


def failed_jobs(rollup: list[dict], required: tuple[str, ...]) -> tuple[str, ...]:
    """The links of the jobs of the required checks whose latest run failed (`ready.failed`), in
    order: GitHub gives a job of a new attempt of the run a link of its own."""
    return tuple(
        sorted(
            str(one.get("detailsUrl") or "")
            for name in ready.failed(rollup, required)
            for one in ready.latest(rollup, name)
        )
    )


@dataclass(frozen=True)
class Batch:
    """A batch as `KEPT` keeps it: the tip it was built over, its tree, the commit pushed to
    `BRANCH`, its members in merge order, when it was pushed, and the rerun of its failed check
    where one was started (`rerun`)."""

    tip: str
    tree: str
    commit: str
    members: tuple[Member, ...]
    at: datetime
    rerun: Rerun | None = None

    def holds(self, one: ready.PullRequest) -> bool:
        return Member(one.number, one.head) in self.members


def narrow(members: tuple[Member, ...]) -> tuple[Member, ...]:
    """The first half of `members`, the larger half where their count is odd."""
    return members[: (len(members) + 1) // 2]


def _members(listed: list[dict]) -> tuple[Member, ...]:
    return tuple(Member(int(m["number"]), str(m["head"])) for m in listed)


def _rerun(kept: object) -> Rerun | None:
    if not isinstance(kept, dict) or not isinstance(kept.get("jobs"), list):
        return None
    try:
        return Rerun(tuple(map(str, kept["jobs"])), datetime.fromisoformat(str(kept.get("at"))))
    except ValueError:
        return None


@dataclass
class Record:
    """`KEPT`: the batch out, if any; the heads of the members of a failed batch of one, and of
    the last suspect of a proven half, which go the single path at those heads; the suspects, the
    members of the last failed batch of two or more that have not merged, in merge order, of which
    the next batch takes the first half; and whether the batch out, or the next one built, is
    built again after a timeout (`again`). The batch out keeps its own rerun (`Batch.rerun`), so
    a batch built anew has none."""

    path: Path
    batch: Batch | None = None
    failed: dict[str, str] = field(default_factory=dict)
    suspects: tuple[Member, ...] = ()
    again: bool = False

    @classmethod
    def read(cls, state: Path) -> Record:
        path = state / KEPT
        kept = store.read_dict(path)
        failed = kept.get("failed")
        failed = {str(k): str(v) for k, v in failed.items()} if isinstance(failed, dict) else {}
        suspects = kept.get("suspects")
        suspects = _members(suspects) if isinstance(suspects, list) else ()
        try:
            made = Batch(
                str(kept["tip"]),
                str(kept["tree"]),
                str(kept["commit"]),
                _members(kept["members"]),
                datetime.fromisoformat(str(kept["at"])),
                _rerun(kept.get("rerun")),
            )
        except (KeyError, TypeError, ValueError):
            made = None
        return cls(path, made, failed, suspects, kept.get("again") is True)

    def write(self) -> None:
        kept: dict = {}
        if self.batch is not None:
            made = self.batch
            kept = {
                "tip": made.tip,
                "tree": made.tree,
                "commit": made.commit,
                "members": [{"number": m.number, "head": m.head} for m in made.members],
                "at": made.at.isoformat(),
            }
            if made.rerun is not None:
                jobs = list(made.rerun.jobs)
                kept["rerun"] = {"jobs": jobs, "at": made.rerun.at.isoformat()}
        suspects = [{"number": m.number, "head": m.head} for m in self.suspects]
        store.write_json(
            self.path, {**kept, "failed": self.failed, "suspects": suspects, "again": self.again}
        )

    def fail(self) -> None:
        """End the batch out as failed: one of two or more members makes them the suspects, and
        a suspect of an earlier batch not in it is one no more; one of one member puts its head
        under `failed` and takes it from the suspects."""
        members = self.batch.members if self.batch else ()
        if len(members) > 1:
            self.suspects = members
        else:
            self.failed |= {str(one.number): one.head for one in members}
            self.suspects = tuple(one for one in self.suspects if one not in members)
        self.batch, self.again = None, False

    def rerun(self, jobs: tuple[str, ...], now: datetime) -> None:
        """Keep the rerun of the batch out's failed `jobs`, started at `now`."""
        if self.batch is not None:
            self.batch = replace(self.batch, rerun=Rerun(jobs, now))

    def late(self) -> None:
        """End the batch out that went `PENDING_MINUTES` with no artifact found: one of two or
        more not yet built again is built again whole (`again`), with the suspects it had, and
        any other fails (`fail`)."""
        members = self.batch.members if self.batch else ()
        if len(members) > 1 and not self.again:
            self.batch, self.again = None, True
        else:
            self.fail()

    def prove(self) -> None:
        """Take the members of the proven batch out from the suspects. Where it held suspects and
        one is left, that one failed the batch they were suspects of: its head goes under
        `failed`, so it takes the single path with no batch built for it alone."""
        members = self.batch.members if self.batch else ()
        left = tuple(one for one in self.suspects if one not in members)
        if len(left) == 1 and len(left) < len(self.suspects):
            self.failed |= {str(left[0].number): left[0].head}
            left = ()
        self.suspects, self.again = left, False

    def keep(self, heads: dict[str, str]) -> None:
        """Keep the failed heads and the suspects still open at the same head (`heads`, by
        number): one whose head moved, or that merged or closed, is judged again from the start."""
        self.failed = {n: head for n, head in self.failed.items() if heads.get(n) == head}
        self.suspects = tuple(m for m in self.suspects if heads.get(str(m.number)) == m.head)


def state_of(
    batch: Batch | None,
    pull: ready.PullRequest | None,
    tip: str,
    run: str | None,
    now: datetime,
    jobs: tuple[str, ...] = (),
) -> str:
    """Where the batch stands: none out, or one stale (the tip moved, or its pull request is not
    open at its commit); proven, where `run` is the run that left the artifact of the tip's tree
    and its tree; to rerun, where its check failed in `jobs`, each a job of a workflow run, and a
    batch of two or more had no rerun; failed, where its check failed otherwise; late, where
    `PENDING_MINUTES` went by from its push, or from its rerun, with no artifact found; and
    pending otherwise. A check that passed with no artifact found is pending: the lookup turns a
    gh error, or a run not yet concluded after its last job passed, into none, and the next run
    looks again. A failed check whose jobs are all of those its rerun was started for is the
    first attempt GitHub still lists, so it is pending too."""
    if batch is None or tip != batch.tip or pull is None or pull.head != batch.commit:
        return NONE
    if run:
        return PROVEN
    again = batch.rerun
    if pull.failed and again is None:
        rerunnable = bool(jobs) and all(_RUN.search(job) for job in jobs)
        return RERUN if rerunnable and len(batch.members) > 1 else FAILED
    if pull.failed and (not jobs or not set(jobs) <= set(again.jobs if again else ())):
        return FAILED
    if now - (again.at if again else batch.at) >= timedelta(minutes=PENDING_MINUTES):
        return LATE
    return PENDING


def _git(main: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=main, capture_output=True, text=True)


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    lines = (ran.stderr or ran.stdout).strip().splitlines()
    return lines[-1] if lines else f"git exited {ran.returncode}"


@dataclass(frozen=True)
class Built:
    tree: str
    commit: str
    members: tuple[Member, ...]


def build(main: Path, base: str, tip: str, heads: list[Member]) -> Built:
    """Merge each head over `tip` in turn with `git merge-tree`, as GitHub's squashes will land
    them: each step a commit of one parent over the last, so each head merges from its own fork
    point, as its squash does. A head that does not merge over those before it (a conflict, or a
    head git cannot read) is left out, and `MOST` heads at most go in. The batch is one commit of
    the last tree, whose one parent is the tip. A commit git could not make is empty, and the
    push of it fails and says why (`push`)."""
    at, tree, members = tip, "", []
    for one in heads:
        merged = _git(main, "merge-tree", "--write-tree", at, one.head)
        found = merged.stdout.split()[:1]
        if merged.returncode or not found or len(members) == MOST:
            continue
        step = _git(main, *_IDENTITY, "commit-tree", found[0], "-p", at, "-m", f"#{one.number}")
        at, tree = step.stdout.strip(), found[0]
        members.append(one)
    numbers = " ".join(f"#{one.number}" for one in members)
    message = f"jmerge: batch of {numbers} over {base} at {tip[:SHA]}"
    made = _git(main, *_IDENTITY, "commit-tree", tree, "-p", tip, "-m", message)
    return Built(tree, made.stdout.strip(), tuple(members))


def push(main: Path, commit: str) -> str:
    """Force-push `commit` to `BRANCH`, jmerge's own branch, and say why where it failed."""
    ran = _git(main, "push", "-q", "--force", "origin", f"{commit}:refs/heads/{BRANCH}")
    return _said(ran) if ran.returncode else ""


Judged = tuple[ready.PullRequest, str, str, ready.Judged]
"""A member as this run judged it: the pull request, its slug, its note and its judgement."""


@dataclass
class Batching:
    """One run's batching: the record, where the batch it holds stands (`state_of`), the run that
    proved it, the batch pull request GitHub lists, and the members this run judged, in merge
    order, each with its slug and its note."""

    record: Record
    state: str
    run: str
    pull: ready.PullRequest | None
    members: list[Judged] = field(default_factory=list)

    def takes(self, one: ready.PullRequest, default: str, revert: bool) -> bool:
        """Whether `one`, ready but for main moving under its check, is a member: a pull request
        into the default branch that is no revert, whose path is its own, first in line, and that
        was no member of a failed batch at this head."""
        failed = self.record.failed.get(str(one.number)) == one.head
        return not revert and bool(default) and one.base == default and not failed

    def chosen(self, members: list[Judged]) -> list[Judged]:
        """The members the next batch takes, of those this run judged: the first half of the
        suspects that are still judged members at their heads (`narrow`), and every member where
        no suspect is left. A suspect not among `members` is one no more."""
        judged = {Member(found[0].number, found[0].head): found for found in members}
        self.record.suspects = tuple(one for one in self.record.suspects if one in judged)
        return [judged[one] for one in narrow(self.record.suspects)] or members

    @property
    def first(self) -> bool:
        """Whether a batch is out, so that a pull request that would merge alone waits for it:
        its merge would move the tip the batch's check ran over."""
        return self.state in (PENDING, PROVEN)
