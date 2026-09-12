// Leadership: the PLUM roster for a unit, and the person card behind a name.
// PLUM is a statutory public list of office-holders. It is shown as published and never joined to workforce
// records, so a name here never acquires an age, a salary band, or a service date from the employment files.
import { el, fmt, loadJSON } from "./common.js";

let directoryPromise = null;
let timelinesPromise = null;

export function directory() {
  if (!directoryPromise) directoryPromise = loadJSON("data/slices/plum/directory.json");
  return directoryPromise;
}

export function timelines() {
  if (!timelinesPromise) timelinesPromise = loadJSON("data/slices/plum/timelines.json").catch(() => ({ people: {} }));
  return timelinesPromise;
}

export function personHref(id) {
  return `executives.html?id=${encodeURIComponent(id)}`;
}

// PLUM names arrive inconsistently cased: "KEITH SONDERLING" next to "Brendan Knight". Title-case for display
// while respecting the prefixes and punctuation that a naive capitalization would mangle.
const PARTICLES = new Set(["de", "del", "della", "der", "di", "du", "la", "le", "van", "von", "y"]);
export function properName(name) {
  if (!name) return name;
  if (name !== name.toUpperCase() && name !== name.toLowerCase()) return name; // already mixed; trust it
  return name.toLowerCase().split(/(\s+)/).map((word, i) => {
    if (!word.trim()) return word;
    if (i > 0 && PARTICLES.has(word)) return word;
    return word
      .replace(/^(mc)(\w)/, (_, p, c) => p[0].toUpperCase() + p[1] + c.toUpperCase())
      .replace(/^(mac)(\w{3,})/, (_, p, rest) => p[0].toUpperCase() + p.slice(1) + rest[0].toUpperCase() + rest.slice(1))
      .replace(/^(o')(\w)/, (_, p, c) => "O'" + c.toUpperCase())
      .replace(/(^|[-–])([a-z])/g, (_, sep, c) => sep + c.toUpperCase());
  }).join("");
}

function statusBadge(p) {
  if (p.status === "Vacant") return el("span", { class: "badge warn" }, "vacant");
  return p.class === "political" ? el("span", { class: "badge pol" }, p.appt_label) : el("span", { class: "badge" }, p.appt_label);
}

function personRow(p) {
  const line = el("div", { class: "lead-row" });
  const shown = properName(p.name);
  const who = p.name
    ? (p.id ? el("a", { href: personHref(p.id), class: "lead-name" }, shown) : el("span", { class: "lead-name" }, shown))
    : el("span", { class: "lead-name muted" }, "— vacant —");
  line.append(who, el("span", { class: "lead-title" }, p.title), statusBadge(p));
  // "Since" is the incumbent's start date; on a vacant position PLUM's begin date describes the post, not a
  // person, so showing it there would read as though someone had held it since then.
  if (p.since && p.status === "Filled") line.append(el("span", { class: "muted lead-since" }, `since ${fmt.day(p.since)}`));
  return line;
}

// The roster for one node. Returns null when the unit has no PLUM positions mapped to it.
export async function leadershipPanel(container, { code, name }) {
  container.innerHTML = "";
  const roster = await loadJSON(`data/slices/plum/node-${code}.json`).catch(() => null);
  if (!roster || !roster.positions.length) return null;
  const filled = roster.positions.filter((p) => p.status === "Filled");
  const vacant = roster.positions.filter((p) => p.status === "Vacant");
  const political = filled.filter((p) => p.class === "political");
  const panel = el("div", { class: "panel" }, el("h2", {}, "Leadership"));
  panel.append(el("p", { class: "muted" },
    `${fmt.int(roster.positions.length)} policy and supporting positions reported under the PLUM Act as of ${fmt.day(roster.snapshot)}: `,
    `${fmt.int(filled.length)} filled, ${fmt.int(vacant.length)} vacant, ${fmt.int(political.length)} of the filled ones political appointees. `,
    el("a", { href: "executives.html?node=" + encodeURIComponent(code) }, "Open in the directory"), "."));
  const show = 12;
  const list = el("div", { class: "lead-list" });
  for (const p of roster.positions.slice(0, show)) list.append(personRow(p));
  panel.append(list);
  if (roster.positions.length > show) {
    const rest = el("div", { class: "lead-list", hidden: "" });
    for (const p of roster.positions.slice(show)) rest.append(personRow(p));
    const more = el("button", { type: "button", onclick: () => { rest.hidden = !rest.hidden; more.textContent = rest.hidden ? `Show all ${roster.positions.length}` : "Show fewer"; } }, `Show all ${roster.positions.length}`);
    panel.append(rest, more);
  }
  container.append(panel);
  return roster;
}

// One person: their current position from the directory, plus every position PLUM has recorded for them.
export async function personCard(container, id) {
  container.innerHTML = "";
  const [dir, tl] = await Promise.all([directory(), timelines()]);
  const appts = dir.appointments || {};
  const current = dir.people.filter((p) => p.id === id);
  const history = tl.people?.[id];
  if (!current.length && !history) {
    container.append(el("p", { class: "notice" }, "No PLUM record with that identifier."));
    return null;
  }
  const name = properName(history?.name || current[0]?.n || "Unknown");
  document.title = `${name} · Fed Pulse`;
  const head = el("div", {}, el("h1", { style: "margin-bottom:.2rem" }, name));
  container.append(head);
  for (const p of current) {
    const meta = appts[p.at] || {};
    const card = el("div", { class: "panel" },
      el("h2", { style: "margin-bottom:.2rem" }, p.t),
      el("p", { class: "muted", style: "margin:0" },
        p.a, p.o && p.o !== p.a ? ` · ${p.o}` : "",
        p.node ? el("span", {}, " · ", el("a", { href: `unit.html?code=${encodeURIComponent(p.node)}` }, "unit page")) : ""),
      el("div", { class: "counters" },
        el("span", {}, "appointment ", el("b", {}, meta.label || p.at)),
        p.pp ? el("span", {}, "pay plan ", el("b", {}, p.pp)) : null,
        p.lv ? el("span", {}, "level ", el("b", {}, p.lv)) : null,
        p.loc ? el("span", {}, "duty location ", el("b", {}, p.loc)) : null,
        p.since ? el("span", {}, "in post since ", el("b", {}, fmt.day(p.since))) : null));
    container.append(card);
  }
  if (history && history.positions.length > 1) {
    const panel = el("div", { class: "panel" }, el("h2", {}, "Positions recorded in PLUM"));
    const t = el("table");
    t.append(el("thead", {}, el("tr", {}, ["Position", "Organization", "Appointment", "From", "To"].map((h) => el("th", { scope: "col" }, h)))));
    const rows = [...history.positions].sort((a, b) => (b.b || "").localeCompare(a.b || ""));
    t.append(el("tbody", {}, rows.map((p) => el("tr", {},
      el("td", {}, p.t),
      el("td", {}, p.o && p.o !== p.a ? `${p.a} · ${p.o}` : p.a),
      el("td", {}, (appts[p.at] || {}).label || p.at),
      el("td", {}, p.b ? fmt.day(p.b) : "—"),
      el("td", {}, p.v ? fmt.day(p.v) : (p.s === "Filled" ? "present" : "—"))))));
    panel.append(el("div", { class: "table-wrap" }, t));
    panel.append(el("p", { class: "muted" }, "PLUM records the positions an agency reports, not a full federal career. A gap means no reportable position, not necessarily a gap in service."));
    container.append(panel);
  }
  return { name, current, history };
}
