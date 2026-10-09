"""Run context shared by all pipeline stages."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from ..ai.base import AIProvider, CallCtx, Usage
from ..knowledge.base import KnowledgeBase
from ..models import Override
from ..settings import CACHE_DIR, app_config, company_config
from ..values import Registry

BLOBS = CACHE_DIR / "blobs"
PARSED = CACHE_DIR / "parsed"
BLOBS.mkdir(parents=True, exist_ok=True)
PARSED.mkdir(parents=True, exist_ok=True)


def ascii_fold(s: str) -> str:
    table = {"æ": "ae", "Æ": "Ae", "ø": "o", "Ø": "O", "å": "a", "Å": "A", "ß": "ss", "õ": "o", "Õ": "O"}
    s = "".join(table.get(c, c) for c in s)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def project_short(name: str) -> str:
    """'30480 Akkasæter Lager - og vedlikeholdshall' -> 'Akkasaeter'; 'Kotka CAM 2E500 - ...' -> 'Kotka'."""
    for tok in re.split(r"[\s_\-]+", ascii_fold(name)):
        t = re.sub(r"[^A-Za-z]", "", tok)
        if len(t) >= 3 and t.upper() not in ("THE", "AND", "CAM", "PROJECT", "LOT") and not re.search(r"\d", tok):
            return t[0].upper() + t[1:]
    return re.sub(r"[^A-Za-z0-9]", "", ascii_fold(name))[:20] or "Project"


def project_id(company: str, name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", ascii_fold(f"{company}--{name}").lower()).strip("-")
    return s[:90]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


CACHE_VERSION = "3"  # bump when a parser changes so cached results are rebuilt


def cache_json(kind: str, key: str, fn: Callable[[], Any]) -> Any:
    """Cache a parser result by content hash (re-runs and revisions are near-instant)."""
    p = PARSED / f"{key}.{kind}.v{CACHE_VERSION}.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            p.unlink(missing_ok=True)
    data = fn()
    p.write_text(json.dumps(data, ensure_ascii=False, default=str), encoding="utf-8")
    return data


@dataclass
class ProjectRef:
    id: str
    company: str
    name: str
    root: Path
    short: str


@dataclass
class RunContext:
    project: ProjectRef
    kb: KnowledgeBase
    provider: AIProvider
    revision: int
    quote_number: str
    report_name: str
    overrides: list[Override] = field(default_factory=list)
    progress: Optional[Callable[..., None]] = None
    reg: Registry = field(default_factory=Registry)
    usage: Usage = field(default_factory=Usage)
    timings: dict[str, float] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    data: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""
    guidelines: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @property
    def cfg(self) -> dict[str, Any]:
        return app_config()

    @property
    def company_cfg(self) -> dict[str, Any]:
        return company_config()

    def call_ctx(self, file_id: Optional[str] = None, file_name: Optional[str] = None) -> CallCtx:
        return CallCtx(project_id=self.project.id, run_id=self.run_id, file_id=file_id, file_name=file_name, usage=self.usage)

    def emit(self, **kw: Any) -> None:
        if self.progress:
            try:
                self.progress(**kw)
            except Exception:
                pass

    def overrides_for(self, target: str) -> list[Override]:
        return [o for o in self.overrides if o.target == target]

    def override(self, target: str, key: str, field_: str = "value") -> Optional[Override]:
        found = None
        for o in self.overrides:
            if o.target == target and o.key == key and (o.field == field_ or field_ == "*"):
                found = o  # last one wins
        return found

    def stage(self, name: str) -> "StageTimer":
        return StageTimer(self, name)


class StageTimer:
    def __init__(self, ctx: RunContext, name: str):
        self.ctx, self.name = ctx, name

    def __enter__(self) -> "StageTimer":
        self.t0 = time.time()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.ctx.timings[self.name] = round(time.time() - self.t0, 2)
