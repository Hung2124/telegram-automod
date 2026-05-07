"""Tests for Stripe webhook handler."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from automod.models import Group, StripeEvent


def _make_stripe_event(event_id: str, event_type: str, data_obj: dict) -> dict:
    return {
        "id": event_id,
        "type": event_type,
        "data": {"object": data_obj},
    }


@pytest.mark.asyncio
async def test_checkout_completed_upgrades_group(db_session) -> None:
    group = Group(id=-300, title="G", owner_user_id=1, plan="free")
    db_session.add(group)
    await db_session.commit()

    event = _make_stripe_event(
        "evt_checkout_1",
        "checkout.session.completed",
        {
            "id": "cs_test_1",
            "client_reference_id": "-300",
            "customer": "cus_test123",
            "subscription": "sub_test123",
            "metadata": {"group_id": "-300"},
        },
    )
    payload = json.dumps(event).encode()

    def mock_construct_event(payload, sig, secret):
        return event

    with patch("stripe.Webhook.construct_event", side_effect=mock_construct_event):
        from automod.stripe_handler import process_webhook_event
        await process_webhook_event(payload, "t=123,v1=abc")

    db_session.expire_all()
    res = await db_session.execute(select(Group).where(Group.id == -300))
    updated = res.scalar_one()
    assert updated.plan == "pro"
    assert updated.stripe_customer_id == "cus_test123"
    assert updated.stripe_subscription_id == "sub_test123"


@pytest.mark.asyncio
async def test_subscription_deleted_downgrades_group(db_session) -> None:
    group = Group(
        id=-301, title="G", owner_user_id=1,
        plan="pro",
        stripe_subscription_id="sub_to_delete",
    )
    db_session.add(group)
    await db_session.commit()

    event = _make_stripe_event(
        "evt_sub_delete_1",
        "customer.subscription.deleted",
        {"id": "sub_to_delete", "status": "canceled"},
    )
    payload = json.dumps(event).encode()

    def mock_construct_event(payload, sig, secret):
        return event

    with patch("stripe.Webhook.construct_event", side_effect=mock_construct_event):
        from automod.stripe_handler import process_webhook_event
        await process_webhook_event(payload, "t=123,v1=abc")

    db_session.expire_all()
    res = await db_session.execute(select(Group).where(Group.id == -301))
    updated = res.scalar_one()
    assert updated.plan == "free"
    assert updated.stripe_subscription_id is None


@pytest.mark.asyncio
async def test_idempotent_duplicate_event(db_session) -> None:
    """Processing the same event twice should not fail or duplicate."""
    group = Group(id=-302, title="G", owner_user_id=1, plan="free")
    db_session.add(group)
    await db_session.commit()

    event = _make_stripe_event(
        "evt_dup_1",
        "checkout.session.completed",
        {
            "client_reference_id": "-302",
            "customer": "cus_dup",
            "subscription": "sub_dup",
        },
    )
    payload = json.dumps(event).encode()

    def mock_construct_event(payload, sig, secret):
        return event

    with patch("stripe.Webhook.construct_event", side_effect=mock_construct_event):
        from automod.stripe_handler import process_webhook_event
        await process_webhook_event(payload, "sig1")
        await process_webhook_event(payload, "sig1")  # second call should be idempotent

    # Should only have one StripeEvent record
    res = await db_session.execute(select(StripeEvent).where(StripeEvent.id == "evt_dup_1"))
    events = res.scalars().all()
    assert len(events) == 1


@pytest.mark.asyncio
async def test_stripe_event_recorded(db_session) -> None:
    group = Group(id=-303, title="G", owner_user_id=1, plan="free")
    db_session.add(group)
    await db_session.commit()

    event = _make_stripe_event(
        "evt_record_1",
        "checkout.session.completed",
        {"client_reference_id": "-303", "customer": "cus_r", "subscription": "sub_r"},
    )
    payload = json.dumps(event).encode()

    def mock_construct_event(payload, sig, secret):
        return event

    with patch("stripe.Webhook.construct_event", side_effect=mock_construct_event):
        from automod.stripe_handler import process_webhook_event
        await process_webhook_event(payload, "sig")

    db_session.expire_all()
    res = await db_session.execute(select(StripeEvent).where(StripeEvent.id == "evt_record_1"))
    evt = res.scalar_one_or_none()
    assert evt is not None
    assert evt.type == "checkout.session.completed"


@pytest.mark.asyncio
async def test_unhandled_event_type_recorded(db_session) -> None:
    event = _make_stripe_event("evt_unknown_1", "invoice.paid", {"id": "inv_1"})
    payload = json.dumps(event).encode()

    def mock_construct_event(payload, sig, secret):
        return event

    with patch("stripe.Webhook.construct_event", side_effect=mock_construct_event):
        from automod.stripe_handler import process_webhook_event
        await process_webhook_event(payload, "sig")

    db_session.expire_all()
    res = await db_session.execute(select(StripeEvent).where(StripeEvent.id == "evt_unknown_1"))
    evt = res.scalar_one_or_none()
    assert evt is not None


@pytest.mark.asyncio
async def test_create_checkout_session() -> None:
    mock_session = MagicMock()
    mock_session.url = "https://checkout.stripe.com/pay/cs_test"

    def mock_create(**kwargs):
        return mock_session

    with patch("stripe.checkout.Session.create", side_effect=mock_create):
        from automod.stripe_handler import create_checkout_session
        url = await create_checkout_session(-400, 1, "price_test")

    assert url == "https://checkout.stripe.com/pay/cs_test"
