"""Declare `jbus scout`: a scout's request, the user's go for it, and its read-only launch.

A home sends a durable scout by hand (`features/home/skills/home/sending-a-scout.md`). This is the
path for anyone else who needs one, such as an expert bot: it asks for research and gets no
crewmate. A request queued with `jbus queue add` goes out as a crewmate, which branches and opens
a pull request, so a request meant for a scout must not go that way.

The table is `scouts.json` in the project's state directory, one row a request, and only the verbs
and the launch step here write it. A row holds its slug, the user's go (`approval`, the record
`jbus.queue.Approval` keeps, with `brief_sha` the sha of the request approved) and its launch
(`launch`: `state` `intent` before the call and `launched` after it, `thread`, `at`). The request
itself is `scouts/<slug>.md` in the home's state directory, where the scout writes its Report, and
the row does not copy it.

- `add` checks the request on stdin against `features/scout/templates/scout-request.md` (`faults`)
  and stores it. It refuses a line that only a crewmate's brief has (`CREWMATE`), and a `Request:`
  line over `jbriefs.parse.LONGEST` characters. It never takes over a request a home wrote itself,
  and never changes one whose scout is out.
- `approve` records the go on the same bases as `jbus queue approve`, for the request whose sha
  the user was shown. A rule is no basis here: a rule's go follows a row the user approved, and a
  scout follows none.
- `show` prints each row's state (`state_of`), what its last Report says
  (`jbus.view.state.request`), its thread and its go.

A pass launches each row whose go holds for the request on disk (`launch`): one `t3_thread_launch`
titled `scout: <slug>`, with the message `/scout <slug>` and the project's own checkout as its
workspace. That checkout is the main one, as it stands: the scout gets no worktree and no branch,
so it has nothing to commit and no pull request to open. The model is the one the role map's
`scout` line gives, and the launch waits, as a crewmate's does, for the dispatch to be on and for
`jgauge room`. A scout takes no crew slot of `max_running`. Once launched, a scout's thread is the
pass's like any other: `jbus.threads` settles it once its Report is written.

As with a crewmate's launch, the row is at `intent` before the call, so a lost reply is never
launched again: the next pass adopts the one thread titled `scout: <slug>`, or records a condition
and leaves the row for the user. jbus records a scout's trouble with `Pass.condition` and never
with `Pass.gate`, since a gate holds back every step for that slug, and a crewmate's row often has
the slug of the scout that researched it.
"""

from __future__ import annotations

import argparse
import fcntl
import re
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import jbus
import jroles
import jsettings
from jbriefs import parse, skills
from jbus import asks, dispatch, queue, threads, verbs, write_json
from jbus.t3 import Client, T3Error, T3Refused
from jbus.view import state as view_state
from jroles import pool

NAME = "scouts.json"
TITLE = "scout: "
TEMPLATE = "scout-request.md"
CREWMATE = ("Task", "Size", "Pull request")
OPTIONAL = ("Home",)
READ_ONLY = "read-only"
_SLUG = re.compile(r"[a-z0-9][a-z0-9._-]*")
_PLACEHOLDER = re.compile(r"<[^<>\n]* [^<>\n]*>")
_ITEM = re.compile(r"^\s*[-*+]\s+")
HEAD = ("slug", "state", "report", "thread", "approved")

Row = dict[str, Any]


def path(state: Path) -> Path:
    return state / NAME


def request_path(home: Path, slug: str) -> Path:
    return home / "scouts" / f"{slug}.md"


def load(state: Path) -> list[Row]:
    """Return the rows of the table. A file that is not a list of rows refuses."""
    found = jbus.read_json(path(state), [])
    if not isinstance(found, list) or not all(
        isinstance(row, dict) and isinstance(row.get("slug"), str) for row in found
    ):
        raise jbus.Refused(f"refused: {path(state)} does not parse, and nothing writes it")
    return found


@contextmanager
def _changing(state: Path) -> Iterator[list[Row]]:
    state.mkdir(parents=True, exist_ok=True)
    with open(state / "scouts.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rows = load(state)
        yield rows
        write_json(path(state), sorted(rows, key=lambda row: row["slug"]))


def _read(file: Path) -> str | None:
    try:
        return file.read_text(errors="replace")
    except OSError:
        return None


def template() -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return the labels a request must have, each one the template has less `OPTIONAL`, and
    the template's own placeholders, each `<...>` span of it with a space in it."""
    text = skills.where("template", TEMPLATE).read_text()
    named = (label for label, _ in parse.fields(text) if label not in (parse.TITLE, ""))
    return tuple(label for label in named if label not in OPTIONAL), tuple(
        dict.fromkeys(_PLACEHOLDER.findall(text))
    )


def faults(slug: str, text: str) -> list[str]:
    """Every reason a request may not be stored, one line each.

    A request is in the template's shape when its first line is `# <slug>: <what to find out>`,
    each label of `labels` has a field whose lines are filled in (not the template's own
    placeholders), its `Questions:` has at least one item, and its `Out of bounds:` starts
    `read-only`. It has no line that only a crewmate's brief has, and its `Request:` line is no
    longer than `jbriefs.parse.LONGEST`.
    """
    found = []
    held = parse.fields(text)
    title = held[0][1][0] if held and held[0][0] == parse.TITLE else ""
    if not title.startswith(f"{slug}: ") or not title.removeprefix(f"{slug}: ").strip():
        found.append(f"first line is not # {slug}: <what to find out>")
    fields = {label: lines for label, lines in reversed(held)}
    labels, placeholders = template()
    for label in labels:
        if label not in fields:
            found.append(f"no {label}: line")
            continue
        first, *rest = fields[label]
        items = [_ITEM.sub("", line).strip() for line in rest if _ITEM.match(line)]
        lines = [line for line in (first.strip(), *items) if line]
        if not lines or (label == "Questions" and not items):
            found.append(f"{label}: line is empty")
        elif any(held in line for held in placeholders for line in lines):
            found.append(f"{label}: line is the template's own text")
        elif label == "Out of bounds" and not first.strip().startswith(READ_ONLY):
            found.append(f"Out of bounds: line does not start {READ_ONLY}")
    for label in CREWMATE:
        if label in fields:
            found.append(f"a {label}: line, which only a crewmate's brief has")
    if long := parse.overlong(text, "Request"):
        found.append(long)
    return found


def state_of(row: Row, text: str | None) -> str:
    """Return where a row is: `requested` with no go, `changed` where the request on disk is not
    the one approved, `approved`, `launching` while a launch has no thread, and `launched`."""
    launch = row.get("launch") or {}
    if launch.get("thread"):
        return "launched"
    if launch:
        return "launching"
    kept = queue.record(row)
    if kept is None:
        return "requested"
    if text is None or queue.brief_sha(text) != kept.brief_sha:
        return "changed"
    return "approved"


def report(home: Path, slug: str) -> str:
    """Return what the request's last Report says, as the view reads it, or `none` before one."""
    said = view_state.request(home, slug)["state"]
    return "none" if said == "researching" else said


def render(home: Path, rows: list[Row]) -> str:
    lines = ["| " + " | ".join(HEAD) + " |", "|" + " --- |" * len(HEAD)]
    for row in rows:
        slug = row["slug"]
        text = _read(request_path(home, slug))
        cells = (
            slug,
            state_of(row, text),
            report(home, slug),
            (row.get("launch") or {}).get("thread", ""),
            queue.approval(row),
        )
        lines.append("| " + " | ".join(cell.replace("|", "\\|") for cell in cells) + " |")
    return "\n".join(lines) + "\n"


def add(state: Path, home: Path, slug: str, text: str) -> str:
    """Store the request and return the line that says so. Refuse a request out of the
    template's shape, one a home wrote itself, and one whose scout is out."""
    if not _SLUG.fullmatch(slug):
        raise jbus.Refused(f"refused: {slug} is not a slug")
    if not text.strip():
        raise jbus.Refused("refused: no request on stdin")
    found = faults(slug, text)
    if found:
        many = "1 fault" if len(found) == 1 else f"{len(found)} faults"
        lines = "".join(f"\n- {fault}" for fault in found)
        raise jbus.Refused(f"refused: {slug}'s request has {many}, and nothing is stored{lines}")
    file = request_path(home, slug)
    with _changing(state) as rows:
        row = next((one for one in rows if one["slug"] == slug), None)
        if row is None and file.exists():
            raise jbus.Refused(
                f"refused: scouts/{slug}.md is there already and jbus did not add it: a home "
                "sent that scout itself"
            )
        if row is not None and row.get("launch"):
            raise jbus.Refused(f"refused: scout {slug} is out already, and its request stays")
        if row is None:
            rows.append(row := {"slug": slug})
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)
    sha = queue.brief_sha(text)
    kept = queue.record(row)
    go = "waits for a go"
    if kept is not None:
        go = "its go holds" if kept.brief_sha == sha else "its go does not hold: approve it again"
    return f"added {slug}: request {sha[:12]}, {go}"


def approve(
    state: Path,
    home: Path,
    slug: str,
    given: str,
    said: queue.Said,
    basis: tuple[str, str],
    user: jsettings.Settings,
) -> str:
    """Record the go for the request whose sha starts with `given`, on the user's words `said`,
    and return the line that says so. jbus writes the time in `user`'s zone."""
    with _changing(state) as rows:
        row = next((one for one in rows if one["slug"] == slug), None)
        if row is None:
            raise jbus.Refused(f"refused: no scout {slug}: add its request first")
        if row.get("launch"):
            raise jbus.Refused(f"refused: scout {slug} is out already")
        text = _read(request_path(home, slug))
        if text is None:
            raise jbus.Refused(f"refused: scouts/{slug}.md is gone: add it again")
        sha = queue.brief_sha(text)
        if sha[:12] != given:
            raise jbus.Refused(f"refused: {slug}'s request is {sha[:12]}, not {given}")
        made = queue.Approval(
            basis=basis[0],
            ref=basis[1],
            words=said.words,
            said_at=said.said_at,
            said_in=said.said_in,
            checked=said.checked,
            ran_by=queue.runner(),
            ran_at=user.stamp(queue.clock()),
            brief_sha=sha,
        )
        row["approval"] = queue.held(made)
    return f"approved {slug}: request {sha[:12]}, {made.line()}"


def _launched(state: Path, slug: str, launch: dict[str, Any] | None) -> None:
    with _changing(state) as rows:
        for row in rows:
            if row["slug"] == slug:
                if launch is None:
                    row.pop("launch", None)
                else:
                    row["launch"] = launch


def _intent(state: Path, home: Path, slug: str, launch: dict[str, Any]) -> bool:
    """Record `launch` as the row's launch only while its go holds for the request on disk, read
    under the table's lock, and say whether it did: an `add` since the pass looked replaces the
    request, and a go holds for the one request approved."""
    with _changing(state) as rows:
        row = next((one for one in rows if one["slug"] == slug), None)
        if row is None or state_of(row, _read(request_path(home, slug))) != "approved":
            return False
        row["launch"] = launch
        return True


def arguments(run: Any, slug: str, routed: pool.Route | None) -> dict[str, Any]:
    """Return the arguments for `t3_thread_launch`: a thread titled `scout: <slug>` in the
    project's own checkout, with no worktree and no branch, told `/scout <slug>`."""
    made: dict[str, Any] = {
        "projectId": run.project.project_id,
        "title": f"{TITLE}{slug}",
        "workspaceStrategy": {"type": "root"},
        "message": f"/scout {slug}",
    }
    if run.config.runtime_mode:
        made["runtimeMode"] = run.config.runtime_mode
    if routed is not None:
        made["modelSelection"] = routed.as_json()
    return made


def adopt(run: Any, client: Client, slug: str, launch: dict[str, Any]) -> None:
    """Look up a launch whose reply was lost, and adopt the one thread titled `scout: <slug>`.
    With none or several, record a condition and leave the row: it is never launched again."""
    title = f"{TITLE}{slug}"
    try:
        listed = threads._listed(client, run.project.project_id, titleContains=title)
    except T3Error as error:
        run.say(f"wait scout {slug}: its lost launch reply could not be looked up ({error})")
        return
    matching = [one["threadId"] for one in listed if one.get("title") == title]
    if len(matching) != 1:
        what = f"scout launch reply lost, {len(matching)} matching threads"
        run.condition(slug, what, str(path(run.state)), key=f"scout lost {launch.get('at')}")
        return
    _launched(
        run.state, slug, {**launch, "state": "launched", "thread": matching[0], "adopted": True}
    )
    dispatch.write_thread(run, slug, matching[0], kind="scouts")
    run.say(f"adopted scout {slug}: {matching[0]}")


def _launch(half: Any) -> None:
    """Launch each scout whose go holds for its request, and adopt each lost launch."""
    run, client = half.run, half.client
    try:
        rows = load(run.state)
    except jbus.Refused as error:
        run.condition("scouts", str(error).removeprefix("refused: "))
        return
    checked: dict[str, bool] = {}
    for row in rows:
        slug, launch = row["slug"], row.get("launch") or {}
        if launch.get("thread"):
            continue
        if launch:
            adopt(run, client, slug, launch)
            continue
        if queue.record(row) is None:
            continue
        text = _read(request_path(run.home, slug))
        if state_of(row, text) != "approved":
            run.say(f"wait scout {slug}: its request changed after its go: approve it again")
            continue
        if not run.config.dispatch or run.config.stop_path.exists():
            run.say(f"wait scout {slug}: the dispatch is off or stopped: nothing is launched")
            return
        try:
            (routed,) = pool.routes("scout", run.now) or (None,)
            full = pool.headroom("scout")
        except jroles.Refused as error:
            run.condition(slug, "the role map gives the scout no model", str(error))
            return
        if routed:
            found = dispatch.mirrored_choice(
                run, slug, routed.selection.instances, checked, full=full
            )
            routed = pool.Route(routed.selection, found)
        choice = routed.choice if routed else pool.Choice(None, "")
        if routed and choice.instance is None:
            run.say(f"wait scout {slug}: no launch: {choice.why}")
            return
        why, _ = dispatch.room(run, choice.instance, role="scout", light=True)
        if why:
            run.say(f"wait scout {slug}: no room: {why}")
            return
        launch = {"state": "intent", "at": run.now.isoformat()}
        if not _intent(run.state, run.home, slug, launch):
            run.say(f"wait scout {slug}: its request changed after its go: approve it again")
            continue
        try:
            reply = client.call("t3_thread_launch", arguments(run, slug, routed))
        except T3Refused as error:
            _launched(run.state, slug, None)
            run.condition(slug, "T3 Code refused the scout's launch", str(error))
            continue
        except T3Error as error:
            run.say(f"launch scout {slug}: no reply ({error}): it is looked up on the next pass")
            continue
        thread = reply.get("threadId")
        if not thread:
            run.say(f"launch scout {slug}: the reply named no thread: it is looked up next pass")
            continue
        _launched(run.state, slug, {**launch, "state": "launched", "thread": thread})
        dispatch.write_thread(run, slug, thread, kind="scouts")
        on = f" on {choice.instance}, {choice.why}" if choice.why else ""
        run.say(f"launched scout {slug}: {thread}{on}")


def _scout(args: argparse.Namespace, config: jbus.Config) -> int:
    project = verbs.project(config, args.project)
    state, home = config.state(project), config.home(project)
    if args.verb == "add":
        print(add(state, home, args.slug, sys.stdin.read()))
    elif args.verb == "approve":
        basis, ref, _ = queue.basis(vars(args))
        said = asks._asks(config, project).said(basis, ref)
        print(approve(state, home, args.slug, args.sha, said, (basis, ref), config.user))
    else:
        print(render(home, load(state)), end="")
    return 0


def _arguments(parser: argparse.ArgumentParser) -> None:
    verbs_of = parser.add_subparsers(dest="verb", required=True)
    verbs_of.add_parser("show", help="each scout's state and its Report", allow_abbrev=False)
    add_one = verbs_of.add_parser(
        "add", help="a scout's request, on stdin, in the template's shape", allow_abbrev=False
    )
    add_one.add_argument("slug")
    go = verbs_of.add_parser(
        "approve", help="record the go for the request the user was shown", allow_abbrev=False
    )
    go.add_argument("slug")
    go.add_argument("--word", metavar="ID", help="a word `jbus word` kept, by its id")
    go.add_argument("--answer", metavar="NUMBER", help="the answer that closed a question")
    go.add_argument("--message", metavar="THREAD/MESSAGE", help="the user's own message in T3 Code")
    go.add_argument(
        "--page", metavar="SESSION/ENTRY", help="the user's own send from a Lavish page"
    )
    go.add_argument("--sha", required=True, help="the first 12 of that request's sha256")


VERBS = (
    verbs.Verb("scout", "a scout's request, its go, and its read-only launch", _arguments, _scout),
)
STEPS = (verbs.Step("after-expedite", 40, "scouts.launch", _launch, ("client", "world")),)
