"""Thin OpenAI wrapper: on-disk cache + cumulative token budget."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CACHE_DIR = Path(".llm_cache")
USAGE_FILE = CACHE_DIR / "usage.json"
MAX_TOTAL_TOKENS = int(os.getenv("VERIFIX_MAX_TOTAL_TOKENS", "300000"))


class BudgetExceeded(RuntimeError):
    pass


_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI()  # reads OPENAI_API_KEY from the environment
    return _client


def total_tokens_used() -> int:
    if USAGE_FILE.exists():
        return json.loads(USAGE_FILE.read_text()).get("total_tokens", 0)
    return 0


def _add_usage(n: int) -> None:
    CACHE_DIR.mkdir(exist_ok=True)
    USAGE_FILE.write_text(json.dumps({"total_tokens": total_tokens_used() + n}))


def chat(messages: list[dict], tools: list[dict] | None = None,
         model: str | None = None, temperature: float = 0.0) -> dict:
    """One chat completion with caching. Returns a plain, JSON-serializable dict."""
    model = model or os.getenv("VERIFIX_MODEL", "gpt-4o-mini")
    payload = {"model": model, "messages": messages, "tools": tools, "temperature": temperature}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    CACHE_DIR.mkdir(exist_ok=True)
    path = CACHE_DIR / f"{key}.json"

    if path.exists():
        out = json.loads(path.read_text())
        out["cached"] = True
        return out

    if total_tokens_used() >= MAX_TOTAL_TOKENS:
        raise BudgetExceeded(
            f"Token budget reached ({total_tokens_used()} >= {MAX_TOTAL_TOKENS}). "
            "Raise VERIFIX_MAX_TOTAL_TOKENS in .env only if you checked your balance."
        )

    kwargs = {"model": model, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["parallel_tool_calls"] = False
    if not model.startswith(("gpt-5", "o")):  # reasoning models reject custom temperature
        kwargs["temperature"] = temperature

    resp = _get_client().chat.completions.create(**kwargs)
    msg = resp.choices[0].message
    out = {
        "content": msg.content,
        "tool_calls": [
            {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
            for tc in (msg.tool_calls or [])
        ],
        "prompt_tokens": resp.usage.prompt_tokens,
        "completion_tokens": resp.usage.completion_tokens,
        "model": model,
        "cached": False,
    }
    path.write_text(json.dumps(out))
    _add_usage(resp.usage.prompt_tokens + resp.usage.completion_tokens)
    return out