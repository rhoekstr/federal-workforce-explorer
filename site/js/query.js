// DuckDB-WASM over the published fact parquet (HTTP range requests against GitHub Releases).
// Loaded lazily; nothing here runs until the user opens the filter panel.
import { el, fmt, altTable } from "./common.js";

const DUCKDB_CDN = "https://cdn.jsdelivr.net/npm/@duckdb/duckdb-wasm@1.29.0/+esm";
let dbPromise = null;

async function getDb() {
  if (!dbPromise) {
    dbPromise = (async () => {
      const duckdb = await import(DUCKDB_CDN);
      const bundles = duckdb.getJsDelivrBundles();
      const bundle = await duckdb.selectBundle(bundles);
      const workerUrl = URL.createObjectURL(new Blob([`importScripts("${bundle.mainWorker}");`], { type: "text/javascript" }));
      const worker = new Worker(workerUrl);
      const db = new duckdb.AsyncDuckDB(new duckdb.ConsoleLogger(duckdb.LogLevel.WARNING), worker);
      await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
      URL.revokeObjectURL(workerUrl);
      return db;
    })();
  }
  return dbPromise;
}

const DIMS = [
  ["series_code", "Occupational series", "series"],
  ["pay_plan_code", "Pay plan", "pay_plan"],
  ["grade", "Grade", null],
  ["step_code", "Step", "step"],
  ["pay_band", "Pay band ($10k)", null],
  ["supervisory_code", "Supervisory status", "codes:supervisory_status"],
  ["work_schedule_code", "Work schedule", "codes:work_schedule"],
  ["appointment_type_code", "Appointment type", "codes:appointment_type"],
  ["position_occupied_code", "Position occupied", "codes:position_occupied"],
  ["tenure_code", "Tenure", "codes:tenure"],
  ["age_bracket", "Age bracket", null],
  ["education_bracket", "Education", null],
  ["veteran", "Veteran", null],
  ["duty_station_code", "Duty station", "duty_station"],
];

function labelFor(dim, lookups, value) {
  const src = DIMS.find((d) => d[0] === dim)?.[2];
  if (!src) return value === "R" && dim === "pay_band" ? "Redacted" : value;
  if (src.startsWith("codes:")) return lookups.codes?.[src.slice(6)]?.[value]?.name || value;
  const t = lookups[src]?.[value];
  if (!t) return value;
  if (src === "duty_station") return `${t.name || value}${t.st ? ", " + t.st : ""}`;
  return t.name || value;
}

// Run one SQL statement against the published parquet and return plain rows.
export async function runQuery(sql) {
  const db = await getDb();
  const conn = await db.connect();
  try {
    const res = await conn.query(sql);
    return res.toArray().map((r) => Object.fromEntries(Object.entries(r.toJSON()).map(([k, v]) => [k, typeof v === "bigint" ? Number(v) : v])));
  } finally {
    await conn.close();
  }
}

// Build the filter panel for one org node. fileUrl is the Release URL of the fact parquet for the latest month.
export function filterPanel(container, { fileUrl, month, orgCode, lookups }) {
  container.innerHTML = "";
  const wrap = el("div", { class: "card" });
  wrap.append(el("h3", {}, `Ask the data (${fmt.month(month)})`));
  if (!fileUrl) {
    wrap.append(el("p", { class: "muted" }, "The fact table for this month is not published to a Release yet, so in-browser queries are unavailable."));
    container.append(wrap);
    return;
  }
  wrap.append(el("p", { class: "muted" }, "Runs DuckDB in your browser against the published parquet, over HTTP range requests. Nothing is sent anywhere else."));
  const controls = el("div", { class: "controls" });
  const dimSel = el("select", { "aria-label": "Break down by" });
  for (const [k, label] of DIMS) dimSel.append(el("option", { value: k }, label));
  const filterDim = el("select", { "aria-label": "Filter dimension" }, el("option", { value: "" }, "(no filter)"));
  for (const [k, label] of DIMS) filterDim.append(el("option", { value: k }, label));
  const filterVal = el("input", { type: "search", placeholder: "filter value (code)", "aria-label": "Filter value" });
  const run = el("button", { class: "primary", type: "button" }, "Run");
  controls.append(el("label", {}, "Break down by ", dimSel), el("label", {}, "Filter ", filterDim), filterVal, run);
  const out = el("div");
  wrap.append(controls, out);
  container.append(wrap);

  async function execute() {
    out.innerHTML = "";
    out.append(el("p", { class: "muted" }, "Loading DuckDB and reading the parquet…"));
    try {
      const db = await getDb();
      const conn = await db.connect();
      const dim = dimSel.value;
      const where = [`org_code LIKE '${orgCode.replace(/'/g, "''")}%'`];
      if (filterDim.value && filterVal.value.trim()) where.push(`${filterDim.value} = '${filterVal.value.trim().replace(/'/g, "''")}'`);
      const sql = `SELECT ${dim} AS k, sum(n)::BIGINT AS n, sum(pay_sum) / nullif(sum(pay_n), 0) AS avg_pay FROM read_parquet('${fileUrl}') WHERE ${where.join(" AND ")} GROUP BY 1 ORDER BY 2 DESC LIMIT 40`;
      const res = await conn.query(sql);
      const rows = res.toArray().map((r) => ({ k: r.k, n: Number(r.n), avg_pay: r.avg_pay == null ? null : Number(r.avg_pay) }));
      await conn.close();
      const total = rows.reduce((s, r) => s + r.n, 0);
      out.innerHTML = "";
      const t = el("table");
      t.append(el("thead", {}, el("tr", {}, el("th", {}, DIMS.find((d) => d[0] === dim)[1]), el("th", { class: "num" }, "Employees"), el("th", { class: "num" }, "Share"), el("th", { class: "num" }, "Avg pay (disclosed)"))));
      t.append(el("tbody", {}, rows.map((r) => el("tr", {}, el("td", {}, `${labelFor(dim, lookups, r.k)} `, el("span", { class: "muted" }, `(${r.k})`)), el("td", { class: "num" }, fmt.int(r.n)), el("td", { class: "num" }, fmt.pct(r.n / total, 1)), el("td", { class: "num" }, r.avg_pay ? "$" + fmt.int(r.avg_pay) : "—")))));
      out.append(el("div", { class: "table-wrap" }, t));
      out.append(el("p", { class: "muted" }, `Query: ${sql}`));
    } catch (err) {
      out.innerHTML = "";
      out.append(el("p", { class: "notice" }, `Query failed: ${err.message}`));
    }
  }
  run.addEventListener("click", execute);
}
