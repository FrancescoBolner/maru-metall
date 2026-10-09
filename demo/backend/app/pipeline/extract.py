"""Stage 2 — Extraction. Code first (IFC, material lists, PDF part lists, keyword search in specs),
AI only where reading is needed (e-mails, RFQ forms, specifications, images, scans)."""
from __future__ import annotations

import re
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional

from ..ai.base import AIError
from ..models import FileEntry
from ..parsers import bom, ifc, misc, pdfdoc
from .context import RunContext, cache_json
from .filemap import docx_text, entry_path

REQ_PATTERNS = {
    "fire": re.compile(r"(?i)fire\s*protection[^\n]{0,60}|intumescent[^\n]{0,40}|\bR\s?(?:30|60|90|120)\b(?![\d.,])|brannbeskytt\w*[^\n]{0,40}|palosuoja\w*[^\n]{0,40}|tulekaitse\w*[^\n]{0,40}"),
    "paint": re.compile(r"\bC[1-5]\.\d{2}\b(?:,?\s*[A-Z]{2,8}\s*\d{2,3}/\d)?|ISO\s?12944[^\n]{0,30}|\bC[1-5]\s?-?(?:VH|H|M|L)\b"),
    "galv": re.compile(r"(?i)\bHDG\b[^\n]{0,30}|hot[- ]dip galvani\w*[^\n]{0,30}|ISO\s?1461[^\n]{0,20}|galvani[sz]\w*[^\n]{0,30}"),
    "recycled": re.compile(r"(?i)recycled[^\n]{0,60}|\bEPD\b[^\n]{0,40}"),
    "exc": re.compile(r"\bEXC\s?[1-4]\b[^\n]{0,30}"),
    "grade": re.compile(r"\bS\s?(?:235|275|355|420|460)[A-Z0-9+]{0,6}"),
    "prep": re.compile(r"(?i)ISO\s?8501[^\n]{0,30}|\bSa\s?2[.,]?5\b"),
    "currency": re.compile(r"\b(?:NOK|SEK|DKK|USD|GBP|PLN)\b[^\n]{0,30}"),
}


def _set_file(ctx: RunContext, e: FileEntry, state: str, method: Optional[str] = None, note: Optional[str] = None) -> None:
    ctx.emit(stage="2", file=e.path, file_id=e.id, file_state=state, method=method, note=note)


def run_extraction(ctx: RunContext) -> dict[str, Any]:
    fm = ctx.data["filemap"]
    active = [e for e in fm.entries if e.status in ("metal-relevant", "partly-relevant")]
    out: dict[str, Any] = {"models": [], "boms": [], "pdf_lists": [], "pdf_hits": [], "docs": [], "drawings": [], "nc": [],
                           "failed": []}
    workers = max(1, int(ctx.cfg.get("ai", {}).get("parallel_files", 4)))
    for e in fm.entries:
        if e.status not in ("metal-relevant", "partly-relevant"):
            _set_file(ctx, e, "skipped", note=e.status)
        else:
            _set_file(ctx, e, "queued")

    def work(e: FileEntry) -> tuple[FileEntry, list[tuple[str, Any]]]:
        _set_file(ctx, e, "reading")
        res = _extract_one(ctx, e)
        return e, res

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(work, e): e for e in active}
        for fut in as_completed(futs):
            e = futs[fut]
            try:
                _, items = fut.result()
                for bucket, item in items:
                    out[bucket].append(item)
                _set_file(ctx, e, "done", method=e.read_by)
            except AIError as ex:
                e.error = str(ex)
                e.read_by = "none"
                e.notes.append("The AI could not read this file; it was skipped. Check it manually or re-run.")
                out["failed"].append({"file_id": e.id, "path": e.path, "error": str(ex)})
                _set_file(ctx, e, "failed", note=str(ex))
            except Exception as ex:  # noqa: BLE001
                e.error = f"{type(ex).__name__}: {ex}"[:300]
                e.read_by = "none"
                e.notes.append("This file could not be read; it was skipped.")
                out["failed"].append({"file_id": e.id, "path": e.path, "error": e.error})
                _set_file(ctx, e, "failed", note=e.error)
    # stable order
    for k in ("models", "boms", "pdf_lists", "pdf_hits", "docs", "drawings", "nc"):
        out[k].sort(key=lambda x: x["entry"].path)
    return out


def _extract_one(ctx: RunContext, e: FileEntry) -> list[tuple[str, Any]]:
    path = entry_path(ctx, e)
    items: list[tuple[str, Any]] = []
    cctx = ctx.call_ctx(e.id, e.path)
    if e.kind == "ifc":
        data = cache_json("ifc", e.sha256, lambda: ifc.parse(path))
        e.read_by = "code"
        e.used_for.append("quantities")
        items.append(("models", {"entry": e, "data": data}))
    elif e.kind == "sheet":
        data = cache_json("bom", e.sha256, lambda: bom.parse(path))
        e.read_by = "code"
        e.used_for.append("quantities (cross-check)")
        items.append(("boms", {"entry": e, "data": data}))
    elif e.kind == "pdf":
        scan = ctx.data["scans"].get(e.id, {})
        if "part lists" in e.reason:
            lists = cache_json("partlists", e.sha256, lambda: _lists_json(pdfdoc.parse_part_lists(path)))
            items.append(("pdf_lists", {"entry": e, "data": lists}))
            e.used_for.append("quantities")
        if scan.get("scanned"):
            png = pdfdoc.render_page_png(path, 1, max_px=int(ctx.cfg.get("pipeline", {}).get("image_max_px", 1600)))
            res = ctx.provider.extract_from_drawing(e.name, png, f"Scanned PDF '{e.name}' page 1 of {e.pages}", cctx, ctx.guidelines)
            e.read_by = "ai" if ctx.provider.name != "offline" else "none"
            items.append(("drawings", {"entry": e, "result": res, "page": 1}))
            return items
        if (e.pages or 0) <= int(ctx.cfg.get("pipeline", {}).get("pdf_text_pages_for_ai", 4)) and "part lists" not in e.reason:
            pages = pdfdoc.page_texts(path)
            import pymupdf
            doc = pdfdoc.open_pdf(path)
            text = "\n".join(f"[page {i + 1}]\n" + doc[i].get_text(sort=True) for i in range(doc.page_count))
            doc.close()
            res = ctx.provider.extract_from_document(e.name, "PDF form / specification", text, cctx,
                                                     page_note=f", {e.pages} page(s)", guidelines=ctx.guidelines)
            e.read_by = "code+ai" if ctx.provider.name != "offline" else "code"
            e.used_for.append("specs, scope, commercial")
            items.append(("docs", {"entry": e, "result": res, "text": text, "kind": "pdf"}))
        else:
            hits = cache_json("pdfhits", e.sha256, lambda: pdfdoc.keyword_hits(path, REQ_PATTERNS))
            items.append(("pdf_hits", {"entry": e, "hits": hits}))
            text = _hits_text(hits)
            if text.strip():
                res = ctx.provider.extract_from_document(
                    e.name, "drawing set: requirement notes found by keyword search (not the full document)", text, cctx,
                    page_note=f", {e.pages} pages, {len(hits)} keyword hits", guidelines=ctx.guidelines)
                items.append(("docs", {"entry": e, "result": res, "text": text, "kind": "pdf-hits"}))
                e.used_for.append("specs (keyword search)")
            e.read_by = ("code+ai" if ctx.provider.name != "offline" else "code")
    elif e.kind == "email":
        mail = ctx.data["emails"].get(e.id) or {}
        text = (f"From: {mail.get('from', '')}\nTo: {mail.get('to', '')}\nCc: {mail.get('cc', '')}\n"
                f"Date: {mail.get('date', '')}\nSubject: {mail.get('subject', '')}\n\n{mail.get('body', '')}")
        res = ctx.provider.extract_from_document(e.name, "e-mail", text, cctx, guidelines=ctx.guidelines)
        e.read_by = "ai" if ctx.provider.name != "offline" else "code"
        e.used_for.append("commercial, scope, specs")
        items.append(("docs", {"entry": e, "result": res, "text": text, "kind": "email"}))
    elif e.kind == "image":
        png = misc.image_png(path, int(ctx.cfg.get("pipeline", {}).get("image_max_px", 1600)))
        context = f"File name: {e.name}. Folder: {e.path.rsplit('/', 1)[0] if '/' in e.path else ''}."
        parent = next((x for x in ctx.data["filemap"].entries if x.id == e.parent_id), None) if e.parent_id else None
        if parent is not None:
            mail = ctx.data["emails"].get(parent.id) or {}
            context += f" Attached to e-mail '{mail.get('subject', '')}': {mail.get('body', '')[:1500]}"
        res = ctx.provider.extract_from_drawing(e.name, png, context, cctx, ctx.guidelines)
        e.read_by = "ai" if ctx.provider.name != "offline" else "none"
        if ctx.provider.name == "offline":
            e.notes.append("Not read: images need an AI vision model (offline mode)")
        items.append(("drawings", {"entry": e, "result": res, "page": 0}))
    elif e.kind in ("text", "docx", "dxf"):
        if e.kind == "text":
            text = misc.read_text(path, 200_000)
        elif e.kind == "docx":
            text = docx_text(path)
        else:
            text = "\n".join(misc.dxf_texts(path).get("texts", []))
        res = ctx.provider.extract_from_document(e.name, e.kind, text, cctx, guidelines=ctx.guidelines)
        e.read_by = "code+ai" if ctx.provider.name != "offline" else "code"
        items.append(("docs", {"entry": e, "result": res, "text": text, "kind": e.kind}))
    elif e.kind == "nc1":
        d = cache_json("nc1", e.sha256, lambda: misc.parse_dstv(path))
        e.read_by = "code"
        items.append(("nc", {"entry": e, "data": d}))
    return items


def _lists_json(parsed: dict[str, Any]) -> dict[str, Any]:
    def row(r: Any) -> dict[str, Any]:
        return {k: getattr(r, k) for k in ("page", "kind", "position", "name", "profile", "material", "exc", "shade", "pcs",
                                           "length", "width", "height", "weight", "weight_sum", "area", "area_sum", "bbox",
                                           "text", "assembly")}
    return {"kind": parsed["kind"], "pages": parsed["pages"], "assemblies": [row(a) for a in parsed["assemblies"]],
            "parts": [row(p) for p in parsed["parts"]]}


def _hits_text(hits: list[dict[str, Any]], max_lines: int = 45) -> str:
    """Compress keyword hits into a short text for the AI: distinct snippets with pages and counts."""
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for h in hits:
        key = (h["key"], re.sub(r"\s+", " ", h["snippet"]).strip().lower()[:80])
        g = groups.setdefault(key, {"snippet": h["snippet"], "pages": [], "context": h["context"], "key": h["key"]})
        g["pages"].append(h["page"])
    order = sorted(groups.values(), key=lambda g: (-len(g["pages"]), g["pages"][0]))
    lines = []
    for g in order[:max_lines]:
        pages = sorted(set(g["pages"]))
        pg = ", ".join(str(p) for p in pages[:8]) + (f" (+{len(pages) - 8} more)" if len(pages) > 8 else "")
        lines.append(f"[page {pages[0]}] {g['snippet'].strip()}\n    found on {len(pages)} page(s): {pg}; context: {g['context'][:220]}")
    return "\n".join(lines)
