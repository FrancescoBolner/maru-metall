"""Application service: projects, runs, revisions, review (edits + written corrections), approval."""
from __future__ import annotations

import json
import re
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from . import db, jobs
from .ai.base import AIError, CallCtx
from .ai.factory import get_provider
from .knowledge.base import normalize_system
from .models import Override, RunResult
from .pipeline.context import ProjectRef, project_id, project_short
from .pipeline.learning import current_guidelines, on_approve, record_corrections, record_run
from .pipeline.runner import run_pipeline
from .settings import RUNS_DIR, company_config
from .storage import get_storage

_run_locks: dict[str, threading.Lock] = {}


# ------------------------------------------------------------------------------------------- projects
def companies() -> list[dict[str, Any]]:
    return get_storage().companies()


def projects(company: str) -> list[dict[str, Any]]:
    st = get_storage()
    out = []
    for p in st.projects(company):
        pid = project_id(company, p["name"])
        latest = db.latest_revision(pid)
        running = jobs.running_for(pid)
        out.append(p | {"id": pid, "short": project_short(p["name"]), "company": company,
                        "latest": latest, "running_job": running["job_id"] if running else None})
    return out


def project_ref(pid: str) -> ProjectRef:
    st = get_storage()
    for c in st.companies():
        for p in st.projects(c["name"]):
            if project_id(c["name"], p["name"]) == pid:
                return ProjectRef(id=pid, company=c["name"], name=p["name"], root=st.project_root(c["name"], p["name"]),
                                  short=project_short(p["name"]))
    raise KeyError(f"Project {pid} not found on the client drive")


def project_info(pid: str) -> dict[str, Any]:
    ref = project_ref(pid)
    db.ensure_project(pid, ref.company, ref.name, ref.short)
    revs = db.revisions(pid)
    ovs = db.overrides(pid)
    running = jobs.running_for(pid)
    files = [f for f in ref.root.rglob("*") if f.is_file()]
    return {"id": pid, "company": ref.company, "name": ref.name, "short": ref.short, "path": str(ref.root),
            "files": len(files), "size": sum(f.stat().st_size for f in files), "revisions": revs,
            "pending_overrides": [o for o in ovs if o["applied_in"] is None], "overrides": ovs,
            "corrections": db.corrections(pid), "running_job": running["job_id"] if running else None}


# ------------------------------------------------------------------------------------------- results
def result_path(pid: str, rev: int) -> Path:
    return RUNS_DIR / pid / f"rev{rev}.json"


@lru_cache(maxsize=12)
def _load(path: str, mtime: float) -> RunResult:
    return RunResult.model_validate_json(Path(path).read_text(encoding="utf-8"))


def load_result(pid: str, rev: Optional[int] = None) -> RunResult:
    if rev is None:
        latest = db.latest_revision(pid)
        if not latest:
            raise KeyError("No report yet for this project")
        rev = int(latest["rev"])
    p = result_path(pid, rev)
    if not p.exists():
        raise KeyError(f"Revision {rev} not found")
    return _load(str(p), p.stat().st_mtime)


def _overrides_models(pid: str) -> list[Override]:
    out = []
    for o in db.overrides(pid):
        out.append(Override(id=str(o["id"]), target=o["target"], key=o["key"], field=o["field"], value=o["value"],
                            reason=o.get("reason"), source=o["source"], text=o.get("text"), created_at=o["created_at"],
                            label=o.get("label"), before=o.get("before")))
    return out


def start_run(pid: str, kind: str = "run") -> dict[str, Any]:
    if jobs.running_for(pid):
        return jobs.get(jobs.running_for(pid)["job_id"])
    ref = project_ref(pid)
    db.ensure_project(pid, ref.company, ref.name, ref.short)
    job = jobs.new_job(pid, kind)

    def work(progress) -> int:
        lock = _run_locks.setdefault(pid, threading.Lock())
        with lock:
            return _run(ref, kind, progress)
    jobs.start(job, work)
    return jobs.get(job["job_id"])


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _run(ref: ProjectRef, kind: str, progress) -> int:
    cfg = company_config()
    seq = db.allocate_quote_seq(ref.id)
    numbering = cfg.get("numbering", {})
    quote_number = numbering.get("pattern", "{project_short}_quote_{seq:04d}").format(project_short=ref.short, seq=seq)
    rev = db.next_rev(ref.id)
    report_name = quote_number + (numbering.get("revision_suffix", "_rev{rev}").format(rev=rev) if rev > 1 else "")
    overrides = _overrides_models(ref.id)
    guidelines, _ = current_guidelines()
    res, ctx = run_pipeline(ref, rev, quote_number, report_name, overrides, progress, guidelines)
    prev = None
    if rev > 1:
        try:
            prev = load_result(ref.id, rev - 1)
        except KeyError:
            prev = None
    new_ovs = [o for o in db.overrides(ref.id) if o["applied_in"] is None]
    res.changes = compute_changes(prev, res, new_ovs) if prev else []
    out = result_path(ref.id, rev)
    out.parent.mkdir(parents=True, exist_ok=True)
    _atomic_write(out, res.model_dump_json())
    s = res.summary
    vals = res.values
    db.add_revision({"project_id": ref.id, "rev": rev, "quote_number": quote_number, "report_name": report_name,
                     "status": "draft", "created_at": db.now(), "duration_s": res.timings.get("total"),
                     "ai_cost_eur": res.ai.get("cost_eur"), "provider": res.ai.get("provider"),
                     "price": vals[s["price_id"]].value, "tonnes": vals["total.kg"].value / 1000,
                     "hours": vals[s["hours_id"]].value, "co2": vals[s["co2_id"]].value, "level": res.filemap.level,
                     "changes": len(res.changes), "result_path": str(out), "kind": kind})
    db.mark_applied(ref.id, rev)
    # the interactive report is ready now; the files follow
    progress(stage="6", stage_state="running", message="Report ready · writing PDF and Excel", revision=rev)
    try:
        record_run(res)
        if new_ovs:
            record_corrections(res, res.changes, new_ovs)
    except Exception as e:  # noqa: BLE001
        res.warnings.append(f"Training data not written: {e}")
    # reports (PDF client + internal, Excel) next to Maru's other quotes
    try:
        from .reports import write_reports
        res.reports = write_reports(res, ref)
    except Exception as e:  # noqa: BLE001 - a report problem must be visible, never a broken file
        res.warnings.append(f"The PDF/Excel export failed: {e}. The interactive report is complete.")
    _atomic_write(out, res.model_dump_json())
    progress(stage="6", stage_state="done", message=f"{report_name} ready")
    return rev


# ------------------------------------------------------------------------------------------- changes
def compute_changes(prev: RunResult, new: RunResult, applied: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def val(r: RunResult, vid: str) -> Any:
        v = r.values.get(vid)
        return v.value if v else None

    def add(label: str, a: Any, b: Any, unit: Optional[str], vid: Optional[str], kind: str) -> None:
        if a == b:
            return
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs((b or 0) - (a or 0)) < 1e-6 * max(1, abs(a or 0)):
            return
        out.append({"label": label, "before": a, "after": b, "unit": unit, "value_id": vid, "kind": kind})

    for vid, label in (("total.price", "Total price"), ("total.kg", "Total steel"), ("total.hours", "Working hours"),
                       ("total.metal_hours", "Workshop hours"), ("total.paint_litres", "Paint"), ("co2.total", "Carbon balance")):
        v = new.values.get(vid)
        add(label, val(prev, vid), val(new, vid), v.unit if v else None, vid, "total")
    pc = {c.name: c for c in prev.categories}
    nc = {c.name: c for c in new.categories}
    for name in list(dict.fromkeys(list(pc) + list(nc))):
        a, b = pc.get(name), nc.get(name)
        if a and b:
            add(f"{name}: surface", val(prev, a.surface_id), val(new, b.surface_id), None, b.surface_id, "category")
            add(f"{name}: in scope", a.included, b.included, None, b.kg_id, "category")
            add(f"{name}: weight", val(prev, a.kg_id), val(new, b.kg_id), "kg", b.kg_id, "category")
        elif b:
            add(f"{name}", "—", "added", None, b.kg_id, "category")
        elif a:
            add(f"{name}", "present", "removed", None, None, "category")
    pf = {e.id: e.status for e in prev.filemap.entries}
    for e in new.filemap.entries:
        if e.id in pf and pf[e.id] != e.status:
            add(f"File {e.name}", pf[e.id], e.status, None, None, "file")
    for k in set(prev.values) & set(new.values):
        if k.startswith(("fact.", "allow.", "param.")):
            add(new.values[k].label, prev.values[k].value, new.values[k].value, new.values[k].unit, k, "fact")
    for o in applied:
        out.insert(0, {"label": f"Correction: {o.get('label') or o['key']}", "before": o.get("before"), "after": o.get("value"),
                       "unit": None, "value_id": None, "kind": "correction", "reason": o.get("reason"), "source": o.get("source"),
                       "text": o.get("text")})
    return out


# ------------------------------------------------------------------------------------------- review
def edit_key_to_override(edit_key: str, value: Any) -> dict[str, Any]:
    parts = edit_key.split(":")
    target = parts[0]
    if target == "line":
        return {"target": "line", "key": parts[1], "field": parts[2], "value": float(value)}
    if target == "category":
        key = parts[1]
        field = parts[2]
        if field == "surface":
            value = normalize_system(str(value))
        if field == "included":
            value = str(value).lower() in ("true", "1", "yes", "included")
        return {"target": "category", "key": key, "field": field, "value": value}
    if target == "fact":
        return {"target": "fact", "key": parts[1], "field": "value", "value": value}
    if target == "param":
        v: Any = value
        if parts[1] in ("labour_rate", "margin_material", "margin_production", "packaging_rate"):
            v = float(str(value).replace(",", "."))
        return {"target": "param", "key": parts[1], "field": "value", "value": v}
    if target == "allowance":
        return {"target": "allowance", "key": parts[1], "field": parts[2], "value": float(value)}
    if target == "file":
        return {"target": "file", "key": parts[1], "field": "status", "value": value}
    raise ValueError(f"Unknown edit target {edit_key}")


def add_edit(pid: str, edit_key: str, value: Any, reason: Optional[str], label: Optional[str], before: Any,
             source: str = "direct_edit", text: Optional[str] = None) -> dict[str, Any]:
    o = edit_key_to_override(edit_key, value)
    o.update(reason=reason, label=label, before=before, source=source, text=text)
    oid = db.add_override(pid, o)
    return o | {"id": oid}


def correction_targets(res: RunResult) -> list[dict[str, Any]]:
    v = res.values
    systems = sorted({str(x) for x in ["NONE", "C1", "C2M", "C2H", "C3M", "C3H", "C3VH", "C4M", "C4H", "C5M", "HDG"]})
    t: list[dict[str, Any]] = []
    for c in res.categories:
        base = c.name.split(" — ")[0]
        key = f"{base}|{c.phase or ''}"
        match = c.name + (" phase " + c.phase if c.phase else "")
        t.append({"id": f"category:{key}:surface", "label": f"{c.name} — surface treatment", "current": v[c.surface_id].value,
                  "allowed": systems, "match": match})
        t.append({"id": f"category:{key}:included", "label": f"{c.name} — in scope", "current": str(c.included).lower(),
                  "allowed": ["true", "false"], "match": match})
    for key in ("paint_system", "fire_rating", "execution_class", "delivery_address", "corrosivity_class", "recycled_content",
                "bid_deadline", "delivery_country"):
        vid = next((f.value_id for f in res.facts if f.key == key), None)
        t.append({"id": f"fact:{key}", "label": (v[vid].label if vid else key.replace("_", " ")),
                  "current": v[vid].value if vid else None,
                  "allowed": ["EXC1", "EXC2", "EXC3", "EXC4"] if key == "execution_class" else None,
                  "match": key.replace("_", " ")})
    for key, label in (("margin_material", "Margin on material"), ("margin_production", "Margin on production"),
                       ("labour_rate", "Labour rate €/h")):
        t.append({"id": f"param:{key}", "label": label, "current": v.get(f"param.{key}").value if v.get(f"param.{key}") else None,
                  "numeric": True, "match": label})
    t.append({"id": "param:method", "label": "Pricing method", "current": res.summary.get("method"), "allowed": ["detailed", "quick"],
              "match": "method quick detailed per tonne"})
    t.append({"id": "param:include_fasteners", "label": "Fasteners (bolts) in the price", "current": None,
              "allowed": ["true", "false"], "match": "fasteners bolts"})
    for key, label in (("anchors", "Anchors quantity"), ("studs", "Rebar studs quantity")):
        vv = v.get(f"allow.{key}.qty")
        if vv:
            t.append({"id": f"allowance:{key}:qty", "label": label, "current": vv.value, "numeric": True, "match": label})
    for l in res.lines[:220]:
        t.append({"id": f"line:{l.id}:pieces", "label": f"{l.profile} {l.grade or ''} ({l.category}{' phase ' + l.phase if l.phase else ''}) — pieces",
                  "current": v[l.pieces_id].value, "numeric": True, "match": f"{l.profile} {l.category}"})
    return t


def interpret_correction(pid: str, text: str) -> dict[str, Any]:
    res = load_result(pid)
    targets = correction_targets(res)
    provider = get_provider()
    try:
        prop = provider.interpret_correction(text, targets, CallCtx(project_id=pid))
    except AIError as e:
        return {"error": f"The correction could not be interpreted ({e}). Edit the values directly instead.", "changes": [],
                "not_applied": []}
    tmap = {t["id"]: t for t in targets}
    changes = []
    for ch in prop.changes:
        t = tmap.get(ch.target)
        if not t:
            continue
        changes.append({"edit_key": ch.target, "label": t["label"], "before": t.get("current"), "after": ch.new_value,
                        "explanation": ch.explanation})
    cid = db.add_correction(pid, text, {"changes": changes, "not_applied": [n.model_dump() for n in prop.not_applied]})
    return {"correction_id": cid, "changes": changes, "not_applied": [n.model_dump() for n in prop.not_applied],
            "provider": provider.name}


def accept_correction(pid: str, correction_id: int, accepted: list[dict[str, Any]], text: str) -> list[dict[str, Any]]:
    out = []
    for ch in accepted:
        out.append(add_edit(pid, ch["edit_key"], ch["after"], ch.get("explanation"), ch.get("label"), ch.get("before"),
                            source="written_correction", text=text))
    db.accept_correction(correction_id, accepted)
    return out


def approve(pid: str, rev: int) -> dict[str, Any]:
    res = load_result(pid, rev)
    db.set_status(pid, rev, "approved")
    corrections = [{"target": o["target"], "key": o["key"], "field": o["field"], "label": o.get("label"), "before": o.get("before"),
                    "after": o.get("value"), "reason": o.get("reason"), "source": o.get("source")}
                   for o in db.overrides(pid) if o["applied_in"] is not None and o["applied_in"] <= rev]
    info = on_approve(res, get_provider(), corrections)
    # mark status inside the stored result too
    p = result_path(pid, rev)
    res2 = RunResult.model_validate_json(p.read_text(encoding="utf-8"))
    res2.status = "approved"
    _atomic_write(p, res2.model_dump_json())

    def rerender() -> None:  # the files lose the DRAFT mark; runs in the background
        try:
            from .reports import write_reports
            write_reports(res2, project_ref(pid))
        except Exception:  # noqa: BLE001 - the approved status is already stored
            pass
    threading.Thread(target=rerender, daemon=True).start()
    return info
