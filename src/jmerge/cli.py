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
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import jsettings
from jbriefs import home as home_rule
from jbriefs import parse
from jbus import mainstate
from jmerge import claims, green, proof, rangediff, ready, rows, sweep
from jmerge.asked import why as asked_why

LIST = (
    "number,url,title,headRefName,headRefOid,baseRefName,mergeable,statusCheckRollup,"
    "files,changedFiles,isDraft"
)
PACKAGE = Path(__file__).parent
PROTECTED = PACKAGE / "protected.txt"
GUARDED = PACKAGE / "guarded.txt"
CI_PATHS = PACKAGE / "ci-paths.txt"
JUDGED_AGAIN_AT_MOST = 2
TIMEOUT_SECONDS = 120


def _run(cwd: Path, *command: str) -> subprocess.CompletedProcess[str]:
    limit = float(os.environ.get("JMERGE_TIMEOUT") or TIMEOUT_SECONDS)
    try:
        return subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=limit)
    except subprocess.TimeoutExpired:
        said = f"timed out after {limit:g} s: {shlex.join(command)}"
        return subprocess.CompletedProcess(command, 124, "", said)


def _text(cwd: Path, *command: str) -> str | None:
    ran = subprocess.run(command, cwd=cwd, capture_output=True)
    return None if ran.returncode else ran.stdout.decode(errors="replace")


def _said(ran: subprocess.CompletedProcess[str]) -> str:
    lines = (ran.stderr or ran.stdout).strip().splitlines()
    return lines[-1].strip() if lines else f"exit {ran.returncode}"


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def patch_id(cwd: Path, base: str, commit: str) -> str | None:
    fork = _run(cwd, "git", "merge-base", f"origin/{base}", commit)
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


def _write_whole(path: Path, text: str) -> None:
    new = path.with_name(f"{path.name}.{os.getpid()}.new")
    new.write_text(text, encoding="utf-8")
    os.replace(new, path)


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


class Behind(str):
    package: Path
    default: str

    def __new__(cls, package: Path, default: str) -> Behind:
        made = super().__new__(
            cls, f"jmerge's own rules are behind {default}'s, and a run that merges pulls them"
        )
        made.package, made.default = package, default
        return made

    def pull(self) -> str:
        pulled = _run(self.package, "git", "pull", "-q", "--ff-only")
        if pulled.returncode:
            return (
                f"jmerge's own rules are behind {self.default}'s and were not pulled "
                f"({_said(pulled)})"
            )
        return f"jmerge pulled {self.default}'s rules; judged on the next run"


def rules_are_mains(package: Path) -> str | Behind:
    if _run(package, "git", "rev-parse", "--show-toplevel").returncode:
        return "jmerge's own rules are not in a git checkout"
    if not _run(package, "git", "ls-files", "--", ".").stdout.strip():
        return "jmerge's own rules are not tracked in a git checkout"
    asked = _run(package, "git", "ls-remote", "--symref", "origin", "HEAD")
    named = re.search(r"^ref: refs/heads/(\S+)\tHEAD$", asked.stdout, re.M)
    if asked.returncode or not named:
        return "the origin of jmerge's own rules could not be asked for its default branch"
    default = named[1]
    if _run(package, "git", "fetch", "-q", "origin").returncode:
        return "the origin of jmerge's own rules could not be fetched"
    status = _run(package, "git", "status", "--porcelain", "--", ".")
    if status.returncode or status.stdout.strip():
        return "jmerge's own rules have a change that is not committed"
    if not _run(package, "git", "diff", "--quiet", f"origin/{default}", "--", ".").returncode:
        return ""
    on = _run(package, "git", "symbolic-ref", "-q", "--short", "HEAD").stdout.strip()
    behind = not _run(
        package, "git", "merge-base", "--is-ancestor", "HEAD", f"origin/{default}"
    ).returncode
    if on != default or not behind:
        at = f"not behind origin/{default}" if on == default else f"on {on or 'no branch'}"
        return f"jmerge's own rules are not {default}'s: their checkout is {at}"
    return Behind(package, default)


class Checked(NamedTuple):
    short: str
    note: str


class Fresh:
    TIMEOUT = 15 * 60
    ASK_TIMEOUT = 10
    AUTHOR = {
        "GIT_AUTHOR_NAME": "jmerge",
        "GIT_AUTHOR_EMAIL": "jmerge@localhost",
        "GIT_COMMITTER_NAME": "jmerge",
        "GIT_COMMITTER_EMAIL": "jmerge@localhost",
    }
    CHECK = "import sys; from jmerge.cli import Fresh; raise SystemExit(Fresh.alone(sys.argv[1:]))"
    SELECTOR = "scripts/select_tests.py"
    APART = (
        "import json, sys; sys.path.insert(0, sys.argv[1]); import select_tests as s; "
        "ours, _ = s.selection(json.loads(sys.argv[2])); "
        "theirs, _ = s.selection(json.loads(sys.argv[3])); "
        "both = set(ours) & set(theirs); "
        "print('apart' if 'all' not in ours + theirs and not both else 'meet')"
    )
    UNIT_OWN = {"INVOCATION_ID", "JOURNAL_STREAM", "SYSTEMD_EXEC_PID", "MANAGERPID"}

    def __init__(self, main: Path, state: Path, run: bool = True, timeout: float = TIMEOUT):
        self.main = main
        self.state = state
        self.run = run
        self.timeout = timeout
        self.command = ready.fresh_command(_read(state / "fresh-check"))
        self.ran = False

    def known(self) -> dict:
        try:
            known = json.loads(_read(self.state / "fresh.json") or "{}")
        except ValueError:
            return {}
        return known if isinstance(known, dict) else {}

    def of(self, number: int, head: str, tip: str, files: tuple[str, ...] | None) -> Checked | None:
        was = self.known().get(str(number))
        asked = {"head": head, "main": tip, "command": self.command}
        recorded = isinstance(was, dict) and {key: was.get(key) for key in asked} == asked
        if recorded and was.get("result") != ready.TIMED_OUT:
            return self._said(str(was.get("result")), head, tip, was)
        if isinstance(was, dict) and self.stands(number, was, head, tip, files):
            return Checked("", ready.fresh_kept(self.command, head, str(was["main"]), tip))
        if not self.run:
            return Checked(ready.FRESH_QUEUED, "") if recorded else None
        merged = _run(self.main, "git", "merge-tree", "--write-tree", tip, head)
        if merged.returncode == 1:
            return Checked(ready.FRESH_CONFLICT, "")
        if merged.returncode:
            return Checked(self._not_run(merged), "")
        tree = _first_word(merged.stdout)
        found = self.marked(tree)
        if found:
            record = {**asked, "result": ready.PASSED, "tree": tree, "marker": found.at}
            now = datetime.now().astimezone()
            self._keep(number, {**record, "at": f"{now:%Y-%m-%dT%H:%M:%S%z}"})
            return self._said(ready.PASSED, head, tip, record)
        if self.ran or self._held():
            return Checked(ready.FRESH_QUEUED, "")
        self.ran = True
        started = self.start(number, head, tip, tree)
        return Checked(started or ready.FRESH_QUEUED, "")

    def stands(
        self, number: int, was: dict, head: str, tip: str, files: tuple[str, ...] | None
    ) -> bool:
        older = str(was.get("main") or "")
        mine = (was.get("result"), was.get("head"), was.get("command"))
        if (
            not files
            or not older
            or was.get("marker")
            or mine != (ready.PASSED, head, self.command)
        ):
            return False
        changed = _text(self.main, "git", "diff", "--name-only", "--no-renames", older, tip)
        merged = _run(self.main, "git", "merge-tree", "--write-tree", tip, head)
        commit = None if merged.returncode else self._commit(_first_word(merged.stdout), head, tip)
        if changed is None or commit is None or commit.returncode:
            return False
        at = self.state / "fresh" / f"{number}.select"
        _run(self.main, "git", "worktree", "remove", "--force", str(at))
        shutil.rmtree(at, ignore_errors=True)
        try:
            added = _run(
                self.main,
                "git",
                "worktree",
                "add",
                "-q",
                "--detach",
                str(at),
                commit.stdout.strip(),
            )
            if added.returncode or not (at / self.SELECTOR).is_file():
                return False
            scripts = str((at / self.SELECTOR).parent)
            theirs = json.dumps(changed.splitlines())
            said = _run(at, sys.executable, "-c", self.APART, scripts, json.dumps(files), theirs)
            return not said.returncode and said.stdout.strip() == "apart"
        finally:
            _run(self.main, "git", "worktree", "remove", "--force", str(at))

    def _commit(self, tree: str, head: str, tip: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "commit-tree", tree, "-p", tip, "-p", head]
            + ["-m", f"jmerge: {head} over {tip}"],
            cwd=self.main,
            capture_output=True,
            text=True,
            env={**os.environ, **self.AUTHOR},
        )

    def marked(self, tree: str) -> green.Marker | None:

        def ask(path: str) -> object:
            answer = subprocess.run(
                ["gh", "api", f"repos/{{owner}}/{{repo}}/{path}"],
                cwd=self.main,
                capture_output=True,
                text=True,
                timeout=self.ASK_TIMEOUT,
            )
            if answer.returncode:
                raise RuntimeError(_said(answer))
            return json.loads(answer.stdout)

        try:
            return green.marker(ask, tree)[0]
        except (OSError, subprocess.SubprocessError, RuntimeError, ValueError, LookupError):
            return None

    def _held(self) -> bool:
        with (self.state / "fresh.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
        return False

    def start(self, number: int, head: str, tip: str, tree: str) -> str:
        arguments = [str(self.main), str(self.state), str(number), head, tip, tree]
        arguments += [self.command, f"{self.timeout:g}"]
        check = [sys.executable, "-c", self.CHECK, *arguments]
        unit = re.sub(r"[^A-Za-z0-9_-]", "-", f"jmerge-fresh-{self.state.name}-{number}")
        names = sorted(set(os.environ) - self.UNIT_OWN)
        launch = ["systemd-run", "--user", "--quiet", "--collect", f"--unit={unit}"]
        launch += [f"--setenv={name}" for name in names] + ["--", *check]
        if shutil.which("systemd-run"):
            started = _run(self.main, *launch)
            if not started.returncode:
                return ""
            if "INVOCATION_ID" in os.environ:
                return self._not_run(started)
        try:
            subprocess.Popen(
                check,
                cwd=self.main,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            return f"a fresh check could not be run ({error})"
        return ""

    @classmethod
    def alone(cls, arguments: list[str]) -> int:
        main, state, number, head, tip, tree, command, timeout = arguments
        fresh = cls(Path(main), Path(state), timeout=float(timeout))
        fresh.command = command
        with (fresh.state / "fresh.lock").open("w") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return 0
            result, commit = fresh.check(int(number), head, tip, tree, lock.fileno())
            now = datetime.now().astimezone()
            record = {"head": head, "main": tip, "command": command, "result": result}
            record["at"] = f"{now:%Y-%m-%dT%H:%M:%S%z}"
            fresh._keep(int(number), record)
            unmarked = fresh.mark(commit) if result == ready.PASSED else ""
            if unmarked:
                fresh._keep(int(number), {**record, "unmarked": unmarked})
        return 0

    def _keep(self, number: int, record: dict) -> None:
        known = {**self.known(), str(number): record}
        _write_whole(self.state / "fresh.json", json.dumps(known, indent=2) + "\n")

    def _said(self, result: str, head: str, tip: str, was: dict) -> Checked:
        if result == ready.PASSED and was.get("marker"):
            tree, marker = str(was.get("tree")), str(was["marker"])
            return Checked("", ready.fresh_skipped(tree, marker, head, tip))
        if result == ready.PASSED:
            unmarked = str(was.get("unmarked") or "")
            more = f", its tree is not marked ({unmarked})" if unmarked else ""
            return Checked("", ready.fresh_note(self.command, head, tip) + more)
        if result != ready.FAILED:
            return Checked(result, "")
        return Checked(ready.short_on_fresh(result, self.command, head, tip), "")

    def mark(self, commit: str) -> str:
        tree = _run(self.main, "git", "rev-parse", "--verify", "-q", f"{commit}^{{tree}}")
        if tree.returncode:
            return _said(tree)
        ref = sweep.marker(tree.stdout.strip())
        pushed = _run(self.main, "git", "push", "-q", "origin", f"+{commit}:{ref}")
        if not pushed.returncode:
            return ""
        refused = re.search(r"^ ! .*\((.+)\)$", pushed.stderr, re.M)
        return refused[1] if refused else _said(pushed)

    @staticmethod
    def _not_run(ran: subprocess.CompletedProcess[str]) -> str:
        return f"a fresh check could not be run ({_said(ran)})"

    def check(self, number: int, head: str, tip: str, tree: str, lock: int) -> tuple[str, str]:
        commit = self._commit(tree, head, tip)
        if commit.returncode:
            return self._not_run(commit), ""
        made = commit.stdout.strip()
        at = self.state / "fresh" / str(number)
        _run(self.main, "git", "worktree", "remove", "--force", str(at))
        shutil.rmtree(at, ignore_errors=True)
        added = _run(self.main, "git", "worktree", "add", "-q", "--detach", str(at), made)
        if added.returncode:
            return self._not_run(added), ""
        env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
        try:
            with at.with_name(f"{number}.log").open("wb") as log:
                ran = subprocess.Popen(
                    self.command,
                    shell=True,
                    cwd=at,
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    pass_fds=(lock,),
                    start_new_session=True,
                )
                try:
                    return (ready.FAILED if ran.wait(self.timeout) else ready.PASSED), made
                except subprocess.TimeoutExpired:
                    os.killpg(ran.pid, signal.SIGKILL)
                    ran.wait()
                    return ready.TIMED_OUT, made
        finally:
            _run(self.main, "git", "worktree", "remove", "--force", str(at))


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
        guarded: tuple[str, ...] = (),
        ci: tuple[str, ...] = (),
        rules: Callable[[], str] = lambda: "",
        own: bool = False,
        fresh: Fresh | None = None,
        *,
        user: jsettings.Settings,
    ) -> None:
        self.user = user
        self.main = main
        self.state = state
        self.every = every
        self.land = land or None
        self.protected = protected
        self.guarded = guarded
        self.ci = ci
        self.fresh = fresh
        self.rules = rules
        self.own = own
        self.unruly: str | None = None
        self.accepted: tuple[int, str] | None = None
        self.lifts: list[str] = []
        self.carried: dict[int, str] = {}
        self.fetched = False
        self.through: int | None = None
        self.order: list[int] = []
        self.rebasing: set[int] = set()
        self.numbers_on: set[int] | None = None
        origin = _run(main, "git", "remote", "get-url", "origin")
        self.about = [] if origin.returncode else ["--repo", origin.stdout.strip()]
        self.listed, self.was = home_rule.ids(state)
        self.mine = home or self.listed

    @functools.cached_property
    def queue(self) -> list[dict] | None:
        return rows.read(self.main)

    @functools.cached_property
    def main_state(self) -> mainstate.Main:
        return rows.main(self.main)

    @functools.cached_property
    def migrations(self) -> rows.Migrations | None:
        return rows.migrations(self.main)

    def numbers(self, default: str) -> set[int] | None:
        if self.numbers_on is None and self.migrations:
            where = f"origin/{default}"
            listed = None
            if not _run(self.main, "git", "fetch", "-q", "origin", default).returncode:
                tree = f"{self.migrations.directory}/"
                listed = _run(self.main, "git", "ls-tree", "-z", "--name-only", where, "--", tree)
            if listed is None or listed.returncode:
                return None
            names = (Path(path).name for path in listed.stdout.split("\0") if path)
            self.numbers_on = {int(d) for name in names if (d := ready.migration_number(name))}
        return self.numbers_on

    def line_up(self, listed: list[ready.PullRequest], default: str) -> list[ready.PullRequest]:
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

    def others(self, text: str) -> bool:
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
            "number,url",
            *self.about,
        )
        try:
            open_pulls = {str(one["url"]): int(one["number"]) for one in json.loads(asked.stdout)}
        except (ValueError, KeyError, TypeError):
            open_pulls = None
        if asked.returncode or open_pulls is None:
            print(f"wait: could not ask GitHub{asked_why(asked)}", flush=True)
            return 1
        homes = self.homes.known
        for brief in sorted((self.state / "tasks").glob("*.md")):
            claim = claims.of_brief(brief.stem, _read(brief), open_pulls, homes)
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
            return "", asked_why(asked)
        branch = asked.stdout.strip()
        return branch, "" if branch else asked_why(asked, "it named no default branch")

    def based_on(self, branch: str) -> str:
        """GitHub retargets an open pull request based on a branch deleted after its own pull
        request merged, so deleting it would change a stack's order:
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
            return f"could not ask GitHub whether a pull request is based on it{asked_why(asked)}"
        if not numbers:
            return ""
        several = "s" if len(numbers) > 1 else ""
        verb = "are" if several else "is"
        return f"the open pull request{several} {' '.join(map(str, numbers))} {verb} based on it"

    def left(self, one: ready.PullRequest) -> tuple[str, ...] | None:
        """`gh pr list` lists a rename under its new path alone, and only the files endpoint
        gives the path it left, as `previous_filename`:
        https://docs.github.com/en/rest/pulls/pulls#list-pull-requests-files
        """
        if not one.renamed:
            return ()
        asked = subprocess.run(
            [
                "gh",
                "api",
                "--paginate",
                f"repos/{{owner}}/{{repo}}/pulls/{one.number}/files",
                "--jq",
                ".[] | .previous_filename // empty",
            ],
            cwd=self.main,
            capture_output=True,
            text=True,
            env={**os.environ, **({"GH_REPO": self.about[1]} if self.about else {})},
        )
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

    def range_diff(self, reviewed: str, head: str, default: str) -> rangediff.Verdict:
        if not self.fetched:
            self.fetched = True
            _run(self.main, "git", "fetch", "-q", "origin")
        return rangediff.verdict(self.main, reviewed, head, default)

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
        files = None if left is None or one.changed > len(one.files) else (*one.files, *left)
        left = left or ()
        moved = self.moved(one.base, one.started)
        if moved is None:
            return f"{one.base} could not be fetched to see what changed after its check", "", ""
        tip, paths = moved
        stale = ready.stale_paths(one.files, left, paths, self.ci) or self.related(
            one, left, tip, paths
        )
        if not stale:
            return "", tip, ""
        path = ready.guarded_path(one, self.guarded, left)
        if path:
            short = ready.short_on_main(stale, one.started, one.base, "a rebase", user=self.user)
            return f"guarded (touches {path}), {short}", "", ""
        asks = self.fresh is not None and self.fresh.command
        found = self.fresh.of(one.number, one.head, tip, files) if asks else None
        if found is None:
            return ready.short_on_main(stale, one.started, one.base, user=self.user), "", ""
        return found.short, "" if found.short else tip, found.note

    def related(
        self, one: ready.PullRequest, left: tuple[str, ...], tip: str, paths: tuple[str, ...]
    ) -> tuple[str, ...]:
        ours = {
            path: _text(self.main, "git", "show", f"{one.head}:{path}") or "" for path in one.files
        }
        ours |= {path: "" for path in left if path not in ours}
        theirs = {
            path: _text(self.main, "git", "show", f"{tip}:{path}") or ""
            for path in paths
            if path not in ours
        }
        return ready.callers_and_dependencies(ours, theirs)

    def short_of_guarded(
        self, one: ready.PullRequest, text: str, rebase: ready.Rebase | None, note: str
    ) -> str:
        if self.unruly is None:
            self.unruly = self.rules()
        short = self.unruly or ready.short_of_guarded(one, text, rebase, note)
        return short or proof.short(text, self.proven_at(one))

    def proven_at(self, one: ready.PullRequest) -> str:
        return self.carried.get(one.number) or one.head

    def waits(self, one: ready.PullRequest, default: str) -> Judgement:
        found = self.judge(one, default)
        if one.number in self.order and found.verb == "wait" and ready.being_rebased(found.why):
            self.rebasing.add(one.number)
        else:
            self.rebasing.discard(one.number)
        return found

    def judge(self, one: ready.PullRequest, default: str) -> Judgement:
        brief = ready.brief_of(one.url, self.state / "tasks")
        self.carried.pop(one.number, None)
        if one.draft:
            return Judgement(brief.stem if brief else "", "wait", ready.DRAFT, "", None)
        if brief is None:
            return Judgement("", "wait", ready.NO_BRIEF, "", None)
        text = _read(brief)
        if self.others(text) and not self.every:
            return Judgement(brief.stem, "wait", ready.OTHER_HOME, "", None)
        short = ready.held(one, default, ready.stack_of(text), self.land)
        short = short or ready.rebase_held(text, one.head) or ready.short_of(text, one.head)
        rebase = ready.rebase_of(text, one.head)
        covered = ready.to_range_diff(rebase, text, one.head)
        lost: tuple[ready.Drop, ...] = ()
        if not short:
            patches = [patch_id(self.main, one.base, each) for each in ready.to_compare(rebase)]
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
        short = short or ready.short_on_github(one)
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
        if reviewed == "":
            short = ready.NO_HEAD
        elif reviewed:
            verdict = self.range_diff(reviewed, one.head, one.base)
            short = ready.short_on_content(verdict)
            if not short:
                self.carried[one.number] = reviewed
            note = ready.rebase_note(verdict) if rebase is None or rebase.did == "changed" else ""
        if short:
            return Judgement(brief.stem, "wait", short, note, None)
        short = (
            rows.short(self.queue, brief.stem)
            or rows.red(self.main_state, brief.stem)
            or self.short_on_migrations(one, default)
        )
        if short:
            return Judgement(brief.stem, "wait", short, note, None)
        left = self.left(one)
        lifted = self.accepted == (one.number, one.head)
        kind, why = ready.drops(lost, text, one.head, user=self.user)
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
        short, tip, fresh = self.stale(one, left)
        if short:
            return Judgement(brief.stem, "wait", short, note, None)
        note = f"{note}, {ready.KEPT}" if note else ""
        left = left or ()
        path = ready.guarded_path(one, self.guarded, left)
        if path:
            short = self.short_of_guarded(one, text, rebase, note)
            if short:
                return Judgement(
                    brief.stem, "wait", f"guarded (touches {path}), {short}", note, None
                )
        if (self.state / "merge-off").exists():
            return Judgement(brief.stem, "wait", ready.MERGE_OFF, note, None)
        rules = bool(path) and ready.changes_the_rules(one, left)
        if one.number in self.order:
            self.through = one.number
        return Judgement(brief.stem, "", "", note, ready.Judged(path, tip, rules, fresh))

    def holds(self) -> dict[str, str]:
        try:
            holds = json.loads(_read(self.state / "holds.json") or "{}")
        except ValueError:
            return {}
        return holds if isinstance(holds, dict) else {}

    def hold(self, one: ready.PullRequest) -> None:
        self.holds_are({**self.holds(), str(one.number): one.head})

    def holds_are(self, holds: dict[str, str]) -> None:
        if holds != self.holds() and self.state.is_dir():
            _write_whole(self.state / "holds.json", json.dumps(holds) + "\n")

    def accept(
        self,
        one: ready.PullRequest,
        default: str,
        by: str | None,
        when: str | None,
        say: Callable[[str], None],
        check: bool,
    ) -> int:
        about = f"{one.number} {one.url}"
        first = self.waits(one, default)
        if first.verb != "hold":
            state = f"it waits: {first.why}" if first.verb else "jmerge merges it by itself"
            say(f"refused {about}: it is not held, {state}")
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
            say(f"{found.verb} {about}: {found.why}")
            return 1
        why = " and ".join(self.lifts) or first.why
        if check:
            ready_line = f"ready {one.number} {one.head} {one.branch} {found.slug}"
            say(f"{ready_line}, accepted: {why}, {safe}")
            return 0
        say(f"accepted {about}: {why}, lifted at {one.head[:12]} by {by} at {when}, {safe}")
        said = self.merge(one, found.slug, found.note, found.judged)
        say(said)
        if not said.startswith("merged "):
            return 1
        self.holds_are({n: head for n, head in self.holds().items() if n != str(one.number)})
        return 0

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
                return f"{tree} could not be removed, and both branches are left ({_said(ran)})"
        ran = _run(self.main, "git", "branch", "-q", "-D", branch)
        if ran.returncode:
            return f"the local and remote branch {branch}, the worktree is removed ({_said(ran)})"
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
        return f"{gone} ({'it is not at the merged head on the origin' if stale else _said(ran)})"

    def merge(
        self,
        one: ready.PullRequest,
        slug: str,
        rebase: str = "",
        judged: ready.Judged | None = None,
    ) -> str:
        number = str(one.number)
        judged = judged or ready.Judged()
        if self.own and self.unruly is None:
            self.unruly = self.rules()
        again = 0
        while judged.tip:
            at = _run(self.main, "git", "ls-remote", "origin", f"refs/heads/{one.base}")
            if not at.returncode and _first_word(at.stdout) == judged.tip:
                break
            if again == JUDGED_AGAIN_AT_MOST:
                guarded = f"guarded (touches {judged.path}), " if judged.path else ""
                return f"wait {number} {one.url}: {guarded}{ready.MAIN_MOVED}"
            again += 1
            self.numbers_on = None
            again_judged = self.waits(one, one.base)
            if again_judged.judged is None:
                return f"{again_judged.verb} {number} {one.url}: {again_judged.why}"
            rebase, judged = again_judged.note, again_judged.judged
        ran = _run(
            self.main,
            "gh",
            "pr",
            "merge",
            number,
            "--squash",
            "--match-head-commit",
            one.head,
            *self.about,
        )
        if ran.returncode:
            return f"wait {number} {one.url}: {ready.MERGE_FAILED}: {_said(ran)}"
        if judged.rules:
            self.unruly = ready.RULES_CHANGED
        notes = [rebase] if rebase else []
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
        pulled = _run(self.main, "git", "pull", "--ff-only")
        self.numbers_on = None
        if pulled.returncode:
            notes.append(f"not pulled: {_said(pulled)}")
        kept = self.clear_up(one.branch, one.head)
        if kept:
            notes.append(f"kept: {kept}")
        if judged.path:
            notes.append(f"guarded: {judged.path}")
        if judged.fresh:
            notes.append(judged.fresh)
        notes.append(f"revert: gh pr revert {shlex.quote(one.url)}")
        return ", ".join([f'merged {number} {slug} {commit} "{one.title}"', *notes])


PROC = Path("/proc")


def _running(tree: str) -> int | None:
    try:
        listed = [PROC / name for name in os.listdir(PROC) if name.isdigit()]
    except OSError:
        return None
    if PROC / str(os.getpid()) not in listed:
        return None
    inside = os.path.realpath(tree)
    found = []
    for entry in listed:
        try:
            at = os.readlink(entry / "cwd")
        except OSError:
            continue
        if at == inside or at.startswith(f"{inside}/"):
            found.append(int(entry.name))
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
        deleted, so a merged head no longer here is fetched from there:
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
                if state == "MERGED" and said["baseRefName"] == self.default:
                    head = str(said["headRefOid"])
            except (ValueError, KeyError, TypeError):
                state = ""
            if not state:
                silent = asked_why(asked)
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
                return gone, what, _said(ran)
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
            label = f"green-tree/{ref.removeprefix(sweep.MARKERS)[:12]}"
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
                kept.append((label, f"its marker could not be removed ({_said(ran)})"))
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


def parser() -> argparse.ArgumentParser:
    top = argparse.ArgumentParser(
        prog="jmerge",
        description="Merge this repo's pull requests that are reviewed, fixed and green, pull "
        "the main checkout, and remove each one's worktree and branches. Prints one line per "
        "open pull request. A pull request based on another "
        "branch is never merged, and one whose brief has a Stack: line only with --land. "
        "A draft is never merged, with any flag. "
        "One whose check started before main changed one of its paths, a CI path "
        "(src/jmerge/ci-paths.txt), or a caller of its files or something they depend on "
        "waits for a fresh check: where the repo's state has a "
        "fresh-check file, its command is run once a run on the head merged over today's "
        "main, and a pass stands in. One whose rebase dropped a line waits for its crew to say "
        "why and for the scoped review to uphold it, and is printed as hold when it does not. "
        "One that changes a protected path (src/jmerge/protected.txt) is never merged and is "
        "printed as hold. One that changes a guarded path (src/jmerge/guarded.txt) is merged "
        "only when its check has a start time, its review is finished at the head, main has "
        "changed none of its paths or a CI path since, and jmerge's own rules are main's; "
        "otherwise it is printed as wait, guarded (touches <path>). "
        "A merge-off file in the repo's state merges nothing. "
        "With --sweep it merges nothing: it "
        "removes the worktree and the branches of each finished thread whose "
        "work is all merged or pushed, and prints what it removed and what it kept. With "
        "--claims it changes nothing: it prints one line per brief that still holds files, "
        "with its state, its home and its Where line. With --accept it lifts the hold of one "
        "pull request, at the head the hold was said at, when a review proved its one safety "
        "fact at that head, and merges it as any other.",
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
        "--accept",
        metavar="NUMBER",
        help="lift the hold of this pull request at its current head and merge it: the "
        "user's hand-merge, with --by and --at; with --check alone, say what it would do",
    )
    top.add_argument(
        "--by", metavar="WHO", help="with --accept: who accepts it, the user jstack's config names"
    )
    top.add_argument(
        "--at", metavar="WHEN", help='with --accept: when it was said, "YYYY-MM-DD HH:MM ZONE"'
    )
    top.add_argument(
        "--all", action="store_true", help="merge the pull requests of this repo's other homes too"
    )
    top.add_argument(
        "--land",
        metavar="STACK",
        help="the stack the user said to land: merge its pull requests as any other, each "
        "once its base is the default branch",
    )
    top.add_argument(
        "--home", metavar="ID", help="the home that is asking (default: the id in home-id)"
    )
    return top


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        user = jsettings.load()
    except jsettings.Invalid as error:
        raise SystemExit(f"jmerge: {error}") from None
    if args.accept is None and (args.by or args.at):
        raise SystemExit("jmerge: --by and --at go with --accept")
    if args.accept is not None and not args.accept.isdigit():
        raise SystemExit(f"jmerge: --accept takes a pull request's number, not {args.accept}")
    said = args.accept is not None and not (args.check and not args.by and not args.at)
    if said and args.by != user.user:
        raise SystemExit(f"jmerge: only {user.user} accepts a hold, not {args.by or 'nobody'}")
    if said and not user.takes(args.at or ""):
        raise SystemExit(f'jmerge: --at is "{user.form(args.at or "")}"')
    here = _run(Path.cwd(), "git", "rev-parse", "--path-format=absolute", "--git-common-dir")
    if here.returncode:
        raise SystemExit("jmerge: not in a git repository")
    if not shutil.which("gh"):
        raise SystemExit("jmerge: gh is not installed")
    main_checkout = Path(here.stdout.strip()).parent
    state = Path.home() / ".local" / "state" / "home" / main_checkout.name
    if args.claims:
        return Repo(main_checkout, state, args.home, args.all, user=user).claimed()
    if args.scope:
        return Repo(main_checkout, state, args.home, args.all, user=user).scoped(args.scope)

    def rules() -> str:
        found = rules_are_mains(PACKAGE)
        return found.pull() if isinstance(found, Behind) and not args.check else found

    repo = Repo(
        main_checkout,
        state,
        args.home,
        args.all,
        args.land,
        patterns(PROTECTED),
        patterns(GUARDED),
        patterns(CI_PATHS),
        rules,
        PACKAGE.resolve().is_relative_to(main_checkout.resolve()),
        Fresh(main_checkout, state, run=not args.check),
        user=user,
    )

    now = datetime.now().astimezone()

    def say(line: str) -> None:
        print(line, flush=True)
        if not args.check and state.is_dir():
            waits = re.match(r"(?:wait|hold) (\d+) ", line)
            if waits:
                try:
                    last = json.loads((state / "merge.log.last").read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    last = {}
                if not isinstance(last, dict):
                    last = {}
                if last.get(waits[1]) == line:
                    return
                last[waits[1]] = line
            with (state / "merge.log").open("a", encoding="utf-8") as log:
                log.write(f"{now:%Y-%m-%d %H:%M} {line}\n")
            if waits:
                (state / "merge.log.last").write_text(json.dumps(last), encoding="utf-8")

    if args.sweep:
        return Sweep(repo).run(say, args.check)

    asked = _run(main_checkout, "gh", "pr", "list", "--state", "open", "--json", LIST, *repo.about)
    try:
        listed = [ready.pull_request(one) for one in json.loads(asked.stdout)]
    except (ValueError, KeyError, TypeError, AttributeError):
        listed = None
    default, silent = repo.default() if listed else ("", "")
    if asked.returncode or listed is None:
        silent = asked_why(asked)
    if silent:
        say(f"wait: could not ask GitHub{silent}")
        return 1

    if args.accept is not None:
        found = next((one for one in listed if one.number == int(args.accept)), None)
        if found is None:
            say(f"refused {args.accept}: no open pull request has that number")
            return 1
        return repo.accept(found, default, args.by, args.at, say, args.check)

    for one in repo.line_up(listed, default):
        found = repo.waits(one, default)
        if found.verb == "hold" and not args.check:
            repo.hold(one)
        if found.judged is None:
            say(f"{found.verb} {one.number} {one.url}: {found.why}")
        elif args.check:
            ready_line = f"ready {one.number} {one.head} {one.branch} {found.slug}"
            guarded = f"guarded: {found.judged.path}" if found.judged.path else ""
            say(", ".join(filter(None, [ready_line, found.note, guarded, found.judged.fresh])))
        else:
            say(repo.merge(one, found.slug, found.note, found.judged))
    return 0
