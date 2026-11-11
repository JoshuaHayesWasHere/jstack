"""statechart site: one self-contained HTML page that explores every committed chart.

It reads each `features/*/spec/*-statechart/chart.mmd`, with the `stories.md` and `summary.json`
beside it, and writes one page with no script, style or font fetched at view time. The layout is
computed here, so the page carries an SVG per chart and only the code that pans, zooms and selects.

`lib.parse_mermaid` reads a chart for what it means (its regions flattened into product states,
for `compare-charts`); the page needs what is drawn instead: each state's id, its composite, its
group's colour and each step's whole label. So this module reads chart.mmd its own way.
"""

import html
import json
import os
import re
import subprocess
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from statechart.lib import LEGEND_ID, ChartError, unwrap
from statechart.overview import MOST, caption, overview_of, plural

CITE = re.compile(r"([\w./-]+\.(?:py|tla|md|sh|toml|json|js|ts))(?::(\d+)|\s+`([^`]+)`)", re.A)

NODE_W = 210
LINE_H = 15
PAD_Y = 12
GAP_X = 34
GAP_Y = 70
ROW_MAX = 4
REGION_GAP = 60
REGION_PAD = 36


@dataclass
class Cite:
    text: str
    path: str | None = None
    line: int | None = None
    code: list = field(default_factory=list)


@dataclass
class State:
    id: str
    label: str
    composite: str = ""
    group: str = ""
    cites: list = field(default_factory=list)
    x: float = 0
    y: float = 0
    h: float = 0
    lines: list = field(default_factory=list)
    heads: list = field(default_factory=list)
    notes: list = field(default_factory=list)


@dataclass
class Step:
    source: str
    target: str
    label: str
    guard: list = field(default_factory=list)
    unless: bool = False
    cites: list = field(default_factory=list)


@dataclass
class Region:
    name: str
    states: list = field(default_factory=list)
    steps: list = field(default_factory=list)
    starts: list = field(default_factory=list)
    w: float = 0
    h: float = 0
    row_of: dict = field(default_factory=dict)


@dataclass
class Chart:
    name: str
    feature: str
    folder: Path
    title: str
    question: str
    regions: list
    legend: list
    fills: dict
    stories: str
    summary: dict


@dataclass
class Flow:
    """The map of the whole flow, from the file `--flow` names: the charts in the page's order,
    what each charts, the question a chart asks when its title asks none, and the hand-offs from
    a group of one chart to a group of another."""

    order: list = field(default_factory=list)
    things: dict = field(default_factory=dict)
    questions: dict = field(default_factory=dict)
    handoffs: list = field(default_factory=list)
    path: Path | None = None


def load_flow(path):
    if path is None:
        return Flow()
    path = Path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as e:
        raise ChartError(f"cannot read {path}: {e.strerror}") from e
    except tomllib.TOMLDecodeError as e:
        raise ChartError(f"{path}: {e}") from e
    flow = Flow(path=path)
    for chart in data.get("chart", []):
        if not isinstance(chart.get("name"), str) or not isinstance(chart.get("thing"), str):
            raise ChartError(f"{path}: each [[chart]] needs a name and a thing")
        flow.order.append(chart["name"])
        flow.things[chart["name"]] = chart["thing"]
        if chart.get("question"):
            flow.questions[chart["name"]] = chart["question"]
    for handoff in data.get("handoff", []):
        ends = [handoff.get("from"), handoff.get("to")]
        if not all(isinstance(e, str) and ": " in e for e in ends) or not handoff.get("says"):
            raise ChartError(
                f'{path}: each [[handoff]] needs from = "Chart: Group", to = "Chart: Group"'
                " and says"
            )
        flow.handoffs.append(
            {
                "from": tuple(ends[0].split(": ", 1)),
                "to": tuple(ends[1].split(": ", 1)),
                "says": handoff["says"],
            }
        )
    return flow


# Reading chart.mmd


_FRONT = re.compile(r"\A\s*---[ \t]*\n([\s\S]*?)\n---[ \t]*\n")
_STATE = re.compile(r'state\s+"([^"]*)"\s+as\s+([A-Za-z_]\w*)\s*(\{)?\s*$', re.A)
_BARE = re.compile(r"state\s+([A-Za-z_]\w*)\s*(\{)?\s*$", re.A)
_STEP = re.compile(r"(\[\*\]|[A-Za-z_]\w*)\s*-->\s*(\[\*\]|[A-Za-z_]\w*)(?:\s*:\s*(.*))?$", re.A)
_CAPTION = re.compile(r"([A-Za-z_]\w*)\s*:\s*(.*)$", re.A)


def _node(state_id, caption):
    return {"id": state_id, "caption": caption, "parts": [{"children": [], "steps": []}]}


def read_tree(text):
    """chart.mmd as written: its title, its composites with their parts, leaves and steps, the
    classDef fills, and which class each state has."""
    front = _FRONT.match(text)
    title = ""
    if front:
        found = re.search(r'^title:\s*"?(.*?)"?\s*$', front.group(1), re.M)
        title = found.group(1) if found else ""
    body = text[front.end() :] if front else text
    root = _node("", "")
    stack = [root]
    fills = {}
    classes = {}
    seen = set()
    implicit = {}
    last = None
    for raw in body.split("\n"):
        line = raw.strip()
        when = re.match(r"%%\s*when\s+(not\s+)?(.+)$", line)
        if when and last is not None:
            last["guard"] = [s.strip() for s in when.group(2).split(",")]
            last["unless"] = bool(when.group(1))
            last = None
            continue
        last = None
        if not line or line.startswith("%%") or re.match(r"(stateDiagram|direction|note)", line):
            continue
        part = stack[-1]["parts"][-1]
        m = re.match(r"classDef\s+(\S+)\s+(.*)$", line)
        if m:
            fills[m.group(1)] = dict(kv.split(":", 1) for kv in m.group(2).split(",") if ":" in kv)
            continue
        m = re.match(r"class\s+(\S+)\s+(\S+)$", line)
        if m:
            for state_id in m.group(1).split(","):
                classes[state_id] = m.group(2)
            continue
        m = _STATE.match(line)
        caption, state_id, opens = (m.group(1), m.group(2), m.group(3)) if m else (None, None, None)
        if not m:
            b = _BARE.match(line)
            if b:
                state_id, opens = b.group(1), b.group(2)
        if state_id:
            seen.add(state_id)
            placeholder = implicit.pop(state_id, None)
            if placeholder is not None:
                placeholder[0].remove(placeholder[1])
            node = _node(state_id, unwrap(caption) if caption is not None else state_id)
            if opens:
                part["children"].append(node)
                stack.append(node)
            else:
                node["leaf"] = True
                part["children"].append(node)
            continue
        if line == "}":
            if len(stack) == 1:
                raise ChartError("unmatched } in the chart")
            stack.pop()
            continue
        if line == "--":
            stack[-1]["parts"].append({"children": [], "steps": []})
            continue
        m = _STEP.match(line)
        if m:
            for end in (m.group(1), m.group(2)):
                if end != "[*]" and end not in seen:
                    seen.add(end)
                    leaf = _node(end, end)
                    leaf["leaf"] = True
                    part["children"].append(leaf)
                    implicit[end] = (part["children"], leaf)
            last = {"from": m.group(1), "to": m.group(2), "label": unwrap(m.group(3) or "")}
            part["steps"].append(last)
            continue
        m = _CAPTION.match(line)
        if m:
            if m.group(1) in implicit:
                implicit.pop(m.group(1))[1]["caption"] = unwrap(m.group(2))
            elif m.group(1) not in seen:
                seen.add(m.group(1))
                leaf = _node(m.group(1), unwrap(m.group(2)))
                leaf["leaf"] = True
                part["children"].append(leaf)
            continue
        raise ChartError(f"cannot read chart line: {line}")
    if len(stack) != 1:
        raise ChartError("the chart has an unclosed {")
    return title, root, fills, classes


def _walk(part, composites, leaves, steps):
    """Each leaf under `part` with the captions of the composites around it, and every step."""
    steps.extend(part["steps"])
    for child in part["children"]:
        if child.get("leaf"):
            leaves.append((child, " › ".join(composites)))
            continue
        for sub in child["parts"]:
            _walk(sub, [*composites, child["caption"]], leaves, steps)


def _first_leaf(node):
    for part in node["parts"]:
        for s in part["steps"]:
            if s["from"] == "[*]":
                return s["to"]
        for child in part["children"]:
            return child["id"] if child.get("leaf") else _first_leaf(child)
    return None


def regions_of(root):
    """The chart's regions: each part of a top-level composite split by `--`, named by the one
    composite that holds the part when there is one; otherwise the whole chart as one region."""
    top = root["parts"][0]
    machine = [c for c in top["children"] if c["id"] != LEGEND_ID]
    if len(machine) == 1 and not machine[0].get("leaf") and len(machine[0]["parts"]) > 1:
        out = []
        for n, part in enumerate(machine[0]["parts"], 1):
            only = part["children"]
            if len(only) == 1 and not only[0].get("leaf") and len(only[0]["parts"]) == 1:
                out.append((only[0]["caption"], only[0]["parts"][0]))
            else:
                out.append((f"Region {n}", part))
        return out
    return [("", {"children": machine, "steps": top["steps"]})]


def composites_by_id(root):
    found = {}

    def visit(node):
        for part in node["parts"]:
            for child in part["children"]:
                if not child.get("leaf"):
                    found[child["id"]] = child
                    visit(child)

    visit(root)
    return found


def legend_of(root, classes, fills):
    for child in root["parts"][0]["children"]:
        if child["id"] == LEGEND_ID:
            return [
                {"name": leaf["caption"], **_paint(fills, classes.get(leaf["id"], ""))}
                for leaf in child["parts"][0]["children"]
            ]
    return []


def _paint(fills, cls):
    style = fills.get(cls, {})
    return {"fill": style.get("fill", "#f4f6f7"), "stroke": style.get("stroke", "#566573")}


# Code cites


class SourceIndex:
    """Where a cited file lives: the cite's feature's own file of that name, or the one file of
    that name under `features/`."""

    def __init__(self, root):
        self.root = root
        self.files = {}
        features = root / "features"
        for folder, dirs, files in os.walk(features):
            here = Path(folder)
            dirs[:] = sorted(
                d
                for d in dirs
                if not d.startswith(".")
                and d != "node_modules"
                and not (here.parent == features and d == "spec")
            )
            for name in sorted(files):
                self.files.setdefault(name, []).append(here / name)

    def find(self, name, feature, word=None):
        """The one file the cite names, or None: the files of its feature before the rest, and
        for a cite of a name, such as queue.py `remove`, the files that define it."""
        tail = name.split("/")
        found = [p for p in self.files.get(tail[-1], []) if list(p.parts[-len(tail) :]) == tail]
        own = [p for p in found if p.relative_to(self.root / "features").parts[0] == feature]
        pick = own or found
        if word and len(pick) > 1:
            pick = [p for p in pick if _defines(p, word)]
        return pick[0] if len(pick) == 1 else None


def _defines(path, word):
    text = path.read_text(encoding="utf-8", errors="replace")
    return re.search(rf"^\s*(def|class)\s+{re.escape(word)}\b", text, re.M) is not None


def cites_of(text, feature, index):
    out = []
    for m in CITE.finditer(text):
        name, number, word = m.group(1), m.group(2), m.group(3)
        cite = Cite(text=m.group(0))
        path = index.find(name, feature, word)
        if path is not None:
            cite.path = path
            lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
            at = int(number) if number else _line_of(lines, word)
            if at and 1 <= at <= len(lines):
                cite.line = at
                cite.code = [
                    (k + 1, lines[k]) for k in range(max(0, at - 3), min(len(lines), at + 2))
                ]
        out.append(cite)
    return out


def _line_of(lines, word):
    for pattern in (rf"^\s*(def|class) {re.escape(word)}\b", rf"\b{re.escape(word)}\b"):
        for k, line in enumerate(lines):
            if re.search(pattern, line):
                return k + 1
    return None


# Reading a chart's folder


def find_charts(root, flow):
    found = sorted((root / "features").glob("*/spec/*-statechart/chart.mmd"))
    rank = {name: k for k, name in enumerate(flow.order)}
    return sorted(found, key=lambda p: (rank.get(p.parent.name[: -len("-statechart")], 99), p))


def read_text(text, name, cite=lambda text: [], question=None):
    """A chart.mmd as the page draws it, its states and steps cited by `cite`."""
    title, tree, fills, classes = read_tree(text)
    composites = composites_by_id(tree)
    regions = []
    for region_name, part in regions_of(tree):
        leaves, raw_steps = [], []
        _walk(part, [], leaves, raw_steps)
        region = Region(region_name)
        for leaf, composite in leaves:
            region.states.append(
                State(
                    id=leaf["id"],
                    label=leaf["caption"],
                    composite=composite,
                    group=classes.get(leaf["id"], ""),
                    cites=cite(leaf["caption"]),
                )
            )
        ids = {s.id for s in region.states}

        def landing(state_id):
            return _first_leaf(composites[state_id]) if state_id in composites else state_id

        for s in raw_steps:
            if s["from"] == "[*]":
                region.starts.append(landing(s["to"]))
                continue
            source, target = landing(s["from"]), landing(s["to"])
            if source not in ids or target not in ids:
                raise ChartError(f"a step from {s['from']} to {s['to']} leaves its region")
            region.steps.append(
                Step(
                    source,
                    target,
                    s["label"],
                    guard=s.get("guard", []),
                    unless=s.get("unless", False),
                    cites=cite(s["label"]),
                )
            )
        regions.append(region)
    return Chart(
        name=name,
        feature="",
        folder=Path(),
        title=title or name,
        question=title if title.endswith("?") else question or title or name,
        regions=regions,
        legend=legend_of(tree, classes, fills),
        fills=fills,
        stories="",
        summary={},
    )


def read_chart(path, root, index, flow):
    folder = path.parent
    name = folder.name[: -len("-statechart")]
    feature = folder.relative_to(root / "features").parts[0]
    chart = read_text(
        path.read_text(encoding="utf-8"),
        name,
        lambda text: cites_of(text, feature, index),
        flow.questions.get(name),
    )
    stories = folder / "stories.md"
    summary = folder / "summary.json"
    chart.feature = feature
    chart.folder = folder
    chart.stories = stories.read_text(encoding="utf-8") if stories.exists() else ""
    chart.summary = json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {}
    return chart


# Layout


def wrap_words(text, width=28):
    rows, row = [], ""
    for w in text.split():
        if row and len(row) + 1 + len(w) > width:
            rows.append(row)
            row = w
        else:
            row = f"{row} {w}" if row else w
    return [*rows, row] if row else rows


def layout(region):
    """Places the region's states in rows: each state's row is its distance in steps from the
    region's start, a row holds at most ROW_MAX states, and the order in a row follows the states
    it steps to and from (barycentres, swept down and up)."""
    states = {s.id: s for s in region.states}
    succ = {s: [] for s in states}
    pred = {s: [] for s in states}
    for step in region.steps:
        if step.source != step.target:
            succ[step.source].append(step.target)
            pred[step.target].append(step.source)
    rank = {}
    frontier = [s for s in dict.fromkeys(region.starts) if s in states]
    order = [s.id for s in region.states]
    while len(rank) < len(states):
        if not frontier:
            frontier = [next(s for s in order if s not in rank)]
            base = max(rank.values(), default=-1) + 1
        else:
            base = 0
        for s in frontier:
            rank[s] = base
        while frontier:
            nxt = []
            for s in frontier:
                for t in succ[s]:
                    if t not in rank:
                        rank[t] = rank[s] + 1
                        nxt.append(t)
            frontier = nxt
    layers = [[] for _ in range(max(rank.values()) + 1)]
    for s in order:
        layers[rank[s]].append(s)
    rows = []
    for layer in layers:
        rows.extend(layer[k : k + ROW_MAX] for k in range(0, len(layer), ROW_MAX))
    rows = [r for r in rows if r]
    row_of = {s: k for k, r in enumerate(rows) for s in r}
    near = {s: [*succ[s], *pred[s]] for s in states}
    for sweep in range(16):
        span = range(1, len(rows)) if sweep % 2 == 0 else range(len(rows) - 2, -1, -1)
        side = -1 if sweep % 2 == 0 else 1
        for k in span:
            pos = {s: i for r in rows for i, s in enumerate(r)}

            def centre(s, k=k, side=side, pos=pos):
                xs = [pos[t] for t in near[s] if row_of[t] == k + side]
                return sum(xs) / len(xs) if xs else pos[s]

            rows[k].sort(key=centre)
    for s in region.states:
        s.lines = wrap_words(s.label)
        s.heads = wrap_words(s.composite, 30) if s.composite else []
        s.h = PAD_Y * 2 + LINE_H * (len(s.lines) + len(s.notes)) + 13 * len(s.heads)
    widest = max(len(r) for r in rows)
    width = widest * NODE_W + (widest - 1) * GAP_X
    y = REGION_PAD + 28
    for r in rows:
        tallest = max(states[s].h for s in r)
        span = len(r) * NODE_W + (len(r) - 1) * GAP_X
        x0 = REGION_PAD + (width - span) / 2
        for i, s in enumerate(r):
            states[s].x = x0 + i * (NODE_W + GAP_X)
            states[s].y = y + (tallest - states[s].h) / 2
        y += tallest + GAP_Y
    region.w = width + REGION_PAD * 2
    region.h = y - GAP_Y + REGION_PAD
    return row_of


# Drawing


def esc(text):
    return html.escape(str(text), quote=True)


def edge_path(a, b, row_of, k, n, width):
    """A curve from a to b: down from a's bottom to b's top when b is in a later row, and
    round the side otherwise. k of n spreads parallel curves apart. Returns the path and the
    curve's middle point."""
    spread = (k - (n - 1) / 2) * 10
    ax, bx = a.x + NODE_W / 2, b.x + NODE_W / 2
    if row_of[b.id] > row_of[a.id]:
        x1, y1 = ax + spread, a.y + a.h
        x2, y2 = bx + spread, b.y
        dy = max(30, (y2 - y1) / 2)
        points = [(x1, y1), (x1, y1 + dy), (x2, y2 - dy), (x2, y2)]
    else:
        right = (ax + bx) / 2 >= width / 2
        sx = a.x + NODE_W if right else a.x
        tx = b.x + NODE_W if right else b.x
        y1 = a.y + a.h / 2 + spread
        y2 = b.y + b.h / 2 + spread
        reach = 50 + abs(y2 - y1) * 0.25 + abs(k) * 6
        out = reach if right else -reach
        points = [(sx, y1), (sx + out, y1), (tx + out, y2), (tx, y2)]
    (x1, y1), (cx1, cy1), (cx2, cy2), (x2, y2) = points
    d = f"M{x1:.1f},{y1:.1f} C{cx1:.1f},{cy1:.1f} {cx2:.1f},{cy2:.1f} {x2:.1f},{y2:.1f}"
    mid = ((x1 + 3 * cx1 + 3 * cx2 + x2) / 8, (y1 + 3 * cy1 + 3 * cy2 + y2) / 8)
    return d, mid


def draw_region(chart, r, offset, width):
    region = chart.regions[r]
    row_of = region.row_of
    shift = (width - region.w) / 2
    states = {s.id: s for s in region.states}
    arrow = f"url(#arrow-{esc(chart.name)})"
    pairs = {}
    for n, step in enumerate(region.steps):
        pairs.setdefault((step.source, step.target), []).append(n)

    def down(source, target):
        return (source, target) if row_of[target] > row_of[source] else (target, source)

    # The pairs that share two states, either way round, fan out side by side.
    fans = {}
    for source, target in pairs:
        fans.setdefault(down(source, target), []).append(source)
    parts = [
        f'<g class="region" transform="translate(0,{offset:.1f})">',
        f'<rect class="region-box" x="0" y="0" width="{width:.1f}" height="{region.h:.1f}"'
        ' rx="18"/>',
        f'<g transform="translate({shift:.1f},0)">',
    ]
    if region.name:
        parts.append(
            f'<text class="region-name" x="{REGION_PAD}" y="{REGION_PAD + 4}">'
            f"{esc(region.name)}</text>"
        )
    parts.append('<g class="edges">')
    for (source, target), steps in pairs.items():
        a, b = states[source], states[target]
        if source == target:
            x, y = a.x + NODE_W, a.y + a.h / 2
            d = (
                f"M{x:.1f},{y - 8:.1f} C{x + 40:.1f},{y - 30:.1f} {x + 40:.1f},{y + 30:.1f}"
                f" {x:.1f},{y + 8:.1f}"
            )
        else:
            fan = fans[down(source, target)]
            d, _ = edge_path(a, b, row_of, fan.index(source), len(fan), region.w - REGION_PAD * 2)
        ids = " ".join(f"{chart.name}-e{r}-{n}" for n in steps)
        said = esc(" | ".join(region.steps[n].label for n in steps))
        parts.append(
            f'<path class="edge" d="{d}" data-from="{esc(source)}" data-to="{esc(target)}"'
            f' data-steps="{ids}" marker-end="{arrow}"><title>{said}</title></path>'
        )
    parts.append("</g>")
    for s in dict.fromkeys(region.starts):
        st = states.get(s)
        if st:
            cx = st.x + NODE_W / 2
            parts.append(
                f'<circle class="start" cx="{cx:.1f}" cy="{st.y - 34:.1f}" r="7"/>'
                f'<path class="edge start-edge" d="M{cx:.1f},{st.y - 27:.1f} L{cx:.1f},{st.y:.1f}"'
                f' marker-end="{arrow}"/>'
            )
    for s in region.states:
        paint = _paint(chart.fills, s.group)
        mid = s.x + NODE_W / 2
        parts.append(
            f'<g class="st" id="{esc(chart.name)}-{esc(s.id)}" data-id="{esc(s.id)}" tabindex="0"'
            f' role="button" style="--fill:{esc(paint["fill"])};--stroke:{esc(paint["stroke"])}">'
            f'<rect x="{s.x:.1f}" y="{s.y:.1f}" width="{NODE_W}" height="{s.h:.1f}" rx="10"/>'
        )
        ty = s.y + PAD_Y + LINE_H - 3
        for head in s.heads:
            parts.append(f'<text class="comp" x="{mid:.1f}" y="{ty:.1f}">{esc(head)}</text>')
            ty += 13
        parts.append(f'<text x="{mid:.1f}" y="{ty:.1f}">')
        for k, line in enumerate(s.lines):
            parts.append(f'<tspan x="{mid:.1f}" dy="{0 if k == 0 else LINE_H}">{esc(line)}</tspan>')
        parts.append("</text></g>")
    parts.append("</g></g>")
    return "".join(parts)


def draw_chart(chart):
    """The chart's regions one under another, each as wide as the widest, so a chart is about
    one desk frame wide and grows down, where the frame scrolls."""
    for region in chart.regions:
        region.row_of = layout(region)
    width = max(region.w for region in chart.regions)
    pieces, offset = [], 0.0
    for r, region in enumerate(chart.regions):
        pieces.append(draw_region(chart, r, offset, width))
        offset += region.h + REGION_GAP
    height = offset - REGION_GAP
    return (
        f'<svg class="chart" viewBox="-20 -20 {width + 40:.1f} {height + 40:.1f}"'
        f' data-w="{width + 40:.1f}" data-h="{height + 40:.1f}" xmlns="http://www.w3.org/2000/svg"'
        f' role="img" aria-label="{esc(chart.title)}">'
        f'<defs><marker id="arrow-{esc(chart.name)}" viewBox="0 0 10 10" refX="9" refY="5"'
        ' markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z"/></marker></defs>' + "".join(pieces) + "</svg>"
    )


# Overviews: one box per group, and the map of the whole flow, one box per chart


def draw_boxes(regions, prefix, links, attrs, css, dots=True):
    """Boxes and labelled arrows, each region laid out as a chart's is, the regions side by side.
    `links[r]` maps a pair of box ids to the arrow's label, and `attrs(state)` gives the
    attributes of a box's <g>. An arrow between two boxes of one row runs straight across the gap
    between them, its label above it. No xmlns: the page is HTML, which needs none."""
    for r, region in enumerate(regions):
        region.steps = [Step(a, b, said) for (a, b), said in links[r].items()]
        region.row_of = layout(region)
    titled = 26 if any(region.name for region in regions) else 0
    height = max(region.h for region in regions) + titled
    arrow = f"arrow-{esc(prefix)}"
    parts, offset = [], 0.0
    xs = [0.0]
    for r, region in enumerate(regions):
        states = {s.id: s for s in region.states}
        row_of = region.row_of
        if region.name:
            parts.append(
                f'<text class="region-name" x="{offset + REGION_PAD:.1f}" y="{REGION_PAD - 6}">'
                f"{esc(region.name)}</text>"
            )
        parts.append(f'<g transform="translate({offset:.1f},{titled})">')
        fans = {}
        for a, b in links[r]:
            key = (a, b) if row_of[b] > row_of[a] else (b, a)
            fans.setdefault(key, []).append(a)
        labels = []
        for (a, b), said in links[r].items():
            sa, sb = states[a], states[b]
            if row_of[a] == row_of[b]:
                y = min(sa.y + sa.h / 2, sb.y + sb.h / 2)
                x1, x2 = (sa.x + NODE_W, sb.x) if sa.x < sb.x else (sa.x, sb.x + NODE_W)
                d = f"M{x1:.1f},{y:.1f} L{x2:.1f},{y:.1f}"
                mx, my = (x1 + x2) / 2, max(sa.y + sa.h, sb.y + sb.h) + 14
            else:
                key = (a, b) if row_of[b] > row_of[a] else (b, a)
                fan = fans[key]
                d, (mx, my) = edge_path(
                    sa, sb, row_of, fan.index(a), len(fan), region.w - 2 * REGION_PAD
                )
            xs.extend(offset + float(x) for x in re.findall(r"(-?[\d.]+),", d))
            parts.append(
                f'<path class="{css}-edge" d="{d}" data-from="{esc(a)}" data-to="{esc(b)}"'
                f' marker-end="url(#{arrow})"><title>{esc(said)}</title></path>'
            )
            w = 7.2 * len(said) + 14
            labels.append(
                f'<g class="{css}-count"><rect x="{mx - w / 2:.1f}" y="{my - 10:.1f}"'
                f' width="{w:.1f}" height="20" rx="10"/>'
                f'<text x="{mx:.1f}" y="{my + 4.5:.1f}">{esc(said)}</text></g>'
            )
        for s in dict.fromkeys(region.starts) if dots else []:
            st = states[s]
            cx = st.x + NODE_W / 2
            parts.append(
                f'<circle class="start" cx="{cx:.1f}" cy="{st.y - 34:.1f}" r="7"/>'
                f'<path class="{css}-edge" d="M{cx:.1f},{st.y - 27:.1f} L{cx:.1f},{st.y:.1f}"'
                f' marker-end="url(#{arrow})"/>'
            )
        for s in region.states:
            mid = s.x + NODE_W / 2
            parts.append(
                f'<g class="{css}-box" {attrs(s)} tabindex="0" role="button">'
                f'<rect x="{s.x:.1f}" y="{s.y:.1f}" width="{NODE_W}" height="{s.h:.1f}" rx="12"/>'
                f'<text x="{mid:.1f}" y="{s.y + PAD_Y + LINE_H - 3:.1f}">'
            )
            for k, line in enumerate(s.lines):
                parts.append(
                    f'<tspan x="{mid:.1f}" dy="{0 if k == 0 else LINE_H}">{esc(line)}</tspan>'
                )
            parts.extend(
                f'<tspan class="note" x="{mid:.1f}" dy="{LINE_H}">{esc(line)}</tspan>'
                for line in s.notes
            )
            parts.append("</text></g>")
        parts.extend(labels)
        parts.append("</g>")
        offset += region.w
        xs.append(offset)
    left, right = min(xs) - 20, max(xs) + 20
    span = right - left
    top = 0 if dots else REGION_PAD
    return (
        f'<svg class="{css}" viewBox="{left:.1f} {top - 20} {span:.1f} {height - top + 40:.1f}"'
        f' style="max-width:{span * 1.1:.0f}px;min-width:{span * 0.9:.0f}px"'
        f' role="img" aria-label="{esc(prefix)}"><defs><marker id="{arrow}" viewBox="0 0 10 10"'
        ' refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        '<path d="M0,0 L10,5 L0,10 z"/></marker></defs>' + "".join(parts) + "</svg>"
    )


def overview_figure(chart):
    """The chart's overview, as its tab shows it above the chart: a box per group, a click on
    which moves the chart below to that group's states."""
    ov = overview_of(chart)
    regions, links, boxes = [], [], {}
    for part in ov.parts:
        region = Region(part.name, starts=[b.key for b in part.boxes if b.start])
        for box in part.boxes:
            boxes[box.key] = box
            region.states.append(
                State(id=box.key, label=box.name, group=box.group, notes=[caption(box)])
            )
        regions.append(region)
        links.append({pair: plural(n, "step") for pair, n in part.links.items()})

    def attrs(s):
        paint = _paint(chart.fills, s.group)
        return (
            f'id="{esc(chart.name)}-ov-{esc(s.id)}" data-box="{esc(s.id)}"'
            f' data-name="{esc(s.label)}" data-states="{esc(" ".join(boxes[s.id].states))}"'
            f' style="--fill:{esc(paint["fill"])};--stroke:{esc(paint["stroke"])}"'
            f' aria-label="{esc(s.label)}: {esc(s.notes[0])}"'
        )

    count = len(ov.boxes())
    return (
        f'<figure class="overview" data-chart="{esc(chart.name)}">'
        f"<figcaption>Overview: {count} {'box' if count == 1 else 'boxes'}, one per group"
        f"{', ' if count > MOST else ''}{'more than ' + str(MOST) if count > MOST else ''}."
        " Tap a box to move the chart below to its states.</figcaption>"
        f"{draw_boxes(regions, f'{chart.name}-ov', links, attrs, 'ov')}</figure>"
    )


def flow_section(charts, flow):
    """The Overview tab: one box per chart, what it charts and the question it answers, the
    hand-offs between them as numbered arrows, and the hand-offs listed under the map, each end
    a button to the group it names."""
    by_name = {c.name: c for c in charts}
    first = flow.handoffs[0]["from"][0] if flow.handoffs else charts[0].name
    region = Region("", starts=[first if first in by_name else charts[0].name])
    for chart in charts:
        groups = len(chart.legend)
        states = sum(len(r.states) for r in chart.regions)
        region.states.append(
            State(
                id=chart.name,
                label=flow.things.get(chart.name, chart.name),
                notes=[
                    *wrap_words(chart.question),
                    f"{plural(states, 'state')}, {plural(groups, 'group')}",
                ],
            )
        )
    links, items = {}, []
    for n, h in enumerate(flow.handoffs, 1):
        ends = []
        for side in ("from", "to"):
            name, group = h[side]
            chart = by_name.get(name)
            if chart is None:
                raise ChartError(f"{flow.path}: hand-off {n} names {name}, which is no chart")
            ov = overview_of(chart)
            keys = [b.key for b in ov.boxes() if b.name == group and b.group]
            if not keys:
                have = ", ".join(g["name"] for g in chart.legend)
                raise ChartError(
                    f"{flow.path}: hand-off {n} names the group {group!r} of {name}, which has"
                    f" no such group; its groups: {have}"
                )
            ends.append(
                f'<button class="go" data-chart="{esc(name)}" data-box="{esc(keys[0])}">'
                f"{esc(name)} &rsaquo; {esc(group)}</button>"
            )
        pair = (h["from"][0], h["to"][0])
        links[pair] = f"{links[pair]}, {n}" if pair in links else str(n)
        items.append(
            f'<li>{ends[0]} &rarr; {ends[1]}<span class="says">{esc(h["says"])}</span></li>'
        )

    def attrs(s):
        return f'id="flow-{esc(s.id)}" data-chart="{esc(s.id)}" aria-label="{esc(s.label)}"'

    map_svg = draw_boxes([region], "flow", [links], attrs, "flow", dots=False)
    listed = f'<ol class="handoffs">{"".join(items)}</ol>' if items else ""
    return (
        '<section class="flow-panel" data-view="overview">'
        '<header class="chart-head"><p class="feature">jstack &middot; overview</p>'
        "<h2>How a task flows through what the charts show</h2>"
        f'<p class="sub">{plural(len(charts), "chart")}, one box each: what it charts and the'
        " question it answers. Tap a box to open its chart. Each numbered arrow is a hand-off,"
        " listed below: a group of one chart leads into a group of another.</p></header>"
        f'<div class="flow-map">{map_svg}</div>'
        f"{listed}</section>"
    )


def cite_data(cite, out_dir):
    return {
        "text": cite.text,
        "href": os.path.relpath(cite.path, out_dir) if cite.path else None,
        "line": cite.line,
        "code": cite.code,
    }


def chart_data(chart, out_dir):
    states, steps = {}, []
    for r, region in enumerate(chart.regions):
        for s in region.states:
            states[s.id] = {
                "label": s.label,
                "composite": s.composite,
                "region": region.name,
                "start": s.id in region.starts,
                "fill": _paint(chart.fills, s.group)["fill"],
                "cites": [cite_data(c, out_dir) for c in s.cites],
            }
        for n, step in enumerate(region.steps):
            steps.append(
                {
                    "id": f"{chart.name}-e{r}-{n}",
                    "from": step.source,
                    "to": step.target,
                    "label": step.label,
                    "guard": step.guard,
                    "unless": step.unless,
                    "cites": [cite_data(c, out_dir) for c in step.cites],
                }
            )
    return {"states": states, "steps": steps}


def stories_html(text):
    """stories.md as HTML: headings, list items, fenced code and paragraphs, all escaped."""
    if not text.strip():
        return '<p class="quiet">No bug paths: every rule the spec checks holds on this chart.</p>'
    out, para, fence = [], [], None

    def inline(s):
        s = esc(s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        return re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)

    def flush():
        if para:
            out.append(f"<p>{inline(' '.join(para))}</p>")
            para.clear()

    for line in text.split("\n"):
        if line.startswith("```"):
            flush()
            if fence is None:
                fence = []
            else:
                out.append(f"<pre>{esc(chr(10).join(fence))}</pre>")
                fence = None
            continue
        if fence is not None:
            fence.append(line)
            continue
        m = re.match(r"(#{1,6})\s+(.*)$", line)
        if m:
            flush()
            level = min(6, len(m.group(1)) + 2)
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
        elif re.match(r"\s*([-*]|\d+\.)\s+", line):
            flush()
            out.append(f"<li>{inline(re.sub(r'^\s*([-*]|\d+\.)\s+', '', line))}</li>")
        elif not line.strip():
            flush()
        else:
            para.append(line.strip())
    flush()
    if fence is not None:
        out.append(f"<pre>{esc(chr(10).join(fence))}</pre>")
    return "\n".join(out)


def overviews(charts, flow):
    """The page's overview parts, by chart name and "Overview" for the map: drawn from the
    charts' groups alone, with no code a chart cites, so a check that each is in the committed
    page holds while the code moves under the charts."""
    out = {"Overview": flow_section(charts, flow)}
    for chart in charts:
        out[chart.name] = overview_figure(chart)
    return out


def page(charts, out_dir, flow):
    parts = overviews(charts, flow)
    tabs = [
        '<button class="tab" role="tab" data-view="overview" aria-selected="true">'
        '<span class="tab-name">Overview</span>'
        '<span class="tab-q">How do the charts hand off to each other?</span></button>'
    ]
    panels, data = [parts["Overview"]], {}
    for chart in charts:
        data[chart.name] = chart_data(chart, out_dir)
        count = sum(len(r.states) for r in chart.regions)
        steps = sum(len(r.steps) for r in chart.regions)
        tabs.append(
            f'<button class="tab" role="tab" data-chart="{esc(chart.name)}"'
            ' aria-selected="false">'
            f'<span class="tab-name">{esc(chart.name)}</span>'
            f'<span class="tab-q">{esc(chart.question)}</span></button>'
        )
        png = os.path.relpath(chart.folder / "chart.png", out_dir)
        spec = os.path.relpath(chart.folder.parent / "README.md", out_dir)
        named = [f"<em>{esc(r.name)}</em>" for r in chart.regions if r.name]
        at_once = (
            f" {len(named)} parts move at the same time: {', '.join(named[:-1])} and {named[-1]}."
            if len(named) > 1
            else ""
        )
        every = chart.summary.get("allTransitions")
        drawn = chart.summary.get("chartTransitions", steps)
        sizes = (
            f"{count} states, {drawn} of {every} steps drawn: the way into each state and a way"
            " out of each."
            if every and drawn < every
            else f"{count} states, {steps} steps."
        )
        model = chart.summary.get("modelStates")
        model_note = f" TLC walked {model} model states to draw it." if model else ""
        panels.append(
            f'<section class="chart-panel" data-chart="{esc(chart.name)}" hidden>'
            '<header class="chart-head">'
            f'<p class="feature">{esc(chart.feature)} &middot; {esc(chart.name)}</p>'
            f"<h2>{esc(chart.question)}</h2>"
            f'<p class="sub">{sizes}{at_once}{model_note}'
            f' Spec: <a href="{esc(spec)}">README</a> &middot;'
            f' <a href="{esc(png)}">chart.png</a></p></header>'
            f"{parts[chart.name]}"
            '<div class="stage"><div class="viewport" tabindex="0"'
            ' aria-label="chart, drag or scroll to move, pinch or ctrl and scroll to zoom">'
            f"{draw_chart(chart)}</div>"
            '<div class="zoom"><button data-zoom="in" aria-label="zoom in">+</button>'
            '<button data-zoom="out" aria-label="zoom out">&minus;</button>'
            '<button data-zoom="fit" aria-label="fit the chart">fit</button></div></div>'
            '<details class="stories"><summary>Bug paths (stories.md)</summary>'
            f"{stories_html(chart.stories)}</details></section>"
        )
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return (
        TEMPLATE.replace("{{TABS}}", "".join(tabs))
        .replace("{{PANELS}}", "".join(panels))
        .replace("{{DATA}}", payload)
        .replace(
            "{{FLOW}}",
            f" and the map in <code>{esc(os.path.relpath(flow.path, out_dir))}</code>"
            if flow.path
            else "",
        )
        .replace("{{STYLE}}", STYLE)
        .replace("{{SCRIPT}}", SCRIPT)
    )


def repo_root(cwd):
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return Path(cwd)
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path(cwd)


def read_all(root, flow):
    root = Path(root).resolve()
    paths = find_charts(root, flow)
    if not paths:
        raise ChartError(f"no features/*/spec/*-statechart/chart.mmd under {root}")
    index = SourceIndex(root)
    charts = []
    for path in paths:
        try:
            charts.append(read_chart(path, root, index, flow))
        except ChartError as e:
            raise ChartError(f"{path.relative_to(root)}: {e}") from e
    return root, charts


def render(root, out, flow=None):
    """The page the charts under `root` and the map in `flow` make, for a page written at
    `out`."""
    flow = load_flow(flow)
    root, charts = read_all(root, flow)
    return page(charts, Path(out).resolve().parent, flow)


def build(root, out, flow=None):
    """Writes the page for every chart under `root` to `out`: the charts it drew."""
    flow = load_flow(flow)
    root, charts = read_all(root, flow)
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    text = page(charts, out.parent, flow)
    scratch = out.with_name(f".{out.name}.part")
    scratch.write_text(text, encoding="utf-8")
    os.replace(scratch, out)
    return charts


STYLE = (Path(__file__).parent / "site.css").read_text(encoding="utf-8")
SCRIPT = (Path(__file__).parent / "site.js").read_text(encoding="utf-8")
TEMPLATE = (Path(__file__).parent / "site.html").read_text(encoding="utf-8")
