"""Training data for Maru's own AI, collected from day one, plus the learning loop.

data/training/
  filemap_decisions.jsonl   one line per file per run: relevance decision and who made it
  values.jsonl              every extracted / predicted value with its references
  corrections.jsonl         every estimator correction: before -> after, reason, source
  approved/<project>_rev<N>.json   final approved values (test cases for future model versions)
  guidelines/guidelines_v<N>.md     versioned guidelines used in prompts for similar projects
  guidelines/examples.jsonl         situation -> correction examples
  calibration_suggestions.jsonl     corrections that point to a rate or norm (never applied automatically)
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..ai.base import AIError, CallCtx
from ..models import RunResult
from ..settings import TRAINING_DIR

GUIDE_DIR = TRAINING_DIR / "guidelines"
APPROVED_DIR = TRAINING_DIR / "approved"
for _d in (GUIDE_DIR, APPROVED_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _append(name: str, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with (TRAINING_DIR / name).open("a", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def record_run(res: RunResult) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    base = {"project_id": res.project_id, "project": res.project_name, "company": res.company, "revision": res.revision, "ts": ts}
    _append("filemap_decisions.jsonl", [
        base | {"file": e.path, "sha256": e.sha256, "kind": e.kind, "size": e.size, "status": e.status, "reason": e.reason,
                "decided_by": e.decided_by, "duplicate_of": e.duplicate_of, "superseded_by": e.superseded_by,
                "read_by": e.read_by, "error": e.error}
        for e in res.filemap.entries])
    rows = []
    for v in res.values.values():
        if v.type in ("extracted", "predicted") and (v.group not in ("quantities",) or v.id.startswith(("cat.", "total."))):
            rows.append(base | {"value_id": v.id, "label": v.label, "value": v.value, "unit": v.unit, "type": v.type,
                                "confidence": v.confidence, "reasoning": v.reasoning, "edited": v.edited.model_dump() if v.edited else None,
                                "refs": [{k: r.get(k) for k in ("kind", "path", "page", "sheet", "cell", "snippet") if r.get(k) is not None}
                                         | ({"guids": len(r.get("guids") or [])} if r.get("guids") else {})
                                         for r in [x.model_dump() for x in v.refs[:4]]]})
    _append("values.jsonl", rows)


def record_corrections(res: RunResult, changes: list[dict[str, Any]], overrides: list[dict[str, Any]]) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    rows = []
    for o in overrides:
        rows.append({"project_id": res.project_id, "project": res.project_name, "revision": res.revision, "ts": ts,
                     "target": o["target"], "key": o["key"], "field": o["field"], "label": o.get("label"),
                     "before": o.get("before"), "after": o.get("value"), "reason": o.get("reason"), "source": o.get("source"),
                     "text": o.get("text")})
    _append("corrections.jsonl", rows)


def current_guidelines() -> tuple[str, int]:
    files = sorted(GUIDE_DIR.glob("guidelines_v*.md"), key=lambda p: int(re.search(r"v(\d+)", p.name).group(1)))
    if not files:
        return "", 0
    p = files[-1]
    return p.read_text(encoding="utf-8"), int(re.search(r"v(\d+)", p.name).group(1))


def on_approve(res: RunResult, provider, corrections: list[dict[str, Any]]) -> dict[str, Any]:
    """Approved project -> test case, guidelines update, calibration suggestions."""
    ts = datetime.now().isoformat(timespec="seconds")
    case = {"project_id": res.project_id, "project": res.project_name, "company": res.company, "revision": res.revision,
            "quote_number": res.report_name, "approved_at": ts, "level": res.filemap.level,
            "values": {vid: {"label": v.label, "value": v.value, "unit": v.unit, "type": v.type}
                       for vid, v in res.values.items()
                       if vid.startswith(("total.", "cat.", "fact.", "co2.total", "allow.")) or v.edited},
            "files": [{"path": e.path, "status": e.status, "sha256": e.sha256} for e in res.filemap.entries]}
    case_path = APPROVED_DIR / f"{res.project_id}_rev{res.revision}.json"
    case_path.write_text(json.dumps(case, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    current, ver = current_guidelines()
    out: dict[str, Any] = {"test_case": str(case_path.name), "guidelines_version": ver, "suggestions": 0}
    if corrections:
        try:
            upd = provider.update_guidelines(current, corrections, res.project_name, CallCtx(project_id=res.project_id))
            text = "\n".join(f"- {g}" for g in upd.guidelines)
            header = (f"# Estimator guidelines v{ver + 1}\n\nUpdated {ts} after approval of {res.project_name} "
                      f"({res.report_name}). Used in the AI prompts for similar projects.\n\n")
            (GUIDE_DIR / f"guidelines_v{ver + 1}.md").write_text(header + text + "\n", encoding="utf-8")
            with (GUIDE_DIR / "examples.jsonl").open("a", encoding="utf-8") as fh:
                for ex in upd.examples:
                    fh.write(json.dumps({"project": res.project_name, "ts": ts} | ex.model_dump(), ensure_ascii=False) + "\n")
            out["guidelines_version"] = ver + 1
        except AIError as e:
            out["guidelines_error"] = str(e)
    # calibration suggestions: corrections on rates, norms or rule-driven quantities
    sugg = []
    for c in corrections:
        tgt = c.get("target")
        key = str(c.get("key"))
        if tgt == "param" and key in ("labour_rate", "margin_material", "margin_production", "packaging_rate"):
            kn = {"labour_rate": "GEN-01 / LAB-EE", "margin_material": "GEN-03", "margin_production": "GEN-04", "packaging_rate": "GEN-06"}[key]
            sugg.append({"knowledge_row": kn, "current": c.get("before"), "suggested": c.get("after"),
                         "evidence": f"{res.project_name}: estimator set {c.get('label') or key} to {c.get('after')}"
                                     + (f" ({c['reason']})" if c.get("reason") else "")})
        elif tgt == "category" and c.get("field") == "surface":
            sugg.append({"knowledge_row": "Predictions PRD-04..06 (default corrosivity)", "current": c.get("before"),
                         "suggested": c.get("after"), "evidence": f"{res.project_name}: {key} surface changed"})
        elif tgt == "line" or tgt == "allowance":
            sugg.append({"knowledge_row": "Predictions / Time_norms (quantity rules)", "current": c.get("before"),
                         "suggested": c.get("after"), "evidence": f"{res.project_name}: {c.get('label') or key} corrected"})
    if sugg:
        _append("calibration_suggestions.jsonl", [s | {"project": res.project_name, "ts": ts, "status": "to review by Maru"} for s in sugg])
    out["suggestions"] = len(sugg)
    return out


def dataset_stats() -> dict[str, Any]:
    def count(name: str) -> int:
        p = TRAINING_DIR / name
        return sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0
    guide, ver = current_guidelines()
    sugg = []
    p = TRAINING_DIR / "calibration_suggestions.jsonl"
    if p.exists():
        sugg = [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()][-30:]
    return {"filemap_decisions": count("filemap_decisions.jsonl"), "values": count("values.jsonl"),
            "corrections": count("corrections.jsonl"), "approved_cases": len(list(APPROVED_DIR.glob("*.json"))),
            "guidelines_version": ver, "guidelines": guide, "calibration_suggestions": sugg}
