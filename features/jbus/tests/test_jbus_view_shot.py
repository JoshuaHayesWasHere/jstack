"""`jbus view-shot` says why it writes no PNG: no view running, no Chromium, a route that is not
one of the page's, an `--out` in a state directory or that is a directory, or a Chromium that drew
nothing. The shots it draws are tested in a browser (`view/page/test_view_page_shot.py`)."""

import pytest

from jbus import cli
from view.scene import Scene, Served, free_port


@pytest.fixture
def served(tmp_path, monkeypatch):
    scene = Scene(tmp_path, monkeypatch)
    monkeypatch.setenv("JBUS_STATE_DIR", str(scene.state_dir))
    monkeypatch.setenv("JBUS_HOME_DIR", str(scene.home_dir))
    monkeypatch.setenv("XDG_STATE_HOME", str(scene.root / "xdg-state"))
    made = Served(scene)
    yield made
    made.close()


def shot(capsys, *words):
    code = cli.main(["view-shot", *words])
    return code, capsys.readouterr().out.strip()


def test_with_no_view_running_it_says_so_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("JBUS_HOME_DIR", raising=False)
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg-state"))
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


def test_it_refuses_a_route_that_is_not_the_page_s(served, tmp_path, capsys):
    out = tmp_path / "shot.png"
    code, said = shot(capsys, "/demo", "--out", str(out), "--port", str(served.port))
    assert (code, said) == (1, "no shot: '/demo' is no route of the page, which starts with #")
    assert not out.exists()


def test_it_refuses_an_out_that_is_a_directory(served, tmp_path, capsys):
    out = tmp_path / "shots"
    out.mkdir()
    code, said = shot(capsys, "#/", "--out", str(out), "--port", str(served.port))
    assert (code, said) == (1, f"no shot: {out} is a directory")
    assert list(out.iterdir()) == []


def test_a_chromium_that_draws_no_png_leaves_the_out_as_it_was(
    served, tmp_path, capsys, monkeypatch
):
    fake = tmp_path / "fake"
    fake.mkdir()
    (fake / "chromium").write_text("#!/bin/sh\nexit 0\n")
    (fake / "chromium").chmod(0o755)
    monkeypatch.setenv("PATH", str(fake))
    out = tmp_path / "shot.png"
    out.write_bytes(b"the last shot")
    code, said = shot(capsys, "#/", "--out", str(out), "--port", str(served.port))
    assert (code, said) == (1, "no shot: chromium wrote no PNG (exit 0)")
    assert out.read_bytes() == b"the last shot"


@pytest.mark.parametrize(
    ("route", "home", "asked"),
    [
        ("#/?stage=crew", "jview", "#/?stage=crew&home=demo/jview"),
        ("#/?stage=crew", "other/x", "#/?stage=crew&home=other/x"),
        ("#/", "jview", "#/?home=demo/jview"),
    ],
)
def test_a_home_is_named_by_its_project_and_home(
    served, kitchen, tmp_path, monkeypatch, route, home, asked
):
    fake = tmp_path / "fake"
    fake.mkdir()
    pages = tmp_path / "pages"
    (fake / "chromium").write_text(f'#!/bin/sh\nfor page; do :; done\necho "$page" >> {pages}\n')
    (fake / "chromium").chmod(0o755)
    monkeypatch.setenv("PATH", f"{fake}:/usr/bin:/bin")
    out = tmp_path / "shot.png"
    code, _ = kitchen.main(
        "view-shot", route, "--home", home, "--out", str(out), "--port", str(served.port)
    )
    assert code == 1
    assert pages.read_text() == f"http://127.0.0.1:{served.port}/{asked}\n"
