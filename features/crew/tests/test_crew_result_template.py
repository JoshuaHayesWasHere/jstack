"""The Result has no `Noticed` line: a fault outside the task is a queued row or nothing.

The template is the one copy of the Result's shape, and the crew skill's stop block renders it by
hand, so both are read as a crewmate's Result would be."""

from jbus import outcome
from test_crew_needs_go import queued, start
from testing.paths import REPO

TEMPLATE = REPO / "features" / "crew" / "templates" / "result.md"


def labels(text):
    """The label of each line of a Result: the words before its first colon."""
    return [line.split(":")[0] for line in text.splitlines() if ":" in line]


def test_the_result_the_stop_block_writes_has_only_the_template_s_lines(kitchen):
    queued(kitchen, approve=False)
    _, brief = start(kitchen)
    result = brief.partition("## Result\n")[2]
    written = [label for label in labels(result) if not label.startswith("- ")]
    assert "Status" in written
    assert "Noticed" not in written
    template = labels(TEMPLATE.read_text())
    assert "Left" in template and "Noticed" not in template
    assert set(written) <= set(template)


def test_each_end_the_outcome_line_offers_is_one_jbus_reads():
    """jbus keeps a row that owes a pull request and closes with none at left until its last Result
    names how it ended (`watch.closes`), so each end the template's `Outcome:` line offers, filled
    in, is one `jbus.outcome.read` parses."""
    (line,) = [one for one in TEMPLATE.read_text().splitlines() if one.startswith("Outcome:")]
    offered = line.removeprefix("Outcome: <").split(">   <")[0].split(" | ")
    ends = []
    for end in offered:
        said = "Outcome: " + end.replace("<slug>", "po-next-row").replace(
            "<why>", "main already does it"
        )
        brief = f"# row\nPull request: open one when done\n\n## Result\nStatus: done\n{said}\n"
        ends.append(outcome.read(brief))
    assert ends == [
        outcome.CarriedBy("po-next-row"),
        outcome.NothingToChange("main already does it"),
        outcome.Dropped("main already does it"),
    ]
