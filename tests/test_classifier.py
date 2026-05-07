"""Smoke tests for classifier — no real LLM call (uses mock)."""
from __future__ import annotations

import pytest

from automod.classifier import Verdict, _to_verdict, classify


def test_to_verdict_defaults() -> None:
    v = _to_verdict({})
    assert v.is_violation is False
    assert v.category == "ok"
    assert v.severity == "none"


def test_to_verdict_full() -> None:
    v = _to_verdict({
        "is_violation": True,
        "category": "scam",
        "severity": "high",
        "reason": "crypto pump-and-dump pattern",
        "confidence": 0.95,
    })
    assert v.is_violation is True
    assert v.category == "scam"
    assert v.severity == "high"
    assert v.confidence == 0.95


@pytest.mark.asyncio
async def test_classify_short_message_skips_llm() -> None:
    """Messages < 3 chars should return ok without LLM call."""
    v = await classify("hi")
    assert v.is_violation is False
    assert v.category == "ok"
    assert v.confidence == 1.0
