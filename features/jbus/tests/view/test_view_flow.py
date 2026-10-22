"""The queue as a flow: the waves of the queued rows and the chain each waits on."""

from jbus.view.state import waves
from view.scene import GATE, ago, iso, row, tasks


def test_a_chain_of_three_names_each_blocker_and_the_first_blocks_two(scene, served):
    findings = "wait: its findings are not handled: the Result has no Fixed line"
    scene.queue(
        [
            row("nut-shell", "pr", pr="#41", why=findings),
            row("nut-meat", depends=["nut-shell"], why="depends on nut-shell"),
            row("nut-oil", depends=["nut-meat"], why="depends on nut-meat"),
            row("nut-husk", approved="", why="not approved"),
            row("nut-bowl", "running", thread="mcp:1"),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    assert found["nut-shell"]["blocked"] == {"by": "", "what": "findings", "state": ""}
    assert found["nut-meat"]["blocked"] == {
        "by": "nut-shell",
        "what": "nut-shell",
        "state": "Findings",
    }
    assert found["nut-oil"]["blocked"] == {"by": "nut-meat", "what": "nut-meat", "state": "Behind"}
    assert found["nut-shell"]["behind"] == ["nut-meat", "nut-oil"]
    assert found["nut-husk"]["blocked"] == {"by": "", "what": "approval", "state": ""}
    assert found["nut-bowl"]["blocked"] is None
    assert {slug: one["blocks"] for slug, one in found.items()} == {
        "nut-shell": 2,
        "nut-meat": 1,
        "nut-oil": 0,
        "nut-husk": 0,
        "nut-bowl": 0,
    }


def test_each_queued_row_has_a_wave_and_the_one_row_it_waits_on_last(scene, served):
    """A chain of four: `pea-soup` is behind three rows. `pea-vine` is behind a row that is out.
    `pea-mash` waits on two rows of one wave, and `pea-pod` is the first of them in the queue.
    `pea-husk` is not approved, and `pea-salt` is behind a row that merged."""
    scene.queue(
        [
            row("pea-pod", "gate", why="a gate the Chef has", priority=0),
            row("pea-one"),
            row("pea-two", depends=["pea-one"]),
            row("pea-three", depends=["pea-two"]),
            row("pea-four", depends=["pea-three"]),
            row("pea-soup", depends=["pea-one", "pea-three", "pea-two"]),
            row("pea-vine", depends=["pea-pod"]),
            row("pea-mash", depends=["pea-one", "pea-pod"]),
            row("pea-husk", approved="", why="not approved", depends=["pea-two"]),
            row("pea-done", "merged", pr="#61"),
            row("pea-salt", depends=["pea-done"]),
        ]
    )
    found = tasks(served.json("/state.json?project=demo"))
    assert {slug: (one["wave"], one["waits_on"]) for slug, one in found.items()} == {
        "pea-pod": (None, ""),
        "pea-one": (0, ""),
        "pea-two": (1, "pea-one"),
        "pea-three": (2, "pea-two"),
        "pea-four": (3, "pea-three"),
        "pea-soup": (3, "pea-three"),
        "pea-vine": (1, "pea-pod"),
        "pea-mash": (1, "pea-pod"),
        "pea-husk": (2, "pea-two"),
        "pea-salt": (0, ""),
    }
    assert found["pea-husk"]["state"]["kind"] == "unapproved"
    assert found["pea-husk"]["blocked"] == {"by": "", "what": "approval", "state": ""}


def test_rows_that_depend_on_each_other_still_get_a_wave():
    assert waves(["a", "b", "c"], {"a": ["b"], "b": ["a"], "c": ["gone"]}) == {
        "a": (2, "b"),
        "b": (1, "a"),
        "c": (1, "gone"),
    }


def test_the_wait_band_is_the_list_the_pass_left_with_the_gates_read_now(scene, served):
    waiting = served.json("/state.json?project=demo")["waiting"]
    assert [(one["kind"], one["line"]) for one in waiting] == [
        ("gate", "gate 4: tea or coffee?"),
        ("row", "gate jam-lid: which lid?"),
        ("approve", "approve tea-kettle: jbus queue approve"),
        ("hold", "hold 14: needs user"),
    ]
    assert waiting[0]["since"] == iso(ago(hours=3))
    assert (waiting[0]["question"], waiting[0]["default"]) == ("tea or coffee?", "tea")
    with open(scene.home / "gates.md", "a") as gates:
        gates.write("\n" + GATE.format(n=6, asked="milk?", status="open", default="no"))
    waiting = served.json("/state.json?project=demo")["waiting"]
    assert [one["line"] for one in waiting if one["kind"] == "gate"] == [
        "gate 4: tea or coffee?",
        "gate 6: milk?",
    ]
    assert waiting[1]["since"] is None
