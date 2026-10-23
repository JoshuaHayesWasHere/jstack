"""The budgets of the page's first screens that hold whatever the layout: scout C's "Budgets as
tests" (jview-ux-c), less the ones that belong to one layout.

Each budget is checked on two scenes, at a desk's width, at 900 and at a phone's. `busy` is the
tests' busy day in six projects: every step of the lineup in `demo`, a crewmate that hung, a
failing CI run, gates and noticed lines, and three more projects beside `stacked`'s two. `many`
is the same with sixteen projects. A third scene, `calm`, has nothing wrong in it.

A scene is opened twice at each width, on every project, `#/`, and on `demo`'s page, `#/demo`.
The probe opens every drawer it can reach from there, and on `#/` it taps each thing on the
first screen once. Each test reads those two looks, which a test before it may have made.

A budget today's page breaks is in `KNOWN`, with the unit that fixes it. Its test is marked as
a strict xfail, so the suite stays green and the fix that makes it pass takes the mark off. The
mark expects the budget's own assertion and nothing else, so a runner with no browser, or a
probe that broke, still fails the test.
"""

import json
import re
import shutil

import pytest

from view.page.browser import (
    BROWSES,
    DESK,
    LAUNCH,
    PATIENCE,
    PHONE,
    TODAY,
    a_day_of_threads,
    lineup,
    look,
)
from view.scene import (
    Scene,
    Served,
    a_noticed,
    ago,
    et,
    iso,
    item,
    judge_row,
    row,
    stacked,
)

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


SCREENS = {1440: DESK, 900: (900, 900), 390: PHONE}


FIRST_WORDS, ALL_WORDS = 120, 300


HEADER = 56


GAP = 6


EXTRA = (
    "bakery",
    "cellar",
    "dairy",
    "farm",
    "garden",
    "hive",
    "icehouse",
    "jetty",
    "kiln",
    "loft",
    "mill",
    "orchard",
    "quarry",
)


SAME = (
    "transitions.jsonl",
    "events.jsonl",
    "main.json",
    "checks.json",
    "stall.json",
    "wake.json",
    "sent.json",
    "ci.jsonl",
    "ci-prs.jsonl",
)


def another(scene, name, n, calm=False):
    """A project like `pantry`: a task running, one waiting for a slot and one merged. Unless
    the scene is calm, every third has a task at a gate and every fourth a pull request whose
    check failed."""
    state = scene.state_dir / name
    state.mkdir()
    (scene.home_dir / name).mkdir()
    rows = [
        row(f"{name}-a", "running", thread=f"mcp:{name}-a"),
        row(f"{name}-b", "queued", why="no slot", since=et(ago(minutes=30))),
        row(f"{name}-c", "merged", pr="#2"),
    ]
    waits = []
    if not calm and n % 3 == 0:
        since = et(ago(minutes=70 + n))
        rows.append(row(f"{name}-d", "gate", why="a gate the Chef has", since=since))
        line = f"gate {name}-d: which way?"
        waits.append(item("row", f"row:{name}-d", line, minutes=70 + n, slug=f"{name}-d"))
    if not calm and n % 4 == 1:
        why = "wait: check has not passed"
        rows.append(row(f"{name}-e", "pr", pr="#7", checks="failed", why=why))
    (state / "queue.json").write_text(json.dumps(rows))
    lines = [judge_row(one, state) for one in rows]
    (state / "work.json").write_text(json.dumps({"at": iso(scene.now), "work": lines}))
    (state / "waiting-on-user.json").write_text(json.dumps(waits))


def a_day_old(scene):
    """Every project gets the files a project that has run for a day has, so the only red on
    the page is the red the scene means. Each project's merge.log names its repo, as jmerge's
    lines do."""
    status = json.loads((scene.state_dir / "status.json").read_text())
    for state in sorted(p.parent for p in scene.state_dir.glob("*/queue.json")):
        for name in SAME:
            if not (state / name).exists():
                shutil.copy(scene.state / name, state / name)
        for name, empty in (
            ("work.json", {"at": iso(scene.now), "work": []}),
            ("waiting-on-user.json", []),
        ):
            if not (state / name).exists():
                (state / name).write_text(json.dumps(empty))
        home = scene.home_dir / state.name
        home.mkdir(exist_ok=True)
        stamp = et(ago(minutes=5)).removesuffix(" ET")
        url = f"https://github.com/acme/{state.name}/pull/1"
        with (home / "merge.log").open("a") as log:
            log.write(f"{stamp} wait 1 {url}: check has not passed\n")
        status["projects"].setdefault(state.name, dict(status["projects"]["demo"]))
    scene.write("status.json", status, scene.state_dir)


def failing(scene):
    """demo's CI has a run that failed last on its branch. Every other repo's CI answers as
    the scene's stand-in does."""
    runs = json.loads((scene.root / "runs.json").read_text())
    bad = runs["workflow_runs"][0] | {
        "id": 599,
        "head_branch": "tea-saucer",
        "conclusion": "failure",
    }
    runs["workflow_runs"].append(bad)
    scene.write("runs-demo.json", runs, scene.root)
    scene.script(
        "gh",
        f'printf "%s\\n" "$*" >> {scene.calls}\n'
        'case "$2" in\n'
        f"*acme/demo/actions/runs*) cat {scene.root}/runs-demo.json ;;\n"
        f"*actions/runs*) cat {scene.root}/runs.json ;;\n"
        f"*check-runs*) cat {scene.root}/check-runs.json ;;\n"
        f"*pulls/*) cat {scene.root}/pull.json ;;\n"
        "*) exit 1 ;;\nesac\n",
    )


def busy(scene, projects=6):
    lineup(scene, TODAY)
    stacked(scene)
    a_day_of_threads(scene)
    a_noticed(scene, *((f"oat-{n}", "new", 10 + n, {}) for n in range(12)))
    for n, name in enumerate(EXTRA[: projects - 3]):
        another(scene, name, n)
    a_day_old(scene)
    failing(scene)


def calm(scene):
    """Projects that run well, and a CI whose every run passed."""
    stacked(scene)
    scene.github(runs=[("oat-bowl", "completed", "success"), ("oat-milk", "completed", "success")])
    for n, name in enumerate(EXTRA[:3]):
        another(scene, name, n, calm=True)
    a_day_old(scene)


SCENES = {"busy": busy, "many": lambda scene: busy(scene, 16), "calm": calm}


EVERY = [(scene, wide) for scene in ("busy", "many") for wide in SCREENS]


KNOWN = {
    (budget, scene, wide): unit
    for budget, unit, broken in (
        ("twice", "jv-one-place", [(scene, wide) for scene, wide in EVERY if wide != 390]),
        ("hung", "jv-needs-from-work", EVERY),
        ("waits", "jv-needs-from-work", EVERY),
        ("drawers", "jv-triage", EVERY),
        ("header", "jv-triage", [("busy", 390), ("many", 390)]),
        ("crumb", "jv-triage", EVERY),
        ("words", "jv-triage", EVERY),
    )
    for scene, wide in broken
}


def cases(budget, scenes=("busy", "many"), widths=tuple(SCREENS)):
    """The scenes and widths a budget is checked on, each marked where today's page breaks
    it."""
    made = []
    for scene in scenes:
        for wide in widths:
            unit = KNOWN.get((budget, scene, wide))
            why = f"today's page breaks it, and {unit} fixes it"
            marks = (
                [pytest.mark.xfail(strict=True, raises=AssertionError, reason=why)] if unit else []
            )
            made.append(pytest.param(scene, wide, marks=marks, id=f"{scene}-{wide}"))
    return made


@pytest.fixture(scope="module")
def views(tmp_path_factory):
    """The looks of a scene at a width, each made once in the module, by the first test that
    asks for it."""
    made = {}

    def view(scene, wide):
        if (scene, wide) not in made:
            made[scene, wide] = looked(tmp_path_factory.mktemp(f"{scene}-{wide}"), scene, wide)
        return made[scene, wide]

    return view


def looked(root, name, wide):
    """What the probe found on `#/` and on `#/demo`, what waits on the user in each project as
    the server gives it, and the slug of every row of the scene."""
    with pytest.MonkeyPatch.context() as patch:
        scene = Scene(root, patch)
        SCENES[name](scene)
        served = Served(scene)
        try:
            how = {"screen": SCREENS[wide], "port": served.port, "at": 1500}
            every = look(scene, root, route="#/", hops=True, budget=60000, **how)
            one = look(scene, root, budget=8000, **how)
            projects = sorted(p.parent.name for p in scene.state_dir.glob("*/queue.json"))
            waits = {p: len(served.json(f"/state.json?project={p}")["waiting"]) for p in projects}
        finally:
            served.close()
    slugs = {
        r["slug"] for q in scene.state_dir.glob("*/queue.json") for r in json.loads(q.read_text())
    }
    return {"#/": every, "#/demo": one, "waits": waits, "slugs": slugs}


def drawers(seen):
    return [(route, one) for route in ("#/", "#/demo") for one in seen[route]["opened"]]


@pytest.mark.parametrize(("scene", "wide"), cases("twice"))
def test_no_slug_shows_twice_on_a_first_screen(views, scene, wide):
    seen = views(scene, wide)
    twice = {}
    for route in ("#/", "#/demo"):
        text = "\n".join(seen[route]["screen"])
        found = {
            s: len(re.findall(rf"(?<![\w-]){re.escape(s)}(?![\w-])", text)) for s in seen["slugs"]
        }
        twice[route] = sorted(s for s, n in found.items() if n > 1)
    assert twice == {"#/": [], "#/demo": []}


@pytest.mark.parametrize(("scene", "wide"), cases("hung"))
def test_one_tap_on_every_project_opens_a_drawer_that_names_the_hung_thread(views, scene, wide):
    """demo's crewmate on jam-jar hung. Some one thing on the first screen of `#/` opens a
    drawer that names it and says it hung."""
    hops = views(scene, wide)["#/"]["hops"]
    assert hops, "the first screen of #/ has nothing to tap"
    reached = [
        h["to"]
        for h in hops
        if h["open"] and "jam-jar" in h["said"] and "hung" in h["said"].lower()
    ]
    assert reached, [(h["to"], h["title"]) for h in hops]


def count(said):
    found = re.match(r"\d+", said)
    return int(found[0]) if found else None


@pytest.mark.parametrize(("scene", "wide"), cases("waits"))
def test_every_screen_counts_the_same_waits(views, scene, wide):
    """The count on every project is the sum of what waits in each project. On demo's page,
    its band and its drawer of what waits on you give the one count of what waits in demo."""
    seen = views(scene, wide)
    drawer = [one for one in seen["#/demo"]["opened"] if one["target"].split(":")[0] == "you"]
    assert drawer, [one["target"] for one in seen["#/demo"]["opened"]]
    every, band, you = (
        count(seen["#/"]["needs"]["count"]),
        count(seen["#/demo"]["needs"]["count"]),
        count(drawer[0]["title"]),
    )
    assert (every, band, you) == (sum(seen["waits"].values()), you, seen["waits"]["demo"])


@pytest.mark.parametrize(("scene", "wide"), cases("drawers"))
def test_every_drawer_but_help_is_short(views, scene, wide):
    long = [
        (route, one["target"], one["first"], one["words"])
        for route, one in drawers(views(scene, wide))
        if not one["target"].startswith("help")
        and (one["first"] > FIRST_WORDS or one["words"] > ALL_WORDS)
    ]
    assert long == []


@pytest.mark.parametrize(("scene", "wide"), cases("header", widths=(390,)))
def test_the_header_of_a_phone_is_no_taller_than_56_px(views, scene, wide):
    seen = views(scene, wide)
    high = {route: seen[route]["header"]["box"][3] for route in ("#/", "#/demo")}
    assert {route: px for route, px in high.items() if px > HEADER} == {}


def touches(crumb, tag):
    """Whether the last link of a breadcrumb and the tag after it share a line with less
    than `GAP` px between them."""
    left, top, wide, high = crumb
    beside = top < tag[1] + tag[3] and tag[1] < top + high
    return beside and -GAP < tag[0] - (left + wide) < GAP


@pytest.mark.parametrize(("scene", "wide"), cases("crumb"))
def test_no_drawer_runs_its_breadcrumb_into_its_tag(views, scene, wide):
    run = [
        (route, one["target"])
        for route, one in drawers(views(scene, wide))
        if one["crumb"] and one["tag"] and touches(one["crumb"], one["tag"])
    ]
    assert run == []


def paints(seen):
    return [
        (route, paint)
        for route in ("#/", "#/demo")
        for paint in seen[route]["paints"]
        + [p for one in seen[route]["opened"] for p in one["paints"]]
    ]


@pytest.mark.parametrize(("scene", "wide"), cases("words"))
def test_every_due_or_missed_mark_says_it_in_words(views, scene, wide):
    """A dot, bar or swatch painted due or missed holds the word for it, and is not colour
    alone."""
    bare = {
        (route, paint["what"]) for route, paint in paints(views(scene, wide)) if not paint["words"]
    }
    assert sorted(bare) == []


@pytest.mark.parametrize(("scene", "wide"), cases("calm", scenes=("calm",)))
def test_a_calm_scene_paints_nothing_missed(views, scene, wide):
    """A legend's swatch names the colour and is no state, so it is not counted. The busy
    scene at the same width paints missed, so the probe sees it when it is there."""
    assert any(p["tone"] == "missed" for _, p in paints(views("busy", wide)))
    found = paints(views(scene, wide))
    missed = {(route, p["what"]) for route, p in found if p["tone"] == "missed" and not p["key"]}
    assert sorted(missed) == []
