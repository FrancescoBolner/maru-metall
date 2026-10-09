"""Knowledge source interface.

Today the knowledge is Maru's Excel file; tomorrow it can be Maru's own model or database.
Anything that can produce a `KnowledgeBase` (tables of rows with stable ids) can replace the Excel
implementation: the rule engine only talks to `KnowledgeBase`.
"""
from __future__ import annotations

import bisect
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional, Protocol

from ..parsers.profiles import Profile, parse_profile


class KnowledgeSource(Protocol):
    name: str

    def load(self) -> "KnowledgeBase": ...


@dataclass
class KRow:
    id: str
    sheet: str
    row: int
    data: dict[str, Any]

    def __getitem__(self, k: str) -> Any:
        return self.data.get(k)

    def get(self, k: str, default: Any = None) -> Any:
        v = self.data.get(k)
        return default if v is None else v


@dataclass
class KnowledgeBase:
    source_name: str
    version: str
    path: str
    tables: dict[str, list[KRow]] = field(default_factory=dict)
    by_id: dict[str, KRow] = field(default_factory=dict)

    # ------------------------------------------------------------------ basics
    def rows(self, sheet: str) -> list[KRow]:
        return self.tables.get(sheet, [])

    def row(self, kid: str) -> Optional[KRow]:
        return self.by_id.get(kid)

    def describe(self, kid: str) -> str:
        r = self.row(kid)
        if not r:
            return kid
        return f"{self.source_name} › {r.sheet} › {kid} (row {r.row})"

    def general(self, key: str, default: Any = None) -> tuple[Any, str]:
        for r in self.rows("General"):
            if r["key"] == key:
                return r["value"], r.id
        return default, "GEN-?"

    def num(self, key: str, default: float = 0.0) -> tuple[float, str]:
        v, kid = self.general(key, default)
        try:
            return float(v), kid
        except (TypeError, ValueError):
            return default, kid

    # ------------------------------------------------------------------ labour
    def labour_rate(self, country: str = "EE") -> tuple[float, str]:
        for r in self.rows("Labour_rates"):
            if str(r["country"]).upper() == country.upper():
                return float(r["eur_per_hour"]), r.id
        return self.num("labour_rate", 46.0)

    # ------------------------------------------------------------------ steel prices
    def price_lists(self) -> list[tuple[str, str]]:
        seen: dict[str, str] = {}
        for r in self.rows("Steel_prices"):
            seen[str(r["price_list"])] = str(r["price_date"])
        return sorted(seen.items(), key=lambda kv: kv[1])

    def choose_price_list(self, inquiry: Optional[date]) -> tuple[str, str, str]:
        """Price list closest in time to the inquiry date (fallback: newest). Returns (list, date, reason)."""
        lists = self.price_lists()
        if not lists:
            return "", "", "no price list"
        if inquiry:
            def dist(l: tuple[str, str]) -> int:
                try:
                    return abs((date.fromisoformat(l[1][:10]) - inquiry).days)
                except ValueError:
                    return 10**6
            best = min(lists, key=lambda l: (dist(l), l[1]))
            return best[0], best[1], f"price list closest to the inquiry date {inquiry.isoformat()} ({dist(best)} days apart)"
        return lists[-1][0], lists[-1][1], "newest price list (no inquiry date found)"

    def steel_price(self, prof: Profile, price_list: str, grade: Optional[str] = None) -> tuple[float, float, str, str]:
        """(€/kg, waste factor, row id, how matched)."""
        rows = [r for r in self.rows("Steel_prices") if str(r["price_list"]) == price_list]
        keys = {k.upper().replace(" ", "") for k in prof.price_keys + [prof.canonical, prof.raw]}
        for r in rows:
            item = str(r["item"] or "")
            if item != "*" and item.upper().replace(" ", "") in keys:
                return float(r["eur_per_kg"]), float(r["waste_factor"] or 1.0), r.id, f"exact item {item}"
        fam = prof.family if prof.family not in ("REBAR", "OTHER") else "*"
        fam = {"HEA": "HEA", "HEB": "HEB", "HEM": "HEM"}.get(fam, fam)
        size = prof.thickness or 0
        best = None
        for r in rows:
            if str(r["item"]) != "*" or str(r["family"]) != fam:
                continue
            lo, hi = r["size_from"], r["size_to"]
            if lo is not None and hi is not None and not (float(lo) <= size <= float(hi)):
                continue
            best = r
            break
        if best is None:
            best = next((r for r in rows if str(r["item"]) == "*" and str(r["family"]) == "*"), None)
        if best is None:
            return 0.85, 1.1, "SP-?", "no price row"
        return float(best["eur_per_kg"]), float(best["waste_factor"] or 1.0), best.id, f"family {best['family']}"

    # ------------------------------------------------------------------ waste
    def waste_value(self, key: str, default: float) -> tuple[float, str]:
        for r in self.rows("Waste"):
            if r["key"] == key:
                return float(r["value"]), r.id
        return default, "WST-?"

    def plate_waste(self, t: float) -> tuple[float, str]:
        for r in self.rows("Waste"):
            if r["key"] == "plate_waste" and float(r["thickness_from"]) <= t <= float(r["thickness_to"]):
                return float(r["value"]), r.id
        return 1.10, "WST-?"

    # ------------------------------------------------------------------ norms
    def norm(self, nid: str) -> Optional[KRow]:
        return self.row(nid)

    def cutting(self, t: float) -> tuple[float, float, str]:
        rows = sorted(self.rows("Cutting_speeds"), key=lambda r: float(r["thickness_mm"]))
        if not rows:
            return 2000.0, 9.0, "CUT-?"
        ts = [float(r["thickness_mm"]) for r in rows]
        i = bisect.bisect_left(ts, t - 1e-9)
        r = rows[min(i, len(rows) - 1)]
        return float(r["speed_mm_min"]), float(r["pierce_s"]), r.id

    def handling(self, part_type: str, value: float, holes: bool) -> tuple[float, str]:
        for r in self.rows("Handling"):
            if r["part_type"] == part_type and float(r["band_from"]) <= value < float(r["band_to"]):
                return float(r["with_holes_min"] if holes else r["without_holes_min"]), r.id
        return 10.0, "HDL-?"

    def plate_drilling(self, t: float) -> tuple[float, str]:
        for r in self.rows("Drilling"):
            if float(r["thickness_from"]) <= t <= float(r["thickness_to"]):
                return float(r["min_per_hole"]), r.id
        return 0.0, "DRP-?"

    # ------------------------------------------------------------------ surface
    def paint_system(self, system: str) -> Optional[KRow]:
        s = normalize_system(system)
        for r in self.rows("Paint_systems"):
            if str(r["system"]).upper() == s:
                return r
        return None

    def surface_rate(self, system: str) -> tuple[float, str, str]:
        s = normalize_system(system)
        for r in self.rows("Surface_rates"):
            if str(r["system"]).upper() == s:
                return float(r["rate"]), str(r["unit"]), r.id
        return 0.0, "EUR/m2", "SUR-?"

    def surface_systems(self) -> list[str]:
        return [str(r["system"]).upper() for r in self.rows("Surface_rates")]

    def fire(self, rating: str) -> Optional[KRow]:
        for r in self.rows("Fire_protection"):
            if str(r["rating"]).upper() == rating.upper().replace(" ", ""):
                return r
        return None

    # ------------------------------------------------------------------ transport
    def transport_region(self, country: Optional[str], text: str = "") -> tuple[str, list[KRow], str]:
        rows = self.rows("Transport")
        t = (text or "").lower()
        for r in rows:
            kws = [k.strip().lower() for k in str(r["keywords"] or "").split(";") if k.strip()]
            if any(k and k in t for k in kws):
                region = str(r["region"])
                return region, [x for x in rows if x["region"] == region], f"address mentions '{next(k for k in kws if k in t)}'"
        if country:
            cand = [r for r in rows if country.upper() in str(r["countries"]).upper()]
            if cand:
                # prefer the region marked as default for the country: the one without keywords
                regions = []
                for r in cand:
                    if r["region"] not in regions:
                        regions.append(r["region"])
                no_kw = [rg for rg in regions if not any((x["keywords"] or "") for x in cand if x["region"] == rg)]
                region = no_kw[0] if no_kw else regions[0]
                return region, [x for x in rows if x["region"] == region], f"country {country}"
        region = str(rows[0]["region"]) if rows else ""
        return region, [x for x in rows if x["region"] == region], "no destination found: first region used"

    # ------------------------------------------------------------------ misc tables
    def fastener(self, fid: str) -> Optional[KRow]:
        return self.row(fid)

    def ppt(self, category: str) -> Optional[KRow]:
        for r in self.rows("Price_per_tonne"):
            if r["category"] == category:
                return r
        return next((r for r in self.rows("Price_per_tonne") if r["category"] == "Other steel"), None)

    def category_info(self, category: str) -> Optional[KRow]:
        for r in self.rows("Categories"):
            if r["category"] == category:
                return r
        return next((r for r in self.rows("Categories") if r["category"] == "Other steel"), None)

    def categories(self) -> list[str]:
        return [str(r["category"]) for r in sorted(self.rows("Categories"), key=lambda r: float(r.get("sort", 99)))]

    def map_category(self, *names: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
        """Map a free-text assembly / part name to a category. Returns (category, row id, keyword)."""
        best: tuple[int, Optional[KRow], str] = (-1, None, "")
        for name in names:
            if not name:
                continue
            low = str(name).lower()
            for r in self.rows("Category_map"):
                kw = str(r["keyword"]).lower()
                match = str(r["match"] or "contains")
                ok = (kw in low) if match == "contains" else bool(re.search(r"(?<![a-zæøå])" + re.escape(kw) + r"(?![a-zæøå])", low))
                if ok and int(r.get("priority", 0)) > best[0]:
                    best = (int(r.get("priority", 0)), r, kw)
        if best[1] is None:
            return None, None, None
        return str(best[1]["category"]), best[1].id, best[2]

    def prediction(self, key: str, default: Any = None) -> tuple[Any, str]:
        for r in self.rows("Predictions"):
            if r["key"] == key:
                return r["value"], r.id
        return default, "PRD-?"

    def co2(self, key: str, default: float = 0.0) -> tuple[float, str]:
        for r in self.rows("CO2_factors"):
            if r["key"] == key:
                return float(r["value"]), r.id
        return default, "CO2-?"

    def profile_props(self, prof: Profile) -> tuple[Optional[float], Optional[float], Optional[str]]:
        keys = {k.upper().replace(" ", "") for k in prof.price_keys + [prof.canonical, prof.raw]}
        for r in self.rows("Profiles"):
            if str(r["profile"]).upper().replace(" ", "") in keys:
                return float(r["kg_per_m"]), float(r["m2_per_m"]), r.id
        return None, None, None

    def i_table(self) -> dict[str, tuple[float, float, float, float]]:
        out = {}
        for r in self.rows("Profiles"):
            if r["h_mm"]:
                out[str(r["profile"]).upper()] = (float(r["h_mm"]), float(r["b_mm"]), float(r["tw_mm"]), float(r["tf_mm"]))
        return out

    def remnants(self) -> list[KRow]:
        return self.rows("Remnant_stock")


def normalize_system(system: Optional[str]) -> str:
    """'C2 M' / 'C2-M' / 'c2m' / 'C3.07 EPPUR 240/2' / 'ISO1461' -> canonical class names."""
    s = (system or "").upper().replace(" ", "").replace("-", "")
    if not s:
        return "NONE"
    if "HDG" in s or "1461" in s or "GALV" in s or "ZINK" in s or "SINK" in s:
        return "HDG"
    m = re.match(r"C([1-5])\.?(\d{2})", s)
    if m:  # ISO 12944-5 system number: C3.07 -> map by durability via known systems
        known = {"C3.07": "C3VH", "C4.06": "C4H"}
        key = f"C{m.group(1)}.{m.group(2)}"
        if key in known:
            return known[key]
    m = re.match(r"C([1-5])(VH|H|M|L)?", s)
    if m:
        cls = f"C{m.group(1)}{m.group(2) or ''}"
        if cls in ("C2", "C3", "C4", "C5"):
            cls += "M"
        return cls
    if s in ("NON", "NONE", "PRIMER"):
        return "NONE" if s != "PRIMER" else "C1"
    return s
