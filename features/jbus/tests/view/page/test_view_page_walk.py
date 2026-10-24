"""The state walk in the browser: the page draws the walk's project (`view.walk`) with the row
text and the chips `SURFACES` names, for a pass that T3 Code did not answer.

The test opens the project's page and the overview of every project once each. It checks each
entry of `SURFACES` that only the page can show: a row of In progress with its state's name, a
chip on it, a row for a thread out with no task, and what the overview row says. A task that is
in Needs you is drawn there only, so In progress has no row for it. The entries
that today's page gets wrong are the ones `walk.KNOWN` marks for the page, and the test fails
when that set changes, so a fix removes its mark.
"""

import pytest

from jbus import work
from view import walk
from view.page.browser import BROWSES, LAUNCH, PATIENCE, look

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


LIVENESS_CHIPS = ("thread hung", "thread quiet", walk.GONE)


def faults(key, made, answer, rows, overview):
    """What the page draws for the state of `key` that `SURFACES` says it must not."""
    kind, name = key
    want = walk.SURFACES[key]
    tasks = {one["slug"]: one for one in answer["tasks"]}
    asked = {one["slug"] for one in answer["needs"]}
    found = []
    if kind == "value":
        for (value, _), slug in made.rows.items():
            task = tasks.get(slug)
            if value != name or not task:
                continue
            drawn = slug in rows
            if drawn != (want.row and slug not in asked):
                found.append(f"{slug}: a row of In progress is {drawn}")
            elif drawn and rows[slug]["state"] != task["state"]["name"]:
                found.append(f"{slug}: reads {rows[slug]['state']!r}")
        unplaced = [
            slug for (value, _), slug in made.rows.items() if value == name and slug in tasks
        ]
        named = "place" in overview and all(slug in overview for slug in unplaced)
        if want.unplaced and not (unplaced and named):
            found.append(f"the overview row does not name what it cannot place: {overview!r}")
    elif kind == "thread":
        for (value, thread), slug in made.rows.items():
            if thread != name or not rows.get(slug, {"open": ""})["open"].startswith("task:"):
                continue
            due = {want.chip} if want.chip and value != thread else set()
            if want.chip == walk.GONE and work.BY_VALUE[value].who != "crew":
                due = set()
            chips = set(rows[slug]["chips"]) & set(LIVENESS_CHIPS)
            if chips != due:
                found.append(f"{slug}: chips {sorted(chips)}, not {sorted(due)}")
    elif kind == "role":
        idle = walk.SURFACES["home", "ended with work out"].row
        for (role, liveness), slug in made.threads.items():
            drawn = slug in rows
            due = liveness != "ended" or (role == "home" and idle)
            if role == name and drawn != (want.row and due):
                found.append(f"{slug}: a row of In progress is {drawn}")
    elif kind == "owner":
        slug = made.owners[name]
        retired = f"home {want.home[1]} retired, so under the root"
        if (slug in rows) != want.row:
            found.append(f"{slug}: a row of In progress is {slug in rows}")
        elif (retired in rows[slug]["chips"]) != bool(want.home[1]):
            found.append(f"{slug}: chips {rows[slug]['chips']}")
    elif kind == "silent" and name == work.T3:
        bare = [slug for slug, one in rows.items() if one["open"].startswith("task:")]
        bare = [
            slug for slug in bare if not any(c.startswith(want.chip) for c in rows[slug]["chips"])
        ]
        if bare:
            found.append(f"{len(bare)} rows have no {want.chip!r} chip, {bare[0]} first")
        if name not in overview:
            found.append(f"the overview row does not name {name}: {overview!r}")
    return found


def test_the_page_draws_each_state_of_the_walk_where_surfaces_says(scene, tmp_path):
    made = walk.build(scene)
    walk.silent(scene, work.T3)
    _, answer = walk.view(scene)
    seen = look(scene, tmp_path, budget=20000)
    assert seen["errors"] == []
    rows = {one["slug"]: one for one in seen["prog"]}
    assert len(rows) == len(seen["prog"])
    shown = look(scene, tmp_path, route="#/")
    assert shown["errors"] == []
    (one,) = shown["stack"]["rows"]
    overview = " ".join([one["name"], one["why"], *one["counts"], one["said"] or ""])
    kinds = ("value", "thread", "role", "silent", "owner")
    checked = [key for key in walk.SURFACES if key[0] in kinds]
    wrong = {key: said for key in checked if (said := faults(key, made, answer, rows, overview))}
    known = {key for key, (_, where) in walk.KNOWN.items() if "page" in where}
    fixed = sorted(known - set(wrong))
    assert fixed == [], f"the page now draws {fixed} right: take each out of walk.KNOWN"
    new = {key: said for key, said in wrong.items() if key not in known}
    assert new == {}, f"the page draws these wrong, and walk.KNOWN does not say so: {new}"
