"""The state walk: every state jbus knows has its place in the view, and `SURFACES` names
each one.

The walk builds `view.walk`'s project once, runs `state.stack` and `state.build` over it as a
pass left it, then again for a pass that T3 Code did not answer and one that GitHub did not,
and checks each entry of `SURFACES` against what they hold. A chip and a row of a thread are
drawn by the page, so `view/page/test_view_page_walk.py` checks those, and the `gone` a task
carries for its chip is checked here. An entry that today's view gets wrong is a known failure
that names its finding (`walk.KNOWN`).
"""

import json
import subprocess
import time

import pytest

from jbus import work
from view import walk
from view.scene import Scene

ON_PAGE = ("role",)


BUILT = {}

ROUNDS = 3

SLOWER = 12

SHELLS = 18


def reference(folder):
    """The CPU seconds of fixed work of the kind the views do in this process, JSON written to
    files and read back: the yardstick of this machine. A runner whose cores are busy makes
    the views wait longer, and does not make them use more."""
    data = {f"k{n}": {"n": n, "text": "x" * 50, "list": list(range(20))} for n in range(400)}
    began = time.process_time()
    for n in range(40):
        file = folder / f"reference-{n % 5}.json"
        file.write_text(json.dumps(data))
        json.loads(file.read_text())
    return time.process_time() - began


def viewed(scene):
    """The three answers over the scene, the CPU seconds this process took for them, and the
    commands they started."""
    started = []
    start = subprocess.Popen.__init__

    def counted(self, args, *rest, **named):
        started.append(args)
        start(self, args, *rest, **named)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess.Popen, "__init__", counted)
        began = time.process_time()
        seen = {}
        for who in ("", work.T3, work.GITHUB):
            walk.silent(scene, who)
            seen[who] = walk.view(scene)
        took = time.process_time() - began
    return seen, took, started


@pytest.fixture
def walked(tmp_path, monkeypatch):
    """The walk's project and the three answers over it, with the CPU time this process took
    for them and the reference's, the least of `ROUNDS` rounds that run one of each in turn, so
    that a burst of load on the runner has to fall on every round to count, and the commands
    each round started. The first test that asks builds them, under the isolation every test
    has (the zone of `testing/jstack_fixtures.py` among it), and the tests after it read the
    same answers."""
    if not BUILT:
        scene = Scene(tmp_path, monkeypatch)
        made = walk.build(scene)
        (tmp_path / "reference").mkdir()
        took, yardstick, shells = [], [], []
        for _ in range(ROUNDS):
            yardstick.append(reference(tmp_path / "reference"))
            seen, cost, started = viewed(scene)
            took.append(cost)
            shells.append(started)
        BUILT["walk"] = made, seen, (min(took), min(yardstick), shells)
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


def test_the_walk_has_each_state_and_its_views_cost_few_references(walked):
    """The views are held to `SLOWER` times the reference in this process, where they take
    about 5 times it, and to the `SHELLS` commands a round they start: views built twice over
    start twice as many. Their shells are counted, not timed, since a loaded runner
    swells the CPU a shell takes to start (0.33 to 1.33 s for the views' shells on CI, against
    0.17 s at the desk) and leaves their number as it was."""
    made, _, (took, yardstick, shells) = walked
    pairs = walk.reached()
    assert set(made.rows) == set(pairs)
    assert {value for value, _ in pairs} == set(work.VALUES)
    assert len(made.threads) == 30
    assert set(made.items) == walk.states()["kind"]
    assert len(made.gates) == 12
    assert set(made.owners) == walk.states()["owner"]
    times = took / yardstick
    assert times < SLOWER, (
        f"the views took {took:.3f} CPU s, {times:.1f} times the reference's {yardstick:.4f} s,"
        f" {times / SLOWER:.1f} times the limit of {SLOWER}"
    )
    most = max(shells, key=len)
    assert len(most) <= SHELLS, f"the views started {len(most)} commands, not {SHELLS}: {most}"


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
    elif kind == "thread":
        for (value, thread), slug in made.rows.items():
            task = tasks.get(slug)
            if thread != name or not task:
                continue
            due = want.chip == walk.GONE and work.BY_VALUE[value].who == "crew"
            if task["gone"] != due:
                faults.append(f"{slug}: gone is {task['gone']}, not {due}")
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
        if not want.broken and file in listed:
            faults.append(f"{file} is {name} and is listed as unwell")
        elif want.broken and (file, name) not in unwell:
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
    elif kind == "owner":
        slug, (home, retired) = made.owners[name], want.home
        task = tasks.get(slug)
        if not task or task["rank"] != want.rank:
            faults.append(f"{slug}: rank {task and task['rank']}, not {want.rank}")
        elif (task["home"], task["retired"]) != want.home:
            faults.append(f"{slug}: under {task['home']!r}, retired {task['retired']!r}")
        groups = {one["name"]: one["open"] for one in project["homes"]}
        if project["homes"][0]["name"] != "" or groups.get(home, 0) < 1:
            faults.append(f"the summary's homes {project['homes']} do not count {slug} as {home!r}")
        if retired and retired in groups:
            faults.append(f"the retired scope {retired} is a home of the summary")
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
