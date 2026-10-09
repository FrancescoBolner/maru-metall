"""1D nesting of profile pieces on stock lengths: a per-project offcut estimate instead of a flat factor."""
from __future__ import annotations

from typing import Iterable


def stock_for(length: float, stocks: list[float]) -> float:
    for s in sorted(stocks):
        if length <= s:
            return s
    return length * 1.02  # special order: exact length + 2 %


def nest(lengths: Iterable[float], stocks: list[float], kerf: float = 5.0, min_reuse: float = 1000.0) -> dict[str, float]:
    """First-fit decreasing. Returns net length, bought length, reusable offcuts and scrap (mm)."""
    pieces = sorted((float(l) for l in lengths if l and l > 0), reverse=True)
    bars: list[list[float]] = []  # [capacity, remaining]
    for p in pieces:
        need = p + kerf
        for b in bars:
            if b[1] >= need:
                b[1] -= need
                break
        else:
            cap = stock_for(need, stocks)
            bars.append([cap, cap - need])
    net = sum(pieces)
    bought = sum(b[0] for b in bars)
    reusable = sum(b[1] for b in bars if b[1] >= min_reuse)
    scrap = bought - net - reusable
    return {"net": net, "bought": bought, "reusable": reusable, "scrap": scrap, "bars": len(bars),
            "factor": bought / net if net else 1.0}
