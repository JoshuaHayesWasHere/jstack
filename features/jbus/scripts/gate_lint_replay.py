"""Replay `jbus gate`'s lint (`jbus.questions.refusal`) over gates already asked, and count what it
would have refused, by the labels a reader gave them.

    uv run python features/jbus/scripts/gate_lint_replay.py <directory>

The home's audit keeps one at `~/.local/state/home/jstack/reports/gate-quality`.

The directory holds `gates_full.jsonl`, one asked gate a line with its `key`, `week`, `question`,
`default` and `holds`, and `labels_<week>.tsv`, a row a gate with its `key`, `klass` (`standing`,
`reversible_obvious`, `josh_choice` or `door`) and `remover_kind` (`none` where no rule, code or
lint already settles it). A gate is removable when its class never needed the user and it has a
remover. The lint must refuse most removable gates and no `josh_choice` or `door` one.

It prints, for each week, the refused count of each group, then every refused gate with its
shape. A gate refused `settled:` is asked nothing, and one refused `not sent:` is asked again
once its default is reworded, so it exits 1 when a `josh_choice` or `door` gate is settled."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

from jbus import questions
from jbus.questions import refusal

NEEDED = ("josh_choice", "door")
NEEDED_GROUP = "josh_choice or door"
SETTLED, NOT_SENT = "settled: ", "not sent"


def group(label: dict[str, str]) -> str:
    if label["klass"] in NEEDED:
        return NEEDED_GROUP
    return "removable" if label["remover_kind"] not in ("", "none") else "no remover"


def why(gate: dict) -> str:
    """Return the shape a gate is settled by, `not sent` for a default that waits for the
    user's word, or "" for a gate `jbus gate` asks."""
    said = refusal(gate["question"], gate["default"], bool(gate["holds"]))
    if said.startswith(SETTLED):
        return next(
            one.shape for one in questions.SETTLED if said.startswith(f"{SETTLED}{one.shape}:")
        )
    return said and NOT_SENT


def main(argv: list[str]) -> int:
    here = Path(argv[0]).expanduser()
    gates = [json.loads(line) for line in (here / "gates_full.jsonl").open()]
    labels = {
        row["key"]: row
        for path in sorted(here.glob("labels_*.tsv"))
        for row in csv.DictReader(path.open(), delimiter="\t")
    }
    seen = [(gate, labels[gate["key"]], why(gate)) for gate in gates if gate["key"] in labels]
    for week in sorted({gate["week"] for gate, _, _ in seen}):
        print(f"week {week}")
        rows = [(label, said) for gate, label, said in seen if gate["week"] == week]
        for name in ("removable", "no remover", "josh_choice or door"):
            some = [said for label, said in rows if group(label) == name]
            refused = Counter(said for said in some if said)
            shapes = ", ".join(f"{shape} {n}" for shape, n in refused.most_common())
            print(f"  {name}: refused {sum(refused.values())} of {len(some)} ({shapes or 'none'})")
    print("refused")
    for gate, label, said in seen:
        if said:
            print(f"  {gate['key']}\t{gate['week']}\t{group(label)}\t{said}")
    lost = [
        gate["key"]
        for gate, label, said in seen
        if said not in ("", NOT_SENT) and group(label) == NEEDED_GROUP
    ]
    print(f"needed gates settled, so asked nothing: {', '.join(lost) or 'none'}")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
