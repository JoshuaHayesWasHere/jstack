"""statechart overview: a chart drawn at the level of its groups, for a reader who wants the shape
before the states.

Each region of the chart gives one box per group that has states in it, and one box for the states
of the region that are in no group. Each arrow between two boxes counts the chart's steps from a
state of one to a state of the other, and a box counts the states in it and the steps between
them. The boxes hold every state of the chart and the arrows and boxes every step, so the
overview's counts add up to the chart's.
"""

from dataclasses import dataclass, field

MOST = 10


@dataclass
class Box:
    key: str
    name: str
    group: str
    states: list = field(default_factory=list)
    inside: int = 0
    start: bool = False


@dataclass
class Part:
    """One region of the overview: its boxes, and the steps between two of them by their keys."""

    name: str
    boxes: list = field(default_factory=list)
    links: dict = field(default_factory=dict)


@dataclass
class Overview:
    name: str
    title: str
    parts: list
    fills: dict
    legend: list

    def boxes(self):
        return [b for p in self.parts for b in p.boxes]


def overview_of(chart):
    """The overview of a chart that `site.read_chart` read: groups in the legend's order, then the
    region's states in no group."""
    named = {f"group{k}": g["name"] for k, g in enumerate(chart.legend)}
    order = list(named)
    parts = []
    for r, region in enumerate(chart.regions):
        part = Part(region.name)
        by_group = {}
        for s in region.states:
            group = s.group if s.group in named else ""
            by_group.setdefault(group, []).append(s.id)
        for group in [*order, ""]:
            if group not in by_group:
                continue
            rest = "In no group" if len(by_group) > 1 or not region.name else region.name
            part.boxes.append(
                Box(
                    key=f"r{r}{group or 'rest'}",
                    name=named.get(group, rest),
                    group=group,
                    states=by_group[group],
                    start=any(s in region.starts for s in by_group[group]),
                )
            )
        box_of = {s: b for b in part.boxes for s in b.states}
        for step in region.steps:
            a, b = box_of[step.source], box_of[step.target]
            if a is b:
                a.inside += 1
            else:
                part.links[(a.key, b.key)] = part.links.get((a.key, b.key), 0) + 1
        parts.append(part)
    return Overview(chart.name, chart.title, parts, chart.fills, chart.legend)


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


def caption(box):
    said = plural(len(box.states), "state")
    if box.inside:
        said += f", {plural(box.inside, 'step')} inside"
    return said


def _quote(text):
    return text.replace('"', "#quot;")


def mermaid(ov):
    """The overview as a Mermaid stateDiagram-v2, regions split by -- as the chart's are, which
    `statechart excalidraw` draws as it draws a chart."""
    lines = ["---", f'title: "Overview: {_quote(ov.title)}"', "---", "stateDiagram-v2"]
    used = {b.group for b in ov.boxes() if b.group}
    for cls in sorted(used, key=lambda g: int(g[len("group") :])):
        style = ov.fills.get(cls, {})
        lines.append(
            f"  classDef {cls} fill:{style.get('fill', '#f4f6f7')},"
            f"stroke:{style.get('stroke', '#566573')},color:#1b2631"
        )
    lines.append("  classDef plain fill:#f4f6f7,stroke:#566573,color:#1b2631")
    split = len(ov.parts) > 1
    indent = "      " if split else "  "
    if split:
        lines.append('  state "At the same time" as regions {')
    for r, part in enumerate(ov.parts):
        if split:
            if r:
                lines.append("    --")
            lines.append(f'    state "{_quote(part.name or f"Region {r + 1}")}" as region{r} {{')
        lines.extend(f"{indent}[*] --> {box.key}" for box in part.boxes if box.start)
        lines.extend(
            f'{indent}state "{_quote(box.name)}<br/>{caption(box)}" as {box.key}'
            for box in part.boxes
        )
        lines.extend(
            f"{indent}{a} --> {b} : {plural(n, 'step')}" for (a, b), n in part.links.items()
        )
        if split:
            lines.append("    }")
    if split:
        lines.append("  }")
    lines.extend(f"  class {box.key} {box.group or 'plain'}" for box in ov.boxes())
    return "\n".join(lines) + "\n"
