"""Claude (Anthropic API) provider. Used for the demo; data leaves the machine (see README, Data protection)."""
from __future__ import annotations

from typing import Any

from .base import AIError, LLMProvider, b64


class ClaudeProvider(LLMProvider):
    name = "claude"
    sends_data_off_machine = True

    def __init__(self, cfg: dict[str, Any], api_key: str, max_retries: int = 3):
        super().__init__(cfg, max_retries)
        import anthropic

        self._anthropic = anthropic
        self.model = cfg.get("model", "claude-sonnet-5-5")
        self.client = anthropic.Anthropic(api_key=api_key, timeout=float(cfg.get("timeout_s", 120)), max_retries=2)
        self.price_in = float(cfg.get("price_usd_per_mtok_in", 2.0))
        self.price_out = float(cfg.get("price_usd_per_mtok_out", 10.0))
        self.usd_to_eur = float(cfg.get("usd_to_eur", 0.92))
        # optional request features; switched off automatically if the model rejects them
        self.use_schema = True
        self.effort = cfg.get("effort")
        self.thinking = cfg.get("thinking")
        self.temperature = cfg.get("temperature")

    def _raw(self, system: str, user_text: str, images: list[bytes], schema: dict[str, Any], call: str) -> tuple[str, int, int]:
        content: list[dict[str, Any]] = []
        for img in images:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64(img)}})
        content.append({"type": "text", "text": user_text})
        for _ in range(4):  # adaptive: drop optional features the model does not accept
            kwargs: dict[str, Any] = {
                "model": self.model,
                "max_tokens": int(self.cfg.get("max_tokens", 8000)),
                "system": system,
                "messages": [{"role": "user", "content": content}],
            }
            output_config: dict[str, Any] = {}
            if self.use_schema:
                output_config["format"] = {"type": "json_schema", "schema": schema}
            if self.effort:
                output_config["effort"] = self.effort
            if output_config:
                kwargs["output_config"] = output_config
            if self.thinking:
                kwargs["thinking"] = {"type": self.thinking}
            if self.temperature is not None:
                kwargs["extra_body"] = {"temperature": self.temperature}
            try:
                resp = self.client.messages.create(**kwargs)
            except self._anthropic.AuthenticationError as e:
                raise AIError("The Claude API key was rejected. Check ANTHROPIC_API_KEY in .env.") from e
            except self._anthropic.BadRequestError as e:
                msg = str(e).lower()
                if "temperature" in msg and self.temperature is not None:
                    self.temperature = None
                    continue
                if "thinking" in msg and self.thinking:
                    self.thinking = None
                    continue
                if "effort" in msg and self.effort:
                    self.effort = None
                    continue
                if ("schema" in msg or "output_config" in msg or "format" in msg) and self.use_schema:
                    self.use_schema = False  # fall back to prompt + validation
                    continue
                raise
            if resp.stop_reason == "refusal":
                raise AIError("The model declined to answer this request.")
            text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", "") == "text")
            u = resp.usage
            return text, int(u.input_tokens or 0), int(u.output_tokens or 0)
        raise AIError("Claude request could not be configured for this model.")
