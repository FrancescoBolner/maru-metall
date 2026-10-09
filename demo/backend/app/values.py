"""Value registry: the single place where traceable values are created.

Rules enforced here:
- `extracted` values must carry at least one file reference;
- `calculated` values must carry a formula (and usually inputs / knowledge rows);
- `predicted` values must carry reasoning.
"""
from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from .models import Ref, V, ValueType


def slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", str(text)).strip("-").lower()
    return s[:60] or "x"


class Registry:
    def __init__(self) -> None:
        self.values: dict[str, V] = {}

    # ------------------------------------------------------------------ helpers
    def _unique(self, vid: str) -> str:
        if vid not in self.values:
            return vid
        i = 2
        while f"{vid}~{i}" in self.values:
            i += 1
        return f"{vid}~{i}"

    def get(self, vid: Optional[str]) -> Optional[V]:
        return self.values.get(vid) if vid else None

    def val(self, vid: Optional[str], default: Any = 0.0) -> Any:
        v = self.get(vid)
        return default if v is None or v.value is None else v.value

    def conf(self, ids: Iterable[str]) -> float:
        cs = [self.values[i].confidence for i in ids if i in self.values]
        return round(min(cs), 3) if cs else 1.0

    # ------------------------------------------------------------------ creators
    def extracted(self, vid: str, label: str, value: Any, unit: Optional[str], refs: list[Ref],
                  confidence: float = 0.97, **kw: Any) -> str:
        if not refs:
            raise ValueError(f"extracted value {vid} without a reference")
        vid = self._unique(vid)
        self.values[vid] = V(id=vid, label=label, value=value, unit=unit, type="extracted",
                             confidence=confidence, refs=refs, **kw)
        return vid

    def calculated(self, vid: str, label: str, value: Any, unit: Optional[str], formula: str,
                   inputs: Iterable[str] = (), kn: Iterable[str] = (), confidence: Optional[float] = None,
                   refs: Optional[list[Ref]] = None, **kw: Any) -> str:
        vid = self._unique(vid)
        inputs = [i for i in inputs if i]
        conf = confidence if confidence is not None else self.conf(inputs)
        self.values[vid] = V(id=vid, label=label, value=value, unit=unit, type="calculated",
                             confidence=conf, formula=formula, inputs=inputs, kn=list(kn),
                             refs=refs or [], **kw)
        return vid

    def predicted(self, vid: str, label: str, value: Any, unit: Optional[str], reasoning: str,
                  confidence: float = 0.6, question: Optional[str] = None, kn: Iterable[str] = (),
                  refs: Optional[list[Ref]] = None, inputs: Iterable[str] = (), **kw: Any) -> str:
        if not reasoning:
            raise ValueError(f"predicted value {vid} without reasoning")
        vid = self._unique(vid)
        self.values[vid] = V(id=vid, label=label, value=value, unit=unit, type="predicted",
                             confidence=confidence, reasoning=reasoning, question=question,
                             kn=list(kn), refs=refs or [], inputs=[i for i in inputs if i], **kw)
        return vid

    def put(self, v: V) -> str:
        v.id = self._unique(v.id)
        self.values[v.id] = v
        return v.id

    # ------------------------------------------------------------------ statistics
    def type_shares(self, ids: Optional[Iterable[str]] = None) -> dict[str, float]:
        pool = [self.values[i] for i in ids] if ids is not None else list(self.values.values())
        n = len(pool) or 1
        out: dict[str, float] = {"extracted": 0, "calculated": 0, "predicted": 0}
        for v in pool:
            out[v.type] += 1
        return {k: round(c / n, 3) for k, c in out.items()}


def kn_ref(kn_id: str, label: str, snippet: Optional[str] = None, sheet: Optional[str] = None,
           row: Optional[int] = None, path: Optional[str] = None) -> Ref:
    return Ref(kind="knowledge_row", kn_id=kn_id, label=label, snippet=snippet, sheet=sheet, row=row, path=path)


def fmt_num(x: Any, nd: int = 0) -> str:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    s = f"{f:,.{nd}f}"
    return s.replace(",", " ")
