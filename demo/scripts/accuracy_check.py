"""Accuracy check: run the assistant on the two example projects (offline rules, no AI key needed)
and compare with Maru Metall's real offers and cost workbooks (data/reference/maru_actuals.json).

    python scripts/accuracy_check.py            → prints a table, writes docs/accuracy.md and data/reference/accuracy_latest.json

Nothing is written to the project database: the pipeline is called directly, no revision is created.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.models import Override  # noqa: E402
from app.pipeline.runner import run_pipeline  # noqa: E402
from app.service import project_ref  # noqa: E402

REF = json.loads((ROOT / "data" / "reference" / "maru_actuals.json").read_text(encoding="utf-8"))


def run(pid: str, overrides: list[Override] | None = None):
    ref = project_ref(pid)
    t0 = time.time()
    res, _ = run_pipeline(ref, 1, f"{ref.short}_accuracy", f"{ref.short}_accuracy", overrides or [], None, "")
    return res, time.time() - t0


def v(res, vid: str) -> float:
    x = res.values.get(vid)
    return float(x.value) if x is not None and isinstance(x.value, (int, float)) else 0.0


def pct(a: float, b: float) -> str:
    return f"{(a - b) / b * 100:+.1f} %" if b else "n/a"


def main() -> int:
    rows_md: list[str] = []
    out: dict[str, dict] = {}
    for pid, m in REF["projects"].items():
        res, secs = run(pid)
        wb = m["workbook"]
        s = res.summary
        steel_sale = v(res, "total.steel_sale")
        extras = {x["label"]: v(res, x["sale_id"]) for x in res.cost.get("extras", [])}
        maru_same_margin = None
        if abs(m["margins"]["material"] - float(v(res, "param.margin_material"))) > 1e-6:
            ovs = [Override(target="param", key="margin_material", value=m["margins"]["material"]),
                   Override(target="param", key="margin_production", value=m["margins"]["production"])]
            res_m, _ = run(pid, ovs)
            maru_same_margin = v(res_m, s["price_id"])
        comp = [
            ("Total price €", v(res, s["price_id"]), m["total_price"]),
            ("Steel structures manufacturing €", steel_sale, m["manufacturing_price"]),
            ("Takeoff kg (steel in scope)", v(res, "total.kg"), m["manufacturing_kg"]),
            ("Workshop hours (metal work)", v(res, s["metal_hours_id"]), wb["metal_hours"]),
            ("Weld length m", v(res, "feat.ops.weld"), wb["welding_m"]),
            ("Labour €", v(res, s["labour_cost_id"]), wb["labour_eur"]),
            ("Material € (before margin)", v(res, "total.cost.material"), wb["material_eur"]),
            ("Surface treatment € (before margin)", v(res, "total.cost.surface-treatment"), wb["surface_eur"]),
            ("Painted / galvanised area m²", v(res, "total.area"), wb["painted_area_m2"]),
            ("Transport €", v(res, "t.cost"), m["transport"]),
        ]
        if maru_same_margin is not None:
            comp.insert(1, (f"Total price € with Maru's margins ({m['margins']['material']:.2f})", maru_same_margin, m["total_price"]))
        out[pid] = {"name": m["name"], "seconds": round(secs, 1), "provider": res.ai.get("provider"),
                    "rows": [{"what": a, "assistant": round(b, 1), "maru": round(c, 1), "diff": pct(b, c)} for a, b, c in comp],
                    "assistant_extras": extras, "maru_separate_lines": m["separate_lines"],
                    "transport_assistant": res.cost.get("transport_info", {}).get("desc"), "transport_maru": m["transport_trucks"]}
        print(f"\n{m['name']}  ({m['offer']}) — pipeline {secs:.1f} s, AI provider: {res.ai.get('provider')}")
        print(f"{'':52} {'assistant':>12} {'Maru':>12} {'diff':>9}")
        for a, b, c in comp:
            print(f"{a:52} {b:12,.0f} {c:12,.0f} {pct(b, c):>9}")
        rows_md.append(f"\n### {m['name']} — Maru offer {m['offer']}\n")
        rows_md.append(f"Pipeline time {secs:.1f} s (offline rules provider, cached file parsing).\n")
        rows_md.append("| | Assistant | Maru | Difference |\n|---|---:|---:|---:|")
        for a, b, c in comp:
            rows_md.append(f"| {a} | {b:,.0f} | {c:,.0f} | {pct(b, c)} |".replace(",", " "))
        rows_md.append(f"\nTransport — assistant: {'; '.join(out[pid]['transport_assistant'] or [])}; Maru: {m['transport_trucks']}.")
        if extras:
            rows_md.append("Other lines — assistant: " + "; ".join(f"{k} € {x:,.0f}".replace(",", " ") for k, x in extras.items())
                           + ". Maru: " + "; ".join(f"{k} € {x:,.0f}".replace(",", " ") for k, x in m["separate_lines"].items()) + ".")
    (ROOT / "data" / "reference" / "accuracy_latest.json").write_text(
        json.dumps({"date": datetime.now().isoformat(timespec="seconds"), "projects": out}, indent=1, ensure_ascii=False), encoding="utf-8")
    md = ["# Accuracy check — assistant vs Maru Metall's real offers",
          f"\nGenerated by `scripts/accuracy_check.py` on {datetime.now():%d.%m.%Y %H:%M}. "
          "Inputs: only the client files in `drives/client/` (\"01 - Input for pricing\") and the knowledge file. "
          "Maru's numbers: `data/reference/maru_actuals.json` (offer PDFs and cost workbooks in `materials/`).",
          *rows_md,
          "\nSee README → *Accuracy and known gaps* for the reasons behind each difference."]
    (ROOT / "docs" / "accuracy.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\nWritten: docs/accuracy.md, data/reference/accuracy_latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
