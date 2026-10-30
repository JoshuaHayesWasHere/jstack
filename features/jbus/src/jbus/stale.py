"""`jbus stale --project <p>`: list the state of a project that nothing will act on again. It
deletes nothing, and writes nothing but its count.

It lists five kinds, a line each, `<kind> <what>: <why>`:

- `brief`: a brief of the home's `tasks/` whose row is removed, or merged or done with nothing it
  waits on (`queue.over`), or whose pull request is merged or closed, and whose last Result does not
  say `Status: done` with `Left: none`. The pull request is the one its last Result's `Branch:` line
  ends on, or else its row's. It is merged or closed when GitHub's list of open pull requests does
  not have it. A brief whose leftover jbus still holds (`jbus.leftover`) is not listed: its home or
  its crewmate is at it.
- `worktree`: a worktree of the project's checkout, other than the checkout itself, whose branch is
  no open row's slug or branch and no open pull request's head. An open row is one that is not
  removed, merged or done. A worktree on a detached head is on no branch, such as a build's source
  tree, so no row or pull request can be its, and it is not listed.
- `hold`: a key of the home's `holds.json`, where `jmerge` keeps the heads it holds, whose pull
  request is not open.
- `told`: a line of a home's `told` whose decision or stop has ended: a `question <n>` that has its
  answer, a `local <slug>` whose row is removed, merged or done, and a `jbus` one whose words are
  on no item of the one list as the last pass found it open (`jbus.told.opened`). Its words are
  compared with each commit, time and number left out, as a stall's minutes grow.
- `home-id`: a `home-id`, the root home's or a scope's, that names a thread T3 Code no longer has.

A kind whose source gave no answer, GitHub's open pull requests or T3 Code's threads, is not
judged where it needs that answer, and a `not judged:` line says so: nothing is called stale on a
guess. The last line counts each kind.

Once an hour a pass runs the same audit and keeps its count in `stale.json` of the project's state
(`audit`). A count above none is an item of the one list (`jbus.wakes`), so the root home hears
it, and hears it again each time the count changes. While the root's own `home-id` is stale there
is no home to hear it (`gone`), and the next home's start writes a new one.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jbus
from jbriefs import below
from jbriefs.home import ids, scopes
from jbus import leftover, passes, questions, queue, read_json, verbs, write_json
from jbus.passes import Pass
from jbus.t3 import GONE, Client, T3Error, T3Refused
from jbus.told import FILE as WAKES
from jbus.told import opened
from jbus.view.state import MOMENT
from jbus.watch import last_result, named, pulls
from jmerge.asked import Silent

if TYPE_CHECKING:
    from jbus.poll import Half

NAME = "stale.json"
KEY = "stale"
HOUR = 60 * 60
KINDS = ("brief", "worktree", "hold", "told", "home-id")
HOLDS = "holds.json"
TOLD = "told"
FIELDS = "number,url,headRefName"
LIMIT = "1000"
CUT = 100
LINE = (
    "jbus stale: {count} stale in {project} ({kinds}): `jbus stale --project {project}` lists "
    "each, and deletes nothing"
)
NO_GITHUB = "GitHub did not list the open pull requests{why}"
_TOLD = re.compile(r"^(?:decision|stop) (?:question (\d+)|local ([^ :]+)|jbus): (.+)$")
_WORDS = re.compile(f"{MOMENT.pattern}|\\d+")


@dataclass(frozen=True)
class Stale:
    """One stale thing: its kind, out of `KINDS`, what it is, and why it is stale."""

    kind: str
    what: str
    why: str

    def line(self) -> str:
        return f"{self.kind} {self.what}: {self.why}"


@dataclass
class Found:
    """What one audit found: each stale thing, and each source that gave no answer, worded."""

    stale: list[Stale] = field(default_factory=list)
    unjudged: list[str] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {kind: sum(one.kind == kind for one in self.stale) for kind in KINDS}

    def summary(self) -> str:
        return ", ".join(f"{kind} {count}" for kind, count in self.counts().items())


def _cut(text: str) -> str:
    return text if len(text) <= CUT else text[: CUT - 3] + "..."


def _clean(result: str) -> bool:
    """Whether a Result says `Status: done` with `Left: none`."""
    said = (below.line(result, label).rstrip(".") for label in ("Status:", "Left:"))
    return tuple(said) == ("done", "none")


def _says(result: str) -> str:
    if not result:
        return "it has no Result"
    status, left = below.line(result, "Status:"), below.line(result, "Left:")
    return _cut(f"its last Result says Status: {status or '(none)'}, Left: {left or '(none)'}")


def briefs(
    home: Path,
    rows: list[queue.Row],
    removed: set[str],
    open_: set[int] | None,
    held: set[str] = frozenset(),
) -> Found:
    """Each brief whose row or pull request ended with its last Result not clean, less those
    whose leftover jbus `held`."""
    found, status = Found(), {row["slug"]: row.get("status") for row in rows}
    over = {row["slug"] for row in rows if queue.over(row)}
    pull = {row["slug"]: str(row.get("pr") or "").lstrip("#") for row in rows}
    unjudged = False
    for path in sorted((home / "tasks").glob("*.md")):
        slug = path.stem
        try:
            result = last_result(path.read_text(errors="replace"))
        except OSError:
            continue
        if _clean(result) or slug in held:
            continue
        why = ""
        if slug in removed:
            why = "its row is removed"
        elif slug in over:
            why = f"its row is {status[slug]}"
        elif status.get(slug) not in queue.FINAL:
            number = named(result)[1] or pull.get(slug, "")
            if number.isdigit() and open_ is None:
                unjudged = True
            elif number.isdigit() and int(number) not in open_:
                why = f"its pull request #{number} is merged or closed"
        if why:
            found.stale.append(Stale("brief", slug, f"{why}, and {_says(result)}"))
    if unjudged:
        found.unjudged.append("brief: a pull request a brief names, open or not")
    return found


def _worktrees(listed: str) -> list[tuple[str, str]]:
    """Each worktree of `git worktree list --porcelain` but the first, the checkout itself, with
    its branch. A worktree on a detached head has none, and is left out."""
    found = []
    for block in listed.strip().split("\n\n")[1:]:
        lines = dict(line.partition(" ")[::2] for line in block.splitlines())
        if "worktree" in lines and lines.get("branch"):
            found.append((lines["worktree"], lines["branch"].removeprefix("refs/heads/")))
    return found


def worktrees(run: Pass, rows: list[queue.Row], pulled: list[dict[str, Any]] | None) -> Found:
    """Each worktree whose branch no open row and no open pull request has."""
    found = Found()
    listed = run.run("git", "worktree", "list", "--porcelain")
    if listed.returncode:
        found.unjudged.append(f"worktree: git worktree list failed ({_cut(listed.stderr.strip())})")
        return found
    if pulled is None:
        found.unjudged.append("worktree: whether a pull request is open on its branch")
        return found
    live = [row for row in rows if row.get("status") not in queue.FINAL]
    names = {row["slug"] for row in live} | {row["branch"] for row in live if row.get("branch")}
    names |= {pull.get("headRefName", "") for pull in pulled}
    for path, branch in _worktrees(listed.stdout):
        if branch not in names:
            why = f"branch {branch}, of no open row and no open pull request"
            found.stale.append(Stale("worktree", path, why))
    return found


def holds(home: Path, open_: set[int] | None) -> Found:
    """Each key of `holds.json` whose pull request is not open."""
    found, kept = Found(), read_json(home / HOLDS, {})
    if not isinstance(kept, dict) or not kept:
        return found
    if open_ is None:
        found.unjudged.append(f"hold: whether the {len(kept)} pull requests held are open")
        return found
    for key in sorted(kept, key=lambda one: (not one.isdigit(), one.zfill(12))):
        if not key.isdigit():
            found.stale.append(Stale("hold", key, "it is no pull request's number"))
        elif int(key) not in open_:
            found.stale.append(Stale("hold", f"#{key}", "its pull request is not open"))
    return found


def words(line: str) -> str:
    """A line with each commit and time a key leaves out (`state.MOMENT`), and each number, left
    out, and its spaces made one."""
    return " ".join(_WORDS.sub(" ", line).split())


def _homes(home: Path) -> list[Path]:
    return [home, *(scope for scope, _, _ in scopes(home))]


def _where(home: Path, path: Path) -> str:
    return path.relative_to(home.parent).as_posix()


def told(
    home: Path,
    rows: list[queue.Row],
    removed: set[str],
    asked: list[questions.Question],
    open_lines: list[str] | None,
) -> Found:
    """Each line of a home's `told` whose decision or stop has ended."""
    found, status = Found(), {row["slug"]: row.get("status") for row in rows}
    answered = {one.number for one in asked if one.answer}
    now = {words(line) for line in open_lines or ()}
    unjudged = False
    for directory in _homes(home):
        path = directory / TOLD
        try:
            lines = path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for at, line in enumerate(lines, 1):
            match = _TOLD.match(line)
            if not match:
                continue
            number, slug, rest = match.groups()
            why = ""
            if number:
                why = f"question {number} has its answer" if int(number) in answered else ""
            elif slug:
                if slug in removed:
                    why = f"its row {slug} is removed"
                elif status.get(slug) in queue.FINAL:
                    why = f"its row {slug} is {status[slug]}"
            elif open_lines is None:
                unjudged = True
            elif words(rest) not in now:
                why = "no item of the one list says it now"
            if why:
                found.stale.append(
                    Stale("told", f"{_where(home, path)}:{at}", f"{why}: {_cut(line)}")
                )
    if unjudged:
        found.unjudged.append(f"told: a jbus line, before a pass kept the open items in {WAKES}")
    return found


def gone(client: Client | None, thread: str) -> bool | None:
    """Whether T3 Code no longer has the thread, or None where it gave no answer."""
    if client is None:
        return None
    try:
        client.call("t3_thread_read", {"threadId": thread, "limit": 1})
    except T3Refused as error:
        return True if GONE.search(str(error)) else None
    except T3Error:
        return None
    return False


def home_ids(home: Path, client: Client | None) -> Found:
    """Each `home-id` that names a thread T3 Code no longer has."""
    found = Found()
    for directory in _homes(home):
        thread = ids(directory)[0]
        if not thread:
            continue
        said = gone(client, thread)
        where = _where(home, directory / "home-id")
        if said is None:
            found.unjudged.append(f"home-id: {where}, T3 Code did not say whether it has {thread}")
        elif said:
            found.stale.append(Stale("home-id", where, f"T3 Code no longer has thread {thread}"))
    return found


def open_pulls(run: Pass) -> tuple[list[dict[str, Any]] | None, str]:
    """GitHub's open pull requests, or None with why where it gave no list."""
    try:
        return pulls(run, "open", FIELDS, "--limit", LIMIT), ""
    except Silent as silent:
        return None, NO_GITHUB.format(why=silent)


def audit(run: Pass, client: Client | None, pulled: list[dict[str, Any]] | None) -> Found:
    """Everything stale in the project's state, with the open pull requests `pulled` (None where
    GitHub gave none). It reads, and writes nothing."""
    try:
        rows = queue.load(run.state)
        removed = set(queue.removed(run.state))
    except queue.Unparsable as error:
        raise jbus.Refused(f"refused: {error.path} does not parse") from error
    open_ = None if pulled is None else {int(pull["number"]) for pull in pulled}
    asked = questions.load(run.state)
    open_lines = opened(read_json(run.state / WAKES, {}))
    found = Found()
    for one in (
        briefs(run.home, rows, removed, open_, set(leftover.read(run.state))),
        worktrees(run, rows, pulled),
        holds(run.home, open_),
        told(run.home, rows, removed, asked, open_lines),
        home_ids(run.home, client),
    ):
        found.stale += one.stale
        found.unjudged += one.unjudged
    return found


def read(state: Path) -> dict[str, Any]:
    """The last hourly count: `{"hour", "count", "kinds", "gone"}`, or empty before the first.
    `gone` is whether the root's `home-id` names a thread T3 Code no longer has."""
    kept = read_json(state / NAME, {})
    return kept if isinstance(kept, dict) else {}


def line(project: str, kept: dict[str, Any]) -> str:
    """The one list's line for a count above none, or nothing while the root home is gone."""
    if not kept.get("count") or kept.get("gone"):
        return ""
    kinds = ", ".join(f"{kind} {n}" for kind, n in kept.get("kinds", {}).items() if n)
    return LINE.format(count=kept["count"], project=project, kinds=kinds)


def hourly(half: Half) -> None:
    """Once an hour, run the audit and keep its count. It lists the open pull requests as the verb
    does, and not the pass's last hundred, so the count is what `jbus stale` prints."""
    run, hour = half.run, int(half.run.now.timestamp() // HOUR)
    if read(run.state).get("hour") == hour:
        return
    pulled, why = open_pulls(run)
    if pulled is None:
        run.say(f"wait {run.project.name}: no stale count ({why})")
        return
    try:
        found = audit(run, half.client, pulled)
    except jbus.Refused as refused:
        run.say(f"wait {run.project.name}: no stale count ({refused})")
        return
    kinds, root = found.counts(), _where(run.home, run.home / "home-id")
    lost = any(one.kind == "home-id" and one.what == root for one in found.stale)
    kept = {"hour": hour, "count": sum(kinds.values()), "kinds": kinds, "gone": lost}
    write_json(run.state / NAME, kept)


def _stale(args: argparse.Namespace, config: jbus.Config) -> int:
    run = passes.Pass(config, verbs.project(config, args.project), datetime.now(UTC))
    try:
        client = Client(config.server, config.token_path)
    except jbus.Refused:
        client = None
    pulled, why = open_pulls(run)
    found = audit(run, client, pulled)
    for one in found.stale:
        print(one.line())
    for one in [why] * bool(why) + found.unjudged:
        print(f"not judged: {one}")
    print(f"stale: {len(found.stale)} in {run.project.name} ({found.summary()}), nothing deleted")
    return 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--project",
        default=argparse.SUPPRESS,
        help="the project's name in the config, when it has several",
    )


VERBS = (
    verbs.Verb(
        "stale",
        "list the briefs, worktrees, holds, told lines and home-ids nothing will act on again",
        _arguments,
        _stale,
    ),
)
STEPS = (verbs.Step("close", 26, "stale.hourly", hourly, ("sight", "client", "budget")),)
