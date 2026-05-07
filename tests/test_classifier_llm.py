"""Tests for classifier LLM-routing logic with mocked SDK clients."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from automod import classifier as clf


@pytest.mark.asyncio
async def test_classify_openai_path() -> None:
    fake_resp = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=json.dumps({
                        "is_violation": True,
                        "category": "spam",
                        "severity": "medium",
                        "reason": "promo",
                        "confidence": 0.85,
                    })
                )
            )
        ]
    )
    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=fake_resp))
        )
    )
    with patch("openai.AsyncOpenAI", return_value=fake_client):
        with patch.object(clf.settings, "llm_provider", "openai"):
            v = await clf.classify("buy crypto now click here")
    assert v.is_violation is True
    assert v.category == "spam"
    assert v.severity == "medium"
    assert v.confidence == 0.85


@pytest.mark.asyncio
async def test_classify_anthropic_path() -> None:
    fake_resp = SimpleNamespace(
        content=[
            SimpleNamespace(
                text=json.dumps({
                    "is_violation": False,
                    "category": "ok",
                    "severity": "none",
                    "reason": "",
                    "confidence": 0.99,
                })
            )
        ]
    )
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=fake_resp))
    )
    with patch("anthropic.AsyncAnthropic", return_value=fake_client):
        with patch.object(clf.settings, "llm_provider", "anthropic"):
            v = await clf.classify("hello world how is everyone")
    assert v.is_violation is False
    assert v.category == "ok"


@pytest.mark.asyncio
async def test_classify_anthropic_strips_code_fences() -> None:
    raw = "```json\n" + json.dumps({"is_violation": False, "category": "ok"}) + "\n```"
    fake_resp = SimpleNamespace(content=[SimpleNamespace(text=raw)])
    fake_client = SimpleNamespace(
        messages=SimpleNamespace(create=AsyncMock(return_value=fake_resp))
    )
    with patch("anthropic.AsyncAnthropic", return_value=fake_client):
        with patch.object(clf.settings, "llm_provider", "anthropic"):
            v = await clf.classify("regular text here")
    assert v.is_violation is False


@pytest.mark.asyncio
async def test_classify_unknown_provider_raises() -> None:
    with patch.object(clf.settings, "llm_provider", "made_up"):
        with pytest.raises(ValueError):
            await clf.classify("test message body")
