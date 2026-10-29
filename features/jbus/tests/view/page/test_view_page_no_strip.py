"""The front page's board draws no strip of stage tiles above its columns (jv-no-strip): Josh,
2026-10-29, "this can get removed". Each column, or each fold on a phone, still names its stage
with its count, and the "Most stuck" headline still names the stage with the most rows not
moving, so nothing the strip said is lost.
"""

import pytest

from view.page.browser import BROWSES, LAUNCH, PATIENCE
from view.page.test_view_page_pipeline import SCREENS, shown

pytestmark = [pytest.mark.browser, pytest.mark.timeout(PATIENCE + BROWSES * (LAUNCH + 5) + 30)]


PROBE = """
window.addEventListener("load", function () { setTimeout(function () {
  var board = document.getElementById("pipeline");
  var all = function (sel, el) { return [].slice.call((el || board).querySelectorAll(sel)); };
  var text = function (el) { return el ? el.innerText.replace(/\\s+/g, " ").trim() : ""; };
  var pre = document.createElement("pre");
  pre.id = "probe";
  pre.textContent = JSON.stringify({
    strips: all("[data-role=strip]", document).length,
    tiles: all(".pl-st", document).length,
    stuck: text(board.querySelector("[data-head=stuck]")),
    stages: all("[data-stage]", board.querySelector("[data-role=cards]")).map(function (c) {
      return { key: c.getAttribute("data-stage"), head: text(c.querySelector("h3, summary")) };
    })
  });
  (window.top === window ? document : window.top.document).body.appendChild(pre);
}, window.__at); });
"""


@pytest.mark.parametrize("wide", list(SCREENS))
def test_the_board_draws_no_strip_and_its_columns_name_each_stage_with_its_count(tmp_path, wide):
    seen, made = shown(tmp_path, "27", SCREENS[wide], script=PROBE)
    assert (seen["strips"], seen["tiles"]) == (0, 0), seen
    assert [one["key"] for one in seen["stages"]] == [one["key"] for one in made["stages"]]
    for stage, drawn in zip(made["stages"], seen["stages"], strict=True):
        assert drawn["head"].startswith(f"{stage['name']} {stage['count']}"), drawn["head"]
    stuck = made["stuck"]
    assert seen["stuck"].lower().startswith("most stuck"), seen["stuck"]
    assert f"{stuck['still']} of {stuck['count']} not moving" in seen["stuck"], seen["stuck"]
