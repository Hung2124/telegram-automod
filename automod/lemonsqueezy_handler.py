"""LemonSqueezy billing integration (replaces stripe_handler.py)."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from .config import settings
from .db import session_scope
from .models import Group, StripeEvent  # reuse StripeEvent table for LS events

log = structlog.get_logger()

LS_API_BASE = "https://api.lemonsqueezy.com/v1"


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
    }


async def create_checkout_url(
    group_id: int,
    user_id: int,
    plan: str,  # "pro" or "enterprise"
) -> str:
    """Create a LemonSqueezy checkout and return the URL."""
    if plan == "pro":
        variant_id = settings.lemonsqueezy_pro_variant_id
    elif plan == "enterprise":
        variant_id = settings.lemonsqueezy_enterprise_variant_id
    else:
        raise ValueError(f"Unknown plan: {plan}")

    if not variant_id:
        raise RuntimeError(f"LemonSqueezy variant ID not configured for plan={plan}")

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "checkout_data": {
                    "custom": {
                        "group_id": str(group_id),
                        "user_id": str(user_id),
                        "plan": plan,
                    }
                },
                "product_options": {
                    "redirect_url": f"{settings.telegram_webhook_url}/payment/success?group_id={group_id}",
                },
            },
            "relationships": {
                "store": {"data": {"type": "stores", "id": settings.lemonsqueezy_store_id}},
                "variant": {"data": {"type": "variants", "id": variant_id}},
            },
        }
    }

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            f"{LS_API_BASE}/checkouts",
            headers=_headers(),
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()

    url: str = data["data"]["attributes"]["url"]
    log.info("lemonsqueezy_checkout_created", group_id=group_id, plan=plan, url=url)
    return url


def verify_webhook_signature(payload_bytes: bytes, sig_header: str) -> bool:
    """Verify HMAC-SHA256 signature from LemonSqueezy webhook."""
    secret = settings.lemonsqueezy_webhook_secret.encode()
    expected = hmac.new(secret, payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig_header)


async def process_webhook_event(payload_bytes: bytes, sig_header: str) -> None:
    """Verify LS signature and process the event idempotently."""
    if not verify_webhook_signature(payload_bytes, sig_header):
        log.warning("lemonsqueezy_invalid_signature")
        raise ValueError("Invalid webhook signature")

    event: dict[str, Any] = json.loads(payload_bytes)
    event_name: str = event.get("meta", {}).get("event_name", "")
    # Use order/subscription ID as idempotency key
    event_id = str(
        event.get("data", {}).get("id", "")
        or event.get("meta", {}).get("custom_data", {}).get("group_id", "unknown")
    ) + "_" + event_name

    async with session_scope() as session:
        existing = await session.get(StripeEvent, event_id)
        if existing is not None:
            log.info("ls_event_duplicate", event_id=event_id)
            return

        session.add(
            StripeEvent(
                id=event_id,
                type=event_name,
                payload=event,
                processed_at=datetime.now(timezone.utc),
            )
        )

        if event_name == "subscription_created":
            await _handle_subscription_created(session, event)
        elif event_name == "subscription_payment_success":
            await _handle_subscription_payment_success(session, event)
        elif event_name in ("subscription_cancelled", "subscription_expired"):
            await _handle_subscription_cancelled(session, event)
        elif event_name == "order_created":
            await _handle_order_created(session, event)
        else:
            log.info("ls_event_unhandled", event_name=event_name)


async def _get_group_from_event(event: dict[str, Any]) -> tuple[int | None, str | None]:
    """Extract group_id and plan from LS event custom_data."""
    meta = event.get("meta", {})
    custom = meta.get("custom_data", {})
    group_id_str = custom.get("group_id")
    plan = custom.get("plan", "pro")
    if not group_id_str:
        return None, None
    return int(group_id_str), plan


async def _handle_subscription_created(session: Any, event: dict[str, Any]) -> None:
    group_id, plan = await _get_group_from_event(event)
    if group_id is None:
        log.warning("ls_subscription_created_no_group")
        return

    group = await session.get(Group, group_id)
    if group is None:
        log.warning("ls_subscription_created_group_not_found", group_id=group_id)
        return

    sub_data = event.get("data", {}).get("attributes", {})
    group.plan = plan or "pro"
    group.stripe_subscription_id = str(event["data"]["id"])
    group.stripe_customer_id = str(sub_data.get("customer_id", ""))
    log.info("ls_subscription_activated", group_id=group_id, plan=group.plan)


async def _handle_subscription_payment_success(session: Any, event: dict[str, Any]) -> None:
    """Keep subscription active on renewal."""
    group_id, plan = await _get_group_from_event(event)
    if group_id is None:
        return
    group = await session.get(Group, group_id)
    if group:
        group.plan = plan or group.plan
        log.info("ls_subscription_renewed", group_id=group_id)


async def _handle_subscription_cancelled(session: Any, event: dict[str, Any]) -> None:
    group_id, _ = await _get_group_from_event(event)
    if group_id is None:
        return
    group = await session.get(Group, group_id)
    if group:
        group.plan = "free"
        group.stripe_subscription_id = None
        log.info("ls_subscription_cancelled", group_id=group_id)


async def _handle_order_created(session: Any, event: dict[str, Any]) -> None:
    """One-time purchase fallback (not used for subscriptions)."""
    group_id, plan = await _get_group_from_event(event)
    log.info("ls_order_created", group_id=group_id, plan=plan)
