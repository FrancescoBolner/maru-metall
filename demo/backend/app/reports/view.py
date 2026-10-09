"""Turns a RunResult into formatted rows for the PDF and Excel reports (same numbers as the app)."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Optional

from ..models import Ref, RunResult, V
from ..settings import company_config

TYPE_LABEL = {"extracted": "Extracted", "calculated": "Calculated", "predicted": "Predicted"}


class Fmt:
    def __init__(self) -> None:
        nf = company_config().get("number_format", {})
        self.th = nf.get("thousands", " ")
        self.dec = nf.get("decimal", ",")

    def num(self, x: Any, nd: int = 0) -> str:
        if x is None or x == "":
            return "—"
        try:
            f = float(x)
        except (TypeError, ValueError):
            return str(x)
        s = f"{f:,.{nd}f}"
        return s.replace(",", "\x00").replace(".", self.dec).replace("\x00", self.th)

    def eur(self, x: Any, nd: int = 0) -> str:
        return self.num(x, nd)

    def pct(self, x: Any, nd: int = 0) -> str:
        try:
            return self.num(float(x) * 100, nd) + " %"
        except (TypeError, ValueError):
            return "—"


def ref_label(r: Ref) -> str:
    if r.kind == "knowledge_row":
        return f"Knowledge {r.kn_id}"
    if r.kind == "ifc_elements":
        return f"{r.path.split('/')[-1] if r.path else ''} · {len(r.guids)} element(s)"
    if r.kind == "pdf_page":
        return f"{(r.path or '').split('/')[-1].split('::')[-1]} · p. {r.page}"
    if r.kind == "sheet_cell":
        return f"{(r.path or '').split('/')[-1].split('::')[-1]} · {r.sheet or ''} {r.cell or ''}".strip()
    if r.kind == "email":
        return f"{(r.path or '').split('/')[-1][:40]} · e-mail"
    if r.kind == "user_edit":
        return "Estimator"
    return (r.label or r.path or "").split("/")[-1][:60]


def source_text(v: Optional[V]) -> str:
    if v is None:
        return ""
    parts = []
    if v.refs:
        parts.append("; ".join(dict.fromkeys(ref_label(r) for r in v.refs[:3])))
    if v.type == "calculated" and v.formula:
        parts.append(v.formula[:140])
    if v.kn:
        parts.append("KB " + ", ".join(v.kn[:4]))
    if v.type == "predicted" and v.reasoning:
        parts.append(v.reasoning[:160])
    return " · ".join(p for p in parts if p)


def build_view(res: RunResult) -> dict[str, Any]:
    f = Fmt()
    V_ = res.values
    cfg = company_config()

    def val(vid: Optional[str], default: Any = None) -> Any:
        v = V_.get(vid) if vid else None
        return default if v is None else v.value

    def vrow(vid: Optional[str], nd: int = 0) -> dict[str, Any]:
        v = V_.get(vid) if vid else None
        if v is None:
            return {"text": "—", "type": "", "conf": "", "src": "", "id": vid}
        txt = f.num(v.value, nd) if isinstance(v.value, (int, float)) and not isinstance(v.value, bool) else str(v.value)
        return {"text": txt, "type": TYPE_LABEL.get(v.type, v.type), "t": v.type, "conf": f"{v.confidence:.2f}",
                "src": source_text(v), "id": vid, "unit": v.unit or "", "edited": bool(v.edited), "conflict": bool(v.conflict)}

    s = res.summary
    facts = {fa.key: V_[fa.value_id] for fa in res.facts if fa.value_id in V_}

    def fact(key: str, default: str = "—") -> str:
        v = facts.get(key)
        if not v or v.value in (None, ""):
            return default
        return str(v.value).split(";")[0].strip()

    inquiry = fact("inquiry_date", "")
    cv = facts.get("client_contact")
    contact = max((p.strip() for p in str(cv.value).split(";")), key=len) if cv and cv.value else ""
    today = date.today()
    validity = int(cfg.get("offer", {}).get("validity_days", 14))
    # offer lines grouped by phase
    offer_rows = []
    phases = []
    for o in res.offer_lines:
        if o["phase"] not in phases:
            phases.append(o["phase"])
    n = 0
    steel_total = sum(val(o["price_id"], 0) for o in res.offer_lines)
    steel_kg = sum(o["kg"] for o in res.offer_lines)
    offer_rows.append({"no": "1.", "name": "Steel structures manufacturing", "surface": "", "amount": f.num(steel_kg), "unit": "kg",
                       "price": f.eur(steel_total), "unit_price": "", "bold": True})
    for ph in phases:
        if ph:
            offer_rows.append({"no": "", "name": f"Phase {ph}", "surface": "", "amount": "", "unit": "", "price": "", "unit_price": "",
                               "sub": True})
        for o in [x for x in res.offer_lines if x["phase"] == ph]:
            n += 1
            offer_rows.append({"no": f"1.{n}", "name": o["label"], "surface": o["surface"], "amount": f.num(o["kg"]), "unit": "kg",
                               "price": f.eur(val(o["price_id"])), "unit_price": f.num(o["unit_price"], 2)})
    k = 1
    for x in res.cost.get("extras", []):
        k += 1
        qty = val(x.get("qty_id")) if x.get("qty_id") else x.get("qty", 1)
        offer_rows.append({"no": f"{k}.", "name": x["label"], "surface": "", "amount": f.num(qty), "unit": x.get("unit", "set"),
                           "price": f.eur(val(x["sale_id"])),
                           "unit_price": f.num(val(x["sale_id"], 0) / qty, 2) if qty and x.get("unit") == "pcs" else "", "bold": True})
    k += 1
    ti = res.cost.get("transport_info", {})
    offer_rows.append({"no": f"{k}.", "name": "Transport: " + "; ".join(ti.get("desc", [])).replace(" × ", " × "), "surface": "",
                       "amount": "1", "unit": "set", "price": f.eur(val(res.cost["transport"])), "unit_price": "", "bold": True})
    excludes = list(cfg.get("offer", {}).get("standard_excludes", []))
    for a in res.assumptions:
        if a["kind"] == "exclusion":
            excludes.append(a["text"])
    if res.cost.get("fire_option") and not any("fire" in e.lower() for e in excludes):
        excludes.append("Fire protection painting")
    remarks = list(cfg.get("offer", {}).get("standard_remarks", []))
    exc = fact("execution_class", "EXC2")
    remarks = [r.replace("execution class as stated", f"execution class {exc}") for r in remarks]
    pred = [a for a in res.assumptions if a["kind"] == "predicted"]
    client_assumptions = []
    for a in pred:
        v = V_.get(a.get("value_id"))
        if v is None or not str(v.id).startswith(("fact.", "allow.", "cat.", "spec.")):
            continue  # internal norms (weld lengths, holes) stay in the internal report
        client_assumptions.append(f"{v.label}: {f.num(v.value) if isinstance(v.value, (int, float)) else v.value}"
                                  f"{' ' + v.unit if v.unit and isinstance(v.value, (int, float)) else ''} (assumed, to be confirmed)")
    options = []
    if res.cost.get("fire_option"):
        fo = res.cost["fire_option"]
        options.append(f"Fire protection {fo['rating']} on all painted steel ({f.num(fo['area'])} m²): + € {f.eur(fo['total'])}")
    fopt = None
    for x in res.values.values():
        if x.id == "x.bolts.cost" and x.reasoning and x.reasoning.startswith("Not in the base price"):
            fopt = x
    if fopt:
        options.append(f"Fasteners for steel-to-steel connections (if required): + € {f.eur(fopt.value)}")
    files_used = [e for e in res.filemap.entries if e.used_for and e.status in ("metal-relevant", "partly-relevant")]
    qty_files = [e.name for e in files_used if any("quantities" in u and "cross" not in u for u in e.used_for)]
    # sections for the internal report
    cats = []
    for c in res.categories:
        cats.append({"name": c.name, "kg": vrow(c.kg_id), "pieces": vrow(c.pieces_id), "area": vrow(c.area_id, 1),
                     "plate": f.pct(val(c.plate_share_id)), "surface": vrow(c.surface_id), "included": c.included,
                     "longest": f.num((c.longest_mm or 0) / 1000, 1)})
    lines = []
    for l in res.lines:
        v = V_[l.kg_id]
        lines.append({"category": l.category + (f" · ph {l.phase}" if l.phase else ""), "profile": l.profile, "grade": l.grade or "",
                      "pieces": vrow(l.pieces_id), "kg": vrow(l.kg_id, 1), "area": vrow(l.area_id, 1),
                      "length": vrow(l.length_id, 1) if l.length_id else {"text": "—"},
                      "type": TYPE_LABEL[v.type], "t": v.type, "conf": f"{v.confidence:.2f}", "ref": source_text(v)[:90]})
    hours = []
    for h in res.hours:
        hv = V_.get(h.hours_id)
        hours.append({"op": h.operation, "cat": h.category, "qty": vrow(h.quantity_id, 0) if h.quantity_id else {"text": "—"},
                      "hours": vrow(h.hours_id, 1), "norm": h.norm, "kn": ", ".join(h.kn[:4]), "costed": h.costed_in})
    ops = [{"op": op, "hours": vrow(i, 1)} for op, i in res.hours_totals.get("by_operation", {}).items()]
    paint = []
    for p in res.paint:
        paint.append({"cat": p.category, "system": p.system, "area": vrow(p.area_id, 1), "coats": p.coats,
                      "litres": [{"product": x["product"], "l": vrow(x["value_id"], 0)} for x in p.litres],
                      "hours": vrow(p.hours_id, 1), "cost": vrow(p.cost_id, 0), "kn": ", ".join(p.kn)})
    cost_groups = [{"label": V_[i].label, "v": vrow(i, 0)} for g, i in res.cost.get("groups", {}).items()]
    cost_cats = []
    for c in res.categories:
        if not c.included:
            continue
        from ..values import slug
        base = f"c.{slug(c.name)}"
        cost_cats.append({"name": c.name, "material": vrow(f"{base}.material"), "labour": vrow(f"{base}.labour"),
                          "surface": vrow(f"s.{slug(c.name)}.cost"), "packaging": vrow(f"{base}.packaging"),
                          "sale": vrow(f"{base}.sale"), "eur_kg": f.num(val(f"{base}.sale", 0) / max(val(c.kg_id, 1), 1), 2)})
    quick = [{"cat": q["category"], "eur_t": vrow(q["eur_t_id"]), "sale": vrow(q["sale_id"]), "hours": vrow(q["hours_id"], 1),
              "ref": q["ref_project"], "kn": q["kn"]} for q in res.cost.get("quick_lines", [])]
    carbon = res.carbon
    co2_groups = [{"label": g["label"], "t": f.num(g["tonnes"], 1), "share": vrow(g["share_id"], 2), "co2": vrow(g["co2_id"], 1),
                   "required": f.pct(g["required"]) if g.get("required") is not None else "—",
                   "planned": f.pct(g["recycled_planned"]), "ok": g["compliant"]} for g in carbon.get("groups", [])]
    co2_parts = [{"label": V_[i].label, "v": vrow(i, 1)} for i in (carbon.get("steel_id"), carbon.get("paint_id"), carbon.get("galv_id"),
                                                                 carbon.get("transport_id"), carbon.get("workshop_id")) if i]
    co2_opts = [{"label": o["label"], "v": vrow(o["delta_id"], 1)} for o in carbon.get("options", [])]
    risks = [{"rank": r.rank, "sev": r.severity, "title": r.title, "detail": r.detail,
              "refs": "; ".join(dict.fromkeys(ref_label(x) for x in r.refs[:3])), "q": r.question or ""} for r in res.risks]
    preds = [V_[a["value_id"]] for a in res.assumptions if a.get("kind") == "predicted" and a.get("value_id") in V_]
    files = [{"path": e.path, "kind": e.kind, "size": f.num(e.size / 1024, 0) + " kB", "pages": e.pages or e.sheets or e.elements or "",
              "status": e.status, "reason": e.reason, "by": e.decided_by, "read": e.read_by or "", "error": e.error or ""}
             for e in res.filemap.entries]
    feats = {}
    for g, ids in res.features.items():
        feats[g] = [{"label": V_[i].label, "v": vrow(i, 1 if V_[i].unit in ('m²', 'm') else 0)} for i in ids if i in V_]
    return {
        "f": f, "cfg": cfg, "res": res, "s": s, "val": val, "vrow": vrow,
        "today": today.strftime("%d.%m.%Y"), "valid_until": (today + timedelta(days=validity)).strftime("%d.%m.%Y"),
        "client_company": res.company, "client_contact": contact,
        "client_email": fact("client_email", ""), "project_title": res.project_name,
        "project_address": fact("delivery_address", "to be confirmed"), "inquiry_date": inquiry,
        "address_conflict": bool(facts.get("delivery_address") and facts["delivery_address"].conflict),
        "delivery_terms": fact("delivery_terms", "DAP"), "delivery_time": fact("delivery_time", "to be agreed"),
        "offer_rows": offer_rows, "total": f.eur(val(s["price_id"])), "excludes": list(dict.fromkeys(excludes)),
        "includes": cfg.get("offer", {}).get("includes", []), "remarks": remarks, "client_assumptions": client_assumptions,
        "options": options, "questions": [q.text for q in res.questions], "qty_files": qty_files,
        "cats": cats, "lines": lines, "hours": hours, "ops": ops, "paint": paint, "cost_groups": cost_groups,
        "cost_cats": cost_cats, "quick": quick, "co2_groups": co2_groups, "co2_parts": co2_parts, "co2_opts": co2_opts,
        "co2_flags": carbon.get("flags", []), "risks": risks, "preds": preds, "files": files, "features": feats,
        "assumptions": res.assumptions, "level": res.filemap.level, "level_reason": res.filemap.level_reason,
    }
