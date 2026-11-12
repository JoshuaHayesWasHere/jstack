<script>
// statechart lanes-check: opens each chart drawn as lanes, in the light theme and then the dark,
// and measures the lanes drawing the page shows at this width, in screen pixels: label lines that
// touch an arrow's line, label lines that touch another arc's label or a box, words in a box that
// touch a line, and pairs of lines that cross or come within 0.75 px. Each line is sampled each
// 0.5 px along its length. It writes what it found into the page, which the browser prints.
(() => {
  const frame = () => new Promise((r) => setTimeout(r, 60));
  function measure(panel) {
    const visible = [...panel.querySelectorAll("svg.lanes")].filter((s) => getComputedStyle(s).display !== "none");
    const toScreen = (el, x, y) => { const m = el.getScreenCTM(); return [m.a * x + m.c * y + m.e, m.b * x + m.d * y + m.f]; };
    const rectOf = (el) => {
      const b = el.getBBox(); const m = el.getScreenCTM();
      const xs = [b.x, b.x + b.width].map((x) => m.a * x + m.e), ys = [b.y, b.y + b.height].map((y) => m.d * y + m.f);
      return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
    };
    const paths = [], labels = [], boxes = [], boxWords = [];
    for (const svg of visible) {
      for (const p of svg.querySelectorAll("path.arc")) {
        const L = p.getTotalLength(), pts = [];
        for (let s = 0; s <= L; s += 0.5) { const q = p.getPointAtLength(s); pts.push(toScreen(p, q.x, q.y)); }
        const q = p.getPointAtLength(L); pts.push(toScreen(p, q.x, q.y));
        paths.push({ id: p.dataset.arc, pts });
      }
      for (const t of svg.querySelectorAll("text.lab")) {
        for (const ts of t.querySelectorAll("tspan")) labels.push({ id: t.dataset.label, text: ts.textContent, r: rectOf(ts) });
      }
      for (const g of svg.querySelectorAll("g.box")) {
        boxes.push({ id: g.dataset.box, r: rectOf(g.querySelector("rect")) });
        for (const t of g.querySelectorAll("text")) boxWords.push({ id: g.dataset.box, text: t.textContent, r: rectOf(t) });
      }
      for (const t of svg.querySelectorAll("text.lane-name, text.lane-sub")) labels.push({ id: "lane:" + t.textContent, text: t.textContent, r: rectOf(t) });
    }
    const hit = (r, s) => r[0] < s[2] && s[0] < r[2] && r[1] < s[3] && s[1] < r[3];
    const segInRect = (a, b, r) => {
      let t0 = 0, t1 = 1; const dx = b[0] - a[0], dy = b[1] - a[1];
      for (const [p, q] of [[-dx, a[0] - r[0]], [dx, r[2] - a[0]], [-dy, a[1] - r[1]], [dy, r[3] - a[1]]]) {
        if (p === 0) { if (q < 0) return false; } else { const t = q / p; if (p < 0) { if (t > t1) return false; if (t > t0) t0 = t; } else { if (t < t0) return false; if (t < t1) t1 = t; } }
      }
      return true;
    };
    const pathHitsRect = (pts, r) => { for (let i = 1; i < pts.length; i++) if (segInRect(pts[i - 1], pts[i], r)) return true; return false; };
    const out = { labelOnLine: [], labelOnLabel: [], labelOnBox: [], wordsOnLine: [], crossings: [] };
    for (const l of labels) for (const p of paths) if (pathHitsRect(p.pts, l.r)) out.labelOnLine.push(`${l.text} | ${p.id}`);
    for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++)
      if (labels[i].id !== labels[j].id && hit(labels[i].r, labels[j].r)) out.labelOnLabel.push(`${labels[i].text} | ${labels[j].text}`);
    for (const l of labels) for (const b of boxes) if (hit(l.r, b.r)) out.labelOnBox.push(`${l.text} | ${b.id}`);
    for (const w of boxWords) for (const p of paths) if (pathHitsRect(p.pts, w.r)) out.wordsOnLine.push(`${w.text} | ${p.id}`);
    const near = (a, b, c, d) => {
      const o = (p, q, r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
      if (Math.sign(o(a, b, c)) !== Math.sign(o(a, b, d)) && Math.sign(o(c, d, a)) !== Math.sign(o(c, d, b))) return true;
      const dist = (p, a, b) => { const l2 = (b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2; let t = l2 ? ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1])) / l2 : 0; t = Math.max(0, Math.min(1, t)); return Math.hypot(p[0] - a[0] - t * (b[0] - a[0]), p[1] - a[1] - t * (b[1] - a[1])); };
      return Math.min(dist(a, c, d), dist(b, c, d), dist(c, a, b), dist(d, a, b)) < 0.75;
    };
    const bbox = (pts) => [Math.min(...pts.map((p) => p[0])), Math.min(...pts.map((p) => p[1])), Math.max(...pts.map((p) => p[0])), Math.max(...pts.map((p) => p[1]))];
    for (let i = 0; i < paths.length; i++) for (let j = i + 1; j < paths.length; j++) {
      const A = paths[i].pts, B = paths[j].pts, ba = bbox(A), bb = bbox(B);
      if (!(ba[0] - 1 < bb[2] && bb[0] - 1 < ba[2] && ba[1] - 1 < bb[3] && bb[1] - 1 < ba[3])) continue;
      let found = false;
      for (let k = 1; k < A.length && !found; k++) for (let m = 1; m < B.length && !found; m++) {
        const a = A[k - 1], b = A[k], c = B[m - 1], d = B[m];
        if (Math.max(a[0], b[0]) + 1 < Math.min(c[0], d[0]) || Math.max(c[0], d[0]) + 1 < Math.min(a[0], b[0])) continue;
        if (Math.max(a[1], b[1]) + 1 < Math.min(c[1], d[1]) || Math.max(c[1], d[1]) + 1 < Math.min(a[1], b[1])) continue;
        if (near(a, b, c, d)) found = true;
      }
      if (found) out.crossings.push(`${paths[i].id} x ${paths[j].id}`);
    }
    return { drawing: visible.map((s) => s.classList[1]).join(" "), lines: paths.length, labels: labels.length, boxes: boxes.length, ...out };
  }
  async function run() {
    const out = [];
    for (const scheme of ["light", "dark"]) {
      document.documentElement.dataset.theme = scheme;
      for (const panel of document.querySelectorAll('.chart-panel[data-kind="lanes"]')) {
        document.querySelector(`.tab[data-chart="${CSS.escape(panel.dataset.chart)}"]`).click();
        document.documentElement.dataset.theme = scheme;
        await frame();
        out.push({ chart: panel.dataset.chart, width: innerWidth, scheme, ...measure(panel) });
      }
    }
    return out;
  }
  run().catch((e) => ({ error: String((e && e.stack) || e) })).then((out) => {
    const pre = document.createElement("pre");
    pre.id = "probe";
    pre.textContent = JSON.stringify(out);
    document.body.append(pre);
  });
})();
</script>
