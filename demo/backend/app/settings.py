"""Paths, environment and configuration loading.

Everything is relative to the demo root (the folder that contains `backend/`, `config/`,
`drives/`, `data/` and `logs/`), so the app keeps working when the `demo/` folder is moved.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

DEMO_ROOT = Path(os.environ.get("MARU_DEMO_ROOT") or Path(__file__).resolve().parents[2])
CONFIG_DIR = DEMO_ROOT / "config"
DATA_DIR = DEMO_ROOT / "data"
LOGS_DIR = DEMO_ROOT / "logs"
DOCS_DIR = DEMO_ROOT / "docs"
FRONTEND_DIST = DEMO_ROOT / "frontend" / "dist"

CACHE_DIR = DATA_DIR / "cache"
RUNS_DIR = DATA_DIR / "runs"
TRAINING_DIR = DATA_DIR / "training"
DB_PATH = DATA_DIR / "maru_demo.sqlite"


def _load_dotenv() -> None:
    """Minimal .env loader (no extra dependency). Existing environment variables win."""
    env_file = DEMO_ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


_load_dotenv()

for _d in (DATA_DIR, LOGS_DIR, CACHE_DIR, RUNS_DIR, TRAINING_DIR):
    _d.mkdir(parents=True, exist_ok=True)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def app_config() -> dict[str, Any]:
    cfg = _read_json(CONFIG_DIR / "app.json")
    # Environment overrides (documented in .env.example)
    ai = cfg.setdefault("ai", {})
    if os.environ.get("AI_PROVIDER"):
        ai["provider"] = os.environ["AI_PROVIDER"]
    if os.environ.get("CLAUDE_MODEL"):
        ai.setdefault("claude", {})["model"] = os.environ["CLAUDE_MODEL"]
    if os.environ.get("LOCAL_AI_BASE_URL"):
        ai.setdefault("local", {})["base_url"] = os.environ["LOCAL_AI_BASE_URL"]
    if os.environ.get("LOCAL_AI_MODEL"):
        ai.setdefault("local", {})["model"] = os.environ["LOCAL_AI_MODEL"]
    return cfg


@lru_cache(maxsize=8)
def company_config(company_id: str | None = None) -> dict[str, Any]:
    cid = company_id or app_config().get("company", "maru")
    return _read_json(CONFIG_DIR / "companies" / f"{cid}.json")


def resolve(rel: str | Path) -> Path:
    """Resolve a path from config (relative to the demo root)."""
    p = Path(rel)
    return p if p.is_absolute() else (DEMO_ROOT / p)


def anthropic_api_key() -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    return key or None
