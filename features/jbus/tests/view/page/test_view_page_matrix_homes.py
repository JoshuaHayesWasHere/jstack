"""Every stage, every home, the stage grid, is drawn on the Homes page, `#/homes`, at its top
above the homes map, and not on the bare front page, `#/`. A cell of it lists that cell's rows on
the board, and Esc comes back to the Homes page. A slug of its Chains line opens the board with
that row picked.
"""

import pytest

from view.page.browser import BROWSES, LAUNCH, PATIENCE, look
from view.page.test_view_page_pipeline import MATRIX
from view.scene import Scene, Served

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + 2 * BROWSES * (LAUNCH + 5) + 60)]


def test_the_grid_is_on_the_homes_page_above_the_map_and_not_on_the_front_page(tmp_path):
    """Over the T moment `#/` draws no grid. `#/homes` draws one, above the map, and its jview
    Check cell opens `#/?home=demo/jview&stage=check`, which lists jview's rows in Check alone
    under "Showing jview, Check ✕"; Esc goes back to `#/homes` and its grid, and the Chains
    line's head, fig-saucer, opens `#/?pick=fig-saucer` with fig-saucer picked on the board."""
    from view.days import t_moment

    scene = Scene(tmp_path / "scene", pytest.MonkeyPatch())
    t_moment(scene)
    served = Served(scene)
    try:
        front = look(
            scene,
            tmp_path,
            route="#/",
            port=served.port,
            script="window.__cells = [];\n" + MATRIX,
            at=2000,
        )
        walk = 'window.__cells = ["cell:demo/jview/check", "esc", "chain:fig-saucer"];\n'
        homes = look(
            scene,
            tmp_path,
            route="#/homes",
            port=served.port,
            script=walk + MATRIX,
            at=2000,
            budget=12000,
        )
        made = served.json("/panel/pipeline.json")["data"]
    finally:
        served.close()
    assert front["errors"] == homes["errors"] == []
    (bare,) = front["seen"]
    assert bare["drawn"] == 0, bare
    first, cell, back, chain = homes["seen"]
    assert first["hash"] == "#/homes"
    assert first["drawn"] == 1 and first["overMap"], first
    mine = sorted(
        one["slug"] for one in made["rows"] if (one["home"], one["stage"]) == ("jview", "check")
    )
    assert mine
    assert cell["hash"] == "#/?home=demo/jview&stage=check"
    assert [(one["key"], sorted(one["slugs"])) for one in cell["stages"]] == [("check", mine)]
    assert cell["bar"] == "Showing jview, Check ✕"
    assert cell["drawn"] == 0
    assert back["hash"] == "#/homes"
    assert back["drawn"] == 1 and back["overMap"], back
    assert chain["hash"] == "#/?pick=fig-saucer"
    assert chain["drawn"] == 0
    assert chain["picked"] == ["fig-saucer"], chain
