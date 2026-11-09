"""jbus's watch of the homes: what a home has out, and the stall of a home that has gone quiet
with work out.

A child home is a scope of the repo's home: a directory of the state with a `home-id` or a
`Was home:` line. The root home owns no row: what it once had out is the catch-all's,
`uncategorized` (`jbriefs.home.catchall`), which is watched under its name whether its
directory is made or not, with the entries of the root's plan whose go holds. While the root
stands in for it (`jbriefs.home.stands_in`), the root's thread is nudged for it and reads the
root's plan. What a home has out (`out`) is read from jbus's own records, never from the
home: each queue row of a brief of its that is not over, each entry of its plan whose go holds
with no live row (`plan.owed`), each crew or reviewer thread of such a brief that the last pass
found unsettled, each question jbus holds for it, and each open gate of its `gates.md`. A row
that is queued and not launched is out, and it has no crew yet.

`jbus out --scope <scope>` prints one line for each, and nothing when nothing is out. The
handoff skill lists it in the note of a scope it archives, whose work is the uncategorized
home's from then on (`RetireHandsOver` in `features/home/spec/HomeTree.tla`). It prints
`unknown:` and ends 1 when jbus's last pass is too old for its list of threads to be trusted.

`watch`, a step of each pass, flags a home that has been quiet for its patience with work out, or a
routine that missed its beat (`StallFlagged`). A routine is a scope whose directory has a `rhythm`
file, its beat in minutes, and it is watched whatever it has out. Any other home, the catch-all
included, is watched while it has a crew, a pull request or an owed entry out: a question or a gate
waits on the user, and the home can do nothing for it until the user answers. A home is quiet from
the last thing it did that jbus can see: a write of one of its crew or reviewer threads, a change in
what it has out, or, before jbus nudged it in this spell, a write of its home thread. A message
queued to the home thread is no write (`threads`). A turn jbus's own nudge started is no progress,
so once nudged the home thread's writes do not end the spell. At its patience (`PATIENCE`, or the
routine's beat) jbus nudges the home thread and logs the first strike; a patience after that nudge
it nudges it again; a patience after the second it launches the home again on a fresh thread
(`launch`), and a patience after that, still quiet, the home is the user's: an item of `jbus needs`
(`stalled`), which wakes no thread. A home whose thread is the one jbus launched for it is not
launched again: its spell goes from the second nudge to `jbus needs`. Each step waits a patience
after the last, so a home first checked long after it went quiet still gets that time to act on a
nudge. No step raises an alert, so no home's stall reaches the root; an alert a stall raised before
is retired. `stalls.json` keeps each spell: when it began, how far it went, when it took its last
step, and what the home had out. It holds a key only for a home that is watched, so it is no list of
the child homes. It was `children.json`, and a state that holds only that is moved to the new name
on the first pass.

`keep_alive`, in the same step before `watch`, keeps the catch-all's home running once the
project's home has started (a root `plan.md`): when the catch-all's `home-id` names no thread, or
one T3 Code has archived or does not know, and the thread jbus last launched for it is not live
either, it makes `uncategorized/` with an empty plan where there is none and launches `/home
uncategorized` in the project's own checkout. `relaunches.json` keeps the last launch of each home,
its thread, when and why, and `launch` launches a home at most once in `PATIENCE`, which is the
time its start has to write its `home-id`, a lost reply included. A launch waits while the dispatch
is off or stopped. The model is the one the role map's `home` line gives."""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import jroles
import jsettings
from jbriefs import below
from jbriefs import home as homes
from jbus import (
    Config,
    Refused,
    alert,
    dispatch,
    mirror,
    outbox,
    plan,
    questions,
    queue,
    read_json,
    record,
    verbs,
    write_json,
)
from jbus.passes import Pass
from jbus.t3 import GONE, Client, T3Error, T3Refused
from jroles import pool

EVENTS = {"home-stall": "quiet"}
STALL = "home-stall"
FILE = "stalls.json"
WAS_FILE = "children.json"
"""The name `FILE` had before, moved on the first pass that finds it with no `FILE`."""
PATIENCE = 60
"""The minutes a child with work out may be quiet before the root flags it."""
STALE = 10
"""The minutes after which the last pass's list of threads is too old to say what is out."""
QUEUED = ("row queued", "row gate")
USERS = ("out question ", "out gate ")
"""What waits on the user and not on the home: no home is watched for it, since a nudge cannot
get it going."""
STEPS_OF = ("calm", "nudged1", "nudged2", "relaunched", "asked")
NUDGE = (
    "jbus: {home} has had {what} out and has done nothing jbus can see for {minutes} "
    "minutes. Carry on with your plan: read `{plan}` and your briefs' last "
    "Results, and pick up each thread that stopped, as the home skill's \"Picking up a thread "
    'that stopped" says. This is nudge {n} of 2; after the second, jbus starts this home again '
    "on a fresh thread."
)
LAUNCHES = "relaunches.json"
"""The last thread jbus launched for each home, by its name, with when and why."""
TITLE = "home: "


def whose(root: Path, state: Path, rows: list[dict[str, Any]]) -> dict[str, Path]:
    """The home of each slug the root knows: each of the queue's `rows`, by its queued brief, and
    each brief under `tasks/` and request under `scouts/` that no row has."""
    texts = {row["slug"]: queue.brief(state, row["slug"]) or "" for row in rows}
    for kind in ("tasks", "scouts"):
        for file in sorted((root / kind).glob("*.md")):
            texts.setdefault(file.stem, file.read_text(errors="replace"))
    home_of = homes.reader(root)
    return {slug: home_of(text) for slug, text in texts.items()}


def out(
    root: Path,
    scope: Path,
    state: Path,
    threads: list[dict[str, Any]],
    known: dict[str, Path] | None = None,
) -> list[str]:
    """Return a line for each thing the home at `scope`, a scope or the root itself, has out, in
    a fixed order: its rows that are not over, its entries whose go holds with no live row, its
    crew and reviewer threads in `threads` (the last pass's), its questions, and its open
    gates. `known` is `whose`, read once by a caller that asks of each home."""
    rows = queue.load(state)
    known = whose(root, state, rows) if known is None else known
    mine = {slug for slug, home in known.items() if home == scope}
    found = [
        f"out {row['slug']}: row {row.get('status') or 'queued'}"
        for row in rows
        if row["slug"] in mine and not queue.over(row)
    ]
    plans = {"", scope.name} if scope == homes.catchall(root) else {_scope(root, scope)}
    found += [
        f"out entry {made.entry}: go holds, no live row"
        for made in plan.owed(state, root, rows)
        if made.scope in plans
    ]
    found += [
        f"out {one['slug']}: {one['role']} thread {one['id']} is not settled"
        for one in threads
        if one.get("role") in ("crew", "reviewer") and one.get("slug") in mine
    ]
    own = "home" if scope == root else f"home-{scope.name}"
    found += [
        f"out question {one.number}: {one.question}"
        for one in questions.load(state)
        if one.answer is None and (one.slug == own or one.slug in mine)
    ]
    found += [
        f"out gate {number}: {asked}"
        for number, asked, _, body in mirror.gates(_read(scope / "gates.md"))
        if below.line(body, "Status:").startswith("open")
    ]
    return found


def _scope(root: Path, scope: Path) -> str:
    """The scope's name as jbus's plan records keep it, empty for the root's own plan."""
    return "" if scope == root else scope.name


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _stale(config: Config, name: str, now: datetime) -> str:
    """Say why the last pass's list of the project's threads cannot be trusted, or nothing: the
    pass is too old, or it could not ask T3 Code or GitHub about this project, so the list is
    the one an earlier pass left."""
    kept = record.read(config)
    silent = kept.get("silent")
    if isinstance(silent, dict) and silent.get(name):
        return f"jbus's last pass could not ask {silent[name]} about {name}"
    started = kept.get("started")
    try:
        at = datetime.fromisoformat(str(started))
    except ValueError:
        return "jbus has recorded no pass"
    minutes = int((now - at).total_seconds() // 60)
    return f"jbus's last pass is {minutes} minutes old" if minutes > STALE else ""


def _out(args: argparse.Namespace, config: Config) -> int:
    """`jbus out --scope <scope>`: say what the scoped home still has out, and nothing when
    nothing is."""
    project = verbs.here(config, args.project, closed=True)
    root = config.home(project)
    scope = root / args.scope
    if not (scope / "plan.md").exists():
        raise Refused(f"refused: {scope} has no plan.md, so {args.scope} is no scoped home")
    old = _stale(config, project.name, queue.clock())
    if old:
        print(f"unknown: {old}, so its list of threads cannot say what {args.scope} has out")
        return 1
    state = config.state_dir / project.state
    said = out(root, scope, state, record.seen(config, project.name))
    if said:
        print("\n".join(said))
    return 0


def _outs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--scope", required=True, help="the scoped home whose work is asked of")


VERBS = (verbs.Verb("out", "say what a scoped home still has out, for its retire", _outs, _out),)


def _rhythm(scope: Path) -> int:
    """The routine's beat in minutes, or 0 for a child that is no routine."""
    text = _read(scope / "rhythm").strip()
    return int(text) if text.isdigit() and int(text) > 0 else 0


def _at(stamp: str) -> datetime | None:
    try:
        return jsettings.when(stamp)
    except (TypeError, ValueError):
        return None


def _send(run: Pass, client: Client, thread: str, message: str, key: str) -> bool:
    """Queue one message to the child's home thread, once for the key. Return whether it is
    done: sent, or refused for good."""
    if key in run.box.sent():
        return True
    name = key.split("|")[1]
    try:
        went = outbox.send(
            run,
            client,
            thread=thread,
            row=name,
            key=key,
            text=message,
            template=STALL,
            needs="act",
        )
    except T3Refused as error:
        run.say(f"wait {name}: T3 Code refused {thread} its nudge ({error})")
    except T3Error as error:
        run.say(f"wait {name}: {thread} could not be nudged ({error})")
        return False
    else:
        if not went:
            return False
    run.box.mark(key)
    return True


def watch(run: Pass, client: Client, threads: list[dict[str, Any]] | None) -> None:
    """Count each home's quiet, the root's and each child's, and nudge, tell or ask for each one
    that is due. See the module. A queue or a question file that does not parse says nothing of
    what is out: the pass gates it, and the watch waits for it."""
    if threads is None:
        return
    try:
        rows = queue.load(run.state)
        questions.read(run.state)
    except (queue.Unparsable, questions.Unparsable):
        return
    if (run.state / WAS_FILE).exists() and not (run.state / FILE).exists():
        (run.state / WAS_FILE).replace(run.state / FILE)
    was: dict[str, Any] = read_json(run.state / FILE, {})
    kept: dict[str, Any] = {}
    known = whose(run.home, run.state, rows)
    catchall = homes.catchall(run.home)
    for scope in watched(run.home):
        thread = homes.thread_of(scope)
        lines = [
            line
            for line in out(run.home, scope, run.state, threads, known)
            if not line.startswith(USERS)
        ]
        launched = [line for line in lines if line.split(": ", 1)[1] not in QUEUED]
        beat = _rhythm(scope)
        if not thread or not (launched or beat):
            continue
        name = scope.name
        seen = hashlib.sha256("\n".join(line.split(": ")[0] for line in launched).encode())
        sig = seen.hexdigest()[:12]
        prev = was.get(name, {})
        step = prev.get("step", "calm") if prev.get("sig") == sig else "calm"
        slugs = {line.split()[1].rstrip(":") for line in lines}
        writes = [
            _at(str(one.get("wrote") or one.get("updatedAt")))
            for one in threads
            if (one.get("role") in ("crew", "reviewer") and one.get("slug") in slugs)
            or (one.get("id") == thread and step == "calm")
        ]
        latest = max((at for at in writes if at), default=None)
        since = _at(prev.get("since", "")) if prev.get("sig") == sig else None
        if since is None:
            since = latest or run.now
            step = "calm"
        elif latest and latest > since:
            since, step = latest, "calm"
        patience = beat or PATIENCE
        quiet = int((run.now - since).total_seconds() // 60)
        rank = STEPS_OF.index(step)
        spell = {"since": since.isoformat(), "step": step, "sig": sig}
        last = _at(prev.get("at", "")) if rank else None
        start = last or since + timedelta(minutes=patience * rank)
        if last:
            spell["at"] = last.isoformat()
        if step != "asked" and run.now - start >= timedelta(minutes=patience):
            what = f"{len(launched)} things" if launched else "its beat"
            standing = scope == catchall and homes.stands_in(run.home)
            plan = "jbus plan" if standing else f"jbus plan --scope {name}"
            went = _act(run, client, (name, plan), thread, spell, quiet, what)
            if went:
                spell["step"] = went
                spell["at"] = run.now.isoformat()
        kept[name] = spell
    for key in alert.streaks(run.config.state_dir):
        if key.startswith(_stall(run, "")):
            alert.retire(run.config.state_dir, key)
    if kept != was:
        write_json(run.state / FILE, kept)


def watched(home: Path) -> list[Path]:
    """The homes `watch` watches, each under its directory's name in `stalls.json`: the
    catch-all's, made or not, and each other scope. The root owns no row, so it is none of them."""
    catchall = homes.catchall(home)
    return [catchall, *(one for one, _, _ in homes.scopes(home) if one != catchall)]


def _stall(run: Pass, name: str) -> str:
    """The key of the alert a home's stall raised before a stall went on `jbus needs`, which each
    pass retires: no home-stall alert is open, so none reaches the root."""
    return f"{STALL} {run.project.name} {name}"


def stalled(state: Path) -> list[dict[str, str]]:
    """The items of `waiting-on-user.json` for each home whose spell came to `asked`: a home jbus
    started again on a fresh thread that stalled again. Each is the user's, on `jbus needs`, and
    wakes no thread (`jbus.wakes.need_items`)."""
    kept: dict[str, Any] = read_json(state / FILE, {})
    return [
        {
            "kind": "stalled",
            "key": f"stalled:{name}",
            "line": f"{STALL} {name}: the home {name} is quiet with work out after jbus nudged it "
            f"twice and started it again on a fresh thread, since {spell.get('since', '')}",
            "slug": f"home-{name}",
        }
        for name, spell in sorted(kept.items())
        if isinstance(spell, dict) and spell.get("step") == "asked"
    ]


def _act(
    run: Pass,
    client: Client,
    named: tuple[str, str],
    thread: str,
    spell: dict[str, Any],
    quiet: int,
    what: str,
) -> str:
    """Take the next step of a home's spell: a nudge, a second nudge, a launch of the home on a
    fresh thread, or the item on `jbus needs`. Return the step the spell is at once it is taken,
    or nothing when it is not taken yet. A home whose thread is the one jbus launched for it is
    not launched again: its spell goes to `jbus needs`. `named` is the home's name and the command
    that prints its plan: the root's own while it stands in for the catch-all."""
    (name, plan), (step, since) = named, (spell["step"], spell["since"])
    home = f"the home {name}"
    if step in ("calm", "nudged1"):
        n = 1 if step == "calm" else 2
        text = NUDGE.format(home=home, what=what, minutes=quiet, plan=plan, n=n)
        if not _send(run, client, thread, text, f"{STALL}|{name}|{since} {n}"):
            return ""
        run.say(f"{STALL} {name}: nudged its home, thread {thread}, {n} of 2")
        if n == 1:
            line = f"{STALL} {name}: {home} has had {what} out and been quiet {quiet} min"
            run.find(name, STALL, f"{line}; jbus nudged it, thread {thread}", key=f"{since} strike")
        return STEPS_OF[n]
    ours = read_json(run.state / LAUNCHES, {}).get(name, {}).get("thread")
    if step == "nudged2" and not (ours and ours == homes.ids(run.home / name)[0]):
        why = f"quiet {quiet} min after two nudges, thread {thread}"
        return "relaunched" if launch(run, client, name, why) else ""
    line = f"{STALL} {name}: {home} is still quiet after jbus started it again, {quiet} min"
    run.find(name, STALL, f"{line}: on jbus needs; thread {thread}", key=f"{since} ask")
    return "asked"


def live(run: Pass, client: Client, thread: str, threads: list[dict[str, Any]]) -> bool | None:
    """Whether a home's thread is live: in the pass's list, or read and not archived. False for
    one T3 Code has archived or does not know, None where it could not say."""
    if any(one.get("id") == thread for one in threads):
        return True
    try:
        read = client.call("t3_thread_read", {"threadId": thread, "limit": 1})
    except T3Refused as error:
        if GONE.search(str(error)):
            return False
        run.say(f"wait home: its thread {thread} could not be read ({error})")
        return None
    except T3Error as error:
        run.say(f"wait home: its thread {thread} could not be read ({error})")
        return None
    return not (read.get("thread") or {}).get("archived")


def keep_alive(run: Pass, client: Client, threads: list[dict[str, Any]] | None) -> None:
    """Keep the catch-all's home running: launch `/home uncategorized` when its `home-id` names
    no live thread, none, an archived one or one T3 Code does not know, and the thread jbus last
    launched for it is not live either. A project whose home has not started, with no root
    `plan.md`, has no catch-all to keep: `/home` makes the scopes under it."""
    if threads is None or not (run.home / "plan.md").exists():
        return
    catchall = homes.catchall(run.home)
    now, was = homes.ids(catchall)
    if now and now != was and live(run, client, now, threads) is not False:
        return
    ours = read_json(run.state / LAUNCHES, {}).get(catchall.name, {}).get("thread", "")
    if ours and ours != now and live(run, client, ours, threads) is not False:
        return
    why = f"its thread {now} is archived or gone" if now and now != was else "it has no thread"
    launch(run, client, catchall.name, why)


def launch(run: Pass, client: Client, name: str, why: str) -> bool:
    """Launch `/home <name>` on a fresh thread in the project's own checkout, making the
    catch-all's directory and plan where there are none. Return whether the home has a launch: one
    now, or one in the last `PATIENCE` minutes, whose start writes its `home-id`. So the keep-alive
    and a stall launch a home at most once in that time, also when a reply was lost."""
    path = run.state / LAUNCHES
    kept: dict[str, Any] = read_json(path, {})
    last = _at(str(kept.get(name, {}).get("at", "")))
    if last and run.now - last < timedelta(minutes=PATIENCE):
        return True
    if not run.config.dispatch or run.config.stop_path.exists():
        run.say(f"wait home {name}: the dispatch is off or stopped: it is not launched")
        return False
    scope = run.home / name
    if not (scope / "plan.md").exists() and not (scope / "plan-archived.md").exists():
        scope.mkdir(parents=True, exist_ok=True)
        (scope / "plan.md").touch()
    try:
        (routed,) = pool.routes("home", run.now) or (None,)
        full = pool.headroom("home")
    except jroles.Refused as error:
        run.say(f"wait home {name}: the role map gives the home no model ({error})")
        return False
    if routed:
        found = dispatch.mirrored_choice(
            run, f"home {name}", routed.selection.instances, {}, full=full
        )
        routed = pool.Route(routed.selection, found)
        if found.instance is None:
            run.say(f"wait home {name}: no launch: {found.why}")
            return False
    asked: dict[str, Any] = {
        "projectId": run.project.project_id,
        "title": f"{TITLE}{run.project.name} {name}",
        "workspaceStrategy": {"type": "root"},
        "message": f"/home {name}",
    }
    if run.config.runtime_mode:
        asked["runtimeMode"] = run.config.runtime_mode
    if routed is not None:
        asked["modelSelection"] = routed.as_json()
    kept[name] = {"at": run.now.isoformat(), "why": why}
    write_json(path, kept)
    try:
        thread = (client.call("t3_thread_launch", asked) or {}).get("threadId") or ""
    except T3Error as error:
        run.say(f"launch home {name}: no reply ({error}): no launch again for {PATIENCE} min")
        return True
    kept[name]["thread"] = thread
    write_json(path, kept)
    run.say(f"launched home {name}: {thread}, since {why}")
    return True


def _watch(half: Any) -> None:
    keep_alive(half.run, half.client, half.out)
    watch(half.run, half.client, half.out)


STEPS = (
    verbs.Step(
        "after-expedite",
        17,
        "children.watch",
        _watch,
        ("client",),
    ),
)
