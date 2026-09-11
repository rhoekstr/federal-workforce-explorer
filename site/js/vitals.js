// Vitals strip: eight measures for a node from data/slices/measures/current.json, with agency-level survey values
// inherited downward and labeled as such.
import { el, fmt, loadJSON } from "./common.js";

const VITALS = [
  ["headcount", "Headcount"],
  ["quit_rate", "Quit rate"],
  ["retirement_eligible_share", "Retirement-eligible"],
  ["first_year_attrition_rate", "First-year attrition"],
  ["span_of_control", "Span of control"],
  ["temp_share", "Temp and term"],
  ["fevs_engagement", "Engagement (FEVS)"],
  ["fevs_leave_outside", "Intend to leave gov (FEVS)"],
];

function fmtValue(m, v) {
  if (v == null) return "—";
  if (m.unit === "percentage") return v.toFixed(m.digits ?? 1) + "%";
  if (m.unit === "index" || m.unit === "ratio" || m.unit === "years") return v.toFixed(m.digits ?? 1);
  return fmt.int(v);
}

function periodLabel(t, p) {
  if (t === "month") return fmt.month(p.slice(0, 4) + p.slice(5, 7));
  if (t === "survey_year") return p.slice(0, 4) + " survey";
  if (t === "fiscal_year") { const y = +p.slice(0, 4), m = +p.slice(5, 7); return `FY${m >= 10 ? y + 1 : y}`; }
  return p.slice(0, 7);
}

export async function vitalsStrip(container, { code, nodes }) {
  const [current, catalog] = await Promise.all([loadJSON("data/slices/measures/current.json"), loadJSON("data/slices/measures/catalog.json")]);
  container.innerHTML = "";
  const strip = el("div", { class: "cards" });
  // Walk up to the agency for survey measures when the node itself has none.
  const chain = [];
  let cur = code;
  while (cur) { chain.push(cur); cur = nodes[cur]?.parent; }
  for (const [m, label] of VITALS) {
    const spec = catalog.measures[m];
    let node = null, v = null;
    // Only survey measures inherit from ancestors; workforce measures must be the unit's own.
    const inheritable = spec.cadence === "survey_year";
    for (const c of inheritable ? chain : chain.slice(0, 1)) { if (current[c]?.[m]) { node = c; v = current[c][m]; break; } }
    const inherited = node && node !== code;
    const card = el("div", { class: "card" }, el("div", { class: "label" }, label), el("div", { class: "value" }, fmtValue(spec, v?.v)),
      el("div", { class: "sub" }, v ? `${periodLabel(v.t, v.p)}${v.note ? ` · ${v.note}` : ""}${inherited ? ` · ${nodes[node].name}` : ""}` : "no value"));
    card.title = spec.definition;
    strip.append(card);
  }
  container.append(strip, el("p", { class: "muted" }, "Survey measures are agency-level and shown for the parent agency where a unit has none. ", el("a", { href: `explore.html?nodes=${encodeURIComponent(code)}&measures=quit_rate,retirement_eligible_share` }, "Explore this unit's measures"), " · ", el("a", { href: "catalog.html" }, "definitions")));
}
