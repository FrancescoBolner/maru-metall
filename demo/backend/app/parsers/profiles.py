"""Steel profile normaliser.

Turns the many ways profiles are written in models and lists ("RHS100X100X6", "CFRHS100x100x6",
"Ø168.3X4.5", "L60*40*6", "FL15*120", "PL6*1698", "Leht 15", "HEB360", "D30", "PL15X170") into a
family + dimensions, and gives section properties (kg/m, m²/m) when the knowledge file has none.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Optional

DENSITY = 7.85e-3  # kg per mm² per m  (7850 kg/m3)

FAMILIES_PLATE = {"PL", "FL"}


@dataclass
class Profile:
    raw: str
    family: str                      # RHS, CHS, IPE, HEA, HEB, HEM, UPE, UNP, L, T, FL, PL, D, WI, REBAR, OTHER
    canonical: str
    dims: dict[str, float] = field(default_factory=dict)
    price_keys: list[str] = field(default_factory=list)

    @property
    def is_plate(self) -> bool:
        return self.family in FAMILIES_PLATE

    @property
    def thickness(self) -> Optional[float]:
        if self.family in ("PL", "FL"):
            return self.dims.get("t")
        if self.family in ("RHS", "CHS"):
            return self.dims.get("t")
        return self.dims.get("tf") or self.dims.get("t")

    @property
    def height(self) -> Optional[float]:
        d = self.dims
        return d.get("h") or d.get("d") or d.get("a") or d.get("w")

    @property
    def is_hollow(self) -> bool:
        return self.family in ("RHS", "CHS")

    @property
    def is_i_section(self) -> bool:
        return self.family in ("IPE", "HEA", "HEB", "HEM", "WI")


_NUM = r"(\d+(?:[.,]\d+)?)"
_SEP = r"\s*[xX*×/]\s*"


def _f(s: str) -> float:
    return float(s.replace(",", "."))


def _fmt(x: float) -> str:
    return f"{x:g}"


def parse_profile(raw: Optional[str]) -> Profile:
    s = (raw or "").strip()
    u = s.upper().replace(" ", "")
    u = u.replace("Ø", "Ø")
    # Plates: "Leht 15" (Estonian), "PL15X170", "PL6*1698", "PLT10", "BL10", "PL2.5X80"
    m = re.match(r"^(?:LEHT|PLT|BL)" + _NUM + "$", u)
    if m:
        t = _f(m.group(1))
        return Profile(s, "PL", f"PL{_fmt(t)}", {"t": t}, [f"leht {_fmt(t)}", f"Leht {_fmt(t)}"])
    m = re.match(r"^(PL|FL|FLT|FLAT)" + _NUM + _SEP + _NUM + "$", u)
    if m:
        fam = "FL" if m.group(1).startswith("FL") else "PL"
        a, b = _f(m.group(2)), _f(m.group(3))
        t, w = (a, b) if a <= b else (b, a)
        return Profile(s, fam, f"{fam}{_fmt(t)}x{_fmt(w)}", {"t": t, "w": w}, [f"leht {_fmt(t)}", f"Leht {_fmt(t)}"])
    m = re.match(r"^(PL|FL)" + _NUM + "$", u)
    if m:
        t = _f(m.group(2))
        return Profile(s, "PL", f"PL{_fmt(t)}", {"t": t}, [f"leht {_fmt(t)}"])
    # Hollow sections
    m = re.match(r"^(?:CF|HF)?(?:RHS|SHS|KKR|VKR)" + _NUM + _SEP + _NUM + _SEP + _NUM + "$", u)
    if m:
        h, b, t = _f(m.group(1)), _f(m.group(2)), _f(m.group(3))
        can = f"RHS{_fmt(h)}x{_fmt(b)}x{_fmt(t)}"
        return Profile(s, "RHS", can, {"h": h, "b": b, "t": t},
                       [f"CFRHS{_fmt(h)}x{_fmt(b)}x{_fmt(t)}", can])
    m = re.match(r"^(?:CF|HF)?(?:CHS|PD|RØR|ROR|Ø)" + _NUM + _SEP + _NUM + "$", u)
    if m:
        d, t = _f(m.group(1)), _f(m.group(2))
        return Profile(s, "CHS", f"CHS{_fmt(d)}x{_fmt(t)}", {"d": d, "t": t}, [f"CFCHS{_fmt(d)}x{_fmt(t)}"])
    # Round bars
    m = re.match(r"^(?:D|RD|RUND|Ø)" + _NUM + "$", u)
    if m:
        d = _f(m.group(1))
        return Profile(s, "D", f"D{_fmt(d)}", {"d": d}, [f"D{_fmt(d)}"])
    m = re.match(r"^REBAR" + _NUM + "$", u)
    if m:
        d = _f(m.group(1))
        return Profile(s, "REBAR", f"REBAR{_fmt(d)}", {"d": d}, [])
    # I / H sections
    m = re.match(r"^(IPE|HEA|HEB|HEM|HE)" + _NUM + r"([ABM])?$", u)
    if m:
        fam = m.group(1)
        if fam == "HE":
            fam = "HE" + (m.group(3) or "A")
        size = _f(m.group(2))
        can = f"{fam}{_fmt(size)}"
        return Profile(s, fam, can, {"size": size}, [can])
    m = re.match(r"^(UPE|UNP|UPN|U)" + _NUM + "$", u)
    if m:
        fam = "UNP" if m.group(1) in ("UNP", "UPN", "U") else "UPE"
        size = _f(m.group(2))
        return Profile(s, fam, f"{fam}{_fmt(size)}", {"size": size, "h": size}, [f"{fam}{_fmt(size)}"])
    # Angles
    m = re.match(r"^L" + _NUM + _SEP + _NUM + _SEP + _NUM + "$", u)
    if m:
        a, b, t = _f(m.group(1)), _f(m.group(2)), _f(m.group(3))
        can = f"L{_fmt(a)}x{_fmt(b)}x{_fmt(t)}"
        return Profile(s, "L", can, {"a": a, "b": b, "t": t, "h": a}, [can])
    m = re.match(r"^L" + _NUM + _SEP + _NUM + "$", u)
    if m:
        a, t = _f(m.group(1)), _f(m.group(2))
        can = f"L{_fmt(a)}x{_fmt(t)}"
        return Profile(s, "L", can, {"a": a, "b": a, "t": t, "h": a}, [can])
    m = re.match(r"^T" + _NUM + "$", u)
    if m:
        a = _f(m.group(1))
        return Profile(s, "T", f"T{_fmt(a)}", {"h": a, "b": a}, [f"T{_fmt(a)}"])
    # Welded I: "WI800-10-25X400", "WI400-8-15X300", "WQ..."
    m = re.match(r"^W[IQ]" + _NUM + r"[-_]" + _NUM + r"[-_]" + _NUM + _SEP + _NUM + "$", u)
    if m:
        h, tw, tf, b = _f(m.group(1)), _f(m.group(2)), _f(m.group(3)), _f(m.group(4))
        return Profile(s, "WI", f"WI{_fmt(h)}-{_fmt(tw)}-{_fmt(tf)}x{_fmt(b)}", {"h": h, "tw": tw, "tf": tf, "b": b}, [])
    return Profile(s, "OTHER", s or "?", {}, [s] if s else [])


def section_props(p: Profile, i_table: Optional[dict[str, tuple[float, float, float, float]]] = None
                  ) -> tuple[Optional[float], Optional[float]]:
    """Return (kg per m, m² per m) from nominal dimensions. Plates return per metre of strip width."""
    d = p.dims
    try:
        if p.family == "RHS":
            h, b, t = d["h"], d["b"], d["t"]
            r = 1.5 * t  # outer corner radius ~ 1.5-2 t
            area = 2 * t * (h + b - 2 * t) - (4 - math.pi) * (r * r - (r - t) ** 2)
            return area * DENSITY, (2 * (h + b) - (8 - 2 * math.pi) * r) / 1000
        if p.family == "CHS":
            dd, t = d["d"], d["t"]
            return math.pi * (dd - t) * t * DENSITY, math.pi * dd / 1000
        if p.family == "D" or p.family == "REBAR":
            dd = d["d"]
            return math.pi / 4 * dd * dd * DENSITY, math.pi * dd / 1000
        if p.family == "L":
            a, b, t = d["a"], d["b"], d["t"]
            return (a + b - t) * t * DENSITY, 2 * (a + b) / 1000
        if p.family in ("PL", "FL") and "w" in d:
            t, w = d["t"], d["w"]
            return t * w * DENSITY, 2 * (t + w) / 1000
        if p.family == "WI":
            h, tw, tf, b = d["h"], d["tw"], d["tf"], d["b"]
            return (2 * b * tf + (h - 2 * tf) * tw) * DENSITY, (2 * h + 4 * b - 2 * tw) / 1000
        if p.is_i_section and i_table and p.canonical in i_table:
            h, b, tw, tf = i_table[p.canonical]
            return (2 * b * tf + (h - 2 * tf) * tw) * DENSITY * 1.04, (2 * h + 4 * b - 2 * tw) / 1000
        if p.family in ("UPE", "UNP") and "h" in d:
            h = d["h"]
            b = 0.38 * h + 20
            tw, tf = 0.035 * h + 2, 0.05 * h + 3
            return (2 * b * tf + (h - 2 * tf) * tw) * DENSITY, (2 * h + 4 * b - 2 * tw) / 1000
        if p.family == "T" and "h" in d:
            h = d["h"]
            t = 0.1 * h + 1
            return (2 * h - t) * t * DENSITY, 4 * h / 1000
    except (KeyError, ValueError):
        return None, None
    return None, None


def plate_geometry(length_mm: float, width_mm: float, t_mm: float) -> dict[str, float]:
    """Cut edge (m), painted area both faces + edges (m²), mass (kg) of a rectangular plate."""
    edge_m = 2 * (length_mm + width_mm) / 1000
    area = (2 * length_mm * width_mm + edge_m * 1000 * t_mm) / 1e6
    kg = length_mm * width_mm * t_mm * DENSITY / 1000
    return {"edge_m": edge_m, "area_m2": area, "kg": kg}
