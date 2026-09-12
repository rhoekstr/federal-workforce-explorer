// One way to get a number: every figure on the site resolves to a catalog measure and comes from here.
// Node slices hold flat series positionally against a shared period axis; sub-elements fall back to a
// DuckDB query over the same-origin measures parquet.
import { loadJSON, fmt, el } from "./common.js";

let ctx = null;

export async function init() {
  if (!ctx) {
    const [catalog, nodesDoc, periods, manifest] = await Promise.all([
      loadJSON("data/slices/measures/catalog.json"),
      loadJSON("data/slices/measures/nodes.json"),
      loadJSON("data/slices/measures/periods.json"),
      loadJSON("data/manifest.json"),
    ]);
    ctx = { measures: catalog.measures, dimensions: catalog.dimensions, nodes: nodesDoc.nodes, periods, manifest };
  }
  return ctx;
}

export function spec(code) {
  return ctx.measures[code];
}

export function shownMeasures(filter = () => true) {
  return Object.entries(ctx.measures)
    .filter(([, m]) => m.display !== false)
    .map(([code, m]) => ({ code, ...m }))
    .filter(filter);
}

export const FAMILIES = [
  ["Workforce", (m) => m.cadence === "month"],
  ["Money", (m) => m.cadence === "quarter"],
  ["Annual and survey", (m) => m.cadence === "fiscal_year" || m.cadence === "survey_year"],
];

// ---- periods -------------------------------------------------------------

export function periodDate(p) {
  return new Date(p + "T00:00:00Z");
}

export function periodLabel(t, p) {
  const y = +p.slice(0, 4), m = +p.slice(5, 7);
  if (t === "month") return fmt.month(p.slice(0, 4) + p.slice(5, 7));
  if (t === "quarter") { const fy = m >= 10 ? y + 1 : y; const q = m >= 10 ? 1 : m <= 3 ? 2 : m <= 6 ? 3 : 4; return `FY${fy} Q${q}`; }
  if (t === "fiscal_year") return `FY${m >= 10 ? y + 1 : y}`;
  return String(y);
}

export function formatValue(m, v) {
  if (v == null) return "—";
  if (!m) return fmt.int(v);
  if (m.unit === "percentage") return v.toFixed(m.digits ?? 1) + "%";
  if (m.unit === "currency" || m.unit === "dollars_per_person") return fmt.dollars(v);
  if (m.unit === "ratio" || m.unit === "years" || m.unit === "index") return v.toFixed(m.digits ?? 1);
  return fmt.int(v);
}

// ---- series --------------------------------------------------------------

/** Expand a packed series {t, i, v, n?, z?} into [{period, date, value, n, note, label}]. */
export function unpack(series) {
  if (!series || !series.v) return [];
  const axis = ctx.periods[series.t] || [];
  const out = [];
  for (let k = 0; k < series.v.length; k++) {
    const v = series.v[k];
    if (v == null) continue;
    const p = axis[series.i + k];
    if (!p) continue;
    out.push({ period: p, date: periodDate(p), value: v, n: series.n?.[k] ?? null, note: series.z?.[String(k)] ?? null, label: periodLabel(series.t, p), t: series.t });
  }
  return out;
}

const nodeCache = new Map();

/** A node's slice: {measures, dims, dims_now}. Sub-elements carry dims_now only; their series come from the parquet. */
export async function loadNode(code) {
  if (!nodeCache.has(code)) {
    const file = ctx.nodes[code]?.kind === "group" ? `group-${code}.json` : `${code}.json`;
    nodeCache.set(code, loadJSON(`data/slices/measures/${file}`).catch(() => ({ node: code })));
  }
  return nodeCache.get(code);
}

function parquetUrl() {
  const rel = ctx.manifest?.measures?.site_url || "data/measures.parquet";
  return new URL(rel, location.href).href;
}

const parquetCache = new Map();

/** Every flat series for one node, read from the parquet in one query. Used for sub-elements. */
export async function loadNodeFromParquet(code) {
  if (!parquetCache.has(code)) {
    parquetCache.set(code, (async () => {
      const { runQuery } = await import("./query.js");
      const sql = `SELECT measure, period_type, period_start, value, n, notation FROM read_parquet('${parquetUrl()}')
                   WHERE node = '${code.replace(/'/g, "''")}' AND dim IS NULL AND value IS NOT NULL ORDER BY measure, period_start`;
      const rows = await Promise.race([
        runQuery(sql),
        new Promise((_, rej) => setTimeout(() => rej(new Error("the in-browser query timed out")), 90000)),
      ]);
      const measures = {};
      for (const r of rows) {
        const axis = ctx.periods[r.period_type] || [];
        const i = axis.indexOf(r.period_start);
        if (i < 0) continue;
        const m = (measures[r.measure] ||= { t: r.period_type, i, v: [], n: [], z: {} });
        const k = i - m.i;
        while (m.v.length < k) { m.v.push(null); m.n.push(null); }
        m.v[k] = Number(r.value);
        m.n[k] = r.n == null ? null : Number(r.n);
        if (r.notation) m.z[String(k)] = r.notation;
      }
      return { node: code, measures };
    })());
  }
  return parquetCache.get(code);
}

/** Flat series for one node and measure, from the slice when present and the parquet otherwise. */
export async function series(code, measure) {
  const slice = await loadNode(code);
  if (slice.measures?.[measure]) return unpack(slice.measures[measure]);
  if (slice.measures) return [];                       // slice exists and this measure is genuinely absent
  const fromParquet = await loadNodeFromParquet(code);
  return unpack(fromParquet.measures[measure]);
}

/** True when this node's flat series need the parquet (slower first paint). */
export async function needsQuery(code) {
  const slice = await loadNode(code);
  return !slice.measures;
}

/** Dimension series for the trend breakdown: {dim_value: [{period, value}]}. Agency level and above. */
export async function dimSeries(code, measure, dim) {
  const slice = await loadNode(code);
  const packed = slice.dims?.[measure]?.[dim];
  if (!packed) return null;
  return Object.fromEntries(Object.entries(packed).map(([k, s]) => [k, unpack(s)]));
}

/** Every dimension at the latest period, for Composition. Available at every level. */
export async function dimsNow(code, measure = "headcount") {
  const slice = await loadNode(code);
  return slice.dims_now?.[measure] || null;
}

export async function current(code) {
  const snap = await loadJSON("data/slices/measures/current.json");
  return snap[code] || {};
}

// ---- dimension labels ----------------------------------------------------

let labelCtx = null;

export async function dimLabels() {
  if (!labelCtx) {
    const [codes, series_lk, step_lk] = await Promise.all([
      loadJSON("data/lookups/codes.json"),
      loadJSON("data/lookups/series.json").catch(() => ({})),
      loadJSON("data/lookups/step.json").catch(() => ({})),
    ]);
    labelCtx = { codes, series: series_lk, step: step_lk };
  }
  return labelCtx;
}

export function dimValueLabel(dim, value, labels) {
  if (value === "_other") return "All other";
  if (value === "_blank") return "Not reported";
  if (dim === "pay_band") return value === "R" ? "Redacted" : `$${value}k`;
  if (dim === "series") return labels.series?.[value]?.name || value;
  if (dim === "step") return labels.step?.[value]?.name || value;
  const table = { supervisory: "supervisory_status", appointment_type: "appointment_type", work_schedule: "work_schedule", separation_category: "separation_category", accession_category: "accession_category" }[dim];
  if (table) return labels.codes?.[table]?.[value]?.name || value;
  return value;
}

export function dimOrder(dim) {
  if (dim === "grade" || dim === "step") return (k) => (/^\d+$/.test(k) ? +k : 100 + (k.charCodeAt(0) || 0));
  if (dim === "age_bracket") return (k) => parseInt(k) || 0;
  if (dim === "pay_band") return (k) => (k === "R" ? 9999 : +k);
  return null;
}

/** A definition link for any measure: the catalog is one click from every number. */
export function defineLink(code, text) {
  const m = ctx.measures[code];
  return el("a", { href: `catalog.html#${code}`, class: "define", title: m?.definition || "" }, text ?? m?.title ?? code);
}

/** A change in a measure's own units: points for percentages, people for counts, dollars for money. */
export function formatDelta(m, d) {
  if (d == null) return "—";
  const sign = d > 0 ? "+" : "";
  if (!m) return sign + fmt.int(d);
  if (m.unit === "percentage") return `${sign}${d.toFixed(Math.max(1, m.digits ?? 1))} pts`;
  if (m.unit === "index") return `${sign}${d.toFixed(1)} pts`;
  if (m.unit === "currency" || m.unit === "dollars_per_person") return (d < 0 ? "−" : "+") + fmt.dollars(Math.abs(d)).slice(1);
  if (m.unit === "ratio" || m.unit === "years") return `${sign}${d.toFixed(1)}`;
  return sign + fmt.int(d);
}

export function nodes() { return ctx.nodes; }
export function dimensions() { return ctx.dimensions || {}; }
export function manifest() { return ctx.manifest; }
export function periodAxis(t) { return ctx.periods[t] || []; }
