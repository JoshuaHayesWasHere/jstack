"""`jbus view-shot`: write a PNG of one route of the running `jbus view`, so a reply can carry the
picture.

It asks the view on this machine, at `127.0.0.1` and the view's port (`view.PORT`, the port
`jbus link` gives), whether it is up (`/healthz`), and refuses when it is not. It then has headless
Chromium load the route, at a width of 1440 or 390 (`SIZES`), and draw it. Chromium's virtual time
stands still while a request is out, so its budget (`BUDGET_MS`) runs out only once the page has
its answers and has drawn them, and before the page's next poll. A `--home` adds
`home=<project>/<home>` to the route's query, for a page that shows one home, as the board keys its
home filter: a bare home is of the project `--project` names, or the one whose repo this is
(`verbs.here`).

It writes the one file `--out` names. A bare name goes into `$XDG_RUNTIME_DIR`, or `/tmp` where
that is not set, and a path under a state directory is refused (`state_dirs`). Chromium runs on a
profile of its own, in a temporary directory that is removed after it, and draws the PNG there: the
file at `--out` is replaced only by a PNG that Chromium wrote. The command reads no state, and no
config but to name the project of a bare `--home`. The page it loads counts its route, as for any
visit, so the view adds a line to its `view-usage.jsonl` for each shot (`usage`).

Chromium runs in its sandbox. Where it cannot make the sandbox's namespaces, as in a container that
gives it none, it aborts before it loads anything, and the shot is drawn again once with
`--no-sandbox` (`UNSANDBOXED`). The page is the view on this machine and nothing else, as the
view's page tests draw it.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import quote

import jbus
from jbus import verbs, view

SIZES = {1440: (1440, 900), 390: (390, 844)}
BUDGET_MS = 4000
TIMEOUT = 60
CHROMIUMS = ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome")
UNSANDBOXED = ("Failed to move to new namespace", "No usable sandbox")


class NoShot(Exception):
    """Why no PNG was written, as the line the command prints."""


def chromium() -> str:
    """The Chromium on `PATH`."""
    for name in CHROMIUMS:
        found = shutil.which(name)
        if found:
            return found
    raise NoShot("no shot: no chromium")


def running(port: int) -> bool:
    """Whether `jbus view` answers its health route at the port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=3) as answer:
            return json.load(answer) == {"ok": True}
    except (OSError, ValueError):
        return False


def state_dirs() -> tuple[Path, ...]:
    """The directories that hold state: `$XDG_STATE_HOME`, and jbus's own two where the
    environment moved them."""
    home = Path.home()
    found = [Path(os.environ.get("XDG_STATE_HOME") or home / ".local" / "state")]
    found += [
        Path(os.environ[one]) for one in ("JBUS_STATE_DIR", "JBUS_HOME_DIR") if os.environ.get(one)
    ]
    return tuple(one.resolve() for one in found)


def target(out: str) -> Path:
    """The file to write: a bare name in the runtime directory, any other path as given. A directory
    is refused, since the PNG would be moved into it under a name `--out` did not give."""
    if "/" not in out:
        runtime = os.environ.get("XDG_RUNTIME_DIR")
        out = str(Path(runtime if runtime and Path(runtime).is_dir() else "/tmp") / out)
    path = Path(out).expanduser().resolve()
    if any(path.is_relative_to(one) for one in state_dirs()):
        raise NoShot(f"no shot: {path} is in a state directory")
    if path.is_dir():
        raise NoShot(f"no shot: {path} is a directory")
    if not path.parent.is_dir():
        raise NoShot(f"no shot: {path.parent} is not a directory")
    return path


def address(port: int, route: str, home: str | None) -> str:
    """The page's address on this machine, with the home added to the route. A route is the page's
    fragment, so one that does not start with `#` is refused: the view answers any other path
    with 404, and Chromium would draw that."""
    if not route.removeprefix("/").startswith("#"):
        raise NoShot(f"no shot: {route!r} is no route of the page, which starts with #")
    route = route.removeprefix("/")
    if home:
        route += ("&" if "?" in route else "?") + f"home={quote(home, safe='/')}"
    return f"http://127.0.0.1:{port}/{route}"


def draw(
    browser: str, profile: Path, size: tuple[int, int], page: str, *more: str
) -> subprocess.CompletedProcess[str]:
    """Have Chromium draw the page into `shot.png` in its own new profile."""
    profile.mkdir()
    try:
        return subprocess.run(
            [
                browser,
                "--headless=new",
                *more,
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-gpu",
                "--hide-scrollbars",
                f"--window-size={size[0]},{size[1]}",
                f"--virtual-time-budget={BUDGET_MS}",
                f"--screenshot={profile / 'shot.png'}",
                page,
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired as error:
        raise NoShot(f"no shot: chromium took longer than {TIMEOUT} s") from error


def shoot(route: str, out: str, width: int = 1440, home: str | None = None, port: int = 0) -> Path:
    """Write the PNG of the route and return its path."""
    port = port or view.PORT
    path = target(out)
    page = address(port, route, home)
    if not running(port):
        raise NoShot("no shot: jbus view is not running")
    browser = chromium()
    size = SIZES[width]
    with tempfile.TemporaryDirectory(prefix="jbus-view-shot-") as scratch:
        profile = Path(scratch) / "sandboxed"
        done = draw(browser, profile, size, page)
        if done.returncode != 0 and any(one in done.stderr for one in UNSANDBOXED):
            profile = Path(scratch) / "unsandboxed"
            done = draw(browser, profile, size, page, "--no-sandbox")
        drawn = profile / "shot.png"
        if done.returncode != 0 or not drawn.is_file():
            said = [line for line in done.stderr.splitlines() if line.strip()]
            why = f": {said[-1].strip()}" if said else ""
            raise NoShot(f"no shot: chromium wrote no PNG (exit {done.returncode}){why}")
        try:
            shutil.move(drawn, path)
        except OSError as error:
            raise NoShot(f"no shot: {path} could not be written ({error.strerror})") from error
    return path


def arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("route", help="the page's route, as '#/' or '#/<project>'")
    parser.add_argument(
        "--out", required=True, help="the PNG to write, a bare name in $XDG_RUNTIME_DIR or /tmp"
    )
    parser.add_argument("--width", type=int, choices=sorted(SIZES, reverse=True), default=1440)
    parser.add_argument(
        "--home", help="the home the page shows, as <project>/<home> or a home of this project"
    )
    parser.add_argument(
        "--port", type=int, default=0, help="the port of jbus view, its own by default"
    )


def run(args: argparse.Namespace) -> int:
    """Print the PNG's path, or why there is none."""
    try:
        home = args.home
        if home and "/" not in home:
            home = f"{verbs.here(jbus.load(), args.project).name}/{home}"
        print(shoot(args.route, args.out, args.width, home, args.port))
    except NoShot as why:
        print(why)
        return 1
    return 0
