import os, subprocess, sys, tempfile, time
from pathlib import Path

import pytest

sys.path.insert(0, "tests")
import test_jbus_view_page as t
from test_jbus_view import Scene


class MP(pytest.MonkeyPatch):
    pass


def run(name, extra, url):
    base = [t.CHROMIUM, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom"]
    with tempfile.TemporaryDirectory(prefix="d-", dir="/tmp") as short, tempfile.TemporaryDirectory() as prof:
        env = {**os.environ, "TMPDIR": short}
        start = time.monotonic()
        try:
            r = subprocess.run(base + [f"--user-data-dir={prof}"] + extra + [url], env=env, capture_output=True, text=True, timeout=40)
            print(f"== {name}: rc={r.returncode} {time.monotonic()-start:.1f}s out={len(r.stdout)} probe={'id=\"probe\"' in r.stdout}", flush=True)
            err = [l for l in r.stderr.splitlines() if "dbus" not in l]
        except subprocess.TimeoutExpired as e:
            print(f"== {name}: TIMEOUT 40s", flush=True)
            err = [l for l in (e.stderr or b"").decode(errors="replace").splitlines() if "dbus" not in l]
        print("\n".join(err[-15:]), flush=True)


mp = pytest.MonkeyPatch()
tmp = Path(tempfile.mkdtemp())
scene = Scene(tmp, mp)
served = t.Served(scene)
proxy = t.Proxy(served.port, 600)
url = f"http://127.0.0.1:{proxy.port}/"
plain = f"http://127.0.0.1:{served.port}/"
run("as the test", ["--hide-scrollbars", "--window-size=1440,900", "--virtual-time-budget=6000"], url)
run("no proxy", ["--hide-scrollbars", "--window-size=1440,900", "--virtual-time-budget=6000"], plain)
run("no budget", ["--hide-scrollbars", "--window-size=1440,900", "--timeout=8000"], url)
run("budget, no-dev-shm", ["--disable-dev-shm-usage", "--window-size=1440,900", "--virtual-time-budget=6000"], url)
run("budget, verbose", ["--window-size=1440,900", "--virtual-time-budget=6000", "--enable-logging=stderr", "--v=1"], url)
os._exit(0)
