"""Background runs with live progress (per file and per stage)."""
from __future__ import annotations

import threading
import time
import traceback
import uuid
from typing import Any, Callable, Optional

from .pipeline.runner import STAGES

_jobs: dict[str, dict[str, Any]] = {}
_by_project: dict[str, str] = {}
_lock = threading.Lock()


def new_job(project_id: str, kind: str) -> dict[str, Any]:
    job_id = uuid.uuid4().hex[:12]
    job = {"job_id": job_id, "project_id": project_id, "kind": kind, "state": "queued", "started_at": time.time(),
           "elapsed": 0.0, "message": "Starting…", "revision": None, "error": None,
           "stages": [dict(s, state="waiting", message="", seconds=None) for s in STAGES],
           "files": {}, "files_order": []}
    with _lock:
        _jobs[job_id] = job
        _by_project[project_id] = job_id
    return job


def running_for(project_id: str) -> Optional[dict[str, Any]]:
    jid = _by_project.get(project_id)
    j = _jobs.get(jid) if jid else None
    return j if j and j["state"] in ("queued", "running") else None


def get(job_id: str) -> Optional[dict[str, Any]]:
    j = _jobs.get(job_id)
    if not j:
        return None
    out = {k: v for k, v in j.items() if k not in ("files", "files_order")}
    out["elapsed"] = round((j.get("finished_at") or time.time()) - j["started_at"], 1)
    out["files"] = [j["files"][p] for p in j["files_order"]]
    return out


def progress_cb(job: dict[str, Any]) -> Callable[..., None]:
    stage_started: dict[str, float] = {}

    def cb(**kw: Any) -> None:
        with _lock:
            sid = kw.get("stage")
            if kw.get("stage_state") and sid:
                for s in job["stages"]:
                    if s["id"] == sid:
                        s["state"] = kw["stage_state"]
                        s["message"] = kw.get("message", "")
                        if kw["stage_state"] == "running":
                            stage_started[sid] = time.time()
                        elif sid in stage_started:
                            s["seconds"] = round(time.time() - stage_started[sid], 1)
                job["message"] = kw.get("message", job["message"])
            if kw.get("revision"):
                job["revision"] = kw["revision"]
                job["report_ready_s"] = round(time.time() - job["started_at"], 1)
            path = kw.get("file")
            if path:
                if path not in job["files"]:
                    job["files"][path] = {"path": path, "state": "", "method": None, "note": None}
                    job["files_order"].append(path)
                f = job["files"][path]
                if kw.get("file_state"):
                    f["state"] = kw["file_state"]
                if kw.get("method"):
                    f["method"] = kw["method"]
                if kw.get("note"):
                    f["note"] = kw["note"]
    return cb


def start(job: dict[str, Any], fn: Callable[[Callable[..., None]], int]) -> None:
    def runner() -> None:
        job["state"] = "running"
        try:
            rev = fn(progress_cb(job))
            job["revision"] = rev
            job.setdefault("report_ready_s", round(time.time() - job["started_at"], 1))
            job["state"] = "done"
            job["message"] = "Report ready"
        except Exception as e:  # noqa: BLE001
            job["state"] = "failed"
            job["error"] = friendly_error(e)
            job["trace"] = traceback.format_exc()[-4000:]
            for s in job["stages"]:
                if s["state"] == "running":
                    s["state"] = "failed"
        finally:
            job["finished_at"] = time.time()

    threading.Thread(target=runner, daemon=True).start()


def friendly_error(e: Exception) -> str:
    msg = str(e)
    if isinstance(e, FileNotFoundError) and "Knowledge" in msg:
        return "The knowledge file was not found. Check config/companies/maru.json (knowledge.path) or rebuild it with scripts/build_knowledge.py."
    if isinstance(e, PermissionError):
        return "A file is open in another program or not readable. Close it and run again."
    return f"The run stopped: {msg[:300]}. Try again; if it repeats, open Technical details and send the log to support."
