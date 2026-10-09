"""Material lists / BOMs in Excel or CSV: header detection, column mapping, subtotal skipping, totals."""
from __future__ import annotations

import csv
import io
import re
import warnings
from pathlib import Path
from typing import Any, Optional

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

COLS = {
    "profile": ("profile", "profil", "profiil", "section", "description", "product description", "nimetus", "dimension"),
    "material": ("material", "grade", "materjal", "mark", "kvalitet", "quality", "steel grade"),
    "qty": ("quantity", "qty", "pcs", "pcs.", "antal", "stk", "kogus", "kpl", "count", "no."),
    "length": ("l [mm]", "length", "length (mm)", "length [mm]", "l", "pikkus", "lengde", "længde", "l (mm)"),
    "unit_weight": ("kg/pc", "kg/pcs", "weight/pc", "unit weight", "kg/tk", "kg / pc"),
    "total_weight": ("sum kg", "total kg", "weight sum", "kaal kokku", "sum weight", "total weight", "weight (t)",
                     "weight", "kg", "vekt"),
    "position": ("part pos.", "part pos", "pos", "position", "part", "mark no", "assembly"),
    "area": ("area", "m2", "m²", "surface", "pind"),
}


def _norm(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "").replace("\xa0", " ")).strip().lower()


def _num(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace("\xa0", "").replace(" ", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _match_header(cells: list[str]) -> dict[str, int]:
    found: dict[str, int] = {}
    for i, c in enumerate(cells):
        if not c:
            continue
        for key, labels in COLS.items():
            if key in found:
                continue
            if c in labels or any(c.startswith(l) for l in labels if len(l) > 3):
                # weight (t) means tonnes: remember
                found[key] = i
                break
    return found


def _sheet_rows(path: Path) -> list[tuple[str, list[list[Any]]]]:
    if path.suffix.lower() == ".csv":
        raw = path.read_bytes().decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(raw[:4000], delimiters=";,\t") if raw.strip() else csv.excel
        return [("csv", [row for row in csv.reader(io.StringIO(raw), dialect)])]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        wb = load_workbook(path, data_only=True, read_only=True)
    out = []
    for ws in wb.worksheets:
        out.append((ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
    wb.close()
    return out


def scan(path: Path) -> dict[str, Any]:
    """Is this a material list? Returns sheets count, header info and declared total (cheap)."""
    sheets = _sheet_rows(path)
    best = None
    for name, rows in sheets:
        for ri, row in enumerate(rows[:40]):
            cells = [_norm(c) for c in row]
            h = _match_header(cells)
            if "profile" in h and ("qty" in h or "total_weight" in h) and len(h) >= 3:
                best = {"sheet": name, "header_row": ri + 1, "columns": h, "rows": len(rows)}
                break
        if best:
            break
    return {"sheets": len(sheets), "is_bom": best is not None, "header": best,
            "sheet_names": [s[0] for s in sheets]}


def parse(path: Path) -> dict[str, Any]:
    sheets = _sheet_rows(path)
    result: dict[str, Any] = {"lines": [], "declared_total": None, "meta": {}, "warnings": [], "units": {}}
    for sheet, rows in sheets:
        header_idx = None
        cols: dict[str, int] = {}
        for ri, row in enumerate(rows[:40]):
            h = _match_header([_norm(c) for c in row])
            if "profile" in h and ("qty" in h or "total_weight" in h) and len(h) >= 3:
                header_idx, cols = ri, h
                break
        if header_idx is None:
            continue
        # metadata above the header: "Total" value, project number, EXC ...
        for ri in range(header_idx):
            row = rows[ri]
            for ci, c in enumerate(row):
                n = _norm(c)
                if n in ("total", "total kg", "sum", "kokku") and ci + 1 < len(row) and _num(row[ci + 1]) is not None:
                    result["declared_total"] = {"value": _num(row[ci + 1]), "sheet": sheet,
                                                "cell": f"{get_column_letter(ci + 2)}{ri + 1}", "label": str(c).strip()}
                elif n in ("project number:", "project number", "project no", "project"):
                    if ci + 1 < len(row) and row[ci + 1] not in (None, ""):
                        result["meta"].setdefault(n.strip(":"), {"value": str(row[ci + 1]).strip(), "sheet": sheet,
                                                                  "cell": f"{get_column_letter(ci + 2)}{ri + 1}"})
                elif n == "exc" and ci + 1 < len(row) and row[ci + 1]:
                    result["meta"]["exc"] = {"value": str(row[ci + 1]).strip(), "sheet": sheet,
                                             "cell": f"{get_column_letter(ci + 2)}{ri + 1}"}
        header_cells = [_norm(c) for c in rows[header_idx]]
        tw_label = header_cells[cols["total_weight"]] if "total_weight" in cols else ""
        weight_in_tonnes = "(t)" in tw_label or tw_label.endswith(" t")
        len_label = header_cells[cols["length"]] if "length" in cols else ""
        length_in_m = "[m]" in len_label or "(m)" in len_label
        result["units"] = {"weight": "t" if weight_in_tonnes else "kg", "length": "m" if length_in_m else "mm"}
        for ri in range(header_idx + 1, len(rows)):
            row = rows[ri]

            def g(key: str) -> Any:
                i = cols.get(key)
                return row[i] if i is not None and i < len(row) else None

            prof = str(g("profile") or "").replace("\xa0", " ").strip()
            mat = str(g("material") or "").replace("\xa0", " ").strip()
            if not prof:
                continue  # subtotal / blank row
            if _norm(prof) in COLS["profile"] or _norm(prof) in ("total",):
                if _norm(prof) == "total" and _num(g("total_weight")) is not None and result["declared_total"] is None:
                    result["declared_total"] = {"value": _num(g("total_weight")), "sheet": sheet,
                                                "cell": f"{get_column_letter(cols['total_weight'] + 1)}{ri + 1}",
                                                "label": "Total row"}
                continue  # repeated header or grand total
            qty = _num(g("qty")) or 0.0
            length = _num(g("length"))
            unit_w = _num(g("unit_weight"))
            tot_w = _num(g("total_weight"))
            if weight_in_tonnes and tot_w is not None:
                tot_w *= 1000
            if length is not None and length_in_m:
                length *= 1000
            if tot_w is None and unit_w is not None:
                tot_w = unit_w * qty
            last_col = max(cols.values()) + 1
            result["lines"].append({
                "sheet": sheet, "row": ri + 1,
                "range": f"A{ri + 1}:{get_column_letter(last_col)}{ri + 1}",
                "profile": prof, "material": mat or None, "qty": qty, "length_mm": length,
                "unit_kg": unit_w, "kg": tot_w or 0.0,
                "position": str(g("position") or "").replace("\xa0", " ").strip() or None,
                "cells": [None if c is None else (c if isinstance(c, (int, float)) else str(c).replace("\xa0", " ").strip())
                          for c in row[:last_col]],
            })
        result["sheet"] = sheet
        result["header_row"] = header_idx + 1
        result["header"] = [str(c or "").replace("\xa0", " ").strip() for c in rows[header_idx]]
        break
    result["total_kg"] = round(sum(l["kg"] for l in result["lines"]), 2)
    return result


def sheet_window(path: Path, sheet: Optional[str], row: int, radius: int = 8, max_cols: int = 14) -> dict[str, Any]:
    """Cells around a row for the source panel."""
    sheets = _sheet_rows(path)
    rows = next((r for n, r in sheets if n == sheet), sheets[0][1] if sheets else [])
    start = max(1, row - radius)
    end = min(len(rows), row + radius)
    out = []
    for r in range(start, end + 1):
        vals = rows[r - 1][:max_cols]
        out.append({"row": r, "cells": ["" if v is None else (round(v, 3) if isinstance(v, float) else str(v).replace("\xa0", " ").strip())
                                         for v in vals]})
    width = max((len(x["cells"]) for x in out), default=0)
    return {"sheet": sheet or (sheets[0][0] if sheets else ""), "rows": out, "highlight_row": row,
            "columns": [get_column_letter(i + 1) for i in range(width)]}
