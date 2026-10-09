"""Stage 3 — Structured takeoff: metal-only quantities per line and category, features per group,
every value with a reference; conflicts shown, never resolved silently."""
from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Any, Optional

from ..ai.schemas import FACT_CATALOG
from ..knowledge.base import normalize_system
from ..models import CategorySummary, ConflictOption, Edit, Fact, Ref, TakeoffLine, V
from ..parsers import pdfdoc
from ..parsers.profiles import parse_profile, section_props
from ..values import fmt_num, slug
from .context import RunContext
from .filemap import entry_path

SINGLE_VALUED = {"bid_deadline", "delivery_address", "delivery_country", "execution_class", "tolerance_class",
                 "corrosivity_class", "durability", "delivery_terms", "project_number", "estimated_weight",
                 "longest_piece", "offer_validity", "currency", "paint_color", "epd_required"}
SOURCE_RANK = {"pdf": 0, "text": 1, "docx": 1, "email": 2, "pdf-hits": 3, "image": 4, "sheet": 1}


# ------------------------------------------------------------------------------------------------ refs
def ifc_ref(e, guids: list[str], label: str, snippet: str) -> Ref:
    return Ref(kind="ifc_elements", file_id=e.id, path=e.path, guids=guids, label=label, snippet=snippet)


def doc_ref(ctx: RunContext, entry, kind: str, snippet: str, page: int = 0) -> Ref:
    if kind in ("pdf", "pdf-hits") and page:
        try:
            boxes = pdfdoc.find_bbox(entry_path(ctx, entry), page, snippet)
        except Exception:
            boxes = []
        return Ref(kind="pdf_page", file_id=entry.id, path=entry.path, page=page, bboxes=boxes,
                   bbox=boxes[0] if boxes else None, snippet=snippet, label=f"{entry.name} · page {page}")
    if kind == "email":
        return Ref(kind="email", file_id=entry.id, path=entry.path, snippet=snippet, label=f"{entry.name} · e-mail text")
    if kind == "image":
        return Ref(kind="image", file_id=entry.id, path=entry.path, snippet=snippet, label=f"{entry.name} · image")
    return Ref(kind="text", file_id=entry.id, path=entry.path, snippet=snippet, label=entry.name)


# ------------------------------------------------------------------------------------------------ main
def build_takeoff(ctx: RunContext) -> None:
    ex = ctx.data["extract"]
    reg = ctx.reg
    parts, assemblies, source_note = _collect_parts(ctx, ex)
    ctx.data["parts"] = parts
    ctx.data["assemblies"] = assemblies
    ctx.data["quantity_source"] = source_note
    facts = consolidate_facts(ctx, ex)
    ctx.data["facts"] = facts
    surfaces = _surface_by_phase(ctx, facts)
    ctx.data["surface_rules"] = surfaces
    _build_lines(ctx, parts, assemblies, surfaces)
    _cross_checks(ctx, ex)
    _messy_flags(ctx, ex)


# ------------------------------------------------------------------------------------------------ parts
def _cat_for(ctx: RunContext, names: list[Optional[str]], main_profile: Optional[str]) -> tuple[str, Optional[str], Optional[str]]:
    kb = ctx.kb
    prof = parse_profile(main_profile or "")
    if prof.family == "D":
        return "Tension rods", "CAT-06", f"main part is a round bar ({prof.canonical})"
    cat, kid, kw = kb.map_category(*names)
    if cat:
        return cat, kid, f"name '{next((n for n in names if n and kw in str(n).lower()), names[0])}' matches keyword '{kw}'"
    return "Other steel", None, f"name '{names[0] or '?'}' is not in the category map"


def _collect_parts(ctx: RunContext, ex: dict[str, Any]) -> tuple[list[dict], dict[str, dict], str]:
    parts: list[dict] = []
    assemblies: dict[str, dict] = {}
    models = ex["models"]
    lists = [x for x in ex["pdf_lists"] if x["data"]["kind"] == "assembly-list" and x["data"]["assemblies"]]
    boms = ex["boms"]
    i_table = ctx.kb.i_table()
    if models:
        source = "ifc"
        for m in models:
            e, d = m["entry"], m["data"]
            by_asm: dict[str, list[dict]] = defaultdict(list)
            for el in d["elements"]:
                by_asm[el.get("assembly") or el["guid"]].append(el)
            bolts_by_asm: dict[str, list[dict]] = defaultdict(list)
            for b in d["bolts"]:
                bolts_by_asm[b.get("assembly") or ""].append(b)
            for akey, els in by_asm.items():
                main = max(els, key=lambda x: x.get("weight") or 0)
                ainfo = d["assemblies"].get(akey, {})
                aname = ainfo.get("name") or main.get("assembly_name") or main.get("name")
                cat, kid, why = _cat_for(ctx, [aname, main.get("name")], main.get("profile"))
                phase = str(main.get("phase")) if main.get("phase") is not None else None
                ak = f"{e.id}:{akey}"
                bl = bolts_by_asm.get(akey, [])
                assemblies[ak] = {"key": ak, "label": aname, "mark": ainfo.get("mark"), "category": cat, "category_kn": kid,
                                  "category_why": why, "phase": phase, "pieces": 1, "file": e, "source": "ifc",
                                  "bolts": sum(int(b.get("count") or 1) for b in bl), "bolt_groups": bl,
                                  "kg": sum(x.get("weight") or 0 for x in els), "class": main.get("class")}
                for el in els:
                    prof = parse_profile(el.get("profile"))
                    is_plate = prof.is_plate or el["entity"] == "IfcPlate"
                    t = prof.thickness if prof.is_plate else (float(el["width"]) if el["entity"] == "IfcPlate" and el.get("width") else prof.thickness)
                    width = prof.dims.get("w") if prof.is_plate else None
                    if is_plate and not width and el.get("height"):
                        width = float(el["height"])
                    parts.append({
                        "uid": el["guid"], "source": "ifc", "file": e, "assembly": ak, "category": cat, "phase": phase,
                        "is_main": el is main, "profile": el.get("profile") or "?", "prof": prof,
                        "family": "PL" if is_plate and prof.family not in ("PL", "FL") else prof.family,
                        "is_plate": is_plate, "t": t, "w": width, "length": float(el.get("length") or 0),
                        "pieces": 1, "kg": float(el.get("weight") or 0), "area": el.get("area"),
                        "grade": el.get("grade"), "guid": el["guid"], "entity": el["entity"], "name": el.get("name"),
                        "cls": el.get("class"),
                    })
        note = f"IFC model{'s' if len(models) > 1 else ''}: " + ", ".join(m["entry"].name for m in models)
    elif lists:
        source = "pdf"
        for lst in lists:
            e, d = lst["entry"], lst["data"]
            parts_by_asm: dict[str, list[dict]] = defaultdict(list)
            for p in d["parts"]:
                parts_by_asm[p.get("assembly") or ""].append(p)
            for a in d["assemblies"]:
                ak = f"{e.id}:{a['position']}"
                aparts = parts_by_asm.get(a["position"], [])
                main = max(aparts, key=lambda x: x.get("weight_sum") or 0) if aparts else None
                cat, kid, why = _cat_for(ctx, [a.get("name"), main.get("profile") if main else None], main.get("profile") if main else None)
                pcs = float(a.get("pcs") or 1)
                assemblies[ak] = {"key": ak, "label": a.get("name"), "mark": a["position"], "category": cat, "category_kn": kid,
                                  "category_why": why, "phase": None, "pieces": pcs, "file": e, "source": "pdf",
                                  "bolts": 0, "bolt_groups": [], "kg": float(a.get("weight_sum") or 0),
                                  "area": float(a.get("area") or 0) * pcs if a.get("area") else None,
                                  "page": a["page"], "bbox": a["bbox"], "text": a["text"], "length": a.get("length")}
                if not aparts:
                    aparts = [{"position": a["position"], "profile": a.get("name") or "?", "material": "", "pcs": pcs,
                               "length": a.get("length"), "width": a.get("width"), "height": a.get("height"),
                               "weight": a.get("weight"), "weight_sum": a.get("weight_sum"), "page": a["page"],
                               "bbox": a["bbox"], "text": a["text"]}]
                psum = sum(float(p.get("weight_sum") or 0) for p in aparts) or 1.0
                scale = (float(a.get("weight_sum") or psum)) / psum  # parts may round differently than the assembly
                for p in aparts:
                    prof = parse_profile(p.get("profile"))
                    t = prof.thickness if prof.is_plate else None
                    width = prof.dims.get("w") if prof.is_plate else None
                    if prof.family == "OTHER" and str(p.get("profile", "")).upper().startswith("CFJ"):
                        prof.family = "PL"
                    parts.append({
                        "uid": f"{e.id}:{a['position']}:{p['position']}", "source": "pdf", "file": e, "assembly": ak,
                        "category": cat, "phase": None, "is_main": p is main, "profile": p.get("profile") or "?", "prof": prof,
                        "family": prof.family, "is_plate": prof.is_plate, "t": t, "w": width,
                        "length": float(p.get("length") or 0), "pieces": float(p.get("pcs") or 1),
                        "kg": float(p.get("weight_sum") or 0) * scale, "area": None, "grade": p.get("material") or None,
                        "page": p.get("page"), "bbox": p.get("bbox"), "text": p.get("text"), "position": p.get("position"),
                    })
        note = "Assembly part lists printed in the drawings: " + ", ".join(x["entry"].name for x in lists)
    elif boms:
        source = "bom"
        for b in boms:
            e, d = b["entry"], b["data"]
            m = re.search(r"phase\s*([\d+ ]+)", e.name, re.I)
            phase = m.group(1).replace(" ", "") if m else None
            for ln in d["lines"]:
                prof = parse_profile(ln["profile"])
                ak = f"{e.id}:row{ln['row']}"
                cat = "Other steel"
                assemblies[ak] = {"key": ak, "label": ln.get("position") or ln["profile"], "mark": ln.get("position"),
                                  "category": cat, "category_kn": None, "category_why": "material list has no element types",
                                  "phase": phase, "pieces": ln["qty"], "file": e, "source": "bom", "bolts": 0,
                                  "bolt_groups": [], "kg": ln["kg"]}
                parts.append({"uid": ak, "source": "bom", "file": e, "assembly": ak, "category": cat, "phase": phase,
                              "is_main": True, "profile": ln["profile"], "prof": prof, "family": prof.family,
                              "is_plate": prof.is_plate, "t": prof.thickness if prof.is_plate else None,
                              "w": prof.dims.get("w"), "length": float(ln.get("length_mm") or 0), "pieces": ln["qty"],
                              "kg": ln["kg"], "area": None, "grade": ln.get("material"), "sheet": ln["sheet"],
                              "row": ln["row"], "range": ln["range"], "cells": ln["cells"]})
        note = "Material lists: " + ", ".join(b["entry"].name for b in boms)
    else:
        source = "none"
        note = "No quantities found in the files (idea level): quantities are predicted"
    ctx.data["quantity_source_kind"] = source
    # areas for parts without one (lists / BOM): profile tables or plate geometry
    for p in parts:
        if p.get("area") is None:
            p["area"], p["area_how"] = _area_for(ctx, p, i_table)
    return parts, assemblies, note


def _area_for(ctx: RunContext, p: dict, i_table: dict) -> tuple[Optional[float], str]:
    prof = p["prof"]
    L = (p.get("length") or 0) / 1000.0
    if p["is_plate"] and p.get("t") and p.get("w") and L:
        per_piece = (2 * L * p["w"] / 1000.0) + 2 * (L + p["w"] / 1000.0) * (p["t"] / 1000.0)
        return per_piece * p["pieces"], "plate: 2 faces + edges"
    kgm, m2m, kid = ctx.kb.profile_props(prof)
    if m2m is None:
        kgm, m2m = section_props(prof, i_table)
        kid = None
    if m2m and L:
        return m2m * L * p["pieces"], (f"knowledge {kid}" if kid else "nominal dimensions")
    if m2m and kgm and p.get("kg"):
        return m2m * p["kg"] / kgm, (f"knowledge {kid}" if kid else "nominal dimensions")
    # fallback: m²/t of the category
    info = ctx.kb.category_info(p["category"])
    m2t = float(info.get("m2_per_t", 20) if info else 20)
    return m2t * p["kg"] / 1000.0, f"category {info.id if info else ''} m²/t"


# ------------------------------------------------------------------------------------------------ facts
def _norm_value(key: str, v: str) -> str:
    s = (v or "").strip().lower()
    if key in ("bid_deadline", "inquiry_date", "offer_validity"):
        d = _parse_date(s)
        return d.isoformat() if d else s
    if key == "delivery_address":
        return re.sub(r"[^a-z0-9æøåäöõü]", "", s)
    if key in ("estimated_weight", "longest_piece"):
        m = re.search(r"\d+(?:[.,]\d+)?", s)
        return str(float(m.group(0).replace(",", "."))) if m else s
    if key == "execution_class":
        m = re.search(r"exc\s*([1-4])", s)
        return f"exc{m.group(1)}" if m else s
    if key == "paint_color":
        m = re.search(r"\d{4}", s)
        return m.group(0) if m else s
    if key == "epd_required":
        return "yes" if s.startswith(("yes", "ja", "true", "☒ yes")) else s
    return re.sub(r"\s+", "", s)


def _parse_date(s: str) -> Optional[date]:
    s = s.strip()
    for fmt in ("%d.%m.%Y", "%d.%m.%y", "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10] if fmt != "%d.%m.%y" else s[:8], fmt).date()
        except ValueError:
            continue
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"(\d{1,2})[.\-/](\d{1,2})[.\-/](\d{2,4})", s)
    if m:
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def consolidate_facts(ctx: RunContext, ex: dict[str, Any]) -> dict[str, Any]:
    reg = ctx.reg
    cands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scope: list[dict[str, Any]] = []
    reqs: list[dict[str, Any]] = []
    flags: list[dict[str, Any]] = []
    for doc in ex["docs"] + [{"entry": d["entry"], "result": d["result"], "kind": "image", "text": None} for d in ex["drawings"]]:
        e, res, kind = doc["entry"], doc["result"], doc["kind"]
        for f in res.facts:
            ref = doc_ref(ctx, e, kind, f.snippet, f.page)
            cands[f.key].append({"value": f.value, "unit": f.unit, "ref": ref, "conf": f.confidence, "kind": kind,
                                 "rank": SOURCE_RANK.get(kind, 5), "file": e})
        for s in res.scope_items:
            scope.append({"item": s.item, "status": s.status, "quantity": s.quantity, "ref": doc_ref(ctx, e, kind, s.snippet, s.page)})
        for r in res.requirements:
            ref = doc_ref(ctx, e, kind, r.snippet, r.page)
            key = (r.kind, re.sub(r"[^a-z0-9]", "", r.text.lower())[:60])
            same = next((x for x in reqs if x["key"] == key), None)
            if same:
                if len(same["refs"]) < 8:
                    same["refs"].append(ref)
                continue
            reqs.append({"kind": r.kind, "text": r.text, "impact": r.cost_impact, "ref": ref, "refs": [ref], "file": e, "key": key})
        for fl in res.flags:
            flags.append({"kind": fl.kind, "detail": fl.detail, "ref": doc_ref(ctx, e, kind, fl.snippet, fl.page)})
    # material-list header facts (code)
    for b in ex["boms"]:
        meta = b["data"].get("meta", {})
        e = b["entry"]
        if "exc" in meta:
            m = meta["exc"]
            cands["execution_class"].append({"value": m["value"], "unit": "", "conf": 0.95, "kind": "sheet", "rank": 1, "file": e,
                                             "ref": Ref(kind="sheet_cell", file_id=e.id, path=e.path, sheet=m["sheet"], cell=m["cell"],
                                                        row=int(re.sub(r"\D", "", m["cell"]) or 1), snippet=f"EXC: {m['value']}",
                                                        label=f"{e.name} · {m['sheet']}!{m['cell']}")})
    # e-mail dates are commercial facts
    for eid, mail in ctx.data.get("emails", {}).items():
        e = next((x for x in ctx.data["filemap"].entries if x.id == eid), None)
        if e is not None and mail.get("date") and e.status != "duplicate":
            cands["inquiry_date"].append({"value": mail["date"][:10], "unit": "", "conf": 0.99, "kind": "email", "rank": 2, "file": e,
                                          "ref": Ref(kind="email", file_id=e.id, path=e.path, snippet=f"Date: {mail['date']}",
                                                     label=f"{e.name} · header")})
    facts: dict[str, Any] = {"ids": {}, "scope": scope, "requirements": reqs, "flags": flags, "conflicts": []}
    for key, items in cands.items():
        if key not in FACT_CATALOG:
            continue
        group, label, _ = FACT_CATALOG[key]
        items.sort(key=lambda c: (c["rank"], -c["conf"]))
        by_norm: dict[str, list[dict]] = defaultdict(list)
        for c in items:
            by_norm[_norm_value(key, c["value"])].append(c)
        if key == "inquiry_date":
            # earliest date found
            best = min(items, key=lambda c: _parse_date(c["value"]) or date.max)
            vid = reg.extracted(f"fact.{key}", label, best["value"], None, [best["ref"]], confidence=best["conf"], group=group)
            facts["ids"][key] = vid
            continue
        if key in SINGLE_VALUED and len(by_norm) > 1:
            opts = []
            for nv, cs in by_norm.items():
                opts.append(ConflictOption(value=cs[0]["value"], unit=cs[0]["unit"] or None, refs=[c["ref"] for c in cs],
                                           note=f"{len(cs)} source(s)"))
            primary = items[0]
            vid = reg.extracted(f"fact.{key}", label, primary["value"], primary["unit"] or None,
                                [c["ref"] for c in items], confidence=0.5, conflict=opts, group=group,
                                editable=True, edit_key=f"fact:{key}",
                                reasoning="Sources disagree; the estimator must choose. Shown first: " + primary["file"].name)
            facts["conflicts"].append({"key": key, "label": label, "value_id": vid,
                                       "options": [o.model_dump() for o in opts]})
        elif key in SINGLE_VALUED:
            primary = items[0]
            vid = reg.extracted(f"fact.{key}", label, primary["value"], primary["unit"] or None,
                                [c["ref"] for c in items][:6], confidence=max(c["conf"] for c in items), group=group,
                                editable=True, edit_key=f"fact:{key}")
        else:
            uniq: list[dict] = []
            for nv, cs in by_norm.items():
                uniq.append(cs[0])
            uniq.sort(key=lambda c: (c["rank"], -c["conf"]))
            value = "; ".join(dict.fromkeys(c["value"] for c in uniq))
            vid = reg.extracted(f"fact.{key}", label, value, uniq[0]["unit"] or None,
                                [c["ref"] for c in items][:8], confidence=max(c["conf"] for c in items), group=group,
                                editable=key in ("fire_rating", "paint_system", "recycled_content"), edit_key=f"fact:{key}")
        facts["ids"][key] = vid
    _apply_fact_overrides(ctx, facts)
    return facts


def _apply_fact_overrides(ctx: RunContext, facts: dict[str, Any]) -> None:
    for o in ctx.overrides_for("fact"):
        key = o.key
        vid = facts["ids"].get(key)
        label = FACT_CATALOG.get(key, ("specs", key, ""))[1]
        group = FACT_CATALOG.get(key, ("specs", key, ""))[0]
        if vid:
            v = ctx.reg.values[vid]
            v.edited = Edit(before=v.value, after=o.value, reason=o.reason, source=o.source, at=o.created_at)
            v.value = o.value
            v.confidence = 1.0
            v.conflict = []
            facts["conflicts"] = [c for c in facts["conflicts"] if c["key"] != key]
        else:
            vid = ctx.reg.extracted(f"fact.{key}", label, o.value, None,
                                    [Ref(kind="user_edit", label="Set by the estimator", snippet=o.text or o.reason or "")],
                                    confidence=1.0, group=group, editable=True, edit_key=f"fact:{key}",
                                    edited=Edit(before=None, after=o.value, reason=o.reason, source=o.source, at=o.created_at))
            facts["ids"][key] = vid


# ------------------------------------------------------------------------------------------------ surfaces
def _surface_by_phase(ctx: RunContext, facts: dict[str, Any]) -> dict[str, Any]:
    reg = ctx.reg
    ids = facts["ids"]
    rules: dict[str, Any] = {"by_phase": {}, "default": None, "default_vid": None, "how": None, "systems_found": []}
    sbp = reg.get(ids.get("surface_by_phase"))
    if sbp and sbp.value:
        txt = str(sbp.value)
        for m in re.finditer(r"(C[1-5][LMH]?|HDG)[^;:]*?phase\s*([\d\s+]+)", txt, re.I):
            for ph in re.findall(r"\d+", m.group(2)):
                rules["by_phase"][ph] = {"system": normalize_system(m.group(1)), "vid": sbp.id}
        for m in re.finditer(r"phase\s*([\d\s+]+?)\s*[:\-–]?\s*(?:painted\s*)?(C[1-5][LMH]?|HDG)", txt, re.I):
            for ph in re.findall(r"\d+", m.group(1)):
                rules["by_phase"].setdefault(ph, {"system": normalize_system(m.group(2)), "vid": sbp.id})
    ps = reg.get(ids.get("paint_system"))
    hits_count: Counter[str] = Counter()
    for h in ctx.data["extract"].get("pdf_hits", []):
        for x in h["hits"]:
            if x["key"] == "paint" and re.match(r"C[1-5]\.\d{2}", x["snippet"]):
                hits_count[normalize_system(x["snippet"][:5])] += 1
    if ps and ps.value:
        systems = [normalize_system(s) for s in re.split(r";\s*", str(ps.value)) if s.strip()]
        systems = [s for s in systems if s in ctx.kb.surface_systems()]
        rules["systems_found"] = list(dict.fromkeys(systems))
        if systems:
            if hits_count:
                main_sys = max(set(systems), key=lambda s: hits_count.get(s, 0))
            else:
                main_sys = systems[0]
            rules["default"], rules["default_vid"], rules["how"] = main_sys, ps.id, "paint system stated in the files"
            if len(set(systems)) > 1:
                rules["mixed"] = {s: hits_count.get(s, 0) for s in set(systems)}
    if rules["default"] is None:
        cc = reg.get(ids.get("corrosivity_class"))
        du = reg.get(ids.get("durability"))
        if cc and cc.value:
            m = re.search(r"C([1-5])", str(cc.value))
            if m:
                d = (str(du.value).strip()[:2].upper() if du and du.value else "M")
                d = d if d in ("L", "M", "H", "VH") else "M"
                sys_ = normalize_system(f"C{m.group(1)}{d}")
                vid = reg.calculated("spec.surface_system", "Paint system from corrosivity + durability", sys_, None,
                                     f"corrosivity {cc.value} + durability {du.value if du else 'M (default)'} → {sys_}",
                                     inputs=[cc.id] + ([du.id] if du else []), kn=["SUR-" + sys_])
                rules["default"], rules["default_vid"], rules["how"] = sys_, vid, "corrosivity class and durability"
    if rules["default"] is None and not rules["by_phase"]:
        val, kid = ctx.kb.prediction("default_corrosivity_indoor", "C2M")
        vid = reg.predicted("spec.surface_system", "Paint system", normalize_system(str(val)), None,
                            "No paint system or corrosivity class found in the files: Maru's default for indoor halls is used.",
                            confidence=0.5, kn=[kid],
                            question="Which corrosivity class / paint system is required (ISO 12944)?",
                            editable=True, edit_key="fact:paint_system")
        rules["default"], rules["default_vid"], rules["how"] = normalize_system(str(val)), vid, "predicted (default)"
    return rules


# ------------------------------------------------------------------------------------------------ lines & categories
def _part_ref(p: dict, guids: Optional[list[str]] = None) -> Ref:
    e = p["file"]
    if p["source"] == "ifc":
        return ifc_ref(e, guids or [p["guid"]], f"{e.name} · {len(guids or [1])} element(s)",
                       f"{p['entity']} '{p['name']}' {p['profile']} {p['grade'] or ''}".strip())
    if p["source"] == "pdf":
        return Ref(kind="pdf_page", file_id=e.id, path=e.path, page=p["page"], bbox=p.get("bbox"),
                   bboxes=[p["bbox"]] if p.get("bbox") else [], snippet=p.get("text"), label=f"{e.name} · page {p['page']}")
    return Ref(kind="sheet_cell", file_id=e.id, path=e.path, sheet=p.get("sheet"), cell=p.get("range"), row=p.get("row"),
               snippet=" | ".join(str(c) for c in (p.get("cells") or []) if c not in (None, "")),
               label=f"{e.name} · {p.get('sheet')} row {p.get('row')}")


def _line_refs(lp: list[dict]) -> list[Ref]:
    first = lp[0]
    if first["source"] == "ifc":
        by_file: dict[str, list[dict]] = defaultdict(list)
        for p in lp:
            by_file[p["file"].id].append(p)
        refs = []
        for fid, ps in by_file.items():
            ents = Counter(p["entity"] for p in ps)
            refs.append(ifc_ref(ps[0]["file"], [p["guid"] for p in ps], f"{ps[0]['file'].name} · {len(ps)} element(s)",
                                f"{', '.join(f'{n}× {k}' for k, n in ents.items())} · profile {ps[0]['profile']} · {ps[0]['grade'] or ''} · Tekla Quantity: Weight, Net surface area, Length"))
        return refs
    refs = []
    seen = set()
    for p in lp:
        key = (p["file"].id, p.get("page"), p.get("row"))
        if key in seen:
            continue
        seen.add(key)
        refs.append(_part_ref(p))
        if len(refs) >= 12:
            break
    return refs


def _build_lines(ctx: RunContext, parts: list[dict], assemblies: dict[str, dict], surfaces: dict[str, Any]) -> None:
    reg, kb = ctx.reg, ctx.kb
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for p in parts:
        groups[(p["category"], p["phase"] or "", p["prof"].canonical if p["prof"].family != "OTHER" else p["profile"], p["grade"] or "")].append(p)
    order = {c: i for i, c in enumerate(kb.categories())}
    lines: list[TakeoffLine] = []
    cat_lines: dict[tuple[str, str], list[TakeoffLine]] = defaultdict(list)
    for (cat, phase, profile, grade), lp in sorted(groups.items(), key=lambda kv: (order.get(kv[0][0], 99), kv[0][1], kv[0][2])):
        lid = "L" + hashlib.sha1(f"{cat}|{phase}|{profile}|{grade}".encode()).hexdigest()[:8]
        refs = _line_refs(lp)
        src = lp[0]["source"]
        conf = 0.98 if src in ("ifc", "bom") else 0.95
        pieces = sum(p["pieces"] for p in lp)
        kg = sum(p["kg"] for p in lp)
        length_m = sum((p["length"] or 0) * p["pieces"] for p in lp) / 1000.0
        area = sum(p["area"] or 0 for p in lp)
        area_how = lp[0].get("area_how")
        label = f"{profile} {grade}".strip()
        base = f"line.{lid}"
        ov_pcs = ctx.override("line", lid, "pieces")
        ov_kg = ctx.override("line", lid, "kg")
        pieces_id = reg.extracted(f"{base}.pieces", f"{label} — pieces", pieces, "pcs", refs, confidence=conf,
                                  editable=True, edit_key=f"line:{lid}:pieces", group="quantities")
        kg_id = reg.extracted(f"{base}.kg", f"{label} — weight", round(kg, 2), "kg", refs, confidence=conf,
                              editable=True, edit_key=f"line:{lid}:kg", group="quantities")
        if ov_pcs is not None:
            v = reg.values[pieces_id]
            v.edited = Edit(before=v.value, after=float(ov_pcs.value), reason=ov_pcs.reason, source=ov_pcs.source, at=ov_pcs.created_at)
            ratio = float(ov_pcs.value) / (pieces or 1)
            v.value = float(ov_pcs.value)
            v.confidence = 1.0
            if ov_kg is None:
                kv = reg.values[kg_id]
                kv.edited = Edit(before=kv.value, after=round(kg * ratio, 2), reason="scaled with the edited piece count",
                                 source=ov_pcs.source, at=ov_pcs.created_at)
                kv.value = round(kg * ratio, 2)
                length_m *= ratio
                area *= ratio
                for p in lp:
                    p["pieces"] *= ratio
                    p["kg"] *= ratio
                    if p.get("area"):
                        p["area"] *= ratio
        if ov_kg is not None:
            kv = reg.values[kg_id]
            kv.edited = Edit(before=kv.value, after=float(ov_kg.value), reason=ov_kg.reason, source=ov_kg.source, at=ov_kg.created_at)
            ratio = float(ov_kg.value) / (kv.value or 1)
            kv.value = float(ov_kg.value)
            kv.confidence = 1.0
            for p in lp:
                p["kg"] *= ratio
        length_id = reg.extracted(f"{base}.length", f"{label} — total length", round(length_m, 2), "m", refs, confidence=conf,
                                  group="quantities") if length_m else None
        if src == "ifc":
            area_id = reg.extracted(f"{base}.area", f"{label} — surface area", round(area, 2), "m²", refs, confidence=conf, group="quantities")
        else:
            kn = [area_how.split("knowledge ")[1]] if area_how and "knowledge" in area_how else []
            area_id = reg.calculated(f"{base}.area", f"{label} — surface area", round(area, 2), "m²",
                                     f"area from {area_how or 'profile geometry'} × length", inputs=[length_id or kg_id], kn=kn,
                                     group="quantities")
        longest = max((p["length"] or 0) for p in lp)
        tl = TakeoffLine(id=lid, category=cat, phase=phase or None, profile=profile, family=lp[0]["family"], grade=grade or None,
                         is_plate=lp[0]["is_plate"], thickness_mm=lp[0].get("t"), source=src, pieces_id=pieces_id, kg_id=kg_id,
                         length_id=length_id, area_id=area_id, longest_mm=longest or None)
        for p in lp:
            p["line"] = lid
        lines.append(tl)
        cat_lines[(cat, phase)].append(tl)
    # category summaries
    cats: list[CategorySummary] = []
    for (cat, phase), tls in sorted(cat_lines.items(), key=lambda kv: (order.get(kv[0][0], 99), kv[0][1])):
        ckey = f"cat.{slug(cat)}" + (f".ph{phase}" if phase else "")
        name = cat + (f" — phase {phase}" if phase else "")
        kg_inputs = [t.kg_id for t in tls]
        kg = sum(reg.val(i) for i in kg_inputs)
        plate_kg = sum(reg.val(t.kg_id) for t in tls if t.is_plate or t.family == "WI")  # welded sections are made of plates
        kg_id = reg.calculated(f"{ckey}.kg", f"{name} — weight", round(kg, 1), "kg", "Σ line weights", inputs=kg_inputs, group="quantities")
        pcs_id = reg.calculated(f"{ckey}.pieces", f"{name} — pieces", sum(reg.val(t.pieces_id) for t in tls), "pcs",
                                "Σ line pieces", inputs=[t.pieces_id for t in tls], group="quantities")
        area_id = reg.calculated(f"{ckey}.area", f"{name} — surface area", round(sum(reg.val(t.area_id) for t in tls), 1), "m²",
                                 "Σ line surface areas", inputs=[t.area_id for t in tls], group="quantities")
        ps_id = reg.calculated(f"{ckey}.plate_share", f"{name} — plate share", round(plate_kg / kg, 3) if kg else 0, "share",
                               "kg of plates and welded sections ÷ total kg", inputs=[kg_id], group="quantities")
        # surface system: override > phase rule > project default
        ov = ctx.override("category", f"{cat}|{phase}", "surface") or ctx.override("category", cat, "surface")
        allowed = ctx.kb.surface_systems()
        if ov is not None:
            sys_ = normalize_system(str(ov.value))
            surf_id = reg.extracted(f"{ckey}.surface", f"{name} — surface treatment", sys_, None,
                                    [Ref(kind="user_edit", label="Set by the estimator", snippet=ov.text or ov.reason or "")],
                                    confidence=1.0, editable=True, edit_key=f"category:{cat}|{phase}:surface", allowed=allowed,
                                    edited=Edit(before=None, after=sys_, reason=ov.reason, source=ov.source, at=ov.created_at))
        elif phase and phase in surfaces["by_phase"]:
            r = surfaces["by_phase"][phase]
            src_v = reg.values[r["vid"]]
            surf_id = reg.extracted(f"{ckey}.surface", f"{name} — surface treatment", r["system"], None, src_v.refs,
                                    confidence=0.9, editable=True, edit_key=f"category:{cat}|{phase}:surface", allowed=allowed,
                                    reasoning=f"Phase {phase} → {r['system']} (surface treatment per phase in the inquiry)")
        elif surfaces["default"]:
            src_v = reg.values[surfaces["default_vid"]]
            if src_v.type == "predicted":
                surf_id = reg.predicted(f"{ckey}.surface", f"{name} — surface treatment", surfaces["default"], None,
                                        src_v.reasoning or "default", confidence=src_v.confidence, kn=src_v.kn,
                                        question=src_v.question, editable=True, edit_key=f"category:{cat}|{phase}:surface",
                                        allowed=allowed)
            elif src_v.type == "calculated":
                surf_id = reg.calculated(f"{ckey}.surface", f"{name} — surface treatment", surfaces["default"], None,
                                         src_v.formula or "", inputs=[src_v.id], kn=src_v.kn, editable=True,
                                         edit_key=f"category:{cat}|{phase}:surface", allowed=allowed)
            else:
                surf_id = reg.extracted(f"{ckey}.surface", f"{name} — surface treatment", surfaces["default"], None,
                                        src_v.refs[:4], confidence=0.85, editable=True,
                                        edit_key=f"category:{cat}|{phase}:surface", allowed=allowed,
                                        reasoning=f"Project paint system ({surfaces['how']})")
        else:
            val, kid = ctx.kb.prediction("default_corrosivity_indoor", "C2M")
            surf_id = reg.predicted(f"{ckey}.surface", f"{name} — surface treatment", normalize_system(str(val)), None,
                                    f"No surface treatment stated for phase {phase}; Maru default used", confidence=0.5, kn=[kid],
                                    question=f"Which surface treatment applies to phase {phase}?", editable=True,
                                    edit_key=f"category:{cat}|{phase}:surface", allowed=allowed)
        inc_ov = ctx.override("category", f"{cat}|{phase}", "included") or ctx.override("category", cat, "included")
        included = True if inc_ov is None else str(inc_ov.value).lower() not in ("false", "0", "no", "excluded")
        asm_count = len({p["assembly"] for p in ctx.data["parts"] if p["category"] == cat and (p["phase"] or "") == phase})
        cats.append(CategorySummary(name=name, phase=phase or None, kg_id=kg_id, pieces_id=pcs_id, area_id=area_id,
                                    plate_share_id=ps_id, surface_id=surf_id,
                                    longest_mm=max((t.longest_mm or 0) for t in tls) or None, included=included,
                                    assemblies=asm_count))
        for t in tls:
            t.surface = reg.val(surf_id, None)
            t.included = included
    ctx.data["lines"] = lines
    ctx.data["categories"] = cats


# ------------------------------------------------------------------------------------------------ checks & flags
def _cross_checks(ctx: RunContext, ex: dict[str, Any]) -> None:
    reg = ctx.reg
    cats = ctx.data["categories"]
    total_all = sum(reg.val(c.kg_id) for c in cats)  # whole takeoff: compared with the client's lists
    total = sum(reg.val(c.kg_id) for c in cats if c.included)  # in scope: what is priced
    out_of_scope = total_all - total
    tol = float(ctx.kb.num("conflict_tolerance", 0.01)[0])
    checks: list[dict[str, Any]] = []
    src_kind = ctx.data.get("quantity_source_kind")
    refs: list[Ref] = []
    reasoning = None
    conflict: list[ConflictOption] = []
    if src_kind in ("ifc", "pdf") and ex["boms"]:
        declared = []
        for b in ex["boms"]:
            dt = b["data"].get("declared_total") or {}
            e = b["entry"]
            val = dt.get("value") or b["data"].get("total_kg")
            declared.append(val)
            refs.append(Ref(kind="sheet_cell", file_id=e.id, path=e.path, sheet=dt.get("sheet"), cell=dt.get("cell"),
                            row=int(re.sub(r"\D", "", dt.get("cell") or "1") or 1), snippet=f"{dt.get('label', 'Total')}: {fmt_num(val, 2)} kg",
                            label=f"{e.name} · total"))
        bom_total = sum(declared)
        diff = (total_all - bom_total) / bom_total if bom_total else 0
        checks.append({"what": "Model total vs material lists", "a": total_all, "b": bom_total, "diff": diff, "ok": abs(diff) <= tol})
        if abs(diff) <= tol:
            reasoning = (f"Confirmed by the material lists: {' + '.join(fmt_num(d, 2) for d in declared)} kg "
                         f"= {fmt_num(bom_total, 2)} kg (difference {diff * 100:+.2f} %).")
        else:
            conflict = [ConflictOption(value=round(total_all, 1), unit="kg", note="takeoff (model)"),
                        ConflictOption(value=round(bom_total, 1), unit="kg", refs=refs, note="material lists")]
            reasoning = f"Model and material lists differ by {diff * 100:+.1f} %: check which is current."
    if src_kind == "pdf":
        # part-list documents repeat the parts of the assembly lists: cross-check, never added
        pl = [x for x in ex["pdf_lists"] if x["data"]["kind"] == "part-list"]
        al = [x for x in ex["pdf_lists"] if x["data"]["kind"] == "assembly-list"]
        if pl and al:
            a_tot = {x["entry"].id: sum(float(a.get("weight_sum") or 0) for a in x["data"]["assemblies"]) for x in al}
            matched = []
            for x in pl:
                p_tot = sum(float(p.get("weight_sum") or 0) for p in x["data"]["parts"])
                best = min(al, key=lambda a: abs(a_tot[a["entry"].id] - p_tot))
                d = (p_tot - a_tot[best["entry"].id]) / a_tot[best["entry"].id] if a_tot[best["entry"].id] else 1
                matched.append((x, best, p_tot, d))
                refs.append(Ref(kind="pdf_page", file_id=x["entry"].id, path=x["entry"].path, page=(x["data"]["pages"] or [2])[0],
                                label=f"{x['entry'].name} · part list", snippet="PART LIST"))
            ok = [m for m in matched if abs(m[3]) <= 0.01]
            worst = max((abs(m[3]) for m in matched), default=0)
            checks.append({"what": "Part lists vs assembly lists (same parts printed twice)", "a": sum(m[2] for m in matched),
                           "b": sum(a_tot[m[1]["entry"].id] for m in matched), "diff": worst, "ok": len(ok) == len(matched)})
            reasoning = (f"{len(matched)} part-list drawing sets repeat the parts of {len({m[1]['entry'].id for m in matched})} "
                         f"assembly sets ({len(ok)} agree within 1 %, largest difference {worst * 100:.2f} %): counted once, "
                         "from the assembly lists.")
    total_id = reg.calculated("total.kg", "Total steel weight (in scope)", round(total, 1), "kg",
                              "Σ category weights in scope" + (f" ({fmt_num(out_of_scope, 0)} kg out of scope not counted)" if out_of_scope > 0.5 else ""),
                              inputs=[c.kg_id for c in cats if c.included], refs=refs, group="quantities")
    v = reg.values[total_id]
    if reasoning:
        v.reasoning = reasoning
    if conflict:
        v.conflict = conflict
        ctx.data.setdefault("quantity_conflicts", []).append(total_id)
    est = reg.get(ctx.data["facts"]["ids"].get("estimated_weight"))
    if est:
        try:
            est_kg = float(str(est.value).split(";")[0]) * (1000 if (est.unit or "t") in ("t", "tonnes", "tons") else 1)
            d = (total_all - est_kg) / est_kg
            checks.append({"what": "Takeoff vs client's estimate", "a": total_all, "b": est_kg, "diff": d, "ok": abs(d) < 0.1})
        except ValueError:
            pass
    ctx.data["checks"] = checks


def _messy_flags(ctx: RunContext, ex: dict[str, Any]) -> None:
    fm = ctx.data["filemap"]
    by_id = {e.id: e for e in fm.entries}
    flags: list[dict[str, Any]] = []
    for v in ctx.data.get("ifc_versions", []):
        a, b = by_id[v["older"]], by_id[v["newer"]]
        flags.append({"kind": "repeated", "title": "Items repeated across IFC files",
                      "detail": (f"{a.name} and {b.name} share {v['common']:,} elements. The newer {b.name} is used; "
                                 f"it removes {v['removed']:,} and adds {v['added']:,} elements compared to the first model."),
                      "refs": [Ref(kind="ifc_elements", file_id=b.id, path=b.path, label=b.name, snippet="newer model (used)"),
                               Ref(kind="ifc_elements", file_id=a.id, path=a.path, label=a.name, snippet="older model (not used)")]})
    for c in ctx.data.get("bom_combined", []):
        e = by_id[c["combined"]]
        flags.append({"kind": "repeated", "title": "Material list repeated",
                      "detail": f"{e.name} is the two phase lists combined ({c['kg']:,.0f} kg): counted once.",
                      "refs": [Ref(kind="sheet_cell", file_id=e.id, path=e.path, label=e.name, snippet="combined list")]})
    pl = [x for x in ex["pdf_lists"] if x["data"]["kind"] == "part-list"]
    if pl and any(x["data"]["kind"] == "assembly-list" for x in ex["pdf_lists"]):
        flags.append({"kind": "repeated", "title": "Parts listed twice in the drawings",
                      "detail": f"{len(pl)} part-drawing sets repeat the parts of the assembly drawings: counted once.",
                      "refs": [Ref(kind="pdf_page", file_id=x["entry"].id, path=x["entry"].path, page=(x["data"]["pages"] or [1])[0],
                                   label=x["entry"].name, snippet="PART LIST") for x in pl[:4]]})
    units = {b["data"].get("units", {}).get("weight") for b in ex["boms"]} | {b["data"].get("units", {}).get("length") for b in ex["boms"]}
    if len({b["data"].get("units", {}).get("weight") for b in ex["boms"]}) > 1 or len({b["data"].get("units", {}).get("length") for b in ex["boms"]}) > 1:
        flags.append({"kind": "units", "title": "Mixed units in material lists", "detail": "Lists use different units (kg/t or mm/m): converted.",
                      "refs": []})
    for f in ctx.data["facts"]["flags"]:
        if f["kind"] == "other_currency":
            flags.append({"kind": "currency", "title": "Prices in another currency", "detail": f["detail"], "refs": [f["ref"]]})
    ctx.data["messy_flags"] = flags
