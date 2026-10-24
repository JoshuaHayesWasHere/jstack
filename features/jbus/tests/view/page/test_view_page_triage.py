"""The triage tab, `#/triage`: Yours and Wrong across every project, and one calm line.

Its budgets are scout C's first three (jview-ux-c), with its fourth for the phone. Every text on
the tab's first screen sits in Yours (`ask`), Wrong (`wrong`) or the calm line (`calm`), and
the calm line is at most 25 words. A quiet project adds no words, so three and sixteen quiet
projects give the tab the same count. Yours and Wrong show at most 6 rows each, and the first
screen at most 180 words, at a desk's width, at 900 and at a phone's. Every entry of the
scene's `wrong` has its row in the first 844 px of a phone. The tab in the header counts what
is Josh's, and so does the drawer of what waits on him in each project.

The scenes are the budget tests' `busy` and `many`, and `quiet` with 3 or 16 quiet projects.
"""

import re

import pytest

from view.page.browser import BROWSES, LAUNCH, PATIENCE, PHONE, gated, look
from view.page.test_view_page_budgets import EXTRA, SCENES, SCREENS, a_day_old, another
from view.scene import Scene, Served, stacked

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 60)]


ROWS, WORDS, CALM = 6, 180, 25


ROLES = ("ask", "wrong", "calm")


AGE = re.compile(r"\S · (\d+m|\d+h\d\d|\d+d|new|no time kept)$")


QUIET = (*EXTRA, "nursery", "oven", "pier")


PROBE = """window.__errs = [];
window.addEventListener("error", function (e) { window.__errs.push(String(e.message)); });
window.addEventListener("load", function () { setTimeout(function () {
  var vh = window.innerHeight, vw = window.innerWidth;
  var all = function (sel, el) { return [].slice.call((el || document).querySelectorAll(sel)); };
  var text = function (el) { return el ? el.textContent.replace(/\\s+/g, " ").trim() : ""; };
  var shown = function (el) {
    return el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true });
  };
  var box = function (el) {
    var b = el.getBoundingClientRect();
    return [b.left, b.top, b.width, b.height].map(Math.round);
  };
  var onScreen = function (b) {
    return b.width > 0 && b.height > 0 && b.top < vh && b.bottom > 0 && b.left < vw;
  };
  var main = document.querySelector("main"), atoms = [];
  var walk = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
  while (walk.nextNode()) {
    var node = walk.currentNode, p = node.parentElement;
    if (!/\\S/.test(node.textContent) || !shown(p)) continue;
    var range = document.createRange();
    range.selectNodeContents(node);
    if (![].some.call(range.getClientRects(), onScreen)) continue;
    var role = p.closest("[data-role]");
    atoms.push({ text: text({ textContent: node.textContent }),
      role: role ? role.getAttribute("data-role") : "" });
  }
  var row = function (r) {
    var btn = r.querySelector(".btn");
    return { text: text(r), box: box(r), meta: text(r.querySelector(".nm")),
      verb: text(btn), href: btn ? btn.getAttribute("href") : "" };
  };
  var parts = {};
  all("main [data-role]").filter(shown).forEach(function (sec) {
    parts[sec.getAttribute("data-role")] = { text: text(sec), head: text(sec.querySelector("h2 b")),
      rows: all("li", sec).filter(shown).map(row),
      tail: all(".tail", sec).filter(shown).map(text) };
  });
  var tab = document.getElementById("tri"), drawer = document.getElementById("drawer");
  var out = { errors: window.__errs, hash: location.hash, atoms: atoms, parts: parts,
    drawer: drawer.open ? text(document.getElementById("dw-title")) : "", tab: null };
  if (tab && shown(tab)) {
    out.tab = { text: text(tab), count: text(tab.querySelector("b")),
      href: tab.getAttribute("href"), current: tab.getAttribute("aria-current") || "" };
  }
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify(out);
  (window.top === window ? document : window.top.document).body.appendChild(pre);
}, window.__at); });
"""


def quiet(scene, n):
    """`pantry` and `larder` beside `demo`, a CI whose every run passed, and `n` projects
    that run well."""
    stacked(scene)
    scene.github(runs=[("oat-bowl", "completed", "success"), ("oat-milk", "completed", "success")])
    for at, name in enumerate(QUIET[:n]):
        another(scene, name, at, calm=True)
    a_day_old(scene)


def asked(scene):
    """The busy day, with three questions jbus holds, which go ahead on their default."""
    SCENES["busy"](scene)
    gated(scene)


MADE = SCENES | {
    "asked": asked,
    "quiet-3": lambda scene: quiet(scene, 3),
    "quiet-16": lambda scene: quiet(scene, 16),
}


def looked(root, name, wide, routes=("#/triage",)):
    """What the probe found on each route, and `/stack.json` as the server gave it."""
    with pytest.MonkeyPatch.context() as patch:
        scene = Scene(root, patch)
        MADE[name](scene)
        served = Served(scene)
        try:
            seen = {
                route: look(
                    scene,
                    root / f"look-{at}",
                    route=route,
                    screen=SCREENS[wide],
                    port=served.port,
                    at=1500,
                    budget=8000,
                    script=PROBE,
                )
                for at, route in enumerate(routes)
            }
            stack = served.json("/stack.json")
        finally:
            served.close()
    return seen | {"stack": stack}


@pytest.fixture(scope="module")
def views(tmp_path_factory):
    made = {}

    def view(name, wide):
        if (name, wide) not in made:
            made[name, wide] = looked(tmp_path_factory.mktemp(f"{name}-{wide}"), name, wide)
        return made[name, wide]

    return view


EVERY = [
    pytest.param(name, wide, id=f"{name}-{wide}") for name in ("busy", "many") for wide in SCREENS
]


def words(atoms):
    return sum(len(one["text"].split()) for one in atoms)


@pytest.mark.parametrize(("name", "wide"), EVERY)
def test_every_text_of_the_first_screen_is_an_ask_a_wrong_or_the_calm_line(views, name, wide):
    seen = views(name, wide)["#/triage"]
    assert seen["errors"] == []
    assert seen["atoms"], "the tab drew nothing"
    assert [one["text"] for one in seen["atoms"] if one["role"] not in ROLES] == []
    calm = seen["parts"]["calm"]["text"]
    assert len(calm.split()) <= CALM, calm


@pytest.mark.parametrize(("name", "wide"), EVERY)
def test_yours_and_wrong_show_at_most_6_rows_and_the_first_screen_180_words(views, name, wide):
    seen = views(name, wide)["#/triage"]
    rows = {role: len(seen["parts"].get(role, {"rows": []})["rows"]) for role in ("ask", "wrong")}
    assert {role: n for role, n in rows.items() if n > ROWS} == {}
    assert rows["ask"] and rows["wrong"], rows
    assert words(seen["atoms"]) <= WORDS, words(seen["atoms"])


@pytest.mark.parametrize("wide", list(SCREENS))
def test_a_quiet_project_adds_no_words(views, wide):
    few, many = views("quiet-3", wide), views("quiet-16", wide)
    assert len(many["stack"]["projects"]) - len(few["stack"]["projects"]) == 13
    counts = [words(one["#/triage"]["atoms"]) for one in (few, many)]
    assert counts[0] == counts[1], [one["#/triage"]["atoms"] for one in (few, many)]


@pytest.mark.parametrize("name", ["busy", "many"])
def test_every_wrong_fact_of_the_scene_is_in_the_first_844_px_of_a_phone(views, name):
    seen = views(name, 390)
    wrong = seen["stack"]["wrong"]
    assert wrong, "the scene has nothing wrong"
    rows = seen["#/triage"]["parts"]["wrong"]["rows"]
    high = PHONE[1]
    missing = [
        (one["subj"], one["cause"])
        for one in wrong
        if not any(
            one["subj"] in row["text"] and row["box"][1] + row["box"][3] <= high for row in rows
        )
    ]
    assert missing == []


def test_each_row_has_its_subject_where_it_is_its_age_and_its_verb_oldest_first(views):
    seen = views("busy", 1440)
    parts, stack = seen["#/triage"]["parts"], seen["stack"]
    for row in parts["ask"]["rows"] + parts["wrong"]["rows"]:
        assert row["verb"] and row["href"].startswith("#/"), row
        assert AGE.search(row["meta"]), row
    first = stack["needs"][0]
    assert first["subj"] in parts["ask"]["rows"][0]["text"]
    assert f"{first['project']}" in parts["ask"]["rows"][0]["text"]
    assert stack["wrong"][0]["subj"] in parts["wrong"]["rows"][0]["text"]


def test_same_kind_approvals_are_one_row_and_the_defaults_one_tail_line(views):
    seen = views("asked", 1440)
    parts, stack = seen["#/triage"]["parts"], seen["stack"]
    approvals = {}
    for need in stack["needs"]:
        if need["verb"].startswith("Approve"):
            approvals.setdefault((need["project"], need["kind"]), []).append(need)
    batched = {key: len(group) for key, group in approvals.items() if len(group) > 1}
    assert batched, approvals
    verbs = [row["verb"] for row in parts["ask"]["rows"]]
    for n in batched.values():
        assert verbs.count(f"Approve {n}") >= 1, verbs
    assert all(
        row["href"].endswith("/you/approve")
        for row in parts["ask"]["rows"]
        if re.fullmatch(r"Approve \d+", row["verb"])
    ), parts["ask"]["rows"]
    proceeds = stack["proceeds"]
    assert proceeds
    (tail,) = [one for one in parts["ask"]["tail"] if "default" in one]
    assert [need["due"] for need in proceeds if need["due"]], proceeds
    assert re.fullmatch(
        rf"{len(proceeds)} take their default if you say nothing, the first at \d\d:\d\d ›", tail
    )


def test_the_tab_counts_what_is_yours_and_says_where_it_is(views):
    seen = views("busy", 1440)["#/triage"]
    stack = views("busy", 1440)["stack"]
    tab = seen["tab"]
    assert tab and tab["href"] == "#/triage" and tab["current"] == "page"
    assert int(tab["count"]) == len(stack["needs"])
    assert int(seen["parts"]["ask"]["head"]) == len(stack["needs"])


def test_the_tab_count_is_the_sum_of_each_projects_drawer_of_what_waits_on_you(tmp_path):
    with pytest.MonkeyPatch.context() as patch:
        scene = Scene(tmp_path, patch)
        SCENES["busy"](scene)
        served = Served(scene)
        try:
            projects = [one["name"] for one in served.json("/stack.json")["projects"]]
            how = {"port": served.port, "at": 1500, "budget": 8000, "script": PROBE}
            tab = look(scene, tmp_path / "tab", route="#/triage", **how)["tab"]
            drawers = {
                name: look(scene, tmp_path / name, route=f"#/{name}/you", **how)["drawer"]
                for name in projects
            }
        finally:
            served.close()
    counted = {name: int(re.match(r"\d+", said)[0]) for name, said in drawers.items()}
    assert all(said.endswith("on you") for said in drawers.values()), drawers
    assert int(tab["count"]) == sum(counted.values()), (tab, counted)


def test_the_tab_is_in_the_header_of_every_route(views, tmp_path):
    seen = views("busy", 1440)
    with pytest.MonkeyPatch.context() as patch:
        scene = Scene(tmp_path, patch)
        SCENES["busy"](scene)
        served = Served(scene)
        try:
            how = {"port": served.port, "at": 1500, "budget": 8000, "script": PROBE}
            tabs = {
                route: look(scene, tmp_path / str(at), route=route, **how)["tab"]
                for at, route in enumerate(("#/", "#/demo"))
            }
        finally:
            served.close()
    assert {route: (tab["href"], tab["current"]) for route, tab in tabs.items()} == {
        "#/": ("#/triage", ""),
        "#/demo": ("#/triage", ""),
    }
    assert tabs["#/"]["count"] == seen["#/triage"]["tab"]["count"]


def test_proposed_items_are_not_batched_since_each_opens_its_own_drawer(tmp_path):
    """Only rows to approve have one list that holds them all. Two proposed work items of one
    project stay two rows, each opening its own item."""

    def items(nth, body):
        made = [
            {
                "project": "demo",
                "kind": "item",
                "key": f"item:{one}",
                "subj": one,
                "what": one,
                "why": "",
                "since": body["at"],
                "verb": "Approve",
                "default": "",
                "risk": "reversible",
                "open": f"#/demo/item/{one}",
                "due": None,
                "item": one,
                "seen": "",
                "slug": "",
                "home": "",
                "answerable": False,
                "unblocks": [],
            }
            for one in ("I-1", "I-2")
        ]
        return body | {"needs": made}

    with pytest.MonkeyPatch.context() as patch:
        scene = Scene(tmp_path, patch)
        SCENES["busy"](scene)
        seen = look(scene, tmp_path / "look", route="#/triage", script=PROBE, at=1500, alter=items)
    rows = seen["parts"]["ask"]["rows"]
    assert [(row["verb"], row["href"]) for row in rows] == [
        ("Approve", "#/demo/item/I-1"),
        ("Approve", "#/demo/item/I-2"),
    ]
