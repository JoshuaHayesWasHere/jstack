"""compare-charts: compares two Mermaid stateDiagram-v2 charts as the machines their steps
reach."""

import re
import sys

from statechart.lib import FULL_LABELS, LEGEND_ID, ChartError, compare_charts, parse_mermaid

USAGE = "Usage: compare-charts EXPECTED.mmd ACTUAL.mmd"
HELP = f"""{USAGE}

Compares two Mermaid stateDiagram-v2 charts: reachable states, start states, and labeled
transitions. statechart from-chart runs it to check that the spec still draws the chart that
the reader agreed to.

EXPECTED is the agreed chart. ACTUAL is what tlc-to-chart drew from the spec in the customer
view with --highlight 0 --full-labels --flat, without --cover, --fixed-dot, or --against-dot. Each
chart compares as the
machine that its steps reach from its start states. A chart with parallel regions compares as its
combined machine, so a guard that blocks a step in only some combinations of regions shows as a
difference. A "%% when ID, ID" or "%% when not ID, ID" line right after a transition is its guard:
the step happens only while another region is in, or not in, one of those states. The label ends
with the guard's words in [ ], which are not part of the label. A combined state is the region
states joined by " | " in region order, which is what chart-to-tla's mapping writes. A step that
does not change the state is not compared, because
tlc-to-chart does not draw it. An edge label "a or b" counts as two labels. An unlabeled edge
counts only when no labeled edge joins the same two states, because tlc-to-chart draws only
the labels.

  -h, --help  Print this help, and exit 0.

Prints each difference and then "N difference(s)", or prints "same". Writes no file.

Exit codes
  0  The charts are the same.
  1  The charts differ.
  2  A bad argument, a chart that it cannot read, or an ACTUAL chart that is not drawn for
     comparison."""
MORE = "Run compare-charts --help for the flags."


class Refused(Exception):
    pass


def or_refuse(file, f):
    try:
        return f()
    except (OSError, ChartError) as e:
        message = e.strerror if isinstance(e, OSError) and e.strerror else str(e)
        raise Refused(f"{file}: {message}") from e


def read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def compare(expected_file, actual_file):
    expected_text, actual_text = (
        or_refuse(f, lambda f=f: read(f)) for f in (expected_file, actual_file)
    )

    def has(pattern):
        return re.search(pattern, actual_text, re.M) is not None

    refusals = [
        (
            has(r"^\s*%% second model"),
            "it has a second model; draw ACTUAL without --fixed-dot or --against-dot",
        ),
        (
            has(rf'^\s*state\s+"[^"]*"\s+as\s+(?!{LEGEND_ID}\b)\w+\s*\{{'),
            "it has boxes; draw ACTUAL with --flat",
        ),
        (
            has(rf'^\s*state\s+"[^"]*"\s+as\s+{LEGEND_ID}\s*\{{')
            and FULL_LABELS not in actual_text,
            "edge labels write shared words once; draw ACTUAL with --full-labels",
        ),
    ]
    for bad, why in refusals:
        if bad:
            raise Refused(f"{actual_file}: {why}")
    expected_regions = or_refuse(expected_file, lambda: parse_mermaid(expected_text)["regions"])
    actual_regions = or_refuse(actual_file, lambda: parse_mermaid(actual_text)["regions"])
    if any(
        re.match(r"\d+(, \d+)*\. ", t["label"])
        for r in actual_regions.values()
        for t in r["transitions"]
    ):
        raise Refused(
            f"{actual_file}: an edge label is a numbered path step; draw ACTUAL with --highlight 0"
        )
    differences = 0
    for title, xs in compare_charts(expected_regions, actual_regions):
        print(f"{title}:")
        for x in xs:
            print(f"  {x}")
        differences += len(xs)
    print("same" if differences == 0 else f"{differences} difference(s)")
    return 0 if differences == 0 else 1


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    files = []
    for a in argv:
        if a in ("-h", "--help"):
            print(HELP)
            return 0
        if a.startswith("-") or len(files) == 2:
            print(f"unknown argument {a}. {MORE}", file=sys.stderr)
            return 2
        files.append(a)
    if len(files) < 2:
        print(f"{USAGE}\n{MORE}", file=sys.stderr)
        return 2
    try:
        return compare(*files)
    except Refused as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
