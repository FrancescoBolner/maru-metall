"""FastAPI app: JSON API + the built frontend (one process, one port)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import db, jobs, service, sources
from .ai.base import read_log
from .ai.factory import provider_status
from .knowledge import load_knowledge
from .knowledge.excel import knowledge_summary
from .pipeline.learning import dataset_stats
from .settings import FRONTEND_DIST, company_config, resolve
from .storage import get_storage

app = FastAPI(title="Maru Metall — Takeoff & Quoting Assistant", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"],
                   allow_headers=["*"])
db.init()


@app.middleware("http")
async def _no_cache_api(request, call_next):  # type: ignore[no-untyped-def]
    """API data must always be fresh when the user moves between pages (rendered source images may be cached)."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/api/") and "/source/pdf" not in path and "/source/image" not in path and "/branding/" not in path:
        response.headers["Cache-Control"] = "no-store"
    elif path in ("/", "/index.html"):
        response.headers["Cache-Control"] = "no-cache"
    return response


@app.on_event("startup")
def _startup() -> None:
    from .reports import warm_up
    try:
        warm_up()
    except Exception:  # noqa: BLE001 - PDFs then render in-process
        pass


def _nf(e: Exception) -> HTTPException:
    return HTTPException(status_code=404, detail=str(e).strip("'\""))


# ------------------------------------------------------------------------------------------- config
@app.get("/api/config")
def config() -> dict[str, Any]:
    c = company_config()
    return {"company": {k: c.get(k) for k in ("id", "name", "legal_name", "app_title", "language", "languages", "currency",
                                              "currency_symbol", "number_format", "branding")},
            "ai": provider_status()}


@app.get("/api/branding/logo")
def logo(variant: str = "default") -> FileResponse:
    b = company_config().get("branding", {})
    p = resolve(b.get("logo", "config/companies/maru_logo.png"))
    if variant == "white":
        w = p.with_name(p.stem + "_white" + p.suffix)
        if w.exists():
            p = w
    return FileResponse(p, media_type="image/png")


# ------------------------------------------------------------------------------------------- companies & projects
@app.get("/api/companies")
def companies() -> list[dict[str, Any]]:
    return service.companies()


@app.get("/api/companies/{company}/projects")
def projects(company: str) -> list[dict[str, Any]]:
    return service.projects(company)


@app.get("/api/projects/{pid}")
def project(pid: str) -> dict[str, Any]:
    try:
        return service.project_info(pid)
    except KeyError as e:
        raise _nf(e)


@app.post("/api/projects/{pid}/run")
def run(pid: str, kind: str = "run") -> dict[str, Any]:
    try:
        return service.start_run(pid, kind)
    except KeyError as e:
        raise _nf(e)


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict[str, Any]:
    j = jobs.get(job_id)
    if not j:
        raise HTTPException(404, "This run is no longer known (the server was restarted). Open the project again.")
    return j


@app.get("/api/projects/{pid}/revisions/{rev}")
def revision(pid: str, rev: int) -> Response:
    try:
        p = service.result_path(pid, rev)
        if not p.exists():
            raise KeyError(f"Revision {rev} not found")
        return Response(p.read_bytes(), media_type="application/json")
    except KeyError as e:
        raise _nf(e)


@app.get("/api/projects/{pid}/revisions/{rev}/download/{kind}")
def download(pid: str, rev: int, kind: str) -> FileResponse:
    try:
        res = service.load_result(pid, rev)
    except KeyError as e:
        raise _nf(e)
    name = res.reports.get(kind)
    if not name:
        raise HTTPException(404, "This file was not generated. See the warnings in the report.")
    p = get_storage().reports_dir(res.company) / name
    if not p.exists():
        raise HTTPException(404, "The file is no longer in the reports folder.")
    media = "application/pdf" if p.suffix == ".pdf" else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    return FileResponse(p, media_type=media, filename=p.name)


# ------------------------------------------------------------------------------------------- sources
@app.get("/api/projects/{pid}/source/pdf")
def src_pdf(pid: str, file_id: str, page: int, rev: Optional[int] = None, boxes: str = "[]", max_px: int = 1700) -> Response:
    try:
        png = sources.pdf_page(pid, rev, file_id, page, json.loads(boxes or "[]"), max_px)
    except KeyError as e:
        raise _nf(e)
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=3600"})


@app.get("/api/projects/{pid}/source/pdfinfo")
def src_pdfinfo(pid: str, file_id: str, page: int = 1, rev: Optional[int] = None) -> dict[str, Any]:
    try:
        return sources.pdf_info(pid, rev, file_id, page)
    except KeyError as e:
        raise _nf(e)


@app.get("/api/projects/{pid}/source/sheet")
def src_sheet(pid: str, file_id: str, row: int, sheet: Optional[str] = None, rev: Optional[int] = None) -> dict[str, Any]:
    try:
        return sources.sheet(pid, rev, file_id, sheet, row)
    except KeyError as e:
        raise _nf(e)


@app.get("/api/projects/{pid}/source/email")
def src_email(pid: str, file_id: str, rev: Optional[int] = None) -> dict[str, Any]:
    try:
        return sources.email(pid, rev, file_id)
    except KeyError as e:
        raise _nf(e)


@app.get("/api/projects/{pid}/source/image")
def src_image(pid: str, file_id: str, rev: Optional[int] = None) -> Response:
    try:
        return Response(sources.image(pid, rev, file_id), media_type="image/png")
    except KeyError as e:
        raise _nf(e)


@app.get("/api/projects/{pid}/source/text")
def src_text(pid: str, file_id: str, rev: Optional[int] = None) -> dict[str, Any]:
    try:
        return sources.text(pid, rev, file_id)
    except KeyError as e:
        raise _nf(e)


class GuidQuery(BaseModel):
    guids: list[str] = []


@app.post("/api/projects/{pid}/source/ifc")
def src_ifc(pid: str, file_id: str, q: GuidQuery, rev: Optional[int] = None) -> dict[str, Any]:
    try:
        return sources.ifc(pid, rev, file_id, q.guids)
    except KeyError as e:
        raise _nf(e)


@app.get("/api/knowledge/rows/{kid}")
def kn_row(kid: str) -> dict[str, Any]:
    try:
        return sources.knowledge_row(kid)
    except KeyError as e:
        raise _nf(e)


# ------------------------------------------------------------------------------------------- review
class EditIn(BaseModel):
    edit_key: str
    value: Any
    reason: Optional[str] = None
    label: Optional[str] = None
    before: Any = None


@app.post("/api/projects/{pid}/edits")
def add_edit(pid: str, e: EditIn) -> dict[str, Any]:
    try:
        return service.add_edit(pid, e.edit_key, e.value, e.reason, e.label, e.before)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.delete("/api/projects/{pid}/edits/{oid}")
def del_edit(pid: str, oid: int) -> dict[str, Any]:
    db.deactivate_override(pid, oid)
    return {"ok": True}


class CorrectionIn(BaseModel):
    text: str


@app.post("/api/projects/{pid}/corrections/interpret")
def interpret(pid: str, c: CorrectionIn) -> dict[str, Any]:
    if not c.text.strip():
        raise HTTPException(400, "Write the correction first.")
    try:
        return service.interpret_correction(pid, c.text)
    except KeyError as e:
        raise _nf(e)


class AcceptIn(BaseModel):
    correction_id: int
    text: str
    changes: list[dict[str, Any]]


@app.post("/api/projects/{pid}/corrections/accept")
def accept(pid: str, a: AcceptIn) -> dict[str, Any]:
    return {"applied": service.accept_correction(pid, a.correction_id, a.changes, a.text)}


@app.post("/api/projects/{pid}/approve/{rev}")
def approve(pid: str, rev: int) -> dict[str, Any]:
    try:
        return service.approve(pid, rev)
    except KeyError as e:
        raise _nf(e)


# ------------------------------------------------------------------------------------------- technical details
@app.get("/api/tech/status")
def tech_status() -> dict[str, Any]:
    try:
        kb = knowledge_summary(load_knowledge())
    except Exception as e:  # noqa: BLE001
        kb = {"error": str(e)}
    return {"ai": provider_status(), "knowledge": kb, "dataset": dataset_stats()}


@app.get("/api/tech/logs")
def tech_logs(project_id: Optional[str] = None, limit: int = 200) -> list[dict[str, Any]]:
    return read_log(limit, project_id)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ------------------------------------------------------------------------------------------- frontend
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str) -> FileResponse:
        f = FRONTEND_DIST / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND_DIST / "index.html")
