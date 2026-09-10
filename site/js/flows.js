// Flows: one bar per effective month, accessions up (blue), separations down (red), DRP hatched.
// Hand-rolled SVG so the hover tooltip (pies per side) is ours. Keyboard: arrows move the focused month.
import { el, fmt, altTable } from "./common.js";

const BLUE = "#005ea2", RED = "#b3261e", DRP = "#d4a017";
const ACC_PALETTE = ["#005ea2", "#4c9a5b", "#2aa198", "#6fb3ff", "#8b5fbf", "#7f7f7f"];
const SEP_PALETTE = ["#b3261e", "#e07a3f", "#c2185b", "#d4a017", "#8b5fbf", "#6b7280", "#7f7f7f", "#4c9a5b", "#2aa198"];
const NS = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, ...children) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) n.setAttribute(k, v);
  for (const c of children) if (c != null) n.append(c.nodeType ? c : document.createTextNode(String(c)));
  return n;
}

function sumCats(cats, skip) {
  return Object.entries(cats || {}).filter(([c]) => c !== skip).reduce((s, [, n]) => s + n, 0);
}

// Build {month, acc, sep, drp, accCats, sepCats} rows for months >= first.
export function flowRows(series, first) {
  const months = new Set([...Object.keys(series.accessions || {}), ...Object.keys(series.separations || {})].filter((m) => m >= first));
  return [...months].sort().map((m) => ({
    month: m,
    acc: sumCats(series.accessions?.[m]),
    sep: sumCats(series.separations?.[m], "DRP"),
    drp: series.separations?.[m]?.DRP || 0,
    accCats: series.accessions?.[m] || {},
    sepCats: Object.fromEntries(Object.entries(series.separations?.[m] || {}).filter(([c]) => c !== "DRP")),
  }));
}

function pie(cats, names, palette, r = 34) {
  const entries = Object.entries(cats).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, n]) => s + n, 0);
  const g = svg("g", { transform: `translate(${r},${r})` });
  if (!total) return { node: g, legend: [] };
  let a0 = -Math.PI / 2;
  const legend = [];
  entries.forEach(([c, n], i) => {
    const a1 = a0 + (2 * Math.PI * n) / total;
    const large = a1 - a0 > Math.PI ? 1 : 0;
    const x0 = r * Math.cos(a0), y0 = r * Math.sin(a0), x1 = r * Math.cos(a1), y1 = r * Math.sin(a1);
    const d = entries.length === 1 ? `M0,${-r}A${r},${r},0,1,1,0,${r}A${r},${r},0,1,1,0,${-r}Z` : `M0,0L${x0},${y0}A${r},${r},0,${large},1,${x1},${y1}Z`;
    g.append(svg("path", { d, fill: palette[i % palette.length], stroke: "var(--card)", "stroke-width": 1 }));
    legend.push({ name: names[c]?.name || c, n, color: palette[i % palette.length], share: n / total });
    a0 = a1;
  });
  return { node: g, legend };
}

export function flowsChart(series, codes, { months, title = "Hires and separations by effective month", width: w } = {}) {
  const first = (months || series.months)[0];
  const rows = flowRows(series, first);
  const fig = el("figure");
  fig.append(el("figcaption", {}, title, " ", el("span", { class: "muted" }, "· blue up = accessions, red down = separations, gold = deferred resignations. Hover or arrow through the months.")));
  if (!rows.length) {
    fig.append(el("p", { class: "muted" }, "No personnel actions in range."));
    return fig;
  }
  const host = document.querySelector("#flows") || document.querySelector("main");
  const W = w || Math.min(1100, Math.max(300, (host?.clientWidth || 800) - 30)), H = 300, ML = 56, MR = 10, MT = 14, MB = 34;
  const iw = W - ML - MR, ih = H - MT - MB;
  const maxUp = Math.max(...rows.map((r) => r.acc), 1), maxDown = Math.max(...rows.map((r) => r.sep), 1);
  const scaleMax = Math.max(maxUp, maxDown);
  const zero = MT + ih * (maxUp / (maxUp + maxDown));
  const yUp = (v) => zero - (v / maxUp) * (zero - MT);
  const yDown = (v) => zero + (v / maxDown) * (MT + ih - zero);
  const bw = iw / rows.length, pad = Math.max(2, bw * 0.15);
  const root = svg("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img", "aria-label": `${title}, ${rows.length} months` });
  const defs = svg("defs");
  const pat = svg("pattern", { id: "drp-hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" });
  pat.append(svg("rect", { width: 6, height: 6, fill: RED }), svg("line", { x1: 0, y1: 0, x2: 0, y2: 6, stroke: DRP, "stroke-width": 3 }));
  defs.append(pat);
  root.append(defs);
  // axes
  root.append(svg("line", { x1: ML, x2: W - MR, y1: zero, y2: zero, stroke: "var(--fg)", "stroke-width": 1 }));
  const ticksUp = Math.max(1, Math.min(4, Math.floor((zero - MT) / 28))), ticksDown = Math.max(1, Math.min(4, Math.floor((MT + ih - zero) / 28)));
  const tickList = [];
  for (let i = 1; i <= ticksUp; i++) tickList.push([yUp((maxUp * i) / ticksUp), (maxUp * i) / ticksUp]);
  for (let i = 1; i <= ticksDown; i++) tickList.push([yDown((maxDown * i) / ticksDown), (maxDown * i) / ticksDown]);
  {
    for (const [y, v] of tickList) {
      root.append(svg("line", { x1: ML, x2: W - MR, y1: y, y2: y, stroke: "var(--line)", "stroke-dasharray": "2 3" }));
      root.append(svg("text", { x: ML - 6, y: y + 4, "text-anchor": "end", "font-size": 10, fill: "var(--muted)" }, fmt.money(v)));
    }
  }
  const bars = [];
  rows.forEach((r, i) => {
    const x = ML + i * bw + pad / 2, w = bw - pad;
    const g = svg("g", { class: "flow-bar", tabindex: 0, role: "button", "aria-label": `${fmt.month(r.month)}: ${fmt.int(r.acc)} accessions, ${fmt.int(r.sep)} separations` });
    g.append(svg("rect", { x, y: yUp(r.acc), width: w, height: zero - yUp(r.acc), fill: BLUE }));
    const sepH = yDown(r.sep) - zero, drpH = r.sep ? sepH * (r.drp / r.sep) : 0;
    g.append(svg("rect", { x, y: zero, width: w, height: Math.max(sepH - drpH, 0), fill: RED }));
    if (drpH > 0) g.append(svg("rect", { x, y: zero + sepH - drpH, width: w, height: drpH, fill: "url(#drp-hatch)" }));
    g.append(svg("rect", { x: ML + i * bw, y: MT, width: bw, height: ih, fill: "transparent" }));
    if (rows.length <= 24 || i % Math.ceil(rows.length / 12) === 0) {
      root.append(svg("text", { x: x + w / 2, y: H - 12, "text-anchor": "middle", "font-size": 10, fill: "var(--muted)" }, fmt.month(r.month).replace(" 20", " ")));
    }
    root.append(g);
    bars.push({ g, r, cx: x + w / 2 });
  });
  const wrap = el("div", { class: "plot", style: "position:relative" });
  wrap.append(root);
  const tip = el("div", { class: "flow-tip card", hidden: "", role: "status" });
  wrap.append(tip);
  const live = el("div", { class: "sr-only", "aria-live": "polite" });
  wrap.append(live);
  const accNames = codes.accession_category || {}, sepNames = codes.separation_category || {};

  function show(b) {
    const r = b.r;
    tip.innerHTML = "";
    const head = el("div", { style: "font-weight:600" }, fmt.month(r.month), " ", el("span", { class: "muted" }, `net ${fmt.signed(r.acc - r.sep)}`));
    tip.append(head);
    const cols = el("div", { style: "display:flex;gap:1rem;margin-top:.3rem" });
    for (const [label, cats, names, pal, total] of [["Accessions", r.accCats, accNames, ACC_PALETTE, r.acc], ["Separations", { ...r.sepCats, ...(r.drp ? { DRP: r.drp } : {}) }, { ...sepNames, DRP: { name: "of which deferred resignation" } }, SEP_PALETTE, r.sep]]) {
      const side = el("div", { style: "min-width:190px" });
      side.append(el("div", { class: "label", style: "font-size:.75rem;color:var(--muted);text-transform:uppercase" }, `${label} ${fmt.int(total)}`));
      const catsNoDrp = Object.fromEntries(Object.entries(cats).filter(([c]) => c !== "DRP"));
      const p = pie(catsNoDrp, names, pal);
      const ps = svg("svg", { viewBox: "0 0 68 68", width: 68, height: 68, "aria-hidden": "true" });
      ps.append(p.node);
      const legend = el("ul", { style: "list-style:none;margin:0;padding:0;font-size:.75rem" });
      for (const l of p.legend.slice(0, 6)) legend.append(el("li", {}, el("i", { style: `display:inline-block;width:.6rem;height:.6rem;background:${l.color};margin-right:.3rem;border-radius:2px` }), `${l.name} ${fmt.int(l.n)} (${fmt.pct(l.share)})`));
      if (cats.DRP) legend.append(el("li", { class: "muted" }, `of which deferred resignation ${fmt.int(cats.DRP)}`));
      side.append(el("div", { style: "display:flex;gap:.5rem;align-items:flex-start" }, ps, legend));
      cols.append(side);
    }
    tip.append(cols);
    tip.hidden = false;
    const left = Math.min(Math.max(b.cx - 200, 0), Math.max(W - 420, 0));
    tip.style.left = `${left}px`;
    live.textContent = `${fmt.month(r.month)}: ${fmt.int(r.acc)} accessions, ${fmt.int(r.sep)} separations, ${fmt.int(r.drp)} deferred resignations`;
    bars.forEach((o) => o.g.setAttribute("opacity", o === b ? "1" : "0.7"));
  }
  function hide() { tip.hidden = true; bars.forEach((o) => o.g.setAttribute("opacity", "1")); }
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
  fig.append(wrap);
  fig.append(altTable(["Effective month", "Accessions", "Separations", "Deferred resignations", "Net"], rows.map((r) => [fmt.month(r.month), fmt.int(r.acc), fmt.int(r.sep), fmt.int(r.drp), fmt.signed(r.acc - r.sep)])));
  return fig;
}
