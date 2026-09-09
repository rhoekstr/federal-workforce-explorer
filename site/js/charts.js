// Chart helpers on Observable Plot (loaded as UMD globals `Plot` and `d3` by the page).
import { el, fmt, altTable } from "./common.js";

const PALETTE = ["#005ea2", "#e07a3f", "#4c9a5b", "#8b5fbf", "#b3261e", "#6b7280", "#d4a017", "#2aa198", "#c2185b", "#7f7f7f"];

export function figure(caption, plotNode, alt) {
  const f = el("figure");
  if (caption) f.append(el("figcaption", {}, caption));
  const wrap = el("div", { class: "plot" });
  wrap.append(plotNode);
  f.append(wrap);
  if (alt) f.append(alt);
  return f;
}

function width() {
  return Math.min(1100, Math.max(320, (document.querySelector("main")?.clientWidth || 800) - 40));
}

// Monthly headcount line. series: {months:[yyyymm], headcount:{yyyymm:n}}
export function headcountChart(series, { title = "Headcount by month", compare } = {}) {
  const data = series.months.filter((m) => series.headcount[m] != null).map((m) => ({ date: fmt.monthDate(m), n: series.headcount[m], month: m }));
  if (!data.length) return el("p", { class: "muted" }, "No headcount series yet.");
  const marks = [
    Plot.ruleY([0]),
    Plot.lineY(data, { x: "date", y: "n", stroke: PALETTE[0], strokeWidth: 2 }),
    Plot.dot(data, { x: "date", y: "n", fill: PALETTE[0], r: 3, title: (d) => `${fmt.month(d.month)}: ${fmt.int(d.n)}` }),
  ];
  if (compare?.length) {
    marks.push(Plot.lineY(compare, { x: "date", y: "n", stroke: PALETTE[1], strokeDasharray: "4 3", strokeWidth: 2 }));
    marks.push(Plot.dot(compare, { x: "date", y: "n", stroke: PALETTE[1], fill: (d) => (d.kind === "estimate" ? "white" : PALETTE[1]), r: 4, title: (d) => `${d.label}: ${fmt.int(d.n)} (${d.kind})` }));
  }
  const plot = Plot.plot({ width: width(), height: 260, marginLeft: 60, x: { type: "utc", label: null, ticks: d3.utcMonth.every(data.length > 18 ? 3 : 1), tickFormat: d3.utcFormat("%b %y") }, y: { grid: true, label: "Employees", tickFormat: "~s", domain: [0, d3.max(data, (d) => d.n) * 1.08] }, marks });
  const alt = altTable(["Month", "Headcount"], data.map((d) => [fmt.month(d.month), fmt.int(d.n)]));
  return figure(title, plot, alt);
}

// Accessions vs separations per effective month, stacked by category. actions: {yyyymm: {cat: n}}
export function actionsChart(series, codes, { title = "Hires and separations by effective month", months } = {}) {
  const sepNames = codes.separation_category || {}, accNames = codes.accession_category || {};
  const rows = [];
  const range = months || series.months;
  const minMonth = range[0];
  for (const [eff, cats] of Object.entries(series.separations || {})) {
    if (eff < minMonth) continue;
    for (const [c, n] of Object.entries(cats)) {
      if (c === "DRP") continue;
      rows.push({ date: fmt.monthDate(eff), month: eff, kind: "Separations", cat: sepNames[c]?.name || c, n: -n });
    }
  }
  for (const [eff, cats] of Object.entries(series.accessions || {})) {
    if (eff < minMonth) continue;
    for (const [c, n] of Object.entries(cats)) rows.push({ date: fmt.monthDate(eff), month: eff, kind: "Accessions", cat: accNames[c]?.name || c, n });
  }
  if (!rows.length) return el("p", { class: "muted" }, "No personnel actions in range.");
  const cats = [...new Set(rows.map((r) => r.cat))];
  const plot = Plot.plot({
    width: width(), height: 300, marginLeft: 60, x: { type: "utc", label: null, interval: "month", ticks: d3.utcMonth.every(1), tickFormat: d3.utcFormat("%b %y") },
    y: { grid: true, label: "Accessions ↑ / Separations ↓", tickFormat: (v) => fmt.money(Math.abs(v)) },
    color: { domain: cats, range: PALETTE, legend: true },
    marks: [Plot.ruleY([0]), Plot.rectY(rows, { x: "date", y: "n", fill: "cat", interval: "month", title: (d) => `${fmt.month(d.month)} ${d.cat}: ${fmt.int(Math.abs(d.n))}` })],
  });
  const byMonth = d3.rollups(rows, (v) => d3.sum(v, (d) => d.n), (d) => d.month, (d) => d.kind);
  const alt = altTable(["Effective month", "Accessions", "Separations"], byMonth.sort().map(([m, kinds]) => {
    const k = Object.fromEntries(kinds);
    return [fmt.month(m), fmt.int(k.Accessions || 0), fmt.int(Math.abs(k.Separations || 0))];
  }));
  return figure(title, plot, alt);
}

// Separations by category per month, as small multiples of bars. Includes the DRP overlay count.
export function separationsByCategory(series, codes, { months, title = "Separations by category" } = {}) {
  const names = codes.separation_category || {};
  const range = months || series.months;
  const minMonth = range[0];
  const totals = {};
  for (const [eff, cats] of Object.entries(series.separations || {})) {
    if (eff < minMonth) continue;
    for (const [c, n] of Object.entries(cats)) totals[c] = (totals[c] || 0) + n;
  }
  const rows = Object.entries(totals).map(([c, n]) => ({ cat: c === "DRP" ? "of which: deferred resignation" : names[c]?.name || c, n, drp: c === "DRP" })).sort((a, b) => b.n - a.n);
  if (!rows.length) return el("p", { class: "muted" }, "No separations in range.");
  const plot = Plot.plot({
    width: width(), height: 26 * rows.length + 40, marginLeft: 240, x: { grid: true, label: "Separations, " + fmt.month(minMonth) + " to " + fmt.month(range[range.length - 1]), tickFormat: "~s" },
    y: { label: null, domain: rows.map((r) => r.cat) },
    marks: [Plot.barX(rows, { y: "cat", x: "n", fill: (d) => (d.drp ? PALETTE[6] : PALETTE[4]), title: (d) => `${d.cat}: ${fmt.int(d.n)}` }), Plot.text(rows, { y: "cat", x: "n", text: (d) => fmt.int(d.n), dx: 4, textAnchor: "start", fontSize: 11 })],
  });
  return figure(title, plot, altTable(["Category", "Separations"], rows.map((r) => [r.cat, fmt.int(r.n)])));
}

// Horizontal bar mix of one dimension for the latest month. mix: {value: n}
export function mixChart(mix, { title, labels = {}, order, top = 20, sortByValue = true } = {}) {
  let rows = Object.entries(mix || {}).filter(([k]) => k !== "_other").map(([k, n]) => ({ k, label: labels[k]?.name || labels[k] || k, n }));
  if (!rows.length) return null;
  if (order) rows.sort((a, b) => order(a.k) - order(b.k)); else if (sortByValue) rows.sort((a, b) => b.n - a.n);
  const other = mix._other || 0;
  rows = rows.slice(0, top);
  if (other) rows.push({ k: "_other", label: "All other", n: other });
  const total = d3.sum(rows, (d) => d.n);
  const plot = Plot.plot({
    width: Math.min(560, width()), height: 22 * rows.length + 36, marginLeft: 170, x: { label: null, tickFormat: "~s", grid: true },
    y: { label: null, domain: rows.map((r) => r.label) },
    marks: [Plot.barX(rows, { y: "label", x: "n", fill: PALETTE[0], title: (d) => `${d.label}: ${fmt.int(d.n)} (${fmt.pct(d.n / total)})` }), Plot.text(rows, { y: "label", x: "n", text: (d) => fmt.pct(d.n / total), dx: 4, textAnchor: "start", fontSize: 10 })],
  });
  return figure(title, plot, altTable([title, "Employees", "Share"], rows.map((r) => [r.label, fmt.int(r.n), fmt.pct(r.n / total)])));
}

// Stacked horizontal split bar (administered / operations / other) as plain HTML.
export function splitBar(parts) {
  const total = parts.reduce((s, p) => s + Math.max(p.value || 0, 0), 0) || 1;
  const bar = el("div", { class: "bar", role: "img", "aria-label": parts.map((p) => `${p.label} ${fmt.dollars(p.value)}`).join(", ") });
  const legend = el("div", { class: "legend" });
  parts.forEach((p, i) => {
    const w = Math.max(p.value || 0, 0) / total;
    bar.append(el("span", { style: `width:${(100 * w).toFixed(2)}%;background:${PALETTE[i]}`, title: `${p.label}: ${fmt.dollars(p.value)}` }));
    legend.append(el("span", {}, el("i", { style: `background:${PALETTE[i]}` }), `${p.label} ${fmt.dollars(p.value)} (${fmt.pct(w)})`));
  });
  return el("div", {}, bar, legend);
}

export function sparkline(values, w = 150, h = 18) {
  const v = values.filter((x) => x != null);
  if (v.length < 2) return null;
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  const pts = v.map((x, i) => `${(i / (v.length - 1)) * w},${h - 2 - ((x - min) / span) * (h - 4)}`).join(" ");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("class", "spark");
  svg.setAttribute("aria-hidden", "true");
  const p = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  p.setAttribute("points", pts);
  p.setAttribute("fill", "none");
  p.setAttribute("stroke", v[v.length - 1] < v[0] ? "#b3261e" : "#4c9a5b");
  p.setAttribute("stroke-width", "1.5");
  svg.append(p);
  return svg;
}
