"""Thin wrapper around an LLM provider (Anthropic SDK or OpenAI SDK).

All AI calls in Paperfin funnel through :func:`chat_json` so we get:

* a single place to swap providers (``LLM_PROVIDER`` in ``.env``)
* tenacity-backed retries for transient failures
* schema-in-prompt + tolerant JSON parsing (works with either wire protocol
  and with third-party gateways that may not honor structured-output
  parameters)
* a Pydantic-model validation step so downstream code sees structured data

Two wire protocols are supported:

============= =============================== ==============================
provider      SDK used                        Endpoint shape
============= =============================== ==============================
``anthropic`` official ``anthropic`` SDK      POST /v1/messages
``openai``    official ``openai`` SDK         POST /v1/chat/completions
============= =============================== ==============================

Set ``LLM_PROVIDER`` in ``.env`` to pick one. Credentials are taken from
``LLM_API_KEY`` / ``LLM_BASE_URL`` / ``LLM_MODEL`` (with back-compat
fallback to the older ``ANTHROPIC_*`` names — see ``config.py``).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import get_settings

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# --- Errors -----------------------------------------------------------------


class LLMNotConfiguredError(RuntimeError):
    """Raised when the LLM is called without an API key configured."""


class LLMResponseError(RuntimeError):
    """Raised when the LLM response cannot be parsed into the expected shape."""


# --- Client cache -----------------------------------------------------------

# One client per provider, lazily initialised. Rebuilt whenever settings
# change via ``reset_client`` (useful in tests).
_clients: dict[str, Any] = {}


def reset_client() -> None:
    _clients.clear()


def _get_anthropic_client():
    from anthropic import Anthropic  # local import — optional dep per provider

    if "anthropic" not in _clients:
        s = get_settings()
        if not s.resolved_llm_api_key:
            raise LLMNotConfiguredError(
                "LLM_API_KEY (or ANTHROPIC_API_KEY) is not set. "
                "Copy .env.example to .env and fill it in."
            )
        kwargs: dict[str, Any] = {"api_key": s.resolved_llm_api_key}
        if s.resolved_llm_base_url:
            kwargs["base_url"] = s.resolved_llm_base_url
        _clients["anthropic"] = Anthropic(**kwargs)
    return _clients["anthropic"]


def _get_openai_client():
    from openai import OpenAI  # local import — optional dep per provider

    if "openai" not in _clients:
        s = get_settings()
        if not s.resolved_llm_api_key:
            raise LLMNotConfiguredError(
                "LLM_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        kwargs: dict[str, Any] = {"api_key": s.resolved_llm_api_key}
        if s.resolved_llm_base_url:
            kwargs["base_url"] = s.resolved_llm_base_url
        _clients["openai"] = OpenAI(**kwargs)
    return _clients["openai"]


# --- JSON extraction --------------------------------------------------------

# Some models (and especially third-party shims) wrap JSON in ```json fences
# or sprinkle explanatory prose around it. Be tolerant.
_FENCE_RE = re.compile(r"```(?:json)?\s*(?P<body>\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json_payload(raw: str) -> str:
    """Return the best-effort JSON substring from a model response."""
    stripped = raw.strip()
    if not stripped:
        return stripped

    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    m = _FENCE_RE.search(stripped)
    if m:
        return m.group("body").strip()

    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = stripped.find(open_ch)
        end = stripped.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            return stripped[start : end + 1]

    return stripped


# --- Provider-specific adapters ---------------------------------------------


def _call_anthropic(
    *, system: str, user: str, temperature: float, max_tokens: int, model: str
) -> str:
    from anthropic import APIError, APIStatusError

    client = _get_anthropic_client()
    try:
        message = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except APIStatusError as exc:
        log.error("LLM API status error (%s): %s", exc.status_code, exc)
        raise LLMResponseError(
            f"LLM request rejected ({exc.status_code}): {exc}"
        ) from exc
    except APIError as exc:
        raise LLMResponseError(f"LLM request failed: {exc}") from exc
    except Exception as exc:
        raise LLMResponseError(f"LLM request failed: {exc}") from exc

    parts = [b.text for b in message.content if getattr(b, "type", "") == "text"]
    return "".join(parts).strip()


def _call_openai(
    *, system: str, user: str, temperature: float, max_tokens: int, model: str
) -> str:
    from openai import APIError, APIStatusError

    client = _get_openai_client()
    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            # Ask for a JSON object where the endpoint supports it; backends
            # that don't honor this field just ignore it, and we still have
            # the schema-in-prompt + tolerant extractor as defence in depth.
            response_format={"type": "json_object"},
        )
    except APIStatusError as exc:
        log.error("LLM API status error (%s): %s", exc.status_code, exc)
        raise LLMResponseError(
            f"LLM request rejected ({exc.status_code}): {exc}"
        ) from exc
    except APIError as exc:
        raise LLMResponseError(f"LLM request failed: {exc}") from exc
    except Exception as exc:
        raise LLMResponseError(f"LLM request failed: {exc}") from exc

    return (resp.choices[0].message.content or "").strip()


_PROVIDERS = {
    "anthropic": _call_anthropic,
    "openai": _call_openai,
}


# --- Main entry point -------------------------------------------------------


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((LLMResponseError,)),
    before_sleep=before_sleep_log(log, logging.WARNING),
    reraise=True,
)
def chat_json(
    *,
    system: str,
    user: str,
    schema: type[T],
    temperature: float = 0.2,
    max_tokens: int = 2048,
) -> T:
    """Run a chat completion and parse the response into ``schema``.

    The system prompt is augmented with the schema's JSON fields so any
    model — Claude, GPT-4, DeepSeek, a local model behind LiteLLM — has a
    strong signal about the desired shape, even when running against
    gateways that don't implement structured-output constraints.
    """
    settings = get_settings()
    provider = (settings.llm_provider or "anthropic").lower()
    call = _PROVIDERS.get(provider)
    if call is None:
        raise LLMNotConfiguredError(
            f"Unknown LLM_PROVIDER={provider!r}. "
            f"Supported: {', '.join(_PROVIDERS)}"
        )

    model = settings.resolved_llm_model
    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    augmented_system = (
        f"{system}\n\n"
        "Respond with a SINGLE JSON object that strictly matches this JSON schema. "
        "Output ONLY the JSON — no prose, no markdown fences, no commentary.\n"
        f"Schema: {schema_hint}"
    )

    log.debug(
        "LLM call provider=%s model=%s approx_prompt_chars=%d",
        provider,
        model,
        len(augmented_system) + len(user),
    )

    content = call(
        system=augmented_system,
        user=user,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
    )

    if not content:
        raise LLMResponseError("LLM returned an empty response")

    payload_str = _extract_json_payload(content)
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(f"LLM returned non-JSON: {content[:400]}") from exc

    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise LLMResponseError(
            f"LLM response did not match schema {schema.__name__}: {exc}"
        ) from exc
