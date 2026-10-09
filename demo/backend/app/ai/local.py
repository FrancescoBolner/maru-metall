"""Local, private AI on Maru's own infrastructure: any OpenAI-compatible endpoint
(Ollama `ollama serve` -> http://localhost:11434/v1, vLLM `vllm serve <model>` -> http://localhost:8000/v1,
LM Studio, llama.cpp server). Nothing leaves Maru's network.

Switch with AI_PROVIDER=local (and LOCAL_AI_BASE_URL / LOCAL_AI_MODEL) in .env.
Vision calls need a vision-capable local model (e.g. qwen2.5-vl, llama3.2-vision); text-only models
are still fine for e-mails, RFQ forms and specifications.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .base import AIError, LLMProvider, b64


class LocalProvider(LLMProvider):
    name = "local"
    sends_data_off_machine = False

    def __init__(self, cfg: dict[str, Any], max_retries: int = 3):
        super().__init__(cfg, max_retries)
        self.model = cfg.get("model", "qwen2.5:14b-instruct")
        self.base_url = cfg.get("base_url", "http://localhost:11434/v1").rstrip("/")
        self.timeout = float(cfg.get("timeout_s", 300))
        self.temperature = cfg.get("temperature", 0)
        self.price_in = float(cfg.get("price_usd_per_mtok_in", 0))
        self.price_out = float(cfg.get("price_usd_per_mtok_out", 0))
        self.use_schema = True

    def _raw(self, system: str, user_text: str, images: list[bytes], schema: dict[str, Any], call: str) -> tuple[str, int, int]:
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for img in images:
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64(img)}"}})
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": content if images else user_text}],
            "temperature": self.temperature,
        }
        if self.use_schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": call, "schema": schema, "strict": True}}
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {self.cfg.get('api_key', 'local')}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:  # noqa: S310 - URL comes from config
                data = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 400 and self.use_schema:
                self.use_schema = False  # older servers: JSON via prompt + validation
                return self._raw(system, user_text, images, schema, call)
            raise AIError(f"The local AI server answered {e.code}: {e.read()[:300]!r}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            raise AIError(f"The local AI server at {self.base_url} is not reachable. Start it or switch AI_PROVIDER.") from e
        text = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage") or {}
        return text, int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0))
