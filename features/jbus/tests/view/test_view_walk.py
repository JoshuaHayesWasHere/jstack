"""The state walk: every state jbus knows has its place in the view, and `SURFACES` names
each one.

The walk builds `view.walk`'s project once, runs `state.stack` and `state.build` over it as a
pass left it, then again for a pass that T3 Code did not answer and one that GitHub did not,
and checks each entry of `SURFACES` against what they hold. A chip and a row of a thread are
drawn by the page alone, so `view/page/test_view_page_walk.py` checks those. An entry that
today's view gets wrong is a known failure that names its finding (`walk.KNOWN`).
"""

import time

import pytest

from jbus import work
from view import walk
from view.scene import Scene

ON_PAGE = ("thread", "role")


BUILT = {}


@pytest.fixture
def walked(tmp_path, monkeypatch):
    """The walk's project and the three answers over it, with how long they took to build.
    The first test that asks builds them, under the isolation every test has (the zone of
    `testing/jstack_fixtures.py` among it), and the tests after it read the same answers."""
    if not BUILT:
        began = time.monotonic()
        scene = Scene(tmp_path, monkeypatch)
        made = walk.build(scene)
        seen = {}
        for who in ("", work.T3, work.GITHUB):
            walk.silent(scene, who)
            seen[who] = walk.view(scene)
        BUILT["walk"] = made, seen, time.monotonic() - began
    return BUILT["walk"]


def test_surfaces_names_every_state_and_nothing_else():
    lacking, extra = walk.missing()
    assert lacking == [], f"SURFACES has no place for {lacking}: add each"
    assert extra == [], f"SURFACES names {extra}, which no module has"


def test_a_state_with_no_entry_fails_the_walk():
    """Taking one entry out of `SURFACES`, or adding a value to the line, leaves a state with
    no place, and `missing` names it."""
    found = walk.states()
    fewer = {key: one for key, one in walk.SURFACES.items() if key != ("value", "hung")}
    assert walk.missing(fewer, found) == ([("value", "hung")], [])
    more = found | {"value": found["value"] | {"parked"}}
    assert walk.missing(walk.SURFACES, more) == ([("value", "parked")], [])
    assert set(walk.KNOWN) <= set(walk.SURFACES)


def test_the_walk_has_each_state_and_builds_in_under_5_seconds(walked):
    made, _, took = walked
    pairs = walk.reached()
    assert set(made.rows) == set(pairs)
    assert {value for value, _ in pairs} == set(work.VALUES)
    assert len(made.threads) == 30
    assert set(made.items) == walk.states()["kind"]
    assert len(made.gates) == 12
    assert took < 5, f"the walk took {took:.1f} s to build"


def needed(stack, slug, pr):
    """Whether a need of Needs you names the row: its key ends in its slug or its pull
    request."""
    return any(one["key"].rpartition(":")[2] in (slug, pr) for one in stack["needs"] if pr or slug)


def wrong(key, made, seen):
    """What the view holds for the state of `key` that `SURFACES` says it must not, as lines;
    none where it is right."""
    kind, name = key
    want = walk.SURFACES[key]
    stack, answer = seen[""]
    project = stack["projects"][0]
    tasks = {one["slug"]: one for one in answer["tasks"]}
    threads = {one["slug"]: one for one in answer["threads"]}
    broken = [one["what"] for one in project["broken"]]
    faults = []
    if project["waits"] != len(stack["needs"]):
        faults.append(f"the overview counts {project['waits']} waits for {len(stack['needs'])}")
    if kind == "value":
        rows = {one["slug"]: one for one in seen[""][1]["tasks"] + seen[""][1]["ended"]}
        for (value, _), slug in made.rows.items():
            if value != name:
                continue
            pr = rows[slug]["row_pr"] if slug in rows else ""
            task = tasks.get(slug)
            drawn = bool(task) and task["step"] != "unknown"
            if needed(stack, slug, pr) != want.needs:
                faults.append(f"{slug}: in Needs you is {not want.needs}")
            if drawn != want.row:
                faults.append(f"{slug}: a row of In progress is {drawn}")
            if (slug in project["unplaced"]) != want.unplaced:
                faults.append(f"{slug}: unplaced on the overview is {not want.unplaced}")
            if want.rank in (None, walk.OVER) and task:
                faults.append(f"{slug}: open at rank {task['rank']}, and it is off the line")
            elif want.rank not in (None, walk.OVER) and (not task or task["rank"] != want.rank):
                faults.append(f"{slug}: rank {task and task['rank']}, not {want.rank}")
    elif kind == "live":
        for (role, liveness), slug in made.threads.items():
            if liveness != name or (role, liveness) == ("home", "ended"):
                continue
            one = threads[slug]
            if (one["out"], one["rank"]) != (want.row, want.rank):
                faults.append(f"{slug}: out {one['out']} at rank {one['rank']}")
    elif kind == "home":
        one = threads[made.threads["home", "ended"]]
        if one["rank"] != want.rank:
            faults.append(f"the idle home ranks {one['rank']}, not {want.rank}")
    elif kind == "kind":
        keys = {one["key"] for one in stack["needs"]}
        faults += [f"{one}: not in Needs you" for one in made.items[name] if one not in keys]
    elif kind == "source":
        file = made.sources[name]
        unwell = {(one["name"], one["state"]) for one in project["health"]["unwell"]}
        listed = {one for one, _ in unwell}
        if name == "ok" and file in listed:
            faults.append(f"{file} is ok and is listed as unwell")
        elif name != "ok" and (file, name) not in unwell:
            faults.append(f"{file} is not listed as {name}")
        if want.broken and not any(want.broken in one for one in broken):
            faults.append(f"no broken reason says {want.broken!r}: {broken}")
    elif kind == "gate":
        asked = made.gates[name]
        for place, queue in (("needs", stack["needs"]), ("proceeds", stack["proceeds"])):
            there = any(one["what"] == asked for one in queue)
            if there != getattr(want, place):
                faults.append(f"{asked!r} in {place} is {there}")
    elif kind == "silent":
        stack, answer = seen[name]
        broken = [one["what"] for one in stack["projects"][0]["broken"]]
        if not any(want.broken in one for one in broken):
            faults.append(f"the overview does not say {want.broken!r}: {broken}")
        doubted = [one for one in answer["tasks"] if (one["unconfirmed"] or {}).get("source")]
        if len(doubted) != len(answer["tasks"]):
            faults.append(f"{len(answer['tasks']) - len(doubted)} tasks are not marked")
    elif kind == "route" and name == "stranded outbox":
        held = project["health"]["bus"]["outbox"]
        if held != walk.STRANDED:
            faults.append(f"the bus says outbox {held}, and {walk.STRANDED} events wait")
        if not any(want.broken in one for one in broken):
            faults.append(f"no broken reason says {want.broken!r}: {broken}")
    elif kind == "route":
        faults += [f"broken says {one!r}" for one in broken if one.startswith("bus")]
    return faults


def cases():
    found = []
    for key in walk.SURFACES:
        if key[0] in ON_PAGE:
            continue
        known = walk.KNOWN.get(key)
        marks = (
            [pytest.mark.xfail(strict=True, raises=AssertionError, reason=known[0])]
            if known and "data" in known[1]
            else []
        )
        found.append(pytest.param(key, id=f"{key[0]}:{key[1]}", marks=marks))
    return found


@pytest.mark.parametrize("key", cases())
def test_each_state_is_where_surfaces_says(walked, key):
    made, seen, _ = walked
    assert wrong(key, made, seen) == []
