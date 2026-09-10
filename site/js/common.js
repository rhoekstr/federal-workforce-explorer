// Shared helpers: data loading, formatting, page chrome. No build step; ES module.
const cache = new Map();

export async function loadJSON(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(path).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path);
}

export const fmt = {
  int: (v) => (v == null ? "—" : Math.round(v).toLocaleString("en-US")),
  signed: (v) => (v == null ? "—" : (v > 0 ? "+" : "") + Math.round(v).toLocaleString("en-US")),
  pct: (v, d = 0) => (v == null ? "—" : (100 * v).toFixed(d) + "%"),
  money: (v) => {
    if (v == null) return "—";
    const a = Math.abs(v);
    if (a >= 1e12) return (v / 1e12).toFixed(2) + "T";
    if (a >= 1e9) return (v / 1e9).toFixed(1) + "B";
    if (a >= 1e6) return (v / 1e6).toFixed(0) + "M";
    if (a >= 1e3) return (v / 1e3).toFixed(0) + "K";
    return v.toFixed(0);
  },
  dollars: (v) => (v == null ? "—" : "$" + fmt.money(v)),
  month: (yyyymm) => {
    if (!yyyymm) return "—";
    const y = yyyymm.slice(0, 4), m = +yyyymm.slice(4, 6);
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][m - 1] + " " + y;
  },
  monthDate: (yyyymm) => new Date(+yyyymm.slice(0, 4), +yyyymm.slice(4, 6) - 1, 1),
};

export function qs(name, fallback = null) {
  const v = new URL(location.href).searchParams.get(name);
  return v == null || v === "" ? fallback : v;
}

export function setQs(params, replace = true) {
  const url = new URL(location.href);
  for (const [k, v] of Object.entries(params)) {
    if (v == null || v === "") url.searchParams.delete(k); else url.searchParams.set(k, v);
  }
  history[replace ? "replaceState" : "pushState"]({}, "", url);
}

export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k === "html") node.innerHTML = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else if (v != null) node.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null) node.append(c.nodeType ? c : document.createTextNode(String(c)));
  return node;
}

export function renderChrome(current) {
  const links = [["index.html", "Overview"], ["org.html", "Org chart"], ["data.html", "Data"], ["about.html", "About"]];
  const header = document.querySelector("header.top");
  if (header) {
    header.innerHTML = "";
    const inner = el("div", { class: "inner" }, el("a", { class: "brand", href: "index.html" }, "Fed Pulse"));
    const nav = el("nav", { "aria-label": "Site" });
    for (const [href, label] of links) nav.append(el("a", { href, ...(href === current ? { "aria-current": "page" } : {}) }, label));
    inner.append(nav);
    header.append(inner);
  }
  const footer = document.querySelector("footer");
  if (footer) footer.innerHTML = 'Sources: OPM Federal Workforce Data, USAspending, OMB Analytical Perspectives. No tracking, no cookies, no server: everything runs in your browser. An <a href="https://awrylabs.com">Awry Labs</a> project. <a href="data.html">Methods and downloads</a>.';
}

// Percent of headcount with a disclosed duty station; shown wherever geography or pay appears.
export function disclosureBadge(share) {
  if (share == null) return null;
  const pct = Math.round(share * 100);
  return el("span", { class: "badge" + (pct < 60 ? " warn" : ""), title: "Share of employees whose duty station and pay OPM disclosed" }, `${pct}% location disclosed`);
}

export function sortableTable(table, rows, columns, { initialSort, onRow, keyOf } = {}) {
  let sortKey = initialSort?.key ?? columns[0].key, dir = initialSort?.dir ?? "desc";
  const thead = el("thead"), tbody = el("tbody");
  table.innerHTML = "";
  table.append(thead, tbody);
  function render() {
    thead.innerHTML = "";
    const tr = el("tr");
    for (const c of columns) {
      const th = el("th", { role: "button", tabindex: 0, class: c.num ? "num" : "", scope: "col", title: c.title || "" }, c.label);
      if (c.key === sortKey) th.setAttribute("aria-sort", dir === "asc" ? "ascending" : "descending");
      const toggle = () => { if (sortKey === c.key) dir = dir === "asc" ? "desc" : "asc"; else { sortKey = c.key; dir = c.num ? "desc" : "asc"; } render(); };
      th.addEventListener("click", toggle);
      th.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
      tr.append(th);
    }
    thead.append(tr);
    const col = columns.find((c) => c.key === sortKey);
    const sorted = [...rows].sort((a, b) => {
      const va = col.value ? col.value(a) : a[sortKey], vb = col.value ? col.value(b) : b[sortKey];
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      const cmp = typeof va === "number" ? va - vb : String(va).localeCompare(String(vb));
      return dir === "asc" ? cmp : -cmp;
    });
    tbody.innerHTML = "";
    for (const r of sorted) {
      const tr = el("tr", onRow ? { class: "clickable", tabindex: 0, role: "link" } : {});
      for (const c of columns) {
        const v = c.value ? c.value(r) : r[c.key];
        const td = el("td", { class: c.num ? "num" : "" });
        const rendered = c.render ? c.render(v, r) : v == null ? "—" : v;
        td.append(rendered?.nodeType ? rendered : String(rendered));
        tr.append(td);
      }
      if (onRow) {
        tr.addEventListener("click", () => onRow(r));
        tr.addEventListener("keydown", (e) => { if (e.key === "Enter") onRow(r); });
      }
      tbody.append(tr);
    }
  }
  render();
}

// Accessible data-table alternative for a chart.
export function altTable(headers, rows, summary = "Data behind this chart") {
  const t = el("table");
  t.append(el("thead", {}, el("tr", {}, headers.map((h) => el("th", { scope: "col" }, h)))));
  t.append(el("tbody", {}, rows.map((r) => el("tr", {}, r.map((v) => el("td", {}, v == null ? "—" : String(v)))))));
  return el("details", { class: "alt" }, el("summary", {}, summary), el("div", { class: "table-wrap" }, t));
}
