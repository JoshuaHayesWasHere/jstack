"""statechart excalidraw: draws a chart.mmd as an Excalidraw scene. Each state is a labelled box,
each step an arrow bound to the boxes at its two ends with its label on it, each region a frame,
and each composite a dashed box around its states. The layout is layered, top to bottom, inside
each composite and region in turn, so no two boxes overlap; a step's label is a node of the layout
in its own right, so labels do not sit on boxes either. The same chart always gives the same file,
byte for byte."""

import json
import os
import re
import sys
import tempfile
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from statechart.lib import LEGEND_ID, ChartError

USAGE = "statechart excalidraw CHART.mmd --out FILE.excalidraw"
HELP = f"""Usage: {USAGE}

excalidraw CHART.mmd
  Draws the chart as an Excalidraw scene and writes it to FILE.excalidraw, which excalidraw.com
  opens. Each state is a box in its group's colour, each step an arrow bound to both of its states,
  with the step's label on it, each region of a chart split by -- a frame, and each composite a
  dashed box around its states. The chart's Legend is a frame of its own. A rebuild of the same
  chart writes the same bytes.

Exit codes
  0  the scene is written
  2  the arguments are wrong, the chart cannot be read, or the file cannot be written"""

FONT = 6
STATE_FONT = 16
LABEL_FONT = 14
LINE_HEIGHT = 1.25
CHAR_WIDTH = 0.6
BOX_PAD_X = 16
BOX_PAD_Y = 12
COMPOSITE_PAD = 24
FRAME_PAD = 40
FRAME_GAP = 120
NODE_GAP = 36
ROW_GAP = 28
DUMMY = 8
START = 22
SWEEPS = 8
TEXT = "#1e1e1e"
PLAIN = ("#ffffff", "#1e1e1e", TEXT)
_ID = r"[A-Za-z_]\w*"


@dataclass(eq=False)
class Box:
    """A state, a start dot, a composite or a region; a composite and a region hold children."""

    id: str
    caption: str
    kind: str
    children: list = field(default_factory=list)
    parent: "Box | None" = None
    w: float = 0.0
    h: float = 0.0
    x: float = 0.0
    y: float = 0.0


@dataclass(eq=False)
class Step:
    source: str
    target: str
    label: str
    points: list = field(default_factory=list)


@dataclass
class Chart:
    title: str
    regions: list
    steps: list
    legend: list
    classes: dict
    styles: dict


def lines_of(caption):
    return [re.sub(r"#quot;|#34;", '"', s).strip() for s in re.split(r"<br\s*/?>", caption)]


def text_size(lines, size):
    return (
        max(len(s) for s in lines) * size * CHAR_WIDTH,
        len(lines) * size * LINE_HEIGHT,
    )


def read_chart(text):
    """The chart as it is drawn: its regions, each a tree of composites and states, and its
    steps as written. Raises ChartError for a line it cannot read or a brace left open or
    unmatched. A composite needs no [*] start here: one that only groups states is drawn as a
    box around them."""
    front = re.match(r"\A\s*---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(\r?\n|\Z)", text)
    title = ""
    if front:
        found = re.search(r'^title:\s*"?(.*?)"?\s*$', front.group(1), re.M)
        title = found.group(1) if found else ""
        text = text[front.end() :]
    root = Box("chart", title, "region")
    parts = {id(root): [[]]}
    stack = [root]
    boxes = {}
    mentioned = {}
    steps = []
    styles = {}
    classes = {}
    legend = []
    starts = {}

    def part():
        return parts[id(stack[-1])][-1]

    def place(box, into):
        into.append(box)
        boxes[box.id] = box

    def start(holder_part):
        key = id(holder_part)
        if key not in starts:
            n = len(starts)
            dot = Box(f"*start{n}", "", "start")
            starts[key] = dot
            holder_part.insert(0, dot)
            boxes[dot.id] = dot
        return starts[key].id

    for raw in text.split("\n"):
        line = raw.strip()
        inline = re.match(rf"^(.*?)({_ID}):::([\w-]+)(.*)$", line)
        while inline:
            classes[inline.group(2)] = inline.group(3)
            line = f"{inline.group(1)}{inline.group(2)}{inline.group(4)}"
            inline = re.match(rf"^(.*?)({_ID}):::([\w-]+)(.*)$", line)
        line = re.sub(r"\[\*\]:::[\w-]+", "[*]", line)
        if not line or line.startswith("%%") or re.match(r"(stateDiagram|direction|note)", line):
            continue
        defined = re.match(r"classDef\s+([\w-]+)\s+(.*)$", line)
        if defined:
            props = dict(
                kv.split(":", 1) for kv in defined.group(2).rstrip(";").split(",") if ":" in kv
            )
            styles[defined.group(1)] = (
                props.get("fill", PLAIN[0]).strip(),
                props.get("stroke", PLAIN[1]).strip(),
                props.get("color", PLAIN[2]).strip(),
            )
            continue
        given = re.match(r"class\s+([\w,\s]+?)\s+([\w-]+)\s*;?$", line)
        if given:
            for state_id in given.group(1).split(","):
                classes[state_id.strip()] = given.group(2)
            continue
        m = re.match(rf'state\s+"([^"]*)"\s+as\s+({_ID})\s*(\{{)?\s*$', line) or re.match(
            rf"state\s+()({_ID})\s*(\{{)?\s*$", line
        )
        if m:
            caption, state_id, opens = m.group(1) or m.group(2), m.group(2), m.group(3)
            if stack[-1].id == LEGEND_ID:
                legend.append((caption, state_id))
                continue
            if opens and state_id == LEGEND_ID:
                stack.append(Box(LEGEND_ID, caption, "legend"))
                parts[id(stack[-1])] = [[]]
                continue
            if opens:
                box = Box(state_id, caption, "composite")
                place(box, part())
                parts[id(box)] = [[]]
                stack.append(box)
            elif state_id not in boxes:
                place(Box(state_id, caption, "state"), part())
            continue
        if line == "}":
            if len(stack) == 1:
                raise ChartError("unmatched } in the chart")
            stack.pop()
            continue
        if line == "--":
            parts[id(stack[-1])].append([])
            continue
        m = re.match(rf"(\[\*\]|{_ID})\s*-->\s*(\[\*\]|{_ID})(?:\s*:\s*(.*))?$", line)
        if m:
            ends = []
            for end in (m.group(1), m.group(2)):
                if end == "[*]":
                    ends.append(start(part()))
                else:
                    mentioned.setdefault(end, part())
                    ends.append(end)
            steps.append(Step(ends[0], ends[1], m.group(3) or ""))
            continue
        m = re.match(rf"({_ID})\s*:\s*(.*)$", line)
        if m:
            if m.group(1) not in boxes:
                place(Box(m.group(1), m.group(2), "state"), part())
            continue
        raise ChartError(f"cannot read chart line: {line}")
    if len(stack) != 1:
        raise ChartError("the chart has an unclosed {")
    for state_id, at in mentioned.items():
        if state_id not in boxes:
            place(Box(state_id, state_id, "state"), at)

    def adopt(box, children):
        box.children = children
        for child in children:
            child.parent = box
            if child.kind == "composite":
                adopt(child, parts[id(child)][0])

    top = list(parts[id(root)][0])
    machine = [b for b in top if b.kind != "start"]
    split = len(machine) == 1 and machine[0].kind == "composite" and len(parts[id(machine[0])]) > 1
    regions = []
    if split:
        holder_ids = set()
        for n, p in enumerate(parts[id(machine[0])]):
            only = p[0] if len(p) == 1 else None
            if (
                only
                and only.kind == "composite"
                and not any(s.target == only.id or s.source == only.id for s in steps)
            ):
                region = Box(only.id, only.caption, "region")
                adopt(region, parts[id(only)][0])
                holder_ids.add(only.id)
                boxes[only.id] = region
            else:
                region = Box(f"{machine[0].id}{n}", f"Region {n + 1}", "region")
                adopt(region, p)
            regions.append(region)
    else:
        root.caption = title or "Main"
        adopt(root, top)
        regions.append(root)
    return Chart(title, regions, steps, legend, classes, styles), boxes


def size_leaf(box):
    if box.kind == "start":
        box.w = box.h = START
        return
    w, h = text_size(lines_of(box.caption), STATE_FONT)
    box.w, box.h = round(w + 2 * BOX_PAD_X), round(h + 2 * BOX_PAD_Y)


def caption_height(box):
    return text_size(lines_of(box.caption), STATE_FONT)[1] + 8


def ancestors(box):
    out = []
    while box is not None:
        out.append(box)
        box = box.parent
    return out


def owner(step, boxes):
    """The container whose layout routes the step, and the two children of it that hold the
    step's ends."""
    a, b = boxes[step.source], boxes[step.target]
    if a is b:
        return a.parent, a, a
    up_a, up_b = ancestors(a), ancestors(b)
    for i, holder in enumerate(up_a[1:], start=1):
        if holder in up_b:
            j = up_b.index(holder)
            return holder, up_a[i - 1], up_b[j - 1]
    raise ChartError(f"the step {step.source} --> {step.target} crosses regions")


@dataclass(eq=False)
class Node:
    """A cell of one container's layered layout: a child box, a bend of a step, or a label."""

    w: float
    h: float
    box: Box | None = None
    rank: int = 0
    x: float = 0.0
    y: float = 0.0


def ranks(children, edges):
    """Each child's rank: back edges, found by a depth-first walk from the start dots and then in
    the order the chart declares, are turned around, and a child sits two ranks below the lowest
    child with a step into it, which leaves a rank between for the steps' labels."""
    out_edges = {id(c): [] for c in children}
    for a, b in edges:
        if a is not b:
            out_edges[id(a)].append(b)
    order = sorted(children, key=lambda c: c.kind != "start")
    seen, on_stack, forward = set(), set(), []
    for root in order:
        if id(root) in seen:
            continue
        walk = [(root, iter(out_edges[id(root)]))]
        seen.add(id(root))
        on_stack.add(id(root))
        while walk:
            node, rest = walk[-1]
            nxt = next(rest, None)
            if nxt is None:
                on_stack.discard(id(node))
                walk.pop()
                continue
            if id(nxt) in on_stack:
                continue
            forward.append((node, nxt))
            if id(nxt) not in seen:
                seen.add(id(nxt))
                on_stack.add(id(nxt))
                walk.append((nxt, iter(out_edges[id(nxt)])))
    incoming = {id(c): 0 for c in children}
    for _, b in forward:
        incoming[id(b)] += 1
    rank = {id(c): 0 for c in children}
    ready = [c for c in children if incoming[id(c)] == 0]
    while ready:
        c = ready.pop(0)
        for a, b in forward:
            if a is c:
                rank[id(b)] = max(rank[id(b)], rank[id(c)] + 2)
                incoming[id(b)] -= 1
                if incoming[id(b)] == 0:
                    ready.append(b)
    return rank


def layout(container, boxes, routed):
    """Sizes the container and places its children, inner containers first; each step routed
    here gets its points, relative to the container's content, in `routed`."""
    for child in container.children:
        if child.children or child.kind == "composite":
            layout(child, boxes, routed)
        else:
            size_leaf(child)
    edges = [(step, a, b) for step, (at, a, b) in routed["owners"].items() if at is container]
    rank = ranks(container.children, [(a, b) for _, a, b in edges])
    nodes = {id(c): Node(c.w, c.h, c, rank[id(c)]) for c in container.children}
    rows = {}
    for c in container.children:
        rows.setdefault(rank[id(c)], []).append(nodes[id(c)])
    links = []
    chains = []
    for step, a, b in edges:
        lo, hi = (a, b) if rank[id(a)] < rank[id(b)] or a is b else (b, a)
        top = rank[id(lo)]
        bottom = rank[id(hi)] if a is not b else top + 2
        mid = (top + bottom) // 2 if a is not b else top + 1
        chain = []
        for r in range(top + 1, bottom if a is not b else top + 2):
            if r == mid:
                lines = lines_of(step.label) if step.label else [""]
                w, h = text_size(lines, LABEL_FONT) if step.label else (DUMMY, DUMMY)
                node = Node(w + 8, h + 4, None, r)
            else:
                node = Node(DUMMY, 0, None, r)
            rows.setdefault(r, []).append(node)
            chain.append(node)
        path = [nodes[id(lo)], *chain, nodes[id(hi)]]
        for u, v in zip(path, path[1:], strict=False):
            links.append((u, v))
        chains.append((step, path if lo is a else path[::-1]))
    order(rows, links)
    place_rows(rows, links)
    pad = COMPOSITE_PAD if container.kind == "composite" else FRAME_PAD
    top_gap = caption_height(container) + pad if container.kind == "composite" else pad
    every = [n for row in rows.values() for n in row]
    width = max((n.x + n.w for n in every), default=0)
    height = max((n.y + n.h for n in every), default=0)
    container.w = round(width + 2 * pad)
    container.h = round(height + top_gap + pad)
    for n in every:
        if n.box is not None:
            n.box.x, n.box.y = n.x + pad, n.y + top_gap
    for step, path in chains:
        routed["points"][step] = (
            container,
            [(n.x + pad + n.w / 2, n.y + top_gap + n.h / 2) for n in path[1:-1]],
        )


def neighbours(links):
    up, down = {}, {}
    for u, v in links:
        down.setdefault(id(u), []).append(v)
        up.setdefault(id(v), []).append(u)
    return up, down


def order(rows, links):
    """Barycenter sweeps, down then up, to cut the crossings between each two rows."""
    up, down = neighbours(links)
    keys = sorted(rows)
    for sweep in range(SWEEPS):
        going = keys[1:] if sweep % 2 == 0 else keys[-2::-1]
        near = up if sweep % 2 == 0 else down
        for r in going:
            row = rows[r]
            at = {id(n): i for k in keys for i, n in enumerate(rows[k])}
            keyed = []
            for i, n in enumerate(row):
                ns = near.get(id(n), [])
                keyed.append((sum(at[id(m)] for m in ns) / len(ns) if ns else i, i, n))
            rows[r] = [n for _, _, n in sorted(keyed, key=lambda k: (k[0], k[1]))]


def place_rows(rows, links):
    """Each row's height and place, then each node's x: first packed, then pulled toward the
    nodes it links to, a node never closer than NODE_GAP to the next in its row."""
    y = 0.0
    for r in sorted(rows):
        row = rows[r]
        h = max(n.h for n in row)
        for n in row:
            n.y = y + (h - n.h) / 2
        y += h + ROW_GAP
    for row in rows.values():
        x = 0.0
        for n in row:
            n.x = x
            x += n.w + gap(n)
    up, down = neighbours(links)
    for _ in range(SWEEPS):
        for r in sorted(rows):
            row = rows[r]
            want = []
            for n in row:
                ns = up.get(id(n), []) + down.get(id(n), [])
                centre = sum(m.x + m.w / 2 for m in ns) / len(ns) if ns else n.x + n.w / 2
                want.append(centre - n.w / 2)
            left = list(want)
            for i in range(1, len(row)):
                left[i] = max(left[i], left[i - 1] + row[i - 1].w + gap(row[i - 1]))
            right = list(want)
            for i in range(len(row) - 2, -1, -1):
                right[i] = min(right[i], right[i + 1] - row[i].w - gap(row[i]))
            for i, n in enumerate(row):
                n.x = (left[i] + right[i]) / 2
            for i in range(1, len(row)):
                row[i].x = max(row[i].x, row[i - 1].x + row[i - 1].w + gap(row[i - 1]))
    least = min((n.x for row in rows.values() for n in row), default=0)
    for row in rows.values():
        for n in row:
            n.x -= least


def gap(n):
    return NODE_GAP if n.box is not None or n.h > 0 else NODE_GAP / 2


def descendants(box):
    for child in box.children:
        yield child
        yield from descendants(child)


def absolute(box, dx, dy):
    box.x += dx
    box.y += dy
    for child in box.children:
        absolute(child, box.x, box.y)


def edge_point(box, toward):
    """Where the line from the box's centre toward a point leaves the box."""
    cx, cy = box.x + box.w / 2, box.y + box.h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    if dx == 0 and dy == 0:
        return cx, box.y + box.h
    if box.kind == "start":
        r = box.w / 2
        d = (dx * dx + dy * dy) ** 0.5
        return cx + dx / d * r, cy + dy / d * r
    sx = (box.w / 2) / abs(dx) if dx else float("inf")
    sy = (box.h / 2) / abs(dy) if dy else float("inf")
    s = min(sx, sy)
    return cx + dx * s, cy + dy * s


def draw(chart, boxes):
    """Lays out every region; returns, for each step, the container that routes it and its bends."""
    routed = {"owners": {step: owner(step, boxes) for step in chart.steps}, "points": {}}
    for region in chart.regions:
        layout(region, boxes, routed)
    return routed


def scene(text):
    """The Excalidraw scene of a chart.mmd, as a dict ready for json.dumps."""
    chart, boxes = read_chart(text)
    routed = draw(chart, boxes)
    elements = []
    title_h = 0.0
    if chart.title:
        lines = lines_of(chart.title)
        w, h = text_size(lines, 28)
        elements.append(text_element("title", lines, 0, 0, w, h, 28, "left", "top", None, None))
        title_h = h + 40
    legend_h = 0.0
    if chart.legend:
        x = FRAME_PAD
        legend_boxes = []
        for caption, state_id in chart.legend:
            lines = lines_of(caption)
            w, h = text_size(lines, STATE_FONT)
            box = Box(f"legend-{state_id}", caption, "legend")
            box.w, box.h = round(w + 2 * BOX_PAD_X), round(h + 2 * BOX_PAD_Y)
            box.x, box.y = x, title_h + FRAME_PAD
            x += box.w + NODE_GAP
            legend_boxes.append((box, chart.classes.get(state_id)))
        tall = max(b.h for b, _ in legend_boxes)
        frame = {"id": "frame-legend", "name": "Legend"}
        for box, cls in legend_boxes:
            elements += box_elements(box, chart.styles.get(cls, PLAIN), frame["id"], [], None)
        elements.append(
            frame_element(frame, 0, title_h, x - NODE_GAP + FRAME_PAD, tall + 2 * FRAME_PAD)
        )
        legend_h = tall + 2 * FRAME_PAD + 60
    x = 0.0
    for region in chart.regions:
        absolute(region, x, title_h + legend_h)
        x += region.w + FRAME_GAP
    arrows = {}
    for step in chart.steps:
        holder, points = routed["points"][step]
        ox, oy = holder.x, holder.y
        step.points = [(px + ox, py + oy) for px, py in points]
        arrows.setdefault(step.source, []).append(step)
        if step.target != step.source:
            arrows.setdefault(step.target, []).append(step)
    ids = {id(s): f"step{n}" for n, s in enumerate(chart.steps)}
    for region in chart.regions:
        frame_id = f"frame-{region.id}"
        inside = []
        for child in descendants(region):
            bound = [ids[id(s)] for s in arrows.get(child.id, [])]
            style = chart.styles.get(chart.classes.get(child.id), PLAIN)
            inside.extend(box_elements(child, style, frame_id, bound, child.kind))
        for step in chart.steps:
            if region in ancestors(boxes[step.source]):
                inside.extend(arrow_elements(ids[id(step)], step, boxes, frame_id))
        elements += inside
        elements.append(
            frame_element(
                {"id": frame_id, "name": region.caption}, region.x, region.y, region.w, region.h
            )
        )
    return {
        "type": "excalidraw",
        "version": 2,
        "source": "statechart excalidraw",
        "elements": elements,
        "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
        "files": {},
    }


def base(element_id, kind, x, y, w, h, frame_id, **extra):
    return {
        "id": element_id,
        "type": kind,
        "x": round(x, 2),
        "y": round(y, 2),
        "width": round(w, 2),
        "height": round(h, 2),
        "angle": 0,
        "strokeColor": TEXT,
        "backgroundColor": "transparent",
        "fillStyle": "solid",
        "strokeWidth": 1,
        "strokeStyle": "solid",
        "roughness": 0,
        "opacity": 100,
        "groupIds": [],
        "frameId": frame_id,
        "roundness": None,
        "seed": zlib.crc32(element_id.encode()) or 1,
        "version": 1,
        "versionNonce": zlib.crc32(f"{element_id}:nonce".encode()) or 1,
        "isDeleted": False,
        "boundElements": [],
        "updated": 1,
        "link": None,
        "locked": False,
        **extra,
    }


def text_element(
    element_id, lines, x, y, w, h, size, align, valign, container, frame_id, color=TEXT
):
    return base(
        element_id,
        "text",
        x,
        y,
        w,
        h,
        frame_id,
        strokeColor=color,
        text="\n".join(lines),
        originalText="\n".join(lines),
        fontSize=size,
        fontFamily=FONT,
        textAlign=align,
        verticalAlign=valign,
        containerId=container,
        autoResize=True,
        lineHeight=LINE_HEIGHT,
    )


def box_elements(box, style, frame_id, bound, kind):
    fill, stroke, color = style
    element_id = f"state-{box.id}" if kind != "legend" else box.id
    data = {"statechart": {"kind": kind or "legend", "id": box.id}}
    if box.kind == "start":
        shape = base(
            element_id,
            "ellipse",
            box.x,
            box.y,
            box.w,
            box.h,
            frame_id,
            backgroundColor=TEXT,
            customData=data,
        )
        shape["boundElements"] = [{"id": a, "type": "arrow"} for a in bound]
        return [shape]
    composite = box.kind == "composite"
    shape = base(
        element_id,
        "rectangle",
        box.x,
        box.y,
        box.w,
        box.h,
        frame_id,
        strokeColor="#868e96" if composite else stroke,
        backgroundColor="transparent" if composite else fill,
        strokeStyle="dashed" if composite else "solid",
        roundness={"type": 3},
        customData=data,
    )
    lines = lines_of(box.caption)
    w, h = text_size(lines, STATE_FONT)
    label_id = f"{element_id}-text"
    shape["boundElements"] = [{"id": label_id, "type": "text"}] + [
        {"id": a, "type": "arrow"} for a in bound
    ]
    ty = box.y + 8 if composite else box.y + (box.h - h) / 2
    label = text_element(
        label_id,
        lines,
        box.x + (box.w - w) / 2,
        ty,
        w,
        h,
        STATE_FONT,
        "center",
        "top" if composite else "middle",
        element_id,
        frame_id,
        TEXT if composite else color,
    )
    return [shape, label]


def arrow_elements(element_id, step, boxes, frame_id):
    a, b = boxes[step.source], boxes[step.target]
    inner = step.points
    first = edge_point(a, inner[0] if inner else (b.x + b.w / 2, b.y + b.h / 2))
    last = edge_point(b, inner[-1] if inner else (a.x + a.w / 2, a.y + a.h / 2))
    points = [first, *inner, last]
    x0, y0 = points[0]
    rel = [[round(px - x0, 2), round(py - y0, 2)] for px, py in points]
    xs = [p[0] for p in rel]
    ys = [p[1] for p in rel]
    data = {"statechart": {"kind": "step", "from": a.id, "to": b.id}}
    out = []
    arrow = base(
        element_id,
        "arrow",
        x0,
        y0,
        max(xs) - min(xs),
        max(ys) - min(ys),
        frame_id,
        roundness={"type": 2},
        points=rel,
        lastCommittedPoint=None,
        startBinding={"elementId": element_id_of(a), "focus": 0, "gap": 4, "fixedPoint": None},
        endBinding={"elementId": element_id_of(b), "focus": 0, "gap": 4, "fixedPoint": None},
        startArrowhead=None,
        endArrowhead="arrow",
        elbowed=False,
        customData=data,
    )
    out.append(arrow)
    if step.label:
        lines = lines_of(step.label)
        w, h = text_size(lines, LABEL_FONT)
        mx, my = points[len(points) // 2]
        label_id = f"{element_id}-label"
        arrow["boundElements"] = [{"id": label_id, "type": "text"}]
        out.append(
            text_element(
                label_id,
                lines,
                mx - w / 2,
                my - h / 2,
                w,
                h,
                LABEL_FONT,
                "center",
                "middle",
                element_id,
                frame_id,
            )
        )
    return out


def element_id_of(box):
    return f"state-{box.id}"


def frame_element(frame, x, y, w, h):
    return base(frame["id"], "frame", x, y, w, h, None, name=frame["name"])


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in ("-h", "--help"):
        print(HELP)
        return 0
    chart_file = out = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in ("-h", "--help"):
            print(HELP)
            return 0
        if a == "--out":
            if i + 1 == len(argv):
                print(f"--out needs a value.\nUsage: {USAGE}", file=sys.stderr)
                return 2
            out = argv[i + 1]
            i += 2
            continue
        if a.startswith("-") or chart_file is not None:
            print(f"unknown argument {a}.\nUsage: {USAGE}", file=sys.stderr)
            return 2
        chart_file = a
        i += 1
    if chart_file is None or out is None:
        print(f"Usage: {USAGE}", file=sys.stderr)
        return 2
    try:
        text = Path(chart_file).read_text(encoding="utf-8")
    except OSError as e:
        print(f"cannot read {chart_file}: {e.strerror}", file=sys.stderr)
        return 2
    try:
        drawn = scene(text)
    except ChartError as e:
        print(f"{chart_file}: {e}", file=sys.stderr)
        return 2
    target = Path(out)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=target.parent, delete=False, suffix=".tmp"
        ) as f:
            f.write(json.dumps(drawn, indent=2, ensure_ascii=False) + "\n")
        mask = os.umask(0)
        os.umask(mask)
        os.chmod(f.name, 0o666 & ~mask)
        os.replace(f.name, target)
    except OSError as e:
        print(f"cannot write {out}: {e.strerror}", file=sys.stderr)
        return 2
    print(f"wrote {out}: {sum(1 for e in drawn['elements'] if e['type'] == 'arrow')} steps")
    return 0
