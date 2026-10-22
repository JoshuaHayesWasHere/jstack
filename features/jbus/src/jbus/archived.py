"""Find the launched threads that T3 Code's list leaves out: archived, missing, or not yet listed.

`t3_thread_list` lists the threads that are not archived, and cannot list the rest. So when
a home archives a finished thread to tidy up, a pass no longer reads that thread, though the
thread still belongs to its row. `ask` reads each launched thread that is not in the list by
its id, with `t3_thread_read`, which also answers for an archived thread:

- archived: the thread is the row's, put away like a settled one (`World.archived`);
- not found: T3 Code has no such thread (`World.missing`);
- found and not archived: a launch that the list does not show yet, which `ask` leaves as
  it is;
- no answer: the row stays as the last pass judged it, not confirmed (`World.unasked`).

`ask` keeps an answer of archived or missing in `unlisted.json`, by thread id, and does not
ask about that thread again. When the user unarchives a thread, it appears in the list
again, and the pass goes by the list.
"""

from __future__ import annotations

from typing import Any

from jbus import dispatch, queue, read_json, write_json
from jbus.t3 import GONE, Client, T3Error, T3Refused
from jbus.wake import Pass
from jbus.watch import World

NAME = "unlisted.json"
ARCHIVED, MISSING = "archived", "missing"
KEPT = ("threadId", "title", "status", "createdAt", "updatedAt")


def ask(run: Pass, client: Client, world: World, rows: list[queue.Row]) -> None:
    """Put each launched thread of `rows` that is missing from the pass's list into `world`."""
    path = run.state / NAME
    kept: dict[str, Any] = read_json(path, {})
    before = dict(kept)
    for row in rows:
        slug = row["slug"]
        thread = dispatch.launched(run, slug)
        if not thread or slug in run.removed or slug in world.threads or slug in world.settled:
            continue
        if thread not in kept:
            try:
                read = client.call("t3_thread_read", {"threadId": thread, "limit": 1})
            except T3Refused as error:
                if not GONE.search(str(error)):
                    run.say(f"wait {slug}: its thread {thread} could not be read ({error})")
                    world.unasked.add(slug)
                    continue
                kept[thread] = {"state": MISSING}
            except T3Error as error:
                run.say(f"wait {slug}: its thread {thread} could not be read ({error})")
                world.unasked.add(slug)
                continue
            else:
                said = read.get("thread") or {}
                if not said.get("archived"):
                    continue
                kept[thread] = {"state": ARCHIVED, "thread": {k: said.get(k) for k in KEPT}}
        if kept[thread]["state"] == MISSING:
            world.missing.add(slug)
        else:
            world.archived[slug] = {**kept[thread]["thread"], "archived": True, "settled": True}
    if kept != before:
        write_json(path, kept)
