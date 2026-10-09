"""Orchestrates the six stages and reports progress (Extract → Predict → Present)."""
from __future__ import annotations

import time
import uuid
from typing import Any, Callable, Optional

from ..ai.factory import get_provider
from ..knowledge import load_knowledge
from ..models import Override, RunResult
from .context import ProjectRef, RunContext

STAGES = [
    {"id": "1", "phase": "Extract", "name": "Read the shared drive", "detail": "File map, relevance, duplicates, project level"},
    {"id": "2", "phase": "Extract", "name": "AI extraction", "detail": "Code reads models and lists; AI reads e-mails, forms and images"},
    {"id": "3", "phase": "Extract", "name": "Structured takeoff", "detail": "Metal-only quantities with references"},
    {"id": "4a", "phase": "Predict", "name": "Risks and assumptions", "detail": "Missing data predicted, risks ranked"},
    {"id": "4b", "phase": "Predict", "name": "Rule engine: cost + CO2", "detail": "Hours, paint, material, price, carbon"},
    {"id": "6", "phase": "Present", "name": "Quote", "detail": "Report, PDF and Excel"},
]


def run_pipeline(project: ProjectRef, revision: int, quote_number: str, report_name: str, overrides: list[Override],
                 progress: Optional[Callable[..., None]] = None, guidelines: str = "") -> tuple[RunResult, RunContext]:
    from .carbon import run_carbon
    from .extract import run_extraction
    from .filemap import build_filemap
    from .predict import build_risks, run_predict
    from .report import build_result
    from .rules import run_rules
    from .takeoff import build_takeoff

    t0 = time.time()
    kb = load_knowledge()
    provider = get_provider()
    ctx = RunContext(project=project, kb=kb, provider=provider, revision=revision, quote_number=quote_number,
                     report_name=report_name, overrides=overrides, progress=progress, guidelines=guidelines,
                     run_id=uuid.uuid4().hex[:10])

    def stage(sid: str, state: str, msg: str = "") -> None:
        ctx.emit(stage=sid, stage_state=state, message=msg)

    stage("1", "running", "Mapping the project folder")
    with ctx.stage("1"):
        ctx.data["filemap"] = build_filemap(ctx)
    fm = ctx.data["filemap"]
    stage("1", "done", f"{len(fm.entries)} files mapped · project level: {fm.level}")

    stage("2", "running", "Reading the relevant files")
    with ctx.stage("2"):
        ctx.data["extract"] = run_extraction(ctx)
    failed = ctx.data["extract"]["failed"]
    stage("2", "done", f"{sum(1 for e in fm.entries if e.read_by in ('code', 'ai', 'code+ai'))} files read" +
          (f" · {len(failed)} could not be read" if failed else ""))

    stage("3", "running", "Building the structured takeoff")
    with ctx.stage("3"):
        build_takeoff(ctx)
    stage("3", "done", f"{len(ctx.data['lines'])} takeoff lines in {len(ctx.data['categories'])} categories")

    stage("4a", "running", "Predicting missing data")
    with ctx.stage("4a"):
        run_predict(ctx)
    stage("4a", "done", "Predictions ready")

    stage("4b", "running", "Applying Maru's rates and norms")
    with ctx.stage("4b"):
        run_rules(ctx)
        run_carbon(ctx)
        build_risks(ctx)
    stage("4b", "done", "Hours, cost and carbon calculated")

    stage("6", "running", "Writing the report")
    with ctx.stage("6"):
        result = build_result(ctx)
    ctx.timings["total"] = round(time.time() - t0, 2)
    result.timings = ctx.timings
    result.ai = ctx.usage.as_dict() | provider.describe()
    return result, ctx
