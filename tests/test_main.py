"""Tests for main.py FastAPI app: /webhook and /healthz."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def _make_fake_ptb() -> MagicMock:
    """Build a stubbed PTB Application."""
    fake_ptb = MagicMock()
    fake_ptb.bot = MagicMock()
    fake_ptb.process_update = AsyncMock()
    fake_ptb.initialize = AsyncMock()
    fake_ptb.start = AsyncMock()
    fake_ptb.stop = AsyncMock()
    fake_ptb.shutdown = AsyncMock()
    fake_ptb.bot.set_webhook = AsyncMock()
    return fake_ptb


def _build_app_with_mock_ptb() -> tuple[FastAPI, MagicMock]:
    """Build a FastAPI app using a stubbed PTB Application."""
    from automod import main as main_module
    fake_ptb = _make_fake_ptb()
    with patch("telegram.Update.de_json", return_value=MagicMock()):
        app = main_module.create_fastapi(fake_ptb)
    return app, fake_ptb


@pytest.mark.asyncio
async def test_healthz() -> None:
    app, _ = _build_app_with_mock_ptb()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


@pytest.mark.asyncio
async def test_webhook_no_secret_accepts_anything() -> None:
    app, ptb = _build_app_with_mock_ptb()
    transport = ASGITransport(app=app)
    with patch("automod.main.settings") as mock_settings:
        mock_settings.telegram_webhook_secret = ""
        with patch("automod.main.Update") as mock_update:
            mock_update.de_json.return_value = MagicMock()
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post("/webhook", json={"update_id": 1})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    ptb.process_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_webhook_secret_mismatch_returns_401() -> None:
    app, _ = _build_app_with_mock_ptb()
    transport = ASGITransport(app=app)
    with patch("automod.main.settings") as mock_settings:
        mock_settings.telegram_webhook_secret = "topsecret"
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/webhook",
                json={"update_id": 1},
                headers={"x-telegram-bot-api-secret-token": "wrong"},
            )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_webhook_secret_match_succeeds() -> None:
    app, ptb = _build_app_with_mock_ptb()
    transport = ASGITransport(app=app)
    with patch("automod.main.settings") as mock_settings:
        mock_settings.telegram_webhook_secret = "topsecret"
        with patch("automod.main.Update") as mock_update:
            mock_update.de_json.return_value = MagicMock()
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await client.post(
                    "/webhook",
                    json={"update_id": 1},
                    headers={"x-telegram-bot-api-secret-token": "topsecret"},
                )
    assert resp.status_code == 200
    ptb.process_update.assert_awaited_once()


def test_build_application_smoke() -> None:
    """Ensure build_application wires handlers without exception."""
    from automod.main import build_application

    with patch("automod.main.settings.telegram_bot_token", "1234567890:fake"):
        ptb = build_application()
    # Should have command handlers registered
    assert len(ptb.handlers[0]) >= 5
