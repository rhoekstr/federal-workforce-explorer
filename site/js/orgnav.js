// Spine-and-shelf org navigator: the path to the selected node as a vertical spine, its children as a wrapping shelf.
import { el, fmt } from "./common.js";
import { sparkline } from "./charts.js";
import { pathTo, searchIndex } from "./orgchart.js";

const SHELF_MAX = 24;
const SMALL_LIMIT = 1000;

function box(tree, node, months, { current, onSelect, extra }) {
  const first = months.find((m) => node.headcount?.[m] != null);
  const change = first && node.headcount?.[tree.latest] != null ? node.headcount[tree.latest] - node.headcount[first] : null;
  const gone = tree.latest && node.last_seen && node.last_seen < tree.latest;
  const b = el("button", { class: "box", type: "button", "aria-current": current ? "true" : null, "data-code": node.code, role: "treeitem", title: `${node.name}: ${fmt.int(node.latest ?? 0)} employees`, onclick: () => onSelect(node.code) });
  b.append(el("div", { class: "n" }, node.name));
  b.append(el("div", { class: "h" }, fmt.int(node.latest ?? 0), change != null ? el("span", { class: change < 0 ? " neg" : " pos" }, ` ${fmt.signed(change)}`) : null, extra ? el("span", { class: "k" }, ` · ${extra}`) : null));
  if (gone) b.append(el("div", { class: "k gone" }, `gone since ${fmt.month(node.last_seen)}`));
  const s = sparkline(months.map((m) => node.headcount?.[m] ?? null));
  if (s) b.append(s);
  return b;
}

export function renderOrgNav(container, tree, selected, onSelect, state = {}) {
  const months = Object.keys(tree.nodes.gov.headcount).sort();
  const path = pathTo(tree, selected);
  const node = tree.nodes[selected];
  const showAll = state.showAll || new Set();
  const smallOpen = state.smallOpen || false;
  container.innerHTML = "";
  const nav = el("div", { class: "orgnav", role: "tree", "aria-label": "Organization navigator" });

  // Search
  const input = el("input", { type: "search", placeholder: "find a unit…", "aria-label": "Find a unit", list: "orgnav-units" });
  const list = el("datalist", { id: "orgnav-units" });
  const index = searchIndex(tree).sort((a, b) => b.latest - a.latest);
  for (const n of index.slice(0, 700)) list.append(el("option", { value: `${n.name} (${n.code})` }));
  const go = () => {
    const m = input.value.match(/\(([A-Z0-9:_]+)\)\s*$/);
    const q = input.value.trim().toLowerCase();
    const hit = (m && tree.nodes[m[1]] && m[1]) || index.find((n) => n.name.toLowerCase() === q)?.code || index.find((n) => n.name.toLowerCase().includes(q))?.code;
    if (hit) { input.value = ""; onSelect(hit); }
  };
  input.addEventListener("change", go);
  nav.append(el("div", { class: "search" }, input, el("button", { type: "button", onclick: go }, "Go")));

  // Spine: every ancestor plus the selected node
  const spine = el("ul", { class: "spine", role: "group" });
  for (const code of path) {
    const n = tree.nodes[code];
    const li = el("li", { role: "none" });
    li.append(box(tree, n, months, { current: code === selected, onSelect }));
    spine.append(li);
  }
  nav.append(spine);

  // Shelf: children of the selected node (or of its parent when it has none, so siblings stay reachable)
  let shelfOwner = node.children.length ? node : (node.parent ? tree.nodes[node.parent] : node);
  let kids = shelfOwner.children.map((c) => tree.nodes[c]);
  let small = [];
  if (shelfOwner.code === "gov") { small = kids.filter((k) => k.small && (k.latest ?? 0) < SMALL_LIMIT); kids = kids.filter((k) => !small.includes(k)); }
  const head = el("div", { class: "shelf-head" }, shelfOwner === node ? `${kids.length + (small.length ? 1 : 0)} units under ${node.name}` : `${node.name} has no sub-units; showing its siblings under ${shelfOwner.name}`);
  nav.append(head);
  const shelf = el("ul", { class: "shelf", role: "group" });
  const visible = showAll.has(shelfOwner.code) ? kids : kids.slice(0, SHELF_MAX);
  for (const k of visible) shelf.append(el("li", { role: "none" }, box(tree, k, months, { current: k.code === selected && shelfOwner !== node, onSelect, extra: k.children.length ? `${k.children.length} units` : null })));
  if (kids.length > visible.length) {
    shelf.append(el("li", { role: "none" }, el("button", { class: "box more", type: "button", onclick: () => renderOrgNav(container, tree, selected, onSelect, { ...state, showAll: new Set([...showAll, shelfOwner.code]) }) }, el("div", { class: "n" }, `+${kids.length - visible.length} more`), el("div", { class: "h" }, fmt.int(kids.slice(visible.length).reduce((s, k) => s + (k.latest ?? 0), 0))))));
  }
  if (small.length) {
    shelf.append(el("li", { role: "none" }, el("button", { class: "box more", type: "button", "aria-expanded": smallOpen ? "true" : "false", onclick: () => renderOrgNav(container, tree, selected, onSelect, { ...state, smallOpen: !smallOpen }) }, el("div", { class: "n" }, `Small agencies (${small.length})`), el("div", { class: "h" }, fmt.int(small.reduce((s, k) => s + (k.latest ?? 0), 0))))));
    if (smallOpen) for (const k of small) shelf.append(el("li", { role: "none" }, box(tree, k, months, { current: k.code === selected, onSelect })));
  }
  nav.append(shelf);

  // Keyboard: arrows move within the shelf, Backspace goes up.
  nav.addEventListener("keydown", (e) => {
    const boxes = [...shelf.querySelectorAll("button.box")];
    const i = boxes.indexOf(document.activeElement);
    if (e.key === "ArrowRight" && boxes[i + 1]) { boxes[i + 1].focus(); e.preventDefault(); }
    else if (e.key === "ArrowLeft" && boxes[i - 1]) { boxes[i - 1].focus(); e.preventDefault(); }
    else if (e.key === "Backspace" && node.parent && document.activeElement.tagName === "BUTTON") { onSelect(node.parent); e.preventDefault(); }
  });
  container.append(nav);
}
