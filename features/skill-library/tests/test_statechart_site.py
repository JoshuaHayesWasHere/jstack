"""`statechart site` writes one page that explores every committed chart: each chart and each of
its states is on it, it fetches nothing when viewed, and it shows each chart's stories."""

import contextlib
import fcntl
import html
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

from statechart_support import node, read, write
from testing.paths import REPO

READ_SET = ("features/*/spec/*-statechart/", "features/*/src/")

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


def site(root, out, *extra):
    return node("statechart", ["site", "--out", str(out), "--root", str(root), *extra], root)


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


@pytest.mark.parametrize("chart", CHARTS, ids=lambda chart: chart.parent.name)
def test_each_charts_groups_hold_few_enough_states_to_find_one_and_none_is_mixed(chart):
    """A reader finds a state by its group's color: a group of more than GROUP_MOST states says
    little about where a state sits, and a mixed state is gray, in no group at all."""
    summary = json.loads(read(chart.parent / "summary.json"))
    big = [
        f"{g['name']} ({g['states']})" for g in summary["chartGroups"] if g["states"] > GROUP_MOST
    ]
    assert not big, f"{chart.parent.name} has groups over {GROUP_MOST} states: {', '.join(big)}"
    assert summary["mixedGroups"] == [], f"{chart.parent.name} has mixed states"


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
  async function run() {
    const out = { charts: {} };
    for (const tab of document.querySelectorAll(".tab")) {
      tab.click();
      await frame();
      const panel = document.querySelector(".chart-panel:not([hidden])");
      const zoom = (z) => panel.querySelector(`[data-zoom="${z}"]`).click();
      const opened = look();
      zoom("in"); await frame();
      const inside = look().label;
      zoom("out"); zoom("out"); await frame();
      const outside = look().label;
      zoom("fit"); await frame();
      out.charts[tab.dataset.chart] = { ...opened, zoomIn: inside, zoomOut: outside, fit: look() };
    }
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
    """What the probe measured on the committed page in a headless browser at a window of this
    size. The probe, added to a copy of the page, opens each tab and measures what the frame
    shows on load, then works the zoom, fit and theme buttons, and writes what it found into
    the page, which the browser prints. The browser opens no window under 500 pixels wide, so
    the phone's page is a frame of 390 pixels inside a wider one, and the probe in it posts
    what it found up to that page."""
    if not CHROMIUM:
        if BROWSER or os.environ.get("GITHUB_ACTIONS") == "true":
            pytest.fail(f"no browser to open the page in: {BROWSER or 'no chromium on PATH'}")
        pytest.skip("no chromium on PATH to open the page in")
    folder = tmp_path / f"{screen[0]}"
    folder.mkdir()
    page = read(REPO / "features" / "home" / "docs" / "charts" / "index.html")
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
def test_the_theme_button_shows_a_sun_or_a_moon_and_switches_the_page(tmp_path):
    first, switched, back = probed(tmp_path, DESK)["theme"]
    for one in (first, switched, back):
        assert len(one["shown"]) == 1 and one["size"] >= 16, one
    assert {first["shown"][0], switched["shown"][0]} == {"sun", "moon"}
    assert first["theme"] != switched["theme"]
    assert back == first
