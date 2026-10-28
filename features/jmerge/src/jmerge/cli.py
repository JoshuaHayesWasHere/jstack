from __future__ import annotations

import argparse
import fcntl
import functools
import itertools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import jbus
import jsettings
from jbriefs import home as home_rule
from jbriefs import parse
from jbus.watch import failed_in
from jmerge import (
    accepts,
    checks,
    claims,
    follow,
    lines,
    mainjson,
    proof,
    rangediff,
    ready,
    rejudge,
    remake,
    rows,
    sweep,
    trailers,
)
from jmerge import gate as merge_gate
from jmerge import stacked as stacks
from jmerge.asked import why as asked_why

LIST = (
    "number,url,title,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,"
    "files,changedFiles,isDraft"
)
PACKAGE = Path(__file__).parent
PROTECTED = PACKAGE / "protected.txt"
CI_PATHS = PACKAGE / "ci-paths.txt"
INTEGRATION = "integration"
REQUIRED_CHECKS = "required-checks"
JUDGED_AGAIN_AT_MOST = 2
LANDED = {
    "--merge": "landed with a merge commit",
    "--squash": "landed as a squash: each unit's pull request into {branch} is its own record",
}
TIMEOUT_SECONDS = 120


def _run(cwd: Path, *command: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    limit = float(os.environ.get("JMERGE_TIMEOUT") or TIMEOUT_SECONDS)
    try:
        return subprocess.run(
            command, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=limit
        )
    except subprocess.TimeoutExpired:
        said = f"timed out after {limit:g} s: {shlex.join(command)}"
        return subprocess.CompletedProcess(command, 124, "", said)


def _why(cwd: Path, asked: subprocess.CompletedProcess[str], said: str = "") -> str:
    """Why `gh` gave no answer, asking `gh api rate_limit` in `cwd` for a rate-limit refusal."""
    return asked_why(asked, functools.partial(_run, cwd), said)


def _text(cwd: Path, *command: str) -> str | None:
    ran = subprocess.run(command, cwd=cwd, capture_output=True)
    return None if ran.returncode else ran.stdout.decode(errors="replace")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def patch_id(cwd: Path, base: str, commit: str, since: str = "") -> str | None:
    fork = _run(cwd, "git", "merge-base", since or f"origin/{base}", commit)
    if fork.returncode:
        return None
    diff = subprocess.run(
        ["git", "diff", fork.stdout.strip(), commit], cwd=cwd, capture_output=True
    )
    if diff.returncode:
        return None
    summed = subprocess.run(
        ["git", "patch-id", "--stable"], cwd=cwd, input=diff.stdout, capture_output=True
    )
    return None if summed.returncode else b"".join(summed.stdout.split()[:1]).decode()


def _first_word(text: str) -> str:
    return "".join(text.split()[:1])


def patterns(path: Path) -> tuple[str, ...]:
    try:
        return ready.patterns_of(path.read_text(encoding="utf-8"))
    except OSError:
        raise SystemExit(f"jmerge: {path} cannot be read") from None
    except ValueError as pattern:
        raise SystemExit(
            f"jmerge: {path} has a pattern that cannot be read, so nothing is merged: {pattern}"
        ) from None


class Merged:
    """A pull request's head merged over today's base, as GitHub's update of its branch merges
    it. Where the repo's state has a `fresh-check` file, a pull request whose check started before
    its base moved is proven over today's base on GitHub, and no suite runs on this machine for a
    merge: `rejudge.BaseMerge` asks GitHub to update the branch, and GitHub's check at the updated
    head decides by the normal path."""

    def __init__(self, main: Path, state: Path, run: bool = True):
        self.main = main
        self.state = state
        self.run = run
        self.command = ready.fresh_command(_read(state / "fresh-check"))

    def of(self, head: str, tip: str) -> str:
        """Why the head over `tip` waits, or nothing when GitHub is to update the branch."""
        merged = _run(self.main, "git", "merge-tree", "--write-tree", tip, head)
        if merged.returncode == 1:
            return ready.FRESH_CONFLICT
        if merged.returncode:
            return ready.UNMERGED.format(why=lines.said(merged))
        return ""


class Gated(NamedTuple):
    verb: str
    why: str
    note: str


class Gate:
    """The repo's merge gate: the command in its state's `merge-gate` file. `jmerge` runs it
    before every merge, in a checkout of the head, with the merge base and the head as its
    last two arguments and as `BASE` and `HEAD`. It runs on every judgement, and `jmerge`
    keeps its answer for that run only, so the next run sees a fix made outside git. Once a
    run's gates have used `BUDGET`, the run starts no more gates. So a last gate that
    `jmerge` stops at `TIMEOUT` still ends within the time that jbus gives `jmerge`. A gate
    runs holding `<state>/gate.lock`. A run that overlaps another, such as a hand run beside
    jbus's, waits for the lock, so it never removes the checkout that the other run's gate is
    using."""

    TIMEOUT = 10 * 60
    BUDGET = 5 * 60

    def __init__(
        self, main: Path, state: Path, timeout: float = TIMEOUT, budget: float = BUDGET
    ) -> None:
        self.main = main
        self.state = state
        self.timeout = timeout
        self.budget = budget
        self.spent = 0.0
        self.command = merge_gate.command(state)
        self.answers: dict[tuple[int, str, str], Gated] = {}
        self.output: dict[int, str] = {}

    def of(self, number: int, head: str, branch: str) -> Gated:
        _run(self.main, "git", "fetch", "-q", "origin", branch)
        tip = _run(self.main, "git", "rev-parse", "-q", "--verify", f"origin/{branch}^{{commit}}")
        key = (number, head, tip.stdout.strip())
        if key not in self.answers:
            if self.spent > self.budget:
                return Gated("wait", ready.GATE_BUSY, "")
            with (self.state / "gate.lock").open("w") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    return Gated("wait", ready.GATE_LOCKED, "")
                started = time.monotonic()
                self.answers[key] = self._run(number, head, key[2], lock.fileno())
                self.spent += time.monotonic() - started
        return self.answers[key]

    def _unstarted(self, why: str) -> Gated:
        return Gated("hold", ready.GATE_UNSTARTED.format(why=why), "")

    def _run(self, number: int, head: str, tip: str, lock: int) -> Gated:
        if _run(self.main, "git", "cat-file", "-e", f"{head}^{{commit}}").returncode:
            _run(self.main, "git", "fetch", "-q", "origin", f"refs/pull/{number}/head")
        fork = _run(self.main, "git", "merge-base", tip, head) if tip else None
        if fork is None or fork.returncode:
            return self._unstarted("where it left main could not be worked out")
        base = fork.stdout.strip()
        at = self.state / "gate" / str(number)
        _run(self.main, "git", "worktree", "remove", "--force", str(at))
        shutil.rmtree(at, ignore_errors=True)
        _run(self.main, "git", "worktree", "prune")
        added = _run(self.main, "git", "worktree", "add", "-q", "--detach", str(at), head)
        if added.returncode:
            return self._unstarted(f"its head could not be checked out ({lines.said(added)})")
        try:
            code, said = merge_gate.run(self.command, at, base, head, self.timeout, (lock,))
        except OSError as error:
            return self._unstarted(str(error))
        finally:
            _run(self.main, "git", "worktree", "remove", "--force", str(at))
        if code == 0:
            return Gated("", "", lines.GATE_OK)
        self.output[number] = said
        if code is None:
            return Gated(
                "hold", ready.GATE_TIMED_OUT.format(limit=merge_gate.over(self.timeout)), ""
            )
        first = ready.first_line(said, code)
        if code in (126, 127):
            return self._unstarted(first)
        return Gated("hold", ready.GATE_FAILED.format(first=first), "")


class Homes(NamedTuple):
    known: dict[str, str]
    running: dict[str, str]


class Judgement(NamedTuple):
    slug: str
    verb: str
    why: str
    note: str
    judged: ready.Judged | None


class Repo:
    def __init__(
        self,
        main: Path,
        state: Path,
        home: str | None,
        every: bool,
        land: str | None = None,
        protected: tuple[str, ...] = (),
        ci: tuple[str, ...] = (),
        merged: Merged | None = None,
        *,
        user: jsettings.Settings,
        gate: Gate | None = None,
    ) -> None:
        self.user = user
        self.main = main
        self.state = state
        self.every = every
        self.land = land or None
        self.protected = protected
        self.ci = ci
        self.merged = merged
        self.gate = gate
        self.accepted: tuple[int, str] | None = None
        self.lifts: list[str] = []
        self.carried: dict[int, str] = {}
        self.fetched = False
        self.through: int | None = None
        self.order: list[int] = []
        self.rebasing: set[int] = set()
        self.numbers_on: dict[str, set[int]] = {}
        self.integration = ready.integration_of(_read(state / INTEGRATION))
        self.required = ready.required_of(_read(state / REQUIRED_CHECKS))
        self.trunk = ""
        self.reds: dict[str, list[dict]] = {}
        self.proofs: dict[tuple[int, str, str, str], rows.Ran] = {}
        self.logs: dict[str, str | None] = {}
        self.open: list[ready.PullRequest] = []
        self.heads: dict[int, bool] = {}
        origin = _run(main, "git", "remote", "get-url", "origin")
        self.about = [] if origin.returncode else ["--repo", origin.stdout.strip()]
        self.base_merge = rejudge.BaseMerge(main, state, self.about, bool(merged and merged.run))
        self.listed, self.was = home_rule.ids(state)
        self.mine = home or self.listed

    @functools.cached_property
    def queue(self) -> list[dict] | None:
        return rows.read(self.main)

    @functools.cached_property
    def main_state(self) -> mainjson.Main:
        return rows.main(self.main)

    @functools.cached_property
    def migrations(self) -> rows.Migrations | None:
        return rows.migrations(self.main)

    def numbers(self, base: str) -> set[int] | None:
        if base not in self.numbers_on and self.migrations:
            where = f"origin/{base}"
            listed = None
            if not _run(self.main, "git", "fetch", "-q", "origin", base).returncode:
                tree = f"{self.migrations.directory}/"
                listed = _run(self.main, "git", "ls-tree", "-z", "--name-only", where, "--", tree)
            if listed is None or listed.returncode:
                return None
            names = (Path(path).name for path in listed.stdout.split("\0") if path)
            self.numbers_on[base] = {int(d) for n in names if (d := ready.migration_number(n))}
        return self.numbers_on.get(base)

    def line_up(self, listed: list[ready.PullRequest], default: str) -> list[ready.PullRequest]:
        listed = sorted(listed, key=lambda one: one.number)
        settings = self.migrations
        mine = {
            one.number: one
            for one in listed
            if settings and ready.migrations(one, settings.directory)
        }
        if not settings or not mine:
            return listed
        slugs = {}
        for number, one in mine.items():
            brief = ready.brief_of(one.url, self.state / "tasks")
            slugs[number] = brief.stem if brief else ""
        self.order = rows.merge_order(self.queue, slugs)
        places = iter(mine[number] for number in self.order)
        return [next(places) if one.number in mine else one for one in listed]

    def short_on_migrations(self, one: ready.PullRequest, default: str) -> str:
        settings = self.migrations
        names = ready.migrations(one, settings.directory) if settings else ()
        if not settings or not names:
            return ""
        taken = self.numbers(default)
        if taken is None:
            return f"{default} could not be fetched to see its migration numbers"
        short = ready.short_on_migration(names, taken, default) if settings.numbered else ""
        if short or one.number not in self.order:
            return short
        for ahead in self.order[: self.order.index(one.number)]:
            if ahead in self.rebasing:
                return ready.MIGRATION_REBASING.format(number=ahead)
        if self.through not in (None, one.number):
            return ready.MIGRATION_MERGING.format(number=self.through)
        return ""

    def has(self, one: ready.PullRequest) -> bool:
        """GitHub keeps each pull request's head as `refs/pull/<number>/head`, also one from a
        fork, so `jmerge` fetches a head the main checkout does not have from that ref:
        https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/checking-out-pull-requests-locally
        """
        if one.number not in self.heads:
            commit = f"{one.head}^{{commit}}"
            if _run(self.main, "git", "cat-file", "-e", commit).returncode:
                _run(self.main, "git", "fetch", "-q", "origin", f"refs/pull/{one.number}/head")
            self.heads[one.number] = not _run(self.main, "git", "cat-file", "-e", commit).returncode
        return self.heads[one.number]

    def on_stack(self, one: ready.PullRequest, default: str, stacked: stacks.Stacked | None) -> str:
        """Why a link jbus stacked waits, or nothing. It waits while its line names its base's
        branch, whatever base GitHub gives it now: GitHub bases it on the default branch by
        itself when the base's branch is deleted on its merge, and its head still holds the
        base's commits then. Once jbus wrote the commit that merged its base and the branch it
        merged into, the default or an integration one, it waits until it is based on that
        branch and its head holds that commit: its crew rebased its own commits onto it."""
        if stacked is None:
            return ""
        onto = stacked.branch if stacked.at else default
        if not stacked.at or one.base != onto:
            return ready.STACKED_ON.format(branch=stacked.branch, slug=stacked.slug, default=onto)
        if not self.has(one) or self.outside(stacked.at, one.head):
            return ready.STACKED_UNMOVED.format(
                slug=stacked.slug, sha=stacked.at[:12], default=onto
            )
        return ""

    def outside(self, commit: str, of: str) -> bool:
        """Whether `of` lacks `commit`. A ref that cannot be read lacks it too, which keeps a
        pull request waiting rather than merging what it may carry."""
        return bool(_run(self.main, "git", "merge-base", "--is-ancestor", commit, of).returncode)

    @functools.cached_property
    def ordered(self) -> dict[int, str]:
        """The open pull requests whose rows merge after another row, by number, with their
        slugs. Only these can hold back a pull request that carries them (`rows.short`)."""
        slugs = rows.ordered(self.queue)
        found = {}
        for one in self.open:
            brief = ready.brief_of(one.url, self.state / "tasks")
            if brief is not None and brief.stem in slugs:
                found[one.number] = brief.stem
        return found

    def carries(self, one: ready.PullRequest) -> list[tuple[str, int, bool]]:
        """The open pull requests in `ordered` whose commits a merge of `one` would land: those
        whose head `one`'s head contains and its base does not. Each comes with whether both
        heads could be read, and one that could not is kept, since it may be carried."""
        found = []
        for other in self.open:
            slug = self.ordered.get(other.number)
            if slug is None or other.number == one.number:
                continue
            if not (self.has(other) and self.has(one)):
                found.append((slug, other.number, False))
            elif not self.outside(other.head, one.head) and self.outside(
                other.head, f"origin/{one.base}"
            ):
                found.append((slug, other.number, True))
        return found

    def others(self, text: str) -> bool:
        """Whether the brief is another home's, to a home that asks with `--home`. A home sees
        its own pull requests alone, and merges none: only a run that names no home, jbus's,
        merges, and it judges every home's brief as its own (`every`). The `home-thread` file
        plays no part: a home that asks never merges, whatever the file holds, since jbus is
        the only merger."""
        return claims.home_of(text, self.homes.known) != self.asking

    @functools.cached_property
    def asking(self) -> str:
        if self.mine == self.listed:
            return claims.ROOT
        if self.mine in self.homes.running:
            return self.homes.running[self.mine]
        root_runs, handed_off = bool(self.listed), self.mine in self.homes.known
        if root_runs or handed_off:
            return claims.NOBODY
        return claims.ROOT

    @functools.cached_property
    def homes(self) -> Homes:
        named, running = {}, {}
        for scope, now, was in home_rule.scopes(self.state):
            named.update(dict.fromkeys(filter(None, [scope.name, now, was]), scope.name))
            if now:
                running[now] = scope.name
        named.update(dict.fromkeys(filter(None, [self.listed, self.was]), claims.ROOT))
        if self.listed:
            running[self.listed] = claims.ROOT
        return Homes(known=named, running=running)

    def claimed(self) -> int:
        asked = _run(
            self.main,
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "1000",
            "--json",
            "number,url,files",
            *self.about,
        )
        try:
            listed = json.loads(asked.stdout)
            open_pulls = {str(one["url"]): int(one["number"]) for one in listed}
            files = {
                str(one["url"]): [str(each["path"]) for each in one.get("files") or []]
                for one in listed
            }
        except (ValueError, KeyError, TypeError, AttributeError):
            open_pulls, files = None, {}
        if asked.returncode or open_pulls is None:
            print(f"wait: could not ask GitHub{_why(self.main, asked)}", flush=True)
            return 1
        homes = self.homes.known
        for brief in sorted((self.state / "tasks").glob("*.md")):
            claim = claims.of_brief(brief.stem, _read(brief), open_pulls, homes, files)
            if claim:
                print(claim.line(), flush=True)
        return 0

    def scoped(self, slug: str) -> int:
        text = _read(self.state / "tasks" / f"{slug}.md")
        if not text:
            print(f"jmerge: no brief {slug} in {self.state / 'tasks'}", file=sys.stderr)
            return 1
        if not parse.where(text):
            print(
                f"jmerge: {slug}'s Where: line names no path, so its width cannot be checked",
                file=sys.stderr,
            )
            return 1
        branch, pull = claims.branch_of(slug, text)
        changed = self.changed(branch, claims.stacked_on(text))
        if changed is None and pull:
            asked = _run(
                self.main, "gh", "pr", "view", pull, "--json", "files", "--jq", ".files[].path"
            )
            changed = None if asked.returncode else sorted(asked.stdout.splitlines())
        if changed is None:
            print(
                f"jmerge: no branch {branch} here or on origin, and no pull request to ask",
                file=sys.stderr,
            )
            return 1
        for line in claims.scope(text, changed):
            print(line, flush=True)
        return 0

    def changed(self, branch: str, base: str) -> list[str] | None:
        if not base:
            tip = _run(
                self.main, "git", "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD"
            )
            base = tip.stdout.strip().removeprefix("origin/")
        heads = (f"refs/heads/{branch}", f"refs/remotes/origin/{branch}")
        starts = (f"refs/remotes/origin/{base}", f"refs/heads/{base}") if base else ()
        for head, start in itertools.product(heads, starts):
            fork = _run(self.main, "git", "merge-base", start, head)
            if fork.returncode:
                continue
            diff = _run(
                self.main,
                *("git", "-c", "core.quotePath=false", "diff", "--no-renames", "--name-only"),
                fork.stdout.strip(),
                head,
            )
            return None if diff.returncode else sorted(diff.stdout.splitlines())
        return None

    def default(self) -> tuple[str, str]:
        asked = _run(
            self.main,
            "gh",
            "repo",
            "view",
            *self.about[1:],
            "--json",
            "defaultBranchRef",
            "--jq",
            ".defaultBranchRef.name",
        )
        if asked.returncode:
            return "", _why(self.main, asked)
        branch = asked.stdout.strip()
        return branch, "" if branch else _why(self.main, asked, "it named no default branch")

    def based_on(self, branch: str) -> str:
        """When a pull request merges and its branch is deleted, GitHub retargets every open pull
        request whose base was that branch. So deleting the branch would change a stack's
        order:
        https://github.blog/changelog/2020-05-19-pull-request-retargeting/
        """
        asked = _run(
            self.main,
            "gh",
            "pr",
            "list",
            "--base",
            branch,
            "--state",
            "open",
            "--json",
            "number",
            *self.about,
        )
        try:
            numbers = sorted(int(one["number"]) for one in json.loads(asked.stdout))
        except (ValueError, KeyError, TypeError):
            numbers = None
        if asked.returncode or numbers is None:
            why = _why(self.main, asked)
            return f"could not ask GitHub whether a pull request is based on it{why}"
        if not numbers:
            return ""
        several = "s" if len(numbers) > 1 else ""
        verb = "are" if several else "is"
        return f"the open pull request{several} {' '.join(map(str, numbers))} {verb} based on it"

    def files_of(self, number: int, jq: str) -> subprocess.CompletedProcess[str]:
        """What `jq` picks from each file of GitHub's files endpoint for pull request `number`,
        paged through: https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files"""
        return subprocess.run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{{owner}}/{{repo}}/pulls/{number}/files",
                "--jq",
                jq,
            ],
            cwd=self.main,
            capture_output=True,
            text=True,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )

    def in_full(self, one: ready.PullRequest) -> ready.PullRequest:
        """`gh pr list` lists at most 100 of a pull request's files, and the files endpoint
        pages through up to 3000:
        https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files
        Where it cannot be read, `one` keeps the files it has, and `ready.needs_the_user`
        holds it for the user with the counts."""
        if len(one.files) >= one.changed:
            return one
        asked = self.files_of(one.number, ".[] | {filename, status}")
        try:
            every = [] if asked.returncode else list(map(json.loads, asked.stdout.splitlines()))
            return ready.listed_in_full(one, every)
        except (ValueError, KeyError, TypeError, AttributeError):
            return one

    def left(self, one: ready.PullRequest) -> tuple[str, ...] | None:
        """`gh pr list` lists a rename under its new path alone, and only the files endpoint
        gives the file's old path, as `previous_filename`:
        https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files
        """
        if not one.renamed:
            return ()
        asked = self.files_of(one.number, ".[] | .previous_filename // empty")
        return None if asked.returncode else tuple(asked.stdout.splitlines())

    def moved(self, default: str, since: datetime) -> tuple[str, tuple[str, ...]] | None:
        if _run(self.main, "git", "fetch", "-q", "origin").returncode:
            return None
        tip = _run(self.main, "git", "rev-parse", "-q", "--verify", f"origin/{default}^{{commit}}")
        log = _run(
            self.main,
            "git",
            "-c",
            "core.quotePath=false",
            "log",
            "--first-parent",
            f"--since={since.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}",
            "--name-status",
            "-M",
            "--format=",
            f"origin/{default}",
            "--",
        )
        if tip.returncode or log.returncode:
            return None
        paths = [path for line in log.stdout.splitlines() for path in line.split("\t")[1:]]
        return tip.stdout.strip(), tuple(dict.fromkeys(paths))

    def range_diff(
        self, reviewed: str, head: str, default: str, stacked: stacks.Stacked | None = None
    ) -> rangediff.Verdict:
        if not self.fetched:
            self.fetched = True
            _run(self.main, "git", "fetch", "-q", "origin")
        since = self.own_fork(default, reviewed, head, stacked) if stacked else None
        return rangediff.verdict(self.main, reviewed, head, default, since or "")

    def rebase_since_review(self, base: str, covered: str, head: str) -> ready.Rebase | None:
        forks = []
        for commit in (covered, head):
            fork = _run(self.main, "git", "merge-base", f"origin/{base}", commit)
            if fork.returncode:
                return None
            forks.append(fork.stdout.strip())
        if forks[0] == forks[1]:
            return None
        names = ("git", "-c", "core.quotePath=false", "diff", "--no-renames", "--name-only")
        patches = [
            _text(self.main, *names, fork, commit)
            for fork, commit in zip(forks, (covered, head), strict=True)
        ]
        if None in patches:
            return None
        files = sorted({file for patch in patches for file in patch.splitlines()})
        return ready.Rebase("changed", tuple(files), covered, head)

    def left_main_elsewhere(self, base: str, under: str, head: str) -> bool:
        for _ in range(2):
            forks = [
                _run(self.main, "git", "merge-base", f"origin/{base}", commit)
                for commit in (under, head)
            ]
            if not any(fork.returncode for fork in forks):
                return forks[0].stdout != forks[1].stdout
            if self.fetched:
                break
            self.fetched = True
            _run(self.main, "git", "fetch", "-q", "origin")
        return True

    def dropped(
        self, base: str, rebase: ready.Rebase, head: str
    ) -> tuple[ready.Drop, ...] | ready.NoPatch:
        forks = []
        for commit in (rebase.before, rebase.head, head):
            fork = _run(self.main, "git", "merge-base", f"origin/{base}", commit)
            if fork.returncode:
                return ready.NoPatch(commit)
            forks.append(fork.stdout.strip())
        old, new, _ = forks
        if old == new:
            return ()
        diff = ("git", "-c", "core.quotePath=false", "diff", "--no-ext-diff", "--no-renames", "-U0")
        patches = [
            _text(self.main, *diff, "--name-only", fork, commit)
            for fork, commit in ((old, rebase.before), (new, rebase.head))
        ]
        if None in patches:
            return ready.NoPatch(rebase.before)
        lost = []
        for file in sorted({file for patch in patches if patch for file in patch.splitlines()}):
            main = _text(self.main, *diff, old, new, "--", file)
            own = _text(self.main, *diff, old, rebase.before, "--", file)
            if main is None or own is None:
                return ready.NoPatch(rebase.before)
            counts = [
                ready.dropped(main, own, _text(self.main, "git", "show", f"{at}:{file}") or "")
                for at in dict.fromkeys((rebase.head, head))
            ]
            theirs, ours = (min(count) for count in zip(*counts, strict=True))
            if theirs or ours:
                lost.append(ready.Drop(file, theirs, ours))
        return tuple(lost)

    def stale(self, one: ready.PullRequest, left: tuple[str, ...] | None) -> tuple[str, str, str]:
        if one.started is None:
            return "", "", ""
        left = left or ()
        moved = self.moved(one.base, one.started)
        if moved is None:
            return f"{one.base} could not be fetched to see what changed after its check", "", ""
        tip, paths = moved
        stale = ready.stale_paths(one.files, left, paths, self.ci)
        if not stale:
            return "", tip, ""
        asks = self.merged is not None and self.merged.command
        if not asks:
            return ready.short_on_main(stale, one.started, one.base, user=self.user), "", ""
        short = self.merged.of(one.head, tip)
        if short:
            return short, "", ""
        reasons = (ready.BASE_MOVED_ASKED, ready.BASE_MOVED_DUE)
        return self.base_merge.of(one, tip, *reasons), "", ""

    def again(self, one: ready.PullRequest, red: str) -> str:
        """Why a pull request whose required checks failed waits, judged over today's base. Its
        check is its own fault, `red`, unless the base moved since the check started. Then GitHub
        merges the base into it, and its check at the updated head decides, unless the last two
        runs of a check that failed, whichever required check it is, failed a same test of its
        own (`rejudge.Repeated`): a merge would fail it again."""
        moved = None if one.started is None else self.moved(one.base, one.started)
        if (
            moved is None
            or not moved[1]
            or any(self.base_merge.repeats(one, moved[0], check) for check in one.failed)
        ):
            return red
        return self.base_merge.of(one, moved[0])

    def proven_at(self, one: ready.PullRequest) -> str:
        return self.carried.get(one.number) or one.head

    def waits(self, one: ready.PullRequest, default: str) -> Judgement:
        found = self.judge(one, default)
        rebasing = found.verb == "wait" and not one.draft and ready.being_rebased(found.why)
        if one.number in self.order and rebasing:
            self.rebasing.add(one.number)
        else:
            self.rebasing.discard(one.number)
        return found

    def judge(self, one: ready.PullRequest, default: str) -> Judgement:
        """The judgement of the pull request. Where all that holds it is a required check that
        failed, or one with no run at its head, it is judged again as if that check had passed,
        and a judgement that gets as far as freshness judges it over today's base: `again` for a
        check that failed, and for a check with no run GitHub's merge of a base that moved since
        its check started, which brings the head the workflows the base has. One that falls short
        of anything else says that, and not the check: #529 waited ten hours on "macos has not
        passed" while it was short of a scoped review that nobody was asked for."""
        found = self.judged(one, default)
        held = ready.red_only(one) or ready.unrun_only(one)
        if not held or found.why != ready.short_on_github(one):
            return found
        return self.judged(replace(one, waiting=(), unrun=()), default, found.why)

    def judged(self, one: ready.PullRequest, default: str, red: str = "") -> Judgement:
        brief = ready.brief_of(one.url, self.state / "tasks")
        self.carried.pop(one.number, None)
        if brief is None:
            return Judgement("", "wait", ready.DRAFT if one.draft else ready.NO_BRIEF, "", None)
        text = _read(brief)
        if self.others(text) and not self.every:
            return Judgement(brief.stem, "wait", ready.OTHER_HOME, "", None)
        self.trunk = default
        stacked = stacks.of(text)
        short = ready.held(one, default, ready.stack_of(text), self.land, self.integration, stacked)
        short = short or self.on_stack(one, default, stacked)
        short = short or ready.short_of(text, one.head)
        rebase = ready.rebase_of(text, one.head)
        covered = ready.to_range_diff(rebase, text, one.head)
        lost: tuple[ready.Drop, ...] = ()
        if not short:
            patches = self.patches(one.base, ready.to_compare(rebase), stacked)
            short = ready.short_on_rebase(rebase, patches)
        if not short and (covered if rebase is None else rebase.did == "changed"):
            if _run(self.main, "git", "fetch", "-q", "origin").returncode:
                short = f"{one.base} could not be fetched to see what its rebase kept"
            elif covered and (rebase is None or not rebase.files):
                rebase = self.rebase_since_review(one.base, covered, one.head) or rebase
            found = () if short or rebase is None else self.dropped(one.base, rebase, one.head)
            if isinstance(found, ready.NoPatch):
                short = ready.cannot_check(found.commit)
            else:
                lost = found
        if rebase is None and covered is None:
            lost = ready.answered(text, one.head)
        short = short or ready.short_on_github(
            replace(one, waiting=(), failed=()) if one.draft else one
        )
        note = ""
        silent = ready.unexplained(lost, text, one.head)
        under = ready.under_fix(rebase, text, one.head)
        if (
            under
            and covered is None
            and not short
            and self.left_main_elsewhere(one.base, under, one.head)
        ):
            covered = under
        reviewed = None if short or silent else covered
        verdict: rangediff.Verdict | None = None
        if reviewed == "":
            short = ready.NO_HEAD
        elif reviewed:
            verdict = self.range_diff(reviewed, one.head, one.base, stacked)
            short = ready.short_on_content(verdict)
            if not short:
                self.carried[one.number] = reviewed
            note = ready.rebase_note(verdict) if rebase is None or rebase.did == "changed" else ""
        if short:
            return Judgement(brief.stem, "wait", short, note, None)
        short = (
            rows.short(self.queue, brief.stem)
            or (
                rows.short(self.queue, brief.stem, self.carries(one))
                if ready.stack_of(text) is None
                else ""
            )
            or self.red(one, default, brief.stem, text)
            or self.short_on_migrations(one, one.base)
        )
        if short:
            return Judgement(brief.stem, "wait", short, note, None)
        left = self.left(one)
        lifted = self.accepted == (one.number, one.head)
        command = verdict.command if verdict else "nothing"
        kind, why = ready.drops(lost, text, one.head, user=self.user, command=command)
        if not kind:
            kind, why = ready.declines(text, user=self.user)
        self.lifts = []
        if lifted and kind == "hold":
            self.lifts.append(why)
            kind = ""
        if kind:
            return Judgement(brief.stem, kind, why, note, None)
        hold = ready.needs_the_user(one, self.protected, left, user=self.user)
        if lifted and hold:
            self.lifts.append(hold)
            hold = ""
        if hold:
            return Judgement(brief.stem, "hold", hold, note, None)
        if one.draft:
            return Judgement(brief.stem, "wait", ready.DRAFT, note, None)
        if red and re.fullmatch(ready.NO_RUN.pattern, red):
            moved = None if one.started is None else self.moved(one.base, one.started)
            if moved is not None and moved[1]:
                reasons = (ready.BASE_MOVED_ASKED, ready.BASE_MOVED_DUE)
                red = self.base_merge.of(one, moved[0], *reasons)
            return Judgement(brief.stem, "wait", red, note, None)
        if red:
            return Judgement(brief.stem, "wait", self.again(one, red), note, None)
        short, tip, fresh = self.stale(one, left)
        if short:
            return Judgement(brief.stem, "wait", short, note, None)
        note = f"{note}, {ready.KEPT}" if note else ""
        if (self.state / "merge-off").exists():
            return Judgement(brief.stem, "wait", ready.MERGE_OFF, note, None)
        gated = (
            self.gate.of(one.number, one.head, one.base)
            if self.gate and self.gate.command
            else None
        )
        if gated and gated.verb:
            return Judgement(brief.stem, gated.verb, gated.why, note, None)
        if one.number in self.order:
            self.through = one.number
        judged = ready.Judged(tip, fresh, gated.note if gated else "")
        return Judgement(brief.stem, "", "", note, judged)

    def red(self, one: ready.PullRequest, default: str, slug: str, text: str) -> str:
        """The red hold on a pull request. For a pull request into main it is main's hold, and
        for a pull request into an integration branch it is that branch's hold. It reads the
        latest checks of the branch's tip, and asks GitHub once per run. When GitHub gives no
        answer for a branch, the branch is not known to be red, as with a main that jbus never
        judged."""
        if one.base == default:
            main, ran = self.main_state, rows.UNPROVED
            if main.red and main.failed and not mainjson.fix_of(slug):
                ran = self.proved(one, main.red, main.failed)
            return rows.red(main, slug, ran) or browser_red(self, one, default, slug)
        if one.base not in self.reds:
            asked = subprocess.run(
                ["gh", "api", f"repos/{{owner}}/{{repo}}/commits/{one.base}/check-runs"],
                cwd=self.main,
                capture_output=True,
                text=True,
                env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
            )
            try:
                runs = [] if asked.returncode else json.loads(asked.stdout)["check_runs"]
            except (ValueError, KeyError, TypeError):
                runs = []
            self.reds[one.base] = runs if isinstance(runs, list) else []
        return rows.base_red(one.base, self.reds[one.base], slug, text)

    def proved(self, one: ready.PullRequest, red: str, failed: tuple[str, ...]) -> rows.Ran:
        """What the pull request's own check proved of the red tip `red` (`rows.Ran`), once a
        run for each head. A check proves nothing until every check of the head has passed, and
        nothing where the head lacks `red`. Then each passed job's log says what it ran
        (`rows.ran_in`), and the logs are read until they cover every test in `failed`. Only the
        jobs of the required check count (`checked`): a browser run's `pytest -m browser` names no
        path and ran no test of the rest."""
        key = (one.number, one.head, red, "check")
        if key not in self.proofs:
            self.proofs[key] = rows.UNPROVED
            rollup = self.reds.get(ROLLUP.format(number=one.number), [])
            if passed(rollup) and self.has(one) and not self.outside(red, one.head):
                every, paths = False, frozenset[str]()
                for job in jobs(checked(rollup)):
                    found = rows.ran_in(self.job_log(job) or "", rows.CHECK)
                    if found is not None:
                        every, paths = every or found.every, paths | found.paths
                    ran = rows.Ran(over=red, every=every, paths=paths)
                    self.proofs[key] = ran
                    if all(map(ran.covers, failed)):
                        break
        return self.proofs[key]

    def proved_browser(self, one: ready.PullRequest, red: str) -> rows.Ran:
        """What the pull request's own browser run proved of main's red browser run at `red`:
        what it ran and the tests it failed, which it names in full, at a head that has `red`."""
        key = (one.number, one.head, red, ready.BROWSER)
        if key not in self.proofs:
            self.proofs[key] = rows.UNPROVED
            rollup = self.reds.get(ROLLUP.format(number=one.number), [])
            run = ready.latest(rollup, ready.BROWSER)
            job = jobs(run, ("FAILURE",))
            log = self.job_log(job[0]) if len(job) == 1 else None
            found = rows.ran_in(log or "", rows.BROWSER)
            if found is not None and self.has(one) and not self.outside(red, one.head):
                failed = failed_in(log or "")
                if failed.count == len(failed.tests):
                    self.proofs[key] = rows.Ran(
                        red, found.every, found.paths, frozenset(failed.tests)
                    )
        return self.proofs[key]

    def run_failed(self, run: object) -> tuple[str, ...]:
        """The tests a run failed, as its failed jobs' logs name them (`mainjson.failures`), or
        none where GitHub did not list its jobs or give a log."""
        said = self.api(f"repos/{{owner}}/{{repo}}/actions/runs/{run}/jobs?per_page=100")
        listed = said.get("jobs") if isinstance(said, dict) else None
        named = []
        for job in listed if isinstance(listed, list) else []:
            if not isinstance(job, dict) or job.get("conclusion") in rows.NOT_RED:
                continue
            log = self.job_log(str(job.get("id")))
            if log is None:
                return ()
            found = failed_in(log)
            named.append((str(job.get("name") or ""), found.tests, found.count))
        return tuple(mainjson.failures(named))

    def api(self, path: str) -> object:
        """GitHub's answer to `gh api <path>`, or None."""
        asked = subprocess.run(
            ["gh", "api", path],
            cwd=self.main,
            capture_output=True,
            text=True,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        try:
            return None if asked.returncode else json.loads(asked.stdout)
        except ValueError:
            return None

    def job_log(self, job: str) -> str | None:
        """A job's log, as GitHub gives it, once a run, or None. gh gives a log that holds escape
        sequences only when asked to, as `jbus.watch.job_log` does."""
        if job not in self.logs:
            asked = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{{owner}}/{{repo}}/actions/jobs/{job}/logs",
                    "--allow-escape-sequences",
                ],
                cwd=self.main,
                capture_output=True,
                text=True,
                env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
            )
            self.logs[job] = None if asked.returncode else asked.stdout
        return self.logs[job]

    def patches(
        self, base: str, compared: tuple[str, ...], stacked: stacks.Stacked | None
    ) -> list[str | None]:
        """The patch of each head a `Rebase:` line compares, the old one over its own commits
        (`own_fork`)."""
        if len(compared) != 2:
            return [patch_id(self.main, base, each) for each in compared]
        before, head = compared
        own = self.own_fork(base, before, head, stacked)
        if own is None:
            return [None, patch_id(self.main, base, head)]
        return [patch_id(self.main, base, before, own), patch_id(self.main, base, head)]

    def own_fork(
        self, base: str, before: str, head: str, stacked: stacks.Stacked | None
    ) -> str | None:
        """Where the link's own commits start in its head `before` a rebase onto `head`: its
        fork from `base`, or None when git cannot say. A link jbus moved once its base merged is
        the exception: its old head forks from the base's branch before the base's commits,
        which a squash merge leaves out of that branch's history, so its own commits are as many
        of its last ones as `head` has above its fork."""
        if stacked is None or not stacked.at:
            fork = _run(self.main, "git", "merge-base", f"origin/{base}", before)
            return None if fork.returncode else fork.stdout.strip()
        fork = _run(self.main, "git", "merge-base", f"origin/{base}", head)
        if fork.returncode:
            return None
        span = f"{fork.stdout.strip()}..{head}"
        count = _run(self.main, "git", "rev-list", "--count", "--first-parent", span)
        if count.returncode:
            return None
        own = _run(self.main, "git", "rev-parse", "--verify", f"{before}~{count.stdout.strip()}")
        return None if own.returncode else own.stdout.strip()

    def holds(self) -> dict[str, str]:
        return jbus.read_dict(self.state / "holds.json")

    def readied(self, one: ready.PullRequest, found: Judgement) -> Judgement:
        """Mark ready a draft whose review is written and whose fix is pushed, so CI runs its one
        check now, on this head (check.yml runs none on a draft). A brief that says
        `Review: none` is marked too, and still holds for the user's word."""
        ran = _run(self.main, "gh", "pr", "ready", str(one.number), *self.about)
        if found.why != ready.DRAFT:
            return found
        if ran.returncode:
            return found._replace(why=ready.UNREADIED.format(said=lines.said(ran)))
        return found._replace(why=ready.READIED.format(head=one.head))

    def hold(self, one: ready.PullRequest) -> None:
        self.holds_are({**self.holds(), str(one.number): one.head})

    def holds_are(self, holds: dict[str, str]) -> None:
        if holds != self.holds() and self.state.is_dir():
            jbus.write_json(self.state / "holds.json", holds)

    def accept(
        self,
        one: ready.PullRequest,
        default: str,
        by: str | None,
        when: str | None,
        say: Callable[[str], None],
        check: bool,
        acting: accepts.Acting | None = None,
    ) -> int:
        """Lift the hold of `one` and merge it, the user's hand-merge. With `acting`, the accept
        is an act of jbus's (`jmerge.accepts`): a door the party may not open parks a gate and
        merges nothing. `check` says what it would do, and is no act."""
        about = f"{one.number} {one.url}"
        first = self.waits(one, default)
        if first.verb != "hold":
            state = f"it waits: {first.why}" if first.verb else "jmerge merges it by itself"
            say(f"refused {about}: it is not held, {state}")
            return 1
        if ready.gate_held(first.why):
            say(f"refused {about}: {first.why}, and a gate that passes lifts it, not --accept")
            return 1
        was = self.holds().get(str(one.number), "")
        if was != one.head:
            held = f"was at {was[:12]}" if was else "is not on record, run jmerge first"
            say(f"refused {about}: its hold {held}, and its head is {one.head[:12]}")
            return 1
        text = _read(self.state / "tasks" / f"{first.slug}.md")
        at = self.proven_at(one)
        proven = proof.fact(text, at)
        if proven is None:
            say(f"refused {about}: {proof.short(text, at)}")
            return 1
        safe = f"safe because {proven[0]} (proven at {at[:12]})"
        self.accepted = (one.number, one.head)
        found = self.waits(one, default)
        if found.judged is None:
            say(lines.waits(found.verb, one.number, one.url, found.why))
            return 1
        why = " and ".join(self.lifts) or first.why
        if check:
            notes = [f"accepted: {why}", safe]
            say(lines.ready(one.number, one.head, one.branch, found.slug, notes))
            return 0
        ran: list[str] = []

        def does() -> str:
            ran.append(one.head)
            say(f"accepted {about}: {why}, lifted at {one.head[:12]} by {by} at {when}, {safe}")
            said = self.merge(one, found.slug, found.note, found.judged)
            say(said)
            if not said.startswith("merged "):
                raise jbus.Refused(said)
            self.holds_are({n: head for n, head in self.holds().items() if n != str(one.number)})
            return said

        if acting is None:
            try:
                does()
            except jbus.Refused:
                return 1
            return 0
        touched = bool(ready.protected_path(one, self.protected, self.left(one) or ()))
        held = accepts.doors(text, touched)
        outcome, line = accepts.accept(acting, one.number, found.slug, one.head, held, does)
        if outcome == "done":
            return 0
        if not ran:
            say(line)
        return 1

    def clear_up(self, branch: str, head: str) -> str:
        tree = at = ""
        listed = _run(self.main, "git", "worktree", "list", "--porcelain").stdout
        for line in listed.splitlines():
            if line.startswith("worktree "):
                at = line.removeprefix("worktree ")
            elif line == f"branch refs/heads/{branch}":
                tree = at
        local = _run(self.main, "git", "rev-parse", "-q", "--verify", f"refs/heads/{branch}")
        if local.stdout.strip() != head:
            return f"{branch} is not at the merged head"
        if tree and _run(self.main, "git", "-C", tree, "status", "--porcelain").stdout.strip():
            return f"{tree} has uncommitted work"
        if tree:
            ran = _run(self.main, "git", "worktree", "remove", tree)
            if ran.returncode:
                why = lines.said(ran)
                return f"{tree} could not be removed, and both branches are left ({why})"
        ran = _run(self.main, "git", "branch", "-q", "-D", branch)
        if ran.returncode:
            why = lines.said(ran)
            return f"the local and remote branch {branch}, the worktree is removed ({why})"
        gone = f"the remote branch {branch}, the worktree and the local branch are removed"
        based = self.based_on(branch)
        if based:
            return f"{gone} ({based})"
        ref = f"refs/heads/{branch}"
        ran = _run(
            self.main, "git", "push", "-q", f"--force-with-lease={ref}:{head}", "origin", f":{ref}"
        )
        if not ran.returncode:
            return ""
        stale = "(stale info)" in ran.stderr
        why = "it is not at the merged head on the origin" if stale else lines.said(ran)
        return f"{gone} ({why})"

    def messages(self, one: ready.PullRequest) -> list[str] | None:
        """The message of each commit on the branch and not on its base, oldest first, as
        GitHub's default squash body lists them, and None when git cannot read them."""
        base = f"refs/remotes/origin/{one.base}"
        fetched = _run(
            self.main, "git", "fetch", "-q", "origin", one.head, f"+refs/heads/{one.base}:{base}"
        )
        if fetched.returncode:
            return None
        ran = _run(self.main, "git", "log", "--reverse", "--format=%B%x00", one.head, "--not", base)
        if ran.returncode:
            return None
        return [message.strip() for message in ran.stdout.split("\0") if message.strip()]

    @functools.cached_property
    def landing(self) -> tuple[str, str]:
        """The flag of `gh pr merge` that lands an integration branch, read once a run from what
        the repo allows: a merge commit where it allows one, else a squash. With neither, or
        when GitHub does not say, the flag is empty and the reason says why:
        https://docs.github.com/en/rest/repos/repos#get-a-repository"""
        ran = subprocess.run(
            ["gh", "api", "repos/{owner}/{repo}"],
            cwd=self.main,
            capture_output=True,
            text=True,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
        if ran.returncode:
            return "", f"{ready.NO_SETTINGS}: {lines.said(ran)}"
        try:
            said = json.loads(ran.stdout)
        except ValueError:
            said = None
        if not isinstance(said, dict):
            return "", f"{ready.NO_SETTINGS}: GitHub's answer is not a repo"
        if not {"allow_merge_commit", "allow_squash_merge"} <= said.keys():
            return "", f"{ready.NO_SETTINGS}: GitHub gives them to a token with push access only"
        if said.get("allow_merge_commit") is True:
            return "--merge", ""
        if said.get("allow_squash_merge") is True:
            return "--squash", ""
        allowed = "rebase merges" if said.get("allow_rebase_merge") is True else "no merge method"
        return "", ready.LANDING_UNALLOWED.format(allowed=allowed)

    def merge(
        self,
        one: ready.PullRequest,
        slug: str,
        rebase: str = "",
        judged: ready.Judged | None = None,
    ) -> str:
        judged = judged or ready.Judged()
        from jmerge.lock import MergeLock

        lock = MergeLock(self.state)
        try:
            return self.merge_holding(lock, one, slug, rebase, judged)
        finally:
            lock.give()

    def merge_holding(
        self, lock, one: ready.PullRequest, slug: str, rebase: str, judged: ready.Judged
    ) -> str:
        """Merge `one` while this run holds the repo's merge lock, from the read of its base's
        tip to the merge. A tip that moved since it was judged gives the lock back while the pull
        request is judged again, so a wait on GitHub holds up no other run."""
        number = str(one.number)
        again = 0
        while lock.take():
            if not judged.tip:
                break
            at = _run(self.main, "git", "ls-remote", "origin", f"refs/heads/{one.base}")
            if not at.returncode and _first_word(at.stdout) == judged.tip:
                break
            lock.give()
            if again == JUDGED_AGAIN_AT_MOST:
                moved = ready.MAIN_MOVED.format(base=one.base)
                return lines.waits("wait", number, one.url, moved)
            again += 1
            self.numbers_on.clear()
            again_judged = self.waits(one, self.trunk or one.base)
            if again_judged.judged is None:
                return lines.waits(again_judged.verb, number, one.url, again_judged.why)
            rebase, judged = again_judged.note, again_judged.judged
        else:
            return lines.waits("wait", number, one.url, ready.MERGING)
        landing = one.base == self.trunk and one.branch in self.integration
        method, why = self.landing if landing else ("--squash", "")
        if not method:
            return lines.waits("wait", number, one.url, why)
        if method == "--merge":
            subject, body = (), one.title
        else:
            messages = self.messages(one)
            if messages is None:
                return lines.waits("wait", number, one.url, ready.NO_MESSAGES)
            subject = ("--subject", f"{one.title} (#{number})")
            body = "\n\n".join(f"* {trailers.strip(message)}" for message in messages)
        ran = _run(
            self.main,
            "gh",
            "pr",
            "merge",
            number,
            method,
            "--match-head-commit",
            one.head,
            *subject,
            "--body-file",
            "-",
            *self.about,
            stdin=trailers.strip(body) + "\n",
        )
        if ran.returncode:
            return lines.waits("wait", number, one.url, f"{ready.MERGE_FAILED}: {lines.said(ran)}")
        notes = [rebase] if rebase else []
        if self.trunk and one.base != self.trunk:
            notes.insert(0, f"into {one.base}")
        if landing:
            notes.insert(0, LANDED[method].format(branch=one.branch))
        asked = _run(
            self.main,
            "gh",
            "pr",
            "view",
            number,
            "--json",
            "mergeCommit",
            "--jq",
            ".mergeCommit.oid",
            *self.about,
        )
        commit = asked.stdout.strip()
        if asked.returncode or not commit:
            commit = one.head
            notes.append("that commit is its head, GitHub did not give the merge commit")
        before = _run(self.main, "git", "rev-parse", "HEAD").stdout.strip()
        pulled = _run(self.main, "git", "pull", "--ff-only")
        self.numbers_on.clear()
        if pulled.returncode:
            notes.append(lines.not_pulled(lines.said(pulled)))
        else:
            notes += follow.follow(_run, self.main, before)
        kept = (
            f"{one.branch} is an integration branch"
            if one.branch in self.integration
            else self.clear_up(one.branch, one.head)
        )
        if kept:
            notes.append(f"kept: {kept}")
        if judged.fresh:
            notes.append(judged.fresh)
        if judged.gate:
            notes.append(judged.gate)
        return lines.merged(number, slug, commit, one.title, notes, one.url)


PROC = Path("/proc")


def _cwds_from_proc() -> dict[int, str] | None:
    try:
        listed = [PROC / name for name in os.listdir(PROC) if name.isdigit()]
    except OSError:
        return None
    if PROC / str(os.getpid()) not in listed:
        return None
    cwds = {}
    for entry in listed:
        try:
            cwds[int(entry.name)] = os.readlink(entry / "cwd")
        except OSError:
            continue
    return cwds


def _cwds_from_lsof() -> dict[int, str] | None:
    """The working directory of each of the user's processes on a Mac, which has no /proc. lsof's
    `-F n` prints a `p<pid>` line for each process and an `n<path>` line for its cwd."""
    command = ["lsof", "-w", "-a", "-d", "cwd", "-u", str(os.getuid()), "-F", "n"]
    try:
        said = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if said.returncode:
        return None
    cwds, pid = {}, 0
    for line in said.stdout.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid:
            cwds[pid] = line[1:]
    return cwds if os.getpid() in cwds else None


def _running(tree: str) -> int | None:
    """The lowest pid of a process whose working directory is in the tree, 0 for none, and None
    when no list of every process could be read. A Mac reads lsof, unless a caller set PROC."""
    on_a_mac = sys.platform == "darwin" and PROC == Path("/proc")
    cwds = _cwds_from_lsof() if on_a_mac else _cwds_from_proc()
    if cwds is None:
        return None
    inside = os.path.realpath(tree)
    found = [pid for pid, at in cwds.items() if at == inside or at.startswith(f"{inside}/")]
    return min(found, default=0)


class Sweep:
    def __init__(self, repo: Repo) -> None:
        self.repo = repo
        self.main = repo.main
        self.state = repo.state
        self.trees = Path.home() / ".t3" / "worktrees" / repo.main.name
        self.default = self.tip = ""
        self.remote: dict[str, str] = {}
        self.markers: dict[str, str] = {}
        self.local: dict[str, str] = {}
        self.worktrees: list[tuple[str, str]] = []

    def read(self) -> bool:
        asked = _run(
            self.main,
            "git",
            "ls-remote",
            "--symref",
            "origin",
            "HEAD",
            "refs/heads/*",
            f"{sweep.MARKERS}*",
        )
        for line in asked.stdout.splitlines():
            first, _, name = line.partition("\t")
            if first.startswith("ref: refs/heads/") and name == "HEAD":
                self.default = first.removeprefix("ref: refs/heads/")
            elif name.startswith("refs/heads/"):
                self.remote[name.removeprefix("refs/heads/")] = first
            elif name.startswith(sweep.MARKERS):
                self.markers[name] = first
        self.tip = self.remote.get(self.default, "")
        if asked.returncode or not self.tip:
            return False
        if _run(self.main, "git", "fetch", "-q", "origin").returncode:
            return False
        self.local = self._heads(self.main)
        at = on = ""
        listed = _run(self.main, "git", "worktree", "list", "--porcelain").stdout
        for line in [*listed.splitlines(), ""]:
            if line.startswith("worktree "):
                at, on = line.removeprefix("worktree "), ""
            elif line.startswith("branch refs/heads/"):
                on = line.removeprefix("branch refs/heads/")
            elif not line and at:
                self.worktrees.append((at, on))
                at = ""
        return True

    def _heads(self, repo: Path) -> dict[str, str]:
        listed = _run(
            repo, "git", "for-each-ref", "--format=%(objectname) %(refname)", "refs/heads"
        )
        heads = (line.split(" ", 1) for line in listed.stdout.splitlines())
        return {name.removeprefix("refs/heads/"): commit for commit, name in heads}

    def records(self) -> dict[str, list[sweep.Record]]:
        named: dict[str, list[sweep.Record]] = {}
        for directory, read in (("tasks", sweep.of_brief), ("scouts", sweep.of_request)):
            for path in sorted((self.state / directory).glob("*.md")):
                record = read(path.stem, _read(path))
                named.setdefault(record.branch, []).append(record)
        return named

    def left(self, branch: str) -> dict[str, str]:
        there = {
            sweep.WORKTREE: next((at for at, on in self.worktrees if on == branch), ""),
            sweep.LOCAL: self.local.get(branch, ""),
            sweep.REMOTE: self.remote.get(branch, ""),
        }
        return {what: at for what, at in there.items() if at}

    def _within(self, commit: str, of: str) -> bool:
        ran = _run(self.main, "git", "merge-base", "--is-ancestor", commit, of)
        return ran.returncode == 0

    def _safe(self, commit: str, head: str, pull: str) -> bool:
        """GitHub keeps a pull request's head as `refs/pull/<number>/head` after its branch is
        deleted. So when the main checkout no longer has a merged head, `jmerge` fetches it
        from that ref:
        https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/checking-out-pull-requests-locally
        """
        if commit == head or self._within(commit, self.tip):
            return True
        if not head:
            return False
        if _run(self.main, "git", "cat-file", "-e", f"{head}^{{commit}}").returncode:
            number = pull.rstrip("/").rsplit("/", 1)[-1]
            _run(self.main, "git", "fetch", "-q", "origin", f"refs/pull/{number}/head")
        return self._within(commit, head)

    def found(self, record: sweep.Record, left: dict[str, str]) -> sweep.Found:
        state = head = silent = ""
        if record.pull and not record.short:
            asked = _run(
                self.main, "gh", "pr", "view", record.pull, "--json", "state,headRefOid,baseRefName"
            )
            try:
                said = json.loads(asked.stdout)
                state = "" if asked.returncode else str(said["state"])
                into = (self.default, *self.repo.integration)
                if state == "MERGED" and said["baseRefName"] in into:
                    head = str(said["headRefOid"])
            except (ValueError, KeyError, TypeError):
                state = ""
            if not state:
                silent = _why(self.main, asked)
        tree = left.get(sweep.WORKTREE, "")
        status = _run(self.main, "git", "-C", tree, "status", "--porcelain") if tree else None
        refs = (sweep.LOCAL, sweep.REMOTE)
        found = sweep.Found(
            default=self.default,
            pull=state,
            silent=silent,
            merged=bool(head),
            tree=tree,
            trees="" if not tree or self.trees in Path(tree).parents else str(self.trees),
            dirty=bool(status and Path(tree).exists() and (status.returncode or status.stdout)),
            stray=tuple(
                ref for ref in refs if ref in left and not self._safe(left[ref], head, record.pull)
            ),
            pid=_running(tree) if tree else 0,
        )
        if sweep.REMOTE in left and not sweep.kept(record, found):
            found = replace(found, based=self.repo.based_on(record.branch))
        return found

    def remove(self, branch: str, left: dict[str, str]) -> tuple[list[str], str, str]:
        ref = f"refs/heads/{branch}"
        tree = left.get(sweep.WORKTREE, "")
        steps = {
            sweep.WORKTREE: ["worktree", "remove", tree],
            sweep.LOCAL: ["update-ref", "-d", ref, left.get(sweep.LOCAL, "")],
            sweep.REMOTE: [
                "push",
                "-q",
                f"--force-with-lease={ref}:{left.get(sweep.REMOTE, '')}",
                "origin",
                f":{ref}",
            ],
        }
        gone: list[str] = []
        for what in left:
            ran = _run(self.main, "git", *steps[what])
            if ran.returncode:
                return gone, what, lines.said(ran)
            gone.append(what)
            if what == sweep.LOCAL:
                _run(self.main, "git", "config", "--remove-section", f"branch.{branch}")
        return gone, "", ""

    def marked(self, ref: str, commit: str) -> int | None:
        asked = "git", "show", "-s", "--format=%ct", f"{commit}^{{commit}}"
        made = _run(self.main, *asked)
        if made.returncode:
            _run(self.main, "git", "fetch", "-q", "origin", ref)
            made = _run(self.main, *asked)
        return int(made.stdout) if not made.returncode and made.stdout.strip().isdigit() else None

    def markers_past(self, say: Callable[[str], None], check: bool) -> list[tuple[str, str]]:
        kept: list[tuple[str, str]] = []
        for ref, commit in sorted(self.markers.items()):
            kind, _, tree = ref.removeprefix(sweep.MARKERS).rpartition("/")
            label = f"green-tree/{kind}{'/' if kind else ''}{tree[:12]}"
            made = self.marked(ref, commit)
            if made is None:
                kept.append((label, "the commit its marker is at could not be read"))
                continue
            days = sweep.past(made, time.time())
            if not days:
                continue
            what = f"{label} no-thread: the marker of a tree that passed {days} days ago"
            if check:
                say(f"removable {what}")
                continue
            lease = f"--force-with-lease={ref}:{commit}"
            ran = _run(self.main, "git", "push", "-q", lease, "origin", f":{ref}")
            if ran.returncode:
                kept.append((label, f"its marker could not be removed ({lines.said(ran)})"))
            else:
                say(f"removed {what}")
        return kept

    def run(self, say: Callable[[str], None], check: bool) -> int:
        if not self.read():
            say("wait: could not read origin")
            return 1
        named = self.records()
        kept: list[tuple[str, str]] = []
        for branch in sorted(named):
            left = self.left(branch)
            if not left:
                continue
            first, *more = named[branch]
            if more:
                why = f"{first.source} and {more[0].source} both name it"
            elif branch == self.default:
                why = "it is the default branch"
            elif branch in self.repo.integration:
                why = "it is an integration branch"
            else:
                why = sweep.kept(first, self.found(first, left))
            if why:
                kept.append((branch, why))
                continue
            thread = first.thread or "no-thread"
            if check:
                say(f"removable {branch} {thread}: {', '.join(left)}")
                continue
            gone, stopped, said = self.remove(branch, left)
            if not gone:
                kept.append((branch, f"{stopped} could not be removed ({said})"))
            else:
                tail = f", kept: {stopped} ({said})" if stopped else ""
                say(f"removed {branch} {thread}: {', '.join(gone)}{tail}")
        kept += self.markers_past(say, check)
        for at, on in self.worktrees[1:]:
            if self.trees in Path(at).parents and on not in named:
                on = f"its branch {on}" if on else "it, and it is on no branch"
                kept.append((Path(at).name, f"no brief or request names {on}"))
        for label, why in sorted(kept):
            say(f"kept {label}: {why}")
        return 0


def _job(repo: str, job: str) -> dict:
    """A job as GitHub gives it, or an empty dict where GitHub gives none."""
    given = _run(Path.cwd(), "gh", "api", f"repos/{repo}/actions/jobs/{job}")
    try:
        found = json.loads(given.stdout) if not given.returncode else {}
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}


def said_of_checks(pull: str) -> str:
    pr = [pull] if pull else []
    try:
        fields = "headRefOid,statusCheckRollup,isDraft"
        asked = _run(Path.cwd(), "gh", "pr", "view", *pr, "--json", fields)
        view = json.loads(asked.stdout) if not asked.returncode else None
        rollup, head = view["statusCheckRollup"] or [], view["headRefOid"] or ""
        draft = bool(view.get("isDraft"))
        never = frozenset() if draft else checks.never_started(rollup, _job)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return "wait: could not ask GitHub"
    return checks.SAID[checks.checks(rollup, never, draft)].format(head=head)


def state_of(cwd: Path) -> Path | None:
    """The repo's state in the homes' state, the directory named for its main checkout, or None
    outside a repo."""
    here = _run(cwd, "git", "rev-parse", "--path-format=absolute", "--git-common-dir")
    if here.returncode:
        return None
    return homes_state(Path(here.stdout.strip()).parent)


def homes_state(main_checkout: Path) -> Path:
    """The repo's state in the homes' state, the directory named for its main checkout. The homes'
    state is `JBUS_HOME_DIR`, as jbus reads it, or `~/.local/state/home`."""
    return home_rule.homes_dir() / main_checkout.name


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="jmerge",
        description="Merge this repo's pull requests that are reviewed, fixed and green, pull "
        "the main checkout, and remove each one's worktree and branches. Prints one line per "
        "open pull request. A pull request based on a branch that is neither the default "
        "branch nor one the integration file in the repo's state names is never merged, and "
        "one whose brief has a Stack: line only with --land. One into an integration branch "
        "is judged against that branch, and the one that lands it on the default branch "
        "merges with a merge commit where the repo allows one, else as a squash. "
        "A draft is never merged, with any flag. "
        "One whose check started before main changed one of its paths, a CI path "
        "(features/jmerge/src/jmerge/ci-paths.txt) waits for a fresh check: where the "
        "repo's state has a "
        "fresh-check file, GitHub is asked to merge main into its branch, and its check at "
        "the updated head stands in; no suite runs on this machine. One whose rebase dropped "
        "a line waits for its crew to say why and for the scoped review to uphold it, and is "
        "printed as hold when it does not. "
        "One that changes a protected path (features/jmerge/src/jmerge/protected.txt) is "
        "never merged and is printed as hold. A merge-off file in the repo's state merges "
        "nothing. "
        "Where the repo's state has a merge-gate file, its command is run last, in a checkout "
        "of the head with the merge base and the head as its last two arguments, and a "
        "non-zero exit is printed as hold, its merge gate failed. "
        "With --sweep it merges nothing: it "
        "removes the worktree and the branches of each finished thread whose "
        "work is all merged or pushed, and prints what it removed and what it kept. With "
        "--claims it changes nothing: it prints one line per brief that still holds files, "
        "with its state, its home and its Where line. With --accept it lifts the hold of one "
        "pull request, at the head the hold was said at, when a review proved its one safety "
        "fact at that head, and merges it as any other. With --checks it changes nothing: it "
        "prints the state of one pull request's checks in a line. With --range-diff it "
        "changes nothing: it prints whether a rebase changed the content of a branch.",
    )
    top.add_argument(
        "--check",
        action="store_true",
        help="print what is ready and what waits, or with --sweep what is removable; "
        "merge and remove nothing",
    )
    instead = top.add_mutually_exclusive_group()
    instead.add_argument(
        "--sweep",
        action="store_true",
        help="remove what finished threads left, in place of merging",
    )
    instead.add_argument(
        "--claims",
        action="store_true",
        help="print the files claimed by each brief that is not launched, out, or has an "
        "open pull request, across this repo's homes; merge, remove and log nothing",
    )
    instead.add_argument(
        "--scope",
        metavar="SLUG",
        help="print each file the brief's branch changes that its Where: line does not cover, "
        "as 'outside: <path>', or 'wider: <path>: <why>' where the last Result's Wider: line "
        "gives a reason; nothing is printed when all are inside; merge, remove and log nothing",
    )
    instead.add_argument(
        "--checks",
        metavar="PR",
        nargs="?",
        const="",
        help="print the state of a pull request's checks in one line, each check by its latest "
        "run: passed, failed, wait or unrun, then why; the pull request is a number, an address "
        "or a branch, by default the current branch's; merge, remove and log nothing",
    )
    instead.add_argument(
        "--range-diff",
        metavar="BEFORE..HEAD",
        help="print 'clean: <why>' when the branch at HEAD has the content it had at BEFORE, "
        "by the range-diff over origin/<--base> that jmerge carries a review over with, else "
        "'changed: <why>'; run it in the checkout that has both; merge, remove and log nothing",
    )
    instead.add_argument(
        "--remake",
        action="store_true",
        help="while a rebase is stopped, name the files to resolve by hand, or make each "
        "generated file again over the base's version, by the command the generated key of "
        "the repo's [[project]] in jbus's config gives it (uv.lock by uv lock where none "
        "does); merge, remove and log nothing",
    )
    instead.add_argument(
        "--gate",
        metavar="HEAD",
        help="run the repo's merge gate in this worktree on HEAD, as a reviewer does, with "
        "BASE and HEAD set and a limit of 9 minutes; print nothing when there is no gate or it "
        "passes, else one finding; exit 1 when the base could not be worked out; merge, "
        "remove and log nothing",
    )
    instead.add_argument(
        "--accept",
        metavar="NUMBER",
        help="lift the hold of this pull request at its current head and merge it: the "
        "user's hand-merge, on --message or on --by and --at, taken as an act of jbus's; with "
        "--check alone, say what it would do",
    )
    top.add_argument(
        "--base",
        metavar="BRANCH",
        default="main",
        help="with --range-diff: the branch both heads sit on (default: main)",
    )
    top.add_argument(
        "--pr",
        metavar="PR",
        default="",
        help="with --gate: the pull request, a number, an address or a branch (default: the "
        "current branch's)",
    )
    top.add_argument(
        "--by", metavar="WHO", help="with --accept: who accepts it, the user jstack's config names"
    )
    top.add_argument(
        "--at", metavar="WHEN", help='with --accept: when it was said, "YYYY-MM-DD HH:MM ZONE"'
    )
    top.add_argument(
        "--message",
        metavar="THREAD/MESSAGE",
        help="with --accept: the user's own message in T3 Code, which jbus reads, in place of "
        "--by and --at",
    )
    top.add_argument(
        "--as",
        dest="as_",
        choices=("home", "user"),
        default="home",
        help="with --accept: the party that accepts, a home (default) or the user, who acts on "
        "a --message alone",
    )
    top.add_argument(
        "--land",
        metavar="STACK",
        help="the stack the user said to land: merge its pull requests as any other, each "
        "once its base is the default branch",
    )
    top.add_argument(
        "--home",
        metavar="ID",
        help="the home that is asking: say what jmerge would do of its own pull requests, as "
        "--check does, and merge nothing, since jbus alone merges",
    )
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.checks is not None:
        print(said_of_checks(args.checks))
        return 0
    if args.range_diff:
        before, _, head = args.range_diff.partition("..")
        found = rangediff.verdict(Path.cwd(), before, head, args.base)
        print(f"{'clean' if found.clean else 'changed'}: {found.why}, by {found.command}")
        return 0
    if args.remake:
        print("\n".join(remake.remake()))
        return 0
    if args.gate is not None:
        found = state_of(Path.cwd())
        if not args.gate:
            raise SystemExit("jmerge: --gate takes the head the review keeps, not nothing")
        if found is None:
            raise SystemExit("jmerge: not in a git repository")
        return merge_gate.review(found, args.gate, args.pr)
    try:
        user = jsettings.load()
    except jsettings.Invalid as error:
        raise SystemExit(f"jmerge: {error}") from None
    if args.accept is None and (args.by or args.at or args.message):
        raise SystemExit("jmerge: --by, --at and --message go with --accept")
    if args.message and (args.by or args.at):
        raise SystemExit("jmerge: --accept takes --message, or --by and --at, and not both")
    if args.accept is not None and not args.accept.isdigit():
        raise SystemExit(f"jmerge: --accept takes a pull request's number, not {args.accept}")
    if args.home:
        args.check = True
    typed = bool(args.by or args.at)
    said = args.accept is not None and not (args.check and not typed and not args.message)
    if said and not args.message and args.by != user.user:
        raise SystemExit(f"jmerge: only {user.user} accepts a hold, not {args.by or 'nobody'}")
    if said and not args.message and not user.takes(args.at or ""):
        raise SystemExit(f'jmerge: --at is "{user.form(args.at or "")}"')
    here = _run(Path.cwd(), "git", "rev-parse", "--path-format=absolute", "--git-common-dir")
    if here.returncode:
        raise SystemExit("jmerge: not in a git repository")
    if not shutil.which("gh"):
        raise SystemExit("jmerge: gh is not installed")
    main_checkout = Path(here.stdout.strip()).parent
    state = homes_state(main_checkout)
    if args.claims:
        return Repo(main_checkout, state, args.home, not args.home, user=user).claimed()
    if args.scope:
        return Repo(main_checkout, state, args.home, not args.home, user=user).scoped(args.scope)

    gate = Gate(main_checkout, state)
    repo = Repo(
        main_checkout,
        state,
        args.home,
        not args.home,
        args.land,
        patterns(PROTECTED),
        patterns(CI_PATHS),
        Merged(main_checkout, state, run=not args.check),
        user=user,
        gate=gate,
    )

    now = datetime.now().astimezone()

    def say(line: str) -> None:
        print(line, flush=True)
        said = lines.one(line)
        held = said and said.word == "hold" and ready.gate_held(said.reason)
        output = (
            "".join(f"  | {one}\n" for one in gate.output.get(said.number, "").splitlines())
            if held
            else ""
        )
        if args.check and output:
            print(output, end="", flush=True)
        if not args.check and state.is_dir():
            waits = str(said.number) if said and said.word in ("wait", "hold") else ""
            kept = lines.logged(line)
            if waits:
                last = jbus.read_dict(state / "merge.log.last")
                if last.get(waits) == kept:
                    return
                last[waits] = kept
            with (state / "merge.log").open("a", encoding="utf-8") as log:
                log.write(f"{now:%Y-%m-%d %H:%M} {kept}\n{output}")
            if waits:
                jbus.write_json(state / "merge.log.last", last)

    if args.sweep:
        return Sweep(repo).run(say, args.check)

    asked = _run(main_checkout, "gh", "pr", "list", "--state", "open", "--json", LIST, *repo.about)
    try:
        listed = [with_browser(repo, one) for one in json.loads(asked.stdout)]
    except (ValueError, KeyError, TypeError, AttributeError):
        listed = None
    default, silent = repo.default() if listed else ("", "")
    if asked.returncode or listed is None:
        silent = _why(main_checkout, asked)
    if silent:
        say(f"wait: could not ask GitHub{silent}")
        return 1
    listed = [ready.unchecked_into(repo.in_full(one), repo.integration) for one in listed]
    repo.open = listed

    if args.accept is not None:
        found = next((one for one in listed if one.number == int(args.accept)), None)
        if found is None:
            say(f"refused {args.accept}: no open pull request has that number")
            return 1
        acting = None
        if said and not args.check:
            try:
                acting = accepts.acting(main_checkout, args.message, args.at, args.as_, user)
            except jbus.Refused as error:
                say(f"refused {args.accept}: {str(error).removeprefix('refused: ')}")
                return 1
            if acting is None and args.message:
                say(f"refused {args.accept}: --message is read by jbus, which has no project here")
                return 1
        by, at = args.by, args.at
        if acting is not None and args.message:
            by, at = user.user, acting.said.said_at
        return repo.accept(found, default, by, at, say, args.check, acting)

    for one in repo.line_up(listed, default):
        found = repo.waits(one, default)
        if one.draft and found.slug and found.why in ready.READY_ON and not args.check:
            found = repo.readied(one, found)
        if found.verb == "hold" and not args.check and not ready.gate_held(found.why):
            repo.hold(one)
        if found.judged is None:
            say(lines.waits(found.verb, one.number, one.url, found.why))
        elif args.check:
            notes = [found.note, found.judged.fresh, found.judged.gate]
            say(lines.ready(one.number, one.head, one.branch, found.slug, notes))
        else:
            say(repo.merge(one, found.slug, found.note, found.judged))
    return 0


MAIN_BROWSER = "{default} browser.yml"
"""The key of `Repo.reds` that keeps main's browser runs, which no branch name can be."""
ROLLUP = "#{number} rollup"
"""The key of `Repo.reds` that keeps a pull request's checks as GitHub lists them."""


def with_browser(repo: Repo, listed: dict) -> ready.PullRequest:
    """The pull request GitHub `listed`, with its checks kept for `browser_red`."""
    repo.reds[ROLLUP.format(number=listed["number"])] = listed.get("statusCheckRollup") or []
    return ready.pull_request(listed, repo.required)


def browser_red(repo: Repo, one: ready.PullRequest, default: str, slug: str) -> str:
    """The wait on a pull request into main for its own browser run: one still going waits as any
    pending run, and one that failed holds it (`rows.browser_red`). It asks GitHub for main's
    browser runs once a run, and only for a pull request whose browser run failed. When GitHub
    gives no answer, main is not known to be red, and the red is the pull request's own. A
    draft's browser run is waived as its failed checks are (`Repo.judged`)."""
    if one.draft:
        return ""
    state = ready.browser(repo.reds.get(ROLLUP.format(number=one.number), []))
    if state == ready.BROWSER_PENDING:
        return ready.NOT_PASSED.format(check=ready.BROWSER)
    if state != ready.BROWSER_FAILED:
        return ""
    key = MAIN_BROWSER.format(default=default)
    if key not in repo.reds:
        asked = subprocess.run(
            [
                "gh",
                "api",
                "repos/{owner}/{repo}/actions/workflows/browser.yml/runs"
                f"?branch={default}&status=completed&per_page=20",
            ],
            cwd=repo.main,
            capture_output=True,
            text=True,
            env={**os.environ, **({"GH_REPO": repo.about[1]} if repo.about else {})},
        )
        try:
            runs = [] if asked.returncode else json.loads(asked.stdout)["workflow_runs"]
        except (ValueError, KeyError, TypeError):
            runs = []
        listed = runs if isinstance(runs, list) else []
        repo.reds[key] = [run for run in listed if isinstance(run, dict)]
    fixing = rows.browser_fixing(repo.main, repo.queue)
    run = rows.main_browser_run(repo.reds[key], default, fixing)
    ran, failed = rows.UNPROVED, ()
    if run is not None and not slug.startswith(rows.BROWSER_FIX):
        failed = repo.run_failed(run.get("id"))
        if failed:
            ran = repo.proved_browser(one, str(run.get("head_sha") or ""))
    return rows.browser_red(one.head, slug, repo.reds[key], default, fixing, ran, failed)


_JOB = re.compile(r"/job/(\d+)")
PASSED = ("SUCCESS", "NEUTRAL", "SKIPPED")


def passed(rollup: list[dict]) -> bool:
    """Whether every check of the head has run and passed, the latest run of each, so every
    part of a check that runs in parts passed."""
    names = {one.get("name") or one.get("context") for one in rollup}
    latest = [run for name in names for run in ready.latest(rollup, name)]
    return bool(latest) and all(
        one.get("conclusion") in PASSED or one.get("state") == "SUCCESS" for one in latest
    )


def checked(rollup: list[dict]) -> list[dict]:
    """The runs in `rollup` of the required check and its parts, as `check 1 of 4` is of
    `check`."""
    return [
        one
        for one in rollup
        if any(
            (one.get("name") or "") == name or (one.get("name") or "").startswith(f"{name} ")
            for name in ready.REQUIRED
        )
    ]


def jobs(rollup: list[dict], ended: tuple[str, ...] = PASSED) -> list[str]:
    """The ids of the jobs of the checks in `rollup` that ended so, from their links."""
    return [
        found[1]
        for one in rollup
        if one.get("conclusion") in ended and (found := _JOB.search(one.get("detailsUrl") or ""))
    ]
