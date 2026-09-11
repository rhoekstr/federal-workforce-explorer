"""The measure catalog: the data dictionary every value must resolve against (Evince A19).

Loads catalog/measures.json and catalog/dimensions.json, validates them, derives extensiveness for derived
measures from their pattern, detects cycles (time offsets are lagging edges and excluded), and generates
operational definitions for derived measures from their calculations (Evince 67).
"""
from __future__ import annotations

import json
from pathlib import Path

from pipeline.config import ROOT

CATALOG_DIR = ROOT / "catalog"
UNITS = {"count", "people", "percentage", "ratio", "currency", "years", "dollars_per_person", "index", "rate"}
AGGREGATIONS = {"sum", "latest", "average", "manual"}
CATEGORIES = {"demand", "input", "process", "output", "outcome", "contextual"}
CADENCES = {"month", "quarter", "fiscal_year", "survey_year"}
LEVELS = {"gov", "department", "agency", "subelement", "group"}
PATTERNS = {"additive", "ratio", "time_offset"}


class CatalogError(ValueError):
    pass


def _load_json(name: str) -> dict:
    return json.loads((CATALOG_DIR / name).read_text())


class Catalog:
    def __init__(self, measures: dict[str, dict], dimensions: dict[str, dict]):
        self.measures = measures
        self.dimensions = dimensions
        self.validate()
        self.derive_properties()
        self.check_cycles()

    @classmethod
    def load(cls) -> "Catalog":
        return cls(_load_json("measures.json")["measures"], _load_json("dimensions.json")["dimensions"])

    # ----- validation -----
    def validate(self) -> None:
        for code, m in self.measures.items():
            where = f"measure {code!r}"
            for field in ("title", "kind", "unit", "aggregation", "category", "cadence", "levels", "since"):
                if field not in m:
                    raise CatalogError(f"{where}: missing {field}")
            if m.get("kind") == "base" and not m.get("definition"):
                raise CatalogError(f"{where}: base measures need an operational definition")
            if m["kind"] not in ("base", "derived"):
                raise CatalogError(f"{where}: kind must be base or derived")
            if m["unit"] not in UNITS:
                raise CatalogError(f"{where}: unknown unit {m['unit']}")
            if m["aggregation"] not in AGGREGATIONS:
                raise CatalogError(f"{where}: unknown aggregation {m['aggregation']}")
            if m["category"] not in CATEGORIES:
                raise CatalogError(f"{where}: unknown category {m['category']}")
            if m["cadence"] not in CADENCES:
                raise CatalogError(f"{where}: unknown cadence {m['cadence']}")
            if not set(m["levels"]) <= LEVELS:
                raise CatalogError(f"{where}: unknown level in {m['levels']}")
            for d in m.get("dimensions", []):
                if d not in self.dimensions:
                    raise CatalogError(f"{where}: unknown dimension {d}")
            if m["kind"] == "base":
                if "extensiveness" not in m:
                    raise CatalogError(f"{where}: base measures must declare extensiveness")
                if "calculation" in m:
                    raise CatalogError(f"{where}: base measures cannot carry a calculation")
            else:
                calc = m.get("calculation")
                if not calc or calc.get("pattern") not in PATTERNS:
                    raise CatalogError(f"{where}: derived measures need a calculation with one of {sorted(PATTERNS)}")
                for comp in self.components(code):
                    if comp["measure"] not in self.measures:
                        raise CatalogError(f"{where}: component {comp['measure']} is not in the catalog")
            if m.get("supersedes") and m["supersedes"] not in self.measures:
                raise CatalogError(f"{where}: supersedes unknown measure {m['supersedes']}")

    def components(self, code: str) -> list[dict]:
        """Components of a derived measure as [{measure, sign|role, offset}]."""
        calc = self.measures[code].get("calculation")
        if not calc:
            return []
        p = calc["pattern"]
        if p == "additive":
            return [{"measure": t["measure"], "sign": t.get("sign", 1), "offset": t.get("offset", 0)} for t in calc["terms"]]
        if p == "ratio":
            return [
                {"measure": calc["numerator"]["measure"], "role": "numerator", "offset": calc["numerator"].get("offset", 0)},
                {"measure": calc["denominator"]["measure"], "role": "denominator", "offset": calc["denominator"].get("offset", 0)},
            ]
        return [{"measure": calc["source"]["measure"], "offset": calc["source"].get("offset", 0)}]

    # ----- derived properties (Evince A16/A17) -----
    def derive_properties(self) -> None:
        for code, m in self.measures.items():
            if m["kind"] != "derived":
                continue
            p = m["calculation"]["pattern"]
            comps = [self.measures[c["measure"]] for c in self.components(code)]
            if p == "ratio":
                m["extensiveness"] = "intensive"
            elif p == "additive":
                kinds = {c.get("extensiveness") for c in comps}
                if len(kinds) > 1:
                    raise CatalogError(f"measure {code!r}: additive components must share extensiveness, got {kinds}")
                m["extensiveness"] = kinds.pop() if kinds else "extensive"
            else:
                m["extensiveness"] = comps[0].get("extensiveness", "extensive")
            if not m.get("definition") or m.get("definition_generated"):
                m["definition"] = self.generated_definition(code)
                m["definition_generated"] = True

    def generated_definition(self, code: str) -> str:
        m = self.measures[code]
        calc = m["calculation"]
        p = calc["pattern"]

        def name(c):
            t = self.measures[c["measure"]]["title"]
            off = c.get("offset", 0)
            return t if not off else f"{t} {abs(off)} {'period' if abs(off) == 1 else 'periods'} {'earlier' if off < 0 else 'later'}"

        if p == "ratio":
            num, den = self.components(code)
            scale = " × 100" if m["unit"] == "percentage" else (" × 1,000" if m["unit"] == "rate" else "")
            return f"{name(num)} divided by {name(den)}{scale}, per {m['cadence'].replace('_', ' ')}."
        if p == "additive":
            parts = []
            for c in self.components(code):
                parts.append(("+ " if c["sign"] > 0 else "− ") + name(c))
            text = " ".join(parts)
            return f"Sum of terms: {text.lstrip('+ ').strip()}, per {m['cadence'].replace('_', ' ')}."
        src = self.components(code)[0]
        return f"{name(src)}, shifted by {src['offset']} {m['cadence'].replace('_', ' ')}s."

    # ----- graph (Evince 136, 140) -----
    def check_cycles(self) -> None:
        graph = {code: [c["measure"] for c in self.components(code) if c.get("offset", 0) == 0] for code in self.measures}
        state: dict[str, int] = {}

        def visit(node, stack):
            state[node] = 1
            for nxt in graph.get(node, []):
                if state.get(nxt) == 1:
                    raise CatalogError(f"cycle in derived measures: {' -> '.join(stack + [node, nxt])}")
                if state.get(nxt) != 2:
                    visit(nxt, stack + [node])
            state[node] = 2

        for code in graph:
            if state.get(code) != 2:
                visit(code, [])

    def evaluation_order(self) -> list[str]:
        """Derived measures in dependency order (components before dependents)."""
        order: list[str] = []
        seen: set[str] = set()

        def visit(code):
            if code in seen:
                return
            seen.add(code)
            for c in self.components(code):
                if self.measures[c["measure"]]["kind"] == "derived":
                    visit(c["measure"])
            if self.measures[code]["kind"] == "derived":
                order.append(code)

        for code in self.measures:
            visit(code)
        return order

    def base(self) -> list[str]:
        return [c for c, m in self.measures.items() if m["kind"] == "base"]

    def public(self) -> dict[str, dict]:
        """Catalog as the site sees it: generated definitions in, internal flags out."""
        return {c: {k: v for k, v in m.items() if not k.startswith("_")} for c, m in self.measures.items()}


def write_public_catalog(catalog: Catalog, path: Path) -> None:
    path.write_text(json.dumps({"measures": catalog.public(), "dimensions": catalog.dimensions}, indent=1, ensure_ascii=False))
