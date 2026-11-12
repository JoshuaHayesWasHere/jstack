(() => {
  "use strict";
  const DATA = JSON.parse(document.getElementById("chart-data").textContent);
  const root = document.documentElement;
  const detail = document.querySelector(".detail");
  const body = detail.querySelector(".detail-body");
  const search = document.querySelector(".search input");
  const views = {};
  let current = null;

  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

  try {
    const saved = localStorage.getItem("statechart-theme");
    if (saved) root.dataset.theme = saved;
  } catch (e) { /* a file:// page may have no storage */ }
  document.querySelector(".theme").addEventListener("click", () => {
    const dark = root.dataset.theme ? root.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try { localStorage.setItem("statechart-theme", root.dataset.theme); } catch (e) { /* none */ }
  });

  // Pan and zoom. Each chart has a camera: the chart point at the frame's top left (x, y) and
  // the frame's pixels to one chart unit (k). The viewBox follows from the camera and the
  // frame's size, so a frame that changes size keeps its scale and never letterboxes.
  // A state's label is 12.5 units, so READABLE keeps it at 11.5 px or more on a fit.
  const READABLE = 0.92;
  function view(name) {
    if (views[name]) return views[name];
    const panel = document.querySelector(`.chart-panel[data-chart="${CSS.escape(name)}"]`);
    const svg = panel.querySelector("svg.chart");
    svg.setAttribute("preserveAspectRatio", "xMinYMin meet");
    const v = { panel, svg, port: panel.querySelector(".viewport"), full: { x: -20, y: -20, w: +svg.dataset.w, h: +svg.dataset.h } };
    v.cam = { x: v.full.x, y: v.full.y, k: 1 };
    views[name] = v;
    wire(v);
    return v;
  }
  function size(v) {
    const r = v.port.getBoundingClientRect();
    return { w: Math.max(1, r.width), h: Math.max(1, r.height), left: r.left, top: r.top };
  }
  function apply(v) {
    const p = size(v);
    const c = v.cam;
    v.svg.setAttribute("viewBox", `${c.x} ${c.y} ${p.w / c.k} ${p.h / c.k}`);
  }
  // Fitted: the chart's whole width across the frame, its top at the frame's top, and a tall
  // chart running on down, to scroll. Where the whole width would make its labels too small
  // to read, as on a phone, it opens at a readable size on its first start state instead.
  function fit(v) {
    const p = size(v);
    const k = Math.max(p.w / v.full.w, READABLE);
    let x = v.full.x;
    if (v.full.w * k > p.w) {
      const start = v.svg.querySelector("circle.start");
      const cx = start ? +start.getAttribute("cx") + offsetOf(v, start).x : v.full.x + v.full.w / 2;
      x = Math.min(Math.max(cx - p.w / k / 2, v.full.x), v.full.x + v.full.w - p.w / k);
    }
    v.cam = { x, y: v.full.y, k };
    v.fitted = true;
    apply(v);
  }
  function offsetOf(v, el) {
    const m = v.svg.getScreenCTM().inverse().multiply(el.getScreenCTM());
    return { x: m.e, y: m.f };
  }
  function zoomAt(v, factor, cx, cy) {
    const p = size(v);
    const c = v.cam;
    const least = Math.min(p.w / v.full.w, p.h / v.full.h) / 2;
    const k = Math.min(4, Math.max(least, c.k * factor));
    const px = c.x + (cx - p.left) / c.k;
    const py = c.y + (cy - p.top) / c.k;
    v.cam = { x: px - (cx - p.left) / k, y: py - (cy - p.top) / k, k };
    v.fitted = false;
    apply(v);
  }
  function panBy(v, dx, dy) {
    v.cam.x -= dx / v.cam.k;
    v.cam.y -= dy / v.cam.k;
    v.fitted = false;
    apply(v);
  }
  // How far the chart can scroll down or up from here, in pixels, so a wheel at its end
  // scrolls the page on.
  function room(v, dy) {
    const p = size(v);
    const c = v.cam;
    const top = v.full.y;
    const bottom = v.full.y + v.full.h - p.h / c.k;
    return dy > 0 ? (bottom - c.y) * c.k : (c.y - top) * c.k;
  }
  function centreOn(v, el) {
    const rect = el.querySelector("rect");
    const at = offsetOf(v, rect);
    const x = at.x + +rect.getAttribute("x") + +rect.getAttribute("width") / 2;
    const y = at.y + +rect.getAttribute("y") + +rect.getAttribute("height") / 2;
    const p = size(v);
    const k = Math.max(v.cam.k, READABLE);
    v.cam = { x: x - p.w / k / 2, y: y - p.h / k / 2, k };
    v.fitted = false;
    apply(v);
  }
  function wire(v) {
    const pts = new Map();
    let moved = false;
    let pinch = 0;
    v.port.addEventListener("pointerdown", (e) => {
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      moved = false;
      if (pts.size === 2) {
        const [a, b] = [...pts.values()];
        pinch = Math.hypot(a.x - b.x, a.y - b.y);
      }
    });
    v.port.addEventListener("pointermove", (e) => {
      const last = pts.get(e.pointerId);
      if (!last) return;
      const now = { x: e.clientX, y: e.clientY };
      if (pts.size === 2) {
        pts.set(e.pointerId, now);
        const [a, b] = [...pts.values()];
        const d = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch) zoomAt(v, d / pinch, (a.x + b.x) / 2, (a.y + b.y) / 2);
        pinch = d;
        moved = true;
        return;
      }
      if (!moved && Math.hypot(now.x - last.x, now.y - last.y) < 5) return;
      if (!moved) { v.port.setPointerCapture(e.pointerId); v.port.classList.add("dragging"); }
      moved = true;
      panBy(v, now.x - last.x, now.y - last.y);
      pts.set(e.pointerId, now);
    });
    const end = (e) => {
      pts.delete(e.pointerId);
      if (pts.size < 2) pinch = 0;
      v.port.classList.remove("dragging");
    };
    v.port.addEventListener("pointerup", end);
    v.port.addEventListener("pointercancel", end);
    // A wheel scrolls the chart, and the page once the chart is at its end; with ctrl, or a
    // trackpad's pinch, which comes as one, it zooms.
    v.port.addEventListener("wheel", (e) => {
      const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? size(v).h : 1;
      if (e.ctrlKey) {
        e.preventDefault();
        zoomAt(v, Math.exp(-e.deltaY * unit * 0.0015), e.clientX, e.clientY);
        return;
      }
      const dx = (e.shiftKey ? e.deltaY : e.deltaX) * unit;
      const dy = e.shiftKey ? 0 : e.deltaY * unit;
      if (!dx && room(v, dy) <= 0) return;
      e.preventDefault();
      panBy(v, -dx, -Math.sign(dy) * Math.min(Math.abs(dy), Math.max(0, room(v, dy))));
    }, { passive: false });
    v.port.addEventListener("click", (e) => {
      if (moved) { moved = false; return; }
      const st = e.target.closest(".st");
      if (st) return pick(st.dataset.id);
      const edge = e.target.closest(".edge");
      if (edge && edge.dataset.steps) return pickEdge(edge);
      clear();
    });
    v.port.addEventListener("keydown", (e) => {
      const st = e.target.closest && e.target.closest(".st");
      if (st && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(st.dataset.id); }
      if (e.key === "+" || e.key === "=") zoomAt(v, 1.25, ...mid(v));
      if (e.key === "-") zoomAt(v, 0.8, ...mid(v));
      if (e.key === "0") fit(v);
    });
    v.panel.querySelectorAll("[data-zoom]").forEach((b) => b.addEventListener("click", () => {
      const z = b.dataset.zoom;
      if (z === "fit") fit(v); else zoomAt(v, z === "in" ? 1.4 : 1 / 1.4, ...mid(v));
    }));
    new ResizeObserver(() => (v.fitted ? fit(v) : apply(v))).observe(v.port);
  }
  function mid(v) {
    const r = v.port.getBoundingClientRect();
    return [r.left + r.width / 2, r.top + r.height / 2];
  }

  // What a click shows.
  function stateEl(id) {
    return view(current).svg.querySelector(`.st[data-id="${CSS.escape(id)}"]`);
  }
  function clear() {
    if (!current) return;
    const v = view(current);
    v.panel.querySelectorAll(".ov-box.lit").forEach((b) => b.classList.remove("lit"));
    v.svg.classList.remove("focus");
    v.svg.querySelectorAll(".near, .picked, .in").forEach((n) => n.classList.remove("near", "picked", "in"));
    detail.classList.remove("open");
  }
  function cites(list) {
    if (!list.length) return "";
    return list.map((c) => {
      const name = c.href ? `<a href="${esc(c.href)}">${esc(c.text)}</a>` : `<code>${esc(c.text)}</code>`;
      const code = c.code && c.code.length
        ? `<pre>${c.code.map(([n, t]) => `<span class="${n === c.line ? "hit" : ""}"><span class="n">${n}</span>${esc(t)}</span>`).join("\n")}</pre>`
        : "";
      const where = c.href ? `<span class="quiet"> ${esc(c.href)}</span>` : `<span class="quiet"> (not found under features/)</span>`;
      return `<div class="cite">${name}${where}${code}</div>`;
    }).join("");
  }
  function guard(step) {
    if (!step.guard.length) return "";
    const d = DATA[current].states;
    const names = step.guard.map((g) => (d[g] ? d[g].label : g));
    return `<span class="guard">${step.unless ? "only unless" : "only when"} the other region is at: ${names.map(esc).join("; ")}</span>`;
  }
  function named(id) {
    const d = DATA[current].states[id];
    if (!d) return id;
    return d.composite ? `${d.composite} \u203a ${d.label}` : d.label;
  }
  function stepButton(step, other, arrow) {
    return `<li><button class="step" data-go="${esc(other)}"><span class="to">${arrow} ${esc(named(other))}</span>` +
      `<span class="says">${esc(step.label || "(no label)")}</span>${guard(step)}</button></li>`;
  }
  function pick(id, centre) {
    const data = DATA[current];
    const s = data.states[id];
    if (!s) return;
    const v = view(current);
    clear();
    const el = stateEl(id);
    v.svg.classList.add("focus");
    el.classList.add("near", "picked");
    const outs = data.steps.filter((t) => t.from === id);
    const ins = data.steps.filter((t) => t.to === id && t.from !== id);
    for (const t of outs) stateEl(t.to).classList.add("near");
    for (const t of ins) stateEl(t.from).classList.add("near");
    v.svg.querySelectorAll(".edge").forEach((p) => {
      if (p.dataset.from === id || p.dataset.to === id) p.classList.add("near");
      if (p.dataset.to === id && p.dataset.from !== id) p.classList.add("in");
    });
    const where = [s.region, s.composite].filter(Boolean).map(esc).join(" &rsaquo; ");
    const citeHtml = cites(s.cites);
    body.innerHTML =
      `<p class="kicker">${where || "state"}${s.start ? ' <span class="chip">start</span>' : ""}</p>` +
      `<h3>${esc(s.label)}</h3>` +
      `<h4>Code it cites</h4>${citeHtml || '<p class="quiet">This state cites no code line.</p>'}` +
      `<h4>Steps out (${outs.length})</h4>${outs.length ? `<ul>${outs.map((t) => stepButton(t, t.to, "&rarr;")).join("")}</ul>` : '<p class="quiet">None: once here, it stays.</p>'}` +
      `<h4>Steps in (${ins.length})</h4>${ins.length ? `<ul>${ins.map((t) => stepButton(t, t.from, "&larr;")).join("")}</ul>` : '<p class="quiet">None: only the start leads here.</p>'}` +
      stepCites(outs.concat(ins));
    detail.classList.add("open");
    if (centre) centreOn(v, el);
    history.replaceState(null, "", `#${encodeURIComponent(current)}/${encodeURIComponent(id)}`);
  }
  function stepCites(steps) {
    const all = steps.filter((t) => t.cites.length);
    if (!all.length) return "";
    return `<h4>Code its steps cite</h4>${all.map((t) => cites(t.cites)).join("")}`;
  }
  function pickEdge(edge) {
    const data = DATA[current];
    const ids = edge.dataset.steps.split(" ");
    const steps = data.steps.filter((t) => ids.includes(t.id));
    if (!steps.length) return;
    clear();
    const v = view(current);
    v.svg.classList.add("focus");
    edge.classList.add("near");
    stateEl(steps[0].from).classList.add("near");
    stateEl(steps[0].to).classList.add("near");
    body.innerHTML =
      `<p class="kicker">${steps.length === 1 ? "a step" : `${steps.length} steps`}</p>` +
      `<h3>${esc(named(steps[0].from))} &rarr; ${esc(named(steps[0].to))}</h3><ul>` +
      steps.map((t) => `<li><button class="step" data-go="${esc(t.to)}"><span class="says">${esc(t.label || "(no label)")}</span>${guard(t)}</button></li>`).join("") +
      `</ul>` + stepCites(steps) +
      `<h4>Go to</h4><ul><li><button class="step" data-go="${esc(steps[0].from)}"><span class="to">&larr; ${esc(named(steps[0].from))}</span></button></li>` +
      `<li><button class="step" data-go="${esc(steps[0].to)}"><span class="to">&rarr; ${esc(named(steps[0].to))}</span></button></li></ul>`;
    detail.classList.add("open");
  }
  body.addEventListener("click", (e) => {
    const go = e.target.closest("[data-go]");
    if (go) pick(go.dataset.go, true);
  });
  detail.querySelector(".close").addEventListener("click", clear);

  // Picking a chart, or the overview of them all.
  const OVERVIEW = "Overview";
  const flowPanel = document.querySelector(".flow-panel");
  function show(name, stateId) {
    if (!DATA[name]) name = OVERVIEW;
    current = name === OVERVIEW ? null : name;
    document.querySelectorAll(".tab").forEach((t) => {
      const mine = (t.dataset.chart || OVERVIEW) === name;
      t.setAttribute("aria-selected", String(mine));
      if (mine) t.parentElement.scrollLeft = t.offsetLeft - t.parentElement.offsetLeft - 14;
    });
    flowPanel.hidden = name !== OVERVIEW;
    document.querySelectorAll(".chart-panel").forEach((p) => { p.hidden = p.dataset.chart !== name; });
    body.innerHTML = name === OVERVIEW
      ? '<p class="quiet">Tap a chart on the map to open it, or a group in the list of hand-offs to open its chart at that group.</p>'
      : '<p class="quiet">Tap a box of the overview to move the chart to its group, or a state or an arrow to read it in full: the code line it cites, the steps into it and the steps out of it.</p>';
    // A chart drawn as lanes is a page to read down, with no camera and no detail to open.
    const lanes = !!document.querySelector(`.chart-panel[data-chart="${CSS.escape(name)}"][data-kind="lanes"]`);
    document.querySelector("main").classList.toggle("lanes", lanes);
    detail.classList.remove("open");
    if (name === OVERVIEW) {
      history.replaceState(null, "", location.pathname + location.search);
      return;
    }
    if (lanes) {
      history.replaceState(null, "", `#${encodeURIComponent(name)}`);
      return;
    }
    fit(view(name));
    find();
    if (stateId) pick(stateId, true);
    else history.replaceState(null, "", `#${encodeURIComponent(name)}`);
  }
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.chart || OVERVIEW)));

  // A box of a chart's overview is a group: a tap moves the chart to the group's states, all of
  // them in the frame, and lights them and the steps between them. Where they lie far apart the
  // labels get small; the detail lists the states, and a tap on one there centres it readable.
  function fitTo(v, els) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const el of els) {
      const rect = el.querySelector("rect");
      const at = offsetOf(v, rect);
      const x = at.x + +rect.getAttribute("x");
      const y = at.y + +rect.getAttribute("y");
      x0 = Math.min(x0, x); y0 = Math.min(y0, y);
      x1 = Math.max(x1, x + +rect.getAttribute("width")); y1 = Math.max(y1, y + +rect.getAttribute("height"));
    }
    const pad = 30;
    const p = size(v);
    const k = Math.min(2, p.w / (x1 - x0 + 2 * pad), p.h / (y1 - y0 + 2 * pad));
    v.cam = { x: (x0 + x1) / 2 - p.w / k / 2, y: (y0 + y1) / 2 - p.h / k / 2, k };
    v.fitted = false;
    apply(v);
  }
  function openGroup(box) {
    const v = view(current);
    const ids = box.dataset.states.split(" ");
    const els = ids.map(stateEl).filter(Boolean);
    clear();
    v.panel.querySelectorAll(".ov-box").forEach((b) => b.classList.toggle("lit", b === box));
    v.svg.classList.add("focus");
    els.forEach((el) => el.classList.add("near"));
    const inside = new Set(ids);
    v.svg.querySelectorAll(".edge").forEach((p) => {
      if (inside.has(p.dataset.from) && inside.has(p.dataset.to)) p.classList.add("near");
    });
    fitTo(v, els);
    body.innerHTML =
      `<p class="kicker">a group of ${ids.length} state${ids.length === 1 ? "" : "s"}</p>` +
      `<h3>${esc(box.dataset.name)}</h3><ul>` +
      ids.map((id) => `<li><button class="step" data-go="${esc(id)}"><span class="to">${esc(named(id))}</span></button></li>`).join("") +
      "</ul>";
    detail.classList.add("open");
    v.panel.querySelector(".stage").scrollIntoView({ block: "nearest" });
  }
  document.querySelectorAll(".chart-panel .overview").forEach((fig) => {
    const go = (e) => {
      const box = e.target.closest(".ov-box");
      if (box) openGroup(box);
    };
    fig.addEventListener("click", go);
    fig.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(e); } });
  });
  // The map: a chart's box opens its chart, and a group named in a hand-off opens its chart at
  // that group.
  flowPanel.addEventListener("click", (e) => {
    const box = e.target.closest(".flow-box");
    if (box) return show(box.dataset.chart);
    const go = e.target.closest("button.go");
    if (!go) return;
    show(go.dataset.chart);
    const target = view(go.dataset.chart).panel.querySelector(`.ov-box[data-box="${CSS.escape(go.dataset.box)}"]`);
    if (target) openGroup(target);
  });
  flowPanel.addEventListener("keydown", (e) => {
    const box = e.target.closest(".flow-box");
    if (box && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); show(box.dataset.chart); }
  });

  // Finding a state by its words.
  function find() {
    if (!current) return null;
    const q = search.value.trim().toLowerCase();
    if (document.querySelector("main").classList.contains("lanes")) return null;
    const v = view(current);
    let first = null;
    v.svg.querySelectorAll(".st").forEach((el) => {
      const s = DATA[current].states[el.dataset.id];
      const hit = q && (s.label.toLowerCase().includes(q) || s.composite.toLowerCase().includes(q));
      el.classList.toggle("found", !!hit);
      if (hit && !first) first = el;
    });
    return first;
  }
  search.addEventListener("input", find);
  search.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    const first = find();
    if (first) pick(first.dataset.id, true);
  });

  const [chart, state] = decodeURIComponent(location.hash.slice(1)).split("/");
  show(chart, state && DATA[chart] && DATA[chart].states[state] ? state : null);
})();
