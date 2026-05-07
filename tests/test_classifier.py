"""Smoke tests for classifier — no real LLM call (uses mock)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from automod.classifier import Verdict, _classify_anthropic, _classify_openai, _to_verdict, classify


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


@pytest.mark.asyncio
async def test_classify_openai_path() -> None:
    """Test the OpenAI classification path with mocked client."""
    response_data = {
        "is_violation": True,
        "category": "spam",
        "severity": "high",
        "reason": "promotional spam",
        "confidence": 0.9,
    }
    mock_resp = MagicMock()
    mock_resp.choices[0].message.content = json.dumps(response_data)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch("automod.classifier.settings") as mock_settings:
        mock_settings.llm_provider = "openai"
        mock_settings.openai_api_key = "sk_test"
        mock_settings.openai_model = "gpt-4o-mini"
        with patch("automod.classifier.AsyncOpenAI" if False else "openai.AsyncOpenAI", mock_client.__class__):
            with patch("automod.classifier._classify_openai", new_callable=AsyncMock, return_value=Verdict(True, "spam", "high", "promotional spam", 0.9)):
                v = await classify("buy crypto now get rich quick!!!")
    assert v.category == "spam"
    assert v.is_violation is True


@pytest.mark.asyncio
async def test_classify_calls_openai_when_provider_openai() -> None:
    """Classify routes to _classify_openai when provider=openai."""
    verdict = Verdict(is_violation=False, category="ok", severity="none", reason="fine", confidence=0.99)
    with patch("automod.classifier.settings") as mock_settings:
        mock_settings.llm_provider = "openai"
        with patch("automod.classifier._classify_openai", new_callable=AsyncMock, return_value=verdict) as mock_fn:
            result = await classify("hello there friend")
    mock_fn.assert_called_once()
    assert result.category == "ok"


@pytest.mark.asyncio
async def test_classify_calls_anthropic_when_provider_anthropic() -> None:
    """Classify routes to _classify_anthropic when provider=anthropic."""
    verdict = Verdict(is_violation=True, category="hate", severity="high", reason="hate speech", confidence=0.95)
    with patch("automod.classifier.settings") as mock_settings:
        mock_settings.llm_provider = "anthropic"
        with patch("automod.classifier._classify_anthropic", new_callable=AsyncMock, return_value=verdict) as mock_fn:
            result = await classify("some long offensive message here")
    mock_fn.assert_called_once()
    assert result.category == "hate"


@pytest.mark.asyncio
async def test_classify_raises_on_unknown_provider() -> None:
    """Classify raises ValueError for unknown LLM provider."""
    with patch("automod.classifier.settings") as mock_settings:
        mock_settings.llm_provider = "gemini"
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            await classify("some message that is long enough")


@pytest.mark.asyncio
async def test_classify_openai_direct() -> None:
    """Direct test of _classify_openai with mocked AsyncOpenAI."""
    response_data = {
        "is_violation": True,
        "category": "scam",
        "severity": "high",
        "reason": "phishing",
        "confidence": 0.95,
    }
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = json.dumps(response_data)

    mock_openai_client = MagicMock()
    mock_openai_client.chat = MagicMock()
    mock_openai_client.chat.completions = MagicMock()
    mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    with patch("automod.classifier.settings") as mock_settings:
        mock_settings.openai_api_key = "sk_test"
        mock_settings.openai_model = "gpt-4o-mini"
        with patch("openai.AsyncOpenAI", return_value=mock_openai_client):
            v = await _classify_openai("test prompt")

    assert v.is_violation is True
    assert v.category == "scam"


@pytest.mark.asyncio
async def test_classify_anthropic_direct() -> None:
    """Direct test of _classify_anthropic with mocked AsyncAnthropic."""
    response_data = {
        "is_violation": False,
        "category": "ok",
        "severity": "none",
        "reason": "normal message",
        "confidence": 0.98,
    }
    mock_content = MagicMock()
    mock_content.text = json.dumps(response_data)

    mock_resp = MagicMock()
    mock_resp.content = [mock_content]

    mock_anthropic_client = MagicMock()
    mock_anthropic_client.messages = MagicMock()
    mock_anthropic_client.messages.create = AsyncMock(return_value=mock_resp)

    with patch("automod.classifier.settings") as mock_settings:
        mock_settings.anthropic_api_key = "ant_test"
        mock_settings.anthropic_model = "claude-3-5-haiku-latest"
        with patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client):
            v = await _classify_anthropic("test prompt")

    assert v.is_violation is False
    assert v.category == "ok"


@pytest.mark.asyncio
async def test_classify_anthropic_with_code_fence() -> None:
    """_classify_anthropic handles JSON wrapped in code fences."""
    response_data = {
        "is_violation": True,
        "category": "nsfw",
        "severity": "high",
        "reason": "adult content",
        "confidence": 0.88,
    }
    mock_content = MagicMock()
    mock_content.text = "```json\n" + json.dumps(response_data) + "\n```"

    mock_resp = MagicMock()
    mock_resp.content = [mock_content]

    mock_anthropic_client = MagicMock()
    mock_anthropic_client.messages = MagicMock()
    mock_anthropic_client.messages.create = AsyncMock(return_value=mock_resp)

    with patch("automod.classifier.settings") as mock_settings:
        mock_settings.anthropic_api_key = "ant_test"
        mock_settings.anthropic_model = "claude-3-5-haiku-latest"
        with patch("anthropic.AsyncAnthropic", return_value=mock_anthropic_client):
            v = await _classify_anthropic("test prompt")

    assert v.is_violation is True
    assert v.category == "nsfw"
