"""Carbon balance (EU requirement): CO2e by steel origin + paint / galvanising + transport, options and flags.
Factors come from the knowledge file and are placeholders until supplier EPDs (EN 15804) are available."""
from __future__ import annotations

import re
from typing import Any

from ..knowledge.base import normalize_system
from ..models import Ref, Risk
from ..values import fmt_num
from .context import RunContext

GROUPS = {"rolled": ("IPE", "HEA", "HEB", "HEM", "UPE", "UNP", "L", "T", "D", "REBAR"),
          "hollow": ("RHS", "CHS"),
          "plates": ("PL", "FL", "WI", "OTHER")}
GROUP_LABEL = {"rolled": "Rolled sections", "hollow": "Hollow sections", "plates": "Plates and welded sections"}


def _group(family: str) -> str:
    for g, fams in GROUPS.items():
        if family in fams:
            return g
    return "plates"


def parse_requirement(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for m in re.finditer(r"(\d{1,3})\s*%\s*([a-z ]*?)(?:profiles|sections|steel|plates)", text.lower()):
        pct = float(m.group(1)) / 100
        words = m.group(2)
        if "hollow" in words:
            out["hollow"] = pct
        elif "rolled" in words:
            out["rolled"] = pct
        elif "plate" in words:
            out["plates"] = pct
        else:
            out.setdefault("all", pct)
    if "all" in out:
        for g in GROUPS:
            out.setdefault(g, out["all"])
        out.pop("all")
    return out


def run_carbon(ctx: RunContext) -> None:
    kb, reg = ctx.kb, ctx.reg
    tot = ctx.data["totals"]
    f_bf, bf_id = kb.co2("steel_bf_bof", 2.0)
    f_eaf, eaf_id = kb.co2("steel_eaf", 0.6)
    f_re, re_id = kb.co2("steel_reused", 0.1)
    rc_eaf, rce_id = kb.co2("recycled_content_eaf", 0.95)
    rc_bf, rcb_id = kb.co2("recycled_content_bf", 0.15)
    market = {"rolled": kb.co2("eaf_share_rolled", 0.6), "hollow": kb.co2("eaf_share_hollow", 0.3), "plates": kb.co2("eaf_share_plates", 0.3)}
    req_v = reg.get(ctx.data["facts"]["ids"].get("recycled_content"))
    req = parse_requirement(str(req_v.value)) if req_v else {}
    # tonnes bought per group
    bought = {g: 0.0 for g in GROUPS}
    by_cat_rolled = {"Columns": 0.0, "Beams": 0.0}
    for m in ctx.data.get("mat_lines", []):
        fam = re.match(r"[A-Z]+", m["profile"].upper())
        from ..parsers.profiles import parse_profile
        g = _group(parse_profile(m["profile"]).family)
        bought[g] += m["kg"] * m["factor"] / 1000
        if m["category"] in by_cat_rolled and g in ("rolled", "hollow"):
            by_cat_rolled[m["category"]] += m["kg"] * m["factor"] / 1000
    groups_out = []
    steel_ids = []
    plan_total = 0.0
    all_eaf_total = 0.0
    market_total = 0.0
    for g in GROUPS:
        t = bought[g]
        if t <= 0:
            continue
        mk, mk_id = market[g]
        need = None
        if g in req:
            need = min(max((req[g] - rc_bf) / (rc_eaf - rc_bf), 0.0), 1.0)
        s = max(need or 0.0, mk)
        co2 = t * (s * f_eaf + (1 - s) * f_bf)
        plan_total += co2
        all_eaf_total += t * f_eaf
        market_total += t * (mk * f_eaf + (1 - mk) * f_bf)
        recycled = s * rc_eaf + (1 - s) * rc_bf
        refs = req_v.refs[:2] if (req_v and g in req) else []
        sid = reg.calculated(f"co2.share.{g}", f"{GROUP_LABEL[g]} — EAF (scrap-based) share planned", round(s, 3), "share",
                             (f"required recycled content {req[g] * 100:.0f} % → EAF share ≥ ({req[g]:.2f} − {rc_bf}) ÷ ({rc_eaf} − {rc_bf}) = {need:.2f}; "
                              f"market share {mk}" if g in req else f"no requirement: market share {mk}"),
                             inputs=[req_v.id] if (req_v and g in req) else [], kn=[mk_id, rce_id, rcb_id], refs=refs, group="carbon")
        cid = reg.calculated(f"co2.steel.{g}", f"{GROUP_LABEL[g]} — CO2e", round(co2, 1), "t CO2e",
                             f"{t:.1f} t bought × ({s:.2f} × {f_eaf} + {1 - s:.2f} × {f_bf}) t CO2e/t", inputs=[sid, tot["bought_kg"]],
                             kn=[eaf_id, bf_id], group="carbon")
        steel_ids.append(cid)
        groups_out.append({"group": g, "label": GROUP_LABEL[g], "tonnes": round(t, 1), "share_id": sid, "co2_id": cid,
                           "required": req.get(g), "recycled_planned": round(recycled, 3),
                           "compliant": (recycled >= req[g] - 1e-9) if g in req else None})
    steel_co2 = reg.calculated("co2.steel", "Steel (by production route)", round(sum(reg.val(i) for i in steel_ids), 1), "t CO2e",
                               "Σ groups", inputs=steel_ids, group="carbon")
    f_paint, p_id = kb.co2("paint", 3.0)
    paint_co2 = reg.calculated("co2.paint", "Paint", round(reg.val(tot["paint_litres"]) * f_paint / 1000, 2), "t CO2e",
                               f"litres × {f_paint} kg/l ÷ 1000", inputs=[tot["paint_litres"]], kn=[p_id], group="carbon")
    zn_up, zn_id = kb.co2("zinc_uptake", 0.6)
    f_zn, fz_id = kb.co2("zinc", 3.5)
    hdg_area = sum(reg.val(c.area_id) for c in ctx.data["categories"] if c.included and normalize_system(str(reg.val(c.surface_id))) == "HDG")
    galv_co2 = reg.calculated("co2.galv", "Hot-dip galvanising", round(hdg_area * zn_up * f_zn / 1000, 2), "t CO2e",
                              f"galvanised area {hdg_area:.0f} m² × {zn_up} kg zinc/m² × {f_zn} kg CO2e/kg ÷ 1000",
                              inputs=[c.area_id for c in ctx.data["categories"] if c.included], kn=[zn_id, fz_id], group="carbon")
    tr = ctx.data["transport"]
    f_tk, tk_id = kb.co2("truck_km", 0.9)
    n_tr = reg.val(tr["trucks_id"])
    transport_co2 = reg.calculated("co2.transport", "Transport", round(n_tr * tr["distance_km"] * f_tk / 1000, 2), "t CO2e",
                                   f"{n_tr:g} trucks × {tr['distance_km']:g} km × {f_tk} kg CO2e/km ÷ 1000",
                                   inputs=[tr["trucks_id"]], kn=[tk_id] + [r.id for r in kb.rows("Transport") if r["region"] == tr["region"]][:1],
                                   group="carbon")
    f_ws, ws_id = kb.co2("workshop", 0.03)
    tonnes = reg.val("total.kg") / 1000
    ws_co2 = reg.calculated("co2.workshop", "Workshop energy", round(tonnes * f_ws, 2), "t CO2e", f"{tonnes:.1f} t × {f_ws} t CO2e/t",
                            inputs=["total.kg"], kn=[ws_id], group="carbon")
    parts_ids = [steel_co2, paint_co2, galv_co2, transport_co2, ws_co2]
    total = reg.calculated("co2.total", "Carbon balance (A1-A4, placeholder factors)", round(sum(reg.val(i) for i in parts_ids), 1),
                           "t CO2e", "steel + paint + galvanising + transport + workshop", inputs=parts_ids, group="carbon")
    intensity = reg.calculated("co2.intensity", "Carbon intensity", round(reg.val(total) / tonnes, 3) if tonnes else 0, "t CO2e/t",
                               "total ÷ tonnes of steel", inputs=[total, "total.kg"], group="carbon")
    # options
    other = sum(reg.val(i) for i in parts_ids[1:])
    options = []
    opt_eaf = reg.calculated("co2.opt.eaf", "Option: all steel from EAF (scrap-based) mills", round(all_eaf_total + other - reg.val(total), 1),
                             "t CO2e", "difference vs plan if every group is bought as EAF steel", inputs=[total], kn=[eaf_id], group="carbon")
    options.append({"label": "All steel from EAF (scrap-based) mills", "delta_id": opt_eaf})
    reuse_t = by_cat_rolled["Columns"] + by_cat_rolled["Beams"]
    if reuse_t > 0:
        # replace planned route of those tonnes with reused sections
        rolled_g = next((g for g in groups_out if g["group"] == "rolled"), None)
        s_r = reg.val(rolled_g["share_id"]) if rolled_g else market["rolled"][0]
        planned = reuse_t * (s_r * f_eaf + (1 - s_r) * f_bf)
        delta = reuse_t * f_re - planned
        opt_re = reg.calculated("co2.opt.reuse", "Option: reclaimed sections for standard columns and beams", round(delta, 1), "t CO2e",
                                f"{reuse_t:.1f} t of rolled/hollow columns and beams × ({f_re} − planned route) t CO2e/t",
                                inputs=[total], kn=[re_id], group="carbon")
        options.append({"label": f"Reclaimed sections for standard columns and beams ({reuse_t:.0f} t), if the client accepts",
                        "delta_id": opt_re})
    if req:
        opt_mk = reg.calculated("co2.opt.market", "Comparison: market steel mix (no recycled requirement)",
                                round(market_total + other - reg.val(total), 1), "t CO2e",
                                "difference vs plan with the usual market mix", inputs=[total], kn=[m[1] for m in market.values()],
                                group="carbon")
        options.append({"label": "Without the recycled-content requirement (market mix)", "delta_id": opt_mk})
    # flags
    flags = []
    rules = ctx.company_cfg.get("country_rules", {})
    cv = reg.get(ctx.data["facts"]["ids"].get("delivery_country"))
    country = str(cv.value)[:2].upper() if cv and cv.value else None
    placeholders = [r.id for r in kb.rows("CO2_factors") if r["status"] == "placeholder"]
    flags.append({"flag": "Missing product data", "detail": f"No supplier EPD (EN 15804) for steel, paint and zinc: {len(placeholders)} "
                  "placeholder factors are used.", "reference": "EN 15804", "severity": "medium", "kn": placeholders[:6]})
    cpr = ctx.company_cfg.get("cpr", {})
    flags.append({"flag": "No carbon declaration", "detail": f"The revised EU Construction Products Regulation phases in GWP declarations "
                  f"from {cpr.get('gwp_declaration_from', '2026')}: products here have no declared GWP yet.", "reference": "Revised CPR",
                  "severity": "medium", "kn": []})
    rule = rules.get(country or "", {})
    lim = rule.get("carbon_limit_t_per_t_steel")
    if lim is not None and reg.val(intensity) > float(lim):
        flags.append({"flag": "Carbon above limit", "detail": f"{reg.val(intensity):.2f} t CO2e/t is above the {rule.get('name', country)} "
                      f"limit of {lim} t CO2e/t ({rule.get('status', 'config')}).", "reference": rule.get("notes", ""), "severity": "high", "kn": []})
    elif rule:
        flags.append({"flag": "Destination rules", "detail": f"{rule.get('name', country)}: {rule.get('notes', '')}",
                      "reference": "config/companies", "severity": "low", "kn": []})
    bench, bid = kb.waste_value("waste_benchmark", 0.075)
    if reg.val(tot["waste_share"]) > bench:
        flags.append({"flag": "Waste above benchmark", "detail": f"Offcuts {reg.val(tot['waste_share']) * 100:.1f} % vs Maru average {bench * 100:.1f} %.",
                      "reference": "Maru's past projects", "severity": "low", "kn": [bid]})
    non_comp = [g for g in groups_out if g["compliant"] is False]
    ctx.data["carbon"] = {"groups": groups_out, "steel_id": steel_co2, "paint_id": paint_co2, "galv_id": galv_co2,
                          "transport_id": transport_co2, "workshop_id": ws_co2, "total_id": total, "intensity_id": intensity,
                          "options": options, "flags": flags, "requirement": req, "requirement_vid": req_v.id if req_v else None,
                          "placeholder": True, "non_compliant": [g["label"] for g in non_comp]}
