"""Swappable knowledge source. Today: Maru's Excel file. Tomorrow: Maru's own model / database."""
from __future__ import annotations

from typing import Any

from ..settings import company_config, resolve
from .base import KnowledgeBase, KnowledgeSource


def get_knowledge_source(cfg: dict[str, Any] | None = None) -> KnowledgeSource:
    cfg = cfg or company_config()
    k = cfg.get("knowledge", {})
    kind = k.get("type", "excel")
    if kind == "excel":
        from .excel import ExcelKnowledgeSource
        return ExcelKnowledgeSource(resolve(k.get("path", "drives/maru/knowledge/Maru_knowledge.xlsx")), k.get("columns") or {})
    raise ValueError(f"Unknown knowledge source type '{kind}'")


def load_knowledge() -> KnowledgeBase:
    """Reread on every run, so Maru's edits are picked up immediately."""
    return get_knowledge_source().load()
