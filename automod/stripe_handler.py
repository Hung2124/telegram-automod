"""Stripe billing integration."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import stripe
import structlog

from .config import settings
from .db import session_scope
from .models import Group, StripeEvent

log = structlog.get_logger()


def _stripe_client() -> None:
    stripe.api_key = settings.stripe_secret_key


async def create_checkout_session(
    group_id: int,
    user_id: int,
    price_id: str,
) -> str:
    """Create a Stripe Checkout Session and return the URL."""
    _stripe_client()

    def _create() -> Any:
        return stripe.checkout.Session.create(
            mode="subscription",
            line_items=[{"price": price_id, "quantity": 1}],
            success_url=settings.stripe_success_url + f"?group_id={group_id}",
            cancel_url=settings.stripe_cancel_url,
            metadata={"group_id": str(group_id), "user_id": str(user_id)},
            client_reference_id=str(group_id),
        )

    session = await asyncio.to_thread(_create)
    return str(session.url)


async def process_webhook_event(payload_bytes: bytes, sig_header: str) -> None:
    """Verify Stripe signature and process the event idempotently."""
    _stripe_client()

    def _construct() -> Any:
        return stripe.Webhook.construct_event(
            payload_bytes, sig_header, settings.stripe_webhook_secret
        )

    event = await asyncio.to_thread(_construct)
    event_id: str = event["id"]
    event_type: str = event["type"]

    async with session_scope() as session:
        existing = await session.get(StripeEvent, event_id)
        if existing is not None:
            log.info("stripe_event_duplicate", event_id=event_id)
            return

        # Record event
        session.add(StripeEvent(
            id=event_id,
            type=event_type,
            payload=dict(event),
            processed_at=datetime.now(timezone.utc),
        ))

        if event_type == "checkout.session.completed":
            await _handle_checkout_completed(session, event["data"]["object"])
        elif event_type == "customer.subscription.deleted":
            await _handle_subscription_deleted(session, event["data"]["object"])
        else:
            log.info("stripe_event_unhandled", event_type=event_type)


async def _handle_checkout_completed(session: Any, checkout_session: Any) -> None:
    group_id_str = checkout_session.get("client_reference_id") or (
        checkout_session.get("metadata") or {}
    ).get("group_id")
    if not group_id_str:
        log.warning("checkout_completed_no_group_id")
        return

    group_id = int(group_id_str)
    group = await session.get(Group, group_id)
    if group is None:
        log.warning("checkout_completed_group_not_found", group_id=group_id)
        return

    group.plan = "pro"
    group.stripe_customer_id = checkout_session.get("customer")
    group.stripe_subscription_id = checkout_session.get("subscription")
    log.info("group_upgraded_to_pro", group_id=group_id)


async def _handle_subscription_deleted(session: Any, subscription: Any) -> None:
    sub_id = subscription.get("id")
    if not sub_id:
        return

    from sqlalchemy import select
    res = await session.execute(
        select(Group).where(Group.stripe_subscription_id == sub_id)
    )
    group = res.scalar_one_or_none()
    if group is None:
        log.warning("subscription_deleted_group_not_found", sub_id=sub_id)
        return

    group.plan = "free"
    group.stripe_subscription_id = None
    log.info("group_downgraded_to_free", group_id=group.id)
