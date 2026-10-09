"""Small readers: images, text files, DSTV NC1 (CNC), DXF (ezdxf), DWG header, Tekla .db1."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional


def image_info(data_or_path: bytes | Path) -> dict[str, Any]:
    from PIL import Image
    import io
    try:
        im = Image.open(io.BytesIO(data_or_path)) if isinstance(data_or_path, (bytes, bytearray)) else Image.open(data_or_path)
        return {"width": im.width, "height": im.height, "mode": im.mode, "format": im.format}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def image_png(data_or_path: bytes | Path, max_px: int = 1600) -> bytes:
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(data_or_path)) if isinstance(data_or_path, (bytes, bytearray)) else Image.open(data_or_path)
    im = im.convert("RGB")
    im.thumbnail((max_px, max_px))
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def read_text(path_or_bytes: Path | bytes, limit: int = 200_000) -> str:
    raw = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else Path(path_or_bytes).read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw[:limit].decode(enc)
        except UnicodeDecodeError:
            continue
    return raw[:limit].decode("utf-8", errors="replace")


def parse_dstv(path: Path) -> dict[str, Any]:
    """DSTV NC1 header (ST block): order, drawing, phase, piece mark, grade, quantity, profile, length,
    weight per metre; counts BO (holes) and AK/IK contour blocks."""
    text = read_text(path, 2_000_000)
    lines = [l.rstrip() for l in text.splitlines()]
    out: dict[str, Any] = {"holes": 0, "contours": 0}
    try:
        i = next(k for k, l in enumerate(lines) if l.strip() == "ST")
    except StopIteration:
        return {"error": "no ST block"}
    vals = [re.sub(r"\*\*.*$", "", l).strip() for l in lines[i + 1:i + 25]]
    keys = ["order", "drawing", "phase", "mark", "grade", "quantity", "profile", "code", "length", "height",
            "width", "flange_t", "web_t", "radius", "kg_per_m", "paint_m2_per_m"]
    for k, v in zip(keys, vals):
        out[k] = v
    for k in ("quantity", "length", "height", "width", "kg_per_m", "paint_m2_per_m", "flange_t", "web_t"):
        try:
            out[k] = float(str(out.get(k, "")).split()[0])
        except (ValueError, IndexError):
            out[k] = None
    block = None
    for l in lines[i:]:
        s = l.strip()
        if s in ("BO", "AK", "IK", "SI", "EN", "KO", "PU", "KA"):
            block = s
            if s in ("AK", "IK"):
                out["contours"] += 1
            continue
        if block == "BO" and s and not s.startswith("**"):
            out["holes"] += 1
    if out.get("length") and out.get("kg_per_m"):
        out["kg"] = round(out["length"] / 1000 * out["kg_per_m"], 3)
    return out


def dxf_texts(path: Path, limit: int = 5000) -> dict[str, Any]:
    try:
        import ezdxf
        doc = ezdxf.readfile(str(path))
    except Exception as e:  # noqa: BLE001
        return {"error": f"DXF not readable: {e}"}
    texts = []
    layers = set()
    for e in doc.modelspace():
        layers.add(e.dxf.layer)
        if e.dxftype() in ("TEXT", "MTEXT"):
            try:
                t = e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text
                texts.append(t)
            except Exception:
                pass
        if len(texts) >= limit:
            break
    return {"texts": texts, "layers": sorted(layers), "entities": len(doc.modelspace())}


def dwg_version(path: Path) -> Optional[str]:
    try:
        head = Path(path).read_bytes()[:6].decode("ascii", errors="ignore")
        return {"AC1032": "AutoCAD 2018+", "AC1027": "AutoCAD 2013", "AC1024": "AutoCAD 2010",
                "AC1021": "AutoCAD 2007", "AC1018": "AutoCAD 2004"}.get(head, head or None)
    except Exception:
        return None
