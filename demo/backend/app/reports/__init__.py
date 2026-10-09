"""Report files next to Maru's other quotes: drives/maru/reports/<company>/<project>_quote_<n>[_revN].*

  <name>.pdf            client offer (clean, like Maru's real offers)
  <name>_internal.pdf   internal report with full traceability
  <name>.xlsx           all data and references
  <name>.json           link between the project folder and the report (traceability)
"""
from __future__ import annotations

import json
import os
import threading
from concurrent.futures import ProcessPoolExecutor
from multiprocessing import get_context
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from ..models import RunResult
from ..settings import resolve, company_config
from .view import build_view

TEMPLATES = Path(__file__).parent / "templates"
FONTS = Path(__file__).parent / "fonts"

_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))


def render_html(res: RunResult, template: str) -> str:
    view = build_view(res)
    logo = resolve(company_config().get("branding", {}).get("logo", "config/companies/maru_logo.png"))
    css = _env.from_string((TEMPLATES / "base.css").read_text(encoding="utf-8")).render(fonts=FONTS.as_uri())
    return _env.get_template(template).render(**view, css=css, logo=logo.as_uri())


def html_to_pdf(html: str, out: Path) -> str:
    """WeasyPrint (best layout). If its system libraries are missing (e.g. plain Windows), fall back to PyMuPDF."""
    try:
        import weasyprint  # noqa: F401
        from weasyprint import HTML
        HTML(string=html, base_url=str(TEMPLATES)).write_pdf(str(out))
        return "weasyprint"
    except (OSError, ImportError):
        import pymupdf
        html, img_dir = _simplify_for_story(html)
        story = pymupdf.Story(html=html, archive=pymupdf.Archive(str(img_dir)) if img_dir else None)
        writer = pymupdf.DocumentWriter(str(out))
        mediabox = pymupdf.paper_rect("a4")
        where = mediabox + (40, 50, -40, -50)
        more = True
        while more:
            dev = writer.begin_page(mediabox)
            more, _ = story.place(where)
            story.draw(dev)
            writer.end_page()
        writer.close()
        return "pymupdf"


def _simplify_for_story(html: str) -> tuple[str, Optional[Path]]:
    """PyMuPDF's HTML engine knows less CSS: drop page rules and web fonts, turn widths into attributes,
    load images from a local archive. The running footer becomes a normal block at the end."""
    import re
    from urllib.parse import unquote, urlparse
    html = re.sub(r"@page\s*{[^{}]*({[^{}]*}[^{}]*)*}", "", html)
    html = re.sub(r"@font-face\s*{[^}]*}", "", html)
    html = html.replace('font-family: "Plex",', "font-family:").replace("font-family: Plex;", "")
    html = re.sub(r'<(td|th)([^>]*?)style="width:\s*(\d+)%;?\s*', r'<\1\2width="\3%" style="', html)
    img_dir: Optional[Path] = None

    def img(m: "re.Match[str]") -> str:
        nonlocal img_dir
        path = Path(unquote(urlparse(m.group(1)).path))
        if path.exists():
            img_dir = path.parent
            return f'src="{path.name}"'
        return 'src=""'
    html = re.sub(r'src="(file://[^"]+)"', img, html)
    html = html.replace('class="logo"', 'class="logo" width="170"')
    m = re.search(r'<div class="footer">.*?</div>', html, flags=re.S)
    if m:  # running footers are not supported: print the company block once, at the end
        html = html.replace(m.group(0), "")
        html = html.replace("</body>", f'<div style="margin-top:8mm;font-size:7pt;color:#01437D">{m.group(0)}</div></body>')
    return html, img_dir


_pool: Optional[ProcessPoolExecutor] = None
_pool_lock = threading.Lock()


def _get_pool() -> Optional[ProcessPoolExecutor]:
    """Two warm worker processes render the PDFs in parallel (PDF layout is CPU-bound).
    'spawn' is safe next to the web server's threads. Set MARU_PDF_WORKERS=0 to render in-process."""
    global _pool
    n = int(os.environ.get("MARU_PDF_WORKERS", "2"))
    if n <= 0:
        return None
    with _pool_lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(max_workers=n, mp_context=get_context("spawn"))
        return _pool


def _warm() -> bool:
    try:
        import weasyprint  # noqa: F401
    except (OSError, ImportError):
        pass
    return True


def warm_up() -> None:
    """Start the PDF workers when the server starts, so the first report is not slower."""
    pool = _get_pool()
    if pool is not None:
        for _ in range(pool._max_workers):  # noqa: SLF001
            pool.submit(_warm)


def _pdf_job(html: str, out: str) -> str:
    return html_to_pdf(html, Path(out))


def write_reports(res: RunResult, ref) -> dict[str, str]:
    global _pool
    from ..storage import get_storage
    from .excel import write_excel
    out_dir = get_storage().reports_dir(res.company)
    name = res.report_name
    files: dict[str, str] = {}
    client = out_dir / f"{name}.pdf"
    internal = out_dir / f"{name}_internal.pdf"
    xlsx = out_dir / f"{name}.xlsx"
    html_client = render_html(res, "client_offer.html")
    html_internal = render_html(res, "internal_report.html")
    pool = _get_pool()
    engine = None
    if pool is not None:
        try:
            f_int = pool.submit(_pdf_job, html_internal, str(internal))
            f_cli = pool.submit(_pdf_job, html_client, str(client))
            write_excel(res, xlsx)
            engine = f_cli.result(timeout=300)
            f_int.result(timeout=300)
        except Exception:  # noqa: BLE001 - broken pool (e.g. killed worker): render in-process instead
            with _pool_lock:
                _pool = None
            engine = None
    if engine is None:
        engine = html_to_pdf(html_client, client)
        html_to_pdf(html_internal, internal)
        if not xlsx.exists():
            write_excel(res, xlsx)
    files = {"client_pdf": client.name, "internal_pdf": internal.name, "xlsx": xlsx.name, "pdf_engine": engine}
    meta = {"report": name, "quote_number": res.quote_number, "revision": res.revision, "status": res.status,
            "project": res.project_name, "company": res.company, "project_folder": str(ref.root),
            "project_id": res.project_id, "created_at": res.created_at,
            "files_used": [{"path": e.path, "sha256": e.sha256, "status": e.status} for e in res.filemap.entries],
            "knowledge_file": res.knowledge, "outputs": files}
    (out_dir / f"{name}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    files["meta"] = f"{name}.json"
    return files
