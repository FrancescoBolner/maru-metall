"""AI provider interface + the strict call runner shared by every provider.

Every AI call:
  1. builds its prompt from a versioned prompt file (config/prompts/<name>.v<N>.md),
  2. asks for structured output against ONE schema (ai/schemas.py),
  3. validates the response (schema + semantic checks: allowed keys, snippets really in the source),
  4. retries up to `max_retries` times with the validation errors fed back,
  5. is logged to logs/ai_calls.jsonl (input summary, raw output, validation, attempts, duration, tokens, cost),
  6. is cached by a hash of provider + model + prompt version + input, so re-runs are near-instant.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, ValidationError

from ..settings import CACHE_DIR, CONFIG_DIR, LOGS_DIR
from .schemas import (FACT_CATALOG, CorrectionProposal, DocumentExtraction, DrawingExtraction, FileClassification,
                      GuidelinesUpdate, MissingPrediction, strict_schema)

AI_LOG = LOGS_DIR / "ai_calls.jsonl"
AI_CACHE = CACHE_DIR / "ai"
AI_CACHE.mkdir(parents=True, exist_ok=True)
_log_lock = threading.Lock()


class AIError(RuntimeError):
    """Raised when a file still fails after all retries (the pipeline marks the file and continues)."""


@dataclass
class Usage:
    calls: int = 0
    cache_hits: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_eur: float = 0.0
    seconds: float = 0.0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, **kw: Any) -> None:
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, getattr(self, k) + v)

    def as_dict(self) -> dict[str, Any]:
        return {"calls": self.calls, "cache_hits": self.cache_hits, "failures": self.failures,
                "input_tokens": self.input_tokens, "output_tokens": self.output_tokens,
                "cost_eur": round(self.cost_eur, 4), "seconds": round(self.seconds, 2)}


@dataclass
class CallCtx:
    project_id: str = ""
    run_id: str = ""
    file_id: Optional[str] = None
    file_name: Optional[str] = None
    usage: Optional[Usage] = None


# ----------------------------------------------------------------------------------------------
def load_prompt(name: str) -> tuple[str, str]:
    """Highest version of config/prompts/<name>.v<N>.md -> (text without front matter, 'name.vN')."""
    best = None
    for p in (CONFIG_DIR / "prompts").glob(f"{name}.v*.md"):
        m = re.search(r"\.v(\d+)\.md$", p.name)
        if m and (best is None or int(m.group(1)) > best[0]):
            best = (int(m.group(1)), p)
    if best is None:
        raise FileNotFoundError(f"prompt {name} not found")
    text = best[1].read_text(encoding="utf-8")
    text = re.sub(r"^---.*?---\s*", "", text, flags=re.S)
    return text, f"{name}.v{best[0]}"


def fill(template: str, **kw: Any) -> str:
    out = template
    for k, v in kw.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def norm_ws(s: str) -> str:
    s = s.replace(" ", " ").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def snippet_in(snippet: str, text: str) -> bool:
    if not snippet.strip():
        return False
    s, t = norm_ws(snippet), norm_ws(text)
    if s in t:
        return True
    # tolerate the model trimming / joining across line breaks: all words in order
    words = [w for w in re.findall(r"[\w%./+-]+", s) if len(w) > 1]
    if len(words) >= 3:
        pos = 0
        for w in words:
            i = t.find(w, pos)
            if i < 0:
                return False
            pos = i + len(w)
        return True
    return False


def catalog_text() -> str:
    return "\n".join(f"- {k}: {label} — {desc}" for k, (grp, label, desc) in FACT_CATALOG.items())


def log_call(entry: dict[str, Any]) -> None:
    with _log_lock:
        with AI_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def read_log(limit: int = 300, project_id: Optional[str] = None) -> list[dict[str, Any]]:
    if not AI_LOG.exists():
        return []
    lines = AI_LOG.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if project_id and e.get("project_id") != project_id:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


# ----------------------------------------------------------------------------------------------
def validate_document(model: DocumentExtraction | DrawingExtraction, source_text: Optional[str]) -> list[str]:
    errs = []
    for i, f in enumerate(model.facts):
        if f.key not in FACT_CATALOG:
            errs.append(f"facts[{i}].key '{f.key}' is not an allowed key")
        if not f.value.strip():
            errs.append(f"facts[{i}] ({f.key}) has an empty value: leave it out instead")
        if not f.snippet.strip():
            errs.append(f"facts[{i}] ({f.key}) has no snippet")
        elif source_text is not None and not snippet_in(f.snippet, source_text):
            errs.append(f"facts[{i}] ({f.key}) snippet is not in the document: '{f.snippet[:80]}'")
        if not 0 <= f.confidence <= 1:
            errs.append(f"facts[{i}].confidence must be between 0 and 1")
    for name in ("scope_items", "requirements", "flags"):
        for i, it in enumerate(getattr(model, name)):
            sn = getattr(it, "snippet", "")
            if source_text is not None and sn and not snippet_in(sn, source_text):
                errs.append(f"{name}[{i}] snippet is not in the document: '{sn[:80]}'")
    return errs


def drop_invalid(model: DocumentExtraction | DrawingExtraction, source_text: Optional[str]) -> int:
    """After the last retry: keep the valid parts, drop items that still fail (never keep an unsupported value)."""
    before = len(model.facts) + len(model.scope_items) + len(model.requirements) + len(model.flags)
    model.facts = [f for f in model.facts if f.key in FACT_CATALOG and f.value.strip() and f.snippet.strip()
                   and (source_text is None or snippet_in(f.snippet, source_text))]
    for name in ("scope_items", "requirements", "flags"):
        setattr(model, name, [it for it in getattr(model, name)
                              if source_text is None or not it.snippet or snippet_in(it.snippet, source_text)])
    after = len(model.facts) + len(model.scope_items) + len(model.requirements) + len(model.flags)
    return before - after


class AIProvider:
    """Interface. Implementations: ClaudeProvider (API), LocalProvider (OpenAI-compatible endpoint), OfflineProvider."""

    name = "base"
    model = ""
    sends_data_off_machine = False

    def __init__(self, cfg: dict[str, Any], max_retries: int = 3):
        self.cfg = cfg
        self.max_retries = max_retries

    # The six calls ------------------------------------------------------------------------
    def classify_file(self, file_name: str, file_kind: str, content: str, ctx: CallCtx) -> FileClassification:
        raise NotImplementedError

    def extract_from_document(self, file_name: str, file_kind: str, text: str, ctx: CallCtx,
                              page_note: str = "", guidelines: str = "") -> DocumentExtraction:
        raise NotImplementedError

    def extract_from_drawing(self, file_name: str, image_png: bytes, context: str, ctx: CallCtx,
                             guidelines: str = "") -> DrawingExtraction:
        raise NotImplementedError

    def predict_missing(self, missing: list[dict[str, Any]], context: str, ctx: CallCtx) -> MissingPrediction:
        raise NotImplementedError

    def interpret_correction(self, text: str, targets: list[dict[str, Any]], ctx: CallCtx) -> CorrectionProposal:
        raise NotImplementedError

    def update_guidelines(self, current: str, corrections: list[dict[str, Any]], project: str, ctx: CallCtx) -> GuidelinesUpdate:
        raise NotImplementedError

    def describe(self) -> dict[str, Any]:
        return {"provider": self.name, "model": self.model, "sends_data_off_machine": self.sends_data_off_machine}


class LLMProvider(AIProvider):
    """Shared prompt building + strict call loop for model-backed providers."""

    price_in = 0.0
    price_out = 0.0
    usd_to_eur = 1.0

    # implemented by subclasses: returns (text, input_tokens, output_tokens)
    def _raw(self, system: str, user_text: str, images: list[bytes], schema: dict[str, Any], call: str) -> tuple[str, int, int]:
        raise NotImplementedError

    def _system(self, guidelines: str = "") -> str:
        from ..settings import company_config
        tmpl, _ = load_prompt("system")
        g = f"\nEstimator guidelines learned from approved projects:\n{guidelines}" if guidelines.strip() else ""
        return fill(tmpl, company=company_config().get("legal_name", "the fabricator"), guidelines=g)

    def _structured(self, call: str, model_cls: type[BaseModel], user_text: str, ctx: CallCtx,
                    images: Optional[list[bytes]] = None, guidelines: str = "",
                    validator: Optional[Callable[[Any], list[str]]] = None,
                    finalize: Optional[Callable[[Any], int]] = None) -> Any:
        images = images or []
        system = self._system(guidelines)
        _, prompt_version = load_prompt(call)
        schema = strict_schema(model_cls)
        h = hashlib.sha256()
        for part in (self.name, self.model, prompt_version, system, user_text):
            h.update(part.encode("utf-8", errors="ignore"))
        for img in images:
            h.update(hashlib.sha256(img).digest())
        key = h.hexdigest()
        cache_file = AI_CACHE / f"{key}.json"
        entry: dict[str, Any] = {
            "ts": datetime.now().isoformat(timespec="seconds"), "id": uuid.uuid4().hex[:12], "provider": self.name,
            "model": self.model, "call": call, "prompt_version": prompt_version, "project_id": ctx.project_id,
            "run_id": ctx.run_id, "file": ctx.file_name,
            "input_summary": {"chars": len(user_text), "images": len(images),
                              "image_bytes": sum(len(i) for i in images), "preview": user_text[:300]},
            "attempts": [],
        }
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                result = model_cls.model_validate(data["result"])
                entry.update(status="cache", duration_s=0.0, cost_eur=0.0, input_tokens=0, output_tokens=0)
                log_call(entry)
                if ctx.usage:
                    ctx.usage.add(cache_hits=1)
                return result
            except Exception:
                cache_file.unlink(missing_ok=True)

        t_all = time.time()
        feedback = ""
        last_valid: Optional[Any] = None
        tok_in = tok_out = 0
        for attempt in range(1, self.max_retries + 1):
            t0 = time.time()
            prompt = user_text + (f"\n\nYour previous answer was rejected. Fix these problems and return the full JSON again:\n{feedback}" if feedback else "")
            att: dict[str, Any] = {"n": attempt}
            try:
                raw, ti, to = self._raw(system, prompt, images, schema, call)
                tok_in += ti
                tok_out += to
                att.update(input_tokens=ti, output_tokens=to, raw=raw[:20000])
            except AIError:
                raise
            except Exception as e:  # noqa: BLE001 - provider/network errors are retried
                att.update(error=f"{type(e).__name__}: {e}"[:500], duration_s=round(time.time() - t0, 2))
                entry["attempts"].append(att)
                feedback = "The request failed; answer again with valid JSON only."
                continue
            errors: list[str] = []
            parsed = None
            try:
                txt = raw.strip()
                if txt.startswith("```"):
                    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt)
                data = json.loads(txt)
                parsed = model_cls.model_validate(data)
            except json.JSONDecodeError as e:
                errors.append(f"Not valid JSON: {e}")
            except ValidationError as e:
                errors.extend(f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:20])
            if parsed is not None and validator:
                errors.extend(validator(parsed))
                last_valid = parsed
            att.update(errors=errors, duration_s=round(time.time() - t0, 2))
            entry["attempts"].append(att)
            if parsed is not None and not errors:
                return self._finish(entry, parsed, cache_file, t_all, tok_in, tok_out, ctx, "ok")
            feedback = "\n".join(f"- {e}" for e in errors[:20])
        if last_valid is not None and finalize is not None:
            dropped = finalize(last_valid)
            entry["dropped_items"] = dropped
            return self._finish(entry, last_valid, cache_file, t_all, tok_in, tok_out, ctx, "ok-after-filtering")
        self._finish(entry, None, None, t_all, tok_in, tok_out, ctx, "failed")
        raise AIError(f"The AI could not produce a valid answer after {self.max_retries} attempts")

    def _finish(self, entry: dict[str, Any], result: Any, cache_file: Optional[Path], t_all: float,
                tok_in: int, tok_out: int, ctx: CallCtx, status: str) -> Any:
        cost = (tok_in * self.price_in + tok_out * self.price_out) / 1e6 * self.usd_to_eur
        dur = time.time() - t_all
        entry.update(status=status, duration_s=round(dur, 2), input_tokens=tok_in, output_tokens=tok_out,
                     cost_eur=round(cost, 5))
        log_call(entry)
        if ctx.usage:
            ctx.usage.add(calls=1, input_tokens=tok_in, output_tokens=tok_out, cost_eur=cost, seconds=dur,
                          failures=1 if status == "failed" else 0)
        if result is not None and cache_file is not None:
            cache_file.write_text(json.dumps({"result": result.model_dump(), "meta": {k: entry[k] for k in ("provider", "model", "call", "prompt_version", "ts")}},
                                             ensure_ascii=False), encoding="utf-8")
        return result

    # ---- the six calls -------------------------------------------------------------------
    def classify_file(self, file_name, file_kind, content, ctx):
        tmpl, _ = load_prompt("classify_file")
        user = fill(tmpl, file_name=file_name, file_kind=file_kind, content=content[: self.cfg.get("max_chars", 24000)])
        return self._structured("classify_file", FileClassification, user, ctx)

    def extract_from_document(self, file_name, file_kind, text, ctx, page_note="", guidelines=""):
        tmpl, _ = load_prompt("extract_document")
        text = text[: self.cfg.get("max_chars", 24000)]
        user = fill(tmpl, file_name=file_name, file_kind=file_kind, page_note=page_note, catalog=catalog_text(), content=text)
        return self._structured("extract_document", DocumentExtraction, user, ctx, guidelines=guidelines,
                                validator=lambda m: validate_document(m, text),
                                finalize=lambda m: drop_invalid(m, text))

    def extract_from_drawing(self, file_name, image_png, context, ctx, guidelines=""):
        tmpl, _ = load_prompt("extract_drawing")
        user = fill(tmpl, file_name=file_name, catalog=catalog_text(), content=context[:4000])
        return self._structured("extract_drawing", DrawingExtraction, user, ctx, images=[image_png], guidelines=guidelines,
                                validator=lambda m: validate_document(m, None),
                                finalize=lambda m: drop_invalid(m, None))

    def predict_missing(self, missing, context, ctx):
        tmpl, _ = load_prompt("predict_missing")
        lines = [f"- {m['key']}: allowed {m.get('allowed') or 'any'} / unit {m.get('unit') or '-'} / default {m.get('default')}"
                 for m in missing]
        user = fill(tmpl, missing="\n".join(lines), content=context[:12000])
        allowed = {m["key"]: m.get("allowed") for m in missing}

        def check(p: MissingPrediction) -> list[str]:
            errs = []
            for i, pr in enumerate(p.predictions):
                if pr.key not in allowed:
                    errs.append(f"predictions[{i}].key '{pr.key}' was not requested")
                elif allowed[pr.key] and pr.value not in [str(a) for a in allowed[pr.key]]:
                    errs.append(f"predictions[{i}].value '{pr.value}' is not one of {allowed[pr.key]}")
                if not pr.reasoning.strip():
                    errs.append(f"predictions[{i}] has no reasoning")
                if re.search(r"(€|eur\b|euro)", pr.value, re.I):
                    errs.append(f"predictions[{i}] contains a price: predictions must never be euro values")
            return errs
        return self._structured("predict_missing", MissingPrediction, user, ctx, validator=check)

    def interpret_correction(self, text, targets, ctx):
        tmpl, _ = load_prompt("interpret_correction")
        tl = "\n".join(f"{t['id']} | {t['label']} | {t.get('current')} | {t.get('allowed') or 'number' if t.get('numeric') else t.get('allowed') or 'text'}"
                       for t in targets)
        user = fill(tmpl, text=text, targets=tl)
        tmap = {t["id"]: t for t in targets}

        def check(p: CorrectionProposal) -> list[str]:
            errs = []
            for i, ch in enumerate(p.changes):
                t = tmap.get(ch.target)
                if t is None:
                    errs.append(f"changes[{i}].target '{ch.target}' is not in the target list")
                    continue
                if t.get("allowed") and ch.new_value not in [str(a) for a in t["allowed"]]:
                    errs.append(f"changes[{i}].new_value '{ch.new_value}' not allowed for {ch.target}: {t['allowed']}")
                if t.get("numeric"):
                    try:
                        float(str(ch.new_value).replace(",", "."))
                    except ValueError:
                        errs.append(f"changes[{i}].new_value must be a number for {ch.target}")
            return errs
        return self._structured("interpret_correction", CorrectionProposal, user, ctx, validator=check)

    def update_guidelines(self, current, corrections, project, ctx):
        tmpl, _ = load_prompt("update_guidelines")
        user = fill(tmpl, guidelines_current=current or "(none yet)", project=project,
                    corrections=json.dumps(corrections, ensure_ascii=False, indent=1)[:12000])
        return self._structured("update_guidelines", GuidelinesUpdate, user, ctx)


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")
