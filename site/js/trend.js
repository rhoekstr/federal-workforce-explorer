// Trend panel: one measure over time for one unit, optionally broken down by a dimension or compared
// with other units. Every value comes from the measures table; the panel does no arithmetic of its own.
import { el, fmt, altTable } from "./common.js";
import { figure } from "./charts.js";
import * as M from "./measures.js";


const PALETTE = ["#005ea2", "#e07a3f", "#4c9a5b", "#8b5fbf", "#b3261e", "#6b7280", "#d4a017", "#2aa198", "#c2185b"];
const RANGES = [["all", "all history"], ["60", "last 5 years"], ["24", "last 2 years"], ["12", "last 12 months"]];

function cutoff(range, axis) {
  if (range === "all" || !axis.length) return null;
  const n = +range;
  return axis[Math.max(0, axis.length - n - 1)];
}

export async function trendPanel(container, { code, name, state, onState }) {
  container.innerHTML = "";
  const nodes = M.nodes();
  const panel = el("div", { class: "panel" }, el("h2", {}, "Trend"));
  const controls = el("div", { class: "controls" });

  const measureSel = el("select", { "aria-label": "Measure" });
  for (const [fam, test] of M.FAMILIES) {
    const og = el("optgroup", { label: fam });
    for (const m of M.shownMeasures(test)) og.append(el("option", { value: m.code, selected: m.code === state.measure ? "" : null }, m.title));
    if (og.children.length) measureSel.append(og);
  }
  const bySel = el("select", { "aria-label": "Breakdown" });
  const modeSel = el("select", { "aria-label": "Breakdown mode" }, el("option", { value: "count" }, "counts"), el("option", { value: "share", selected: state.mode === "share" ? "" : null }, "shares"));
  const cmpInput = el("input", { type: "search", list: "trend-units", placeholder: "compare with…", "aria-label": "Compare with", size: 20 });
  const cmpList = el("datalist", { id: "trend-units" });
  const index = Object.values(nodes).filter((n) => n.code !== code).slice(0, 1200);
  for (const n of index) cmpList.append(el("option", { value: `${n.name} (${n.code})` }));
  const cmpChips = el("span");
  const rangeSel = el("select", { "aria-label": "Range" }, ...RANGES.map(([v, l]) => el("option", { value: v, selected: (state.range || "all") === v ? "" : null }, l)));
  controls.append(el("label", {}, "Measure ", measureSel), el("label", {}, "Break down ", bySel), modeSel,
    el("label", {}, "Compare ", cmpInput), cmpList, cmpChips, el("label", {}, "Range ", rangeSel));
  panel.append(controls);
  const body = el("div");
  panel.append(body);
  container.append(panel);

  const cmp = new Set((state.cmp || "").split(",").filter((c) => c && nodes[c]));
  const labels = await M.dimLabels();

  async function refreshBreakdowns() {
    const measure = measureSel.value;
    const slice = await M.loadNode(code);
    const available = Object.keys(slice.dims?.[measure] || {});
    bySel.innerHTML = "";
    bySel.append(el("option", { value: "none" }, "no breakdown"));
    for (const d of available) bySel.append(el("option", { value: d, selected: d === state.by ? "" : null }, M.dimensions()[d]?.title || d));
    bySel.disabled = !available.length;
    bySel.title = available.length ? "" : "Breakdowns over time are stored for agencies and above";
  }

  async function render() {
    const st = { measure: measureSel.value, by: bySel.value || "none", mode: modeSel.value, cmp: [...cmp].join(","), range: rangeSel.value };
    onState?.(st);
    modeSel.hidden = st.by === "none";
    cmpChips.innerHTML = "";
    for (const c of cmp) cmpChips.append(el("button", { type: "button", class: "badge", title: "remove", onclick: () => { cmp.delete(c); render(); } }, `${nodes[c].name} ×`), " ");
    body.innerHTML = "";
    body.append(el("p", { class: "muted" }, "Loading…"));

    const m = M.spec(st.measure);
    const axis = M.periodAxis(m.cadence);
    const from = cutoff(st.range, axis);
    const width = Math.min(1100, Math.max(300, (container.clientWidth || 800) - 30));

    if (st.by !== "none") {
      const dims = await M.dimSeries(code, st.measure, st.by);
      body.innerHTML = "";
      if (!dims) { body.append(el("p", { class: "muted" }, "No breakdown for this unit.")); return; }
      const order = M.dimOrder(st.by);
      const keys = Object.keys(dims).sort(order ? (a, b) => order(a) - order(b) : (a, b) => (dims[b].at(-1)?.value || 0) - (dims[a].at(-1)?.value || 0));
      const rows = [];
      for (const k of keys) for (const d of dims[k]) {
        if (from && d.period < from) continue;
        rows.push({ ...d, key: k, series: M.dimValueLabel(st.by, k, labels) });
      }
      const domain = keys.map((k) => M.dimValueLabel(st.by, k, labels));
      const plot = Plot.plot({
        width, height: 320, marginLeft: 60,
        x: { type: "utc", label: null },
        y: { grid: true, label: st.mode === "share" ? "Share" : m.title, tickFormat: st.mode === "share" ? ".0%" : "~s" },
        color: { domain, range: PALETTE, legend: true },
        marks: [Plot.areaY(rows, Plot.stackY({ offset: st.mode === "share" ? "normalize" : null }, { x: "date", y: "value", fill: "series", order: domain, title: (d) => `${d.label} ${d.series}: ${fmt.int(d.value)}` })), Plot.ruleY([0])],
      });
      const periods = [...new Set(rows.map((r) => r.period))].sort();
      const table = altTable(["Period", ...domain], periods.map((p) => [rows.find((r) => r.period === p)?.label || p, ...keys.map((k) => fmt.int(dims[k].find((d) => d.period === p)?.value ?? 0))]));
      body.append(figure(el("span", {}, `${name}: `, M.defineLink(st.measure), ` by ${(M.dimensions()[st.by]?.title || st.by).toLowerCase()}`), plot, table));
      return;
    }

    const lines = [];
    for (const node of [code, ...cmp]) {
      const pts = (await M.series(node, st.measure)).filter((d) => !from || d.period >= from);
      if (pts.length) lines.push({ node, name: nodes[node]?.name || node, pts });
    }
    body.innerHTML = "";
    if (!lines.length) {
      body.append(el("p", { class: "muted" }, "No values for this measure and unit. ", M.defineLink(st.measure, "What this measure covers")));
      return;
    }
    const indexed = cmp.size > 0 && (m.unit === "people" || m.unit === "count" || m.unit === "currency");
    const rows = [];
    for (const L of lines) {
      const base = indexed ? L.pts[0].value || 1 : 1;
      for (const d of L.pts) rows.push({ ...d, series: L.name, value: indexed ? (100 * d.value) / base : d.value });
    }
    const fine = m.cadence === "month" || m.cadence === "quarter";
    const marks = [Plot.ruleY([0]), Plot.lineY(rows, { x: "date", y: "value", stroke: "series", strokeWidth: 2, strokeDasharray: fine ? null : "4 3" })];
    marks.push(Plot.dot(rows, { x: "date", y: "value", fill: (d) => (d.note === "estimate" ? "var(--card)" : undefined), stroke: "series", r: fine && rows.length > 60 ? 0 : 3, title: (d) => `${d.series}\n${d.label}: ${indexed ? d.value.toFixed(1) : M.formatValue(m, d.value)}${d.n != null ? ` (n ${fmt.int(d.n)})` : ""}${d.note ? ` [${d.note}]` : ""}` }));
    const plot = Plot.plot({
      width, height: 300, marginLeft: 64,
      x: { type: "utc", label: null },
      y: { grid: true, label: indexed ? `Index (100 = ${lines[0].pts[0].label})` : m.title, tickFormat: m.unit === "currency" || m.unit === "dollars_per_person" ? (v) => "$" + fmt.money(v) : "~s", domain: m.unit === "people" && !indexed ? [0, d3.max(rows, (d) => d.value) * 1.08] : undefined },
      color: { domain: lines.map((L) => L.name), range: PALETTE, legend: lines.length > 1 },
      marks,
    });
    const periods = [...new Set(rows.map((r) => r.period))].sort();
    const table = altTable(["Period", ...lines.map((L) => L.name)], periods.map((p) => {
      const any = rows.find((r) => r.period === p);
      return [any?.label || p, ...lines.map((L) => { const d = L.pts.find((x) => x.period === p); return d ? M.formatValue(m, d.value) + (d.note ? ` [${d.note}]` : "") : "—"; })];
    }));
    body.append(figure(el("span", {}, `${name}: `, M.defineLink(st.measure), indexed ? ", indexed" : ""), plot, table));
  }

  measureSel.addEventListener("change", async () => { await refreshBreakdowns(); render(); });
  for (const c of [bySel, modeSel, rangeSel]) c.addEventListener("change", render);
  cmpInput.addEventListener("change", () => {
    const mm = cmpInput.value.match(/\(([A-Za-z0-9:_]+)\)\s*$/);
    const hit = (mm && nodes[mm[1]] && mm[1]) || index.find((n) => n.name.toLowerCase() === cmpInput.value.trim().toLowerCase())?.code;
    if (hit && cmp.size < 4) { cmp.add(hit); cmpInput.value = ""; render(); }
  });
  await refreshBreakdowns();
  if (state.by && [...bySel.options].some((o) => o.value === state.by)) bySel.value = state.by;
  await render();
}
