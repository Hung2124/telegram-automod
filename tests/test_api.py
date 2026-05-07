"""Tests for the REST API endpoints."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from automod.api import create_access_token, router
from automod.models import AuditLog, Group, GroupMember, User


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _token(user_id: int) -> str:
    return create_access_token(user_id)


@pytest.fixture
def app():
    return _build_test_app()


@pytest.mark.asyncio
async def test_list_groups_empty(app, db_session) -> None:
    token = _token(999)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_groups_as_owner(app, db_session) -> None:
    g = Group(id=-500, title="MyGroup", owner_user_id=1, plan="free")
    db_session.add(g)
    await db_session.commit()

    token = _token(1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["id"] == -500
    assert data[0]["title"] == "MyGroup"


@pytest.mark.asyncio
async def test_list_groups_as_member(app, db_session) -> None:
    g = Group(id=-501, title="MemberGroup", owner_user_id=99, plan="free")
    u = User(id=2, first_name="User2")
    db_session.add_all([g, u])
    await db_session.flush()
    m = GroupMember(group_id=-501, user_id=2, role="member")
    db_session.add(m)
    await db_session.commit()

    token = _token(2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert any(g["id"] == -501 for g in data)


@pytest.mark.asyncio
async def test_get_group_detail(app, db_session) -> None:
    g = Group(id=-502, title="DetailGroup", owner_user_id=3, plan="pro")
    u = User(id=3, first_name="Owner3")
    db_session.add_all([g, u])
    await db_session.flush()
    log = AuditLog(
        group_id=-502,
        user_id=3,
        message_text="test msg",
        verdict_category="spam",
        verdict_severity="high",
        verdict_confidence=0.9,
        verdict_reason="reason",
        action_taken="delete",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(log)
    await db_session.commit()

    token = _token(3)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/api/groups/-502", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["group"]["title"] == "DetailGroup"
    assert len(data["recent_audit"]) == 1
    assert data["recent_audit"][0]["verdict_category"] == "spam"


@pytest.mark.asyncio
async def test_get_group_not_found(app, db_session) -> None:
    token = _token(1)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups/-9999", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_group_forbidden(app, db_session) -> None:
    g = Group(id=-503, title="OtherGroup", owner_user_id=88, plan="free")
    db_session.add(g)
    await db_session.commit()

    # User 5 is not owner and not a member
    token = _token(5)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups/-503", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_group_mute_duration(app, db_session) -> None:
    g = Group(id=-504, title="PatchGroup", owner_user_id=4, plan="pro")
    db_session.add(g)
    await db_session.commit()

    token = _token(4)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/groups/-504",
            headers={"Authorization": f"Bearer {token}"},
            json={"mute_duration_minutes": 30},
        )
    assert resp.status_code == 200
    assert resp.json()["mute_duration_minutes"] == 30


@pytest.mark.asyncio
async def test_patch_group_rules_free_plan_rejected(app, db_session) -> None:
    g = Group(id=-505, title="FreeGroup", owner_user_id=6, plan="free")
    db_session.add(g)
    await db_session.commit()

    token = _token(6)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/groups/-505",
            headers={"Authorization": f"Bearer {token}"},
            json={"rules_text": "no spam"},
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_patch_group_rules_pro_plan_ok(app, db_session) -> None:
    g = Group(id=-506, title="ProGroup", owner_user_id=7, plan="pro")
    db_session.add(g)
    await db_session.commit()

    token = _token(7)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/groups/-506",
            headers={"Authorization": f"Bearer {token}"},
            json={"rules_text": "no spam allowed"},
        )
    assert resp.status_code == 200
    assert resp.json()["rules_text"] == "no spam allowed"


@pytest.mark.asyncio
async def test_group_stats(app, db_session) -> None:
    g = Group(id=-507, title="StatsGroup", owner_user_id=8, plan="free")
    u = User(id=8, first_name="User8")
    db_session.add_all([g, u])
    await db_session.flush()

    for i in range(3):
        db_session.add(AuditLog(
            group_id=-507,
            user_id=8,
            message_text=f"msg {i}",
            verdict_category="spam",
            verdict_severity="high",
            verdict_confidence=0.9,
            verdict_reason="spam",
            action_taken="delete",
            created_at=datetime.now(timezone.utc),
        ))
    await db_session.commit()

    token = _token(8)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/groups/-507/stats",
            headers={"Authorization": f"Bearer {token}"},
            params={"window": "24h"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 3
    assert data["by_category"]["spam"] == 3


@pytest.mark.asyncio
async def test_unauthorized_request(app) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups")
    assert resp.status_code in (401, 403)  # HTTPBearer returns 403 or 401 when no credentials


@pytest.mark.asyncio
async def test_expired_token(app) -> None:
    """Expired JWT token should return 401."""
    import jwt
    from datetime import datetime, timezone, timedelta
    from automod.config import settings
    expired_payload = {
        "user_id": 1,
        "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
    }
    expired_token = jwt.encode(expired_payload, settings.secret_key, algorithm="HS256")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups", headers={"Authorization": f"Bearer {expired_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_invalid_token(app) -> None:
    """Completely invalid JWT token should return 401."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups", headers={"Authorization": "Bearer not_a_valid_jwt"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_missing_user_id(app) -> None:
    """JWT token without user_id field should return 401."""
    import jwt
    from automod.config import settings
    bad_payload = {"sub": "something_else"}
    bad_token = jwt.encode(bad_payload, settings.secret_key, algorithm="HS256")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/groups", headers={"Authorization": f"Bearer {bad_token}"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_patch_group_action_thresholds(app, db_session) -> None:
    """PATCH /api/groups/{id} can update action_thresholds."""
    g = Group(id=-510, title="ThreshGroup", owner_user_id=11, plan="pro")
    db_session.add(g)
    await db_session.commit()

    token = _token(11)
    new_thresholds = {"high": "delete_and_mute", "medium": "delete", "low": "noop"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            "/api/groups/-510",
            headers={"Authorization": f"Bearer {token}"},
            json={"action_thresholds": new_thresholds},
        )
    assert resp.status_code == 200
    assert resp.json()["action_thresholds"] == new_thresholds


@pytest.mark.asyncio
async def test_group_stats_7d_window(app, db_session) -> None:
    """Stats endpoint supports 7d window."""
    g = Group(id=-511, title="StatsGroup7d", owner_user_id=12, plan="free")
    db_session.add(g)
    await db_session.commit()

    token = _token(12)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/api/groups/-511/stats",
            headers={"Authorization": f"Bearer {token}"},
            params={"window": "7d"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["window"] == "7d"
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_create_access_token_and_decode() -> None:
    """create_access_token creates a valid decodable token."""
    from automod.api import create_access_token, _decode_token
    token = create_access_token(42)
    payload = _decode_token(token)
    assert payload["user_id"] == 42


@pytest.mark.asyncio
async def test_stripe_webhook_invalid_sig(app) -> None:
    import stripe

    def mock_construct_event(payload, sig, secret):
        raise stripe.error.SignatureVerificationError("bad sig", sig)

    with patch("stripe.Webhook.construct_event", side_effect=mock_construct_event):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/stripe/webhook",
                content=b"{}",
                headers={"stripe-signature": "bad_sig"},
            )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_stripe_webhook_valid(app, db_session) -> None:
    g = Group(id=-508, title="G", owner_user_id=1, plan="free")
    db_session.add(g)
    await db_session.commit()

    event = {
        "id": "evt_api_test_1",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "-508",
                "customer": "cus_api",
                "subscription": "sub_api",
            }
        },
    }

    def mock_construct_event(payload, sig, secret):
        return event

    with patch("stripe.Webhook.construct_event", side_effect=mock_construct_event):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/stripe/webhook",
                content=json.dumps(event).encode(),
                headers={"stripe-signature": "t=123,v1=abc"},
            )
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
