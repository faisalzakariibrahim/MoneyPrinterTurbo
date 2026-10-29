"""Claude client helpers: forced-tool structured output, plain text, retries, caching."""

from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Any

import anthropic
from loguru import logger

from app.longform.settings import get_settings

WEB_SEARCH_TOOL = os.environ.get("LF_WEB_SEARCH_TOOL", "web_search_20260209")


class LLMError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def client() -> anthropic.Anthropic:
    key = get_settings().anthropic_api_key
    if not key:
        raise LLMError("ANTHROPIC_API_KEY is not configured on the worker")
    return anthropic.Anthropic(api_key=key, max_retries=4, timeout=600)


def cached_system(*blocks: str) -> list[dict]:
    """System prompt blocks; the last one is marked for prompt caching so chapter
    calls that share the niche profile + outline only pay for it once."""
    out = [{"type": "text", "text": b} for b in blocks if b]
    if out:
        out[-1]["cache_control"] = {"type": "ephemeral"}
    return out


def _create(**kwargs: Any):
    last: Exception | None = None
    for attempt in range(3):
        try:
            return client().messages.create(**kwargs)
        except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            last = e
            wait = 5 * (attempt + 1)
            logger.warning(f"claude call failed ({type(e).__name__}); retrying in {wait}s")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            raise LLMError(f"Claude API error {e.status_code}") from e
    raise LLMError("Claude API unavailable after retries") from last


def structured(
    *,
    model: str,
    system: list[dict] | str,
    prompt: str,
    tool_name: str,
    tool_description: str,
    schema: dict,
    max_tokens: int = 8000,
) -> dict:
    """Force Claude to answer by calling a single tool whose input is our JSON schema."""
    resp = _create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        tools=[{"name": tool_name, "description": tool_description, "input_schema": schema}],
        tool_choice={"type": "tool", "name": tool_name},
    )
    for block in resp.content:
        if getattr(block, "type", "") == "tool_use" and block.name == tool_name:
            return dict(block.input)
    raise LLMError("model did not return structured output")


def text(
    *,
    model: str,
    system: list[dict] | str,
    messages: list[dict],
    max_tokens: int = 8000,
    tools: list[dict] | None = None,
) -> tuple[str, str]:
    """Return (text, stop_reason). Only text blocks are joined (tool/search blocks skipped)."""
    kwargs: dict[str, Any] = dict(model=model, max_tokens=max_tokens, system=system, messages=messages)
    if tools:
        kwargs["tools"] = tools
    resp = _create(**kwargs)
    parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
    return "".join(parts).strip(), resp.stop_reason or ""
