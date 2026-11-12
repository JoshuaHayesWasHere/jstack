"""Reference lanes: a chart drawn as rows of boxes, one row per thing that moves on its own, from
every step of TLC's state graph, with no two lines crossing and no words on a line.

A mapping that names `lanes` says how. Its parts:

- `lanes`: {lane: {"name", "about", "start", "boxes": {box: words}, "chips": {box: {chip: words}}}},
  the boxes in the order the story meets them; `chips`, where a box joins several values, names
  them, and the moves between them are a table instead of arrows.
- `lane_moves(before, after, action)`: the boxes a step moves, as [(lane, from, to, effect)], and
  for a step that moves none, the key of its `still` row. A move inside a box has from == to and
  the effect `chip>chip`.
- `arrows`: {(lane, from, to, effect): (who, words, guard or None)}, every arrow the graph takes.
- `still`: {key: (who, lane, words)}, every kind of step that moves no box.
- `who`: {who: words}, who takes a step, in the order the legend lists them and colours them.
- `lane_configs` (optional): the configs whose graphs are drawn, beside the spec; its own by
  default.
- `seen(state_dir)` (optional): {arrow: (n, source)} or {(lane, from, to): (n, source)}, what a
  real log records of an arrow or of every arrow between two boxes. An arrow it leaves out
  shows no count.

Each lane is laid out by the book router: its boxes in a row, each arrow an orthogonal arc above or
below the row, with the box order and the side of each arc searched so that no two arcs on one side
interleave. Two arcs that do not interleave nest or sit apart, so no two lines cross, and each label
sits in its own band inside its own arc. A lane whose arcs admit no such order is refused: merge two
of its boxes, or draw some of its moves as a table.

Two checks run on what is drawn: `coverage`, which reads the page as written and asks that each step
of the graph lands on exactly one arc of each drawing, table cell or row, and that each of those
holds at least one step; and `faults`, which measures the layout's own geometry, its lines
against each other and against each label and box, with label sizes estimated from their
characters. The browser check (`statechart lanes-check`) measures the same on the rendered page
and is the one that counts.
"""

import collections
import html
import itertools
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

from statechart.lib import ChartError, parse_dot

E = html.escape

CHAR = 6.15  # px per character of the 11 px label font, a little over its real width
LH = 13.5  # a label's line height
PADX = 7  # between a label and its arc's sides
LGAP = 4  # between an arc's horizontal and its label
GAP = 7  # between a label's far edge and the next arc out
BASE = 16  # the lowest an arc runs from its box
NEAR = 0.75  # two lines this close touch

WIDE = {"name": "wide", "w": 1090, "x0": 132, "bw": 126, "bh": 34, "head": 0}
NARROW = {"name": "narrow", "w": 684, "x0": 4, "bw": 96, "bh": 34, "head": 30}


def arrow_id(key):
    return ".".join(key).replace(">", "-")


# The mapping's lanes, read once


@dataclass
class Lanes:
    lanes: dict
    who: list
    arrows: dict
    still: dict
    lane_moves: object
    configs: list
    seen: object = None

    @classmethod
    def of(cls, mapping, spec):
        lanes = getattr(mapping, "lanes", None)
        if not isinstance(lanes, dict) or not lanes:
            raise ChartError("the mapping names no lanes")
        for lane, it in lanes.items():
            boxes = it.get("boxes") or {}
            if it.get("start") not in boxes:
                raise ChartError(
                    f"lane {lane}: its start {it.get('start')!r} is not one of its boxes"
                )
        configs = list(getattr(mapping, "lane_configs", None) or [f"{Path(spec).stem}.cfg"])
        return cls(
            lanes=lanes,
            who=list(getattr(mapping, "who", {}).items()),
            arrows=dict(getattr(mapping, "arrows", {})),
            still=dict(getattr(mapping, "still", {})),
            lane_moves=mapping.lane_moves,
            configs=configs,
            seen=getattr(mapping, "seen", None),
        )


# The graph and its projection


def graph(spec, cfg, tools):
    """TLC's state graph of `spec` under the config file `cfg`: {"nodes", "edges", "loops"} as
    `lib.parse_dot` reads it. TLC runs in a test slot on the workers `tools.workers()` names, and
    dumps it into a folder of its own, removed after, whatever happens: a dump runs to hundreds
    of megabytes."""
    from statechart.cli import run_tlc
    from statechart.tools import workers

    work = tempfile.mkdtemp(prefix="statechart-lanes-")
    try:
        base = os.path.join(work, Path(cfg).stem)
        dump = os.path.join(work, "graph")
        text = Path(cfg).read_text(encoding="utf-8")
        run_tlc(tools, str(spec), text, base, dump=dump, workers=workers())
        with open(f"{dump}.dot", encoding="utf-8") as handle:
            return parse_dot(handle.read())
    finally:
        shutil.rmtree(work, ignore_errors=True)


@dataclass
class Projection:
    """Every step of the graphs, by where it lands: `moves` counts each arrow's steps by config,
    `still` each still row's, and `kinds` each set of places one step lands on, so the coverage
    check counts steps and not arrows."""

    moves: dict = field(default_factory=lambda: collections.defaultdict(collections.Counter))
    still: dict = field(default_factory=lambda: collections.defaultdict(collections.Counter))
    kinds: collections.Counter = field(default_factory=collections.Counter)
    totals: dict = field(default_factory=dict)

    @property
    def steps(self):
        return sum(self.kinds.values())


def project(lanes, graphs):
    """`graphs`: [(config name, graph)]. Each step is projected by the mapping's `lane_moves`; a
    move or still row the mapping has no words for is refused, so a new step in the spec fails
    the drawing instead of going unlabelled."""
    p = Projection()
    unnamed = collections.Counter()
    for name, g in graphs:
        nodes = g["nodes"]
        steps = [*g["edges"], *g["loops"]]
        p.totals[name] = (len(nodes), len(steps))
        for e in steps:
            before, after = nodes[e["from"]]["vars"], nodes[e["to"]]["vars"]
            moves, still = lanes.lane_moves(before, after, e["action"])
            moves = [tuple(m) for m in moves]
            for m in moves:
                if m[1] != m[2] and m not in lanes.arrows:
                    unnamed[f"arrow {m}"] += 1
                p.moves[m][name] += 1
            if not moves:
                if still not in lanes.still:
                    unnamed[f"still row {still!r} ({e['action']})"] += 1
                p.still[still][name] += 1
            p.kinds[(tuple(moves), None if moves else still)] += 1
    if unnamed:
        listed = "; ".join(f"{k} ({n} steps)" for k, n in unnamed.most_common(8))
        raise ChartError(f"steps the mapping has no words for: {listed}")
    return p


# The book router


def wrap(text, width):
    most = max(4, int(width / CHAR))
    lines, cur = [], ""
    for word in text.split():
        if not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= most:
            cur += " " + word
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def _conflicts(order, arcs):
    pos = {b: i for i, b in enumerate(order)}
    span = [tuple(sorted((pos[a["from"]], pos[a["to"]]))) for a in arcs]
    pairs = []
    for i, j in itertools.combinations(range(len(arcs)), 2):
        (a, b), (c, d) = span[i], span[j]
        if a < c < b < d or c < a < d < b:
            pairs.append((i, j))
    return span, pairs


def _two_sides(n, pairs, prefer):
    """Arcs split between the two sides so no interleaving pair shares one, each component on
    the split with fewer arcs off the side they prefer; None when a component has an odd cycle."""
    adj = [[] for _ in range(n)]
    for i, j in pairs:
        adj[i].append(j)
        adj[j].append(i)
    side = [None] * n
    cost = 0
    for s in range(n):
        if side[s] is not None:
            continue
        comp, side[s], stack = [s], 0, [s]
        while stack:
            u = stack.pop()
            for v in adj[u]:
                if side[v] is None:
                    side[v] = 1 - side[u]
                    comp.append(v)
                    stack.append(v)
                elif side[v] == side[u]:
                    return None, None
        keep = sum(1 for u in comp if side[u] != prefer[u])
        if len(comp) - keep < keep:
            for u in comp:
                side[u] = 1 - side[u]
        cost += min(keep, len(comp) - keep)
    return side, cost


def choose(story, arcs):
    """The box order and each arc's side (0 above, 1 below) with no two arcs on a side
    interleaving. Of those, the one closest to the story: the start box first, boxes moved
    least, arcs shortest, forward arcs above."""
    best = None
    for order in itertools.permutations(story):
        span, pairs = _conflicts(order, arcs)
        pos = {b: i for i, b in enumerate(order)}
        prefer = [0 if pos[a["to"]] > pos[a["from"]] else 1 for a in arcs]
        side, off = _two_sides(len(arcs), pairs, prefer)
        if side is None:
            continue
        moved = sum(abs(i - story.index(b)) for i, b in enumerate(order))
        cost = (order[0] != story[0], moved, sum(b - a for a, b in span), off)
        if best is None or cost < best[0]:
            best = (cost, list(order), side)
    if best is None:
        raise ChartError(
            f"no order of the boxes {', '.join(story)} draws their arrows without two crossing:"
            " merge two boxes, or draw some moves as a table"
        )
    return best[1], best[2]


def label_lines(arc, width):
    """An arc's label as lines of (text, who, kind): each arrow's words, its count, then the
    guards, then the count of every move between the two boxes."""
    out = []
    for eff in arc["effects"]:
        out.extend((line, eff["who"], "words") for line in wrap(eff["words"], width))
        if eff.get("seen"):
            out.append((f"seen {eff['seen'][0]:,}", None, "seen"))
    for guard in sorted({e["guard"] for e in arc["effects"] if e.get("guard")}):
        out.extend((line, None, "guard") for line in wrap(f"[{guard}]", width))
    if arc.get("seen"):
        out.append((f"seen {arc['seen'][0]:,}", None, "seen"))
    return out


def route_lane(story, arcs, size, box_lines):
    """One lane laid out: its boxes in a row, each arc's path and its label's lines and place, in
    the lane's own coordinates. `arcs`: [{"id", "from", "to", "effects"}]."""
    order, side = choose(story, arcs)
    bw = size["bw"]
    bh = max(size["bh"], 10 + 15 * max(len(v) for v in box_lines.values()))
    n = len(order)
    dx = (size["w"] - size["x0"] - bw - 4) / max(1, n - 1)
    if n == 2:
        dx = min(dx, 2.6 * bw)
    bx = {b: size["x0"] + i * dx for i, b in enumerate(order)}
    pos = {b: i for i, b in enumerate(order)}
    A = [dict(a, side=side[i], i=i) for i, a in enumerate(arcs)]
    # Ports: per box and side, the arcs to the left nearest first, then those to the right
    # farthest first, so nested arcs never touch.
    for b in order:
        for s in (0, 1):
            here = [a for a in A if a["side"] == s and b in (a["from"], a["to"])]

            def key(a, b=b):
                other = a["to"] if a["from"] == b else a["from"]
                d = pos[other] - pos[b]
                return (0, -d, a["i"]) if d < 0 else (1, -d, -a["i"])

            here.sort(key=key)
            for k, a in enumerate(here):
                a["x_from" if a["from"] == b else "x_to"] = bx[b] + bw * (k + 1) / (len(here) + 1)
    for a in A:
        a["xl"], a["xr"] = sorted((a["x_from"], a["x_to"]))
        a["lines"] = label_lines(a, a["xr"] - a["xl"] - 2 * PADX)
        a["lh"] = len(a["lines"]) * LH
    # Heights, inside out: each arc clears every arc it encloses and that arc's label.
    for s in (0, 1):
        on = sorted([a for a in A if a["side"] == s], key=lambda a: a["xr"] - a["xl"])
        for a in on:
            inner = [
                c
                for c in on
                if c is not a
                and "d" in c
                and c["xl"] >= a["xl"] - 0.01
                and c["xr"] <= a["xr"] + 0.01
            ]
            a["d"] = max([BASE] + [c["d"] + LGAP + c["lh"] + GAP for c in inner])
    up = max([a["d"] + LGAP + a["lh"] for a in A if a["side"] == 0], default=0) + 6
    down = max([a["d"] + LGAP + a["lh"] for a in A if a["side"] == 1], default=0) + 6
    top = size["head"] + up
    down = max(down, size.get("min_below", 0))
    for a in A:
        sign = -1 if a["side"] == 0 else 1
        edge = top if a["side"] == 0 else top + bh
        y = edge + sign * a["d"]
        a["points"] = [(a["x_from"], edge), (a["x_from"], y), (a["x_to"], y), (a["x_to"], edge)]
        a["label_x"] = (a["xl"] + a["xr"]) / 2
        a["label_y0"] = (y - LGAP - a["lh"]) if a["side"] == 0 else (y + LGAP)
    boxes = [{"id": b, "x": bx[b], "y": top, "w": bw, "h": bh} for b in order]
    return {"w": size["w"], "h": top + bh + down, "boxes": boxes, "arcs": A}


# The lanes' content


def _arcs(lanes, lane, projection, seen):
    """One arc per pair of boxes the lane's arrows join, its arrows in the mapping's order."""
    by = {}
    for key, (who, words, guard) in lanes.arrows.items():
        if key[0] != lane or key not in projection.moves:
            continue
        _, f, t, _ = key
        arc = by.setdefault(
            (f, t), {"id": f"{lane}.{f}.{t}", "from": f, "to": t, "effects": [], "ids": []}
        )
        arc["effects"].append(
            {
                "words": words,
                "who": who,
                "guard": guard,
                "seen": seen.get(key),
                "configs": sorted(projection.moves[key]),
            }
        )
        arc["ids"].append(arrow_id(key))
    for (f, t), arc in by.items():
        arc["seen"] = seen.get((lane, f, t))
    return list(by.values())


def _box_lines(lane, size):
    out = {}
    for b, words in lane["boxes"].items():
        lines = wrap(words, size["bw"] - 10)
        chips = (lane.get("chips") or {}).get(b)
        if chips and len(chips) > 1:
            lines += wrap(" · ".join(chips.values()), size["bw"] - 8)
        out[b] = lines
    return out


@dataclass
class Drawing:
    name: str
    size: dict
    lanes: list  # [(lane id, lane, layout, y offset, box lines)]
    h: float


def lay_out(lanes, projection, seen, size):
    out, y = [], 0.0
    for lane_id, lane in lanes.lanes.items():
        arcs = _arcs(lanes, lane_id, projection, seen)
        lines = _box_lines(lane, size)
        sub = len(wrap(lane["about"], size["x0"] - 18)) if size["x0"] > 40 else 0
        it = route_lane(
            list(lane["boxes"]), arcs, dict(size, min_below=max(0, 14 * sub - 4)), lines
        )
        out.append((lane_id, lane, it, y, lines))
        y += it["h"] + 10
    return Drawing(size["name"], size, out, y)


# The layout's geometry, measured with estimated label sizes


def _segments(points):
    return list(itertools.pairwise(points))


def _touch(s, t):
    """Two axis-parallel segments that meet or come within NEAR."""
    (a, b), (c, d) = s, t
    ax0, ax1 = sorted((a[0], b[0]))
    ay0, ay1 = sorted((a[1], b[1]))
    cx0, cx1 = sorted((c[0], d[0]))
    cy0, cy1 = sorted((c[1], d[1]))
    return ax0 - NEAR <= cx1 and cx0 - NEAR <= ax1 and ay0 - NEAR <= cy1 and cy0 - NEAR <= ay1


def _hits(seg, r):
    (a, b) = seg
    x0, x1 = sorted((a[0], b[0]))
    y0, y1 = sorted((a[1], b[1]))
    return x0 < r[2] and r[0] < x1 + 0.01 and y0 < r[3] and r[1] < y1 + 0.01


def _overlap(r, s):
    return r[0] < s[2] and s[0] < r[2] and r[1] < s[3] and s[1] < r[3]


def shapes(drawing):
    """The drawing's lines, label boxes and boxes in its own coordinates: (paths, labels, boxes),
    each path [(id, points)], each label (owner, text, rect), each box (id, rect)."""
    paths, labels, boxes = [], [], []
    for lane_id, lane, it, y0, _ in drawing.lanes:
        for a in it["arcs"]:
            paths.append((a["id"], [(x, y + y0) for x, y in a["points"]]))
            for k, (text, _, _) in enumerate(a["lines"]):
                w = len(text) * CHAR
                top = a["label_y0"] + y0 + k * LH
                rect = (a["label_x"] - w / 2, top + 1.5, a["label_x"] + w / 2, top + LH - 1.5)
                labels.append((a["id"], text, rect))
        boxes.extend(
            (f"{lane_id}.{b['id']}", (b["x"], b["y"] + y0, b["x"] + b["w"], b["y"] + y0 + b["h"]))
            for b in it["boxes"]
        )
        for text, rect, _ in _lane_names(drawing.size, it["boxes"][0], y0, lane):
            labels.append((f"lane:{lane_id}", text, rect))
    return paths, labels, boxes


def _lane_names(size, first, y0, lane):
    """The lane's name and what it is, as (text, rect, (x, y, class)): left of the boxes when
    there is room, else above them."""
    name, about = lane["name"], lane["about"]
    out = []
    if size["x0"] > 40:
        mid = first["y"] + y0 + first["h"] / 2
        out.append(
            (name, (10, mid - 13, 10 + len(name) * 7.4, mid + 1), (10, mid - 2, "lane-name"))
        )
        for k, line in enumerate(wrap(about, size["x0"] - 18)):
            y = mid + 13 + k * 14
            out.append((line, (10, y - 10, 10 + len(line) * 6.2, y + 3), (10, y, "lane-sub")))
    else:
        text = f"{name}  {about}"
        out.append((text, (8, y0 + 6, 8 + len(text) * 7.0, y0 + 22), (8, y0 + 18, "lane-name")))
    return out


def faults(drawing):
    """What the layout's geometry gets wrong, by kind: two lines that cross or touch, a label on a
    line, a label on another arc's label, a label on a box. Each is a list of what it names."""
    paths, labels, boxes = shapes(drawing)
    out = {"crossings": [], "label_on_line": [], "label_on_label": [], "label_on_box": []}
    segs = [(pid, _segments(pts)) for pid, pts in paths]
    for (p, ps), (q, qs) in itertools.combinations(segs, 2):
        if any(_touch(s, t) for s in ps for t in qs):
            out["crossings"].append(f"{p} x {q}")
    for _, text, r in labels:
        for pid, ps in segs:
            if any(_hits(s, r) for s in ps):
                out["label_on_line"].append(f"{text} | {pid}")
        for bid, b in boxes:
            if _overlap(r, b):
                out["label_on_box"].append(f"{text} | {bid}")
    for (o1, t1, r1), (o2, t2, r2) in itertools.combinations(labels, 2):
        if o1 != o2 and _overlap(r1, r2):
            out["label_on_label"].append(f"{t1} | {t2}")
    return out


# The panel


def svg(chart, lanes, drawing):
    size = drawing.size
    who_index = {w: k for k, (w, _) in enumerate(lanes.who)}
    parts = [
        f'<svg class="lanes {drawing.name}" viewBox="0 0 {size["w"]} {drawing.h:.0f}"'
        f' role="img" aria-label="{E(chart)} lanes" data-chart="{E(chart)}"'
        ' xmlns="http://www.w3.org/2000/svg">'
    ]
    marks = "".join(
        f'<marker id="m-{E(chart)}-{drawing.name}-{k}" viewBox="0 0 10 10" refX="9" refY="5"'
        f' markerWidth="6" markerHeight="6" orient="auto">'
        f'<path class="mk w{k}" d="M0,0L10,5L0,10z"/></marker>'
        for k in [*range(len(lanes.who)), "x"]
    )
    parts.append(f"<defs>{marks}</defs>")
    for lane_id, lane, it, y0, lines in drawing.lanes:
        parts.append(f'<g transform="translate(0,{y0:.1f})" data-lane="{E(lane_id)}">')
        parts.append(
            f'<rect class="lane-bg" x="0" y="0" width="{size["w"]}" height="{it["h"]:.1f}" rx="8"/>'
        )
        for text, _, (x, y, cls) in _lane_names(size, it["boxes"][0], 0, lane):
            parts.append(f'<text class="{cls}" x="{x}" y="{y:.1f}">{E(text)}</text>')
        for a in it["arcs"]:
            whos = {who_index.get(e["who"], "x") for e in a["effects"]}
            k = whos.pop() if len(whos) == 1 else "x"
            dash = ' stroke-dasharray="5 4"' if any(e.get("guard") for e in a["effects"]) else ""
            d = "M{:.1f},{:.1f} V{:.1f} H{:.1f} V{:.1f}".format(
                a["points"][0][0],
                a["points"][0][1],
                a["points"][1][1],
                a["points"][2][0],
                a["points"][3][1],
            )
            tip = "; ".join(
                e["words"]
                + (f" [{e['guard']}]" if e.get("guard") else "")
                + (f" (seen {e['seen'][0]:,}: {e['seen'][1]})" if e.get("seen") else "")
                for e in a["effects"]
            )
            title = f"{lane['boxes'][a['from']]} → {lane['boxes'][a['to']]}: {tip}"
            parts.append(
                f'<path class="arc w{k}" d="{d}"{dash}'
                f' marker-end="url(#m-{E(chart)}-{drawing.name}-{k})"'
                f' data-arrow="{" ".join(a["ids"])}" data-arc="{E(a["id"])}">'
                f"<title>{E(title)}</title></path>"
            )
        for a in it["arcs"]:
            t = [
                f'<text class="lab" x="{a["label_x"]:.1f}" y="{a["label_y0"] + LH - 3.5:.1f}"'
                f' data-label="{E(a["id"])}">'
            ]
            for n, (line, who, kind) in enumerate(a["lines"]):
                cls = f"t{who_index.get(who, 'x')}" if kind == "words" else f"t-{kind}"
                t.append(
                    f'<tspan class="{cls}" x="{a["label_x"]:.1f}" dy="{0 if n == 0 else LH}">'
                    f"{E(line)}</tspan>"
                )
            t.append("</text>")
            parts.append("".join(t))
        for b in it["boxes"]:
            start = " start" if b["id"] == lane["start"] else ""
            parts.append(
                f'<g class="box{start}" data-box="{E(lane_id)}.{E(b["id"])}">'
                f'<rect x="{b["x"]:.1f}" y="{b["y"]:.1f}"'
                f' width="{b["w"]}" height="{b["h"]:.1f}" rx="7"/>'
            )
            words = lines[b["id"]]
            y1 = b["y"] + b["h"] / 2 - (len(words) - 1) * 7.5 + 4
            name_lines = len(wrap(lane["boxes"][b["id"]], size["bw"] - 10))
            for n, line in enumerate(words):
                cls = "bn" if n < name_lines else "chip"
                parts.append(
                    f'<text class="{cls}" x="{b["x"] + b["w"] / 2:.1f}" y="{y1 + 15 * n:.1f}">'
                    f"{E(line)}</text>"
                )
            parts.append("</g>")
        parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def _dot(lanes, who):
    k = next((n for n, (w, _) in enumerate(lanes.who) if w == who), "x")
    return f'<span class="dot w{k}"></span>'


def matrices(chart, lanes, projection, seen):
    """Each box's moves between its chips as a table: a count where a log records the move, a ✓
    where only the model takes it, a dot where neither does."""
    out = []
    for lane_id, lane in lanes.lanes.items():
        for box, chips in (lane.get("chips") or {}).items():
            inner = {
                tuple(key[3].split(">")): key
                for key in projection.moves
                if key[0] == lane_id and key[1] == key[2] == box
            }
            if not inner:
                continue
            head = "".join(f"<th>{E(w)}</th>" for w in chips.values())
            body = ""
            for a, aw in chips.items():
                cells = ""
                for b in chips:
                    key = inner.get((a, b))
                    if not key:
                        cells += '<td class="none">·</td>'
                        continue
                    count = seen.get(key)
                    mark = f'<span class="num">{count[0]:,}</span>' if count else "✓"
                    tip = f' title="{E(count[1])}"' if count else ""
                    cells += f'<td data-item="{E(chart)}:{E(arrow_id(key))}"{tip}>{mark}</td>'
                body += f"<tr><th>{E(aw)}</th>{cells}</tr>"
            out.append(
                f'<div class="matrix"><b>{E(lane["boxes"][box])}</b>'
                f'<table class="mx"><tr><th>from \\ to</th>{head}</tr>{body}</table></div>'
            )
    return out


def panel(chart, lanes, projection, seen):
    """The lanes panel's body: the legend, the lanes wide and narrow, the moves inside boxes, the
    steps that move no box and every arrow with its count and source. Returns (html, drawings)."""
    drawings = [lay_out(lanes, projection, seen, size) for size in (WIDE, NARROW)]
    legend = "".join(
        f'<li><i class="w{k}"></i>{E(words)}</li>' for k, (_, words) in enumerate(lanes.who)
    )
    legend += '<li><i class="dash"></i>has a guard [in brackets]</li>'
    legend += (
        '<li><span class="num">seen N</span> how often a real log records it;'
        " no number: no log records it</li>"
    )
    out = [f'<ul class="lane-legend">{legend}</ul>', '<div class="lane-sheet">']
    out += [svg(chart, lanes, d) for d in drawings]
    out.append("</div>")
    mx = matrices(chart, lanes, projection, seen)
    if mx:
        out.append(
            '<h3>Moves inside a box</h3><div class="lane-tables">' + "".join(mx) + "</div>"
            '<p class="quiet">These are a table, not arrows: they join most of the statuses each'
            " to each, which no drawing of them as arrows can do without lines crossing.</p>"
        )
    rows = "".join(
        f'<tr data-item="{E(chart)}:still:{E(key)}"><td>{E(lanes.lanes[lane]["name"])}</td>'
        f"<td>{_dot(lanes, who)}{E(words)}</td>"
        f'<td class="quiet">{E(", ".join(sorted(projection.still[key])))}</td></tr>'
        for key, (who, lane, words) in lanes.still.items()
        if key in projection.still
    )
    if rows:
        out.append(
            "<h3>Steps that move no box</h3>"
            '<table class="lane-table"><tr><th>Lane</th><th>What happens</th><th>In</th></tr>'
            f"{rows}</table>"
        )
    rows, pairs = [], set()
    for key, (who, words, guard) in lanes.arrows.items():
        if key not in projection.moves:
            continue
        lane = lanes.lanes[key[0]]
        count = seen.get(key)
        if not count and key[:3] in seen:
            # A count between two boxes goes on the first of their arrows, and the rest say so.
            count = seen[key[:3]] if key[:3] not in pairs else None
            ditto = key[:3] in pairs
            pairs.add(key[:3])
        else:
            ditto = False
        shown = (
            f'<span class="num" title="{E(count[1])}">{count[0]:,}</span>'
            if count
            else '<span class="quiet">in the count above</span>'
            if ditto
            else '<span class="quiet">none yet</span>'
        )
        rows.append(
            f"<tr><td>{E(lane['name'])}</td><td>{E(lane['boxes'][key[1]])}</td>"
            f"<td>{E(lane['boxes'][key[2]])}</td><td>{_dot(lanes, who)}{E(words)}"
            f"{f' <i>[{E(guard)}]</i>' if guard else ''}</td>"
            f'<td class="quiet">{E(", ".join(sorted(projection.moves[key])))}</td>'
            f"<td>{shown}</td></tr>"
        )
    out.append(
        '<h3>Every arrow <span class="quiet">(a count between two boxes is every logged move'
        " between them; hover a count for its source)</span></h3>"
        '<table class="lane-table"><tr><th>Lane</th><th>From</th><th>To</th><th>Who, what</th>'
        f"<th>In</th><th>Seen</th></tr>{''.join(rows)}</table>"
    )
    return "".join(out), drawings


# Coverage, read from the page as written


class _Page(HTMLParser):
    """The places one chart's steps can land on the page: each arc of each of its drawings, and
    each table cell or row named `<chart>:<item>`."""

    def __init__(self, chart):
        super().__init__()
        self.chart = chart
        self.svg = None
        self.arcs = collections.defaultdict(list)
        self.items = collections.Counter()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        classes = (a.get("class") or "").split()
        if tag == "svg" and "lanes" in classes:
            self.svg = classes[-1] if a.get("data-chart") == self.chart else None
        if tag == "path" and self.svg and "data-arrow" in a:
            self.arcs[self.svg].append(set((a["data-arrow"] or "").split()))
        item = a.get("data-item") or ""
        if item.startswith(f"{self.chart}:"):
            self.items[item[len(self.chart) + 1 :]] += 1


def coverage(page_html, chart, projection):
    """Each step against the page as written: a step that moves boxes must land on exactly one arc
    of each drawing, or for a move inside a box on one table cell; a step that moves none on one
    row of its still table. Then each arc, cell and row must hold a step. Returns
    {"steps": n, "steps_without_place": n, "places_without_step": [...], "examples": [...]}."""
    page = _Page(chart)
    page.feed(page_html)
    drawings = list(page.arcs)
    bad = collections.Counter()
    used_arcs, used_items, reached = collections.Counter(), collections.Counter(), set()
    for (moves, still), n in projection.kinds.items():
        if not moves:
            item = f"still:{still}"
            if page.items[item] != 1:
                bad[f"still row {still} is on the page {page.items[item]} times"] += n
            used_items[item] += n
            continue
        for m in moves:
            aid = arrow_id(m)
            reached.add(aid)
            if m[1] == m[2]:
                if page.items[aid] != 1:
                    bad[f"table cell {aid} is on the page {page.items[aid]} times"] += n
                used_items[aid] += n
                continue
            if not drawings:
                bad[f"{aid}: no lanes drawn"] += n
            for d in drawings:
                hits = [i for i, ids in enumerate(page.arcs[d]) if aid in ids]
                if len(hits) != 1:
                    bad[f"{aid} is on {len(hits)} arcs of the {d} drawing"] += n
                for h in hits:
                    used_arcs[(d, h)] += n
    empty = [
        f"arc {sorted(ids)} ({d})"
        for d in drawings
        for i, ids in enumerate(page.arcs[d])
        if not used_arcs[(d, i)]
    ]
    empty += sorted(
        f"arrow {i} ({d})"
        for d in drawings
        for ids in page.arcs[d]
        for i in ids
        if i not in reached
    )
    empty += sorted(f"cell or row {k}" for k in page.items if not used_items[k])
    return {
        "steps": projection.steps,
        "steps_without_place": sum(bad.values()),
        "places_without_step": empty,
        "examples": [f"{n} steps: {k}" for k, n in bad.most_common(5)] + empty[:5],
    }
