"""REST API endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select

from .config import settings
from .db import session_scope
from .models import AuditLog, Group, GroupMember

log = structlog.get_logger()
router = APIRouter()
_bearer = HTTPBearer()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user_id(
    creds: HTTPAuthorizationCredentials = Depends(_bearer),
) -> int:
    payload = _decode_token(creds.credentials)
    user_id = payload.get("user_id")
    if not isinstance(user_id, int):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
    return user_id


def create_access_token(user_id: int, expires_minutes: int = 60 * 24) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GroupOut(BaseModel):
    id: int
    title: str
    plan: str
    is_active: bool
    rules_text: str
    action_thresholds: dict[str, Any]
    mute_duration_minutes: int

    model_config = {"from_attributes": True}


class GroupPatch(BaseModel):
    rules_text: str | None = None
    action_thresholds: dict[str, Any] | None = None
    mute_duration_minutes: int | None = None


class AuditLogOut(BaseModel):
    id: int
    user_id: int
    message_text: str
    verdict_category: str
    verdict_severity: str
    verdict_confidence: float
    verdict_reason: str
    action_taken: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _get_group_for_user(group_id: int, user_id: int) -> Group:
    """Fetch a group, raising 404/403 as appropriate."""
    async with session_scope() as session:
        group = await session.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")

        # check user is owner or member
        res = await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
            )
        )
        member = res.scalar_one_or_none()
        is_owner = group.owner_user_id == user_id
        if not is_owner and member is None:
            raise HTTPException(status_code=403, detail="Access denied")

        return group


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/api/groups", response_model=list[GroupOut])
async def list_groups(user_id: int = Depends(get_current_user_id)) -> list[GroupOut]:
    async with session_scope() as session:
        # groups where user is owner
        res_owner = await session.execute(
            select(Group).where(Group.owner_user_id == user_id)
        )
        owner_groups = list(res_owner.scalars().all())

        # groups where user is a member
        res_member = await session.execute(
            select(Group)
            .join(GroupMember, Group.id == GroupMember.group_id)
            .where(GroupMember.user_id == user_id)
        )
        member_groups = list(res_member.scalars().all())

        # deduplicate
        seen: set[int] = set()
        groups = []
        for g in owner_groups + member_groups:
            if g.id not in seen:
                seen.add(g.id)
                groups.append(g)

    return [GroupOut.model_validate(g) for g in groups]


@router.get("/api/groups/{group_id}", response_model=dict[str, Any])
async def get_group(
    group_id: int,
    user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    group = await _get_group_for_user(group_id, user_id)

    async with session_scope() as session:
        res = await session.execute(
            select(AuditLog)
            .where(AuditLog.group_id == group_id)
            .order_by(AuditLog.created_at.desc())
            .limit(20)
        )
        logs = list(res.scalars().all())

    return {
        "group": GroupOut.model_validate(group),
        "recent_audit": [AuditLogOut.model_validate(l) for l in logs],
    }


@router.patch("/api/groups/{group_id}", response_model=GroupOut)
async def patch_group(
    group_id: int,
    patch: GroupPatch,
    user_id: int = Depends(get_current_user_id),
) -> GroupOut:
    await _get_group_for_user(group_id, user_id)

    async with session_scope() as session:
        group = await session.get(Group, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="Group not found")

        if patch.rules_text is not None:
            if group.plan == "free":
                raise HTTPException(status_code=403, detail="Custom rules require Pro plan")
            group.rules_text = patch.rules_text
        if patch.action_thresholds is not None:
            group.action_thresholds = patch.action_thresholds
        if patch.mute_duration_minutes is not None:
            group.mute_duration_minutes = patch.mute_duration_minutes

    return GroupOut.model_validate(group)


@router.get("/api/groups/{group_id}/stats")
async def group_stats(
    group_id: int,
    window: str = "24h",
    user_id: int = Depends(get_current_user_id),
) -> dict[str, Any]:
    await _get_group_for_user(group_id, user_id)

    windows = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}
    hours = windows.get(window, 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    async with session_scope() as session:
        res = await session.execute(
            select(AuditLog).where(
                AuditLog.group_id == group_id,
                AuditLog.created_at >= cutoff,
            )
        )
        logs = list(res.scalars().all())

    by_category: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    by_action: dict[str, int] = {}
    for entry in logs:
        by_category[entry.verdict_category] = by_category.get(entry.verdict_category, 0) + 1
        by_severity[entry.verdict_severity] = by_severity.get(entry.verdict_severity, 0) + 1
        by_action[entry.action_taken] = by_action.get(entry.action_taken, 0) + 1

    return {
        "window": window,
        "total": len(logs),
        "violations": sum(1 for l in logs if l.verdict_category != "ok"),
        "by_category": by_category,
        "by_severity": by_severity,
        "by_action": by_action,
    }


@router.post("/stripe/webhook", status_code=200)
async def stripe_webhook(request: Request) -> dict[str, str]:
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    try:
        from .stripe_handler import process_webhook_event
        await process_webhook_event(payload, sig)
    except Exception as e:
        log.error("stripe_webhook_error", err=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    return {"status": "ok"}
