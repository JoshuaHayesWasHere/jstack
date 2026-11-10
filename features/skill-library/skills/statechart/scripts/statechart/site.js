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

  // Pan and zoom, by moving each chart's viewBox.
  function view(name) {
    if (views[name]) return views[name];
    const panel = document.querySelector(`.chart-panel[data-chart="${CSS.escape(name)}"]`);
    const svg = panel.querySelector("svg.chart");
    const v = { panel, svg, port: panel.querySelector(".viewport"), full: { x: -20, y: -20, w: +svg.dataset.w, h: +svg.dataset.h } };
    v.box = { ...v.full };
    views[name] = v;
    wire(v);
    return v;
  }
  function apply(v) {
    const b = v.box;
    v.svg.setAttribute("viewBox", `${b.x} ${b.y} ${b.w} ${b.h}`);
  }
  function fit(v) {
    v.box = { ...v.full };
    apply(v);
  }
  function scale(v) {
    const r = v.port.getBoundingClientRect();
    return Math.max(v.box.w / r.width, v.box.h / r.height);
  }
  function zoomAt(v, factor, cx, cy) {
    const r = v.port.getBoundingClientRect();
    const s = scale(v);
    const ox = v.box.x + (v.box.w - r.width * s) / 2;
    const oy = v.box.y + (v.box.h - r.height * s) / 2;
    const px = ox + (cx - r.left) * s;
    const py = oy + (cy - r.top) * s;
    const w = Math.min(v.full.w * 4, Math.max(120, v.box.w / factor));
    const k = w / v.box.w;
    v.box = { x: px - (px - v.box.x) * k, y: py - (py - v.box.y) * k, w, h: v.box.h * k };
    apply(v);
  }
  function centreOn(v, el) {
    const rect = el.querySelector("rect");
    const g = el.closest(".region");
    const t = g.transform.baseVal.consolidate();
    const dx = t ? t.matrix.e : 0;
    const x = +rect.getAttribute("x") + dx + 105;
    const y = +rect.getAttribute("y") + +rect.getAttribute("height") / 2;
    const r = v.port.getBoundingClientRect();
    const w = Math.min(v.box.w, 1100);
    const h = w * (r.height / Math.max(1, r.width));
    v.box = { x: x - w / 2, y: y - h / 2, w, h };
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
      const s = scale(v);
      v.box.x -= (now.x - last.x) * s;
      v.box.y -= (now.y - last.y) * s;
      pts.set(e.pointerId, now);
      apply(v);
    });
    const end = (e) => {
      pts.delete(e.pointerId);
      if (pts.size < 2) pinch = 0;
      v.port.classList.remove("dragging");
    };
    v.port.addEventListener("pointerup", end);
    v.port.addEventListener("pointercancel", end);
    v.port.addEventListener("wheel", (e) => {
      e.preventDefault();
      zoomAt(v, Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.0015)), e.clientX, e.clientY);
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
    new ResizeObserver(() => apply(v)).observe(v.port);
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
    const v = view(current);
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

  // Picking a chart.
  function show(name, stateId) {
    if (!DATA[name]) name = Object.keys(DATA)[0];
    current = name;
    document.querySelectorAll(".tab").forEach((t) => {
      t.setAttribute("aria-selected", String(t.dataset.chart === name));
      if (t.dataset.chart === name) t.parentElement.scrollLeft = t.offsetLeft - t.parentElement.offsetLeft - 14;
    });
    document.querySelectorAll(".chart-panel").forEach((p) => { p.hidden = p.dataset.chart !== name; });
    const v = view(name);
    fit(v);
    body.innerHTML = '<p class="quiet">Tap a state or an arrow to read it in full: the code line it cites, the steps into it and the steps out of it.</p>';
    detail.classList.remove("open");
    find();
    if (stateId) pick(stateId, true);
    else history.replaceState(null, "", `#${encodeURIComponent(name)}`);
  }
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => show(t.dataset.chart)));

  // Finding a state by its words.
  function find() {
    const q = search.value.trim().toLowerCase();
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
