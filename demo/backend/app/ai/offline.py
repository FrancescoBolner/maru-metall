"""Offline rules provider: same interface and schemas as the AI providers, implemented with patterns.

Used automatically when no API key is configured, so the demo runs end to end anywhere.
It only reads what is literally written (labels, ticked checkboxes, standard phrases); every value it
returns carries a verbatim snippet, exactly like the AI providers.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any, Optional

from .base import AIProvider, CallCtx, log_call
from .schemas import (AIChange, AIFact, AIFlag, AINotApplied, AINotFound, AIPrediction, AIRequirement, AIScopeItem,
                      CorrectionProposal, DocumentExtraction, DrawingExtraction, FileClassification, GuidelineExample,
                      GuidelinesUpdate, MissingPrediction)

CHECKED = "☒"
UNCHECKED = "☐"

# label (start of a form line) -> fact key
LABELS: list[tuple[str, str]] = [
    (r"project number|quotation no\.?|prosjektnummer|projekti(?:n)? numero", "project_number"),
    (r"project name|quotation name|prosjektnavn", "project_name"),
    (r"project leader|project manager|prosjektleder|filled by", "client_contact"),
    (r"deadline for receiving quotation|deadline price offer|offer deadline|tender deadline|deadline|tilbudsfrist", "bid_deadline"),
    (r"delivery ad+ress|delivery address|leveringsadresse|tarneaadress", "delivery_address"),
    (r"place", "delivery_address"),
    (r"country", "delivery_country"),
    (r"delivery time anchor groups|wsd from [\w ]+|contact person at site", "_skip"),
    (r"delivery time steel structures|delivery time", "delivery_time"),
    (r"longest assembly|longest piece|longest element|longest member", "longest_piece"),
    (r"estimated weight[^:]*", "estimated_weight"),
    (r"surface treatment and colou?r|surface treatment", "surface_by_phase"),
    (r"steel grade|material grade|steel quality", "steel_grade"),
    (r"workshop drawings", "workshop_drawings_by"),
    (r"erection", "erection_included"),
    (r"bolts and washers|bolts", "bolts"),
    (r"anchor groups|anchors", "anchors"),
    (r"execution class(?: \(exc\))?", "execution_class"),
    (r"geometrical tolerance(?: \(en 1090-2\))?|tolerance class", "tolerance_class"),
    (r"durability", "durability"),
    (r"ral code|colou?r", "paint_color"),
    (r"epd", "epd_required"),
    (r"intumescent coating", "fire_rating"),
    (r"if hdg", "galvanising"),
    (r"type of protection", "galvanising"),
    (r"terms|delivery terms|incoterms?", "delivery_terms"),
    (r"class", "corrosivity_class"),
    (r"date", "inquiry_date"),
]
COUNTRY_CODES = {"norway": "NO", "norge": "NO", "finland": "FI", "suomi": "FI", "sweden": "SE", "sverige": "SE",
                 "estonia": "EE", "eesti": "EE", "denmark": "DK", "danmark": "DK", "latvia": "LV", "lithuania": "LT",
                 "germany": "DE"}


def _checked(value: str) -> list[str]:
    """Options ticked in a checkbox list: '☐ EXC1 ☒ EXC2 ☐ EXC3' -> ['EXC2']."""
    out = []
    for m in re.finditer(CHECKED + r"\s*([^☐☒]+)", value):
        opt = re.sub(r"\s{2,}.*$", "", m.group(1).strip())
        opt = opt.strip()
        if opt:
            out.append(opt)
    return out


def _fact(key: str, value: str, snippet: str, page: int = 0, unit: str = "", conf: float = 0.9) -> AIFact:
    return AIFact(key=key, value=value.strip()[:200], unit=unit, snippet=snippet.strip()[:300], page=page, confidence=conf)


def _line_at(text: str, pos: int) -> str:
    s = text.rfind("\n", 0, pos) + 1
    e = text.find("\n", pos)
    return text[s: e if e >= 0 else len(text)].strip()


def _sentence_at(text: str, start: int, end: int) -> str:
    s = max(text.rfind(".", 0, start), text.rfind("\n", 0, start), text.rfind("*", 0, start)) + 1
    e_candidates = [i for i in (text.find(".", end), text.find("\n", end)) if i >= 0]
    e = min(e_candidates) if e_candidates else len(text)
    return text[s:e + (1 if e < len(text) and text[e] == "." else 0)].strip()


def _page_of(text: str, pos: int) -> int:
    m = None
    for m in re.finditer(r"\[page (\d+)\]", text[:pos]):
        pass
    return int(m.group(1)) if m else 0


class OfflineProvider(AIProvider):
    name = "offline"
    model = "rules-v1"
    sends_data_off_machine = False

    def _log(self, call: str, ctx: CallCtx, chars: int, result: Any, t0: float) -> None:
        log_call({"ts": datetime.now().isoformat(timespec="seconds"), "id": f"off-{int(t0 * 1000) % 10**9}",
                  "provider": self.name, "model": self.model, "call": call, "prompt_version": "rules-v1",
                  "project_id": ctx.project_id, "run_id": ctx.run_id, "file": ctx.file_name,
                  "input_summary": {"chars": chars, "images": 0}, "attempts": [{"n": 1, "errors": [],
                  "raw": json.dumps(result.model_dump(), ensure_ascii=False)[:20000]}],
                  "status": "ok", "duration_s": round(time.time() - t0, 3), "input_tokens": 0, "output_tokens": 0,
                  "cost_eur": 0.0})
        if ctx.usage:
            ctx.usage.add(calls=1, seconds=time.time() - t0)

    # ------------------------------------------------------------------------------------------
    def classify_file(self, file_name, file_kind, content, ctx):
        t0 = time.time()
        low = (file_name + " " + content).lower()
        metal = len(re.findall(r"steel|stål|teras|s355|s275|s235|\bhea\d|\bipe\d|\brhs|\bexc\d|weld|beam|column|bracing", low))
        other = len(re.findall(r"hvac|ventilat|plumbing|sanitar|electric|concrete|betong|betoon|timber|wood|glass|architect", low))
        if metal >= 3 and metal > other:
            res = FileClassification(status="metal-relevant", discipline="steel structure",
                                     reason=f"Mentions steel terms {metal} times", confidence=0.6)
        elif other > metal and other >= 2:
            res = FileClassification(status="not-relevant", discipline="other",
                                     reason=f"Mostly non-steel terms ({other} hits)", confidence=0.55)
        else:
            res = FileClassification(status="partly-relevant", discipline="other",
                                     reason="Could not be classified automatically; please check", confidence=0.3)
        self._log("classify_file", ctx, len(content), res, t0)
        return res

    # ------------------------------------------------------------------------------------------
    def extract_from_document(self, file_name, file_kind, text, ctx, page_note="", guidelines=""):
        t0 = time.time()
        facts: list[AIFact] = []
        scope: list[AIScopeItem] = []
        reqs: list[AIRequirement] = []
        flags: list[AIFlag] = []
        seen: set[tuple[str, str]] = set()

        def add(f: AIFact) -> None:
            k = (f.key, f.value.lower())
            if k not in seen and f.value.strip():
                seen.add(k)
                facts.append(f)

        lines = text.splitlines()
        # 1) form lines: "Label:   value" (+ continuation lines)
        for i, raw in enumerate(lines):
            line = raw.strip()
            if not line or len(line) > 220:
                continue
            for pat, key in LABELS:
                m = re.match(rf"^(?:{pat})\s*:?\s+(.+)$", line, re.I)
                if not m:
                    continue
                value = m.group(1).strip()
                if re.match(r"^[A-Za-z][\w ()/.-]{0,40}:\s", value) and key not in ("delivery_address", "delivery_country", "delivery_time"):
                    continue
                # continuation lines (indented, no label of their own)
                j = i + 1
                cont = []
                while j < len(lines) and len(cont) < 2:
                    nxt = lines[j]
                    if not nxt.strip():
                        if cont or j - i > 2:
                            break
                        j += 1
                        continue
                    if len(nxt) - len(nxt.lstrip()) >= 12 and ":" not in nxt.strip()[:25] and key in ("surface_by_phase", "delivery_address", "anchors"):
                        cont.append(nxt.strip())
                        j += 1
                        continue
                    break
                page = _page_of(text, text.find(raw))
                if key == "_skip":
                    break
                if CHECKED in value or UNCHECKED in value:
                    picked = _checked(value)
                    if not picked:
                        break
                    value = ", ".join(picked)
                if key == "delivery_address" and value.lower().startswith("adr:"):
                    value = value[4:].strip()
                if key == "delivery_time" and "week" in line.lower() and "year" not in line.lower():
                    pass
                if key == "corrosivity_class" and not re.search(r"\bC[1-5]\b", value):
                    break
                if key == "durability" and not re.match(r"^(L|M|H|VH|I)\b", value):
                    break
                if key == "paint_color":
                    mm = re.search(r"(\d{4})", value)
                    if not mm:
                        break
                    value = f"RAL {mm.group(1)}" + (" (not yet approved)" if "not yet approved" in value.lower() else "")
                if key == "inquiry_date" and not re.search(r"\d{1,2}[.-]\d{1,2}[.-]\d{2,4}", value):
                    break
                if key == "erection_included" and not re.match(r"(yes|no|included|not included|n/a)", value, re.I):
                    break
                full = value + ((" " + " ".join(cont)) if cont else "")
                snippet = line + ((" " + " ".join(cont)) if cont else "")
                if key == "delivery_country":
                    code = COUNTRY_CODES.get(value.lower().split()[0].strip(","), value[:2].upper() if len(value) <= 3 else None)
                    if code:
                        add(_fact("delivery_country", code, line, page))
                    break
                if key == "estimated_weight":
                    mm = re.search(r"(\d+(?:[.,]\d+)?)\s*(tonn?e?s?|tons|t)\b", value, re.I)
                    if mm:
                        add(_fact("estimated_weight", mm.group(1).replace(",", "."), line, page, unit="t", conf=0.85))
                    break
                if key == "longest_piece":
                    mm = re.search(r"(\d+(?:[.,]\d+)?)\s*m\b", value)
                    if mm:
                        add(_fact("longest_piece", mm.group(1).replace(",", "."), line, page, unit="m", conf=0.85))
                    break
                if key == "anchors" and value.upper() in ("N/A", "NA", "-"):
                    scope.append(AIScopeItem(item=line.split(":")[0].strip(), status="excluded", quantity="", snippet=line, page=page))
                    break
                if key == "bolts":
                    status = "included" if re.search(r"includ", value, re.I) else "unclear"
                    scope.append(AIScopeItem(item="Bolts and washers" + (", Hilti anchors" if "hilti" in value.lower() else ""),
                                             status=status, quantity="", snippet=line, page=page))
                    add(_fact("bolts", value, line, page))
                    break
                if key == "fire_rating":
                    picked = value
                    if picked.lower().startswith("no"):
                        add(_fact("fire_rating", "No intumescent coating", line, page, conf=0.9))
                    else:
                        add(_fact("fire_rating", picked, line, page))
                        reqs.append(AIRequirement(kind="fire_rating", text=f"Intumescent coating: {picked}", snippet=line, page=page, cost_impact="high"))
                    break
                if key == "epd_required":
                    yes = value.lower().startswith("yes")
                    add(_fact("epd_required", "yes" if yes else value, line, page))
                    if yes:
                        reqs.append(AIRequirement(kind="epd", text="EPD required for the steel", snippet=line, page=page, cost_impact="medium"))
                    break
                if key == "galvanising":
                    if re.search(r"HDG|1461|galvan", value, re.I):
                        add(_fact("galvanising", value, line, page))
                    break
                add(_fact(key, full, snippet, page))
                break

        flat = text
        # 2) cost-changing requirements anywhere in the text
        for m in re.finditer(r"(?:minimum of\s*)?(\d{1,3})\s*%\s*recycled steel in ([a-z ]+?profiles)(?:,?\s*and\s*(\d{1,3})\s*%\s*in\s*([a-z ]+?profiles))?",
                             flat, re.I | re.S):
            snippet = re.sub(r"\s+", " ", _sentence_at(flat, m.start(), m.end()))
            val = f"{m.group(1)}% {m.group(2).strip()}"
            if m.group(3):
                val += f"; {m.group(3)}% {m.group(4).strip()}"
            add(_fact("recycled_content", val, snippet, _page_of(flat, m.start()), conf=0.95))
            if not any(r.kind == "recycled_content" for r in reqs):
                reqs.append(AIRequirement(kind="recycled_content", text=f"Minimum recycled steel: {val}", snippet=snippet,
                                          page=_page_of(flat, m.start()), cost_impact="high"))
        for m in re.finditer(r"fire protection[^\n]{0,80}|intumescent[^\n]{0,60}|brannbeskyttelse[^\n]{0,60}|tulekaitse[^\n]{0,60}|palosuoja[^\n]{0,60}",
                             flat, re.I):
            line = _line_at(flat, m.start())
            if UNCHECKED in line and CHECKED not in line:
                continue
            if re.search(r"intumescent coating\s*:?\s*☐\s*yes\s*☒\s*no", line, re.I) or "if intumescent" in line.lower():
                continue
            rating = re.search(r"\bR\s?(15|30|45|60|90|120)\b", line)
            txt = f"Fire protection required ({rating.group(0)})" if rating else "Fire protection required, rating not stated in this file"
            if not any(f.key == "fire_rating" and f.snippet == line for f in facts):
                add(_fact("fire_rating", rating.group(0).replace(" ", "") if rating else "required (rating not stated)", line,
                          _page_of(flat, m.start()), conf=0.8))
                reqs.append(AIRequirement(kind="fire_rating", text=txt, snippet=line, page=_page_of(flat, m.start()), cost_impact="high"))
        for m in re.finditer(r"\bC([1-5])\.(\d{2})\b(?:,?\s*[A-Z]{2,8}\s*\d{2,3}/\d)?", flat):
            line = _line_at(flat, m.start())
            add(_fact("paint_system", m.group(0).strip(), m.group(0).strip(), _page_of(flat, m.start()), conf=0.9))
            reqs.append(AIRequirement(kind="paint_system", text=f"Paint system {m.group(0).strip()} (ISO 12944-5)",
                                      snippet=m.group(0).strip(), page=_page_of(flat, m.start()),
                                      cost_impact="high" if int(m.group(1)) >= 3 else "medium"))
        for m in re.finditer(r"painted\s+(C[1-5]\s?[LMH]?)\b[^\n.]{0,40}", flat, re.I):
            sn = _sentence_at(flat, m.start(), m.end())
            add(_fact("paint_system", m.group(1).replace(" ", "").upper(), sn, 0, conf=0.85))
            ral = re.search(r"RAL\s?(\d{4})", sn)
            if ral:
                add(_fact("paint_color", f"RAL {ral.group(1)}", sn, 0, conf=0.85))
        for m in re.finditer(r"\b(C[1-5][MH])\b\s+RAL\s?\d{4}[^\n]{0,60}", flat):
            sn = _line_at(flat, m.start())
            add(_fact("paint_system", m.group(1), sn, _page_of(flat, m.start()), conf=0.9))
        for m in re.finditer(r"\b(HDG|hot[- ]dip galvani[sz]\w*|galvani[sz]ed)\b", flat, re.I):
            sn = re.sub(r"\s+", " ", _sentence_at(flat, m.start(), m.end()))
            if len(sn) > 260:
                sn = _line_at(flat, m.start())
            if UNCHECKED + " " + m.group(0) in flat[max(0, m.start() - 3): m.end()]:
                continue
            if not any(f.key == "galvanising" and (norm(f.snippet) == norm(sn) or norm(f.snippet) in norm(sn) or norm(sn) in norm(f.snippet)) for f in facts):
                add(_fact("galvanising", sn[:160], sn, _page_of(flat, m.start()), conf=0.8))
            if not any(r.kind == "galvanising" for r in reqs):
                reqs.append(AIRequirement(kind="galvanising", text="Hot-dip galvanising required for part of the steel",
                                          snippet=sn, page=_page_of(flat, m.start()), cost_impact="high"))
        for m in re.finditer(r"\bEXC\s?([1-4])\b", flat):
            line = _line_at(flat, m.start())
            if UNCHECKED in line:
                continue  # checkbox lines are read by the form parser
            add(_fact("execution_class", f"EXC{m.group(1)}", line[:200], _page_of(flat, m.start()), conf=0.9))
        grades = []
        for m in re.finditer(r"\bS\s?(235|275|355|420|460)(?:[A-Z0-9+]{0,6})", flat):
            g = m.group(0).replace(" ", "")
            if g not in grades:
                grades.append(g)
                add(_fact("steel_grade", g, _line_at(flat, m.start())[:200], _page_of(flat, m.start()), conf=0.85))
            if len(grades) >= 6:
                break
        for m in re.finditer(r"\b(NOK|SEK|DKK|USD|GBP|PLN)\b|\d\s?kr\b", flat):
            flags.append(AIFlag(kind="other_currency", detail=f"Amounts in {m.group(0).strip()} found",
                                snippet=_line_at(flat, m.start())[:200], page=_page_of(flat, m.start())))
            break
        # 3) plain-language e-mail statements
        for m in re.finditer(r"approx(?:\.|imately)?\s*(\d{2,5})\s*(tonnes|tons|tonns|t)\b", flat, re.I):
            add(_fact("estimated_weight", m.group(1), _line_at(flat, m.start()), 0, unit="t", conf=0.8))
        for m in re.finditer(r"longest[^\n.]{0,60}?(\d{1,2}(?:[.,]\d)?)\s*m\b", flat, re.I):
            add(_fact("longest_piece", m.group(1).replace(",", "."), _sentence_at(flat, m.start(), m.end()), 0, unit="m", conf=0.8))
        for m in re.finditer(r"delivery time[^\n]{0,80}?week\s*\d{1,2}[^\n]*", flat, re.I):
            if any(f.key == "delivery_time" for f in facts):
                break
            add(_fact("delivery_time", re.sub(r"\s+", " ", m.group(0))[:160], _line_at(flat, m.start()), 0, conf=0.8))
        for m in re.finditer(r"(?im)^[\s*•-]*(no anchors[^\n]*)", flat):
            scope.append(AIScopeItem(item="Anchors", status="excluded", quantity="", snippet=m.group(1).strip(), page=0))
        for m in re.finditer(r"([^\n.]{3,120}?)\s+(?:must|shall|to)\s+be\s+included(?:[^\n.]*)", flat, re.I):
            sn = _sentence_at(flat, m.start(), m.end())
            item = re.sub(r"^(comments|also|and|the|note)\s*:?\s+", "", re.sub(r"\s{2,}", " ", m.group(1).strip()), flags=re.I)
            item = re.sub(r"^(comments|also)\s+", "", item, flags=re.I).rstrip(":")
            if len(item) < 4:
                continue
            q = re.search(r"(\d+)\s*(?:pieces|pcs|stk|tk)\b", flat[m.start(): m.end() + 200], re.I)
            scope.append(AIScopeItem(item=item[:80], status="included", quantity="", snippet=sn, page=_page_of(flat, m.start())))
        for m in re.finditer(r"(?:assume|approx\.?|around|about)\s+(?:around\s+)?(\d{1,5})\s*(?:pieces|pcs|stk|tk)\s+(?:of\s+)?([A-Za-z][A-Za-z0-9\- ]{2,40})", flat, re.I):
            sn = _sentence_at(flat, m.start(), m.end())
            item = m.group(2).strip().rstrip(".")
            scope.append(AIScopeItem(item=item, status="included", quantity=m.group(1), snippet=sn, page=0))
            if re.search(r"anchor|hilti|hus", item + sn, re.I):
                add(_fact("anchors", f"{m.group(1)} pcs {item}", sn, 0, conf=0.75))
        for m in re.finditer(r"([^\n.]{0,80}(?:disregard|not included|excluded|exclude)[^\n.]{0,120})", flat, re.I):
            sn = m.group(1).strip()
            if CHECKED in sn or UNCHECKED in sn or len(sn) < 12:
                continue
            item = re.sub(r"^.*?(?:disregard|exclude[ds]?)\s*", "", sn, flags=re.I)[:80] or sn[:80]
            scope.append(AIScopeItem(item=item, status="excluded", quantity="", snippet=sn, page=_page_of(flat, m.start())))
        for m in re.finditer(r"([^\n.]{0,120}(?:price post|separate price|as an option|optional)[^\n.]{0,80})", flat, re.I):
            sn = m.group(1).strip()
            prev_end = m.start() - 1
            while prev_end > 0 and flat[prev_end] in " \n.":
                prev_end -= 1
            prev_start = max(flat.rfind(".", 0, prev_end), flat.rfind("\n", 0, prev_end)) + 1
            ctx_s = flat[prev_start:prev_end + 1].strip()
            scope.append(AIScopeItem(item=(ctx_s[:60] + " — " if ctx_s else "") + "separate price line", status="option", quantity="",
                                     snippet=sn, page=_page_of(flat, m.start())))
        for m in re.finditer(r"([^\n.]{0,160}\b(?:missing|are not in the model|not yet modelled)\b[^\n.]{0,120})", flat, re.I):
            sn = m.group(1).strip()
            if len(sn) < 15:
                continue
            kind = "model_incomplete" if re.search(r"model|stud|steel|plate|beam", sn, re.I) else "missing_data"
            flags.append(AIFlag(kind=kind, detail="The sender says some items are missing", snippet=sn, page=_page_of(flat, m.start())))
        for m in re.finditer(r"(?im)^(?:from|fra):\s*(.+?)\s*<([^>@\s]+@[^>\s]+)>", flat):
            add(_fact("client_contact", m.group(1).strip(), m.group(0).strip(), 0, conf=0.9))
            add(_fact("client_email", m.group(2).strip(), m.group(0).strip(), 0, conf=0.95))
            break
        own = (self.cfg.get("own_company") or "maru").lower()
        for m in re.finditer(r"(?m)^\s*([A-ZÆØÅ][\w&.]*(?:\s[A-ZÆØÅ][\w&.]*){0,3}\s(?:AS|A/S|ASA|Oy|Oyj|AB|OÜ|ApS|GmbH|Ltd))\s*$", flat):
            if own in m.group(1).lower():
                continue
            add(_fact("client_company", m.group(1).strip(), m.group(1).strip(), _page_of(flat, m.start()), conf=0.8))
            break
        for m in re.finditer(r"(?im)^date:\s*(.+)$", flat):
            add(_fact("inquiry_date", m.group(1).strip()[:40], m.group(0).strip(), 0, conf=0.9))
            break
        uniq, seen_sn = [], set()
        for it in scope:
            k = norm(it.snippet)[:120] + it.status
            if k in seen_sn:
                continue
            seen_sn.add(k)
            uniq.append(it)
        scope = uniq
        nf = [AINotFound(key=k, reason="not stated in this file") for k in
              ("execution_class", "corrosivity_class", "delivery_address", "bid_deadline") if not any(f.key == k for f in facts)]
        res = DocumentExtraction(facts=facts, scope_items=scope, requirements=reqs, flags=flags, not_found=nf)
        self._log("extract_document", ctx, len(text), res, t0)
        return res

    # ------------------------------------------------------------------------------------------
    def extract_from_drawing(self, file_name, image_png, context, ctx, guidelines=""):
        """Without a vision model only the file name / e-mail context can be used (low confidence)."""
        t0 = time.time()
        facts, scope, reqs = [], [], []
        name = file_name
        m = re.search(r"phase\s*([\d+ ]+?)\s*-\s*(painted\s*)?(C[1-5][LMH]|HDG)", name, re.I)
        if m:
            system = m.group(3).upper()
            facts.append(AIFact(key="surface_by_phase", value=f"Phase {m.group(1).strip()}: {system}", unit="",
                                snippet=name, page=0, confidence=0.55))
            scope.append(AIScopeItem(item=f"Phase {m.group(1).strip()} ({'galvanised' if system == 'HDG' else 'painted ' + system})",
                                     status="included", quantity="", snippet=name, page=0))
        desc = ("Image not read: no vision model is configured (offline mode). "
                + ("The file name describes the surface treatment of a phase." if m else "Kept for the estimator to look at."))
        res = DrawingExtraction(description=desc, facts=facts, scope_items=scope, requirements=reqs, flags=[])
        self._log("extract_drawing", ctx, len(context), res, t0)
        return res

    # ------------------------------------------------------------------------------------------
    def predict_missing(self, missing, context, ctx):
        t0 = time.time()
        preds = []
        for m in missing:
            default = m.get("default")
            if default in (None, ""):
                continue
            preds.append(AIPrediction(key=m["key"], value=str(default), unit=m.get("unit") or "",
                                      reasoning=m.get("why") or "Not stated in the files; the knowledge-file default is used.",
                                      confidence=float(m.get("confidence", 0.55)), question=m.get("question") or ""))
        res = MissingPrediction(predictions=preds)
        self._log("predict_missing", ctx, len(context), res, t0)
        return res

    # ------------------------------------------------------------------------------------------
    def interpret_correction(self, text, targets, ctx):
        t0 = time.time()
        changes: list[AIChange] = []
        not_applied: list[AINotApplied] = []
        clauses = [c.strip() for c in re.split(r"[;\n]|,\s*(?=[a-z])|\.\s+|\band\b(?=\s+(?:the\s+)?[a-z]+\s+(?:are|is)\b)", text) if c.strip()]
        cats = [t for t in targets if t["id"].startswith("category:")]
        used: set[str] = set()

        def mentioned(target: dict[str, Any], clause: str) -> bool:
            words = [w for w in re.findall(r"[a-zæøåäö]{4,}", target.get("match", target["label"]).lower())]
            cl = clause.lower()
            return any(w[:-1] in cl or w in cl for w in words)

        def propose(tid: str, value: Any, why: str) -> None:
            if tid in used:
                return
            t = next((x for x in targets if x["id"] == tid), None)
            if t is None:
                return
            if t.get("allowed") and str(value) not in [str(a) for a in t["allowed"]]:
                return
            used.add(tid)
            changes.append(AIChange(target=tid, new_value=str(value), explanation=why))

        def scope_object(clause: str) -> str | None:
            """'... for the stairs' → 'stairs' (the part of the takeoff the clause is about), if it names one."""
            m = re.search(r"\bfor (?:the |all )?([a-zæøåäö][a-zæøåäö ]{2,30}?)(?:\s*(?:,|\.|$|\band\b|\bonly\b|\bphase\b))", clause.lower())
            if not m:
                return None
            obj = m.group(1).strip()
            return None if obj in ("all", "everything", "all steel", "the whole project", "steel", "whole project") else obj

        def surface_subset(clause: str, exclude: tuple[str, ...]) -> tuple[list[dict[str, Any]], str | None]:
            hit = [t for t in cats if t["id"].endswith(":surface") and mentioned(t, clause)]
            if hit:
                return hit, None
            obj = scope_object(clause)
            if obj:  # names a part that is not in the takeoff → do not touch everything
                return [], obj
            return [t for t in cats if t["id"].endswith(":surface") and str(t.get("current", "")).upper() not in exclude], None

        for clause in clauses:
            low = clause.lower()
            handled = False
            # galvanising instead of paint
            if re.search(r"galvani[sz]|hdg|hot[- ]dip", low) and re.search(r"instead|rather than|not paint|in place of|replace", low):
                subset, missing = surface_subset(clause, ("HDG", "NONE"))
                for t in subset:
                    propose(t["id"], "HDG", f"'{clause}': galvanising replaces paint for {t['label'].split(' — ')[0]}")
                if missing:
                    not_applied.append(AINotApplied(text=clause, reason=f"No '{missing}' found in the takeoff, so no surface treatment was changed"))
                handled = True
            m = re.search(r"\b(c[1-5](?:vh|[lmh])?|c[1-5]\.\d{2})\b", low)
            if not handled and m and re.search(r"paint|system|class|coat", low):
                from ..knowledge.base import normalize_system
                system = normalize_system(m.group(1))
                subset, missing = surface_subset(clause, ("HDG",))
                for t in subset:
                    propose(t["id"], system, f"'{clause}': paint system {system}")
                if missing:
                    not_applied.append(AINotApplied(text=clause, reason=f"No '{missing}' found in the takeoff, so no paint system was changed"))
                handled = True
            if re.search(r"out of scope|not in scope|excluded|exclude|not included|remove|delete|drop|by others", low):
                subset = [t for t in cats if t["id"].endswith(":included") and mentioned(t, clause)]
                for t in subset:
                    propose(t["id"], "false", f"'{clause}': {t['label'].split(' — ')[0]} out of scope")
                if not subset:
                    noun = re.sub(r"\b(are|is|out of scope|not in scope|excluded|not included|by others|remove|the)\b", "", low).strip(" .,")
                    not_applied.append(AINotApplied(text=clause, reason=f"No '{noun or clause}' found in the takeoff, nothing to remove"))
                handled = True
            m = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:→|->|to|instead of)\s*(\d+(?:[.,]\d+)?)", clause)
            m2 = re.search(r"(\d+(?:[.,]\d+)?)\s+instead of\s+(\d+(?:[.,]\d+)?)", clause)
            if not handled and (m or m2):
                if m2:
                    new, old = m2.group(1), m2.group(2)
                else:
                    old, new = m.group(1), m.group(2)
                cand = [t for t in targets if t.get("numeric") and mentioned(t, clause)]
                cand = [t for t in cand if str(t.get("current")) in (old, old.replace(",", "."))] or cand
                if cand:
                    propose(cand[0]["id"], new.replace(",", "."), f"'{clause}': {old} → {new}")
                    handled = True
            m = re.search(r"margin[^\d]{0,20}(\d+(?:[.,]\d+)?)\s*%", low)
            if m:
                coef = round(1 + float(m.group(1).replace(",", ".")) / 100, 4)
                for tid in ("param:margin_material", "param:margin_production"):
                    if "material" in low and tid.endswith("production"):
                        continue
                    if "production" in low and tid.endswith("material"):
                        continue
                    propose(tid, coef, f"'{clause}': margin {m.group(1)} %")
                handled = True
            m = re.search(r"labou?r rate[^\d]{0,15}(\d+(?:[.,]\d+)?)", low)
            if m:
                propose("param:labour_rate", m.group(1).replace(",", "."), f"'{clause}'")
                handled = True
            m = re.search(r"\br\s?(30|60|90|120)\b", low)
            if m and re.search(r"fire|intumescent|r30|r60|r90", low):
                propose("fact:fire_rating", f"R{m.group(1)}", f"'{clause}': fire protection R{m.group(1)}")
                handled = True
            m = re.search(r"\bexc\s?([1-4])\b|execution class\s*([1-4])", low)
            if m:
                propose("fact:execution_class", f"EXC{m.group(1) or m.group(2)}", f"'{clause}'")
                handled = True
            m = re.search(r"(\d{1,5})\s*(?:pcs|pieces|anchors)", low)
            if m and "anchor" in low:
                propose("allowance:anchors:qty", m.group(1), f"'{clause}'")
                handled = True
            if not handled:
                not_applied.append(AINotApplied(text=clause, reason="Not understood by the offline rules; edit the value directly or rephrase"))
        res = CorrectionProposal(changes=changes, not_applied=not_applied)
        self._log("interpret_correction", ctx, len(text), res, t0)
        return res

    # ------------------------------------------------------------------------------------------
    def update_guidelines(self, current, corrections, project, ctx):
        t0 = time.time()
        bullets = [b.strip("- ").strip() for b in (current or "").splitlines() if b.strip().startswith("-")]
        examples = []
        def show(x: Any) -> str:
            if isinstance(x, bool) or str(x).lower() in ("true", "false"):
                return "yes" if str(x).lower() == "true" else "no"
            if isinstance(x, float) and x.is_integer():
                return str(int(x))
            return str(x)

        for c in corrections[:20]:
            label = c.get("label") or c.get("key")
            b = f"{label}: estimator changed {show(c.get('before'))} → {show(c.get('after'))}" + (f" ({c['reason']})" if c.get("reason") else "")
            if b not in bullets:
                bullets.append(b)
            examples.append(GuidelineExample(situation=f"{project}: {label} was {show(c.get('before'))}",
                                             correction=f"set to {show(c.get('after'))}" + (f" because {c['reason']}" if c.get("reason") else "")))
        res = GuidelinesUpdate(guidelines=bullets[-15:], examples=examples[:5])
        self._log("update_guidelines", ctx, len(json.dumps(corrections)), res, t0)
        return res


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()
