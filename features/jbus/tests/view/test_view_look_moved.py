"""The rule of the view's shot tests for a shot that moved, a shot that is missing and a browser
that moved (`test_view_page_look.compare` and `drawn_by`), with a browser's `--version` line in
place of a browser and images made here in place of its shots: a CI run on main or on a tag fails,
with the line that names the shots to keep, and any other run skips, since the kept shots are
main's and only the shots row redraws them (`jbus.shots`)."""

import pytest
from PIL import Image

from jbus import shots
from view.page import test_view_page_look as look
from view.page.test_view_page_look import compare, drawn_by

KEPT = "Google Chrome 155.0.8059.39"
THIS = "Google Chrome 156.0.8078.47"
MOVED = f"the shots were drawn by {KEPT}, and this is {THIS}"
MAIN = [
    ("schedule", "refs/heads/main"),
    ("push", "refs/heads/main"),
    ("workflow_dispatch", "refs/heads/main"),
    ("push", "refs/tags/v1.0.0"),
    ("release", "refs/tags/v1.0.0"),
]
ELSEWHERE = [
    ("pull_request", "refs/pull/7/merge"),
    ("workflow_dispatch", "refs/heads/browser-red-fix"),
]


def on(monkeypatch, event, ref):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_REF", ref)


def desk(monkeypatch):
    for name in ("CI", "GITHUB_EVENT_NAME", "GITHUB_REF"):
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize("event, ref", MAIN)
def test_a_browser_that_moved_fails_a_ci_run_on_main_or_a_tag(monkeypatch, event, ref):
    on(monkeypatch, event, ref)
    with pytest.raises(pytest.fail.Exception) as failed:
        drawn_by(KEPT, THIS)
    assert str(failed.value) == f"{MOVED}: {shots.MOVED}"


@pytest.mark.parametrize("event, ref", ELSEWHERE)
def test_a_browser_that_moved_skips_any_other_run_with_the_line_a_desk_skips_with(
    monkeypatch, event, ref
):
    on(monkeypatch, event, ref)
    with pytest.raises(pytest.skip.Exception) as skipped:
        drawn_by(KEPT, THIS)
    assert str(skipped.value) == MOVED
    desk(monkeypatch)
    with pytest.raises(pytest.skip.Exception) as on_a_desk:
        drawn_by(KEPT, THIS)
    assert str(on_a_desk.value) == MOVED


def test_the_browser_that_drew_the_shots_compares_them_on_any_run(monkeypatch):
    on(monkeypatch, "schedule", "refs/heads/main")
    assert drawn_by(THIS, THIS) is None


@pytest.fixture
def drawn(tmp_path, monkeypatch):
    """A kept shot, white, and the browser that drew the kept shots as this one."""
    monkeypatch.setattr(look, "browser", lambda: (look.SHOTS / look.DRAWN_BY).read_text().strip())
    kept = tmp_path / "all-390-dark.png"
    Image.new("RGB", (40, 40), "white").save(kept)
    return kept


def black_half():
    page = Image.new("RGB", (40, 40), "white")
    page.paste((0, 0, 0), (0, 0, 40, 20))
    return page


@pytest.mark.parametrize("event, ref", ELSEWHERE)
def test_a_shot_that_moved_skips_off_main_naming_the_shot_it_drew(
    drawn, tmp_path, monkeypatch, event, ref
):
    on(monkeypatch, event, ref)
    new = tmp_path / "new.png"
    with pytest.raises(pytest.skip.Exception) as skipped:
        compare(drawn, black_half(), new)
    assert str(skipped.value) == (
        f"50.00% of all-390-dark.png moved; the new shot is {new}: a pull request keeps main's "
        "shots, and the shots row redraws them once it merged"
    )
    with Image.open(new) as kept_drawn:
        assert kept_drawn.getpixel((0, 0)) == (0, 0, 0)


@pytest.mark.parametrize("event, ref", MAIN)
def test_a_shot_that_moved_fails_on_main_or_a_tag_naming_the_shots_to_keep(
    drawn, tmp_path, monkeypatch, event, ref
):
    on(monkeypatch, event, ref)
    new = tmp_path / "new.png"
    with pytest.raises(pytest.fail.Exception) as failed:
        compare(drawn, black_half(), new)
    assert str(failed.value) == (
        f"50.00% of all-390-dark.png moved; the new shot is {new}: {shots.MOVED}"
    )


def test_a_shot_that_is_missing_skips_off_main_and_fails_on_main(drawn, tmp_path, monkeypatch):
    missing = tmp_path / "help-390-dark.png"
    new = tmp_path / "new.png"
    desk(monkeypatch)
    with pytest.raises(pytest.skip.Exception) as skipped:
        compare(missing, black_half(), new)
    assert str(skipped.value).startswith("no shot is kept for help-390-dark.png; the new shot is ")
    on(monkeypatch, "schedule", "refs/heads/main")
    with pytest.raises(pytest.fail.Exception) as failed:
        compare(missing, black_half(), new)
    assert str(failed.value).endswith(f": {shots.MOVED}")


@pytest.mark.parametrize("event, ref", [*MAIN, *ELSEWHERE])
def test_a_shot_that_did_not_move_passes_on_any_run(drawn, monkeypatch, event, ref):
    on(monkeypatch, event, ref)
    assert compare(drawn, Image.new("RGB", (40, 40), "white"), drawn.parent / "new.png") is None
