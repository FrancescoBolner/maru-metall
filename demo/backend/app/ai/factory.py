"""Choose the AI provider from configuration (a config change, no code change)."""
from __future__ import annotations

from typing import Any

from ..settings import anthropic_api_key, app_config
from .base import AIProvider
from .offline import OfflineProvider


def get_provider() -> AIProvider:
    ai: dict[str, Any] = app_config().get("ai", {})
    choice = (ai.get("provider") or "auto").lower()
    retries = int(ai.get("max_retries", 3))
    common = {"max_chars": int(ai.get("max_chars_per_call", 24000))}
    if choice in ("auto", "claude"):
        key = anthropic_api_key()
        if key:
            from .claude import ClaudeProvider
            return ClaudeProvider({**ai.get("claude", {}), **common}, api_key=key, max_retries=retries)
        if choice == "claude":
            p = OfflineProvider({}, retries)
            p.fallback_reason = "AI_PROVIDER=claude but ANTHROPIC_API_KEY is not set: using offline rules"  # type: ignore[attr-defined]
            return p
    if choice == "local":
        from .local import LocalProvider
        return LocalProvider({**ai.get("local", {}), **common}, max_retries=retries)
    p = OfflineProvider({}, retries)
    p.fallback_reason = "No AI key configured: offline rules provider"  # type: ignore[attr-defined]
    return p


def provider_status() -> dict[str, Any]:
    p = get_provider()
    d = p.describe()
    d["fallback_reason"] = getattr(p, "fallback_reason", None)
    d["configured"] = (app_config().get("ai", {}).get("provider") or "auto")
    d["key_present"] = bool(anthropic_api_key())
    return d
