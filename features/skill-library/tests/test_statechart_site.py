"""`statechart site` writes one page that explores every committed chart: each chart and each of
its states is on it, it fetches nothing when viewed, and it shows each chart's stories."""

import contextlib
import fcntl
import html
import importlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import pytest

from statechart_support import DOOR_MAP, lib, needs_tlc, node, read, run_door, write
from testing.paths import REPO

chart_site = importlib.import_module("statechart.site")

READ_SET = ("features/*/spec/*-statechart/", "features/*/src/", "features/home/docs/charts/")

CHARTS = sorted((REPO / "features").glob("*/spec/*-statechart/chart.mmd"))
LEAF = re.compile(r'^\s*state "([^"]*)" as (\w+)\s*$', re.M)


def declared_states(chart):
    """Each state the chart declares, as `id: caption`, its legend left out: its groups and the
    entry for a state that breaks a rule (`legendWrong`)."""
    return {
        state_id: re.sub(r"\s+", " ", re.sub(r"<br\s*/?>", " ", caption)).strip()
        for caption, state_id in LEAF.findall(read(chart))
        if not state_id.startswith("legend")
    }


FLOW = REPO / "features" / "home" / "docs" / "charts" / "flow.toml"


def site(root, out, *extra):
    return node("statechart", ["site", "--out", str(out), "--root", str(root), *extra], root)


def test_the_page_opens_on_a_map_of_every_chart_and_how_they_hand_off(tmp_path):
    out = tmp_path / "index.html"
    shutil.copy(FLOW, tmp_path / "flow.toml")
    r = site(REPO, out)
    assert r.returncode == 0, r.stderr
    page = read(out)
    first = re.search(r'<button class="tab"[^>]*>', page)[0]
    assert 'data-view="overview"' in first and 'aria-selected="true"' in first
    flow = re.search(r'<section class="flow-panel".*?</section>', page, re.S)[0]
    things = {
        "RowLife": "A row in the queue",
        "ThreadLife": "A crew&#x27;s thread",
        "PrVerdict": "A pull request at jmerge",
        "FlowToday": "A pair of rows on their way to main",
        "MainRed": "A red main",
        "HomeTreeToday": "A tree of homes",
        "TellOnce": "A thing jbus does once",
        "MainFix": "The fix and revert jbus files",
        "CrewProof": "A crew&#x27;s proof on its brief",
    }
    for name, thing in things.items():
        assert f'data-chart="{name}"' in flow and thing in flow, name
    handoffs = re.findall(r"<li>(.*?)</li>", flow)
    assert len(handoffs) >= 5
    for item in handoffs:
        ends = re.findall(r'class="go" data-chart="(\w+)"', item)
        assert len(ends) == 2 and ends[0] != ends[1], item
    for name in things:
        assert re.search(rf'<figure class="overview" data-chart="{name}">', page), name
        assert page.index(f'data-chart="{name}" hidden>') < page.index(
            f'<figure class="overview" data-chart="{name}">'
        )


def test_a_hand_off_to_a_group_a_chart_does_not_have_stops_the_page(tmp_path):
    folder = lamp(tmp_path, "")
    flow = tmp_path / "flow.toml"
    write(flow, '[[chart]]\nname = "Lamp"\nthing = "A lamp"\n')
    write(
        folder / "chart.mmd", CHART.replace("  class off group0\n", LEGEND + "  class off group0\n")
    )
    assert site(tmp_path, tmp_path / "index.html", "--flow", str(flow)).returncode == 0
    write(
        flow,
        read(flow) + '[[handoff]]\nfrom = "Lamp: Dark"\nto = "Lamp: Dark"\nsays = "x"\n',
    )
    r = site(tmp_path, tmp_path / "index.html", "--flow", str(flow))
    assert r.returncode == 2
    assert "the group 'Dark' of Lamp, which has no such group; its groups: Dark room" in r.stderr


def test_the_page_holds_each_committed_chart_and_each_of_its_states(tmp_path):
    out = tmp_path / "charts" / "index.html"
    r = site(REPO, out)
    assert r.returncode == 0, r.stderr
    page = read(out)
    names = {c.parent.name.removesuffix("-statechart") for c in CHARTS}
    assert names >= {"HomeTreeToday", "RowLife", "MainRed", "ThreadLife", "PrVerdict", "FlowToday"}
    for chart in CHARTS:
        name = chart.parent.name.removesuffix("-statechart")
        assert f'class="tab" role="tab" data-chart="{name}"' in page
        assert f'<section class="chart-panel" data-chart="{name}"' in page
        states = declared_states(chart)
        assert states, chart
        for state_id, caption in states.items():
            assert page.count(f'id="{name}-{state_id}"') == 1, (name, state_id)
            assert html.escape(caption, quote=True) in page or caption in page, (name, caption)
    total = sum(len(declared_states(c)) for c in CHARTS)
    assert r.stdout == f"wrote {out}: {len(CHARTS)} charts, {total} states\n"


GROUP_MOST = 15


REGROUP_IN = {"TellOnce-statechart": "st-tellonce-groups"}
"""A chart still to be regrouped, with the queued row that regroups it: strict, so the entry
goes once the chart passes."""


@pytest.mark.parametrize(
    "chart",
    [
        pytest.param(
            chart,
            marks=pytest.mark.xfail(strict=True, reason=f"regrouped in {REGROUP_IN[name]}")
            if (name := chart.parent.name) in REGROUP_IN
            else (),
        )
        for chart in CHARTS
    ],
    ids=lambda chart: chart.parent.name,
)
def test_each_charts_groups_hold_few_enough_states_to_find_one_and_none_is_mixed(chart):
    """A reader finds a state by its group's color: a group of more than GROUP_MOST states says
    little about where a state sits, and a mixed state is gray, in no group at all."""
    summary = json.loads(read(chart.parent / "summary.json"))
    big = [
        f"{g['name']} ({g['states']})" for g in summary["chartGroups"] if g["states"] > GROUP_MOST
    ]
    assert not big, f"{chart.parent.name} has groups over {GROUP_MOST} states: {', '.join(big)}"
    assert summary["mixedGroups"] == [], f"{chart.parent.name} has mixed states"


def ways_out(chart):
    """Each region of the chart as it is drawn: each state's caption, the composites around it
    named first, and the labels of the arrows drawn out of it. An arrow from a composite's border
    leaves from every state inside it."""
    _, tree, _, _ = chart_site.read_tree(read(chart))
    composites = chart_site.composites_by_id(tree)

    def inside(node, around):
        for part in node["parts"]:
            for child in part["children"]:
                if child.get("leaf"):
                    yield child["id"], lib.unwrap(": ".join([*around, child["caption"]]))
                else:
                    yield from inside(child, [*around, child["caption"]])

    for _, part in chart_site.regions_of(tree):
        named = dict(inside({"parts": [part]}, []))
        out = {state_id: [] for state_id in named}
        steps = []

        def walk(p, steps=steps):
            steps.extend(p["steps"])
            for child in p["children"]:
                for sub in child.get("parts", []):
                    walk(sub)

        walk(part)
        for s in steps:
            if s["from"] == "[*]":
                continue
            sources = (
                [i for i, _ in inside(composites[s["from"]], [])]
                if s["from"] in composites
                else [s["from"]]
            )
            for source in sources:
                out[source].append(lib.unwrap(s["label"]))
        yield {named[i]: labels for i, labels in out.items()}


def stalls(chart):
    """What the chart draws that reads as a stall: a state with no arrow out that summary.json
    does not name final, or an arrow with no label. A summary.json with no `final` was written by
    a from-spec that drew no way out of a state the model can leave, so the fault is the drawing,
    and the one fix is to draw it again."""
    summary = json.loads(read(chart.parent / "summary.json"))
    name = chart.parent.name
    if "final" not in summary:
        command = summary.get("drawnFrom", {}).get("command", "statechart from-spec")
        return [
            f"{name}/summary.json names no final state, so an older from-spec drew it, one that"
            f" drew no way out of a state the model can leave: draw it again, in"
            f" {chart.parent.parent.relative_to(chart.parents[4])}, with {command}"
        ]
    final = set(summary["final"])
    out = []
    for region in ways_out(chart):
        dead = sorted(s for s, labels in region.items() if not labels and s not in final)
        if dead:
            out.append(f"{name} draws no way out of: {'; '.join(dead)}")
        bare = sorted(s for s, labels in region.items() if any(not label for label in labels))
        if bare:
            out.append(f"{name} has an arrow with no label out of: {bare}")
    return out


@pytest.mark.parametrize("chart", CHARTS, ids=lambda chart: chart.parent.name)
def test_each_state_but_a_final_one_shows_an_arrow_out_that_says_who_takes_it(chart):
    """A state drawn with no arrow out reads as a stall. Each state the model can leave shows one
    way out, labelled, and only a state with no way out in the model, which summary.json names
    final, ends a path. A state where a rule broke is no exception: from-spec draws from the whole
    model, so a bug state the model can leave shows its way out, and one it cannot is final."""
    assert not stalls(chart), "\n".join(stalls(chart))


def test_a_chart_drawn_before_each_state_kept_a_way_out_is_told_to_draw_it_again(tmp_path):
    """The model PRs drawn before from-spec kept a way out of each state (#1702) failed here
    naming their bug states, and each crew hand-patched its chart; drawing it again was the fix.
    A dead state the model can leave still fails, and one summary.json names final passes."""
    folder = lamp(tmp_path, "")
    write(folder / "chart.mmd", CHART.replace("  on --> off : you flip it back\n", ""))
    drawn = {"command": "statechart from-spec Lamp.tla --expect-broken NeverDark"}
    write(folder / "summary.json", json.dumps({"drawnFrom": drawn}))
    assert stalls(folder / "chart.mmd") == [
        "Lamp-statechart/summary.json names no final state, so an older from-spec drew it, one"
        " that drew no way out of a state the model can leave: draw it again, in"
        f" features/lamp/spec, with {drawn['command']}"
    ]
    write(folder / "summary.json", json.dumps({"final": [], "drawnFrom": drawn}))
    assert stalls(folder / "chart.mmd") == ["Lamp-statechart draws no way out of: On"]
    write(folder / "summary.json", json.dumps({"final": ["On"], "drawnFrom": drawn}))
    assert stalls(folder / "chart.mmd") == []


@needs_tlc
@pytest.mark.timeout(300)
def test_from_spec_draws_a_way_out_of_a_bug_state_the_model_can_leave_and_calls_one_it_cannot_final(
    tmp_path,
):
    """A rule broken as expected stops TLC's check at the bug, yet from-spec draws the chart from
    the whole model, so the bug state keeps its way out, or is final when the model has none."""
    run = run_door(tmp_path, DOOR_MAP)
    for rule, bug, leaves in [
        ("NoShownWhileClosed", "Window closed: reply shown", True),
        ("NoLostReply", "reply lost", False),
    ]:
        drawn = run(rule)
        summary = json.loads(read(drawn["out"] / "summary.json"))
        assert summary["classes"][0]["invariant"] == rule
        assert (bug in summary["final"]) is not leaves, rule
        assert stalls(drawn["out"] / "chart.mmd") == [], rule


def test_the_page_says_how_many_steps_a_chart_draws_of_how_many_it_could(tmp_path):
    folder = lamp(tmp_path / "a", "")
    write(folder / "summary.json", json.dumps({"chartTransitions": 2, "allTransitions": 5}))
    assert site(tmp_path / "a", tmp_path / "a.html").returncode == 0
    said = "2 states, 2 of 5 steps drawn: the way into each state and a way out of each."
    assert said in read(tmp_path / "a.html")
    lamp(tmp_path / "b", "")
    assert site(tmp_path / "b", tmp_path / "b.html").returncode == 0
    assert "2 states, 2 steps." in read(tmp_path / "b.html")


def test_the_page_fetches_nothing_when_it_is_viewed(tmp_path):
    out = tmp_path / "index.html"
    assert site(REPO, out).returncode == 0
    page = read(out)
    assert not re.search(r"<script[^>]*\bsrc=|<link\b|@import|url\(\s*['\"]?https?:", page)
    assert re.findall(r"https?://[^\s\"'<>]+", page) == ["http://www.w3.org/2000/svg"] * len(CHARTS)


CHART = """---
title: "Does the lamp light?"
---
stateDiagram-v2
  classDef group0 fill:#d1f2eb,stroke:#697976,color:#1b2631
  [*] --> off
  state "Off (lamp.py:2, the switch is down)" as off
  state "On" as on
  off --> on : you flip the switch
  on --> off : you flip it back
  class off group0
"""


LEGEND = """  state "Legend" as legend {
    state "Dark room" as legendGroup0
  }
  class legendGroup0 group0
"""


def lamp(root, stories):
    folder = root / "features" / "lamp" / "spec" / "Lamp-statechart"
    folder.mkdir(parents=True)
    write(folder / "chart.mmd", CHART)
    write(folder / "stories.md", stories)
    src = root / "features" / "lamp" / "src"
    src.mkdir()
    write(src / "lamp.py", "def lamp():\n    return 'down'\n")
    return folder


def test_the_page_tells_a_charts_bug_paths_and_says_so_when_it_has_none(tmp_path):
    lamp(tmp_path / "a", "## Bug 1: NeverDark\n\nYou flip the switch, and the lamp `stays` on.\n")
    out = tmp_path / "a" / "index.html"
    assert site(tmp_path / "a", out).returncode == 0
    page = read(out)
    assert "<h4>Bug 1: NeverDark</h4>" in page
    assert "the lamp <code>stays</code> on." in page
    assert "Does the lamp light?" in page
    assert "return &#x27;down&#x27;" in page or "return 'down'" in page
    lamp(tmp_path / "b", "")
    out = tmp_path / "b" / "index.html"
    assert site(tmp_path / "b", out).returncode == 0
    assert "No bug paths" in read(out)


def test_check_says_whether_the_written_page_is_the_one_the_charts_make(tmp_path):
    folder = lamp(tmp_path, "")
    out = tmp_path / "index.html"
    assert site(tmp_path, out).returncode == 0
    current = site(tmp_path, out, "--check")
    assert (current.returncode, current.stdout) == (0, f"{out} is current\n")
    write(folder / "chart.mmd", CHART.replace('"On"', '"Lit"'))
    stale = site(tmp_path, out, "--check")
    assert stale.returncode == 1
    assert stale.stdout == f"{out} is stale: run statechart site --out {out}\n"


BROWSER = os.environ.get("JSTACK_TEST_BROWSER", "")
CHROMIUM = shutil.which(BROWSER) if BROWSER else shutil.which("chromium")
DESK, PHONE = (1440, 900), (390, 844)
LAUNCH = 60

PROBE = """<script>
(() => {
  const frame = () => new Promise((r) => setTimeout(r, 50));
  const port = () => document.querySelector(".chart-panel:not([hidden]) .viewport");
  function look() {
    const p = port().getBoundingClientRect();
    const svg = port().querySelector("svg");
    const boxes = [...svg.querySelectorAll(".region-box")].map((b) => b.getBoundingClientRect());
    const left = Math.max(p.left, Math.min(...boxes.map((b) => b.left)));
    const right = Math.min(p.right, Math.max(...boxes.map((b) => b.right)));
    const top = Math.min(...boxes.map((b) => b.top));
    const labels = [...svg.querySelectorAll(".st text:not(.comp)")];
    const size = (t) => parseFloat(getComputedStyle(t).fontSize) * t.getScreenCTM().a;
    const px = Math.min(...labels.map(size));
    return { drawn: (right - left) / p.width, above: (top - p.top) / p.height, label: px };
  }
  // Where a group's states sit once its overview box is tapped: the share of them whose
  // centre is inside the frame, whether each is lit, and whether the frame is on the screen.
  function group(panel, box) {
    const p = port().getBoundingClientRect();
    const ids = box.dataset.states.split(" ");
    const els = ids.map((id) => panel.querySelector(`svg.chart .st[data-id="${CSS.escape(id)}"]`));
    const inside = els.filter((el) => {
      const r = el.getBoundingClientRect();
      const x = r.left + r.width / 2, y = r.top + r.height / 2;
      return x >= p.left && x <= p.right && y >= p.top && y <= p.bottom;
    });
    const stage = panel.querySelector(".stage").getBoundingClientRect();
    return {
      name: box.dataset.name, states: ids.length, found: els.filter(Boolean).length,
      inside: inside.length, lit: els.filter((el) => el && el.classList.contains("near")).length,
      boxLit: box.classList.contains("lit"),
      onScreen: stage.top < innerHeight && stage.bottom > 0,
    };
  }
  const selected = () => {
    const t = document.querySelector('.tab[aria-selected="true"]');
    return t ? t.dataset.chart || t.dataset.view : null;
  };
  async function run() {
    const flow = document.querySelector(".flow-panel");
    const out = {
      charts: {},
      opens: selected(),
      flowShown: !!flow && !flow.hidden && flow.getBoundingClientRect().height > 0,
      flowBoxes: [...document.querySelectorAll(".flow-panel .flow-box")]
        .map((b) => b.dataset.chart),
      handoffs: document.querySelectorAll(".flow-panel .handoffs li").length,
    };
    for (const tab of document.querySelectorAll(".tab[data-chart]")) {
      tab.click();
      await frame();
      const panel = document.querySelector(".chart-panel:not([hidden])");
      const zoom = (z) => panel.querySelector(`[data-zoom="${z}"]`).click();
      const opened = look();
      const fig = panel.querySelector(".overview");
      const figRect = fig.getBoundingClientRect();
      const ovLabels = [...fig.querySelectorAll(".ov-box text")];
      const px = (t) => parseFloat(getComputedStyle(t).fontSize) * t.getScreenCTM().a;
      const ovPx = Math.min(...ovLabels.map(px));
      const overview = {
        boxes: fig.querySelectorAll(".ov-box").length,
        above: figRect.bottom <= panel.querySelector(".stage").getBoundingClientRect().top,
        label: ovPx,
        groups: [],
      };
      for (const box of fig.querySelectorAll(".ov-box")) {
        box.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        await frame();
        overview.groups.push(group(panel, box));
      }
      scrollTo(0, 0);
      zoom("fit"); await frame();
      zoom("in"); await frame();
      const inside = look().label;
      zoom("out"); zoom("out"); await frame();
      const outside = look().label;
      zoom("fit"); await frame();
      out.charts[tab.dataset.chart] = {
        ...opened, zoomIn: inside, zoomOut: outside, fit: look(), overview,
      };
    }
    out.mapOpens = {};
    for (const name of out.flowBoxes) {
      document.querySelector('.tab[data-view="overview"]').click();
      await frame();
      const box = document.querySelector(`.flow-box[data-chart="${CSS.escape(name)}"]`);
      box.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      await frame();
      out.mapOpens[name] = selected();
    }
    document.querySelector('.tab[data-view="overview"]').click();
    await frame();
    const go = document.querySelectorAll(".flow-panel .handoffs button.go")[1];
    go.click();
    await frame();
    const lit = document.querySelector(".chart-panel:not([hidden]) .ov-box.lit");
    out.handoffOpens = {
      chart: selected(), wanted: go.dataset.chart,
      box: lit && lit.dataset.box, wantedBox: go.dataset.box,
    };
    const theme = document.querySelector(".theme");
    const glyph = () => {
      const shown = [...theme.querySelectorAll("svg")]
        .filter((g) => getComputedStyle(g).display !== "none");
      const r = shown.length === 1 ? shown[0].getBoundingClientRect() : { width: 0 };
      return { shown: shown.map((g) => g.dataset.glyph), size: r.width,
               theme: getComputedStyle(document.documentElement).getPropertyValue("--bg").trim() };
    };
    out.theme = [glyph()];
    theme.click(); await frame(); out.theme.push(glyph());
    theme.click(); await frame(); out.theme.push(glyph());
    return out;
  }
  run().catch((e) => ({ error: String(e && e.stack || e) })).then((out) => {
    if (parent !== window) return parent.postMessage(JSON.stringify(out), "*");
    const pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify(out);
    document.body.append(pre);
  });
})();
</script>"""

PHONE_FRAME = """<!doctype html><body style="margin:0"><iframe src="probed.html"
style="border:0;width:{w}px;height:{h}px"></iframe><script>
addEventListener("message", (e) => {{
  const pre = document.createElement("pre"); pre.id = "probe"; pre.textContent = e.data;
  document.body.append(pre);
}});
</script></body>"""


@contextlib.contextmanager
def browser_lock():
    """The machine's browser lock, where its folder exists, as the browser tests of jbus take it,
    so only one of their browsers runs at a time."""
    held = Path(os.environ["HOME"]) / ".local" / "state" / "locks" / "browser.lock"
    if not held.parent.is_dir():
        yield
        return
    until = time.monotonic() + 240
    with open(held, "a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > until:
                    pytest.fail(f"{held} was held for 240 s by other browser tests: run it again")
                time.sleep(0.1)
        yield


def probed(tmp_path, screen):
    """What the probe measured, in a headless browser at a window of this size, on the page that
    `statechart site` builds from the committed charts. The probe, added to a copy of the page,
    opens each tab and measures what the frame shows on load, then works the zoom, fit and theme
    buttons, and writes what it found into the page, which the browser prints. The browser opens
    no window under 500 pixels wide, so the phone's page is a frame of 390 pixels inside a wider
    one, and the probe in it posts what it found up to that page."""
    if not CHROMIUM:
        if BROWSER or os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail(f"no browser to open the page in: {BROWSER or 'no chromium on PATH'}")
        pytest.skip("no chromium on PATH to open the page in")
    folder = tmp_path / f"{screen[0]}"
    folder.mkdir()
    built = site(REPO, folder / "index.html", "--flow", str(FLOW))
    assert built.returncode == 0, built.stderr
    page = read(folder / "index.html")
    write(folder / "probed.html", page.replace("</body>", PROBE + "</body>"))
    target, window = folder / "probed.html", screen
    if screen[0] < 500:
        write(folder / "phone.html", PHONE_FRAME.format(w=screen[0], h=screen[1]))
        target, window = folder / "phone.html", (500, screen[1])
    command = [CHROMIUM, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars"]
    command += [f"--user-data-dir={folder / 'profile'}", "--allow-file-access-from-files"]
    command += [f"--window-size={window[0]},{window[1]}", "--virtual-time-budget=8000"]
    command += ["--dump-dom", target.as_uri()]
    with browser_lock(), tempfile.TemporaryDirectory(prefix="st-site-", dir="/tmp") as short:
        env = {**os.environ, "TMPDIR": short}
        with subprocess.Popen(
            ["timeout", "--kill-after=5", str(LAUNCH), *command],
            start_new_session=True,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as browser:
            try:
                out, err = browser.communicate(timeout=LAUNCH + 30)
            finally:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(browser.pid, signal.SIGKILL)
    found = re.search(r'<pre id="probe">(.*?)</pre>', out, re.S)
    assert found, f"the probe wrote nothing: {out[-1500:]} {err[-1500:]}"
    said = json.loads(html.unescape(found[1]))
    assert "error" not in said, said["error"]
    return said


@pytest.mark.browser
@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["desk", "phone"])
def test_each_chart_opens_fitted_to_the_frames_width_with_its_labels_readable(tmp_path, screen):
    said = probed(tmp_path, screen)
    names = [c.parent.name.removesuffix("-statechart") for c in CHARTS]
    assert sorted(said["charts"]) == sorted(names)
    for name, chart in said["charts"].items():
        assert chart["drawn"] >= 0.9, (name, chart)
        assert chart["label"] >= 11, (name, chart)
        assert chart["above"] <= 0.2, (name, chart)
        assert chart["zoomIn"] > chart["label"] > chart["zoomOut"], (name, chart)
        fit = chart["fit"]
        assert (fit["drawn"], fit["label"]) == (chart["drawn"], chart["label"]), (name, chart)


@pytest.mark.browser
@pytest.mark.parametrize("screen", [DESK, PHONE], ids=["desk", "phone"])
def test_the_page_opens_on_the_map_and_each_overview_box_moves_its_chart_to_that_group(
    tmp_path, screen
):
    said = probed(tmp_path, screen)
    names = [c.parent.name.removesuffix("-statechart") for c in CHARTS]
    assert said["opens"] == "overview" and said["flowShown"], said
    assert sorted(said["flowBoxes"]) == sorted(names)
    assert said["handoffs"] >= len(names) - 1
    assert said["mapOpens"] == {name: name for name in names}
    opens = said["handoffOpens"]
    assert (opens["chart"], opens["box"]) == (opens["wanted"], opens["wantedBox"]), opens
    for name, chart in said["charts"].items():
        overview = chart["overview"]
        assert 1 <= overview["boxes"] <= 10, (name, overview["boxes"])
        assert overview["above"], name
        if screen == DESK:
            assert overview["label"] >= 11, (name, overview["label"])
        assert len(overview["groups"]) == overview["boxes"]
        for g in overview["groups"]:
            assert g["found"] == g["lit"] == g["states"], (name, g)
            assert g["boxLit"] and g["onScreen"], (name, g)
            assert g["inside"] == g["states"], (name, g)


@pytest.mark.browser
def test_the_theme_button_shows_a_sun_or_a_moon_and_switches_the_page(tmp_path):
    first, switched, back = probed(tmp_path, DESK)["theme"]
    for one in (first, switched, back):
        assert len(one["shown"]) == 1 and one["size"] >= 16, one
    assert {first["shown"][0], switched["shown"][0]} == {"sun", "moon"}
    assert first["theme"] != switched["theme"]
    assert back == first
