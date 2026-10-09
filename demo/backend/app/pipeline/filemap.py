"""Stage 1 — Read the shared drive: file map, relevance, duplicates, versions, project level.

Code first: extension, name, metadata and a quick content scan decide almost every file.
The AI (`classify_file`) is only asked about files the rules cannot decide.
"""
from __future__ import annotations

import hashlib
import re
import time
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ..ai.base import AIError
from ..models import FileEntry, FileMap
from ..parsers import bom, email_, ifc, misc, pdfdoc
from .context import BLOBS, RunContext, cache_json, sha256_file

KIND_BY_EXT = {
    ".ifc": "ifc", ".ifczip": "ifc", ".xlsx": "sheet", ".xlsm": "sheet", ".xls": "sheet", ".csv": "sheet",
    ".pdf": "pdf", ".eml": "email", ".msg": "email", ".png": "image", ".jpg": "image", ".jpeg": "image",
    ".tif": "image", ".tiff": "image", ".bmp": "image", ".gif": "image", ".webp": "image",
    ".db1": "tekla-db", ".db2": "tekla-db", ".dwg": "dwg", ".dxf": "dxf", ".nc1": "nc1", ".nc": "nc1",
    ".txt": "text", ".md": "text", ".docx": "docx", ".zip": "archive", ".7z": "archive", ".rar": "archive",
    ".tsc": "tekla-db", ".tcd": "tekla-db",
}
SKIP_NAMES = {"thumbs.db", ".ds_store", "desktop.ini"}
KIND_LABEL = {"ifc": "IFC model", "sheet": "Spreadsheet", "pdf": "PDF", "email": "E-mail", "image": "Image",
              "tekla-db": "Tekla database", "dwg": "DWG drawing", "dxf": "DXF drawing", "nc1": "CNC file (DSTV)",
              "text": "Text", "docx": "Word document", "archive": "Archive", "other": "Other"}


def _fid(rel: str) -> str:
    return "f" + hashlib.sha1(rel.encode("utf-8")).hexdigest()[:10]


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def blob_path(sha: str, name: str) -> Path:
    ext = Path(name).suffix.lower() or ".bin"
    return BLOBS / f"{sha}{ext}"


def entry_path(ctx: RunContext, e: FileEntry) -> Path:
    """Local path to read an entry (folder file or extracted attachment blob)."""
    if e.parent_id:
        return blob_path(e.sha256, e.name)
    return ctx.project.root / e.path


def docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="ignore")
        xml = re.sub(r"</w:p>", "\n", xml)
        return re.sub(r"<[^>]+>", "", xml)
    except Exception:
        return ""


def build_filemap(ctx: RunContext) -> FileMap:
    t0 = time.time()
    root = ctx.project.root
    rules = ctx.company_cfg.get("file_rules", {})
    max_files = int(ctx.cfg.get("pipeline", {}).get("max_files_scan", 20000))
    entries: list[FileEntry] = []
    emails: dict[str, dict[str, Any]] = {}
    paths = sorted(p for p in root.rglob("*") if p.is_file())
    if len(paths) > max_files:
        ctx.warnings.append(f"Only the first {max_files} of {len(paths)} files were mapped.")
        paths = paths[:max_files]
    ctx.emit(stage="1", message=f"Mapping {len(paths)} files", files_total=len(paths))

    for p in paths:
        rel = p.relative_to(root).as_posix()
        name = p.name
        if name.lower() in SKIP_NAMES or name.startswith("~$"):
            continue
        ext = p.suffix.lower()
        st = p.stat()
        e = FileEntry(id=_fid(rel), path=rel, name=name, ext=ext, kind=KIND_BY_EXT.get(ext, "other"),
                      size=st.st_size, date=_iso(st.st_mtime), sha256=sha256_file(p) if st.st_size else "")
        entries.append(e)
        if e.kind == "email":
            try:
                parsed = email_.parse(p)
                emails[e.id] = parsed
                if parsed.get("date"):
                    e.date = parsed["date"]
                for a in parsed["attachments"]:
                    data = a["data"]
                    sha = hashlib.sha256(data).hexdigest()
                    bp = blob_path(sha, a["name"])
                    if not bp.exists():
                        bp.write_bytes(data)
                    aext = Path(a["name"]).suffix.lower()
                    child = FileEntry(id=_fid(rel + "::" + a["name"]), path=f"{rel}::{a['name']}", name=a["name"],
                                      ext=aext, kind=KIND_BY_EXT.get(aext, "other"), size=len(data),
                                      date=parsed.get("date"), sha256=sha, parent_id=e.id)
                    if a.get("inline"):
                        child.notes.append("inline image in the e-mail body")
                    entries.append(child)
            except Exception as ex:  # noqa: BLE001
                e.status, e.reason, e.error = "unreadable", "E-mail could not be opened", str(ex)[:200]

    by_id = {e.id: e for e in entries}
    # dates: folder files that are also e-mail attachments take the e-mail date
    att_date: dict[str, str] = {}
    for e in entries:
        if e.parent_id and e.date:
            att_date.setdefault(e.sha256, e.date)
    for e in entries:
        if not e.parent_id and e.sha256 in att_date:
            e.date = att_date[e.sha256]
            e.notes.append("dated by the e-mail it was attached to")

    # ---------------------------------------------------------------- classification (code first)
    ctx.data["emails"] = emails
    scans: dict[str, dict[str, Any]] = {}
    for i, e in enumerate(entries):
        if e.status == "unreadable" and e.error:
            continue
        ctx.emit(stage="1", file=e.path, file_state="mapping", index=i)
        try:
            _classify(ctx, e, by_id, emails, scans, rules)
        except Exception as ex:  # noqa: BLE001
            e.status, e.reason, e.error = "unreadable", f"Could not be read ({type(ex).__name__})", str(ex)[:300]
            e.read_by = "none"

    # superseded folders ("Ei kehti", "old", ...)
    kw = [k.lower() for k in rules.get("superseded_folder_keywords", [])]
    for e in entries:
        folders = [f.lower() for f in e.path.split("::")[0].split("/")[:-1]]
        hit = next((f for f in folders for k in kw if k == f or f.startswith(k + " ") or f.endswith(" " + k)), None)
        if hit and e.status != "unreadable":
            e.status, e.decided_by = "duplicate", "rule"
            e.reason = f"In folder '{hit}', marked as not valid / superseded"

    _mark_duplicates(entries)
    _mark_content_duplicates(ctx, entries, scans)
    _mark_versions(ctx, entries, scans)
    _apply_file_overrides(ctx, entries)

    level, level_reason = _project_level(entries, scans)
    counts: dict[str, int] = defaultdict(int)
    for e in entries:
        counts[e.status] += 1
    ctx.data["scans"] = scans
    fm = FileMap(root=str(root), entries=entries, level=level, level_reason=level_reason, counts=dict(counts),
                 total_size=sum(e.size for e in entries if not e.parent_id), seconds=round(time.time() - t0, 2))
    return fm


# ------------------------------------------------------------------------------------------------
def _kw_hits(text: str, words: list[str]) -> int:
    low = text.lower()
    return sum(len(re.findall(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", low)) for w in words)


def _classify(ctx: RunContext, e: FileEntry, by_id: dict[str, FileEntry], emails: dict[str, Any],
              scans: dict[str, dict[str, Any]], rules: dict[str, Any]) -> None:
    path = entry_path(ctx, e)
    metal_kw = rules.get("metal_keywords", [])
    not_kw = rules.get("not_relevant_keywords", [])
    rfq_kw = rules.get("rfq_keywords", [])
    e.read_by = "code"
    if e.size == 0:
        e.status, e.reason = "unreadable", "Empty file"
        return
    k = e.kind
    if k == "ifc":
        q = cache_json("ifcscan", e.sha256, lambda: ifc.quick_scan(path))
        scans[e.id] = q
        e.elements = q["elements"]
        e.notes.append(f"{q.get('application') or 'IFC'} · {q.get('schema')}")
        if q["metal_elements"] and (q["steel_materials"] or not q["materials"]):
            if q["nonmetal_elements"] > q["metal_elements"]:
                e.status = "partly-relevant"
                e.reason = (f"Whole-building model: {q['metal_elements']} steel members out of "
                            f"{q['metal_elements'] + q['nonmetal_elements']} elements; non-steel elements are excluded")
            else:
                e.status = "metal-relevant"
                e.reason = f"Steel model: {q['metal_elements']} beams/columns/members/plates ({', '.join(q['steel_materials'][:4])})"
        else:
            e.status = "not-relevant"
            e.reason = f"No steel members in the model ({', '.join(list(q['materials'])[:3]) or 'no steel material'})"
    elif k == "sheet":
        s = cache_json("bomscan", e.sha256, lambda: bom.scan(path))
        scans[e.id] = s
        e.sheets = s["sheets"]
        if s["is_bom"]:
            e.status, e.reason = "metal-relevant", f"Material list: profiles, quantities and weights (sheet '{s['header']['sheet']}')"
        else:
            e.status, e.reason = "partly-relevant", "Spreadsheet without a material-list header"
            _ai_classify(ctx, e, path, f"Sheets: {', '.join(s['sheet_names'])}")
    elif k == "pdf":
        s = cache_json("pdfscan", e.sha256, lambda: {k2: v for k2, v in pdfdoc.scan(path, int(ctx.cfg.get('pipeline', {}).get('pdf_scan_pages', 6))).items()})
        scans[e.id] = s
        e.pages = s["pages"]
        text = s["text"]
        m_hits, n_hits, r_hits = _kw_hits(text, metal_kw), _kw_hits(text, not_kw), _kw_hits(text + " " + e.name, rfq_kw)
        if s["scanned"]:
            e.status, e.reason = "partly-relevant", "Scanned PDF without a text layer: read by AI vision"
            e.notes.append("scanned")
        elif "PART LIST" in text or "ASSEMBLY PART" in text.upper():
            e.status, e.reason = "metal-relevant", f"Steel drawings with part lists ({e.pages} pages)"
        elif r_hits:
            e.status, e.reason = "metal-relevant", "Price inquiry / request for tender form"
        elif m_hits >= 3 and m_hits >= n_hits:
            e.status, e.reason = "metal-relevant", f"Mentions steel {m_hits} times"
        elif n_hits > m_hits and n_hits >= 2:
            e.status, e.reason = "not-relevant", f"Not about steel (architecture / MEP / concrete terms: {n_hits})"
        else:
            e.status, e.reason = "partly-relevant", "Could not be classified by the rules"
            _ai_classify(ctx, e, path, text[:6000])
    elif k == "email":
        mail = emails.get(e.id, {})
        e.status = "metal-relevant"
        e.reason = f"E-mail '{mail.get('subject', '')[:60]}': commercial and scope information"
        e.notes.append(f"{len(mail.get('attachments', []))} attachments")
    elif k == "image":
        info = misc.image_info(path)
        scans[e.id] = info
        if "error" in info:
            e.status, e.reason = "unreadable", "Image could not be opened"
        elif e.size < int(rules.get("small_image_bytes", 20000)) or (info.get("width", 0) < 200 and info.get("height", 0) < 200):
            e.status, e.reason = "not-relevant", "Small image (logo or signature)"
        elif re.search(r"phase|hdg|galv|paint|scope|colou?r|legend|model|delivery", e.name, re.I):
            e.status, e.reason = "partly-relevant", "Colour-coded model screenshot (scope / surface treatment)"
        else:
            e.status, e.reason = "partly-relevant", "Screenshot or picture: looked at for scope information"
        e.notes.append(f"{info.get('width')}×{info.get('height')} px")
    elif k == "tekla-db":
        e.status = "unreadable"
        e.reason = "Tekla model database (proprietary format). The IFC export of the same model is used instead."
        e.read_by = "none"
    elif k == "dwg":
        twin = (path.with_suffix(".pdf").name)
        e.status, e.read_by = "unreadable", "none"
        e.reason = f"AutoCAD DWG ({misc.dwg_version(path) or 'binary'}): needs a CAD converter; the PDF print is used when present"
        e.notes.append(f"look for {twin}")
    elif k == "dxf":
        d = cache_json("dxf", e.sha256, lambda: misc.dxf_texts(path))
        scans[e.id] = d
        if d.get("error"):
            e.status, e.reason = "unreadable", d["error"][:150]
        else:
            hits = _kw_hits(" ".join(d.get("texts", [])), metal_kw)
            e.status = "metal-relevant" if hits >= 2 else "partly-relevant"
            e.reason = f"DXF drawing: {d.get('entities')} entities, {hits} steel terms"
    elif k == "nc1":
        d = cache_json("nc1", e.sha256, lambda: misc.parse_dstv(path))
        scans[e.id] = d
        if d.get("error"):
            e.status, e.reason = "unreadable", "DSTV file without header"
        else:
            e.status = "metal-relevant"
            e.reason = f"CNC file: {d.get('profile')} {d.get('grade')} L={d.get('length')} mm, {d.get('holes')} holes"
    elif k in ("text", "docx"):
        text = misc.read_text(path, 100_000) if k == "text" else docx_text(path)
        scans[e.id] = {"text": text[:20000]}
        m_hits, n_hits, r_hits = _kw_hits(text, metal_kw), _kw_hits(text, not_kw), _kw_hits(text, rfq_kw)
        if r_hits or m_hits >= 3:
            e.status, e.reason = "metal-relevant", "Text with steel requirements"
        elif n_hits >= 2:
            e.status, e.reason = "not-relevant", "Text without steel information"
        elif len(text.strip()) < 400:
            e.status, e.reason = "not-relevant", f"Short note without steel information: “{text.strip()[:80]}”"
        else:
            e.status, e.reason = "partly-relevant", "Text document"
            _ai_classify(ctx, e, path, text[:6000])
    elif k == "archive":
        e.status, e.reason, e.read_by = "unreadable", "Archive: unpack it into the project folder to include its files", "none"
    else:
        e.status, e.reason, e.read_by = "unreadable", f"Unsupported file type '{e.ext or 'no extension'}'", "none"


def _ai_classify(ctx: RunContext, e: FileEntry, path: Path, content: str) -> None:
    try:
        res = ctx.provider.classify_file(e.name, KIND_LABEL.get(e.kind, e.kind), content, ctx.call_ctx(e.id, e.path))
    except AIError as ex:
        e.notes.append(f"AI classification failed: {ex}")
        return
    if res.confidence >= 0.5 or res.status != "partly-relevant":
        e.status = res.status
        e.reason = res.reason
        e.decided_by = "ai" if ctx.provider.name != "offline" else "rule"
        e.read_by = "code+ai" if ctx.provider.name != "offline" else "code"


def _mark_duplicates(entries: list[FileEntry]) -> None:
    groups: dict[str, list[FileEntry]] = defaultdict(list)
    for e in entries:
        if e.sha256 and e.kind != "email":
            groups[e.sha256].append(e)
    for sha, grp in groups.items():
        if len(grp) < 2:
            continue

        def rank(x: FileEntry) -> tuple:
            copy_marker = bool(re.search(r"\(\d+\)|copy|kopi|koopia", x.name, re.I))
            return (x.parent_id is not None, copy_marker, x.status == "duplicate", len(x.path))
        keep = sorted(grp, key=rank)[0]
        for x in grp:
            if x is keep:
                continue
            if x.status == "duplicate" and x.superseded_by:
                continue
            x.status, x.duplicate_of, x.decided_by = "duplicate", keep.id, "rule"
            where = "e-mail attachment" if x.parent_id else "file"
            x.reason = f"Identical {where} to {keep.path.split('::')[-1]} (same content)"


def _mark_content_duplicates(ctx: RunContext, entries: list[FileEntry], scans: dict[str, Any]) -> None:
    """Same content saved twice with different bytes (e.g. a list re-saved by Excel, a PDF printed twice)."""
    fps: dict[str, list[FileEntry]] = defaultdict(list)
    for e in entries:
        if e.status in ("duplicate", "unreadable", "not-relevant"):
            continue
        fp = None
        if e.kind == "sheet" and scans.get(e.id, {}).get("is_bom"):
            parsed = cache_json("bom", e.sha256, lambda e=e: bom.parse(entry_path(ctx, e)))
            fp = f"bom:{round(float(parsed.get('total_kg') or 0), 1)}:{len(parsed.get('lines', []))}"
        elif e.kind == "pdf" and scans.get(e.id, {}).get("text"):
            fp = "pdf:" + hashlib.sha1(re.sub(r"\s+", " ", scans[e.id]["text"]).encode("utf-8")).hexdigest() + f":{e.pages}"
        if fp:
            fps[fp].append(e)
    for fp, grp in fps.items():
        if len(grp) < 2:
            continue
        keep = sorted(grp, key=lambda x: (x.parent_id is not None, len(x.path)))[0]
        for x in grp:
            if x is keep:
                continue
            x.status, x.duplicate_of, x.decided_by = "duplicate", keep.id, "rule"
            x.reason = (f"Same content as {keep.path.split('::')[-1]} (" +
                        ("same lines and total weight" if fp.startswith("bom") else "same text") + ", saved as a different file)")


def _mark_versions(ctx: RunContext, entries: list[FileEntry], scans: dict[str, Any]) -> None:
    by_id = {e.id: e for e in entries}
    tol = float(ctx.kb.num("conflict_tolerance", 0.01)[0])
    # IFC models sharing GlobalIds are versions of the same model: keep the newest
    ifcs = [e for e in entries if e.kind == "ifc" and e.status in ("metal-relevant", "partly-relevant")]
    guid_sets = {e.id: set(cache_json("ifcguids", e.sha256, lambda e=e: sorted(ifc.guid_set(entry_path(ctx, e))))) for e in ifcs}
    overlap_min = float(ctx.cfg.get("pipeline", {}).get("ifc_version_overlap", 0.5))
    ifcs_sorted = sorted(ifcs, key=lambda x: (x.date or "", x.path))
    version_notes = []
    for i, a in enumerate(ifcs_sorted):
        for b in ifcs_sorted[i + 1:]:
            ga, gb = guid_sets[a.id], guid_sets[b.id]
            if not ga or not gb:
                continue
            common = len(ga & gb)
            if common / min(len(ga), len(gb)) >= overlap_min and a.status != "duplicate":
                removed, added = len(ga - gb), len(gb - ga)
                a.status, a.superseded_by, a.decided_by = "duplicate", b.id, "rule"
                a.reason = (f"Older version of {b.name}: shares {common:,} of {len(ga):,} elements; the newer model "
                            f"removes {removed:,} and adds {added:,} elements. The newer model is used.")
                version_notes.append({"older": a.id, "newer": b.id, "common": common, "removed": removed, "added": added,
                                      "older_count": len(ga), "newer_count": len(gb)})
    ctx.data["ifc_versions"] = version_notes
    # material lists: a list equal to the sum of others is a combined copy
    boms = [e for e in entries if e.kind == "sheet" and e.status == "metal-relevant"]
    totals: dict[str, float] = {}
    for e in boms:
        parsed = cache_json("bom", e.sha256, lambda e=e: bom.parse(entry_path(ctx, e)))
        totals[e.id] = float(parsed.get("total_kg") or 0)
    combined_notes = []
    for e in boms:
        others = [o for o in boms if o.id != e.id and o.status == "metal-relevant"]
        for n in (2, 3):
            from itertools import combinations
            for combo in combinations(others, n):
                s = sum(totals[o.id] for o in combo)
                if totals[e.id] and s and abs(s - totals[e.id]) / totals[e.id] < 0.001:
                    e.status, e.decided_by = "duplicate", "rule"
                    e.duplicate_of = combo[0].id
                    e.reason = ("Combined copy of " + " + ".join(o.name for o in combo) +
                                f" (totals match: {totals[e.id]:,.2f} kg). The separate lists are used.")
                    combined_notes.append({"combined": e.id, "parts": [o.id for o in combo], "kg": totals[e.id]})
                    break
            if e.status == "duplicate":
                break
    ctx.data["bom_combined"] = combined_notes
    # name revisions: "drawing rev A.pdf" vs "drawing rev C.pdf"
    rev_re = re.compile(r"[\s_\-]*(?:rev(?:ision)?|r)\.?\s*([A-Z]|\d{1,2})(?=\.[a-z0-9]+$)", re.I)
    groups: dict[str, list[tuple[str, FileEntry]]] = defaultdict(list)
    for e in entries:
        m = rev_re.search(e.name)
        if m and e.status not in ("duplicate", "unreadable"):
            base = rev_re.sub("", e.name).lower()
            groups[base + e.ext].append((m.group(1).upper(), e))
    for base, items in groups.items():
        if len(items) < 2:
            continue
        def key(t: tuple[str, FileEntry]) -> tuple:
            r = t[0]
            return (0, int(r)) if r.isdigit() else (1, ord(r))
        items.sort(key=key)
        newest = items[-1][1]
        for rev, e in items[:-1]:
            e.status, e.superseded_by, e.decided_by = "duplicate", newest.id, "rule"
            e.reason = f"Older revision ({rev}) of {newest.name}; the newest revision is used"


def _apply_file_overrides(ctx: RunContext, entries: list[FileEntry]) -> None:
    for o in ctx.overrides_for("file"):
        for e in entries:
            if e.id == o.key:
                before = e.status
                e.status = o.value
                e.decided_by = "estimator"
                e.reason = f"Set by the estimator ({before} → {o.value})" + (f": {o.reason}" if o.reason else "")
                if o.value != "duplicate":
                    e.duplicate_of = None
                    e.superseded_by = None


def _project_level(entries: list[FileEntry], scans: dict[str, Any]) -> tuple[str, str]:
    active = [e for e in entries if e.status in ("metal-relevant", "partly-relevant")]
    has_model = any(e.kind == "ifc" for e in active)
    has_list = any(e.kind == "sheet" and e.status == "metal-relevant" for e in active)
    has_partlists = any(e.kind == "pdf" and "part lists" in e.reason for e in active)
    has_specs = any(e.kind in ("pdf", "email", "text", "docx") and ("inquiry" in e.reason.lower() or "tender" in e.reason.lower()
                                                                  or e.kind == "email" or "requirements" in e.reason) for e in active)
    has_drawings = any(e.kind in ("pdf", "dxf", "dwg", "image") for e in active)
    if has_model and (has_list or has_specs):
        parts = ["IFC/Tekla model"] + (["material lists"] if has_list else []) + (["specs / RFQ"] if has_specs else [])
        return "full", "Full project: " + ", ".join(parts)
    if has_model:
        return "full", "Full project: IFC/Tekla model"
    if has_partlists or (has_drawings and has_list):
        return "draft", "Draft: drawings with part lists" if has_partlists else "Draft: drawings and a material list"
    if has_list:
        return "draft", "Draft: material list"
    return "idea", "Idea: e-mails, sketches or a few drawings only"
