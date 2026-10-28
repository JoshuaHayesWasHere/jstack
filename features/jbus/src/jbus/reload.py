"""`tell` tells each thread out that a merge changed a skill it may have loaded.

A thread keeps the text of each skill it loaded and runs it until it reads the file again, so
after a merge that changed a skill, a thread out runs the old text. `jmerge` names on its
`merged` line each skill whose `SKILL.md` the merge changed (`jmerge.lines.skills_of`).

`tell` keeps each such merge in `reload.json`, written before any send so a pass that stops
partway loses none, until every thread that was out when the merge landed is told: one
message each, under the key `reload|<commit 12>|<thread>`, marked in
`sent.json` once T3 Code took it. Once every one is told, the merge itself is marked,
`reload|<commit 12>`, and a `merged` line printed again for it adds nothing. So a thread hears
of a merge once, and a send that got no answer, or that the outbox held, goes on a later pass.
A thread started after the merge loaded the new text and is not told. A thread whose title
gives no role (`roles.OTHER`) is the user's own and is not told either.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jbus import outbox, read_json, record, roles, t3, verbs, write_json
from jbus.passes import Pass
from jbus.t3 import Client, T3Error
from jbus.watch import when
from jmerge import lines as lines_of
from jmerge.lines import one as parse

if TYPE_CHECKING:
    from collections.abc import Iterable

FILE = "reload.json"
TEMPLATE = "reload"
TOLD = (
    "jbus: pull request #{number} merged at {commit} and changed these skills: {names}. The "
    "text of them you loaded before then is old: read each one's SKILL.md again from the file "
    "before you next follow it."
)


def owed(run: Pass, said: Iterable[str]) -> list[dict[str, Any]]:
    """Return the merges whose threads are still to be told: those kept in `reload.json`, and
    each `merged` line of this pass that names a skill."""
    kept: list[dict[str, Any]] = read_json(run.state / FILE, [])
    for text in said:
        line, names = parse(text), lines_of.skills_of(text)
        if not names or line is None or line.word != "merged":
            continue
        commit = text.split()[3]
        done = f"{TEMPLATE}|{commit[:12]}" in run.box.sent()
        if not done and all(one["commit"] != commit for one in kept):
            at = record.stamp(run.now)
            kept.append({"number": line.number, "commit": commit, "skills": names, "at": at})
    return kept


def tell(run: Pass, client: Client, said: Iterable[str]) -> None:
    """Tell each thread out of a merge that changed a skill, once, as the module says."""
    kept = owed(run, said)
    if not kept:
        return
    write_json(run.state / FILE, kept)
    try:
        out = t3.listed(client, run.project.project_id, settled=False)
    except T3Error as error:
        run.say(f"wait {run.project.name}: the threads out could not be told of a skill ({error})")
        return
    write_json(run.state / FILE, [one for one in kept if not _told(run, client, one, out)])


def _told(run: Pass, client: Client, merge: dict[str, Any], out: list[dict[str, Any]]) -> bool:
    """Tell each thread of `out` that was out when `merge` landed and has a role, and return
    whether every one of them is told now."""
    commit, landed = merge["commit"], when(merge["at"])
    text = TOLD.format(number=merge["number"], commit=commit[:12], names=", ".join(merge["skills"]))
    every = True
    for thread in out:
        at, title = thread["threadId"], str(thread.get("title", ""))
        role, slug = roles.role_of(title)
        try:
            began = when(thread["createdAt"])
        except (KeyError, TypeError, ValueError):
            began = landed
        key = f"{TEMPLATE}|{commit[:12]}|{at}"
        if role == roles.OTHER or began > landed or key in run.box.sent():
            continue
        try:
            went = outbox.send(
                run,
                client,
                thread=at,
                row=slug or title,
                key=key,
                text=text,
                template=TEMPLATE,
                needs="decide",
            )
        except T3Error as error:
            run.say(f"wait {slug or title}: its thread could not be told of a skill ({error})")
            went = False
        if went:
            run.box.mark(key)
        every = every and went
    if every:
        run.box.mark(f"{TEMPLATE}|{commit[:12]}")
        run.say(f"told {run.project.name}: #{merge['number']} changed {', '.join(merge['skills'])}")
    return every


STEPS = (
    verbs.Step(
        "tellers",
        75,
        "reload.tell",
        lambda half: tell(half.run, half.client, half.said),
        ("client",),
    ),
)
