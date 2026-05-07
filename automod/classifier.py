"""LLM-powered message classifier.

Sends each message to an LLM with a JSON-output prompt asking:
  is_violation, category, severity, reason

Categories: spam, scam, nsfw, hate, off_topic, advertising, ok
Severity:   low, medium, high
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from .config import settings

Category = Literal["spam", "scam", "nsfw", "hate", "off_topic", "advertising", "ok"]
Severity = Literal["low", "medium", "high", "none"]


@dataclass
class Verdict:
    is_violation: bool
    category: Category
    severity: Severity
    reason: str
    confidence: float  # 0.0 - 1.0


SYSTEM_PROMPT = """You are a Telegram group moderator AI. Classify the message.

Return STRICT JSON: {"is_violation": bool, "category": str, "severity": str, "reason": str, "confidence": float}

Categories: spam, scam, nsfw, hate, off_topic, advertising, ok
Severity:   none (ok), low, medium, high

Be strict on: crypto pump-and-dump, fake giveaway scams, phishing links, NSFW content, hate speech, repeated promotional spam.
Be lenient on: casual off-topic chat, mild profanity, jokes."""


async def classify(message_text: str, group_rules: str = "") -> Verdict:
    """Classify a single message. Returns Verdict.

    For empty / very short messages, returns ok without calling LLM (cost saving).
    """
    text = (message_text or "").strip()
    if len(text) < 3:
        return Verdict(False, "ok", "none", "too short", 1.0)

    user_prompt = f"GROUP RULES (if any):\n{group_rules or '(default)'}\n\nMESSAGE:\n{text}"

    if settings.llm_provider == "xiaomi":
        return await _classify_xiaomi(user_prompt)
    elif settings.llm_provider == "openai":
        return await _classify_openai(user_prompt)
    elif settings.llm_provider == "anthropic":
        return await _classify_anthropic(user_prompt)
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


async def _classify_xiaomi(user_prompt: str) -> Verdict:
    """Xiaomi MiMo via OpenAI-compatible endpoint."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=settings.xiaomi_api_key,
        base_url=settings.xiaomi_base_url,
    )
    resp = await client.chat.completions.create(
        model=settings.xiaomi_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt + "\n\nReturn ONLY the JSON object, no prose."},
        ],
        temperature=0.0,
        max_tokens=200,
    )
    raw = (resp.choices[0].message.content or "{}").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json\n")
    data = json.loads(raw)
    return _to_verdict(data)


async def _classify_openai(user_prompt: str) -> Verdict:
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    resp = await client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
        max_tokens=200,
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    return _to_verdict(data)


async def _classify_anthropic(user_prompt: str) -> Verdict:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.anthropic_model,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt + "\n\nReturn ONLY the JSON object, no prose."}],
        max_tokens=200,
        temperature=0.0,
    )
    raw = resp.content[0].text.strip()
    # Anthropic may wrap in code fences
    if raw.startswith("```"):
        raw = raw.split("```")[1].lstrip("json\n")
    data = json.loads(raw)
    return _to_verdict(data)


def _to_verdict(d: dict) -> Verdict:
    return Verdict(
        is_violation=bool(d.get("is_violation", False)),
        category=d.get("category", "ok"),  # type: ignore[arg-type]
        severity=d.get("severity", "none"),  # type: ignore[arg-type]
        reason=str(d.get("reason", "")),
        confidence=float(d.get("confidence", 0.5)),
    )
