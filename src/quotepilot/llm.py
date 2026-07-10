"""Thin Qwen client: OpenAI-compatible calls with retries, JSON extraction,
schema-validated structured output, and per-run token accounting."""

from __future__ import annotations

import json
import re
import time
from typing import Type, TypeVar

from openai import APIConnectionError, APIStatusError, BadRequestError, OpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from . import config

T = TypeVar("T", bound=BaseModel)

_client: OpenAI | None = None


def client() -> OpenAI:
    global _client
    if _client is None:
        if not config.QWEN_API_KEY:
            raise RuntimeError("QWEN_API_KEY is not set (see .env.example)")
        _client = OpenAI(api_key=config.QWEN_API_KEY, base_url=config.QWEN_BASE_URL)
    return _client


class UsageTracker:
    """Accumulates token usage per model for one autopilot run."""

    def __init__(self) -> None:
        self.by_model: dict[str, dict[str, int]] = {}

    def add(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        slot = self.by_model.setdefault(
            model, {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}
        )
        slot["prompt_tokens"] += prompt_tokens
        slot["completion_tokens"] += completion_tokens
        slot["calls"] += 1


def chat(
    model: str,
    system: str,
    user: str,
    *,
    usage: UsageTracker | None = None,
    temperature: float = 0.3,
    max_tokens: int = 2000,
    json_mode: bool = False,
    retries: int = 3,
) -> str:
    """One chat completion with exponential-backoff retries."""
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    kwargs: dict = {}
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            resp = client().chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs,
            )
            if usage and resp.usage:
                usage.add(model, resp.usage.prompt_tokens, resp.usage.completion_tokens)
            return resp.choices[0].message.content or ""
        except BadRequestError:
            # Some models reject response_format — retry once without it.
            if json_mode and "response_format" in kwargs:
                kwargs.pop("response_format")
                continue
            raise
        except (RateLimitError, APIConnectionError, APIStatusError) as err:
            last_err = err
            time.sleep(2**attempt)
    raise RuntimeError(f"Qwen call failed after {retries} retries: {last_err}")


_JSON_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> str:
    """Pull a JSON object out of a possibly fenced / chatty response."""
    match = _JSON_FENCE.search(text)
    if match:
        return match.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text.strip()


def structured(
    model: str,
    system: str,
    user: str,
    schema: Type[T],
    *,
    usage: UsageTracker | None = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    validation_retries: int = 2,
) -> T:
    """Chat call whose output must validate against a Pydantic schema.

    On validation failure, the error is fed back to the model for repair.
    """
    schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
    sys_prompt = (
        f"{system}\n\nRespond with ONLY a JSON object that validates against this "
        f"JSON Schema (no prose, no markdown fences):\n{schema_json}"
    )
    prompt = user
    last_error = ""
    for _ in range(validation_retries + 1):
        raw = chat(
            model,
            sys_prompt,
            prompt,
            usage=usage,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
        )
        try:
            return schema.model_validate_json(extract_json(raw))
        except (ValidationError, ValueError) as err:
            last_error = str(err)
            prompt = (
                f"{user}\n\nYour previous JSON was invalid:\n{last_error}\n"
                "Return corrected JSON only."
            )
    raise RuntimeError(f"Structured output failed validation: {last_error}")
