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
from dataclasses import dataclass, field
from pathlib import Path

from statechart.lib import LEGEND_ID, ChartError, unwrap

# The question a chart answers, for a chart whose title does not ask one.
QUESTIONS = {
    "RowLife": "What happens to my row?",
    "HomeTreeToday": "When a child home stalls or retires, does what it had out still reach you?",
}

# The order the page lists the charts in: from the user's row to the merge, then the homes.
ORDER = ["RowLife", "ThreadLife", "PrVerdict", "FlowToday", "MainRed", "HomeTreeToday"]

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


def find_charts(root):
    found = sorted((root / "features").glob("*/spec/*-statechart/chart.mmd"))
    rank = {name: k for k, name in enumerate(ORDER)}
    return sorted(found, key=lambda p: (rank.get(p.parent.name[: -len("-statechart")], 99), p))


def read_chart(path, root, index):
    folder = path.parent
    name = folder.name[: -len("-statechart")]
    feature = folder.relative_to(root / "features").parts[0]
    title, tree, fills, classes = read_tree(path.read_text(encoding="utf-8"))
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
                    cites=cites_of(leaf["caption"], feature, index),
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
                    cites=cites_of(s["label"], feature, index),
                )
            )
        regions.append(region)
    stories = folder / "stories.md"
    summary = folder / "summary.json"
    question = title if title.endswith("?") else QUESTIONS.get(name, title or name)
    return Chart(
        name=name,
        feature=feature,
        folder=folder,
        title=title or name,
        question=question,
        regions=regions,
        legend=legend_of(tree, classes, fills),
        fills=fills,
        stories=stories.read_text(encoding="utf-8") if stories.exists() else "",
        summary=json.loads(summary.read_text(encoding="utf-8")) if summary.exists() else {},
    )


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
        s.h = PAD_Y * 2 + LINE_H * len(s.lines) + 13 * len(s.heads)
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
    round the side otherwise. k of n spreads parallel curves apart."""
    spread = (k - (n - 1) / 2) * 10
    ax, bx = a.x + NODE_W / 2, b.x + NODE_W / 2
    if row_of[b.id] > row_of[a.id]:
        x1, y1 = ax + spread, a.y + a.h
        x2, y2 = bx + spread, b.y
        dy = max(30, (y2 - y1) / 2)
        return (
            f"M{x1:.1f},{y1:.1f} C{x1:.1f},{y1 + dy:.1f} {x2:.1f},{y2 - dy:.1f} {x2:.1f},{y2:.1f}"
        )
    right = (ax + bx) / 2 >= width / 2
    sx = a.x + NODE_W if right else a.x
    tx = b.x + NODE_W if right else b.x
    y1 = a.y + a.h / 2 + spread
    y2 = b.y + b.h / 2 + spread
    reach = 50 + abs(y2 - y1) * 0.25 + abs(k) * 6
    out = reach if right else -reach
    return f"M{sx:.1f},{y1:.1f} C{sx + out:.1f},{y1:.1f} {tx + out:.1f},{y2:.1f} {tx:.1f},{y2:.1f}"


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
            d = edge_path(a, b, row_of, fan.index(source), len(fan), region.w - REGION_PAD * 2)
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


def page(charts, out_dir):
    tabs, panels, data = [], [], {}
    for k, chart in enumerate(charts):
        data[chart.name] = chart_data(chart, out_dir)
        count = sum(len(r.states) for r in chart.regions)
        steps = sum(len(r.steps) for r in chart.regions)
        tabs.append(
            f'<button class="tab" role="tab" data-chart="{esc(chart.name)}"'
            f' aria-selected="{"true" if k == 0 else "false"}">'
            f'<span class="tab-name">{esc(chart.name)}</span>'
            f'<span class="tab-q">{esc(chart.question)}</span></button>'
        )
        legend = "".join(
            f'<li><span class="swatch" style="--fill:{esc(g["fill"])};--stroke:{esc(g["stroke"])}">'
            f"</span>{esc(g['name'])}</li>"
            for g in chart.legend
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
            f'<section class="chart-panel" data-chart="{esc(chart.name)}"'
            f'{"" if k == 0 else " hidden"}><header class="chart-head">'
            f'<p class="feature">{esc(chart.feature)} &middot; {esc(chart.name)}</p>'
            f"<h2>{esc(chart.question)}</h2>"
            f'<p class="sub">{sizes}{at_once}{model_note}'
            f' Spec: <a href="{esc(spec)}">README</a> &middot;'
            f' <a href="{esc(png)}">chart.png</a></p>'
            f'<ul class="legend">{legend}</ul></header>'
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


def read_all(root):
    root = Path(root).resolve()
    paths = find_charts(root)
    if not paths:
        raise ChartError(f"no features/*/spec/*-statechart/chart.mmd under {root}")
    index = SourceIndex(root)
    charts = []
    for path in paths:
        try:
            charts.append(read_chart(path, root, index))
        except ChartError as e:
            raise ChartError(f"{path.relative_to(root)}: {e}") from e
    return root, charts


def render(root, out):
    """The page the charts under `root` make, for a page written at `out`."""
    root, charts = read_all(root)
    return page(charts, Path(out).resolve().parent)


def build(root, out):
    """Writes the page for every chart under `root` to `out`: the charts it drew."""
    root, charts = read_all(root)
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    text = page(charts, out.parent)
    scratch = out.with_name(f".{out.name}.part")
    scratch.write_text(text, encoding="utf-8")
    os.replace(scratch, out)
    return charts


STYLE = (Path(__file__).parent / "site.css").read_text(encoding="utf-8")
SCRIPT = (Path(__file__).parent / "site.js").read_text(encoding="utf-8")
TEMPLATE = (Path(__file__).parent / "site.html").read_text(encoding="utf-8")
