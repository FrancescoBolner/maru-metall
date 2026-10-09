"""PDF reading with PyMuPDF: metadata, text, keyword hits with bounding boxes, embedded part lists,
and page rendering with highlights for the source panel."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

import pymupdf

pymupdf.TOOLS.mupdf_display_errors(False)

POS_RE = re.compile(r"^[A-Z][A-Z0-9]{1,}-\d{2,}$")
MAT_RE = re.compile(r"^S\d{3}[A-Z0-9+]*$")
EXC_RE = re.compile(r"^EXC\d$")
DATE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}$")
NUM_RE = re.compile(r"^-?\d+(?:[.,]\d+)?$")


def open_pdf(path: Path | bytes) -> pymupdf.Document:
    if isinstance(path, (bytes, bytearray)):
        return pymupdf.open(stream=bytes(path), filetype="pdf")
    return pymupdf.open(str(path))


def scan(path: Path | bytes, max_pages: int = 6) -> dict[str, Any]:
    """Cheap metadata + text sample for the file map."""
    doc = open_pdf(path)
    pages = doc.page_count
    text_parts = []
    chars = 0
    for i in range(min(pages, max_pages)):
        t = doc[i].get_text()
        chars += len(t.strip())
        text_parts.append(t)
    sample = "\n".join(text_parts)
    title = (doc.metadata or {}).get("title") or ""
    out = {"pages": pages, "text": sample, "chars": chars, "title": title,
           "scanned": chars < 30 * min(pages, max_pages)}
    doc.close()
    return out


def page_texts(path: Path | bytes, pages: Optional[Iterable[int]] = None) -> list[tuple[int, str]]:
    doc = open_pdf(path)
    idx = range(doc.page_count) if pages is None else [p for p in pages if 0 <= p < doc.page_count]
    out = [(i + 1, doc[i].get_text()) for i in idx]
    doc.close()
    return out


def find_bbox(path: Path | bytes, page_no: int, snippet: str) -> list[list[float]]:
    """Bounding boxes of a snippet on a page (1-based page). Tries the full snippet, then shorter parts."""
    if not snippet:
        return []
    doc = open_pdf(path)
    try:
        if not (1 <= page_no <= doc.page_count):
            return []
        page = doc[page_no - 1]
        cands = [snippet.strip()]
        words = snippet.split()
        if len(words) > 6:
            cands.append(" ".join(words[:6]))
        if len(words) > 3:
            cands.append(" ".join(words[:3]))
        for c in cands:
            rects = page.search_for(c, quads=False)
            if rects:
                return [[round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)] for r in rects[:6]]
        # form fields: label and value sit in different cells ("Date:      22.10.2025")
        out: list[list[float]] = []
        for part in re.split(r"\s{2,}|\t|\n", snippet):
            part = part.strip()
            if len(part) < 3:
                continue
            rects = page.search_for(part, quads=False)
            if len(rects) == 1 or (rects and len(part) >= 8):
                r = rects[0]
                out.append([round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)])
            if len(out) >= 6:
                break
        return out
    finally:
        doc.close()


def keyword_hits(path: Path | bytes, patterns: dict[str, re.Pattern], max_pages: int = 400,
                 max_hits_per_key: int = 40) -> list[dict[str, Any]]:
    """Search every page for requirement keywords; returns hits with page, snippet and bbox."""
    doc = open_pdf(path)
    hits: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for i in range(min(doc.page_count, max_pages)):
        page = doc[i]
        text = page.get_text()
        if not text.strip():
            continue
        flat = re.sub(r"[ \t]+", " ", text)
        for key, pat in patterns.items():
            for m in pat.finditer(flat):
                if counts.get(key, 0) >= max_hits_per_key:
                    break
                snippet = m.group(0).strip()
                line_start = flat.rfind("\n", 0, m.start()) + 1
                line_end = flat.find("\n", m.end())
                context = flat[max(0, line_start - 120): (line_end if line_end > 0 else m.end()) + 120]
                rects = page.search_for(snippet.split("\n")[0][:60]) if snippet else []
                hits.append({
                    "key": key, "page": i + 1, "snippet": snippet[:200],
                    "context": re.sub(r"\s+", " ", context).strip()[:400],
                    "bbox": [[round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1)] for r in rects[:3]],
                })
                counts[key] = counts.get(key, 0) + 1
    doc.close()
    return hits


def render_page_png(path: Path | bytes, page_no: int, boxes: Optional[list[list[float]]] = None,
                    max_px: int = 1600, color: tuple[float, float, float] = (1.0, 0.75, 0.0)) -> bytes:
    """Render a page to PNG and draw highlight rectangles (PDF coordinates)."""
    doc = open_pdf(path)
    try:
        page = doc[max(0, min(page_no - 1, doc.page_count - 1))]
        rect = page.rect
        zoom = max(0.2, min(4.0, max_px / max(rect.width, rect.height)))
        if boxes:
            shape = page.new_shape()
            for b in boxes:
                r = pymupdf.Rect(*b)
                r = r + (-3, -3, 3, 3)
                shape.draw_rect(r)
            shape.finish(color=(0.85, 0.1, 0.1), fill=color, fill_opacity=0.35, width=1.8)
            shape.commit()
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def page_size(path: Path | bytes, page_no: int) -> tuple[float, float]:
    doc = open_pdf(path)
    try:
        r = doc[max(0, min(page_no - 1, doc.page_count - 1))].rect
        return r.width, r.height
    finally:
        doc.close()


# ----------------------------------------------------------------------------------------------
# Embedded assembly / part lists (Tekla report layout printed in drawing sets)

HEADER_LABELS = [
    ("pcs", ("pcs.", "pcs", "kpl", "tk")),
    ("length", ("length",)),
    ("width", ("width",)),
    ("height", ("height", "thickness")),
    ("weight", ("paino", "weight")),
    ("area", ("area",)),
    ("date", ("date",)),
]


@dataclass
class ListRow:
    page: int
    kind: str                     # "assembly" | "part"
    position: str
    name: str = ""
    profile: str = ""
    material: str = ""
    exc: str = ""
    shade: str = ""
    pcs: float = 0
    length: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    weight: Optional[float] = None
    weight_sum: Optional[float] = None
    area: Optional[float] = None
    area_sum: Optional[float] = None
    bbox: list[float] = field(default_factory=list)
    text: str = ""
    assembly: Optional[str] = None


def _rows_of_words(page: pymupdf.Page, tol: float = 2.5) -> list[list[tuple]]:
    words = page.get_text("words")
    words = sorted(words, key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    out: list[list[tuple]] = []
    cur: list[tuple] = []
    cy: Optional[float] = None
    for w in words:
        yc = (w[1] + w[3]) / 2
        if cy is None or abs(yc - cy) <= tol:
            cur.append(w)
            cy = yc if cy is None else (cy + yc) / 2
        else:
            out.append(sorted(cur, key=lambda w: w[0]))
            cur, cy = [w], yc
    if cur:
        out.append(sorted(cur, key=lambda w: w[0]))
    return out


def _header_anchors(rows: list[list[tuple]]) -> dict[str, float]:
    """Find column centres from header words ('Pcs.', 'Length', 'Weight sum', 'Area sum', ...)."""
    anchors: dict[str, float] = {}
    for r in rows:
        texts = [w[4].lower() for w in r]
        if not any(t in ("pcs.", "pcs", "length", "paino", "weight", "date") for t in texts):
            continue
        for i, w in enumerate(r):
            t = w[4].lower().strip(":")
            nxt = r[i + 1][4].lower() if i + 1 < len(r) else ""
            gap_ok = i + 1 < len(r) and r[i + 1][0] - w[2] < 30
            cx = (w[0] + w[2]) / 2
            if nxt.startswith("[") and gap_ok:
                cx = (w[0] + r[i + 1][2]) / 2
            if nxt == "sum" and gap_ok:
                cx = (w[0] + r[i + 1][2]) / 2
                key = {"weight": "weight_sum", "length": "length_sum", "area": "area_sum"}.get(t)
                if key and key not in anchors:
                    anchors[key] = cx
                continue
            for key, labels in HEADER_LABELS:
                if t in labels and key not in anchors:
                    if key == "date" and "length" not in anchors and "pcs" not in anchors:
                        continue
                    anchors[key] = cx
                    break
    return anchors


def parse_part_lists(path: Path | bytes, max_pages: int = 400) -> dict[str, Any]:
    """Parse Tekla-style 'ASSEMBLY PART LIST' / 'PART LIST' tables printed in drawing PDFs.

    Returns {"assemblies": [...], "parts": [...], "kind": "assembly-list"|"part-list"|None, "pages": [...]}.
    Numbers are assigned to columns by the nearest header column centre, so layouts that omit empty
    cells (e.g. width/height of profiles) still parse correctly.
    """
    doc = open_pdf(path)
    assemblies: list[ListRow] = []
    parts: list[ListRow] = []
    list_kind: Optional[str] = None
    anchors: dict[str, float] = {}
    pages_used: list[int] = []
    current_asm: Optional[ListRow] = None
    for pi in range(min(doc.page_count, max_pages)):
        page = doc[pi]
        txt = page.get_text()
        is_list_page = ("PART LIST" in txt) or (anchors and POS_RE.search(txt.split("\n")[0] if txt else ""))
        rows = _rows_of_words(page)
        if not rows:
            continue
        new_anchors = _header_anchors(rows[:25])
        if "ASSEMBLY PART LIST" in txt:
            list_kind = list_kind or "assembly-list"
        elif "PART LIST" in txt and "PART LIST FOR ASSEMBLY" not in txt:
            list_kind = list_kind or "part-list"
        if new_anchors.get("pcs") and (new_anchors.get("weight") or new_anchors.get("weight_sum")):
            anchors = new_anchors
        if not anchors:
            continue
        found_on_page = 0
        for r in rows:
            toks = [w[4] for w in r]
            if len(toks) < 5:
                continue
            # locate position token among the first three tokens
            pos_idx = next((i for i, t in enumerate(toks[:3]) if POS_RE.match(t)), None)
            if pos_idx is None:
                continue
            # list rows always carry a date column; tables printed on drawing sheets do not
            if not any(DATE_RE.match(t) for t in toks):
                continue
            pos = toks[pos_idx]
            rest = r[pos_idx + 1:]
            exc = next((w[4] for w in rest if EXC_RE.match(w[4])), "")
            mat = next((w[4] for w in rest if MAT_RE.match(w[4])), "")
            # textual columns before the first numeric column
            first_num_x = min((w[0] for w in rest if NUM_RE.match(w[4]) and (w[0] + w[2]) / 2 > anchors.get("pcs", 0) - 25),
                              default=10_000)
            text_words = [w for w in rest if w[0] < first_num_x - 2 and not EXC_RE.match(w[4]) and not MAT_RE.match(w[4])]
            is_asm = bool(exc) and list_kind != "part-list"
            row = ListRow(page=pi + 1, kind="assembly" if is_asm else "part", position=pos, exc=exc, material=mat,
                          bbox=[round(min(w[0] for w in r), 1), round(min(w[1] for w in r), 1),
                                round(max(w[2] for w in r), 1), round(max(w[3] for w in r), 1)],
                          text=" ".join(toks))
            if row.kind == "assembly":
                # name = words before EXC; shade = words after EXC
                exc_x = next(w[0] for w in rest if EXC_RE.match(w[4]))
                row.name = " ".join(w[4] for w in text_words if w[0] < exc_x)
                row.shade = " ".join(w[4] for w in text_words if w[0] > exc_x)
            else:
                mat_x = next((w[0] for w in rest if MAT_RE.match(w[4])), 10_000)
                pre = [w[4] for w in text_words if w[0] < mat_x]
                # part lists may have a 'Name' column (PLATE, BEAM) before the profile
                if len(pre) >= 2 and not re.search(r"\d", pre[0]):
                    row.name, row.profile = pre[0], " ".join(pre[1:])
                else:
                    row.profile = " ".join(pre)
            numeric = [w for w in rest if NUM_RE.match(w[4]) and w[0] >= first_num_x - 2]
            for w in numeric:
                cx = (w[0] + w[2]) / 2
                key = min(anchors, key=lambda k: abs(anchors[k] - cx) if k != "date" else 10_000)
                val = float(w[4].replace(",", "."))
                if getattr(row, key, None) in (None, 0):
                    setattr(row, key, val)
            if not row.pcs:
                continue
            if row.kind == "assembly":
                current_asm = row
                assemblies.append(row)
            else:
                row.assembly = current_asm.position if (current_asm and list_kind == "assembly-list") else None
                parts.append(row)
            found_on_page += 1
        if found_on_page:
            pages_used.append(pi + 1)
    doc.close()
    return {"kind": list_kind, "assemblies": assemblies, "parts": parts, "pages": pages_used}


def doc_title_block(text: str) -> dict[str, str]:
    """Pick title-block fields from a drawing's first page (best effort)."""
    out: dict[str, str] = {}
    m = re.search(r"(\d{6,}-[A-Z0-9]+-\d{4}-\d{4}-\d{6})", text)
    if m:
        out["document"] = m.group(1)
    m = re.search(r"Warehouse, Steel Structures,([^\n]+\n[^\n]+)", text)
    if m:
        out["title"] = re.sub(r"\s+", " ", m.group(0)).strip()
    m = re.search(r"APPROVED FOR CONSTRUCTION\s+(\d{2}\.\d{2}\.\d{4})", text, re.I)
    if m:
        out["status_date"] = m.group(1)
    return out
