"""Stage 6 — Quote: assemble the report model (summary, sections, internal + client content)."""
from __future__ import annotations

import re
from typing import Any

from ..knowledge.base import normalize_system
from ..models import Fact, Ref, RunResult
from ..ai.schemas import FACT_CATALOG
from ..values import fmt_num
from .context import RunContext


def build_result(ctx: RunContext) -> RunResult:
    reg = ctx.reg
    d = ctx.data
    tot = d["totals"]
    facts_ids = d["facts"]["ids"]
    facts = [Fact(key=k, group=FACT_CATALOG[k][0] if k in FACT_CATALOG else "specs", label=reg.values[v].label, value_id=v)
             for k, v in facts_ids.items()]
    # scope items as values
    scope_ids = []
    seen = set()
    for i, s in enumerate(d["facts"]["scope"]):
        key = (s["status"], re.sub(r"[^a-z0-9]", "", s["item"].lower())[:40])
        if key in seen:
            continue
        seen.add(key)
        val = s["status"] + (f" ({s['quantity']})" if s["quantity"] else "")
        scope_ids.append(reg.extracted(f"scope.{len(scope_ids) + 1}", s["item"][:90], val, None, [s["ref"]], confidence=0.85,
                                       group="scope"))
    # operations feature group
    ops = []
    hr = d["hours_rows"]
    for op, label in (("Plasma cutting", "Cut edges"), ("Sawing", "Saw cuts"), ("Drilling", "Holes"), ("Welding", "Weld length (a5)"),
                      ("Fitting / assembly", "Parts to fit")):
        q_ids = [h.quantity_id for h in hr if h.operation == op and h.quantity_id]
        if q_ids:
            unit = reg.values[q_ids[0]].unit
            ops.append(reg.calculated(f"feat.ops.{op[:4].lower()}", label, round(sum(reg.val(i) for i in q_ids), 0), unit,
                                      "Σ over categories", inputs=q_ids, group="operations"))
    asm_total = sum(c.assemblies for c in d["categories"] if c.included)
    ops.append(reg.calculated("feat.ops.asm", "Assemblies", asm_total, "pcs", "assemblies in the takeoff", group="operations"))
    cats = [c for c in d["categories"] if c.included]  # totals cover the scope only
    total_kg = reg.val("total.kg")
    plate_kg = sum(reg.val(c.plate_share_id) * reg.val(c.kg_id) for c in cats)
    ps_id = reg.calculated("total.plate_share", "Plate share", round(plate_kg / total_kg, 3) if total_kg else 0, "share",
                           "plate kg ÷ total kg", inputs=[c.plate_share_id for c in cats] + ["total.kg"], group="quantities")
    pcs_id = reg.calculated("total.pieces", "Number of pieces", sum(reg.val(c.pieces_id) for c in cats), "pcs",
                            "Σ category pieces", inputs=[c.pieces_id for c in cats], group="quantities")
    area_id = reg.calculated("total.area", "Surface area (paint + galvanising)", round(sum(reg.val(c.area_id) for c in cats), 1), "m²",
                             "Σ category areas", inputs=[c.area_id for c in cats], group="quantities")
    features = {
        "quantities": ["total.kg"] + [c.kg_id for c in cats] + [ps_id, area_id, pcs_id, d.get("longest_id")],
        "operations": ops,
        "specs": [v for k, v in facts_ids.items() if FACT_CATALOG.get(k, ("specs",))[0] == "specs"],
        "scope": [v for k, v in facts_ids.items() if FACT_CATALOG.get(k, ("",))[0] == "scope"] + scope_ids,
        "commercial": [v for k, v in facts_ids.items() if FACT_CATALOG.get(k, ("",))[0] == "commercial"],
        "logistics": [v for k, v in facts_ids.items() if FACT_CATALOG.get(k, ("",))[0] == "logistics"] + [d["transport"]["trucks_id"]],
    }
    features = {k: [x for x in v if x] for k, v in features.items()}
    # assumptions & exclusions
    assumptions = []
    for v in reg.values.values():
        if v.type == "predicted" and not v.edited and v.id not in ("spec.surface_system",):
            assumptions.append({"kind": "predicted", "text": f"{v.label}: {fmt_num(v.value, 0) if isinstance(v.value, (int, float)) else v.value}"
                                f"{(' ' + v.unit) if v.unit and isinstance(v.value, (int, float)) else ''} — {v.reasoning}",
                                "value_id": v.id, "question": v.question})
    for s in d["facts"]["scope"]:
        if s["status"] == "excluded":
            assumptions.append({"kind": "exclusion", "text": f"Excluded by the client: {s['item']}", "refs": [s["ref"].model_dump()]})
        elif s["status"] == "option":
            assumptions.append({"kind": "option", "text": f"Separate price line requested: {s['item']}", "refs": [s["ref"].model_dump()]})
    if d.get("fire_option"):
        assumptions.append({"kind": "exclusion", "text": "Fire protection painting is not included (see risks for the option price)",
                            "value_id": d["fire_option"]["vid"]})
    for c in d["categories"]:
        if not c.included:
            assumptions.append({"kind": "exclusion", "text": f"{c.name}: out of scope (estimator)", "value_id": c.kg_id})
    assumptions.append({"kind": "note", "text": d.get("remnant_note", "")})
    tr = d["transport"]
    assumptions.append({"kind": "note", "text": f"Transport region: {tr['region']} ({tr['why']}): " + "; ".join(tr["desc"]),
                        "value_id": tr["cost_id"]})
    seen_text: dict[str, dict[str, Any]] = {}
    for a in assumptions:  # the same exclusion stated in two files is one assumption with two references
        key = (a.get("text") or "").strip().lower()
        if key in seen_text:
            seen_text[key].setdefault("refs", []).extend(a.get("refs") or [])
        else:
            seen_text[key] = a
    assumptions = [a for a in seen_text.values() if a.get("text")]
    # summary
    risks = d["risks"]
    report_values = set()
    for c in cats:
        report_values.update([c.kg_id, c.area_id, c.surface_id])
    for l in d["lines"]:
        report_values.update([l.kg_id, l.pieces_id])
    for h in d["hours_rows"]:
        report_values.update([h.hours_id] + ([h.quantity_id] if h.quantity_id else []))
    report_values.update(facts_ids.values())
    report_values.update(scope_ids)
    shares = reg.type_shares([i for i in report_values if i in reg.values])
    price = reg.val(tot["price"])
    pred_euro = 0.0
    for x in d["extra_lines"]:
        v = reg.values.get(x.get("qty_id") or x["sale_id"])
        if v is not None and v.type == "predicted":
            pred_euro += reg.val(x["sale_id"])
    weld_pred = sum(reg.val(h.hours_id) for h in d["hours_rows"] if h.operation == "Welding") * reg.val(d["params"]["labour_rate"]) * \
        reg.val(d["params"]["margin_production"])
    summary = {
        "price_id": tot["price"], "low_id": tot["price_low"], "high_id": tot["price_high"], "method": tot["method"],
        "detailed_id": tot["detailed"], "quick_id": tot["quick"], "gap_id": tot["gap"],
        "tonnes_id": "total.kg", "pieces_id": pcs_id, "plate_share_id": ps_id, "longest_id": d.get("longest_id"),
        "hours_id": tot["hours"], "metal_hours_id": tot["metal_hours"], "labour_cost_id": tot["labour_cost"],
        "paint_litres_id": tot["paint_litres"], "paint_cost_id": tot["paint_cost"], "galv_cost_id": tot.get("galv_cost"),
        "painted_area_id": tot["painted_area"], "co2_id": d["carbon"]["total_id"], "co2_intensity_id": d["carbon"]["intensity_id"],
        "confidence": shares,
        "predicted_share_of_price": round((pred_euro + weld_pred) / price, 3) if price else 0,
        "top_risks": [r.id for r in risks[:5]], "questions": len(d["questions"]),
        "eur_per_kg": round(price / total_kg, 3) if total_kg else None,
        "level": d["filemap"].level, "level_reason": d["filemap"].level_reason,
        "quantity_source": d.get("quantity_source"), "checks": d.get("checks", []),
    }
    return RunResult(
        project_id=ctx.project.id, company=ctx.project.company, project_name=ctx.project.name,
        project_path=str(ctx.project.root), revision=ctx.revision, quote_number=ctx.quote_number, report_name=ctx.report_name,
        timings=ctx.timings, ai=ctx.usage.as_dict() | ctx.provider.describe(), filemap=d["filemap"], facts=facts,
        lines=d["lines"], categories=cats, features=features, hours=d["hours_rows"],
        hours_totals={"total": tot["hours"], "metal": tot["metal_hours"], "quick": tot["quick_hours"], "by_operation": tot["op_hours"],
                      "by_category": tot["cat_hours"], "labour_cost": tot["labour_cost"]},
        paint=d["paint_rows"], paint_totals={"litres": tot["paint_litres"], "by_product": tot["litres_by_product"], "cost": tot["paint_cost"],
                                             "galv_cost": tot.get("galv_cost"), "area": tot["painted_area"]},
        material={"lines": d["mat_lines"], "waste_kg": tot["waste_kg"], "reusable_kg": tot["reusable_kg"], "bought_kg": tot["bought_kg"],
                  "waste_share": tot["waste_share"], "bolts_kg": tot.get("bolts_kg"), "remnant_note": d.get("remnant_note"),
                  "price_list_id": d["params"]["price_list_id"]},
        cost={"lines": [c.model_dump() for c in d["cost_lines"]], "groups": tot["groups"], "margin": tot["margin"],
              "steel_sale": tot["steel_sale"], "extras": d["extra_lines"], "transport": tot["transport"], "detailed": tot["detailed"],
              "quick": tot["quick"], "quick_lines": d["quick"], "gap": tot["gap"], "method": tot["method"], "price": tot["price"],
              "low": tot["price_low"], "high": tot["price_high"], "params": {k: v for k, v in d["params"].items() if isinstance(v, str) and k != "price_list"},
              "fire_option": d.get("fire_option"), "transport_info": {k: v for k, v in d["transport"].items()}},
        offer_lines=d["offer_lines"], carbon=d["carbon"], risks=risks, questions=d["questions"], assumptions=assumptions,
        summary=summary, values=reg.values, overrides=ctx.overrides, knowledge={"file": ctx.kb.source_name, "version": ctx.kb.version},
        warnings=ctx.warnings,
    )
