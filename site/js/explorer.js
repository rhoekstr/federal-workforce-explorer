// Measures explorer: any measures, any nodes, any span, on one time axis. State lives in the URL.
// Series come from data/slices/measures/{node}.json (government, departments, agencies, groups); other nodes
// fall back to a DuckDB query over the published measures parquet.
import { el, fmt, loadJSON, altTable } from "./common.js";
import { figure } from "./charts.js";

const PALETTE = ["#005ea2", "#e07a3f", "#4c9a5b", "#8b5fbf", "#b3261e", "#6b7280", "#d4a017", "#2aa198", "#c2185b", "#7f7f7f"];
const UNIT_LABEL = { people: "People", count: "Count", percentage: "Percent", ratio: "Ratio", currency: "Dollars", years: "Years", dollars_per_person: "Dollars per person", index: "Index (0–100)", rate: "Per 1,000" };
const FAMILIES = [
  ["Workforce", (m) => m.cadence === "month" && !m.code.startsWith("fevs_") && m.kind !== "hidden"],
  ["Money", (m) => m.cadence === "quarter"],
  ["Annual and survey", (m) => m.cadence === "fiscal_year" || m.cadence === "survey_year"],
];

export function periodDate(ptype, pstart) {
  const d = new Date(pstart + "T00:00:00Z");
  return d;
}

function periodLabel(ptype, pstart) {
  const y = +pstart.slice(0, 4), m = +pstart.slice(5, 7);
  if (ptype === "month") return fmt.month(pstart.slice(0, 4) + pstart.slice(5, 7));
  if (ptype === "quarter") { const fy = m >= 10 ? y + 1 : y; const q = m >= 10 ? 1 : m <= 3 ? 2 : m <= 6 ? 3 : 4; return `FY${fy} Q${q}`; }
  if (ptype === "fiscal_year") return `FY${m >= 10 ? y + 1 : y}`;
  return String(y);
}

function formatValue(m, v) {
  if (v == null) return "—";
  if (m.unit === "percentage") return v.toFixed(m.digits ?? 1) + "%";
  if (m.unit === "currency") return fmt.dollars(v);
  if (m.unit === "dollars_per_person") return fmt.dollars(v);
  if (m.unit === "ratio" || m.unit === "years" || m.unit === "index") return v.toFixed(m.digits ?? 1);
  return fmt.int(v);
}

async function loadSeries(node, measure, manifest) {
  const slice = await loadJSON(`data/slices/measures/${node}.json`).catch(() => null);
  if (slice) return slice.measures[measure] || null;
  // Fallback: DuckDB over the same-origin copy of the measures table (sub-elements and historical nodes).
  const url = new URL("data/measures.parquet", location.href).href;
  let rows;
  try {
    const { runQuery } = await import("./query.js");
    const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error("timed out after 90 s")), 90000));
    rows = await Promise.race([runQuery(`SELECT period_type, period_start, value, n, notation FROM read_parquet('${url}') WHERE node = '${node.replace(/'/g, "''")}' AND measure = '${measure}' AND dim IS NULL AND value IS NOT NULL ORDER BY period_start`), timeout]);
  } catch (err) {
    console.warn("measures query failed", err);
    return null;
  }
  if (!rows.length) return null;
  const values = {};
  for (const r of rows) values[r.period_start] = [r.value == null ? null : Number(r.value), r.n == null ? null : Number(r.n), r.notation];
  return { period_type: rows[0].period_type, values };
}

export async function explorer(container, { catalog, nodes, manifest, state, onState }) {
  const measures = catalog.measures;
  const visible = Object.entries(measures).filter(([, m]) => m.display !== false).map(([code, m]) => ({ code, ...m }));
  const nodeList = Object.values(nodes).filter((n) => n.kind !== "subelement" || true);
  container.innerHTML = "";

  // Controls
  const selNodes = new Set((state.nodes || "gov").split(",").filter((c) => nodes[c]));
  const selMeasures = new Set((state.measures || "headcount").split(",").filter((c) => measures[c]));
  const controls = el("div", { class: "panel" });
  const nodeInput = el("input", { type: "search", list: "x-nodes", placeholder: "add a unit by name…", "aria-label": "Add unit", size: 32 });
  const nodeList_ = el("datalist", { id: "x-nodes" });
  for (const n of Object.values(nodes).sort((a, b) => (a.kind === "gov" ? -1 : 0) || a.name.localeCompare(b.name)).slice(0, 900)) nodeList_.append(el("option", { value: `${n.name} (${n.code})` }));
  const nodeChips = el("span");
  const measureSel = el("select", { "aria-label": "Add measure" }, el("option", { value: "" }, "add a measure…"));
  for (const [fam, test] of FAMILIES) {
    const og = el("optgroup", { label: fam });
    for (const m of visible.filter(test)) og.append(el("option", { value: m.code }, m.title));
    if (og.children.length) measureSel.append(og);
  }
  const measureChips = el("span");
  const fromSel = el("select", { "aria-label": "From" }, ...["2005", "2010", "2015", "2019", "2023", "2025"].map((y) => el("option", { value: `${y}-01-01`, selected: (state.from || "2005-01-01") === `${y}-01-01` ? "" : null }, `since ${y}`)));
  const modeSel = el("select", { "aria-label": "Scale" }, el("option", { value: "native" }, "native units"), el("option", { value: "index", selected: state.mode === "index" ? "" : null }, "index (100 = first point)"));
  controls.append(el("h2", {}, "Explore"), el("div", { class: "controls" }, el("label", {}, "Units ", nodeInput), nodeList_, nodeChips), el("div", { class: "controls" }, el("label", {}, "Measures ", measureSel), measureChips), el("div", { class: "controls" }, el("label", {}, "Range ", fromSel), el("label", {}, "Scale ", modeSel)));
  container.append(controls);
  const body = el("div");
  container.append(body);

  function readState() { return { nodes: [...selNodes].join(","), measures: [...selMeasures].join(","), from: fromSel.value, mode: modeSel.value }; }

  async function render() {
    const st = readState();
    onState?.(st);
    nodeChips.innerHTML = "";
    for (const c of selNodes) nodeChips.append(el("button", { type: "button", class: "badge", title: "remove", onclick: () => { if (selNodes.size > 1) { selNodes.delete(c); render(); } } }, `${nodes[c].name} ×`), " ");
    measureChips.innerHTML = "";
    for (const c of selMeasures) measureChips.append(el("button", { type: "button", class: "badge", title: measures[c].definition, onclick: () => { if (selMeasures.size > 1) { selMeasures.delete(c); render(); } } }, `${measures[c].title} ×`), " ");
    body.innerHTML = "";
    body.append(el("p", { class: "muted" }, "Loading…"));
    const series = [];
    for (const node of selNodes) for (const code of selMeasures) {
      const s = await loadSeries(node, code, manifest);
      const m = measures[code];
      if (!s) { series.push({ node, code, m, empty: true }); continue; }
      const pts = Object.entries(s.values).filter(([p]) => p >= st.from).map(([p, v]) => ({ period: p, date: periodDate(s.period_type, p), value: Array.isArray(v) ? v[0] : v, n: Array.isArray(v) ? v[1] : null, note: Array.isArray(v) ? v[2] : null, label: periodLabel(s.period_type, p) })).filter((d) => d.value != null);
      series.push({ node, code, m, ptype: s.period_type, pts, label: `${nodes[node].name}: ${m.title}` });
    }
    body.innerHTML = "";
    const missing = series.filter((s) => s.empty);
    if (missing.length) body.append(el("p", { class: "notice" }, `No values for: ${missing.map((s) => `${nodes[s.node].name} / ${s.m.title}`).join("; ")}. Check the catalog for each measure's levels and since-date.`));
    const present = series.filter((s) => !s.empty && s.pts.length);
    if (!present.length) { body.append(el("p", { class: "muted" }, "Nothing to plot.")); return; }
    const width = Math.min(1100, Math.max(320, (container.clientWidth || 900) - 30));
    const groups = new Map();
    for (const s of present) { const key = st.mode === "index" ? "index" : s.m.unit; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(s); }
    const xDomain = [d3.min(present, (s) => d3.min(s.pts, (d) => d.date)), d3.max(present, (s) => d3.max(s.pts, (d) => d.date))];
    let colorIndex = 0;
    for (const [unit, group] of groups) {
      const rows = [];
      for (const s of group) {
        const base = st.mode === "index" ? s.pts[0].value || 1 : 1;
        const color = PALETTE[colorIndex++ % PALETTE.length];
        for (const d of s.pts) rows.push({ ...d, series: s.label, value: st.mode === "index" ? (100 * d.value) / base : d.value, fine: s.ptype === "month" || s.ptype === "quarter", color, m: s.m });
      }
      const marks = [Plot.ruleY([0])];
      const fine = rows.filter((r) => r.fine), coarse = rows.filter((r) => !r.fine);
      if (fine.length) marks.push(Plot.lineY(fine, { x: "date", y: "value", stroke: "series", strokeWidth: 2, curve: "step-after" === "x" ? "linear" : "linear" }));
      if (coarse.length) marks.push(Plot.lineY(coarse, { x: "date", y: "value", stroke: "series", strokeDasharray: "4 3" }), Plot.dot(coarse, { x: "date", y: "value", fill: (d) => (d.note === "estimate" ? "white" : undefined), stroke: "series", r: 4 }));
      marks.push(Plot.dot(rows, { x: "date", y: "value", fill: "series", r: fine.length > 60 ? 0 : 2.5, title: (d) => `${d.series}\n${d.label}: ${st.mode === "index" ? d.value.toFixed(1) : formatValue(d.m, d.value)}${d.n != null ? ` (n ${fmt.int(d.n)})` : ""}${d.note ? ` [${d.note}]` : ""}` }));
      const plot = Plot.plot({
        width, height: 300, marginLeft: 64, x: { type: "utc", label: null, domain: xDomain },
        y: { grid: true, label: st.mode === "index" ? "Index" : UNIT_LABEL[unit] || unit, tickFormat: unit === "currency" || unit === "dollars_per_person" ? (v) => "$" + fmt.money(v) : "~s", domain: unit === "percentage" && st.mode !== "index" ? undefined : undefined },
        color: { domain: group.map((s) => s.label), range: group.map((s, i) => PALETTE[(colorIndex - group.length + i) % PALETTE.length]), legend: true },
        marks,
      });
      const periods = [...new Set(rows.map((r) => r.period))].sort();
      const table = altTable(["Period", ...group.map((s) => s.label)], periods.map((p) => [rows.find((r) => r.period === p)?.label || p, ...group.map((s) => { const d = s.pts.find((x) => x.period === p); return d ? formatValue(s.m, d.value) + (d.note ? ` [${d.note}]` : "") : "—"; })]));
      body.append(figure(`${UNIT_LABEL[unit] || unit}${st.mode === "index" ? " (indexed)" : ""} · dashed and dotted = annual or survey values, hollow = estimate`, plot, table));
    }
    // Definitions under the charts.
    const defs = el("details", { class: "alt" }, el("summary", {}, "Definitions of the measures shown"));
    for (const code of selMeasures) { const m = measures[code]; defs.append(el("p", {}, el("b", {}, m.title), ` (${m.kind}, ${m.cadence.replace("_", " ")}, ${m.category}, since ${m.since.slice(0, 7)}): `, m.definition, " ", el("a", { href: `catalog.html#${code}` }, "catalog"))); }
    body.append(defs);
  }

  nodeInput.addEventListener("change", () => {
    const mm = nodeInput.value.match(/\(([A-Za-z0-9:_]+)\)\s*$/);
    const code = mm && nodes[mm[1]] ? mm[1] : Object.values(nodes).find((n) => n.name.toLowerCase() === nodeInput.value.trim().toLowerCase())?.code;
    if (code && selNodes.size < 6) { selNodes.add(code); nodeInput.value = ""; render(); }
  });
  measureSel.addEventListener("change", () => { if (measureSel.value && selMeasures.size < 6) { selMeasures.add(measureSel.value); measureSel.value = ""; render(); } });
  fromSel.addEventListener("change", render);
  modeSel.addEventListener("change", render);
  await render();
}
