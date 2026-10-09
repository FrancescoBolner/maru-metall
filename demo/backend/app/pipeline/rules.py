"""Stage 4b — Rule engine: cost + hours from the takeoff and Maru's knowledge file. Code only, never AI.

Two pricing methods:
  * detailed part-by-part: operations per part (cutting, drilling, sawing, bevels, fitting, welding) × time norms,
    paint bottom-up per m², material with nesting / thickness waste, packaging, transport, fasteners;
  * quick €/t per category: Maru's reference €/t and h/t per category adjusted for steel price, surface system,
    plate share and margins.
Same input, same result, every time; every number has a formula and knowledge-file rows.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from datetime import date
from typing import Any, Optional

from ..knowledge.base import normalize_system
from ..models import CostLine, Edit, HoursRow, PaintRow, Ref
from ..parsers.profiles import parse_profile, section_props
from ..values import fmt_num, slug
from .context import RunContext
from .nesting import nest
from .takeoff import _parse_date

OPS = ["Plasma cutting", "Edge cleaning", "Sawing", "Drilling", "Bevels and cut-outs", "Fitting / assembly", "Welding",
       "Stud welding", "Blasting", "Painting", "Galvanising handling", "Packaging", "Loading"]
METAL_OPS = {"Plasma cutting", "Edge cleaning", "Sawing", "Drilling", "Bevels and cut-outs", "Fitting / assembly", "Welding",
             "Stud welding"}


# ---------------------------------------------------------------------------------------------- parameters
def _param(ctx: RunContext, key: str, label: str, value: Any, unit: Optional[str], kid: str, editable: bool = True,
           allowed: Optional[list] = None) -> str:
    reg = ctx.reg
    vid = reg.calculated(f"param.{key}", label, value, unit, f"value from the knowledge file ({kid})", kn=[kid],
                         confidence=1.0, editable=editable, edit_key=f"param:{key}", allowed=allowed, group="parameters")
    ov = ctx.override("param", key)
    if ov is not None:
        v = reg.values[vid]
        new = ov.value
        try:
            new = float(ov.value) if unit not in (None, "") else ov.value
        except (TypeError, ValueError):
            pass
        v.edited = Edit(before=v.value, after=new, reason=ov.reason, source=ov.source, at=ov.created_at)
        v.value = new
    return vid


def load_params(ctx: RunContext) -> dict[str, Any]:
    kb, reg = ctx.kb, ctx.reg
    country = ctx.company_cfg.get("workshop_country", "EE")
    rate, rid = kb.labour_rate(country)
    p: dict[str, Any] = {}
    p["labour_rate"] = _param(ctx, "labour_rate", f"Labour rate ({country} workshop)", rate, "€/h", rid)
    mm, mid = kb.num("margin_material", 1.05)
    p["margin_material"] = _param(ctx, "margin_material", "Margin on material", mm, "x", mid)
    mp, pid = kb.num("margin_production", 1.05)
    p["margin_production"] = _param(ctx, "margin_production", "Margin on production, surface and packaging", mp, "x", pid)
    pk, kid = kb.num("packaging_rate", 0.03)
    p["packaging_rate"] = _param(ctx, "packaging_rate", "Packaging", pk, "€/kg", kid)
    wm, wid = kb.num("welding_min_per_m", 10)
    p["weld_min"] = (wm, wid)
    # price list: newest on or before the inquiry date
    inq = reg.get(ctx.data["facts"]["ids"].get("inquiry_date"))
    d = _parse_date(str(inq.value)) if inq else None
    plist, pdate, why = kb.choose_price_list(d)
    ov = ctx.override("param", "price_list")
    if ov is not None and ov.value in [l for l, _ in kb.price_lists()]:
        plist = ov.value
        pdate = dict(kb.price_lists())[plist]
        why = "chosen by the estimator"
    pl_vid = reg.calculated("param.price_list", "Steel price list", f"{plist} ({pdate})", None,
                            f"{why}", inputs=[inq.id] if inq else [], kn=[r.id for r in kb.rows("Steel_prices")
                                                                           if r["price_list"] == plist][:1],
                            editable=True, edit_key="param:price_list", allowed=[l for l, _ in kb.price_lists()],
                            group="parameters")
    p["price_list"] = plist
    p["price_list_id"] = pl_vid
    return p


# ---------------------------------------------------------------------------------------------- helpers
def _band(ctx: RunContext, v) -> float:
    kb = ctx.kb
    if v is None:
        return 0.0
    if v.type == "extracted":
        return float(kb.num("uncertainty_extracted", 0.02)[0]) if not v.edited else 0.0
    if v.type == "calculated":
        return float(kb.num("uncertainty_calculated", 0.06)[0])
    return float(kb.num("uncertainty_predicted", 0.4)[0]) * (1 - float(v.confidence)) + 0.05


def _profile_height(prof) -> float:
    d = prof.dims
    if prof.family in ("RHS",):
        return max(d.get("h", 0), d.get("b", 0))
    if prof.family in ("CHS", "D", "REBAR"):
        return d.get("d", 0)
    if prof.family == "L":
        return max(d.get("a", 0), d.get("b", 0))
    if prof.is_i_section:
        return d.get("h") or d.get("size", 0)
    if prof.family in ("UPE", "UNP"):
        return d.get("h") or d.get("size", 0)
    if prof.family == "T":
        return d.get("h", 0)
    if prof.family in ("PL", "FL"):
        return d.get("w", 0)
    return 100.0


def _wall(prof, i_table) -> float:
    """Wall / flange thickness used for the weld size of end welds."""
    d = prof.dims
    if prof.family in ("RHS", "CHS"):
        return float(d.get("t", 6))
    if prof.family == "WI":
        return float(d.get("tf", 15))
    if prof.is_i_section:
        row = i_table.get(prof.canonical.upper())
        return float(row[3]) if row else 10.0
    if prof.family == "L":
        return float(d.get("t", 8))
    return 8.0


def _section_perimeter(prof, i_table) -> float:
    """Perimeter of the cross-section in metres (for end welds and bevels)."""
    d = prof.dims
    if prof.family == "RHS":
        return 2 * (d["h"] + d["b"]) / 1000
    if prof.family in ("CHS", "D"):
        return math.pi * d["d"] / 1000
    if prof.family == "L":
        return 2 * (d["a"] + d["b"]) / 1000
    kgm, m2m = section_props(prof, i_table)
    return float(m2m or 0.4)


# ---------------------------------------------------------------------------------------------- main
def run_rules(ctx: RunContext) -> None:
    kb, reg = ctx.kb, ctx.reg
    params = load_params(ctx)
    ctx.data["params"] = params
    rate = reg.val(params["labour_rate"])
    m_mat = reg.val(params["margin_material"])
    m_prod = reg.val(params["margin_production"])
    pack_rate = reg.val(params["packaging_rate"])
    weld_min, weld_kid = params["weld_min"]
    i_table = kb.i_table()
    cats = ctx.data["categories"]
    cat_by_key = {(c.name.split(" — ")[0], c.phase or ""): c for c in cats}
    included = {k for k, c in cat_by_key.items() if c.included}
    parts = [p for p in ctx.data["parts"] if (p["category"], p["phase"] or "") in included]
    assemblies = ctx.data["assemblies"]

    # ------------------------------------------------------------------ operations per part
    acc: dict[tuple[str, tuple], dict[str, float]] = defaultdict(lambda: defaultdict(float))
    kn_used: dict[str, set[str]] = defaultdict(set)
    hole_source: dict[tuple, str] = {}
    parts_by_asm: dict[str, list[dict]] = defaultdict(list)
    for p in parts:
        parts_by_asm[p["assembly"]].append(p)
    holes_per_bolt, hpb_kid = kb.prediction("holes_per_bolt", 2)
    wef = kb.row("TN-WEF")
    end_a = float(wef["norm"]) if wef else 0.7
    end_cap = 12.0
    wbu = kb.row("TN-WBU")
    bu_k, bu_cap = 0.5, 8.0
    for akey, ap in parts_by_asm.items():
        asm = assemblies.get(akey, {})
        ck = (ap[0]["category"], ap[0]["phase"] or "")
        cat = ck[0]
        info = kb.category_info(cat)
        main = next((p for p in ap if p["is_main"]), max(ap, key=lambda x: x["kg"]))
        plates = [p for p in ap if p["is_plate"]]
        multi = len(ap) > 1
        asm_kg = sum(p["kg"] for p in ap)
        Lm = float(main["length"] or 0)
        rod = main["family"] == "D"
        built_up = (cat in ("Welded beams", "Welded columns") or main["family"] == "WI" or
                    (main["is_plate"] and Lm >= 1500 and any(p is not main and p["is_plate"] and (p["length"] or 0) >= 0.5 * Lm for p in ap)))
        # holes: from the model's bolt groups when available, else predicted per tonne
        if asm.get("source") == "ifc":
            holes = float(asm.get("bolts", 0)) * float(holes_per_bolt)
            hole_source[ck] = "model"
        else:
            hpt = float(info.get("holes_per_t", 30)) if info else 30.0
            holes = hpt * asm_kg / 1000.0
            hole_source[ck] = hole_source.get(ck, "predicted")
            kn_used["holes_pred"].add(info.id if info else "CAT-12")
        plate_pieces = sum(p["pieces"] for p in plates) or 0
        a = acc[("asm", ck)]
        a["assemblies"] += float(asm.get("pieces", 1) or 1)
        a["holes"] += holes
        for p in ap:
            prof = p["prof"]
            pcs = float(p["pieces"] or 1)
            L = float(p["length"] or 0)
            if p["is_plate"]:
                t = float(p.get("t") or prof.thickness or 10)
                W = float(p.get("w") or 0) or (p["kg"] / pcs / (t * max(L, 1) * 7.85e-6) if L else 100)
                edge = 2 * (L + W) / 1000 * pcs
                ph = holes * (p["pieces"] / plate_pieces) if plate_pieces else 0.0
                speed, pierce, cid = kb.cutting(t)
                cut_h = edge * 5 / (speed * 0.06) + (ph * 5 * pierce / 3600 if t < 35 else 0)
                kn_used["cut"].add(cid)
                acc[("Plasma cutting", ck)]["h"] += cut_h
                acc[("Plasma cutting", ck)]["q"] += edge
                acc[("Edge cleaning", ck)]["h"] += edge * 0.012
                acc[("Edge cleaning", ck)]["q"] += edge
                if t >= 35 and ph:
                    mph, did = kb.plate_drilling(t)
                    acc[("Drilling", ck)]["h"] += ph * mph / 60
                    acc[("Drilling", ck)]["q"] += ph
                    kn_used["drill_p"].add(did)
                kgpc = p["kg"] / pcs
                mins, hid = kb.handling("plate", kgpc, ph > 0)
                acc[("Fitting / assembly", ck)]["h"] += mins * pcs / 60
                acc[("Fitting / assembly", ck)]["q"] += pcs
                kn_used["fit"].add(hid)
                if multi and p is not main and not rod:
                    if built_up and Lm >= 1500 and L >= 0.5 * Lm:
                        weld = 0.0  # flange / web plate of a built-up section: covered by the 4 × L rule below
                    else:
                        weld = 2 * max(L, W) / 1000 * pcs  # TN-WPL: 2 × plate length
                    acc[("Welding", ck)]["q"] += weld
            elif prof.family == "WI":
                # welded I section modelled as one part: web + 2 flanges are plasma cut from plates
                d = prof.dims
                tf = float(d.get("tf", 15))
                edge = (2 * (L + d.get("h", 400)) + 4 * (L + d.get("b", 200))) / 1000 * pcs
                speed, pierce, cid = kb.cutting(tf)
                kn_used["cut"].add(cid)
                acc[("Plasma cutting", ck)]["h"] += edge * 5 / (speed * 0.06)
                acc[("Plasma cutting", ck)]["q"] += edge
                acc[("Edge cleaning", ck)]["h"] += edge * 0.012
                acc[("Edge cleaning", ck)]["q"] += edge
                mins, hid = kb.handling("plate", p["kg"] / pcs / 3, False)
                acc[("Fitting / assembly", ck)]["h"] += 3 * mins * pcs / 60
                acc[("Fitting / assembly", ck)]["q"] += 3 * pcs
                kn_used["fit"].add(hid)
                if multi and plates and p is main:
                    f_end = min(max(1.0, (end_a * tf / 5) ** 2), end_cap)
                    acc[("Welding", ck)]["q"] += 6 * float(d.get("h", 400)) / 1000 * 2 * pcs * f_end  # TN-WPE end plates
                elif multi and p is not main:
                    acc[("Welding", ck)]["q"] += 2 * L / 1000 * pcs
            else:
                H = _profile_height(prof) or 100
                acc[("Sawing", ck)]["h"] += 2 * H / 20 / 60 * pcs
                acc[("Sawing", ck)]["q"] += 2 * pcs
                if not plate_pieces and p is main and holes:
                    acc[("Drilling", ck)]["h"] += holes * 0.5 / 60
                    acc[("Drilling", ck)]["q"] += holes
                per = _section_perimeter(prof, i_table)
                if p is main and info and float(info.get("bevel_share", 0)) > 0 and not rod:
                    acc[("Bevels and cut-outs", ck)]["h"] += 2 * per * 20 / 60 * float(info["bevel_share"]) * pcs
                    acc[("Bevels and cut-outs", ck)]["q"] += 2 * pcs * float(info["bevel_share"])
                mins, hid = kb.handling("profile", L, False)
                acc[("Fitting / assembly", ck)]["h"] += mins * pcs / 60
                acc[("Fitting / assembly", ck)]["q"] += pcs
                kn_used["fit"].add(hid)
                weld = 0.0
                f_end = min(max(1.0, (end_a * _wall(prof, i_table) / 5) ** 2), end_cap)  # TN-WEF: a = 0.7 t, (a/5)^2
                if multi:
                    if rod and p is main:
                        weld = math.pi * H / 1000 * 2 * pcs  # rod ends only; turnbuckles and forks are not welded
                    elif p is main and plates:
                        if prof.family == "L":
                            weld = 2 * L / 1000 * pcs
                        else:
                            k = 6 if prof.is_i_section else (2 if prof.family in ("T", "UPE", "UNP") else 4)
                            weld = k * H / 1000 * 2 * pcs * f_end  # TN-WPE
                    elif p is not main and not rod:
                        weld = min(2 * L / 1000, 2 * per) * pcs * f_end
                acc[("Welding", ck)]["q"] += weld
        if built_up:
            if main["family"] == "WI":
                tw = float(main["prof"].dims.get("tw", 10))
            else:
                tw = max((float(pp.get("t") or 8) for pp in plates), default=8.0)
            a_size = min(max(bu_k * tw, 4.0), bu_cap)
            acc[("Welding", ck)]["q"] += 4 * Lm / 1000 * float(main["pieces"] or 1) * (a_size / 5) ** 2  # TN-WBU
        a["kg"] += asm_kg

    # ------------------------------------------------------------------ hours values
    hours_rows: list[HoursRow] = []
    cat_hours: dict[tuple, list[str]] = defaultdict(list)
    cat_metal_hours: dict[tuple, list[str]] = defaultdict(list)
    op_ids: dict[str, list[str]] = defaultdict(list)
    tn = {"Plasma cutting": "TN-CUT", "Edge cleaning": "TN-CLN", "Sawing": "TN-SAW", "Drilling": "TN-DRL",
          "Bevels and cut-outs": "TN-BEV", "Fitting / assembly": "TN-FIT", "Welding": "TN-WLD"}
    qty_unit = {"Plasma cutting": "m", "Edge cleaning": "m", "Sawing": "cuts", "Drilling": "holes", "Bevels and cut-outs": "ends",
                "Fitting / assembly": "parts", "Welding": "m a5"}
    norm_text = {"Plasma cutting": "edge m × 5 / speed(t) + holes × 5 × pierce(t)", "Edge cleaning": "0.012 h per m of cut edge",
                 "Sawing": "2 cuts × section height / 20 min", "Drilling": "0.5 min/hole (profiles), 3-10 min/hole (plates ≥ 35 mm)",
                 "Bevels and cut-outs": "2 ends × section perimeter × 20 min/m × bevel share", "Fitting / assembly": "min per part by weight / length band",
                 "Welding": f"{weld_min:g} min per m of a5-equivalent weld"}
    for ck in sorted({k[1] for k in acc if k[0] != "asm"}, key=lambda x: (x[0], x[1])):
        c = cat_by_key[ck]
        cname = c.name
        base = f"h.{slug(cname)}"
        for op in ["Plasma cutting", "Edge cleaning", "Sawing", "Drilling", "Bevels and cut-outs", "Fitting / assembly", "Welding"]:
            d = acc.get((op, ck))
            if not d or (d.get("h", 0) == 0 and d.get("q", 0) == 0):
                continue
            kn = [tn[op]] + sorted(kn_used["cut"])[:6] if op == "Plasma cutting" else [tn[op]]
            if op == "Fitting / assembly":
                kn += sorted(kn_used["fit"])
            if op == "Drilling":
                kn += sorted(kn_used["drill_p"])
            if op == "Welding":
                q = d["q"]
                qid = reg.predicted(f"{base}.weld_m", f"{cname} — weld length (a5 equivalent)", round(q, 1), "m",
                                    "Weld sizes and lengths are not in the client files: estimated from the part geometry with "
                                    "Maru's workbook rules (profile end welds, 2 × length of attached plates, 4 × length of built-up "
                                    "sections, a5 equivalence).", confidence=0.6, kn=["TN-WPE", "TN-WPL", "TN-WBU", "TN-A5"],
                                    inputs=[c.kg_id], group="operations")
                h = q * weld_min / 60
                hid = reg.calculated(f"{base}.welding", f"{cname} — welding hours", round(h, 1), "h",
                                     f"weld length × {weld_min:g} min/m ÷ 60", inputs=[qid], kn=[weld_kid, "TN-WLD"], group="hours")
            else:
                qtype_pred = op == "Drilling" and hole_source.get(ck) == "predicted"
                if qtype_pred:
                    qid = reg.predicted(f"{base}.{slug(op)}.q", f"{cname} — {op.lower()} quantity", round(d["q"], 1), qty_unit[op],
                                        "No bolt data in the files: holes predicted per tonne for this category.",
                                        confidence=0.5, kn=sorted(kn_used["holes_pred"]), inputs=[c.kg_id], group="operations")
                else:
                    qid = reg.calculated(f"{base}.{slug(op)}.q", f"{cname} — {op.lower()} quantity", round(d["q"], 1), qty_unit[op],
                                         f"from part geometry{' and bolt groups in the model (2 holes per bolt)' if op == 'Drilling' else ''}",
                                         inputs=[c.kg_id, c.pieces_id], kn=[hpb_kid] if op == "Drilling" else [], group="operations")
                hid = reg.calculated(f"{base}.{slug(op)}", f"{cname} — {op.lower()} hours", round(d["h"], 1), "h",
                                     norm_text[op], inputs=[qid], kn=kn, group="hours")
            hours_rows.append(HoursRow(operation=op, category=cname, quantity_id=qid, hours_id=hid, norm=norm_text[op], kn=kn,
                                       costed_in="labour"))
            cat_hours[ck].append(hid)
            cat_metal_hours[ck].append(hid)
            op_ids[op].append(hid)
        ctx.data.setdefault("asm_counts", {})[ck] = acc[("asm", ck)].get("assemblies", 0)

    # ------------------------------------------------------------------ allowances (studs welded in the workshop)
    allowance_costs: list[dict[str, Any]] = []
    for al in ctx.data.get("allowances", []):
        if al["kind"] == "studs":
            qv = reg.values[al["qty_id"]]
            mins, mkid = kb.prediction("stud_minutes", 6)
            h = float(qv.value or 0) * float(mins) / 60
            hid = reg.calculated("h.allowance.studs", "Rebar studs — welding hours", round(h, 1), "h",
                                 f"studs × {mins} min ÷ 60", inputs=[qv.id], kn=[mkid], group="hours")
            hours_rows.append(HoursRow(operation="Stud welding", category="Allowances", quantity_id=qv.id, hours_id=hid,
                                       norm=f"{mins} min per stud", kn=[mkid], costed_in="labour"))
            op_ids["Stud welding"].append(hid)
            al["hours_id"] = hid

    # ------------------------------------------------------------------ surface treatment (paint bottom-up / HDG)
    paint_rows: list[PaintRow] = []
    surf_cost_ids: dict[tuple, str] = {}
    litres_by_product: dict[str, list[str]] = defaultdict(list)
    paint_hours_ids: list[str] = []
    blast_hours_ids: list[str] = []
    galv_hours_ids: list[str] = []
    for c in cats:
        ck = (c.name.split(" — ")[0], c.phase or "")
        if not c.included:
            continue
        system = normalize_system(str(reg.val(c.surface_id, "NONE")))
        area = reg.val(c.area_id)
        kg = reg.val(c.kg_id)
        base = f"s.{slug(c.name)}"
        if system == "HDG":
            r, unit, sid = kb.surface_rate("HDG")
            cost = kg * r
            cid = reg.calculated(f"{base}.cost", f"{c.name} — hot-dip galvanising", round(cost, 2), "€",
                                 f"weight × {r} €/kg", inputs=[c.kg_id, c.surface_id], kn=[sid], group="surface")
            gh, gkid = (float(kb.row("TN-GAL")["norm"]) if kb.row("TN-GAL") else 1.5), "TN-GAL"
            ghid = reg.calculated(f"{base}.galv_h", f"{c.name} — galvanising handling hours", round(kg / 1000 * gh, 1), "h",
                                  f"tonnes × {gh} h/t (inside the galvanising rate)", inputs=[c.kg_id], kn=[gkid], group="hours")
            hours_rows.append(HoursRow(operation="Galvanising handling", category=c.name, quantity_id=c.kg_id, hours_id=ghid,
                                       norm=f"{gh} h/t", kn=[gkid], costed_in="galvanising"))
            galv_hours_ids.append(ghid)
            cat_hours[ck].append(ghid)
            surf_cost_ids[ck] = cid
            paint_rows.append(PaintRow(category=c.name, system="HDG", area_id=c.area_id, coats=0, litres=[], hours_id=ghid,
                                       cost_id=cid, kn=[sid, gkid]))
            continue
        ps = kb.paint_system(system)
        if ps is None or system in ("NONE",):
            if system != "NONE":
                ctx.warnings.append(f"No paint system '{system}' in the knowledge file for {c.name}: surface not priced")
            continue
        coats = int(ps["coats"])
        prods = []
        mat_cost = 0.0
        l_ids = []
        for pref in ("p1", "p2"):
            name, nco = ps[f"{pref}_name"], int(ps[f"{pref}_coats"] or 0)
            if not name or not nco:
                continue
            dft, vs, eur = float(ps[f"{pref}_dft_um"]), float(ps[f"{pref}_volume_solids"]), float(ps[f"{pref}_eur_per_l"])
            loss = float(ps["loss_factor"])
            lpm2 = dft / (1000 * vs) * loss
            litres = area * lpm2 * nco
            lid = reg.calculated(f"{base}.{pref}.litres", f"{c.name} — {name}", round(litres, 1), "l",
                                 f"area × {nco} coat(s) × {dft:g} µm ÷ (1000 × {vs:g} volume solids) × {loss:g} loss",
                                 inputs=[c.area_id, c.surface_id], kn=[ps.id], group="paint")
            mat_cost += litres * eur
            prods.append({"product": name, "value_id": lid, "eur_per_l": eur, "coats": nco, "dft": dft})
            l_ids.append(lid)
            litres_by_product[name].append(lid)
        bmin = float(ps["blasting_min_per_m2"])
        pmin = float(ps["painting_min_per_m2_per_coat"])
        bh = area * bmin / 60
        phh = area * pmin * coats / 60
        bhid = reg.calculated(f"{base}.blast_h", f"{c.name} — blasting hours", round(bh, 1), "h", f"area × {bmin:g} min/m² ÷ 60",
                              inputs=[c.area_id], kn=["TN-BLA", ps.id], group="hours")
        phid = reg.calculated(f"{base}.paint_h", f"{c.name} — painting hours", round(phh, 1), "h",
                              f"area × {coats} coats × {pmin:g} min/m² ÷ 60", inputs=[c.area_id], kn=[ps.id], group="hours")
        hours_rows.append(HoursRow(operation="Blasting", category=c.name, quantity_id=c.area_id, hours_id=bhid,
                                   norm=f"{bmin:g} min/m²", kn=["TN-BLA", ps.id], costed_in="surface"))
        hours_rows.append(HoursRow(operation="Painting", category=c.name, quantity_id=c.area_id, hours_id=phid,
                                   norm=f"{pmin:g} min/m² per coat × {coats}", kn=[ps.id], costed_in="surface"))
        blast_hours_ids.append(bhid)
        paint_hours_ids.append(phid)
        cat_hours[ck] += [bhid, phid]
        cost = mat_cost + (bh + phh) * rate + area * float(ps["blasting_material_eur_per_m2"])
        cid = reg.calculated(f"{base}.cost", f"{c.name} — painting {system}", round(cost, 2), "€",
                             f"paint litres × €/l + (blasting + painting hours) × {rate:g} €/h + area × {ps['blasting_material_eur_per_m2']} €/m² abrasive",
                             inputs=l_ids + [bhid, phid, c.area_id, params["labour_rate"]], kn=[ps.id, "SUR-" + system], group="surface")
        v = reg.values[cid]
        v.reasoning = (f"Bottom-up {cost / area:.2f} €/m² vs Maru's all-in rate {ps['maru_all_in_eur_per_m2']} €/m² "
                       f"(knowledge {('SUR-' + system)})") if area else None
        surf_cost_ids[ck] = cid
        paint_rows.append(PaintRow(category=c.name, system=system, area_id=c.area_id, coats=coats, litres=prods,
                                   hours_id=phid, cost_id=cid, kn=[ps.id]))

    # ------------------------------------------------------------------ material: nesting per profile, waste by thickness
    stock = [kb.waste_value("stock_length", 12000)[0], kb.waste_value("stock_length_long", 15000)[0],
             kb.waste_value("stock_length_xl", 18000)[0]]
    kerf = kb.waste_value("saw_kerf", 5)[0]
    min_reuse = kb.waste_value("min_reusable_offcut", 1000)[0]
    floor_, floor_id = kb.waste_value("profile_waste_floor", 1.03)
    cap_, cap_id = kb.waste_value("profile_waste_cap", 1.15)
    mat_lines: list[dict[str, Any]] = []
    cat_mat_ids: dict[tuple, list[str]] = defaultdict(list)
    waste_kg_total = 0.0
    reusable_kg_total = 0.0
    net_kg_total = 0.0
    parts_by_line: dict[str, list[dict]] = defaultdict(list)
    for p in parts:
        parts_by_line[p.get("line")].append(p)
    for line in ctx.data["lines"]:
        ck = (line.category, line.phase or "")
        if ck not in included:
            continue
        lp = parts_by_line.get(line.id, [])
        kg = reg.val(line.kg_id)
        prof = parse_profile(line.profile)
        eur, waste_list, sp_id, how = kb.steel_price(prof, params["price_list"], line.grade)
        if line.is_plate:
            t = line.thickness_mm or prof.thickness or 10
            factor, wid = kb.plate_waste(float(t))
            wkn = [wid]
            wf_formula = f"plate thickness {t:g} mm → factor {factor}"
            reusable = 0.0
        else:
            lengths = []
            for p in lp:
                lengths += [p["length"]] * int(round(p["pieces"] or 1))
            n = nest(lengths, stock, kerf, min_reuse) if lengths else {"factor": waste_list, "reusable": 0, "net": 0}
            factor = min(max(n["factor"], floor_), cap_)
            wkn = ["WST-01", "WST-02", "WST-03", "WST-04", "WST-05", floor_id, cap_id]
            wf_formula = (f"1D nesting of {len(lengths)} pieces on {stock[0] / 1000:g}/{stock[1] / 1000:g}/{stock[2] / 1000:g} m stock: "
                          f"bought {n['bought'] / 1000:.1f} m for {n['net'] / 1000:.1f} m net" if lengths else "price-list waste factor")
            reusable = (n["reusable"] / n["net"] * kg) if n.get("net") else 0.0
        wfid = reg.calculated(f"m.{line.id}.waste", f"{line.profile} — waste factor", round(factor, 3), "x", wf_formula,
                              inputs=[line.kg_id] + ([line.length_id] if line.length_id else []), kn=wkn, group="material")
        cost = kg * factor * eur
        mid = reg.calculated(f"m.{line.id}.cost", f"{line.profile} {line.grade or ''} — material".strip(), round(cost, 2), "€",
                             f"{fmt_num(kg, 1)} kg × {factor:.3f} × {eur} €/kg ({how})", inputs=[line.kg_id, wfid],
                             kn=[sp_id], group="material")
        cat_mat_ids[ck].append(mid)
        waste_kg_total += kg * (factor - 1)
        reusable_kg_total += reusable
        net_kg_total += kg
        mat_lines.append({"line": line.id, "profile": line.profile, "grade": line.grade, "category": line.category,
                          "phase": line.phase, "kg": kg, "factor": factor, "eur_per_kg": eur, "cost_id": mid,
                          "waste_id": wfid, "price_kn": sp_id, "reusable_kg": reusable})
    waste_id = reg.calculated("m.waste_kg", "Offcuts and waste (bought − net)", round(waste_kg_total, 0), "kg",
                              "Σ net kg × (waste factor − 1)", inputs=[m["waste_id"] for m in mat_lines][:60], group="material")
    reuse_id = reg.calculated("m.reusable_kg", "Reusable offcuts (≥ 1 m) for remnant stock", round(reusable_kg_total, 0), "kg",
                              "Σ offcuts longer than the minimum reusable length", kn=["WST-05"], group="material")
    bought_id = reg.calculated("m.bought_kg", "Steel to buy (net + offcuts)", round(net_kg_total + waste_kg_total, 0), "kg",
                               "net steel + offcuts", inputs=["total.kg", waste_id], group="material")
    waste_share_id = reg.calculated("m.waste_share", "Offcut share", round(waste_kg_total / net_kg_total, 4) if net_kg_total else 0,
                                    "share", "offcuts ÷ net steel", inputs=[waste_id, "total.kg"], group="material")
    remn = kb.remnants()
    ctx.data["remnant_note"] = ("Remnant stock list checked: " + str(len(remn)) + " rows") if remn else \
        "Remnant stock check skipped: Maru's remnant list is not in the knowledge file yet"

    # ------------------------------------------------------------------ fasteners & allowances
    extra_lines: list[dict[str, Any]] = []
    bolts_kg = 0.0
    bolt_refs: list[Ref] = []
    bolt_groups = [b for a in assemblies.values() for b in a.get("bolt_groups", [])
                   if (a["category"], a["phase"] or "") in included]
    fac3 = kb.row("FAS-03")
    k3 = float(fac3["value"]) if fac3 else 2.5e-5
    for b in bolt_groups:
        dmm = float(b.get("size") or 16)
        lmm = float(b.get("length") or 60)
        per = 7.85e-6 * math.pi / 4 * dmm * dmm * lmm + k3 * dmm ** 3
        bolts_kg += per * int(b.get("count") or 1)
    bolts_included = any(s["status"] == "included" and re.search(r"bolt|fasten", s["item"], re.I) for s in ctx.data["facts"]["scope"])
    fas = kb.row("FAS-01")
    if bolt_groups:
        files = {a["file"].id: a["file"] for a in assemblies.values() if a.get("bolt_groups")}
        for e in list(files.values())[:2]:
            bolt_refs.append(Ref(kind="ifc_elements", file_id=e.id, path=e.path, label=f"{e.name} · bolt groups",
                                 snippet=f"{len(bolt_groups)} IfcMechanicalFastener groups, {sum(int(b.get('count') or 1) for b in bolt_groups)} bolts (Tekla Bolt: size, length, count)",
                                 guids=[b["guid"] for b in bolt_groups][:400]))
        bk_id = reg.calculated("x.bolts.kg", "Bolts, nuts and washers — weight", round(bolts_kg, 1), "kg",
                               "Σ bolts × (shank π/4·d²·L·7.85e-6 + head/nut/washers k·d³)", kn=["FAS-03"], refs=bolt_refs,
                               confidence=0.85, group="fasteners")
    elif bolts_included or True:
        bpt, bkid = kb.prediction("bolts_kg_per_t", 5.0)
        bolts_kg = float(bpt) * reg.val("total.kg") / 1000
        bk_id = reg.predicted("x.bolts.kg", "Bolts, nuts and washers — weight", round(bolts_kg, 1), "kg",
                              f"No bolts in the files: {bpt} kg per tonne of steel ({bkid}).", confidence=0.4, kn=[bkid],
                              inputs=["total.kg"], question="Are site bolts included in the scope, and is a bolt list available?",
                              group="fasteners")
    if fas is not None and bolts_kg > 0:
        cost = bolts_kg * float(fas["value"]) * float(fas["margin"] or 1)
        cid = reg.calculated("x.bolts.cost", "Fasteners for steel-to-steel connections", round(cost, 2), "€",
                             f"weight × {fas['value']} €/kg × {fas['margin']}", inputs=[bk_id], kn=["FAS-01"], group="fasteners")
        line = {"key": "bolts", "label": "Fasteners for steel-to-steel connections", "qty": 1, "unit": "set",
                "cost_id": cid, "sale_id": cid, "kind": "fasteners"}
        bolt_ov = ctx.override("param", "include_fasteners")
        include = (bool(bolt_groups) or bolts_included) if bolt_ov is None else str(bolt_ov.value).lower() in ("true", "1", "yes")
        if include:
            extra_lines.append(line)
        else:
            ctx.data["fastener_option"] = line
            reg.values[cid].reasoning = ("Not in the base price: the files neither contain bolts nor ask for them. "
                                         "Shown as an option; confirm with the client.")
    for al in ctx.data.get("allowances", []):
        qv = reg.values[al["qty_id"]]
        if al["kind"] == "anchors":
            fa = kb.row("FAS-02")
            unit_eur = float(fa["value"]) if fa else 6.23
            cid = reg.calculated("x.anchors.cost", al["label"], round(float(qv.value or 0) * unit_eur, 2), "€",
                                 f"quantity × {unit_eur} €/pc", inputs=[qv.id], kn=["FAS-02"], group="fasteners")
            extra_lines.append({"key": "anchors", "label": al["label"], "qty_id": qv.id, "unit": "pcs", "cost_id": cid,
                                "sale_id": cid, "kind": "anchors"})
        elif al["kind"] == "studs":
            smass, smid = kb.prediction("stud_mass", 0.49)
            kg = float(qv.value or 0) * float(smass)
            eur, waste, spid, _ = kb.steel_price(parse_profile("D20"), params["price_list"])
            mat = kg * eur * 1.1
            lab = reg.val(al.get("hours_id")) * rate
            sale = mat * m_mat + lab * m_prod
            cid = reg.calculated("x.studs.cost", al["label"], round(sale, 2), "€",
                                 f"studs × {smass} kg × {eur} €/kg × 1.1 × margin + welding hours × {rate:g} €/h × margin",
                                 inputs=[qv.id, al.get("hours_id"), params["margin_material"], params["margin_production"]],
                                 kn=[smid, spid], group="fasteners")
            extra_lines.append({"key": "studs", "label": al["label"], "qty_id": qv.id, "unit": "pcs", "cost_id": cid,
                                "sale_id": cid, "kind": "studs"})

    # ------------------------------------------------------------------ transport
    total_kg = reg.val("total.kg")
    country_v = reg.get(ctx.data["facts"]["ids"].get("delivery_country"))
    addr_v = reg.get(ctx.data["facts"]["ids"].get("delivery_address"))
    country = str(country_v.value).strip()[:2].upper() if country_v and country_v.value else None
    addr_text = " ".join(str(x) for x in [addr_v.value if addr_v else "", " ".join(str(o.value) for o in (addr_v.conflict if addr_v else [])),
                                          ctx.project.name])
    region, trows, region_why = kb.transport_region(country, addr_text)
    by_type = {r["truck_type"]: r for r in trows}
    std = by_type.get("standard")
    longest_by_part = [(p["length"] or 0, p["kg"]) for p in parts]
    long_kg = sum(kg for L, kg in longest_by_part if L > float(std["max_length_m"]) * 1000) if std else 0
    xl_kg = sum(kg for L, kg in longest_by_part if L > float(by_type.get("long", std)["max_length_m"]) * 1000) if std else 0
    payload = float(std["payload_kg"]) if std else 18500
    coef = float(std["coefficient"]) if std else 1.15
    trucks = {"special": math.ceil(xl_kg / payload) if xl_kg else 0}
    trucks["long"] = math.ceil(max(long_kg - xl_kg, 0) / payload) if long_kg - xl_kg > 0 else 0
    rest = max(total_kg - long_kg, 0)
    trucks["standard"] = math.ceil(rest / payload) if rest > 0 else 0
    tr_cost = 0.0
    tr_kn = []
    desc = []
    for tt in ("standard", "long", "special"):
        if trucks[tt] and tt in by_type:
            r = by_type[tt]
            tr_cost += trucks[tt] * float(r["eur_per_truck"]) * coef
            tr_kn.append(r.id)
            desc.append(f"{trucks[tt]} × {tt} truck ({r['max_length_m']} m) × {r['eur_per_truck']} €")
    n_trucks = sum(trucks.values())
    trucks_id = reg.calculated("t.trucks", "Trucks", n_trucks, "trucks",
                               f"pieces longer than {std['max_length_m'] if std else 13.5} m go on long/special trucks; "
                               f"{payload:,.0f} kg per truck", inputs=["total.kg", ctx.data.get("longest_id")], kn=tr_kn, group="logistics")
    tr_id = reg.calculated("t.cost", f"Transport to {region}", round(tr_cost, 2), "€",
                           " + ".join(desc) + f", × {coef} coefficient ({region_why})",
                           inputs=[trucks_id] + ([country_v.id] if country_v else []), kn=tr_kn, group="logistics")
    load_h = float(kb.row("TN-LOD")["norm"]) if kb.row("TN-LOD") else 1.5
    lhid = reg.calculated("h.loading", "Loading hours", round(n_trucks * load_h, 1), "h", f"trucks × {load_h} h",
                          inputs=[trucks_id], kn=["TN-LOD"], group="hours")
    hours_rows.append(HoursRow(operation="Loading", category="All", quantity_id=trucks_id, hours_id=lhid, norm=f"{load_h} h/truck",
                               kn=["TN-LOD"], costed_in="transport"))
    ctx.data["transport"] = {"region": region, "why": region_why, "trucks": trucks, "distance_km": float(std["distance_km"]) if std else 0,
                             "desc": desc, "cost_id": tr_id, "trucks_id": trucks_id}

    # ------------------------------------------------------------------ per category cost & selling price
    cost_lines: list[CostLine] = []
    cat_sale: dict[tuple, str] = {}
    totals = defaultdict(list)
    pack_h_rate = float(kb.row("TN-PCK")["norm"]) if kb.row("TN-PCK") else 0.4
    for c in cats:
        ck = (c.name.split(" — ")[0], c.phase or "")
        if not c.included:
            continue
        base = f"c.{slug(c.name)}"
        mat_ids = cat_mat_ids.get(ck, [])
        mat = sum(reg.val(i) for i in mat_ids)
        mat_id = reg.calculated(f"{base}.material", f"{c.name} — material", round(mat, 2), "€", "Σ material of the lines",
                                inputs=mat_ids + [params["price_list_id"]], group="cost")
        mh_ids = cat_metal_hours.get(ck, [])
        mh = sum(reg.val(i) for i in mh_ids)
        mh_id = reg.calculated(f"{base}.metal_h", f"{c.name} — metalwork hours", round(mh, 1), "h", "Σ operation hours",
                               inputs=mh_ids, group="hours")
        lab_id = reg.calculated(f"{base}.labour", f"{c.name} — labour", round(mh * rate, 2), "€", f"metalwork hours × {rate:g} €/h",
                                inputs=[mh_id, params["labour_rate"]], kn=["GEN-01"], group="cost")
        surf_id = surf_cost_ids.get(ck)
        surf = reg.val(surf_id) if surf_id else 0.0
        kg = reg.val(c.kg_id)
        pack_id = reg.calculated(f"{base}.packaging", f"{c.name} — packaging", round(kg * pack_rate, 2), "€",
                                 f"weight × {pack_rate} €/kg", inputs=[c.kg_id, params["packaging_rate"]], kn=["GEN-06"], group="cost")
        ph_id = reg.calculated(f"{base}.pack_h", f"{c.name} — packaging hours", round(kg / 1000 * pack_h_rate, 1), "h",
                               f"tonnes × {pack_h_rate} h/t (inside the packaging rate)", inputs=[c.kg_id], kn=["TN-PCK"], group="hours")
        hours_rows.append(HoursRow(operation="Packaging", category=c.name, quantity_id=c.kg_id, hours_id=ph_id,
                                   norm=f"{pack_h_rate} h/t", kn=["TN-PCK"], costed_in="packaging"))
        cat_hours[ck].append(ph_id)
        sale = mat * m_mat + (mh * rate + surf + kg * pack_rate) * m_prod
        sale_id = reg.calculated(f"{base}.sale", f"{c.name} — price", round(sale, 2), "€",
                                 f"material × {m_mat:g} + (labour + surface + packaging) × {m_prod:g}",
                                 inputs=[mat_id, lab_id] + ([surf_id] if surf_id else []) + [pack_id, params["margin_material"],
                                                                                            params["margin_production"]],
                                 kn=["GEN-03", "GEN-04"], group="cost")
        cat_sale[ck] = sale_id
        for grp, vid, kn in (("Material", mat_id, []), ("Labour", lab_id, ["GEN-01"]),
                             ("Surface treatment", surf_id, []), ("Packaging", pack_id, ["GEN-06"])):
            if vid:
                cost_lines.append(CostLine(group=grp, label=c.name, value_id=vid, kn=kn, category=c.name))
                totals[grp].append(vid)
        totals["Sale"].append(sale_id)
        totals["metal_h"].append(mh_id)
    # aggregate hours
    all_hours = [h.hours_id for h in hours_rows]
    metal_h_ids = [h.hours_id for h in hours_rows if h.costed_in == "labour"]
    tot_metal_h = reg.calculated("total.metal_hours", "Workshop hours (metalwork)", round(sum(reg.val(i) for i in metal_h_ids), 1), "h",
                                 "Σ cutting, drilling, sawing, bevels, fitting and welding hours", inputs=metal_h_ids, group="hours")
    tot_h = reg.calculated("total.hours", "Total working hours", round(sum(reg.val(i) for i in all_hours), 1), "h",
                           "Σ all operation hours (metalwork, surface, galvanising handling, packaging, loading)",
                           inputs=all_hours, group="hours")
    lab_total = reg.calculated("total.labour_cost", "Labour cost (metalwork)", round(reg.val(tot_metal_h) * rate, 2), "€",
                               f"metalwork hours × {rate:g} €/h", inputs=[tot_metal_h, params["labour_rate"]], kn=["GEN-01"], group="cost")
    op_totals = {}
    for op in OPS:
        ids_ = [h.hours_id for h in hours_rows if h.operation == op]
        if ids_:
            op_totals[op] = reg.calculated(f"total.h.{slug(op)}", f"{op} — total hours", round(sum(reg.val(i) for i in ids_), 1), "h",
                                           f"Σ {op.lower()} hours over categories", inputs=ids_, group="hours")
    cat_h_totals = {}
    for c in cats:
        ck = (c.name.split(" — ")[0], c.phase or "")
        if ck in cat_hours:
            cat_h_totals[c.name] = reg.calculated(f"total.hcat.{slug(c.name)}", f"{c.name} — total hours",
                                                  round(sum(reg.val(i) for i in cat_hours[ck]), 1), "h", "Σ operation hours",
                                                  inputs=cat_hours[ck], group="hours")
    # paint totals
    litres_tot = {}
    for prod, ids_ in litres_by_product.items():
        litres_tot[prod] = reg.calculated(f"total.litres.{slug(prod)}", f"{prod} — total litres", round(sum(reg.val(i) for i in ids_), 0),
                                          "l", "Σ litres over categories", inputs=ids_, group="paint")
    paint_l = reg.calculated("total.paint_litres", "Paint (all products)", round(sum(reg.val(i) for i in litres_tot.values()), 0), "l",
                             "Σ litres of all paint products", inputs=list(litres_tot.values()), group="paint")
    surf_ids = [v for v in surf_cost_ids.values()]
    paint_ids = [v for k, v in surf_cost_ids.items() if "galvanising" not in reg.values[v].label]
    galv_ids = [v for v in surf_ids if v not in paint_ids]
    paint_cost = reg.calculated("total.paint_cost", "Painting cost (paint, blasting, labour)", round(sum(reg.val(i) for i in paint_ids), 2),
                                "€", "Σ painting cost over categories", inputs=paint_ids, group="paint")
    galv_cost = reg.calculated("total.galv_cost", "Hot-dip galvanising cost", round(sum(reg.val(i) for i in galv_ids), 2), "€",
                               "Σ galvanising over categories", inputs=galv_ids, group="paint") if galv_ids else None
    painted_area = reg.calculated("total.painted_area", "Painted area", round(sum(reg.val(c.area_id) for c in cats if c.included and
                                                                                   normalize_system(str(reg.val(c.surface_id))) not in ("HDG", "NONE")), 1),
                                  "m²", "Σ area of painted categories", inputs=[c.area_id for c in cats if c.included], group="paint")
    # cost groups
    group_ids = {}
    for grp in ("Material", "Labour", "Surface treatment", "Packaging"):
        ids_ = totals.get(grp, [])
        group_ids[grp] = reg.calculated(f"total.cost.{slug(grp)}", f"{grp} (before margin)", round(sum(reg.val(i) for i in ids_), 2), "€",
                                        f"Σ {grp.lower()} over categories", inputs=ids_, group="cost")
    steel_sale = reg.calculated("total.steel_sale", "Steel structures (fabrication price)", round(sum(reg.val(i) for i in totals["Sale"]), 2), "€",
                                "Σ category prices", inputs=totals["Sale"], group="cost")
    extras_ids = [x["sale_id"] for x in extra_lines]
    margin_amount = reg.calculated("total.margin", "Margin", round(reg.val(steel_sale) - sum(reg.val(group_ids[g]) for g in group_ids), 2), "€",
                                   "price − costs before margin", inputs=[steel_sale] + list(group_ids.values()), kn=["GEN-03", "GEN-04"],
                                   group="cost")
    detailed_total = reg.calculated("total.price.detailed", "Total price — detailed method",
                                    round(reg.val(steel_sale) + sum(reg.val(i) for i in extras_ids) + reg.val(tr_id), 2), "€",
                                    "steel structures + fasteners and allowances + transport",
                                    inputs=[steel_sale] + extras_ids + [tr_id], group="cost")

    # ------------------------------------------------------------------ quick €/t method
    ctx.data["mat_lines"] = mat_lines
    quick = _quick_method(ctx, cats, params, rate, m_mat, m_prod)
    quick_total = reg.calculated("total.price.quick", "Total price — quick €/t method",
                                 round(sum(reg.val(q["sale_id"]) for q in quick) + sum(reg.val(i) for i in extras_ids) + reg.val(tr_id), 2), "€",
                                 "Σ tonnes × €/t per category + fasteners and allowances + transport",
                                 inputs=[q["sale_id"] for q in quick] + extras_ids + [tr_id], group="cost")
    quick_hours = reg.calculated("total.hours.quick", "Workshop hours — quick method", round(sum(reg.val(q["hours_id"]) for q in quick), 1), "h",
                                 "Σ tonnes × h/t per category (plate-share adjusted)", inputs=[q["hours_id"] for q in quick], group="hours")
    gap = (reg.val(detailed_total) - reg.val(quick_total)) / reg.val(quick_total) if reg.val(quick_total) else 0
    gap_id = reg.calculated("total.method_gap", "Gap detailed vs quick", round(gap, 4), "share", "(detailed − quick) ÷ quick",
                            inputs=[detailed_total, quick_total], group="cost")
    level = ctx.data["filemap"].level
    has_parts = ctx.data.get("quantity_source_kind") in ("ifc", "pdf")
    method = "detailed" if level == "full" or (level == "draft" and has_parts) else "quick"
    mov = ctx.override("param", "method")
    if mov is not None and mov.value in ("detailed", "quick"):
        method = mov.value
    chosen = detailed_total if method == "detailed" else quick_total
    price_id = reg.calculated("total.price", "Total price", reg.val(chosen), "€",
                              f"{'detailed part-by-part' if method == 'detailed' else 'quick €/t'} method "
                              f"({'chosen by the estimator' if mov else 'default for a ' + level + ' project'})",
                              inputs=[chosen], editable=True, edit_key="param:method", allowed=["detailed", "quick"], group="cost")

    # ------------------------------------------------------------------ uncertainty range
    comps = []
    for c in cats:
        ck = (c.name.split(" — ")[0], c.phase or "")
        if not c.included:
            continue
        b_kg = _band(ctx, reg.values[c.kg_id])
        b_rate = float(kb.num("uncertainty_rates", 0.03)[0])
        comps.append((reg.val(f"c.{slug(c.name)}.material") * m_mat, math.hypot(b_kg, b_rate)))
        hb = 0.0
        for hid in cat_metal_hours.get(ck, []):
            hv = reg.values[hid]
            ib = max((_band(ctx, reg.values[i]) for i in hv.inputs if i in reg.values), default=0.06)
            hb = max(hb, ib) if hv.label.endswith("welding hours") else hb
        comps.append((reg.val(f"c.{slug(c.name)}.labour") * m_prod, math.hypot(0.08, hb)))
        sid = surf_cost_ids.get(ck)
        if sid:
            sb = _band(ctx, reg.values[c.surface_id])
            comps.append((reg.val(sid) * m_prod, math.hypot(0.05, sb)))
    for x in extra_lines:
        v = reg.values.get(x.get("qty_id") or "") or reg.values[x["sale_id"]]
        comps.append((reg.val(x["sale_id"]), _band(ctx, v) + 0.05))
    comps.append((reg.val(tr_id), 0.10))
    spread = math.sqrt(sum((a * b) ** 2 for a, b in comps))
    total = reg.val(price_id)
    method_gap_band = abs(gap) * 0.25 * total
    spread = math.hypot(spread, method_gap_band)
    low = reg.calculated("total.price.low", "Price range — low", round(total - spread, 0), "€",
                         "total − √Σ(component × band)² (bands by value type and confidence)", inputs=[price_id],
                         kn=["GEN-10", "GEN-11", "GEN-12", "GEN-13"], group="cost")
    high = reg.calculated("total.price.high", "Price range — high", round(total + spread, 0), "€",
                          "total + √Σ(component × band)² (bands by value type and confidence)", inputs=[price_id],
                          kn=["GEN-10", "GEN-11", "GEN-12", "GEN-13"], group="cost")

    # ------------------------------------------------------------------ fire protection option (never in the base price)
    fire_v = reg.get(ctx.data["facts"]["ids"].get("fire_rating"))
    fire_req = [r for r in ctx.data["facts"]["requirements"] if r["kind"] == "fire_rating"]
    if fire_req:
        rating = None
        if fire_v and re.search(r"R\s?(15|30|45|60|90|120)", str(fire_v.value)):
            rating = re.search(r"R\s?(15|30|45|60|90|120)", str(fire_v.value)).group(0).replace(" ", "")
        if not rating:
            rating, _ = kb.prediction("default_fire_rating_option", "R30")
        fp = kb.fire(str(rating)) or kb.fire("R30")
        if fp is not None:
            area = reg.val(painted_area)
            per = (float(fp["layers"]) * (float(fp["material_eur_m2_layer"]) + float(fp["labour_eur_m2_layer"])) +
                   float(fp["topcoat_eur_m2"])) * float(fp["margin"])
            fvid = reg.calculated("option.fire", f"Option: fire protection {fp['rating']} on all painted steel", round(area * per, 0), "€",
                                  f"painted area × ({fp['layers']} layer(s) × ({fp['material_eur_m2_layer']} + {fp['labour_eur_m2_layer']}) + "
                                  f"{fp['topcoat_eur_m2']} top coat) × {fp['margin']}", inputs=[painted_area], kn=[fp.id], group="options")
            ctx.data["fire_option"] = {"rating": fp["rating"], "area": area, "total": reg.val(fvid), "vid": fvid}

    # ------------------------------------------------------------------ offer lines (client version) & results
    offer = []
    for c in cats:
        ck = (c.name.split(" — ")[0], c.phase or "")
        if not c.included:
            continue
        kg = reg.val(c.kg_id)
        sale = reg.val(cat_sale[ck])
        info = kb.category_info(ck[0])
        offer.append({"kind": "steel", "category": ck[0], "phase": c.phase, "label": (info["offer_label"] if info else ck[0]),
                      "surface": normalize_system(str(reg.val(c.surface_id))), "qty_id": c.kg_id, "unit": "kg",
                      "price_id": cat_sale[ck], "unit_price": round(sale / kg, 2) if kg else None, "kg": kg})
    ctx.data.update({
        "hours_rows": hours_rows, "paint_rows": paint_rows, "cost_lines": cost_lines, "extra_lines": extra_lines,
        "offer_lines": offer, "mat_lines": mat_lines, "quick": quick,
        "totals": {"price": price_id, "price_low": low, "price_high": high, "detailed": detailed_total, "quick": quick_total,
                   "gap": gap_id, "method": method, "steel_sale": steel_sale, "margin": margin_amount, "groups": group_ids,
                   "hours": tot_h, "metal_hours": tot_metal_h, "quick_hours": quick_hours, "labour_cost": lab_total,
                   "paint_litres": paint_l, "litres_by_product": litres_tot, "paint_cost": paint_cost, "galv_cost": galv_cost,
                   "painted_area": painted_area, "op_hours": op_totals, "cat_hours": cat_h_totals, "transport": tr_id,
                   "waste_kg": waste_id, "reusable_kg": reuse_id, "bought_kg": bought_id, "waste_share": waste_share_id,
                   "bolts_kg": bk_id if bolts_kg else None},
    })


def _quick_method(ctx: RunContext, cats, params, rate, m_mat, m_prod) -> list[dict[str, Any]]:
    kb, reg = ctx.kb, ctx.reg
    slope, slope_id = kb.num("plate_share_hours_slope", 3.7)
    out = []
    # project steel price level vs the reference list of each category
    mat_lines = ctx.data.get("mat_lines", [])
    for c in cats:
        if not c.included:
            continue
        cat = c.name.split(" — ")[0]
        r = kb.ppt(cat)
        if r is None:
            continue
        kg = reg.val(c.kg_id)
        t = kg / 1000
        ps = reg.val(c.plate_share_id)
        lines = [m for m in mat_lines if m["category"] == cat and (m["phase"] or "") == (c.phase or "")]
        proj_eur = (sum(m["kg"] * m["eur_per_kg"] for m in lines) / sum(m["kg"] for m in lines)) if lines and sum(m["kg"] for m in lines) else float(r["steel_eur_kg"])
        ratio = proj_eur / float(r["steel_eur_kg"])
        system = normalize_system(str(reg.val(c.surface_id)))
        m2t = (reg.val(c.area_id) / t) if t else float(r["m2_per_t"])
        if system == "HDG":
            surf_t = kb.surface_rate("HDG")[0] * 1000
        else:
            surf_t = kb.surface_rate(system)[0] * m2t
        h_t = float(r["hours_per_t"]) + slope * (ps - float(r["plate_share"])) / 0.10
        h_t = max(h_t, 0.5 * float(r["hours_per_t"]))
        prod_t = h_t * rate
        pack = reg.val(params["packaging_rate"]) * 1000
        eur_t = float(r["material_eur_t"]) * ratio * m_mat + (prod_t + surf_t + pack) * m_prod
        hid = reg.calculated(f"q.{slug(c.name)}.hours", f"{c.name} — hours (quick)", round(h_t * t, 1), "h",
                             f"{t:.2f} t × ({r['hours_per_t']} h/t + {slope} h/t per +10 % plates × ({ps:.2f} − {r['plate_share']}) ÷ 0.10)",
                             inputs=[c.kg_id, c.plate_share_id], kn=[r.id, slope_id], group="hours")
        rid = reg.calculated(f"q.{slug(c.name)}.eur_t", f"{c.name} — €/t (quick)", round(eur_t, 0), "€/t",
                             f"material {r['material_eur_t']} €/t × steel price ratio {ratio:.2f} × {m_mat:g} + "
                             f"(hours {h_t:.1f} h/t × {rate:g} €/h + surface {system} {surf_t:.0f} €/t + packaging {pack:.0f} €/t) × {m_prod:g}",
                             inputs=[c.plate_share_id, c.surface_id, c.area_id, params["labour_rate"]],
                             kn=[r.id, "SUR-" + system, "GEN-06"], group="cost")
        sid = reg.calculated(f"q.{slug(c.name)}.sale", f"{c.name} — price (quick)", round(eur_t * t, 2), "€", "tonnes × €/t",
                             inputs=[c.kg_id, rid], kn=[r.id], group="cost")
        out.append({"category": c.name, "eur_t_id": rid, "sale_id": sid, "hours_id": hid, "ref_project": r["reference_project"],
                    "kn": r.id})
    return out
