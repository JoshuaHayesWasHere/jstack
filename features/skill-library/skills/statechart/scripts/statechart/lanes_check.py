"""statechart lanes-check: measures each chart drawn as lanes on a page `statechart site --lanes`
wrote, in a headless Chromium, at 728 and 1144 px wide and in the light and the dark theme: the
pairs of lines that cross or touch, the label lines on a line, on another arc's label or on a box,
and the words in a box on a line. It is the check that counts: `site` estimates label sizes from
their characters, and this one reads what the browser drew. It runs only where someone types it,
or `make charts` does, and never in CI."""

import contextlib
import html
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

WIDTHS = (728, 1144)
CHROMIUMS = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome")
TIMEOUT = 120
PROBE = (Path(__file__).parent / "lanes_probe.js").read_text(encoding="utf-8")
COUNTS = ("crossings", "labelOnLine", "labelOnLabel", "labelOnBox", "wordsOnLine")

USAGE = """Usage: statechart lanes-check FILE

Opens FILE, a page `statechart site --lanes` wrote, in a headless Chromium at 728 and 1144 px wide,
in the light and the dark theme, and prints for each chart drawn as lanes the pairs of lines that
cross or touch, the label lines on a line, on another arc's label or on a box, and the words in a
box on a line. CHROME names the browser; by default the first of chromium, chromium-browser,
google-chrome-stable and google-chrome on PATH.

Exit codes: 0 every count is 0, 1 a count above 0, 2 no browser, no page, or a probe that wrote
nothing."""


def browser():
    given = os.environ.get("CHROME")
    found = shutil.which(given) if given else next(filter(None, map(shutil.which, CHROMIUMS)), None)
    if not found:
        raise RuntimeError(f"no browser: {given or 'none of ' + ', '.join(CHROMIUMS)} on PATH")
    return found


def probe(page, width, chrome):
    """What the probe found on `page` at `width`, as a list, one entry per chart and theme."""
    # Chromium's socket goes in its TMPDIR, and a socket's path must be short: /tmp, not $TMPDIR.
    short = "/tmp" if os.path.isdir("/tmp") else None
    with tempfile.TemporaryDirectory(prefix="statechart-lanes-check-", dir=short) as work:
        target = Path(work) / "probed.html"
        target.write_text(
            page.read_text(encoding="utf-8").replace("</body>", PROBE + "</body>"), encoding="utf-8"
        )
        command = [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--hide-scrollbars"]
        command += [f"--user-data-dir={Path(work) / 'profile'}", f"--window-size={width},900"]
        command += ["--virtual-time-budget=20000", "--dump-dom", target.as_uri()]
        with subprocess.Popen(
            command,
            start_new_session=True,
            env={**os.environ, "TMPDIR": work},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ) as run:
            try:
                out, err = run.communicate(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                out, err = "", f"the browser took over {TIMEOUT} s"
            finally:
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(run.pid, signal.SIGKILL)
    found = re.search(r'<pre id="probe">(.*?)</pre>', out, re.S)
    if not found:
        raise RuntimeError(f"the probe wrote nothing at {width} px: {err.strip()[-600:]}")
    said = json.loads(html.unescape(found[1]))
    if isinstance(said, dict) and "error" in said:
        raise RuntimeError(f"the probe failed at {width} px: {said['error']}")
    return said


def main(argv):
    if not argv or argv[0] in ("-h", "--help") or len(argv) != 1:
        print(USAGE)
        return 0 if argv and argv[0] in ("-h", "--help") else 2
    page = Path(argv[0])
    try:
        if not page.is_file():
            raise RuntimeError(f"{page} is not there: run statechart site --lanes first")
        chrome = browser()
        results = [r for width in WIDTHS for r in probe(page, width, chrome)]
    except RuntimeError as e:
        print(e, file=sys.stderr)
        return 2
    if not results:
        print(
            f"{page}: no chart drawn as lanes; draw it with statechart site --lanes",
            file=sys.stderr,
        )
        return 2
    off = 0
    for r in results:
        counts = ", ".join(f"{len(r[k])} {k}" for k in COUNTS)
        print(
            f"{r['chart']} {r['width']} px {r['scheme']} ({r['drawing']}: {r['lines']} lines,"
            f" {r['labels']} label lines, {r['boxes']} boxes): {counts}"
        )
        for line in [x for k in COUNTS for x in r[k]][:6]:
            print(f"    {line}")
        off += sum(len(r[k]) for k in COUNTS)
    return 1 if off else 0
