"""Each view the telemetry store makes has a row in its doc, `the-telemetry-store.md`.

A row is a line of one of the doc's tables whose first cell is the view's name in code font. The
views are those the store collects from `jbus.telemetry.views`, so a new view's module with no
row fails here, and the failure names it.
"""

import re

from jbus.telemetry.views import VIEWS
from testing.paths import REPO

DOC = REPO / "features/jbus/docs/jbus/the-telemetry-store.md"


def test_each_view_of_the_store_has_a_row_in_its_doc():
    rows = set(re.findall(r"^\| `([a-z0-9_]+)` \|", DOC.read_text(), flags=re.MULTILINE))
    missing = [name for name, _ in VIEWS if name not in rows]
    assert not missing, f"views with no row in {DOC.relative_to(REPO)}: {', '.join(missing)}"
