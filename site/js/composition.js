// Composition: one dimension of a unit's headcount at the latest month, from the measures table.
import { el, fmt, disclosureBadge, altTable } from "./common.js";
import { figure } from "./charts.js";
import * as M from "./measures.js";

const BAR = "#005ea2";

export async function compositionPanel(container, { code, name, state, onState }) {
  container.innerHTML = "";
  const panel = el("div", { class: "panel" }, el("h2", {}, "Composition"));
  container.append(panel);
  const body = el("div", {}, el("p", { class: "muted" }, "Loading…"));

  const [dims, labels, snap] = await Promise.all([M.dimsNow(code), M.dimLabels(), M.current(code)]);
  const dimSpecs = M.dimensions();
  if (!dims) {
    panel.append(el("p", { class: "muted" }, "No composition data for this unit."));
    return;
  }

  const summaryMeasures = [["headcount", null], ["avg_pay", "pay_disclosed_share"], ["avg_service_years", null], ["location_disclosed_share", null]];
  const line = el("div", { class: "counters" });
  for (const [m, qual] of summaryMeasures) {
    const v = snap[m];
    if (!v) continue;
    const spec = M.spec(m);
    if (m === "location_disclosed_share") { line.append(disclosureBadge(v.v / 100)); continue; }
    line.append(el("span", {}, M.defineLink(m, spec.title.toLowerCase()), " ", el("b", {}, M.formatValue(spec, v.v)),
      qual && snap[qual] ? el("span", { class: "muted" }, ` (${M.formatValue(M.spec(qual), snap[qual].v)} disclosed)`) : null));
  }
  const asOf = snap.headcount?.p;
  if (asOf) line.prepend(el("span", {}, "as of ", el("b", {}, M.periodLabel("month", asOf))));
  panel.append(line);

  const sel = el("select", { "aria-label": "Dimension" });
  for (const d of Object.keys(dims)) sel.append(el("option", { value: d, selected: d === state.dim ? "" : null }, dimSpecs[d]?.title || d));
  panel.append(el("div", { class: "controls" }, el("label", {}, "Show ", sel)), body);

  function render() {
    const dim = sel.value;
    onState?.({ dim });
    body.innerHTML = "";
    const values = dims[dim] || {};
    const order = M.dimOrder(dim);
    let rows = Object.entries(values).map(([k, n]) => ({ k, label: M.dimValueLabel(dim, k, labels), n }));
    rows.sort(order ? (a, b) => order(a.k) - order(b.k) : (a, b) => b.n - a.n);
    const total = rows.reduce((s, r) => s + r.n, 0) || 1;
    const width = Math.min(620, Math.max(300, (container.clientWidth || 700) - 30));
    const plot = Plot.plot({
      width, height: 22 * rows.length + 40, marginLeft: 180,
      x: { label: null, tickFormat: "~s", grid: true },
      y: { label: null, domain: rows.map((r) => r.label) },
      marks: [
        Plot.barX(rows, { y: "label", x: "n", fill: BAR, title: (d) => `${d.label}: ${fmt.int(d.n)} (${fmt.pct(d.n / total)})` }),
        Plot.text(rows, { y: "label", x: "n", text: (d) => fmt.pct(d.n / total), dx: 4, textAnchor: "start", fontSize: 10 }),
      ],
    });
    body.append(figure(el("span", {}, `${name}: `, M.defineLink("headcount"), ` by ${(dimSpecs[dim]?.title || dim).toLowerCase()}, ${asOf ? M.periodLabel("month", asOf) : "latest month"}`),
      plot, altTable([dimSpecs[dim]?.title || dim, "Employees", "Share"], rows.map((r) => [r.label, fmt.int(r.n), fmt.pct(r.n / total)]))));
  }
  sel.addEventListener("change", render);
  render();
}
