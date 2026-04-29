"""Thin wrapper around the Anthropic (or Anthropic-compatible) SDK.

All AI calls in Paperfin funnel through ``chat_json`` so we get:

* a single place to swap models (``Settings.anthropic_model``)
* tenacity-backed retries for transient failures
* schema-in-prompt + tolerant JSON parsing (works on real Claude
  **and** on third-party Anthropic-compatible gateways like MiniMax
  that don't honor the ``response_format`` family of parameters)
* a Pydantic model validation step so downstream code sees structured data

Point ``ANTHROPIC_BASE_URL`` at the gateway; leave it unset to hit the
official Anthropic API. The ``chat_json(system, user, schema)`` contract
is unchanged from the previous OpenAI-backed implementation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TypeVar

from anthropic import Anthropic, APIError, APIStatusError
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


class LLMNotConfiguredError(RuntimeError):
    """Raised when the LLM is called without an API key configured."""


class LLMResponseError(RuntimeError):
    """Raised when the LLM response cannot be parsed into the expected shape."""


_client: Anthropic | None = None


def get_client() -> Anthropic:
    """Return a singleton Anthropic client configured from settings."""
    global _client
    if _client is None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise LLMNotConfiguredError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and fill it in."
            )
        kwargs: dict[str, object] = {"api_key": settings.anthropic_api_key}
        if settings.anthropic_base_url:
            kwargs["base_url"] = settings.anthropic_base_url
        _client = Anthropic(**kwargs)
    return _client


# --- JSON extraction --------------------------------------------------------

# Some models (and especially third-party shims) wrap JSON in ```json fences or
# sprinkle explanatory prose before/after. Be tolerant.
_FENCE_RE = re.compile(r"```(?:json)?\s*(?P<body>\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def _extract_json_payload(raw: str) -> str:
    """Return the best-effort JSON substring from a model response.

    Strategy:
    1. If the response is already valid JSON, return it.
    2. If it's wrapped in a ```json ... ``` fence, extract the body.
    3. Otherwise, grab the outermost ``{...}`` or ``[...]`` slice.
    """
    stripped = raw.strip()
    if not stripped:
        return stripped

    # 1. happy path
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    # 2. fenced block
    m = _FENCE_RE.search(stripped)
    if m:
        return m.group("body").strip()

    # 3. fall back to the outermost braces/brackets
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = stripped.find(open_ch)
        end = stripped.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            return stripped[start : end + 1]

    return stripped  # hand the caller the raw string; json.loads will fail cleanly


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

    The system prompt automatically receives the schema's JSON fields so the
    model has a strong signal about the desired shape, even when running
    against gateways that don't implement response-format constraints.
    """
    settings = get_settings()
    client = get_client()

    schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    augmented_system = (
        f"{system}\n\n"
        "Respond with a SINGLE JSON object that strictly matches this JSON schema. "
        "Output ONLY the JSON — no prose, no markdown fences, no commentary.\n"
        f"Schema: {schema_hint}"
    )

    log.debug(
        "LLM call model=%s approx_prompt_chars=%d",
        settings.anthropic_model,
        len(augmented_system) + len(user),
    )

    try:
        message = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=augmented_system,
            messages=[{"role": "user", "content": user}],
        )
    except APIStatusError as exc:
        # 4xx from the gateway: auth errors, bad model, malformed request.
        # These are not worth retrying — fail fast with a readable error.
        log.error("LLM API status error (%s): %s", exc.status_code, exc)
        raise LLMResponseError(
            f"LLM request rejected ({exc.status_code}): {exc}"
        ) from exc
    except APIError as exc:
        # Connection / timeout / 5xx: let tenacity retry.
        raise LLMResponseError(f"LLM request failed: {exc}") from exc
    except Exception as exc:  # defensive: anything else (DNS, socket, etc.)
        raise LLMResponseError(f"LLM request failed: {exc}") from exc

    # Claude returns ``content`` as a list of blocks. Concatenate every text block.
    text_parts = [
        block.text for block in message.content if getattr(block, "type", "") == "text"
    ]
    content = "".join(text_parts).strip()
    if not content:
        raise LLMResponseError("LLM returned an empty response")

    payload_str = _extract_json_payload(content)
    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError as exc:
        raise LLMResponseError(
            f"LLM returned non-JSON: {content[:400]}"
        ) from exc

    try:
        return schema.model_validate(payload)
    except ValidationError as exc:
        raise LLMResponseError(
            f"LLM response did not match schema {schema.__name__}: {exc}"
        ) from exc
