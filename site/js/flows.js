// Flows: one bar per effective month, accessions up (blue), separations down (red), deferred resignations hatched.
// Built from named catalog measures rather than a category dimension, so it works at every level of the tree.
// Hand-rolled SVG so the hover tooltip (a pie per side) is ours. Keyboard: arrows move the focused month.
import { el, fmt, altTable } from "./common.js";
import * as M from "./measures.js";

const BLUE = "#005ea2", RED = "#b3261e", DRP = "#d4a017";
const ACC_PALETTE = ["#005ea2", "#4c9a5b", "#2aa198", "#6fb3ff"];
const SEP_PALETTE = ["#b3261e", "#e07a3f", "#c2185b", "#8b5fbf", "#6b7280"];
const UP = ["new_hires", "transfers_in"];
const DOWN = ["quits", "retirements", "rifs", "transfers_out", "terminations"];
const NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, ...children) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  for (const c of children) if (c != null) n.append(c.nodeType ? c : document.createTextNode(String(c)));
  return n;
}

/** Rows of {period, label, acc, sep, drp, up:{measure:n}, down:{measure:n}} from the node's measures. */
export async function flowRows(code, from) {
  const wanted = ["accessions", "separations", "deferred_resignations", ...UP, ...DOWN];
  const got = {};
  for (const m of wanted) got[m] = await M.series(code, m);
  const periods = new Map();
  for (const m of wanted) for (const d of got[m]) {
    if (from && d.period < from) continue;
    const row = periods.get(d.period) || { period: d.period, label: d.label, date: d.date, up: {}, down: {}, acc: 0, sep: 0, drp: 0 };
    if (m === "accessions") row.acc = d.value;
    else if (m === "separations") row.sep = d.value;
    else if (m === "deferred_resignations") row.drp = d.value;
    else if (UP.includes(m)) row.up[m] = d.value;
    else row.down[m] = d.value;
    periods.set(d.period, row);
  }
  return [...periods.values()].sort((a, b) => a.period.localeCompare(b.period));
}

function pie(parts, palette, r = 34) {
  const entries = parts.filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, n]) => s + n, 0);
  const g = svg("g", { transform: `translate(${r},${r})` });
  const legend = [];
  if (!total) return { node: g, legend };
  let a0 = -Math.PI / 2;
  entries.forEach(([name, n], i) => {
    const a1 = a0 + (2 * Math.PI * n) / total;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const x0 = r * Math.cos(a0), y0 = r * Math.sin(a0), x1 = r * Math.cos(a1), y1 = r * Math.sin(a1);
    const d = entries.length === 1
      ? `M0,${-r}A${r},${r},0,1,1,0,${r}A${r},${r},0,1,1,0,${-r}Z`
      : `M0,0L${x0},${y0}A${r},${r},0,${large},1,${x1},${y1}Z`;
    g.append(svg("path", { d, fill: palette[i % palette.length], stroke: "var(--card)", "stroke-width": 1 }));
    legend.push({ name, n, color: palette[i % palette.length], share: n / total });
    a0 = a1;
  });
  return { node: g, legend };
}

export async function flowsPanel(container, { code, name, from }) {
  container.innerHTML = "";
  const panel = el("div", { class: "panel" }, el("h2", {}, "Hires and separations"));
  container.append(panel);
  const body = el("div", {}, el("p", { class: "muted" }, "Loading…"));
  panel.append(body);

  const rows = await flowRows(code, from);
  body.innerHTML = "";
  if (!rows.length) { body.append(el("p", { class: "muted" }, "No personnel actions in range.")); return; }

  panel.insertBefore(el("p", { class: "muted" },
    "Blue above the line is ", M.defineLink("accessions", "accessions"), ", red below is ",
    M.defineLink("separations", "separations"), ", gold is ", M.defineLink("deferred_resignations", "deferred resignations"),
    ". Dated by the month the action took effect. Hover or arrow through the months."), body);

  const W = Math.min(1100, Math.max(300, (container.clientWidth || 800) - 30)), H = 300, ML = 56, MR = 10, MT = 14, MB = 34;
  const iw = W - ML - MR, ih = H - MT - MB;
  const maxUp = Math.max(...rows.map((r) => r.acc), 1), maxDown = Math.max(...rows.map((r) => r.sep), 1);
  const zero = MT + ih * (maxUp / (maxUp + maxDown));
  const yUp = (v) => zero - (v / maxUp) * (zero - MT);
  const yDown = (v) => zero + (v / maxDown) * (MT + ih - zero);
  const bw = iw / rows.length, pad = Math.max(1, Math.min(4, bw * 0.15));
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": `Hires and separations for ${name}, ${rows.length} months` });
  const defs = svg("defs");
  const pat = svg("pattern", { id: "drp-hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
  pat.append(svg("rect", { width: 6, height: 6, fill: RED }), svg("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: DRP, "stroke-width": 3 }));
  defs.append(pat);
  root.append(defs, svg("line", { x1: ML, x2: W - MR, y1: zero, y2: zero, stroke: "var(--fg)", "stroke-width": 1 }));
  const ticksUp = Math.max(1, Math.min(4, Math.floor((zero - MT) / 28))), ticksDown = Math.max(1, Math.min(4, Math.floor((MT + ih - zero) / 28)));
  for (let i = 1; i <= ticksUp; i++) { const v = (maxUp * i) / ticksUp, y = yUp(v); root.append(svg("line", { x1: ML, x2: W - MR, y1: y, y2: y, stroke: "var(--line)", "stroke-dasharray": "2 3" }), svg("text", { x: ML - 6, y: y + 4, "text-anchor": "end", "font-size": 10, fill: "var(--muted)" }, fmt.money(v))); }
  for (let i = 1; i <= ticksDown; i++) { const v = (maxDown * i) / ticksDown, y = yDown(v); root.append(svg("line", { x1: ML, x2: W - MR, y1: y, y2: y, stroke: "var(--line)", "stroke-dasharray": "2 3" }), svg("text", { x: ML - 6, y: y + 4, "text-anchor": "end", "font-size": 10, fill: "var(--muted)" }, fmt.money(v))); }

  const bars = [];
  rows.forEach((r, i) => {
    const x = ML + i * bw + pad / 2, w = Math.max(1, bw - pad);
    const g = svg("g", { class: "flow-bar", tabindex: 0, role: "button", "aria-label": `${r.label}: ${fmt.int(r.acc)} accessions, ${fmt.int(r.sep)} separations` });
    g.append(svg("rect", { x, y: yUp(r.acc), width: w, height: Math.max(0, zero - yUp(r.acc)), fill: BLUE }));
    const sepH = yDown(r.sep) - zero, drpH = r.sep ? sepH * (Math.min(r.drp, r.sep) / r.sep) : 0;
    g.append(svg("rect", { x, y: zero, width: w, height: Math.max(sepH - drpH, 0), fill: RED }));
    if (drpH > 0) g.append(svg("rect", { x, y: zero + sepH - drpH, width: w, height: drpH, fill: "url(#drp-hatch)" }));
    g.append(svg("rect", { x: ML + i * bw, y: MT, width: bw, height: ih, fill: "transparent" }));
    if (rows.length <= 24 ? true : i % Math.ceil(rows.length / 12) === 0) {
      root.append(svg("text", { x: x + w / 2, y: H - 12, "text-anchor": "middle", "font-size": 10, fill: "var(--muted)" }, r.label.replace(" 20", " ")));
    }
    root.append(g);
    bars.push({ g, r, cx: x + w / 2 });
  });

  const wrap = el("div", { class: "plot", style: "position:relative" }, root);
  const tip = el("div", { class: "flow-tip card", hidden: "", role: "status" });
  const live = el("div", { class: "sr-only", "aria-live": "polite" });
  wrap.append(tip, live);
  body.append(wrap);

  const title = (code) => M.spec(code)?.title || code;
  function show(b) {
    const r = b.r;
    tip.innerHTML = "";
    tip.append(el("div", { style: "font-weight:600" }, r.label, " ", el("span", { class: "muted" }, `net ${fmt.signed(r.acc - r.sep)}`)));
    const cols = el("div", { style: "display:flex;gap:1rem;margin-top:.3rem" });
    for (const [label, parts, pal, total, extra] of [
      ["Accessions", UP.map((m) => [title(m), r.up[m] || 0]), ACC_PALETTE, r.acc, null],
      ["Separations", DOWN.map((m) => [title(m), r.down[m] || 0]), SEP_PALETTE, r.sep, r.drp],
    ]) {
      const side = el("div", { style: "min-width:190px" });
      side.append(el("div", { class: "label", style: "font-size:.75rem;color:var(--muted);text-transform:uppercase" }, `${label} ${fmt.int(total)}`));
      const p = pie(parts, pal);
      const ps = svg("svg", { viewBox: "0 0 68 68", width: 68, height: 68, "aria-hidden": "true" });
      ps.append(p.node);
      const legend = el("ul", { style: "list-style:none;margin:0;padding:0;font-size:.75rem" });
      for (const l of p.legend) legend.append(el("li", {}, el("i", { style: `display:inline-block;width:.6rem;height:.6rem;background:${l.color};margin-right:.3rem;border-radius:2px` }), `${l.name} ${fmt.int(l.n)} (${fmt.pct(l.share)})`));
      if (extra) legend.append(el("li", { class: "muted" }, `of which deferred resignation ${fmt.int(extra)}`));
      side.append(el("div", { style: "display:flex;gap:.5rem;align-items:flex-start" }, ps, legend));
      cols.append(side);
    }
    tip.append(cols);
    tip.hidden = false;
    tip.style.left = `${Math.min(Math.max(b.cx - 200, 0), Math.max(W - 420, 0))}px`;
    live.textContent = `${r.label}: ${fmt.int(r.acc)} accessions, ${fmt.int(r.sep)} separations, ${fmt.int(r.drp)} deferred resignations`;
    bars.forEach((o) => o.g.setAttribute("opacity", o === b ? "1" : "0.7"));
  }
  const hide = () => { tip.hidden = true; bars.forEach((o) => o.g.setAttribute("opacity", "1")); };
  bars.forEach((b, i) => {
    b.g.addEventListener("mouseenter", () => show(b));
    b.g.addEventListener("focus", () => show(b));
    b.g.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" && bars[i + 1]) { bars[i + 1].g.focus(); e.preventDefault(); }
      if (e.key === "ArrowLeft" && bars[i - 1]) { bars[i - 1].g.focus(); e.preventDefault(); }
      if (e.key === "Escape") hide();
    });
  });
  root.addEventListener("mouseleave", hide);
  body.append(altTable(["Effective month", "Accessions", "Separations", "Deferred resignations", "Net"],
    rows.map((r) => [r.label, fmt.int(r.acc), fmt.int(r.sep), fmt.int(r.drp), fmt.signed(r.acc - r.sep)])));
}
