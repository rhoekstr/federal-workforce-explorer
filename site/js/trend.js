// Trend panel: one chart, configurable (metric × breakdown × compare × range). State lives in the URL.
import { el, fmt, loadJSON, altTable } from "./common.js";
import { figure } from "./charts.js";

const PALETTE = ["#005ea2", "#e07a3f", "#4c9a5b", "#8b5fbf", "#b3261e", "#6b7280", "#d4a017", "#2aa198", "#c2185b"];
export const METRICS = {
  headcount: { label: "Headcount", kind: "level" },
  net: { label: "Net change (accessions − separations)", kind: "flow" },
  accessions: { label: "Accessions", kind: "flow" },
  separations: { label: "Separations", kind: "flow" },
  sep_rate: { label: "Separation rate (% of prior-month headcount)", kind: "rate" },
  acc_rate: { label: "Accession rate (% of prior-month headcount)", kind: "rate" },
};
export const BREAKDOWNS = {
  none: "No breakdown",
  grade: "Grade", age_bracket: "Age bracket", supervisory_code: "Supervisory status", appointment_type_code: "Appointment type",
  pay_band: "Pay band", work_schedule_code: "Work schedule", series_code: "Occupational series", step_code: "Step",
};

function sumCats(cats, skip) { return Object.entries(cats || {}).filter(([c]) => c !== skip).reduce((s, [, n]) => s + n, 0); }

// Metric series for a node: [{month, value}] from its series slice.
export function metricSeries(series, metric, months) {
  const out = [];
  months.forEach((m, i) => {
    const prev = i ? series.headcount[months[i - 1]] : null;
    const acc = sumCats(series.accessions?.[m]), sep = sumCats(series.separations?.[m], "DRP");
    let v = null;
    if (metric === "headcount") v = series.headcount[m] ?? null;
    else if (metric === "net") v = acc - sep;
    else if (metric === "accessions") v = acc;
    else if (metric === "separations") v = sep;
    else if (metric === "sep_rate") v = prev ? (100 * sep) / prev : null;
    else if (metric === "acc_rate") v = prev ? (100 * acc) / prev : null;
    out.push({ month: m, date: fmt.monthDate(m), value: v });
  });
  return out;
}

function labelFor(dim, value, lookups, codes) {
  if (value === "_other") return "All other";
  if (value === "_blank") return "Not reported";
  if (dim === "pay_band") return value === "R" ? "Redacted" : `$${value}k`;
  if (dim === "series_code") return lookups.series?.[value]?.name || value;
  if (dim === "step_code") return lookups.step?.[value]?.name || value;
  const table = { supervisory_code: "supervisory_status", appointment_type_code: "appointment_type", work_schedule_code: "work_schedule" }[dim];
  if (table) return codes[table]?.[value]?.name || value;
  return value;
}

function rangeMonths(months, range) {
  if (range === "12") return months.slice(-13);
  if (/^\d{6}$/.test(range)) return months.filter((m) => m >= range);
  return months;
}

export function trendPanel(container, { code, name, tree, series, trend, codes, lookups, state, onState }) {
  const months = series.months;
  container.innerHTML = "";
  const panel = el("div", { class: "panel" }, el("h2", {}, "Trend"));
  const controls = el("div", { class: "controls" });
  const metricSel = el("select", { "aria-label": "Metric" });
  for (const [k, v] of Object.entries(METRICS)) metricSel.append(el("option", { value: k, selected: k === state.metric ? "" : null }, v.label));
  const bySel = el("select", { "aria-label": "Breakdown" });
  const available = trend ? Object.keys(trend.by) : [];
  for (const [k, v] of Object.entries(BREAKDOWNS)) if (k === "none" || available.includes(k)) bySel.append(el("option", { value: k, selected: k === state.by ? "" : null }, v));
  const modeSel = el("select", { "aria-label": "Breakdown mode" }, el("option", { value: "count" }, "counts"), el("option", { value: "share", selected: state.mode === "share" ? "" : null }, "shares"));
  const cmpInput = el("input", { type: "search", list: "cmp-units", placeholder: "compare with… (name)", "aria-label": "Compare with", size: 22 });
  const cmpList = el("datalist", { id: "cmp-units" });
  const idx = Object.values(tree.nodes).filter((n) => n.code !== code).sort((a, b) => (b.latest || 0) - (a.latest || 0)).slice(0, 600);
  for (const n of idx) cmpList.append(el("option", { value: `${n.name} (${n.code})` }));
  const rangeSel = el("select", { "aria-label": "Range" }, el("option", { value: "all" }, "all months"), el("option", { value: "12", selected: state.range === "12" ? "" : null }, "last 12 months"));
  for (const m of months.slice(0, -1)) rangeSel.append(el("option", { value: m, selected: state.range === m ? "" : null }, `since ${fmt.month(m)}`));
  const cmpChips = el("span");
  controls.append(el("label", {}, "Metric ", metricSel), el("label", {}, "Break down ", bySel), modeSel, el("label", {}, "Compare ", cmpInput), cmpList, cmpChips, el("label", {}, "Range ", rangeSel));
  panel.append(controls);
  const body = el("div");
  panel.append(body);
  if (!trend) panel.append(el("p", { class: "muted" }, "Breakdowns are precomputed for units with 500 or more employees; this unit shows totals only."));
  container.append(panel);

  const cmp = new Set((state.cmp || "").split(",").filter((c) => c && tree.nodes[c]));

  function readState() {
    return { metric: metricSel.value, by: bySel.value, mode: modeSel.value, cmp: [...cmp].join(","), range: rangeSel.value };
  }

  async function render() {
    const st = readState();
    onState?.(st);
    modeSel.hidden = st.by === "none";
    cmpChips.innerHTML = "";
    for (const c of cmp) cmpChips.append(el("button", { type: "button", class: "badge", title: "remove", onclick: () => { cmp.delete(c); render(); } }, `${tree.nodes[c].name} ×`), " ");
    const ms = rangeMonths(months, st.range);
    body.innerHTML = "";
    const width = Math.min(1100, Math.max(300, (container.clientWidth || document.querySelector("main")?.clientWidth || 800) - 30));
    const metric = METRICS[st.metric];
    const yLabel = metric.kind === "rate" ? "%" : metric.label;

    if (st.by !== "none" && trend && st.metric === "headcount") {
      const rows = [];
      const values = trend.by[st.by];
      for (const [v, ser] of Object.entries(values)) for (const m of ms) if (ser[m] != null) rows.push({ month: m, date: fmt.monthDate(m), key: v, label: labelFor(st.by, v, lookups, codes), n: ser[m] });
      const order = Object.keys(values).map((v) => labelFor(st.by, v, lookups, codes));
      const plot = Plot.plot({
        width, height: 320, marginLeft: 56, x: { type: "utc", label: null, ticks: d3.utcMonth.every(ms.length > 14 ? 3 : 1), tickFormat: d3.utcFormat("%b %y") },
        y: { grid: true, label: st.mode === "share" ? "Share of headcount" : "Employees", tickFormat: st.mode === "share" ? ".0%" : "~s", percent: false },
        color: { domain: order, range: PALETTE, legend: true },
        marks: [Plot.areaY(rows, Plot.stackY({ offset: st.mode === "share" ? "normalize" : null }, { x: "date", y: "n", fill: "label", order, title: (d) => `${fmt.month(d.month)} ${d.label}: ${fmt.int(d.n)}` })), Plot.ruleY([0])],
      });
      const table = altTable(["Month", ...order], ms.map((m) => [fmt.month(m), ...Object.keys(values).map((v) => fmt.int(values[v][m] ?? 0))]));
      body.append(figure(`${name}: headcount by ${BREAKDOWNS[st.by].toLowerCase()}${st.mode === "share" ? " (shares)" : ""}`, plot, table));
      return;
    }

    const lines = [{ code, name, series }];
    for (const c of cmp) lines.push({ code: c, name: tree.nodes[c].name, series: await loadJSON(`data/slices/series/${c}.json`).catch(() => null) });
    const indexed = cmp.size > 0 && metric.kind === "level";
    const rows = [];
    for (const L of lines) {
      if (!L.series) continue;
      const ser = metricSeries(L.series, st.metric, months).filter((d) => ms.includes(d.month) && d.value != null);
      const base = indexed ? ser[0]?.value || 1 : 1;
      for (const d of ser) rows.push({ ...d, node: L.name, value: indexed ? (100 * d.value) / base : d.value });
    }
    if (!rows.length) { body.append(el("p", { class: "muted" }, "Nothing to plot for this range.")); return; }
    const plot = Plot.plot({
      width, height: 300, marginLeft: 56, x: { type: "utc", label: null, ticks: d3.utcMonth.every(ms.length > 14 ? 3 : 1), tickFormat: d3.utcFormat("%b %y") },
      y: { grid: true, label: indexed ? `Index (100 = ${fmt.month(ms[0])})` : yLabel, tickFormat: metric.kind === "rate" || indexed ? ".1f" : "~s", domain: metric.kind === "level" && !indexed ? [0, d3.max(rows, (d) => d.value) * 1.08] : undefined },
      color: { domain: lines.map((L) => L.name), range: PALETTE, legend: lines.length > 1 },
      marks: [Plot.ruleY([0]), Plot.lineY(rows, { x: "date", y: "value", stroke: "node", strokeWidth: 2 }), Plot.dot(rows, { x: "date", y: "value", fill: "node", r: 2.5, title: (d) => `${d.node}, ${fmt.month(d.month)}: ${metric.kind === "rate" || indexed ? d.value.toFixed(1) : fmt.int(d.value)}` })],
    });
    const table = altTable(["Month", ...lines.map((L) => L.name)], ms.map((m) => [fmt.month(m), ...lines.map((L) => { const r = rows.find((x) => x.month === m && x.node === L.name); return r ? (metric.kind === "rate" || indexed ? r.value.toFixed(1) : fmt.int(r.value)) : "—"; })]));
    body.append(figure(`${name}: ${metric.label.toLowerCase()}${indexed ? ", indexed" : ""}`, plot, table));
  }

  for (const c of [metricSel, bySel, modeSel, rangeSel]) c.addEventListener("change", render);
  cmpInput.addEventListener("change", () => {
    const m = cmpInput.value.match(/\(([A-Z0-9:_]+)\)\s*$/);
    const hit = m && tree.nodes[m[1]] ? m[1] : idx.find((n) => n.name.toLowerCase() === cmpInput.value.trim().toLowerCase())?.code;
    if (hit && cmp.size < 3) { cmp.add(hit); cmpInput.value = ""; render(); }
  });
  render();
  return { render };
}
