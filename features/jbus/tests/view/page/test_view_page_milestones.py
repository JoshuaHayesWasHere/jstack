"""The Milestones drawer on the page: a bar for each plan entry."""

import html
import re

import pytest

from view.page.browser import BROWSES, LAUNCH, PATIENCE, browse
from view.scene import Served
from view.test_view_milestones import sandbox

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


def drawn(port, tmp_path):
    """The text of the wide drawer that `#/demo/milestones` opens, once the page stops changing,
    or nothing where no drawer is open."""
    ran = browse(
        f"--user-data-dir={tmp_path / 'profile'}",
        "--virtual-time-budget=3000",
        f"http://127.0.0.1:{port}/#/demo/milestones",
    )
    found = re.search(
        r'<dialog class="drawer wide" id="drawer"[^>]* open="">(.*?)</dialog>', ran.stdout, re.S
    )
    said = found[1] if found else ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", said))).strip()


def test_the_drawer_draws_four_of_seven_as_a_chain_and_marks_what_holds_it(scene, tmp_path):
    sandbox(scene)
    served = Served(scene)
    try:
        said = drawn(served.port, tmp_path)
    finally:
        served.close()
    assert "Now 2 milestones are held, 5 of 10 rows merged" in said, said
    tea = said.partition("tea-set a whole tea set, seven pieces 4 of 7")[2].strip()
    assert tea.startswith(
        "4 merged #1 #2 #3 #4 → tea-5 Check #5 → tea-6 Running → tea-7 behind tea-6 → done not yet"
        " 4 of 7 merged, #5 at pr, 1 queued, 1 running"
        " blocked held at tea-7 : waits on tea-6, which is working tea-pot waits on this"
    ), said
    pot = said.partition("tea-pot a pot to pour from 0 of 2")[2].strip()
    assert pot.startswith(
        "pot-2 Running → pot-1 behind tea-6 → done not yet 0 of 2 merged, 1 queued, 1 running"
        " stuck held at pot-2 : its turn has written nothing, and may be hung"
        " Waits on tea-set ( tea-6 , working)"
    ), said
    assert "tea-cosy a cosy for the pot proposed" in said, said
    assert said.index("tea-pot a pot") < said.index("tea-cosy") < said.index("finished: jbus plan")
    assert "1 entry has every row finished: jbus plan close rye-loaf a loaf of rye 1 of 1" in said
