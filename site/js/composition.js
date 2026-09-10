// Composition panel: one dimension at a time for the latest month, with the summary line.
import { el, fmt, disclosureBadge } from "./common.js";
import { mixChart } from "./charts.js";

const DIMS = {
  grade: "Grade", step_code: "Step or rate", age_bracket: "Age bracket", pay_band: "Pay band ($ thousands)",
  series_code: "Occupational series", appointment_type_code: "Appointment type", supervisory_code: "Supervisory status", work_schedule_code: "Work schedule",
};

export function compositionPanel(container, { mix, codes, lookups, state, onState }) {
  container.innerHTML = "";
  const panel = el("div", { class: "panel" }, el("h2", {}, "Composition"));
  if (!mix) { panel.append(el("p", { class: "muted" }, "No composition data for this unit.")); container.append(panel); return; }
  const s = mix._summary;
  const line = el("div", { class: "counters" },
    el("span", {}, "as of ", el("b", {}, fmt.month(s.month))), el("span", {}, el("b", {}, fmt.int(s.n)), " employees"),
    s.avg_pay ? el("span", {}, "average pay ", el("b", {}, "$" + fmt.int(s.avg_pay)), ` (${fmt.pct(s.pay_disclosed_share)} disclosed)`) : null,
    s.avg_los ? el("span", {}, "average service ", el("b", {}, s.avg_los + " yrs")) : null, disclosureBadge(s.disclosed_location_share));
  const sel = el("select", { "aria-label": "Dimension" });
  for (const [k, v] of Object.entries(DIMS)) if (mix[k]) sel.append(el("option", { value: k, selected: k === state.dim ? "" : null }, v));
  panel.append(line, el("div", { class: "controls" }, el("label", {}, "Show ", sel)));
  const body = el("div");
  panel.append(body);
  container.append(panel);
  function render() {
    const dim = sel.value;
    onState?.({ dim });
    body.innerHTML = "";
    const opts = { title: DIMS[dim] };
    if (dim === "grade") opts.order = (k) => (/^\d+$/.test(k) ? +k : 100 + k.charCodeAt(0));
    if (dim === "step_code") { opts.labels = lookups.step; opts.order = (k) => (/^\d+$/.test(k) ? +k : 100); }
    if (dim === "age_bracket") opts.order = (k) => parseInt(k) || 0;
    if (dim === "pay_band") { opts.order = (k) => (k === "R" ? 999 : +k); opts.labels = { R: "Redacted" }; }
    if (dim === "series_code") { opts.labels = lookups.series; opts.top = 15; }
    if (dim === "appointment_type_code") { opts.labels = codes.appointment_type; opts.top = 10; }
    if (dim === "supervisory_code") opts.labels = codes.supervisory_status;
    if (dim === "work_schedule_code") opts.labels = codes.work_schedule;
    const chart = mixChart(mix[dim], opts);
    if (chart) body.append(chart);
  }
  sel.addEventListener("change", render);
  render();
}
