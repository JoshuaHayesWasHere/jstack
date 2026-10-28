"""Check a scout's request, and launch a scout for each row of the queue that is one.

A scout's request is a row of the queue (`jbus.queue`), queued with `jbus queue add` as any row
is: `add` takes a text whose head has a `Request:` line and no `Task:` line as a request
(`jbus.queue.requested`), keeps it as a row of role `scout`, and checks it here (`faults`) against
`features/scout/templates/scout-request.md`. It refuses a line that only a crewmate's brief has
(`CREWMATE`), and a `Request:` line over `jbriefs.parse.LONGEST` characters. The row is approved as
any row is, by the user's word or by its plan entry's go (`jbus.queue.entered`), and it waits on
its `--depends` as a crewmate's row does.

A pass launches each scout row whose go holds for its queued request and whose depends are over
(`watch.final`): one `t3_thread_launch` titled `scout: <slug>`, with the message `/scout <slug>`
and the project's own checkout as its workspace. That checkout is the main one, as it stands: the
scout gets no worktree and no branch, so it has nothing to commit and no pull request to open. The
launch writes the request to `scouts/<slug>.md` in the home's state directory, where the scout
writes its Report, or checks that the one there is the request queued. The model is the one the
role map's `scout` line gives, and the launch waits, as a crewmate's does, for the dispatch to be
on and for `jgauge room`. A scout takes no crew slot of `max_running`. Once launched, a scout's
thread is the pass's like any other: `jbus.threads` settles it once its Report is written, and the
row is `done` once that Report says `Status: done` (`watch.facts`).

As with a crewmate's launch, jbus keeps a record under `launches/` (`dispatch.record_path`), with
`role` `scout`, at `intent` before the call, so a lost reply is never launched again: the next pass
adopts the one thread titled `scout: <slug>`, or records a condition and leaves the row for the
user. jbus records a scout's trouble with `Pass.condition` and never with `Pass.gate`.
"""

from __future__ import annotations

import re
from typing import Any

import jroles
from jbriefs import parse, skills
from jbus import dispatch, queue, t3, verbs, watch, write_json
from jbus.passes import Changed, Depends
from jbus.t3 import Client, T3Error, T3Refused
from jroles import pool

TITLE = "scout: "
TEMPLATE = "scout-request.md"
CREWMATE = ("Task", "Size", "Pull request")
OPTIONAL = ("Home",)
READ_ONLY = "read-only"
_PLACEHOLDER = re.compile(r"<[^<>\n]* [^<>\n]*>")
_ITEM = re.compile(r"^\s*[-*+]\s+")


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
    longer than `jbriefs.parse.LONGEST`. It does not have its scout ask the user mid-task
    (`jbus.queue.asks`).
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
    return [*found, *queue.asks(text, "request")]


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


def adopt(run: Any, client: Client, slug: str, path: Any, record: dict[str, Any]) -> None:
    """Look up a launch whose reply was lost, and adopt the one thread titled `scout: <slug>`.
    With none or several, record a condition and leave the row: it is never launched again."""
    title = f"{TITLE}{slug}"
    try:
        listed = t3.listed(client, run.project.project_id, titleContains=title)
    except T3Error as error:
        run.say(f"wait scout {slug}: its lost launch reply could not be looked up ({error})")
        return
    matching = [one["threadId"] for one in listed if one.get("title") == title]
    if len(matching) != 1:
        what = f"scout launch reply lost, {len(matching)} matching threads"
        run.condition(slug, what, str(path), key=f"scout lost {record.get('at')}")
        return
    write_json(path, {**record, "state": "launched", "thread": matching[0], "adopted": True})
    dispatch.write_thread(run, slug, matching[0], kind="scouts")
    run.say(f"adopted scout {slug}: {matching[0]}")


def _launch(half: Any) -> None:
    """Launch each scout row whose go holds for its request and whose depends are over, and
    adopt each lost launch."""
    run, client, world, rows = half.run, half.client, half.seen.world, half.rows
    scouting = sorted(
        (row for row in rows or [] if queue.role(row) == queue.SCOUT), key=queue.order
    )
    if not scouting:
        return
    over = watch.final(run, world, rows)
    checked: dict[str, bool] = {}
    for row in scouting:
        slug = row["slug"]
        if slug in run.removed:
            continue
        records = dispatch.records(run, slug)
        if any(record.get("thread") for _, record in records):
            continue
        if records:
            adopt(run, client, slug, *records[-1])
            continue
        if not row.get("approved"):
            continue
        text = queue.brief(run.state, slug)
        if text is None or not queue.approved_text(row, text):
            now = queue.brief_sha(text or "")[:12]
            lines = tuple(queue.changed(row, text))
            run.reasons[slug] = Changed(now, row.get("brief_sha", "")[:12], lines)
            run.say(f"wait scout {slug}: its request changed after its go: approve it again")
            continue
        unmet = tuple(other for other in row.get("depends", []) if other not in over)
        if unmet:
            run.reasons[slug] = Depends(unmet)
            continue
        if not run.config.dispatch or run.config.stop_path.exists():
            run.say(f"wait scout {slug}: the dispatch is off or stopped: nothing is launched")
            return
        target = run.home / "scouts" / f"{slug}.md"
        plain = queue.body(text)
        wrote = not target.exists()
        if not wrote and queue.body(target.read_text(errors="replace")).strip() != plain.strip():
            run.condition(slug, f"scouts/{slug}.md differs from the queued request", str(target))
            continue
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
        again = queue.fresh(run.state, slug) or {}
        same = all(again.get(column) == row.get(column) for column in ("approved", "brief_sha"))
        if not same or not queue.approved_text(row, queue.brief(run.state, slug) or ""):
            run.say(f"wait scout {slug}: its row changed during the pass")
            continue
        if wrote:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(dispatch.homed(plain, text))
        sha = queue.brief_sha(text)
        path = dispatch.record_path(run, slug, sha)
        launch = {
            "key": f"{run.project.name}/{slug}/{sha[:12]}",
            "role": queue.SCOUT,
            "state": "intent",
            "at": run.now.isoformat(),
        }
        write_json(path, launch)
        try:
            reply = client.call("t3_thread_launch", arguments(run, slug, routed))
        except T3Refused as error:
            path.unlink()
            if wrote:
                target.unlink()
            run.condition(slug, "T3 Code refused the scout's launch", str(error))
            continue
        except T3Error as error:
            run.say(f"launch scout {slug}: no reply ({error}): it is looked up on the next pass")
            continue
        thread = reply.get("threadId")
        if not thread:
            run.say(f"launch scout {slug}: the reply named no thread: it is looked up next pass")
            continue
        write_json(path, {**launch, "state": "launched", "thread": thread})
        dispatch.write_thread(run, slug, thread, kind="scouts")
        on = f" on {choice.instance}, {choice.why}" if choice.why else ""
        run.say(f"launched scout {slug}: {thread}{on}")


STEPS = (verbs.Step("after-expedite", 40, "scouts.launch", _launch, ("client", "world")),)
