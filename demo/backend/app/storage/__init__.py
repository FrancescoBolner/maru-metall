"""Swappable storage. Local folders now (simulated drives); Google Drive / SharePoint later would implement
the same interface (typically by syncing a project folder to a local cache before a run)."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from ..settings import app_config, resolve


class Storage(Protocol):
    def companies(self) -> list[dict[str, Any]]: ...
    def projects(self, company: str) -> list[dict[str, Any]]: ...
    def project_root(self, company: str, project: str) -> Path: ...
    def reports_dir(self, company: str) -> Path: ...


class LocalStorage:
    """drives/client/<company>/<project_name>/** and drives/maru/reports/<company>/"""

    def __init__(self, client_root: Path, reports_root: Path):
        self.client_root = client_root
        self.reports_root = reports_root
        self.client_root.mkdir(parents=True, exist_ok=True)
        self.reports_root.mkdir(parents=True, exist_ok=True)

    def companies(self) -> list[dict[str, Any]]:
        out = []
        for d in sorted(p for p in self.client_root.iterdir() if p.is_dir() and not p.name.startswith(".")):
            projects = [p for p in d.iterdir() if p.is_dir() and not p.name.startswith(".")]
            out.append({"name": d.name, "projects": len(projects)})
        return out

    def projects(self, company: str) -> list[dict[str, Any]]:
        base = self.client_root / company
        if not base.is_dir():
            return []
        out = []
        for d in sorted(p for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")):
            files = [f for f in d.rglob("*") if f.is_file()]
            mtime = max((f.stat().st_mtime for f in files), default=d.stat().st_mtime)
            out.append({"name": d.name, "files": len(files), "size": sum(f.stat().st_size for f in files),
                        "modified": datetime.fromtimestamp(mtime).isoformat(timespec="seconds")})
        return out

    def project_root(self, company: str, project: str) -> Path:
        p = (self.client_root / company / project).resolve()
        if not str(p).startswith(str(self.client_root.resolve())):
            raise ValueError("invalid project path")
        return p

    def reports_dir(self, company: str) -> Path:
        d = self.reports_root / company
        d.mkdir(parents=True, exist_ok=True)
        return d


def get_storage() -> Storage:
    s = app_config().get("storage", {})
    if s.get("type", "local") == "local":
        return LocalStorage(resolve(s.get("client_root", "drives/client")), resolve(s.get("reports_dir", "drives/maru/reports")))
    raise ValueError(f"Unknown storage type {s.get('type')}")
