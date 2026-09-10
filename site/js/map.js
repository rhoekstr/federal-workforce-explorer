// Map panel: county choropleth of where a unit's employees are, honest about what OPM withholds.
// Precomputed geo slices for government and agencies; sub-elements are computed from the parquet in the browser.
import { el, fmt, loadJSON } from "./common.js";
import { figure } from "./charts.js";

let topoPromise = null;
function topo() {
  if (!topoPromise) topoPromise = loadJSON("data/geo/counties-10m.json");
  return topoPromise;
}

// Same rules as pipeline/geo.py classify().
export function classify(ds) {
  if (!ds) return "invalid";
  if (ds.name === "Not disclosed") return "nds";
  if (ds.cc && ds.cc !== "US") return "abroad";
  if (ds.fips && ds.fips.length === 5 && /^\d{5}$/.test(ds.fips) && ds.st && ds.st !== "*") return "county";
  if (ds.cc === "US" && ds.name && ds.name !== "INVALID") return "territory";
  return "invalid";
}

// Build a geo object from [duty_station_code, n] rows (browser path for sub-elements).
export function geoFromRows(rows, duty, month) {
  const g = { month, n: 0, disclosed: 0, abroad: 0, territory: 0, invalid: 0, counties: {}, states: {} };
  for (const [code, n] of rows) {
    g.n += n;
    const b = code === "NDS" ? "nds" : classify(duty[code]);
    if (b === "county") { g.disclosed += n; const d = duty[code]; g.counties[d.fips] = (g.counties[d.fips] || 0) + n; g.states[d.st] = (g.states[d.st] || 0) + n; }
    else if (b === "abroad") { g.disclosed += n; g.abroad += n; }
    else if (b === "territory") { g.disclosed += n; g.territory += n; }
    else if (b === "invalid") g.invalid += n;
  }
  g.disclosed_share = g.n ? g.disclosed / g.n : null;
  return g;
}

export async function mapPanel(container, { code, name, geo, loadGeo, state, onState }) {
  container.innerHTML = "";
  const panel = el("div", { class: "panel" }, el("h2", {}, "Where they work"));
  const levelSel = el("select", { "aria-label": "Map level" }, el("option", { value: "county" }, "counties"), el("option", { value: "state", selected: state.level === "state" ? "" : null }, "states"));
  panel.append(el("div", { class: "controls" }, el("label", {}, "Show ", levelSel)));
  const body = el("div");
  panel.append(body);
  container.append(panel);
  body.append(el("p", { class: "muted" }, geo ? "Drawing…" : "Reading the parquet in your browser…"));
  let g = geo;
  try {
    if (!g) g = await loadGeo();
  } catch (err) {
    body.innerHTML = "";
    body.append(el("p", { class: "notice" }, `Could not compute the map: ${err.message}`));
    return;
  }
  const t = await topo();
  const counties = topojson.feature(t, t.objects.counties);
  const states = topojson.feature(t, t.objects.states);
  const stateMesh = topojson.mesh(t, t.objects.states, (a, b) => a !== b);
  const nation = topojson.mesh(t, t.objects.nation);
  const stateNameByFips = Object.fromEntries(states.features.map((f) => [f.id, f.properties.name]));
  const stateFipsByAbbr = {};
  for (const f of counties.features) { const st = f.id.slice(0, 2); if (!stateFipsByAbbr[st]) stateFipsByAbbr[st] = st; }

  function render() {
    const level = levelSel.value;
    onState?.({ level });
    body.innerHTML = "";
    const nds = g.n - g.disclosed - g.invalid;
    const counters = el("div", { class: "counters" },
      el("span", {}, el("b", {}, fmt.pct(g.disclosed_share)), ` of ${name}'s ${fmt.int(g.n)} employees have a disclosed location; the map shows those.`),
      el("span", {}, "not disclosed ", el("b", {}, fmt.int(nds))), el("span", {}, "outside the U.S. ", el("b", {}, fmt.int(g.abroad))), el("span", {}, "territories ", el("b", {}, fmt.int(g.territory))));
    body.append(counters);
    if (!g.disclosed) {
      body.append(el("p", { class: "notice" }, "OPM withholds every duty station for this unit, so there is nothing to map."));
      return;
    }
    const width = Math.min(1000, Math.max(300, (container.clientWidth || document.querySelector("main")?.clientWidth || 800) - 30));
    const values = level === "county" ? g.counties : Object.fromEntries(Object.entries(g.states).map(([abbr, n]) => [abbr, n]));
    let features, key, label;
    if (level === "county") { features = counties.features; key = (f) => f.id; label = (f) => `${f.properties.name}, ${stateNameByFips[f.id.slice(0, 2)] || ""}`; }
    else {
      // states keyed by abbreviation in the slice; map via a small FIPS→abbr table built from county lookups is not available here,
      // so use the state name list from the TopoJSON and the abbreviation table below.
      features = states.features; key = (f) => STATE_ABBR[f.properties.name] || f.id; label = (f) => f.properties.name;
    }
    const max = Math.max(...Object.values(values), 1);
    const plot = Plot.plot({
      width, height: width * 0.62, projection: "albers-usa",
      color: { type: "log", domain: [1, max], scheme: "blues", legend: true, label: "Employees", tickFormat: "~s" },
      marks: [
        Plot.geo(features, { fill: (f) => values[key(f)] || null, stroke: level === "county" ? null : "var(--line)", title: (f) => `${label(f)}: ${fmt.int(values[key(f)] || 0)}` }),
        level === "county" ? Plot.geo(stateMesh, { stroke: "var(--fg)", strokeOpacity: 0.35, strokeWidth: 0.6 }) : null,
        Plot.geo(nation, { stroke: "var(--fg)", strokeOpacity: 0.5, strokeWidth: 0.8 }),
      ].filter(Boolean),
    });
    const top = Object.entries(values).sort((a, b) => b[1] - a[1]).slice(0, 15);
    const rows = top.map(([k, n]) => [level === "county" ? (label(counties.features.find((f) => f.id === k) || { properties: { name: k }, id: k })) : (Object.entries(STATE_ABBR).find(([, a]) => a === k)?.[0] || k), fmt.int(n), fmt.pct(n / g.disclosed)]);
    body.append(figure(`${name}: employees by ${level} (${fmt.month(g.month)}, log color scale)`, plot, el("details", { class: "alt" }, el("summary", {}, `Top ${top.length} ${level === "county" ? "counties" : "states"}`), el("div", { class: "table-wrap" }, (() => { const tb = el("table"); tb.append(el("thead", {}, el("tr", {}, [level === "county" ? "County" : "State", "Employees", "Share of located"].map((h) => el("th", {}, h))))); tb.append(el("tbody", {}, rows.map((r) => el("tr", {}, r.map((v) => el("td", {}, v)))))); return tb; })()))));
  }
  levelSel.addEventListener("change", render);
  render();
}

const STATE_ABBR = { Alabama: "AL", Alaska: "AK", Arizona: "AZ", Arkansas: "AR", California: "CA", Colorado: "CO", Connecticut: "CT", Delaware: "DE", "District of Columbia": "DC", Florida: "FL", Georgia: "GA", Hawaii: "HI", Idaho: "ID", Illinois: "IL", Indiana: "IN", Iowa: "IA", Kansas: "KS", Kentucky: "KY", Louisiana: "LA", Maine: "ME", Maryland: "MD", Massachusetts: "MA", Michigan: "MI", Minnesota: "MN", Mississippi: "MS", Missouri: "MO", Montana: "MT", Nebraska: "NE", Nevada: "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", Ohio: "OH", Oklahoma: "OK", Oregon: "OR", Pennsylvania: "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", Tennessee: "TN", Texas: "TX", Utah: "UT", Vermont: "VT", Virginia: "VA", Washington: "WA", "West Virginia": "WV", Wisconsin: "WI", Wyoming: "WY", "Puerto Rico": "PR" };
