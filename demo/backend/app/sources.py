"""Source panel: render the exact place a value comes from (PDF page with highlight, sheet window,
e-mail text, IFC elements with a plan view, image, knowledge-file row)."""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .knowledge import load_knowledge
from .models import FileEntry, RunResult
from .parsers import bom, email_, misc, pdfdoc
from .pipeline.context import CACHE_DIR, cache_json
from .pipeline.filemap import blob_path
from .service import load_result, project_ref

RENDER = CACHE_DIR / "render"
RENDER.mkdir(parents=True, exist_ok=True)


def _entry(pid: str, rev: Optional[int], file_id: str) -> tuple[FileEntry, Path]:
    res = load_result(pid, rev)
    e = next((x for x in res.filemap.entries if x.id == file_id), None)
    if e is None:
        raise KeyError("File not found in this report")
    path = blob_path(e.sha256, e.name) if e.parent_id else project_ref(pid).root / e.path
    if not path.exists():
        raise KeyError("The file is no longer on the drive")
    return e, path


def pdf_page(pid: str, rev: Optional[int], file_id: str, page: int, boxes: list[list[float]], max_px: int = 1700) -> bytes:
    e, path = _entry(pid, rev, file_id)
    key = hashlib.sha1(json.dumps([e.sha256, page, boxes, max_px]).encode()).hexdigest()
    out = RENDER / f"{key}.png"
    if not out.exists():
        out.write_bytes(pdfdoc.render_page_png(path, page, boxes, max_px=max_px))
    return out.read_bytes()


def pdf_info(pid: str, rev: Optional[int], file_id: str, page: int) -> dict[str, Any]:
    e, path = _entry(pid, rev, file_id)
    w, h = pdfdoc.page_size(path, page)
    return {"name": e.name, "path": e.path, "pages": e.pages, "page": page, "width": w, "height": h}


def sheet(pid: str, rev: Optional[int], file_id: str, sheet_name: Optional[str], row: int) -> dict[str, Any]:
    e, path = _entry(pid, rev, file_id)
    w = bom.sheet_window(path, sheet_name, row)
    w.update(name=e.name, path=e.path)
    return w


def email(pid: str, rev: Optional[int], file_id: str) -> dict[str, Any]:
    e, path = _entry(pid, rev, file_id)
    m = email_.parse(path)
    return {"name": e.name, "path": e.path, "from": m["from"], "to": m["to"], "cc": m["cc"], "date": m["date"],
            "subject": m["subject"], "body": m["body"], "attachments": [a["name"] for a in m["attachments"]]}


def image(pid: str, rev: Optional[int], file_id: str) -> bytes:
    e, path = _entry(pid, rev, file_id)
    return misc.image_png(path, 1600)


def text(pid: str, rev: Optional[int], file_id: str) -> dict[str, Any]:
    e, path = _entry(pid, rev, file_id)
    if e.kind == "pdf":
        t = "\n".join(f"— page {p} —\n{x}" for p, x in pdfdoc.page_texts(path, range(0, min(e.pages or 1, 6))))
    else:
        t = misc.read_text(path, 100_000)
    return {"name": e.name, "path": e.path, "text": t}


def ifc(pid: str, rev: Optional[int], file_id: str, guids: list[str]) -> dict[str, Any]:
    e, path = _entry(pid, rev, file_id)
    from .parsers import ifc as ifcp
    data = cache_json("ifc", e.sha256, lambda: ifcp.parse(path))
    els = data["elements"]
    gs = set(guids)
    sel = [x for x in els if x["guid"] in gs]
    # plan view: member axes projected on X/Y, in metres relative to the model's corner
    pts = []
    for x in els:
        if x.get("axis"):
            pts += [x["axis"][0], x["axis"][1]]
        elif x.get("point"):
            pts.append(x["point"])
    if pts:
        minx = min(p[0] for p in pts)
        miny = min(p[1] for p in pts)
        maxx = max(p[0] for p in pts)
        maxy = max(p[1] for p in pts)
    else:
        minx = miny = 0
        maxx = maxy = 1

    def seg(x: dict[str, Any]) -> Optional[list[float]]:
        if x.get("axis"):
            a, b = x["axis"]
            return [round((a[0] - minx) / 1000, 2), round((a[1] - miny) / 1000, 2), round((b[0] - minx) / 1000, 2), round((b[1] - miny) / 1000, 2)]
        if x.get("point"):
            p = x["point"]
            return [round((p[0] - minx) / 1000, 2), round((p[1] - miny) / 1000, 2)] * 2
        return None

    background = [s for s in (seg(x) for x in els if x["guid"] not in gs and x["entity"] in ("IfcBeam", "IfcColumn", "IfcMember")) if s]
    highlight = [s for s in (seg(x) for x in sel) if s]
    cols = ["guid", "entity", "name", "assembly_name", "assembly_mark", "profile", "grade", "length", "weight", "area", "phase", "class"]
    return {"name": e.name, "path": e.path, "total_elements": len(els), "selected": len(sel),
            "elements": [{k: x.get(k) for k in cols} for x in sel[:400]],
            "plan": {"width": round((maxx - minx) / 1000, 2), "height": round((maxy - miny) / 1000, 2),
                     "background": background, "highlight": highlight},
            "application": data.get("application"), "schema": data.get("schema")}


def knowledge_row(kid: str) -> dict[str, Any]:
    kb = load_knowledge()
    r = kb.row(kid)
    if r is None:
        raise KeyError(f"Knowledge row {kid} not found")
    return {"id": r.id, "sheet": r.sheet, "row": r.row, "file": kb.source_name, "version": kb.version,
            "data": {k: (v if not hasattr(v, "isoformat") else v.isoformat()) for k, v in r.data.items()}}
