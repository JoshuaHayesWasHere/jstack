"""`jbus view-shot` in a browser: it draws a route of the running view with the test browser, at
1440 or 390 wide, writes the PNG to the one path `--out` names, and prints that path. A bare name
goes into the runtime directory, and an `--out` that cannot be written is said so."""

import os
import struct

import pytest

from jbus import cli
from view.page.browser import CHROMIUM, LAUNCH, PATIENCE

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + 3 * (LAUNCH + 5) + 30)]


@pytest.fixture
def shooting(scene, served, tmp_path, monkeypatch):
    """The view of the scene, and the test browser first on `PATH` as `chromium`, where the
    command looks for it. The rest of `PATH` stays, the scene's stubs before the system's: Google
    Chrome's `google-chrome` is a bash wrapper that needs `readlink`, `dirname` and `cat`. The
    state directories are the scene's, so no `--out` of a test is in one."""
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    monkeypatch.setenv("XDG_STATE_HOME", str(scene.root / "xdg-state"))
    named = tmp_path / "browser"
    named.mkdir()
    (named / "chromium").symlink_to(CHROMIUM)
    monkeypatch.setenv("PATH", f"{named}{os.pathsep}{os.environ['PATH']}")
    return str(served.port)


def shot(capsys, *words):
    code = cli.main(["view-shot", *words])
    return code, capsys.readouterr().out.strip()


def size(png):
    """The width and height in the PNG's header."""
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


@pytest.mark.parametrize("width", [1440, 390])
def test_it_writes_the_png_of_the_route_at_the_width_and_prints_its_path(
    shooting, tmp_path, capsys, width
):
    out = tmp_path / "shots" / "board.png"
    out.parent.mkdir()
    code, said = shot(
        capsys, "#/demo", "--out", str(out), "--width", str(width), "--port", shooting
    )
    assert (code, said) == (0, str(out))
    assert size(out)[0] == width
    assert sorted(p.name for p in out.parent.iterdir()) == ["board.png"]


def test_a_bare_name_goes_into_the_runtime_directory(shooting, tmp_path, capsys, monkeypatch):
    runtime = tmp_path / "run"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    code, said = shot(capsys, "#/", "--out", "shot.png", "--home", "demo/jview", "--port", shooting)
    assert (code, said) == (0, str(runtime / "shot.png"))
    assert size(runtime / "shot.png")[0] == 1440


@pytest.mark.skipif(os.geteuid() == 0, reason="root writes into a read-only directory")
def test_an_out_that_cannot_be_written_says_so(shooting, tmp_path, capsys):
    shut = tmp_path / "shut"
    shut.mkdir()
    shut.chmod(0o500)
    out = shut / "shot.png"
    try:
        code, said = shot(capsys, "#/", "--out", str(out), "--port", shooting)
    finally:
        shut.chmod(0o700)
    assert (code, said) == (1, f"no shot: {out} could not be written (Permission denied)")
    assert not out.exists()
