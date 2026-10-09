"""Stage 4a — Risks and assumptions: fill the gaps visibly (predicted values with reasoning, confidence and a
question for the client), allowances for items mentioned but not modelled, ranked risks."""
from __future__ import annotations

import re
from typing import Any, Optional

from ..ai.base import AIError
from ..ai.schemas import FACT_CATALOG
from ..models import Edit, Question, Ref, Risk
from ..values import fmt_num
from .context import RunContext

TLD_COUNTRY = {"fi": "FI", "no": "NO", "se": "SE", "ee": "EE", "dk": "DK", "lv": "LV", "lt": "LT", "de": "DE"}
SUFFIX_COUNTRY = {"oy": "FI", "oyj": "FI", "ab": "SE", "a/s": "DK", "aps": "DK", "asa": "NO", "oü": "EE"}


def run_predict(ctx: RunContext) -> None:
    reg, kb = ctx.reg, ctx.kb
    facts = ctx.data["facts"]
    ids = facts["ids"]
    missing: list[dict[str, Any]] = []

    def need(key: str, allowed: Optional[list[str]], default: Any, kid: str, question: str, why: str, conf: float = 0.55) -> None:
        if key in ids:
            return
        missing.append({"key": key, "allowed": allowed, "default": default, "kn": kid, "question": question, "why": why,
                        "confidence": conf, "unit": ""})

    v, kid = kb.prediction("default_exc", "EXC2")
    need("execution_class", ["EXC1", "EXC2", "EXC3", "EXC4"], v, kid, "Which execution class (EN 1090-2) applies?",
         f"No execution class in the files; Maru's offers are normally EXC2 ({kid}).")
    v, kid = kb.prediction("default_grade_rolled", "S355J2")
    need("steel_grade", None, v, kid, "Which steel grades are required?", f"No steel grade in the files; Maru's standard ({kid}).", 0.6)
    v, kid = kb.prediction("default_tolerance", "class 1")
    need("tolerance_class", ["class 1", "class 2"], v, kid, "Which EN 1090-2 tolerance class is required?",
         f"Not stated; Maru's offers assume class 1 ({kid}).", 0.6)
    # destination country from e-mail domain / company suffix
    if "delivery_country" not in ids:
        guess, why, refs = _guess_country(ctx)
        if guess:
            missing.append({"key": "delivery_country", "allowed": list(ctx.company_cfg.get("country_rules", {}).keys()) + ["DK", "LV", "LT", "DE"],
                            "default": guess, "kn": "", "question": "Please confirm the delivery address.", "why": why,
                            "confidence": 0.6, "unit": "", "refs": refs})
    if missing:
        context = _context_text(ctx)
        try:
            res = ctx.provider.predict_missing([{k: m[k] for k in ("key", "allowed", "default", "question", "why", "confidence", "unit")}
                                                for m in missing], context, ctx.call_ctx(None, "predict_missing"))
            by_key = {p.key: p for p in res.predictions}
        except AIError as e:
            ctx.warnings.append(f"Predictions fell back to the knowledge-file defaults ({e})")
            by_key = {}
        for m in missing:
            p = by_key.get(m["key"])
            value = p.value if p else m["default"]
            reasoning = (p.reasoning if p else m["why"])
            conf = float(p.confidence) if p else m["confidence"]
            question = (p.question if p and p.question else m["question"])
            label = FACT_CATALOG[m["key"]][1]
            group = FACT_CATALOG[m["key"]][0]
            ov = ctx.override("fact", m["key"])
            vid = reg.predicted(f"fact.{m['key']}", label, value, m.get("unit") or None, reasoning, confidence=conf,
                                question=question, kn=[m["kn"]] if m.get("kn") else [], refs=m.get("refs") or [],
                                group=group, editable=True, edit_key=f"fact:{m['key']}", allowed=m.get("allowed"))
            if ov is not None:
                vv = reg.values[vid]
                vv.edited = Edit(before=vv.value, after=ov.value, reason=ov.reason, source=ov.source, at=ov.created_at)
                vv.value, vv.confidence = ov.value, 1.0
            ids[m["key"]] = vid
    _allowances(ctx)
    _longest_piece(ctx)


def _guess_country(ctx: RunContext) -> tuple[Optional[str], str, list[Ref]]:
    reg = ctx.reg
    ids = ctx.data["facts"]["ids"]
    em = reg.get(ids.get("client_email"))
    if em and em.value:
        tld = str(em.value).split(";")[0].strip().rsplit(".", 1)[-1].lower()
        if tld in TLD_COUNTRY:
            return TLD_COUNTRY[tld], f"No delivery address in the files; the client's e-mail domain ends in '.{tld}'.", em.refs[:1]
    for e in ctx.data["filemap"].entries:
        for word in re.findall(r"[A-Za-zÆØÅæøå/]+", e.name):
            if word.lower() in SUFFIX_COUNTRY:
                return SUFFIX_COUNTRY[word.lower()], f"Company form '{word}' in '{e.name}'", []
    comp = ctx.project.company.split()[-1].lower() if ctx.project.company else ""
    if comp in SUFFIX_COUNTRY:
        return SUFFIX_COUNTRY[comp], f"No delivery address in the files; the client company '{ctx.project.company}' is registered as '{comp.upper()}'.", []
    return None, "", []


def _context_text(ctx: RunContext) -> str:
    reg = ctx.reg
    lines = [f"Project: {ctx.project.name} (client {ctx.project.company})",
             f"Level: {ctx.data['filemap'].level}", f"Total steel: {fmt_num(reg.val('total.kg'), 0)} kg"]
    for k, vid in ctx.data["facts"]["ids"].items():
        v = reg.values[vid]
        lines.append(f"- {v.label}: {v.value} ({v.refs[0].label if v.refs else v.type})")
    for c in ctx.data["categories"]:
        lines.append(f"- category {c.name}: {fmt_num(reg.val(c.kg_id), 0)} kg, surface {reg.val(c.surface_id)}")
    return "\n".join(lines)


def _allowances(ctx: RunContext) -> None:
    """Items the client asks for that are not in the quantities: anchors, rebar studs, ..."""
    reg, kb = ctx.reg, ctx.kb
    facts = ctx.data["facts"]
    allowances: list[dict[str, Any]] = []
    scope = facts["scope"]
    # anchors with a stated quantity
    anchors = [s for s in scope if s["status"] == "included" and re.search(r"anchor|hilti|hus\d", s["item"], re.I) and s["quantity"]]
    if anchors:
        s = anchors[0]
        qty = float(re.sub(r"[^\d.]", "", s["quantity"]) or 0)
        ov = ctx.override("allowance", "anchors", "qty")
        vid = reg.extracted("allow.anchors.qty", f"Anchors {s['item']} — quantity", qty, "pcs", [s["ref"]], confidence=0.75,
                            editable=True, edit_key="allowance:anchors:qty",
                            reasoning="Quantity stated by the client as an assumption ('assume around …'): confirm.")
        if ov is not None:
            v = reg.values[vid]
            v.edited = Edit(before=v.value, after=float(ov.value), reason=ov.reason, source=ov.source, at=ov.created_at)
            v.value, v.confidence = float(ov.value), 1.0
        allowances.append({"key": "anchors", "label": f"Anchors {s['item']}", "qty_id": vid, "unit": "pcs", "kind": "anchors"})
    # rebar studs on deck beams: mentioned as required, flagged as missing from the model
    stud_scope = [s for s in scope if s["status"] == "included" and re.search(r"rebar|stud", s["item"], re.I)]
    missing_flag = [f for f in facts["flags"] if f["kind"] == "model_incomplete" and re.search(r"stud|rebar", f["ref"].snippet or "", re.I)]
    if stud_scope:
        s = stud_scope[0]
        deck = [c for c in ctx.data["categories"] if c.name.startswith("Welded beams")] or \
               [c for c in ctx.data["categories"] if c.name.startswith("Beams")]
        deck_lines = [l for l in ctx.data["lines"] if any(l.category == c.name.split(" — ")[0] and (l.phase or "") == (c.phase or "") for c in deck)]
        deck_len = sum(reg.val(l.length_id) for l in deck_lines if l.length_id and not l.is_plate)
        if deck_len == 0:
            deck_len = sum(reg.val(l.length_id) for l in deck_lines if l.length_id) / 3
        spacing, kid = kb.prediction("stud_spacing_per_m", 2)
        studs = round(deck_len * float(spacing))
        ov = ctx.override("allowance", "studs", "qty")
        refs = [s["ref"]] + [f["ref"] for f in missing_flag[:1]]
        qid = reg.predicted("allow.studs.qty", "Rebar studs ø20 on deck beams — quantity", studs, "pcs",
                            (f"The client requires rebar studs ø20 welded to the deck beams" +
                             (" and says they are missing from the model" if missing_flag else "") +
                             f". Estimated as {spacing} studs per metre ({kid}) over {fmt_num(deck_len, 0)} m of "
                             f"{', '.join(c.name for c in deck) or 'beams'}."),
                            confidence=0.35, kn=[kid], refs=refs, inputs=[l.length_id for l in deck_lines if l.length_id][:20],
                            question="How many rebar studs (ø20, length) per deck beam, or at what spacing?",
                            editable=True, edit_key="allowance:studs:qty")
        if ov is not None:
            v = reg.values[qid]
            v.edited = Edit(before=v.value, after=float(ov.value), reason=ov.reason, source=ov.source, at=ov.created_at)
            v.value, v.confidence = float(ov.value), 1.0
        allowances.append({"key": "studs", "label": "Rebar studs ø20 welded to deck beams (allowance)", "qty_id": qid,
                           "unit": "pcs", "kind": "studs"})
    ctx.data["allowances"] = allowances


def _longest_piece(ctx: RunContext) -> None:
    reg = ctx.reg
    ids = ctx.data["facts"]["ids"]
    scope = [c for c in ctx.data["categories"] if c.included]  # what is delivered decides the truck
    longest = max((c.longest_mm or 0) for c in scope) if scope else 0
    in_scope = {(c.name.split(" — ")[0], c.phase or "") for c in scope}
    lines = [l for l in ctx.data["lines"] if (l.longest_mm or 0) == longest and (l.category, l.phase or "") in in_scope] or \
            [l for l in ctx.data["lines"] if (l.longest_mm or 0) == longest]
    vid = reg.calculated("q.longest", "Longest piece in the takeoff", round(longest / 1000, 2), "m",
                         "max piece length over all lines", inputs=[l.kg_id for l in lines[:3]], group="logistics")
    ctx.data["longest_id"] = vid
    stated = reg.get(ids.get("longest_piece"))
    if stated:
        try:
            s = float(str(stated.value).split(";")[0])
        except ValueError:
            return
        v = reg.values[vid]
        v.refs = stated.refs[:2]
        if abs(s - longest / 1000) > 1.0:
            v.reasoning = (f"The client states about {s:g} m; the takeoff contains a {longest / 1000:.1f} m piece — "
                           "check transport and the model.")
        else:
            v.reasoning = f"Consistent with the client's statement ({s:g} m)."


def build_risks(ctx: RunContext) -> None:
    """Rank risks: cost-changing requirements → conflicts → missing scope / data → messy input → carbon."""
    reg = ctx.reg
    facts = ctx.data["facts"]
    risks: list[Risk] = []
    n = 0

    def add(sev: str, kind: str, title: str, detail: str, refs: list[Ref], vids: list[str] = (), question: Optional[str] = None) -> None:
        nonlocal n
        n += 1
        risks.append(Risk(id=f"R{n}", rank=0, severity=sev, kind=kind, title=title, detail=detail, refs=refs[:6],
                          value_ids=list(vids), question=question))

    order = {"fire_rating": 0, "galvanising": 2, "recycled_content": 1, "paint_system": 3, "epd": 4, "corrosivity": 5}
    reqs = sorted(facts["requirements"], key=lambda r: (order.get(r["kind"], 9), r["impact"] != "high"))
    seen_kind: set[str] = set()
    fire_opt = ctx.data.get("fire_option")
    for r in reqs:
        if r["kind"] in seen_kind:
            continue
        seen_kind.add(r["kind"])
        if r["kind"] == "fire_rating":
            detail = r["text"] + ". Fire protection is not in the base price."
            if fire_opt:
                detail += (f" If {fire_opt['rating']} applied to all painted steel it would add about "
                           f"€{fmt_num(fire_opt['total'], 0)} ({fmt_num(fire_opt['area'], 0)} m²).")
            add("high", "requirement", "Fire protection required", detail, r["refs"], [fire_opt["vid"]] if fire_opt else [],
                "Which members need fire protection and which class (R30/R60/R90, critical temperature)?")
        elif r["kind"] == "recycled_content":
            add("high", "requirement", "Recycled steel content required", r["text"] + ". Steel must be bought from EAF mills with certificates; affects price and supplier choice.",
                r["refs"], [facts["ids"].get("recycled_content", "")], "Which proof is needed (mill certificates, EPD)?")
        elif r["kind"] == "galvanising":
            add("high", "requirement", "Hot-dip galvanising for part of the steel", r["text"] + ". Priced per kg (galvaniser) instead of paint per m².",
                r["refs"], [facts["ids"].get("galvanising", "")])
        elif r["kind"] == "paint_system":
            mixed = ctx.data["surface_rules"].get("mixed")
            detail = r["text"]
            if mixed:
                detail += " — the drawings name more than one system: " + ", ".join(f"{k} on {v} page(s)" for k, v in mixed.items()) + "; the most frequent is used."
            add("high" if mixed else "medium", "requirement", "Paint system set by the drawings", detail, r["refs"],
                [facts["ids"].get("paint_system", "")], "Confirm the paint system for each member type." if mixed else None)
        elif r["kind"] == "epd":
            add("medium", "requirement", "EPD requested", r["text"] + ". Supplier EPDs (EN 15804) are needed for the carbon declaration.", r["refs"],
                [facts["ids"].get("epd_required", "")])
        else:
            add("medium" if r["impact"] != "high" else "high", "requirement", r["text"][:80], r["text"], r["refs"])
    for c in facts["conflicts"]:
        add("high", "conflict", f"Conflicting {c['label'].lower()}",
            " vs ".join(f"“{o['value']}”" for o in c["options"]) + ". Not resolved automatically.",
            [r for o in c["options"] for r in [Ref(**x) for x in o["refs"]]], [c["value_id"]],
            f"Which {c['label'].lower()} is correct?")
    for vid in ctx.data.get("quantity_conflicts", []):
        v = reg.values[vid]
        add("high", "conflict", "Quantities differ between sources", v.reasoning or "", v.refs, [vid])
    for f in facts["flags"]:
        if f["kind"] in ("model_incomplete", "missing_data"):
            add("high" if f["kind"] == "model_incomplete" else "medium", "missing", "Client says the model is incomplete",
                f["ref"].snippet or f["detail"], [f["ref"]], [], "When will the complete model be available?")
            break
    for a in ctx.data.get("allowances", []):
        v = reg.values[a["qty_id"]]
        if v.type == "predicted":
            add("medium", "missing", f"{a['label']}: quantity predicted", v.reasoning or "", v.refs, [a["qty_id"]], v.question)
    ids = facts["ids"]
    for key in ("delivery_address", "bid_deadline"):
        if key not in ids:
            add("medium", "missing", f"No {FACT_CATALOG[key][1].lower()} in the files", "Not found in any file.", [], [],
                f"What is the {FACT_CATALOG[key][1].lower()}?")
    for f in ctx.data.get("messy_flags", []):
        add("low", "messy", f["title"], f["detail"], f["refs"])
    for s in facts["scope"]:
        if s["status"] == "excluded" and re.search(r"plate|h-plate|disregard", s["item"], re.I):
            add("low", "scope", "Client asks to leave out part of the model", s["ref"].snippet or s["item"], [s["ref"]], [],
                None)
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    kind_rank = {"requirement": 0, "conflict": 1, "missing": 2, "scope": 3, "messy": 4, "carbon": 5, "other": 6}
    risks.sort(key=lambda r: (kind_rank.get(r.kind, 9) if r.kind == "requirement" else 1 + kind_rank.get(r.kind, 9), sev_rank[r.severity]))
    for i, r in enumerate(risks, 1):
        r.rank = i
    ctx.data["risks"] = risks
    # questions for the client: predicted values + conflicts + missing data
    qs: list[Question] = []
    seen_q: set[str] = set()
    for r in risks:
        if r.question and r.question not in seen_q:
            seen_q.add(r.question)
            qs.append(Question(id=f"Q{len(qs) + 1}", text=r.question, reason=r.title, value_ids=r.value_ids))
    for v in reg.values.values():
        if v.type == "predicted" and v.question and v.question not in seen_q and not v.edited:
            seen_q.add(v.question)
            qs.append(Question(id=f"Q{len(qs) + 1}", text=v.question, reason=f"{v.label} was predicted ({v.value})", value_ids=[v.id]))
    ctx.data["questions"] = qs
