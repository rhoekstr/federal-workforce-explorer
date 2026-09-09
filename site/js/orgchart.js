// Classic collapsed org chart: boxes and lines, one branch expanded at a time, small agencies grouped.
import { el, fmt } from "./common.js";
import { sparkline } from "./charts.js";

const SHOW_MAX = 20;
const SMALL_LIMIT = 1000;

export function pathTo(tree, code) {
  const path = [];
  let cur = tree.nodes[code];
  while (cur) { path.unshift(cur.code); cur = cur.parent ? tree.nodes[cur.parent] : null; }
  return path;
}

function headcountValues(node, months) {
  return months.map((m) => node.headcount?.[m] ?? null);
}

function nodeBox(tree, node, { selected, expanded, onSelect, months, hasChildren }) {
  const latest = node.latest ?? 0;
  const first = months.find((m) => node.headcount?.[m] != null);
  const change = first && node.headcount?.[tree.latest] != null && node.headcount?.[first] != null ? node.headcount[tree.latest] - node.headcount[first] : null;
  const gone = tree.latest && node.last_seen && node.last_seen < tree.latest;
  const btn = el("button", {
    class: "node", type: "button", "aria-pressed": selected ? "true" : "false", "data-code": node.code,
    "aria-expanded": hasChildren ? (expanded ? "true" : "false") : null,
    title: `${node.name}: ${fmt.int(latest)} employees` + (gone ? ` (last seen ${fmt.month(node.last_seen)})` : ""),
    onclick: () => onSelect(node.code),
  });
  btn.append(el("div", { class: "n" }, node.name));
  btn.append(el("div", { class: "h" }, fmt.int(latest), change != null ? el("span", { class: change < 0 ? " neg" : " pos" }, ` ${fmt.signed(change)}`) : null));
  if (gone) btn.append(el("div", { class: "k gone" }, `gone since ${fmt.month(node.last_seen)}`));
  const spark = sparkline(headcountValues(node, months));
  if (spark) btn.append(spark);
  if (hasChildren) btn.append(el("span", { class: "exp", "aria-hidden": "true" }, expanded ? "−" : "+"));
  return btn;
}

function childrenOf(tree, code, showAll) {
  const node = tree.nodes[code];
  let kids = node.children.map((c) => tree.nodes[c]);
  let small = [];
  if (code === "gov") {
    small = kids.filter((k) => k.small && (k.latest ?? 0) < SMALL_LIMIT);
    kids = kids.filter((k) => !small.includes(k));
  }
  const hidden = showAll ? [] : kids.slice(SHOW_MAX);
  return { kids: showAll ? kids : kids.slice(0, SHOW_MAX), hidden, small };
}

// Render the tree with the path to `selected` expanded. Returns the root <ul>.
export function renderOrgChart(container, tree, selected, onSelect, state = {}) {
  const months = Object.keys(tree.nodes.gov.headcount).sort();
  const path = new Set(pathTo(tree, selected));
  const showAll = state.showAll || new Set();
  container.innerHTML = "";

  function renderNode(code, isSmallGroup = false) {
    const node = tree.nodes[code];
    const expanded = path.has(code);
    const { kids, hidden, small } = childrenOf(tree, code, showAll.has(code));
    const hasChildren = kids.length > 0 || small.length > 0;
    const li = el("li");
    li.append(nodeBox(tree, node, { selected: code === selected, expanded, onSelect, months, hasChildren }));
    if (expanded && hasChildren) {
      const ul = el("ul", { role: "group" });
      for (const k of kids) ul.append(renderNode(k.code));
      if (hidden.length) {
        ul.append(el("li", {}, el("button", { class: "node more", type: "button", onclick: () => { showAll.add(code); renderOrgChart(container, tree, selected, onSelect, { showAll }); } }, el("div", { class: "n" }, `+${hidden.length} more`), el("div", { class: "h" }, fmt.int(hidden.reduce((s, k) => s + (k.latest ?? 0), 0))))));
      }
      if (small.length) {
        const smallExpanded = path.has("small") || state.smallOpen;
        const li2 = el("li");
        li2.append(el("button", { class: "node more", type: "button", "aria-expanded": smallExpanded ? "true" : "false", onclick: () => renderOrgChart(container, tree, selected, onSelect, { showAll, smallOpen: !smallExpanded }) },
          el("div", { class: "n" }, `Small agencies (${small.length})`), el("div", { class: "h" }, fmt.int(small.reduce((s, k) => s + (k.latest ?? 0), 0))), el("span", { class: "exp", "aria-hidden": "true" }, smallExpanded ? "−" : "+")));
        if (smallExpanded) {
          const ul2 = el("ul", { role: "group" });
          for (const k of small) ul2.append(renderNode(k.code, true));
          li2.append(ul2);
        }
        ul.append(li2);
      }
      li.append(ul);
    }
    return li;
  }

  const root = el("ul", { class: "orgchart", role: "tree", "aria-label": "Organization chart" });
  root.append(renderNode("gov"));
  container.append(root);
  // Keep the selected box in view.
  container.querySelector('.node[aria-pressed="true"]')?.scrollIntoView({ block: "nearest", inline: "center" });
}

export function searchIndex(tree) {
  return Object.values(tree.nodes).filter((n) => n.code !== "gov").map((n) => ({ code: n.code, name: n.name, level: n.level, latest: n.latest ?? 0, parent: n.parent }));
}
