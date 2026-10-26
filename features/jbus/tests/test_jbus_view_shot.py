"""`jbus view-shot` writes a PNG of one route of the running view, at 1440 or 390 wide, to the one
path `--out` names, and says why when it cannot."""

import shutil
import struct

import pytest

from jbus import cli
from view.scene import Scene, Served, free_port

CHROMIUM = shutil.which("chromium") or shutil.which("google-chrome")


@pytest.fixture
def served(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    made = Served(scene)
    yield made
    made.close()


def shot(capsys, *words):
    code = cli.main(["view-shot", *words])
    return code, capsys.readouterr().out.strip()


def size(png):
    """The width and height in the PNG's header."""
    data = png.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


@pytest.mark.skipif(not CHROMIUM, reason="no chromium on this machine")
@pytest.mark.parametrize("width", [1440, 390])
def test_it_writes_the_png_of_the_route_at_the_width_and_prints_its_path(
    served, tmp_path, capsys, width
):
    out = tmp_path / "shots" / "board.png"
    out.parent.mkdir()
    port = str(served.port)
    code, said = shot(capsys, "#/demo", "--out", str(out), "--width", str(width), "--port", port)
    assert (code, said) == (0, str(out))
    assert size(out)[0] == width
    assert sorted(p.name for p in out.parent.iterdir()) == ["board.png"]


@pytest.mark.skipif(not CHROMIUM, reason="no chromium on this machine")
def test_a_bare_name_goes_into_the_runtime_directory(served, tmp_path, capsys, monkeypatch):
    runtime = tmp_path / "run"
    runtime.mkdir()
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(runtime))
    code, said = shot(
        capsys, "#/", "--out", "shot.png", "--home", "jview", "--port", str(served.port)
    )
    assert (code, said) == (0, str(runtime / "shot.png"))
    assert size(runtime / "shot.png")[0] == 1440


def test_with_no_view_running_it_says_so_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("JBUS_HOME_DIR", raising=False)
    out = tmp_path / "shot.png"
    code, said = shot(capsys, "#/", "--out", str(out), "--port", str(free_port()))
    assert (code, said) == (1, "no shot: jbus view is not running")
    assert not out.exists()


def test_with_no_chromium_it_says_so_and_writes_nothing(served, tmp_path, capsys, monkeypatch):
    empty = tmp_path / "nothing"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    out = tmp_path / "shot.png"
    code, said = shot(capsys, "#/", "--out", str(out), "--port", str(served.port))
    assert (code, said) == (1, "no shot: no chromium")
    assert not out.exists()


def test_it_refuses_a_path_in_a_state_directory(served, tmp_path, capsys, monkeypatch):
    state = tmp_path / "state"
    (state / "jbus").mkdir(parents=True)
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    out = state / "jbus" / "shot.png"
    code, said = shot(capsys, "#/", "--out", str(out), "--port", str(served.port))
    assert (code, said) == (1, f"no shot: {out} is in a state directory")
    assert not out.exists()
